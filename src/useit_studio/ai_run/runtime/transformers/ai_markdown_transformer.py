"""
AI Markdown Transformer

Generates concise Markdown for AI context window.

Design Goals:
- Minimal: Only include essential information
- Focused: Highlight current task and recent history
- De-noised: Skip skipped nodes, compress old loop iterations

Output Format:
```markdown
# Context

## Variables
- key: value

## Current Plan
- [x] Completed Node (Summary: ...)
- [-->] **Current Node**
- [ ] Pending Node
```
"""

from typing import List, Optional, Dict, Any
from ..models import (
    WorkflowRuntimeState,
    ExecutionNode,
    ExecutionNodeType,
    NodeStatus,
    ActionRecord,
    ActionStatus,
)


class AIMarkdownTransformer:
    """
    View A: Generate AI Context Markdown
    
    Goals: Minimal, focused, de-noised
    
    Rules:
    1. Skip nodes with status == 'skipped'
    2. For loops: show only summary for old iterations, expand current
    3. Keep only recent N completed nodes in history
    4. Optionally show pending nodes from graph definition
    
    Usage:
        transformer = AIMarkdownTransformer(state)
        markdown = transformer.transform()
        
        # With full plan from graph
        transformer = AIMarkdownTransformer(state, graph_nodes=graph_manager.nodes)
        markdown = transformer.transform()
    """
    
    MAX_HISTORY_ITEMS = 10
    MAX_VALUE_LENGTH = 100
    MAX_ACTIONS_SHOWN = None  # No limit: show all steps
    
    def __init__(
        self,
        state: WorkflowRuntimeState,
        include_variables: bool = True,
        include_history: bool = False,
        max_history: int = 10,
        graph_nodes: Optional[Dict[str, Dict[str, Any]]] = None,
        graph_edges: Optional[List[Dict[str, Any]]] = None,
    ):
        """
        Initialize transformer
        
        Args:
            state: Workflow runtime state
            include_variables: Whether to include variables section
            include_history: Whether to include separate history section
            max_history: Maximum history items to show
            graph_nodes: Optional graph nodes dict to show pending nodes
            graph_edges: Optional graph edges list for ordering
        """
        self.state = state
        self.include_variables = include_variables
        self.include_history = include_history
        self.max_history = max_history
        self.graph_nodes = graph_nodes
        self.graph_edges = graph_edges
        
        # Build adjacency list if edges provided
        self._adjacency_list: Dict[str, List[str]] = {}
        if graph_edges:
            for edge in graph_edges:
                source = edge.get("source")
                target = edge.get("target")
                if source and target:
                    if source not in self._adjacency_list:
                        self._adjacency_list[source] = []
                    self._adjacency_list[source].append(target)
    
    def transform(self) -> str:
        """
        Generate complete AI context Markdown
        
        Returns:
            Formatted Markdown string
        """
        parts = []
        
        # 1. Header
        parts.append("# Context")
        parts.append("")
        
        # 2. Global Variables (blackboard)
        if self.include_variables:
            parts.extend(self._build_variables_section())
            parts.append("")
        
        # 3. Current Plan (TODO tree)
        parts.append("## Current Plan")
        
        # If graph_nodes provided, show full plan with pending nodes
        if self.graph_nodes:
            plan_lines = self._build_full_plan_tree()
        else:
            plan_lines = self._build_plan_tree(self.state.execution_tree, indent=0)
        
        if plan_lines:
            parts.extend(plan_lines)
        else:
            parts.append("- (No tasks executed yet)")
        parts.append("")
        
        # 4. Recent History (optional)
        if self.include_history:
            parts.append("## Recent History")
            history_lines = self._build_recent_history()
            parts.extend(history_lines)
            parts.append("")
        
        return "\n".join(parts)
    
    def transform_minimal(self) -> str:
        """
        Generate minimal context (just the plan tree)
        
        Returns:
            Minimal Markdown string
        """
        parts = []
        parts.append("## Current Plan")
        plan_lines = self._build_plan_tree(self.state.execution_tree, indent=0)
        if plan_lines:
            parts.extend(plan_lines)
        else:
            parts.append("- (No tasks executed yet)")
        
        return "\n".join(parts)
    
    def _build_variables_section(self) -> List[str]:
        """Build variables section"""
        lines = ["## Variables"]
        
        if self.state.variables:
            for key, value in self.state.variables.items():
                # Skip internal variables
                if key.startswith("_"):
                    continue
                display_value = self._truncate_value(value)
                lines.append(f"- {key}: {display_value}")
        else:
            lines.append("- (No variables set)")
        
        return lines
    
    def _build_full_plan_tree(self) -> List[str]:
        """
        Build full plan tree including pending nodes from graph
        
        This method combines:
        1. Executed nodes from execution_tree (with status)
        2. Pending nodes from graph_nodes (not yet started)
        """
        if not self.graph_nodes:
            return self._build_plan_tree(self.state.execution_tree, indent=0)
        
        lines = []
        
        # Get executed node IDs
        executed_ids = set(self.state._node_index.keys())
        
        # Find start node
        start_node_id = None
        for node_id, node in self.graph_nodes.items():
            if node.get("data", {}).get("type") == "start":
                start_node_id = node_id
                break
        
        if not start_node_id:
            return self._build_plan_tree(self.state.execution_tree, indent=0)
        
        # Traverse graph and build plan
        visited = set()
        self._traverse_and_build_plan(start_node_id, lines, visited, executed_ids, indent=0)
        
        return lines
    
    def _traverse_and_build_plan(
        self,
        node_id: str,
        lines: List[str],
        visited: set,
        executed_ids: set,
        indent: int = 0,
        parent_loop_id: Optional[str] = None,
    ):
        """Traverse graph and build plan tree"""
        if node_id in visited:
            return
        visited.add(node_id)
        
        node_def = self.graph_nodes.get(node_id)
        if not node_def:
            return
        
        node_data = node_def.get("data", {})
        node_type = node_data.get("type", "unknown")
        node_title = node_data.get("title", node_id)
        node_parent = node_def.get("parentNode")
        # 尝试获取 instruction，如果没有则使用 description
        node_instruction = node_data.get("instruction", "") or node_data.get("description", "")
        indent_str = "  " * indent
        
        # Skip nodes inside loops when traversing main flow
        # (they will be handled when we process the loop)
        if node_parent and not parent_loop_id:
            # This node is inside a loop, skip for now
            pass
        else:
            # Check if this node has been executed
            exec_node = self.state.get_node(node_id)
            
            if node_type == "loop":
                # Handle loop specially
                self._build_loop_plan(node_id, lines, visited, executed_ids, indent)
            elif exec_node:
                # Node has been executed - show with status
                status_mark = self._get_status_mark(exec_node.status)
                if exec_node.status == NodeStatus.RUNNING:
                    # Show current node with instruction - marked as [Node]
                    display_text = self._format_running_node(node_title, node_instruction, node_data)
                    lines.append(f"{indent_str}- {status_mark} [Node] **{display_text}** (Current Node)")
                    # Show task_tips if available
                    task_tips = node_data.get("task_tips", "")
                    if task_tips:
                        lines.append(f"{indent_str}  - Task Tips: {task_tips}")
                    # Show action history if available (new action_history or legacy output_data)
                    if exec_node.action_history or exec_node.output_data:
                        action_lines = self._build_action_history(exec_node, indent + 1)
                        lines.extend(action_lines)
                elif exec_node.status == NodeStatus.SKIPPED:
                    pass  # Skip skipped nodes
                else:
                    # Completed node - show with instruction and full summary (no truncation)
                    display_text = self._format_completed_node(node_title, node_instruction, node_data)
                    lines.append(f"{indent_str}- {status_mark} [Node] {display_text}")
                    # Show summary on new line with indentation (supports XML format)
                    if exec_node.history_summary and exec_node.status == NodeStatus.SUCCESS:
                        lines.append(f"{indent_str}  {exec_node.history_summary}")
            else:
                # Node not yet executed - show as pending with instruction if available
                display_text = self._format_pending_node(node_title, node_instruction, node_data)
                lines.append(f"{indent_str}- [ ] [Node] {display_text}")
        
        # Traverse to next nodes
        next_nodes = self._adjacency_list.get(node_id, [])
        for next_id in next_nodes:
            next_def = self.graph_nodes.get(next_id, {})
            next_parent = next_def.get("parentNode")
            
            # Only traverse if not inside a different loop
            if not next_parent or next_parent == parent_loop_id:
                self._traverse_and_build_plan(next_id, lines, visited, executed_ids, indent, parent_loop_id)
    
    def _build_loop_plan(
        self,
        loop_id: str,
        lines: List[str],
        visited: set,
        executed_ids: set,
        indent: int,
    ):
        """Build loop plan with internal nodes"""
        loop_def = self.graph_nodes.get(loop_id)
        if not loop_def:
            return
        
        loop_data = loop_def.get("data", {})
        loop_title = loop_data.get("title", loop_id)
        loop_goal = loop_data.get("instruction", "") or loop_data.get("description", "")
        indent_str = "  " * indent
        
        # Check if loop has been executed
        exec_loop = self.state.get_node(loop_id)
        
        if exec_loop:
            # Loop has started
            
            # Get iteration_plan from internal_state
            iteration_plan = exec_loop.internal_state.get("iteration_plan", [])
            
            # Get actual iterations from children
            iterations = [
                c for c in exec_loop.children
                if c.type == ExecutionNodeType.LOOP_ITERATION
            ]
            
            # Determine current iteration index based on actual iteration status
            # This is more accurate than exec_loop.status which may be inconsistent
            current_iteration_idx = 0
            has_running_iteration = False
            for i, iteration in enumerate(iterations):
                if iteration.status == NodeStatus.RUNNING:
                    current_iteration_idx = i
                    has_running_iteration = True
                    break
                elif iteration.status == NodeStatus.SUCCESS:
                    current_iteration_idx = i + 1  # Next iteration is current
            
            # Determine if loop is actually running based on iterations
            # Loop is running if: has running iteration OR not all planned iterations are done
            loop_actually_running = has_running_iteration or (current_iteration_idx < len(iteration_plan))
            loop_actually_completed = not loop_actually_running and current_iteration_idx >= len(iteration_plan) and len(iterations) > 0
            
            # Use actual status for display
            if loop_actually_completed:
                status_mark = "[x]"
                lines.append(f"{indent_str}- {status_mark} Loop: {loop_title} - Completed")
            elif loop_actually_running:
                status_mark = "[-->]"
                lines.append(f"{indent_str}- {status_mark} **Loop: {loop_title}**")
            else:
                status_mark = self._get_status_mark(exec_loop.status)
                lines.append(f"{indent_str}- {status_mark} Loop: {loop_title}")
            
            # Show loop goal if available
            if loop_goal:
                lines.append(f"{indent_str}  - Goal: {self._truncate_value(loop_goal, 80)}")
            
            # Show iteration plan overview if available
            if iteration_plan:
                lines.append(f"{indent_str}  - Plan ({len(iteration_plan)} iterations):")
                for i, task in enumerate(iteration_plan):
                    if i < current_iteration_idx:
                        status = "✓"
                    elif i == current_iteration_idx and loop_actually_running:
                        status = "→"
                    elif loop_actually_completed:
                        status = "✓"
                    else:
                        status = " "
                    current_marker = " ← Current" if i == current_iteration_idx and loop_actually_running else ""
                    lines.append(f"{indent_str}    {status} {i+1}. {self._truncate_value(task, 60)}{current_marker}")
            
            if iterations:
                for i, iteration in enumerate(iterations):
                    is_current = (iteration.status == NodeStatus.RUNNING)
                    is_last = (i == len(iterations) - 1)
                    
                    # Get iteration task from plan
                    iter_task = iteration_plan[i] if i < len(iteration_plan) else ""
                    
                    # Show as current if: iteration is running, OR it's the last iteration and loop is still running
                    if is_current or (is_last and loop_actually_running and not has_running_iteration):
                        # Current iteration: show executed + pending nodes
                        iter_status = self._get_status_mark(iteration.status)
                        if iter_task:
                            lines.append(f"{indent_str}  - {iter_status} **Iteration {i + 1}: {self._truncate_value(iter_task, 50)}** (Current)")
                        else:
                            lines.append(f"{indent_str}  - {iter_status} **Iteration {i + 1}** (Current)")
                        
                        # Show executed children
                        for child in iteration.children:
                            if child.status == NodeStatus.SKIPPED:
                                continue
                            child_lines = self._build_plan_tree([child], indent + 2)
                            lines.extend(child_lines)
                        
                        # Show pending nodes inside loop
                        self._show_pending_loop_nodes(loop_id, iteration, lines, indent + 2)
                    else:
                        # Completed iteration: show summary then expand children so node outputs are visible
                        summary = iteration.history_summary or iter_task or "Completed"
                        status = "[x]" if iteration.status == NodeStatus.SUCCESS else "[!]"
                        lines.append(f"{indent_str}  - {status} Iteration {i + 1}: {self._truncate_value(summary, 60)}")
                        # Expand children so node outputs (action_history, history_summary) are visible
                        for child in iteration.children:
                            if child.status == NodeStatus.SKIPPED:
                                continue
                            child_lines = self._build_plan_tree([child], indent + 2)
                            lines.extend(child_lines)
            elif loop_actually_running:
                # TODO: need to check 
                for child in iteration.children:
                    if child.status == NodeStatus.SKIPPED:
                        continue
                    child_lines = self._build_plan_tree([child], indent + 2)
                    lines.extend(child_lines)
            elif exec_loop.status == NodeStatus.RUNNING:
                # Loop started but no iteration yet - show pending internal nodes
                lines.append(f"{indent_str}  - [ ] (Pending iterations)")
                self._show_pending_loop_nodes(loop_id, None, lines, indent + 2)
        else:
            # Loop not started yet - show as pending with internal nodes
            lines.append(f"{indent_str}- [ ] Loop: {loop_title}")
            
            # Show internal nodes as pending
            self._show_pending_loop_nodes(loop_id, None, lines, indent + 1)
    
    def _show_pending_loop_nodes(
        self,
        loop_id: str,
        current_iteration: Optional[ExecutionNode],
        lines: List[str],
        indent: int,
    ):
        """Show pending nodes inside a loop"""
        if not self.graph_nodes:
            return
        
        indent_str = "  " * indent
        
        # Get executed node IDs in current iteration
        executed_in_iteration = set()
        if current_iteration:
            for child in current_iteration.children:
                # Extract base node ID (remove _iter_N suffix)
                base_id = child.node_def_id
                executed_in_iteration.add(base_id)
        
        # Find nodes inside this loop
        loop_nodes = []
        for node_id, node_def in self.graph_nodes.items():
            if node_def.get("parentNode") == loop_id:
                node_data = node_def.get("data", {})
                node_type = node_data.get("type", "unknown")
                node_title = node_data.get("title", node_id)
                loop_nodes.append({
                    "id": node_id,
                    "type": node_type,
                    "title": node_title,
                })
        
        # Sort by finding loop-start first
        loop_start_id = None
        for n in loop_nodes:
            if n["type"] == "loop-start":
                loop_start_id = n["id"]
                break
        
        # Traverse from loop-start
        if loop_start_id:
            visited = set()
            self._traverse_loop_pending(loop_start_id, loop_id, executed_in_iteration, lines, visited, indent)
    
    def _traverse_loop_pending(
        self,
        node_id: str,
        loop_id: str,
        executed_ids: set,
        lines: List[str],
        visited: set,
        indent: int,
    ):
        """Traverse and show pending nodes inside a loop"""
        if node_id in visited:
            return
        visited.add(node_id)
        
        node_def = self.graph_nodes.get(node_id)
        if not node_def:
            return
        
        # Only process nodes inside this loop
        if node_def.get("parentNode") != loop_id:
            return
        
        node_data = node_def.get("data", {})
        node_type = node_data.get("type", "unknown")
        node_title = node_data.get("title", node_id)
        # 尝试获取 instruction，如果没有则使用 description
        node_instruction = node_data.get("instruction", "") or node_data.get("description", "")
        indent_str = "  " * indent
        
        # Check if already executed
        if node_id not in executed_ids:
            # Not executed yet - show as pending with instruction
            display_text = self._format_pending_node(node_title, node_instruction, node_data)
            lines.append(f"{indent_str}- [ ] {display_text}")
        
        # Traverse to next nodes inside loop
        next_nodes = self._adjacency_list.get(node_id, [])
        for next_id in next_nodes:
            next_def = self.graph_nodes.get(next_id, {})
            if next_def.get("parentNode") == loop_id:
                self._traverse_loop_pending(next_id, loop_id, executed_ids, lines, visited, indent)
    
    def _build_plan_tree(
        self,
        nodes: List[ExecutionNode],
        indent: int = 0,
    ) -> List[str]:
        """
        Build TODO tree structure
        
        Format:
        - [x] Completed Node (Summary: ...)
        - [-->] **Current Node**
        - [ ] Pending Node
        """
        lines = []
        indent_str = "  " * indent
        
        for node in nodes:
            # Skip skipped nodes
            if node.status == NodeStatus.SKIPPED:
                continue
            
            # Build status marker
            status_mark = self._get_status_mark(node.status)
            
            # Handle different node types
            if node.type == ExecutionNodeType.LOOP_CONTAINER:
                # Loop node - special handling
                lines.extend(self._build_loop_lines(node, indent))
            elif node.type == ExecutionNodeType.LOOP_ITERATION:
                # Iteration nodes are handled by loop
                continue
            elif node.status == NodeStatus.RUNNING:
                # Current node - highlight with instruction if available, marked as [Node]
                display_name = self._format_exec_node_name(node)
                lines.append(f"{indent_str}- {status_mark} [Node] **{display_name}** (Current Node)")
                # Show task_tips if available (from input_data or graph_nodes)
                task_tips = self._get_task_tips(node)
                if task_tips:
                    lines.append(f"{indent_str}  - Task Tips: {task_tips}")
                # Show action history if available (new action_history or legacy output_data)
                if node.action_history or node.output_data:
                    action_lines = self._build_action_history(node, indent + 1)
                    lines.extend(action_lines)
            else:
                # Completed or pending node - show with instruction and full summary (no truncation)
                display_name = self._format_exec_node_name(node)
                lines.append(f"{indent_str}- {status_mark} [Node] {display_name}")
                # Show summary on new line with indentation (supports XML format)
                if node.history_summary and node.status == NodeStatus.SUCCESS:
                    lines.append(f"{indent_str}  {node.history_summary}")
                # Show steps (action_history) for completed nodes so loop iterations show steps after loop completes
                if node.status == NodeStatus.SUCCESS and (node.action_history or node.output_data):
                    action_lines = self._build_action_history(node, indent + 1)
                    lines.extend(action_lines)
        
        return lines
    
    def _build_loop_lines(
        self,
        loop_node: ExecutionNode,
        indent: int,
    ) -> List[str]:
        """
        Build loop node Markdown
        
        Folding Strategy:
        - Completed iterations: show only one-line summary
        - Current iteration: fully expand internal TODO
        """
        lines = []
        indent_str = "  " * indent
        
        # Loop header
        status_mark = self._get_status_mark(loop_node.status)
        if loop_node.status == NodeStatus.SUCCESS:
            lines.append(f"{indent_str}- {status_mark} Loop: {loop_node.name} - Completed")
        elif loop_node.status == NodeStatus.RUNNING:
            lines.append(f"{indent_str}- {status_mark} **Loop: {loop_node.name}**")
        else:
            lines.append(f"{indent_str}- {status_mark} Loop: {loop_node.name}")
        
        # Process iteration children
        iterations = [
            c for c in loop_node.children
            if c.type == ExecutionNodeType.LOOP_ITERATION
        ]
        other_children = [
            c for c in loop_node.children
            if c.type != ExecutionNodeType.LOOP_ITERATION
        ]
        
        for i, iteration in enumerate(iterations):
            is_current = (iteration.status == NodeStatus.RUNNING)
            is_last = (i == len(iterations) - 1)
            
            if is_current or (is_last and loop_node.status == NodeStatus.RUNNING):
                # Current iteration: fully expand
                iter_status = self._get_status_mark(iteration.status)
                lines.append(f"{indent_str}  - {iter_status} **Iteration {i + 1}** (Current)")
                
                # Expand iteration children
                for child in iteration.children:
                    if child.status == NodeStatus.SKIPPED:
                        continue
                    child_lines = self._build_plan_tree([child], indent + 2)
                    lines.extend(child_lines)
            else:
                # Completed iteration: show summary then expand children so Browser Use steps are visible
                summary = iteration.history_summary or "Completed"
                status = "[x]" if iteration.status == NodeStatus.SUCCESS else "[!]"
                lines.append(f"{indent_str}  - {status} Iteration {i + 1}: {self._truncate_value(summary, 60)}")
                for child in iteration.children:
                    if child.status == NodeStatus.SKIPPED:
                        continue
                    child_lines = self._build_plan_tree([child], indent + 2)
                    lines.extend(child_lines)
        
        # Handle non-iteration children (if any)
        if other_children:
            child_lines = self._build_plan_tree(other_children, indent + 1)
            lines.extend(child_lines)
        
        return lines
    
    def _build_action_history(
        self,
        node: ExecutionNode,
        indent: int,
    ) -> List[str]:
        """
        Build action history for current node
        
        Uses the new action_history field (List[ActionRecord]) if available,
        falls back to output_data for backward compatibility.
        """
        lines = []
        indent_str = "  " * indent
        
        # First, try to use the new action_history field
        if node.action_history:
            return self._build_action_history_from_records(node, indent)
        
        # Fallback: check output_data for backward compatibility
        if not node.output_data:
            return lines
        
        # Check for action history in output_data (legacy format)
        actions = node.output_data.get("action_history", [])
        if not actions and node.output_data.get("action"):
            actions = [node.output_data["action"]]
        
        if actions:
            lines.append(f"{indent_str}- Actions Taken So Far:")
            shown_actions = actions[-self.MAX_ACTIONS_SHOWN:] if self.MAX_ACTIONS_SHOWN else actions
            for i, action in enumerate(shown_actions):
                lines.append(f"{indent_str}  - Step {i + 1}: {self._truncate_value(action, 80)}")
        
        return lines
    
    def _build_action_history_from_records(
        self,
        node: ExecutionNode,
        indent: int,
    ) -> List[str]:
        """
        Build action history from ActionRecord list
        
        Format (new with thinking):
        - [x] [Step 1] Increase title font
          - **Thinking**: Checked paragraph 1, font size is 20pt. Need to increase...
        - [-->] [Step 2] Verify change
        
        Format (legacy without thinking):
        - [x] [Step 1] Click login button
        """
        lines = []
        indent_str = "  " * indent
        
        # Limit to recent actions (None = show all)
        actions = node.action_history[-self.MAX_ACTIONS_SHOWN:] if self.MAX_ACTIONS_SHOWN else node.action_history
        
        for action in actions:
            status_mark = self._get_action_status_mark(action.status)
            summary = action.get_summary()
            
            if action.status == ActionStatus.RUNNING:
                lines.append(f"{indent_str}- {status_mark} **[Step {action.step}] {summary}**")
            elif action.status == ActionStatus.FAILED:
                lines.append(f"{indent_str}- {status_mark} [Step {action.step}] {summary} (FAILED)")
            else:
                lines.append(f"{indent_str}- {status_mark} [Step {action.step}] {summary}")
            
            # Show thinking for ALL steps (not just SUCCESS)
            # AI needs to see previous thinking to understand context and make decisions
            if action.thinking:
                lines.append(f"{indent_str}  - **Thinking**: {action.thinking}")
            
            # Show error message for failed steps (critical for AI to understand what went wrong)
            if action.error and action.status == ActionStatus.FAILED:
                # Truncate very long errors but keep enough context
                error_msg = action.error[:500] + "..." if len(action.error) > 500 else action.error
                lines.append(f"{indent_str}  - **Error**: {error_msg}")
            
            # Show result observation if available (helps AI understand execution result)
            if action.result_observation:
                lines.append(f"{indent_str}  - **Result**: {action.result_observation}")
            
            # Show step memory if available (AI's notebook for this step)
            if action.step_memory:
                lines.append(f"{indent_str}  <step_memory>{action.step_memory}</step_memory>")
        
        return lines
    
    def _get_action_status_mark(self, status: ActionStatus) -> str:
        """Get status marker for action"""
        if status == ActionStatus.SUCCESS:
            return "[x]"
        elif status == ActionStatus.RUNNING:
            return "[-->]"
        elif status == ActionStatus.FAILED:
            return "[!]"
        else:
            return "[ ]"
    
    def _build_recent_history(self) -> List[str]:
        """Build recent completed nodes history"""
        lines = []
        completed_nodes = []
        self._collect_completed_nodes(self.state.execution_tree, completed_nodes)
        
        # Only take recent N
        recent = completed_nodes[-self.max_history:]
        
        if recent:
            for node in recent:
                summary = node.history_summary or "Completed"
                lines.append(f"- {node.name}: {self._truncate_value(summary, 80)}")
        else:
            lines.append("- (No history yet)")
        
        return lines
    
    def _collect_completed_nodes(
        self,
        nodes: List[ExecutionNode],
        result: List[ExecutionNode],
    ):
        """Recursively collect completed nodes"""
        for node in nodes:
            if node.status == NodeStatus.SUCCESS:
                result.append(node)
            if node.children:
                self._collect_completed_nodes(node.children, result)
    
    def _get_status_mark(self, status: NodeStatus) -> str:
        """Get status marker for TODO list"""
        markers = {
            NodeStatus.SUCCESS: "[x]",
            NodeStatus.RUNNING: "[-->]",
            NodeStatus.FAILED: "[!]",
            NodeStatus.PENDING: "[ ]",
            NodeStatus.SKIPPED: "[-]",
        }
        return markers.get(status, "[ ]")
    
    def _truncate_value(self, value: Any, max_length: int = None) -> str:
        """Truncate long values"""
        max_len = max_length or self.MAX_VALUE_LENGTH
        str_value = str(value)
        if len(str_value) > max_len:
            return str_value[:max_len] + "..."
        return str_value
    
    def _format_pending_node(
        self,
        title: str,
        instruction: str,
        node_data: Dict[str, Any],
    ) -> str:
        """
        Format a pending node display text with instruction/description
        
        Args:
            title: Node title
            instruction: Node instruction (for computer-use nodes)
            node_data: Full node data dict
            
        Returns:
            Formatted display string
        """
        return self._format_node_with_instruction(title, instruction, node_data)
    
    def _format_running_node(
        self,
        title: str,
        instruction: str,
        node_data: Dict[str, Any],
    ) -> str:
        """
        Format a running (current) node display text with instruction/description
        
        Current node: show FULL instruction (no truncation).
        AI needs the complete context for the task it's working on.
        
        Args:
            title: Node title
            instruction: Node instruction (for computer-use nodes)
            node_data: Full node data dict
            
        Returns:
            Formatted display string
        """
        return self._format_node_with_instruction(title, instruction, node_data, truncate=False)
    
    def _format_completed_node(
        self,
        title: str,
        instruction: str,
        node_data: Dict[str, Any],
    ) -> str:
        """
        Format a completed node display text with instruction/description
        
        Completed node: TRUNCATE instruction to reduce token usage.
        Note: Summary (appended separately) is never truncated.
        
        Args:
            title: Node title
            instruction: Node instruction (for computer-use nodes)
            node_data: Full node data dict
            
        Returns:
            Formatted display string (instruction truncated, summary preserved)
        """
        return self._format_node_with_instruction(title, instruction, node_data, truncate=True)
    
    def _format_node_with_instruction(
        self,
        title: str,
        instruction: str,
        node_data: Dict[str, Any],
        truncate: bool = True,
    ) -> str:
        """
        Format a node display text with instruction/description
        
        Args:
            title: Node title
            instruction: Node instruction (for computer-use nodes)
            node_data: Full node data dict
            truncate: Whether to truncate long instruction (default True for completed/pending, False for running/current)
            
        Returns:
            Formatted display string
        """
        # Get additional info from node_data
        node_type = node_data.get("type", "")
        prompt = node_data.get("prompt", "")  # For tool-use, llm nodes
        description = node_data.get("description", "")
        
        # Determine what extra info to show
        extra_info = ""
        
        if instruction:
            # Computer-use nodes have instruction
            extra_info = instruction
        elif prompt:
            # Tool-use, LLM nodes have prompt
            extra_info = prompt
        elif description:
            # Some nodes have description
            extra_info = description
        
        # Format the output
        if extra_info:
            if truncate:
                display_info = self._truncate_value(extra_info, 100)
            else:
                display_info = extra_info
            return f"{title}: {display_info}"
        else:
            return title
    
    def _format_exec_node_name(self, exec_node: ExecutionNode, truncate: bool = True) -> str:
        """
        Format an ExecutionNode name with instruction if available
        
        For running nodes, tries to get instruction from:
        1. input_data.instruction
        2. graph_nodes (if available)
        
        Args:
            exec_node: The execution node
            truncate: Whether to truncate long instruction (False for running/current nodes)
            
        Returns:
            Formatted display string
        """
        title = exec_node.name
        instruction = ""
        node_data = {}
        
        # Try to get instruction from input_data
        if exec_node.input_data:
            instruction = exec_node.input_data.get("instruction", "") or exec_node.input_data.get("description", "")
            node_data = exec_node.input_data
        
        # If no instruction in input_data, try graph_nodes
        if not instruction and self.graph_nodes:
            node_def = self.graph_nodes.get(exec_node.node_def_id)
            if node_def:
                node_data = node_def.get("data", {})
                instruction = node_data.get("instruction", "") or node_data.get("description", "")
        
        return self._format_node_with_instruction(title, instruction, node_data, truncate=truncate)
    
    def _get_task_tips(self, exec_node: ExecutionNode) -> str:
        """
        Get task_tips for an ExecutionNode
        
        Tries to get task_tips from:
        1. input_data.task_tips
        2. graph_nodes (if available)
        
        Args:
            exec_node: The execution node
            
        Returns:
            Task tips string or empty string
        """
        task_tips = ""
        
        # Try to get from input_data
        if exec_node.input_data:
            task_tips = exec_node.input_data.get("task_tips", "")
        
        # If not found, try graph_nodes
        if not task_tips and self.graph_nodes:
            node_def = self.graph_nodes.get(exec_node.node_def_id)
            if node_def:
                node_data = node_def.get("data", {})
                task_tips = node_data.get("task_tips", "")
        
        return task_tips


def generate_ai_markdown(
    state: WorkflowRuntimeState,
    include_variables: bool = True,
    include_history: bool = False,
) -> str:
    """
    Convenience function to generate AI Markdown
    
    Args:
        state: Workflow runtime state
        include_variables: Whether to include variables section
        include_history: Whether to include history section
        
    Returns:
        Formatted Markdown string
    """
    transformer = AIMarkdownTransformer(
        state,
        include_variables=include_variables,
        include_history=include_history,
    )
    return transformer.transform()
