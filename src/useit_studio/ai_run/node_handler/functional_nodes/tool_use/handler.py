"""
Tool Use Node Handler V2 - 纯桥接层

职责：
1. 实现 BaseNodeHandlerV2 接口
2. 从请求中提取工具配置
3. 创建工具并运行 ToolUseAgent 决策循环
4. 转发事件，处理流式输出
5. 任务结束后触发文件传输（如有需要）

特点：
- 运行过程中不需要和 Local Engine 交互
- 仅在任务结束后传输文件到用户本机
- 采用 planner_only 模式
- 使用 LangChain tool calling 调用预定义工具
"""

from __future__ import annotations

import uuid
from typing import Dict, Any, List, AsyncGenerator, Optional
from datetime import datetime

from useit_studio.ai_run.node_handler.base_v2 import (
    BaseNodeHandlerV2,
    NodeContext as V2NodeContext,
    NodeCompleteEvent,
    ErrorEvent,
)
from useit_studio.ai_run.utils.logger_utils import LoggerUtils

# 工具名称到显示名称的映射（用于前端显示）
TOOL_DISPLAY_NAMES: Dict[str, str] = {
    "web_search": "Web Search",
    "rag": "RAG",
    "file_read": "File Read",
    "file_write": "File Write",
    "code_execute": "Code Execute",
    "doc_extract": "Doc Extract",
}


def get_tool_display_name(tool_name: str) -> str:
    """获取工具的显示名称"""
    return TOOL_DISPLAY_NAMES.get(tool_name, tool_name.replace("_", " ").title())

from .core import create_agent
from .models import (
    ToolConfig,
    PlannerOutput,
    FileTransferEvent,
)
from .tools.base import create_tools_from_configs


logger = LoggerUtils(component_name="ToolUseNodeHandlerV2")


