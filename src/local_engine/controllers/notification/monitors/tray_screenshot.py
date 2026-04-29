"""
托盘图标截图检测模块

通过截取托盘图标区域的图片，对比变化来检测闪烁。
不需要管理员权限，适用于任何托盘图标。
"""

import hashlib
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class IconRect:
    """图标矩形区域"""
    left: int
    top: int
    right: int
    bottom: int
    
    @property
    def width(self) -> int:
        return self.right - self.left
    
    @property
    def height(self) -> int:
        return self.bottom - self.top
    
    def to_tuple(self) -> Tuple[int, int, int, int]:
        return (self.left, self.top, self.right, self.bottom)


class TrayIconScreenshot:
    """
    托盘图标截图检测器
    
    通过截图对比检测图标是否在闪烁
    """
    
    def __init__(self, history_size: int = 4):
        """
        初始化
        
        Args:
            history_size: 保留的历史截图哈希数量
        """
        self._history_size = history_size
        self._hash_history: List[str] = []
        self._mss = None
        self._pil = None
        self._uiautomation = None
        self._imports_ready = False
    
    def _import_modules(self) -> bool:
        """延迟导入模块"""
        if self._imports_ready:
            return True
        
        try:
            import mss
            from PIL import Image
            import uiautomation as auto
            
            self._mss = mss
            self._pil = Image
            self._uiautomation = auto
            self._imports_ready = True
            return True
        except ImportError as e:
            logger.error(f"Failed to import modules: {e}")
            return False
    
    def find_tray_icon_rect(self, name_contains: str) -> Optional[IconRect]:
        """
        通过 UI Automation 查找托盘图标的位置
        
        Args:
            name_contains: 图标名称包含的文字（如 "微信"、"QQ"）
            
        Returns:
            图标的矩形区域，未找到返回 None
        """
        if not self._import_modules():
            return None
        
        auto = self._uiautomation
        
        try:
            # 在线程中使用 uiautomation 需要初始化 COM
            # 使用 UIAutomationInitializerInThread 上下文管理器
            with auto.UIAutomationInitializerInThread():
                # 查找主托盘区域
                taskbar = auto.PaneControl(ClassName="Shell_TrayWnd")
                if not taskbar.Exists(0, 0):
                    return None
                
                tray_notify = taskbar.PaneControl(ClassName="TrayNotifyWnd")
                if not tray_notify.Exists(0, 0):
                    return None
                
                sys_pager = tray_notify.PaneControl(ClassName="SysPager")
                if not sys_pager.Exists(0, 0):
                    return None
                
                toolbar = sys_pager.ToolBarControl(ClassName="ToolbarWindow32")
                if toolbar.Exists(0, 0):
                    for item in toolbar.GetChildren():
                        try:
                            name = item.Name or ""
                            if name_contains.lower() in name.lower():
                                rect = item.BoundingRectangle
                                return IconRect(
                                    left=rect.left,
                                    top=rect.top,
                                    right=rect.right,
                                    bottom=rect.bottom
                                )
                        except Exception:
                            continue
                
                # 查找溢出区域
                overflow = auto.PaneControl(ClassName="NotifyIconOverflowWindow")
                if overflow.Exists(0, 0):
                    overflow_toolbar = overflow.ToolBarControl(ClassName="ToolbarWindow32")
                    if overflow_toolbar.Exists(0, 0):
                        for item in overflow_toolbar.GetChildren():
                            try:
                                name = item.Name or ""
                                if name_contains.lower() in name.lower():
                                    rect = item.BoundingRectangle
                                    return IconRect(
                                        left=rect.left,
                                        top=rect.top,
                                        right=rect.right,
                                        bottom=rect.bottom
                                    )
                            except Exception:
                                continue
                
                return None
            
        except Exception as e:
            logger.debug(f"Failed to find tray icon: {e}")
            return None
    
    def capture_icon(self, rect: IconRect) -> Optional[bytes]:
        """
        截取指定区域的图片
        
        Args:
            rect: 截取区域
            
        Returns:
            PNG 格式的图片数据，失败返回 None
        """
        if not self._import_modules():
            logger.debug("Modules not imported")
            return None
        
        try:
            import io
            with self._mss.mss() as sct:
                monitor = {
                    "left": rect.left,
                    "top": rect.top,
                    "width": rect.width,
                    "height": rect.height,
                }
                screenshot = sct.grab(monitor)
                
                # 转换为 PIL Image
                # self._pil 是 PIL.Image 模块
                img = self._pil.frombytes(
                    "RGB",
                    screenshot.size,
                    screenshot.bgra,
                    "raw",
                    "BGRX"
                )
                
                # 转换为 bytes
                buffer = io.BytesIO()
                img.save(buffer, format="PNG")
                return buffer.getvalue()
                
        except Exception as e:
            logger.error(f"Failed to capture icon: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    def compute_hash(self, image_data: bytes) -> str:
        """计算图片的哈希值"""
        return hashlib.md5(image_data).hexdigest()
    
    def check_flashing(self, rect: IconRect) -> Optional[bool]:
        """
        检测图标是否在闪烁
        
        Args:
            rect: 图标区域
            
        Returns:
            True - 正在闪烁
            False - 未闪烁
            None - 检测失败
        """
        # 截取当前图标
        image_data = self.capture_icon(rect)
        if image_data is None:
            return None
        
        # 计算哈希
        current_hash = self.compute_hash(image_data)
        
        # 更新历史
        self._hash_history.append(current_hash)
        if len(self._hash_history) > self._history_size:
            self._hash_history.pop(0)
        
        # 判断是否在闪烁（历史中有不同的哈希值）
        if len(self._hash_history) >= 2:
            unique_hashes = set(self._hash_history)
            return len(unique_hashes) > 1
        
        return False
    
    def get_hash_history(self) -> List[str]:
        """获取哈希历史"""
        return self._hash_history.copy()
    
    def clear_history(self) -> None:
        """清空历史"""
        self._hash_history.clear()
