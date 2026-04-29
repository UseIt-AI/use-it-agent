"""
PowerPoint Agent V2 - PowerPoint 自动化模块

基于 office_agent 统一架构实现。

使用 PowerShell COM 自动化操作 PowerPoint 应用程序。

核心组件：
- PPTAgent: 决策循环的核心实现（OfficeAgent 的配置）
- create_agent: 工厂函数
- PPTNodeHandlerV2: 与 node_handler 架构的桥接层

使用方式：
    from ppt_v2 import create_agent, SlideSnapshot
    
    agent = create_agent(api_keys={"OPENAI_API_KEY": "..."})
    
    async for event in agent.run(
        user_goal="创建演示文稿",
        node_instruction="添加标题幻灯片",
        initial_snapshot=snapshot,
    ):
        print(event)
"""

# ==================== 从 models 导入 ====================

from .models import (
    # 动作类型
    ActionType,
    
    # 数据结构
    ShapeInfo,
    SlideInfo,
    PresentationInfo,
    SlideSnapshot,
    
    # Planner/Actor 输出
    PlannerOutput,
    PPTAction,
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
    slide_snapshot_from_dict,
)

# ==================== 从 core 导入 ====================

from .core import create_agent, PPTAgent

# ==================== Handler ====================

from .handler import PPTNodeHandlerV2

# ==================== 导出 ====================

__all__ = [
    # 核心类
    "PPTAgent",
    "PPTNodeHandlerV2",
    "create_agent",
    
    # 数据模型
    "ActionType",
    "ShapeInfo",
    "SlideInfo",
    "PresentationInfo",
    "SlideSnapshot",
    "PlannerOutput",
    "PPTAction",
    "AgentStep",
    "AgentContext",
    
    # 事件
    "ReasoningDeltaEvent",
    "PlanCompleteEvent",
    "ActionEvent",
    "StepCompleteEvent",
    "ErrorEvent",
    
    # 函数
    "slide_snapshot_from_dict",
]
