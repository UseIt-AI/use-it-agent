"""
`useit_ai_run.node_handler` package

V2 architecture: BaseNodeHandlerV2 with unified async execute() interface.
Handlers are registered via NodeHandlerRegistry.
"""

from .base_v2 import BaseNodeHandlerV2, NodeContext, SCREENSHOT_NOT_REQUIRED_TYPES
from .registry import NodeHandlerRegistry

__all__ = [
    "BaseNodeHandlerV2",
    "NodeContext",
    "NodeHandlerRegistry",
    "SCREENSHOT_NOT_REQUIRED_TYPES",
]
