"""
Word Agent V2 - Planner Only 模式

单阶段架构：
- Planner: 分析状态 → 直接输出 Code

这是简化版架构，减少一次 LLM 调用。
"""

from .planner import WordPlanner
from .agent import WordAgent

__all__ = ["WordPlanner", "WordAgent"]
