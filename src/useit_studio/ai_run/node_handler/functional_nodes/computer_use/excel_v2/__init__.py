"""
Excel Agent V2 - Excel 自动化模块

基于 office_agent 统一架构实现。

使用 PowerShell COM 自动化操作 Excel 应用程序。

核心组件：
- ExcelAgent: 决策循环的核心实现（OfficeAgent 的配置）
- create_agent: 工厂函数
- ExcelNodeHandlerV2: 与 node_handler 架构的桥接层

使用方式：
    from excel_v2 import create_agent, SheetSnapshot
    
    agent = create_agent(api_keys={"OPENAI_API_KEY": "..."})
    
    async for event in agent.run(
        user_goal="处理销售数据",
        node_instruction="计算总和",
        initial_snapshot=snapshot,
    ):
        print(event)
"""

# ==================== 从 models 导入 ====================

from .models import (
    # 动作类型
    ActionType,
    
    # 数据结构
    CellInfo,
    SheetInfo,
    WorkbookInfo,
    SheetSnapshot,
    
    # Planner/Actor 输出
    PlannerOutput,
    ExcelAction,
    AgentStep,
    
    # 上下文
    AgentContext,
    
    # 事件类型
    ReasoningDeltaEvent,
    PlanCompleteEvent,
    ActionEvent,
    StepCompleteEvent,
    ErrorEvent,
    
    # 辅助函数
    sheet_snapshot_from_dict,
)

# ==================== 从 core 导入 ====================

from .core import create_agent, ExcelAgent

# ==================== Handler ====================

from .handler import ExcelNodeHandlerV2

# ==================== 导出 ====================

__all__ = [
    # 核心类
    "ExcelAgent",
    "ExcelNodeHandlerV2",
    "create_agent",
    
    # 数据模型
    "ActionType",
    "CellInfo",
    "SheetInfo",
    "WorkbookInfo",
    "SheetSnapshot",
    "PlannerOutput",
    "ExcelAction",
    "AgentStep",
    "AgentContext",
    
    # 事件
    "ReasoningDeltaEvent",
    "PlanCompleteEvent",
    "ActionEvent",
    "StepCompleteEvent",
    "ErrorEvent",
    
    # 函数
    "sheet_snapshot_from_dict",
]
