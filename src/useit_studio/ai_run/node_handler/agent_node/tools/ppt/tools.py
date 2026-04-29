"""PPT tools —— 每个类 = 一个 action。

有两种工具：
1. 普通直通工具（`EngineTool`）：Router 决策后直接把 Params 映射成 /step 请求。
2. **LLM 子规划工具**（`LLMEngineTool`）：Router 只负责"何时调用这个工具 +
   给一段 description + 路由参数（slide、render_mode 等）"；真正的 SVG / chart
   JSON / COM 代码由工具自己独立的 LLM 调用生成——这些工具携带聚焦的
   `system_prompt`，避免把生成任务塞进 Router 导致质量下降。

老 `functional_nodes/ppt_v2/tools/` 里的 LLMTool（PPTLayoutTool /
NativeChartTool / CodeExecutionTool）的 system_prompt / 生成流程在下方
`LLMEngineTool` 子类中一比一对齐。
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any, ClassVar, Dict, List, Optional

from ..helpers import extract_snapshot_dict
from ..protocol import EngineTool, InlineTool, LLMEngineTool, ToolCall
from .layout_inspector import format_report_markdown, inspect_snapshot

if TYPE_CHECKING:
    from useit_studio.ai_run.node_handler.base_v2 import NodeContext
    from ...models import (
        PlannerOutput,
    )


class _PPTEngineTool(EngineTool):
    """PPT 系列共享：group="ppt"，默认 /step 协议。"""

    group: ClassVar[str] = "ppt"
    target: ClassVar[str] = "ppt"


class _PPTLLMEngineTool(LLMEngineTool):
    """PPT 系列 LLM 子规划工具的共享基类。"""

    group: ClassVar[str] = "ppt"
    target: ClassVar[str] = "ppt"


# ==========================================================================
# Helpers — 从 ctx 抽 slide_width / slide_height / shapes_context
# ==========================================================================


def _slide_dimensions(ctx: "NodeContext") -> tuple[float, float]:
    snap = extract_snapshot_dict(ctx)
    sw = snap.get("slide_width") if isinstance(snap, dict) else None
    sh = snap.get("slide_height") if isinstance(snap, dict) else None
    try:
        sw_f = float(sw) if sw is not None else 960.0
    except (TypeError, ValueError):
        sw_f = 960.0
    try:
        sh_f = float(sh) if sh is not None else 540.0
    except (TypeError, ValueError):
        sh_f = 540.0
    return sw_f, sh_f


def _shapes_context(ctx: "NodeContext", max_chars: int = 20000) -> str:
    """返回给子 LLM 看的"当前幻灯片形状上下文"。

    兼容多种 snapshot 形态：若 snapshot 已经给了文本化的
    `shapes_context` / `current_slide_context` 字段直接用；否则把 shapes 列表
    序列化成每个 shape 一行的紧凑 JSON。
    """
    snap = extract_snapshot_dict(ctx)
    if not isinstance(snap, dict):
        return ""
    for key in ("shapes_context", "current_slide_context", "context"):
        v = snap.get(key)
        if isinstance(v, str) and v.strip():
            return v[:max_chars]
    shapes = snap.get("shapes")
    current_slide = snap.get("current_slide")
    if not isinstance(shapes, list) and isinstance(current_slide, dict):
        shapes = current_slide.get("elements") or current_slide.get("shapes")
    content = snap.get("content")
    if not isinstance(shapes, list) and isinstance(content, dict):
        current = content.get("current_slide")
        if isinstance(current, dict):
            shapes = current.get("elements") or current.get("shapes")
    if isinstance(shapes, list):
        lines: List[str] = []
        for s in shapes[:200]:
            if isinstance(s, dict):
                compact = {
                    k: s.get(k)
                    for k in (
                        "handle_id", "layer_id", "layer_role", "render_as",
                        "layer_z", "type", "type_name", "name", "x", "y",
                        "width", "height", "bounds", "text",
                    )
                    if k in s
                }
                lines.append(json.dumps(compact, ensure_ascii=False))
        text = "\n".join(lines)
        return text[:max_chars]
    return ""


def _project_files_context(ctx: "NodeContext", max_chars: int = 8000) -> str:
    snap = extract_snapshot_dict(ctx)
    if isinstance(snap, dict):
        v = snap.get("project_files")
        if isinstance(v, str) and v.strip():
            return v[:max_chars]
    extra = ctx.additional_context or ""
    return extra[:max_chars]


def _extract_first_json(text: str) -> Dict[str, Any]:
    """Best-effort JSON 提取——优先从 ```json 块中取，否则找第一对 `{...}`。"""
    m = re.search(r"```(?:json)?\s*(\{[\s\S]+?\})\s*```", text, re.IGNORECASE)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass
    raise ValueError(f"no JSON object in sub-LLM output: {text[:200]}...")


def _extract_first_svg(text: str) -> str:
    m = re.search(r"(<svg[\s\S]*?</svg>)", text, re.IGNORECASE)
    if not m:
        raise ValueError(f"no <svg> block in sub-LLM output: {text[:200]}...")
    return _sanitize_open_strokes(m.group(1).strip())


# Tags whose contents are typically stroke-only / open curves.  In SVG the
# default fill for any drawn element is **black** (not "none"), but the
# downstream PowerPoint renderer goes a step further and applies the
# theme's Accent 1 fill (commonly ``#4F81BD``) to any freeform whose fill
# is unspecified.  See trajectory 260426-041213: the layout LLM emitted
# four open arcs as ``<path d="..." stroke="black" stroke-width="3"/>``
# (no fill), the engine turned them into freeforms with
# ``fill_color="#4F81BD"``, and the user saw "AI 把好好的曲线给填充
# (成默认蓝/白色) 了，没有任何理由".  Defending against this in the
# agent layer is the cheapest fix — we don't ship the engine.
_OPEN_STROKE_TAGS = ("path", "polyline", "polygon", "line")
_OPEN_STROKE_TAG_RE = re.compile(
    r"<(?P<tag>" + "|".join(_OPEN_STROKE_TAGS) + r")\b(?P<attrs>[^>]*)/?>",
    re.IGNORECASE,
)


def _sanitize_open_strokes(svg: str) -> str:
    """Inject ``fill="none"`` into any stroked path/polyline/line that
    omits an explicit fill.

    Heuristic:
      * Element has a ``stroke`` (or ``stroke-*``) attribute, OR is a
        ``<line>`` (lines are always stroke-only by intent).
      * Element does NOT already declare ``fill=`` (attribute or inline
        ``style="fill: ..."``).

    In that case we add ``fill="none"`` so the engine treats it as an
    open stroke instead of falling back to its theme default fill.

    Closed shapes that intentionally have both fill and stroke (e.g.
    a colored badge with a black border) are left alone — they already
    declare their fill explicitly.
    """

    def repl(m: "re.Match[str]") -> str:
        tag = m.group("tag").lower()
        attrs = m.group("attrs") or ""

        # Already has fill specified anywhere?  Bail out, respect the LLM.
        if re.search(r"\bfill\s*=", attrs, re.IGNORECASE):
            return m.group(0)
        if re.search(
            r"\bstyle\s*=\s*(['\"])[^'\"]*\bfill\s*:", attrs, re.IGNORECASE
        ):
            return m.group(0)

        # Has stroke information, or is a primitive that is stroke-only by
        # design (``<line>``)?
        is_stroked = bool(
            re.search(r"\bstroke[\w-]*\s*=", attrs, re.IGNORECASE)
        ) or bool(
            re.search(
                r"\bstyle\s*=\s*(['\"])[^'\"]*\bstroke\s*:",
                attrs,
                re.IGNORECASE,
            )
        ) or tag == "line"
        if not is_stroked:
            return m.group(0)

        # Inject ``fill="none"`` right after the opening tag name, before
        # any other attributes — keeps the rest of the element verbatim.
        whole = m.group(0)
        # Replace ``<tag`` with ``<tag fill="none"`` (case-insensitive).
        return re.sub(
            r"<" + tag,
            f'<{tag} fill="none"',
            whole,
            count=1,
            flags=re.IGNORECASE,
        )

    return _OPEN_STROKE_TAG_RE.sub(repl, svg)


def _extract_palette(svg: str) -> List[str]:
    """Extract a slide palette from ``<svg data-palette="#aaa,#bbb,...">``.

    Returns a deduplicated list of upper-case ``#RRGGBB`` strings. Invalid
    entries are silently dropped; an empty list disables the palette-drift
    rule for the slide.
    """
    m = re.search(
        r"<svg\b[^>]*\bdata-palette\s*=\s*(['\"])(.*?)\1",
        svg,
        re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return []
    raw = m.group(2)
    out: List[str] = []
    seen: set[str] = set()
    for piece in re.split(r"[,\s]+", raw):
        token = piece.strip().strip(";")
        if not token:
            continue
        if not token.startswith("#"):
            token = "#" + token
        if not re.fullmatch(r"#[0-9a-fA-F]{3}|#[0-9a-fA-F]{6}", token):
            continue
        if len(token) == 4:
            token = "#" + "".join(ch * 2 for ch in token[1:])
        token = token.upper()
        if token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def _extract_layer_specs(svg: str) -> List[Dict[str, Any]]:
    """Extract logical layer metadata from `<g data-layer-id="...">` blocks.

    Each top-level layer ``<g>`` may carry the following self-describing
    attributes; all are optional and free-form:

    - ``data-layer-id``      (required) — stable handle for future patches
    - ``data-render-as``     ``native`` only. ``image`` is no longer
      supported — the agent must always emit native PowerPoint shapes so
      reference replication stays element-by-element.
    - ``data-layer-role``    free-form string used as a tag (e.g. "headline")
    - ``data-layer-z``       integer z-order
    - ``data-layer-bbox``    ``"x,y,w,h"`` — visual budget the linter checks
    - ``data-layer-no-overlap`` ``"id1,id2,..."`` — layers that must not overlap
    - ``data-layer-tags``    ``"tag1,tag2"``    — free-form grouping tags
    """
    specs: List[Dict[str, Any]] = []
    seen: set[str] = set()
    pattern = r"<g\b([^>]*)\bdata-layer-id\s*=\s*(['\"])(.*?)\2([^>]*)>"
    for match in re.finditer(pattern, svg, re.IGNORECASE):
        attrs = f"{match.group(1)} {match.group(4)}"
        layer_id = match.group(3).strip()
        if not layer_id or layer_id in seen:
            continue
        seen.add(layer_id)

        def attr(name: str) -> Optional[str]:
            m = re.search(rf"\b{name}\s*=\s*(['\"])(.*?)\1", attrs, re.IGNORECASE)
            return m.group(2).strip() if m else None

        spec: Dict[str, Any] = {"id": layer_id}
        role = attr("data-layer-role") or attr("data-role")
        # Image-rasterized layers are disabled: coerce any stray
        # ``data-render-as="image"`` to ``native`` so the engine produces
        # editable shapes instead of a flattened picture.
        render_as = attr("data-render-as")
        if render_as and render_as.strip().lower() == "image":
            render_as = "native"
        z_raw = attr("data-layer-z") or attr("data-z")
        bbox_raw = attr("data-layer-bbox") or attr("data-bbox")
        no_overlap_raw = attr("data-layer-no-overlap") or attr("data-no-overlap")
        tags_raw = attr("data-layer-tags") or attr("data-tags")

        if role:
            spec["role"] = role
        if render_as:
            spec["render_as"] = render_as
        if z_raw:
            try:
                spec["z"] = int(float(z_raw))
            except ValueError:
                spec["z"] = z_raw
        if bbox_raw:
            try:
                parts = [
                    float(p) for p in re.split(r"[,\s]+", bbox_raw.strip()) if p
                ]
                if len(parts) == 4:
                    spec["bbox"] = parts
            except ValueError:
                pass
        if no_overlap_raw:
            ids = [t.strip() for t in no_overlap_raw.split(",") if t.strip()]
            if ids:
                spec["no_overlap_with"] = ids
        if tags_raw:
            tag_list = [t.strip() for t in tags_raw.split(",") if t.strip()]
            if tag_list:
                spec["tags"] = tag_list
        # ``data-action="rebuild"`` (or alias ``data-layer-action="rebuild"``)
        # opts a layer into destructive patch_scope semantics — the engine
        # deletes every shape in the layer and re-creates it from this SVG.
        # WITHOUT this attribute, patch is a true merge (preserves shapes
        # not mentioned in the SVG).  This used to be unconditional, which
        # caused 60-shape layers to be wiped and rebuilt on every minor
        # tweak — see notes in ``_parse_llm_output`` below.
        action_raw = attr("data-layer-action") or attr("data-action")
        if action_raw and action_raw.strip().lower() == "rebuild":
            spec["rebuild"] = True
        specs.append(spec)
    return specs


def _extract_first_code(text: str, default_lang: str) -> tuple[str, str]:
    m = re.search(r"```(\w+)?\s*\n([\s\S]*?)```", text)
    if m:
        lang_raw = (m.group(1) or "").strip().lower()
        code = m.group(2).strip()
        if lang_raw in ("python", "py"):
            return code, "Python"
        if lang_raw in ("powershell", "ps1", "ps"):
            return code, "PowerShell"
        return code, default_lang
    idx = text.find("</thinking>")
    if idx != -1:
        rest = text[idx + len("</thinking>"):].strip()
        if rest:
            return rest, default_lang
    return text.strip(), default_lang


# ==========================================================================
# Detail blocks — 直接注入 Router Planner 的 system prompt
# ==========================================================================

_UPDATE_ELEMENT_DETAIL = r"""Modify existing shapes by `handle_id` (single) or `handle_ids` (list for batch).
Params: `slide`, `handle_id` / `handle_ids`, `properties { ... }`.
Only include properties you want to change — omitted properties are preserved.

**Batch mode** — apply the same `properties` to multiple shapes in one step:
```json
{
  "Action": "ppt_update_element",
  "Params": {
    "slide": 1,
    "handle_ids": ["Oval 25", "Oval 30", "Oval 36"],
    "properties": {
      "line_gradient": {"type": "linear", "angle": 45, "stops": [{"position": 0, "color": "#FF4D00"}, {"position": 1, "color": "#FFD700"}]}
    }
  }
}
```

**Supported properties:**

| Property | Type | Description |
|----------|------|-------------|
| `x` / `y` / `width` / `height` | float | Geometry in pt |
| `rotation` | float | Degrees |
| `visible` | bool | Visibility |
| `fill_color` | string | `#RRGGBB` / `"none"` (exclusive with `fill_gradient`) |
| `fill_gradient` | object | See gradient schema below |
| `line_color` | string | `#RRGGBB` / `"none"` (exclusive with `line_gradient`) |
| `line_gradient` | object | Same schema as `fill_gradient` |
| `line_weight` | float | Border thickness (pt) |
| `shadow` | object / null | Shadow effect (see schema) — `null` removes |
| `text` | string | Replace all text (exclusive with `rich_text`) |
| `rich_text` | array | Per-segment formatted text (see below) |
| `text_formats` | array | Format ranges of existing text (see below) |
| `font_name` / `font_size` / `font_bold` / `font_italic` / `font_color` | — | Whole-text font props (ignored with `rich_text`) |
| `text_align` | string | `left` / `center` / `right` / `justify` |
| `cell_format` | array | Per-cell styling for existing tables. `row`/`col` MUST be 1-based integers (NEVER `"*"` or strings). |

