"""
基础LLM客户端抽象类

提供统一的LLM调用接口，支持流式和非流式调用
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, AsyncGenerator, Union
from dataclasses import dataclass
import time
import logging

from .message_types import UnifiedMessage


@dataclass
class TokenUsage:
    """Token使用统计"""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    model: str = ""
    cost: float = 0.0
    
    def __post_init__(self):
        if self.total_tokens == 0:
            self.total_tokens = self.input_tokens + self.output_tokens


@dataclass 
class LLMResponse:
    """LLM响应"""
    content: str = ""
    token_usage: TokenUsage = None
    model: str = ""
    finish_reason: str = ""
    response_time: float = 0.0
    metadata: Dict[str, Any] = None
    tool_calls: List[Dict[str, Any]] = None  # Tool calling 结果
    
    def __post_init__(self):
        if self.token_usage is None:
            self.token_usage = TokenUsage()
        if self.metadata is None:
            self.metadata = {}
        if self.tool_calls is None:
            self.tool_calls = []
    
    @property
    def has_tool_calls(self) -> bool:
        """是否有工具调用"""
        return bool(self.tool_calls)


@dataclass
class StreamChunk:
    """流式响应块"""
    content: str = ""
    chunk_type: str = "text"  # text, reasoning, complete, error
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class BaseLLMClient(ABC):
    """
    基础LLM客户端抽象类
    
    定义所有LLM客户端的统一接口：
    - 支持流式和非流式调用
    - 统一的消息格式
    - Token统计功能
    - 可插拔的模型适配器
    """
    
    def __init__(
        self,
        model: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        **kwargs
    ):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.extra_params = kwargs
        
        # 统计信息
        self.total_tokens_used = 0
        self.total_cost = 0.0
        self.request_count = 0
        
        # 日志
        self.logger = logging.getLogger(f"useit.{self.__class__.__name__}")
        
        # 初始化客户端
        self._initialize_client()
    
    @abstractmethod
    def _initialize_client(self):
        """初始化具体的LLM客户端 - 子类实现"""
        pass
    
    @abstractmethod
    async def call(
        self,
        messages: List[UnifiedMessage],
        **kwargs
    ) -> LLMResponse:
        """
        非流式调用LLM
        
        Args:
            messages: 统一消息格式列表
            **kwargs: 额外参数
            
        Returns:
            LLM响应
        """
        pass
    
    @abstractmethod
    async def stream(
        self,
        messages: List[UnifiedMessage],
        **kwargs
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        流式调用LLM
        
        Args:
            messages: 统一消息格式列表
            **kwargs: 额外参数
            
        Yields:
            流式响应块
        """
        pass
    
    @abstractmethod
    def calculate_cost(self, token_usage: TokenUsage) -> float:
        """计算成本 - 子类实现"""
        pass
    
    def _update_stats(self, token_usage: TokenUsage):
        """更新统计信息"""
        self.total_tokens_used += token_usage.total_tokens
        self.total_cost += token_usage.cost
        self.request_count += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_tokens_used": self.total_tokens_used,
            "total_cost": self.total_cost,
            "request_count": self.request_count,
            "model": self.model,
            "avg_tokens_per_request": self.total_tokens_used / max(self.request_count, 1)
        }
    
    def reset_stats(self):
        """重置统计信息"""
        self.total_tokens_used = 0
        self.total_cost = 0.0
        self.request_count = 0