class ToolUseNodeHandlerV2(BaseNodeHandlerV2):
    """
    Tool Use 节点处理器 V2 - 纯桥接层
    
    支持的节点类型：
    - tool-use
    
    特点：
    - 无需 Local Engine 交互（工具在服务端执行）
    - 仅在任务结束后传输文件
    - 支持多步骤 tool calling
    """
    
    @classmethod
    def supported_types(cls) -> List[str]:
        return ["tool-use"]
    
    async def _generate_result_markdown(
        self,
        completion_summary: str,
        user_goal: str,
        node_instruction: str,
        planner_model: str,
        api_keys: Dict[str, Any],
    ) -> Optional[str]:
        """
        调用 LLM 生成 markdown 格式的结果文档
        
        Args:
            completion_summary: 任务完成摘要
            user_goal: 用户目标
            node_instruction: 节点指令
            planner_model: LLM 模型名称
            api_keys: API 密钥字典
            
        Returns:
            markdown 格式的文档内容，如果生成失败则返回 None
        """
        try:
            from useit_studio.ai_run.llm_utils import call_llm
            
            # 构建 prompt，要求 LLM 将结果格式化为 markdown
            system_prompt = """You are a professional technical writer. Your task is to convert task execution results into a well-formatted markdown document.

Requirements:
1. Use clear headings and structure
2. Include all important information from the summary
3. Format the content in a readable way
4. Use markdown features like lists, code blocks, and emphasis appropriately
5. Keep the document concise but comprehensive"""
            
            user_message = f"""Please convert the following task execution result into a well-formatted markdown document.

User Goal: {user_goal}
Node Instruction: {node_instruction or 'N/A'}

Task Completion Summary:
{completion_summary}

Please create a markdown document that:
- Has a clear title based on the task
- Summarizes the task objective
- Describes the execution process and results
- Highlights key outcomes or findings
- Is well-structured and easy to read"""
            
            # 调用 LLM 生成 markdown
            response = await call_llm(
                messages=[user_message],
                model=planner_model,
                system_prompt=system_prompt,
                api_key=api_keys.get("OPENAI_API_KEY"),
                temperature=0.7,
                max_tokens=2000,
            )
            
            if response and response.content:
                return response.content.strip()
            
            logger.logger.warning("[ToolUseNodeHandlerV2] LLM returned empty content for markdown generation")
            return None
            
        except Exception as e:
            logger.logger.error(f"[ToolUseNodeHandlerV2] Error generating markdown: {e}", exc_info=True)
            return None
    
    async def execute(self, ctx: V2NodeContext) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行 Tool Use 节点
        
        流程：
        1. 解析节点配置（工具列表）
        2. 创建工具并绑定到 Agent
        3. 运行决策循环
        4. 转发事件
        5. 任务完成后，如有需要则传输文件到本机
        """
        logger.logger.info(f"[ToolUseNodeHandlerV2] Starting node: {ctx.node_id}")
        
        cua_id = f"tooluse_{uuid.uuid4().hex[:8]}_{ctx.node_id}"
        
        try:
            # 解析节点配置
            node_data = ctx.node_dict.get("data", {})
            user_goal = ctx.query
            
            # 使用 ctx.get_node_instruction() 获取指令
            # 如果在循环中，会自动拼接循环上下文（当前迭代任务、整体计划等）
            # 否则返回节点的静态配置
            node_instruction = ctx.get_node_instruction()
            query = node_instruction or user_goal
            
            logger.logger.info(f"[ToolUseNodeHandlerV2] Query: {query[:100] if query else 'Empty'}...")
            
            # 解析工具配置
            tools_config = node_data.get("tools", [])
            tool_configs = [ToolConfig.from_dict(tc) for tc in tools_config]
            
            logger.logger.info(f"[ToolUseNodeHandlerV2] Tool configs: {[tc.tool_type.value for tc in tool_configs]}")
            
            # 创建 LangChain 工具
            tools = create_tools_from_configs(
                tool_configs,
                ctx.planner_api_keys,
                project_id=getattr(ctx, "project_id", None),
                chat_id=getattr(ctx, "chat_id", None),
            )
            
            if not tools:
                logger.logger.warning("[ToolUseNodeHandlerV2] No tools created, using empty tool list")
            else:
                logger.logger.info(f"[ToolUseNodeHandlerV2] Created {len(tools)} tools: {[t.name for t in tools]}")
            
            # 发送节点开始事件
            yield {
                "type": "node_start",
                "nodeId": ctx.node_id,
                "title": ctx.get_node_title(),
                "nodeType": ctx.node_type,
                "instruction": ctx.get_node_instruction(),
            }
            
            # 创建 Agent
            agent = create_agent(
                planner_model=ctx.planner_model,
                api_keys=ctx.planner_api_keys,
                tools=tools,
                node_id=ctx.node_id,
            )
            
            # 获取 history_md
            history_md = ""
            if ctx.flow_processor:
                try:
                    from useit_studio.ai_run.runtime.transformers import AIMarkdownTransformer
                    history_md = AIMarkdownTransformer(
                        ctx.flow_processor.runtime_state.state,
                        graph_nodes=ctx.flow_processor.graph_manager.nodes,
                        graph_edges=ctx.flow_processor.graph_manager.edges,
                    ).transform()
                except Exception as e:
                    logger.logger.warning(f"[ToolUseNodeHandlerV2] Failed to generate history_md: {e}")
            
            # 运行 Agent 决策循环
            step_count = 0
            current_planner_content: Dict[str, Any] = {}
            files_to_transfer: List[str] = []
            step_cua_end_sent = False  # 跟踪当前 step 是否已发送 cua_end
            
            max_steps = node_data.get("max_steps", 60)
            
            # 获取附件文件内容（异步，包含智能路由判断）
            attached_files_content = ""
            if hasattr(ctx, 'get_attached_files_content'):
                attached_files_content = await ctx.get_attached_files_content()
            
            agent_gen = agent.run(
                user_goal=user_goal,
                node_instruction=node_instruction,
                max_steps=max_steps,
                log_dir=ctx.log_folder,
                history_md=history_md,
                project_id=getattr(ctx, "project_id", None),
                chat_id=getattr(ctx, "chat_id", None),
                attached_files_content=attached_files_content,
                attached_files=getattr(ctx, "attached_files", None),
            )
            
            async for event in agent_gen:
                event_type = event.get("type", "")
                
                # Step 开始
                if event_type == "step_start":
                    step_count = event.get("step", step_count + 1)
                    step_cua_end_sent = False  # 重置标志
                    yield {
                        "type": "cua_start",
                        "cuaId": f"{cua_id}_step{step_count}",
                        "step": step_count,
                        "title": "LLM",
                        "nodeId": ctx.node_id,
                    }
                
                # 推理过程
                elif event_type == "reasoning_delta":
                    yield {
                        "type": "cua_delta",
                        "cuaId": f"{cua_id}_step{step_count}",
                        "reasoning": event.get("content", ""),
                        "kind": event.get("source", "planner"),
                    }
                
                # 规划完成
                elif event_type == "plan_complete":
                    planner_content = event.get("content", {})
                    current_planner_content = planner_content
                    yield {
                        "type": "planner_complete",
                        "content": {"tool_plan": planner_content},
                    }
                    
                    # 记录 action 到 RuntimeStateManager
                    if ctx.flow_processor and planner_content:
                        try:
                            action_title = planner_content.get("Title", "Tool call")
                            thinking = planner_content.get("Thinking", "")
                            tool_calls = planner_content.get("ToolCalls", [])
                            
                            ctx.flow_processor.runtime_state.record_node_action(
                                node_id=ctx.node_id,
                                thinking=thinking,
                                title=action_title,
                                observation="",
                                reasoning="",
                                action_type="tool_call",
                                action_params={"tool_calls": tool_calls},
                                action_target=action_title,
                            )
                        except Exception as e:
                            logger.logger.warning(f"[ToolUseNodeHandlerV2] Failed to record action: {e}")
                    
                    # 检查任务是否完成（MilestoneCompleted 为 true 或 Action 为 stop）
                    is_completed = planner_content.get("MilestoneCompleted", False) or planner_content.get("Action") == "stop"
                    logger.logger.info(f"[ToolUseNodeHandlerV2] is_completed={is_completed}, MilestoneCompleted={planner_content.get('MilestoneCompleted')}, Action={planner_content.get('Action')}")
                    if is_completed:
                        result_markdown = planner_content.get("result_markdown")
                        result_filename = planner_content.get("result_filename")
                        completion_summary = planner_content.get("node_completion_summary", "Task completed")
                        logger.logger.info(f"[ToolUseNodeHandlerV2] result_markdown exists: {bool(result_markdown)}, result_filename: {result_filename}")
                        
                        # 保存 markdown 结果并上传到 S3
                        if result_markdown:
                            s3_key = await self._save_and_upload_result_markdown(
                                ctx=ctx,
                                markdown_content=result_markdown,
                                filename=result_filename or "result.md",
                                step_count=step_count,
                            )
                            if s3_key:
                                files_to_transfer.append(s3_key)
                                logger.logger.info(f"[ToolUseNodeHandlerV2] Result markdown uploaded to S3: {s3_key}")
                        
                        # 发送 cua_end
                        if not step_cua_end_sent:
                            yield {
                                "type": "cua_end",
                                "cuaId": f"{cua_id}_step{step_count}",
                                "status": "completed",
                                "title": "LLM",
                                "action": {"type": "stop"},
                            }
                            step_cua_end_sent = True
                        
                        # 如果有文件需要传输，发送文件传输事件
                        if files_to_transfer:
                            yield FileTransferEvent(
                                files=files_to_transfer,
                                target="local",
                                status="pending",
                            ).to_dict()
                            logger.logger.info(f"[ToolUseNodeHandlerV2] Files to transfer: {files_to_transfer}")
                        
                        # 完成最后一个 action 的状态更新
                        if ctx.flow_processor:
                            try:
                                ctx.flow_processor.runtime_state.complete_node_action(
                                    node_id=ctx.node_id,
                                    status="success",
                                    result_observation=completion_summary or "Task completed successfully",
                                )
                            except Exception as e:
                                logger.logger.warning(f"[ToolUseNodeHandlerV2] Failed to complete final action: {e}")
                        
                        # 发送 node_complete
                        yield NodeCompleteEvent(
                            node_id=ctx.node_id,
                            node_type=ctx.node_type,
                            is_node_completed=True,
                            handler_result={
                                "is_node_completed": True,
                                "summary": completion_summary,
                                "files_transferred": files_to_transfer,
                            },
                            action_summary="LLM",
                            node_completion_summary=completion_summary or "Tool use completed",
                        ).to_dict()
                        return
                
                # 工具调用（服务器端执行的工具不需要发送 tool_call 给前端）
                # tool_call 事件仅用于 Local Engine 执行的工具
                elif event_type == "tool_call":
                    # 服务器端执行的工具（如 web_search），不发送 tool_call 事件
                    # 前端通过 search_progress 和 search_result 获取进度和结果
                    pass
                
                # 搜索进度事件（web_search 工具专用）
                elif event_type == "search_progress":
                    yield {
                        "type": "cua_delta",
                        "cuaId": f"{cua_id}_step{step_count}",
                        "kind": "search_progress",
                        "payload": {
                            "stage": event.get("stage", ""),
                            "message": event.get("message", ""),
                            "queries": event.get("queries"),
                            "current_query": event.get("current_query"),
                            "total_results": event.get("total_results", 0),
                            "elapsed_time": event.get("elapsed_time", 0),
                        },
                    }
                
                # RAG 检索进度事件
                elif event_type == "rag_progress":
                    yield {
                        "type": "cua_delta",
                        "cuaId": f"{cua_id}_step{step_count}",
                        "kind": "rag_progress",
                        "payload": {
                            "stage": event.get("stage", ""),
                            "message": event.get("message", ""),
                            "queries": event.get("queries"),
                            "current_query": event.get("current_query"),
                            "total_results": event.get("total_results", 0),
                            "elapsed_time": event.get("elapsed_time", 0),
                        },
                    }
                
                # 文档提取进度事件（doc_extract 工具）
                elif event_type == "extract_progress":
                    yield {
                        "type": "cua_delta",
                        "cuaId": f"{cua_id}_step{step_count}",
                        "kind": "extract_progress",
                        "payload": {
                            "stage": event.get("stage", ""),
                            "message": event.get("message", ""),
                            "percentage": event.get("percentage", 0),
                            "current_page": event.get("current_page"),
                            "total_pages": event.get("total_pages"),
                            "current_figure": event.get("current_figure"),
                            "total_figures": event.get("total_figures"),
                        },
                    }
                
                # 工具结果
                elif event_type == "tool_result":
                    tool_name = event.get("name", "")
                    
                    tool_result_event = {
                        "type": "tool_result",
                        "id": event.get("id", ""),
                        "name": tool_name,
                        "result": event.get("result", ""),
                        "success": event.get("success", True),
                        "error": event.get("error"),
                    }
                    # 传递结构化数据供前端可视化（如 web_search 结果）
                    if event.get("structured_data"):
                        tool_result_event["structured_data"] = event["structured_data"]
                    yield tool_result_event

                    # 额外发送搜索结果事件（前端统一用 cua_delta + kind）
                    if tool_name == "web_search" and event.get("structured_data"):
                        structured_data = event["structured_data"]
                        yield {
                            "type": "cua_delta",
                            "cuaId": f"{cua_id}_step{step_count}",
                            "kind": "search_result",
                            "payload": {
                                "answer": structured_data.get("answer"),
                                "results": structured_data.get("results", []),
                                "source": "web_search",
                                "timestamp": datetime.now().astimezone().isoformat(),
                            },
                        }
                    
                    # 额外发送文档提取结果事件
                    elif tool_name == "doc_extract" and event.get("structured_data"):
                        structured_data = event["structured_data"]
                        yield {
                            "type": "cua_delta",
                            "cuaId": f"{cua_id}_step{step_count}",
                            "kind": "extract_result",
                            "payload": {
                                "title": structured_data.get("title", ""),
                                "total_pages": structured_data.get("total_pages", 0),
                                "pages_processed": structured_data.get("pages_processed", 0),
                                "figures": structured_data.get("figures", []),
                                "tables": structured_data.get("tables", []),
                                "metadata": structured_data.get("metadata", {}),
                                "s3": structured_data.get("s3"),
                                "source": "doc_extract",
                                "timestamp": datetime.now().astimezone().isoformat(),
                            },
                        }
                    
                    # 发送 cua_end 结束当前 step（title = 工具显示名 or "LLM"）
                    if not step_cua_end_sent:
                        step_title = get_tool_display_name(tool_name) if tool_name else "LLM"
                        yield {
                            "type": "cua_end",
                            "cuaId": f"{cua_id}_step{step_count}",
                            "status": "completed",
                            "title": step_title,
                        }
                        step_cua_end_sent = True
                    
                    # 更新 RuntimeStateManager
                    if ctx.flow_processor:
                        try:
                            ctx.flow_processor.runtime_state.complete_node_action(
                                node_id=ctx.node_id,
                                status="success" if event.get("success", True) else "failed",
                                result_observation=event.get("result", "")[:500],
                                error=event.get("error") if not event.get("success", True) else None,
                            )
                        except Exception as e:
                            logger.logger.warning(f"[ToolUseNodeHandlerV2] Failed to update action status: {e}")
                
                # 任务完成
                elif event_type == "task_completed":
                    completion_summary = event.get("summary", "")
                    files_to_transfer = event.get("files_to_transfer", [])
                    result_markdown = event.get("result_markdown")
                    result_filename = event.get("result_filename")
                    tool_calls = current_planner_content.get("ToolCalls", []) if isinstance(current_planner_content, dict) else []
                    tool_name_raw = tool_calls[0].get("name") if tool_calls else None
                    action_title = get_tool_display_name(tool_name_raw) if tool_name_raw else "LLM"
                    
                    # 保存 markdown 结果并上传到 S3，将 S3 key 添加到 files_to_transfer
                    if result_markdown:
                        s3_key = await self._save_and_upload_result_markdown(
                            ctx=ctx,
                            markdown_content=result_markdown,
                            filename=result_filename or "result.md",
                            step_count=step_count,
                        )
                        if s3_key:
                            # TODO: Replace Presigned URL with direct download link
                            files_to_transfer.append(s3_key)
                    
                    # 发送 cua_end（如果还没发送）
                    if not step_cua_end_sent:
                        yield {
                            "type": "cua_end",
                            "cuaId": f"{cua_id}_step{step_count}",
                            "status": "completed",
                            "title": action_title,
                            "action": {"type": "stop"},
                        }
                        step_cua_end_sent = True
                    
                    # 如果有文件需要传输，发送文件传输事件
                    if files_to_transfer:
                        yield FileTransferEvent(
                            files=files_to_transfer,
                            target="local",
                            status="pending",
                        ).to_dict()
                        
                        logger.logger.info(f"[ToolUseNodeHandlerV2] Files to transfer: {files_to_transfer}")
                    
                    # 完成最后一个 action 的状态更新
                    if ctx.flow_processor:
                        try:
                            ctx.flow_processor.runtime_state.complete_node_action(
                                node_id=ctx.node_id,
                                status="success",
                                result_observation=completion_summary or "Task completed successfully",
                            )
                        except Exception as e:
                            logger.logger.warning(f"[ToolUseNodeHandlerV2] Failed to complete final action: {e}")
                    
                    # 发送 node_complete
                    yield NodeCompleteEvent(
                        node_id=ctx.node_id,
                        node_type=ctx.node_type,
                        is_node_completed=True,
                        handler_result={
                            "is_node_completed": True,
                            "summary": completion_summary,
                            "files_transferred": files_to_transfer,
                        },
                        action_summary=action_title,
                        node_completion_summary=completion_summary or "Tool use completed",
                    ).to_dict()
                    return
                
                # 达到最大步数
                elif event_type == "max_steps_reached":
                    if not step_cua_end_sent:
                        tool_name_raw = (current_planner_content.get("ToolCalls", [{}])[0].get("name") 
                                        if isinstance(current_planner_content, dict) and current_planner_content.get("ToolCalls") 
                                        else None)
                        yield {
                            "type": "cua_end",
                            "cuaId": f"{cua_id}_step{step_count}",
                            "status": "completed",
                            "title": get_tool_display_name(tool_name_raw) if tool_name_raw else "LLM",
                        }
                        step_cua_end_sent = True
                    
                    yield NodeCompleteEvent(
                        node_id=ctx.node_id,
                        node_type=ctx.node_type,
                        is_node_completed=True,
                        handler_result={
                            "is_node_completed": True,
                            "summary": f"Reached maximum steps ({event.get('steps', max_steps)})",
                        },
                        action_summary="Reached max steps",
                        node_completion_summary="Tool use reached maximum steps limit",
                    ).to_dict()
                    return
                
                # 错误
                elif event_type == "error":
                    if not step_cua_end_sent:
                        yield {
                            "type": "cua_end",
                            "cuaId": f"{cua_id}_step{step_count}",
                            "status": "error",
                            "error": event.get("content", "Unknown error"),
                        }
                        step_cua_end_sent = True
                    yield ErrorEvent(
                        message=event.get("content", "Unknown error"),
                        node_id=ctx.node_id,
                    ).to_dict()
                    return
        
        except Exception as e:
            error_msg = f"Tool Use node execution failed: {str(e)}"
            logger.logger.error(error_msg, exc_info=True)
            
            yield {
                "type": "cua_end",
                "cuaId": cua_id,
                "status": "error",
                "error": error_msg,
            }
            yield ErrorEvent(message=error_msg, node_id=ctx.node_id).to_dict()
    
    async def _save_and_upload_result_markdown(
        self,
        ctx: V2NodeContext,
        markdown_content: str,
        filename: str,
        step_count: int,
    ) -> Optional[str]:
        """
        保存 markdown 结果到本地并上传到 S3
        
        Args:
            ctx: 节点上下文
            markdown_content: markdown 内容
            filename: 文件名 (如 "search_results.md")
            step_count: 当前步骤数
            
        Returns:
            S3 key (如 "projects/{project_id}/outputs/{filename_date}.md")
            如果上传失败或未配置 S3，返回 None
        """
        import os
        
        try:
            # 1. 确定本地保存路径
            if ctx.run_logger:
                # 使用 RunLogger 的当前 step 目录
                step_dir = ctx.run_logger.get_step_dir()
                if not step_dir:
                    step_dir = ctx.log_folder
            else:
                step_dir = ctx.log_folder or os.path.join("logs", "tool_use", ctx.node_id)
            
            os.makedirs(step_dir, exist_ok=True)
            
            # 清理文件名（移除非法字符和扩展名）
            base_filename = filename.replace('.md', '') if filename.endswith('.md') else filename
            safe_base = "".join(c for c in base_filename if c.isalnum() or c in ('_', '-')).strip()
            if not safe_base:
                safe_base = "result"
            
            # 添加日期时间后缀
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_filename = f"{safe_base}_{timestamp}.md"
            
            local_path = os.path.join(step_dir, safe_filename)
            
            # 2. 保存到本地
            with open(local_path, "w", encoding="utf-8") as f:
                f.write(markdown_content)
            
            logger.logger.info(f"[ToolUseNodeHandlerV2] Saved result markdown to: {local_path}")
            
            # 3. 上传到 S3 (如果配置了 project_id)
            project_id = getattr(ctx, "project_id", None)
            
            if not project_id:
                logger.logger.info("[ToolUseNodeHandlerV2] project_id not provided, skip S3 upload")
                return None
            
            try:
                from useit_studio.ai_run.utils.s3_uploader import get_s3_uploader, _get_s3_client
                
                # 检查 S3 客户端是否可用
                if _get_s3_client() is None:
                    logger.logger.info("[ToolUseNodeHandlerV2] S3 client not available, skip upload")
                    return None
                
                uploader = get_s3_uploader()
                
                # 构建 S3 key
                # 格式: projects/{project_id}/outputs/{filename_date}.md
                s3_key = f"projects/{project_id}/outputs/{safe_filename}"
                
                # 上传文件
                success = await uploader.upload_file_async(
                    local_path=local_path,
                    s3_key=s3_key,
                    content_type="text/markdown"
                )
                
                if success:
                    logger.logger.info(f"[ToolUseNodeHandlerV2] Uploaded result markdown to S3: {s3_key}")
                    return s3_key
                else:
                    logger.logger.warning("[ToolUseNodeHandlerV2] Failed to upload result markdown to S3")
                    return None
                        
            except Exception as e:
                logger.logger.warning(f"[ToolUseNodeHandlerV2] S3 upload error: {e}")
                return None
                
        except Exception as e:
            logger.logger.error(f"[ToolUseNodeHandlerV2] Failed to save result markdown: {e}")
            return None