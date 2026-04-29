"""
System controller - 机器环境感知

提供给 AI Agent 查询本机环境的只读端点（加一个 launch）:
- ProcessHandler:  运行中的进程
- WindowHandler:   打开的顶级窗口（AI 感知"用户开了哪些 ppt/word/..."的主力）
- SoftwareHandler: 已安装软件（注册表 HKLM + HKCU + App Paths）
- Launcher:        启动 exe / 按 AppUserModelID 启动
"""

from .process_handler import ProcessHandler
from .window_handler import WindowHandler as SystemWindowHandler
from .software_handler import SoftwareHandler
from .launcher import Launcher

__all__ = [
    "ProcessHandler",
    "SystemWindowHandler",
    "SoftwareHandler",
    "Launcher",
]