class LangChainBasedClient(BaseLLMClient):
    """
    基于LangChain的客户端基类
    
    提供LangChain通用功能的实现
    """
    
    def __init__(self, **kwargs):
        # IMPORTANT:
        # BaseLLMClient.__init__() calls self._initialize_client().
        # If we set llm_instance/llm_streaming_instance to None AFTER super().__init__,
        # we will accidentally wipe out the initialized clients and later crash with:
        # "'NoneType' object has no attribute 'astream'".
        self.llm_instance = None
        self.llm_streaming_instance = None
        super().__init__(**kwargs)
    
    @abstractmethod
    def _create_langchain_llm(self, streaming: bool = False):
        """创建LangChain LLM实例 - 子类实现"""
        pass
    
    def _initialize_client(self):
        """初始化LangChain客户端"""
        self.llm_instance = self._create_langchain_llm(streaming=False)
        self.llm_streaming_instance = self._create_langchain_llm(streaming=True)
    
    def _messages_to_langchain(self, messages: List[UnifiedMessage]):
        """转换消息为LangChain格式"""
        from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
        
        langchain_messages = []
        
        for msg in messages:
            lc_format = msg.to_langchain_format()
            
            if msg.role == "system":
                langchain_messages.append(SystemMessage(content=lc_format["content"]))
            elif msg.role == "user":
                langchain_messages.append(HumanMessage(content=lc_format["content"]))
            elif msg.role == "assistant":
                langchain_messages.append(AIMessage(content=lc_format["content"]))
        
        return langchain_messages
    
    async def call(
        self,
        messages: List[UnifiedMessage],
        **kwargs
    ) -> LLMResponse:
        """非流式调用"""
        start_time = time.time()
        
        try:
            # 转换消息格式
            lc_messages = self._messages_to_langchain(messages)
            
            # 调用LLM
            response = await self.llm_instance.ainvoke(lc_messages)
            
            # 处理响应
            content = response.content
            response_time = time.time() - start_time
            
            # 提取token使用信息
            token_usage = self._extract_token_usage(response)
            token_usage.model = self.model
            token_usage.cost = self.calculate_cost(token_usage)
            
            # 更新统计
            self._update_stats(token_usage)
            
            return LLMResponse(
                content=content,
                token_usage=token_usage,
                model=self.model,
                response_time=response_time,
                metadata=getattr(response, 'response_metadata', {})
            )
            
        except Exception as e:
            response_time = time.time() - start_time
            return LLMResponse(
                content=f"Error: {str(e)}",
                model=self.model,
                response_time=response_time,
                finish_reason="error"
            )
    
    async def stream(
        self,
        messages: List[UnifiedMessage],
        **kwargs
    ) -> AsyncGenerator[StreamChunk, None]:
        """流式调用"""
        try:
            if self.llm_streaming_instance is None:
                raise RuntimeError("LLM streaming client is not initialized (llm_streaming_instance is None)")
            # 转换消息格式
            lc_messages = self._messages_to_langchain(messages)

            # 收集完整响应用于token统计
            full_content = []
            last_chunk = None
            # 与 ToolUsePlanner 一致：usage 往往在「最后一个带 usage_metadata 的 chunk」上，
            # 不一定与最后一个文本 chunk 重合。
            last_chunk_with_usage = None

            # 流式调用
            async for chunk in self.llm_streaming_instance.astream(lc_messages):
                last_chunk = chunk  # 保存最后一个 chunk
                if getattr(chunk, "usage_metadata", None):
                    last_chunk_with_usage = chunk

                if hasattr(chunk, 'content') and chunk.content:
                    raw_content = chunk.content
                    
                    # 详细日志：记录原始 content 的类型和内容
                    self.logger.debug(
                        f"[LangChainBasedClient.stream] chunk.content type={type(raw_content).__name__}, "
                        f"preview={str(raw_content)[:200] if raw_content else 'None'}"
                    )
                    
                    content = raw_content
                    
                    # 处理 content 可能是列表的情况（Gemini 等模型）
                    if isinstance(content, list):
                        self.logger.debug(f"[LangChainBasedClient.stream] Processing list with {len(content)} items")
                        # 从列表中提取文本内容
                        text_parts = []
                        for i, item in enumerate(content):
                            self.logger.debug(f"[LangChainBasedClient.stream] list[{i}] type={type(item).__name__}")
                            if isinstance(item, str):
                                text_parts.append(item)
                            elif isinstance(item, dict):
                                # 尝试多种可能的键名
                                if 'text' in item:
                                    text_parts.append(str(item['text']))
                                elif 'content' in item:
                                    text_parts.append(str(item['content']))
                                else:
                                    # 最后尝试转换为字符串
                                    self.logger.debug(f"[LangChainBasedClient.stream] dict keys={list(item.keys())}")
                                    text_parts.append(str(item))
                            elif hasattr(item, 'text'):
                                text_parts.append(str(item.text))
                            else:
                                # 兜底：转换为字符串
                                self.logger.debug(f"[LangChainBasedClient.stream] fallback str() for type={type(item).__name__}")
                                text_parts.append(str(item))
                        content = "".join(text_parts)
                    elif not isinstance(content, str):
                        # 如果不是字符串也不是列表，转换为字符串
                        self.logger.debug(f"[LangChainBasedClient.stream] Converting non-str type={type(content).__name__} to str")
                        content = str(content)
                    
                    if content:  # 确保有内容
                        full_content.append(content)

                        yield StreamChunk(
                            content=content,
                            chunk_type="text",
                            metadata={"chunk": chunk}
                        )

            # 发送完成信号和token统计
            full_response_content = "".join(full_content)

            # 尝试从 chunk 中提取 token usage（优先带 usage_metadata 的 chunk）
            token_usage = None
            chunk_for_usage = last_chunk_with_usage or last_chunk
            if chunk_for_usage:
                try:
                    # 调用子类的 _extract_token_usage 方法
                    token_usage = self._extract_token_usage(chunk_for_usage)
                    if token_usage and token_usage.total_tokens > 0:
                        # 成功提取到 token usage
                        token_usage.model = self.model
                        token_usage.cost = self.calculate_cost(token_usage)
                except Exception:
                    # 提取失败，使用简单估算
                    token_usage = None

            # 如果没有提取到 token usage，使用简单估算
            if token_usage is None or token_usage.total_tokens == 0:
                estimated_tokens = len(full_response_content.split())
                token_usage = TokenUsage(
                    output_tokens=estimated_tokens,
                    total_tokens=estimated_tokens,
                    model=self.model
                )
                token_usage.cost = self.calculate_cost(token_usage)

            # 更新统计
            self._update_stats(token_usage)

            yield StreamChunk(
                content=full_response_content,
                chunk_type="complete",
                metadata={
                    "token_usage": token_usage,
                    "total_tokens": token_usage.total_tokens
                }
            )
            
        except Exception as e:
            yield StreamChunk(
                content=str(e),
                chunk_type="error",
                metadata={"error": str(e)}
            )
    
    def _extract_token_usage(self, response) -> TokenUsage:
        """从响应中提取token使用信息"""
        usage_info = getattr(response, 'response_metadata', {}).get('token_usage', {})
        
        return TokenUsage(
            input_tokens=usage_info.get('prompt_tokens', 0),
            output_tokens=usage_info.get('completion_tokens', 0),
            total_tokens=usage_info.get('total_tokens', 0)
        )
    
    async def call_with_tools(
        self,
        messages: List[UnifiedMessage],
        tools: List[Dict[str, Any]],
        tool_choice: str = "auto",
        **kwargs
    ) -> LLMResponse:
        """
        带 Tool Calling 的 LLM 调用
        
        Args:
            messages: 统一消息格式列表
            tools: 工具定义列表，格式为 OpenAI function calling 格式：
                [{
                    "name": "tool_name",
                    "description": "Tool description",
                    "parameters": {
                        "type": "object",
                        "properties": {...},
                        "required": [...]
                    }
                }]
            tool_choice: 工具选择策略
                - "auto": 模型自动决定是否调用工具
                - "required": 强制模型调用工具
                - "none": 禁止调用工具
                - 具体工具名: 强制调用指定工具
            **kwargs: 额外参数
            
        Returns:
            LLMResponse，其中 tool_calls 包含工具调用结果
        """
        start_time = time.time()
        
        try:
            # 转换消息格式
            lc_messages = self._messages_to_langchain(messages)
            
            # 转换工具格式为 LangChain 格式
            lc_tools = self._convert_tools_to_langchain(tools)
            
            # 处理 tool_choice
            lc_tool_choice = self._convert_tool_choice(tool_choice, tools)
            
            # 绑定工具到 LLM
            llm_with_tools = self.llm_instance.bind_tools(
                lc_tools,
                tool_choice=lc_tool_choice
            )
            
            # 调用 LLM
            response = await llm_with_tools.ainvoke(lc_messages)
            
            response_time = time.time() - start_time
            
            # 提取 tool_calls
            tool_calls = self._extract_tool_calls(response)
            
            # 提取 token 使用信息
            token_usage = self._extract_token_usage(response)
            token_usage.model = self.model
            token_usage.cost = self.calculate_cost(token_usage)
            
            # 更新统计
            self._update_stats(token_usage)
            
            return LLMResponse(
                content=response.content or "",
                token_usage=token_usage,
                model=self.model,
                response_time=response_time,
                metadata=getattr(response, 'response_metadata', {}),
                tool_calls=tool_calls,
            )
            
        except Exception as e:
            response_time = time.time() - start_time
            self.logger.error(f"LLM call_with_tools failed: {e}")
            return LLMResponse(
                content=f"Error: {str(e)}",
                model=self.model,
                response_time=response_time,
                finish_reason="error"
            )
    
    def _convert_tools_to_langchain(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        转换工具定义为 LangChain 格式
        
        输入格式（OpenAI function calling 格式）：
        [{
            "name": "execute_powershell",
            "description": "Execute PowerShell code",
            "parameters": {
                "type": "object",
                "properties": {"code": {"type": "string"}},
                "required": ["code"]
            }
        }]
        
        LangChain 使用相同格式，直接返回
        """
        return tools
    
    def _convert_tool_choice(
        self, 
        tool_choice: str, 
        tools: List[Dict[str, Any]]
    ) -> Any:
        """
        转换 tool_choice 为 LangChain 格式
        
        Args:
            tool_choice: "auto" | "required" | "none" | 具体工具名
            tools: 工具列表
            
        Returns:
            LangChain 格式的 tool_choice
        """
        if tool_choice == "auto":
            return "auto"
        elif tool_choice == "required":
            # 对于 "required"，LangChain 某些模型可能需要不同处理
            # Gemini: 使用 "any"
            # OpenAI: 使用 "required"
            return "any"  # LangChain 统一用 "any" 表示必须调用工具
        elif tool_choice == "none":
            return "none"
        else:
            # 具体工具名 - 强制调用指定工具
            return {"type": "function", "function": {"name": tool_choice}}
    
    def _extract_tool_calls(self, response) -> List[Dict[str, Any]]:
        """
        从 LangChain 响应中提取 tool_calls
        
        Returns:
            工具调用列表，格式：
            [{
                "id": "call_xxx",
                "name": "tool_name",
                "args": {"arg1": "value1", ...}
            }]
        """
        tool_calls = []
        
        if hasattr(response, 'tool_calls') and response.tool_calls:
            for tc in response.tool_calls:
                # LangChain 的 tool_call 格式
                if isinstance(tc, dict):
                    tool_calls.append({
                        "id": tc.get("id", ""),
                        "name": tc.get("name", ""),
                        "args": tc.get("args", {}),
                    })
                else:
                    # 可能是对象格式
                    tool_calls.append({
                        "id": getattr(tc, "id", ""),
                        "name": getattr(tc, "name", ""),
                        "args": getattr(tc, "args", {}),
                    })
        
        return tool_calls