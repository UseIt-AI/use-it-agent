"""
PPT COM Constants and Type Mappings

集中管理所有 PowerPoint COM 自动化所需的常量和映射表。
"""

# ==================== Slide Layouts ====================

SLIDE_LAYOUTS = {
    "blank": 12,
    "title": 1,
    "title_and_content": 2,
    "section_header": 3,
    "two_content": 4,
    "comparison": 5,
    "title_only": 11,
    "content_with_caption": 7,
    "picture_with_caption": 8,
}

# ==================== AutoShape Types (msoAutoShapeType) ====================

SHAPE_TYPES = {
    "rectangle": 1,
    "rounded_rectangle": 5,
    "oval": 9,
    "diamond": 4,
    "triangle": 7,
    "right_triangle": 6,
    "parallelogram": 2,
    "trapezoid": 3,
    "pentagon": 56,
    "hexagon": 10,
    "octagon": 57,
    "cross": 11,
    "star_5": 12,
    "star_4": 91,
    "right_arrow": 33,
    "left_arrow": 34,
    "up_arrow": 35,
    "down_arrow": 36,
    "left_right_arrow": 37,
    "up_down_arrow": 38,
    "callout_rectangle": 105,
    "callout_rounded_rectangle": 106,
    "callout_oval": 107,
    "callout_cloud": 108,
    "heart": 21,
    "lightning_bolt": 22,
    "sun": 23,
    "moon": 24,
    "arc": 25,
    "line_callout_1": 109,
    "chevron": 52,
    "cube": 14,
    "can": 13,
    "donut": 18,
    "no_symbol": 19,
    "block_arc": 20,
    "smiley_face": 17,
}

# ==================== Chart Types (xlChartType) ====================

CHART_TYPES = {
    "column_clustered": 51,
    "column_stacked": 52,
    "column_100_stacked": 53,
    "bar_clustered": 57,
    "bar_stacked": 58,
    "bar_100_stacked": 59,
    "line": 4,
    "line_markers": 65,
    "line_stacked": 63,
    "pie": 5,
    "pie_exploded": 69,
    "pie_3d": -4102,
    "doughnut": -4120,
    "doughnut_exploded": 80,
    "area": 1,
    "area_stacked": 76,
    "xy_scatter": -4169,
    "xy_scatter_lines": 74,
    "xy_scatter_smooth": 72,
    "radar": -4151,
    "radar_filled": 82,
    "bubble": 15,
    "stock_hlc": 88,
    "treemap": 117,
    "sunburst": 120,
    "waterfall": 119,
    "funnel": 123,
    "combo": -4152,
}

# ==================== Placeholder Types ====================

PLACEHOLDER_TYPES = {
    1: "title",
    2: "body",
    3: "center_title",
    4: "subtitle",
    5: "vertical_title",
    6: "vertical_body",
    7: "object",
    8: "chart",
    9: "bitmap",
    10: "media_clip",
    11: "org_chart",
    12: "table",
    13: "slide_number",
    14: "header",
    15: "footer",
    16: "date",
}

# ==================== Text Alignment ====================

TEXT_ALIGN = {
    "left": 1,        # ppAlignLeft
    "center": 2,      # ppAlignCenter
    "right": 3,       # ppAlignRight
    "justify": 4,     # ppAlignJustify
    "distribute": 5,  # ppAlignDistribute
}

# ==================== Text Orientation ====================
MSO_TEXT_ORIENTATION_HORIZONTAL = 1

# ==================== Shape Type IDs (msoShapeType, for reading) ====================

SHAPE_TYPE_NAMES = {
    1: "auto_shape",
    2: "callout",
    3: "chart",
    4: "comment",
    5: "freeform",
    6: "group",
    7: "embedded_ole_object",
    8: "form_control",
    9: "line",
    10: "linked_ole_object",
    11: "linked_picture",
    12: "ole_control_object",
    13: "picture",
    14: "placeholder",
    15: "text_effect",
    16: "media",
    17: "textbox",
    18: "script_anchor",
    19: "table",
    20: "canvas",
    21: "diagram",
    22: "ink",
    23: "ink_comment",
    24: "smart_art",
    25: "slicer",
    26: "web_video",
    27: "content_app",
    28: "graphic",
    29: "linked_graphic",
    30: "3d_model",
    31: "linked_3d_model",
}

