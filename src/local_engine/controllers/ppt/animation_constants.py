"""
PowerPoint 动画与幻灯片切换 — COM 常量与解析

- MsoAnimEffect: https://learn.microsoft.com/en-us/office/vba/api/powerpoint.msoanimeffect
- MsoAnimateTriggerType: Sequence.AddEffect 的 Trigger 参数
- PpEntryEffect: SlideShowTransition.EntryEffect
"""

from typing import Any, Union

# ==================== MsoAnimateTriggerType ====================

MSO_ANIM_TRIGGER: dict[str, int] = {
    "on_click": 1,
    "page_click": 1,
    "click": 1,
    "with_previous": 2,
    "after_previous": 3,
}

# ==================== MsoAnimEffect（常用 + 名称即枚举名小写） ====================

MSO_ANIM_EFFECT_ALIASES: dict[str, int] = {
    # 常用别名
    "appear": 1,
    "fade": 10,
    "fly": 2,
    "float": 30,
    "wipe": 22,
    "zoom": 23,
    "split": 16,
    "wheel": 21,
    "bounce": 26,
    "swivel": 19,
    "grow_shrink": 59,
    "spin": 61,
    "teeter": 80,
    "pulse": 79,  # msoAnimEffectStyleEmphasis
    "dissolve": 9,
    "blinds": 3,
    "box": 4,
    "checkerboard": 5,
    "circle": 6,
    "crawl": 7,
    "diamond": 8,
    "peek": 12,
    "plus": 13,
    "random_bars": 14,
    "spiral": 15,
    "stretch": 17,
    "strips": 18,
    "wedge": 20,
    "flash_once": 11,
    "light_speed": 32,
    "flip": 51,
    "fold": 53,
    "glide": 49,
    "rise_up": 34,
    "swish": 35,
    "whip": 38,
    "bold_flash": 63,
    "brush_color": 66,
    "change_font_color": 56,
    "transparent": 62,
    # 与枚举名一致（节选，便于直接查文档填名）
    "mso_anim_effect_appear": 1,
    "mso_anim_effect_fade": 10,
    "mso_anim_effect_fly": 2,
    "mso_anim_effect_float": 30,
    "mso_anim_effect_wipe": 22,
    "mso_anim_effect_zoom": 23,
}


def resolve_mso_anim_effect(value: Union[str, int]) -> int:
    """解析为 MsoAnimEffect 整型；支持 int 或别名 / 枚举风格字符串。"""
    if isinstance(value, int):
        return value
    if not isinstance(value, str):
        raise ValueError(f"effect must be str or int, got {type(value)}")

    key = value.strip().lower().replace("-", "_")
    if key in MSO_ANIM_EFFECT_ALIASES:
        return MSO_ANIM_EFFECT_ALIASES[key]
    if key.isdigit():
        return int(key)
    raise ValueError(
        f"Unknown animation effect: {value!r}. "
        f"Use an integer (MsoAnimEffect) or a known alias such as fade, fly, appear. "
        f"See MS docs: MsoAnimEffect enumeration."
    )


# ==================== MsoAnimTextUnitEffect (Sequence.ConvertToTextUnitEffect) ====================
# https://learn.microsoft.com/en-us/office/vba/api/powerpoint.msoanimtextuniteffect
# 与 PpTextUnitEffect（旧 AnimationSettings）枚举值不同，勿混用。

MSO_ANIM_TEXT_UNIT_EFFECT_ALIASES: dict[str, int] = {
    "paragraph": 0,
    "by_paragraph": 0,
    "para": 0,
    "mso_anim_text_unit_effect_by_paragraph": 0,
    "character": 1,
    "by_character": 1,
    "char": 1,
    "letter": 1,
    "mso_anim_text_unit_effect_by_character": 1,
    "word": 2,
    "by_word": 2,
    "mso_anim_text_unit_effect_by_word": 2,
    "mixed": -1,
    "mso_anim_text_unit_effect_mixed": -1,
}


def resolve_mso_anim_text_unit_effect(value: Union[str, int]) -> int:
    """
    解析为 MsoAnimTextUnitEffect，供 MainSequence.ConvertToTextUnitEffect 使用。
    用于同一文本框内按段落 / 词 / 字拆分动画（与整框一次播放入场不同）。
    """
    if isinstance(value, int):
        if value in (-1, 0, 1, 2):
            return value
        raise ValueError(
            f"text_unit int must be one of -1, 0, 1, 2 (MsoAnimTextUnitEffect), got {value}"
        )
    if not isinstance(value, str):
        raise ValueError(f"text_unit must be str or int, got {type(value)}")
    key = value.strip().lower().replace("-", "_")
    if key in MSO_ANIM_TEXT_UNIT_EFFECT_ALIASES:
        return MSO_ANIM_TEXT_UNIT_EFFECT_ALIASES[key]
    if key.isdigit() or (key.startswith("-") and key[1:].isdigit()):
        return int(key)
    raise ValueError(
        f"Unknown text_unit: {value!r}. "
        f"Use: paragraph, word, character, mixed, or an integer (MsoAnimTextUnitEffect). "
        f"See MS docs: MsoAnimTextUnitEffect enumeration."
    )


def resolve_mso_anim_trigger(value: Any) -> int:
    """解析为 MsoAnimateTriggerType 整型。默认：单击开始。"""
    if value is None:
        return 1
    if isinstance(value, int):
        if value in (1, 2, 3):
            return value
        raise ValueError(f"trigger int must be 1, 2, or 3, got {value}")
    if not isinstance(value, str):
        raise ValueError(f"trigger must be str or int, got {type(value)}")
    key = value.strip().lower().replace("-", "_")
    if key in MSO_ANIM_TRIGGER:
        return MSO_ANIM_TRIGGER[key]
    raise ValueError(
        f"Unknown trigger: {value!r}. Use: on_click, with_previous, after_previous"
    )


# ==================== PpEntryEffect（幻灯片切换，常用子集） ====================

PP_ENTRY_EFFECT_ALIASES: dict[str, int] = {
    "none": 0,
    "cut": 257,
    "fade": 1793,
    "fade_smoothly": 3849,
    "dissolve": 1537,
    "push_left": 3853,
    "push_right": 3854,
    "push_up": 3855,
    "push_down": 3852,
    "wipe_left": 2817,
    "wipe_right": 2819,
    "wipe_up": 2818,
    "wipe_down": 2820,
    "split_horizontal_in": 3586,
    "split_vertical_in": 3588,
    "random": 513,
    "blinds_horizontal": 769,
    "blinds_vertical": 770,
    "cover_left": 1281,
    "cover_right": 1283,
    "uncover_left": 2049,
    "fly_from_left": 3329,
    "fly_from_right": 3331,
    "fly_from_bottom": 3332,
    "zoom_in": 3345,
    "zoom_out": 3347,
    "cube_left": 3914,
    "cube_right": 3916,
    "flip_left": 3905,
}


def resolve_pp_entry_effect(value: Union[str, int]) -> int:
    """解析为 PpEntryEffect（幻灯片切换效果）。"""
    if isinstance(value, int):
        return value
    if not isinstance(value, str):
        raise ValueError(f"transition must be str or int, got {type(value)}")
    key = value.strip().lower().replace("-", "_")
    if key in PP_ENTRY_EFFECT_ALIASES:
        return PP_ENTRY_EFFECT_ALIASES[key]
    if key.isdigit():
        return int(key)
    raise ValueError(
        f"Unknown slide transition: {value!r}. "
        f"Use an integer (PpEntryEffect) or a known name: none, fade, push_left, wipe_left, ..."
    )
