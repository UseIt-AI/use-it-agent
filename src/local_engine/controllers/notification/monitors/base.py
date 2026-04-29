"""
Base Monitor 抽象类

定义所有通知监听器的基础接口
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class MonitorStatus(str, Enum):
    """监听器状态"""
    STOPPED = "stopped"
    RUNNING = "running"
    ERROR = "error"
    NOT_FOUND = "not_found"  # 目标应用未找到


@dataclass
class NotificationEvent:
    """通知事件"""
    source: str  # 来源应用名称 (如 "wechat", "qq", "dingtalk")
    event_type: str  # 事件类型 (如 "new_message", "state_change")
    timestamp: datetime = field(default_factory=datetime.now)
    data: Dict[str, Any] = field(default_factory=dict)
    message: str = ""  # 人类可读的消息描述
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
            "message": self.message,
        }


class BaseMonitor(ABC):
    """
    通知监听器基类
    
    所有具体的监听器实现都应该继承此类
    """
    
    def __init__(self, name: str, poll_interval: float = 0.5):
        """
        初始化监听器
        
        Args:
            name: 监听器名称 (如 "wechat", "qq")
            poll_interval: 轮询间隔 (秒)
        """
        self.name = name
        self.poll_interval = poll_interval
        self._status = MonitorStatus.STOPPED
        self._task: Optional[asyncio.Task] = None
        self._callbacks: List[Callable[[NotificationEvent], None]] = []
        self._events: List[NotificationEvent] = []
        self._max_events = 100  # 最多保留的事件数量
        self._last_error: Optional[str] = None
        
    @property
    def status(self) -> MonitorStatus:
        return self._status
    
    @property
    def last_error(self) -> Optional[str]:
        return self._last_error
    
    @property
    def events(self) -> List[NotificationEvent]:
        """获取最近的事件列表"""
        return self._events.copy()
    
    def add_callback(self, callback: Callable[[NotificationEvent], None]) -> None:
        """添加事件回调"""
        self._callbacks.append(callback)
        
    def remove_callback(self, callback: Callable[[NotificationEvent], None]) -> None:
        """移除事件回调"""
        if callback in self._callbacks:
            self._callbacks.remove(callback)
    
    def _emit_event(self, event: NotificationEvent) -> None:
        """触发事件"""
        # 保存事件
        self._events.append(event)
        if len(self._events) > self._max_events:
            self._events = self._events[-self._max_events:]
        
        # 调用所有回调
        for callback in self._callbacks:
            try:
                callback(event)
            except Exception as e:
                logger.error(f"[{self.name}] Callback error: {e}")
    
    @abstractmethod
    async def check_available(self) -> bool:
        """
        检查目标应用是否可用（如是否在运行、图标是否可见等）
        
        Returns:
            bool: 是否可用
        """
        pass
    
    @abstractmethod
    async def poll_once(self) -> Optional[NotificationEvent]:
        """
        执行一次轮询检查
        
        Returns:
            NotificationEvent: 如果检测到新事件则返回，否则返回 None
        """
        pass
    
    async def _monitor_loop(self) -> None:
        """监听循环"""
        logger.info(f"[{self.name}] Monitor loop started")
        
        while self._status == MonitorStatus.RUNNING:
            try:
                # 检查应用是否可用
                if not await self.check_available():
                    self._status = MonitorStatus.NOT_FOUND
                    self._last_error = f"{self.name} not found or not visible"
                    logger.warning(f"[{self.name}] {self._last_error}")
                    await asyncio.sleep(self.poll_interval * 2)  # 等待更长时间再重试
                    self._status = MonitorStatus.RUNNING  # 继续尝试
                    continue
                
                # 执行一次轮询
                event = await self.poll_once()
                if event:
                    self._emit_event(event)
                    logger.info(f"[{self.name}] Event: {event.message}")
                    
            except asyncio.CancelledError:
                logger.info(f"[{self.name}] Monitor loop cancelled")
                break
            except Exception as e:
                self._last_error = str(e)
                logger.error(f"[{self.name}] Monitor error: {e}")
                self._status = MonitorStatus.ERROR
                await asyncio.sleep(self.poll_interval * 2)
                self._status = MonitorStatus.RUNNING  # 尝试恢复
                
            await asyncio.sleep(self.poll_interval)
        
        logger.info(f"[{self.name}] Monitor loop stopped")
    
    async def start(self) -> bool:
        """
        启动监听
        
        Returns:
            bool: 是否成功启动
        """
        if self._status == MonitorStatus.RUNNING:
            logger.warning(f"[{self.name}] Already running")
            return True
        
        # 先检查是否可用
        if not await self.check_available():
            self._status = MonitorStatus.NOT_FOUND
            self._last_error = f"{self.name} not found or not visible"
            logger.warning(f"[{self.name}] {self._last_error}")
            # 仍然启动，会在循环中继续尝试
        
        self._status = MonitorStatus.RUNNING
        self._last_error = None
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info(f"[{self.name}] Monitor started")
        return True
    
    async def stop(self) -> None:
        """停止监听"""
        if self._status == MonitorStatus.STOPPED:
            return
            
        self._status = MonitorStatus.STOPPED
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
            
        logger.info(f"[{self.name}] Monitor stopped")
    
    def get_status_info(self) -> Dict[str, Any]:
        """获取监听器状态信息"""
        return {
            "name": self.name,
            "status": self._status.value,
            "poll_interval": self.poll_interval,
            "last_error": self._last_error,
            "event_count": len(self._events),
            "recent_events": [e.to_dict() for e in self._events[-5:]],
        }
    
    def clear_events(self) -> None:
        """清空事件历史"""
        self._events.clear()
