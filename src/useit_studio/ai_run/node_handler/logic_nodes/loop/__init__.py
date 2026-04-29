"""
Loop Node Module - 循环节点处理模块

包含：
- LoopNodeHandlerV2: 循环容器节点处理器 (loop_handler.py)
- LoopStartNodeHandlerV2: 循环开始节点处理器 (loop_start_handler.py)
- LoopEndNodeHandlerV2: 循环结束节点处理器 (loop_end_handler.py)

使用方式：
    from useit_studio.ai_run.node_handler.logic_nodes.loop import (
        LoopNodeHandlerV2,
        LoopStartNodeHandlerV2,
        LoopEndNodeHandlerV2,
    )
"""

# Handlers - 每个节点类型一个独立文件
from .loop_handler import LoopNodeHandlerV2
from .loop_start_handler import LoopStartNodeHandlerV2
from .loop_end_handler import LoopEndNodeHandlerV2

# Models
from .models import (
    LoopContext,
    IterationPlanOutput,
    LoopEndDecision,
    LoopPlanningEvent,
    LoopIterationEvent,
    LoopCompleteEvent,
)

# Core
from .core import (
    LoopPlanner,
    LoopEndEvaluator,
    collect_loop_milestone_descriptions,
)


__all__ = [
    # Handlers
    "LoopNodeHandlerV2",
    "LoopStartNodeHandlerV2",
    "LoopEndNodeHandlerV2",
    # Models
    "LoopContext",
    "IterationPlanOutput",
    "LoopEndDecision",
    "LoopPlanningEvent",
    "LoopIterationEvent",
    "LoopCompleteEvent",
    # Core
    "LoopPlanner",
    "LoopEndEvaluator",
    "collect_loop_milestone_descriptions",
]
