"""
OpenAI模型适配器

基于LangChain实现的OpenAI模型支持
"""

import os
from typing import Dict, List, Any, Optional, AsyncGenerator
from langchain_openai import ChatOpenAI

from ..base.client import LangChainBasedClient, LLMResponse, TokenUsage
from ..token_counter import TokenCounter


class OpenAIAdapter(LangChainBasedClient):
    """OpenAI模型适配器"""
    
    def __init__(
        self,
        model: str = "gpt-4o-mini",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        **kwargs
    ):
        # 获取API密钥
        if api_key is None:
            api_key = os.getenv("OPENAI_API_KEY")
        
        if not api_key:
            raise ValueError("OpenAI API key is required. Set OPENAI_API_KEY environment variable or pass api_key parameter.")
        
        super().__init__(
            model=model,
            api_key=api_key,
            base_url=base_url,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs
        )
    
    def _create_langchain_llm(self, streaming: bool = False) -> ChatOpenAI:
        """创建LangChain ChatOpenAI实例"""
        kwargs = {
            "model": self.model,
            "openai_api_key": self.api_key,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "streaming": streaming,
        }

        # 如果有自定义base_url
        if self.base_url:
            kwargs["openai_api_base"] = self.base_url

        # 处理 response_format（需要通过 model_kwargs 传递给 OpenAI API）
        model_kwargs = {}
        extra_params_copy = self.extra_params.copy()
        if "response_format" in extra_params_copy:
            model_kwargs["response_format"] = extra_params_copy.pop("response_format")

        # 添加其他参数
        kwargs.update(extra_params_copy)

        # 如果有 model_kwargs，添加到参数中
        if model_kwargs:
            kwargs["model_kwargs"] = model_kwargs

        return ChatOpenAI(**kwargs)
    
    def calculate_cost(self, token_usage: TokenUsage) -> float:
        """计算OpenAI模型成本"""
        return TokenCounter.calculate_cost(token_usage, self.model)
    
    def _extract_token_usage(self, response) -> TokenUsage:
        """从OpenAI响应中提取token使用信息"""
        # LangChain ChatOpenAI的响应格式
        metadata = getattr(response, 'response_metadata', {})
        usage_info = metadata.get('token_usage', {})
        
        return TokenUsage(
            input_tokens=usage_info.get('prompt_tokens', 0),
            output_tokens=usage_info.get('completion_tokens', 0),
            total_tokens=usage_info.get('total_tokens', 0),
            model=self.model
        )


class GPTAdapter(OpenAIAdapter):
    """GPT模型适配器（OpenAI的别名）"""
    pass


