"""
Base Controller for Local Engine Architecture
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List
import logging

from .models import ControllerResponse


logger = logging.getLogger(__name__)


class BaseController(ABC):
    """
    Abstract base class for all controllers.

    Each controller manages a specific domain (Excel, AutoCAD, Computer Use, etc.)
    and provides a set of actions that can be executed.
    """

    def __init__(self):
        """Initialize the controller"""
        self.name = self.__class__.__name__
        logger.info(f"Initializing controller: {self.name}")

    @abstractmethod
    def get_supported_actions(self) -> List[str]:
        """
        Return list of actions this controller supports.

        Returns:
            List of action names (e.g., ["get_snapshot", "execute_code"])
        """
        pass

    @abstractmethod
    async def handle_action(
        self, action: str, params: Dict[str, Any]
    ) -> ControllerResponse:
        """
        Handle an action request.

        Args:
            action: The action to perform
            params: Parameters for the action

        Returns:
            ControllerResponse with success status and data/error
        """
        pass

    async def initialize(self) -> None:
        """
        Optional initialization hook.
        Called when controller is registered.
        """
        logger.info(f"Controller {self.name} initialized")

    async def cleanup(self) -> None:
        """
        Optional cleanup hook.
        Called when shutting down.
        """
        logger.info(f"Controller {self.name} cleaned up")

    def validate_action(self, action: str) -> None:
        """
        Validate that an action is supported.

        Args:
            action: The action to validate

        Raises:
            ValueError: If action is not supported
        """
        supported = self.get_supported_actions()
        if action not in supported:
            raise ValueError(
                f"Action '{action}' not supported by {self.name}. "
                f"Supported actions: {supported}"
            )

    def validate_params(self, params: Dict[str, Any], required_keys: List[str]) -> None:
        """
        Validate that required parameters are present.

        Args:
            params: Parameters to validate
            required_keys: List of required parameter keys

        Raises:
            ValueError: If required parameters are missing
        """
        missing = [key for key in required_keys if key not in params]
        if missing:
            raise ValueError(
                f"Missing required parameters: {missing}. "
                f"Provided: {list(params.keys())}"
            )
