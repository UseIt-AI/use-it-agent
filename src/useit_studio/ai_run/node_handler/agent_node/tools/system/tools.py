"""System tools —— 桌面窗口 & 进程控制。

Two consolidated engine tools (``system_window_control`` and
``system_process_control``) that dispatch on an ``action`` discriminator
field.  Matches the :mod:`..gui` pack shape: flat ``{name, args}`` tool
calls (not the ``/step`` protocol used by PPT/Excel/Word).

Design notes
------------
* **Schema authored here, not on the frontend.**  The old flow relied on
  ``zod.toJSONSchema()`` on the frontend side which was dropping
  ``items.properties`` on nested arrays (e.g. ``zones``) and breaking
  both Gemini function-call 400s AND the frontend's own Zod validator
  after the LLM replied.  Authoring the schema here guarantees a
  consistent shape for every consumer (orchestrator LLM, AgentNode
  Router Planner, and the frontend).
* **Strict on ``required``.**  ``action`` is the only unconditional
  required field — every other argument is action-specific.  The tool
  description + ``router_detail`` carry the per-action "required extras"
  rules so the LLM knows what to fill per action.
"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, TYPE_CHECKING

from ..protocol import EngineTool, ToolCall

if TYPE_CHECKING:
    from ...models import (
        PlannerOutput,
    )


class _SystemEngineTool(EngineTool):
    """Flat payload shape (name + args), matching the GUI pack.

    Target stays ``"app"`` so the existing frontend app-action handler
    (``systemActions.ts`` → ``localEngine.windowControl/processControl``)
    keeps working without changes.
    """

    group: ClassVar[str] = "system"
    target: ClassVar[str] = "app"

    def build_tool_call(
        self, params: Dict[str, Any], planner_output: "PlannerOutput"
    ) -> ToolCall:
        return ToolCall(name=self.action_name, args=dict(params))


# ---------------------------------------------------------------------------
# Reusable sub-schemas
# ---------------------------------------------------------------------------

_ZONE_ITEM_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "description": (
        "A rectangle expressed as 0~1 proportions of the monitor's work "
        "area (taskbar excluded).  E.g. `{x:0, y:0, width:0.5, height:1}` "
        "= entire left half."
    ),
    "properties": {
        "x": {"type": "number", "description": "Left edge (0~1)."},
        "y": {"type": "number", "description": "Top edge (0~1)."},
        "width": {"type": "number", "description": "Width (0~1)."},
        "height": {"type": "number", "description": "Height (0~1)."},
    },
    "required": ["x", "y", "width", "height"],
}

_WINDOW_LAYOUTS = [
    "auto",
    "full",
    "left_right",
    "top_bottom",
    "vertical_3",
    "horizontal_3",
    "vertical_n",
    "horizontal_n",
    "grid_2x2",
    "main_left",
    "main_right",
    "main_top",
    "main_bottom",
]


# ---------------------------------------------------------------------------
# Window control
# ---------------------------------------------------------------------------


_WINDOW_CONTROL_ROUTER_DETAIL = """\
### `system_window_control` — operate on windows

`action` values and their required extras:

