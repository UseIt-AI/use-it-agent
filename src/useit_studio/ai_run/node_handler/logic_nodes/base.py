from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, TYPE_CHECKING


from useit_studio.ai_run.utils.logger_utils import LoggerUtils
from useit_studio.ai_run.agent_loop.workflow.graph_manager import GraphManager

if TYPE_CHECKING:
    from useit_studio.ai_run.node_handler.functional_nodes.computer_use.gui.planner.flowlogic_planner import FlowLogicPlanner


class BaseNodeHandler(ABC):
    """Abstract base class for all node handlers"""
    
    def __init__(
        self, 
        logger: LoggerUtils,
        graph_manager: GraphManager,
        workflow_id: str,
        logging_dir: str,
    ):
        self.logger = logger
        self.graph_manager = graph_manager
        self.workflow_id = workflow_id
        self.logging_dir = logging_dir
    
    @abstractmethod
    def handle(
        self, 
        planner: "FlowLogicPlanner",
        current_node: Dict,
        current_state: Dict,
        **kwargs
    ) -> Dict:
        """
        Handle the node processing logic
        
        Args:
            current_node: The current node data
            current_state: The current state of the procedure
            **kwargs: Additional arguments (screenshot_path, overall_task_query, etc.)
        """
        pass
    
    def _get_node_id(self, current_node: Dict) -> str:
        """Helper method to get node ID"""
        return current_node.get('id', 'unknown_node')
    
    def _get_node_title(self, current_node: Dict) -> str:
        """Helper method to get node title"""
        return current_node.get('title', current_node.get('data', {}).get('title', 'Untitled Node'))
    
    def _log_info(self, message: str):
        """Helper method for logging info messages"""
        self.logger.logger.info(f"[{self.__class__.__name__}] {message}")
    
    def _log_warning(self, message: str):
        """Helper method for logging warning messages"""
        self.logger.logger.warning(f"[{self.__class__.__name__}] {message}")
    
    def _log_error(self, message: str):
        """Helper method for logging error messages"""
        self.logger.logger.error(f"[{self.__class__.__name__}] {message}") 

    # --- Result helpers for consistent status/error fields ---
    def build_error_result(
        self,
        current_state: Dict,
        error_message: str,
        observation: str = "Error occurred during node handling",
        reasoning: Optional[str] = None,
        instruction: str = "",
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict:
        """
        Build a standardized error-shaped handler result.
        """
        result: Dict[str, Any] = {
            "Observation": observation,
            "Reasoning": reasoning or error_message,
            "Instruction": instruction,
            "is_node_completed": False,
            "current_state": current_state,
            "error": error_message,
            "error_message": error_message,
            "status": "error",
        }
        if extra:
            result.update(extra)
        return result

    def build_success_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure success status fields exist on a normal result."""
        result.setdefault("status", "success")
        result.setdefault("error_message", None)
        return result