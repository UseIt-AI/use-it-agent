"""
基础抽象层

提供LLM客户端的基础抽象类和消息类型定义
"""

from .client import BaseLLMClient, LangChainBasedClient, LLMResponse, StreamChunk, TokenUsage
from .message_types import UnifiedMessage, TextMessageContent, ImageMessageContent, interleave_to_messages

__all__ = [
    "BaseLLMClient",
    "LangChainBasedClient", 
    "LLMResponse",
    "StreamChunk",
    "TokenUsage",
    "UnifiedMessage",
    "TextMessageContent", 
    "ImageMessageContent",
    "interleave_to_messages"
]