"""
鼠标操作处理器

坐标系说明：
    所有坐标均为 **逻辑坐标 (logical pixel)**，与 pynput 坐标系一致。
    逻辑分辨率 = win32api.GetSystemMetrics(SM_CXSCREEN/SM_CYSCREEN)
    例如：2560x1440 物理分辨率 + 125% 缩放 = 2048x1152 逻辑分辨率
    
    通过 SetProcessDpiAwareness(0) 显式设置进程为 DPI 不感知，
    确保 pynput 和 win32api 使用逻辑坐标。
"""
import ctypes
import logging
import math
import time
from typing import Dict, Any, Optional, List, Tuple

from ..core.dependencies import (
    PYNPUT_AVAILABLE, WINDOWS_API_AVAILABLE,
    mouse, MouseButton, win32gui
)

logger = logging.getLogger(__name__)

# 设置进程 DPI 不感知，确保使用逻辑坐标
# PROCESS_DPI_UNAWARE = 0
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(0)
    logger.info("Set process DPI awareness to UNAWARE (logical coordinates)")
except Exception as e:
    # 可能已经设置过，或者 Windows 版本不支持
    logger.debug(f"SetProcessDpiAwareness failed (may already be set): {e}")

# 拖拽配置
DRAG_DELAY = 0.05  # 基础延迟时间（秒）
DRAG_SPEED = 300   # 拖拽速度（像素/秒），降低以便观察
DRAG_MIN_STEP_DELAY = 0.008  # 最小步进延迟（秒）
DRAG_EASE_DISTANCE = 80  # 起点/终点减速区域（像素）

# 平滑移动配置
MOVE_SPEED = 1200        # 鼠标移动速度（像素/秒）
MOVE_MIN_DURATION = 0.06 # 最小移动时间（秒），短距离不会太快
MOVE_MAX_DURATION = 0.4  # 最大移动时间（秒），长距离不会太慢
MOVE_STEP_INTERVAL = 0.008  # 步进间隔（秒）
CLICK_SETTLE_DELAY = 0.5  # 到达目标后、点击前的停顿（秒）

# Windows mouse_event flags
_MOUSEEVENTF_MOVE = 0x0001
_MOUSEEVENTF_ABSOLUTE = 0x8000

# 缓存逻辑屏幕尺寸（进程生命周期内不变）
_screen_w: int = 0
_screen_h: int = 0


def _get_screen_size() -> tuple:
    """获取并缓存逻辑屏幕尺寸"""
    global _screen_w, _screen_h
    if _screen_w <= 0 or _screen_h <= 0:
        _screen_w = ctypes.windll.user32.GetSystemMetrics(0)  # SM_CXSCREEN
        _screen_h = ctypes.windll.user32.GetSystemMetrics(1)  # SM_CYSCREEN
    return _screen_w, _screen_h


def _move_cursor(x: int, y: int):
    """
    移动光标并注入输入事件，兼顾精度与录屏兼容性。
    
    1. mouse_event(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE):
       向 Windows 输入队列注入 WM_MOUSEMOVE 事件，
       使 Focusee 等通过低级鼠标钩子捕获的录屏软件能感知移动轨迹。
       但 MOUSEEVENTF_ABSOLUTE 的 [0,65536] 归一化在 DPI 缩放下可能有像素偏差。
    2. SetCursorPos(x, y):
       校正光标到精确的逻辑像素位置，确保 GetCursorPos 返回值与预期一致，
       避免后续 _smooth_move_to 读取起点时产生累积偏移。
    """
    sw, sh = _get_screen_size()
    norm_x = int(x * 65536 / sw)
    norm_y = int(y * 65536 / sh)
    ctypes.windll.user32.mouse_event(
        _MOUSEEVENTF_MOVE | _MOUSEEVENTF_ABSOLUTE,
        norm_x, norm_y, 0, 0
    )
    ctypes.windll.user32.SetCursorPos(x, y)