> **z-order** — don't use this tool; use `ppt_reorder_elements`.

**Gradient schema** (`fill_gradient` / `line_gradient`):
```json
{"type": "linear", "angle": 45, "stops": [{"position": 0, "color": "#FF4D00", "opacity": 1}, {"position": 1, "color": "#FFD700"}]}
```
`type`: `"linear"` or `"radial"`; `angle` degrees (linear only); `stops` ≥ 2 with `position` (0–1), `color`, optional `opacity` (0–1).

**Shadow schema** (`null` to remove):
```json
{"color": "#000000", "blur": 8, "offset_x": 4, "offset_y": 4, "opacity": 0.5}
```

**rich_text** — per-segment formatting (replaces entire text):
```json
[
  {"text": "Title: ", "font_bold": true, "font_size": 28, "font_color": "#FF4D00"},
  {"text": "gradient!", "fill_gradient": {"type": "linear", "angle": 0, "stops": [{"position": 0, "color": "#FF4D00"}, {"position": 1, "color": "#FFD700"}]}}
]
```
Each segment: `text` (required), optional `font_name`, `font_size`, `font_bold`, `font_italic`, `font_underline`, `font_color`, `fill_gradient`.

**text_formats** — format ranges without replacing all text:
```json
[
  {"match": "keyword", "font_bold": true, "font_color": "#FF0000"},
  {"match": "second", "nth": 2, "font_italic": true},
  {"start": 0, "length": 5, "font_size": 24},
  {"match": "old text", "text": "new text", "font_color": "#0066CC"}
]
```
Locate by `match` (substring, optional `nth` 1-based) or `start` + `length`. Optional `text` to replace. Combinable with `text`/`rich_text`."""


_ALIGN_ELEMENTS_DETAIL = r"""Align shapes spatially — the **engine** does the math, not you.

**Use this for**: "center A on B", "align titles left", "center on slide".
**Do NOT** use `ppt_update_element` with raw x/y for alignment.
**Do NOT** confuse with `text_align` (text alignment INSIDE a text box).

**Params:** `slide`, `targets` (list), plus ONE of:
- `reference` (single shape Name or `"slide"`) — all targets align to this one reference
- `references` (list, same length as targets) — 1:1 paired alignment (target[i] → reference[i])
- neither — targets align to each other

