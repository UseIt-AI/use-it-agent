from typing import Dict
from useit_studio.ai_run.node_handler.logic_nodes.base import BaseNodeHandler


class StartNodeHandler(BaseNodeHandler):
    """Handler for start node type"""
    
    def handle(self, current_node: Dict, current_state: Dict, **kwargs) -> Dict:
        """Handle start node processing"""
        node_id = self._get_node_id(current_node)
        node_title = self._get_node_title(current_node)
        
        self._log_info(f"Processing Start Node: {node_id} - {node_title}")
        
        return self.build_success_result({
            "Observation": f"",
            "Reasoning": "",
            "Action": "Starting point of the workflow.",
            "is_node_completed": True,
            "current_state": current_state,
            "node_completion_summary": "Started the workflow."
        }) 