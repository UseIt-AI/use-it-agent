"""SVG parsing utilities: path data, transforms, CSS, gradient stops, etc."""

import math
import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple

from ..constants import parse_color
from .models import GradientStop


# ==================== Simple helpers ====================

def strip_ns(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def parse_url_ref(value: str) -> str:
    """Extract ID from ``url(#id)`` reference. Returns '' if not a url ref."""
    if value and value.strip().startswith("url("):
        inner = value.strip().removeprefix("url(").removesuffix(")").strip().strip("'\"")
        return inner.lstrip("#")
    return ""


def pct_to_frac(val: str) -> float:
    """Convert '50%' -> 0.5, plain numbers pass through."""
    val = val.strip()
    if val.endswith("%"):
        return float(val[:-1]) / 100.0
    return float(val)


def to_float(val: str | None, default: float = 0.0) -> float:
    if val is None:
        return default
    val = str(val).strip()
    for suffix in ("px", "pt", "em", "rem", "%"):
        val = val.replace(suffix, "")
    try:
        return float(val)
    except ValueError:
        return default


def parse_length(val: str | None, default: float = 0.0) -> float:
    return to_float(val, default)


# ==================== Style / CSS ====================

def parse_inline_style(elem: ET.Element) -> Dict[str, str]:
    style_str = elem.get("style", "")
    if not style_str:
        return {}
    result = {}
    for pair in style_str.split(";"):
        pair = pair.strip()
        if ":" in pair:
            k, v = pair.split(":", 1)
            result[k.strip()] = v.strip()
    return result


def merge_style(parent: Dict, child: Dict) -> Dict:
    merged = dict(parent)
    merged.update(child)
    return merged


def parse_css(css_text: str) -> Dict[str, Dict[str, str]]:
    """Parse CSS from <style> into {class_name: {property: value}}."""
    result: Dict[str, Dict[str, str]] = {}
    css_text = re.sub(r'/\*.*?\*/', '', css_text, flags=re.DOTALL)

    for match in re.finditer(r'\.([a-zA-Z0-9_-]+)\s*\{([^}]*)\}', css_text):
        class_name = match.group(1)
        props: Dict[str, str] = {}
        for pair in match.group(2).split(";"):
            pair = pair.strip()
            if ":" in pair:
                k, v = pair.split(":", 1)
                props[k.strip()] = v.strip()
        result[class_name] = props
    return result


# ==================== Polygon / Points ====================

def parse_polygon_points(points_str: str) -> List[Tuple[float, float]]:
    """Parse SVG <polygon>/<polyline> ``points`` attribute."""
    nums = re.findall(r'[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?', points_str)
    pts: List[Tuple[float, float]] = []
    for i in range(0, len(nums) - 1, 2):
        pts.append((float(nums[i]), float(nums[i + 1])))
    return pts


# ==================== Affine Matrix ====================

def compose_matrix(
    parent: Tuple[float, float, float, float, float, float],
    child: Tuple[float, float, float, float, float, float],
) -> Tuple[float, float, float, float, float, float]:
    """Compose two 2D affine matrices: parent * child.

    Matrix layout: [a c e; b d f; 0 0 1].
    """
    pa, pb, pc, pd, pe, pf = parent
    ca, cb, cc, cd, ce, cf = child
    return (
        pa * ca + pc * cb,          # a
        pb * ca + pd * cb,          # b
        pa * cc + pc * cd,          # c
        pb * cc + pd * cd,          # d
        pa * ce + pc * cf + pe,     # e
        pb * ce + pd * cf + pf,     # f
    )


def parse_transform_matrix(
    transform: str,
) -> Tuple[float, float, float, float, float, float]:
    """Parse SVG ``transform`` attribute into a full 2D affine matrix.

    Returns ``(a, b, c, d, e, f)`` where  x' = a*x + c*y + e, y' = b*x + d*y + f.
    Handles translate, scale, rotate, and matrix.
    """
    if not transform:
        return (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

    a, b, c, d, e, f = 1.0, 0.0, 0.0, 1.0, 0.0, 0.0

    for m in re.finditer(
        r'(translate|scale|rotate|matrix)\s*\(([^)]+)\)', transform
    ):
        func = m.group(1)
        nums = [
            float(x)
            for x in re.findall(
                r'[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?', m.group(2)
            )
        ]

        if func == "translate" and nums:
            tx = nums[0]
            ty = nums[1] if len(nums) > 1 else 0.0
            e, f = a * tx + c * ty + e, b * tx + d * ty + f

        elif func == "scale" and nums:
            sx = nums[0]
            sy = nums[1] if len(nums) > 1 else sx
            a, c = a * sx, c * sy
            b, d = b * sx, d * sy

        elif func == "rotate" and nums:
            angle_deg = nums[0]
            cx_r = nums[1] if len(nums) >= 3 else 0.0
            cy_r = nums[2] if len(nums) >= 3 else 0.0
            if cx_r or cy_r:
                e, f = a * cx_r + c * cy_r + e, b * cx_r + d * cy_r + f

            rad = math.radians(angle_deg)
            cos_a = math.cos(rad)
            sin_a = math.sin(rad)
            na = a * cos_a + c * sin_a
            nb = b * cos_a + d * sin_a
            nc = -a * sin_a + c * cos_a
            nd = -b * sin_a + d * cos_a
            a, b, c, d = na, nb, nc, nd

            if cx_r or cy_r:
                e, f = (
                    a * (-cx_r) + c * (-cy_r) + e,
                    b * (-cx_r) + d * (-cy_r) + f,
                )

        elif func == "matrix" and len(nums) >= 6:
            ma, mb, mc, md, me, mf = nums[:6]
            na = a * ma + c * mb
            nb = b * ma + d * mb
            nc = a * mc + c * md
            nd = b * mc + d * md
            ne = a * me + c * mf + e
            nf = b * me + d * mf + f
            a, b, c, d, e, f = na, nb, nc, nd, ne, nf

    return (a, b, c, d, e, f)


def parse_transform(transform: str) -> Tuple[float, float, float, float]:
    """Legacy wrapper -- returns (translate_x, translate_y, scale_x, scale_y).

    For transforms that include rotation, use ``parse_transform_matrix`` instead.
    """
    a, _b, _c, d, e, f = parse_transform_matrix(transform)
    return e, f, a, d


# ==================== Gradient interpolation ====================

def interpolate_gradient_color(
    stops: List[GradientStop], t: float,
) -> int:
    """Interpolate color at position *t* (0..1) along sorted gradient stops.

    Returns a PPT-compatible RGB integer (R | G<<8 | B<<16).
    """
    if not stops:
        return 0
    if t <= stops[0].offset:
        return parse_color(stops[0].color) or 0
    if t >= stops[-1].offset:
        return parse_color(stops[-1].color) or 0

    for i in range(len(stops) - 1):
        if stops[i].offset <= t <= stops[i + 1].offset:
            span = stops[i + 1].offset - stops[i].offset
            ratio = (t - stops[i].offset) / span if span > 0 else 0.0
            c1 = parse_color(stops[i].color) or 0
            c2 = parse_color(stops[i + 1].color) or 0
            r1, g1, b1 = c1 & 0xFF, (c1 >> 8) & 0xFF, (c1 >> 16) & 0xFF
            r2, g2, b2 = c2 & 0xFF, (c2 >> 8) & 0xFF, (c2 >> 16) & 0xFF
            r = int(r1 + (r2 - r1) * ratio)
            g = int(g1 + (g2 - g1) * ratio)
            b = int(b1 + (b2 - b1) * ratio)
            return r | (g << 8) | (b << 16)

    return parse_color(stops[-1].color) or 0


def interpolate_gradient_opacity(
    stops: List[GradientStop], t: float,
) -> float:
    """Interpolate opacity at position *t* (0..1) along sorted gradient stops."""
    if not stops:
        return 1.0
    if t <= stops[0].offset:
        return stops[0].opacity
    if t >= stops[-1].offset:
        return stops[-1].opacity

    for i in range(len(stops) - 1):
        if stops[i].offset <= t <= stops[i + 1].offset:
            span = stops[i + 1].offset - stops[i].offset
            ratio = (t - stops[i].offset) / span if span > 0 else 0.0
            return stops[i].opacity + (stops[i + 1].opacity - stops[i].opacity) * ratio

    return stops[-1].opacity


def parse_gradient_stops(elem: ET.Element) -> List[GradientStop]:
    """Parse <stop> children, reading color/opacity from both XML attrs and inline style."""
    stops: List[GradientStop] = []
    for child in elem:
        if strip_ns(child.tag) == "stop":
            offset_str = child.get("offset", "0")
            offset = pct_to_frac(offset_str)
            stop_style = parse_inline_style(child)
            color = stop_style.get("stop-color") or child.get("stop-color", "#000000")
            opacity_str = stop_style.get("stop-opacity") or child.get("stop-opacity", "1")
            opacity = to_float(opacity_str, 1.0)
            stops.append(GradientStop(offset=offset, color=color, opacity=opacity))
    return stops


# ==================== SVG Path Parser ====================

def parse_path_d(d: str) -> List[Tuple]:
    """Parse SVG path 'd' attribute into absolute commands.

    Returns list of tuples:
    - ("M", x, y)
    - ("L", x, y)
    - ("C", x1, y1, x2, y2, x, y)
    - ("Z",)
    """
    commands: List[Tuple] = []
    cx, cy = 0.0, 0.0  # current point
    sx, sy = 0.0, 0.0  # subpath start (for Z)
    last_cp: Optional[Tuple[float, float]] = None  # last control point for S

    tokens = re.findall(
        r'[MmLlHhVvCcSsQqAaZz]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?', d
    )

    i = 0
    cmd: Optional[str] = None

    def _nums(count: int) -> List[float]:
        nonlocal i
        vals = []
        for _ in range(count):
            if i < len(tokens):
                try:
                    vals.append(float(tokens[i]))
                    i += 1
                except ValueError:
                    break
            else:
                break
        return vals

    while i < len(tokens):
        token = tokens[i]

        if token.isalpha():
            cmd = token
            i += 1
            if cmd in ("Z", "z"):
                commands.append(("Z",))
                cx, cy = sx, sy
                last_cp = None
                continue
        elif cmd is None:
            i += 1
            continue

        if cmd == "M":
            ns = _nums(2)
            if len(ns) < 2: break
            cx, cy = ns[0], ns[1]
            sx, sy = cx, cy
            commands.append(("M", cx, cy))
            cmd = "L"
            last_cp = None
        elif cmd == "m":
            ns = _nums(2)
            if len(ns) < 2: break
            cx += ns[0]; cy += ns[1]
            sx, sy = cx, cy
            commands.append(("M", cx, cy))
            cmd = "l"
            last_cp = None
        elif cmd == "L":
            ns = _nums(2)
            if len(ns) < 2: break
            cx, cy = ns[0], ns[1]
            commands.append(("L", cx, cy))
            last_cp = None
        elif cmd == "l":
            ns = _nums(2)
            if len(ns) < 2: break
            cx += ns[0]; cy += ns[1]
            commands.append(("L", cx, cy))
            last_cp = None
        elif cmd == "H":
            ns = _nums(1)
            if not ns: break
            cx = ns[0]
            commands.append(("L", cx, cy))
            last_cp = None
        elif cmd == "h":
            ns = _nums(1)
            if not ns: break
            cx += ns[0]
            commands.append(("L", cx, cy))
            last_cp = None
        elif cmd == "V":
            ns = _nums(1)
            if not ns: break
            cy = ns[0]
            commands.append(("L", cx, cy))
            last_cp = None
        elif cmd == "v":
            ns = _nums(1)
            if not ns: break
            cy += ns[0]
            commands.append(("L", cx, cy))
            last_cp = None
        elif cmd == "C":
            ns = _nums(6)
            if len(ns) < 6: break
            commands.append(("C", ns[0], ns[1], ns[2], ns[3], ns[4], ns[5]))
            last_cp = (ns[2], ns[3])
            cx, cy = ns[4], ns[5]
        elif cmd == "c":
            ns = _nums(6)
            if len(ns) < 6: break
            x1, y1 = cx + ns[0], cy + ns[1]
            x2, y2 = cx + ns[2], cy + ns[3]
            ex, ey = cx + ns[4], cy + ns[5]
            commands.append(("C", x1, y1, x2, y2, ex, ey))
            last_cp = (x2, y2)
            cx, cy = ex, ey
        elif cmd == "S":
            ns = _nums(4)
            if len(ns) < 4: break
            if last_cp:
                rx = 2 * cx - last_cp[0]
                ry = 2 * cy - last_cp[1]
            else:
                rx, ry = cx, cy
            commands.append(("C", rx, ry, ns[0], ns[1], ns[2], ns[3]))
            last_cp = (ns[0], ns[1])
            cx, cy = ns[2], ns[3]
        elif cmd == "s":
            ns = _nums(4)
            if len(ns) < 4: break
            if last_cp:
                rx = 2 * cx - last_cp[0]
                ry = 2 * cy - last_cp[1]
            else:
                rx, ry = cx, cy
            x2, y2 = cx + ns[0], cy + ns[1]
            ex, ey = cx + ns[2], cy + ns[3]
            commands.append(("C", rx, ry, x2, y2, ex, ey))
            last_cp = (x2, y2)
            cx, cy = ex, ey
        elif cmd == "Q":
            ns = _nums(4)
            if len(ns) < 4: break
            qx, qy, ex, ey = ns
            c1x = cx + 2 / 3 * (qx - cx)
            c1y = cy + 2 / 3 * (qy - cy)
            c2x = ex + 2 / 3 * (qx - ex)
            c2y = ey + 2 / 3 * (qy - ey)
            commands.append(("C", c1x, c1y, c2x, c2y, ex, ey))
            last_cp = (qx, qy)
            cx, cy = ex, ey
        elif cmd == "q":
            ns = _nums(4)
            if len(ns) < 4: break
            qx, qy = cx + ns[0], cy + ns[1]
            ex, ey = cx + ns[2], cy + ns[3]
            c1x = cx + 2 / 3 * (qx - cx)
            c1y = cy + 2 / 3 * (qy - cy)
            c2x = ex + 2 / 3 * (qx - ex)
            c2y = ey + 2 / 3 * (qy - ey)
            commands.append(("C", c1x, c1y, c2x, c2y, ex, ey))
            last_cp = (qx, qy)
            cx, cy = ex, ey
        elif cmd in ("A", "a"):
            ns = _nums(7)
            if len(ns) < 7: break
            arc_rx, arc_ry = abs(ns[0]), abs(ns[1])
            phi = ns[2]
            fa, fs = int(ns[3]), int(ns[4])
            if cmd == "A":
                ex, ey = ns[5], ns[6]
            else:
                ex, ey = cx + ns[5], cy + ns[6]

            if arc_rx == 0 or arc_ry == 0:
                commands.append(("L", ex, ey))
            else:
                beziers = _arc_to_beziers(cx, cy, arc_rx, arc_ry, phi, fa, fs, ex, ey)
                commands.extend(beziers)

            cx, cy = ex, ey
            last_cp = None
        else:
            i += 1

    return commands


# ==================== Arc -> Bezier ====================

def _arc_to_beziers(
    x1: float, y1: float,
    rx: float, ry: float,
    phi_deg: float, fa: int, fs: int,
    x2: float, y2: float,
) -> List[Tuple]:
    """Convert SVG arc to cubic bezier curve(s).

    Implements the endpoint-to-center parameterization from the SVG spec,
    then splits the arc into <=90 degree segments approximated by cubic beziers.
    """
    if (x1 == x2 and y1 == y2) or rx == 0 or ry == 0:
        return [("L", x2, y2)]

    phi = math.radians(phi_deg)
    cos_phi = math.cos(phi)
    sin_phi = math.sin(phi)

    # Step 1: (x1', y1')
    dx = (x1 - x2) / 2
    dy = (y1 - y2) / 2
    x1p = cos_phi * dx + sin_phi * dy
    y1p = -sin_phi * dx + cos_phi * dy

    # Adjust radii if too small
    x1p2, y1p2 = x1p * x1p, y1p * y1p
    rx2, ry2 = rx * rx, ry * ry
    lam = x1p2 / rx2 + y1p2 / ry2
    if lam > 1:
        s = math.sqrt(lam)
        rx *= s; ry *= s
        rx2 = rx * rx; ry2 = ry * ry

    # Step 2: (cx', cy')
    num = max(0, rx2 * ry2 - rx2 * y1p2 - ry2 * x1p2)
    den = rx2 * y1p2 + ry2 * x1p2
    sq = math.sqrt(num / den) if den > 0 else 0
    if fa == fs:
        sq = -sq
    cxp = sq * rx * y1p / ry
    cyp = -sq * ry * x1p / rx

    # Step 3: (cx, cy)
    cx_c = cos_phi * cxp - sin_phi * cyp + (x1 + x2) / 2
    cy_c = sin_phi * cxp + cos_phi * cyp + (y1 + y2) / 2

    # Step 4: angles
    def _angle(ux, uy, vx, vy):
        n = math.hypot(ux, uy) * math.hypot(vx, vy)
        if n == 0:
            return 0
        c = max(-1, min(1, (ux * vx + uy * vy) / n))
        a = math.acos(c)
        return -a if ux * vy - uy * vx < 0 else a

    theta1 = _angle(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dtheta = _angle(
        (x1p - cxp) / rx, (y1p - cyp) / ry,
        (-x1p - cxp) / rx, (-y1p - cyp) / ry,
    )
    if fs == 0 and dtheta > 0:
        dtheta -= 2 * math.pi
    elif fs == 1 and dtheta < 0:
        dtheta += 2 * math.pi

    # Split into segments <= 90 degrees
    n_segs = max(1, int(math.ceil(abs(dtheta) / (math.pi / 2))))
    seg_angle = dtheta / n_segs
    alpha = 4.0 / 3.0 * math.tan(seg_angle / 4)

    beziers: List[Tuple] = []
    for i in range(n_segs):
        t1 = theta1 + i * seg_angle
        t2 = theta1 + (i + 1) * seg_angle
        cos1, sin1 = math.cos(t1), math.sin(t1)
        cos2, sin2 = math.cos(t2), math.sin(t2)

        c1x = rx * cos1 - alpha * rx * sin1
        c1y = ry * sin1 + alpha * ry * cos1
        c2x = rx * cos2 + alpha * rx * sin2
        c2y = ry * sin2 - alpha * ry * cos2
        epx = rx * cos2
        epy = ry * sin2

        def _to_global(px, py):
            return (
                cos_phi * px - sin_phi * py + cx_c,
                sin_phi * px + cos_phi * py + cy_c,
            )

        gc1 = _to_global(c1x, c1y)
        gc2 = _to_global(c2x, c2y)
        gep = _to_global(epx, epy)
        beziers.append(("C", gc1[0], gc1[1], gc2[0], gc2[1], gep[0], gep[1]))

    return beziers