# ==================== Z-Order Commands (MsoZOrderCmd) ====================

Z_ORDER_COMMANDS = {
    "bring_to_front": 0,     # msoBringToFront
    "send_to_back": 1,       # msoSendToBack
    "bring_forward": 2,      # msoBringForward
    "send_backward": 3,      # msoSendBackward
}

# ==================== Gradient Styles (MsoGradientStyle) ====================

MSO_GRADIENT_HORIZONTAL = 1       # msoGradientHorizontal
MSO_GRADIENT_FROM_CENTER = 7      # msoGradientFromCenter

# ==================== Line Dash Styles ====================

LINE_DASH_STYLES = {
    "solid": 1,         # msoLineSolid
    "dash": 4,          # msoLineDash
    "dot": 3,           # msoLineSquareDot
    "dash_dot": 5,      # msoLineDashDot
    "dash_dot_dot": 6,  # msoLineDashDotDot
    "long_dash": 7,     # msoLineLongDash
    "round_dot": 2,     # msoLineRoundDot
}

# ==================== Alignment (msoAlignCmd) ====================

ALIGN_TYPES = {
    "left": 0,           # msoAlignLefts
    "center": 1,         # msoAlignCenters
    "right": 2,          # msoAlignRights
    "top": 3,            # msoAlignTops
    "middle": 4,         # msoAlignMiddles
    "bottom": 5,         # msoAlignBottoms
}

# ==================== Distribute (msoDistributeCmd) ====================

DISTRIBUTE_TYPES = {
    "horizontal": 0,     # msoDistributeHorizontally
    "vertical": 1,       # msoDistributeVertically
}

# ==================== Animation Effects (MsoAnimEffect) ====================

ANIMATION_EFFECTS = {
    # Entrance
    "appear": 1,
    "fly": 2,
    "blinds": 3,
    "box": 4,
    "checkerboard": 5,
    "diamond": 8,
    "dissolve": 9,
    "fade": 10,
    "flash_once": 11,
    "peek": 12,
    "split": 13,
    "random_bars": 15,
    "wheel": 21,
    "wipe": 22,
    "strips": 23,
    "random": 24,
    "bounce": 25,
    "grow_and_turn": 26,
    "float": 42,
    "swivel": 45,
    "pinwheel": 50,
    "zoom": 53,
    # Emphasis
    "spin": 14,
    "grow_shrink": 32,
    "pulse": 35,
    "teeter": 40,
    "wave": 41,
    "bold_flash": 63,
}

# ==================== Animation Triggers (MsoAnimTriggerType) ====================

ANIMATION_TRIGGERS = {
    "on_click": 1,           # msoAnimTriggerOnPageClick
    "with_previous": 2,      # msoAnimTriggerWithPrevious
    "after_previous": 3,     # msoAnimTriggerAfterPrevious
}

# ==================== Animation Directions (MsoAnimDirection) ====================

ANIMATION_DIRECTIONS = {
    "from_top": 33,
    "from_left": 34,
    "from_right": 35,
    "from_bottom": 36,
    "from_bottom_left": 37,
    "from_bottom_right": 38,
    "from_top_left": 39,
    "from_top_right": 40,
}

# ==================== Slide Transitions (PpEntryEffect) ====================

SLIDE_TRANSITIONS = {
    "none": 0,              # ppEffectNone
    "cut": 257,             # ppEffectCut
    "fade": 3844,           # ppEffectAppear (instant fade)
    "fade_smoothly": 3849,  # ppEffectFadeSmoothly
    "cover": 3845,          # ppEffectCircleOut
    "push": 3846,           # ppEffectDiamondOut
    "wipe": 3847,           # ppEffectCombHorizontal
    "split": 3848,          # ppEffectCombVertical
    "reveal": 3849,         # ppEffectFadeSmoothly
    "flash": 3850,          # ppEffectNewsflash
    "random_bars": 3851,    # ppEffectPlusOut
    "dissolve": 1537,       # ppEffectDissolve
    "random": 513,          # ppEffectRandom
}

