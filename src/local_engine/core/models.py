"""
Data models for Local Engine Controller Architecture
"""

from typing import Any, Dict, Optional
from pydantic import BaseModel


class ExecuteRequest(BaseModel):
    """Request model for controller action execution"""

    action: str
    params: Dict[str, Any] = {}
    timeout: Optional[int] = 60  # seconds


class ControllerResponse(BaseModel):
    """Response model for controller action execution"""

    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    message: Optional[str] = None

    @classmethod
    def success_response(cls, data: Dict[str, Any], message: Optional[str] = None):
        """Create a success response"""
        return cls(success=True, data=data, message=message)

    @classmethod
    def error_response(cls, error: str, message: Optional[str] = None):
        """Create an error response"""
        return cls(success=False, error=error, message=message)
