"""
API v1 - 统一的 RESTful API

端点格式: /api/v1/{controller}/{action}
"""

from .router import router

__all__ = ["router"]