class OpenAIResponsesAdapter(LangChainBasedClient):
    """
    OpenAI Responses API适配器
    
    专门用于支持gpt-5等新模型的Responses API
    """
    
    def __init__(
        self,
        model: str = "gpt-5.2",
        api_key: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        **kwargs
    ):
        # 检查是否为支持的模型
        if not model.startswith(('gpt-5', 'o1')):
            raise ValueError(f"OpenAI Responses API adapter only supports gpt-5 and o1 models, got {model}")
        
        super().__init__(
            model=model,
            api_key=api_key,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs
        )
    
    def _create_langchain_llm(self, streaming: bool = False):
        """
        对于Responses API，我们需要使用自定义的实现
        因为LangChain可能还不支持Responses API
        """
        # 这里我们将使用自定义的Responses API包装器
        from .responses_api_wrapper import ResponsesAPILLM
        
        return ResponsesAPILLM(
            model=self.model,
            api_key=self.api_key,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            streaming=streaming,
            **self.extra_params
        )
    
    def calculate_cost(self, token_usage: TokenUsage) -> float:
        """计算Responses API模型成本"""
        return TokenCounter.calculate_cost(token_usage, self.model)

    def _extract_token_usage(self, response) -> TokenUsage:
        """从Responses API响应中提取token使用信息"""
        # ResponsesAPILLM 的响应格式
        metadata = getattr(response, 'response_metadata', {})

        # token_usage 可能在 metadata 或 metadata['token_usage'] 中
        if 'token_usage' in metadata:
            usage_info = metadata['token_usage']
            return TokenUsage(
                input_tokens=usage_info.get('prompt_tokens', 0),
                output_tokens=usage_info.get('completion_tokens', 0),
                total_tokens=usage_info.get('total_tokens', 0),
                model=self.model
            )

        # 如果没有 token_usage，返回空统计
        return TokenUsage(
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            model=self.model
        )

    # ------------------------------------------------------------------
    # Tool calling via native Responses API (bypasses LangChain bind_tools)
    # ------------------------------------------------------------------

    async def call_with_tools(
        self,
        messages: list,
        tools: list,
        tool_choice: str = "auto",
        **kwargs,
    ) -> LLMResponse:
        """
        Tool calling using the OpenAI Responses API natively.

        The parent ``LangChainBasedClient.call_with_tools`` relies on
        ``bind_tools`` which ``ResponsesAPILLM`` does not support.
        This override calls the Responses API directly with the
        ``tools`` parameter.
        """
        import asyncio
        import json as _json
        import logging
        import time

        logger = logging.getLogger(__name__)
        start_time = time.time()

        # Ensure the underlying LLM (and its OpenAI client) is ready
        if not hasattr(self, 'llm_instance') or self.llm_instance is None:
            self.llm_instance = self._create_langchain_llm(streaming=False)
        client = self.llm_instance._client  # OpenAI sync client

        # UnifiedClient passes List[UnifiedMessage]; Responses wrapper expects LangChain BaseMessage
        lc_messages = self._messages_to_langchain(messages)
        responses_input = self.llm_instance._convert_messages_to_responses_format(lc_messages)

        # Convert flat tool defs to Responses API format
        api_tools = []
        for t in tools:
            api_tools.append({
                "type": "function",
                "name": t.get("name", ""),
                "description": t.get("description", ""),
                "parameters": t.get("parameters", {"type": "object", "properties": {}}),
            })

        # Build create kwargs
        create_kwargs: dict = {
            "model": self.model,
            "input": responses_input,
            "tools": api_tools,
            "max_output_tokens": self.max_tokens,
        }

        # tool_choice mapping
        if tool_choice == "required":
            create_kwargs["tool_choice"] = "required"
        elif tool_choice == "none":
            create_kwargs["tool_choice"] = "none"
        elif tool_choice not in ("auto", None):
            # Specific tool name
            create_kwargs["tool_choice"] = {
                "type": "function",
                "name": tool_choice,
            }

        if self.model.startswith("gpt-5"):
            create_kwargs["reasoning"] = {"effort": "none"}

        logger.info("[ResponsesAPI] call_with_tools: model=%s tools=%d tool_choice=%s",
                     self.model, len(api_tools), tool_choice)

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, lambda: client.responses.create(**create_kwargs)
            )
        except Exception as exc:
            elapsed = time.time() - start_time
            logger.error("[ResponsesAPI] call_with_tools failed (%.1fs): %s", elapsed, exc)
            return LLMResponse(
                content=f"Error: {exc}",
                model=self.model,
                response_time=elapsed,
                finish_reason="error",
            )

        elapsed = time.time() - start_time

        # Extract tool calls and text from response outputs
        tool_calls = []
        text_parts = []

        for output in getattr(response, "output", []):
            output_type = getattr(output, "type", None)

            if output_type == "function_call":
                call_id = getattr(output, "call_id", "") or getattr(output, "id", "")
                name = getattr(output, "name", "")
                arguments_raw = getattr(output, "arguments", "{}")
                try:
                    args = _json.loads(arguments_raw) if isinstance(arguments_raw, str) else arguments_raw
                except _json.JSONDecodeError:
                    args = {}
                tool_calls.append({"id": call_id, "name": name, "args": args})

            elif output_type == "message":
                for content_item in getattr(output, "content", []):
                    if hasattr(content_item, "text"):
                        text_parts.append(content_item.text)

        # Token usage
        usage = getattr(response, "usage", None)
        if usage:
            token_usage = TokenUsage(
                input_tokens=getattr(usage, "input_tokens", 0),
                output_tokens=getattr(usage, "output_tokens", 0),
                total_tokens=getattr(usage, "total_tokens", 0),
                model=self.model,
            )
            token_usage.cost = self.calculate_cost(token_usage)
        else:
            token_usage = TokenUsage(model=self.model)

        self._update_stats(token_usage)

        content = "\n".join(text_parts)
        logger.info("[ResponsesAPI] call_with_tools done (%.1fs): tool_calls=%d text_len=%d",
                     elapsed, len(tool_calls), len(content))

        return LLMResponse(
            content=content,
            token_usage=token_usage,
            model=self.model,
            response_time=elapsed,
            finish_reason="tool_calls" if tool_calls else "stop",
            tool_calls=tool_calls,
        )