"""ShapeRendererMixin: all _render_* methods for individual SVG elements."""

from __future__ import annotations

import logging
import math
import os
from typing import TYPE_CHECKING, Any, Dict, List

from ..constants import (
    MSO_TEXT_ORIENTATION_HORIZONTAL,
    SHAPE_TYPES,
    TEXT_ALIGN,
    parse_color,
)
from .models import (
    MSO_EDITING_AUTO,
    MSO_EDITING_CORNER,
    MSO_EDITING_SMOOTH,
    MSO_SEGMENT_CURVE,
    MSO_SEGMENT_LINE,
    XLINK_NS,
)
from .parsers import (
    compose_matrix,
    merge_style,
    parse_path_d,
    parse_polygon_points,
    parse_transform_matrix,
    parse_url_ref,
    strip_ns,
    to_float,
)

if TYPE_CHECKING:
    import xml.etree.ElementTree as ET

    from .context import RenderContext

logger = logging.getLogger(__name__)


class ShapeRendererMixin:
    """Mixin providing shape rendering methods (_render_*)."""

    def _render_rect(self, elem: ET.Element, ctx: RenderContext) -> int:
        style = ctx.resolve_style(elem)
        x = ctx.tx(to_float(elem.get("x", "0")))
        y = ctx.ty(to_float(elem.get("y", "0")))
        w = ctx.sx(to_float(elem.get("width", "0")))
        h = ctx.sy(to_float(elem.get("height", "0")))
        if w <= 0 or h <= 0:
            return 0

        rx = to_float(elem.get("rx", "0"))
        is_rounded = rx > 0 or to_float(elem.get("ry", "0")) > 0
        shape_type = SHAPE_TYPES["rounded_rectangle"] if is_rounded else SHAPE_TYPES["rectangle"]
        shape = ctx.slide.Shapes.AddShape(shape_type, x, y, w, h)

        if is_rounded and rx > 0:
            try:
                adj = min(rx / (min(to_float(elem.get("width", "1")), to_float(elem.get("height", "1"))) / 2), 0.5)
                shape.Adjustments[1] = adj
            except Exception:
                pass

        self._apply_style(shape, style, elem, ctx)
        self._set_handle(shape, elem, ctx)
        return 1

    def _render_ellipse(self, elem: ET.Element, ctx: RenderContext) -> int:
        style = ctx.resolve_style(elem)
        cx = ctx.tx(to_float(elem.get("cx", "0")))
        cy = ctx.ty(to_float(elem.get("cy", "0")))
        rx = ctx.sx(to_float(elem.get("rx", "0")))
        ry = ctx.sy(to_float(elem.get("ry", "0")))
        if rx <= 0 or ry <= 0:
            return 0
        shape = ctx.slide.Shapes.AddShape(SHAPE_TYPES["oval"], cx - rx, cy - ry, rx * 2, ry * 2)
        self._apply_style(shape, style, elem, ctx)
        self._set_handle(shape, elem, ctx)
        return 1

    def _render_circle(self, elem: ET.Element, ctx: RenderContext) -> int:
        style = ctx.resolve_style(elem)
        cx = ctx.tx(to_float(elem.get("cx", "0")))
        cy = ctx.ty(to_float(elem.get("cy", "0")))
        r_x = ctx.sx(to_float(elem.get("r", "0")))
        r_y = ctx.sy(to_float(elem.get("r", "0")))
        if r_x <= 0:
            return 0
        shape = ctx.slide.Shapes.AddShape(SHAPE_TYPES["oval"], cx - r_x, cy - r_y, r_x * 2, r_y * 2)
        self._apply_style(shape, style, elem, ctx)
        self._set_handle(shape, elem, ctx)
        return 1

    def _render_line(self, elem: ET.Element, ctx: RenderContext) -> int:
        style = ctx.resolve_style(elem)
        stroke_str = style.get("stroke", elem.get("stroke", ""))

        x1 = ctx.tx(to_float(elem.get("x1", "0")))
        y1 = ctx.ty(to_float(elem.get("y1", "0")))
        x2 = ctx.tx(to_float(elem.get("x2", "0")))
        y2 = ctx.ty(to_float(elem.get("y2", "0")))

        ref = parse_url_ref(stroke_str)
        if ref and ref in ctx.gradient_defs:
            return self._render_gradient_line(
                ctx, elem, style, x1, y1, x2, y2, ctx.gradient_defs[ref],
            )

        shape = ctx.slide.Shapes.AddLine(x1, y1, x2, y2)
        self._apply_line_style(shape, style, elem)
        self._set_handle(shape, elem, ctx)
        return 1

    def _render_gradient_line(
        self, ctx, elem, style, x1, y1, x2, y2, gdef,
    ) -> int:
        """Render a line with gradient stroke as a single filled freeform.

        Builds a thin closed polygon matching the stroke width and fills
        it with the SVG linear/radial gradient.  For ``stroke-linecap:
        round|square`` the polygon is extended by half the stroke width
        at each end.
        """
        sw = to_float(style.get("stroke-width", elem.get("stroke-width", "1")))
        opacity_attr = to_float(style.get("opacity", elem.get("opacity", "1")), 1.0)
        linecap = style.get("stroke-linecap", elem.get("stroke-linecap", "butt"))
        half = sw / 2.0

        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy)
        if length < 0.1:
            return 0

        nx = -dy / length * half
        ny = dx / length * half

        if linecap in ("round", "square"):
            ext_x = dx / length * half
            ext_y = dy / length * half
            x1 -= ext_x
            y1 -= ext_y
            x2 += ext_x
            y2 += ext_y

        p1 = (x1 + nx, y1 + ny)
        p2 = (x1 - nx, y1 - ny)
        p3 = (x2 - nx, y2 - ny)
        p4 = (x2 + nx, y2 + ny)

        builder = ctx.slide.Shapes.BuildFreeform(MSO_EDITING_CORNER, p1[0], p1[1])
        builder.AddNodes(MSO_SEGMENT_LINE, MSO_EDITING_AUTO, p2[0], p2[1])
        builder.AddNodes(MSO_SEGMENT_LINE, MSO_EDITING_AUTO, p3[0], p3[1])
        builder.AddNodes(MSO_SEGMENT_LINE, MSO_EDITING_AUTO, p4[0], p4[1])
        builder.AddNodes(MSO_SEGMENT_LINE, MSO_EDITING_AUTO, p1[0], p1[1])

        shape = builder.ConvertToShape()
        shape.Line.Visible = False
        self._apply_gradient_fill(shape, gdef)

        if opacity_attr < 0.99:
            try:
                gs = shape.Fill.GradientStops
                for idx in range(1, gs.Count + 1):
                    base_t = gs(idx).Transparency
                    gs(idx).Transparency = 1.0 - (1.0 - base_t) * opacity_attr
            except Exception:
                pass

        self._set_handle(shape, elem, ctx)
        return 1

    def _render_text(self, elem: ET.Element, ctx: RenderContext) -> int:
        style = ctx.resolve_style(elem)
        x = ctx.tx(to_float(elem.get("x", "0")))
        y = ctx.ty(to_float(elem.get("y", "0")))

        raw_size = to_float(style.get("font-size", elem.get("font-size", "18")))
        font_size = raw_size * ctx._scale_y

        spans = self._collect_text_spans(elem, style, ctx)
        if not spans:
            return 0

        anchor = style.get("text-anchor", elem.get("text-anchor", "start"))
        dominant_baseline = style.get("dominant-baseline", elem.get("dominant-baseline", ""))
        alignment_baseline = style.get("alignment-baseline", elem.get("alignment-baseline", ""))

        # Per-span width estimate (CJK-aware, includes a 1.18 safety multiplier
        # in `_estimate_text_width`).
        per_span_widths = [
            self._estimate_text_width(
                s["text"],
                s.get("font_size") or font_size,
                bool(s.get("bold")),
            )
            for s in spans
        ]
        actual_w = max(per_span_widths) if per_span_widths else 0.0
        line_height = font_size * 1.3
        num_lines = len(spans)
        estimated_h = num_lines * line_height

        baseline = dominant_baseline or alignment_baseline
        if baseline in ("central", "middle"):
            text_y = y - estimated_h / 2
        elif baseline in ("hanging", "text-before-edge"):
            text_y = y
        else:
            text_y = y - font_size * 0.85

        # Wrap policy (default: NEVER auto-wrap):
        #   PowerPoint's WordWrap only controls *implicit* wrapping at the box
        #   edge; explicit linebreaks (\r between paragraphs / <tspan> lines)
        #   work regardless of this flag. The LLM-emitted layout already
        #   carries every line break it wants, so any auto-wrap that PPT adds
        #   on top is noise — it triggers whenever our width estimate
        #   underestimates a single line by even ~1pt and the line silently
        #   spills onto the layer below.
        #
        #   Opt-in soft wrap → set data-wrap="true" on prose paragraphs that
        #   should reflow inside their declared data-width (body copy, long
        #   descriptions). data-no-wrap is kept as an explicit override.
        no_wrap_attr = (elem.get("data-no-wrap") or "").strip().lower()
        wrap_attr = (elem.get("data-wrap") or "").strip().lower()
        placeholder = (elem.get("data-placeholder") or "").strip().lower()
        # Body placeholders carry prose by convention → soft-wrap by default
        # so the LLM doesn't have to remember data-wrap on every body inject.
        # Title / subtitle / caption / label placeholders stay no-wrap.
        body_placeholder = placeholder in ("body", "content", "text", "paragraph")
        if wrap_attr in ("true", "1", "yes"):
            word_wrap = True
        elif no_wrap_attr in ("true", "1", "yes"):
            word_wrap = False
        elif body_placeholder:
            word_wrap = True
        else:
            word_wrap = False

        # Box sizing is in PPT points at this stage. Explicit data-width /
        # data-height are authored in SVG coordinates, so scale them just like
        # rect width/height. For auto-sized labels, keep the seeded width close
        # to the estimated glyph run; PowerPoint may still tighten the textbox
        # after text insertion, and a large floor would leave middle/end
        # anchored labels visibly offset from their SVG anchor.
        seed_w = max(actual_w, font_size * 0.5, 1.0)
        if elem.get("data-width") is not None:
            box_w = ctx.sx(to_float(elem.get("data-width"), 0.0))
        else:
            box_w = seed_w
        if elem.get("data-height") is not None:
            box_h = ctx.sy(to_float(elem.get("data-height"), 0.0))
        else:
            box_h = estimated_h

        # Position the BOX so its alignment edge sits on the SVG anchor. This
        # decouples the visual position from `actual_w` (which could be off by
        # a few pt due to font fallback) and from any later AutoSize behavior.
        text_x = x
        if anchor == "middle":
            text_x = x - box_w / 2
        elif anchor == "end":
            text_x = x - box_w

        text_x = max(0, text_x)
        text_y = max(0, text_y)

        shape = ctx.slide.Shapes.AddTextbox(
            MSO_TEXT_ORIENTATION_HORIZONTAL, text_x, text_y, box_w, box_h
        )
        try:
            shape.Fill.Visible = 0
            shape.Fill.Transparency = 1.0
        except Exception:
            pass

        tf = shape.TextFrame
        tf.WordWrap = word_wrap
        # AutoSize=ppAutoSizeShapeToFitText shifts x unpredictably on
        # center/end-anchored boxes (see the long comment above box sizing).
        # Disable it for non-wrap text — the seeded box already fits the text
        # and we don't want PPT moving it. For wrap text (body prose), keep
        # AutoSize so the box can grow vertically when explicit \r breaks
        # produce more lines than estimated_h covers.
        tf.AutoSize = 1 if word_wrap else 0  # 1 = ppAutoSizeShapeToFitText, 0 = ppAutoSizeNone
        try:
            tf.MarginLeft = 0
            tf.MarginRight = 0
            tf.MarginTop = 0
            tf.MarginBottom = 0
        except Exception:
            pass

        ppt_align = TEXT_ALIGN.get(
            {"start": "left", "middle": "center", "end": "right"}.get(anchor, "left"), 1
        )

        text_gradient_def = None
        for i, span in enumerate(spans):
            if i == 0:
                para = tf.TextRange
            else:
                tf.TextRange.InsertAfter("\r")
                para = tf.TextRange.Paragraphs(i + 1)

            para.Text = span["text"]
            para.ParagraphFormat.Alignment = ppt_align
            para.ParagraphFormat.SpaceBefore = 0
            para.ParagraphFormat.SpaceAfter = 0

            font = para.Font
            if span.get("font_name"):
                font.Name = span["font_name"]
            font.Size = span.get("font_size") or font_size
            if span.get("bold"):
                font.Bold = True
            if span.get("italic"):
                font.Italic = True

            gdef = span.get("gradient_def")
            if gdef:
                text_gradient_def = gdef
                color = parse_color(span.get("fill") or span.get("color"))
                if color is not None:
                    font.Color.RGB = color
            else:
                color = parse_color(span.get("fill") or span.get("color"))
                if color is not None:
                    font.Color.RGB = color

        if text_gradient_def:
            try:
                self._apply_text_gradient(shape, text_gradient_def)
            except Exception:
                pass

        try:
            shape.Fill.Visible = 0
            shape.Fill.Transparency = 1.0
        except Exception:
            pass
        shape.Line.Visible = False
        try:
            if anchor == "middle":
                shape.Left = max(0, x - shape.Width / 2)
            elif anchor == "end":
                shape.Left = max(0, x - shape.Width)
        except Exception:
            pass
        self._set_handle(shape, elem, ctx)
        return 1

    def _render_image(self, elem: ET.Element, ctx: RenderContext) -> int:
        href = elem.get(f"{{{XLINK_NS}}}href") or elem.get("href") or ""
        if not href:
            return 0
        x = ctx.tx(to_float(elem.get("x", "0")))
        y = ctx.ty(to_float(elem.get("y", "0")))
        w = ctx.sx(to_float(elem.get("width", "100")))
        h = ctx.sy(to_float(elem.get("height", "100")))

        if href.startswith("data:"):
            file_path = self._materialize_data_uri(href)
            if not file_path:
                return 0
        else:
            file_path = os.path.normpath(os.path.abspath(href))

        try:
            shape = ctx.slide.Shapes.AddPicture(
                file_path, LinkToFile=False, SaveWithDocument=True,
                Left=x, Top=y, Width=w, Height=h,
            )
            self._set_handle(shape, elem, ctx)
            return 1
        except Exception as e:
            logger.warning(f"[SlideRenderer] Failed to insert image {file_path}: {e}")
            return 0

    @staticmethod
    def _materialize_data_uri(href: str) -> str:
        """Decode a ``data:image/...;base64,...`` URI into a temp file.

        Returns the absolute file path on success, or empty string on failure.
        Supports png/jpg/jpeg/gif/svg/webp (others fall back to .bin and let
        AddPicture decide).
        """
        import base64
        import re
        import tempfile

        match = re.match(r"data:([^;,]+)?(?:;([^,]+))?,(.*)", href, re.DOTALL)
        if not match:
            return ""
        mime = (match.group(1) or "").strip().lower()
        encoding = (match.group(2) or "").strip().lower()
        payload = match.group(3) or ""

        ext_map = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/gif": ".gif",
            "image/webp": ".webp",
            "image/svg+xml": ".svg",
        }
        ext = ext_map.get(mime, ".bin")
        try:
            if encoding == "base64":
                data = base64.b64decode(payload, validate=False)
            else:
                from urllib.parse import unquote_to_bytes
                data = unquote_to_bytes(payload)
        except Exception as e:
            logger.warning(f"[SlideRenderer] Failed to decode data URI: {e}")
            return ""

        try:
            fd, path = tempfile.mkstemp(prefix="useit_dataimg_", suffix=ext)
            try:
                os.write(fd, data)
            finally:
                os.close(fd)
            return path
        except Exception as e:
            logger.warning(f"[SlideRenderer] Failed to write data URI temp: {e}")
            return ""

    def _render_group(self, elem: ET.Element, ctx: RenderContext) -> int:
        transform = elem.get("transform", "")
        group_style = ctx.resolve_style(elem)
        layer_id = elem.get("data-layer-id")
        layer_role = elem.get("data-layer-role") or elem.get("data-role")
        render_as = elem.get("data-render-as")
        layer_z = elem.get("data-layer-z") or elem.get("data-z")
        child_matrix = parse_transform_matrix(transform)
        child_ctx = ctx.with_layer(
            layer_id, layer_role, render_as, layer_z, group_style
        ).with_affine(child_matrix, group_style)

        count = 0
        for child in elem:
            count += self._render_element(child, child_ctx)
        return count

    def _render_path(self, elem: ET.Element, ctx: RenderContext) -> int:
        style = ctx.resolve_style(elem)
        d = elem.get("d", "").strip()
        if not d:
            return 0

        commands = parse_path_d(d)
        if not commands:
            return 0

        cmd_types = [c[0] for c in commands]
        if cmd_types == ["M", "L"]:
            _, mx, my = commands[0]
            _, lx, ly = commands[1]
            p1 = ctx.transform_point(mx, my)
            p2 = ctx.transform_point(lx, ly)
            shape = ctx.slide.Shapes.AddLine(p1[0], p1[1], p2[0], p2[1])
            self._apply_line_style(shape, style, elem)
            self._set_handle(shape, elem, ctx)
            return 1

        builder = None
        for cmd in commands:
            t = cmd[0]
            if t == "M":
                px, py = ctx.transform_point(cmd[1], cmd[2])
                if builder is not None:
                    try:
                        shape = builder.ConvertToShape()
                        self._apply_style(shape, style, elem, ctx)
                    except Exception:
                        pass
                builder = ctx.slide.Shapes.BuildFreeform(MSO_EDITING_CORNER, px, py)
            elif builder is None:
                continue
            elif t == "L":
                lx, ly = ctx.transform_point(cmd[1], cmd[2])
                builder.AddNodes(MSO_SEGMENT_LINE, MSO_EDITING_AUTO, lx, ly)
            elif t == "C":
                c1x, c1y = ctx.transform_point(cmd[1], cmd[2])
                c2x, c2y = ctx.transform_point(cmd[3], cmd[4])
                ex, ey = ctx.transform_point(cmd[5], cmd[6])
                builder.AddNodes(
                    MSO_SEGMENT_CURVE, MSO_EDITING_SMOOTH,
                    c1x, c1y, c2x, c2y, ex, ey,
                )
            elif t == "Z":
                pass  # closed on ConvertToShape

        if builder is None:
            return 0

        shape = builder.ConvertToShape()
        self._apply_style(shape, style, elem, ctx)
        self._set_handle(shape, elem, ctx)
        return 1

    def _render_use(self, elem: ET.Element, ctx: RenderContext) -> int:
        href = elem.get("href") or elem.get(f"{{{XLINK_NS}}}href") or ""
        ref_id = href.lstrip("#")
        if not ref_id or ref_id not in ctx.defs_map:
            return 0

        ref_elem = ctx.defs_map[ref_id]
        use_x = to_float(elem.get("x", "0"))
        use_y = to_float(elem.get("y", "0"))

        transform = elem.get("transform", "")
        child_mat = parse_transform_matrix(transform)
        use_translate = (1.0, 0.0, 0.0, 1.0, use_x, use_y)
        combined = compose_matrix(child_mat, use_translate)

        use_style = ctx.resolve_style(elem)
        child_ctx = ctx.with_affine(combined, use_style)

        ref_tag = strip_ns(ref_elem.tag)
        if ref_tag == "g":
            ref_transform = ref_elem.get("transform", "")
            ref_mat = parse_transform_matrix(ref_transform)
            ref_style = child_ctx.resolve_style(ref_elem)
            inner_ctx = child_ctx.with_affine(ref_mat, ref_style)
            count = 0
            for child in ref_elem:
                count += self._render_element(child, inner_ctx)
            return count
        else:
            return self._render_element(ref_elem, child_ctx)

    def _render_polygon(self, elem: ET.Element, ctx: RenderContext) -> int:
        """Render <polygon> or <polyline> via BuildFreeform."""
        style = ctx.resolve_style(elem)
        points_str = elem.get("points", "").strip()
        if not points_str:
            return 0

        pts = parse_polygon_points(points_str)
        if len(pts) < 2:
            return 0

        tx_pts = [ctx.transform_point(px, py) for px, py in pts]

        first = tx_pts[0]
        builder = ctx.slide.Shapes.BuildFreeform(MSO_EDITING_CORNER, first[0], first[1])
        for px, py in tx_pts[1:]:
            builder.AddNodes(MSO_SEGMENT_LINE, MSO_EDITING_AUTO, px, py)

        is_polygon = strip_ns(elem.tag) == "polygon"
        if is_polygon:
            builder.AddNodes(MSO_SEGMENT_LINE, MSO_EDITING_AUTO, first[0], first[1])

        shape = builder.ConvertToShape()
        self._apply_style(shape, style, elem, ctx)
        self._set_handle(shape, elem, ctx)
        return 1

    # ==================== Text span helpers ====================

    @staticmethod
    def _estimate_text_width(text: str, font_size: float, is_bold: bool = False) -> float:
        """Estimate rendered text width in points, CJK-aware with safety headroom.

        Default 0.65×fontSize per char massively under-estimates CJK and bold uppercase,
        which is the main reason single-line labels wrap on first render.
        """
        if not text or not font_size or font_size <= 0:
            return 0.0
        width = 0.0
        for ch in text:
            cp = ord(ch)
            if (
                0x4E00 <= cp <= 0x9FFF      # CJK Unified Ideographs
                or 0x3400 <= cp <= 0x4DBF   # CJK Extension A
                or 0xF900 <= cp <= 0xFAFF   # CJK Compatibility Ideographs
                or 0x3000 <= cp <= 0x303F   # CJK Symbols and Punctuation
                or 0xFF00 <= cp <= 0xFFEF   # Halfwidth and Fullwidth Forms
                or 0x3040 <= cp <= 0x30FF   # Hiragana / Katakana
                or 0xAC00 <= cp <= 0xD7AF   # Hangul Syllables
            ):
                width += font_size * 1.0
            elif ch == " ":
                width += font_size * 0.30
            elif ch.isupper() or ch.isdigit():
                width += font_size * 0.62
            elif ch.islower():
                width += font_size * 0.52
            else:
                width += font_size * 0.55
        if is_bold:
            width *= 1.06
        return width * 1.18  # safety headroom against font metric drift

    def _collect_text_spans(
        self, elem: ET.Element, parent_style: Dict, ctx: RenderContext
    ) -> List[Dict]:
        spans = []
        if elem.text and elem.text.strip():
            spans.append(self._make_span(elem.text.strip(), elem, parent_style, ctx))
        for child in elem:
            tag = strip_ns(child.tag)
            if tag == "tspan":
                text = (child.text or "").strip()
                if text:
                    child_style = merge_style(parent_style, ctx.resolve_style(child))
                    spans.append(self._make_span(text, child, child_style, ctx))
            if child.tail and child.tail.strip():
                spans.append(self._make_span(child.tail.strip(), elem, parent_style, ctx))
        return spans

    def _make_span(
        self, text: str, elem: ET.Element, style: Dict, ctx: RenderContext
    ) -> Dict[str, Any]:
        font_size_raw = style.get("font-size", elem.get("font-size"))
        font_weight = style.get("font-weight", elem.get("font-weight", "normal"))
        font_style_val = style.get("font-style", elem.get("font-style", "normal"))
        font_family = style.get("font-family", elem.get("font-family"))
        fill = style.get("fill", elem.get("fill"))

        gradient_def = None
        if fill and fill.strip().startswith("url("):
            ref = parse_url_ref(fill)
            if ref and ref in ctx.gradient_defs:
                gradient_def = ctx.gradient_defs[ref]
                fill = self._resolve_gradient_color(fill, ctx) or fill

        scaled_size = to_float(font_size_raw) * ctx._scale_y if font_size_raw else None

        return {
            "text": text,
            "font_name": font_family.split(",")[0].strip().strip("'\"") if font_family else None,
            "font_size": scaled_size,
            "bold": font_weight in ("bold", "700", "800", "900"),
            "italic": font_style_val == "italic",
            "fill": fill,
            "gradient_def": gradient_def,
        }

    # ==================== foreignObject (HTML table) ====================

    _XHTML_NS = "http://www.w3.org/1999/xhtml"

    def _render_foreign_object(self, elem: "ET.Element", ctx: "RenderContext") -> int:
        """Render <foreignObject> containing an HTML <table> as a native PPT table."""
        from ..constants import DEFAULT_TABLE_STYLE, resolve_table_style

        table_elem = self._find_html_table(elem)
        if table_elem is None:
            return 0

        x = ctx.tx(to_float(elem.get("x", "0")))
        y = ctx.ty(to_float(elem.get("y", "0")))
        w = ctx.sx(to_float(elem.get("width", "400")))
        h = ctx.sy(to_float(elem.get("height", "200")))

        data_matrix, has_header = self._parse_html_table(table_elem)
        if not data_matrix:
            logger.warning("[SlideRenderer] foreignObject table has no data rows")
            return 0

        num_rows = len(data_matrix)
        num_cols = max(len(row) for row in data_matrix)

        try:
            shape = ctx.slide.Shapes.AddTable(num_rows, num_cols, x, y, w, h)
            table = shape.Table

            # Apply table style
            style_name = elem.get("data-table-style") or DEFAULT_TABLE_STYLE
            style_guid = resolve_table_style(style_name)
            if style_guid:
                try:
                    table.ApplyStyle(style_guid)
                except Exception as e:
                    logger.warning(
                        f"[SlideRenderer] ApplyStyle failed ({style_name}): {e}"
                    )

            for r_idx, row in enumerate(data_matrix):
                for c_idx, val in enumerate(row):
                    if c_idx < num_cols:
                        cell = table.Cell(r_idx + 1, c_idx + 1)
                        cell.Shape.TextFrame.TextRange.Text = (
                            str(val) if val is not None else ""
                        )

            first_row_attr = elem.get("data-first-row-header", "").lower()
            if first_row_attr == "false":
                table.FirstRow = False
            elif first_row_attr == "true" or has_header:
                table.FirstRow = True

            self._set_handle(shape, elem, ctx)
            logger.info(
                f"[SlideRenderer] Inserted table {num_rows}x{num_cols} "
                f"style={style_name}, handle={elem.get('data-handle-id')}"
            )
            return 1
        except Exception as e:
            logger.warning(f"[SlideRenderer] Failed to insert foreignObject table: {e}")
            return 0

    def _find_html_table(self, foreign_obj: "ET.Element"):
        """Find the first <table> element inside a <foreignObject>."""
        import xml.etree.ElementTree as _ET

        for ns in (f"{{{self._XHTML_NS}}}", ""):
            table = foreign_obj.find(f".//{ns}table")
            if table is not None:
                return table
        for child in foreign_obj.iter():
            if strip_ns(child.tag) == "table":
                return child
        return None

    def _parse_html_table(self, table_elem: "ET.Element"):
        """Parse an HTML <table> element into (data_matrix, has_header)."""
        has_header = False
        rows: List[List[str]] = []

        def _find(parent, tag):
            for ns in (f"{{{self._XHTML_NS}}}", ""):
                result = parent.find(f"{ns}{tag}")
                if result is not None:
                    return result
            return None

        def _findall(parent, tag):
            for ns in (f"{{{self._XHTML_NS}}}", ""):
                results = parent.findall(f"{ns}{tag}")
                if results:
                    return results
            return []

        def _cell_text(cell_elem) -> str:
            parts = []
            if cell_elem.text:
                parts.append(cell_elem.text.strip())
            for child in cell_elem:
                if child.text:
                    parts.append(child.text.strip())
                if child.tail:
                    parts.append(child.tail.strip())
            return " ".join(p for p in parts if p)

        def _process_rows(container):
            for tr in _findall(container, "tr"):
                row = []
                for cell in list(tr):
                    tag = strip_ns(cell.tag)
                    if tag in ("th", "td"):
                        row.append(_cell_text(cell))
                if row:
                    rows.append(row)

        thead = _find(table_elem, "thead")
        if thead is not None:
            has_header = True
            _process_rows(thead)

        tbody = _find(table_elem, "tbody")
        if tbody is not None:
            _process_rows(tbody)
        elif thead is not None:
            for tr in _findall(table_elem, "tr"):
                row = []
                for cell in list(tr):
                    tag = strip_ns(cell.tag)
                    if tag in ("th", "td"):
                        row.append(_cell_text(cell))
                if row:
                    rows.append(row)
        else:
            first_row_has_th = False
            for tr in _findall(table_elem, "tr"):
                row = []
                for cell in list(tr):
                    tag = strip_ns(cell.tag)
                    if tag in ("th", "td"):
                        row.append(_cell_text(cell))
                        if tag == "th" and len(rows) == 0:
                            first_row_has_th = True
                if row:
                    rows.append(row)
            if first_row_has_th:
                has_header = True

        return rows, has_header
