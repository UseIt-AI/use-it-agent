"""
窗口枚举与操作（EnumWindows + 进程关联 + SetWindowPos / ShowWindow）

这是 AI 感知"用户开了哪些文档/网页"、并对窗口做状态/布局操作的主力：
- Office SDI 模式下，每个打开的 ppt/word/xlsx 都是独立的顶级窗口
- 浏览器的每个窗口也是独立顶级窗口
- 通过 HWND -> PID -> 进程名/exe 反查，AI 能直接定位
- 提供 minimize/maximize/restore/close/set_topmost/move_resize/tile 等写操作

所有写操作都支持三种目标定位方式：
- hwnd (推荐，最精确)
- process_name + title_contains (模糊匹配)
匹配到多个窗口时返回 candidates，让调用方挑一个 hwnd 重试。
"""
import ctypes
import logging
from ctypes import wintypes
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    import win32gui
    import win32con
    import win32process
    import win32api
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False
    win32gui = None  # type: ignore[assignment]
    win32con = None  # type: ignore[assignment]
    win32process = None  # type: ignore[assignment]
    win32api = None  # type: ignore[assignment]
    logger.warning("pywin32 not available, WindowHandler disabled")

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    psutil = None  # type: ignore[assignment]

try:
    from PIL import Image, ImageGrab
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False
    Image = None  # type: ignore[assignment]
    ImageGrab = None  # type: ignore[assignment]


# pywin32（截至 v311）从来没有把 Win32 API `IsZoomed` 暴露到 `win32gui`
# 模块里——`IsIconic` 有，`IsZoomed` 没有。所以我们用 GetWindowPlacement
# 反推：placement[1] 是 showCmd，3 (SW_SHOWMAXIMIZED) 就是最大化。
#
# 仍保留一层 `hasattr` 兜底：万一将来 pywin32 补齐了就直接走原生 API。
_SW_SHOWMAXIMIZED = 3


def _is_zoomed(hwnd: int) -> bool:
    """窗口最大化判定，替代 pywin32 并未暴露的 win32gui.IsZoomed。"""
    native = getattr(win32gui, "IsZoomed", None)
    if native is not None:
        try:
            return bool(native(hwnd))
        except Exception as e:
            logger.debug("[WindowHandler] win32gui.IsZoomed(%s) failed: %s", hwnd, e)
    try:
        placement = win32gui.GetWindowPlacement(hwnd)
        # placement = (flags, showCmd, ptMinPosition, ptMaxPosition, rcNormalPosition)
        return placement[1] == _SW_SHOWMAXIMIZED
    except Exception as e:
        logger.debug("[WindowHandler] GetWindowPlacement(%s) failed: %s", hwnd, e)
        return False


# =========================================================================
# Screenshot helpers（模块级，也给 PPT 的 snapshot_extractor 复用）
#
# 设计目标：**绝不抢用户焦点**。以往用 SetForegroundWindow + ImageGrab，
# 会把用户正在打字的 Word / 浏览器焦点抢走。现在改成"优先 PrintWindow，
# 必要时回退 ImageGrab"，两条路都不需要把目标窗口变前台。
# =========================================================================

_PW_RENDERFULLCONTENT = 0x00000002  # Windows 8.1+：让 PrintWindow 也能截 Chrome/DirectX 内容


def _get_dwm_rect(hwnd: int) -> Optional[Tuple[int, int, int, int]]:
    """
    用 DwmGetWindowAttribute(DWMWA_EXTENDED_FRAME_BOUNDS=9) 拿"真实窗口矩形"，
    排除掉 Win10+ 自动加的 DWM 阴影留白。拿不到就回退 GetWindowRect。
    """
    try:
        rect = wintypes.RECT()
        DWMWA_EXTENDED_FRAME_BOUNDS = 9
        hr = ctypes.windll.dwmapi.DwmGetWindowAttribute(
            hwnd, DWMWA_EXTENDED_FRAME_BOUNDS,
            ctypes.byref(rect), ctypes.sizeof(rect),
        )
        if hr == 0:
            return (rect.left, rect.top, rect.right, rect.bottom)
    except Exception as e:
        logger.debug("[capture] DwmGetWindowAttribute failed hwnd=%s: %s", hwnd, e)
    try:
        return win32gui.GetWindowRect(hwnd)
    except Exception:
        return None


def _printwindow_capture(hwnd: int, width: int, height: int):
    """
    用 Win32 PrintWindow 把窗口"内容渲染到位图"——关键优点：**不需要窗口
    在前台**，甚至被遮挡也能截。对 Chrome / Electron / DirectX 用 RENDERFULLCONTENT
    标志能大幅提升成功率，但对某些硬件加速的图形应用仍可能返回黑帧，所以上层
    要配合 `_looks_mostly_black` 做健康检查。

    返回 PIL.Image 或 None。
    """
    if not _PIL_AVAILABLE or not WIN32_AVAILABLE:
        return None
    if width <= 0 or height <= 0:
        return None

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    hwnd_dc = user32.GetWindowDC(hwnd)
    if not hwnd_dc:
        return None
    mem_dc = None
    bitmap = None
    try:
        mem_dc = gdi32.CreateCompatibleDC(hwnd_dc)
        if not mem_dc:
            return None
        bitmap = gdi32.CreateCompatibleBitmap(hwnd_dc, width, height)
        if not bitmap:
            return None
        old_bitmap = gdi32.SelectObject(mem_dc, bitmap)
        try:
            ok = user32.PrintWindow(hwnd, mem_dc, _PW_RENDERFULLCONTENT)
            if not ok:
                # 某些老窗口 FULLCONTENT 不支持，退回 flag=0
                ok = user32.PrintWindow(hwnd, mem_dc, 0)
            if not ok:
                return None

            class _BITMAPINFOHEADER(ctypes.Structure):
                _fields_ = [
                    ("biSize", wintypes.DWORD),
                    ("biWidth", wintypes.LONG),
                    ("biHeight", wintypes.LONG),
                    ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD),
                    ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD),
                    ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG),
                    ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD),
                ]

            bmi = _BITMAPINFOHEADER()
            bmi.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
            bmi.biWidth = width
            bmi.biHeight = -height  # 负值 = top-down bitmap
            bmi.biPlanes = 1
            bmi.biBitCount = 32
            bmi.biCompression = 0  # BI_RGB

            buf = ctypes.create_string_buffer(width * height * 4)
            got = gdi32.GetDIBits(mem_dc, bitmap, 0, height, buf, ctypes.byref(bmi), 0)
            if not got:
                return None

            img = Image.frombuffer("RGBA", (width, height), bytes(buf), "raw", "BGRA", 0, 1)
            return img.convert("RGB")
        finally:
            gdi32.SelectObject(mem_dc, old_bitmap)
    except Exception as e:
        logger.debug("[capture] PrintWindow failed hwnd=%s: %s", hwnd, e)
        return None
    finally:
        if bitmap:
            gdi32.DeleteObject(bitmap)
        if mem_dc:
            gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(hwnd, hwnd_dc)


