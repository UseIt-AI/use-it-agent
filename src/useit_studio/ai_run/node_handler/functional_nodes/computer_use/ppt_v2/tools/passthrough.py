"""
PPT V2 — Passthrough Tools

Simple actions that need no LLM call. The Router Planner provides all
required parameters; these tools just wrap them into a ``tool_call`` event.
"""

from __future__ import annotations

from typing import Any, Dict, List, Union

from .base import PassthroughTool, ToolRegistry, ToolRequest, ToolResult


# ---------------------------------------------------------------------------
# update_element — detailed API reference injected into the Router prompt
# ---------------------------------------------------------------------------

_UPDATE_ELEMENT_DETAIL = r"""Modify existing shapes by `handle_id` (single) or `handle_ids` (list for batch).
Params: `slide`, `handle_id`/`handle_ids`, `properties { ... }`.
Only include properties you want to change — omitted properties are preserved.

**Batch mode:** Apply the same properties to multiple shapes in one step:
```json
{
  "action": "update_element", "slide": 1,
  "handle_ids": ["Oval 25", "Oval 30", "Oval 36"],
  "properties": {
    "line_gradient": {"type": "linear", "angle": 45, "stops": [{"position": 0, "color": "#FF4D00"}, {"position": 1, "color": "#FFD700"}]}
  }
}
```

**Supported properties:**

| Property | Type | Description |
|----------|------|-------------|
| `x` | float | Left offset (pt) |
| `y` | float | Top offset (pt) |
| `width` | float | Width (pt) |
| `height` | float | Height (pt) |
| `rotation` | float | Rotation angle (degrees) |
| `visible` | bool | Visibility |
| `fill_color` | string | Solid fill (`#RRGGBB` or `"none"`). Exclusive with `fill_gradient`. |
| `fill_gradient` | object | Gradient fill (see schema below). Exclusive with `fill_color`. |
| `line_color` | string | Solid border (`#RRGGBB` or `"none"`). Exclusive with `line_gradient`. |
| `line_gradient` | object | Gradient border (same schema as `fill_gradient`). Exclusive with `line_color`. |
| `line_weight` | float | Border thickness (pt) |
| `shadow` | object / null | Shadow effect (see schema below). `null` to remove. |
| `text` | string | Replace all text. Exclusive with `rich_text`. |
| `rich_text` | array | Per-segment formatted text (see below). Exclusive with `text`. |
| `text_formats` | array | Format ranges of existing text (see below). Combinable with `text`/`rich_text`. |
| `font_name` | string | Font name (whole text; ignored with `rich_text`) |
| `font_size` | float | Font size pt (whole text; ignored with `rich_text`) |
| `font_bold` | bool | Bold (whole text; ignored with `rich_text`) |
| `font_italic` | bool | Italic (whole text; ignored with `rich_text`) |
| `font_color` | string | Font color `#RRGGBB` (whole text; ignored with `rich_text`) |
| `text_align` | string | `left` / `center` / `right` / `justify` |
| `cell_format` | array | Per-cell styling for existing tables. `row`/`col` must be integers (1-based), NEVER `"*"` or strings. |

> **z-order**: Use `reorder_elements` instead (supports batch, relative, and basic commands).

**Gradient schema** (`fill_gradient` / `line_gradient`):
```json
{"type": "linear", "angle": 45, "stops": [{"position": 0, "color": "#FF4D00", "opacity": 1}, {"position": 1, "color": "#FFD700"}]}
```
`type`: `"linear"` or `"radial"`. `angle`: degrees (linear only). `stops` (≥2): `position` (0–1), `color`, optional `opacity` (0–1).

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

**text_formats** — format ranges without full replacement:
```json
[
  {"match": "keyword", "font_bold": true, "font_color": "#FF0000"},
  {"match": "second", "nth": 2, "font_italic": true},
  {"start": 0, "length": 5, "font_size": 24},
  {"match": "old text", "text": "new text", "font_color": "#0066CC"}
]
```
Locate by `match` (substring, optional `nth` = 1-based) or `start` + `length`. Optional `text` to replace. Combinable with `text`/`rich_text`.

**Combined examples:**

Gradient fill + border + shadow:
```json
{
  "action": "update_element", "slide": "current", "handle_id": "card_bg",
  "properties": {
    "fill_gradient": {"type": "linear", "angle": 0, "stops": [{"position": 0, "color": "#1E3A5F"}, {"position": 1, "color": "#87CEEB"}]},
    "line_gradient": {"type": "linear", "angle": 45, "stops": [{"position": 0, "color": "#FF4D00"}, {"position": 1, "color": "#FFD700"}]},
    "line_weight": 4,
    "shadow": {"color": "#000000", "blur": 10, "offset_x": 3, "offset_y": 3, "opacity": 0.4}
  }
}
```

Set text + highlight keywords:
```json
{
  "action": "update_element", "slide": "current", "handle_id": "body",
  "properties": {
    "text": "AI is transforming the world. Deep Learning is the core driver.",
    "font_size": 16, "font_color": "#333333",
    "text_formats": [
      {"match": "AI", "font_bold": true, "font_color": "#FF4D00"},
      {"match": "Deep Learning", "font_bold": true, "font_color": "#0066CC"}
    ]
  }
}
```"""


