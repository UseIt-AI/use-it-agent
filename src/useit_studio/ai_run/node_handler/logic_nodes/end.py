from typing import Dict
from useit_studio.ai_run.node_handler.logic_nodes.base import BaseNodeHandler


class EndNodeHandler(BaseNodeHandler):
    """Handler for end node type"""
    
    def handle(self, current_node: Dict, current_state: Dict, **kwargs) -> Dict:
        """Handle end node processing"""
        node_id = self._get_node_id(current_node)
        node_title = self._get_node_title(current_node)
        
        self._log_info(f"Processing End Node: {node_id} - {node_title}")
        
        return self.build_success_result({
            "Observation": f"Reached end node {node_id}. Flow complete.",
            "Reasoning": "This is a terminal point in the process.",
            "Action": "Process finished.",
            "is_node_completed": True,
            "is_workflow_completed": True,  # End node means workflow is complete
            "next_node_id": None,  # Explicitly no next node
            "current_state": current_state,
            "node_completion_summary": "Reached the end of the workflow."
        }) 