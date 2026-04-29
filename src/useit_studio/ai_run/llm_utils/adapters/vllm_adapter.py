"""
vLLM模型适配器

支持本地部署的vLLM模型
"""

import os
from typing import Optional
from ..base.client import LangChainBasedClient, TokenUsage
from ..token_counter import TokenCounter


class vLLMAdapter(LangChainBasedClient):
    """vLLM模型适配器"""
    
    def __init__(
        self,
        model: str = "llama-2-7b-chat",
        api_key: Optional[str] = None,
        base_url: str = "http://localhost:8000",
        max_tokens: int = 4096,
        temperature: float = 0.0,
        **kwargs
    ):
        # vLLM通常不需要API key，但可以设置用于认证
        if api_key is None:
            api_key = os.getenv("VLLM_API_KEY", "dummy-key")  # 使用dummy key
        
        super().__init__(
            model=model,
            api_key=api_key,
            base_url=base_url,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs
        )
    
    def _create_langchain_llm(self, streaming: bool = False):
        """创建LangChain vLLM实例"""
        try:
            from langchain_community.llms import VLLM
            from langchain_community.chat_models import ChatOpenAI  # 作为备选
        except ImportError:
            raise ImportError("langchain-community is required for vLLM support. Install with: pip install langchain-community")
        
        # 尝试使用VLLM类
        try:
            kwargs = {
                "model": self.model,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
                "streaming": streaming,
            }
            
            # 如果有tensor_parallel_size等vLLM特有参数
            vllm_params = {k: v for k, v in self.extra_params.items() 
                          if k in ['tensor_parallel_size', 'gpu_memory_utilization', 'dtype', 'quantization']}
            kwargs.update(vllm_params)
            
            return VLLM(**kwargs)
            
        except Exception:
            # 如果VLLM类不可用，尝试使用OpenAI兼容的接口
            from langchain_openai import ChatOpenAI
            
            kwargs = {
                "model": self.model,
                "openai_api_key": self.api_key,
                "openai_api_base": self.base_url,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
                "streaming": streaming,
            }
            
            return ChatOpenAI(**kwargs)
    
    def calculate_cost(self, token_usage: TokenUsage) -> float:
        """计算vLLM模型成本（本地部署通常免费）"""
        # 本地部署的模型通常没有API调用成本
        # 可以根据实际情况计算电力成本等
        return 0.0
    
    def _extract_token_usage(self, response) -> TokenUsage:
        """从vLLM响应中提取token使用信息"""
        metadata = getattr(response, 'response_metadata', {})
        usage_info = metadata.get('token_usage', {})
        
        # vLLM可能不提供详细的token统计，需要估算
        input_tokens = usage_info.get('prompt_tokens', 0)
        output_tokens = usage_info.get('completion_tokens', 0) 
        total_tokens = usage_info.get('total_tokens', input_tokens + output_tokens)
        
        # 如果没有token信息，使用简单估算
        if total_tokens == 0:
            content = getattr(response, 'content', '')
            total_tokens = TokenCounter.estimate_tokens(content)
            output_tokens = total_tokens
        
        return TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            model=self.model
        )


class LocalLLMAdapter(vLLMAdapter):
    """本地LLM适配器（vLLM的别名）"""
    pass


class HuggingFaceAdapter(LangChainBasedClient):
    """HuggingFace模型适配器"""
    
    def __init__(
        self,
        model: str = "microsoft/DialoGPT-medium", 
        api_key: Optional[str] = None,
        **kwargs
    ):
        # 获取HuggingFace API key
        if api_key is None:
            api_key = os.getenv("HUGGINGFACE_API_KEY")
        
        super().__init__(
            model=model,
            api_key=api_key,
            **kwargs
        )
    
    def _create_langchain_llm(self, streaming: bool = False):
        """创建LangChain HuggingFace实例"""
        try:
            from langchain_huggingface import HuggingFacePipeline
            from transformers import pipeline
        except ImportError:
            raise ImportError("langchain-huggingface and transformers are required. Install with: pip install langchain-huggingface transformers")
        
        # 创建transformers pipeline
        hf_pipeline = pipeline(
            "text-generation",
            model=self.model,
            max_new_tokens=self.max_tokens,
            temperature=self.temperature,
            **self.extra_params
        )
        
        return HuggingFacePipeline(
            pipeline=hf_pipeline,
            streaming=streaming
        )
    
    def calculate_cost(self, token_usage: TokenUsage) -> float:
        """HuggingFace模型成本（本地运行通常免费）"""
        return 0.0
    
    def _extract_token_usage(self, response) -> TokenUsage:
        """从HuggingFace响应中提取token使用信息"""
        # HuggingFace本地模型通常不提供详细token统计
        content = getattr(response, 'content', '')
        estimated_tokens = TokenCounter.estimate_tokens(content)
        
        return TokenUsage(
            input_tokens=0,  # 难以准确估算
            output_tokens=estimated_tokens,
            total_tokens=estimated_tokens,
            model=self.model
        )