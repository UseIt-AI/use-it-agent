"""
Controller Registry for managing all controllers
"""

from typing import Dict, Optional, List
import logging

from .base import BaseController


logger = logging.getLogger(__name__)


class ControllerRegistry:
    """
    Singleton registry for managing all controllers.

    Responsibilities:
    - Register/unregister controllers
    - Lookup controllers by name
    - Initialize and cleanup all controllers
    """

    _instance: Optional["ControllerRegistry"] = None
    _controllers: Dict[str, BaseController] = {}

    def __new__(cls):
        """Ensure singleton instance"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._controllers = {}
        return cls._instance

    def register(self, name: str, controller: BaseController) -> None:
        """
        Register a controller.

        Args:
            name: Controller name (e.g., "excel", "autocad")
            controller: Controller instance

        Raises:
            ValueError: If controller name already registered
        """
        if name in self._controllers:
            raise ValueError(f"Controller '{name}' already registered")

        if not isinstance(controller, BaseController):
            raise TypeError(
                f"Controller must inherit from BaseController, got {type(controller)}"
            )

        self._controllers[name] = controller
        logger.info(f"Registered controller: {name} ({controller.__class__.__name__})")

    def unregister(self, name: str) -> None:
        """
        Unregister a controller.

        Args:
            name: Controller name to unregister
        """
        if name in self._controllers:
            del self._controllers[name]
            logger.info(f"Unregistered controller: {name}")

    def get(self, name: str) -> Optional[BaseController]:
        """
        Get a controller by name.

        Args:
            name: Controller name

        Returns:
            Controller instance or None if not found
        """
        return self._controllers.get(name)

    def get_all(self) -> Dict[str, BaseController]:
        """
        Get all registered controllers.

        Returns:
            Dictionary of controller name -> controller instance
        """
        return self._controllers.copy()

    def list_controllers(self) -> List[str]:
        """
        List all registered controller names.

        Returns:
            List of controller names
        """
        return list(self._controllers.keys())

    async def initialize_all(self) -> None:
        """Initialize all registered controllers"""
        logger.info(f"Initializing {len(self._controllers)} controllers...")
        for name, controller in self._controllers.items():
            try:
                await controller.initialize()
                logger.info(f"[OK] Initialized: {name}")
            except Exception as e:
                logger.error(f"[X] Failed to initialize {name}: {e}")

    async def cleanup_all(self) -> None:
        """Cleanup all registered controllers"""
        logger.info(f"Cleaning up {len(self._controllers)} controllers...")
        for name, controller in self._controllers.items():
            try:
                await controller.cleanup()
                logger.info(f"[OK] Cleaned up: {name}")
            except Exception as e:
                logger.error(f"[X] Failed to cleanup {name}: {e}")


# Global singleton instance
controller_registry = ControllerRegistry()
