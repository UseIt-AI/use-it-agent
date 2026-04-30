"""
Tool Use Node - Agent 实现

Planner Only 模式的 Agent：
1. 调用 Planner 进行总体规划
2. 根据规划结果调用 LangChain Tools
3. 收集工具执行结果
4. 判断任务是否完成
"""

import asyncio
from typing import Dict, Any, Optional, AsyncGenerator, List

from langchain_core.tools import BaseTool as LangChainBaseTool

from ...models import (
    AgentContext,
    AgentStep,
    PlannerOutput,
    ToolCallResult,
    ReasoningDeltaEvent,
    PlanCompleteEvent,
    ToolCallEvent,
    ToolResultEvent,
    ErrorEvent,
)
from .planner import ToolUsePlanner
from useit_studio.ai_run.utils.logger_utils import LoggerUtils


logger = LoggerUtils(component_name="ToolUseAgent")


class ToolUseAgent:
    """
    Tool Use Agent - Planner Only 模式
    
    职责：
    1. 调用 Planner 进行总体规划
    2. 根据规划结果直接调用 LangChain Tools（无需 Local Engine）
    3. 收集工具执行结果
    4. 多轮决策直到任务完成
    """
    
    def __init__(
        self,
        planner_model: str = "gpt-4o-mini",
        api_keys: Optional[Dict[str, str]] = None,
        tools: Optional[List[LangChainBaseTool]] = None,
        node_id: str = "",
    ):
        """
        初始化 Tool Use Agent
        
        Args:
            planner_model: Planner 使用的模型
            api_keys: API 密钥字典
            tools: LangChain 工具列表
            node_id: 节点 ID
        """
        self.api_keys = api_keys or {}
        self.tools = tools or []
        self.node_id = node_id
        
        # 创建工具名称到工具的映射
        self.tools_by_name: Dict[str, LangChainBaseTool] = {
            tool.name: tool for tool in self.tools
        }
        
        # 初始化 Planner
        self.planner = ToolUsePlanner(
            model=planner_model,
            api_keys=api_keys,
            tools=self.tools,
            node_id=node_id,
        )
        
        logger.logger.info(
            f"[ToolUseAgent] Initialized with {len(self.tools)} tools: "
            f"{list(self.tools_by_name.keys())}"
        )
    
    def set_node_id(self, node_id: str):
        """更新节点 ID"""
        self.node_id = node_id
        self.planner.set_node_id(node_id)
    
    async def run(
        self,
        user_goal: str = "",
        node_instruction: str = "",
        max_steps: int = 60,
        log_dir: Optional[str] = None,
        history_md: str = "",
        project_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        attached_files_content: str = "",
        attached_files: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        运行决策循环
        
        Args:
            user_goal: 用户输入的宏观目标
            node_instruction: 当前节点的具体指令
            max_steps: 最大步数
            log_dir: 日志目录
            history_md: 工作流历史记录
            project_id: 项目 ID（注入到 tool_args，用于 S3 输出上传、RAG 范围）
            chat_id: 聊天 ID（注入到 tool_args，用于 RAG 范围）
            attached_files_content: 附件文件内容
            attached_files: 附件文件列表（含 local_path 信息，用于 doc_extract 路径解析）
            
        Yields:
            各种事件：
            - {"type": "step_start", "step": int}
            - {"type": "reasoning_delta", ...}
            - {"type": "plan_complete", ...}
            - {"type": "tool_call", ...}
            - {"type": "tool_result", ...}
            - {"type": "task_completed", "summary": str}
            - {"type": "error", ...}
        """
        display_instruction = node_instruction or user_goal
        logger.logger.info(f"[ToolUseAgent] Starting decision loop - Instruction: {display_instruction[:50]}...")
        
        # 构建 attached_file_paths 映射（文件名/路径 → local_path）
        self._attached_file_paths: Dict[str, str] = {}
        for f in (attached_files or []):
            local_path = f.get("local_path", "")
            if local_path:
                # 用 name 和 path 都做映射，方便 LLM 用任意方式引用
                if f.get("name"):
                    self._attached_file_paths[f["name"]] = local_path
                if f.get("path"):
                    self._attached_file_paths[f["path"]] = local_path
                # basename 映射
                import os
                basename = os.path.basename(local_path)
                if basename:
                    self._attached_file_paths[basename] = local_path
        
        if self._attached_file_paths:
            logger.logger.info(f"[ToolUseAgent] Attached file paths: {self._attached_file_paths}")
        
        # 重置 Planner 的消息历史
        self.planner.reset()
        
        # 初始化上下文
        context = AgentContext(
            user_goal=user_goal,
            node_instruction=node_instruction,
            tool_results=[],
            history_md=history_md,
            available_tools=list(self.tools_by_name.keys()),
            attached_files_content=attached_files_content,
        )
        
        for step in range(1, max_steps + 1):
            logger.logger.info(f"[ToolUseAgent] Step {step}/{max_steps}")
            
            yield {"type": "step_start", "step": step}
            
            try:
                # 1. Planner 决策（流式）
                planner_output: Optional[PlannerOutput] = None
                
                async for event in self.planner.plan_streaming(context, log_dir):
                    yield event
                    
                    if event.get("type") == "plan_complete":
                        planner_output = PlannerOutput.from_dict(event.get("content", {}))
                
                if not planner_output:
                    yield ErrorEvent(message="Planner did not return a valid result").to_dict()
                    return
                
                logger.logger.info(
                    f"[ToolUseAgent] Planner decision - Action: {planner_output.next_action}, "
                    f"ToolCalls: {len(planner_output.tool_calls)}, "
                    f"Completed: {planner_output.is_milestone_completed}"
                )
                
                # 2. 检查是否完成
                if planner_output.is_milestone_completed or planner_output.next_action == "stop":
                    yield {
                        "type": "task_completed",
                        "summary": planner_output.completion_summary or "Task completed",
                        "files_to_transfer": planner_output.files_to_transfer,
                        "result_markdown": planner_output.result_markdown,
                        "result_filename": planner_output.result_filename,
                    }
                    return
                
                # 3. 执行工具调用
                if planner_output.tool_calls:
                    for tool_call in planner_output.tool_calls:
                        tool_name = tool_call.get("name", "")
                        tool_args = dict(tool_call.get("args", {}))
                        # 注入 project_id / chat_id（LLM 不提供，由请求上下文传入）
                        if project_id is not None:
                            tool_args["project_id"] = project_id
                        if chat_id is not None:
                            tool_args["chat_id"] = chat_id
                        call_id = tool_call.get("id", f"call_{step}")
                        
                        # 发送 tool_call 事件
                        yield ToolCallEvent(
                            tool_name=tool_name,
                            tool_args=tool_args,
                            call_id=call_id,
                        ).to_dict()
                        
                        # 执行工具（web_search 和 rag_search 使用流式方法，其他工具使用普通方法）
                        if tool_name == "web_search":
                            # web_search 使用流式方法，发送搜索进度事件
                            result = None
                            async for event in self._execute_web_search_streaming(tool_args):
                                if event.get("type") == "tool_result_internal":
                                    # 内部事件，提取结果
                                    result = event["result"]
                                else:
                                    # 搜索进度事件，直接转发给前端
                                    yield event
                            
                            if result is None:
                                result = ToolCallResult(
                                    tool_name=tool_name,
                                    tool_args=tool_args,
                                    result="Error: web_search did not return a result",
                                    success=False,
                                    error="No result returned",
                                )
                        elif tool_name == "rag_search":
                            # rag_search 使用流式方法，发送搜索进度事件
                            result = None
                            async for event in self._execute_rag_search_streaming(tool_args):
                                if event.get("type") == "tool_result_internal":
                                    # 内部事件，提取结果
                                    result = event["result"]
                                else:
                                    # 搜索进度事件，直接转发给前端
                                    yield event
                            
                            if result is None:
                                result = ToolCallResult(
                                    tool_name=tool_name,
                                    tool_args=tool_args,
                                    result="Error: rag_search did not return a result",
                                    success=False,
                                    error="No result returned",
                                )
                        elif tool_name == "doc_extract":
                            # doc_extract 使用流式方法，发送提取进度事件
                            result = None
                            async for event in self._execute_doc_extract_streaming(tool_args):
                                if event.get("type") == "tool_result_internal":
                                    result = event["result"]
                                else:
                                    yield event
                            
                            if result is None:
                                result = ToolCallResult(
                                    tool_name=tool_name,
                                    tool_args=tool_args,
                                    result="Error: doc_extract did not return a result",
                                    success=False,
                                    error="No result returned",
                                )
                        else:
                            # 其他工具使用普通方法
                            result = await self._execute_tool(tool_name, tool_args)
                        
                        # 发送 tool_result 事件（包含结构化数据供前端可视化）
                        yield ToolResultEvent(
                            tool_name=tool_name,
                            result=result.result,
                            success=result.success,
                            call_id=call_id,
                            error=result.error,
                            structured_data=result.structured_data,
                        ).to_dict()
                        
                        # 添加结果到 Planner 的消息历史
                        self.planner.add_tool_result(
                            tool_call_id=call_id,
                            tool_name=tool_name,
                            result=result.result if result.success else f"Error: {result.error}",
                        )
                        
                        # 添加到上下文的工具结果历史
                        context.tool_results.append(result)
                else:
                    # 没有工具调用但也没有完成，可能是错误
                    logger.logger.warning("[ToolUseAgent] No tool calls and not completed")
                    yield ErrorEvent(message="Planner returned no action").to_dict()
                    return
                    
            except Exception as e:
                logger.logger.error(f"[ToolUseAgent] Step {step} failed: {e}", exc_info=True)
                yield ErrorEvent(message=str(e)).to_dict()
                return
        
        # 达到最大步数
        logger.logger.warning(f"[ToolUseAgent] Reached maximum steps {max_steps}")
        yield {"type": "max_steps_reached", "steps": max_steps}
    
    async def _execute_tool(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
    ) -> ToolCallResult:
        """
        执行工具调用
        
        Args:
            tool_name: 工具名称
            tool_args: 工具参数
            
        Returns:
            工具调用结果（web_search 工具会包含 structured_data）
        """
        logger.logger.info(f"[ToolUseAgent] Executing tool: {tool_name} with args: {tool_args}")
        
        tool = self.tools_by_name.get(tool_name)
        if not tool:
            error_msg = f"Tool '{tool_name}' not found. Available tools: {list(self.tools_by_name.keys())}"
            logger.logger.error(f"[ToolUseAgent] {error_msg}")
            return ToolCallResult(
                tool_name=tool_name,
                tool_args=tool_args,
                result="",
                success=False,
                error=error_msg,
            )
        
        try:
            # 特殊处理 web_search 工具：获取结构化数据供前端可视化
            structured_data = None
            if tool_name == "web_search":
                structured_data = await self._execute_web_search_with_structured_data(tool_args)
            
            # 调用工具（支持同步和异步）
            if asyncio.iscoroutinefunction(tool.invoke):
                result = await tool.ainvoke(tool_args)
            else:
                result = tool.invoke(tool_args)
            
            # 确保结果是字符串
            if not isinstance(result, str):
                result = str(result)
            
            logger.logger.info(f"[ToolUseAgent] Tool result: {result[:200]}...")
            
            return ToolCallResult(
                tool_name=tool_name,
                tool_args=tool_args,
                result=result,
                success=True,
                structured_data=structured_data,
            )
            
        except Exception as e:
            error_msg = f"Tool execution failed: {str(e)}"
            logger.logger.error(f"[ToolUseAgent] {error_msg}", exc_info=True)
            return ToolCallResult(
                tool_name=tool_name,
                tool_args=tool_args,
                result="",
                success=False,
                error=error_msg,
            )
    
    async def _execute_web_search_streaming(
        self,
        tool_args: Dict[str, Any],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行 web_search 并流式返回进度事件
        
        这个方法直接调用 WebSearchTool 的 search_streaming 方法，
        流式发送搜索进度事件给前端。
        
        Args:
            tool_args: 工具参数 (query, max_results)
            
        Yields:
            搜索进度事件，最后一个是包含结果的内部事件
        """
        try:
            from ...tools.web_search import WebSearchTool
            
            # 创建 WebSearchTool 实例
            web_search_tool = WebSearchTool(
                api_key=self.api_keys.get("TAVILY_API_KEY", ""),
                openai_api_key=self.api_keys.get("OPENAI_API_KEY", ""),
            )
            
            query = tool_args.get("query", "")
            max_results = tool_args.get("max_results", 5)
            
            # 流式搜索
            final_result = None
            async for event in web_search_tool.search_streaming(query, max_results):
                if event.get("type") == "search_complete":
                    # 搜索完成，构建最终结果
                    result_data = event.get("result", {})
                    text = web_search_tool._format_for_llm(result_data)
                    
                    final_result = ToolCallResult(
                        tool_name="web_search",
                        tool_args=tool_args,
                        result=text,
                        success=True,
                        structured_data={
                            "result_type": "web_search",
                            **result_data,
                        },
                    )
                else:
                    # 进度事件，直接转发
                    yield event
            
            # 返回最终结果（通过内部事件）
            if final_result:
                yield {"type": "tool_result_internal", "result": final_result}
            else:
                yield {
                    "type": "tool_result_internal",
                    "result": ToolCallResult(
                        tool_name="web_search",
                        tool_args=tool_args,
                        result="Error: Search did not complete",
                        success=False,
                        error="No result returned",
                    )
                }
            
        except Exception as e:
            logger.logger.error(f"[ToolUseAgent] web_search streaming failed: {e}", exc_info=True)
            yield {
                "type": "tool_result_internal",
                "result": ToolCallResult(
                    tool_name="web_search",
                    tool_args=tool_args,
                    result="",
                    success=False,
                    error=str(e),
                )
            }
    
    async def _execute_rag_search_streaming(
        self,
        tool_args: Dict[str, Any],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行 rag_search 并流式返回进度事件
        
        这个方法直接调用 RAGTool 的 search_streaming 方法，
        流式发送搜索进度事件给前端。
        
        Args:
            tool_args: 工具参数 (query, top_k, project_id, chat_id, workflow_run_id)
            
        Yields:
            搜索进度事件，最后一个是包含结果的内部事件
        """
        try:
            from ...tools.rag import RAGTool
            
            # 创建 RAGTool 实例
            rag_tool = RAGTool(
                rag_url=self.api_keys.get("RAG_URL", ""),
            )
            
            query = tool_args.get("query", "")
            top_k = tool_args.get("top_k", 5)
            project_id = tool_args.get("project_id")
            chat_id = tool_args.get("chat_id")
            workflow_run_id = tool_args.get("workflow_run_id")
            
            # 流式搜索
            final_result = None
            async for event in rag_tool.search_streaming(
                query=query, 
                top_k=top_k,
                project_id=project_id,
                chat_id=chat_id,
                workflow_run_id=workflow_run_id,
            ):
                if event.get("type") == "rag_complete":
                    # 搜索完成，构建最终结果
                    result_data = event.get("result", {})
                    text = rag_tool._format_for_llm(result_data)
                    
                    final_result = ToolCallResult(
                        tool_name="rag_search",
                        tool_args=tool_args,
                        result=text,
                        success=True,
                        structured_data={
                            "result_type": "rag_search",
                            **result_data,
                        },
                    )
                else:
                    # 进度事件，直接转发
                    yield event
            
            # 返回最终结果（通过内部事件）
            if final_result:
                yield {"type": "tool_result_internal", "result": final_result}
            else:
                yield {
                    "type": "tool_result_internal",
                    "result": ToolCallResult(
                        tool_name="rag_search",
                        tool_args=tool_args,
                        result="Error: RAG search did not complete",
                        success=False,
                        error="No result returned",
                    )
                }
            
        except Exception as e:
            logger.logger.error(f"[ToolUseAgent] rag_search streaming failed: {e}", exc_info=True)
            yield {
                "type": "tool_result_internal",
                "result": ToolCallResult(
                    tool_name="rag_search",
                    tool_args=tool_args,
                    result="",
                    success=False,
                    error=str(e),
                )
            }
    
    def _resolve_attached_file_path(self, path_value: str) -> str:
        """
        将 LLM 提供的文件路径解析为实际的本地路径
        
        LLM 可能给出文件名、相对路径或完整路径，这里尝试多种方式匹配：
        1. 精确匹配 (name / path / basename)
        2. basename 反向匹配
        3. 已经是有效的绝对路径则直接返回
        """
        import os
        
        if not path_value:
            return path_value
        
        # 1. 精确匹配
        if path_value in self._attached_file_paths:
            resolved = self._attached_file_paths[path_value]
            logger.logger.info(f"[ToolUseAgent] Resolved path (exact): {path_value} -> {resolved}")
            return resolved
        
        # 2. basename 匹配：LLM 给的是文件名，映射表里有完整路径
        path_basename = os.path.basename(path_value)
        if path_basename and path_basename in self._attached_file_paths:
            resolved = self._attached_file_paths[path_basename]
            logger.logger.info(f"[ToolUseAgent] Resolved path (basename): {path_value} -> {resolved}")
            return resolved
        
        # 3. 反向 basename 匹配：LLM 给了完整路径，映射表里是文件名
        for key, local_path in self._attached_file_paths.items():
            if os.path.basename(local_path) == path_basename:
                logger.logger.info(f"[ToolUseAgent] Resolved path (reverse basename): {path_value} -> {local_path}")
                return local_path
        
        # 4. 已经是有效路径则直接返回
        if os.path.isabs(path_value) and os.path.exists(path_value):
            logger.logger.info(f"[ToolUseAgent] Path is valid absolute: {path_value}")
            return path_value
        
        logger.logger.warning(f"[ToolUseAgent] Could not resolve path: {path_value}, returning as-is")
        return path_value
    
    async def _execute_doc_extract_streaming(
        self,
        tool_args: Dict[str, Any],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行 doc_extract 并流式返回进度事件
        
        调用 DocExtractTool 的 extract_streaming 方法，
        流式发送提取进度事件给前端。
        
        Args:
            tool_args: 工具参数 (pdf_path, output_dir, max_pages)
            
        Yields:
            提取进度事件，最后一个是包含结果的内部事件
        """
        try:
            from ...tools.doc_extract import DocExtractTool
            
            # 创建 DocExtractTool 实例
            doc_extract_tool = DocExtractTool(
                project_id=tool_args.get("project_id"),
                chat_id=tool_args.get("chat_id"),
            )
            
            pdf_path = tool_args.get("pdf_path", "")
            output_dir = tool_args.get("output_dir", "doc_extract_output")
            max_pages = tool_args.get("max_pages")
            
            # 自动解析 attached_files 中的路径
            pdf_path = self._resolve_attached_file_path(pdf_path)
            
            logger.logger.info(f"[ToolUseAgent] doc_extract streaming: pdf_path={pdf_path}")
            
            # 流式提取
            final_result = None
            async for event in doc_extract_tool.extract_streaming(
                pdf_path=pdf_path,
                output_dir=output_dir,
                max_pages=max_pages,
            ):
                if event.get("type") == "extract_complete":
                    # 提取完成，构建最终结果
                    result_data = event.get("result", {})
                    text = doc_extract_tool._format_for_llm(result_data)
                    
                    final_result = ToolCallResult(
                        tool_name="doc_extract",
                        tool_args=tool_args,
                        result=text,
                        success=True,
                        structured_data={
                            "result_type": "doc_extract",
                            **result_data,
                        },
                    )
                else:
                    # 进度事件，直接转发
                    yield event
            
            # 返回最终结果
            if final_result:
                yield {"type": "tool_result_internal", "result": final_result}
            else:
                yield {
                    "type": "tool_result_internal",
                    "result": ToolCallResult(
                        tool_name="doc_extract",
                        tool_args=tool_args,
                        result="Error: Document extraction did not complete",
                        success=False,
                        error="No result returned",
                    )
                }
            
        except Exception as e:
            logger.logger.error(f"[ToolUseAgent] doc_extract streaming failed: {e}", exc_info=True)
            yield {
                "type": "tool_result_internal",
                "result": ToolCallResult(
                    tool_name="doc_extract",
                    tool_args=tool_args,
                    result="",
                    success=False,
                    error=str(e),
                )
            }
    
    async def _execute_web_search_with_structured_data(
        self,
        tool_args: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        执行 web_search 并获取结构化数据（非流式版本，保持兼容）
        
        Args:
            tool_args: 工具参数 (query, max_results)
            
        Returns:
            结构化数据（如果可用）
        """
        try:
            from ...tools.web_search import WebSearchTool
            
            # 创建 WebSearchTool 实例
            web_search_tool = WebSearchTool(
                api_key=self.api_keys.get("TAVILY_API_KEY", ""),
                openai_api_key=self.api_keys.get("OPENAI_API_KEY", ""),
            )
            
            # 调用并获取结构化数据
            query = tool_args.get("query", "")
            max_results = tool_args.get("max_results", 5)
            project_id = tool_args.get("project_id")
            
            result = await web_search_tool.invoke_with_structured_data(
                query=query,
                max_results=max_results,
                project_id=project_id,
            )
            
            return result.get("structured_data")
            
        except Exception as e:
            logger.logger.warning(f"[ToolUseAgent] Failed to get structured data for web_search: {e}")
            return None
    
    async def step(
        self,
        context: AgentContext,
        log_dir: Optional[str] = None,
    ) -> AgentStep:
        """
        执行单步（非流式，用于简单场景）
        
        Args:
            context: Agent 上下文
            log_dir: 日志目录
            
        Returns:
            AgentStep 包含完整的执行结果
        """
        try:
            # 1. Planner 决策
            planner_output = await self.planner.plan(context, log_dir)
            
            # 2. 如果完成，直接返回
            if planner_output.is_milestone_completed or planner_output.next_action == "stop":
                return AgentStep(
                    planner_output=planner_output,
                    tool_results=[],
                    reasoning_text="Task completed",
                )
            
            # 3. 执行工具调用
            tool_results = []
            for tool_call in planner_output.tool_calls:
                tool_name = tool_call.get("name", "")
                tool_args = tool_call.get("args", {})
                call_id = tool_call.get("id", "")
                
                result = await self._execute_tool(tool_name, tool_args)
                result.call_id = call_id
                tool_results.append(result)
                
                # 添加到 Planner 消息历史
                self.planner.add_tool_result(
                    tool_call_id=call_id,
                    tool_name=tool_name,
                    result=result.result if result.success else f"Error: {result.error}",
                )
            
            return AgentStep(
                planner_output=planner_output,
                tool_results=tool_results,
                reasoning_text=f"Executed {len(tool_results)} tool(s)",
            )
            
        except Exception as e:
            logger.logger.error(f"[ToolUseAgent] step failed: {e}", exc_info=True)
            return AgentStep(
                planner_output=PlannerOutput(
                    thinking=f"Error occurred: {str(e)}",
                    next_action="stop",
                    is_milestone_completed=False,
                ),
                error=str(e),
            )
    
    async def step_streaming(
        self,
        context: AgentContext,
        log_dir: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行单步（流式，用于回调处理）
        
        Yields:
            - {"type": "reasoning_delta", ...}
            - {"type": "plan_complete", ...}
            - {"type": "tool_call", ...}
            - {"type": "tool_result", ...}
            - {"type": "step_complete", "step": AgentStep}
            - {"type": "error", ...}
        """
        try:
            # 1. Planner 流式决策
            planner_output: Optional[PlannerOutput] = None
            
            async for event in self.planner.plan_streaming(context, log_dir):
                yield event
                
                if event.get("type") == "plan_complete":
                    planner_output = PlannerOutput.from_dict(event.get("content", {}))
            
            if not planner_output:
                yield {"type": "error", "content": "Planner did not return a valid result"}
                return
            
            # 2. 如果完成，返回
            if planner_output.is_milestone_completed or planner_output.next_action == "stop":
                yield {
                    "type": "step_complete",
                    "step": AgentStep(
                        planner_output=planner_output,
                        tool_results=[],
                        reasoning_text="Task completed",
                    ),
                }
                return
            
            # 3. 执行工具调用
            tool_results = []
            for tool_call in planner_output.tool_calls:
                tool_name = tool_call.get("name", "")
                tool_args = tool_call.get("args", {})
                call_id = tool_call.get("id", "")
                
                # 发送 tool_call 事件
                yield ToolCallEvent(
                    tool_name=tool_name,
                    tool_args=tool_args,
                    call_id=call_id,
                ).to_dict()
                
                # 执行工具
                result = await self._execute_tool(tool_name, tool_args)
                result.call_id = call_id
                tool_results.append(result)
                
                # 发送 tool_result 事件（包含结构化数据供前端可视化）
                yield ToolResultEvent(
                    tool_name=tool_name,
                    result=result.result,
                    success=result.success,
                    call_id=call_id,
                    error=result.error,
                    structured_data=result.structured_data,
                ).to_dict()
                
                # 添加到 Planner 消息历史
                self.planner.add_tool_result(
                    tool_call_id=call_id,
                    tool_name=tool_name,
                    result=result.result if result.success else f"Error: {result.error}",
                )
            
            # 4. 返回完整的 step 结果
            yield {
                "type": "step_complete",
                "step": AgentStep(
                    planner_output=planner_output,
                    tool_results=tool_results,
                    reasoning_text=f"Executed {len(tool_results)} tool(s)",
                ),
            }
            
        except Exception as e:
            logger.logger.error(f"[ToolUseAgent] step_streaming failed: {e}", exc_info=True)
            yield {"type": "error", "content": str(e)}


# ==================== 便捷函数 ====================

async def run_tool_use_agent(
    user_goal: str = "",
    node_instruction: str = "",
    tools: Optional[List[LangChainBaseTool]] = None,
    api_keys: Optional[Dict[str, str]] = None,
    planner_model: str = "gpt-4o-mini",
    max_steps: int = 60,
    log_dir: Optional[str] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    便捷函数：运行 Tool Use Agent
    
    Args:
        user_goal: 用户输入的宏观目标
        node_instruction: 当前节点的具体指令
        tools: LangChain 工具列表
        api_keys: API 密钥
        planner_model: Planner 模型
        max_steps: 最大步数
        log_dir: 日志目录
    """
    agent = ToolUseAgent(
        planner_model=planner_model,
        api_keys=api_keys,
        tools=tools,
    )
    
    async for event in agent.run(
        user_goal=user_goal,
        node_instruction=node_instruction,
        max_steps=max_steps,
        log_dir=log_dir,
    ):
        yield event