# ---------------------------------------------------------------------------
# align_elements — detailed API reference injected into the Router prompt
# ---------------------------------------------------------------------------

_ALIGN_ELEMENTS_DETAIL = r"""Align shapes spatially — the **engine** does the math, not you.

**Use this for**: "center A on B", "align titles left", "center on slide".
**Do NOT** use `update_element` with `x`/`y` for alignment — use this tool instead.
**Do NOT** confuse with `text_align` (which is text alignment *inside* a text box).

**Params:** `slide`, `targets` (list), plus ONE of:
- `reference` (single shape Name or `"slide"`) — all targets align to this one reference
- `references` (list, same length as targets) — 1:1 paired alignment (target[i] → reference[i])
- neither — targets align to each other

**`horizontal`**: `"left"` | `"center"` | `"right"` | null (don't change x)
**`vertical`**: `"top"` | `"middle"` | `"bottom"` | null (don't change y)

**Examples:**

Center numbers inside circles (1:1 paired):
```json
{
  "action": "align_elements", "slide": "current",
  "targets": ["TextBox 27", "TextBox 32", "TextBox 38"],
  "references": ["Oval 25", "Oval 30", "Oval 36"],
  "horizontal": "center", "vertical": "middle"
}
```

Left-align multiple titles to each other:
```json
{
  "action": "align_elements", "slide": "current",
  "targets": ["Title 1", "Title 2", "Title 3"],
  "horizontal": "left"
}
```

Center a title on the slide:
```json
{
  "action": "align_elements", "slide": "current",
  "targets": ["Title 1"],
  "reference": "slide",
  "horizontal": "center"
}
```"""


# ---------------------------------------------------------------------------
# add_shape_animation — detailed API reference injected into the Router prompt
# ---------------------------------------------------------------------------

