"""
Token统计和成本计算功能

支持不同模型的token计算和成本估算
"""

from typing import Dict, List, Union
import re
from dataclasses import dataclass

from .base.client import TokenUsage


# 模型定价配置 (USD per 1k tokens)
MODEL_PRICING = {
    # OpenAI GPT模型
    "gpt-4o": {"input": 0.0025, "output": 0.01},
    "gpt-4o-mini": {"input": 0.000150, "output": 0.000600},
    "gpt-4-turbo": {"input": 0.01, "output": 0.03},
    "gpt-4": {"input": 0.03, "output": 0.06},
    "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
    "gpt-5.1": {"input": 0.05, "output": 0.15},  # 估算价格
    "gpt-5.2": {"input": 0.05, "output": 0.15},  # 估算价格（暂与 gpt-5.1 对齐）
    
    # Claude模型
    "claude-3-5-sonnet-20241022": {"input": 0.003, "output": 0.015},
    "claude-3-5-haiku-20241022": {"input": 0.001, "output": 0.005},
    "claude-3-opus-20240229": {"input": 0.015, "output": 0.075},
    
    # Gemini模型
    "gemini-1.5-pro": {"input": 0.00125, "output": 0.005},
    "gemini-1.5-flash": {"input": 0.000075, "output": 0.0003},
    
    # 默认价格
    "default": {"input": 0.001, "output": 0.003}
}


class TokenCounter:
    """Token计数器和成本计算器"""
    
    @staticmethod
    def estimate_tokens(text: str) -> int:
        """
        估算文本的token数量
        
        简单估算：一般1个token约等于4个字符（英文）或1-2个中文字符
        """
        if not text:
            return 0
        
        # 分别计算中文和英文字符
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        english_chars = len(re.sub(r'[\u4e00-\u9fff]', '', text))
        
        # 中文：1.5个字符=1个token，英文：4个字符=1个token
        estimated = int(chinese_chars / 1.5 + english_chars / 4)
        return max(estimated, 1)  # 至少1个token
    
    @staticmethod
    def calculate_cost(token_usage: TokenUsage, model: str = None) -> float:
        """
        计算成本
        
        Args:
            token_usage: Token使用情况
            model: 模型名称（可选，从token_usage中获取）
            
        Returns:
            成本（USD）
        """
        model = model or token_usage.model
        
        # 获取模型定价
        pricing = MODEL_PRICING.get(model)
        if not pricing:
            # 尝试模糊匹配
            for model_key in MODEL_PRICING:
                if model_key in model.lower() or model.lower() in model_key:
                    pricing = MODEL_PRICING[model_key]
                    break
            else:
                pricing = MODEL_PRICING["default"]
        
        # 计算成本
        input_cost = (token_usage.input_tokens / 1000) * pricing["input"]
        output_cost = (token_usage.output_tokens / 1000) * pricing["output"]
        
        return round(input_cost + output_cost, 6)
    
    @staticmethod
    def create_token_usage(
        input_tokens: int = 0,
        output_tokens: int = 0,
        model: str = "",
        calculate_cost: bool = True
    ) -> TokenUsage:
        """
        创建TokenUsage对象
        
        Args:
            input_tokens: 输入token数
            output_tokens: 输出token数  
            model: 模型名称
            calculate_cost: 是否计算成本
            
        Returns:
            TokenUsage对象
        """
        token_usage = TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            model=model
        )
        
        if calculate_cost:
            token_usage.cost = TokenCounter.calculate_cost(token_usage)
        
        return token_usage


class TokenTracker:
    """Token使用追踪器"""
    
    def __init__(self):
        self.sessions: Dict[str, Dict] = {}
        self.total_usage = {
            "total_tokens": 0,
            "total_cost": 0.0,
            "request_count": 0,
            "models": {}
        }
    
    def track_usage(self, session_id: str, token_usage: TokenUsage, operation: str = "call"):
        """
        追踪token使用
        
        Args:
            session_id: 会话ID
            token_usage: Token使用情况
            operation: 操作类型（call, stream等）
        """
        # 更新会话统计
        if session_id not in self.sessions:
            self.sessions[session_id] = {
                "total_tokens": 0,
                "total_cost": 0.0,
                "request_count": 0,
                "operations": {}
            }
        
        session = self.sessions[session_id]
        session["total_tokens"] += token_usage.total_tokens
        session["total_cost"] += token_usage.cost
        session["request_count"] += 1
        
        if operation not in session["operations"]:
            session["operations"][operation] = 0
        session["operations"][operation] += 1
        
        # 更新全局统计
        self.total_usage["total_tokens"] += token_usage.total_tokens
        self.total_usage["total_cost"] += token_usage.cost
        self.total_usage["request_count"] += 1
        
        model = token_usage.model
        if model not in self.total_usage["models"]:
            self.total_usage["models"][model] = {
                "tokens": 0,
                "cost": 0.0,
                "requests": 0
            }
        
        self.total_usage["models"][model]["tokens"] += token_usage.total_tokens
        self.total_usage["models"][model]["cost"] += token_usage.cost
        self.total_usage["models"][model]["requests"] += 1
    
    def get_session_stats(self, session_id: str) -> Dict:
        """获取会话统计"""
        return self.sessions.get(session_id, {})
    
    def get_total_stats(self) -> Dict:
        """获取总体统计"""
        return self.total_usage.copy()
    
    def get_model_stats(self, model: str) -> Dict:
        """获取特定模型统计"""
        return self.total_usage["models"].get(model, {})
    
    def reset_session(self, session_id: str):
        """重置会话统计"""
        if session_id in self.sessions:
            del self.sessions[session_id]
    
    def reset_all(self):
        """重置所有统计"""
        self.sessions.clear()
        self.total_usage = {
            "total_tokens": 0,
            "total_cost": 0.0,
            "request_count": 0,
            "models": {}
        }


# 全局token追踪器实例
global_token_tracker = TokenTracker()