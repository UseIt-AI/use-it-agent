"""
Agent Loop

在 ``FlowProcessor`` 之上的薄封装：``/agent`` 固定走最小工作流
（start → agent → end），不再包含编排器 LLM。
"""

from useit_studio.ai_run.agent_loop.action_models import (
    OrchestratorState,
    AppActionCall,
    WorkflowActionCall,
    TextResponse,
    OrchestratorContext,
    PlannerDecision,
    StepStartEvent,
    ReasoningDeltaEvent,
    PlanCompleteEvent,
    StepCompleteEvent,
    TaskCompletedEvent,
    ErrorEvent,
)
from useit_studio.ai_run.agent_loop.agent_loop import AgentLoop
from useit_studio.ai_run.agent_loop.logger import AgentLoopLogger

# Back-compat alias
AgentOrchestratorLoop = AgentLoop

__all__ = [
    "OrchestratorState",
    "AppActionCall",
    "WorkflowActionCall",
    "TextResponse",
    "OrchestratorContext",
    "AgentLoop",
    "AgentOrchestratorLoop",
    "AgentLoopLogger",
    # Event types (aligned with OfficeAgent)
    "PlannerDecision",
    "StepStartEvent",
    "ReasoningDeltaEvent",
    "PlanCompleteEvent",
    "StepCompleteEvent",
    "TaskCompletedEvent",
    "ErrorEvent",
]
