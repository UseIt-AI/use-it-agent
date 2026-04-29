"""
Claude模型适配器

基于LangChain实现的Claude模型支持
"""

import os
from typing import Optional
from ..base.client import LangChainBasedClient, TokenUsage
from ..token_counter import TokenCounter


def _claude_api_rejects_temperature_field(model: str) -> bool:
    """
    部分 Claude API 模型对 Messages 请求里显式 `temperature` 返回 400：
    invalid_request_error — '`temperature` is deprecated for this model.'
    此类模型需从 ChatAnthropic 构造参数中省略 temperature。
    """
    m = (model or "").lower()
    if "claude-opus-4-7" in m:
        return True
    if "claude-opus-4-6" in m:
        return True
    return False


class ClaudeAdapter(LangChainBasedClient):
    """Claude模型适配器"""
    
    def __init__(
        self,
        model: str = "claude-3-5-sonnet-20241022",
        api_key: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        **kwargs
    ):
        # 获取 API 密钥（与 VLMClient._get_api_key_for_model 一致）
        if api_key is None:
            api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")

        if not api_key:
            raise ValueError(
                "Anthropic API key is required. Set ANTHROPIC_API_KEY or CLAUDE_API_KEY "
                "(e.g. in useit-agent-internal/.env), or pass api_key."
            )
        
        super().__init__(
            model=model,
            api_key=api_key,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs
        )
    
    def _create_langchain_llm(self, streaming: bool = False):
        """创建LangChain Claude实例"""
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError:
            raise ImportError("langchain-anthropic is required for Claude support. Install with: pip install langchain-anthropic")
        
        kwargs = {
            "model": self.model,
            "anthropic_api_key": self.api_key,
            "max_tokens": self.max_tokens,
            "streaming": streaming,
        }
        if not _claude_api_rejects_temperature_field(self.model):
            kwargs["temperature"] = self.temperature

        # 添加其他参数（extra 里若带 temperature，对新模型需剔除以免 400）
        extra = dict(self.extra_params or {})
        if _claude_api_rejects_temperature_field(self.model):
            extra.pop("temperature", None)
        kwargs.update(extra)

        return ChatAnthropic(**kwargs)
    
    def calculate_cost(self, token_usage: TokenUsage) -> float:
        """计算Claude模型成本"""
        return TokenCounter.calculate_cost(token_usage, self.model)
    
    def _extract_token_usage(self, response) -> TokenUsage:
        """从Claude响应中提取token使用信息"""
        metadata = getattr(response, 'response_metadata', {})
        usage_info = metadata.get('token_usage', {})
        
        # Claude的token字段可能不同
        input_tokens = usage_info.get('input_tokens', 0)
        output_tokens = usage_info.get('output_tokens', 0)
        
        return TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            model=self.model
        )


class AnthropicAdapter(ClaudeAdapter):
    """Anthropic模型适配器（Claude的别名）"""
    pass