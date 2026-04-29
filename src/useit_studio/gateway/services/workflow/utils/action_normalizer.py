"""
动作格式归一化 - 将 AI_Run 的 action 转换为 local_engine 可执行格式
"""
from typing import Any, Dict

from ..constants import ACTION_TYPE_ALIASES, RIGHT_CLICK_ACTIONS


def normalize_action_for_local_engine(ai_run_action: Dict[str, Any]) -> Dict[str, Any]:
    """
    将 AI_Run 的 action payload 规范化为 local_engine 可执行的 GUI action 格式
    
    处理：
    - 类型别名映射 (doubleclick -> double_click)
    - 坐标格式转换 (position/coordinate -> x/y)
    - scroll 数组转换 ([0, -3] -> scroll_x, scroll_y)
    - 右键点击处理
    
    注意：
    - 对 cua_update(code) 不会走这个函数（直接原样下发）
    - 这里只处理常见的 GUI 动作：CLICK/DOUBLE_CLICK/TYPE/SCROLL/SCREENSHOT/WAIT 等
    
    Args:
        ai_run_action: AI_Run 返回的动作
        
    Returns:
        local_engine 兼容的动作格式
    """
    if not isinstance(ai_run_action, dict):
        return {"type": "unknown"}

    # 如果已经是 local_engine 兼容格式（type 存在），尽量少改动
    raw_type = ai_run_action.get("type")
    if isinstance(raw_type, str) and raw_type.strip():
        return _normalize_typed_action(ai_run_action, raw_type.strip().lower())

    # action: "CLICK"/"TYPE"/... 格式
    act = ai_run_action.get("action")
    if isinstance(act, str) and act.strip():
        return _normalize_action_field(ai_run_action, act.strip().upper())

    # 无法识别则原样返回（让 local_engine 再尝试）
    return dict(ai_run_action)


def _normalize_typed_action(action: Dict[str, Any], action_type: str) -> Dict[str, Any]:
    """处理已有 type 字段的动作"""
    # 应用别名映射
    action_type = ACTION_TYPE_ALIASES.get(action_type, action_type)
    
    out = dict(action)
    out["type"] = action_type
    
    # position -> x/y 兼容
    _extract_coordinates(out)
    
    # scroll 数组 -> scroll_x/scroll_y 兼容
    # AI 发送格式: {"type": "scroll", "scroll": [0, -3]}
    # local_engine 期望格式: {"type": "scroll", "scroll_x": 0, "scroll_y": -3}
    scroll = out.get("scroll")
    if isinstance(scroll, (list, tuple)) and len(scroll) >= 2:
        out.setdefault("scroll_x", scroll[0])
        out.setdefault("scroll_y", scroll[1])
    
    # right_click 兜底
    if action_type in RIGHT_CLICK_ACTIONS:
        out["type"] = "click"
        out.setdefault("button", "right")
    
    return out


def _normalize_action_field(action: Dict[str, Any], action_upper: str) -> Dict[str, Any]:
    """处理 action 字段格式的动作"""
    value = action.get("value", "")
    x, y = _get_position(action)

    if action_upper in ("CLICK", "LEFT_CLICK", "RIGHT_CLICK"):
        out = {"type": "click", "button": "left" if action_upper != "RIGHT_CLICK" else "right"}
        if x is not None and y is not None:
            out["x"], out["y"] = x, y
        return out
    
    if action_upper in ("DOUBLE_CLICK", "DOUBLECLICK"):
        out = {"type": "double_click", "button": "left"}
        if x is not None and y is not None:
            out["x"], out["y"] = x, y
        return out
    
    if action_upper in ("TYPE", "TYPE_TEXT"):
        return {"type": "type", "text": str(value or "")}
    
    if action_upper == "SCROLL":
        # value 可能包含滚动信息；没有的话给默认
        scroll_amount = 300
        if str(value).strip().lstrip("-").isdigit():
            scroll_amount = int(value)
        return {"type": "scroll", "scroll_x": 0, "scroll_y": scroll_amount, "x": 0, "y": 0}
    
    if action_upper == "SCREENSHOT":
        return {"type": "screenshot"}
    
    if action_upper == "WAIT":
        try:
            sec = float(value) if str(value).strip() else 1.0
        except (TypeError, ValueError):
            sec = 1.0
        return {"type": "wait", "seconds": sec}

    # 无法识别则原样返回
    return dict(action)


def _extract_coordinates(out: Dict[str, Any]) -> None:
    """从 position/coordinate 字段提取坐标到 x/y"""
    for key in ("position", "coordinate"):
        pos = out.get(key)
        if isinstance(pos, (list, tuple)) and len(pos) >= 2:
            out.setdefault("x", pos[0])
            out.setdefault("y", pos[1])
            break


def _get_position(action: Dict[str, Any]) -> tuple:
    """获取位置坐标"""
    position = action.get("position") or action.get("coordinate") or []
    if isinstance(position, (list, tuple)) and len(position) >= 2:
        return position[0], position[1]
    return None, None
