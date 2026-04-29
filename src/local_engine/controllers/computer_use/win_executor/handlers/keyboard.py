"""
键盘操作处理器 (64位 Windows 兼容)
"""
import ctypes
from ctypes import wintypes
import logging
import time
from typing import Dict, Any, List

from ..core.dependencies import (
    PYNPUT_AVAILABLE,
    keyboard, KBKey
)

logger = logging.getLogger(__name__)


# ============================================================
# 按键映射
# ============================================================
SPECIAL_KEYS = {
    "enter": KBKey.enter if KBKey else None,
    "return": KBKey.enter if KBKey else None,
    "esc": KBKey.esc if KBKey else None,
    "escape": KBKey.esc if KBKey else None,
    "tab": KBKey.tab if KBKey else None,
    "space": KBKey.space if KBKey else None,
    "backspace": KBKey.backspace if KBKey else None,
    "delete": KBKey.delete if KBKey else None,
    "del": KBKey.delete if KBKey else None,
    "home": KBKey.home if KBKey else None,
    "end": KBKey.end if KBKey else None,
    "pageup": KBKey.page_up if KBKey else None,
    "pagedown": KBKey.page_down if KBKey else None,
    "up": KBKey.up if KBKey else None,
    "down": KBKey.down if KBKey else None,
    "left": KBKey.left if KBKey else None,
    "right": KBKey.right if KBKey else None,
    "ctrl": KBKey.ctrl if KBKey else None,
    "control": KBKey.ctrl if KBKey else None,
    "alt": KBKey.alt if KBKey else None,
    "shift": KBKey.shift if KBKey else None,
    "win": KBKey.cmd if KBKey else None,
    "windows": KBKey.cmd if KBKey else None,
    "cmd": KBKey.cmd if KBKey else None,
    "f1": KBKey.f1 if KBKey else None,
    "f2": KBKey.f2 if KBKey else None,
    "f3": KBKey.f3 if KBKey else None,
    "f4": KBKey.f4 if KBKey else None,
    "f5": KBKey.f5 if KBKey else None,
    "f6": KBKey.f6 if KBKey else None,
    "f7": KBKey.f7 if KBKey else None,
    "f8": KBKey.f8 if KBKey else None,
    "f9": KBKey.f9 if KBKey else None,
    "f10": KBKey.f10 if KBKey else None,
    "f11": KBKey.f11 if KBKey else None,
    "f12": KBKey.f12 if KBKey else None,
    "capslock": KBKey.caps_lock if KBKey else None,
    "numlock": KBKey.num_lock if KBKey else None,
    "printscreen": KBKey.print_screen if KBKey else None,
    "insert": KBKey.insert if KBKey else None,
}


def _key_from_string(key: str):
    """
    将按键字符串转换为 pynput Key 或字符
    
    注意：对于普通字符键（如 a-z），pynput 区分大小写：
    - 'a' -> 输入小写 a
    - 'A' -> 输入大写 A（相当于 Shift+A）
    
    所以普通字符需要转小写，避免意外输入大写字母。
    """
    if not key:
        return None
    
    key_lower = key.lower()
    
    # 先查特殊键
    if key_lower in SPECIAL_KEYS:
        return SPECIAL_KEYS[key_lower]
    
    # 普通字符键，返回小写（避免意外输入大写）
    return key_lower


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
# Win32 剪贴板操作（用于输入中文）
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
    """使用 Win32 API 设置剪贴板内容（Unicode, 64位兼容）"""
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
        logger.error(f"Win32 clipboard error: {e}")
        return False


def _get_clipboard_win32() -> str:
    """使用 Win32 API 获取剪贴板内容"""
    try:
        if not _open_clipboard_with_retry():
            return ""
        
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
        logger.error(f"Win32 clipboard get error: {e}")
        return ""


def _type_text_safe(text: str) -> bool:
    """
    安全地输入文本，支持中文和特殊字符
    
    使用 Win32 API 操作剪贴板 + Ctrl+V 粘贴
    不受输入法状态影响，支持所有 Unicode 字符
    """
    if not text:
        return True
    
    if not PYNPUT_AVAILABLE:
        return False
    
    try:
        # 1. 保存当前剪贴板内容
        old_clipboard = _get_clipboard_win32()
        
        # 2. 设置剪贴板内容
        if not _set_clipboard_win32(text):
            logger.error("Failed to set clipboard")
            return False
        
        time.sleep(0.05)  # 等待剪贴板更新
        
        # 3. Ctrl+V 粘贴
        keyboard.press(KBKey.ctrl)
        time.sleep(0.02)
        keyboard.press('v')
        time.sleep(0.02)
        keyboard.release('v')
        time.sleep(0.02)
        keyboard.release(KBKey.ctrl)
        time.sleep(0.1)  # 等待粘贴完成
        
        # 4. 恢复原剪贴板内容
        if old_clipboard:
            time.sleep(0.1)
            _set_clipboard_win32(old_clipboard)
        
        return True
        
    except Exception as e:
        logger.exception(f"Type text failed: {e}")
        return False


class KeyboardHandler:
    """键盘操作处理器"""
    
    @staticmethod
    def type_text(text: str) -> Dict[str, Any]:
        """输入文本（支持中文）"""
        if not PYNPUT_AVAILABLE:
            return {"success": False, "error": "pynput not available"}
        if not text:
            return {"success": False, "error": "text required"}
        
        success = _type_text_safe(text)
        if success:
            return {"success": True}
        else:
            return {"success": False, "error": "Failed to type text"}
    
    @staticmethod
    def press_key(key: str) -> Dict[str, Any]:
        """按下并释放按键"""
        if not PYNPUT_AVAILABLE:
            return {"success": False, "error": "pynput not available"}
        if not key:
            return {"success": False, "error": "key required"}
        
        k = _key_from_string(key)
        keyboard.press(k)
        keyboard.release(k)
        return {"success": True}
    
    @staticmethod
    def key_down(key: str) -> Dict[str, Any]:
        """按下按键"""
        if not PYNPUT_AVAILABLE:
            return {"success": False, "error": "pynput not available"}
        if not key:
            return {"success": False, "error": "key required"}
        
        k = _key_from_string(key)
        keyboard.press(k)
        return {"success": True}
    
    @staticmethod
    def key_up(key: str) -> Dict[str, Any]:
        """释放按键"""
        if not PYNPUT_AVAILABLE:
            return {"success": False, "error": "pynput not available"}
        if not key:
            return {"success": False, "error": "key required"}
        
        k = _key_from_string(key)
        keyboard.release(k)
        return {"success": True}
    
    @staticmethod
    def hotkey(keys: str | List[str]) -> Dict[str, Any]:
        """组合键"""
        if not PYNPUT_AVAILABLE:
            return {"success": False, "error": "pynput not available"}
        if not keys:
            return {"success": False, "error": "keys required"}
        
        # 支持 "ctrl+c" 或 ["ctrl", "c"] 格式
        if isinstance(keys, str):
            parts = [p.strip() for p in keys.split('+')]
        else:
            parts = keys
        
        seq = [_key_from_string(p) for p in parts if p]
        
        # 按下所有修饰键
        for k in seq[:-1]:
            keyboard.press(k)
        
        # 按下并释放最后一个键
        last = seq[-1]
        keyboard.press(last)
        keyboard.release(last)
        
        # 释放修饰键
        for k in reversed(seq[:-1]):
            keyboard.release(k)
        
        return {"success": True}
