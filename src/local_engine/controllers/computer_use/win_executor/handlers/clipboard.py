"""
剪贴板操作处理器 (64位 Windows 兼容)
"""
import ctypes
from ctypes import wintypes
import logging
import time
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# ============================================================
# Win32 API 类型定义 (64位兼容)
# ============================================================
HANDLE = ctypes.c_void_p
LPVOID = ctypes.c_void_p
HGLOBAL = ctypes.c_void_p
UINT = ctypes.c_uint
SIZE_T = ctypes.c_size_t

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

# 获取 DLL
_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32

# 设置函数签名 (64位兼容)
_kernel32.GlobalAlloc.argtypes = [UINT, SIZE_T]
_kernel32.GlobalAlloc.restype = HGLOBAL

_kernel32.GlobalLock.argtypes = [HGLOBAL]
_kernel32.GlobalLock.restype = LPVOID

_kernel32.GlobalUnlock.argtypes = [HGLOBAL]
_kernel32.GlobalUnlock.restype = wintypes.BOOL

_kernel32.GlobalFree.argtypes = [HGLOBAL]
_kernel32.GlobalFree.restype = HGLOBAL

_user32.OpenClipboard.argtypes = [wintypes.HWND]
_user32.OpenClipboard.restype = wintypes.BOOL

_user32.CloseClipboard.argtypes = []
_user32.CloseClipboard.restype = wintypes.BOOL

_user32.EmptyClipboard.argtypes = []
_user32.EmptyClipboard.restype = wintypes.BOOL

_user32.SetClipboardData.argtypes = [UINT, HANDLE]
_user32.SetClipboardData.restype = HANDLE

_user32.GetClipboardData.argtypes = [UINT]
_user32.GetClipboardData.restype = HANDLE


# ============================================================
# 剪贴板操作函数
# ============================================================
def _open_clipboard_with_retry(max_retries: int = 10, delay: float = 0.05) -> bool:
    """尝试打开剪贴板（带重试）"""
    for i in range(max_retries):
        if _user32.OpenClipboard(None):
            return True
        time.sleep(delay)
    logger.error(f"Failed to open clipboard after {max_retries} retries")
    return False


def _set_clipboard_win32(text: str) -> bool:
    """使用 Win32 API 设置剪贴板内容"""
    try:
        if not _open_clipboard_with_retry():
            return False
        
        try:
            _user32.EmptyClipboard()
            
            text_bytes = (text + '\0').encode('utf-16-le')
            h_mem = _kernel32.GlobalAlloc(GMEM_MOVEABLE, len(text_bytes))
            if not h_mem:
                logger.error("Failed to allocate memory")
                return False
            
            p_mem = _kernel32.GlobalLock(h_mem)
            if not p_mem:
                _kernel32.GlobalFree(h_mem)
                logger.error("Failed to lock memory")
                return False
            
            ctypes.memmove(p_mem, text_bytes, len(text_bytes))
            _kernel32.GlobalUnlock(h_mem)
            
            if not _user32.SetClipboardData(CF_UNICODETEXT, h_mem):
                _kernel32.GlobalFree(h_mem)
                logger.error("Failed to set clipboard data")
                return False
            
            return True
        finally:
            _user32.CloseClipboard()
    except Exception as e:
        logger.error(f"Set clipboard error: {e}")
        return False


def _get_clipboard_win32() -> Optional[str]:
    """使用 Win32 API 获取剪贴板内容"""
    try:
        if not _open_clipboard_with_retry():
            return None
        
        try:
            h_data = _user32.GetClipboardData(CF_UNICODETEXT)
            if not h_data:
                return ""
            
            p_data = _kernel32.GlobalLock(h_data)
            if not p_data:
                return ""
            
            try:
                text = ctypes.wstring_at(p_data)
                return text
            finally:
                _kernel32.GlobalUnlock(h_data)
        finally:
            _user32.CloseClipboard()
    except Exception as e:
        logger.error(f"Get clipboard error: {e}")
        return None


class ClipboardHandler:
    """剪贴板操作处理器"""
    
    @staticmethod
    def get_clipboard() -> Dict[str, Any]:
        """获取剪贴板内容"""
        content = _get_clipboard_win32()
        if content is None:
            return {"success": False, "error": "Failed to access clipboard"}
        return {"success": True, "content": content}
    
    @staticmethod
    def set_clipboard(text: str) -> Dict[str, Any]:
        """设置剪贴板内容"""
        if _set_clipboard_win32(text):
            return {"success": True}
        else:
            return {"success": False, "error": "Failed to set clipboard"}
