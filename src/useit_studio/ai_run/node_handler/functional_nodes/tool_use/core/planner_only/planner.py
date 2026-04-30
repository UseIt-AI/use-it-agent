"""
Tool Use Node - Planner 实现

使用 LangChain 的 tool calling 机制：
1. 将工具绑定到 LLM
2. LLM 自动决定调用哪个工具
3. 解析 tool_calls 并返回
"""

import json
import os
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, AsyncGenerator, List

from langchain_core.tools import BaseTool as LangChainBaseTool
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
from langchain_openai import ChatOpenAI

from ...models import (
    PlannerOutput,
    AgentContext,
    ReasoningDeltaEvent,
    PlanCompleteEvent,
)
from useit_studio.ai_run.utils.logger_utils import LoggerUtils
from useit_studio.ai_run.llm_utils.request_token_tracker import get_current as get_current_tracker


logger = LoggerUtils(component_name="ToolUsePlanner")

# Gemini 系列模型前缀，用于判断是否需要走 Google API
_GEMINI_MODEL_PREFIXES = ("gemini-", "google/gemini", "models/gemini")
# Gemini 中支持原生 thinking 的模型前缀（与 llm_utils/adapters/gemini_adapter.py 保持一致）
_GEMINI_THINKING_PREFIXES = ("gemini-2.5", "gemini-3")


# ==================== Prompt 模板 ====================

PLANNER_SYSTEM_PROMPT = """You are an AI assistant with access to tools. Your job is to complete the user's task by using the available tools.

## Your Role

You are a helpful assistant that can use tools to find information and complete tasks. 
Analyze the user's request and decide which tool(s) to use, or if you have enough information to provide a final answer.

## How to Think

1. **Understand the Goal**: What does the user want to accomplish?
2. **Check Previous Results**: If tools were already called, analyze their results.
3. **Decide Next Action**:
   - If more information is needed → call a tool
   - If you have enough information → provide a final answer
4. **Be Thorough**: Don't guess - use tools to verify information.

## Rules

1. **Use tools when you need external information**
2. **Don't make assumptions** - verify with tools
3. **Summarize findings clearly** when you're done
4. **If a tool fails**, try alternative approaches or explain why you can't proceed
5. **Stay focused** on the user's specific request

## CRITICAL: Final Response Format (When Task is Complete)

When you have completed the task and have enough information to answer, you MUST respond with a well-structured Markdown document. This is NOT a summary - it is the COMPLETE answer to the user's question.

**Your response MUST follow this exact format:**

```
<!-- RESULT_FILENAME: descriptive_filename.md -->

# [Title that describes the answer]

[Your complete, well-formatted answer in Markdown]

## [Section 1]
...

## [Section 2]
...

[Include ALL relevant information from tool results]
```

**IMPORTANT Requirements:**
1. The `<!-- RESULT_FILENAME: xxx.md -->` comment MUST be on the FIRST line
2. The filename should be descriptive and relevant to the content (e.g., `ai_trends_2024.md`, `python_best_practices.md`, `search_results_react.md`)
3. Use proper Markdown formatting: headings, lists, tables, code blocks as appropriate
4. Include ALL relevant data from tool results - don't just summarize, include the actual content
5. Structure the document clearly with sections and subsections
6. If there are multiple sources, cite them properly

**Example Response:**
```
<!-- RESULT_FILENAME: latest_ai_news.md -->

# Latest AI News and Developments

## Summary
Brief overview of the key findings...

## Detailed Findings

### 1. Large Language Models
- GPT-4o released with multimodal capabilities
- Claude 3 series launched
- Key improvements in reasoning and context length

### 2. Image Generation
- DALL-E 3 improvements
- Midjourney V6 features

## Sources
1. [Source Title](url)
2. [Source Title](url)

## Conclusion
...
```

When you need more information:
- Call the appropriate tool with the right arguments
"""


