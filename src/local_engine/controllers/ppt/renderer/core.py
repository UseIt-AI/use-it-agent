"""SlideRenderer: main entry point for SVG -> PowerPoint conversion.

Parses an SVG string, walks the element tree, and dispatches to
shape-specific renderers via the ShapeRendererMixin and StyleMixin.
"""

import copy
import json
import logging
import os
import tempfile
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

from .context import RenderContext
from .models import FilterDef, GradientDef
from ..constants import TEXT_ALIGN, parse_color
from .parsers import (
    parse_css,
    parse_gradient_stops,
    parse_url_ref,
    pct_to_frac,
    strip_ns,
    to_float,
)
from .shapes import ShapeRendererMixin
from .styles import StyleMixin

logger = logging.getLogger(__name__)


class SlideRenderer(ShapeRendererMixin, StyleMixin):
    """SVG -> PowerPoint shapes renderer with CSS / transform / path support."""

    def render(
        self,
        slide,
        svg_string: str,
        slide_width: float,
        slide_height: float,
    ) -> Dict[str, Any]:
        handles: Dict[str, str] = {}
        placeholders: List[Dict] = []
        shapes_created = 0

        try:
            root = ET.fromstring(svg_string)
        except ET.ParseError as e:
            return {
                "success": False, "handles": {}, "placeholders": [],
                "shapes_created": 0, "error": f"SVG parse error: {e}",
            }

        css_classes, defs_map, gradient_defs, filter_defs = self._parse_defs(root)
        scale_x, scale_y, offset_x, offset_y = self._parse_viewbox(
            root, slide_width, slide_height
        )

        ctx = RenderContext(
            slide=slide,
            scale_x=scale_x, scale_y=scale_y,
            offset_x=offset_x, offset_y=offset_y,
            slide_width=slide_width, slide_height=slide_height,
            handles=handles, placeholders=placeholders,
            inherited_style={},
            css_classes=css_classes,
            defs_map=defs_map,
            gradient_defs=gradient_defs,
            filter_defs=filter_defs,
        )

        for child in root:
            if strip_ns(child.tag) == "defs":
                continue
            shapes_created += self._render_element(child, ctx)

        return {
            "success": True, "handles": handles, "placeholders": placeholders,
            "shapes_created": shapes_created, "error": None,
        }

    def render_layered(
        self,
        slide,
        svg_string: str,
        slide_width: float,
        slide_height: float,
        layers: Optional[List[Dict[str, Any]]] = None,
        palette: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Render SVG with logical layer metadata persisted onto PPT shapes."""
        handles: Dict[str, str] = {}
        placeholders: List[Dict] = []
        shapes_created = 0

        try:
            root = ET.fromstring(svg_string)
        except ET.ParseError as e:
            return {
                "success": False, "handles": {}, "placeholders": [],
                "shapes_created": 0, "error": f"SVG parse error: {e}",
            }

        css_classes, defs_map, gradient_defs, filter_defs = self._parse_defs(root)
        scale_x, scale_y, offset_x, offset_y = self._parse_viewbox(
            root, slide_width, slide_height
        )
        ctx = RenderContext(
            slide=slide,
            scale_x=scale_x, scale_y=scale_y,
            offset_x=offset_x, offset_y=offset_y,
            slide_width=slide_width, slide_height=slide_height,
            handles=handles, placeholders=placeholders,
            inherited_style={},
            css_classes=css_classes,
            defs_map=defs_map,
            gradient_defs=gradient_defs,
            filter_defs=filter_defs,
        )

        layer_meta_by_id = self._layer_meta_by_id(layers)
        for child in self._ordered_layer_children(root, layers):
            if strip_ns(child.tag) == "defs":
                continue
            self._apply_layer_params_to_element(child, layer_meta_by_id)
            if self._is_image_layer(child):
                shapes_created += self._render_layer_as_image(child, root, ctx)
                continue
            shapes_created += self._render_element(child, ctx)

        # Persist blueprint declaration on the slide so the layout linter
        # and snapshot extractor can validate against it on later turns.
        self._save_blueprint(slide, layers, palette)

        return {
            "success": True, "handles": handles, "placeholders": placeholders,
            "shapes_created": shapes_created, "error": None,
        }

    # ==================== Blueprint persistence ====================

    BLUEPRINT_CHUNK = 4000
    BLUEPRINT_MAX_CHUNKS = 20

    @classmethod
    def _save_blueprint(
        cls,
        slide,
        layers: Optional[List[Dict[str, Any]]],
        palette: Optional[List[str]] = None,
    ) -> None:
        """Store blueprint declarations on slide.Tags as chunked JSON.

        The persisted structure is always ``{"layers": [...], "palette": [...]}``.
        Per-tag value length is bounded for safety; we split the JSON into
        sequential chunks ``useit_blueprint_<i>`` and write the count to
        ``useit_blueprint_n``. Old chunks are cleared first to avoid stale data.
        """
        # Always clear stale blueprint tags first.
        try:
            slide.Tags.Delete("useit_blueprint_n")
        except Exception:
            pass
        for i in range(cls.BLUEPRINT_MAX_CHUNKS):
            try:
                slide.Tags.Delete(f"useit_blueprint_{i}")
            except Exception:
                pass

        if not layers and not palette:
            return
        doc: Dict[str, Any] = {"layers": layers or []}
        if palette:
            doc["palette"] = palette
        try:
            payload = json.dumps(doc, ensure_ascii=False, separators=(",", ":"))
        except Exception as e:
            logger.warning(f"[Blueprint] serialize failed: {e}")
            return
        chunks = [
            payload[i : i + cls.BLUEPRINT_CHUNK]
            for i in range(0, len(payload), cls.BLUEPRINT_CHUNK)
        ]
        if len(chunks) > cls.BLUEPRINT_MAX_CHUNKS:
            logger.warning(
                f"[Blueprint] {len(chunks)} chunks exceeds limit; truncating"
            )
            chunks = chunks[: cls.BLUEPRINT_MAX_CHUNKS]
        try:
            slide.Tags.Add("useit_blueprint_n", str(len(chunks)))
            for i, c in enumerate(chunks):
                slide.Tags.Add(f"useit_blueprint_{i}", c)
        except Exception as e:
            logger.warning(f"[Blueprint] write failed: {e}")

    @classmethod
    def _load_blueprint(cls, slide) -> Dict[str, Any]:
        """Load blueprint document. Returns ``{"layers": [...], "palette": [...]}``.

        Backward-compatible: if the persisted payload is a bare ``list`` (legacy
        format), it's interpreted as ``layers``.
        """
        try:
            n_str = slide.Tags("useit_blueprint_n") or ""
        except Exception:
            return {"layers": [], "palette": []}
        if not n_str:
            return {"layers": [], "palette": []}
        try:
            n = int(n_str)
        except Exception:
            return {"layers": [], "palette": []}
        parts: List[str] = []
        for i in range(n):
            try:
                parts.append(slide.Tags(f"useit_blueprint_{i}") or "")
            except Exception:
                return {"layers": [], "palette": []}
        payload = "".join(parts)
        if not payload:
            return {"layers": [], "palette": []}
        try:
            data = json.loads(payload)
        except Exception:
            return {"layers": [], "palette": []}
        if isinstance(data, list):  # legacy format
            return {"layers": data, "palette": []}
        if isinstance(data, dict):
            return {
                "layers": data.get("layers") or [],
                "palette": data.get("palette") or [],
            }
        return {"layers": [], "palette": []}

    # ==================== Patch Mode ====================

    def patch(
        self,
        slide,
        svg_string: str,
        slide_width: float,
        slide_height: float,
    ) -> Dict[str, Any]:
        """Patch-mode rendering: update/delete/create shapes by data-handle-id.

        For each SVG element with data-handle-id:
          - data-action="delete"  → delete the matching shape
          - shape.Name matches    → update the existing shape in place
          - no match              → create a new shape (supplement)
        Shapes not mentioned in the SVG are left untouched.
        """
        handles: Dict[str, str] = {}
        shapes_created = 0
        shapes_updated = 0
        shapes_deleted = 0

        try:
            root = ET.fromstring(svg_string)
        except ET.ParseError as e:
            return {
                "success": False, "handles": {}, "placeholders": [],
                "shapes_created": 0, "error": f"SVG parse error: {e}",
            }

        css_classes, defs_map, gradient_defs, filter_defs = self._parse_defs(root)
        scale_x, scale_y, offset_x, offset_y = self._parse_viewbox(
            root, slide_width, slide_height
        )

        ctx = RenderContext(
            slide=slide,
            scale_x=scale_x, scale_y=scale_y,
            offset_x=offset_x, offset_y=offset_y,
            slide_width=slide_width, slide_height=slide_height,
            handles=handles, placeholders=[],
            inherited_style={},
            css_classes=css_classes,
            defs_map=defs_map,
            gradient_defs=gradient_defs,
            filter_defs=filter_defs,
        )

        # Build shape.Name → COM shape index map
        shape_index: Dict[str, int] = {}
        for i in range(1, slide.Shapes.Count + 1):
            try:
                name = slide.Shapes(i).Name
                if name:
                    shape_index[name] = i
            except Exception:
                continue

        new_elements: List[ET.Element] = []

        # Walk all SVG elements (including nested inside <g>)
        for elem in self._collect_patch_elements(root):
            handle_id = elem.get("data-handle-id")
            data_action = elem.get("data-action", "")

            if not handle_id:
                new_elements.append(elem)
                continue

            if handle_id in shape_index:
                if data_action == "delete":
                    try:
                        slide.Shapes(shape_index[handle_id]).Delete()
                        shapes_deleted += 1
                        logger.info(f"[Patch] Deleted shape '{handle_id}'")
                        # Rebuild index after deletion (indices shift)
                        shape_index = self._rebuild_shape_index(slide)
                    except Exception as e:
                        logger.warning(f"[Patch] Failed to delete '{handle_id}': {e}")
                else:
                    try:
                        shape = slide.Shapes(shape_index[handle_id])
                        self._merge_update_shape(shape, elem, ctx)
                        shapes_updated += 1
                        handles[handle_id] = handle_id
                        logger.info(f"[Patch] Updated shape '{handle_id}'")
                    except Exception as e:
                        logger.warning(f"[Patch] Failed to update '{handle_id}': {e}")
            else:
                if data_action == "delete":
                    logger.debug(f"[Patch] Ignoring delete for non-existent '{handle_id}'")
                else:
                    new_elements.append(elem)

        # Create new elements using standard supplement logic
        if new_elements:
            for elem in new_elements:
                try:
                    count = self._render_element(elem, ctx)
                    shapes_created += count
                except Exception as e:
                    tag = strip_ns(elem.tag)
                    hid = elem.get("data-handle-id", "?")
                    logger.warning(f"[Patch] Failed to create <{tag}> '{hid}': {e}")

        return {
            "success": True,
            "handles": handles,
            "placeholders": [],
            "shapes_created": shapes_created,
            "shapes_updated": shapes_updated,
            "shapes_deleted": shapes_deleted,
            "error": None,
        }

    def patch_layered(
        self,
        slide,
        svg_string: str,
        slide_width: float,
        slide_height: float,
        layers: Optional[List[Dict[str, Any]]] = None,
        patch_scope: Optional[Dict[str, Any]] = None,
        palette: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Layer-scoped patch: replace all shapes belonging to target layer_ids."""
        scope = patch_scope or {}
        layer_ids = scope.get("layer_ids") or scope.get("layers") or []
        if isinstance(layer_ids, str):
            layer_ids = [layer_ids]
        target_layer_ids = {str(layer_id) for layer_id in layer_ids if layer_id}
        if scope.get("type") != "layer" or not target_layer_ids:
            return self.patch(slide, svg_string, slide_width, slide_height)

        try:
            root = ET.fromstring(svg_string)
        except ET.ParseError as e:
            return {
                "success": False, "handles": {}, "placeholders": [],
                "shapes_created": 0, "error": f"SVG parse error: {e}",
            }

        shapes_deleted = self._delete_shapes_by_layer(slide, target_layer_ids)
        target_svg = self._svg_with_only_layers(root, target_layer_ids)

        # Merge incoming layer deltas into the existing blueprint so partial
        # patches don't erase declarations for layers that weren't touched.
        existing_doc = self._load_blueprint(slide)
        merged_layers = self._merge_blueprint(
            existing_doc.get("layers") or [], layers
        )
        # Palette: incoming wins if provided, else preserve existing.
        merged_palette = palette if palette else (existing_doc.get("palette") or [])

        render_result = self.render_layered(
            slide, ET.tostring(target_svg, encoding="unicode"),
            slide_width, slide_height, merged_layers, merged_palette,
        )
        render_result["shapes_deleted"] = shapes_deleted
        render_result.setdefault("shapes_updated", 0)
        return render_result

    @staticmethod
    def _merge_blueprint(
        existing: List[Dict[str, Any]],
        delta: Optional[List[Dict[str, Any]]],
    ) -> List[Dict[str, Any]]:
        """Merge new layer specs into existing blueprint, dedup by id (delta wins)."""
        if not delta:
            return existing or []
        by_id: Dict[str, Dict[str, Any]] = {}
        order: List[str] = []
        for spec in (existing or []):
            lid = spec.get("id")
            if lid and lid not in by_id:
                by_id[lid] = dict(spec)
                order.append(lid)
        for spec in delta:
            lid = spec.get("id")
            if not lid:
                continue
            if lid in by_id:
                by_id[lid].update(spec)
            else:
                by_id[lid] = dict(spec)
                order.append(lid)
        return [by_id[lid] for lid in order]

    @staticmethod
    def _rebuild_shape_index(slide) -> Dict[str, int]:
        idx: Dict[str, int] = {}
        for i in range(1, slide.Shapes.Count + 1):
            try:
                name = slide.Shapes(i).Name
                if name:
                    idx[name] = i
            except Exception:
                continue
        return idx

    def _collect_patch_elements(self, root: ET.Element) -> List[ET.Element]:
        """Collect all actionable SVG elements for patch mode.

        Flattens top-level <g> wrappers used purely for data-action="delete",
        but preserves structural <g> groups (with transforms) for supplement rendering.
        """
        elements: List[ET.Element] = []
        for child in root:
            tag = strip_ns(child.tag)
            if tag == "defs":
                continue

            handle_id = child.get("data-handle-id")
            data_action = child.get("data-action", "")

            if handle_id:
                elements.append(child)
            elif tag == "g" and not handle_id:
                # Recurse into anonymous groups
                for sub in child:
                    elements.append(sub)
            else:
                elements.append(child)
        return elements

    def _merge_update_shape(
        self, shape, elem: ET.Element, ctx: RenderContext
    ) -> None:
        """Update an existing PPT shape's properties from an SVG element.

        Only attributes explicitly present in the SVG element are applied;
        omitted attributes leave the shape's current values untouched.
        """
        tag = strip_ns(elem.tag)
        style = ctx.resolve_style(elem)

        # ── 1. Geometry ──
        self._patch_geometry(shape, elem, tag, ctx)

        # ── 2. Fill (only if explicitly specified) ──
        fill_val = style.get("fill", elem.get("fill"))
        if fill_val is not None:
            ref = parse_url_ref(fill_val)
            if ref and ref in ctx.gradient_defs:
                try:
                    from .styles import StyleMixin
                    StyleMixin._apply_gradient_fill_static(shape, ctx.gradient_defs[ref])
                except Exception:
                    pass
            elif fill_val.lower() == "none":
                try:
                    shape.Fill.Background()
                except Exception:
                    pass
            else:
                color = parse_color(fill_val)
                if color is not None:
                    if tag == "text":
                        # For text elements, fill sets font color
                        try:
                            shape.TextFrame.TextRange.Font.Color.RGB = color
                        except Exception:
                            pass
                    else:
                        try:
                            shape.Fill.Solid()
                            shape.Fill.ForeColor.RGB = color
                        except Exception:
                            pass

        # ── 3. Stroke / Line ──
        stroke_val = style.get("stroke", elem.get("stroke"))
        if stroke_val is not None:
            if stroke_val.lower() == "none":
                try:
                    shape.Line.Visible = False
                except Exception:
                    pass
            else:
                color = parse_color(stroke_val)
                if color is not None:
                    try:
                        shape.Line.Visible = True
                        shape.Line.ForeColor.RGB = color
                    except Exception:
                        pass

        stroke_width = style.get("stroke-width", elem.get("stroke-width"))
        if stroke_width is not None:
            try:
                shape.Line.Weight = float(stroke_width) * ctx._scale_x
            except Exception:
                pass

        # ── 4. Opacity ──
        opacity_val = style.get("opacity", elem.get("opacity"))
        if opacity_val is not None:
            # Placeholder — PPT shape-level transparency is limited
            pass

        # ── 5. Text content + font (only for text-bearing elements) ──
        if tag == "text":
            self._patch_text(shape, elem, style, ctx)

    def _patch_geometry(
        self, shape, elem: ET.Element, tag: str, ctx: RenderContext
    ) -> None:
        """Update shape position/size from SVG element attributes."""
        if tag in ("rect", "image"):
            if elem.get("x") is not None:
                shape.Left = ctx.tx(to_float(elem.get("x")))
            if elem.get("y") is not None:
                shape.Top = ctx.ty(to_float(elem.get("y")))
            if elem.get("width") is not None:
                shape.Width = ctx.sx(to_float(elem.get("width")))
            if elem.get("height") is not None:
                shape.Height = ctx.sy(to_float(elem.get("height")))

        elif tag == "text":
            # Text positioning: use same logic as render for anchor adjustment
            if elem.get("x") is not None or elem.get("y") is not None:
                raw_size = to_float(
                    style.get("font-size", elem.get("font-size", "18"))
                    if (style := ctx.resolve_style(elem)) else elem.get("font-size", "18")
                )
                font_size = raw_size * ctx._scale_y

                x = ctx.tx(to_float(elem.get("x", "0")))
                y = ctx.ty(to_float(elem.get("y", "0")))

                anchor = (ctx.resolve_style(elem).get("text-anchor")
                          or elem.get("text-anchor", "start"))
                dominant_baseline = (ctx.resolve_style(elem).get("dominant-baseline")
                                     or elem.get("dominant-baseline", ""))

                # Adjust x for anchor
                cur_w = shape.Width
                if anchor == "middle":
                    x = x - cur_w / 2
                elif anchor == "end":
                    x = x - cur_w

                # Adjust y for baseline
                if dominant_baseline in ("central", "middle"):
                    y = y - shape.Height / 2
                elif dominant_baseline in ("hanging", "text-before-edge"):
                    pass
                else:
                    y = y - font_size * 0.85

                shape.Left = max(0, x)
                shape.Top = max(0, y)

        elif tag == "circle":
            cx = to_float(elem.get("cx"))
            cy = to_float(elem.get("cy"))
            r = to_float(elem.get("r"))
            if elem.get("cx") is not None:
                r_x = ctx.sx(r)
                shape.Left = ctx.tx(cx) - r_x
            if elem.get("cy") is not None:
                r_y = ctx.sy(r)
                shape.Top = ctx.ty(cy) - r_y
            if elem.get("r") is not None:
                shape.Width = ctx.sx(r) * 2
                shape.Height = ctx.sy(r) * 2

        elif tag == "ellipse":
            cx = to_float(elem.get("cx"))
            cy = to_float(elem.get("cy"))
            rx = to_float(elem.get("rx"))
            ry = to_float(elem.get("ry"))
            if elem.get("cx") is not None:
                shape.Left = ctx.tx(cx) - ctx.sx(rx)
            if elem.get("cy") is not None:
                shape.Top = ctx.ty(cy) - ctx.sy(ry)
            if elem.get("rx") is not None:
                shape.Width = ctx.sx(rx) * 2
            if elem.get("ry") is not None:
                shape.Height = ctx.sy(ry) * 2

    def _patch_text(
        self, shape, elem: ET.Element, style: Dict, ctx: RenderContext
    ) -> None:
        """Update text content and font properties on an existing text shape."""
        # Collect text from element and tspan children
        texts = []
        if elem.text and elem.text.strip():
            texts.append(elem.text.strip())
        for child in elem:
            if strip_ns(child.tag) == "tspan":
                t = (child.text or "").strip()
                if t:
                    texts.append(t)

        if texts:
            try:
                new_text = "\r".join(texts)
                shape.TextFrame.TextRange.Text = new_text
            except Exception:
                pass

        # Font properties — only apply if explicitly set in SVG
        try:
            font = shape.TextFrame.TextRange.Font
        except Exception:
            return

        fs = style.get("font-size", elem.get("font-size"))
        if fs is not None:
            try:
                font.Size = to_float(fs) * ctx._scale_y
            except Exception:
                pass

        fn = style.get("font-family", elem.get("font-family"))
        if fn is not None:
            try:
                font.Name = fn.strip("'\"")
            except Exception:
                pass

        fw = style.get("font-weight", elem.get("font-weight"))
        if fw is not None:
            try:
                font.Bold = fw == "bold"
            except Exception:
                pass

        fi = style.get("font-style", elem.get("font-style"))
        if fi is not None:
            try:
                font.Italic = fi == "italic"
            except Exception:
                pass

        # text-anchor → paragraph alignment
        anchor = style.get("text-anchor", elem.get("text-anchor"))
        if anchor is not None:
            align_map = {"start": "left", "middle": "center", "end": "right"}
            ppt_align = TEXT_ALIGN.get(align_map.get(anchor, "left"))
            if ppt_align is not None:
                try:
                    for i in range(1, shape.TextFrame.TextRange.Paragraphs().Count + 1):
                        shape.TextFrame.TextRange.Paragraphs(i).ParagraphFormat.Alignment = ppt_align
                except Exception:
                    pass

    # ==================== Defs / CSS ====================

    def _parse_defs(
        self, root: ET.Element
    ) -> Tuple[
        Dict[str, Dict[str, str]],
        Dict[str, ET.Element],
        Dict[str, GradientDef],
        Dict[str, FilterDef],
    ]:
        css_classes: Dict[str, Dict[str, str]] = {}
        defs_map: Dict[str, ET.Element] = {}
        gradient_defs: Dict[str, GradientDef] = {}
        filter_defs: Dict[str, FilterDef] = {}

        for elem in root:
            if strip_ns(elem.tag) != "defs":
                continue
            for child in elem:
                child_tag = strip_ns(child.tag)

                if child_tag == "style":
                    css_classes.update(parse_css(child.text or ""))

                elif child_tag == "linearGradient":
                    gid = child.get("id")
                    if gid:
                        gradient_defs[gid] = self._parse_linear_gradient(child)

                elif child_tag == "radialGradient":
                    gid = child.get("id")
                    if gid:
                        gradient_defs[gid] = self._parse_radial_gradient(child)

                elif child_tag == "filter":
                    fid = child.get("id")
                    if fid:
                        fdef = self._parse_filter(child)
                        if fdef:
                            filter_defs[fid] = fdef

                elem_id = child.get("id")
                if elem_id:
                    defs_map[elem_id] = child

        return css_classes, defs_map, gradient_defs, filter_defs

    # ---- gradient / filter parsers ----

    @staticmethod
    def _parse_linear_gradient(elem: ET.Element) -> GradientDef:
        gdef = GradientDef(
            kind="linear",
            x1=pct_to_frac(elem.get("x1", "0%")),
            y1=pct_to_frac(elem.get("y1", "0%")),
            x2=pct_to_frac(elem.get("x2", "100%")),
            y2=pct_to_frac(elem.get("y2", "0%")),
        )
        gdef.stops = parse_gradient_stops(elem)
        return gdef

    @staticmethod
    def _parse_radial_gradient(elem: ET.Element) -> GradientDef:
        gdef = GradientDef(
            kind="radial",
            cx=pct_to_frac(elem.get("cx", "50%")),
            cy=pct_to_frac(elem.get("cy", "50%")),
            r=pct_to_frac(elem.get("r", "50%")),
        )
        gdef.stops = parse_gradient_stops(elem)
        return gdef

    @staticmethod
    def _parse_filter(elem: ET.Element) -> Optional[FilterDef]:
        for child in elem:
            tag = strip_ns(child.tag)
            if tag == "feGaussianBlur":
                std = to_float(child.get("stdDeviation", "0"), 0.0)
                if std > 0:
                    return FilterDef(kind="glow", blur_radius=std)
            elif tag == "feDropShadow":
                std = to_float(child.get("stdDeviation", "0"), 0.0)
                dx = to_float(child.get("dx", "0"), 0.0)
                dy = to_float(child.get("dy", "0"), 0.0)
                color = child.get("flood-color", "#000000")
                opacity = to_float(child.get("flood-opacity", "1"), 1.0)
                if std > 0:
                    return FilterDef(
                        kind="shadow", blur_radius=std,
                        shadow_dx=dx, shadow_dy=dy,
                        shadow_color=color, shadow_opacity=opacity,
                    )
        return None

    # ==================== ViewBox ====================

    def _parse_viewbox(
        self, root: ET.Element, slide_w: float, slide_h: float
    ) -> Tuple[float, float, float, float]:
        vb = root.get("viewBox")
        if vb:
            parts = vb.replace(",", " ").split()
            if len(parts) == 4:
                vb_x, vb_y, vb_w, vb_h = (float(p) for p in parts)
                sx = slide_w / vb_w if vb_w else 1.0
                sy = slide_h / vb_h if vb_h else 1.0
                return sx, sy, -vb_x * sx, -vb_y * sy

        svg_w = to_float(root.get("width"), slide_w)
        svg_h = to_float(root.get("height"), slide_h)
        sx = slide_w / svg_w if svg_w else 1.0
        sy = slide_h / svg_h if svg_h else 1.0
        return sx, sy, 0.0, 0.0

    # ==================== Element Dispatch ====================

    def _render_element(self, elem: ET.Element, ctx: RenderContext) -> int:
        tag = strip_ns(elem.tag)

        if elem.get("data-placeholder"):
            self._record_placeholder(elem, ctx)
            return 0

        handler = {
            "rect": self._render_rect,
            "ellipse": self._render_ellipse,
            "circle": self._render_circle,
            "text": self._render_text,
            "line": self._render_line,
            "polygon": self._render_polygon,
            "polyline": self._render_polygon,
            "path": self._render_path,
            "image": self._render_image,
            "g": self._render_group,
            "use": self._render_use,
            "foreignObject": self._render_foreign_object,
            "foreignobject": self._render_foreign_object,
        }.get(tag)

        if not handler:
            return 0

        filter_ref = parse_url_ref(
            ctx.resolve_style(elem).get("filter", elem.get("filter", ""))
        )
        shapes_before = ctx.slide.Shapes.Count if filter_ref else 0

        try:
            count = handler(elem, ctx)
        except Exception as e:
            logger.warning(f"[SlideRenderer] Failed to render <{tag}>: {e}")
            return 0

        if filter_ref and count > 0:
            fdef = ctx.filter_defs.get(filter_ref)
            if fdef:
                shapes_after = ctx.slide.Shapes.Count
                for i in range(shapes_before + 1, shapes_after + 1):
                    try:
                        if fdef.kind == "shadow":
                            self._apply_shadow(ctx.slide.Shapes(i), fdef)
                        else:
                            self._apply_glow(ctx.slide.Shapes(i), fdef)
                    except Exception:
                        pass

        return count

    # ==================== Helpers ====================

    @staticmethod
    def _layer_attrs(elem: ET.Element) -> Dict[str, Optional[str]]:
        return {
            "layer_id": elem.get("data-layer-id"),
            "layer_role": elem.get("data-layer-role") or elem.get("data-role"),
            "render_as": elem.get("data-render-as"),
            "layer_z": elem.get("data-layer-z") or elem.get("data-z"),
        }

    def _ordered_layer_children(
        self,
        root: ET.Element,
        layers: Optional[List[Dict[str, Any]]] = None,
    ) -> List[ET.Element]:
        children = [child for child in root if strip_ns(child.tag) != "defs"]
        z_by_id = {}
        for layer in layers or []:
            if isinstance(layer, dict) and layer.get("id") is not None:
                try:
                    z_by_id[str(layer["id"])] = float(layer.get("z", 0))
                except (TypeError, ValueError):
                    z_by_id[str(layer["id"])] = 0.0

        def sort_key(item: Tuple[int, ET.Element]) -> Tuple[float, int]:
            idx, elem = item
            layer_id = elem.get("data-layer-id")
            if layer_id and layer_id in z_by_id:
                return z_by_id[layer_id], idx
            try:
                return float(elem.get("data-layer-z") or elem.get("data-z") or idx), idx
            except (TypeError, ValueError):
                return float(idx), idx

        return [elem for _, elem in sorted(enumerate(children), key=sort_key)]

    @staticmethod
    def _layer_meta_by_id(
        layers: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        result = {}
        for layer in layers or []:
            if isinstance(layer, dict) and layer.get("id") is not None:
                result[str(layer["id"])] = layer
        return result

    @staticmethod
    def _apply_layer_params_to_element(
        elem: ET.Element,
        layer_meta_by_id: Dict[str, Dict[str, Any]],
    ) -> None:
        layer_id = elem.get("data-layer-id")
        if not layer_id:
            return
        meta = layer_meta_by_id.get(layer_id) or {}
        attr_map = {
            "role": "data-layer-role",
            "render_as": "data-render-as",
            "z": "data-layer-z",
        }
        for meta_key, attr_name in attr_map.items():
            if elem.get(attr_name) is None and meta.get(meta_key) is not None:
                elem.set(attr_name, str(meta[meta_key]))

    def _svg_with_only_layers(
        self,
        root: ET.Element,
        target_layer_ids: set[str],
    ) -> ET.Element:
        new_root = copy.deepcopy(root)
        for child in list(new_root):
            if strip_ns(child.tag) == "defs":
                continue
            layer_id = child.get("data-layer-id")
            if layer_id not in target_layer_ids:
                new_root.remove(child)
        return new_root

    # ==================== Image-layer rasterization ====================

    @staticmethod
    def _is_image_layer(elem: ET.Element) -> bool:
        """A layer is rasterized when its top-level element opts in via
        ``data-render-as="image"``. The flag may sit on a <g> wrapper or any
        other top-level element that carries a ``data-layer-id``.
        """
        return (elem.get("data-render-as") or "").strip().lower() == "image"

    def _render_layer_as_image(
        self,
        layer_elem: ET.Element,
        root: ET.Element,
        ctx: RenderContext,
    ) -> int:
        """Insert a layer as a single Picture using PowerPoint's native SVG
        importer.

        The layer subtree is wrapped in a fresh standalone SVG (preserving the
        original ``viewBox`` and a deep copy of ``<defs>``) and written to a
        temp ``.svg`` file. ``Shapes.AddPicture`` on PowerPoint 2019+ handles
        the rasterization. The picture spans the full slide so the layer
        appears at exactly its declared coordinates.
        """
        layer_id = layer_elem.get("data-layer-id") or "image"
        try:
            standalone = self._build_standalone_svg(layer_elem, root)
        except Exception as e:
            logger.warning(f"[ImageLayer] build standalone SVG failed: {e}")
            return 0

        try:
            ET.register_namespace("", "http://www.w3.org/2000/svg")
            ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
            svg_str = ET.tostring(standalone, encoding="unicode")
        except Exception as e:
            logger.warning(f"[ImageLayer] serialize SVG failed: {e}")
            return 0

        tmp_path = ""
        try:
            fd, tmp_path = tempfile.mkstemp(prefix="useit_layer_", suffix=".svg")
            try:
                os.write(fd, svg_str.encode("utf-8"))
            finally:
                os.close(fd)
        except Exception as e:
            logger.warning(f"[ImageLayer] write temp svg failed: {e}")
            return 0

        try:
            shape = ctx.slide.Shapes.AddPicture(
                tmp_path, LinkToFile=False, SaveWithDocument=True,
                Left=0, Top=0,
                Width=ctx.slide_width, Height=ctx.slide_height,
            )
        except Exception as e:
            logger.warning(
                f"[ImageLayer] AddPicture failed for layer '{layer_id}': {e}"
            )
            self._cleanup_temp(tmp_path)
            return 0

        try:
            shape.Name = f"{layer_id}.image"
            ctx.handles[shape.Name] = shape.Name
        except Exception:
            pass
        self._add_shape_tag(shape, "useit_layer_id", layer_id)
        self._add_shape_tag(
            shape, "useit_layer_role",
            layer_elem.get("data-layer-role") or layer_elem.get("data-role"),
        )
        self._add_shape_tag(shape, "useit_render_as", "image")
        self._add_shape_tag(
            shape, "useit_layer_z",
            layer_elem.get("data-layer-z") or layer_elem.get("data-z"),
        )
        self._cleanup_temp(tmp_path)
        return 1

    @staticmethod
    def _build_standalone_svg(
        layer_elem: ET.Element,
        root: ET.Element,
    ) -> ET.Element:
        """Build a self-contained <svg> root that contains exactly one layer.

        The new root inherits the original viewBox/width/height so coordinates
        remain absolute relative to the slide; ``<defs>`` is deep-copied so
        gradients/filters referenced by the layer keep working.
        """
        SVG_NS = "http://www.w3.org/2000/svg"
        XLINK_NS = "http://www.w3.org/1999/xlink"
        new_root = ET.Element(f"{{{SVG_NS}}}svg")
        for attr in ("viewBox", "width", "height"):
            value = root.get(attr)
            if value is not None:
                new_root.set(attr, value)
        if root.get("preserveAspectRatio") is not None:
            new_root.set("preserveAspectRatio", root.get("preserveAspectRatio"))
        new_root.set("xmlns", SVG_NS)
        new_root.set("xmlns:xlink", XLINK_NS)

        for child in root:
            if strip_ns(child.tag) == "defs":
                new_root.append(copy.deepcopy(child))

        layer_clone = copy.deepcopy(layer_elem)
        # PPT's SVG importer doesn't understand our useit_* / data-* attributes
        # and would rather see clean SVG; strip them off the clone (originals
        # on the live tree are untouched).
        SlideRenderer._strip_extension_attrs(layer_clone)
        new_root.append(layer_clone)
        return new_root

    @staticmethod
    def _strip_extension_attrs(elem: ET.Element) -> None:
        """Recursively remove ``data-*`` attributes from an SVG subtree."""
        stack = [elem]
        while stack:
            node = stack.pop()
            for key in list(node.attrib.keys()):
                if key.startswith("data-"):
                    del node.attrib[key]
            stack.extend(list(node))

    @staticmethod
    def _cleanup_temp(path: str) -> None:
        if not path:
            return
        try:
            os.unlink(path)
        except Exception:
            pass

    @staticmethod
    def _shape_tag(shape, key: str) -> Optional[str]:
        try:
            value = shape.Tags.Item(key)
            if value:
                return str(value)
        except Exception:
            return None
        return None

    def _shape_layer_id(self, shape) -> Optional[str]:
        layer_id = self._shape_tag(shape, "useit_layer_id")
        if layer_id:
            return layer_id
        try:
            name = shape.Name or ""
        except Exception:
            return None
        if "." in name:
            prefix = name.split(".", 1)[0].strip()
            return prefix or None
        return None

    def _delete_shapes_by_layer(self, slide, target_layer_ids: set[str]) -> int:
        deleted = 0
        for i in range(slide.Shapes.Count, 0, -1):
            try:
                shape = slide.Shapes(i)
                if self._shape_layer_id(shape) in target_layer_ids:
                    shape.Delete()
                    deleted += 1
            except Exception as e:
                logger.warning(f"[LayerPatch] Failed to delete layer shape #{i}: {e}")
        return deleted

    @staticmethod
    def _add_shape_tag(shape, key: str, value: Optional[str]) -> None:
        if value is None:
            return
        try:
            shape.Tags.Delete(key)
        except Exception:
            pass
        try:
            shape.Tags.Add(key, str(value))
        except Exception:
            pass

    def _apply_layer_metadata(self, shape, elem: ET.Element, ctx: RenderContext) -> None:
        attrs = self._layer_attrs(elem)
        layer_id = attrs["layer_id"] or ctx.layer_id
        layer_role = attrs["layer_role"] or ctx.layer_role
        render_as = attrs["render_as"] or ctx.render_as
        layer_z = attrs["layer_z"] or ctx.layer_z
        if not layer_id:
            return
        self._add_shape_tag(shape, "useit_layer_id", layer_id)
        self._add_shape_tag(shape, "useit_layer_role", layer_role)
        self._add_shape_tag(shape, "useit_render_as", render_as)
        self._add_shape_tag(shape, "useit_layer_z", layer_z)

    def _set_handle(self, shape, elem: ET.Element, ctx: RenderContext) -> None:
        handle_id = elem.get("data-handle-id")
        layer_id = elem.get("data-layer-id") or ctx.layer_id
        if handle_id and layer_id and not handle_id.startswith(f"{layer_id}."):
            handle_id = f"{layer_id}.{handle_id}"
        if handle_id:
            try:
                shape.Name = handle_id
                ctx.handles[handle_id] = handle_id
            except Exception as e:
                logger.warning(f"[SlideRenderer] Failed to set handle '{handle_id}': {e}")
        self._apply_layer_metadata(shape, elem, ctx)

    def _record_placeholder(self, elem: ET.Element, ctx: RenderContext) -> None:
        tag = strip_ns(elem.tag)
        x = ctx.tx(to_float(elem.get("x", elem.get("cx", "0"))))
        y = ctx.ty(to_float(elem.get("y", elem.get("cy", "0"))))
        w = ctx.sx(to_float(elem.get("width", str(to_float(elem.get("rx", "50")) * 2))))
        h = ctx.sy(to_float(elem.get("height", str(to_float(elem.get("ry", "50")) * 2))))
        ctx.placeholders.append({
            "id": elem.get("data-placeholder"),
            "type": elem.get("data-type", tag),
            "bounds": {"x": round(x, 2), "y": round(y, 2), "w": round(w, 2), "h": round(h, 2)},
        })
