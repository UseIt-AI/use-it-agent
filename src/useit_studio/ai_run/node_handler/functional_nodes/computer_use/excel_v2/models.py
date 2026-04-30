"""
Excel Agent V2 - 数据模型定义

从 office_agent 导入共享模型，并提供 Excel 特定的别名和扩展。
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

# ==================== Excel 特定的 Snapshot ====================

from .snapshot import (
    CellInfo,
    SheetInfo,
    WorkbookInfo,
    SheetSnapshot,
    sheet_snapshot_from_dict,
    col_to_letter,
    letter_to_col,
)

# ==================== Excel 特定别名 ====================

# ExcelAction 是 OfficeAction 的别名
ExcelAction = OfficeAction


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
    
    # Excel 特定
    "CellInfo",
    "SheetInfo",
    "WorkbookInfo",
    "SheetSnapshot",
    "sheet_snapshot_from_dict",
    "col_to_letter",
    "letter_to_col",
    
    # 兼容别名
    "ExcelAction",
]
