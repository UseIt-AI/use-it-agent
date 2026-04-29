"""
AI Run 统一事件系统

提供统一的事件格式、事件转换和事件流管理功能。
"""

from .schemas import (
    BaseStreamEvent,
    TextEvent,
    ClientRequestEvent,
    CUAStartEvent,
    CUADeltaEvent,
    CUAUpdateEvent,
    CUARequestEvent,
    CUAEndEvent,
    ErrorEvent,
    WorkflowCompleteEvent,
    NodeStartEvent,
    NodeEndEvent,
    InternalNodeEvent,
)

from .adapter import EventAdapter
from .manager import StreamEventManager

__all__ = [
    # Schemas
    "BaseStreamEvent",
    "TextEvent",
    "ClientRequestEvent",
    "CUAStartEvent",
    "CUADeltaEvent",
    "CUAUpdateEvent",
    "CUARequestEvent",
    "CUAEndEvent",
    "ErrorEvent",
    "WorkflowCompleteEvent",
    "NodeStartEvent",
    "NodeEndEvent",
    "InternalNodeEvent",
    # Core components
    "EventAdapter",
    "StreamEventManager",
]
