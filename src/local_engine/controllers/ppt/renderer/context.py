"""RenderContext: carries rendering state through recursive SVG->PPT calls."""

import math
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple

from .models import FilterDef, GradientDef
from .parsers import compose_matrix, parse_inline_style


class RenderContext:
    """Carries rendering state through recursive calls.

    Internally tracks a full 2D affine matrix [a, b, c, d, e, f] so that
    rotation and skew are preserved for polygon / path coordinate transforms.

    The legacy tx/ty/sx/sy helpers still work for the axis-aligned (no-rotation)
    fast path, but callers that need rotation correctness should use
    ``transform_point(x, y)``.
    """

    def __init__(
        self,
        slide,
        scale_x: float,
        scale_y: float,
        offset_x: float,
        offset_y: float,
        slide_width: float,
        slide_height: float,
        handles: Dict[str, str],
        placeholders: List[Dict],
        inherited_style: Dict,
        css_classes: Dict[str, Dict[str, str]],
        defs_map: Dict[str, ET.Element],
        gradient_defs: Optional[Dict[str, GradientDef]] = None,
        filter_defs: Optional[Dict[str, FilterDef]] = None,
        matrix: Optional[Tuple[float, float, float, float, float, float]] = None,
        layer_id: Optional[str] = None,
        layer_role: Optional[str] = None,
        render_as: Optional[str] = None,
        layer_z: Optional[str] = None,
    ):
        self.slide = slide
        self._scale_x = scale_x
        self._scale_y = scale_y
        self._offset_x = offset_x
        self._offset_y = offset_y
        self.slide_width = slide_width
        self.slide_height = slide_height
        self.handles = handles
        self.placeholders = placeholders
        self.inherited_style = inherited_style
        self.css_classes = css_classes
        self.defs_map = defs_map
        self.gradient_defs: Dict[str, GradientDef] = gradient_defs or {}
        self.filter_defs: Dict[str, FilterDef] = filter_defs or {}
        self.layer_id = layer_id
        self.layer_role = layer_role
        self.render_as = render_as
        self.layer_z = layer_z

        # Full affine: [a, b, c, d, e, f]  ->  x'=ax+cy+e, y'=bx+dy+f
        if matrix is not None:
            self._mat = matrix
        else:
            self._mat = (scale_x, 0.0, 0.0, scale_y, offset_x, offset_y)

    # ---------- coordinate helpers ----------

    def tx(self, svg_x: float) -> float:
        return svg_x * self._scale_x + self._offset_x

    def ty(self, svg_y: float) -> float:
        return svg_y * self._scale_y + self._offset_y

    def sx(self, svg_w: float) -> float:
        return svg_w * self._scale_x

    def sy(self, svg_h: float) -> float:
        return svg_h * self._scale_y

    def transform_point(self, x: float, y: float) -> Tuple[float, float]:
        """Apply full affine (incl. rotation) to a point."""
        a, b, c, d, e, f = self._mat
        return (a * x + c * y + e, b * x + d * y + f)

    # ---------- style resolution ----------

    def resolve_style(self, elem: ET.Element) -> Dict[str, str]:
        """Resolve: inherited -> CSS classes -> inline style (highest priority)."""
        result = dict(self.inherited_style)

        class_str = elem.get("class", "")
        if class_str:
            for cls_name in class_str.split():
                cls_props = self.css_classes.get(cls_name, {})
                result.update(cls_props)

        inline = parse_inline_style(elem)
        result.update(inline)
        return result

    # ---------- child context ----------

    def with_transform(
        self, dx: float, dy: float, sx: float, sy: float, style: Dict
    ) -> "RenderContext":
        """Child context with additional translation + scale (legacy API)."""
        return RenderContext(
            slide=self.slide,
            scale_x=self._scale_x * sx,
            scale_y=self._scale_y * sy,
            offset_x=self._offset_x + dx * self._scale_x,
            offset_y=self._offset_y + dy * self._scale_y,
            slide_width=self.slide_width,
            slide_height=self.slide_height,
            handles=self.handles,
            placeholders=self.placeholders,
            inherited_style=style,
            css_classes=self.css_classes,
            defs_map=self.defs_map,
            gradient_defs=self.gradient_defs,
            filter_defs=self.filter_defs,
            matrix=compose_matrix(self._mat, (sx, 0.0, 0.0, sy, dx, dy)),
            layer_id=self.layer_id,
            layer_role=self.layer_role,
            render_as=self.render_as,
            layer_z=self.layer_z,
        )

    def with_affine(
        self,
        child_matrix: Tuple[float, float, float, float, float, float],
        style: Dict,
    ) -> "RenderContext":
        """Child context composed with an arbitrary affine (supports rotation)."""
        composed = compose_matrix(self._mat, child_matrix)
        a, b, c, d, e, f = composed
        return RenderContext(
            slide=self.slide,
            scale_x=math.sqrt(a * a + b * b),
            scale_y=math.sqrt(c * c + d * d),
            offset_x=e,
            offset_y=f,
            slide_width=self.slide_width,
            slide_height=self.slide_height,
            handles=self.handles,
            placeholders=self.placeholders,
            inherited_style=style,
            css_classes=self.css_classes,
            defs_map=self.defs_map,
            gradient_defs=self.gradient_defs,
            filter_defs=self.filter_defs,
            matrix=composed,
            layer_id=self.layer_id,
            layer_role=self.layer_role,
            render_as=self.render_as,
            layer_z=self.layer_z,
        )

    def with_layer(
        self,
        layer_id: Optional[str],
        layer_role: Optional[str],
        render_as: Optional[str],
        layer_z: Optional[str],
        style: Dict,
    ) -> "RenderContext":
        """Child context carrying logical layer metadata."""
        return RenderContext(
            slide=self.slide,
            scale_x=self._scale_x,
            scale_y=self._scale_y,
            offset_x=self._offset_x,
            offset_y=self._offset_y,
            slide_width=self.slide_width,
            slide_height=self.slide_height,
            handles=self.handles,
            placeholders=self.placeholders,
            inherited_style=style,
            css_classes=self.css_classes,
            defs_map=self.defs_map,
            gradient_defs=self.gradient_defs,
            filter_defs=self.filter_defs,
            matrix=self._mat,
            layer_id=layer_id if layer_id is not None else self.layer_id,
            layer_role=layer_role if layer_role is not None else self.layer_role,
            render_as=render_as if render_as is not None else self.render_as,
            layer_z=layer_z if layer_z is not None else self.layer_z,
        )
