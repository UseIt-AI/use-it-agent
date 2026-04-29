"""
Notification Controller

统一管理各种应用的通知监听器
"""

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional, Type

from .monitors import BaseMonitor, MonitorStatus, NotificationEvent, WeChatTrayMonitor

logger = logging.getLogger(__name__)


# 注册可用的监听器类型
AVAILABLE_MONITORS: Dict[str, Type[BaseMonitor]] = {
    "wechat": WeChatTrayMonitor,
    # 后续可以添加更多监听器
    # "qq": QQTrayMonitor,
    # "dingtalk": DingTalkMonitor,
    # "teams": TeamsMonitor,
}


class NotificationController:
    """
    通知监听控制器
    
    管理多个应用的通知监听器，提供统一的接口来：
    - 启动/停止监听器
    - 获取监听状态
    - 获取通知事件
    - 注册事件回调
    """
    
    _instance: Optional["NotificationController"] = None
    
    def __new__(cls) -> "NotificationController":
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._monitors: Dict[str, BaseMonitor] = {}
        self._global_callbacks: List[Callable[[NotificationEvent], None]] = []
        self._initialized = True
        logger.info("NotificationController initialized")
    
    @classmethod
    def get_instance(cls) -> "NotificationController":
        """获取单例实例"""
        return cls()
    
    @classmethod
    def get_available_monitors(cls) -> List[str]:
        """获取可用的监听器类型列表"""
        return list(AVAILABLE_MONITORS.keys())
    
    def _create_monitor(self, monitor_type: str, **kwargs) -> Optional[BaseMonitor]:
        """
        创建监听器实例
        
        Args:
            monitor_type: 监听器类型 (如 "wechat")
            **kwargs: 传递给监听器的参数
            
        Returns:
            监听器实例，类型不支持时返回 None
        """
        monitor_class = AVAILABLE_MONITORS.get(monitor_type)
        if not monitor_class:
            logger.error(f"Unknown monitor type: {monitor_type}")
            return None
            
        try:
            monitor = monitor_class(**kwargs)
            
            # 添加全局回调
            for callback in self._global_callbacks:
                monitor.add_callback(callback)
                
            return monitor
        except Exception as e:
            logger.error(f"Failed to create monitor {monitor_type}: {e}")
            return None
    
    def add_global_callback(self, callback: Callable[[NotificationEvent], None]) -> None:
        """
        添加全局事件回调（会应用到所有监听器）
        
        Args:
            callback: 事件回调函数
        """
        self._global_callbacks.append(callback)
        # 添加到已有的监听器
        for monitor in self._monitors.values():
            monitor.add_callback(callback)
    
    def remove_global_callback(self, callback: Callable[[NotificationEvent], None]) -> None:
        """移除全局事件回调"""
        if callback in self._global_callbacks:
            self._global_callbacks.remove(callback)
            for monitor in self._monitors.values():
                monitor.remove_callback(callback)
    
    async def start_monitor(
        self, 
        monitor_type: str, 
        poll_interval: float = 0.5,
        **kwargs
    ) -> Dict[str, Any]:
        """
        启动指定类型的监听器
        
        Args:
            monitor_type: 监听器类型 (如 "wechat")
            poll_interval: 轮询间隔 (秒)
            **kwargs: 其他参数
            
        Returns:
            操作结果
        """
        if monitor_type in self._monitors:
            monitor = self._monitors[monitor_type]
            if monitor.status == MonitorStatus.RUNNING:
                return {
                    "success": True,
                    "message": f"{monitor_type} monitor already running",
                    "status": monitor.get_status_info(),
                }
        
        # 创建新的监听器
        monitor = self._create_monitor(
            monitor_type, 
            poll_interval=poll_interval,
            **kwargs
        )
        
        if not monitor:
            return {
                "success": False,
                "error": f"Unknown monitor type: {monitor_type}",
                "available_types": self.get_available_monitors(),
            }
        
        self._monitors[monitor_type] = monitor
        
        # 启动监听
        success = await monitor.start()
        
        return {
            "success": success,
            "message": f"{monitor_type} monitor started" if success else f"Failed to start {monitor_type} monitor",
            "status": monitor.get_status_info(),
        }
    
    async def stop_monitor(self, monitor_type: str) -> Dict[str, Any]:
        """
        停止指定类型的监听器
        
        Args:
            monitor_type: 监听器类型
            
        Returns:
            操作结果
        """
        if monitor_type not in self._monitors:
            return {
                "success": False,
                "error": f"Monitor {monitor_type} not found",
            }
        
        monitor = self._monitors[monitor_type]
        await monitor.stop()
        
        return {
            "success": True,
            "message": f"{monitor_type} monitor stopped",
            "status": monitor.get_status_info(),
        }
    
    async def stop_all(self) -> Dict[str, Any]:
        """停止所有监听器"""
        results = {}
        for monitor_type in list(self._monitors.keys()):
            result = await self.stop_monitor(monitor_type)
            results[monitor_type] = result
        
        return {
            "success": True,
            "message": "All monitors stopped",
            "results": results,
        }
    
    def get_monitor_status(self, monitor_type: str) -> Dict[str, Any]:
        """
        获取指定监听器的状态
        
        Args:
            monitor_type: 监听器类型
            
        Returns:
            状态信息
        """
        if monitor_type not in self._monitors:
            return {
                "success": False,
                "error": f"Monitor {monitor_type} not found or not started",
            }
        
        return {
            "success": True,
            "status": self._monitors[monitor_type].get_status_info(),
        }
    
    def get_all_status(self) -> Dict[str, Any]:
        """获取所有监听器的状态"""
        statuses = {}
        for monitor_type, monitor in self._monitors.items():
            statuses[monitor_type] = monitor.get_status_info()
        
        return {
            "success": True,
            "available_types": self.get_available_monitors(),
            "active_monitors": list(self._monitors.keys()),
            "statuses": statuses,
        }
    
    def get_events(
        self, 
        monitor_type: Optional[str] = None,
        limit: int = 50
    ) -> Dict[str, Any]:
        """
        获取通知事件
        
        Args:
            monitor_type: 监听器类型，None 表示获取所有
            limit: 最大返回数量
            
        Returns:
            事件列表
        """
        events = []
        
        if monitor_type:
            if monitor_type not in self._monitors:
                return {
                    "success": False,
                    "error": f"Monitor {monitor_type} not found",
                }
            events = [e.to_dict() for e in self._monitors[monitor_type].events]
        else:
            # 获取所有监听器的事件
            for monitor in self._monitors.values():
                events.extend([e.to_dict() for e in monitor.events])
            # 按时间排序
            events.sort(key=lambda x: x["timestamp"], reverse=True)
        
        return {
            "success": True,
            "events": events[:limit],
            "total": len(events),
        }
    
    def clear_events(self, monitor_type: Optional[str] = None) -> Dict[str, Any]:
        """
        清空事件历史
        
        Args:
            monitor_type: 监听器类型，None 表示清空所有
            
        Returns:
            操作结果
        """
        if monitor_type:
            if monitor_type not in self._monitors:
                return {
                    "success": False,
                    "error": f"Monitor {monitor_type} not found",
                }
            self._monitors[monitor_type].clear_events()
        else:
            for monitor in self._monitors.values():
                monitor.clear_events()
        
        return {
            "success": True,
            "message": "Events cleared",
        }
    
    async def check_once(self, monitor_type: str) -> Dict[str, Any]:
        """
        执行一次检查（不启动持续监听）
        
        Args:
            monitor_type: 监听器类型
            
        Returns:
            检查结果
        """
        # 临时创建监听器进行检查
        monitor = self._create_monitor(monitor_type)
        if not monitor:
            return {
                "success": False,
                "error": f"Unknown monitor type: {monitor_type}",
            }
        
        try:
            # 检查可用性
            available = await monitor.check_available()
            if not available:
                return {
                    "success": True,
                    "available": False,
                    "error": monitor.last_error,
                }
            
            # 执行一次轮询
            event = await monitor.poll_once()
            
            return {
                "success": True,
                "available": True,
                "event": event.to_dict() if event else None,
                "status": monitor.get_status_info(),
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }


# 全局实例（懒加载）
_controller: Optional[NotificationController] = None


def get_notification_controller() -> NotificationController:
    """获取 NotificationController 单例"""
    global _controller
    if _controller is None:
        _controller = NotificationController()
    return _controller