def _debug_circle(cx: int, cy: int, radius: int = 30, steps: int = 40, delay: float = 0.03):
    """在指定位置画一个圈，用于调试起点坐标"""
    for i in range(steps + 1):
        angle = 2 * math.pi * i / steps
        px = int(cx + radius * math.cos(angle))
        py = int(cy + radius * math.sin(angle))
        _move_cursor(px, py)
        time.sleep(delay)
    _move_cursor(cx, cy)


def _nudge_cursor():
    """微小抖动，用于唤醒录屏软件的鼠标事件捕获"""
    ctypes.windll.user32.mouse_event(_MOUSEEVENTF_MOVE, 2, 0, 0, 0)
    time.sleep(0.005)
    ctypes.windll.user32.mouse_event(_MOUSEEVENTF_MOVE, -2, 0, 0, 0)
    time.sleep(0.005)


def _smooth_move_to(target_x: int, target_y: int):
    """匀速直线移动鼠标到目标位置"""
    _nudge_cursor()

    current_x, current_y = mouse.position
    logger.info(f"[_smooth_move_to] start=({current_x},{current_y}) target=({target_x},{target_y})")

    distance = math.sqrt((target_x - current_x) ** 2 + (target_y - current_y) ** 2)

    if distance < 2:
        _move_cursor(target_x, target_y)
        return

    duration = max(MOVE_MIN_DURATION, min(distance / MOVE_SPEED, MOVE_MAX_DURATION))
    steps = max(int(duration / MOVE_STEP_INTERVAL), 5)

    for i in range(1, steps + 1):
        t = i / steps
        # ease-out cubic: 快起慢停
        t = 1.0 - (1.0 - t) ** 3
        px = int(current_x + (target_x - current_x) * t)
        py = int(current_y + (target_y - current_y) * t)
        _move_cursor(px, py)
        time.sleep(duration / steps)

    _move_cursor(target_x, target_y)


def _map_button(button: str) -> "MouseButton":
    """映射按钮字符串到 pynput MouseButton"""
    b = (button or "left").lower()
    if b == "left":
        return MouseButton.left
    if b == "right":
        return MouseButton.right
    if b == "middle":
        return MouseButton.middle
    return MouseButton.left


