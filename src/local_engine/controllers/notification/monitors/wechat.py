"""
WeChat 托盘图标监听器

通过多种方式检测微信是否有新消息：
1. 托盘内存读取 - 读取 TBBUTTON 结构中的 iBitmap 索引（检测图标闪烁）
2. UI Automation API - 读取托盘图标的 Name 属性
3. 窗口标题检测 - 检查微信窗口标题变化

注意：检测图标闪烁需要管理员权限（读取 explorer.exe 内存）
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import BaseMonitor, MonitorStatus, NotificationEvent
from .tray_screenshot import TrayIconScreenshot, IconRect

logger = logging.getLogger(__name__)


class WeChatTrayMonitor(BaseMonitor):
    """
    微信托盘图标监听器
    
    优先使用 UI Automation API（不需要管理员权限）
    """
    
    def __init__(
        self, 
        poll_interval: float = 0.5, 
        history_size: int = 4,
        check_duration: float = 3.0,
        check_interval: float = 60.0,
    ):
        """
        初始化微信监听器
        
        Args:
            poll_interval: 检查时的轮询间隔 (秒)，默认 0.5 秒
            history_size: 历史记录大小，用于判断闪烁
            check_duration: 每次检查的持续时间 (秒)，默认 3 秒
            check_interval: 两次检查之间的间隔 (秒)，默认 60 秒
        """
        super().__init__(name="wechat", poll_interval=poll_interval)
        self._history_size = history_size
        self._check_duration = check_duration
        self._check_interval = check_interval
        self._state_history: List[str] = []  # 存储状态历史
        self._is_flashing = False
        self._last_flash_time: Optional[datetime] = None
        self._wechat_found = False
        self._last_tooltip: Optional[str] = None
        self._detection_method: str = "unknown"
        
        # 延迟导入模块
        self._imports_ready = False
        self._uiautomation = None
        self._win32gui = None
        self._win32process = None
        
        # 截图检测器
        self._screenshot_detector = TrayIconScreenshot(history_size=history_size)
        self._icon_rect: Optional[IconRect] = None
        
        # 间歇检查状态
        self._last_check_time: Optional[datetime] = None
        self._in_check_window = False
        
    def _import_modules(self) -> bool:
        """延迟导入模块"""
        if self._imports_ready:
            return True
            
        try:
            # 尝试导入 uiautomation（优先，不需要管理员权限）
            try:
                import uiautomation as auto
                self._uiautomation = auto
                logger.info("Using uiautomation for tray detection (no admin required)")
            except ImportError:
                logger.warning("uiautomation not installed, trying pywin32")
                self._uiautomation = None
            
            # 导入 pywin32（用于窗口检测）
            try:
                import win32gui
                import win32process
                self._win32gui = win32gui
                self._win32process = win32process
            except ImportError:
                logger.warning("pywin32 not installed")
                
            self._imports_ready = True
            return True
        except Exception as e:
            logger.error(f"Failed to import modules: {e}")
            return False
    
    def _detect_flashing_via_screenshot(self) -> Optional[bool]:
        """
        通过截图对比检测图标是否在闪烁
        
        Returns:
            True - 正在闪烁（有新消息）
            False - 未闪烁
            None - 无法检测
        """
        try:
            # 获取图标位置
            if self._icon_rect is None:
                logger.debug("Looking for WeChat tray icon...")
                self._icon_rect = self._screenshot_detector.find_tray_icon_rect("微信")
                if self._icon_rect is None:
                    # 尝试英文名
                    self._icon_rect = self._screenshot_detector.find_tray_icon_rect("WeChat")
                
                if self._icon_rect:
                    logger.info(f"Found WeChat icon at: {self._icon_rect.to_tuple()}")
                else:
                    logger.debug("WeChat tray icon not found")
            
            if self._icon_rect is None:
                return None
            
            # 检测闪烁
            result = self._screenshot_detector.check_flashing(self._icon_rect)
            logger.debug(f"Screenshot flash detection result: {result}, history: {self._screenshot_detector.get_hash_history()}")
            return result
        except Exception as e:
            logger.error(f"Screenshot detection error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def _find_wechat_tray_via_uiautomation(self) -> Optional[Dict[str, Any]]:
        """
        通过 UI Automation 查找微信托盘图标
        
        Returns:
            图标信息字典，未找到返回 None
        """
        if not self._uiautomation:
            return None
            
        auto = self._uiautomation
        
        try:
            # 查找系统托盘
            taskbar = auto.PaneControl(ClassName="Shell_TrayWnd")
            if not taskbar.Exists(0, 0):
                return None
            
            # 查找托盘通知区域
            tray_notify = taskbar.PaneControl(ClassName="TrayNotifyWnd")
            if not tray_notify.Exists(0, 0):
                return None
            
            sys_pager = tray_notify.PaneControl(ClassName="SysPager")
            if not sys_pager.Exists(0, 0):
                return None
            
            # 方法1: 查找 ToolbarWindow32
            toolbar = sys_pager.ToolBarControl(ClassName="ToolbarWindow32")
            if toolbar.Exists(0, 0):
                try:
                    for item in toolbar.GetChildren():
                        try:
                            name = item.Name or ""
                            if "微信" in name or "WeChat" in name.lower():
                                return {
                                    "name": name,
                                    "found_in": "main_tray",
                                }
                        except Exception:
                            continue
                except Exception as e:
                    logger.debug(f"Error iterating toolbar: {e}")
            
            # 方法2: 直接在 SysPager 下查找所有按钮控件
            try:
                for item in sys_pager.GetChildren():
                    try:
                        name = item.Name or ""
                        if "微信" in name or "WeChat" in name.lower():
                            return {
                                "name": name,
                                "found_in": "sys_pager",
                            }
                        # 递归查找子控件
                        for child in item.GetChildren():
                            try:
                                child_name = child.Name or ""
                                if "微信" in child_name or "WeChat" in child_name.lower():
                                    return {
                                        "name": child_name,
                                        "found_in": "sys_pager_child",
                                    }
                            except Exception:
                                continue
                    except Exception:
                        continue
            except Exception as e:
                logger.debug(f"Error searching SysPager: {e}")
            
            # 方法3: 查找溢出区域（^ 折叠菜单）
            overflow = auto.PaneControl(ClassName="NotifyIconOverflowWindow")
            if overflow.Exists(0, 0):
                overflow_toolbar = overflow.ToolBarControl(ClassName="ToolbarWindow32")
                if overflow_toolbar.Exists(0, 0):
                    try:
                        for item in overflow_toolbar.GetChildren():
                            try:
                                name = item.Name or ""
                                if "微信" in name or "WeChat" in name.lower():
                                    return {
                                        "name": name,
                                        "found_in": "overflow_tray",
                                    }
                            except Exception:
                                continue
                    except Exception:
                        pass
            
            return None
            
        except Exception as e:
            logger.debug(f"UI Automation search failed: {e}")
            return None
    
    def _find_wechat_window(self) -> Optional[Dict[str, Any]]:
        """
        查找微信主窗口
        
        Returns:
            窗口信息字典，未找到返回 None
        """
        if not self._win32gui:
            return None
            
        result = {"hwnd": None, "title": None, "class": None}
        
        def enum_callback(hwnd, _):
            try:
                class_name = self._win32gui.GetClassName(hwnd)
                title = self._win32gui.GetWindowText(hwnd)
                
                # 微信主窗口的类名（包括新版 Qt 窗口）
                # WeChatMainWndForPC - 旧版微信
                # Qt51514QWindowIcon - 新版微信 (Qt 框架)
                # ChatWnd - 聊天窗口
                if class_name in ["WeChatMainWndForPC", "ChatWnd"]:
                    result["hwnd"] = hwnd
                    result["title"] = title
                    result["class"] = class_name
                    return False  # 停止枚举
                
                # 新版微信使用 Qt 框架，类名是 Qt51514QWindowIcon
                # 需要同时检查标题是否为"微信"
                if "Qt" in class_name and "QWindow" in class_name:
                    if title == "微信" or title == "WeChat":
                        result["hwnd"] = hwnd
                        result["title"] = title
                        result["class"] = class_name
                        return False
            except Exception:
                pass
            return True
        
        try:
            self._win32gui.EnumWindows(enum_callback, None)
        except Exception:
            pass
        
        return result if result["hwnd"] else None
    
    def _check_wechat_process_running(self) -> bool:
        """检查微信进程是否在运行"""
        if not self._win32gui or not self._win32process:
            return False
            
        try:
            import win32con
            import win32api
            
            # 通过窗口查找
            def enum_callback(hwnd, pids):
                try:
                    _, pid = self._win32process.GetWindowThreadProcessId(hwnd)
                    pids.add(pid)
                except Exception:
                    pass
                return True
            
            pids = set()
            self._win32gui.EnumWindows(enum_callback, pids)
            
            # 检查是否有 WeChat.exe 进程
            for pid in pids:
                try:
                    handle = win32api.OpenProcess(
                        win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ,
                        False, pid
                    )
                    if handle:
                        try:
                            exe_name = self._win32process.GetModuleFileNameEx(handle, 0)
                            if "WeChat.exe" in exe_name:
                                win32api.CloseHandle(handle)
                                return True
                        finally:
                            win32api.CloseHandle(handle)
                except Exception:
                    continue
                    
            return False
        except Exception:
            return False
    
    async def check_available(self) -> bool:
        """检查微信是否可用"""
        if not self._import_modules():
            self._last_error = "Required modules not installed"
            return False
        
        loop = asyncio.get_event_loop()
        
        # 方法1: 通过 UI Automation 查找托盘图标
        if self._uiautomation:
            result = await loop.run_in_executor(
                None, self._find_wechat_tray_via_uiautomation
            )
            if result:
                self._wechat_found = True
                self._detection_method = "uiautomation"
                self._last_tooltip = result.get("name")
                logger.info(f"WeChat found via UI Automation: {result}")
                return True
        
        # 方法2: 查找微信窗口
        window_info = await loop.run_in_executor(None, self._find_wechat_window)
        if window_info:
            self._wechat_found = True
            self._detection_method = "window"
            logger.info(f"WeChat window found: {window_info}")
            return True
        
        # 方法3: 检查进程
        process_running = await loop.run_in_executor(
            None, self._check_wechat_process_running
        )
        if process_running:
            self._wechat_found = True
            self._detection_method = "process"
            logger.info("WeChat process found")
            return True
        
        self._wechat_found = False
        self._last_error = "WeChat not found"
        return False
    
    def _should_check_now(self) -> bool:
        """
        判断当前是否应该进行检查
        
        间歇检查模式：每隔 check_interval 秒检查 check_duration 秒
        """
        now = datetime.now()
        
        # 首次检查
        if self._last_check_time is None:
            self._last_check_time = now
            self._in_check_window = True
            logger.debug(f"Starting first check window")
            return True
        
        elapsed = (now - self._last_check_time).total_seconds()
        
        # 在检查窗口内
        if self._in_check_window:
            if elapsed < self._check_duration:
                return True
            else:
                # 检查窗口结束
                self._in_check_window = False
                logger.debug(f"Check window ended, sleeping for {self._check_interval - self._check_duration:.1f}s")
                # 清空历史，为下次检查做准备
                self._screenshot_detector.clear_history()
                return False
        
        # 在休眠期间
        if elapsed >= self._check_interval:
            # 开始新的检查窗口
            self._last_check_time = now
            self._in_check_window = True
            logger.debug(f"Starting new check window")
            return True
        
        return False
    
    async def poll_once(self) -> Optional[NotificationEvent]:
        """执行一次轮询检查"""
        # 检查是否在检查窗口内
        if not self._should_check_now():
            # 不在检查窗口，跳过本次轮询
            return None
        
        loop = asyncio.get_event_loop()
        
        # 方法1: 通过截图对比检测图标闪烁（通用方案，不需要管理员权限）
        is_flashing = await loop.run_in_executor(
            None, self._detect_flashing_via_screenshot
        )
        
        if is_flashing is not None:
            was_flashing = self._is_flashing
            self._is_flashing = is_flashing
            self._detection_method = "screenshot"
            
            if is_flashing and not was_flashing:
                # 开始闪烁 - 有新消息
                self._last_flash_time = datetime.now()
                return NotificationEvent(
                    source="wechat",
                    event_type="new_message",
                    data={
                        "hash_history": self._screenshot_detector.get_hash_history(),
                        "detection_method": "screenshot",
                    },
                    message="WeChat has new message (icon flashing detected)",
                )
            elif not is_flashing and was_flashing:
                # 停止闪烁 - 消息已读
                return NotificationEvent(
                    source="wechat",
                    event_type="message_read",
                    data={
                        "flash_duration": (
                            (datetime.now() - self._last_flash_time).total_seconds()
                            if self._last_flash_time else None
                        ),
                        "detection_method": "screenshot",
                    },
                    message="WeChat message read (icon stopped flashing)",
                )
            # 如果截图检测成功，直接返回
            return None
        
        # 方法2: 使用 UI Automation 检测 tooltip 变化
        if self._uiautomation:
            result = await loop.run_in_executor(
                None, self._find_wechat_tray_via_uiautomation
            )
            
            if result:
                current_name = result.get("name", "")
                
                self._state_history.append(current_name)
                if len(self._state_history) > self._history_size:
                    self._state_history.pop(0)
                
                # 检测是否有新消息的关键词
                has_message_indicator = any([
                    "条消息" in current_name,
                    "条新消息" in current_name,
                    "new message" in current_name.lower(),
                    "unread" in current_name.lower(),
                ])
                
                if has_message_indicator and self._last_tooltip != current_name:
                    self._last_tooltip = current_name
                    self._last_flash_time = datetime.now()
                    self._detection_method = "uiautomation"
                    return NotificationEvent(
                        source="wechat",
                        event_type="new_message",
                        data={
                            "tooltip": current_name,
                            "detection_method": "uiautomation",
                        },
                        message=f"WeChat: {current_name}",
                    )
        
        # 方法3: 检测窗口标题变化
        window_info = await loop.run_in_executor(None, self._find_wechat_window)
        if window_info:
            title = window_info.get("title", "")
            if title and ("条新消息" in title or "new message" in title.lower()):
                if self._last_tooltip != title:
                    self._last_tooltip = title
                    self._detection_method = "window_title"
                    return NotificationEvent(
                        source="wechat",
                        event_type="new_message",
                        data={
                            "window_title": title,
                            "detection_method": "window_title",
                        },
                        message=f"WeChat: {title}",
                    )
        
        return None
    
    def get_status_info(self) -> Dict[str, Any]:
        """获取监听器状态信息"""
        info = super().get_status_info()
        info.update({
            "wechat_found": self._wechat_found,
            "detection_method": self._detection_method,
            "is_flashing": self._is_flashing,
            "last_flash_time": (
                self._last_flash_time.isoformat() if self._last_flash_time else None
            ),
            "last_tooltip": self._last_tooltip,
            "state_history": self._state_history.copy(),
            "hash_history": self._screenshot_detector.get_hash_history(),
            "icon_rect": (
                self._icon_rect.to_tuple() if self._icon_rect else None
            ),
            "requires_admin": False,  # 截图方案不需要管理员权限
            "check_interval": self._check_interval,
            "check_duration": self._check_duration,
            "in_check_window": self._in_check_window,
            "last_check_time": (
                self._last_check_time.isoformat() if self._last_check_time else None
            ),
        })
        return info
    
    def reset_state(self) -> None:
        """重置监听状态"""
        self._state_history.clear()
        self._screenshot_detector.clear_history()
        self._is_flashing = False
        self._last_flash_time = None
        self._last_tooltip = None
        self._icon_rect = None
        self._last_check_time = None
        self._in_check_window = False
