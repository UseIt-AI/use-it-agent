"""
Office Agent - 统一的 Office 自动化 Agent 基础架构

支持 Word、Excel、PPT 等 Office 应用的自动化，通过 PowerShell COM 接口执行操作。

架构设计：
1. 共享基础组件：Agent、Planner、Handler、Models
2. 应用特化组件：Snapshot 结构、COM API Prompt

支持两种架构模式：
1. planner_only（推荐）: Planner 直接输出代码，单阶段
2. planner_actor: Planner + Actor 两阶段

使用方式：
    from office_agent import create_office_agent, OfficeAgentConfig
    
    # 创建 Word Agent
    agent = create_office_agent(
        app_type="word",
        config=OfficeAgentConfig(planner_model="gpt-4o-mini"),
        api_keys={"OPENAI_API_KEY": "..."}
    )
    
    async for event in agent.run(...):
        print(event)
"""

from .models import (
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

from .base_agent import OfficeAgent, OfficeAgentConfig
from .base_planner import OfficePlanner, OfficePlannerConfig
from .factory import create_office_agent

__all__ = [
    # 核心类
    "OfficeAgent",
    "OfficeAgentConfig",
    "OfficePlanner",
    "OfficePlannerConfig",
    "create_office_agent",
    
    # 枚举
    "ActionType",
    "OfficeAppType",
    
    # 数据模型
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
]