`horizontal`: `"left"` | `"center"` | `"right"` | null (don't change x)
`vertical`:   `"top"`  | `"middle"` | `"bottom"` | null (don't change y)

**Examples:**

Center numbers inside circles (1:1 paired):
```json
{"slide": "current",
 "targets": ["TextBox 27", "TextBox 32", "TextBox 38"],
 "references": ["Oval 25", "Oval 30", "Oval 36"],
 "horizontal": "center", "vertical": "middle"}
```

Left-align multiple titles to each other:
```json
{"slide": "current", "targets": ["Title 1", "Title 2", "Title 3"], "horizontal": "left"}
```

Center a title on the slide:
```json
{"slide": "current", "targets": ["Title 1"], "reference": "slide", "horizontal": "center"}
```"""


_REORDER_ELEMENTS_DETAIL = r"""Change z-order (front/back stacking) of shapes. Three modes:

**Mode 1 — Batch ordering** (array bottom→top):
```json
{"slide": "current", "order": ["bg_rect", "content_image", "title_text", "logo"]}
```
Shapes NOT in `order` keep their position; listed shapes move above all others.

**Mode 2 — Relative positioning** (above/below another shape):
```json
{"slide": "current", "handle_id": "title_text", "command": "above", "reference": "image_bg"}
```

**Mode 3 — Basic commands** (`bring_to_front` / `send_to_back` / `bring_forward` / `send_backward`):
```json
{"slide": "current", "handle_id": "logo", "command": "bring_to_front"}
```"""


_INSERT_NATIVE_TABLE_DETAIL = r"""Insert a PPT native table. Prefer this over drawing fake tables with rectangles.

**IMPORTANT:** `slide` MUST be an integer (e.g. `1`, `2`), NOT `"current"`.

**Params:** `slide` (int), `bounding_box` (`{x, y, w, h}`), `data` (2D array), `handle_id` (optional), plus styling:

| Param | Type | Description |
|-------|------|-------------|
| `first_row_header` | bool | Default `true`. First row gets header styling. |
| `cell_format` | array | Per-cell styling (see below). **Design colors to match the slide's palette.** |

**You are the designer.** Look at the slide's existing colors/style and design the table to match.

**Two-step pattern** — create structure first, then style:
1. `ppt_insert_native_table` with data + bounding_box
2. `ppt_update_element` with `cell_format` for visual polish
(Or do it in one call with inline `cell_format`.)

Example — 3-row, 3-col with styled header:
```json
{"slide": 2,
 "bounding_box": {"x": 80, "y": 100, "w": 800, "h": 320},
 "data": [["Product", "Q1", "Q2"], ["Alpha", "$120k", "$150k"], ["Beta", "$90k", "$110k"]],
 "handle_id": "sales_table",
 "cell_format": [
   {"row": 1, "col": 1, "fill_color": "#1A1A2E", "font_color": "#FFFFFF", "font_bold": true, "align": "center"},
   {"row": 1, "col": 2, "fill_color": "#1A1A2E", "font_color": "#FFFFFF", "font_bold": true, "align": "center"},
   {"row": 1, "col": 3, "fill_color": "#1A1A2E", "font_color": "#FFFFFF", "font_bold": true, "align": "center"}
 ]}
```

**cell_format rules:**
- `row` / `col` MUST be **1-based integers**. Row 1 = first row.
- **NEVER** use `"*"`, range syntax, or strings — only integers. These crash the engine.
- To style a whole row/column, enumerate each cell.

Supported per-cell props: `fill_color`, `fill_gradient`, `fill_transparency`, `font_color`, `font_bold`, `font_italic`, `font_size`, `font_name`, `align`, `line_color`, `line_transparency`, `line_weight`, `margin_left/right/top/bottom`."""


_ADD_SHAPE_ANIMATION_DETAIL = r"""Add animation to a shape.

**ALWAYS call `ppt_clear_slide_animations` first** when rebuilding animations from scratch.

**Params:** `slide`, `handle_id` (or `shape_index`), `effect`, optional `category`, `trigger`, `duration`, `delay`, `direction`, `text_unit`, `insert_at`.

**Effects** (engine maps to COM constants):
- Entrance: `appear`, `fade`, `fly`, `blinds`, `box`, `checkerboard`, `diamond`, `dissolve`, `peek`, `split`, `wipe`, `wheel`, `zoom`, `bounce`, `float`, `grow_and_turn`, `swivel`, `pinwheel`
- Emphasis: `pulse`, `spin`, `grow_shrink`, `teeter`, `wave`, `bold_flash`
- Exit: same names as entrance, set `category: "exit"`

`category`: `"entrance"` (default) | `"exit"` | `"emphasis"`
`trigger`:  `"on_click"` (default, new click step) | `"with_previous"` (sync) | `"after_previous"` (auto-chain)
`direction` (for `fly` / `wipe` / `peek`): `from_top`, `from_bottom`, `from_left`, `from_right`, …

**Sequential appear/disappear pattern** — emit the whole sequence by calling this tool repeatedly in subsequent planner steps (one animation per step is fine; the engine preserves ordering):
```
1. ppt_group_elements (handle_ids of step 1) → group "step_1"
2. ppt_group_elements (handle_ids of step 2) → group "step_2"
3. ppt_clear_slide_animations
4. ppt_add_shape_animation handle_id="step_1" effect="appear" trigger="on_click"
5. ppt_add_shape_animation handle_id="step_2" effect="appear" trigger="on_click"
6. ppt_add_shape_animation handle_id="step_1" effect="appear" category="exit" trigger="with_previous"
```
Click → step_1 appears → click → step_2 appears + step_1 disappears."""


# --------------------------------------------------------------------------
# 下面 3 个 detail 是 **Router 侧** 的 "when-to-use"——刻意保持简短。
# 真正的生成指南（SVG 排版 / chart 规划 / COM pitfall）在对应 LLMEngineTool
# 子类的 system_prompt 里。
# --------------------------------------------------------------------------

_EXECUTE_CODE_ROUTER_DETAIL = r"""Escape hatch when no structured tool fits (conditional logic, loops, bulk ops
across many shapes, or rare COM operations). **Prefer `ppt_update_element` for ALL
styling** — only reach for this tool when nothing else works.

Router only gives a natural-language `Description` plus optional routing Params
(`language`: `"PowerShell"` / `"Python"`, `timeout`: seconds). A dedicated code-generation
LLM will write the actual code with full COM pitfall awareness (TextFrame2, BGR colors,
etc.) — you do NOT need to write code in Params.

Example Router call:
```json
{"Action": "ppt_execute_code",
 "Description": "Delete every red rectangle (fill = #FF0000) from slide 3.",
 "Params": {"language": "PowerShell"}}
```"""


_RENDER_PPT_LAYOUT_ROUTER_DETAIL = r"""Create or restyle a slide's entire layout via SVG → native PowerPoint shapes.
This is the **big hammer** for slide creation; a dedicated layout LLM will
generate the full `<svg>` markup.

Router only gives a natural-language `Description` plus routing Params:

| Param | Type | Note |
|-------|------|------|
| `slide` | int / `"current"` | which slide to render into |
| `render_mode` | `"create"` / `"supplement"` / `"patch"` | See below |

**When to pick which render_mode:**

- **`create`** — **destructive: clears the slide and rebuilds it from scratch, assigning brand-new `handle_id`s.**  Use ONLY when (a) the slide is empty / brand new, or (b) the user explicitly asked to start over, or (c) more than ~50% of the existing shapes would need re-laying-out anyway.  Do **NOT** pick `create` to "fix a typo and shift things left" — that wipes 100+ correctly-placed shapes and invalidates every handle id you'd just been editing.
- **`supplement`** — ADD new elements to an existing slide ("add a footer", "add decoration"); preserves existing shapes.
- **`patch`** — MODIFY / MOVE / RESTYLE existing elements; **TRUE MERGE: shapes you don't mention are preserved by `data-handle-id`**.  Surgical, not destructive.  Best for nudging a handful of shapes inside an otherwise-correct slide.

> **`patch` is NOT a redraw.**  When the layout sub-LLM emits SVG for `patch` mode it only needs to include the shapes that are actually changing or being added.  The other 50 shapes in the same layer stay put — the engine merges by handle_id, not by layer.  If a whole layer is so broken that surgical merge cannot fix it, the sub-LLM can opt that single layer into "wipe and rebuild" by adding `data-action="rebuild"` on its `<g data-layer-id>`; you (the planner) can also force this from outside by passing `Params.patch_scope={"type":"layer","layer_ids":["..."]}`.  Do not reach for either escape hatch unless surgical patches fail.

**Tool ladder for non-empty slides** (try the cheapest one first):

1. `ppt_update_element` — single shape: typo, colour, fill, position/size of one element.
2. `ppt_arrange_elements` — collective alignment / distribution / "shift everything 10pt left".
3. `ppt_render_ppt_layout` with `render_mode='patch'` — restructure a layer or two.
4. `ppt_render_ppt_layout` with `render_mode='supplement'` — add new layers.
5. `ppt_render_ppt_layout` with `render_mode='create'` — last resort; only with explicit justification (see above).

Hitting "Shape not found" from `ppt_update_element` is **not** a reason to escalate to `create`.  Re-read the editable handle inventory in the user prompt — handles drift on every `create` and the one you tried may be stale.  Pick a handle that's actually in the inventory, or use `arrange_elements` / `patch` instead.

Example Router call:
```json
{"Action": "ppt_render_ppt_layout",
 "Description": "Title slide: 'Q3 Revenue Review', subtitle 'October 2024'. Corporate blue + accent orange.",
 "Params": {"slide": 1, "render_mode": "create"}}
```

## Layout Issues Loop

After every render the snapshot's `current_slide.layout_issues` lists violations of
the LLM-declared layer blueprint. When that list is non-empty, fix issues before
generating new content.

Each turn:
1. Fix `severity="major"` first (orphan, over-budget, out-of-bounds, illegal-overlap),
   then `"minor"`. Group issues by `layer_id` and address each group in one call.
2. Pick the lightest tool that resolves the issue:
   - `orphan` → `ppt_delete_element` (handle_id from the issue), unless the layer should exist (then re-declare it via render_ppt_layout patch).
   - `out-of-bounds` / `over-budget` on 1–5 shapes → `ppt_update_element` with new x/y/w/h.
   - `palette-drift` → `ppt_update_element` with `fill_color` / `line_color` snapped to the suggested palette hex.
   - `baseline-drift` → `ppt_update_element` to align the offending row-mate's bottom (or vertical center) with its siblings — usually adjust `y` and/or `h` of the larger one. Address one row at a time.
   - `over-budget` on a whole layer or `illegal-overlap` across most of a layer → `ppt_render_ppt_layout` with `render_mode="patch"` AND `Params.patch_scope={"type":"layer","layer_ids":[...]}` (or, equivalently, the sub-LLM marks `<g data-layer-id="..." data-action="rebuild">`). The engine deletes that layer's shapes and re-renders them from the new SVG. Reserve this for actually-tangled layers — for ≤5 shapes inside an otherwise-correct layer, prefer plain patch (no patch_scope) which preserves everything you don't mention.
3. Stop the loop when (a) `layout_issues` is empty, or (b) the count did not strictly decrease vs. the previous turn — do not retry indefinitely.

Do not regenerate the whole slide unless every layer is broken."""


_INSERT_NATIVE_CHART_ROUTER_DETAIL = r"""Insert a native PowerPoint chart (column / bar / line / pie / scatter / area).
A dedicated chart LLM will pick chart_type, structure the data array, and choose
a bounding box based on the Description.

Router only gives a natural-language `Description` describing what to chart
(preferably citing specific numbers or data sources) plus optional `slide`
param. You do NOT need to produce `chart_type` / `data` / `bounding_box` yourself.

Example Router call:
```json
{"Action": "ppt_insert_native_chart",
 "Description": "Bar chart of Q1-Q4 revenue for Product A (120/150/180/210k) and Product B (90/110/140/170k).",
 "Params": {"slide": 2}}
```"""


# --------------------------------------------------------------------------
# Sub-LLM system prompts (ported verbatim from functional_nodes/ppt_v2)
# --------------------------------------------------------------------------

_RENDER_PPT_LAYOUT_SYSTEM_PROMPT = r"""You are a senior presentation designer who outputs SVG for `render_ppt_layout`.

Create polished slide layouts with strong hierarchy, coherent color, confident spacing, and clear editable structure. Preserve creative visual quality; only constrain the parts that must become editable PowerPoint shapes.

## Output Contract

- Output raw SVG only. No JSON wrapper and no code fence.
- The root `<svg>` viewBox must exactly match the slide size provided in the request.
- Coordinates are PowerPoint points.
- Give important elements stable `data-handle-id` values for future edits.
- Declare the slide palette on the root `<svg data-palette="#0A0A0A,#E60028,#FFFFFF,#7E7E7E">`. The layout linter checks every fill / stroke against this list (pure white, pure black and near-greys are always exempt). Add brand neutrals you intend to use; keep total count ≤ 6.

## Layer Declaration Contract

Wrap each logical part of the slide in a top-level `<g data-layer-id="…">`. Layer ids are free-form — name them after their content (`hero-headline`, `card-1`, `top-bar`, `side-cover`, `brand-mark`). There is no fixed taxonomy: a slide can have 2 layers (top-bar + content) or 8 (card grid), whatever fits the design.

Optional layer attributes — engine + linter understand them, but only the ones useful for your design need to be present:

- `data-render-as="native"` — every layer must be rendered as native, editable PowerPoint shapes. **Do NOT** use `data-render-as="image"`; rasterized layers are disabled because they collapse a vector reproduction into a single flat picture and defeat element-by-element replication.
- `data-layer-bbox="x,y,w,h"` — visual budget in slide pt. The layout linter flags shapes that exceed this rectangle, which catches "decoration accidentally took over the slide" failures.
- `data-layer-no-overlap="other-id-1,other-id-2"` — declare layers that must not overlap this one.
- `data-layer-tags="title,primary"` — free-form grouping tags.
- `data-layer-z="50"` — explicit z-order; lower draws first.

Example:

```xml
<g data-layer-id="hero-headline" data-render-as="native"
   data-layer-bbox="80,180,560,260"
   data-layer-no-overlap="brand-mark,nav">
  <text data-handle-id="hero-headline.title" ...>JOIN US</text>
</g>
```

Use child element handles like `hero-headline.title` so the layer prefix is stable across edits.

Future patches target layers by `data-layer-id`. After every render the engine returns `layout_issues` validating against your declared bboxes / no_overlap rules — fix only the listed issues on the next turn, do not regenerate the whole slide.

## Native-Only Layers

Every layer must be rendered as **native, editable PowerPoint shapes**. Image-rasterized layers (`data-render-as="image"`) are disabled — when replicating a reference, you must reproduce it element-by-element with real shapes, not collapse it into a flat picture.

Favor PowerPoint-safe SVG:

- Good: `<rect>`, `<ellipse>`, `<circle>`, `<line>`, `<polygon>`, `<polyline>`, simple `<path>`, `<text>`, `<tspan>`, `<image href="/absolute/path">` (only for genuine external photos / picture assets, not for re-rendering vector artwork), `<foreignObject><table>`.
- For diagonal or irregular regions, draw the region directly with `<polygon>` or closed `<path>` instead of relying on clipping a rectangle.
- Use gradients and opacity sparingly for polish. Keep transforms simple so editability is preserved.
- For complex decorative artwork (masks, clipped textures, grain, elaborate filters), simplify the design into native shapes you can express with the elements above. Do **not** fall back to a rasterized layer.

### Open strokes vs filled shapes (CRITICAL — wrong default fills the curve)

`<path>`, `<polyline>` and `<line>` are interpreted by the PowerPoint renderer as **closed freeforms** unless you tell it otherwise. If you omit `fill=`, the engine applies the slide theme's default fill (often `#4F81BD` Accent-1 blue or, on some themes, white) to the *interior* of the path — turning what you intended as an open curve into a coloured shape that hides whatever sits behind it.

Rules:
- If the element is meant to be an **open stroke** — an arrow shaft, a wrapping arc, a connector line, a hand-drawn-looking curve — write `fill="none"` explicitly, in addition to `stroke=` and `stroke-width=`.
  ```xml
  <path d="M ... C ... " fill="none" stroke="#000" stroke-width="3"/>
  <polyline points="..." fill="none" stroke="#444" stroke-width="2"/>
  ```
- If the element is a **filled badge / icon / wedge** (closed region with a coloured interior), specify `fill="#xxxxxx"` explicitly. Never rely on the SVG default.
- A `<polygon>` is closed by definition; it's always safe to give it a `fill=`.
- `<line>` is always stroke-only — the sanitizer will inject `fill="none"` for you, but stating it is clearer.

Failing this rule is the single biggest source of "the curve I drew came out as a blue / white blob" reports.

## Tables

For real data tables, use one `<foreignObject>` containing a simple HTML `<table>` and a `data-handle-id`. It creates a native PowerPoint table.

- Put only table structure and cell text inside `foreignObject`.
- Do not draw data tables as grids of `<rect>` and `<text>`.
- Do not rely on HTML/CSS styling, `colspan`, or `rowspan` inside the table.

## Canvas Fit Protocol (MANDATORY — DO THIS BEFORE ANY COORDINATE)

When you replicate a reference image OR adapt a template/archetype with a fixed aspect ratio onto a slide whose `slide_width × slide_height` may differ, you MUST first compute a **fit-box** so the entire composition lives strictly inside the canvas — proportionally scaled, never cropped, never overflowing.

**Step 1 — Measure the source aspect ratio.**
- Reference image: estimate from its visible pixel dimensions. `ar_src = W_src / H_src`.
- Archetype / mockup: use its native frame (e.g. a 960×540 design → `ar_src ≈ 1.778`).

**Step 2 — Get the canvas aspect ratio.**
- `ar_dst = slide_width / slide_height`. Use the EXACT `slide_width × slide_height` from the request — never assume 960×540.

**Step 3 — Compute a centered fit-box (contain inside canvas, preserve aspect).**
- Reserve a safe margin `M`: 24 pt by default, 16 pt only when `min(slide_width, slide_height) < 400`.
- Available area: `Wa = slide_width − 2·M`, `Ha = slide_height − 2·M`.
- If `ar_src ≥ Wa / Ha` → fit by width:  `Wfit = Wa`,  `Hfit = Wa / ar_src`.
- Else                                 → fit by height: `Hfit = Ha`,  `Wfit = Ha · ar_src`.
- Center it: `Xfit = (slide_width − Wfit) / 2`,  `Yfit = (slide_height − Hfit) / 2`.
- Uniform scale used for everything inside: `s = Wfit / W_src` (≡ `Hfit / H_src`).

**Step 4 — Map every coordinate / size / font-size through that scale.**
- For any source point `(xs, ys)` and size `(ws, hs)`:
  - `x = Xfit + xs · s`,  `y = Yfit + ys · s`,  `w = ws · s`,  `h = hs · s`.
- font-size, stroke-width, corner radius, gap, padding — multiplied by `s` too.
- After mapping, EVERY shape's bbox MUST satisfy `x ≥ 0`, `y ≥ 0`, `x + w ≤ slide_width`, `y + h ≤ slide_height`. If any element fails, you computed the fit-box wrong — redo step 3. Do NOT clip or trim.

**Step 5 — Sanity floor.**
- If `s < 0.55`, the canvas is too small to faithfully reproduce the source — DO NOT just shrink (text becomes unreadable). Switch to a more compact archetype (horizontal row instead of vertical stack; 2×2 grid instead of a 4-step diagonal; single line of cards instead of multi-row) and re-run the protocol. Never let resulting font-size drop below 10 pt.

**Step 6 — Pick an archetype that fits the fit-box, NOT the raw canvas.**
- For `Hfit < 300 pt`, reject any vertical/diagonal stack of ≥ 4 stages — those need ~400 pt of height; on a short canvas they will overflow no matter what `s` you pick. Switch to a horizontal arrangement.

Why this is non-negotiable: PowerPoint canvases vary widely (960×540, 720×540, 648×360, 1280×720, custom sizes). Coordinates copied from a 960×540 mental model onto a 648×360 canvas WILL overflow; the only correct path is proportional scaling through a fit-box.

## Design Invariants

- One clear focal point per slide.
- Use a cohesive palette: one primary, one accent, and neutrals unless the task gives brand colors.
- Keep generous margins and visible separation between unrelated groups.
- Make text contrast unambiguous against its background.
- For one-line labels, badges, tickers, and short numbers, allocate enough text box width to avoid accidental PowerPoint wrapping.
- Use `"Microsoft YaHei"` for Chinese text when no template font is specified.

## Placeholders and Existing Slides

If the current slide context contains native placeholders and the task is filling template text, use `<text data-placeholder="title|subtitle|body">` with explicit geometry matching the placeholder.

If the current slide already has shapes, respect the render-mode instructions in the user prompt. Do not invent unrelated changes.

## Visual Inputs (use your eyes, not the JSON)

You receive up to two kinds of images alongside this prompt:

- **Current slide screenshot** — a render of the actual PowerPoint slide as it looks RIGHT NOW. Present whenever the previous engine call returned a screenshot (i.e. on every `patch` / `supplement` call, and on `create` calls that follow a prior render). This is ground truth for the current state.
- **Reference image(s)** — what the user wants the slide to look like. For replication tasks, this is the primary visual target.

**Use the images, not the JSON shapes context, to judge fidelity.** The "Current Slide Shapes" block in the user prompt is a list of bboxes and colors — it tells you element identities and approximate geometry, but it CANNOT tell you whether the rendered curve points the right way, whether the colour balance feels right, whether a circle visually overlaps another, or whether the spacing reads as intended.

For `patch` / `supplement` mode, the workflow is:
1. Look at the current screenshot. Name the concrete visual defects vs. the reference (one short sentence each, e.g. "step-1.arc curls left but the reference curls right", "step-3.circle is half off the bottom edge").
2. Use the JSON shapes context only to recover the `data-handle-id` and current geometry of the shapes you need to edit.
3. Output SVG that fixes only the named defects. Preserve everything else — `patch` semantics merge.

Do NOT hallucinate defects from JSON alone (e.g. "y=-6.67 means it's off-canvas, I'll move it" — first check the screenshot; if the shape looks fine on screen, the negative coordinate is cosmetic and may be intentional crop).

## Thinking

In `<thinking>`, briefly decide IN THIS ORDER:
1. **Canvas Fit (FIRST — see Canvas Fit Protocol).** Read the actual `slide_width × slide_height` from the request. Determine `ar_src` (from reference image or archetype). Compute and explicitly write down `(Xfit, Yfit, Wfit, Hfit, s)`. If `s < 0.55` or `Hfit < 300pt` with a ≥4-stage vertical archetype, switch archetype FIRST, then recompute.
2. **Visual diff (for patch / supplement only).** Look at the current slide screenshot and the reference. Enumerate concrete visual defects in 1-3 short bullets. If no screenshot is attached, say so explicitly and proceed only if the task is `create`.
3. Overall composition, focal point, palette, and the layer list (id + bbox budget for each) — sized inside the fit-box, with all numbers already passed through `s`.
4. Which layers are native vs image; declare any `no_overlap_with` constraints.
5. For patch/supplement tasks, which existing handles or layers are touched. Honor the visual defects from step 2 first; then any `layout_issues` reported in the prompt.
6. **Hard bounds check (REQUIRED before emitting):** walk every element you placed and verify `x ≥ 0`, `y ≥ 0`, `x + w ≤ slide_width`, `y + h ≤ slide_height`. If ANY element fails, your fit-box was wrong — redo step 1. Do NOT clip / trim / hope it'll work.
7. Final spacing and text-wrap sanity check.

Then output only the SVG.
"""


_INSERT_NATIVE_CHART_SYSTEM_PROMPT = r"""You are a PowerPoint chart specialist. Given a description and slide state, generate the JSON payload for an `insert_native_chart` action.

## Chart Types

`column_clustered` | `column_stacked` | `bar_clustered` | `line` | `line_markers` | `pie` | `area` | `scatter`

## Data Format

A 2D array. First row = column headers, first column = row labels:

```json
[
    ["Category", "Q1", "Q2", "Q3"],
    ["Product A", 120, 150, 180],
    ["Product B", 90, 110, 140]
]
```

## Bounding Box

Position and size in PowerPoint points (pt):

```json
{"x": 100, "y": 100, "w": 500, "h": 300}
```

Ensure the chart fits within the slide dimensions and avoids overlapping existing shapes.

## Response Format

<thinking>
1. Determine the best chart type for the data.
2. Structure the data array.
3. Choose a reasonable bounding box.
</thinking>

```json
{
    "chart_type": "column_clustered",
    "bounding_box": {"x": 100, "y": 100, "w": 500, "h": 300},
    "data": [
        ["Category", "Series1", "Series2"],
        ["A", 10, 20],
        ["B", 30, 40]
    ],
    "title": "Chart Title",
    "handle_id": "my_chart"
}
```
"""


_EXECUTE_CODE_SYSTEM_PROMPT = r"""You are a PowerPoint code-execution specialist. Generate PowerShell (or Python) code that will be executed via subprocess to manipulate the active PowerPoint presentation.

## PowerShell COM Patterns

```powershell
# Connect to PowerPoint
try {
    $ppt = [System.Runtime.InteropServices.Marshal]::GetActiveObject("PowerPoint.Application")
} catch {
    $ppt = New-Object -ComObject PowerPoint.Application
}
$ppt.Visible = $true

# Access active presentation
$presentation = $ppt.ActivePresentation

# Slide access (1-indexed)
$slide = $presentation.Slides(1)
$currentSlide = $ppt.ActiveWindow.View.Slide

# Save
$presentation.Save()
```

## Python COM Patterns

```python
import win32com.client

ppt = win32com.client.GetActiveObject("PowerPoint.Application")
pres = ppt.ActivePresentation
slide = pres.Slides(1)

# Find shape by name
shape = None
for s in slide.Shapes:
    if s.Name == "target_name":
        shape = s
        break
```

## IMPORTANT — Prefer `update_element` over COM code for text formatting

Before writing COM code for text formatting, consider using `update_element` instead:
- **Per-segment formatted text**: `update_element` with `rich_text` property
- **Gradient text**: `rich_text` segments support `fill_gradient`
- **Keyword highlighting**: `update_element` with `text_formats` property
- **Gradient borders**: `update_element` with `line_gradient` property

Only write COM code if the task genuinely requires loops, conditionals, or operations
that `update_element` cannot handle.

## COM API Pitfalls (CRITICAL — read before writing code)

1. **Text gradient/fill — MUST use TextFrame2, NEVER TextFrame:**
   - `shape.TextFrame.TextRange.Font` → OLD `Font` class, NO `.Fill` property.
   - `shape.TextFrame2.TextRange.Font.Fill` → CORRECT (`Font2` with `FillFormat`).
   - Code using `TextFrame.TextRange.Font.Fill` will throw `<unknown>.Fill` silently.

2. **Per-character gradient — late-bound COM often fails:**
   Late-bound CDispatch often fails to resolve `.Font.Fill` on `Characters()` sub-ranges.
   Use early binding: `ppt = win32com.client.gencache.EnsureDispatch("PowerPoint.Application")`
   Or apply to WHOLE text range when possible:
   ```python
   tf2 = shape.TextFrame2
   tr = tf2.TextRange
   tr.Font.Fill.Visible = True
   tr.Font.Fill.TwoColorGradient(1, 1)  # msoGradientHorizontal
   tr.Font.Fill.ForeColor.RGB = 0x004DFF  # #FF4D00 in BGR
   tr.Font.Fill.GradientStops(2).Color.RGB = 0x00D7FF  # #FFD700 in BGR
   ```

3. **Gradient border (Line.Fill) — does NOT exist in COM:**
   `shape.Line.Fill` is not accessible. Use `update_element` with `line_gradient` instead.

4. **Color values in COM are BGR, not RGB:**
   `#FF4D00` → `R + G*256 + B*65536` = `255 + 77*256 + 0*65536` = `0x004DFF`

5. **Per-character solid color (no gradient):**
   ```python
   tr = shape.TextFrame2.TextRange
   part1 = tr.Characters(1, split_pos)       # 1-indexed
   part1.Font.Color.RGB = 0x004DFF           # orange in BGR
   part2 = tr.Characters(split_pos + 1, rest_len)
   part2.Font.Color.RGB = 0xFFFFFF           # white
   ```
   `.Font.Color.RGB` works on both TextFrame and TextFrame2 sub-ranges.

6. **Animations — NEVER write COM animation code:**
   Use the `add_shape_animation` / `clear_slide_animations` structured actions instead.
   They handle all COM constants, Exit flags, and trigger ordering correctly.

## Rules

- Use `$true`/`$false` instead of MsoTriState enums (avoids TypeNotFound errors).
- Use single quotes for string literals containing special characters.
- Always wrap in try-catch for error handling.
- Print a short summary at the end so the agent can read stdout.
- Output MUST be complete, runnable code — no placeholders or TODOs.
- When an operation fails, print the actual error message — do NOT silently swallow exceptions.

## Response Format

<thinking>
1. Understand what needs to be done.
2. Plan the COM operations.
3. Check COM pitfalls above for the APIs involved.
</thinking>

Then output the code in a fenced code block:

```powershell
# Your code here
```

Or for Python:

```python
# Your code here
```
"""


# ==========================================================================
# Presentation lifecycle (open / close)  — flat protocol, NOT /step
# ==========================================================================


_PPT_DOCUMENT_DETAIL = r"""Presentation lifecycle.  Discriminate on `action`:

| action  | required     | optional       | notes |
|---------|--------------|----------------|-------|
| `open`  | `file_path`  | `read_only`    | absolute path to a `.pptx` / `.ppt` file.  PowerPoint is auto-launched if not running, and an already-open presentation with the same path is just re-activated (no duplicate open). |
| `close` | —            | `save`         | closes the *currently active* presentation.  `save=true` saves first, default `false` discards changes. |

### When to use

- The user's goal references a **specific .pptx file path** (e.g. "帮我修改
  D:\Decks\demo.pptx 的第 2 页") → call `ppt_document action="open"
  file_path="D:\\Decks\\demo.pptx"` **as the very first PPT step**, before
  any `ppt_slide` / `ppt_render_ppt_layout` / `ppt_update_element` / etc.
- If the snapshot already shows `presentation_info.path` matches the user's
  target file, you can skip `open`.  Re-opening the same file is harmless
  but wastes a turn.
- Use `close` only when the user explicitly asks to close / finish; the
  default is to leave the deck open for further edits.

### Why this is separate from `/step`

`ppt_*` engine tools (slide / update_element / render_ppt_layout / ...)
all attach to a *running* PowerPoint via COM `GetActiveObject`.  When
PowerPoint isn't running yet, those calls fail with
`Operation unavailable`.  `ppt_document action="open"` goes through a
different endpoint (`POST /api/v1/ppt/open`) that launches PowerPoint
(`Dispatch`) and opens the file before any other tool runs.

### Examples
```json
{"Action": "ppt_document",
 "Params": {"action": "open", "file_path": "D:\\Workspace\\report.pptx"}}

{"Action": "ppt_document",
 "Params": {"action": "open", "file_path": "C:\\Users\\me\\slides.pptx", "read_only": true}}

{"Action": "ppt_document",
 "Params": {"action": "close", "save": true}}
```
"""


_PPT_DOCUMENT_ACTION_TO_ENGINE: Dict[str, str] = {
    "open": "open",
    "close": "close",
}


class PPTDocument(_PPTEngineTool):
    """Presentation lifecycle — open / close a specific .pptx file.

    Goes through the flat protocol (``{name: "open"|"close", args: {...}}``)
    instead of ``/step`` because the underlying Local Engine endpoints
    (``/api/v1/ppt/open`` / ``/close``) are reachable without an existing
    PowerPoint COM connection.  This is the **only** way to recover from
    the ``GetActiveObject -> Operation unavailable`` failure mode that
    every ``/step``-based tool produces when PowerPoint isn't running.
    """

    name = "ppt_document"
    router_hint = (
        "Presentation lifecycle: open / close.  Discriminate on `action`. "
        "Use `action=\"open\"` with `file_path` as the FIRST PPT step "
        "whenever the user's goal references a specific .pptx path — this "
        "auto-launches PowerPoint and opens the file before any other "
        "ppt_* tool runs."
    )
    router_detail = _PPT_DOCUMENT_DETAIL
    is_destructive = True  # close+save=false discards user edits.
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": list(_PPT_DOCUMENT_ACTION_TO_ENGINE.keys()),
                "description": "Lifecycle operation.",
            },
            "file_path": {
                "type": "string",
                "description": (
                    "action=open only.  Absolute Windows path to the "
                    ".pptx / .ppt file (e.g. `D:\\\\Workspace\\\\demo.pptx`)."
                ),
            },
            "read_only": {
                "type": "boolean",
                "description": "action=open only.  Open the file read-only.",
            },
            "save": {
                "type": "boolean",
                "description": "action=close only.  Save before closing (default false).",
            },
        },
        "required": ["action"],
    }

    def build_tool_call(
        self,
        params: Dict[str, Any],
        planner_output: "PlannerOutput",
    ) -> ToolCall:
        params = dict(params)
        action_key = params.pop("action", None)
        engine_action = _PPT_DOCUMENT_ACTION_TO_ENGINE.get(action_key)
        if engine_action is None:
            raise ValueError(
                f"ppt_document: invalid action {action_key!r}; "
                f"expected one of {list(_PPT_DOCUMENT_ACTION_TO_ENGINE)}"
            )
        if engine_action == "open" and not params.get("file_path"):
            raise ValueError(
                "ppt_document action='open' requires `file_path` (absolute path to a .pptx file)."
            )
        # Strip /step-only flags that don't belong on the flat open/close payload.
        params.pop("return_screenshot", None)
        params.pop("current_slide_only", None)
        args = {k: v for k, v in params.items() if v is not None}
        return ToolCall(name=engine_action, args=args)


