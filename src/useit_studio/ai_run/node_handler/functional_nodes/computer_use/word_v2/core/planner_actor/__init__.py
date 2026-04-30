"""
Word Agent V2 - Planner + Actor 模式

两阶段架构：
1. Planner: 分析状态 → 输出自然语言 Action
2. Actor: 自然语言 Action → PowerShell 代码

这是原始的架构设计，保留用于对比。
"""

from .planner import WordPlanner
from .actor import WordActor
from .agent import WordAgent

__all__ = ["WordPlanner", "WordActor", "WordAgent"]
