"""
屏幕操作处理器（截图、屏幕信息）

坐标系说明：
    所有坐标均为 **逻辑坐标 (logical pixel)**，与 pynput 坐标系一致。
    逻辑分辨率 = win32api.GetSystemMetrics(SM_CXSCREEN/SM_CYSCREEN)
    例如：2560x1440 物理分辨率 + 125% 缩放 = 2048x1152 逻辑分辨率
    
    通过 SetProcessDpiAwareness(0) 显式设置进程为 DPI 不感知，
    确保所有 API 使用逻辑坐标。
"""
import base64
import ctypes
import logging
import os
from datetime import datetime
from io import BytesIO
from typing import Dict, Any

from ..core.dependencies import (
    PIL_AVAILABLE, WINDOWS_API_AVAILABLE,
    ImageGrab, win32api, win32con
)
from logging_config import get_screenshot_debug_dir
from .image_utils import compress_fullscreen_screenshot

logger = logging.getLogger(__name__)

# 截图保存目录（调试用；打包后写到用户可写目录，见 logging_config.get_screenshot_debug_dir）
SCREENSHOT_DEBUG_DIR = str(get_screenshot_debug_dir())

# 设置进程 DPI 不感知，确保使用逻辑坐标
# PROCESS_DPI_UNAWARE = 0
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(0)
    logger.info("Set process DPI awareness to UNAWARE (logical coordinates)")
except Exception as e:
    # 可能已经设置过，或者 Windows 版本不支持
    logger.debug(f"SetProcessDpiAwareness failed (may already be set): {e}")


class ScreenHandler:
    """屏幕操作处理器"""
    
    @staticmethod
    def screenshot(compress: bool = True) -> Dict[str, Any]:
        """
        截取屏幕（逻辑分辨率）
        
        由于未设置 DPI 感知，截图自动为逻辑分辨率，
        与 pynput 鼠标坐标系一致。
        
        Args:
            compress: 是否压缩截图（缩放 + JPEG 压缩到 ~300KB）
        """
        if not PIL_AVAILABLE:
            return {"success": False, "error": "PIL not available"}
        
        screenshot = ImageGrab.grab()
        original_width, original_height = screenshot.width, screenshot.height
        
        # DEBUG: 保存原始截图到磁盘
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            debug_path = os.path.join(SCREENSHOT_DEBUG_DIR, f"screenshot_{timestamp}.png")
            screenshot.save(debug_path, format="PNG")
            logger.info(f"[ScreenHandler] DEBUG: Raw screenshot saved to {debug_path}")
        except Exception as e:
            logger.warning(f"[ScreenHandler] DEBUG: Failed to save screenshot: {e}")
        
        if compress:
            # 先转为 bytes，再压缩
            buffered = BytesIO()
            screenshot.save(buffered, format="PNG")
            buffered.seek(0)
            raw_bytes = buffered.read()
            
            # 使用压缩工具（缩放 + JPEG 压缩）
            compressed_bytes = compress_fullscreen_screenshot(raw_bytes)
            image_data = base64.b64encode(compressed_bytes).decode()
            
            logger.info(f"[ScreenHandler] Screenshot compressed: {len(raw_bytes)/1024:.1f}KB -> {len(compressed_bytes)/1024:.1f}KB")
        else:
            # 不压缩，使用原始 PNG
            buffered = BytesIO()
            screenshot.save(buffered, format="PNG", optimize=True)
            buffered.seek(0)
            image_data = base64.b64encode(buffered.getvalue()).decode()
        
        # 返回截图尺寸信息（返回原始尺寸，供坐标计算使用）
        return {
            "success": True,
            "image_data": image_data,
            "width": original_width,
            "height": original_height,
            "compressed": compress,
        }
    
    @staticmethod
    def get_screen_size() -> Dict[str, Any]:
        """
        获取屏幕尺寸（逻辑像素）
        
        返回的是逻辑分辨率，与 pynput 鼠标坐标系一致。
        例如：2K 屏 + 125% 缩放 → 返回 2048x1152
        
        Returns:
            {
                "success": True,
                "size": {"width": 2048, "height": 1152},
                "scale": 1.25,
                "scale_percent": 125,
                "physical_size": {"width": 2560, "height": 1440},
                "coordinate_system": "logical"
            }
        """
        try:
            # 获取 DPI 信息
            scale, dpi = ScreenHandler._get_dpi_scale()
            
            if WINDOWS_API_AVAILABLE:
                # 未设置 DPI 感知时，GetSystemMetrics 返回逻辑分辨率
                logical_w = win32api.GetSystemMetrics(win32con.SM_CXSCREEN)
                logical_h = win32api.GetSystemMetrics(win32con.SM_CYSCREEN)
            elif PIL_AVAILABLE:
                # PIL 截图也是逻辑分辨率
                img = ImageGrab.grab()
                logical_w, logical_h = img.width, img.height
            else:
                return {"success": False, "error": "No method available"}
            
            # 计算物理分辨率
            physical_w = int(logical_w * scale)
            physical_h = int(logical_h * scale)
            
            return {
                "success": True,
                "size": {"width": logical_w, "height": logical_h},
                "scale": round(scale, 4),
                "scale_percent": int(scale * 100),
                "dpi": dpi,
                "physical_size": {"width": physical_w, "height": physical_h},
                "coordinate_system": "logical",
                "note": "All coordinates (mouse, screenshot) use logical pixels"
            }
            
        except Exception as e:
            logger.error(f"Failed to get screen size: {e}")
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def _get_dpi_scale() -> tuple:
        """
        获取 DPI 缩放比例
        
        Returns:
            (scale, dpi) - 例如 (1.25, 120) 表示 125% 缩放
        """
        try:
            # 方法1: 使用 shcore.GetDpiForSystem (Windows 8.1+)
            try:
                ctypes.windll.shcore.GetDpiForSystem.restype = ctypes.c_uint
                system_dpi = ctypes.windll.shcore.GetDpiForSystem()
                return system_dpi / 96.0, system_dpi
            except Exception:
                pass
            
            # 方法2: 从 DC 获取
            try:
                user32 = ctypes.windll.user32
                hdc = user32.GetDC(0)
                gdi32 = ctypes.windll.gdi32
                system_dpi = gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
                user32.ReleaseDC(0, hdc)
                return system_dpi / 96.0, system_dpi
            except Exception:
                pass
            
            # 默认值
            return 1.0, 96
            
        except Exception:
            return 1.0, 96
    
    @staticmethod
    def get_screen_info() -> Dict[str, Any]:
        """
        获取完整的屏幕信息（兼容旧接口）
        
        Returns:
            {
                "success": True,
                "logical_size": {"width": 2048, "height": 1152},
                "physical_size": {"width": 2560, "height": 1440},
                "scale": 1.25,
                "scale_percent": 125,
                "dpi": 120,
                "coordinate_system": "logical"
            }
        """
        result = ScreenHandler.get_screen_size()
        
        if not result.get("success"):
            return result
        
        # 转换为旧格式（兼容）
        return {
            "success": True,
            "logical_size": result["size"],
            "physical_size": result["physical_size"],
            "scale": result["scale"],
            "scale_percent": result["scale_percent"],
            "dpi": result["dpi"],
            "coordinate_system": "logical",
            "note": "All coordinates (mouse, screenshot) use logical pixels"
        }
