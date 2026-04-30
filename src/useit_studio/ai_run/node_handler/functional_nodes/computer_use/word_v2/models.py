"""
Word Agent V2 - 数据模型定义

从 office_agent 导入共享模型，并提供 Word 特定的别名和扩展。
"""

# ==================== 从 office_agent 导入共享模型 ====================

from ..office_agent.models import (
    # 核心枚举
    ActionType,
    OfficeAppType,
    
    # 通用数据结构
    PlannerOutput,
    OfficeAction,
    AgentStep,
    AgentContext,
    
    # 事件类型
    ReasoningDeltaEvent,
    PlanCompleteEvent,
    ActionEvent,
    StepCompleteEvent,
    ErrorEvent,
    
    # Protocol
    BaseSnapshot,
)

# ==================== Word 特定的 Snapshot ====================

from .snapshot import (
    DocumentInfo,
    ParagraphInfo,
    TableInfo,
    DocumentContent,
    DocumentSnapshot,
    document_snapshot_from_dict,
)

# ==================== Word 特定别名（向后兼容） ====================

# WordAction 是 OfficeAction 的别名
WordAction = OfficeAction

# NodeContext 保留向后兼容
from dataclasses import dataclass
from typing import Optional


@dataclass
class NodeContext:
    """
    节点上下文 - Handler 传递给 Agent 的所有必要信息
    
    保留向后兼容。
    """
    node_id: str
    task_description: str           # 整体任务描述
    objective: str                  # 当前目标（用户指令）
    initial_snapshot: Optional[DocumentSnapshot] = None
    language: str = "PowerShell"
    history_md: str = ""


# ==================== 导出 ====================

__all__ = [
    # 枚举
    "ActionType",
    "OfficeAppType",
    
    # 通用模型（从 office_agent 导入）
    "PlannerOutput",
    "OfficeAction",
    "AgentStep",
    "AgentContext",
    "BaseSnapshot",
    
    # 事件
    "ReasoningDeltaEvent",
    "PlanCompleteEvent",
    "ActionEvent",
    "StepCompleteEvent",
    "ErrorEvent",
    
    # Word 特定
    "DocumentInfo",
    "ParagraphInfo",
    "TableInfo",
    "DocumentContent",
    "DocumentSnapshot",
    "document_snapshot_from_dict",
    
    # 兼容别名
    "WordAction",
    "NodeContext",
]
