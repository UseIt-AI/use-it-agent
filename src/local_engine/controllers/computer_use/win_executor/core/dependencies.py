"""
依赖检测和控制器初始化
"""
import logging

logger = logging.getLogger(__name__)

# ============================================================
# PIL (Pillow) - 截图
# ============================================================
try:
    from PIL import Image, ImageGrab
    PIL_AVAILABLE = True
    logger.info("PIL (Pillow) loaded successfully")
except ImportError as e:
    PIL_AVAILABLE = False
    Image = None
    ImageGrab = None
    logger.error(f"PIL import failed: {e}")

# ============================================================
# pynput - 鼠标键盘控制
# ============================================================
try:
    from pynput.keyboard import Controller as KeyboardController
    from pynput.keyboard import Key as KBKey
    from pynput.mouse import Button as MouseButton
    from pynput.mouse import Controller as MouseController
    PYNPUT_AVAILABLE = True
    logger.info("pynput loaded successfully")
except ImportError as e:
    PYNPUT_AVAILABLE = False
    KeyboardController = None
    KBKey = None
    MouseButton = None
    MouseController = None
    logger.error(f"pynput import failed: {e}")

# ============================================================
# pywin32 - Windows API
# ============================================================
try:
    import win32api
    import win32con
    import win32gui
    WINDOWS_API_AVAILABLE = True
    logger.info("Windows API (pywin32) loaded successfully")
except ImportError as e:
    WINDOWS_API_AVAILABLE = False
    win32api = None
    win32con = None
    win32gui = None
    logger.warning(f"Windows API import failed: {e} (some features unavailable)")

# ============================================================
# 控制器实例
# ============================================================
if PYNPUT_AVAILABLE:
    mouse = MouseController()
    keyboard = KeyboardController()
else:
    mouse = None
    keyboard = None