| action            | required extras                                             | notes |
|-------------------|-------------------------------------------------------------|-------|
| `list`            | —                                                           | optional: `process_name`, `title_contains`, `include_minimized` |
| `get_foreground`  | —                                                           | current foreground window |
| `list_monitors`   | —                                                           | enumerate monitors (includes each monitor's `work_area`) |
| `activate`        | one of `hwnd` / `process_name` / `title_contains`           | bring to front; auto-restores if minimised |
| `minimize`        | same locator rules as activate                              | |
| `maximize`        | same locator rules as activate                              | |
| `restore`         | same locator rules as activate                              | |
| `close`           | same locator rules as activate; optional `force: bool`      | default sends `WM_CLOSE`; `force=true` hard-kills |
| `set_topmost`     | locator + `on: bool`                                        | pin / unpin on top |
| `move_resize`     | locator + `x, y, width, height` (pixels)                    | auto-unmaximises first |
| `tile`            | `hwnds: int[]` + `layout` (optional `monitor_id`, `ratios`, `zones`) | see layout catalog below |

**Target locator rules:**
- `hwnd` is strongly preferred — copy it verbatim from the current-turn
  `### open_windows` snapshot (each line starts with `hwnd=<N>`).  Never
  invent hwnds.
- Otherwise pass `process_name` and/or `title_contains` for fuzzy lookup.
  If multiple match, the tool returns `success=false` with
  `data.candidates`; pick one and re-call with a specific `hwnd`.

**`tile.layout` catalog:** `auto` / `full` / `left_right` / `top_bottom`
/ `vertical_3` / `horizontal_3` / `vertical_n` / `horizontal_n` /
`grid_2x2` / `main_left` / `main_right` / `main_top` / `main_bottom`.
`main_*` puts `hwnds[0]` in the "main" slot and stacks the rest on the
opposite side.

**`tile.ratios` (optional numbers):**
- For even splits (`left_right` / `top_bottom` / `vertical_*` /
  `horizontal_*`): length MUST equal `hwnds.length`.
- For `main_*` layouts: length MUST be exactly 2 — `[main, stack]`.
- Auto-normalised: `[4, 1]` and `[0.8, 0.2]` are equivalent.

**`tile.zones` (optional, full manual override):**
- Each entry is `{x, y, width, height}` as 0~1 proportions of the work
  area (not pixels).  `hwnds[i]` goes into `zones[i]`.
- When provided, `layout` and `ratios` are ignored.
- Use ONLY for irregular rectangles that no named layout covers.

Example — A on left, B+C stacked on right:
```json
{"action": "tile", "hwnds": [A, B, C], "layout": "main_left"}
```

Example — left 80% / right 20% full-height (manual zones):
```json
{"action": "tile", "hwnds": [A, B],
 "zones": [{"x":0,"y":0,"width":0.8,"height":1},
           {"x":0.8,"y":0,"width":0.2,"height":1}]}
```

**UseIt-Studio chat strip (recommended pattern).**
UseIt-Studio is the app the user talks to you through.  When you tile
multiple windows for the user, put UseIt-Studio (find it in
`open_windows` by `process_name` containing `UseIt-Studio`) into a
~15-20% right-side strip and let the work windows fill the left ~80%.
This keeps the chat visible without pinning it on top.

Example — work windows stacked on the left, UseIt-Studio as right strip:
```json
{"action": "tile",
 "hwnds": [<work_top>, <work_bottom>, <useit>],
 "zones": [{"x":0,   "y":0,   "width":0.8, "height":0.5},
           {"x":0,   "y":0.5, "width":0.8, "height":0.5},
           {"x":0.8, "y":0,   "width":0.2, "height":1.0}]}
```

Example — single work window + chat strip:
```json
{"action": "tile",
 "hwnds": [<work>, <useit>],
 "zones": [{"x":0,   "y":0, "width":0.8, "height":1.0},
           {"x":0.8, "y":0, "width":0.2, "height":1.0}]}
```

Skip the chat strip only when the user explicitly asks for single-window
focus, or when the task does not involve tiling at all.
"""


class SystemWindowControl(_SystemEngineTool):
    name = "system_window_control"
    router_hint = (
        "Manage desktop windows (list / activate / minimize / maximize / "
        "restore / close / set_topmost / move_resize / tile / "
        "list_monitors).  Discriminate on `action`; see router_detail for "
        "per-action required fields and the full `tile.layout` catalog."
    )
    router_detail = _WINDOW_CONTROL_ROUTER_DETAIL
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "list",
                    "get_foreground",
                    "list_monitors",
                    "activate",
                    "minimize",
                    "maximize",
                    "restore",
                    "close",
                    "set_topmost",
                    "move_resize",
                    "tile",
                ],
                "description": "Operation to perform. See router_detail for per-action args.",
            },
            # --- target locator (activate / minimize / maximize / restore /
            # --- close / set_topmost / move_resize, and optionally `list`) ---
            "hwnd": {
                "type": "integer",
                "description": (
                    "Window handle.  Copy verbatim from the `hwnd=<N>` prefix "
                    "of the current-turn `open_windows` snapshot.  Do NOT invent."
                ),
            },
            "process_name": {
                "type": "string",
                "description": (
                    "Case-insensitive exe name (e.g. \"POWERPNT.EXE\") for fuzzy "
                    "lookup when `hwnd` is unknown."
                ),
            },
            "title_contains": {
                "type": "string",
                "description": "Case-insensitive substring of the window title.",
            },
            # --- list-only ---
            "include_minimized": {
                "type": "boolean",
                "description": "action=list only.  Include minimised windows.  Default true.",
            },
            # --- set_topmost ---
            "on": {
                "type": "boolean",
                "description": "action=set_topmost only.  true = pin / false = unpin.",
            },
            # --- move_resize (pixels) ---
            "x": {"type": "integer", "description": "action=move_resize only: left, in pixels."},
            "y": {"type": "integer", "description": "action=move_resize only: top, in pixels."},
            "width": {"type": "integer", "description": "action=move_resize only: width, in pixels."},
            "height": {"type": "integer", "description": "action=move_resize only: height, in pixels."},
            # --- tile ---
            "hwnds": {
                "type": "array",
                "items": {"type": "integer"},
                "description": (
                    "action=tile only.  Windows to arrange; order = placement "
                    "order (left→right, top→bottom; main_* puts hwnds[0] in "
                    "the main slot)."
                ),
            },
            "layout": {
                "type": "string",
                "enum": _WINDOW_LAYOUTS,
                "description": (
                    "action=tile only.  Layout strategy.  Default \"auto\".  See "
                    "router_detail for the full catalog + per-layout hwnds-length rules."
                ),
            },
            "monitor_id": {
                "type": "integer",
                "description": (
                    "action=tile only.  Target monitor id (from "
                    "action=list_monitors).  Default: primary."
                ),
            },
            "ratios": {
                "type": "array",
                "items": {"type": "number"},
                "description": (
                    "action=tile only.  Asymmetric split ratios.  For even "
                    "splits: length MUST equal hwnds.length.  For main_*: "
                    "length MUST be 2 ([main, stack]).  Integers or decimals "
                    "both accepted (auto-normalised).  E.g. [4, 1] or "
                    "[0.8, 0.2] both mean 80/20."
                ),
            },
            "zones": {
                "type": "array",
                "items": _ZONE_ITEM_SCHEMA,
                "description": (
                    "action=tile only.  Custom rectangles; overrides "
                    "layout/ratios.  Length MUST equal hwnds.length; "
                    "hwnds[i] is placed into zones[i]."
                ),
            },
            # --- close ---
            "force": {
                "type": "boolean",
                "description": (
                    "action=close only.  force=true hard-kills the process "
                    "(no save prompt).  Default false."
                ),
            },
        },
        "required": ["action"],
        "additionalProperties": False,
    }


# ---------------------------------------------------------------------------
# Process control
# ---------------------------------------------------------------------------


_PROCESS_CONTROL_ROUTER_DETAIL = """\
### `system_process_control` — launch apps & inspect installed software

`action` values and their required extras:

| action           | required extras                                | notes |
|------------------|------------------------------------------------|-------|
| `launch`         | at least one of `name` / `file` / `exe_path`   | smart launcher — open an app, open a file, or run an exe |
| `find_exe`       | `name`                                         | list candidate exe paths for a fuzzy app name |
| `list_installed` | —                                              | optional `name` substring filter |
| `list_processes` | —                                              | optional `name_contains` / `include_system` / `include_metrics` |
| `get_process`    | `pid`                                          | details for one running process |

**Launch rules:**
- If the user specifies the app AND a file, pass both:
  `{"action":"launch", "name":"<app>", "file":"<abs_path>"}`.
- If they just say "open this .pptx", pass `{"action":"launch", "file":"<abs_path>"}`
  and let the OS file-association choose.
- **Never double-launch.**  Before `launch`, check the current-turn
  `open_windows` snapshot — if a matching `process_name` is already
  present, call `system_window_control` with `action="activate"` instead.
"""


class SystemProcessControl(_SystemEngineTool):
    name = "system_process_control"
    router_hint = (
        "Launch apps / open files / inspect installed software and running "
        "processes.  Discriminate on `action` (launch / find_exe / "
        "list_installed / list_processes / get_process)."
    )
    router_detail = _PROCESS_CONTROL_ROUTER_DETAIL
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "launch",
                    "find_exe",
                    "list_installed",
                    "list_processes",
                    "get_process",
                ],
                "description": "Operation to perform. See router_detail for per-action args.",
            },
            # --- launch / find_exe / list_installed ---
            "name": {
                "type": "string",
                "description": (
                    "Display name from `installed_apps` (e.g. \"PowerPoint\").  "
                    "Required by action=find_exe; primary arg for action=launch "
                    "when you're launching an app (vs. a file)."
                ),
            },
            "file": {
                "type": "string",
                "description": (
                    "action=launch only.  Absolute path to a file to open "
                    "(OS file-association chooses the app unless `name`/`exe_path` "
                    "is also given)."
                ),
            },
            "exe_path": {
                "type": "string",
                "description": (
                    "action=launch only.  Absolute path to a specific exe to run "
                    "(overrides `name` lookup)."
                ),
            },
            "args": {
                "type": "array",
                "items": {"type": "string"},
                "description": "action=launch only.  Command-line args to pass to the exe.",
            },
            "cwd": {
                "type": "string",
                "description": "action=launch only.  Working directory for the launched process.",
            },
            # --- list_processes filters ---
            "name_contains": {
                "type": "string",
                "description": "action=list_processes only.  Case-insensitive process-name substring filter.",
            },
            "include_system": {
                "type": "boolean",
                "description": "action=list_processes only.  Include system processes.  Default false.",
            },
            "include_metrics": {
                "type": "boolean",
                "description": "action=list_processes only.  Include CPU / memory metrics per entry.  Default false.",
            },
            # --- get_process ---
            "pid": {
                "type": "integer",
                "description": "action=get_process only.  Process id to look up.",
            },
        },
        "required": ["action"],
        "additionalProperties": False,
    }


TOOLS = [SystemWindowControl(), SystemProcessControl()]
