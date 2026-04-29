"""StyleMixin: all _apply_* methods for fill, stroke, gradient, glow, shadow."""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, Dict, Optional

from ..constants import SHAPE_TYPES, parse_color
from .models import (
    FilterDef,
    GradientDef,
    MSO_ARROWHEAD_OPEN,
    MSO_GRADIENT_FROM_CENTER,
    MSO_GRADIENT_HORIZONTAL,
    MSO_LINE_DASH,
)
from .parsers import parse_url_ref, strip_ns, to_float

if TYPE_CHECKING:
    import xml.etree.ElementTree as ET

    from .context import RenderContext

logger = logging.getLogger(__name__)


class StyleMixin:
    """Mixin providing style / gradient / effect application to PPT shapes."""

    def _apply_style(
        self,
        shape,
        style: Dict,
        elem: ET.Element,
        ctx: Optional[RenderContext] = None,
    ) -> None:
        fill_str = style.get("fill", elem.get("fill"))
        stroke_str = style.get("stroke", elem.get("stroke"))
        stroke_width = style.get("stroke-width", elem.get("stroke-width"))
        fill_opacity = style.get("fill-opacity", elem.get("fill-opacity"))
        opacity = style.get("opacity", elem.get("opacity"))
        dasharray = style.get("stroke-dasharray", elem.get("stroke-dasharray"))

        # ---------- Fill ----------
        gradient_applied = False
        if fill_str and fill_str.startswith("url("):
            ref = parse_url_ref(fill_str)
            if ctx and ref and ref in ctx.gradient_defs:
                self._apply_gradient_fill(shape, ctx.gradient_defs[ref])
                gradient_applied = True
            elif ctx and ref and ref in ctx.defs_map:
                pat = ctx.defs_map[ref]
                if strip_ns(pat.tag) == "pattern":
                    self._expand_pattern(shape, pat, ctx)
                    gradient_applied = True  # suppress further fill ops
        elif fill_str and fill_str.lower() in ("none", "transparent"):
            try:
                shape.Fill.Visible = 0
                shape.Fill.Transparency = 1.0
            except Exception:
                pass
        elif fill_str:
            color = parse_color(fill_str)
            if color is not None:
                shape.Fill.Solid()
                shape.Fill.ForeColor.RGB = color

        if fill_opacity and not gradient_applied:
            try:
                shape.Fill.Transparency = 1.0 - float(fill_opacity)
            except Exception:
                pass

        # ---------- Stroke ----------
        if stroke_str and stroke_str.startswith("url("):
            ref = parse_url_ref(stroke_str)
            if ctx and ref and ref in ctx.gradient_defs:
                sw = to_float(stroke_width, 1.0)
                self._apply_gradient_stroke(
                    shape, ctx.gradient_defs[ref], ctx, sw,
                )
            else:
                shape.Line.Visible = False
        elif stroke_str and stroke_str.lower() in ("none", "transparent"):
            shape.Line.Visible = False
        elif stroke_str:
            color = parse_color(stroke_str)
            if color is not None:
                shape.Line.Visible = True
                shape.Line.ForeColor.RGB = color
        else:
            shape.Line.Visible = False

        if stroke_width:
            try:
                shape.Line.Weight = to_float(stroke_width)
            except Exception:
                pass

        if dasharray and dasharray.lower() != "none":
            try:
                shape.Line.Visible = True
                shape.Line.DashStyle = MSO_LINE_DASH
            except Exception:
                pass

        if opacity and not gradient_applied:
            try:
                shape.Fill.Transparency = 1.0 - float(opacity)
            except Exception:
                pass

        # Arrowhead (marker-end)
        marker_end = style.get("marker-end", elem.get("marker-end"))
        if marker_end and "arrow" in marker_end.lower():
            try:
                shape.Line.EndArrowheadStyle = MSO_ARROWHEAD_OPEN
            except Exception:
                pass

    def _apply_line_style(self, shape, style: Dict, elem: ET.Element) -> None:
        stroke = style.get("stroke", elem.get("stroke", "#000000"))
        stroke_width = style.get("stroke-width", elem.get("stroke-width", "1"))
        dasharray = style.get("stroke-dasharray", elem.get("stroke-dasharray"))
        marker_end = style.get("marker-end", elem.get("marker-end"))

        color = parse_color(stroke)
        if color is not None:
            shape.Line.ForeColor.RGB = color
        try:
            shape.Line.Weight = to_float(stroke_width)
        except Exception:
            pass

        opacity = style.get("opacity", elem.get("opacity"))
        stroke_opacity = style.get("stroke-opacity", elem.get("stroke-opacity"))
        effective = to_float(stroke_opacity or opacity, 1.0)
        if effective < 0.99:
            try:
                shape.Line.Transparency = 1.0 - effective
            except Exception:
                pass

        if dasharray and dasharray.lower() != "none":
            try:
                shape.Line.DashStyle = MSO_LINE_DASH
            except Exception:
                pass

        if marker_end and "arrow" in marker_end.lower():
            try:
                shape.Line.EndArrowheadStyle = MSO_ARROWHEAD_OPEN
            except Exception:
                pass

    # ==================== Gradient / Glow Helpers ====================

    @staticmethod
    def _apply_gradient_fill(shape, gdef: GradientDef) -> None:
        """Map SVG <linearGradient>/<radialGradient> -> PPT gradient fill."""
        stops = sorted(gdef.stops, key=lambda s: s.offset)
        if len(stops) < 2:
            return

        try:
            if gdef.kind == "radial":
                shape.Fill.TwoColorGradient(MSO_GRADIENT_FROM_CENTER, 1)
            else:
                shape.Fill.TwoColorGradient(MSO_GRADIENT_HORIZONTAL, 1)
                dx = gdef.x2 - gdef.x1
                dy = gdef.y2 - gdef.y1
                angle = math.degrees(math.atan2(dy, dx))
                shape.Fill.GradientAngle = angle % 360

            gs = shape.Fill.GradientStops

            while gs.Count > 2:
                gs.Delete(gs.Count)

            c0 = parse_color(stops[0].color)
            cN = parse_color(stops[-1].color)
            if c0 is not None:
                gs(1).Color.RGB = c0
            gs(1).Position = stops[0].offset
            gs(1).Transparency = 1.0 - stops[0].opacity

            if cN is not None:
                gs(2).Color.RGB = cN
            gs(2).Position = stops[-1].offset
            gs(2).Transparency = 1.0 - stops[-1].opacity

            for stop in stops[1:-1]:
                c = parse_color(stop.color) or 0
                gs.Insert(c, stop.offset)
                for idx in range(1, gs.Count + 1):
                    if abs(gs(idx).Position - stop.offset) < 0.005:
                        gs(idx).Transparency = 1.0 - stop.opacity
                        break

        except Exception as e:
            logger.warning(f"[SlideRenderer] Gradient fill failed: {e}")

    def _apply_gradient_stroke(
        self,
        shape,
        gdef: GradientDef,
        ctx: Optional[RenderContext] = None,
        stroke_width: float = 1.0,
    ) -> None:
        """Apply gradient border using an overlay shape behind the original.

        PPT COM doesn't expose ``Line.Fill`` for AutoShapes, so we simulate a
        gradient border by placing a slightly larger gradient-filled copy of the
        shape behind the original.  For non-AutoShape types (freeform, line)
        we fall back to a solid color from the gradient's middle stop.
        """
        stops = sorted(gdef.stops, key=lambda s: s.offset)
        if len(stops) < 2:
            return

        MSO_AUTO_SHAPE = 1
        if ctx and shape.Type == MSO_AUTO_SHAPE:
            try:
                half = stroke_width / 2.0
                border = ctx.slide.Shapes.AddShape(
                    shape.AutoShapeType,
                    shape.Left - half,
                    shape.Top - half,
                    shape.Width + stroke_width,
                    shape.Height + stroke_width,
                )

                try:
                    if shape.AutoShapeType == SHAPE_TYPES["rounded_rectangle"]:
                        border.Adjustments[1] = shape.Adjustments[1]
                except Exception:
                    pass

                self._apply_gradient_fill(border, gdef)
                border.Line.Visible = False
                border.ZOrder(3)  # msoSendBackward

                shape.Line.Visible = False
                return
            except Exception as e:
                logger.debug(f"[SlideRenderer] Gradient stroke overlay failed: {e}")

        mid_idx = len(stops) // 2
        fallback = parse_color(stops[mid_idx].color)
        if fallback is not None:
            try:
                shape.Line.Visible = True
                shape.Line.ForeColor.RGB = fallback
            except Exception:
                pass

    def _expand_pattern(self, fill_shape, pat_elem: ET.Element, ctx: RenderContext) -> None:
        """Expand <pattern> by tiling its children across the fill_shape's bounding box."""
        try:
            pat_w = to_float(pat_elem.get("width", "0"))
            pat_h = to_float(pat_elem.get("height", "0"))
            if pat_w <= 0 or pat_h <= 0:
                return

            area_x = fill_shape.Left
            area_y = fill_shape.Top
            area_w = fill_shape.Width
            area_h = fill_shape.Height

            fill_shape.Fill.Visible = 0
            fill_shape.Fill.Transparency = 1.0
            fill_shape.Line.Visible = False

            cols = int(math.ceil(area_w / (pat_w * ctx._scale_x))) + 1
            rows = int(math.ceil(area_h / (pat_h * ctx._scale_y))) + 1

            MAX_TILES = 500
            if cols * rows > MAX_TILES:
                logger.debug(
                    f"[SlideRenderer] Pattern expansion skipped: "
                    f"{cols}x{rows} tiles exceeds limit {MAX_TILES}"
                )
                return

            for row in range(rows):
                for col in range(cols):
                    tile_ox = col * pat_w
                    tile_oy = row * pat_h
                    tile_mat = (1.0, 0.0, 0.0, 1.0, tile_ox, tile_oy)
                    tile_ctx = ctx.with_affine(tile_mat, ctx.inherited_style)
                    for child in pat_elem:
                        if strip_ns(child.tag) in ("defs", "style"):
                            continue
                        self._render_element(child, tile_ctx)
        except Exception as e:
            logger.warning(f"[SlideRenderer] Pattern expansion failed: {e}")

    @staticmethod
    def _apply_glow(shape, fdef: FilterDef) -> None:
        """Map SVG feGaussianBlur -> PPT Shape.Glow effect."""
        if fdef.kind != "glow":
            return
        try:
            shape.Glow.Radius = fdef.blur_radius
            try:
                fill_rgb = shape.Fill.ForeColor.RGB
                shape.Glow.Color.RGB = fill_rgb
            except Exception:
                pass
            shape.Glow.Transparency = 0.6
        except Exception as e:
            logger.debug(f"[SlideRenderer] Glow effect failed: {e}")

    @staticmethod
    def _apply_shadow(shape, fdef: FilterDef) -> None:
        """Map SVG feDropShadow -> PPT Shape.Shadow effect."""
        try:
            shadow = shape.Shadow
            shadow.Visible = True
            shadow.OffsetX = fdef.shadow_dx
            shadow.OffsetY = fdef.shadow_dy
            shadow.Blur = fdef.blur_radius
            color = parse_color(fdef.shadow_color)
            if color is not None:
                shadow.ForeColor.RGB = color
            shadow.Transparency = 1.0 - fdef.shadow_opacity
        except Exception as e:
            logger.debug(f"[SlideRenderer] Shadow effect failed: {e}")

    def _apply_text_gradient(self, shape, gdef: GradientDef) -> None:
        """Apply gradient fill to the entire text range via TextFrame2 API.

        ``shape.TextFrame2.TextRange.Font.Fill`` exposes a FillFormat that
        supports ``TwoColorGradient`` + ``GradientStops``.  Per-paragraph
        ``Paragraphs()`` is unavailable on late-bound CDispatch, so the
        gradient is applied to the whole text range.
        """
        stops = sorted(gdef.stops, key=lambda s: s.offset)
        if len(stops) < 2:
            return

        ff = shape.TextFrame2.TextRange.Font.Fill
        ff.Visible = True

        if gdef.kind == "radial":
            ff.TwoColorGradient(MSO_GRADIENT_FROM_CENTER, 1)
        else:
            ff.TwoColorGradient(MSO_GRADIENT_HORIZONTAL, 1)
            dx = gdef.x2 - gdef.x1
            dy = gdef.y2 - gdef.y1
            angle = math.degrees(math.atan2(dy, dx))
            ff.GradientAngle = angle % 360

        gs = ff.GradientStops

        while gs.Count > 2:
            gs.Delete(gs.Count)

        c0 = parse_color(stops[0].color)
        cN = parse_color(stops[-1].color)
        if c0 is not None:
            gs(1).Color.RGB = c0
        gs(1).Position = stops[0].offset
        gs(1).Transparency = 1.0 - stops[0].opacity
        if cN is not None:
            gs(2).Color.RGB = cN
        gs(2).Position = stops[-1].offset
        gs(2).Transparency = 1.0 - stops[-1].opacity

        for stop in stops[1:-1]:
            c = parse_color(stop.color) or 0
            gs.Insert(c, stop.offset)
            for idx in range(1, gs.Count + 1):
                if abs(gs(idx).Position - stop.offset) < 0.005:
                    gs(idx).Transparency = 1.0 - stop.opacity
                    break

    @staticmethod
    def _resolve_gradient_color(fill_str: str, ctx: RenderContext) -> Optional[str]:
        """For url(#gradient) fills, return a representative solid color from the stops."""
        if not fill_str or not fill_str.strip().startswith("url("):
            return None
        ref = parse_url_ref(fill_str)
        if ref and ref in ctx.gradient_defs:
            gdef = ctx.gradient_defs[ref]
            if gdef.stops:
                sorted_stops = sorted(gdef.stops, key=lambda s: s.offset)
                mid_idx = len(sorted_stops) // 2
                return sorted_stops[mid_idx].color
        return None
