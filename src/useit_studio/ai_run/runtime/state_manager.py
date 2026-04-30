"""
Runtime State Manager

Core class for managing workflow execution state.
Provides methods for:
- Starting and completing nodes
- Managing loop iterations
- Tracking skipped branches
- Querying execution state
"""

from typing import Dict, List, Optional, Any, Tuple
import time
import json
import os

from .models import (
    WorkflowRuntimeState,
    ExecutionNode,
    ExecutionNodeType,
    NodeStatus,
    ActionRecord,
    ActionStatus,
)
from .protocols import NodeOutputProtocol


class RuntimeStateManager:
    """
    Runtime State Manager
    
    Responsibilities:
    1. Maintain WorkflowRuntimeState as single source of truth
    2. Handle node state transitions
    3. Manage execution tree structure
    4. Provide state query interfaces
    
    Usage:
        manager = RuntimeStateManager(workflow_id="wf_001", run_id="run_abc")
        
        # Start a node
        node = manager.start_node("node_1", "My Task", "computer-use")
        
        # Complete with output
        output = NodeOutputProtocol(node_id="node_1", status="success", ...)
        manager.complete_node("node_1", output)
        
        # Query state
        current = manager.get_current_node()
        completed = manager.get_completed_nodes()
    """
    
    # Node type classification mapping
    LOOP_TYPES = {"loop"}
    LOGIC_TYPES = {"if-else", "start", "end", "loop-start", "loop-end"}
    
    def __init__(
        self,
        workflow_id: str,
        run_id: str,
        initial_variables: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize RuntimeStateManager
        
        Args:
            workflow_id: Workflow definition ID
            run_id: Unique run/task ID
            initial_variables: Optional initial global variables
        """
        self.state = WorkflowRuntimeState(
            workflow_id=workflow_id,
            run_id=run_id,
            variables=initial_variables or {},
        )
        self._loop_stack: List[str] = []  # Current loop stack
        self._iteration_counters: Dict[str, int] = {}  # Loop iteration counters
    
    # ==================== Node Lifecycle Management ====================
    
    def start_node(
        self,
        node_def_id: str,
        name: str,
        original_node_type: str,
        input_data: Optional[Dict[str, Any]] = None,
        parent_id: Optional[str] = None,
    ) -> ExecutionNode:
        """
        Start executing a node
        
        Creates an ExecutionNode and adds it to the execution tree.
        
        Args:
            node_def_id: Node definition ID from workflow
            name: Display name
            original_node_type: Original node type (computer-use, if-else, etc.)
            input_data: Input data for this node
            parent_id: Parent node ID (from workflow definition)
            
        Returns:
            Created ExecutionNode
        """
        # Classify node type
        exec_type = self._classify_node_type(original_node_type)
        
        # Generate runtime ID
        if self._loop_stack and parent_id:
            # Inside a loop - use the running iteration's index for suffix
            loop_id = self._loop_stack[-1]
            iteration_node = self._get_current_iteration_node(loop_id)
            if iteration_node:
                # Extract iteration number from the running iteration node
                # ID format: "{loop_id}_iteration_{num}"
                try:
                    iter_num = int(iteration_node.id.rsplit('_iteration_', 1)[-1])
                except (ValueError, IndexError):
                    iter_num = self._iteration_counters.get(loop_id, 0)
            else:
                # No running iteration yet - use counter (will be 0 for first iteration)
                iter_num = self._iteration_counters.get(loop_id, 0)
            runtime_id = f"{node_def_id}_iter_{iter_num}"
        else:
            runtime_id = node_def_id
        
        # Check if node already exists (for loop iterations)
        existing = self.state.get_node(runtime_id)
        if existing and existing.status == NodeStatus.RUNNING:
            # Already running, just return it
            return existing
        
        # Create execution node
        exec_node = ExecutionNode(
            id=runtime_id,
            node_def_id=node_def_id,
            name=name,
            type=exec_type,
            original_node_type=original_node_type,
            status=NodeStatus.RUNNING,
            input_data=input_data,
            start_time=time.time(),
            parent_id=parent_id,
        )
        
        # Add to execution tree based on type and context
        if exec_type == ExecutionNodeType.LOOP_CONTAINER:
            # Loop container goes to main tree
            self.state.execution_tree.append(exec_node)
            self._loop_stack.append(runtime_id)
            self._iteration_counters[runtime_id] = 0
            
        elif self._loop_stack and parent_id:
            # Inside a loop - add to current iteration's children
            loop_id = self._loop_stack[-1]
            loop_node = self.state.get_node(loop_id)
            
            if loop_node:
                # Find or create current iteration node
                iteration_node = self._get_or_create_current_iteration(loop_id)
                if iteration_node:
                    exec_node.parent_id = iteration_node.id
                    iteration_node.children.append(exec_node)
                else:
                    # Fallback: add directly to loop
                    exec_node.parent_id = loop_id
                    loop_node.children.append(exec_node)
            else:
                # Fallback: add to main tree
                self.state.execution_tree.append(exec_node)
        else:
            # Not in loop - add to main tree
            self.state.execution_tree.append(exec_node)
        
        # Register to index
        self.state.register_node(exec_node)
        self.state.current_node_id = runtime_id
        
        return exec_node
    
    def complete_node(
        self,
        node_id: str,
        output: NodeOutputProtocol,
    ) -> ExecutionNode:
        """
        Complete a node execution
        
        Updates node status, output data, and global variables.
        
        Args:
            node_id: Node ID to complete
            output: Node output protocol instance
            
        Returns:
            Updated ExecutionNode
            
        Raises:
            ValueError: If node not found
        """
        resolved_id = self._resolve_node_id(node_id)
        exec_node = self.state.get_node(resolved_id)
        if not exec_node:
            # Try without iteration suffix (legacy)
            exec_node = self.state.get_node(output.node_id)
            if not exec_node:
                raise ValueError(f"Node {node_id} not found in execution tree")
        
        # Update node status
        if output.status == "success":
            exec_node.status = NodeStatus.SUCCESS
        elif output.status == "failed":
            exec_node.status = NodeStatus.FAILED
        else:
            exec_node.status = NodeStatus.PENDING
        
        exec_node.output_data = output.output_data
        exec_node.history_summary = output.history_summary
        exec_node.end_time = time.time()
        exec_node.token_usage = output.token_usage
        
        # Handle logic node special fields
        if output.chosen_branch_id:
            exec_node.selected_path = output.chosen_branch_id
        
        # Update global variables blackboard
        if output.update_variables:
            self.state.variables.update(output.update_variables)
        
        # If loop container ends, pop from stack
        # BUT only if break_loop is True (loop is truly done).
        # When the loop handler finishes planning (break_loop=False),
        # the loop must stay in the stack so child nodes get added
        # to iteration.children correctly.
        if exec_node.type == ExecutionNodeType.LOOP_CONTAINER:
            if self._loop_stack and self._loop_stack[-1] == node_id:
                if output.break_loop:
                    self._loop_stack.pop()
                else:
                    # Loop handler completed planning, iterations haven't run yet.
                    # Keep loop RUNNING so iteration children are properly nested.
                    exec_node.status = NodeStatus.RUNNING
        
        # If loop-end with break, mark loop as complete
        if exec_node.original_node_type == "loop-end" and output.break_loop:
            if self._loop_stack:
                loop_id = self._loop_stack[-1]
                loop_node = self.state.get_node(loop_id)
                if loop_node:
                    loop_node.status = NodeStatus.SUCCESS
                    loop_node.end_time = time.time()
                self._loop_stack.pop()
        
        return exec_node
    
    def finish_loop(self, loop_id: str):
        """
        Cleanly finish a loop: pop from stack and mark as complete.
        
        Call this when the loop exits for ANY reason (break_loop, max_iterations, etc.)
        and complete_node did NOT already handle the cleanup (e.g. max_iterations path
        where break_loop=False).
        
        Safe to call even if the loop is already finished (idempotent).
        """
        # Pop from stack if it's the current loop
        if self._loop_stack and self._loop_stack[-1] == loop_id:
            self._loop_stack.pop()
        
        # Mark loop container as complete
        loop_node = self.state.get_node(loop_id)
        if loop_node and loop_node.status == NodeStatus.RUNNING:
            loop_node.status = NodeStatus.SUCCESS
            loop_node.end_time = time.time()
    
    def skip_node(
        self,
        node_def_id: str,
        name: str,
        original_node_type: str,
        reason: str = "Branch not selected",
    ) -> ExecutionNode:
        """
        Mark a node as skipped (for unselected If-Else branches)
        
        Args:
            node_def_id: Node definition ID
            name: Display name
            original_node_type: Original node type
            reason: Reason for skipping
            
        Returns:
            Created ExecutionNode with SKIPPED status
        """
        exec_type = self._classify_node_type(original_node_type)
        
        exec_node = ExecutionNode(
            id=node_def_id,
            node_def_id=node_def_id,
            name=name,
            type=exec_type,
            original_node_type=original_node_type,
            status=NodeStatus.SKIPPED,
            history_summary=reason,
            start_time=time.time(),
            end_time=time.time(),
        )
        
        # Add to execution tree (skipped nodes are also recorded)
        if self._loop_stack:
            loop_id = self._loop_stack[-1]
            iteration_node = self._get_current_iteration_node(loop_id)
            if iteration_node:
                exec_node.parent_id = iteration_node.id
                iteration_node.children.append(exec_node)
            else:
                loop_node = self.state.get_node(loop_id)
                if loop_node:
                    exec_node.parent_id = loop_id
                    loop_node.children.append(exec_node)
                else:
                    self.state.execution_tree.append(exec_node)
        else:
            self.state.execution_tree.append(exec_node)
        
        self.state.register_node(exec_node)
        return exec_node
    
    def skip_branch_nodes(
        self,
        branch_node_ids: List[str],
        node_info_map: Dict[str, Dict[str, Any]],
        reason: str = "Branch not selected",
    ) -> List[ExecutionNode]:
        """
        Mark multiple nodes as skipped (entire branch)
        
        Args:
            branch_node_ids: List of node IDs to skip
            node_info_map: Map of node_id to node info (name, type)
            reason: Reason for skipping
            
        Returns:
            List of created skipped nodes
        """
        skipped_nodes = []
        for node_id in branch_node_ids:
            info = node_info_map.get(node_id, {})
            name = info.get("name", info.get("title", node_id))
            node_type = info.get("type", "unknown")
            
            skipped = self.skip_node(node_id, name, node_type, reason)
            skipped_nodes.append(skipped)
        
        return skipped_nodes
    
    # ==================== Loop Iteration Management ====================
    
    def start_loop_iteration(self, loop_id: str) -> ExecutionNode:
        """
        Start a new loop iteration
        
        Creates a loop_iteration node as a child of the loop container.
        
        Args:
            loop_id: Loop container node ID
            
        Returns:
            Created iteration node
            
        Raises:
            ValueError: If loop not found
        """
        loop_node = self.state.get_node(loop_id)
        if not loop_node:
            raise ValueError(f"Loop {loop_id} not found")
        
        # Increment iteration counter
        iteration_num = self._iteration_counters.get(loop_id, 0)
        self._iteration_counters[loop_id] = iteration_num + 1
        
        # Create iteration node
        iteration_node = ExecutionNode(
            id=f"{loop_id}_iteration_{iteration_num}",
            node_def_id=loop_id,
            name=f"Iteration {iteration_num + 1}",
            type=ExecutionNodeType.LOOP_ITERATION,
            original_node_type="loop-iteration",
            status=NodeStatus.RUNNING,
            parent_id=loop_id,
            start_time=time.time(),
        )
        
        loop_node.children.append(iteration_node)
        self.state.register_node(iteration_node)
        
        return iteration_node
    
    def complete_loop_iteration(
        self,
        loop_id: str,
        summary: Optional[str] = None,
    ) -> Optional[ExecutionNode]:
        """
        Complete current loop iteration
        
        Args:
            loop_id: Loop container node ID
            summary: Iteration summary
            
        Returns:
            Completed iteration node
        """
        iteration_node = self._get_current_iteration_node(loop_id)
        if iteration_node:
            iteration_node.status = NodeStatus.SUCCESS
            iteration_node.end_time = time.time()
            if summary:
                iteration_node.history_summary = summary
        
        return iteration_node
    
    def get_current_iteration(self, loop_id: str) -> int:
        """
        Get the 0-based index of the currently RUNNING iteration.
        
        Note: _iteration_counters tracks "next iteration number to create",
        which is often 1 higher than the running iteration's index.
        This method looks at the actual running iteration node for accuracy.
        """
        loop_node = self.state.get_node(loop_id)
        if loop_node:
            for i, child in enumerate(loop_node.children):
                if (child.type == ExecutionNodeType.LOOP_ITERATION and
                    child.status == NodeStatus.RUNNING):
                    return i
        # Fallback: use counter - 1 (counter tracks next-to-create)
        counter = self._iteration_counters.get(loop_id, 0)
        return max(0, counter - 1) if counter > 0 else 0
    
    def _get_or_create_current_iteration(self, loop_id: str) -> Optional[ExecutionNode]:
        """Get or create current iteration node"""
        iteration_node = self._get_current_iteration_node(loop_id)
        if not iteration_node:
            iteration_node = self.start_loop_iteration(loop_id)
        return iteration_node
    
    def _get_current_iteration_node(self, loop_id: str) -> Optional[ExecutionNode]:
        """Get the current (running) iteration node for a loop"""
        loop_node = self.state.get_node(loop_id)
        if not loop_node:
            return None
        
        # Find running iteration
        for child in reversed(loop_node.children):
            if (child.type == ExecutionNodeType.LOOP_ITERATION and 
                child.status == NodeStatus.RUNNING):
                return child
        
        return None
    
    # ==================== State Query Interfaces ====================
    
    def get_current_node(self) -> Optional[ExecutionNode]:
        """Get currently executing node"""
        if self.state.current_node_id:
            return self.state.get_node(self.state.current_node_id)
        return None
    
    def get_completed_nodes(self) -> List[ExecutionNode]:
        """Get all completed nodes (flattened)"""
        return self.state.get_completed_nodes()
    
    def get_pending_nodes(self) -> List[ExecutionNode]:
        """Get all pending nodes"""
        return self.state.get_nodes_by_status(NodeStatus.PENDING)
    
    def get_loop_context(self) -> Optional[Dict[str, Any]]:
        """Get current loop context"""
        if not self._loop_stack:
            return None
        
        loop_id = self._loop_stack[-1]
        loop_node = self.state.get_node(loop_id)
        if not loop_node:
            return None
        
        iteration_count = len([
            c for c in loop_node.children
            if c.type == ExecutionNodeType.LOOP_ITERATION
        ])
        
        return {
            "loop_id": loop_id,
            "iteration": self._iteration_counters.get(loop_id, 0),
            "iteration_count": iteration_count,
            "in_loop": True,
        }
    
    def is_in_loop(self) -> bool:
        """Check if currently inside a loop"""
        return bool(self._loop_stack)
    
    def get_variables(self) -> Dict[str, Any]:
        """Get global variables blackboard"""
        return self.state.variables.copy()
    
    def set_variable(self, key: str, value: Any):
        """Set a global variable"""
        self.state.variables[key] = value
    
    def update_variables(self, updates: Dict[str, Any]):
        """Update multiple global variables"""
        self.state.variables.update(updates)
    
    # ==================== Workflow Lifecycle ====================
    
    def complete_workflow(
        self,
        final_status: str = "completed",
    ):
        """Mark workflow as completed"""
        self.state.mark_completed(final_status)
    
    def fail_workflow(self, error_message: str):
        """Mark workflow as failed"""
        self.state.status = "failed"
        self.state.end_time = time.time()
        self.set_variable("_workflow_error", error_message)
    
    # ==================== Persistence ====================
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize entire state to dictionary"""
        return {
            "state": self.state.to_dict(),
            "loop_stack": self._loop_stack.copy(),
            "iteration_counters": self._iteration_counters.copy(),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RuntimeStateManager":
        """Restore state from dictionary"""
        state_data = data.get("state", {})
        state = WorkflowRuntimeState.from_dict(state_data)
        
        manager = cls(
            workflow_id=state.workflow_id,
            run_id=state.run_id,
        )
        manager.state = state
        manager._loop_stack = data.get("loop_stack", [])
        manager._iteration_counters = data.get("iteration_counters", {})
        
        return manager
    
    def save_to_file(self, file_path: str) -> bool:
        """Save state to JSON file"""
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
            return True
        except Exception:
            return False
    
    @classmethod
    def load_from_file(cls, file_path: str) -> Optional["RuntimeStateManager"]:
        """Load state from JSON file"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return cls.from_dict(data)
        except Exception:
            return None
    
    # ==================== Node Internal State Management ====================
    
    def _resolve_node_id(self, node_id: str) -> str:
        """
        Resolve graph node_id to runtime execution node id.
        Inside a loop, the execution node has id like node_def_id_iter_N;
        handlers and flow_processor pass graph node_id, so we must resolve to the
        actual runtime node so action_history is recorded on the node in iteration.children.
        """
        if self.state.get_node(node_id):
            return node_id
        if self.state.current_node_id:
            current = self.state.get_node(self.state.current_node_id)
            if current and getattr(current, "node_def_id", None) == node_id:
                return self.state.current_node_id
        return node_id
    
    def get_node_resolved(self, node_id: str):
        """Get ExecutionNode by node_id, resolving to runtime id when inside a loop."""
        resolved_id = self._resolve_node_id(node_id)
        return self.state.get_node(resolved_id)
    
    def record_node_action(
        self,
        node_id: str,
        observation: Optional[str] = None,
        reasoning: Optional[str] = None,
        action_type: Optional[str] = None,
        action_params: Optional[Dict[str, Any]] = None,
        action_target: Optional[str] = None,
        token_usage: Optional[Dict[str, Any]] = None,
        thinking: Optional[str] = None,
        title: Optional[str] = None,
        step_memory: Optional[str] = None,
    ) -> ActionRecord:
        """
        Record an agent action within a node
        
        Creates a new ActionRecord and adds it to the node's action_history.
        The action starts in RUNNING status.
        
        Args:
            node_id: Node ID
            observation: What the agent observed before acting (legacy)
            reasoning: Agent's reasoning for the action (legacy)
            action_type: Type of action (click, type, scroll, etc.)
            action_params: Action parameters
            action_target: Target element description
            token_usage: Token usage for this step
            thinking: Free-form thinking from agent (new format)
            title: Short title for UI display
            step_memory: Key information/notes collected at this step by AI
            
        Returns:
            Created ActionRecord
            
        Raises:
            ValueError: If node not found
        """
        resolved_id = self._resolve_node_id(node_id)
        exec_node = self.state.get_node(resolved_id)
        if not exec_node:
            raise ValueError(f"Node {node_id} not found")
        
        # Increment step count
        exec_node.step_count += 1
        
        # Create action record
        action = ActionRecord(
            step=exec_node.step_count,
            timestamp=time.time(),
            thinking=thinking,
            title=title,
            observation=observation,
            reasoning=reasoning,
            action_type=action_type,
            action_params=action_params,
            action_target=action_target,
            status=ActionStatus.RUNNING,
            token_usage=token_usage,
            step_memory=step_memory,
        )
        
        exec_node.action_history.append(action)
        return action
    
    def complete_node_action(
        self,
        node_id: str,
        step: Optional[int] = None,
        status: str = "success",
        result_observation: Optional[str] = None,
        error: Optional[str] = None,
    ) -> Optional[ActionRecord]:
        """
        Complete an action within a node
        
        Args:
            node_id: Node ID
            step: Step number to complete (defaults to last action)
            status: Action status (success/failed)
            result_observation: Observation after action
            error: Error message if failed
            
        Returns:
            Updated ActionRecord or None
        """
        resolved_id = self._resolve_node_id(node_id)
        exec_node = self.state.get_node(resolved_id)
        if not exec_node or not exec_node.action_history:
            return None
        
        # Find the action to complete
        if step is not None:
            action = next(
                (a for a in exec_node.action_history if a.step == step),
                None
            )
        else:
            # Default to last action
            action = exec_node.action_history[-1]
        
        if not action:
            return None
        
        # Update action status
        action.status = ActionStatus.SUCCESS if status == "success" else ActionStatus.FAILED
        action.result_observation = result_observation
        action.error = error
        
        # Update failure tracking
        if action.status == ActionStatus.FAILED:
            exec_node.consecutive_failures += 1
        else:
            exec_node.consecutive_failures = 0
        
        return action
    
    def get_node_action_history(self, node_id: str) -> List[ActionRecord]:
        """
        Get action history for a node
        
        Args:
            node_id: Node ID
            
        Returns:
            List of ActionRecords
        """
        resolved_id = self._resolve_node_id(node_id)
        exec_node = self.state.get_node(resolved_id)
        if not exec_node:
            return []
        return exec_node.action_history.copy()
    
    def get_node_last_action(self, node_id: str) -> Optional[ActionRecord]:
        """
        Get the most recent action for a node
        
        Args:
            node_id: Node ID
            
        Returns:
            Last ActionRecord or None
        """
        resolved_id = self._resolve_node_id(node_id)
        exec_node = self.state.get_node(resolved_id)
        if not exec_node:
            return None
        return exec_node.get_last_action()
    
    def get_node_step_count(self, node_id: str) -> int:
        """
        Get current step count for a node
        
        Args:
            node_id: Node ID
            
        Returns:
            Current step count
        """
        resolved_id = self._resolve_node_id(node_id)
        exec_node = self.state.get_node(resolved_id)
        if not exec_node:
            return 0
        return exec_node.step_count
    
    def set_node_state(self, node_id: str, key: str, value: Any):
        """
        Set internal state value for a node
        
        Args:
            node_id: Node ID
            key: State key
            value: State value
            
        Raises:
            ValueError: If node not found
        """
        exec_node = self.state.get_node(node_id)
        if not exec_node:
            raise ValueError(f"Node {node_id} not found")
        exec_node.internal_state[key] = value
    
    def get_node_state(self, node_id: str, key: str, default: Any = None) -> Any:
        """
        Get internal state value for a node
        
        Args:
            node_id: Node ID
            key: State key
            default: Default value if key not found
            
        Returns:
            State value or default
        """
        exec_node = self.state.get_node(node_id)
        if not exec_node:
            return default
        return exec_node.internal_state.get(key, default)
    
    def update_node_state(self, node_id: str, updates: Dict[str, Any]):
        """
        Batch update internal state for a node
        
        Args:
            node_id: Node ID
            updates: Dictionary of state updates
            
        Raises:
            ValueError: If node not found
        """
        exec_node = self.state.get_node(node_id)
        if not exec_node:
            raise ValueError(f"Node {node_id} not found")
        exec_node.internal_state.update(updates)
    
    def get_all_node_state(self, node_id: str) -> Dict[str, Any]:
        """
        Get entire internal state for a node
        
        Args:
            node_id: Node ID
            
        Returns:
            Copy of internal state dict
        """
        exec_node = self.state.get_node(node_id)
        if not exec_node:
            return {}
        return exec_node.internal_state.copy()
    
    def increment_node_retry(self, node_id: str) -> int:
        """
        Increment retry count for a node
        
        Args:
            node_id: Node ID
            
        Returns:
            New retry count
            
        Raises:
            ValueError: If node not found
        """
        exec_node = self.state.get_node(node_id)
        if not exec_node:
            raise ValueError(f"Node {node_id} not found")
        exec_node.retry_count += 1
        return exec_node.retry_count
    
    def should_retry_node(self, node_id: str) -> bool:
        """
        Check if node should retry (under max retries)
        
        Args:
            node_id: Node ID
            
        Returns:
            True if should retry
        """
        exec_node = self.state.get_node(node_id)
        if not exec_node:
            return False
        return exec_node.should_retry()
    
    def record_node_failure(self, node_id: str, error: str):
        """
        Record a failure for a node
        
        Increments consecutive_failures and stores error in internal_state.
        
        Args:
            node_id: Node ID
            error: Error message
            
        Raises:
            ValueError: If node not found
        """
        exec_node = self.state.get_node(node_id)
        if not exec_node:
            raise ValueError(f"Node {node_id} not found")
        
        exec_node.consecutive_failures += 1
        
        # Store error history
        errors = exec_node.internal_state.get("_errors", [])
        errors.append({
            "timestamp": time.time(),
            "error": error,
            "step": exec_node.step_count,
        })
        exec_node.internal_state["_errors"] = errors
        exec_node.internal_state["_last_error"] = error
    
    def reset_node_failures(self, node_id: str):
        """
        Reset consecutive failure count for a node
        
        Call this after a successful action.
        
        Args:
            node_id: Node ID
        """
        exec_node = self.state.get_node(node_id)
        if exec_node:
            exec_node.consecutive_failures = 0
    
    def get_node_failure_count(self, node_id: str) -> int:
        """
        Get consecutive failure count for a node
        
        Args:
            node_id: Node ID
            
        Returns:
            Consecutive failure count
        """
        exec_node = self.state.get_node(node_id)
        if not exec_node:
            return 0
        return exec_node.consecutive_failures
    
    # ==================== Internal Helpers ====================
    
    def _classify_node_type(self, original_type: str) -> ExecutionNodeType:
        """Classify original node type to execution type"""
        if original_type in self.LOOP_TYPES:
            return ExecutionNodeType.LOOP_CONTAINER
        elif original_type in self.LOGIC_TYPES:
            return ExecutionNodeType.LOGIC
        else:
            return ExecutionNodeType.ACTION
