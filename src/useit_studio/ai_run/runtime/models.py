"""
Runtime State Data Models

Defines the core data structures for workflow execution state management:
- ExecutionNode: Represents a node in the execution tree
- WorkflowRuntimeState: The single source of truth for workflow state
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Literal
from enum import Enum
import time


class NodeStatus(str, Enum):
    """Node execution status"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class ExecutionNodeType(str, Enum):
    """Execution node type classification"""
    ACTION = "action"                      # Action nodes (computer-use, llm, mcp, etc.)
    LOGIC = "logic"                        # Logic nodes (if-else, start, end)
    LOOP_CONTAINER = "loop_container"      # Loop container
    LOOP_ITERATION = "loop_iteration"      # Loop iteration


class ActionStatus(str, Enum):
    """Action execution status within a node"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class ActionRecord:
    """
    Record of a single action within a node
    
    For agent-based nodes (like computer-use), each step the agent takes
    is recorded as an ActionRecord.
    
    Attributes:
        step: Step number (1-indexed)
        timestamp: When the action was recorded
        thinking: Free-form thinking/reasoning from the agent (new format)
        observation: What the agent observed before acting (legacy)
        reasoning: Agent's reasoning for the action (legacy)
        action_type: Type of action (click, type, scroll, etc.)
        action_params: Action parameters
        action_target: Target element description
        title: Short title for UI display
        status: Action execution status
        result_observation: [DEPRECATED] Observation after action - use step_memory instead
        error: Error message if failed
        token_usage: Token usage for this step
        step_memory: Key information/notes collected at this step by AI (concise text)
    """
    step: int
    timestamp: float = field(default_factory=time.time)
    
    # Agent thinking (new format: free-form thinking)
    thinking: Optional[str] = None
    title: Optional[str] = None
    
    # Legacy fields (for backward compatibility)
    observation: Optional[str] = None
    reasoning: Optional[str] = None
    
    # Action details
    action_type: Optional[str] = None
    action_params: Optional[Dict[str, Any]] = None
    action_target: Optional[str] = None
    
    # Result
    status: ActionStatus = ActionStatus.PENDING
    # DEPRECATED: result_observation will be gradually removed.
    # Use step_memory instead for AI to record key information at each step.
    # result_observation was handler-hardcoded text like "Task completed", not useful for AI.
    result_observation: Optional[str] = None
    error: Optional[str] = None
    
    # Token usage
    token_usage: Optional[Dict[str, Any]] = None
    
    # Step memory: AI's "notebook" for this step
    # AI can output step_memory to record important data, observations, or summaries
    # This is displayed in milestone_history.md after each step as <step_memory>...</step_memory>
    step_memory: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to serializable dictionary"""
        return {
            "step": self.step,
            "timestamp": self.timestamp,
            "thinking": self.thinking,
            "title": self.title,
            "observation": self.observation,
            "reasoning": self.reasoning,
            "actionType": self.action_type,
            "actionParams": self.action_params,
            "actionTarget": self.action_target,
            "status": self.status.value,
            "resultObservation": self.result_observation,
            "error": self.error,
            "tokenUsage": self.token_usage,
            "stepMemory": self.step_memory,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ActionRecord":
        """Create ActionRecord from dictionary"""
        return cls(
            step=data["step"],
            timestamp=data.get("timestamp", time.time()),
            thinking=data.get("thinking"),
            title=data.get("title"),
            observation=data.get("observation"),
            reasoning=data.get("reasoning"),
            action_type=data.get("actionType"),
            action_params=data.get("actionParams"),
            action_target=data.get("actionTarget"),
            status=ActionStatus(data.get("status", "pending")),
            result_observation=data.get("resultObservation"),
            error=data.get("error"),
            token_usage=data.get("tokenUsage"),
            step_memory=data.get("stepMemory"),
        )
    
    def get_summary(self) -> str:
        """Get a one-line summary of this action"""
        # Prefer title, then action_target, then action_type
        target = self.title or self.action_target or self.action_type or "action"
        if self.status == ActionStatus.FAILED and self.error:
            return f"{target} (Failed: {self.error[:30]})"
        else:
            # 不需要在 summary 中添加 "(执行中)"，因为上层会用状态标记 [-->] 来表示
            return target


@dataclass
class ExecutionNode:
    """
    Execution Node (Runtime State Object)
    
    Represents a node in the execution tree, including its status,
    input/output data, and nested children for loops.
    
    Attributes:
        id: Runtime unique ID (can be f"{node_def_id}_{iteration}" for iterations)
        node_def_id: Corresponding static Node ID in workflow definition
        name: Display name
        type: Node type classification
        original_node_type: Original node type (computer-use, if-else, etc.)
        status: Current execution status
        input_data: Input data for this node
        output_data: Full output data (for storage and frontend)
        history_summary: One-line summary for AI context
        selected_path: Selected branch (for logic nodes)
        skipped_paths: Unselected branches
        children: Nested nodes (for loops and sub-flows)
        parent_id: Parent node ID
        start_time: Execution start timestamp
        end_time: Execution end timestamp
        token_usage: Token usage statistics
        
        # Node Internal State (for agent-based nodes)
        internal_state: Flexible key-value store for agent state
        action_history: List of actions taken within this node
        step_count: Current step number
        retry_count: Number of retries
        max_retries: Maximum allowed retries
        consecutive_failures: Count of consecutive failures
    """
    id: str
    node_def_id: str
    name: str
    type: ExecutionNodeType
    original_node_type: str
    
    # State machine
    status: NodeStatus = NodeStatus.PENDING
    
    # Input/Output
    input_data: Optional[Dict[str, Any]] = None
    output_data: Optional[Dict[str, Any]] = None
    
    # AI-specific fields
    history_summary: Optional[str] = None
    
    # Logic flow related
    selected_path: Optional[str] = None
    skipped_paths: List[str] = field(default_factory=list)
    
    # Nested structure (Loop or Sub-flow)
    children: List["ExecutionNode"] = field(default_factory=list)
    parent_id: Optional[str] = None
    
    # Timestamps
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    
    # Token usage
    token_usage: Optional[Dict[str, Any]] = None
    
    # ========== Node Internal State (for agent-based nodes) ==========
    
    # Flexible internal state (key-value store for agent)
    internal_state: Dict[str, Any] = field(default_factory=dict)
    
    # Action history - each entry is one agent step
    action_history: List[ActionRecord] = field(default_factory=list)
    
    # Step counter (no total - it's open-ended)
    step_count: int = 0
    
    # Retry/error tracking
    retry_count: int = 0
    max_retries: int = 2
    consecutive_failures: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to serializable dictionary"""
        return {
            "id": self.id,
            "nodeDefId": self.node_def_id,
            "name": self.name,
            "type": self.type.value,
            "originalNodeType": self.original_node_type,
            "status": self.status.value,
            "inputData": self.input_data,
            "outputData": self.output_data,
            "historySummary": self.history_summary,
            "selectedPath": self.selected_path,
            "skippedPaths": self.skipped_paths,
            "children": [child.to_dict() for child in self.children],
            "parentId": self.parent_id,
            "startTime": self.start_time,
            "endTime": self.end_time,
            "tokenUsage": self.token_usage,
            # Node internal state
            "internalState": self.internal_state,
            "actionHistory": [action.to_dict() for action in self.action_history],
            "stepCount": self.step_count,
            "retryCount": self.retry_count,
            "maxRetries": self.max_retries,
            "consecutiveFailures": self.consecutive_failures,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExecutionNode":
        """Create ExecutionNode from dictionary"""
        children = [cls.from_dict(child) for child in data.get("children", [])]
        action_history = [
            ActionRecord.from_dict(action) 
            for action in data.get("actionHistory", [])
        ]
        
        return cls(
            id=data["id"],
            node_def_id=data.get("nodeDefId", data["id"]),
            name=data["name"],
            type=ExecutionNodeType(data["type"]),
            original_node_type=data.get("originalNodeType", "unknown"),
            status=NodeStatus(data.get("status", "pending")),
            input_data=data.get("inputData"),
            output_data=data.get("outputData"),
            history_summary=data.get("historySummary"),
            selected_path=data.get("selectedPath"),
            skipped_paths=data.get("skippedPaths", []),
            children=children,
            parent_id=data.get("parentId"),
            start_time=data.get("startTime"),
            end_time=data.get("endTime"),
            token_usage=data.get("tokenUsage"),
            # Node internal state
            internal_state=data.get("internalState", {}),
            action_history=action_history,
            step_count=data.get("stepCount", 0),
            retry_count=data.get("retryCount", 0),
            max_retries=data.get("maxRetries", 3),
            consecutive_failures=data.get("consecutiveFailures", 0),
        )
    
    def get_duration_ms(self) -> Optional[float]:
        """Get execution duration in milliseconds"""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time) * 1000
        return None
    
    def is_completed(self) -> bool:
        """Check if node is completed (success or failed)"""
        return self.status in (NodeStatus.SUCCESS, NodeStatus.FAILED)
    
    def is_running(self) -> bool:
        """Check if node is currently running"""
        return self.status == NodeStatus.RUNNING
    
    # ========== Node Internal State Methods ==========
    
    def get_last_action(self) -> Optional[ActionRecord]:
        """Get the most recent action"""
        if self.action_history:
            return self.action_history[-1]
        return None
    
    def get_running_action(self) -> Optional[ActionRecord]:
        """Get currently running action if any"""
        for action in reversed(self.action_history):
            if action.status == ActionStatus.RUNNING:
                return action
        return None
    
    def get_completed_actions(self) -> List[ActionRecord]:
        """Get all completed actions"""
        return [a for a in self.action_history if a.status == ActionStatus.SUCCESS]
    
    def get_failed_actions(self) -> List[ActionRecord]:
        """Get all failed actions"""
        return [a for a in self.action_history if a.status == ActionStatus.FAILED]
    
    def has_actions(self) -> bool:
        """Check if node has any recorded actions"""
        return len(self.action_history) > 0
    
    def should_retry(self) -> bool:
        """Check if node should retry (under max retries)"""
        return self.retry_count < self.max_retries


@dataclass
class WorkflowRuntimeState:
    """
    Workflow Runtime State (Single Source of Truth)
    
    This is the central data structure that maintains all runtime state
    for a workflow execution. It includes:
    - Global variables (blackboard)
    - Execution tree (node hierarchy)
    - Current pointer
    
    Attributes:
        workflow_id: Workflow definition ID
        run_id: Unique ID for this execution run (task_id)
        status: Overall workflow status
        variables: Global variables blackboard
        execution_tree: Tree of execution nodes
        current_node_id: Currently active node
    """
    workflow_id: str
    run_id: str
    status: Literal["running", "paused", "completed", "failed"] = "running"
    
    # 1. Global variables (blackboard)
    variables: Dict[str, Any] = field(default_factory=dict)
    
    # 2. Execution tree (skeleton)
    execution_tree: List[ExecutionNode] = field(default_factory=list)
    
    # 3. Current pointer
    current_node_id: Optional[str] = None
    
    # 4. Node ID to ExecutionNode quick index
    _node_index: Dict[str, ExecutionNode] = field(default_factory=dict, repr=False)
    
    # 5. Timestamps
    start_time: Optional[float] = field(default_factory=time.time)
    end_time: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to serializable dictionary (for frontend)"""
        return {
            "workflowId": self.workflow_id,
            "runId": self.run_id,
            "status": self.status,
            "variables": self.variables,
            "executionTree": [node.to_dict() for node in self.execution_tree],
            "currentNodeId": self.current_node_id,
            "startTime": self.start_time,
            "endTime": self.end_time,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowRuntimeState":
        """Create WorkflowRuntimeState from dictionary"""
        state = cls(
            workflow_id=data["workflowId"],
            run_id=data["runId"],
            status=data.get("status", "running"),
            variables=data.get("variables", {}),
            current_node_id=data.get("currentNodeId"),
            start_time=data.get("startTime"),
            end_time=data.get("endTime"),
        )
        
        # Rebuild execution tree
        for node_data in data.get("executionTree", []):
            node = ExecutionNode.from_dict(node_data)
            state.execution_tree.append(node)
            state._rebuild_index(node)
        
        return state
    
    def _rebuild_index(self, node: ExecutionNode):
        """Recursively rebuild node index"""
        self._node_index[node.id] = node
        for child in node.children:
            self._rebuild_index(child)
    
    def get_node(self, node_id: str) -> Optional[ExecutionNode]:
        """Get ExecutionNode by ID"""
        return self._node_index.get(node_id)
    
    def register_node(self, node: ExecutionNode):
        """Register node to index"""
        self._node_index[node.id] = node
    
    def unregister_node(self, node_id: str):
        """Remove node from index"""
        self._node_index.pop(node_id, None)
    
    def get_all_nodes(self) -> List[ExecutionNode]:
        """Get all nodes (flattened)"""
        return list(self._node_index.values())
    
    def get_nodes_by_status(self, status: NodeStatus) -> List[ExecutionNode]:
        """Get all nodes with specified status"""
        return [node for node in self._node_index.values() if node.status == status]
    
    def get_completed_nodes(self) -> List[ExecutionNode]:
        """Get all completed nodes"""
        return [
            node for node in self._node_index.values()
            if node.status in (NodeStatus.SUCCESS, NodeStatus.FAILED)
        ]
    
    def get_running_nodes(self) -> List[ExecutionNode]:
        """Get all running nodes"""
        return self.get_nodes_by_status(NodeStatus.RUNNING)
    
    def mark_completed(self, final_status: Literal["completed", "failed"] = "completed"):
        """Mark workflow as completed"""
        self.status = final_status
        self.end_time = time.time()
    
    def get_duration_ms(self) -> Optional[float]:
        """Get workflow duration in milliseconds"""
        if self.start_time:
            end = self.end_time or time.time()
            return (end - self.start_time) * 1000
        return None