# ==========================================================================
# Slide lifecycle  (consolidated: add / delete / duplicate / move / goto)
# ==========================================================================


_PPT_SLIDE_ACTION_TO_ENGINE: Dict[str, str] = {
    "add": "add_slide",
    "delete": "delete_slide",
    "duplicate": "duplicate_slide",
    "move": "move_slide",
    "goto": "goto_slide",
}


_PPT_SLIDE_DETAIL = r"""Slide-level CRUD.  Discriminate on `action`:

| action      | required                | optional               | notes |
|-------------|-------------------------|------------------------|-------|
| `add`       | —                       | `layout`, `index`      | layout: "blank" / "title" / "title_content" / ... |
| `delete`    | `slide`                 | —                      | destructive |
| `duplicate` | `slide`                 | —                      | |
| `move`      | `slide`, `to_index`     | —                      | 1-based indices |
| `goto`      | `slide`                 | —                      | read-only; `slide` can be int or `"first"` / `"last"` / `"next"` / `"prev"` |

Examples:
```json
{"Action": "ppt_slide", "Params": {"action": "add", "layout": "title"}}
{"Action": "ppt_slide", "Params": {"action": "move", "slide": 3, "to_index": 1}}
{"Action": "ppt_slide", "Params": {"action": "goto", "slide": "next"}}
```
"""


class PPTSlide(_PPTEngineTool):
    """Slide-level CRUD via `action` discriminator.

    Consolidates ``ppt_add_slide`` / ``ppt_delete_slide`` / ``ppt_duplicate_slide``
    / ``ppt_move_slide`` / ``ppt_goto_slide`` into one tool.  Legacy names are
    rewritten by :func:`..._legacy_aliases.rewrite_legacy_tool_call` so saved
    history keeps working.
    """

    name = "ppt_slide"
    router_hint = (
        "Slide-level CRUD (add / delete / duplicate / move / goto). "
        "Discriminate on `action`; see router_detail for per-action params."
    )
    router_detail = _PPT_SLIDE_DETAIL
    # Marked destructive because ``action="delete"`` is possible; other
    # actions are safe.  The flag is informational only (no runtime gate).
    is_destructive = True
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": list(_PPT_SLIDE_ACTION_TO_ENGINE.keys()),
                "description": "Operation to perform.",
            },
            "slide": {
                "type": ["integer", "string"],
                "description": (
                    "1-based slide index.  For action=goto also accepts "
                    "\"first\" / \"last\" / \"next\" / \"prev\".  "
                    "Required for delete / duplicate / move / goto."
                ),
            },
            "layout": {
                "type": "string",
                "description": "action=add only.  Slide layout name.  Default \"blank\".",
            },
            "index": {
                "type": "integer",
                "description": "action=add only.  1-based index to insert at (omit = append).",
            },
            "to_index": {
                "type": "integer",
                "description": "action=move only.  Target 1-based index.",
            },
        },
        "required": ["action"],
    }

    def build_tool_call(
        self,
        params: Dict[str, Any],
        planner_output: "PlannerOutput",
    ) -> ToolCall:
        params = dict(params)
        action_key = params.pop("action", None)
        engine_action = _PPT_SLIDE_ACTION_TO_ENGINE.get(action_key)
        if engine_action is None:
            raise ValueError(
                f"ppt_slide: invalid action {action_key!r}; "
                f"expected one of {list(_PPT_SLIDE_ACTION_TO_ENGINE)}"
            )
        return_screenshot = params.pop("return_screenshot", True)
        current_slide_only = params.pop("current_slide_only", True)
        return ToolCall(
            name="step",
            args={
                "actions": [{"action": engine_action, **params}],
                "return_screenshot": return_screenshot,
                "current_slide_only": current_slide_only,
            },
        )