_ADD_SHAPE_ANIMATION_DETAIL = r"""Add animation to a shape.
**ALWAYS call `clear_slide_animations` first** when rebuilding animations from scratch.
**For animation sequences, use batch mode** (`"Action": "actions"` with `"Actions"` array) to send all steps atomically in one JSON block.

**Params:** `slide`, `handle_id` (or `shape_index`), `effect`, plus optional `category`, `trigger`, `duration`, `delay`, `direction`, `text_unit`, `insert_at`.

**Effects** (string names — engine maps to COM constants):
- Entrance: `appear`, `fade`, `fly`, `blinds`, `box`, `checkerboard`, `diamond`, `dissolve`, `peek`, `split`, `wipe`, `wheel`, `zoom`, `bounce`, `float`, `grow_and_turn`, `swivel`, `pinwheel`
- Emphasis: `pulse`, `spin`, `grow_shrink`, `teeter`, `wave`, `bold_flash`
- Exit: same names as entrance, set `"category": "exit"`

**Category:** `"entrance"` (default) | `"exit"` | `"emphasis"`
**Trigger:** `"on_click"` (default, new click step) | `"with_previous"` (sync) | `"after_previous"` (auto-chain)
**Direction** (for `fly`, `wipe`, `peek`): `from_top`, `from_bottom`, `from_left`, `from_right`, etc.

**Sequential appear/disappear pattern** (milestones, tabs, steps) — use batch mode:
```json
{
  "Action": "actions",
  "Title": "Setup sequential animation",
  "Actions": [
    {"action": "group_elements", "slide": "current", "handle_ids": ["Oval 25", "TextBox 27"], "group_name": "step_1"},
    {"action": "group_elements", "slide": "current", "handle_ids": ["Oval 30", "TextBox 32"], "group_name": "step_2"},
    {"action": "clear_slide_animations", "slide": "current"},
    {"action": "add_shape_animation", "handle_id": "step_1", "effect": "appear", "trigger": "on_click"},
    {"action": "add_shape_animation", "handle_id": "step_2", "effect": "appear", "trigger": "on_click"},
    {"action": "add_shape_animation", "handle_id": "step_1", "effect": "appear", "category": "exit", "trigger": "with_previous"}
  ],
  "MilestoneCompleted": false,
  "node_completion_summary": null
}
```
Click → step_1 appears → click → step_2 appears + step_1 disappears.

**Multi-step entrance sequence** — use batch mode:
```json
{
  "Action": "actions",
  "Title": "Multi-step entrance",
  "Actions": [
    {"action": "clear_slide_animations", "slide": "current"},
    {"action": "add_shape_animation", "handle_id": "title", "effect": "fly", "direction": "from_top", "trigger": "on_click"},
    {"action": "add_shape_animation", "handle_id": "subtitle", "effect": "fade", "trigger": "after_previous", "delay": 0.3},
    {"action": "add_shape_animation", "handle_id": "left_img", "effect": "fade", "trigger": "on_click"},
    {"action": "add_shape_animation", "handle_id": "right_img", "effect": "fade", "trigger": "with_previous"}
  ],
  "MilestoneCompleted": false,
  "node_completion_summary": null
}
```"""


# ---------------------------------------------------------------------------
# reorder_elements — detailed API reference injected into the Router prompt
# ---------------------------------------------------------------------------

_REORDER_ELEMENTS_DETAIL = r"""Change z-order (front/back stacking) of shapes. Three modes:

**Mode 1 — Batch ordering** (array from bottom to top):
```json
{"action": "reorder_elements", "slide": "current", "order": ["bg_rect", "content_image", "title_text", "logo"]}
```
Shapes NOT in `order` keep their position; listed shapes move above all others.

**Mode 2 — Relative positioning** (above/below another shape):
```json
{"action": "reorder_elements", "slide": "current", "handle_id": "title_text", "command": "above", "reference": "image_bg"}
```

**Mode 3 — Basic commands** (`bring_to_front` / `send_to_back` / `bring_forward` / `send_backward`):
```json
{"action": "reorder_elements", "slide": "current", "handle_id": "logo", "command": "bring_to_front"}
```

Use batch mode for compound changes:
```json
{
  "Action": "actions",
  "Title": "Reorder layers",
  "Actions": [
    {"action": "reorder_elements", "slide": "current", "handle_id": "bg_rect", "command": "send_to_back"},
    {"action": "reorder_elements", "slide": "current", "handle_id": "logo", "command": "bring_to_front"}
  ],
  "MilestoneCompleted": false,
  "node_completion_summary": null
}
```"""


# ---------------------------------------------------------------------------
# insert_native_table — detailed API reference injected into the Router prompt
# ---------------------------------------------------------------------------

