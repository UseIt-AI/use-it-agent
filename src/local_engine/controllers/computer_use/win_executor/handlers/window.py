"""
窗口操作处理器（Windows API）
"""
import logging
from typing import Dict, Any

from ..core.dependencies import (
    WINDOWS_API_AVAILABLE,
    win32gui
)

logger = logging.getLogger(__name__)


class WindowHandler:
    """窗口操作处理器"""
    
    @staticmethod
    def get_accessibility_tree() -> Dict[str, Any]:
        """获取前台窗口的可访问性树"""
        if not WINDOWS_API_AVAILABLE:
            return {"success": False, "error": "Windows API not available"}
        
        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return {"success": False, "error": "No foreground window found"}
            
            window_text = win32gui.GetWindowText(hwnd)
            rect = win32gui.GetWindowRect(hwnd)
            
            tree = {
                "role": "Window",
                "title": window_text,
                "position": {"x": rect[0], "y": rect[1]},
                "size": {"width": rect[2] - rect[0], "height": rect[3] - rect[1]},
                "children": []
            }
            
            def enum_child_proc(hwnd_child, children_list):
                try:
                    child_text = win32gui.GetWindowText(hwnd_child)
                    child_rect = win32gui.GetWindowRect(hwnd_child)
                    child_class = win32gui.GetClassName(hwnd_child)
                    child_info = {
                        "role": child_class,
                        "title": child_text,
                        "position": {"x": child_rect[0], "y": child_rect[1]},
                        "size": {
                            "width": child_rect[2] - child_rect[0],
                            "height": child_rect[3] - child_rect[1]
                        }
                    }
                    children_list.append(child_info)
                except:
                    pass
                return True
            
            win32gui.EnumChildWindows(hwnd, enum_child_proc, tree["children"])
            return {"success": True, "tree": tree}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def find_element(title: str) -> Dict[str, Any]:
        """按标题查找窗口"""
        if not WINDOWS_API_AVAILABLE:
            return {"success": False, "error": "Windows API not available"}
        
        if not title:
            return {"success": False, "error": "title required"}
        
        hwnd = win32gui.FindWindow(None, title)
        if hwnd:
            rect = win32gui.GetWindowRect(hwnd)
            return {
                "success": True,
                "element": {
                    "role": "Window",
                    "title": title,
                    "position": {"x": rect[0], "y": rect[1]},
                    "size": {"width": rect[2] - rect[0], "height": rect[3] - rect[1]}
                }
            }
        return {"success": False, "error": "Element not found"}


