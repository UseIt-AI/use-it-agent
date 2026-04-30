"""PPT layout inspector.

Pure-Python static checker that runs over a PowerPoint snapshot dict (the
shape the Local Engine returns after ``ppt_*`` actions) and flags layout
problems that the orchestrator LLM routinely misses:

* Two text-bearing elements whose axis-aligned bounding boxes overlap — the
  NVIDIA / NASDAQ case from log ``260424-104015_agent_tid_3ed3c8d8`` where
  ``$188.00`` landed fine but the two title text boxes were stacked on top
  of each other, producing the visual ``"CorporationQ: NVDA"`` mash-up.
* Shapes that extend past the slide canvas (``x + w > slide_width`` etc.).
* Degenerate geometry (``w <= 0`` / ``h <= 0``).
* Short single-line text where the box is **too narrow** (likely wrap) or
  **unusually tall** (likely wrapped glyphs), which then collide with other
  shapes — the NVDA / divider / price case from log ``260424-181324``.

The report is formatted as Markdown and is safe to drop into an LLM's
``last_execution_output``; it is also kept short enough to be useful even
for very busy slides (we cap each section at 10 issues).

Used by:

- ``ppt_verify_layout`` inline tool (explicit planner call).
- ``AgentNodeHandler._compose_last_execution_output`` (auto-surface the
  issue count so the planner sees the warning even without calling the
  tool explicitly).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Issue:
    """One layout problem found in a snapshot."""

    kind: str  # "overlap" | "off_canvas" | "degenerate" | "text_fit"
    severity: str  # "error" | "warning"
    message: str


@dataclass
class InspectionReport:
    """Aggregated result of inspecting a single slide."""

    slide_index: Optional[int]
    slide_width: float
    slide_height: float
    element_count: int
    issues: List[Issue]

    @property
    def has_issues(self) -> bool:
        return bool(self.issues)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


_TEXT_BEARING_TYPES = {"textbox", "placeholder"}
_OVERLAP_MIN_RATIO = 0.15
"""Minimum fraction of the *smaller* element's area that must be covered
by the intersection before we report anything.  Below this threshold the
overlap is almost certainly intentional (icons sitting on a card
background, a small badge landing in the whitespace of a larger text
box, etc.)."""

_OVERLAP_ERROR_RATIO = 0.8
"""Above this fraction the overlap is almost always a real collision —
two text boxes landing on essentially the same rectangle (the NVIDIA /
NASDAQ mash-up case).  Between :data:`_OVERLAP_MIN_RATIO` and this value
the issue is reported as a *warning* instead of an error because the
overlap can still be an intentional layout (e.g. a "USD" unit badge
positioned in the right-hand whitespace of a larger "$188.00" text
box)."""


def inspect_snapshot(
    snapshot: Dict[str, Any],
    *,
    slide_index: Optional[int] = None,
) -> InspectionReport:
    """Run every check on the *current slide* of ``snapshot``.

    ``snapshot`` is the dict returned by Local Engine PPT actions — either
    the top-level ``execution_result`` (in which case we look for
    ``snapshot.content.current_slide`` etc.) or the already-extracted
    ``snapshot`` sub-dict.  The function is forgiving about nesting.
    """
    slide, sw, sh = _extract_slide(snapshot)
    if not slide:
        return InspectionReport(
            slide_index=slide_index,
            slide_width=sw,
            slide_height=sh,
            element_count=0,
            issues=[],
        )

    elements = _coerce_elements(slide.get("elements") or [])
    issues: List[Issue] = []
    issues.extend(_check_degenerate(elements))
    issues.extend(_check_off_canvas(elements, sw, sh))
    issues.extend(_check_overlaps(elements))
    issues.extend(_check_text_fit(elements))

    return InspectionReport(
        slide_index=slide_index if slide_index is not None else slide.get("index"),
        slide_width=sw,
        slide_height=sh,
        element_count=len(elements),
        issues=issues,
    )


def format_report_markdown(report: InspectionReport) -> str:
    """Render ``report`` as Markdown suitable for planner consumption."""
    if not report.has_issues:
        return (
            f"## Layout check: PASSED\n"
            f"- slide {report.slide_index or '?'} "
            f"({report.slide_width:.0f}×{report.slide_height:.0f} pt, "
            f"{report.element_count} element(s))\n"
            f"- no overlap / off-canvas / degenerate geometry detected"
        )
    lines: List[str] = []
    lines.append(
        f"## Layout check: {report.error_count} error(s), "
        f"{report.warning_count} warning(s)"
    )
    lines.append(
        f"- slide {report.slide_index or '?'} "
        f"({report.slide_width:.0f}×{report.slide_height:.0f} pt, "
        f"{report.element_count} element(s))"
    )
    lines.append("")

    by_kind: Dict[str, List[Issue]] = {}
    for issue in report.issues:
        by_kind.setdefault(issue.kind, []).append(issue)

    section_titles = [
        ("overlap", "### Overlapping elements"),
        ("text_fit", "### Text may wrap (width / height vs font)"),
        ("off_canvas", "### Elements extending past slide canvas"),
        ("degenerate", "### Degenerate geometry (zero / negative size)"),
    ]
    for kind, title in section_titles:
        items = by_kind.get(kind) or []
        if not items:
            continue
        lines.append(title)
        for issue in items[:10]:
            lines.append(f"- {issue.message}")
        if len(items) > 10:
            lines.append(f"- …and {len(items) - 10} more {kind} issue(s) omitted.")
        lines.append("")

    lines.append(
        "**Next step**: use `ppt_update_element` to nudge / resize the "
        "conflicting shapes (reference them by `handle_id` above), or "
        "`ppt_render_ppt_layout` with `render_mode=\"patch\"` if the whole "
        "section needs re-laying-out.  Do **not** `stop` while error-level "
        "issues remain."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def _check_degenerate(elements: List[Dict[str, Any]]) -> List[Issue]:
    out: List[Issue] = []
    for el in elements:
        w, h = _bounds(el)[2:]
        if w <= 0 or h <= 0:
            out.append(
                Issue(
                    kind="degenerate",
                    severity="error",
                    message=(
                        f"`{_label(el)}` has zero / negative size "
                        f"(w={w:g}, h={h:g}) — shape is invisible."
                    ),
                )
            )
    return out


def _check_text_fit(elements: List[Dict[str, Any]]) -> List[Issue]:
    """Heuristic: narrow box or tall box for short one-line text ⇒ likely wrap.

    PowerPoint auto-fits by growing *height* when width is tight — the
    snapshot often shows a single \"line\" in ``text`` but a tall bbox; the
    last character may still render on a new line, colliding with elements
    below (dividers, large numbers).
    """
    out: List[Issue] = []
    for el in elements:
        if not _is_text_bearing(el):
            continue
        raw = el.get("text")
        if not isinstance(raw, str) or not raw.strip():
            continue
        text = raw.strip()
        if not text:
            continue
        # Heuristics are for a single visual line; multi-line body copy is noisier.
        if "\n" in text:
            continue
        font = el.get("font")
        if not isinstance(font, dict):
            font = {}
        fs = _num(font.get("size"), 0.0) or 12.0
        bold = bool(font.get("bold"))
        _x, _y, w, h = _bounds(el)
        if w <= 0 or h <= 0 or fs <= 0:
            continue
        # Heuristic: Latin tickers / labels up to 24 chars
        if len(text) > 24:
            continue
        em = fs * 1.35
        width_factor = 0.70 if bold else 0.62
        min_w = len(text) * fs * width_factor
        if w + 0.5 < min_w and "\n" not in text:
            out.append(
                Issue(
                    kind="text_fit",
                    severity="warning",
                    message=(
                        f"`{_label(el)}` (`{_text_preview(el)}`) box width w={w:.1f} pt "
                        f"looks too narrow for {len(text)} char(s) at {fs:.1f}pt "
                        f"{'(bold) ' if bold else ''}— rough min single-line width "
                        f"~{min_w:.0f} pt.  Text may wrap and grow the box downward."
                    ),
                )
            )
        if "\n" not in text and h > em * 1.75:
            out.append(
                Issue(
                    kind="text_fit",
                    severity="warning",
                    message=(
                        f"`{_label(el)}` (`{_text_preview(el)}`) has height h={h:.1f} pt, "
                        f"much larger than one line (~{em:.1f} pt) at {fs:.1f}pt — text "
                        f"is likely wrapping inside the box, which can push content "
                        f"into elements below (e.g. tickers over dividers / prices)."
                    ),
                )
            )
    return out


def _check_off_canvas(
    elements: List[Dict[str, Any]], sw: float, sh: float
) -> List[Issue]:
    out: List[Issue] = []
    if sw <= 0 or sh <= 0:
        return out
    for el in elements:
        x, y, w, h = _bounds(el)
        if w <= 0 or h <= 0:
            continue
        right, bottom = x + w, y + h
        exceed_right = right - sw
        exceed_bottom = bottom - sh
        exceed_left = -x
        exceed_top = -y
        worst = max(exceed_right, exceed_bottom, exceed_left, exceed_top)
        if worst <= 0.5:  # half-point tolerance for rounding
            continue
        # Choose severity: >10pt outside or >5% of canvas → error, else warn.
        limit = max(sw, sh) * 0.05
        sev = "error" if worst > max(10.0, limit) else "warning"
        out.append(
            Issue(
                kind="off_canvas",
                severity=sev,
                message=(
                    f"`{_label(el)}` bounds [x={x:g}, y={y:g}, w={w:g}, "
                    f"h={h:g}] extends {worst:.1f} pt past the "
                    f"{sw:.0f}×{sh:.0f} pt slide canvas."
                ),
            )
        )
    return out


def _check_overlaps(elements: List[Dict[str, Any]]) -> List[Issue]:
    """Pairwise bbox intersection for text-bearing elements.

    We only flag overlaps where **both** shapes carry non-empty text — two
    empty decorative rectangles stacking is almost always intentional
    (card + gradient accent etc.), but two text boxes sharing the same
    rectangle is exactly the NVIDIA / NASDAQ mash-up the planner couldn't
    see.
    """
    out: List[Issue] = []
    text_els = [el for el in elements if _is_text_bearing(el)]
    n = len(text_els)
    for i in range(n):
        a = text_els[i]
        ax, ay, aw, ah = _bounds(a)
        if aw <= 0 or ah <= 0:
            continue
        a_area = aw * ah
        for j in range(i + 1, n):
            b = text_els[j]
            bx, by, bw, bh = _bounds(b)
            if bw <= 0 or bh <= 0:
                continue
            ix1 = max(ax, bx)
            iy1 = max(ay, by)
            ix2 = min(ax + aw, bx + bw)
            iy2 = min(ay + ah, by + bh)
            iw, ih = ix2 - ix1, iy2 - iy1
            if iw <= 0.5 or ih <= 0.5:
                continue
            inter = iw * ih
            b_area = bw * bh
            smaller = min(a_area, b_area) or 1.0
            ratio = inter / smaller
            if ratio < _OVERLAP_MIN_RATIO:
                continue
            sev = "error" if ratio >= _OVERLAP_ERROR_RATIO else "warning"
            out.append(
                Issue(
                    kind="overlap",
                    severity=sev,
                    message=(
                        f"`{_label(a)}` ({_text_preview(a)}) overlaps "
                        f"`{_label(b)}` ({_text_preview(b)}) — "
                        f"intersection {iw:.1f}×{ih:.1f} pt, "
                        f"{ratio * 100:.0f}% of the smaller element's area."
                    ),
                )
            )
    return out


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _extract_slide(
    snapshot: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], float, float]:
    """Return (current_slide dict, slide_width, slide_height).

    Walks both the ``execution_result`` shape (``.snapshot.content.current_slide``
    etc.) and the flatter ``.content.current_slide`` shape returned when the
    caller has already drilled in one level.
    """
    if not isinstance(snapshot, dict):
        return None, 0.0, 0.0

    # Drill through the known wrappers.
    roots = [snapshot]
    if isinstance(snapshot.get("snapshot"), dict):
        roots.append(snapshot["snapshot"])
    if isinstance(snapshot.get("data"), dict):
        roots.append(snapshot["data"])
        if isinstance(snapshot["data"].get("snapshot"), dict):
            roots.append(snapshot["data"]["snapshot"])

    slide: Optional[Dict[str, Any]] = None
    sw: float = 0.0
    sh: float = 0.0

    for root in roots:
        content = root.get("content") if isinstance(root, dict) else None
        if isinstance(content, dict):
            cs = content.get("current_slide")
            if isinstance(cs, dict) and slide is None:
                slide = cs
                sw = _num(cs.get("width"), sw)
                sh = _num(cs.get("height"), sh)
        # Slide-level width/height may also live under presentation_info.
        pi = root.get("presentation_info") if isinstance(root, dict) else None
        if isinstance(pi, dict):
            if sw <= 0:
                sw = _num(pi.get("slide_width"), sw)
            if sh <= 0:
                sh = _num(pi.get("slide_height"), sh)

    # Legacy single-level snapshot where `current_slide` sits at the root.
    if slide is None and isinstance(snapshot.get("current_slide"), dict):
        slide = snapshot["current_slide"]
        sw = _num(slide.get("width"), sw) if sw <= 0 else sw
        sh = _num(slide.get("height"), sh) if sh <= 0 else sh

    return slide, sw, sh


def _coerce_elements(raw: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    return [el for el in raw if isinstance(el, dict)]


def _bounds(el: Dict[str, Any]) -> Tuple[float, float, float, float]:
    b = el.get("bounds") or {}
    if not isinstance(b, dict):
        return 0.0, 0.0, 0.0, 0.0
    return (
        _num(b.get("x"), 0.0),
        _num(b.get("y"), 0.0),
        _num(b.get("w"), 0.0),
        _num(b.get("h"), 0.0),
    )


def _num(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _label(el: Dict[str, Any]) -> str:
    hid = el.get("handle_id") or el.get("id") or el.get("name")
    if hid:
        return str(hid)
    tn = el.get("type_name") or el.get("type") or "shape"
    idx = el.get("index")
    return f"{tn}#{idx}" if idx is not None else str(tn)


def _is_text_bearing(el: Dict[str, Any]) -> bool:
    tn = str(el.get("type_name") or "").lower()
    has_text = bool((el.get("text") or "").strip()) if isinstance(
        el.get("text"), str
    ) else False
    return has_text and (tn in _TEXT_BEARING_TYPES or tn == "")


def _text_preview(el: Dict[str, Any], max_len: int = 40) -> str:
    txt = el.get("text") or ""
    if not isinstance(txt, str):
        return '""'
    txt = txt.strip().replace("\n", " ")
    if len(txt) > max_len:
        txt = txt[: max_len - 1] + "…"
    return f'"{txt}"'