# ==========================================================================
# Element editing (styling / geometry / text / z-order / grouping)
# ==========================================================================


class PPTUpdateElement(_PPTEngineTool):
    """改形状属性；支持 `handle_id` 单个或 `handle_ids` 批量。"""

    name = "ppt_update_element"
    router_hint = (
        "Modify existing shapes (geometry, fill, line, shadow, text, font). "
        "Params: slide, handle_id or handle_ids (list), properties. "
        "**Prefer over ppt_execute_code for ALL styling.**"
    )
    router_detail = _UPDATE_ELEMENT_DETAIL
    input_schema = {
        "type": "object",
        "properties": {
            "slide": {"type": ["integer", "string"]},
            "handle_id": {"type": "string"},
            "handle_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "batch target list.  Either (a) one shared flat `properties` dict "
                    "applied to every id, or (b) per-id dicts: `properties` = "
                    '`{"handle_a": {"y": 10}, "handle_b": {"height": 2}}` — keys must '
                    "match the `handle_ids` entries."
                ),
            },
            "properties": {"type": "object"},
        },
        "required": ["slide", "properties"],
    }

    def build_tool_call(
        self,
        params: Dict[str, Any],
        planner_output: "PlannerOutput",
    ) -> ToolCall:
        """批量展开 `handle_ids` 为多个独立 action，一次 /step 打包下发。"""
        params = dict(params)
        return_screenshot = params.pop("return_screenshot", True)
        current_slide_only = params.pop("current_slide_only", True)

        handle_ids = params.pop("handle_ids", None)
        if handle_ids and isinstance(handle_ids, list):
            shared = {k: v for k, v in params.items()}
            props = shared.get("properties")
            if (
                isinstance(props, dict)
                and all(h in props and isinstance(props[h], dict) for h in handle_ids)
            ):
                base = {k: v for k, v in shared.items() if k != "properties"}
                actions = [
                    {
                        "action": self.action_name,
                        "handle_id": hid,
                        **base,
                        "properties": props[hid],  # type: ignore[index]
                    }
                    for hid in handle_ids
                ]
            else:
                actions = [
                    {"action": self.action_name, "handle_id": hid, **shared}
                    for hid in handle_ids
                ]
        else:
            actions = [{"action": self.action_name, **params}]

        return ToolCall(
            name="step",
            args={
                "actions": actions,
                "return_screenshot": return_screenshot,
                "current_slide_only": current_slide_only,
            },
        )


# --------------------------------------------------------------------------
# Arrange — align / reorder / group / ungroup  (consolidated)
# --------------------------------------------------------------------------


_PPT_ARRANGE_ACTION_TO_ENGINE: Dict[str, str] = {
    "align": "align_elements",
    "reorder": "reorder_elements",
    "group": "group_elements",
    "ungroup": "ungroup_elements",
}


_PPT_ARRANGE_DETAIL = (
    r"""Structural / spatial operations on existing shapes.  Discriminate on `action`:

| action    | required                     | optional                                                    | notes |
|-----------|------------------------------|-------------------------------------------------------------|-------|
| `align`   | `slide`, `targets`           | `reference` / `references`, `horizontal`, `vertical`        | engine does the math — no manual x/y |
| `reorder` | `slide`                      | `order` / (`command` + `handle_id` + `reference`)           | 3 modes (batch / relative / basic command) |
| `group`   | `slide`, `handle_ids`        | `group_name`                                                | returns a single group shape |
| `ungroup` | `slide`, `handle_id`         | —                                                           | dissolves a group back into its children |

> For changing a shape's properties (geometry / fill / text / font), use
> `ppt_update_element` instead — this tool does not modify visual attrs.
> For deleting a shape, use `ppt_delete_element`.

"""
    "\n### action=align details\n\n" + _ALIGN_ELEMENTS_DETAIL
    + "\n\n### action=reorder details\n\n" + _REORDER_ELEMENTS_DETAIL
)


class PPTArrangeElements(_PPTEngineTool):
    """Structural operations on existing shapes (align / reorder / group / ungroup)."""

    name = "ppt_arrange_elements"
    router_hint = (
        "Structural / spatial ops on existing shapes: align (engine-math) / "
        "reorder z-order / group / ungroup.  Discriminate on `action`."
    )
    router_detail = _PPT_ARRANGE_DETAIL
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": list(_PPT_ARRANGE_ACTION_TO_ENGINE.keys()),
                "description": "Operation: align / reorder / group / ungroup.",
            },
            "slide": {"type": ["integer", "string"]},
            # --- align ---
            "targets": {
                "type": "array",
                "items": {"type": "string"},
                "description": "action=align only.  Shape handle_ids to align.",
            },
            "reference": {
                "type": "string",
                "description": (
                    "action=align: single reference shape (or `\"slide\"`) to align targets to. "
                    "action=reorder: reference shape for `above` / `below` relative mode."
                ),
            },
            "references": {
                "type": "array",
                "items": {"type": "string"},
                "description": "action=align only.  Multiple references (alternative to `reference`).",
            },
            "horizontal": {
                "type": ["string", "null"],
                "enum": ["left", "center", "right", None],
                "description": "action=align only.  Horizontal alignment mode.",
            },
            "vertical": {
                "type": ["string", "null"],
                "enum": ["top", "middle", "bottom", None],
                "description": "action=align only.  Vertical alignment mode.",
            },
            # --- reorder ---
            "order": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "action=reorder (batch mode).  Full handle_id list in "
                    "back-to-front order."
                ),
            },
            "handle_id": {
                "type": "string",
                "description": (
                    "action=reorder (relative / command modes): target handle_id.  "
                    "action=ungroup: the group's handle_id to dissolve."
                ),
            },
            "command": {
                "type": "string",
                "enum": [
                    "bring_to_front",
                    "send_to_back",
                    "bring_forward",
                    "send_backward",
                    "above",
                    "below",
                ],
                "description": (
                    "action=reorder: basic z-order command (`bring_to_front` / "
                    "`send_to_back` / `bring_forward` / `send_backward`) or "
                    "relative (`above` / `below` with `reference`)."
                ),
            },
            # --- group ---
            "handle_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "action=group only.  Shape handle_ids to merge into one group.",
            },
            "group_name": {
                "type": "string",
                "description": "action=group only.  Optional name for the new group.",
            },
        },
        "required": ["action", "slide"],
    }

    def build_tool_call(
        self,
        params: Dict[str, Any],
        planner_output: "PlannerOutput",
    ) -> ToolCall:
        params = dict(params)
        action_key = params.pop("action", None)
        engine_action = _PPT_ARRANGE_ACTION_TO_ENGINE.get(action_key)
        if engine_action is None:
            raise ValueError(
                f"ppt_arrange_elements: invalid action {action_key!r}; "
                f"expected one of {list(_PPT_ARRANGE_ACTION_TO_ENGINE)}"
            )
        return_screenshot = params.pop("return_screenshot", True)
        current_slide_only = params.pop("current_slide_only", True)
        return ToolCall(
            name="step",
            args={
                "actions": [{"action": engine_action, **params}],
                "return_screenshot": return_screenshot,
                "current_slide_only": current_slide_only,
            },
        )


class PPTDeleteElement(_PPTEngineTool):
    name = "ppt_delete_element"
    router_hint = "Delete a shape by handle_id. Params: slide, handle_id."
    is_destructive = True
    input_schema = {
        "type": "object",
        "properties": {
            "slide": {"type": ["integer", "string"]},
            "handle_id": {"type": "string"},
        },
        "required": ["slide", "handle_id"],
    }


# ==========================================================================
# Media / tables / charts (content insertion)
# ==========================================================================


# --------------------------------------------------------------------------
# Insert — media / native table  (consolidated; chart stays separate as it's
# an LLMEngineTool with a dedicated sub-LLM)
# --------------------------------------------------------------------------


_PPT_INSERT_ACTION_TO_ENGINE: Dict[str, str] = {
    "media": "insert_media",
    "table": "insert_native_table",
}


_PPT_INSERT_DETAIL = (
    r"""Insert non-chart content on a slide.  Discriminate on `action`:

| action  | required                                | optional                                           | notes |
|---------|-----------------------------------------|----------------------------------------------------|-------|
| `media` | `slide`, `media_path`                   | `bounding_box`, `handle_id`                        | inserts an image / video / etc. directly |
| `table` | `slide`, `bounding_box`, `data` (2D)    | `handle_id`, `first_row_header`, `cell_format`     | prefer over drawing a fake rect+text "table" |

> For charts (column / bar / line / pie / scatter / area), use the
> dedicated `ppt_insert_native_chart` tool — it runs a focused sub-LLM
> to plan `chart_type`, `data`, and `bounding_box`.

"""
    "\n### action=table details\n\n" + _INSERT_NATIVE_TABLE_DETAIL
)


class PPTInsert(_PPTEngineTool):
    """Insert content (media / native table) on a slide."""

    name = "ppt_insert"
    router_hint = (
        "Insert content on a slide (media file or native table).  "
        "Discriminate on `action`; for charts use `ppt_insert_native_chart`."
    )
    router_detail = _PPT_INSERT_DETAIL
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": list(_PPT_INSERT_ACTION_TO_ENGINE.keys()),
                "description": "What to insert: `media` or `table`.",
            },
            "slide": {
                "type": ["integer", "string"],
                "description": "Target slide (1-based index or \"current\").",
            },
            "bounding_box": {
                "type": "object",
                "description": (
                    "Placement rectangle in slide pt.  "
                    "`{x, y, width, height}`.  "
                    "action=table: required.  action=media: optional."
                ),
            },
            "handle_id": {
                "type": "string",
                "description": "Optional handle_id for the newly inserted shape.",
            },
            # --- media ---
            "media_path": {
                "type": "string",
                "description": "action=media only.  Absolute path to the media file.",
            },
            # --- table ---
            "data": {
                "type": "array",
                "description": "action=table only.  2-D array of cell values (list of rows).",
            },
            "first_row_header": {
                "type": "boolean",
                "description": "action=table only.  Style the first row as a header.",
            },
            "cell_format": {
                "type": "array",
                "description": (
                    "action=table only.  Per-cell styling list "
                    "(`row`/`col` 1-based ints; never `\"*\"` or strings)."
                ),
            },
        },
        "required": ["action", "slide"],
    }

    def build_tool_call(
        self,
        params: Dict[str, Any],
        planner_output: "PlannerOutput",
    ) -> ToolCall:
        params = dict(params)
        action_key = params.pop("action", None)
        engine_action = _PPT_INSERT_ACTION_TO_ENGINE.get(action_key)
        if engine_action is None:
            raise ValueError(
                f"ppt_insert: invalid action {action_key!r}; "
                f"expected one of {list(_PPT_INSERT_ACTION_TO_ENGINE)}"
            )
        return_screenshot = params.pop("return_screenshot", True)
        current_slide_only = params.pop("current_slide_only", True)
        return ToolCall(
            name="step",
            args={
                "actions": [{"action": engine_action, **params}],
                "return_screenshot": return_screenshot,
                "current_slide_only": current_slide_only,
            },
        )


class PPTInsertNativeChart(_PPTLLMEngineTool):
    """Router 只给 description；子 LLM 负责挑 chart_type / 组 data / 定 bounding_box。"""

    name = "ppt_insert_native_chart"
    router_hint = (
        "Insert a native PowerPoint chart (column / bar / line / pie / scatter / area). "
        "Router provides Description of what to chart + optional slide. A dedicated "
        "chart LLM produces chart_type / data / bounding_box."
    )
    router_detail = _INSERT_NATIVE_CHART_ROUTER_DETAIL
    system_prompt = _INSERT_NATIVE_CHART_SYSTEM_PROMPT
    max_tokens: ClassVar[int] = 8192
    input_schema = {
        "type": "object",
        "properties": {
            "slide": {"type": ["integer", "string"], "default": "current"},
        },
    }

    def _build_user_prompt(
        self,
        params: Dict[str, Any],
        planner_output: "PlannerOutput",
        ctx: "NodeContext",
    ) -> str:
        description = planner_output.description or planner_output.title or ""
        sw, sh = _slide_dimensions(ctx)
        shapes_ctx = _shapes_context(ctx)
        project_files = _project_files_context(ctx)
        lines = [
            f"## Task\n\n{description}",
            f"\n## Slide Canvas: {sw} × {sh} pt",
        ]
        if shapes_ctx:
            lines.append(f"\n## Current Slide Shapes\n\n{shapes_ctx}")
        if project_files:
            lines.append(f"\n## Available Data\n\n```\n{project_files}\n```")
        lines.append(
            "\nThink in `<thinking>`, then output the chart JSON in a fenced ```json block."
        )
        return "\n".join(lines)

    def _parse_llm_output(
        self,
        raw_text: str,
        params: Dict[str, Any],
        planner_output: "PlannerOutput",
        ctx: "NodeContext",
    ) -> ToolCall:
        chart_json = _extract_first_json(raw_text)
        slide = params.get("slide", "current")
        action: Dict[str, Any] = {"action": "insert_native_chart", "slide": slide}
        for key in ("chart_type", "bounding_box", "data", "title", "handle_id"):
            if key in chart_json:
                action[key] = chart_json[key]
        return ToolCall(
            name="step",
            args={
                "actions": [action],
                "return_screenshot": True,
                "current_slide_only": True,
            },
        )


