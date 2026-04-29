"""
Runtime State Management Module

This module provides the core runtime state management for workflow execution,
implementing the MVVM pattern with:
- Model: WorkflowRuntimeState (single source of truth)
- View A: AI Markdown (via AIMarkdownTransformer)
- View B: Frontend JSON (via FrontendTransformer)

Usage:
    from useit_studio.ai_run.runtime import (
        RuntimeStateManager,
        WorkflowRuntimeState,
        ExecutionNode,
        NodeOutputProtocol,
        AIMarkdownTransformer,
        FrontendTransformer,
        ActionRecord,
        ActionStatus,
    )
    
    # Create state manager
    manager = RuntimeStateManager(workflow_id="wf_001", run_id="run_abc")
    
    # Start and complete nodes
    node = manager.start_node("node_1", "My Node", "computer-use")
    manager.complete_node("node_1", output)
    
    # Record actions within a node (for agent-based nodes)
    action = manager.record_node_action(
        "node_1",
        observation="看到登录按钮",
        reasoning="需要点击登录",
        action_type="click",
        action_target="登录按钮",
    )
    manager.complete_node_action("node_1", status="success")
    
    # Generate views
    markdown = AIMarkdownTransformer(manager.state).transform()
    json_data = FrontendTransformer(manager.state).get_full_state()
"""

from .models import (
    NodeStatus,
    ExecutionNodeType,
    ExecutionNode,
    WorkflowRuntimeState,
    ActionRecord,
    ActionStatus,
)

from .protocols import NodeOutputProtocol

from .state_manager import RuntimeStateManager

from .transformers import (
    AIMarkdownTransformer,
    FrontendTransformer,
)

__all__ = [
    # Models
    "NodeStatus",
    "ExecutionNodeType", 
    "ExecutionNode",
    "WorkflowRuntimeState",
    "ActionRecord",
    "ActionStatus",
    # Protocols
    "NodeOutputProtocol",
    # State Manager
    "RuntimeStateManager",
    # Transformers
    "AIMarkdownTransformer",
    "FrontendTransformer",
]
