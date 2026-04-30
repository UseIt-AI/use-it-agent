"""
Node Output Protocol

Defines the standardized output structure that every node handler
should return after execution.

This protocol enables:
1. Consistent state updates across all node types
2. Backward compatibility with existing handler_result format
3. Clear separation of concerns (full data vs summary vs variables)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Literal


@dataclass
class NodeOutputProtocol:
    """
    Standardized Node Output Protocol
    
    Every worker node must return this structure after execution.
    
    Attributes:
        node_id: ID of the executed node
        status: Execution status (success/failed/pending)
        output_data: Full output data (for storage and frontend details)
        update_variables: Variables to update in global blackboard
        history_summary: One-line summary for AI context (must be concise!)
        next_path_selection: Selected path (for logic nodes)
        break_loop: Whether to break the loop (for loop-end nodes)
        chosen_branch_id: Selected branch ID (for if-else nodes)
        token_usage: Token usage statistics
        error_message: Error message if failed
        action_summary: Short action description for progress tracking
    """
    node_id: str
    status: Literal["success", "failed", "pending"] = "success"
    
    # 1. Full data (for storage and frontend details)
    output_data: Optional[Dict[str, Any]] = None
    
    # 2. Variables to update in global blackboard
    update_variables: Optional[Dict[str, Any]] = None
    
    # 3. History summary (CRITICAL: must be concise!)
    history_summary: Optional[str] = None
    
    # 4. Flow control fields
    next_path_selection: Optional[str] = None       # For logic nodes
    break_loop: Optional[bool] = None               # For loop-end
    chosen_branch_id: Optional[str] = None          # For if-else
    next_node_id: Optional[str] = None              # Explicit next node
    
    # 5. Token usage
    token_usage: Optional[Dict[str, Any]] = None
    
    # 6. Error information
    error_message: Optional[str] = None
    
    # 7. Action summary (for progress tracking)
    action_summary: Optional[str] = None
    
    # 8. Node completion flag
    is_node_completed: bool = True
    
    @classmethod
    def from_handler_result(cls, handler_result: Dict[str, Any]) -> "NodeOutputProtocol":
        """
        Convert from existing handler_result format
        
        This provides backward compatibility with the current handler
        return format, allowing gradual migration.
        
        Args:
            handler_result: Dictionary returned by node handlers
            
        Returns:
            NodeOutputProtocol instance
        """
        # Determine status
        status = "success"
        if handler_result.get("status") == "error" or handler_result.get("error"):
            status = "failed"
        elif not handler_result.get("is_node_completed", True):
            status = "pending"
        
        # Extract output data
        output_data = {
            "observation": handler_result.get("Observation"),
            "reasoning": handler_result.get("Reasoning"),
            "action": handler_result.get("Action") or handler_result.get("Instruction"),
        }
        
        # Extract variables from current_state
        update_variables = handler_result.get("current_state", {})
        
        # Extract history summary
        history_summary = handler_result.get("node_completion_summary")
        if not history_summary:
            # Fallback: use observation or action as summary
            history_summary = handler_result.get("Observation") or handler_result.get("Action")
        
        # Extract action summary for progress
        action_summary = handler_result.get("action_summary")
        if not action_summary:
            action_summary = handler_result.get("Instruction") or handler_result.get("Action")
        
        return cls(
            node_id=handler_result.get("processed_node_id", ""),
            status=status,
            output_data=output_data,
            update_variables=update_variables,
            history_summary=history_summary,
            next_path_selection=handler_result.get("next_node_id"),
            break_loop=handler_result.get("break_loop"),
            chosen_branch_id=handler_result.get("chosen_branch_id"),
            next_node_id=handler_result.get("next_node_id"),
            token_usage=handler_result.get("token_usage"),
            error_message=handler_result.get("error_message") or handler_result.get("error"),
            action_summary=action_summary,
            is_node_completed=handler_result.get("is_node_completed", True),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format"""
        return {
            "node_id": self.node_id,
            "status": self.status,
            "output_data": self.output_data,
            "update_variables": self.update_variables,
            "history_summary": self.history_summary,
            "next_path_selection": self.next_path_selection,
            "break_loop": self.break_loop,
            "chosen_branch_id": self.chosen_branch_id,
            "next_node_id": self.next_node_id,
            "token_usage": self.token_usage,
            "error_message": self.error_message,
            "action_summary": self.action_summary,
            "is_node_completed": self.is_node_completed,
        }
    
    def to_handler_result(self) -> Dict[str, Any]:
        """
        Convert back to handler_result format
        
        Useful for backward compatibility when integrating
        with existing code that expects handler_result.
        """
        result = {
            "processed_node_id": self.node_id,
            "status": "error" if self.status == "failed" else "success",
            "is_node_completed": self.is_node_completed,
            "node_completion_summary": self.history_summary,
            "current_state": self.update_variables or {},
        }
        
        if self.output_data:
            result["Observation"] = self.output_data.get("observation")
            result["Reasoning"] = self.output_data.get("reasoning")
            result["Action"] = self.output_data.get("action")
            result["Instruction"] = self.output_data.get("action")
        
        if self.break_loop is not None:
            result["break_loop"] = self.break_loop
        
        if self.chosen_branch_id:
            result["chosen_branch_id"] = self.chosen_branch_id
        
        if self.next_node_id:
            result["next_node_id"] = self.next_node_id
        
        if self.token_usage:
            result["token_usage"] = self.token_usage
        
        if self.error_message:
            result["error"] = self.error_message
            result["error_message"] = self.error_message
        
        return result
    
    def is_success(self) -> bool:
        """Check if execution was successful"""
        return self.status == "success"
    
    def is_failed(self) -> bool:
        """Check if execution failed"""
        return self.status == "failed"
    
    def has_variables(self) -> bool:
        """Check if there are variables to update"""
        return bool(self.update_variables)


def create_success_output(
    node_id: str,
    history_summary: str,
    output_data: Optional[Dict[str, Any]] = None,
    update_variables: Optional[Dict[str, Any]] = None,
    token_usage: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> NodeOutputProtocol:
    """
    Helper function to create a successful node output
    
    Args:
        node_id: Node ID
        history_summary: Concise summary for AI context
        output_data: Full output data
        update_variables: Variables to update
        token_usage: Token usage stats
        **kwargs: Additional fields
        
    Returns:
        NodeOutputProtocol with success status
    """
    return NodeOutputProtocol(
        node_id=node_id,
        status="success",
        history_summary=history_summary,
        output_data=output_data,
        update_variables=update_variables,
        token_usage=token_usage,
        is_node_completed=True,
        **kwargs,
    )


def create_error_output(
    node_id: str,
    error_message: str,
    output_data: Optional[Dict[str, Any]] = None,
) -> NodeOutputProtocol:
    """
    Helper function to create a failed node output
    
    Args:
        node_id: Node ID
        error_message: Error description
        output_data: Partial output data if any
        
    Returns:
        NodeOutputProtocol with failed status
    """
    return NodeOutputProtocol(
        node_id=node_id,
        status="failed",
        error_message=error_message,
        history_summary=f"Failed: {error_message}",
        output_data=output_data,
        is_node_completed=True,
    )