_INSERT_NATIVE_TABLE_DETAIL = r"""Insert a PPT native table. Prefer this over drawing fake tables with rectangles.

**IMPORTANT:** `slide` MUST be an integer (e.g. `1`, `2`), NOT `"current"`. Use the slide index from the snapshot.

**Params:** `slide` (int), `bounding_box` (`{x, y, w, h}`), `data` (2D array), `handle_id` (optional), plus styling:

| Param | Type | Description |
|-------|------|-------------|
| `first_row_header` | bool | Default `true`. First row gets header styling. |
| `cell_format` | array | Per-cell styling (see below). **Design colors to match the slide's palette.** |

**You are the designer.** Look at the slide's existing colors/style and design the table to match.
Typical approach: gradient or solid fill on header row, alternating subtle row tones, thin borders, generous padding.

**Two-step pattern** — create structure first, then style:
1. `insert_native_table` with data + bounding_box
2. `update_element` with `cell_format` for visual polish

Or do it in one call with inline `cell_format`.

Example — 3-row, 3-col table with styled header:
```json
{
  "action": "insert_native_table", "slide": 2,
  "bounding_box": {"x": 80, "y": 100, "w": 800, "h": 320},
  "data": [["Product", "Q1", "Q2"], ["Alpha", "$120k", "$150k"], ["Beta", "$90k", "$110k"]],
  "handle_id": "sales_table",
  "cell_format": [
    {"row": 1, "col": 1, "fill_color": "#1A1A2E", "font_color": "#FFFFFF", "font_bold": true, "align": "center"},
    {"row": 1, "col": 2, "fill_color": "#1A1A2E", "font_color": "#FFFFFF", "font_bold": true, "align": "center"},
    {"row": 1, "col": 3, "fill_color": "#1A1A2E", "font_color": "#FFFFFF", "font_bold": true, "align": "center"},
    {"row": 2, "col": 1, "font_size": 14, "align": "center"},
    {"row": 2, "col": 2, "font_size": 14, "align": "center"},
    {"row": 2, "col": 3, "font_size": 14, "align": "center"},
    {"row": 3, "col": 1, "font_size": 14, "align": "center"},
    {"row": 3, "col": 2, "font_size": 14, "align": "center"},
    {"row": 3, "col": 3, "font_size": 14, "align": "center"}
  ]
}
```

**cell_format** — target by `row`/`col`:
- `row` and `col` MUST be **integers** (1-based). Row 1 = first row, Col 1 = first column.
- **NEVER use `"*"`, range syntax, or strings** — only integers. These will crash the engine.
- To style an entire row: create one entry per column in that row.
- To style an entire column: create one entry per row in that column.
- To apply global defaults: list each row explicitly, or apply to a few key rows.

Supported properties: `fill_color`, `fill_gradient`, `fill_transparency`, `font_color`, `font_bold`, `font_italic`, `font_size`, `font_name`, `align`, `line_color`, `line_transparency`, `line_weight`, `margin_left/right/top/bottom`.

Example — 7-row, 6-col table with styled header + totals:
```json
{"cell_format": [
  {"row": 1, "col": 1, "fill_color": "#333333", "font_color": "#FFFFFF", "font_bold": true, "align": "center"},
  {"row": 1, "col": 2, "fill_color": "#00B5AD", "font_color": "#FFFFFF", "font_bold": true, "align": "center"},
  {"row": 1, "col": 3, "fill_color": "#00B5AD", "font_color": "#FFFFFF", "font_bold": true, "align": "center"},
  {"row": 1, "col": 4, "fill_color": "#8B7368", "font_color": "#FFFFFF", "font_bold": true, "align": "center"},
  {"row": 1, "col": 5, "fill_color": "#32B5E5", "font_color": "#FFFFFF", "font_bold": true, "align": "center"},
  {"row": 1, "col": 6, "fill_color": "#FFB840", "font_color": "#000000", "font_bold": true, "align": "center"},
  {"row": 7, "col": 1, "fill_color": "#333333", "font_color": "#FFFFFF", "font_bold": true},
  {"row": 7, "col": 2, "fill_color": "#E9ECEF", "font_bold": true, "align": "center"},
  {"row": 7, "col": 3, "fill_color": "#E9ECEF", "font_bold": true, "align": "center"},
  {"row": 7, "col": 4, "fill_color": "#E9ECEF", "font_bold": true, "align": "center"},
  {"row": 7, "col": 5, "fill_color": "#E9ECEF", "font_bold": true, "align": "center"},
  {"row": 7, "col": 6, "fill_color": "#E9ECEF", "font_bold": true, "align": "center"}
]}
```"""


def _expand_update_element(params: Dict[str, Any]) -> Union[Dict, List[Dict]]:
    """Support both single ``handle_id`` and batch ``handle_ids``.

    When ``handle_ids`` (list) is provided, the same ``properties`` / ``slide``
    are applied to every handle, producing one action per element.
    """
    handle_ids = params.pop("handle_ids", None)
    if handle_ids and isinstance(handle_ids, list):
        shared = {k: v for k, v in params.items()}
        return [{"handle_id": hid, **shared} for hid in handle_ids]
    return params


# ---------------------------------------------------------------------------
# Stop tool — special: signals task completion instead of engine /step
# ---------------------------------------------------------------------------

