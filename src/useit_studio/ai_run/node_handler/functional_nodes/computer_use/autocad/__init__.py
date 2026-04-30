"""
AutoCAD Agent - AutoCAD 自动化模块

通过 AutoCAD V2 HTTP API 控制 AutoCAD 应用程序。

核心组件：
- AutoCADAgent: 决策循环的核心实现
- create_agent: 工厂函数
- AutoCADNodeHandlerV2: 与 node_handler 架构的桥接层

使用方式：
    from autocad import create_agent, AutoCADSnapshot
    
    agent = create_agent(api_keys={"OPENAI_API_KEY": "..."})
    
    async for event in agent.run(
        user_goal="绘制图纸",
        node_instruction="绘制一个矩形",
        initial_snapshot=snapshot,
    ):
        print(event)

API 文档参考：autocadHandler.api.md
"""

# ==================== 从 models 导入 ====================

from .models import (
    # Agent 相关
    AutoCADAgentConfig,
    AutoCADPlannerOutput,
    AutoCADAction,
    AutoCADAgentStep,
    AutoCADAgentContext,
    
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

# ==================== 从 core 导入 ====================

from .core import (
    create_agent,
    AutoCADAgent,
    AutoCADPlanner,
)

# ==================== Handler ====================

from .handler import (
    AutoCADNodeHandlerV2,
    handle_node_streaming,
)

# ==================== 导出 ====================

__all__ = [
    # 核心类
    "AutoCADAgent",
    "AutoCADPlanner",
    "AutoCADNodeHandlerV2",
    "create_agent",
    
    # 兼容旧接口
    "handle_node_streaming",
    
    # Agent 数据模型
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
