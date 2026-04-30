"""
AutoCAD Agent - 数据模型定义

导出 AutoCAD 相关的所有数据模型。
"""

# ==================== 从 core 导入 Agent 相关模型 ====================

from .core import (
    AutoCADAgentConfig,
    AutoCADPlannerOutput,
    AutoCADAction,
    AutoCADAgentStep,
    AutoCADAgentContext,
)

# ==================== 从 snapshot 导入快照相关模型 ====================

from .snapshot import (
    # 图元信息
    LineInfo,
    CircleInfo,
    ArcInfo,
    PolylineInfo,
    TextInfo,
    DimensionInfo,
    
    # 图纸内容
    DrawingContent,
    DocumentInfo,
    AutoCADStatus,
    
    # 快照
    AutoCADSnapshot,
    autocad_snapshot_from_dict,
)


# ==================== 导出 ====================

__all__ = [
    # Agent 相关
    "AutoCADAgentConfig",
    "AutoCADPlannerOutput",
    "AutoCADAction",
    "AutoCADAgentStep",
    "AutoCADAgentContext",
    
    # 图元信息
    "LineInfo",
    "CircleInfo",
    "ArcInfo",
    "PolylineInfo",
    "TextInfo",
    "DimensionInfo",
    
    # 图纸内容
    "DrawingContent",
    "DocumentInfo",
    "AutoCADStatus",
    
    # 快照
    "AutoCADSnapshot",
    "autocad_snapshot_from_dict",
]
