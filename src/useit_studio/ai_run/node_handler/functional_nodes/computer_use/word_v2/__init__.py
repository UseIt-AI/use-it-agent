"""
Word Agent V2 - Word 自动化模块

基于 office_agent 统一架构重构。

支持两种架构模式：
1. planner_only（推荐）: Planner 直接输出代码，单阶段
2. planner_actor: Planner + Actor 两阶段

核心组件：
- WordAgent: 决策循环的核心实现（OfficeAgent 的别名）
- create_agent: 工厂函数，用于创建指定模式的 Agent
- WordNodeHandlerV2: 与 node_handler 架构的桥接层

使用方式：
    from word_v2 import create_agent, DocumentSnapshot
    
    # 使用 planner_only 模式（推荐）
    agent = create_agent(mode="planner_only", api_keys={"OPENAI_API_KEY": "..."})
    
    async for event in agent.run(
        user_goal="打开文档，把标题放大一号",
        node_instruction="把第一段字体放大",
        initial_snapshot=snapshot,
    ):
        print(event)
"""

# ==================== 从 models 导入 ====================

from .models import (
    # 动作类型
    ActionType,
    
    # 文档数据结构
    DocumentInfo,
    ParagraphInfo,
    TableInfo,
    DocumentContent,
    DocumentSnapshot,
    
    # Planner/Actor 输出
    PlannerOutput,
    WordAction,
    AgentStep,
    
    # 上下文
    AgentContext,
    NodeContext,
    
    # 事件类型
    ReasoningDeltaEvent,
    PlanCompleteEvent,
    ActionEvent,
    StepCompleteEvent,
    ErrorEvent,
    
    # 辅助函数
    document_snapshot_from_dict,
)

# ==================== 从 core 导入 ====================

from .core import create_agent, WordAgent

# ==================== Handler ====================

from .handler_v2 import WordNodeHandlerV2

# ==================== 导出 ====================

__all__ = [
    # 核心类
    "WordAgent",
    "WordNodeHandlerV2",
    "create_agent",
    
    # 数据模型
    "ActionType",
    "DocumentInfo",
    "ParagraphInfo",
    "TableInfo",
    "DocumentContent",
    "DocumentSnapshot",
    "PlannerOutput",
    "WordAction",
    "AgentStep",
    "AgentContext",
    "NodeContext",
    
    # 事件
    "ReasoningDeltaEvent",
    "PlanCompleteEvent",
    "ActionEvent",
    "StepCompleteEvent",
    "ErrorEvent",
    
    # 函数
    "document_snapshot_from_dict",
]