# ==========================================================================
# Layout rendering (SVG → native shapes) — big hammer for slide creation
# ==========================================================================


class PPTRenderPPTLayout(_PPTLLMEngineTool):
    """Router 只给 description + slide + render_mode；子 LLM 负责写完整 SVG。"""

    name = "ppt_render_ppt_layout"
    router_hint = (
        "Render SVG layout to native PowerPoint shapes. Router provides a "
        "Description + slide + render_mode (create/supplement/patch); "
        "a dedicated layout LLM generates the SVG."
    )
    router_detail = _RENDER_PPT_LAYOUT_ROUTER_DETAIL
    system_prompt = _RENDER_PPT_LAYOUT_SYSTEM_PROMPT
    max_tokens: ClassVar[int] = 16384
    input_schema = {
        "type": "object",
        "properties": {
            "slide": {"type": ["integer", "string"], "default": "current"},
            "render_mode": {
                "type": "string",
                "enum": ["create", "supplement", "patch"],
                "default": "create",
            },
            "patch_scope": {
                "type": "object",
                "description": (
                    "OPTIONAL escape hatch for ``render_mode='patch'``. "
                    "When omitted, patch is a true merge: shapes not "
                    "mentioned in the SVG are preserved.  Pass "
                    "``{\"type\":\"layer\",\"layer_ids\":[...]}`` only "
                    "when an entire layer is so broken it must be "
                    "wiped and re-rendered.  For per-layer rebuilds it "
                    "is usually cleaner to add "
                    "``data-action='rebuild'`` to the relevant ``<g "
                    "data-layer-id>`` in the SVG instead."
                ),
                "properties": {
                    "type": {"type": "string", "enum": ["layer"]},
                    "layer_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
        },
    }

    def _build_user_prompt(
        self,
        params: Dict[str, Any],
        planner_output: "PlannerOutput",
        ctx: "NodeContext",
    ) -> str:
        description = planner_output.description or planner_output.title or ""
        render_mode = params.get("render_mode", "create")
        sw, sh = _slide_dimensions(ctx)
        shapes_ctx = _shapes_context(ctx)
        project_files = _project_files_context(ctx)

        lines = [
            f"## Task\n\n{description}",
            f"\n## Slide Canvas\n\nSize: **{sw} × {sh} pt** — use `viewBox=\"0 0 {sw} {sh}\"`.",
            f"\n## Render Mode: **{render_mode}**",
        ]

        if shapes_ctx:
            lines.append(f"\n## Current Slide Shapes\n\n{shapes_ctx}")

        if render_mode == "supplement":
            existing_ids = re.findall(r"handle_id['\"]?\s*[:=]\s*['\"]?([^,'\"}\s]+)", shapes_ctx or "")
            ids_str = ", ".join(existing_ids[:50]) if existing_ids else "(none)"
            lines.append(
                "\n## Mode: supplement — ADD new elements only\n\n"
                "**DO NOT** regenerate any existing elements.\n"
                f"Existing handle_ids to **AVOID**: {ids_str}\n\n"
                "Only output SVG for **NEW** elements that don't exist yet. "
                "Position them to avoid overlap with existing elements."
            )
        elif render_mode == "patch":
            lines.append(
                "\n## Mode: patch — EDIT existing elements (TRUE MERGE semantics)\n\n"
                "**Default behaviour: every shape NOT mentioned in your "
                "SVG is preserved unchanged on the slide.**  This is a "
                "surgical edit, not a redraw.  In particular, you do "
                "**not** need to re-emit the other 50+ shapes of a layer "
                "just to nudge 3 of them — leave them out and the "
                "engine will keep them as-is.\n"
                "- Use existing `data-handle-id` to target shapes for update.\n"
                "- Geometry (x, y, w, h): **always include** for shapes you ARE editing.\n"
                "- Visual/text attrs: **ONLY include if changing** (omitted attrs are preserved as-is).\n"
                "- To delete an element: `<g data-handle-id=\"...\" data-action=\"delete\"/>`\n"
                "- To add a new element: use a new `data-handle-id`.\n"
                "- All elements **NOT** in your SVG are **preserved** unchanged.\n"
                "\n"
                "### When you DO need to wipe-and-rebuild a layer\n"
                "Only when the layer's geometry is so tangled that "
                "patching individual shapes would not converge (e.g. "
                "the entire grid needs a complete re-flow), mark the "
                "layer's wrapper `<g>` with `data-action=\"rebuild\"`:\n"
                "```\n"
                "<g data-layer-id=\"china-grid-map\" data-action=\"rebuild\"> ... full SVG ... </g>\n"
                "```\n"
                "The engine will then delete every shape currently in "
                "that layer and re-create them from your SVG.  **Do "
                "NOT use `data-action=\"rebuild\"` casually** — it "
                "throws away handles, history and any user touch-ups; "
                "prefer surgical merge whenever possible."
            )

        if project_files:
            lines.append(f"\n## Project Files\n\n```\n{project_files}\n```")

        lines.append(
            "\n## Instructions\n\n"
            "Think in `<thinking>`, then output the raw SVG markup only (no JSON wrapper, no code fence)."
        )
        return "\n".join(lines)

    def _parse_llm_output(
        self,
        raw_text: str,
        params: Dict[str, Any],
        planner_output: "PlannerOutput",
        ctx: "NodeContext",
    ) -> ToolCall:
        svg = _extract_first_svg(raw_text)
        slide = params.get("slide", "current")
        render_mode = params.get("render_mode", "create")
        layer_specs = _extract_layer_specs(svg)
        palette = _extract_palette(svg)
        action_payload: Dict[str, Any] = {
            "action": "render_ppt_layout",
            "slide": slide,
            "svg": svg,
            "render_mode": render_mode,
            "clear_slide": render_mode == "create",
        }
        if layer_specs:
            action_payload["render_strategy"] = "layered"
            action_payload["layers"] = layer_specs
            # patch_scope rules:
            #   * Default for patch is **true merge** (engine preserves
            #     every shape NOT mentioned in the SVG, by handle_id).
            #     We do NOT auto-attach patch_scope=layer any more —
            #     historically that caused the engine to wipe an entire
            #     60-shape layer for what the LLM meant as a 3-shape edit.
            #   * If the planner explicitly passes
            #     ``Params.patch_scope`` it wins (escape hatch for the
            #     "the whole layer is broken, redo it" case).
            #   * Otherwise the layout sub-LLM can opt a single layer in
            #     by marking ``<g data-layer-id="X" data-action="rebuild">``.
            if render_mode == "patch":
                explicit_scope = params.get("patch_scope")
                rebuild_ids = [
                    spec["id"] for spec in layer_specs if spec.get("rebuild")
                ]
                if isinstance(explicit_scope, dict) and explicit_scope.get("layer_ids"):
                    action_payload["patch_scope"] = explicit_scope
                elif rebuild_ids:
                    action_payload["patch_scope"] = {
                        "type": "layer",
                        "layer_ids": rebuild_ids,
                    }
        if palette:
            action_payload["palette"] = palette
        return ToolCall(
            name="step",
            args={
                "actions": [action_payload],
                "return_screenshot": True,
                "current_slide_only": True,
            },
        )


# ==========================================================================
# Animation
# ==========================================================================


_PPT_ANIMATION_ACTION_TO_ENGINE: Dict[str, str] = {
    "add": "add_shape_animation",
    "clear": "clear_slide_animations",
}


_PPT_ANIMATION_DETAIL = (
    r"""Animations on a slide.  Discriminate on `action`:

| action  | required           | optional                                                                                      | notes |
|---------|--------------------|-----------------------------------------------------------------------------------------------|-------|
| `add`   | `slide`, `effect`  | `handle_id` / `shape_index`, `category`, `trigger`, `duration`, `delay`, `direction`, `text_unit`, `insert_at` | entrance / exit / emphasis |
| `clear` | `slide`            | `handle_id`                                                                                   | destructive; omit `handle_id` to clear the entire slide's timeline |

**Never use `ppt_execute_code` for animations — use this tool.**
Call `clear` first if you want to rebuild an animation sequence from scratch.

"""
    "\n### action=add details\n\n" + _ADD_SHAPE_ANIMATION_DETAIL
)


class PPTAnimation(_PPTEngineTool):
    """Animation add / clear on a slide."""

    name = "ppt_animation"
    router_hint = (
        "Slide animations: `add` a single effect (entrance/exit/emphasis) or "
        "`clear` all animations.  Discriminate on `action`."
    )
    router_detail = _PPT_ANIMATION_DETAIL
    is_destructive = True  # `action="clear"` wipes timelines.
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": list(_PPT_ANIMATION_ACTION_TO_ENGINE.keys()),
                "description": "`add` to add an animation; `clear` to remove animations.",
            },
            "slide": {"type": ["integer", "string"]},
            "handle_id": {
                "type": "string",
                "description": (
                    "action=add: target shape.  "
                    "action=clear: only this shape's animations (omit to clear whole slide)."
                ),
            },
            # --- add ---
            "shape_index": {
                "type": "integer",
                "description": "action=add only.  1-based index fallback when `handle_id` is unknown.",
            },
            "effect": {
                "type": "string",
                "description": "action=add only.  Effect name (e.g. `fade_in`, `fly_in`).",
            },
            "category": {
                "type": "string",
                "enum": ["entrance", "exit", "emphasis"],
                "default": "entrance",
                "description": "action=add only.",
            },
            "trigger": {
                "type": "string",
                "enum": ["on_click", "with_previous", "after_previous"],
                "default": "on_click",
                "description": "action=add only.",
            },
            "duration": {
                "type": "number",
                "description": "action=add only.  Seconds.",
            },
            "delay": {
                "type": "number",
                "description": "action=add only.  Seconds.",
            },
            "direction": {
                "type": "string",
                "description": "action=add only.  E.g. `from_left`, `from_bottom`.",
            },
            "text_unit": {
                "type": "string",
                "description": "action=add only.  `paragraph` / `word` / `letter`.",
            },
            "insert_at": {
                "type": "integer",
                "description": "action=add only.  1-based position in the timeline.",
            },
        },
        "required": ["action", "slide"],
    }

    def build_tool_call(
        self,
        params: Dict[str, Any],
        planner_output: "PlannerOutput",
    ) -> ToolCall:
        params = dict(params)
        action_key = params.pop("action", None)
        engine_action = _PPT_ANIMATION_ACTION_TO_ENGINE.get(action_key)
        if engine_action is None:
            raise ValueError(
                f"ppt_animation: invalid action {action_key!r}; "
                f"expected one of {list(_PPT_ANIMATION_ACTION_TO_ENGINE)}"
            )
        if action_key == "add" and not params.get("effect"):
            raise ValueError("ppt_animation: action='add' requires `effect`.")
        return_screenshot = params.pop("return_screenshot", True)
        current_slide_only = params.pop("current_slide_only", True)
        return ToolCall(
            name="step",
            args={
                "actions": [{"action": engine_action, **params}],
                "return_screenshot": return_screenshot,
                "current_slide_only": current_slide_only,
            },
        )


# ==========================================================================
# Escape hatch
# ==========================================================================


class PPTExecuteCode(_PPTLLMEngineTool):
    """Router 只给 description；子 LLM 负责写实际的 PowerShell / Python COM 代码。"""

    name = "ppt_execute_code"
    router_hint = (
        "Escape hatch: run PowerShell/Python COM code. Router provides Description "
        "of what should happen + optional language/timeout; a dedicated code LLM "
        "writes the actual code with COM pitfall awareness."
    )
    router_detail = _EXECUTE_CODE_ROUTER_DETAIL
    system_prompt = _EXECUTE_CODE_SYSTEM_PROMPT
    max_tokens: ClassVar[int] = 8192
    is_destructive = True
    input_schema = {
        "type": "object",
        "properties": {
            "language": {
                "type": "string",
                "enum": ["PowerShell", "Python"],
                "default": "PowerShell",
            },
            "timeout": {"type": "integer", "default": 120},
        },
    }

    def _build_user_prompt(
        self,
        params: Dict[str, Any],
        planner_output: "PlannerOutput",
        ctx: "NodeContext",
    ) -> str:
        description = planner_output.description or planner_output.title or ""
        language = params.get("language", "PowerShell")
        shapes_ctx = _shapes_context(ctx)
        project_files = _project_files_context(ctx)
        lines = [
            f"## Task\n\n{description}",
            f"\nPreferred language: **{language}**",
        ]
        if shapes_ctx:
            lines.append(f"\n## Current Slide State\n\n{shapes_ctx}")
        if project_files:
            lines.append(f"\n## Project Files\n\n```\n{project_files}\n```")
        lines.append(
            "\nThink in `<thinking>`, then output the complete, runnable code in a fenced code block."
        )
        return "\n".join(lines)

    def _parse_llm_output(
        self,
        raw_text: str,
        params: Dict[str, Any],
        planner_output: "PlannerOutput",
        ctx: "NodeContext",
    ) -> ToolCall:
        language_default = params.get("language", "PowerShell")
        code, language = _extract_first_code(raw_text, language_default)
        timeout = params.get("timeout", 120)
        return ToolCall(
            name="step",
            args={
                "code": code,
                "language": language,
                "return_screenshot": True,
                "current_slide_only": True,
                "timeout": timeout,
            },
        )