# ==================== Named Colors ====================

NAMED_COLORS = {
    "black": "#000000",
    "white": "#FFFFFF",
    "red": "#FF0000",
    "green": "#008000",
    "blue": "#0000FF",
    "yellow": "#FFFF00",
    "cyan": "#00FFFF",
    "magenta": "#FF00FF",
    "orange": "#FFA500",
    "purple": "#800080",
    "gray": "#808080",
    "grey": "#808080",
    "silver": "#C0C0C0",
    "navy": "#000080",
    "teal": "#008080",
    "maroon": "#800000",
    "olive": "#808000",
    "lime": "#00FF00",
    "aqua": "#00FFFF",
    "fuchsia": "#FF00FF",
    "pink": "#FFC0CB",
    "brown": "#A52A2A",
    "coral": "#FF7F50",
    "gold": "#FFD700",
    "indigo": "#4B0082",
    "violet": "#EE82EE",
    "tomato": "#FF6347",
    "salmon": "#FA8072",
    "khaki": "#F0E68C",
    "crimson": "#DC143C",
    "transparent": None,
    "none": None,
}


# ==================== Utility Functions ====================

def parse_color(color_str: str) -> int | None:
    """
    Parse SVG/CSS color string to COM RGB integer.

    Supports: #hex, #short-hex, rgb(), named colors.
    Returns None for 'none'/'transparent'.
    """
    if not color_str:
        return None

    color_str = color_str.strip().lower()

    if color_str in ("none", "transparent", ""):
        return None

    if color_str in NAMED_COLORS:
        hex_val = NAMED_COLORS[color_str]
        if hex_val is None:
            return None
        color_str = hex_val

    if color_str.startswith("#"):
        hex_str = color_str[1:]
        if len(hex_str) == 3:
            hex_str = hex_str[0]*2 + hex_str[1]*2 + hex_str[2]*2
        if len(hex_str) == 6:
            r = int(hex_str[0:2], 16)
            g = int(hex_str[2:4], 16)
            b = int(hex_str[4:6], 16)
            return r + g * 256 + b * 65536
        if len(hex_str) == 8:
            r = int(hex_str[0:2], 16)
            g = int(hex_str[2:4], 16)
            b = int(hex_str[4:6], 16)
            return r + g * 256 + b * 65536

    if color_str.startswith("rgb"):
        import re
        m = re.match(r'rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)', color_str)
        if m:
            r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
            return r + g * 256 + b * 65536

    return None


def color_int_to_hex(color_int: int) -> str:
    """Convert COM RGB integer to hex string (#RRGGBB)."""
    r = color_int & 0xFF
    g = (color_int >> 8) & 0xFF
    b = (color_int >> 16) & 0xFF
    return f"#{r:02X}{g:02X}{b:02X}"


def resolve_slide(pres, slide_ref) -> object:
    """
    Resolve a slide reference to a COM Slide object.

    slide_ref can be:
    - int: 1-based slide index
    - "current": the currently active slide
    - "last": the last slide
    """
    if isinstance(slide_ref, int):
        if slide_ref < 1 or slide_ref > pres.Slides.Count:
            raise ValueError(f"Slide index {slide_ref} out of range (1-{pres.Slides.Count})")
        return pres.Slides(slide_ref)

    if slide_ref == "last":
        if pres.Slides.Count == 0:
            raise ValueError("No slides in presentation")
        return pres.Slides(pres.Slides.Count)

    raise ValueError(f"Invalid slide reference: {slide_ref}")


