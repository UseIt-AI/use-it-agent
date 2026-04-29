"""
Browser Use 工具模块
"""

from .shortcut import (
    get_shortcuts_status,
    enable_remote_debugging,
    disable_remote_debugging,
    get_chrome_shortcut_paths,
    read_shortcut,
    write_shortcut,
)

from .monkey_patches import apply_patches

__all__ = [
    # 快捷方式工具
    "get_shortcuts_status",
    "enable_remote_debugging",
    "disable_remote_debugging",
    "get_chrome_shortcut_paths",
    "read_shortcut",
    "write_shortcut",
    # Monkey patches
    "apply_patches",
]
