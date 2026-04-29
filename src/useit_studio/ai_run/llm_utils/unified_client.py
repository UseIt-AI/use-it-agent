"""
统一LLM客户端

提供统一的LLM调用入口，支持所有模型和调用格式
"""

from typing import Dict, List, Any, Optional, AsyncGenerator, Union
import logging

from .base import BaseLLMClient, LLMResponse, StreamChunk, UnifiedMessage
from .message_builder import MessageBuilder
from .token_counter import global_token_tracker
from .request_token_tracker import get_current as get_current_tracker
from .adapters import (
    OpenAIAdapter, GPTAdapter, OpenAIResponsesAdapter,
    ClaudeAdapter, AnthropicAdapter,
    GeminiAdapter, GoogleAdapter,
    vLLMAdapter, LocalLLMAdapter, HuggingFaceAdapter
)


# 模型到适配器的映射
MODEL_ADAPTERS = {
    # OpenAI模型
    "gpt-4o": OpenAIAdapter,
    "gpt-4o-mini": OpenAIAdapter,
    "gpt-4-turbo": OpenAIAdapter,
    "gpt-4": OpenAIAdapter,
    "gpt-3.5-turbo": OpenAIAdapter,
    
    # OpenAI Responses API模型
    "gpt-5": OpenAIResponsesAdapter,
    "gpt-5.1": OpenAIResponsesAdapter,
    "gpt-5.2": OpenAIResponsesAdapter,
    "o1": OpenAIResponsesAdapter,
    "o1-preview": OpenAIResponsesAdapter,
    "o1-mini": OpenAIResponsesAdapter,
    
    # Claude模型
    "claude-3-5-sonnet": ClaudeAdapter,
    "claude-3-5-haiku": ClaudeAdapter,
    "claude-3-opus": ClaudeAdapter,
    "claude": ClaudeAdapter,
    
    # Gemini模型
    "gemini-1.5-pro": GeminiAdapter,
    "gemini-1.5-flash": GeminiAdapter,
    "gemini-2.0-flash": GeminiAdapter,
    "gemini-2.5-flash-preview": GeminiAdapter,
    "gemini-3-flash-preview": GeminiAdapter,
    "gemini-3-pro-preview": GeminiAdapter,
    "gemini-3.1-pro-preview": GeminiAdapter,
    "gemini-3.1-flash-lite-preview": GeminiAdapter,
    "gemini": GeminiAdapter,
    
    # 本地/vLLM模型
    "llama": vLLMAdapter,
    "mistral": vLLMAdapter,
    "qwen": vLLMAdapter,
}

# Provider到适配器的映射
PROVIDER_ADAPTERS = {
    "openai": OpenAIAdapter,
    "gpt": OpenAIAdapter,
    "responses": OpenAIResponsesAdapter,
    "claude": ClaudeAdapter,
    "anthropic": ClaudeAdapter,
    "gemini": GeminiAdapter,
    "google": GeminiAdapter,
    "vllm": vLLMAdapter,
    "local": vLLMAdapter,
    "huggingface": HuggingFaceAdapter,
}


# Adapter class name -> provider string (用于 request_token_tracker)
ADAPTER_PROVIDER = {
    "OpenAIAdapter": "openai",
    "GPTAdapter": "openai",
    "OpenAIResponsesAdapter": "openai",
    "ClaudeAdapter": "anthropic",
    "AnthropicAdapter": "anthropic",
    "GeminiAdapter": "google",
    "GoogleAdapter": "google",
}