# ==========================================================================
# Verification (inline, server-side)
# ==========================================================================


_VERIFY_LAYOUT_SYSTEM_PROMPT = """\
You are a visual layout reviewer for PowerPoint slides.

You receive:
1. **The rendered slide** as a screenshot (the application window). This
   is GROUND TRUTH for what the user currently sees.
2. **Optional reference image(s)** — see the `## Task type` block in the
   user prompt for how to treat them.  Depending on `task_type` they may
   be the TARGET (replicate), the BEFORE state (modify), or absent.
3. The user prompt's `## Task type`, `## Focus` and `## Acceptance
   criteria` blocks — these are the planner's distillation of what the
   user actually asked for.  Treat them as the authoritative spec.
4. A short text block in the user prompt with: slide canvas dimensions,
   element count, the user's stated goal, and an *optional* engine-level
   bbox pre-flag (overlap / off-canvas / degenerate counts) — treat that
   pre-flag as a HINT, not the source of truth.

# Task-type semantics (THE MOST IMPORTANT RULE)

The `task_type` in the user prompt determines how you use the reference
image and what counts as a defect.

- **`replicate`** — the user wants the slide to look like the reference.
  Compare current screenshot vs reference: composition, proportion,
  colour family, element count, arrow / curve direction, reading order.
  Differences from the reference ARE defects.

- **`modify`** — the user wants the slide CHANGED.  The reference (if
  attached) is the BEFORE state; the user explicitly does NOT want the
  current screenshot to look like it.  **Differences from the reference
  are the user's intent, NOT defects.**  Do not flag "tile sizes
  changed", "shapes moved", "labels different from reference" etc.
  Judge the current screenshot against the `## Focus` and
  `## Acceptance criteria` blocks instead.  Only flag genuine visual
  breakage (text mashing, off-canvas, illegible, shapes blown out
  beyond their card, missing primary content, broken layout).

- **`create`** — fresh content; no reference comparison.  Judge the
  current screenshot on its own visual merit against `## Focus` and
  `## Acceptance criteria`.

When `task_type` is missing or unrecognised, default to **`modify`**
(the safer, more conservative interpretation: only flag breakage).

# What counts as acceptable

A slide is acceptable to ship when:

- It is clearly visible and not visually broken (no big chunks off the
  canvas, no obviously stacked / illegible text, no upside-down /
  mirrored elements that should be upright, no shapes that blew up
  beyond their card / panel).
- For `replicate` tasks: the rendered slide is a faithful enough
  replica of the reference (composition, primary element count,
  colour family, arrow direction, reading order).
- The `## Acceptance criteria` items are visibly satisfied.
- Text that's supposed to be readable IS readable (not clipped, not
  collapsed to height < ~10 pt, not running off the side of its box).
- Decorative shapes don't visually obstruct the focal content.

You are NOT a pixel-perfect grader — small spacing / colour / font
shade differences are fine.  We're catching real defects, not nitpicks.
**Aesthetic preferences that contradict the user's stated focus are
NEVER errors** (e.g. don't flag "tiles aren't uniform" when the user's
focus says "tile sizes vary by province area").

# Output format (STRICT)

Emit exactly one of:

```
## Layout check (visual): PASSED
- slide <W>×<H> pt, <N> element(s)
- <one short sentence summarising the visual state, e.g. "matches the reference; minor spacing differences only">
```

…or, if there are real issues:

```
## Layout check (visual): <E> error(s), <W> warning(s)
- slide <W>×<H> pt, <N> element(s)

### Visual issues
1. **error** `<handle_id_or_descriptor>` — <one-sentence concrete defect>. Suggested fix: `<tool>` <short hint>.
2. **warning** `<handle_id_or_descriptor>` — <one-sentence concrete defect>. Suggested fix: `<tool>` <short hint>.
…

### Reference comparison (only when a reference image is provided)
- <bullet 1: "the curved arc on step-1 is facing left; in the reference it faces right">
- <bullet 2: …>

**Next step**: <"Fix the listed errors with `ppt_update_element` / `ppt_render_ppt_layout` (render_mode='patch'). Do NOT `stop` while errors remain." — adapt as needed>
```

Severity rules:
- **error** — obvious shipping blocker: text mashed on top of other text;
  shape clearly off-canvas in the screenshot; arrow pointing wrong way;
  totally wrong colour family vs reference; text unreadable; major
  element missing entirely.
- **warning** — noticeable but not blocking: small overlap, slight
  off-canvas (a few pt), spacing inconsistent, palette drift, minor
  alignment differences.
- Cap your list at 8 items. If there are more, list the worst 8 and
  add a final note like "…and ~3 more minor warnings omitted".

When citing an element you MUST use a `handle_id` that appears in the
**Editable handle inventory** block of the user prompt, verbatim.  This
is the single source of truth for what's addressable on the slide right
now.  If you cannot find a matching handle for the defect you see
(e.g. an unnamed decorative rectangle), describe the element visually
instead ("the red circle in the top-left", "the arrow between step-1
and step-2") rather than guessing a handle name.

DO NOT copy handle_ids out of the geometry pre-pass list, the previous
turn's verifier output, or anywhere else — those have been observed to
lag the live render by one redraw and will break the planner's
follow-up `ppt_update_element` call.

NEVER fabricate handle_ids. NEVER claim defects you cannot see in the
screenshot. NEVER mark something an `error` purely because the engine
pre-flag flagged it — verify visually first; if the pre-flag says
"off-canvas y=-6.67" but the screenshot shows the shape comfortably on
the slide, it's NOT an error (the bbox might be a logical wrapper).

Output ONLY the markdown — no <thinking> block, no JSON, no preamble.
"""


_VERIFY_LAYOUT_DETAIL = """\
### `ppt_verify_layout` — visual layout review (vision LLM)

After any slide-modifying action (`ppt_render_ppt_layout`,
`ppt_update_element`, `ppt_arrange_elements`, `ppt_insert`,
`ppt_insert_native_chart`, `ppt_execute_code`), call this tool **before
`stop`**.  It runs a vision LLM over the rendered slide screenshot to
catch shipping-blocker defects you cannot judge from text or bbox JSON
alone:

- Wrong-direction arcs / arrows / orientations.
- Text mashing / unreadable text / clipped letters.
- Major elements off the visible canvas.
- Replication tasks: visible mismatch with the user's reference image
  (composition, palette, missing elements, swapped order).
- Decorative shapes covering focal content.

The vision LLM compares **the rendered slide screenshot** with the
**user's reference image** (when one was attached to this turn) and
returns a markdown report with concrete defects + suggested fix tools.
A fast geometry pre-pass (overlap / off-canvas / degenerate / text-fit)
runs first and is fed into the prompt as a hint.

**Parameters**:
- `task_type` (recommended): one of `"replicate"` / `"modify"` /
  `"create"`.  This is the single most important parameter — it tells
  the verifier how to use the reference image:
    * `replicate` — reference is the TARGET; compare strictly.
    * `modify` — reference is the BEFORE state; differences from it are
      the user's intent, NOT defects.  Verifier only flags real visual
      breakage and any unmet items in `acceptance_criteria`.
    * `create` — no reference comparison; judge on its own merits and
      against `acceptance_criteria`.
   Default is `"modify"` (the conservative choice).  **Always pass
   `replicate` explicitly when the user asked to copy / replicate /
   "make it look like this" / 复刻 — otherwise the verifier will
   under-flag fidelity issues.**
- `focus` (recommended for `modify` / `create`): a one-sentence
  description of what the verifier should check for, paraphrasing the
  user's actual ask.  E.g. `"tile sizes vary by province area; XJ/XZ/
  NM/HL noticeably bigger"`.  Without this, the verifier defaults to
  generic breakage checks only.
- `acceptance_criteria` (optional): a list of short, concrete must-haves
  the verifier should treat as pass/fail (`["title says 'Q3 Review'",
  "left column lists exactly 3 bullets"]`).  Items not visibly
  satisfied become errors.
- `slide` (optional, informational): target slide index.  The tool
  always reviews the snapshot's `current_slide`.
- `min_overlap_ratio` (optional): float 0-1, override the default 0.15
  overlap threshold for the geometry pre-pass.

**Output**:
- `## Layout check (visual): PASSED` when the screenshot looks ok, or
- `## Layout check (visual): N error(s), M warning(s)` followed by per-
  defect bullets ("`step-1.arc` curls left but reference curls right —
  fix: `ppt_update_element` to flip horizontally").  When the screenshot
  is missing this turn, the tool falls back to a geometry-only report
  with a clear `(no screenshot — geometry only)` header and asks the
  planner to re-snapshot first.

**Hard rule**: if the report contains any `**error**` line, you MUST
NOT emit `stop`.  Fix the listed defects (usually one
`ppt_update_element` reposition or one `ppt_render_ppt_layout` patch),
then re-call `ppt_verify_layout` to confirm before stopping.
"""