class MouseHandler:
    """
    鼠标操作处理器
    
    所有坐标均为逻辑坐标 (logical pixel)
    """
    
    @staticmethod
    def click(x: Optional[int] = None, y: Optional[int] = None, button: str = "left") -> Dict[str, Any]:
        """
        单击
        
        Args:
            x, y: 逻辑坐标 (logical pixel)
            button: 鼠标按钮
        """
        if not PYNPUT_AVAILABLE:
            return {"success": False, "error": "pynput not available"}
        if x is not None and y is not None:
            _smooth_move_to(int(x), int(y))
            time.sleep(CLICK_SETTLE_DELAY)
        mouse.click(_map_button(button))
        return {"success": True}
    
    @staticmethod
    def double_click(x: Optional[int] = None, y: Optional[int] = None, button: str = "left") -> Dict[str, Any]:
        """
        双击
        
        Args:
            x, y: 逻辑坐标 (logical pixel)
            button: 鼠标按钮
        """
        if not PYNPUT_AVAILABLE:
            return {"success": False, "error": "pynput not available"}
        if x is not None and y is not None:
            _smooth_move_to(int(x), int(y))
            time.sleep(CLICK_SETTLE_DELAY)
        mouse.click(_map_button(button), 2)
        return {"success": True}
    
    @staticmethod
    def move(x: int, y: int) -> Dict[str, Any]:
        """
        移动鼠标
        
        Args:
            x, y: 逻辑坐标 (logical pixel)
        """
        if not PYNPUT_AVAILABLE:
            return {"success": False, "error": "pynput not available"}
        _smooth_move_to(int(x), int(y))
        return {"success": True}
    
    @staticmethod
    def mouse_down(button: str = "left", x: Optional[int] = None, y: Optional[int] = None) -> Dict[str, Any]:
        """按下鼠标"""
        if not PYNPUT_AVAILABLE:
            return {"success": False, "error": "pynput not available"}
        if x is not None and y is not None:
            _smooth_move_to(int(x), int(y))
        mouse.press(_map_button(button))
        return {"success": True}
    
    @staticmethod
    def mouse_up(button: str = "left", x: Optional[int] = None, y: Optional[int] = None) -> Dict[str, Any]:
        """释放鼠标"""
        if not PYNPUT_AVAILABLE:
            return {"success": False, "error": "pynput not available"}
        if x is not None and y is not None:
            _smooth_move_to(int(x), int(y))
        mouse.release(_map_button(button))
        return {"success": True}
    
    @staticmethod
    def drag(start_x: Optional[int] = None, start_y: Optional[int] = None,
             end_x: Optional[int] = None, end_y: Optional[int] = None,
             dx: int = 0, dy: int = 0,
             path: Optional[List[Tuple[int, int]]] = None,
             button: str = "left",
             speed: Optional[float] = None) -> Dict[str, Any]:
        """
        拖拽 - 支持直线拖拽和折线路径拖拽
        
        参数:
            start_x, start_y: 起点坐标，逻辑坐标 (logical pixel)（直线模式）
            end_x, end_y: 终点坐标，逻辑坐标 (logical pixel)（直线模式）
            dx, dy: 相对偏移（直线模式）
            path: 折线路径 [(x1, y1), (x2, y2), ...]，逻辑坐标 (logical pixel)（折线模式）
            button: 鼠标按钮 (left, right, middle)
            speed: 移动速度（像素/秒），默认 300
        
        特性:
            - 固定速度移动，路径越长时间越长
            - 起点和终点区域减速，确保 UI 响应
        """
        if not PYNPUT_AVAILABLE:
            return {"success": False, "error": "pynput not available"}
        
        btn = _map_button(button)
        move_speed = speed or DRAG_SPEED
        
        # 构建路径点列表
        if path and len(path) >= 2:
            # 折线模式
            points = [(int(p[0]), int(p[1])) for p in path]
        else:
            # 直线模式
            if start_x is not None and start_y is not None:
                sx, sy = int(start_x), int(start_y)
            else:
                sx, sy = mouse.position
            
            if end_x is not None and end_y is not None:
                ex, ey = int(end_x), int(end_y)
            elif dx or dy:
                ex, ey = sx + int(dx), sy + int(dy)
            else:
                return {"success": False, "error": "No target specified"}
            
            points = [(sx, sy), (ex, ey)]
        
        if len(points) < 2:
            return {"success": False, "error": "Need at least 2 points"}
        
        # 计算总路径长度
        total_length = 0
        segments = []
        for i in range(1, len(points)):
            x1, y1 = points[i - 1]
            x2, y2 = points[i]
            seg_len = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
            segments.append((x1, y1, x2, y2, seg_len))
            total_length += seg_len
        
        if total_length == 0:
            return {"success": False, "error": "Zero length path"}
        
        # 计算总时间
        total_duration = total_length / move_speed
        
        # 1. 移动到起点
        start_pt = points[0]
        _move_cursor(start_pt[0], start_pt[1])
        time.sleep(DRAG_DELAY * 2)  # 起点等待稍长
        
        # 2. 按下鼠标
        mouse.press(btn)
        time.sleep(DRAG_DELAY * 2)  # 按下后等待稍长
        
        # 3. 沿路径移动
        accumulated_dist = 0
        
        for seg_idx, (x1, y1, x2, y2, seg_len) in enumerate(segments):
            if seg_len == 0:
                continue
            
            # 计算这段需要多少步（每 5ms 一步）
            seg_duration = (seg_len / total_length) * total_duration
            steps = max(int(seg_duration / DRAG_MIN_STEP_DELAY), 5)
            
            for step in range(1, steps + 1):
                t = step / steps
                x = int(x1 + (x2 - x1) * t)
                y = int(y1 + (y2 - y1) * t)
                
                # 计算当前位置在整条路径上的距离
                current_dist = accumulated_dist + seg_len * t
                
                # 计算速度因子（起点和终点减速）
                # 起点区域：0 -> DRAG_EASE_DISTANCE
                # 终点区域：total_length - DRAG_EASE_DISTANCE -> total_length
                speed_factor = 1.0
                
                if current_dist < DRAG_EASE_DISTANCE:
                    # 起点减速：从 0.3 加速到 1.0
                    speed_factor = 0.3 + 0.7 * (current_dist / DRAG_EASE_DISTANCE)
                elif current_dist > total_length - DRAG_EASE_DISTANCE:
                    # 终点减速：从 1.0 减速到 0.3
                    remaining = total_length - current_dist
                    speed_factor = 0.3 + 0.7 * (remaining / DRAG_EASE_DISTANCE)
                
                # 根据速度因子调整延迟（速度慢 = 延迟长）
                step_delay = (seg_duration / steps) / speed_factor
                step_delay = max(step_delay, DRAG_MIN_STEP_DELAY)
                
                _move_cursor(x, y)
                time.sleep(step_delay)
            
            accumulated_dist += seg_len
        
        # 4. 确保到达终点
        end_pt = points[-1]
        _move_cursor(end_pt[0], end_pt[1])
        time.sleep(DRAG_DELAY * 3)  # 终点等待更长，让 UI 响应
        
        # 5. 释放鼠标
        mouse.release(btn)
        time.sleep(DRAG_DELAY)
        
        return {
            "success": True,
            "path_points": len(points),
            "total_length": round(total_length, 1),
            "duration": round(total_duration, 2),
        }
    
    @staticmethod
    def drag_to(x: int, y: int) -> Dict[str, Any]:
        """
        从当前位置拖拽到指定位置
        
        Args:
            x, y: 目标位置，逻辑坐标 (logical pixel)
        """
        if not PYNPUT_AVAILABLE:
            return {"success": False, "error": "pynput not available"}
        
        current_x, current_y = mouse.position  # 逻辑坐标
        target_x, target_y = int(x), int(y)  # 逻辑坐标
        
        # 按下鼠标
        mouse.press(MouseButton.left)
        time.sleep(DRAG_DELAY)
        
        # 平滑移动
        steps = 10
        for i in range(1, steps + 1):
            ratio = i / steps
            px = int(current_x + (target_x - current_x) * ratio)
            py = int(current_y + (target_y - current_y) * ratio)
            _move_cursor(px, py)
            time.sleep(DRAG_DELAY / steps)
        
        time.sleep(DRAG_DELAY)
        
        # 释放鼠标
        mouse.release(MouseButton.left)
        return {"success": True}
    
    @staticmethod
    def scroll(dx: int = 0, dy: int = 0, x: Optional[int] = None, y: Optional[int] = None) -> Dict[str, Any]:
        """
        滚动
        
        Args:
            dx, dy: 滚动量（不是坐标）
            x, y: 滚动位置，逻辑坐标 (logical pixel)
        """
        if not PYNPUT_AVAILABLE:
            return {"success": False, "error": "pynput not available"}
        if x is not None and y is not None:
            _smooth_move_to(int(x), int(y))
        mouse.scroll(dx, dy)
        return {"success": True}
    
    @staticmethod
    def scroll_down(clicks: int = 3) -> Dict[str, Any]:
        """向下滚动"""
        if not PYNPUT_AVAILABLE:
            return {"success": False, "error": "pynput not available"}
        mouse.scroll(0, -abs(clicks))
        return {"success": True}
    
    @staticmethod
    def scroll_up(clicks: int = 3) -> Dict[str, Any]:
        """向上滚动"""
        if not PYNPUT_AVAILABLE:
            return {"success": False, "error": "pynput not available"}
        mouse.scroll(0, abs(clicks))
        return {"success": True}
    
    @staticmethod
    def get_position() -> Dict[str, Any]:
        """
        获取鼠标位置
        
        Returns:
            position: 逻辑坐标 (logical pixel)
        """
        if WINDOWS_API_AVAILABLE:
            pos = win32gui.GetCursorPos()  # 返回逻辑坐标
            return {"success": True, "position": {"x": pos[0], "y": pos[1]}}
        elif PYNPUT_AVAILABLE:
            x, y = mouse.position  # 返回逻辑坐标
            return {"success": True, "position": {"x": int(x), "y": int(y)}}
        else:
            return {"success": False, "error": "No method available"}

