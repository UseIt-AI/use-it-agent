"""
GUI Agent V2 - Core 模块

包含 Planner、Actor 和 IntentRefiner 的核心实现。

Planner 说明：
- Planner (planner.py): Teach Mode Planner，需要 guidance_steps，按轨迹执行
- AutonomousPlanner (autonomous_planner.py): 自主规划器，不需要 guidance_steps

Unified Planner（Planner-Only 模式）：
- UnifiedPlanner: 有 guidance_steps，一次调用完成规划和动作生成
- UnifiedAutonomousPlanner: 无 guidance_steps，一次调用完成规划和动作生成
"""

from .planner import Planner
from .actor import Actor
from .intent_refiner import IntentRefiner, CompletionSummarizer
from .autonomous_planner import AutonomousPlanner, create_planner
from .unified_planner import (
    UnifiedPlanner,
    UnifiedAutonomousPlanner,
    UnifiedPlannerBase,
    create_unified_planner,
)

# 向后兼容别名
TeachModePlanner = AutonomousPlanner  # 旧名称，建议使用 AutonomousPlanner

__all__ = [
    # 传统模式
    "Planner",
    "Actor", 
    "IntentRefiner", 
    "CompletionSummarizer",
    "AutonomousPlanner",
    "TeachModePlanner",  # 向后兼容
    "create_planner",
    # Planner-Only 模式
    "UnifiedPlanner",
    "UnifiedAutonomousPlanner",
    "UnifiedPlannerBase",
    "create_unified_planner",
]
