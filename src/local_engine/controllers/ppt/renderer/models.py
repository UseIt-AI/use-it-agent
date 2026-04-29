"""Data structures and constants shared across the renderer package."""

from dataclasses import dataclass, field
from typing import List

# ---------- SVG namespaces ----------

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"

# ---------- PowerPoint FreeForm constants ----------

MSO_EDITING_AUTO = 0
MSO_EDITING_CORNER = 1
MSO_EDITING_SMOOTH = 2
MSO_SEGMENT_LINE = 0
MSO_SEGMENT_CURVE = 1

# ---------- PPT line / arrow / gradient ----------

MSO_LINE_SOLID = 1
MSO_LINE_ROUND_DOT = 3
MSO_LINE_DASH = 4

MSO_ARROWHEAD_NONE = 1
MSO_ARROWHEAD_OPEN = 3

MSO_GRADIENT_HORIZONTAL = 1
MSO_GRADIENT_FROM_CENTER = 7


# ---------- SVG Defs data structures ----------

@dataclass
class GradientStop:
    offset: float        # 0.0 – 1.0
    color: str           # raw color string (hex, rgb, named)
    opacity: float = 1.0 # from stop-opacity

@dataclass
class GradientDef:
    kind: str = "linear"  # "linear" or "radial"
    stops: List["GradientStop"] = field(default_factory=list)
    # linear gradient params
    x1: float = 0.0
    y1: float = 0.0
    x2: float = 1.0
    y2: float = 0.0
    # radial gradient params
    cx: float = 0.5
    cy: float = 0.5
    r: float = 0.5

@dataclass
class FilterDef:
    kind: str = "glow"          # "glow" | "shadow"
    blur_radius: float = 8.0    # from feGaussianBlur / feDropShadow stdDeviation
    shadow_dx: float = 0.0
    shadow_dy: float = 0.0
    shadow_color: str = "#000000"
    shadow_opacity: float = 0.6
