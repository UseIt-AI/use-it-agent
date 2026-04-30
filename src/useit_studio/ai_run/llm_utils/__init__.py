"""
统一LLM工具包

提供统一的LLM调用接口，支持多种模型和调用格式
"""

from .unified_client import UnifiedClient, call_llm, stream_llm
from .message_builder import MessageBuilder, InterleaveListBuilder
from .token_counter import TokenCounter, TokenTracker, global_token_tracker
from .config import LLMConfig, ConfigManager, APIKeyManager, global_config_manager, global_api_key_manager

# 导出基础类型
from .base import (
    BaseLLMClient, LangChainBasedClient, 
    LLMResponse, StreamChunk, TokenUsage,
    UnifiedMessage, TextMessageContent, ImageMessageContent,
    interleave_to_messages
)

# 导出所有适配器
from .adapters import (
    OpenAIAdapter, GPTAdapter, OpenAIResponsesAdapter,
    ClaudeAdapter, AnthropicAdapter,
    GeminiAdapter, GoogleAdapter,
    vLLMAdapter, LocalLLMAdapter, HuggingFaceAdapter
)

__version__ = "1.0.0"

__all__ = [
    # 核心客户端
    "UnifiedClient",
    "call_llm", 
    "stream_llm",
    
    # 消息构建
    "MessageBuilder",
    "InterleaveListBuilder",
    "UnifiedMessage",
    "TextMessageContent",
    "ImageMessageContent", 
    "interleave_to_messages",
    
    # Token统计
    "TokenCounter",
    "TokenTracker",
    "global_token_tracker",
    "TokenUsage",
    
    # 配置管理
    "LLMConfig",
    "ConfigManager",
    "APIKeyManager",
    "global_config_manager",
    "global_api_key_manager",
    
    # 基础类型
    "BaseLLMClient",
    "LangChainBasedClient",
    "LLMResponse", 
    "StreamChunk",
    
    # 所有适配器
    "OpenAIAdapter",
    "GPTAdapter",
    "OpenAIResponsesAdapter", 
    "ClaudeAdapter",
    "AnthropicAdapter",
    "GeminiAdapter",
    "GoogleAdapter",
    "vLLMAdapter",
    "LocalLLMAdapter",
    "HuggingFaceAdapter",
]


def get_client(
    model: str = "gpt-5.2",
    provider: str = None,
    config_name: str = "default",
    **kwargs
) -> UnifiedClient:
    """
    获取配置好的统一客户端
    
    Args:
        model: 模型名称
        provider: 提供商名称
        config_name: 配置名称（从配置文件读取）
        **kwargs: 额外参数
        
    Returns:
        配置好的UnifiedClient实例
    """
    # 从配置文件加载配置
    if config_name and config_name in global_config_manager.configs:
        config = global_config_manager.get_config(config_name)
        
        # 合并参数
        params = {
            "model": model or config.model,
            "provider": provider or config.provider,
            "api_key": config.api_key,
            "base_url": config.base_url,
            "max_tokens": config.max_tokens,
            "temperature": config.temperature,
            **config.extra_params,
            **kwargs  # kwargs优先级最高
        }
    else:
        params = {
            "model": model,
            "provider": provider,
            **kwargs
        }
    
    # 如果没有指定api_key，尝试从APIKeyManager获取
    if not params.get("api_key") and provider:
        api_key = global_api_key_manager.get_key(provider)
        if api_key:
            params["api_key"] = api_key
    
    return UnifiedClient(**params)


def list_models() -> dict:
    """
    列出支持的模型
    
    Returns:
        按提供商分组的模型列表
    """
    return {
        "openai": [
            "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4", "gpt-3.5-turbo"
        ],
        "openai_responses": [
            "gpt-5", "gpt-5.1", "o1", "o1-preview", "o1-mini"
        ],
        "claude": [
            "claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022", "claude-3-opus-20240229"
        ],
        "gemini": [
            "gemini-1.5-pro", "gemini-1.5-flash"
        ],
        "local": [
            "llama-2-7b-chat", "mistral-7b", "qwen-7b", "custom-model"
        ]
    }


# 简化的使用示例
"""
# 基本使用
from useit_studio.ai_run.llm_utils import call_llm, stream_llm

# 非流式调用
response = await call_llm(
    messages=["What is AI?", "image.png", "Explain this image"], 
    model="gpt-4o"
)
print(response.content)

# 流式调用
async for chunk in stream_llm(
    messages=["Tell me a story"], 
    model="claude-3-5-sonnet"
):
    if chunk.chunk_type == "text":
        print(chunk.content, end="")

# 使用统一客户端
from useit_studio.ai_run.llm_utils import UnifiedClient

client = UnifiedClient(model="gemini-1.5-flash")
response = await client.call(["Hello world"])
print(response.content)

# 使用配置
from useit_studio.ai_run.llm_utils import get_client

client = get_client(config_name="claude")  # 从配置文件加载
response = await client.call(["How are you?"])
"""