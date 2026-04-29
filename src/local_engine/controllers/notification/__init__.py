"""
Notification 监听控制器

支持监听各种应用的通知状态，包括：
- WeChat (微信) 托盘图标闪烁检测
- 更多应用待扩展...
"""

from .controller import NotificationController

__all__ = ["NotificationController"]