def _looks_mostly_black(img, ratio: float = 0.98) -> bool:
    """
    PrintWindow 对 DirectX 类应用偶尔返回黑帧。采样 ~400 像素判决：
    如果 >98% 的采样点 RGB 都 <10，就认为这次截图是废的。
    """
    try:
        w, h = img.size
        sx = max(1, w // 20)
        sy = max(1, h // 20)
        total = 0
        black = 0
        for x in range(0, w, sx):
            for y in range(0, h, sy):
                total += 1
                px = img.getpixel((x, y))
                if isinstance(px, tuple):
                    if max(px[:3]) < 10:
                        black += 1
                elif px < 10:
                    black += 1
        return total > 0 and (black / total) >= ratio
    except Exception:
        return False


def _imagegrab_region(rect: Tuple[int, int, int, int]):
    """PIL ImageGrab 截屏幕 bbox——只在窗口"肉眼可见"时可靠，但不抢焦点。"""
    if not _PIL_AVAILABLE:
        return None
    try:
        return ImageGrab.grab(bbox=rect, all_screens=True)
    except Exception as e:
        logger.debug("[capture] ImageGrab failed rect=%s: %s", rect, e)
        return None


def capture_hwnd_image(hwnd: int, prefer_printwindow: bool = False):
    """
    **对外唯一**的窗口截图入口。不抢焦点。

    策略：
    - 窗口已最小化 / 隐藏 → 只能用 PrintWindow
    - 窗口可见 →
        默认：ImageGrab 先（对 Office/DirectX 最准），失败再 PrintWindow
        prefer_printwindow=True：反过来（给"窗口可能被其它窗口遮挡"的场景）

    返回 PIL.Image 或 None。
    """
    if not _PIL_AVAILABLE or not WIN32_AVAILABLE:
        return None
    if not win32gui.IsWindow(hwnd):
        return None

    rect = _get_dwm_rect(hwnd)
    if rect is None:
        return None
    left, top, right, bottom = rect
    w, h = right - left, bottom - top
    if w <= 0 or h <= 0:
        return None

    try:
        is_hidden = bool(win32gui.IsIconic(hwnd)) or not bool(win32gui.IsWindowVisible(hwnd))
    except Exception:
        is_hidden = False

    # 最小化 / 隐藏的情况只有 PrintWindow 能用
    if is_hidden:
        img = _printwindow_capture(hwnd, w, h)
        if img is not None and not _looks_mostly_black(img):
            return img
        return None

    if prefer_printwindow:
        img = _printwindow_capture(hwnd, w, h)
        if img is not None and not _looks_mostly_black(img):
            return img
        return _imagegrab_region(rect)

    # 默认路径：ImageGrab 先
    img = _imagegrab_region(rect)
    if img is not None:
        return img
    # 回退
    img = _printwindow_capture(hwnd, w, h)
    if img is not None and not _looks_mostly_black(img):
        return img
    return None


def _is_real_top_window(hwnd: int, include_minimized: bool = True) -> bool:
    """
    判断是否是用户关心的"真正的顶级窗口"。

    过滤掉：不可见 / 无标题 / 工具窗口 / 子窗口（有 owner）
    这套规则跟 Windows Alt-Tab 列表里看得到的窗口基本一致。
    """
    if not win32gui.IsWindowVisible(hwnd):
        return False
    if not win32gui.GetWindowText(hwnd):
        return False

    ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
    if ex_style & win32con.WS_EX_TOOLWINDOW:
        return False

    # 有 owner 的窗口通常是对话框 / popup
    if win32gui.GetWindow(hwnd, win32con.GW_OWNER):
        return False

    # 最小化窗口：默认保留（is_minimized 字段会标记）
    if not include_minimized and win32gui.IsIconic(hwnd):
        return False

    return True


def _pid_to_proc_info(pid_cache: Dict[int, Dict[str, str]], pid: int) -> Dict[str, str]:
    """pid -> {"name": ..., "exe": ...}，带缓存避免重复查询"""
    if pid in pid_cache:
        return pid_cache[pid]

    info = {"name": "", "exe": ""}
    if PSUTIL_AVAILABLE and pid > 0:
        try:
            proc = psutil.Process(pid)
            info["name"] = proc.name()
            try:
                info["exe"] = proc.exe() or ""
            except (psutil.AccessDenied, Exception):
                info["exe"] = ""
        except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
            pass

    pid_cache[pid] = info
    return info


class WindowHandler:
    """顶级窗口枚举"""

    @staticmethod
    def list_windows(
        process_name: Optional[str] = None,
        title_contains: Optional[str] = None,
        include_minimized: bool = True,
    ) -> Dict[str, Any]:
        """
        列出所有"真正的"顶级窗口。

        Args:
            process_name: 按进程名过滤（如 "POWERPNT.EXE"），大小写不敏感
            title_contains: 标题模糊匹配
            include_minimized: 是否包含最小化窗口

        Returns:
            {"success": True, "windows": [...], "count": N}
        """
        if not WIN32_AVAILABLE:
            return {"success": False, "error": "pywin32 not available", "windows": [], "count": 0}

        foreground_hwnd = win32gui.GetForegroundWindow()
        pid_cache: Dict[int, Dict[str, str]] = {}
        proc_needle = process_name.lower() if process_name else None
        title_needle = title_contains.lower() if title_contains else None

        windows: List[Dict[str, Any]] = []

        def enum_proc(hwnd, _param):
            try:
                if not _is_real_top_window(hwnd, include_minimized=include_minimized):
                    return True

                title = win32gui.GetWindowText(hwnd)
                class_name = win32gui.GetClassName(hwnd)

                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                proc_info = _pid_to_proc_info(pid_cache, pid)

                # 过滤
                if proc_needle and proc_needle not in proc_info["name"].lower():
                    return True
                if title_needle and title_needle not in title.lower():
                    return True

                rect = win32gui.GetWindowRect(hwnd)
                is_minimized = bool(win32gui.IsIconic(hwnd))

                windows.append({
                    "hwnd": hwnd,
                    "title": title,
                    "class_name": class_name,
                    "pid": pid,
                    "process_name": proc_info["name"],
                    "exe": proc_info["exe"],
                    "is_visible": True,
                    "is_minimized": is_minimized,
                    "is_foreground": (hwnd == foreground_hwnd),
                    "rect": {
                        "x": rect[0],
                        "y": rect[1],
                        "width": rect[2] - rect[0],
                        "height": rect[3] - rect[1],
                    },
                })
            except Exception as e:
                logger.debug(f"Failed to read window hwnd={hwnd}: {e}")
            return True

        win32gui.EnumWindows(enum_proc, None)

        return {"success": True, "windows": windows, "count": len(windows)}

    @staticmethod
    def group_by_process(
        process_name: Optional[str] = None,
        title_contains: Optional[str] = None,
        include_minimized: bool = True,
    ) -> Dict[str, Any]:
        """按进程聚合窗口。适合 AI 问"用户开了几个 ppt"这种场景，一次调用就够。"""
        base = WindowHandler.list_windows(
            process_name=process_name,
            title_contains=title_contains,
            include_minimized=include_minimized,
        )
        if not base.get("success"):
            return base

        groups_map: Dict[int, Dict[str, Any]] = {}
        for w in base["windows"]:
            pid = w["pid"]
            if pid not in groups_map:
                groups_map[pid] = {
                    "pid": pid,
                    "process_name": w["process_name"],
                    "exe": w["exe"],
                    "window_count": 0,
                    "windows": [],
                }
            groups_map[pid]["windows"].append(w)
            groups_map[pid]["window_count"] += 1

        groups = sorted(groups_map.values(), key=lambda g: (g["process_name"].lower(), g["pid"]))
        return {"success": True, "groups": groups, "count": len(groups)}

    @staticmethod
    def activate_window(
        hwnd: Optional[int] = None,
        process_name: Optional[str] = None,
        title_contains: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        把指定窗口切到前台（Alt-Tab 等效）。

        查找顺序:
        1. 传了 hwnd -> 直接用
        2. 否则按 process_name / title_contains 模糊匹配:
           - 命中 0 个: 返回 not found
           - 命中 1 个: 用它
           - 命中多个: 返回 error + candidates，让调用方（AI）挑 hwnd 重试

        Windows 有 Foreground Lock，光调 SetForegroundWindow 在 Win10+ 常常失败。
        标准绕法: 先 SW_RESTORE 取消最小化，再 AttachThreadInput 到当前前台线程
        后调 SetForegroundWindow，完事再 detach。
        """
        if not WIN32_AVAILABLE:
            return {"success": False, "error": "pywin32 not available"}

        # ---------- 1. 解析目标 hwnd ----------
        target_hwnd: int
        if hwnd:
            target_hwnd = int(hwnd)
            if not win32gui.IsWindow(target_hwnd):
                return {"success": False, "error": f"hwnd {target_hwnd} is not a valid window"}
        else:
            if not process_name and not title_contains:
                return {
                    "success": False,
                    "error": "provide at least one of: hwnd, process_name, title_contains",
                }
            lookup = WindowHandler.list_windows(
                process_name=process_name,
                title_contains=title_contains,
                include_minimized=True,
            )
            if not lookup.get("success"):
                return lookup
            matches: List[Dict[str, Any]] = lookup.get("windows", [])
            if not matches:
                return {
                    "success": False,
                    "error": "no window matched",
                    "criteria": {"process_name": process_name, "title_contains": title_contains},
                }
            if len(matches) > 1:
                return {
                    "success": False,
                    "error": f"{len(matches)} windows matched; specify hwnd to disambiguate",
                    "candidates": [
                        {
                            "hwnd": m["hwnd"],
                            "title": m["title"],
                            "process_name": m["process_name"],
                            "is_minimized": m.get("is_minimized", False),
                        }
                        for m in matches[:10]
                    ],
                }
            target_hwnd = int(matches[0]["hwnd"])

        # 记录调用前状态
        was_iconic = False
        try:
            was_iconic = bool(win32gui.IsIconic(target_hwnd))
        except Exception:
            pass

        # ---------- 2. 取消最小化（SW_RESTORE）或普通 show ----------
        restored = False
        try:
            if was_iconic:
                win32gui.ShowWindow(target_hwnd, win32con.SW_RESTORE)
                restored = True
            else:
                win32gui.ShowWindow(target_hwnd, win32con.SW_SHOW)
        except Exception as e:
            logger.debug("[WindowHandler] ShowWindow failed hwnd=%s: %s", target_hwnd, e)

        # ---------- 3. 骗过 Windows foreground lock ----------
        # Win10+ 对 SetForegroundWindow 有严格限制（只允许"有最近用户输入权"的进程抢前台）。
        # 广为人知的绕法：模拟一次按键按下-释放，让 OS 认为当前进程有用户输入。
        #
        # 注意：**不能用 VK_MENU (Alt)**。Alt 单按-单释是 Office Ribbon 触发
        # KeyTips（显示 H/N/O 等快捷键字母）的快捷键，之前用 Alt 会导致
        # 被激活的 Word / Excel / PowerPoint 窗口进入 KeyTips 状态。
        #
        # 这里改用 VK_F24 (0x87)：这是 Windows 保留的功能键、没有任何默认
        # 绑定，Office / 浏览器 / 其它常见程序都不响应它，是"空语义"输入。
        _VK_F24 = 0x87
        try:
            win32api.keybd_event(_VK_F24, 0, 0, 0)  # F24 down
            win32api.keybd_event(_VK_F24, 0, win32con.KEYEVENTF_KEYUP, 0)  # F24 up
        except Exception as e:
            logger.debug("[WindowHandler] keybd_event(F24) failed: %s", e)

        # ---------- 4. AttachThreadInput + SetForegroundWindow ----------
        set_ok = False
        try:
            fg_hwnd = win32gui.GetForegroundWindow()
            fg_thread_id = (
                win32process.GetWindowThreadProcessId(fg_hwnd)[0] if fg_hwnd else 0
            )
            cur_thread_id = win32api.GetCurrentThreadId()
            attached = False
            try:
                if fg_thread_id and fg_thread_id != cur_thread_id:
                    try:
                        win32process.AttachThreadInput(fg_thread_id, cur_thread_id, True)
                        attached = True
                    except Exception as e:
                        logger.debug("[WindowHandler] AttachThreadInput failed: %s", e)
                try:
                    win32gui.BringWindowToTop(target_hwnd)
                except Exception as e:
                    logger.debug("[WindowHandler] BringWindowToTop failed: %s", e)
                try:
                    win32gui.SetForegroundWindow(target_hwnd)
                    set_ok = True
                except Exception as e:
                    logger.debug("[WindowHandler] SetForegroundWindow failed: %s", e)
            finally:
                if attached:
                    try:
                        win32process.AttachThreadInput(fg_thread_id, cur_thread_id, False)
                    except Exception:
                        pass
        except Exception as e:
            logger.warning("[WindowHandler] activate flow threw: %s", e)

        # ---------- 5. 兜底：SwitchToThisWindow（已被 MS 标 deprecated 但仍工作） ----------
        if not set_ok:
            try:
                # 二参数 True = "switch with alt-tab animation"，能无视 foreground lock
                user32 = win32api.LoadLibrary("user32.dll")
                # 注意：win32api 没直接暴露 SwitchToThisWindow，走 ctypes 更稳
                import ctypes
                ctypes.windll.user32.SwitchToThisWindow(int(target_hwnd), True)
                set_ok = True  # 把它当次级成功
                logger.debug("[WindowHandler] SwitchToThisWindow fallback used")
            except Exception as e:
                logger.debug("[WindowHandler] SwitchToThisWindow fallback failed: %s", e)

        # ---------- 6. 校验并返回 ----------
        title = ""
        pid = 0
        try:
            title = win32gui.GetWindowText(target_hwnd)
            _, pid = win32process.GetWindowThreadProcessId(target_hwnd)
        except Exception:
            pass
        now_fg = 0
        now_iconic = False
        try:
            now_fg = win32gui.GetForegroundWindow()
            now_iconic = bool(win32gui.IsIconic(target_hwnd))
        except Exception:
            pass

        is_fg = now_fg == target_hwnd
        # 即便 is_fg=False，但我们成功把它从最小化恢复了 / 或 SetForegroundWindow 没抛，
        # 视觉上窗口已经变化（顶层 z-order 变化 / 从任务栏恢复），用户体感就是成功。
        # 仅当 既没能提到前台 也没能从最小化恢复 也没调成 SetForegroundWindow 才算失败。
        visible_now = (not now_iconic) and restored  # 从最小化 -> 展开
        effective = is_fg or set_ok or visible_now

        warning: Optional[str] = None
        if not is_fg:
            if set_ok:
                warning = (
                    "SetForegroundWindow succeeded but window did not end up in the foreground "
                    "(likely Windows foreground-lock). The window should still be visible/topmost."
                )
            elif visible_now:
                warning = (
                    "Could not grab foreground focus (Windows foreground-lock), but the window "
                    "was restored from minimized and is now visible. User may need to click it."
                )
            else:
                warning = "Failed to activate window — neither focus nor minimize state changed."

        return {
            "success": bool(effective),
            "hwnd": target_hwnd,
            "title": title,
            "pid": pid,
            "is_foreground": is_fg,
            "was_iconic": was_iconic,
            "restored": restored,
            "set_foreground_ok": set_ok,
            "warning": warning,
            # 失败时也带 error 字段，前端 UI 能直接展示
            "error": warning if not effective else None,
        }

    @staticmethod
    def get_foreground_window() -> Dict[str, Any]:
        """取当前前台窗口（Alt-Tab 最前那个）"""
        if not WIN32_AVAILABLE:
            return {"success": False, "error": "pywin32 not available"}

        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return {"success": False, "error": "no foreground window"}

        try:
            title = win32gui.GetWindowText(hwnd)
            class_name = win32gui.GetClassName(hwnd)
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            rect = win32gui.GetWindowRect(hwnd)

            pid_cache: Dict[int, Dict[str, str]] = {}
            proc_info = _pid_to_proc_info(pid_cache, pid)

            return {
                "success": True,
                "window": {
                    "hwnd": hwnd,
                    "title": title,
                    "class_name": class_name,
                    "pid": pid,
                    "process_name": proc_info["name"],
                    "exe": proc_info["exe"],
                    "is_minimized": bool(win32gui.IsIconic(hwnd)),
                    "rect": {
                        "x": rect[0],
                        "y": rect[1],
                        "width": rect[2] - rect[0],
                        "height": rect[3] - rect[1],
                    },
                },
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ================================================================
    #  以下是窗口"写操作"API。所有方法共用 _resolve_hwnd 做目标定位，
    #  失败时返回与 activate_window 一致的 error/candidates 结构。
    # ================================================================

    @staticmethod
    def _resolve_hwnd(
        hwnd: Optional[int] = None,
        process_name: Optional[str] = None,
        title_contains: Optional[str] = None,
    ) -> Tuple[Optional[int], Optional[Dict[str, Any]]]:
        """
        把 (hwnd | process_name | title_contains) 解析为一个确定的 hwnd。

        Returns:
            (hwnd, None)                     # 成功
            (None, {"success": False, ...})  # 失败（未找到 / 多个候选 / 参数不全）
        """
        if not WIN32_AVAILABLE:
            return None, {"success": False, "error": "pywin32 not available"}

        if hwnd:
            h = int(hwnd)
            if not win32gui.IsWindow(h):
                return None, {"success": False, "error": f"hwnd {h} is not a valid window"}
            return h, None

        if not process_name and not title_contains:
            return None, {
                "success": False,
                "error": "provide at least one of: hwnd, process_name, title_contains",
            }

        lookup = WindowHandler.list_windows(
            process_name=process_name,
            title_contains=title_contains,
            include_minimized=True,
        )
        if not lookup.get("success"):
            return None, lookup
        matches: List[Dict[str, Any]] = lookup.get("windows", [])
        if not matches:
            return None, {
                "success": False,
                "error": "no window matched",
                "criteria": {"process_name": process_name, "title_contains": title_contains},
            }
        if len(matches) > 1:
            return None, {
                "success": False,
                "error": f"{len(matches)} windows matched; specify hwnd to disambiguate",
                "candidates": [
                    {
                        "hwnd": m["hwnd"],
                        "title": m["title"],
                        "process_name": m["process_name"],
                        "is_minimized": m.get("is_minimized", False),
                    }
                    for m in matches[:10]
                ],
            }
        return int(matches[0]["hwnd"]), None

    @staticmethod
    def _describe_hwnd(hwnd: int) -> Dict[str, Any]:
        """读窗口的基础信息（给写操作的返回值复用）"""
        try:
            rect = win32gui.GetWindowRect(hwnd)
            is_iconic = bool(win32gui.IsIconic(hwnd))
            is_zoomed = _is_zoomed(hwnd)
            ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            is_topmost = bool(ex_style & win32con.WS_EX_TOPMOST)
            title = win32gui.GetWindowText(hwnd)
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            return {
                "hwnd": hwnd,
                "title": title,
                "pid": pid,
                "is_minimized": is_iconic,
                "is_maximized": is_zoomed,
                "is_topmost": is_topmost,
                "rect": {
                    "x": rect[0],
                    "y": rect[1],
                    "width": rect[2] - rect[0],
                    "height": rect[3] - rect[1],
                },
            }
        except Exception as e:
            return {"hwnd": hwnd, "error": str(e)}

    @staticmethod
    def _show_window(hwnd: int, cmd: int, action_name: str) -> Dict[str, Any]:
        """ShowWindow 的薄封装 + 统一错误处理"""
        try:
            win32gui.ShowWindow(hwnd, cmd)
        except Exception as e:
            logger.warning("[WindowHandler] %s hwnd=%s failed: %s", action_name, hwnd, e)
            return {"success": False, "error": f"{action_name} failed: {e}"}
        return {"success": True, "action": action_name, "window": WindowHandler._describe_hwnd(hwnd)}

    @staticmethod
    def minimize(
        hwnd: Optional[int] = None,
        process_name: Optional[str] = None,
        title_contains: Optional[str] = None,
    ) -> Dict[str, Any]:
        """最小化窗口"""
        target, err = WindowHandler._resolve_hwnd(hwnd, process_name, title_contains)
        if err:
            return err
        return WindowHandler._show_window(target, win32con.SW_MINIMIZE, "minimize")

    @staticmethod
    def maximize(
        hwnd: Optional[int] = None,
        process_name: Optional[str] = None,
        title_contains: Optional[str] = None,
    ) -> Dict[str, Any]:
        """最大化窗口"""
        target, err = WindowHandler._resolve_hwnd(hwnd, process_name, title_contains)
        if err:
            return err
        return WindowHandler._show_window(target, win32con.SW_MAXIMIZE, "maximize")

    @staticmethod
    def restore(
        hwnd: Optional[int] = None,
        process_name: Optional[str] = None,
        title_contains: Optional[str] = None,
    ) -> Dict[str, Any]:
        """还原窗口（取消最小化 / 最大化）"""
        target, err = WindowHandler._resolve_hwnd(hwnd, process_name, title_contains)
        if err:
            return err
        return WindowHandler._show_window(target, win32con.SW_RESTORE, "restore")

    @staticmethod
    def close(
        hwnd: Optional[int] = None,
        process_name: Optional[str] = None,
        title_contains: Optional[str] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        关闭窗口。

        - force=False（默认）: PostMessage(WM_CLOSE)，等价于用户点 X，
          Office 等应用会弹"是否保存"对话框。
        - force=True: TerminateProcess(pid) 强杀，用于卡死/不响应的窗口。
        """
        target, err = WindowHandler._resolve_hwnd(hwnd, process_name, title_contains)
        if err:
            return err

        if force:
            try:
                _, pid = win32process.GetWindowThreadProcessId(target)
            except Exception as e:
                return {"success": False, "error": f"GetWindowThreadProcessId failed: {e}"}
            if not pid:
                return {"success": False, "error": "cannot get pid for hwnd"}
            try:
                if PSUTIL_AVAILABLE:
                    psutil.Process(pid).kill()
                else:
                    import ctypes
                    PROCESS_TERMINATE = 0x0001
                    handle = ctypes.windll.kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
                    if not handle:
                        return {"success": False, "error": f"OpenProcess failed for pid {pid}"}
                    try:
                        ok = ctypes.windll.kernel32.TerminateProcess(handle, 1)
                        if not ok:
                            return {"success": False, "error": f"TerminateProcess failed for pid {pid}"}
                    finally:
                        ctypes.windll.kernel32.CloseHandle(handle)
            except Exception as e:
                return {"success": False, "error": f"force kill failed: {e}"}
            return {"success": True, "action": "close", "force": True, "hwnd": target, "pid": pid}

        # 非 force: 走 WM_CLOSE
        try:
            win32gui.PostMessage(target, win32con.WM_CLOSE, 0, 0)
        except Exception as e:
            return {"success": False, "error": f"PostMessage(WM_CLOSE) failed: {e}"}
        return {"success": True, "action": "close", "force": False, "hwnd": target}

    @staticmethod
    def set_topmost(
        on: bool,
        hwnd: Optional[int] = None,
        process_name: Optional[str] = None,
        title_contains: Optional[str] = None,
    ) -> Dict[str, Any]:
        """置顶 / 取消置顶"""
        target, err = WindowHandler._resolve_hwnd(hwnd, process_name, title_contains)
        if err:
            return err

        # HWND_TOPMOST = -1, HWND_NOTOPMOST = -2
        insert_after = -1 if on else -2
        flags = win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE
        try:
            win32gui.SetWindowPos(target, insert_after, 0, 0, 0, 0, flags)
        except Exception as e:
            return {"success": False, "error": f"SetWindowPos(topmost) failed: {e}"}
        return {
            "success": True,
            "action": "set_topmost",
            "on": bool(on),
            "window": WindowHandler._describe_hwnd(target),
        }

    @staticmethod
    def move_resize(
        x: int,
        y: int,
        width: int,
        height: int,
        hwnd: Optional[int] = None,
        process_name: Optional[str] = None,
        title_contains: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        精确摆放窗口。

        如果窗口是最大化状态，会先 SW_RESTORE 再 SetWindowPos（否则 Windows
        会忽略坐标继续保持最大化）。
        """
        target, err = WindowHandler._resolve_hwnd(hwnd, process_name, title_contains)
        if err:
            return err

        try:
            if win32gui.IsIconic(target) or _is_zoomed(target):
                win32gui.ShowWindow(target, win32con.SW_RESTORE)
        except Exception as e:
            logger.debug("[WindowHandler] pre-restore failed: %s", e)

        flags = win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE
        try:
            win32gui.SetWindowPos(target, 0, int(x), int(y), int(width), int(height), flags)
        except Exception as e:
            return {"success": False, "error": f"SetWindowPos failed: {e}"}
        return {
            "success": True,
            "action": "move_resize",
            "window": WindowHandler._describe_hwnd(target),
        }

    @staticmethod
    def list_monitors() -> Dict[str, Any]:
        """
        列出所有显示器及其工作区（排除任务栏后的可用区域）。

        返回的 id 从 1 开始，1 = 主显示器。`tile` 可以用 id 指定目标屏幕。
        """
        if not WIN32_AVAILABLE:
            return {"success": False, "error": "pywin32 not available"}
        monitors: List[Dict[str, Any]] = []
        try:
            handles = win32api.EnumDisplayMonitors(None, None)
        except Exception as e:
            return {"success": False, "error": f"EnumDisplayMonitors failed: {e}"}

        for idx, (hmon, _hdc, _rect) in enumerate(handles, start=1):
            try:
                info = win32api.GetMonitorInfo(hmon)
                mon_rect = info.get("Monitor", (0, 0, 0, 0))
                work = info.get("Work", mon_rect)
                is_primary = bool(info.get("Flags", 0) & 1)  # MONITORINFOF_PRIMARY = 1
                monitors.append({
                    "id": idx,
                    "is_primary": is_primary,
                    "device": info.get("Device", ""),
                    "bounds": {
                        "x": mon_rect[0],
                        "y": mon_rect[1],
                        "width": mon_rect[2] - mon_rect[0],
                        "height": mon_rect[3] - mon_rect[1],
                    },
                    "work_area": {
                        "x": work[0],
                        "y": work[1],
                        "width": work[2] - work[0],
                        "height": work[3] - work[1],
                    },
                })
            except Exception as e:
                logger.debug("[WindowHandler] GetMonitorInfo failed idx=%s: %s", idx, e)
        return {"success": True, "monitors": monitors, "count": len(monitors)}

    @staticmethod
    def _monitor_for_hwnd(hwnd: int) -> Optional[Dict[str, Any]]:
        """从 hwnd 反查它所在的显示器（用 MonitorFromWindow）。"""
        if not WIN32_AVAILABLE:
            return None
        try:
            MONITOR_DEFAULTTONEAREST = 2
            hmon = ctypes.windll.user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
        except Exception:
            return None
        mons = WindowHandler.list_monitors().get("monitors", [])
        # 没法直接从 hmon 拿 id，退而求其次：比较 window 中心点落在哪个 monitor bounds 里
        try:
            rect = win32gui.GetWindowRect(hwnd)
            cx = (rect[0] + rect[2]) // 2
            cy = (rect[1] + rect[3]) // 2
        except Exception:
            return mons[0] if mons else None
        for m in mons:
            b = m["bounds"]
            if b["x"] <= cx < b["x"] + b["width"] and b["y"] <= cy < b["y"] + b["height"]:
                return m
        return mons[0] if mons else None

    @staticmethod
    def capture(
        scope: str = "window",
        hwnd: Optional[int] = None,
        process_name: Optional[str] = None,
        title_contains: Optional[str] = None,
        monitor_id: Optional[int] = None,
        prefer_printwindow: bool = False,
        compress: bool = True,
    ) -> Dict[str, Any]:
        """
        统一截图入口，scope 决定截图范围：

        - "window":      单窗口。通过 hwnd 或 process_name+title_contains 定位。
                         **不抢焦点**（PrintWindow 优先，必要时回退 ImageGrab）。
        - "monitor":     整个显示器。默认用 hwnd 所在显示器，没有 hwnd 时看
                         monitor_id（默认主显示器）。含任务栏和桌面上其它窗口，
                         这正是跨软件协作要的。
        - "all_screens": 所有显示器拼起来的虚拟桌面（多屏环境适用）。

        Returns:
            { success, scope, image_data (base64), width, height,
              compressed_size_kb, context: {...} }
        """
        if not _PIL_AVAILABLE:
            return {"success": False, "error": "PIL not available"}
        if not WIN32_AVAILABLE:
            return {"success": False, "error": "pywin32 not available"}

        import base64 as _b64
        from io import BytesIO as _BytesIO
        # 用现成的压缩策略：窗口截图和全屏/整屏截图走不同 preset
        try:
            from controllers.computer_use.win_executor.handlers.image_utils import (
                compress_screenshot_from_pil,
                compress_fullscreen_screenshot,
            )
        except Exception as e:
            return {"success": False, "error": f"compression helper unavailable: {e}"}

        scope = (scope or "window").lower()
        img = None
        context: Dict[str, Any] = {"scope": scope}

        if scope == "window":
            target, err = WindowHandler._resolve_hwnd(
                hwnd=hwnd, process_name=process_name, title_contains=title_contains,
            )
            if err:
                return err
            img = capture_hwnd_image(int(target), prefer_printwindow=prefer_printwindow)
            if img is None:
                return {
                    "success": False,
                    "error": "failed to capture window (both PrintWindow and ImageGrab failed)",
                    "context": {"hwnd": int(target)},
                }
            try:
                context["hwnd"] = int(target)
                context["title"] = win32gui.GetWindowText(int(target))
            except Exception:
                pass

        elif scope == "monitor":
            mon = None
            # 1) 明确指定 monitor_id 优先
            if monitor_id is not None:
                all_mons = WindowHandler.list_monitors().get("monitors", [])
                mon = next((m for m in all_mons if m["id"] == monitor_id), None)
                if mon is None:
                    return {"success": False, "error": f"monitor_id {monitor_id} not found"}
            # 2) 没指定就用 hwnd 所在显示器
            elif hwnd is not None or process_name or title_contains:
                target, err = WindowHandler._resolve_hwnd(
                    hwnd=hwnd, process_name=process_name, title_contains=title_contains,
                )
                if err is None:
                    mon = WindowHandler._monitor_for_hwnd(int(target))
            # 3) 都没给就主显示器
            if mon is None:
                all_mons = WindowHandler.list_monitors().get("monitors", [])
                mon = next((m for m in all_mons if m["is_primary"]), all_mons[0] if all_mons else None)
            if mon is None:
                return {"success": False, "error": "no monitor available"}
            b = mon["bounds"]
            rect = (b["x"], b["y"], b["x"] + b["width"], b["y"] + b["height"])
            img = _imagegrab_region(rect)
            if img is None:
                return {"success": False, "error": "ImageGrab failed for monitor"}
            context["monitor_id"] = mon["id"]
            context["monitor_bounds"] = b

        elif scope == "all_screens":
            try:
                img = ImageGrab.grab(all_screens=True)
            except Exception as e:
                return {"success": False, "error": f"ImageGrab(all_screens) failed: {e}"}
            context["virtual_desktop"] = {"width": img.width, "height": img.height}

        else:
            return {"success": False, "error": f"unknown scope: {scope!r}"}

        original_w, original_h = img.size

        # 压缩策略：window 保细节，monitor / all_screens 走全屏 preset（更激进）
        if compress:
            if scope == "window":
                compressed_bytes = compress_screenshot_from_pil(img)
            else:
                buf = _BytesIO()
                img.save(buf, format="PNG")
                compressed_bytes = compress_fullscreen_screenshot(buf.getvalue())
            image_data = _b64.b64encode(compressed_bytes).decode()
            size_kb = len(compressed_bytes) / 1024
        else:
            buf = _BytesIO()
            img.save(buf, format="PNG", optimize=True)
            raw = buf.getvalue()
            image_data = _b64.b64encode(raw).decode()
            size_kb = len(raw) / 1024

        return {
            "success": True,
            "action": "capture",
            "scope": scope,
            "image_data": image_data,
            "width": original_w,
            "height": original_h,
            "compressed": compress,
            "compressed_size_kb": round(size_kb, 1),
            "context": context,
        }

    @staticmethod
    def _normalize_ratios(ratios: Optional[List[float]], n: int) -> Optional[List[float]]:
        """
        把任意正数列表规整为总和 = 1 的比例列表。

        - 允许传整数（如 [4, 1]）或小数（如 [0.8, 0.2]）
        - 长度必须等于 n；否则返回 None 表示无效
        - 任意 <=0 的值被视为非法，返回 None
        """
        if not ratios:
            return None
        if len(ratios) != n:
            return None
        try:
            floats = [float(r) for r in ratios]
        except (TypeError, ValueError):
            return None
        if any(r <= 0 for r in floats):
            return None
        total = sum(floats)
        return [r / total for r in floats]

    @staticmethod
    def _split_range(
        start: int,
        length: int,
        fractions: List[float],
    ) -> List[Tuple[int, int]]:
        """
        把 [start, start+length) 按 fractions（已归一化）切成多段 (offset, size)。
        保证最后一段吞掉所有舍入误差，避免留缝/越界。
        """
        result: List[Tuple[int, int]] = []
        running = 0
        for i, f in enumerate(fractions):
            if i == len(fractions) - 1:
                size = length - running
            else:
                size = int(round(length * f))
            result.append((start + running, size))
            running += size
        return result

    @staticmethod
    def _grid_slots(
        work: Dict[str, int],
        cols: int,
        rows: int,
        n: int,
    ) -> List[Tuple[int, int, int, int]]:
        """按 cols×rows 均匀网格返回前 n 个 slot（row-major，左上起 → 右下）。"""
        x, y, w, h = work["x"], work["y"], work["width"], work["height"]
        col_w = w // cols
        row_h = h // rows
        slots: List[Tuple[int, int, int, int]] = []
        for r in range(rows):
            for c in range(cols):
                cw = (w - c * col_w) if c == cols - 1 else col_w
                rh = (h - r * row_h) if r == rows - 1 else row_h
                slots.append((x + c * col_w, y + r * row_h, cw, rh))
                if len(slots) >= n:
                    return slots
        return slots[:n]

    @staticmethod
    def _compute_tile_slots(
        work: Dict[str, int],
        layout: str,
        n: int,
        ratios: Optional[List[float]] = None,
    ) -> List[Tuple[int, int, int, int]]:
        """
        给定工作区 + 布局 + 窗口数，计算每个窗口的 (x, y, w, h)。

        支持的 layout（按类别）:

        单窗口 snap 预设（多余 hwnd 会被丢进 skipped）:
            full, left_half, right_half, top_half, bottom_half,
            top_left, top_right, bottom_left, bottom_right, center

        等分（支持 ratios 非对称分）:
            left_right (2), top_bottom (2),
            vertical_3 / horizontal_3 (3),
            vertical_n / horizontal_n (N = len(hwnds))

        网格:
            grid_2x2 (4), grid_2x3 (6), grid_3x2 (6), grid_3x3 (9)

        主从（hwnd[0] = main，其余堆在 stack 侧；ratios 传 2 元，为 main:stack 宽/高比）:
            main_left, main_right, main_top, main_bottom

        auto 兜底: 1=full, 2=left_right, 3=vertical_3, 4=grid_2x2,
                   5-6=grid_3x2, 7-9=grid_3x3, 10+=vertical_n
        """
        x, y, w, h = work["x"], work["y"], work["width"], work["height"]
        layout = (layout or "auto").lower()

        # ----- auto -----
        if layout == "auto":
            if n <= 1:
                layout = "full"
            elif n == 2:
                layout = "left_right"
            elif n == 3:
                layout = "vertical_3"
            elif n == 4:
                layout = "grid_2x2"
            elif n <= 6:
                layout = "grid_3x2"
            elif n <= 9:
                layout = "grid_3x3"
            else:
                layout = "vertical_n"

        # ========== 单窗口 snap 预设 ==========
        # 这组返回 1 个 slot；n > 1 时多余 hwnd 会在 tile() 里被标为 skipped。
        single_presets: Dict[str, Tuple[int, int, int, int]] = {
            "full":         (x,            y,            w,       h),
            "left_half":    (x,            y,            w // 2,  h),
            "right_half":   (x + w // 2,   y,            w - w // 2, h),
            "top_half":     (x,            y,            w,       h // 2),
            "bottom_half":  (x,            y + h // 2,   w,       h - h // 2),
            "top_left":     (x,            y,            w // 2,  h // 2),
            "top_right":    (x + w // 2,   y,            w - w // 2, h // 2),
            "bottom_left":  (x,            y + h // 2,   w // 2,  h - h // 2),
            "bottom_right": (x + w // 2,   y + h // 2,   w - w // 2, h - h // 2),
        }
        if layout in single_presets:
            return [single_presets[layout]]
        if layout == "center":
            # 以工作区为基准居中 60%×60%
            cw, ch = int(w * 0.6), int(h * 0.6)
            return [(x + (w - cw) // 2, y + (h - ch) // 2, cw, ch)]

        # ========== 等分（含 ratios）==========
        if layout in ("left_right", "vertical_n"):
            count = max(n, 1)
            fractions = (
                WindowHandler._normalize_ratios(ratios, count)
                or [1.0 / count] * count
            )
            slices = WindowHandler._split_range(x, w, fractions)
            return [(sx, y, sw, h) for sx, sw in slices]

        if layout in ("top_bottom", "horizontal_n"):
            count = max(n, 1)
            fractions = (
                WindowHandler._normalize_ratios(ratios, count)
                or [1.0 / count] * count
            )
            slices = WindowHandler._split_range(y, h, fractions)
            return [(x, sy, w, sh) for sy, sh in slices]

        if layout == "vertical_3":
            count = min(n, 3)
            fractions = (
                WindowHandler._normalize_ratios(ratios, count)
                or [1.0 / count] * count
            )
            slices = WindowHandler._split_range(x, w, fractions)
            return [(sx, y, sw, h) for sx, sw in slices][:n]

        if layout == "horizontal_3":
            count = min(n, 3)
            fractions = (
                WindowHandler._normalize_ratios(ratios, count)
                or [1.0 / count] * count
            )
            slices = WindowHandler._split_range(y, h, fractions)
            return [(x, sy, w, sh) for sy, sh in slices][:n]

        # ========== 网格 ==========
        grid_specs: Dict[str, Tuple[int, int]] = {
            "grid_2x2": (2, 2),
            "grid_2x3": (2, 3),  # 2 列 × 3 行
            "grid_3x2": (3, 2),  # 3 列 × 2 行
            "grid_3x3": (3, 3),
        }
        if layout in grid_specs:
            cols, rows = grid_specs[layout]
            return WindowHandler._grid_slots(work, cols, rows, min(n, cols * rows))

        # ========== 主从（main + stack） ==========
        # hwnd[0] = main（大的），hwnd[1:] 均分 stack 侧。
        # ratios 传 2 元就是 main:stack 的比例（默认 [2, 1] ≈ 67/33）
        if layout in ("main_left", "main_right", "main_top", "main_bottom"):
            if n <= 1:
                return [(x, y, w, h)]
            main_frac = 2.0 / 3.0
            if ratios and len(ratios) == 2:
                norm = WindowHandler._normalize_ratios(ratios, 2)
                if norm:
                    main_frac = norm[0]
            stack_n = n - 1

            if layout == "main_left":
                main_w = int(w * main_frac)
                stack_w = w - main_w
                slots = [(x, y, main_w, h)]
                ys = WindowHandler._split_range(y, h, [1.0 / stack_n] * stack_n)
                slots.extend((x + main_w, sy, stack_w, sh) for sy, sh in ys)
                return slots
            if layout == "main_right":
                main_w = int(w * main_frac)
                stack_w = w - main_w
                stack_slots: List[Tuple[int, int, int, int]] = []
                ys = WindowHandler._split_range(y, h, [1.0 / stack_n] * stack_n)
                for sy, sh in ys:
                    stack_slots.append((x, sy, stack_w, sh))
                # hwnd[0] 依然是 main 放在右侧；stack 占左
                slots = [(x + stack_w, y, main_w, h)] + stack_slots
                return slots
            if layout == "main_top":
                main_h = int(h * main_frac)
                stack_h = h - main_h
                slots = [(x, y, w, main_h)]
                xs = WindowHandler._split_range(x, w, [1.0 / stack_n] * stack_n)
                slots.extend((sx, y + main_h, sw, stack_h) for sx, sw in xs)
                return slots
            # main_bottom
            main_h = int(h * main_frac)
            stack_h = h - main_h
            stack_slots = []
            xs = WindowHandler._split_range(x, w, [1.0 / stack_n] * stack_n)
            for sx, sw in xs:
                stack_slots.append((sx, y, sw, stack_h))
            slots = [(x, y + stack_h, w, main_h)] + stack_slots
            return slots

        # 未知 layout，兜底按 auto 分
        return WindowHandler._compute_tile_slots(work, "auto", n, ratios)

    @staticmethod
    def _parse_zones(
        work: Dict[str, int],
        zones: List[Dict[str, Any]],
    ) -> Tuple[List[Tuple[int, int, int, int]], Optional[str]]:
        """
        把自定义 zones 转成绝对像素 slot。

        zones 每项 dict 必须含 x / y / width / height 四个 number。
        所有值当作工作区的 0~1 比例解释（例：{"x":0,"y":0,"width":0.8,"height":1}）。
        这样避免多显示器 / 不同分辨率下硬编码像素的坑。

        Returns:
            (slots, err_message_or_None)
        """
        if not zones:
            return [], "zones must be a non-empty list"
        wx, wy, ww, wh = work["x"], work["y"], work["width"], work["height"]
        slots: List[Tuple[int, int, int, int]] = []
        for i, z in enumerate(zones):
            if not isinstance(z, dict):
                return [], f"zones[{i}] must be an object with x/y/width/height"
            try:
                zx = float(z.get("x", 0))
                zy = float(z.get("y", 0))
                zw = float(z.get("width", 0))
                zh = float(z.get("height", 0))
            except (TypeError, ValueError):
                return [], f"zones[{i}] has non-numeric fields"
            for name, val in (("x", zx), ("y", zy), ("width", zw), ("height", zh)):
                if val < 0 or val > 1:
                    return [], (
                        f"zones[{i}].{name}={val} out of range. "
                        "All zone values must be proportions in [0, 1] relative to work area."
                    )
            if zw <= 0 or zh <= 0:
                return [], f"zones[{i}] width/height must be > 0"
            slots.append((
                wx + int(round(ww * zx)),
                wy + int(round(wh * zy)),
                max(1, int(round(ww * zw))),
                max(1, int(round(wh * zh))),
            ))
        return slots, None

    @staticmethod
    def tile(
        hwnds: List[int],
        layout: str = "auto",
        monitor_id: Optional[int] = None,
        ratios: Optional[List[float]] = None,
        zones: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        把多个窗口按指定布局在目标显示器的工作区内平铺。

        Args:
            hwnds: 要平铺的窗口句柄列表。顺序决定放置位置（左→右，上→下）。
                   单个 hwnd 失效不会让整个调用失败，会记到 errors 里继续处理其它。
            layout: 布局名（详见 _compute_tile_slots）。给了 zones 时此参数被忽略。
            monitor_id: 显示器 id（从 list_monitors 拿），None = 主显示器
            ratios: 可选非对称比例数组。支持整数（[4,1]）或小数（[0.8,0.2]）。
                    仅作用于 left_right / top_bottom / vertical_3 / horizontal_3 /
                    vertical_n / horizontal_n / main_* 等可分比例的 layout。
            zones: 完全自定义矩形列表。每项 {x, y, width, height}，值都是
                   0~1 之间的比例（相对工作区）。给了 zones 就完全无视 layout / ratios。
                   例：[{"x":0,"y":0,"width":0.8,"height":1},
                        {"x":0.8,"y":0,"width":0.2,"height":1}]

        Returns:
            {
              "success": bool,        # 只要至少一个窗口被成功摆好就是 True
              "layout": ..., "monitor_id": ..., "work_area": {...},
              "placed": [{"hwnd", "rect", "title"}, ...],
              "skipped": [{"hwnd", "reason"}, ...],    # 无效 hwnd 或 slot 不足
              "errors":  [{"hwnd", "error"}, ...],     # SetWindowPos 真的抛了
            }
        """
        if not WIN32_AVAILABLE:
            return {"success": False, "error": "pywin32 not available"}
        if not hwnds or not isinstance(hwnds, list):
            return {"success": False, "error": "hwnds must be a non-empty list"}

        # 关键改动：对无效 hwnd 容错，不再让单个 bad hwnd 把整个 tile 搞挂。
        # Office / Electron 启动时 hwnd 短暂变化是常事，AI 拿到的句柄
        # 到执行时可能已经失效（比如 splash screen 先消失）。
        valid: List[int] = []
        skipped: List[Dict[str, Any]] = []
        for h in hwnds:
            try:
                h_int = int(h)
            except (TypeError, ValueError):
                skipped.append({"hwnd": h, "reason": "not an int"})
                continue
            if not win32gui.IsWindow(h_int):
                skipped.append({"hwnd": h_int, "reason": "hwnd no longer valid (window closed?)"})
                continue
            valid.append(h_int)

        if not valid:
            return {
                "success": False,
                "error": "all provided hwnds are invalid",
                "skipped": skipped,
            }

        # 选显示器
        mon_result = WindowHandler.list_monitors()
        if not mon_result.get("success"):
            return mon_result
        monitors = mon_result.get("monitors", [])
        if not monitors:
            return {"success": False, "error": "no monitors detected"}

        if monitor_id is not None:
            target_mon = next((m for m in monitors if m["id"] == monitor_id), None)
            if target_mon is None:
                return {"success": False, "error": f"monitor_id {monitor_id} not found"}
        else:
            target_mon = next((m for m in monitors if m["is_primary"]), monitors[0])

        work = target_mon["work_area"]

        # ---- 计算 slots：zones 优先（自定义矩形），否则按 layout + ratios ----
        slots: List[Tuple[int, int, int, int]] = []
        layout_used = layout
        ratio_warning: Optional[str] = None
        effective_ratios: Optional[List[float]] = None

        if zones:
            parsed, z_err = WindowHandler._parse_zones(work, zones)
            if z_err:
                return {"success": False, "error": f"invalid zones: {z_err}"}
            slots = parsed
            layout_used = "zones"
        else:
            # ratios 长度必须等于 valid（不是原始 hwnds）。若传了但对不上，
            # 降级回等分并在 warning 里告知。
            if ratios is not None:
                # main_* 的 ratios 只需要 2 元（main, stack），单独处理
                is_main_stack = (layout or "").lower().startswith("main_")
                expected = 2 if is_main_stack else len(valid)
                if len(ratios) != expected:
                    ratio_warning = (
                        f"ratios length ({len(ratios)}) != expected ({expected}) for layout={layout}; "
                        f"falling back to default proportions"
                    )
                else:
                    normalized = WindowHandler._normalize_ratios(ratios, expected)
                    if normalized is None:
                        ratio_warning = (
                            "ratios contain non-positive or invalid values; "
                            "falling back to default proportions"
                        )
                    else:
                        effective_ratios = normalized

            slots = WindowHandler._compute_tile_slots(
                work, layout or "auto", len(valid), effective_ratios,
            )

        if not slots:
            return {
                "success": False,
                "error": f"no slots computed for layout={layout_used}, n={len(valid)}",
            }

        placed: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []
        flags = win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE

        # 数量不够 slot 的尾部窗口就跳过；slot 不够窗口就忽略溢出的
        for idx, hwnd in enumerate(valid[: len(slots)]):
            slot = slots[idx]
            target_rect = {"x": slot[0], "y": slot[1], "width": slot[2], "height": slot[3]}
            try:
                # 先解除最小化/最大化，否则 SetWindowPos 对 maximized 窗口无效
                if win32gui.IsIconic(hwnd) or _is_zoomed(hwnd):
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                win32gui.SetWindowPos(hwnd, 0, slot[0], slot[1], slot[2], slot[3], flags)

                # 读一下实际结果——有些窗口有 minWidth/minHeight 限制，
                # SetWindowPos 会被窗口的 WM_GETMINMAXINFO 拒绝部分缩放
                try:
                    real_rect = win32gui.GetWindowRect(hwnd)
                    real = {
                        "x": real_rect[0],
                        "y": real_rect[1],
                        "width": real_rect[2] - real_rect[0],
                        "height": real_rect[3] - real_rect[1],
                    }
                except Exception:
                    real = target_rect

                entry: Dict[str, Any] = {
                    "hwnd": hwnd,
                    "rect": real,
                    "target_rect": target_rect,
                    "title": win32gui.GetWindowText(hwnd),
                }
                # 实际尺寸和目标差太大，很可能是被窗口自己的 minWidth 拒绝了
                if abs(real["width"] - target_rect["width"]) > 20 or \
                   abs(real["height"] - target_rect["height"]) > 20:
                    entry["size_mismatch"] = True
                placed.append(entry)
            except Exception as e:
                logger.warning("[WindowHandler] tile hwnd=%s failed: %s", hwnd, e)
                errors.append({"hwnd": hwnd, "target_rect": target_rect, "error": str(e)})

        # 超过 slots 数的尾部 hwnd 也算 skipped（常见于 single-window preset 传了多个 hwnd）
        overflow = valid[len(slots):]
        for h in overflow:
            skipped.append({
                "hwnd": h,
                "reason": (
                    f"layout={layout_used} only has {len(slots)} slot(s); "
                    f"extra hwnd skipped"
                ),
            })

        result: Dict[str, Any] = {
            "success": len(placed) > 0,
            "action": "tile",
            "layout": layout_used,
            "ratios": effective_ratios,
            "monitor_id": target_mon["id"],
            "work_area": work,
            "placed": placed,
            "skipped": skipped,
            "errors": errors,
        }
        if ratio_warning:
            result["warning"] = ratio_warning
        return result
