"""
Notification API 端点 - 应用通知监听

监听各种应用的通知状态，如微信新消息、QQ 消息等。

主要端点:
- GET  /api/v1/notification/status           获取所有监听器状态
- GET  /api/v1/notification/status/{type}    获取指定监听器状态
- POST /api/v1/notification/start            启动监听器
- POST /api/v1/notification/stop             停止监听器
- POST /api/v1/notification/stop_all         停止所有监听器
- GET  /api/v1/notification/events           获取通知事件
- POST /api/v1/notification/check            执行一次检查
- GET  /api/v1/notification/types            获取支持的监听器类型
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
import logging

from controllers.notification.controller import (
    NotificationController,
    get_notification_controller,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_controller() -> NotificationController:
    """获取 NotificationController 实例"""
    return get_notification_controller()


# ==================== 请求模型 ====================

class StartMonitorRequest(BaseModel):
    """启动监听器请求"""
    monitor_type: str = Field(..., description="监听器类型 (如 'wechat')")
    poll_interval: float = Field(
        default=0.5, 
        ge=0.1, 
        le=10.0,
        description="检查时的轮询间隔 (秒)，建议 0.3-0.5"
    )
    check_duration: float = Field(
        default=3.0,
        ge=1.0,
        le=30.0,
        description="每次检查的持续时间 (秒)，默认 3 秒"
    )
    check_interval: float = Field(
        default=60.0,
        ge=5.0,
        le=3600.0,
        description="两次检查之间的间隔 (秒)，默认 60 秒"
    )


class StopMonitorRequest(BaseModel):
    """停止监听器请求"""
    monitor_type: str = Field(..., description="监听器类型")


class CheckOnceRequest(BaseModel):
    """执行一次检查请求"""
    monitor_type: str = Field(..., description="监听器类型")


class GetEventsRequest(BaseModel):
    """获取事件请求"""
    monitor_type: Optional[str] = Field(
        default=None, 
        description="监听器类型，None 表示获取所有"
    )
    limit: int = Field(
        default=50, 
        ge=1, 
        le=500,
        description="最大返回数量"
    )


class ClearEventsRequest(BaseModel):
    """清空事件请求"""
    monitor_type: Optional[str] = Field(
        default=None,
        description="监听器类型，None 表示清空所有"
    )


# ==================== API 端点 ====================

@router.get("/types")
async def get_available_types() -> Dict[str, Any]:
    """
    获取支持的监听器类型列表
    
    Returns:
        {
            "success": true,
            "data": {
                "types": ["wechat", ...]
            }
        }
    """
    controller = _get_controller()
    return {
        "success": True,
        "data": {
            "types": controller.get_available_monitors(),
        }
    }


@router.get("/status")
async def get_all_status() -> Dict[str, Any]:
    """
    获取所有监听器的状态
    
    Returns:
        {
            "success": true,
            "data": {
                "available_types": ["wechat", ...],
                "active_monitors": ["wechat"],
                "statuses": {
                    "wechat": {...}
                }
            }
        }
    """
    controller = _get_controller()
    result = controller.get_all_status()
    return {
        "success": result["success"],
        "data": result,
    }


@router.get("/status/{monitor_type}")
async def get_monitor_status(monitor_type: str) -> Dict[str, Any]:
    """
    获取指定监听器的状态
    
    Args:
        monitor_type: 监听器类型 (如 "wechat")
        
    Returns:
        {
            "success": true,
            "data": {
                "name": "wechat",
                "status": "running",
                "is_flashing": false,
                ...
            }
        }
    """
    controller = _get_controller()
    result = controller.get_monitor_status(monitor_type)
    
    if not result["success"]:
        raise HTTPException(status_code=404, detail=result.get("error"))
    
    return {
        "success": True,
        "data": result["status"],
    }


@router.post("/start")
async def start_monitor(request: StartMonitorRequest) -> Dict[str, Any]:
    """
    启动监听器
    
    Args:
        request: 启动请求，包含监听器类型和轮询间隔
        
    Returns:
        {
            "success": true,
            "data": {
                "message": "wechat monitor started",
                "status": {...}
            }
        }
        
    Note:
        - WeChat 监听需要管理员权限
        - 微信图标需要在任务栏可见区域（不能在折叠菜单里）
    """
    controller = _get_controller()
    result = await controller.start_monitor(
        monitor_type=request.monitor_type,
        poll_interval=request.poll_interval,
        check_duration=request.check_duration,
        check_interval=request.check_interval,
    )
    
    return {
        "success": result["success"],
        "data": result,
    }


@router.post("/stop")
async def stop_monitor(request: StopMonitorRequest) -> Dict[str, Any]:
    """
    停止监听器
    
    Args:
        request: 停止请求，包含监听器类型
        
    Returns:
        {
            "success": true,
            "data": {
                "message": "wechat monitor stopped",
                "status": {...}
            }
        }
    """
    controller = _get_controller()
    result = await controller.stop_monitor(request.monitor_type)
    
    if not result["success"]:
        raise HTTPException(status_code=404, detail=result.get("error"))
    
    return {
        "success": True,
        "data": result,
    }


@router.post("/stop_all")
async def stop_all_monitors() -> Dict[str, Any]:
    """
    停止所有监听器
    
    Returns:
        {
            "success": true,
            "data": {
                "message": "All monitors stopped",
                "results": {...}
            }
        }
    """
    controller = _get_controller()
    result = await controller.stop_all()
    
    return {
        "success": True,
        "data": result,
    }


@router.get("/events")
async def get_events(
    monitor_type: Optional[str] = None,
    limit: int = 50
) -> Dict[str, Any]:
    """
    获取通知事件列表
    
    Args:
        monitor_type: 监听器类型，None 表示获取所有
        limit: 最大返回数量
        
    Returns:
        {
            "success": true,
            "data": {
                "events": [
                    {
                        "source": "wechat",
                        "event_type": "new_message",
                        "timestamp": "2024-01-01T12:00:00",
                        "message": "WeChat has new message"
                    }
                ],
                "total": 1
            }
        }
    """
    controller = _get_controller()
    result = controller.get_events(monitor_type=monitor_type, limit=limit)
    
    if not result["success"]:
        raise HTTPException(status_code=404, detail=result.get("error"))
    
    return {
        "success": True,
        "data": result,
    }


@router.post("/events/clear")
async def clear_events(request: ClearEventsRequest) -> Dict[str, Any]:
    """
    清空事件历史
    
    Args:
        request: 清空请求，包含监听器类型
        
    Returns:
        {
            "success": true,
            "data": {
                "message": "Events cleared"
            }
        }
    """
    controller = _get_controller()
    result = controller.clear_events(request.monitor_type)
    
    if not result["success"]:
        raise HTTPException(status_code=404, detail=result.get("error"))
    
    return {
        "success": True,
        "data": result,
    }


@router.post("/check")
async def check_once(request: CheckOnceRequest) -> Dict[str, Any]:
    """
    执行一次检查（不启动持续监听）
    
    适用于只想检查一次当前状态的场景。
    
    Args:
        request: 检查请求，包含监听器类型
        
    Returns:
        {
            "success": true,
            "data": {
                "available": true,
                "event": {...} or null,
                "status": {...}
            }
        }
    """
    controller = _get_controller()
    result = await controller.check_once(request.monitor_type)
    
    return {
        "success": result["success"],
        "data": result,
    }


# ==================== WebSocket 端点（可选，用于实时推送） ====================

# 如果需要实时推送事件，可以添加 WebSocket 支持
# from fastapi import WebSocket, WebSocketDisconnect
# 
# @router.websocket("/ws")
# async def websocket_endpoint(websocket: WebSocket):
#     """WebSocket 端点，用于实时接收通知事件"""
#     await websocket.accept()
#     
#     controller = _get_controller()
#     
#     async def event_callback(event):
#         await websocket.send_json(event.to_dict())
#     
#     controller.add_global_callback(event_callback)
#     
#     try:
#         while True:
#             # 保持连接
#             await websocket.receive_text()
#     except WebSocketDisconnect:
#         controller.remove_global_callback(event_callback)
