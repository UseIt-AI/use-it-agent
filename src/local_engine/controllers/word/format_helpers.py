"""
Word 格式值转换工具。

把 Word COM 返回的"魔数式"常量值翻译成 AI / 前端能读懂的字符串或 bool。
做成模块级函数方便 snapshot 和 action_executor 都复用。
"""

from typing import Optional

from .constants import (
    ALIGNMENT_NAMES,
    LINE_SPACING_RULE_NAMES,
    WD_UNDEFINED,
)


def alignment_name(value: Optional[int]) -> str:
    """wdAlignParagraph* → 'left' / 'center' / ..."""
    if value is None:
        return "unknown"
    return ALIGNMENT_NAMES.get(value, f"unknown({value})")


def line_spacing_rule_name(value: Optional[int]) -> str:
    """wdLineSpace* → 'single' / '1.5_lines' / ..."""
    if value is None:
        return "unknown"
    return LINE_SPACING_RULE_NAMES.get(value, f"unknown({value})")


def tri_state_to_bool(value) -> Optional[bool]:
    """
    Word 的 Bold/Italic 等是三态：True/False/wdUndefined(9999999)。
    只有明确的 True/False 才转 bool，其余 None。
    """
    if value is None or value == WD_UNDEFINED:
        return None
    return bool(value)


def color_to_hex(color) -> Optional[str]:
    """
    Word 颜色是 BGR 打包的 long：0xBBGGRR。负值 / wdUndefined / None 返回 None。
    """
    if color is None or color == WD_UNDEFINED or color < 0:
        return None
    try:
        r = color & 0xFF
        g = (color >> 8) & 0xFF
        b = (color >> 16) & 0xFF
        return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:
        return None


def safe_round(value, ndigits: int = 2) -> float:
    """Word 有些格式属性在"继承"状态下为 None，round 会炸。"""
    if value is None or value == WD_UNDEFINED:
        return 0.0
    try:
        return round(float(value), ndigits)
    except Exception:
        return 0.0


def safe_font_size(size) -> Optional[float]:
    """字号读回来是 float，但混合段落会给 wdUndefined。"""
    if size is None or size == WD_UNDEFINED:
        return None
    try:
        return float(size)
    except Exception:
        return None