class ToolUsePlanner:
    """
    Tool Use Planner
    
    使用 LangChain 的 tool calling 机制来决定调用哪个工具。
    """
    
    def __init__(
        self,
        model: str = "gpt-4o-mini",
        api_keys: Optional[Dict[str, str]] = None,
        tools: Optional[List[LangChainBaseTool]] = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        node_id: str = "",
    ):
        """
        初始化 Planner
        
        Args:
            model: 使用的模型
            api_keys: API 密钥
            tools: LangChain 工具列表
            max_tokens: 最大 token 数
            temperature: 温度参数
            node_id: 节点 ID
        """
        self.model = model
        self.api_keys = api_keys or {}
        self.tools = tools or []
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.node_id = node_id

        # 按模型名路由到对应的 LLM（OpenAI / Gemini），provider 用于 token tracker
        self.llm, self.provider = self._create_llm()

        # 绑定工具到 LLM
        if self.tools:
            self.llm_with_tools = self.llm.bind_tools(self.tools)
            logger.logger.info(
                f"[ToolUsePlanner] Bound {len(self.tools)} tools to LLM "
                f"(model={self.model}, provider={self.provider})"
            )
        else:
            self.llm_with_tools = self.llm
            logger.logger.warning(
                f"[ToolUsePlanner] No tools provided "
                f"(model={self.model}, provider={self.provider})"
            )

        # 消息历史（用于多轮对话）
        self.messages: List[Any] = []

    @staticmethod
    def _is_gemini_model(model: str) -> bool:
        """判断是否是 Gemini 系列模型"""
        model_lower = (model or "").lower()
        return any(model_lower.startswith(p) for p in _GEMINI_MODEL_PREFIXES)

    def _create_llm(self):
        """
        按模型名路由到对应的 LangChain LLM。

        - Gemini 系列 → ChatGoogleGenerativeAI（原生支持 streaming tool calling）
        - 其它 → ChatOpenAI

        Returns:
            (llm, provider) 元组
        """
        model_lower = (self.model or "").lower()

        # Gemini 系列：走 Google API
        if self._is_gemini_model(self.model):
            try:
                from langchain_google_genai import ChatGoogleGenerativeAI
            except ImportError as e:
                raise ImportError(
                    "langchain-google-genai is required for Gemini support in "
                    "ToolUsePlanner. Install with: pip install langchain-google-genai"
                ) from e

            google_api_key = (
                self.api_keys.get("GOOGLE_API_KEY")
                or os.getenv("GOOGLE_API_KEY", "")
            )
            if not google_api_key:
                logger.logger.warning(
                    "[ToolUsePlanner] GOOGLE_API_KEY is empty while using Gemini model "
                    f"{self.model}; request will likely fail."
                )

            kwargs: Dict[str, Any] = dict(
                model=self.model,
                google_api_key=google_api_key,
                temperature=self.temperature,
                max_output_tokens=self.max_tokens,
            )
            # 关闭原生 thinking，让模型走 prompt 里的 <thinking> 逻辑，
            # 行为与 llm_utils/adapters/gemini_adapter.py 保持一致
            if any(model_lower.startswith(p) for p in _GEMINI_THINKING_PREFIXES):
                kwargs["thinking_budget"] = 0

            try:
                llm = ChatGoogleGenerativeAI(**kwargs)
            except TypeError:
                kwargs.pop("thinking_budget", None)
                llm = ChatGoogleGenerativeAI(**kwargs)

            return llm, "google"

        # 其它默认走 OpenAI
        llm = ChatOpenAI(
            model=self.model,
            api_key=self.api_keys.get("OPENAI_API_KEY", ""),
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )
        return llm, "openai"
    
    def set_node_id(self, node_id: str):
        """更新节点 ID"""
        self.node_id = node_id
    
    def reset(self):
        """重置消息历史"""
        self.messages = []

    def _record_token_usage(self, response):
        """从 LangChain 响应中提取 token 使用量并记录到 request tracker"""
        tracker = get_current_tracker()
        if not tracker:
            return
        # LangChain AIMessage: usage_metadata (newer) or response_metadata.token_usage (older)
        usage_metadata = getattr(response, 'usage_metadata', None)
        if usage_metadata:
            tracker.record(
                input_tokens=usage_metadata.get('input_tokens', 0),
                output_tokens=usage_metadata.get('output_tokens', 0),
                total_tokens=usage_metadata.get('total_tokens', 0),
                model=self.model,
                provider=self.provider,
            )
            return
        token_usage = getattr(response, 'response_metadata', {}).get('token_usage', {})
        if token_usage:
            tracker.record(
                input_tokens=token_usage.get('prompt_tokens', 0),
                output_tokens=token_usage.get('completion_tokens', 0),
                total_tokens=token_usage.get('total_tokens', 0),
                model=self.model,
                provider=self.provider,
            )

    def add_tool_result(self, tool_call_id: str, tool_name: str, result: str):
        """
        添加工具调用结果到消息历史
        
        Args:
            tool_call_id: 工具调用 ID
            tool_name: 工具名称
            result: 工具结果
        """
        self.messages.append(
            ToolMessage(content=result, tool_call_id=tool_call_id, name=tool_name)
        )
    
    async def plan(
        self,
        context: AgentContext,
        log_dir: Optional[str] = None,
    ) -> PlannerOutput:
        """
        非流式规划
        
        Args:
            context: Agent 上下文
            log_dir: 日志目录
            
        Returns:
            PlannerOutput 对象
        """
        # 构建消息
        messages = self._build_messages(context)
        
        # 调用 LLM
        response = await self.llm_with_tools.ainvoke(messages)

        # 记录 token 使用量
        self._record_token_usage(response)

        # 解析响应
        return self._parse_response(response)
    
    async def plan_streaming(
        self,
        context: AgentContext,
        log_dir: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式规划
        
        Yields:
            ReasoningDeltaEvent - 推理过程增量
            PlanCompleteEvent - 规划完成
        """
        # 构建消息
        messages = self._build_messages(context)
        
        logger.logger.info(f"[ToolUsePlanner] Starting streaming plan with {len(messages)} messages")
        
        # 保存请求日志
        if log_dir:
            self._log_request(messages, log_dir)
        
        full_content = ""
        tool_call_chunks = {}  # 用于合并流式 tool_call 片段（按 index）
        last_usage_metadata = None  # 捕获流式最后一个 chunk 的 usage_metadata

        try:
            # 流式调用 LLM
            async for chunk in self.llm_with_tools.astream(messages):
                # 捕获 usage_metadata（通常在最后一个 chunk 中）
                if hasattr(chunk, 'usage_metadata') and chunk.usage_metadata:
                    last_usage_metadata = chunk.usage_metadata
                # 处理文本内容
                if chunk.content:
                    content = chunk.content
                    if isinstance(content, list):
                        content = "".join(str(c) for c in content)
                    full_content += content
                    yield ReasoningDeltaEvent(content=content, source="planner").to_dict()
                
                # 处理流式 tool_call_chunks（增量合并）
                # LangChain 流式返回时，tool_calls 通常通过 tool_call_chunks 传递
                if hasattr(chunk, 'tool_call_chunks') and chunk.tool_call_chunks:
                    for tcc in chunk.tool_call_chunks:
                        tcc_dict = tcc if isinstance(tcc, dict) else {
                            "id": getattr(tcc, "id", None),
                            "index": getattr(tcc, "index", 0),
                            "name": getattr(tcc, "name", ""),
                            "args": getattr(tcc, "args", ""),
                        }
                        idx = tcc_dict.get("index", 0)
                        
                        if idx not in tool_call_chunks:
                            tool_call_chunks[idx] = {
                                "id": "",
                                "name": "",
                                "args": "",
                            }
                        
                        # 合并 id（只设置一次）
                        if tcc_dict.get("id") and not tool_call_chunks[idx]["id"]:
                            tool_call_chunks[idx]["id"] = tcc_dict["id"]
                        # 合并 name（只设置一次，不拼接）
                        if tcc_dict.get("name") and not tool_call_chunks[idx]["name"]:
                            tool_call_chunks[idx]["name"] = tcc_dict["name"]
                        # 合并 args（字符串形式，需要拼接）
                        if tcc_dict.get("args"):
                            tool_call_chunks[idx]["args"] += tcc_dict["args"]
            
            # 记录流式调用的 token 使用量
            if last_usage_metadata:
                tracker = get_current_tracker()
                if tracker:
                    tracker.record(
                        input_tokens=last_usage_metadata.get('input_tokens', 0),
                        output_tokens=last_usage_metadata.get('output_tokens', 0),
                        total_tokens=last_usage_metadata.get('total_tokens', 0),
                        model=self.model,
                        provider=self.provider,
                    )

            # 将流式收集的 tool_call_chunks 转换为完整的 tool_calls
            tool_calls = []
            for idx in sorted(tool_call_chunks.keys()):
                tcc = tool_call_chunks[idx]
                if tcc.get("name"):
                    # 解析 args JSON 字符串
                    args_str = tcc.get("args", "")
                    try:
                        args = json.loads(args_str) if args_str else {}
                    except json.JSONDecodeError:
                        logger.logger.warning(f"[ToolUsePlanner] Failed to parse tool args: {args_str}")
                        args = {}
                    
                    tool_calls.append({
                        "id": tcc.get("id") or f"call_{uuid.uuid4().hex[:8]}",
                        "name": tcc["name"],
                        "args": args,
                    })
            
            logger.logger.info(f"[ToolUsePlanner] Collected {len(tool_calls)} tool_calls: {[tc['name'] for tc in tool_calls]}")
            
            # 构建 PlannerOutput
            planner_output = self._build_output(full_content, tool_calls)
            
            # 保存响应日志
            if log_dir:
                self._log_response(full_content, tool_calls, log_dir)
            
            # 保存 AI 响应到消息历史
            if tool_calls:
                # 有 tool_calls 时，需要保存完整的 AI 消息
                # LangChain AIMessage 需要 tool_calls 格式: [{"id": ..., "name": ..., "args": {...}}]
                # 但某些版本需要 "type": "function"
                formatted_tool_calls = [
                    {
                        "id": tc["id"],
                        "name": tc["name"],
                        "args": tc["args"],
                        "type": "function",  # LangChain 需要这个字段
                    }
                    for tc in tool_calls
                ]
                ai_message = AIMessage(content=full_content or "", tool_calls=formatted_tool_calls)
                self.messages.append(ai_message)
            elif full_content:
                self.messages.append(AIMessage(content=full_content))
            
            yield PlanCompleteEvent(planner_output=planner_output).to_dict()
            
        except Exception as e:
            logger.logger.error(f"[ToolUsePlanner] Streaming failed: {e}", exc_info=True)
            yield {"type": "error", "content": str(e)}
    
    def _build_messages(self, context: AgentContext) -> List[Any]:
        """
        构建 LLM 消息
        
        Args:
            context: Agent 上下文
            
        Returns:
            消息列表
        """
        messages = [SystemMessage(content=PLANNER_SYSTEM_PROMPT)]
        
        # 如果是首次调用，添加用户消息
        if not self.messages:
            user_prompt = context.to_prompt()
            messages.append(HumanMessage(content=user_prompt))
        else:
            # 添加历史消息（包括之前的 AI 消息和工具结果）
            # 首先添加初始用户消息
            initial_prompt = f"""## User's Overall Goal
{context.user_goal}

## Current Node Instruction (YOUR GOAL)
{context.node_instruction or context.user_goal or "(No instruction provided)"}
"""
            messages.append(HumanMessage(content=initial_prompt))
            messages.extend(self.messages)
        
        return messages
    
    def _parse_response(self, response: AIMessage) -> PlannerOutput:
        """
        解析 LLM 响应
        
        Args:
            response: AI 消息
            
        Returns:
            PlannerOutput 对象
        """
        content = response.content or ""
        tool_calls = response.tool_calls if hasattr(response, 'tool_calls') else []
        
        return self._build_output(content, tool_calls)
    
    def _build_output(
        self, 
        content: str, 
        tool_calls: List[Dict[str, Any]]
    ) -> PlannerOutput:
        """
        构建 PlannerOutput
        
        Args:
            content: 文本内容
            tool_calls: 工具调用列表
            
        Returns:
            PlannerOutput 对象
        """
        # 处理 tool_calls
        formatted_tool_calls = []
        for tc in tool_calls:
            # LangChain tool_call 格式可能是 dict 或对象
            if isinstance(tc, dict):
                formatted_tool_calls.append({
                    "id": tc.get("id", f"call_{uuid.uuid4().hex[:8]}"),
                    "name": tc.get("name", ""),
                    "args": tc.get("args", {}),
                })
            else:
                # 对象格式
                formatted_tool_calls.append({
                    "id": getattr(tc, "id", f"call_{uuid.uuid4().hex[:8]}"),
                    "name": getattr(tc, "name", ""),
                    "args": getattr(tc, "args", {}),
                })
        
        # 判断是否有工具调用
        if formatted_tool_calls:
            # 有工具调用
            return PlannerOutput(
                thinking=content,
                next_action="tool_call",
                title=f"Call {formatted_tool_calls[0]['name']}",
                tool_calls=formatted_tool_calls,
                is_milestone_completed=False,
            )
        else:
            # 没有工具调用，任务完成
            # 提取 markdown 文件名和内容
            result_filename, result_markdown = self._extract_result_markdown(content)
            
            return PlannerOutput(
                thinking=content,
                next_action="stop",
                title="Task completed",
                tool_calls=[],
                is_milestone_completed=True,
                completion_summary=content[:500] if content else "Task completed",
                result_markdown=result_markdown,
                result_filename=result_filename,
            )
    
    def _extract_result_markdown(self, content: str) -> tuple:
        """
        从 LLM 响应中提取 markdown 文件名和内容
        
        期望格式:
        <!-- RESULT_FILENAME: xxx.md -->
        [markdown content]
        
        Args:
            content: LLM 响应内容
            
        Returns:
            (filename, markdown_content) 元组
            如果没有找到文件名，返回默认文件名
        """
        import re
        
        if not content:
            return ("result.md", "")
        
        # 尝试提取文件名
        # 匹配 <!-- RESULT_FILENAME: xxx.md --> 格式
        filename_pattern = r'<!--\s*RESULT_FILENAME:\s*([^\s>]+\.md)\s*-->'
        match = re.search(filename_pattern, content, re.IGNORECASE)
        
        if match:
            filename = match.group(1).strip()
            # 移除文件名注释，保留其余内容作为 markdown
            markdown_content = re.sub(filename_pattern, '', content, count=1, flags=re.IGNORECASE).strip()
        else:
            # 没有找到文件名，使用默认值
            # 生成基于时间戳的文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"result_{timestamp}.md"
            markdown_content = content.strip()
        
        # 清理 markdown 内容
        # 移除可能的 markdown 代码块包装
        if markdown_content.startswith('```markdown'):
            markdown_content = markdown_content[len('```markdown'):].strip()
        if markdown_content.startswith('```'):
            markdown_content = markdown_content[3:].strip()
        if markdown_content.endswith('```'):
            markdown_content = markdown_content[:-3].strip()
        
        return (filename, markdown_content)
    
    # ==================== 日志方法 ====================
    # NOTE: ToolUsePlanner 没走 UnifiedClient（因为需要 streaming tool calling +
    # 多轮 tool 消息历史，UnifiedClient 暂不支持），而是直接按模型名路由到
    # ChatOpenAI 或 ChatGoogleGenerativeAI（见 _create_llm）。Token 使用量通过
    # _record_token_usage() 手动记录到 request_token_tracker，provider 会根据
    # 实际后端动态设置，确保全局统计正确。
    
    def _log_request(self, messages: List[Any], log_dir: str):
        """
        记录 LLM 请求
        
        Args:
            messages: LangChain 消息列表
            log_dir: 日志目录
        """
        try:
            os.makedirs(log_dir, exist_ok=True)
            
            # 处理消息内容
            processed_messages = []
            for msg in messages:
                msg_type = type(msg).__name__
                content = getattr(msg, 'content', str(msg))
                processed_messages.append({
                    "type": msg_type,
                    "content": content[:5000] if len(content) > 5000 else content,  # 截断过长内容
                })
            
            log_data = {
                "timestamp": datetime.now().isoformat(),
                "node_id": self.node_id,
                "model": self.model,
                "max_tokens": self.max_tokens,
                "temperature": self.temperature,
                "tools": [t.name for t in self.tools] if self.tools else [],
                "messages": processed_messages,
            }
            
            filename = f"planner_{self.node_id[:20] if len(self.node_id) > 20 else self.node_id}_request.json"
            filepath = os.path.join(log_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(log_data, f, ensure_ascii=False, indent=2)

            # 同步保存可读的 markdown 版本，便于人工排查
            md_filename = filename.replace(".json", ".md")
            md_filepath = os.path.join(log_dir, md_filename)
            with open(md_filepath, 'w', encoding='utf-8') as f:
                f.write(self._format_request_markdown(log_data))
                
        except Exception as e:
            logger.logger.warning(f"[ToolUsePlanner] Failed to log request: {e}")
    
    def _log_response(
        self, 
        content: str, 
        tool_calls: List[Dict[str, Any]], 
        log_dir: str
    ):
        """
        记录 LLM 响应
        
        Args:
            content: 响应文本内容
            tool_calls: 工具调用列表
            log_dir: 日志目录
        """
        try:
            os.makedirs(log_dir, exist_ok=True)
            
            log_data = {
                "timestamp": datetime.now().isoformat(),
                "node_id": self.node_id,
                "model": self.model,
                "content": content,
                "tool_calls": tool_calls,
                "has_tool_calls": len(tool_calls) > 0,
            }
            
            filename = f"planner_{self.node_id[:20] if len(self.node_id) > 20 else self.node_id}_response.json"
            filepath = os.path.join(log_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(log_data, f, ensure_ascii=False, indent=2)

            # 同步保存可读的 markdown 版本，便于人工排查
            md_filename = filename.replace(".json", ".md")
            md_filepath = os.path.join(log_dir, md_filename)
            with open(md_filepath, 'w', encoding='utf-8') as f:
                f.write(self._format_response_markdown(log_data))
                
        except Exception as e:
            logger.logger.warning(f"[ToolUsePlanner] Failed to log response: {e}")

    def _format_request_markdown(self, log_data: Dict[str, Any]) -> str:
        """将 request 日志格式化为 markdown 文本。"""
        lines = [
            "# Planner Request Log",
            "",
            f"- timestamp: {log_data.get('timestamp', '')}",
            f"- node_id: {log_data.get('node_id', '')}",
            f"- model: {log_data.get('model', '')}",
            f"- max_tokens: {log_data.get('max_tokens', '')}",
            f"- temperature: {log_data.get('temperature', '')}",
            f"- tools: {', '.join(log_data.get('tools', []))}",
            "",
            "## Messages",
            "",
        ]

        messages = log_data.get("messages", [])
        for idx, msg in enumerate(messages, start=1):
            msg_type = msg.get("type", "Unknown")
            content = msg.get("content", "")
            lines.extend([
                f"### {idx}. {msg_type}",
                "",
                "```text",
                content,
                "```",
                "",
            ])

        return "\n".join(lines)

    def _format_response_markdown(self, log_data: Dict[str, Any]) -> str:
        """将 response 日志格式化为 markdown 文本。"""
        tool_calls = log_data.get("tool_calls", [])
        lines = [
            "# Planner Response Log",
            "",
            f"- timestamp: {log_data.get('timestamp', '')}",
            f"- node_id: {log_data.get('node_id', '')}",
            f"- model: {log_data.get('model', '')}",
            f"- has_tool_calls: {log_data.get('has_tool_calls', False)}",
            f"- tool_call_count: {len(tool_calls)}",
            "",
            "## Content",
            "",
            "```text",
            log_data.get("content", ""),
            "```",
            "",
            "## Tool Calls",
            "",
            "```json",
            json.dumps(tool_calls, ensure_ascii=False, indent=2),
            "```",
            "",
        ]
        return "\n".join(lines)