def resolve_slide_with_app(app, pres, slide_ref):
    """Like resolve_slide but also handles 'current' via app.ActiveWindow."""
    if slide_ref == "current" or slide_ref is None:
        try:
            return app.ActiveWindow.View.Slide
        except Exception:
            if pres.Slides.Count > 0:
                return pres.Slides(1)
            raise ValueError("No slides in presentation and no active slide")
    return resolve_slide(pres, slide_ref)


def find_shape_by_handle(slide, handle_id: str):
    """Find a shape on a slide by its Name property (handle_id)."""
    for i in range(1, slide.Shapes.Count + 1):
        shape = slide.Shapes(i)
        try:
            if shape.Name == handle_id:
                return shape
        except Exception:
            continue
    return None


def find_shape_by_index(slide, index: int):
    """Find a shape on a slide by its 1-based index."""
    if 1 <= index <= slide.Shapes.Count:
        return slide.Shapes(index)
    return None


# ==================== Table Styles (OOXML style GUIDs) ====================

TABLE_STYLES = {
    # -- No Style --
    "no_style": "{2D5ABB26-0587-4C30-8999-92F81FD0307C}",
    "grid_only": "{5940675A-B579-460E-94D1-54222C63F5DA}",

    # -- Light --
    "light_1": "{9D7B26C5-4107-4FEC-AEDC-1716B250A1BB}",
    "light_1_accent_1": "{3B4B98B0-60AC-42C2-AFA5-B58CD77FA1E5}",
    "light_1_accent_2": "{0E3FDE45-AF77-4B5C-9715-49D594BDF05E}",
    "light_1_accent_3": "{C083E6E3-FA7D-4D7B-A595-EF9225AFEA82}",
    "light_2": "{7E9639D4-E3E2-4D34-9284-5A2195B3D0D7}",
    "light_2_accent_1": "{69012ECD-51FC-41F1-AA8D-1B2483CD663E}",
    "light_3": "{BDBED569-4797-4DF1-A0F4-6AAB3CD982D8}",
    "light_3_accent_1": "{BC89EF96-8CEA-46FF-86C4-4CE0E7609802}",

    # -- Medium --
    "medium_1": "{793D81CF-94F2-401A-BA57-92F5A7B2D0C5}",
    "medium_1_accent_1": "{B301B821-A1FF-4177-AEE7-76D212191A09}",
    "medium_2": "{073A0DAA-6AF3-43AB-8588-CEC1D06C72B9}",
    "medium_2_accent_1": "{21E4AEA4-8DFA-4A89-87EB-49C32662AFE0}",
    "medium_2_accent_2": "{F5AB1C69-6EDB-4FF4-983F-18BD219EF322}",
    "medium_3": "{C083E6E3-FA7D-4D7B-A595-EF9225AFEA82}",
    "medium_3_accent_1": "{16D9F66E-5EB9-4882-86FB-DCBF35E3C3E4}",
    "medium_4": "{D7AC3CCA-C797-4891-BE02-D94E43425B78}",
    "medium_4_accent_1": "{69CF1AB2-1976-4502-BF36-3FF5EA218861}",

    # -- Dark --
    "dark_1": "{E8034E78-7F5D-4C2E-B375-FC64B27BC917}",
    "dark_1_accent_1": "{D03447BB-5D67-496B-8E87-E561075AD55C}",
    "dark_1_accent_2": "{ED083AE6-46FA-4A59-8FB0-9F97EB10719F}",
    "dark_2": "{5202B0CA-FC54-4571-9B66-8C3CDE3F1DC9}",
    "dark_2_accent_1": "{0660B408-B3CF-4A94-85FC-2B1E0A45F4A2}",
    "dark_2_accent_3": "{7E9639D4-E3E2-4D34-9284-5A2195B3D0D7}",
}

DEFAULT_TABLE_STYLE = "no_style"


def resolve_table_style(name_or_guid: str | None) -> str | None:
    """Resolve a friendly style name or raw GUID to a table style GUID."""
    if not name_or_guid:
        return None
    if name_or_guid.startswith("{"):
        return name_or_guid
    return TABLE_STYLES.get(name_or_guid)