class PPTVerifyLayout(InlineTool):
    """Visual layout reviewer for the most recent PPT snapshot.

    Runs a vision LLM over:
      - the **rendered slide screenshot** returned by the previous PPT
        engine action (this is ground truth for what the user sees);
      - the **user reference image(s)** attached to this node (when the
        task is "make it look like this" / replication);
      - a short text block with canvas dims, element count, the user's
        stated goal, and an optional engine-level bbox pre-flag from
        the geometry inspector.

    The pure-Python geometry checker (`layout_inspector.inspect_snapshot`)
    still runs first as a fast, free pre-pass — its findings are folded
    into the LLM prompt as hints and also appended as a trailer when
    relevant.  When the screenshot is missing (rare — every PPT engine
    action requests `return_screenshot=true` by default), the tool falls
    back to the geometry-only report with a clear marker so the planner
    knows it didn't get a visual judgment this turn.

    Why visual
    ----------
    The legacy text/JSON-only check missed a whole class of bugs the
    user actually cares about: wrong-direction arcs, mirrored elements,
    palette drift, replicated layouts that don't actually resemble the
    reference, decorative shapes blanketing focal content.  Bboxes don't
    tell you any of that.  See conversation around 260426.

    Inline design choice
    --------------------
    Still an `InlineTool` — no Local Engine round-trip.  We only need
    one extra LLM call (vision) which we make in-process; the screenshot
    is already on `ctx.execution_result`.
    """

    name = "ppt_verify_layout"
    group = "ppt"
    router_hint = (
        "Visual layout review: a vision LLM looks at the rendered slide "
        "screenshot (and the user's reference image when present) and "
        "lists concrete defects with suggested fixes.  Call **before "
        "`stop`** after any layout change."
    )
    router_detail = _VERIFY_LAYOUT_DETAIL
    is_read_only = True

    # Vision verifier sub-LLM config.  Kept conservative: short output, low
    # temperature, screenshot-friendly model.  Inherits the same model as
    # the planner unless explicitly overridden.
    _VERIFIER_MAX_TOKENS: ClassVar[int] = 1024
    _VERIFIER_TEMPERATURE: ClassVar[float] = 0.2

    input_schema = {
        "type": "object",
        "properties": {
            "task_type": {
                "type": "string",
                "enum": ["replicate", "modify", "create"],
                "description": (
                    "How to interpret the reference image. "
                    "'replicate' = reference is the target (strict "
                    "comparison). 'modify' = reference is the BEFORE "
                    "state; differences from it are intentional. "
                    "'create' = no reference. Default: 'modify'."
                ),
            },
            "focus": {
                "type": "string",
                "description": (
                    "One-sentence paraphrase of what the user actually "
                    "asked for; the verifier checks the rendered slide "
                    "against this. Strongly recommended for "
                    "task_type='modify' / 'create'."
                ),
            },
            "acceptance_criteria": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Concrete must-haves that translate directly into "
                    "pass/fail visual checks. Items not visibly "
                    "satisfied become errors."
                ),
            },
            "slide": {
                "type": ["integer", "string"],
                "description": (
                    "Informational; the review always targets the "
                    "``current_slide`` of the latest snapshot."
                ),
            },
            "min_overlap_ratio": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": (
                    "Override the default 0.15 overlap-area ratio "
                    "threshold for the geometry pre-pass."
                ),
            },
        },
    }

    _VALID_TASK_TYPES: ClassVar[set] = {"replicate", "modify", "create"}

    async def run(
        self, params: Dict[str, Any], ctx: "NodeContext"
    ) -> str:
        snap = extract_snapshot_dict(ctx)
        if not snap:
            return (
                "[ppt_verify_layout] no snapshot available in the current "
                "execution_result.  Run a PPT action that returns a "
                "snapshot first (e.g. `ppt_render_ppt_layout`, "
                "`ppt_update_element`, or any other `ppt_*` action with "
                "`return_screenshot=true`)."
            )

        slide_index = self._coerce_slide_index(params)
        report = self._run_geometry_inspector(snap, slide_index, params)
        intent = self._coerce_intent(params)

        screenshot_b64 = self._extract_screenshot_b64(snap)
        if not screenshot_b64:
            # Vision review is impossible without a render. Surface the
            # geometry-only report with a clear header so the planner knows
            # it didn't get a visual judgment.
            geo_md = format_report_markdown(report)
            header = (
                "## Layout check (visual): SKIPPED — no screenshot this turn\n"
                "- The previous PPT action did not return a screenshot, so a "
                "visual review could not run.  Falling back to the geometry "
                "pre-pass below.\n"
                "- To get a real visual review, re-run the relevant PPT "
                "action with `return_screenshot=true` (the default) or call "
                "`ppt_render_ppt_layout` again, then call "
                "`ppt_verify_layout`.\n\n"
            )
            return header + geo_md

        try:
            visual_md = await self._run_visual_verifier(
                ctx=ctx,
                snapshot=snap,
                geometry_report=report,
                intent=intent,
            )
        except Exception as e:  # noqa: BLE001
            # Vision call failed — fall back to geometry-only with a
            # warning header.  Better an honest geometry report than a
            # silent skip.
            geo_md = format_report_markdown(report)
            return (
                "## Layout check (visual): FAILED to run vision review — "
                f"falling back to geometry-only.\n"
                f"- reason: `{type(e).__name__}: {e}`\n\n"
                + geo_md
            )

        # Append the geometry pre-pass as a trailer ONLY when it actually
        # found something — the visual reviewer is the headline; geometry
        # is supporting evidence.
        if report.has_issues:
            visual_md = (
                visual_md.rstrip()
                + "\n\n---\n\n"
                + "### Engine geometry pre-pass (raw bbox checks, supporting evidence)\n"
                + format_report_markdown(report)
            )
        return visual_md

    # -- helpers --

    @classmethod
    def _coerce_intent(cls, params: Dict[str, Any]) -> Dict[str, Any]:
        """Normalise the task-type / focus / acceptance_criteria params.

        Returns a dict with stable keys: ``task_type`` (always one of
        ``replicate`` / ``modify`` / ``create``), ``focus`` (str | None),
        and ``acceptance_criteria`` (list[str], possibly empty).
        Unknown / missing task_type falls back to ``modify`` — the
        conservative interpretation (only flag breakage), which avoids
        the historical loop where the verifier kept demanding the slide
        match a stale "before" screenshot.
        """
        if not isinstance(params, dict):
            return {"task_type": "modify", "focus": None, "acceptance_criteria": []}

        raw_type = params.get("task_type")
        if isinstance(raw_type, str) and raw_type.strip().lower() in cls._VALID_TASK_TYPES:
            task_type = raw_type.strip().lower()
        else:
            task_type = "modify"

        focus = params.get("focus")
        focus_s: Optional[str] = None
        if isinstance(focus, str):
            stripped = focus.strip()
            if stripped:
                focus_s = stripped

        ac_raw = params.get("acceptance_criteria")
        ac_list: List[str] = []
        if isinstance(ac_raw, list):
            for item in ac_raw:
                if isinstance(item, str):
                    s = item.strip()
                    if s:
                        ac_list.append(s)
        elif isinstance(ac_raw, str) and ac_raw.strip():
            # Tolerate a single-string form ("- a; - b") — split on newlines.
            for line in ac_raw.splitlines():
                s = line.strip(" -•\t")
                if s:
                    ac_list.append(s)

        return {
            "task_type": task_type,
            "focus": focus_s,
            "acceptance_criteria": ac_list,
        }

    @staticmethod
    def _coerce_slide_index(params: Dict[str, Any]) -> Optional[int]:
        if not isinstance(params, dict):
            return None
        v = params.get("slide")
        if isinstance(v, int):
            return v
        if isinstance(v, str):
            try:
                return int(v)
            except ValueError:
                return None
        return None

    @staticmethod
    def _run_geometry_inspector(
        snap: Dict[str, Any],
        slide_index: Optional[int],
        params: Dict[str, Any],
    ):
        """Run the pure-Python geometry inspector; supports a per-call
        ``min_overlap_ratio`` override via a scoped constant swap (same
        pattern as the legacy implementation, kept for parity)."""
        override = params.get("min_overlap_ratio") if isinstance(params, dict) else None
        if override is None:
            return inspect_snapshot(snap, slide_index=slide_index)
        from . import layout_inspector as _li
        try:
            ratio = float(override)
        except (TypeError, ValueError):
            return inspect_snapshot(snap, slide_index=slide_index)
        prev = _li._OVERLAP_MIN_RATIO
        _li._OVERLAP_MIN_RATIO = max(0.0, min(1.0, ratio))
        try:
            return inspect_snapshot(snap, slide_index=slide_index)
        finally:
            _li._OVERLAP_MIN_RATIO = prev

    @staticmethod
    def _extract_screenshot_b64(snap: Dict[str, Any]) -> Optional[str]:
        for key in ("screenshot", "screenshot_base64"):
            v = snap.get(key)
            if isinstance(v, str) and v.strip():
                s = v.strip()
                if s.startswith("data:") and "," in s:
                    s = s.split(",", 1)[1]
                return s
        return None

    @staticmethod
    def _extract_attached_images_b64(ctx: "NodeContext") -> List[str]:
        out: List[str] = []
        for item in getattr(ctx, "attached_images", None) or []:
            if not isinstance(item, dict):
                continue
            v = item.get("base64")
            if not isinstance(v, str) or not v.strip():
                continue
            s = v.strip()
            if s.startswith("data:") and "," in s:
                s = s.split(",", 1)[1]
            out.append(s)
        return out

    def _build_verifier_user_prompt(
        self,
        ctx: "NodeContext",
        snapshot: Dict[str, Any],
        geometry_report,
        intent: Dict[str, Any],
    ) -> str:
        sw, sh = _slide_dimensions(ctx)
        cur_slide = None
        content = snapshot.get("content") if isinstance(
            snapshot.get("content"), dict
        ) else None
        if content:
            cs = content.get("current_slide")
            if isinstance(cs, dict):
                cur_slide = cs
        elements: List[Dict[str, Any]] = []
        if cur_slide and isinstance(cur_slide.get("elements"), list):
            elements = [e for e in cur_slide["elements"] if isinstance(e, dict)]
        elem_count = len(elements)

        user_goal = (getattr(ctx, "query", "") or "").strip() or "(no explicit goal)"
        node_instr = ""
        try:
            node_instr = (ctx.get_node_instruction() or "").strip()
        except Exception:  # noqa: BLE001
            pass

        ref_count = len(self._extract_attached_images_b64(ctx))

        task_type = intent.get("task_type", "modify")
        focus = intent.get("focus")
        ac_list = intent.get("acceptance_criteria") or []

        lines: List[str] = [
            "## Slide under review",
            f"- canvas: {sw:.0f}×{sh:.0f} pt",
            f"- elements on current slide: {elem_count}",
            "",
            "## User intent",
            f"- overall goal: {user_goal}",
        ]
        if node_instr:
            lines.append(f"- current node: {node_instr}")
        lines.append("")

        # ---- Task type (most important block; drives reference handling) ----
        lines.append("## Task type")
        if task_type == "replicate":
            lines.append(
                "- **`replicate`** — the user wants the slide to look "
                "like the reference image.  Compare strictly: "
                "composition, primary element count, palette family, "
                "arrow / curve direction, reading order.  Differences "
                "from the reference ARE defects."
            )
        elif task_type == "create":
            lines.append(
                "- **`create`** — fresh content.  No reference "
                "comparison.  Judge the screenshot on its own visual "
                "merit and against the focus / acceptance criteria "
                "below."
            )
        else:  # modify
            lines.append(
                "- **`modify`** — the user wants the slide CHANGED "
                "from its prior state.  Any reference image attached "
                "this turn is the BEFORE state; the user explicitly "
                "does NOT want the current screenshot to look like it.  "
                "**Differences from the reference are the user's "
                "intent, NOT defects** — do not flag them.  Only flag "
                "real visual breakage and unmet acceptance criteria."
            )
        lines.append("")

        if focus:
            lines.append("## Focus")
            lines.append(f"- {focus}")
            lines.append("")

        if ac_list:
            lines.append("## Acceptance criteria")
            lines.append(
                "Each item below must be visibly satisfied in the "
                "screenshot.  Items that are NOT satisfied → **error**."
            )
            for item in ac_list[:12]:
                lines.append(f"- {item}")
            if len(ac_list) > 12:
                lines.append(f"- …and {len(ac_list) - 12} more (omitted)")
            lines.append("")

        lines.append("## Image inputs (in order)")
        lines.append(
            "1. **rendered slide screenshot** — the current PowerPoint "
            "window content.  Treat this as ground truth for what's on "
            "the slide right now."
        )
        if ref_count > 0:
            if task_type == "replicate":
                lines.append(
                    f"2. **user reference image(s)** ({ref_count} total) — "
                    "what the slide is supposed to look like.  Compare "
                    "the screenshot to these images."
                )
            elif task_type == "modify":
                lines.append(
                    f"2. **prior-state image(s)** ({ref_count} total) — "
                    "the slide as it looked BEFORE the user asked for "
                    "changes.  These are NOT a target.  Use them only "
                    "to recognise what the user is trying to change "
                    "away from."
                )
            else:  # create
                lines.append(
                    f"2. **incidental image(s)** ({ref_count} total) — "
                    "task type is 'create', so do NOT compare the "
                    "screenshot to these.  Judge on visual merit + "
                    "focus / acceptance criteria only."
                )
        else:
            lines.append(
                "2. (no reference image attached this turn — judge the "
                "screenshot on its own visual merit: not broken, not "
                "off-canvas, readable, balanced)."
            )
        lines.append("")

        # Live handle inventory — verifier MUST cite handles only from this list.
        if elements:
            lines.append(
                "## Editable handle inventory (current slide — SOURCE OF TRUTH)"
            )
            lines.append(
                "When you cite an element by `handle_id`, it MUST come from "
                "this list verbatim.  Do not invent or copy from older "
                "outputs — handles drift on every render."
            )
            from useit_studio.ai_run.node_handler.agent_node.handler import AgentNodeHandler
            inventory = AgentNodeHandler._format_handle_inventory(
                elements, max_lines=80
            )
            if inventory:
                lines.extend(inventory)
            else:
                lines.append("- (no addressable handle_ids on this slide)")
            lines.append("")

        lines.append("## Engine geometry pre-flag (HINT, not verdict)")
        if not geometry_report.has_issues:
            lines.append(
                "- The bbox-level inspector found **no overlap / off-canvas "
                "/ degenerate / text-fit** issues.  Don't manufacture issues "
                "that aren't visible in the screenshot."
            )
        else:
            lines.append(
                f"- The bbox-level inspector flagged {geometry_report.error_count} "
                f"error(s) and {geometry_report.warning_count} warning(s).  "
                "These messages may quote handle_ids — IGNORE those quoted "
                "ids when writing your report; use only the inventory above. "
                "Use these messages only to identify locations to look at:"
            )
            for issue in geometry_report.issues[:10]:
                lines.append(f"  - [{issue.kind}/{issue.severity}] {issue.message}")
            if len(geometry_report.issues) > 10:
                lines.append(f"  - …and {len(geometry_report.issues) - 10} more")
        lines.append("")

        lines.append(
            "## Your task\n"
            "Look at the rendered screenshot.  Decide if the slide is "
            "ready to ship vs. the user intent above.  Emit the markdown "
            "format defined in the system prompt — nothing else."
        )
        return "\n".join(lines)

    async def _run_visual_verifier(
        self,
        *,
        ctx: "NodeContext",
        snapshot: Dict[str, Any],
        geometry_report,
        intent: Dict[str, Any],
    ) -> str:
        """Build prompt + call vision LLM + return its markdown body."""
        from useit_studio.ai_run.node_handler.functional_nodes.computer_use.gui_v2.utils.llm_client import (
            LLMConfig,
            VLMClient,
        )
        from useit_studio.ai_run.utils.logger_utils import LoggerUtils

        node_data = (
            (ctx.node_dict or {}).get("data", {}) if getattr(ctx, "node_dict", None) else {}
        )
        model = (
            node_data.get("model")
            or getattr(ctx, "planner_model", None)
            or "gpt-4o-mini"
        )

        vlm = VLMClient(
            config=LLMConfig(
                model=model,
                max_tokens=self._VERIFIER_MAX_TOKENS,
                temperature=self._VERIFIER_TEMPERATURE,
                role=f"tool:{self.name}",
                node_id=getattr(ctx, "node_id", "unknown"),
            ),
            api_keys=getattr(ctx, "planner_api_keys", None),
            logger=LoggerUtils(component_name=f"InlineTool:{self.name}"),
        )

        screenshot_b64 = self._extract_screenshot_b64(snapshot) or ""
        attached_b64 = self._extract_attached_images_b64(ctx)
        user_prompt = self._build_verifier_user_prompt(
            ctx, snapshot, geometry_report, intent
        )

        response = await vlm.call(
            prompt=user_prompt,
            system_prompt=_VERIFY_LAYOUT_SYSTEM_PROMPT,
            screenshot_base64=screenshot_b64,
            attached_images_base64=attached_b64 or None,
            log_dir=getattr(ctx, "log_folder", None),
        )

        content = (response.get("content") or "").strip()
        if not content:
            raise RuntimeError(
                "vision verifier returned empty content"
            )
        # Light sanity guard: if the model didn't follow the format and
        # produced free-form text without our header, wrap it so the
        # planner still gets a parseable response.
        if "Layout check (visual)" not in content:
            content = (
                "## Layout check (visual): unstructured response — review manually\n"
                "- the vision model did not follow the strict format; raw output below.\n\n"
                + content
            )
        return content


# ==========================================================================
# Registry
# ==========================================================================

TOOLS: List[Any] = [
    # presentation lifecycle (open a specific .pptx / close)
    PPTDocument(),
    # slide lifecycle (consolidated: add / delete / duplicate / move / goto)
    PPTSlide(),
    # element editing
    PPTUpdateElement(),
    PPTArrangeElements(),   # align / reorder / group / ungroup
    PPTDeleteElement(),
    # content insertion (media / table; chart stays separate as LLMEngineTool)
    PPTInsert(),
    PPTInsertNativeChart(),
    # layout rendering (SVG -> native shapes)
    PPTRenderPPTLayout(),
    # animation (add / clear)
    PPTAnimation(),
    # layout verification (inline; static geometry check on last snapshot)
    PPTVerifyLayout(),
    # escape hatch
    PPTExecuteCode(),
]
