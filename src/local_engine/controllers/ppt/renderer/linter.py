"""LayoutLinter: generic, taxonomy-free layout validation.

The linter intentionally does not know about role names or slot grids. It
relies entirely on the LLM-declared blueprint (the `layers` list passed to
``render_ppt_layout``) as ground truth and emits issues whenever rendered
shapes contradict that declaration.

Rules (all rules are independent and cheap):

1. ``orphan``           — a shape claims a ``layer_id`` that does not appear
                          in the blueprint.
2. ``out-of-bounds``    — a shape extends past the slide rectangle.
3. ``over-budget``      — a shape exceeds the layer's declared
                          ``data-layer-bbox`` budget (with tolerance).
4. ``illegal-overlap``  — two layers overlap despite a declared
                          ``no_overlap_with`` constraint between them.
5. ``palette-drift``    — a shape's fill or stroke color is too far from
                          every entry in the declared ``palette``.
6. ``baseline-drift``   — sibling shapes in the same layer that look like a
                          horizontal row have visibly different bottoms.

Issue dicts:

```
{
  "type":          "orphan" | "out-of-bounds" | "over-budget" | "illegal-overlap" | "palette-drift" | "baseline-drift",
  "severity":      "major" | "minor",
  "layer_id":      "<layer the issue belongs to, may be None>",
  "handle_id":     "<offending shape's COM Name, may be None>",
  "other_layer_id":   "<for illegal-overlap, the second layer>",
  "other_handle_id":  "<for illegal-overlap, the second shape>",
  "message":       "<human-readable summary>",
  "fix_hint":      "<short suggested action>",
}
```
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)


class LayoutLinter:
    """Stateless layout validator. Use ``LayoutLinter.lint(...)``."""

    BBOX_TOLERANCE_PT = 8.0
    OUT_OF_BOUNDS_TOLERANCE_PT = 1.0
    OVERLAP_THRESHOLD = 0.05
    PALETTE_DISTANCE_LIMIT = 18.0  # RGB Euclidean distance threshold
    BASELINE_DRIFT_PT = 2.5        # row-mate bottoms allowed to differ by this
    BASELINE_HEIGHT_RATIO = 0.30   # row-mates must have heights within ±30%
    BASELINE_VERTICAL_OVERLAP = 0.55  # row-mates must vertically overlap ≥55%
    DECIMALS = 2

    @classmethod
    def lint(
        cls,
        shapes: List[Dict[str, Any]],
        slide_width: float,
        slide_height: float,
        blueprint: Optional[Any],
    ) -> List[Dict[str, Any]]:
        """Run all rules and return a flat list of issues.

        Args:
            shapes: list of dicts with ``layer_id``, ``handle_id``, ``bounds``,
                and optionally ``fill_color``/``line_color`` (hex). Extra
                fields are ignored.
            slide_width / slide_height: in points.
            blueprint: either ``{"layers": [...], "palette": [...]}`` (current
                schema) or a bare ``layers`` list (legacy, palette empty).
        """
        layers, palette = cls._unpack_blueprint(blueprint)
        issues: List[Dict[str, Any]] = []
        bp_by_id: Dict[str, Dict[str, Any]] = {}
        for spec in layers:
            lid = spec.get("id")
            if isinstance(lid, str) and lid:
                bp_by_id[lid] = spec

        layer_shapes: Dict[str, List[Dict[str, Any]]] = {}
        for s in shapes:
            lid = s.get("layer_id")
            if lid:
                layer_shapes.setdefault(str(lid), []).append(s)

        cls._rule_orphan(layer_shapes, bp_by_id, issues)
        cls._rule_out_of_bounds(shapes, slide_width, slide_height, issues)
        cls._rule_over_budget(layer_shapes, bp_by_id, issues)
        cls._rule_illegal_overlap(layer_shapes, bp_by_id, issues)
        cls._rule_palette_drift(shapes, palette, issues)
        cls._rule_baseline_drift(layer_shapes, issues)
        return issues

    @staticmethod
    def _unpack_blueprint(
        blueprint: Optional[Any],
    ) -> tuple:
        """Return (layers, palette) from either dict or legacy list form."""
        if not blueprint:
            return [], []
        if isinstance(blueprint, list):
            return blueprint, []
        if isinstance(blueprint, dict):
            return blueprint.get("layers") or [], blueprint.get("palette") or []
        return [], []

    # ------------------------------------------------------------------ rules

    @classmethod
    def _rule_orphan(
        cls,
        layer_shapes: Dict[str, List[Dict[str, Any]]],
        bp_by_id: Dict[str, Dict[str, Any]],
        issues: List[Dict[str, Any]],
    ) -> None:
        if not bp_by_id:
            return  # no blueprint declared → can't tell what's orphan
        for lid, group in layer_shapes.items():
            if lid in bp_by_id:
                continue
            for s in group:
                issues.append({
                    "type": "orphan",
                    "severity": "major",
                    "layer_id": lid,
                    "handle_id": s.get("handle_id"),
                    "message": (
                        f"Shape claims layer '{lid}' but it's not in the blueprint."
                    ),
                    "fix_hint": (
                        f"Either delete this shape, or add '{lid}' to the layers "
                        "declaration."
                    ),
                })

    @classmethod
    def _rule_out_of_bounds(
        cls,
        shapes: Iterable[Dict[str, Any]],
        slide_w: float,
        slide_h: float,
        issues: List[Dict[str, Any]],
    ) -> None:
        tol = cls.OUT_OF_BOUNDS_TOLERANCE_PT
        for s in shapes:
            b = s.get("bounds")
            if not b:
                continue
            x, y, w, h = b.get("x", 0), b.get("y", 0), b.get("w", 0), b.get("h", 0)
            offsets = [
                ("left", -x),
                ("right", (x + w) - slide_w),
                ("top", -y),
                ("bottom", (y + h) - slide_h),
            ]
            edge, magnitude = max(offsets, key=lambda kv: kv[1])
            if magnitude <= tol:
                continue
            issues.append({
                "type": "out-of-bounds",
                "severity": "major",
                "layer_id": s.get("layer_id"),
                "handle_id": s.get("handle_id"),
                "message": (
                    f"Shape extends past slide {edge} edge by "
                    f"{round(magnitude, cls.DECIMALS)}pt."
                ),
                "fix_hint": "Move or resize the shape to stay inside the slide.",
            })

    @classmethod
    def _rule_over_budget(
        cls,
        layer_shapes: Dict[str, List[Dict[str, Any]]],
        bp_by_id: Dict[str, Dict[str, Any]],
        issues: List[Dict[str, Any]],
    ) -> None:
        tol = cls.BBOX_TOLERANCE_PT
        for lid, group in layer_shapes.items():
            spec = bp_by_id.get(lid)
            if not spec:
                continue
            budget = spec.get("bbox") or spec.get("bbox_budget")
            if not (isinstance(budget, (list, tuple)) and len(budget) == 4):
                continue
            try:
                bx, by, bw, bh = (float(v) for v in budget)
            except (TypeError, ValueError):
                continue
            for s in group:
                b = s.get("bounds")
                if not b:
                    continue
                x, y, w, h = b.get("x", 0), b.get("y", 0), b.get("w", 0), b.get("h", 0)
                left_excess = bx - x
                top_excess = by - y
                right_excess = (x + w) - (bx + bw)
                bottom_excess = (y + h) - (bh + by)
                excess = max(left_excess, top_excess, right_excess, bottom_excess)
                if excess <= tol:
                    continue
                issues.append({
                    "type": "over-budget",
                    "severity": "major",
                    "layer_id": lid,
                    "handle_id": s.get("handle_id"),
                    "message": (
                        f"Shape in layer '{lid}' overflows declared bbox by "
                        f"{round(excess, cls.DECIMALS)}pt."
                    ),
                    "fix_hint": (
                        "Either shrink the shape or grow the layer's "
                        "data-layer-bbox to match."
                    ),
                })

    @classmethod
    def _rule_illegal_overlap(
        cls,
        layer_shapes: Dict[str, List[Dict[str, Any]]],
        bp_by_id: Dict[str, Dict[str, Any]],
        issues: List[Dict[str, Any]],
    ) -> None:
        seen_pairs: set = set()
        for lid, spec in bp_by_id.items():
            forbidden = spec.get("no_overlap_with") or spec.get("no_overlap") or []
            if isinstance(forbidden, str):
                forbidden = [forbidden]
            for other in forbidden:
                pair_key = tuple(sorted((lid, other)))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
                a_shapes = layer_shapes.get(lid, [])
                b_shapes = layer_shapes.get(other, [])
                for sa in a_shapes:
                    for sb in b_shapes:
                        ratio = cls._overlap_ratio(sa.get("bounds"), sb.get("bounds"))
                        if ratio <= cls.OVERLAP_THRESHOLD:
                            continue
                        issues.append({
                            "type": "illegal-overlap",
                            "severity": "major",
                            "layer_id": lid,
                            "handle_id": sa.get("handle_id"),
                            "other_layer_id": other,
                            "other_handle_id": sb.get("handle_id"),
                            "message": (
                                f"Layer '{lid}' overlaps '{other}' by "
                                f"{round(ratio * 100, 1)}% (declared no_overlap)."
                            ),
                            "fix_hint": (
                                "Reposition or resize one layer to remove overlap."
                            ),
                        })

    @classmethod
    def _rule_palette_drift(
        cls,
        shapes: Iterable[Dict[str, Any]],
        palette: List[str],
        issues: List[Dict[str, Any]],
    ) -> None:
        """Flag shapes whose fill or line color is far from every palette entry.

        Pure black, pure white, and ``"none"`` are always treated as compatible
        (they're the universal neutrals and almost never cause palette drift
        complaints from designers). All other colors must be within
        ``PALETTE_DISTANCE_LIMIT`` of at least one declared palette entry.
        """
        if not palette:
            return
        palette_rgb: List[tuple] = []
        for hex_str in palette:
            rgb = cls._hex_to_rgb(hex_str)
            if rgb is not None:
                palette_rgb.append(rgb)
        if not palette_rgb:
            return

        for s in shapes:
            for slot in ("fill_color", "line_color"):
                color = s.get(slot)
                rgb = cls._hex_to_rgb(color)
                if rgb is None:
                    continue
                if cls._is_neutral(rgb):
                    continue
                nearest, dist = cls._nearest_palette(rgb, palette_rgb)
                if dist <= cls.PALETTE_DISTANCE_LIMIT:
                    continue
                issues.append({
                    "type": "palette-drift",
                    "severity": "minor",
                    "layer_id": s.get("layer_id"),
                    "handle_id": s.get("handle_id"),
                    "message": (
                        f"{slot} {color} drifts {round(dist, 1)} units from "
                        f"nearest palette color {cls._rgb_to_hex(nearest)}."
                    ),
                    "fix_hint": (
                        f"Snap {slot} to {cls._rgb_to_hex(nearest)} or extend "
                        f"the declared palette to include {color}."
                    ),
                })

    @classmethod
    def _rule_baseline_drift(
        cls,
        layer_shapes: Dict[str, List[Dict[str, Any]]],
        issues: List[Dict[str, Any]],
    ) -> None:
        """Flag sibling shapes in the same layer whose bottoms don't align.

        Two shapes are considered row-mates when:
          * they belong to the same declared layer,
          * their heights are within ``BASELINE_HEIGHT_RATIO`` of each other,
          * they vertically overlap by at least ``BASELINE_VERTICAL_OVERLAP``,
          * they do not horizontally overlap (i.e. they sit side-by-side).

        Any row-mate pair whose bottom edges differ by more than
        ``BASELINE_DRIFT_PT`` is reported once.
        """
        tol = cls.BASELINE_DRIFT_PT
        seen_pairs: set = set()
        for lid, group in layer_shapes.items():
            usable = []
            for s in group:
                b = s.get("bounds")
                if not b:
                    continue
                h = float(b.get("h", 0))
                if h <= 0:
                    continue
                usable.append((s, b, h))
            usable.sort(key=lambda item: item[1].get("x", 0))
            for i, (sa, ba, ha) in enumerate(usable):
                for sb, bb, hb in usable[i + 1:]:
                    ratio = abs(ha - hb) / max(ha, hb)
                    if ratio > cls.BASELINE_HEIGHT_RATIO:
                        continue
                    ay1, ay2 = ba.get("y", 0), ba.get("y", 0) + ha
                    by1, by2 = bb.get("y", 0), bb.get("y", 0) + hb
                    v_overlap = max(0.0, min(ay2, by2) - max(ay1, by1))
                    v_ref = min(ha, hb)
                    if v_ref <= 0 or v_overlap / v_ref < cls.BASELINE_VERTICAL_OVERLAP:
                        continue
                    ax1, ax2 = ba.get("x", 0), ba.get("x", 0) + ba.get("w", 0)
                    bx1, bx2 = bb.get("x", 0), bb.get("x", 0) + bb.get("w", 0)
                    if min(ax2, bx2) - max(ax1, bx1) > 0:
                        continue  # they horizontally overlap → not a row pair
                    drift = abs(ay2 - by2)
                    if drift <= tol:
                        continue
                    pair_key = tuple(sorted((
                        str(sa.get("handle_id") or id(sa)),
                        str(sb.get("handle_id") or id(sb)),
                    )))
                    if pair_key in seen_pairs:
                        continue
                    seen_pairs.add(pair_key)
                    issues.append({
                        "type": "baseline-drift",
                        "severity": "minor",
                        "layer_id": lid,
                        "handle_id": sa.get("handle_id"),
                        "other_layer_id": lid,
                        "other_handle_id": sb.get("handle_id"),
                        "message": (
                            f"Row-mates in layer '{lid}' have bottoms that "
                            f"differ by {round(drift, cls.DECIMALS)}pt."
                        ),
                        "fix_hint": (
                            "Snap both shapes to a shared bottom (or shared "
                            "vertical center) so the row reads as one line."
                        ),
                    })

    # -------------------------------------------------------------- utilities

    @staticmethod
    def _hex_to_rgb(value: Optional[str]) -> Optional[tuple]:
        if not isinstance(value, str):
            return None
        v = value.strip().lstrip("#")
        if len(v) == 3:
            v = "".join(ch * 2 for ch in v)
        if len(v) != 6:
            return None
        try:
            return (int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16))
        except ValueError:
            return None

    @staticmethod
    def _rgb_to_hex(rgb: tuple) -> str:
        r, g, b = rgb
        return f"#{r:02X}{g:02X}{b:02X}"

    @staticmethod
    def _is_neutral(rgb: tuple) -> bool:
        """Pure black, pure white, near-grey are always palette-compatible."""
        r, g, b = rgb
        if max(abs(r - g), abs(g - b), abs(r - b)) <= 4:
            return True  # near-grey
        return False

    @classmethod
    def _nearest_palette(
        cls, rgb: tuple, palette_rgb: List[tuple]
    ) -> tuple:
        best = palette_rgb[0]
        best_dist = cls._color_distance(rgb, best)
        for cand in palette_rgb[1:]:
            d = cls._color_distance(rgb, cand)
            if d < best_dist:
                best = cand
                best_dist = d
        return best, best_dist

    @staticmethod
    def _color_distance(a: tuple, b: tuple) -> float:
        """Weighted Euclidean RGB distance, perceptual-ish without ΔE deps."""
        dr, dg, db = a[0] - b[0], a[1] - b[1], a[2] - b[2]
        return (2 * dr * dr + 4 * dg * dg + 3 * db * db) ** 0.5

    @staticmethod
    def _overlap_ratio(
        a: Optional[Dict[str, Any]],
        b: Optional[Dict[str, Any]],
    ) -> float:
        """Intersection area divided by smaller bbox area; 0 if no overlap."""
        if not (a and b):
            return 0.0
        ax1, ay1 = a.get("x", 0), a.get("y", 0)
        ax2, ay2 = ax1 + a.get("w", 0), ay1 + a.get("h", 0)
        bx1, by1 = b.get("x", 0), b.get("y", 0)
        bx2, by2 = bx1 + b.get("w", 0), by1 + b.get("h", 0)
        ix1, iy1 = max(ax1, bx1), max(ay1, by1)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)
        iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
        inter = iw * ih
        if inter <= 0:
            return 0.0
        a_area = max(0.0, (ax2 - ax1) * (ay2 - ay1))
        b_area = max(0.0, (bx2 - bx1) * (by2 - by1))
        ref = min(a_area, b_area) if min(a_area, b_area) > 0 else max(a_area, b_area)
        return inter / ref if ref > 0 else 0.0