class UnifiedClient:
    """
    统一LLM客户端

    提供统一的接口来调用各种LLM模型，支持：
    - 多种模型（OpenAI、Claude、Gemini、vLLM等）
    - Interleave list格式输入
    - 流式和非流式调用
    - Token统计和成本追踪
    """
    
    def __init__(
        self,
        model: str = "gpt-4o-mini",
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        session_id: str = "default",
        **kwargs
    ):
        """
        初始化统一客户端
        
        Args:
            model: 模型名称
            provider: 提供商名称（可选，会自动推断）
            api_key: API密钥（可选，从环境变量获取）
            base_url: API基础URL（可选）
            max_tokens: 最大token数
            temperature: 温度参数
            session_id: 会话ID（用于统计追踪）
            **kwargs: 其他模型参数
        """
        self.model = model
        self.provider = provider
        self.session_id = session_id
        self.logger = logging.getLogger(__name__)
        
        # 选择适配器
        self.adapter_class = self._select_adapter(model, provider)
        
        # 创建适配器实例
        self.adapter = self.adapter_class(
            model=model,
            api_key=api_key,
            base_url=base_url,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs
        )
    
    def _select_adapter(self, model: str, provider: Optional[str] = None) -> type:
        """选择合适的适配器"""
        # 优先使用指定的provider
        if provider:
            adapter_class = PROVIDER_ADAPTERS.get(provider.lower())
            if adapter_class:
                return adapter_class
        
        # 根据model名称匹配
        model_lower = model.lower()

        # Claude 4.x / 3.x 官方 id（避免仅依赖模糊 dict 顺序）
        if model_lower.startswith("claude-"):
            return ClaudeAdapter

        # ---- High priority routing for Responses API models ----
        # gpt-5.x / o1* should always go through OpenAI Responses API adapter.
        # This avoids accidental fallback to ChatCompletions adapters caused by fuzzy matching
        # (e.g. matching "gpt" keyword and selecting OpenAIAdapter).
        if model_lower.startswith("gpt-5") or model_lower.startswith("o1"):
            return OpenAIResponsesAdapter
        
        # 精确匹配
        if model_lower in MODEL_ADAPTERS:
            return MODEL_ADAPTERS[model_lower]
        
        # 模糊匹配
        # Note: avoid overly-generic keyword matches like "gpt" that can misroute models.
        for model_key, adapter_class in MODEL_ADAPTERS.items():
            if model_key in model_lower:
                return adapter_class
        for model_key, adapter_class in MODEL_ADAPTERS.items():
            keywords = [k for k in model_key.split("-") if k and k not in {"gpt"}]
            if any(keyword in model_lower for keyword in keywords):
                return adapter_class
        
        # 默认使用OpenAI适配器
        self.logger.warning(f"Unknown model {model}, falling back to OpenAI adapter")
        return OpenAIAdapter

    def _record_to_request_tracker(self, token_usage):
        """将 token 使用量记录到 request-level tracker（如果已绑定）"""
        tracker = get_current_tracker()
        if tracker and token_usage:
            provider = ADAPTER_PROVIDER.get(self.adapter_class.__name__, "unknown")
            tracker.record(
                input_tokens=token_usage.input_tokens,
                output_tokens=token_usage.output_tokens,
                total_tokens=token_usage.total_tokens,
                model=token_usage.model or self.model,
                provider=provider,
            )

    async def call(
        self,
        messages: Union[List[str], List[Dict], List[UnifiedMessage], str],
        system_prompt: str = "",
        **kwargs
    ) -> LLMResponse:
        """
        非流式调用LLM
        
        Args:
            messages: 支持多种格式：
                - Interleave list: ["text", "image.png", "text"]
                - Chat format: [{"role": "user", "content": "..."}]
                - UnifiedMessage列表
                - 单个字符串
            system_prompt: 系统提示词
            **kwargs: 额外参数
            
        Returns:
            LLM响应
        """
        try:
            # 转换消息格式
            unified_messages = self._convert_messages(messages, system_prompt)
            
            # 调用适配器
            response = await self.adapter.call(unified_messages, **kwargs)
            
            # 追踪token使用
            global_token_tracker.track_usage(
                session_id=self.session_id,
                token_usage=response.token_usage,
                operation="call"
            )
            self._record_to_request_tracker(response.token_usage)

            return response
            
        except Exception as e:
            self.logger.error(f"LLM call failed: {e}")
            return LLMResponse(
                content=f"Error: {str(e)}",
                model=self.model,
                finish_reason="error"
            )
    
    async def stream(
        self,
        messages: Union[List[str], List[Dict], List[UnifiedMessage], str],
        system_prompt: str = "",
        **kwargs
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        流式调用LLM
        
        Args:
            messages: 支持多种格式（同call方法）
            system_prompt: 系统提示词
            **kwargs: 额外参数
            
        Yields:
            流式响应块
        """
        try:
            # 转换消息格式
            unified_messages = self._convert_messages(messages, system_prompt)
            
            # 流式调用适配器
            async for chunk in self.adapter.stream(unified_messages, **kwargs):
                yield chunk
                
                # 如果是完成块，追踪token使用
                if chunk.chunk_type == "complete":
                    token_usage = chunk.metadata.get("token_usage")
                    if token_usage:
                        global_token_tracker.track_usage(
                            session_id=self.session_id,
                            token_usage=token_usage,
                            operation="stream"
                        )
                        self._record_to_request_tracker(token_usage)
            
        except Exception as e:
            self.logger.error(f"LLM stream failed: {e}")
            yield StreamChunk(
                content=str(e),
                chunk_type="error",
                metadata={"error": str(e)}
            )
    
    def _convert_messages(
        self,
        messages: Union[List[str], List[Dict], List[UnifiedMessage], str],
        system_prompt: str = ""
    ) -> List[UnifiedMessage]:
        """转换各种消息格式为统一格式"""
        if isinstance(messages, str):
            # 单个字符串
            return MessageBuilder.from_simple_format(text=messages, system_prompt=system_prompt)
        
        elif isinstance(messages, list):
            if not messages:
                return MessageBuilder.from_simple_format(system_prompt=system_prompt)
            
            # 检查第一个元素的类型来判断格式
            first_item = messages[0]
            
            if isinstance(first_item, UnifiedMessage):
                # 已经是UnifiedMessage格式
                if system_prompt:
                    # 添加系统消息
                    system_msg = UnifiedMessage("system")
                    system_msg.add_text(system_prompt)
                    return [system_msg] + messages
                return messages
            
            elif isinstance(first_item, dict) and "role" in first_item:
                # Chat format: [{"role": "user", "content": "..."}]
                return MessageBuilder.from_chat_format(messages, system_prompt)
            
            else:
                # Interleave list: ["text", "image.png", ...]
                return MessageBuilder.from_interleave_list(messages, system_prompt)
        
        else:
            # 其他类型转为字符串
            return MessageBuilder.from_simple_format(text=str(messages), system_prompt=system_prompt)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        adapter_stats = self.adapter.get_stats()
        session_stats = global_token_tracker.get_session_stats(self.session_id)
        
        return {
            "adapter": adapter_stats,
            "session": session_stats,
            "model": self.model,
            "provider": self.provider or "auto",
            "session_id": self.session_id
        }
    
    def reset_stats(self):
        """重置统计信息"""
        self.adapter.reset_stats()
        global_token_tracker.reset_session(self.session_id)
    
    async def call_with_tools(
        self,
        messages: Union[List[str], List[Dict], List[UnifiedMessage], str],
        tools: List[Dict],
        system_prompt: str = "",
        tool_choice: str = "auto",
        **kwargs
    ) -> LLMResponse:
        """
        带 Tool Calling 的 LLM 调用
        
        Args:
            messages: 支持多种格式（同 call 方法）
            tools: 工具定义列表，格式：
                [{
                    "name": "tool_name",
                    "description": "Tool description",
                    "parameters": {
                        "type": "object",
                        "properties": {...},
                        "required": [...]
                    }
                }]
            system_prompt: 系统提示词
            tool_choice: 工具选择策略
                - "auto": 模型自动决定是否调用工具
                - "required": 强制模型调用工具
                - "none": 禁止调用工具
                - 具体工具名: 强制调用指定工具
            **kwargs: 额外参数
            
        Returns:
            LLMResponse，其中 tool_calls 包含工具调用结果
            
        Example:
            tools = [{
                "name": "execute_code",
                "description": "Execute code",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string", "description": "Code to execute"}
                    },
                    "required": ["code"]
                }
            }]
            
            response = await client.call_with_tools(
                messages="Write code to print hello",
                tools=tools,
                tool_choice="required"
            )
            
            if response.has_tool_calls:
                code = response.tool_calls[0]["args"]["code"]
        """
        try:
            # 转换消息格式
            unified_messages = self._convert_messages(messages, system_prompt)
            
            # 调用适配器的 call_with_tools
            response = await self.adapter.call_with_tools(
                unified_messages, 
                tools=tools,
                tool_choice=tool_choice,
                **kwargs
            )
            
            # 追踪 token 使用
            global_token_tracker.track_usage(
                session_id=self.session_id,
                token_usage=response.token_usage,
                operation="call_with_tools"
            )
            self._record_to_request_tracker(response.token_usage)

            return response
            
        except Exception as e:
            self.logger.error(f"LLM call_with_tools failed: {e}")
            return LLMResponse(
                content=f"Error: {str(e)}",
                model=self.model,
                finish_reason="error"
            )


# 便捷函数
async def call_llm(
    messages: Union[List[str], List[Dict], str],
    model: str = "gpt-4o-mini",
    system_prompt: str = "",
    provider: Optional[str] = None,
    **kwargs
) -> LLMResponse:
    """
    便捷的LLM调用函数
    
    Args:
        messages: 消息（支持interleave list等多种格式）
        model: 模型名称
        system_prompt: 系统提示词
        provider: 提供商（可选）
        **kwargs: 其他参数
        
    Returns:
        LLM响应
    """
    client = UnifiedClient(model=model, provider=provider, **kwargs)
    return await client.call(messages, system_prompt)


async def stream_llm(
    messages: Union[List[str], List[Dict], str],
    model: str = "gpt-4o-mini",
    system_prompt: str = "",
    provider: Optional[str] = None,
    **kwargs
) -> AsyncGenerator[StreamChunk, None]:
    """
    便捷的LLM流式调用函数
    
    Args:
        messages: 消息（支持interleave list等多种格式）
        model: 模型名称
        system_prompt: 系统提示词
        provider: 提供商（可选）
        **kwargs: 其他参数
        
    Yields:
        流式响应块
    """
    client = UnifiedClient(model=model, provider=provider, **kwargs)
    async for chunk in client.stream(messages, system_prompt):
        yield chunk