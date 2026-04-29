"""
Gemini模型适配器

基于LangChain实现的Gemini模型支持。
对 Gemini 2.5 / 3 系列等原生 Thinking 模型，通过 thinking_budget=0
关闭原生思考，让模型遵循 prompt 在文本中输出 <thinking> 块，
使流式输出行为与 GPT 完全一致。
"""

import os
import logging
from typing import Optional

from ..base.client import LangChainBasedClient, TokenUsage
from ..token_counter import TokenCounter

logger = logging.getLogger(__name__)


class GeminiAdapter(LangChainBasedClient):
    """Gemini模型适配器"""

    _THINKING_MODEL_PREFIXES = ("gemini-2.5", "gemini-3")

    def __init__(
        self,
        model: str = "gemini-1.5-flash",
        api_key: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        **kwargs
    ):
        if api_key is None:
            api_key = os.getenv("GOOGLE_API_KEY")

        if not api_key:
            raise ValueError(
                "Google API key is required. "
                "Set GOOGLE_API_KEY environment variable or pass api_key parameter."
            )

        super().__init__(
            model=model,
            api_key=api_key,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs
        )

    def _is_thinking_model(self) -> bool:
        model_lower = self.model.lower()
        return any(model_lower.startswith(p) for p in self._THINKING_MODEL_PREFIXES)

    def _create_langchain_llm(self, streaming: bool = False):
        """创建LangChain Gemini实例"""
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError:
            raise ImportError(
                "langchain-google-genai is required for Gemini support. "
                "Install with: pip install langchain-google-genai"
            )

        kwargs = {
            "model": self.model,
            "google_api_key": self.api_key,
            "temperature": self.temperature,
            "max_output_tokens": self.max_tokens,
            "streaming": streaming,
        }

        # Gemini 2.5+ / 3+ 原生 Thinking 模型：
        # 设置 thinking_budget=0 关闭原生思考，让模型遵循 prompt 中的
        # <thinking> 指令在文本中输出思考过程，与 GPT 行为完全一致。
        if self._is_thinking_model():
            kwargs["thinking_budget"] = 0
            logger.info(
                "[GeminiAdapter] Thinking model detected (%s), "
                "set thinking_budget=0 to use prompt-based <thinking> instead",
                self.model,
            )

        kwargs.update(self.extra_params)

        try:
            return ChatGoogleGenerativeAI(**kwargs)
        except TypeError:
            if self._is_thinking_model():
                logger.warning(
                    "[GeminiAdapter] thinking_budget not supported by current "
                    "langchain-google-genai version, falling back without it"
                )
                kwargs.pop("thinking_budget", None)
                return ChatGoogleGenerativeAI(**kwargs)
            raise

    def calculate_cost(self, token_usage: TokenUsage) -> float:
        """计算Gemini模型成本"""
        return TokenCounter.calculate_cost(token_usage, self.model)

    def _extract_token_usage(self, response) -> TokenUsage:
        """从Gemini响应中提取token使用信息

        - LangChain 在 **usage_metadata** 上常用 input_tokens / output_tokens。
        - Google 原生在 **response_metadata.usage_metadata** 里用 prompt_token_count 等。
        两处可能只填其一或 input 一侧为 0，故合并后再做一次 total 差值补全。
        """
        # --- LangChain 顶层 usage_metadata ---
        lc_in = lc_out = lc_tot = 0
        um = getattr(response, "usage_metadata", None)
        if isinstance(um, dict) and um:
            it = um.get("input_tokens")
            if it is None:
                it = um.get("prompt_tokens")
            ot = um.get("output_tokens")
            if ot is None:
                ot = um.get("completion_tokens")
            tt = um.get("total_tokens")
            lc_in = int(it or 0)
            lc_out = int(ot or 0)
            lc_tot = int(tt) if tt is not None else lc_in + lc_out
            if lc_in == 0 and lc_tot > lc_out >= 0:
                lc_in = max(0, lc_tot - lc_out)

        # --- response_metadata（Google / 旧版 LangChain）---
        metadata = getattr(response, "response_metadata", {}) or {}
        self.logger.debug(
            "[GeminiAdapter] response_metadata keys: %s", list(metadata.keys())
        )
        usage_info = metadata.get("usage_metadata") or metadata.get("token_usage") or {}
        if not isinstance(usage_info, dict):
            usage_info = {}

        g_in = int(
            usage_info.get("prompt_token_count", 0)
            or usage_info.get("input_tokens", 0)
            or usage_info.get("prompt_tokens", 0)
        )
        g_out = int(
            usage_info.get("candidates_token_count", 0)
            or usage_info.get("output_tokens", 0)
            or usage_info.get("completion_tokens", 0)
        )
        g_tot = int(
            usage_info.get("total_token_count", 0)
            or usage_info.get("total_tokens", 0)
            or (g_in + g_out)
        )
        if g_in == 0 and g_tot > g_out >= 0:
            g_in = max(0, g_tot - g_out)

        # 合并：优先非零的 input；output/total 取较大者以免漏计
        input_tokens = max(lc_in, g_in)
        output_tokens = max(lc_out, g_out)
        total_tokens = max(lc_tot, g_tot)
        if total_tokens == 0:
            total_tokens = input_tokens + output_tokens
        if input_tokens == 0 and total_tokens > output_tokens >= 0:
            input_tokens = max(0, total_tokens - output_tokens)

        self.logger.debug(
            "[GeminiAdapter] merged usage lc=(%s,%s,%s) google=(%s,%s,%s) -> in=%s out=%s tot=%s",
            lc_in,
            lc_out,
            lc_tot,
            g_in,
            g_out,
            g_tot,
            input_tokens,
            output_tokens,
            total_tokens,
        )

        return TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            model=self.model,
        )


class GoogleAdapter(GeminiAdapter):
    """Google模型适配器（Gemini的别名）"""
    pass
