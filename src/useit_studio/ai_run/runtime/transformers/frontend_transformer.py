"""
Frontend JSON Transformer

Generates full JSON structure for frontend rendering.

Design Goals:
- Complete: Include all execution data
- Real-time: Support incremental updates
- Structured: Enable tree rendering and status visualization

Output Format:
{
    "workflowId": "wf_001",
    "runId": "run_abc",
    "status": "running",
    "variables": {...},
    "executionTree": [...],
    "currentNodeId": "node_1"
}
"""

from typing import Dict, Any, List, Optional
from ..models import WorkflowRuntimeState, ExecutionNode, NodeStatus


class FrontendTransformer:
    """
    View B: Generate Frontend JSON Structure
    
    Goals: Complete, real-time, structured
    
    Strategies:
    1. Full state push (for initial load or reconnect)
    2. Diff/incremental updates (for real-time)
    3. Single node updates (for minimal push)
    
    Usage:
        transformer = FrontendTransformer(state)
        
        # Full state
        full_json = transformer.get_full_state()
        
        # Incremental update
        diff = transformer.get_diff()
        
        # Single node update
        update = transformer.get_node_update("node_1")
    """
    
    def __init__(self, state: WorkflowRuntimeState):
        """
        Initialize transformer
        
        Args:
            state: Workflow runtime state
        """
        self.state = state
        self._last_snapshot: Optional[Dict] = None
    
    def get_full_state(self) -> Dict[str, Any]:
        """
        Get complete state (for initial load or reconnect)
        
        Returns:
            Full state dictionary
        """
        return self.state.to_dict()
    
    def get_diff(self) -> Optional[Dict[str, Any]]:
        """
        Get state difference (for incremental updates)
        
        Returns:
            Changed parts of state, or None if no changes
        """
        current = self.state.to_dict()
        
        if self._last_snapshot is None:
            self._last_snapshot = current
            return None  # First call, no diff
        
        diff = self._compute_diff(self._last_snapshot, current)
        self._last_snapshot = current
        
        return diff if diff else None
    
    def get_node_update(self, node_id: str) -> Optional[Dict[str, Any]]:
        """
        Get single node update (minimal push)
        
        Args:
            node_id: Node ID to get update for
            
        Returns:
            Node update event payload
        """
        node = self.state.get_node(node_id)
        if not node:
            return None
        
        return {
            "type": "node_update",
            "payload": {
                "nodeId": node_id,
                "node": node.to_dict(),
            }
        }
    
    def get_status_update(self) -> Dict[str, Any]:
        """
        Get status change event (for WebSocket)
        
        Returns:
            Status update event payload
        """
        return {
            "type": "status_update",
            "payload": {
                "workflowId": self.state.workflow_id,
                "runId": self.state.run_id,
                "status": self.state.status,
                "currentNodeId": self.state.current_node_id,
            }
        }
    
    def get_variables_update(self) -> Dict[str, Any]:
        """
        Get variables change event
        
        Returns:
            Variables update event payload
        """
        return {
            "type": "variables_update",
            "payload": {
                "variables": self.state.variables,
            }
        }
    
    def get_progress_summary(self) -> Dict[str, Any]:
        """
        Get progress summary for dashboard
        
        Returns:
            Progress summary with counts
        """
        total_nodes = len(self.state.get_all_nodes())
        completed = len(self.state.get_nodes_by_status(NodeStatus.SUCCESS))
        failed = len(self.state.get_nodes_by_status(NodeStatus.FAILED))
        running = len(self.state.get_nodes_by_status(NodeStatus.RUNNING))
        pending = len(self.state.get_nodes_by_status(NodeStatus.PENDING))
        skipped = len(self.state.get_nodes_by_status(NodeStatus.SKIPPED))
        
        progress_pct = (completed / total_nodes * 100) if total_nodes > 0 else 0
        
        return {
            "type": "progress_summary",
            "payload": {
                "workflowId": self.state.workflow_id,
                "runId": self.state.run_id,
                "status": self.state.status,
                "totalNodes": total_nodes,
                "completedNodes": completed,
                "failedNodes": failed,
                "runningNodes": running,
                "pendingNodes": pending,
                "skippedNodes": skipped,
                "progressPercent": round(progress_pct, 1),
                "durationMs": self.state.get_duration_ms(),
            }
        }
    
    def get_execution_tree_flat(self) -> List[Dict[str, Any]]:
        """
        Get flattened execution tree (for list views)
        
        Returns:
            List of all nodes with parent references
        """
        nodes = []
        self._flatten_tree(self.state.execution_tree, nodes, parent_id=None)
        return nodes
    
    def get_node_path(self, node_id: str) -> List[str]:
        """
        Get path from root to specified node
        
        Args:
            node_id: Target node ID
            
        Returns:
            List of node IDs from root to target
        """
        path = []
        node = self.state.get_node(node_id)
        
        while node:
            path.insert(0, node.id)
            if node.parent_id:
                node = self.state.get_node(node.parent_id)
            else:
                break
        
        return path
    
    def _compute_diff(
        self,
        old: Dict[str, Any],
        new: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Compute difference between two states"""
        diff = {}
        
        # Check top-level field changes
        for key in ["status", "currentNodeId"]:
            if old.get(key) != new.get(key):
                diff[key] = new.get(key)
        
        # Check variables changes
        if old.get("variables") != new.get("variables"):
            diff["variables"] = new.get("variables")
        
        # Check execution tree changes
        old_nodes = self._flatten_tree_to_map(old.get("executionTree", []))
        new_nodes = self._flatten_tree_to_map(new.get("executionTree", []))
        
        # Find added nodes
        added = []
        for node_id in new_nodes:
            if node_id not in old_nodes:
                added.append(new_nodes[node_id])
        
        # Find changed nodes
        changed = []
        for node_id in new_nodes:
            if node_id in old_nodes and old_nodes[node_id] != new_nodes[node_id]:
                changed.append(new_nodes[node_id])
        
        # Find removed nodes
        removed = []
        for node_id in old_nodes:
            if node_id not in new_nodes:
                removed.append(node_id)
        
        if added:
            diff["addedNodes"] = added
        if changed:
            diff["changedNodes"] = changed
        if removed:
            diff["removedNodeIds"] = removed
        
        return diff
    
    def _flatten_tree(
        self,
        nodes: List[ExecutionNode],
        result: List[Dict[str, Any]],
        parent_id: Optional[str],
    ):
        """Flatten tree to list with parent references"""
        for node in nodes:
            node_dict = node.to_dict()
            node_dict["parentId"] = parent_id
            # Remove nested children from flattened view
            children = node_dict.pop("children", [])
            result.append(node_dict)
            
            # Recurse into children
            for child in node.children:
                self._flatten_tree([child], result, parent_id=node.id)
    
    def _flatten_tree_to_map(self, tree: List[Dict]) -> Dict[str, Dict]:
        """Flatten tree to {id: node} mapping"""
        result = {}
        
        def _traverse(nodes):
            for node in nodes:
                # Create a copy without children for comparison
                node_copy = {k: v for k, v in node.items() if k != "children"}
                result[node["id"]] = node_copy
                if "children" in node:
                    _traverse(node["children"])
        
        _traverse(tree)
        return result


class WebSocketEventBuilder:
    """
    Helper class to build WebSocket events
    
    Provides standardized event format for real-time updates.
    """
    
    @staticmethod
    def node_started(node: ExecutionNode) -> Dict[str, Any]:
        """Build node started event"""
        return {
            "type": "node_started",
            "timestamp": node.start_time,
            "payload": {
                "nodeId": node.id,
                "nodeDefId": node.node_def_id,
                "name": node.name,
                "nodeType": node.original_node_type,
            }
        }
    
    @staticmethod
    def node_completed(node: ExecutionNode) -> Dict[str, Any]:
        """Build node completed event"""
        return {
            "type": "node_completed",
            "timestamp": node.end_time,
            "payload": {
                "nodeId": node.id,
                "status": node.status.value,
                "summary": node.history_summary,
                "durationMs": node.get_duration_ms(),
            }
        }
    
    @staticmethod
    def node_failed(node: ExecutionNode, error: str) -> Dict[str, Any]:
        """Build node failed event"""
        return {
            "type": "node_failed",
            "timestamp": node.end_time,
            "payload": {
                "nodeId": node.id,
                "error": error,
            }
        }
    
    @staticmethod
    def workflow_completed(state: WorkflowRuntimeState) -> Dict[str, Any]:
        """Build workflow completed event"""
        return {
            "type": "workflow_completed",
            "timestamp": state.end_time,
            "payload": {
                "workflowId": state.workflow_id,
                "runId": state.run_id,
                "status": state.status,
                "durationMs": state.get_duration_ms(),
            }
        }
    
    @staticmethod
    def loop_iteration_started(
        loop_id: str,
        iteration: int,
    ) -> Dict[str, Any]:
        """Build loop iteration started event"""
        return {
            "type": "loop_iteration_started",
            "payload": {
                "loopId": loop_id,
                "iteration": iteration,
            }
        }
    
    @staticmethod
    def variable_updated(key: str, value: Any) -> Dict[str, Any]:
        """Build variable updated event"""
        return {
            "type": "variable_updated",
            "payload": {
                "key": key,
                "value": value,
            }
        }