class StopTool:
    """Pseudo-tool that signals the agent loop to stop."""

    _name = "stop"
    _router_hint = "Mark task as completed (only after visual review passes)"

    @property
    def name(self) -> str:
        return self._name

    @property
    def router_hint(self) -> str:
        return self._router_hint

    async def execute(self, request: ToolRequest) -> ToolResult:
        return ToolResult(name="stop", args={}, reasoning="Task completed")

    async def execute_streaming(self, request: ToolRequest):
        result = await self.execute(request)
        yield {"type": "tool_result", "result": result}


# ---------------------------------------------------------------------------
# Factory: register all passthrough tools
# ---------------------------------------------------------------------------

def register_passthrough_tools(registry: ToolRegistry) -> None:
    """Create and register every simple passthrough tool."""

    registry.register(PassthroughTool(
        name="add_slide",
        router_hint='Add a new slide. Params: layout ("blank"|"title"|"title_content"|…), index (optional, 1-based).',
    ))

    registry.register(PassthroughTool(
        name="delete_slide",
        router_hint="Delete a slide by index. Params: slide (int).",
    ))

    registry.register(PassthroughTool(
        name="duplicate_slide",
        router_hint="Duplicate a slide. Params: slide (int).",
    ))

    registry.register(PassthroughTool(
        name="move_slide",
        router_hint="Move a slide to a new position. Params: slide (int), to_index (int).",
    ))

    registry.register(PassthroughTool(
        name="goto_slide",
        router_hint='Navigate to a slide. Params: slide (int | "first" | "last" | "next" | "prev").',
    ))

    registry.register(PassthroughTool(
        name="update_element",
        router_hint=(
            "Modify existing shapes (geometry, fill, line, shadow, text, font, z-order). "
            "Params: slide, handle_id/handle_ids, properties. "
            "**Prefer over execute_code for ALL styling.**"
        ),
        router_detail=_UPDATE_ELEMENT_DETAIL,
        build_args_fn=_expand_update_element,
    ))

    registry.register(PassthroughTool(
        name="align_elements",
        router_hint=(
            "Spatially align shapes (center on shape, align edges, center on slide). "
            "Engine calculates positions — no manual x/y math needed. "
            "Params: slide, targets, reference/references, horizontal, vertical."
        ),
        router_detail=_ALIGN_ELEMENTS_DETAIL,
    ))

    registry.register(PassthroughTool(
        name="reorder_elements",
        router_hint=(
            "Change z-order (front/back stacking). "
            "3 modes: batch order list, relative (above/below reference), "
            "or command (bring_to_front/send_to_back/bring_forward/send_backward)."
        ),
        router_detail=_REORDER_ELEMENTS_DETAIL,
    ))

    registry.register(PassthroughTool(
        name="delete_element",
        router_hint="Delete a shape by handle_id. Params: slide, handle_id.",
    ))

    registry.register(PassthroughTool(
        name="group_elements",
        router_hint="Group multiple shapes into one. Params: slide, handle_ids (list), group_name (optional).",
    ))

    registry.register(PassthroughTool(
        name="ungroup_elements",
        router_hint="Dissolve a group back into individual shapes. Params: slide, handle_id.",
    ))

    registry.register(PassthroughTool(
        name="insert_media",
        router_hint="Insert an image/media file directly. Params: slide, media_path, bounding_box, handle_id (optional).",
    ))

    registry.register(PassthroughTool(
        name="insert_native_table",
        router_hint=(
            "Insert a native PPT table. **Prefer over fake rect+text tables for any tabular data.** "
            "Params: slide, bounding_box, data (2D array), handle_id, cell_format. "
            "Design table colors with cell_format to match the slide's visual style."
        ),
        router_detail=_INSERT_NATIVE_TABLE_DETAIL,
    ))

    registry.register(PassthroughTool(
        name="add_shape_animation",
        router_hint=(
            "Add animation to a shape (entrance/exit/emphasis). "
            "Params: slide, handle_id, effect, category, trigger, duration, delay, direction. "
            "**NEVER use execute_code for animations — use this tool.**"
        ),
        router_detail=_ADD_SHAPE_ANIMATION_DETAIL,
    ))

    registry.register(PassthroughTool(
        name="clear_slide_animations",
        router_hint=(
            "Clear all animations on a slide, or just one shape's animations. "
            "Params: slide, handle_id (optional). "
            "Call before rebuilding animation sequences."
        ),
    ))

    registry.register(StopTool())
