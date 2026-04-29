"""
GUI Agent V2 - 简化的 Computer Use Agent

这是一个重构后的 GUI Agent 实现，相比旧版（gui/）有以下改进：

1. **清晰的分层架构**
   - models.py: 所有数据结构的单一真相来源
   - core/planner.py: 高层次规划（决定做什么）
   - core/actor.py: 低层次执行（决定怎么做）
   - agent.py: 协调 Planner 和 Actor
   - handler_v2.py: 与外部系统交互的接口（实现 BaseNodeHandlerV2）

2. **无冗余**
   - 没有 Factory 模式的过度设计
   - 没有 Legacy 和 LangChain 版本并存
   - 没有 Shim 文件

3. **单一职责**
   - 每个模块只做一件事
   - 依赖关系清晰

使用示例：

    from gui_v2 import GUIAgent, NodeContext
    
    agent = GUIAgent(
        planner_model="gpt-4o",
        actor_model="gpt-4o",
        api_keys={"OPENAI_API_KEY": "..."},
    )
    
    context = NodeContext(
        node_id="node_1",
        task_description="在 Amazon 上搜索笔记本电脑",
        milestone_objective="点击搜索框并输入关键词",
        guidance_steps=["点击搜索框", "输入 laptop", "点击搜索按钮"],
    )
    
    # 流式执行
    async for event in agent.step_streaming(context, screenshot_path):
        print(event)
    
    # 非流式执行
    result = await agent.step(context, screenshot_path)
"""

# 核心类
from .agent import GUIAgent, run_gui_agent_step, PlannerType
from .handler_v2 import GUINodeHandlerV2, handle_gui_node_v2

# 数据模型
from .models import (
    # 动作相关
    ActionType,
    CoordinateSystem,
    DeviceAction,
    
    # 规划相关
    PlannerOutput,
    
    # Agent 相关
    AgentStep,
    NodeContext,
    TokenUsage,
    
    # 事件相关
    ReasoningDeltaEvent,
    PlanCompleteEvent,
    ActionEvent,
    StepCompleteEvent,
    ErrorEvent,
)

# 核心组件（如果需要单独使用）
from .core.planner import Planner
from .core.actor import Actor
from .core.intent_refiner import IntentRefiner, CompletionSummarizer
from .core.autonomous_planner import AutonomousPlanner, create_planner

# 向后兼容别名
TeachModePlanner = AutonomousPlanner

# 工具类
from .utils.llm_client import VLMClient, LLMConfig

__all__ = [
    # 主要入口
    "GUIAgent",
    "GUINodeHandlerV2",
    "run_gui_agent_step",
    "handle_gui_node_v2",
    "PlannerType",
    
    # 数据模型
    "ActionType",
    "CoordinateSystem",
    "DeviceAction",
    "PlannerOutput",
    "AgentStep",
    "NodeContext",
    "TokenUsage",
    
    # 事件
    "ReasoningDeltaEvent",
    "PlanCompleteEvent",
    "ActionEvent",
    "StepCompleteEvent",
    "ErrorEvent",
    
    # 核心组件
    "Planner",
    "Actor",
    "IntentRefiner",
    "CompletionSummarizer",
    "AutonomousPlanner",
    "TeachModePlanner",  # 向后兼容别名
    "create_planner",
    
    # 工具
    "VLMClient",
    "LLMConfig",
    
    # 注意：历史记录管理已迁移到 RuntimeStateManager
    # 使用 useit_ai_run.runtime.transformers.ai_markdown_transformer.AIMarkdownTransformer
]
