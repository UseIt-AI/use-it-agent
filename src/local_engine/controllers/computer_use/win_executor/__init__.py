"""
Windows Executor - Windows 桌面自动化执行器

提供 Windows 平台的桌面自动化能力：
- 鼠标/键盘控制
- 屏幕截图
- 剪贴板操作
- 文件系统操作
- 窗口管理

注意：不要设置 DPI 感知！
保持 Windows 默认的 DPI 虚拟化，这样：
- pynput 使用逻辑坐标
- 屏幕 API 返回逻辑分辨率
- 截图自动缩放到逻辑分辨率
三者天然对齐，无需坐标转换。
"""

from .app import app, main
from .core.dependencies import PIL_AVAILABLE, PYNPUT_AVAILABLE, WINDOWS_API_AVAILABLE

__all__ = ['app', 'main', 'PIL_AVAILABLE', 'PYNPUT_AVAILABLE', 'WINDOWS_API_AVAILABLE']
