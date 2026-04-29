"""Word tools —— Microsoft Word via Local Engine（/step + /snapshot 协议）。"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, List, TYPE_CHECKING

from ..protocol import EngineTool, ToolCall

if TYPE_CHECKING:
    from ...models import (
        PlannerOutput,
    )


# ==========================================================================
# Router guidance — shared across all word_* tools
# ==========================================================================

_WORD_PIPELINE_DETAIL = r"""Microsoft Word Local Engine — `/api/v1/word/step` + `/api/v1/word/snapshot`.

Both endpoints share a **snapshot-scope** vocabulary and never steal focus
(screenshots are captured via `capture_hwnd_image`).  Word documents can be
hundreds of pages, so default to the *smallest* scope that answers your
current question and only widen when you need to.

### Three-mode `/step` dispatcher

Exactly one payload shape per call — mixing them is a 400 error:

| Mode | When to use | Required fields |
|------|-------------|-----------------|
| **skill** (preferred / Layer 2) | A vetted script matches the task (see `skill_manifest`).  Running a pre-approved script beats regenerating PowerShell from scratch. | `skill_id`, `script_path` (relative to the skill root), `parameters` object; `language` optional. |
| **code** (fallback / Layer 3) | Complex / exploratory / one-off operations where no skill fits. | `code`; `language` optional (`"PowerShell"` default, `"Python"` allowed). |
| **actions** (Layer 1) | Structured batch of primitive actions (`apply_style`, `insert_text`, …). | `actions: [...]` |

**IMPORTANT — `actions` mode is NOT implemented yet.**  The backend returns
`execution.success=false, execution.not_implemented=true` for any `actions`
payload.  Do NOT emit structured actions until a capability update says
otherwise — stick to **skill** (`word_execute_script`) or **code**
(`word_execute_code`).

### `snapshot_scope` vocabulary

| Scope | Typical payload | When to pick it |
|-------|-----------------|-----------------|
| `outline_only` | a few KB | First touch on an unfamiliar / long document — read the heading tree before anything else. |
| `paragraph_range` | narrow | Inspect or edit a specific slice.  Derive `[start, end]` (1-based, closed) from `paragraph_index` values in the outline. |
| `current_page` | 10–30 KB | **Default.**  Use to verify an edit landed. |
| `current_section` | scales with section | When the user's intent clearly scopes to "this section". |
| `selection` | small | Operating on `app.Selection`.  Empty selection silently falls back to `current_page`. |
| `full` | potentially MB | Only when the user explicitly wants whole-document analysis; cap with `max_paragraphs`. |

Recommended flow for large docs:
`word_snapshot(outline_only)` → `word_snapshot(paragraph_range=[s,e])` for the
slice you care about → edit via `word_execute_script` / `word_execute_code` →
`word_snapshot(current_page)` to confirm.

Each outline entry carries `level`, `text`, `paragraph_index`, `range`, `style`
— use `paragraph_index` to build `paragraph_range` without guessing.

Compatibility note: the legacy `current_page_only` boolean still works
(`true` → `current_page`, `false` → `full`).  Prefer `snapshot_scope`.
"""


_WORD_EXECUTE_CODE_DETAIL = (
    _WORD_PIPELINE_DETAIL
    + r"""

### `word_execute_code` specifics

Router passes the code directly (no sub-LLM).  The code is dispatched to
`/word/step` in **code mode**; it runs inside a COM session already attached
to the active Word document.

Example:
```json
{"Action": "word_execute_code",
 "Description": "Bold every paragraph whose style is Heading 1.",
 "Params": {
   "code": "$doc = $Word.ActiveDocument\nforeach ($p in $doc.Paragraphs) {\n  if ($p.Style.NameLocal -eq 'Heading 1') { $p.Range.Font.Bold = $true }\n}",
   "language": "PowerShell"
 }}
```

Prefer `word_execute_script` whenever a matching skill exists — running a
vetted script is safer and faster than regenerating code.
"""
)


_WORD_EXECUTE_SCRIPT_DETAIL = (
    _WORD_PIPELINE_DETAIL
    + r"""

### `word_execute_script` specifics

Dispatches to `/word/step` in **skill mode**.  Use when a matching entry
exists in the user's `skill_manifest`; Router supplies `skill_id`,
`script_path` (relative to the skill root) and the script's `parameters`
object.  Language defaults to PowerShell.

Example:
```json
{"Action": "word_execute_script",
 "Description": "Apply standard corporate heading styles via the governance skill.",
 "Params": {
   "skill_id": "corp_style_v1",
   "script_path": "scripts/apply_headings.ps1",
   "parameters": {"variant": "formal"}
 }}
```

If no skill fits the task, fall back to `word_execute_code`.
"""
)


_WORD_SNAPSHOT_DETAIL = (
    _WORD_PIPELINE_DETAIL
    + r"""

### `word_snapshot` specifics

Read-only; hits `/api/v1/word/snapshot`.  Use it to *look before you leap*
— especially on long documents where blindly dumping `full` would waste
tokens.  Supports the same `snapshot_scope` / `paragraph_range` /
`max_paragraphs` / `return_screenshot` knobs as `/step`, plus content-slice
toggles you only turn on when needed:

| Field | Purpose |
|-------|---------|
| `include_content` | Paragraph text. |
| `include_outline` | Heading tree with `paragraph_index` anchors. |
| `include_styles` | Style catalog used in the doc. |
| `include_bookmarks` | Bookmarks + locations. |
| `include_toc` | Table of contents (if present). |

Leave every include-* toggle off unless you specifically need that slice —
enabling everything defeats the whole point of the scope system.

Example — scope the outline of a large doc before editing:
```json
{"Action": "word_snapshot",
 "Description": "Get the heading tree so I can pick paragraphs to edit.",
 "Params": {"snapshot_scope": "outline_only", "include_outline": true}}
```
"""
)


# ==========================================================================
# Shared input-schema fragments
# ==========================================================================

_SCOPE_ENUM = [
    "outline_only",
    "paragraph_range",
    "current_page",
    "current_section",
    "selection",
    "full",
]


def _shared_scope_schema_props() -> Dict[str, Any]:
    """Knobs that both /step and /snapshot honour."""
    return {
        "snapshot_scope": {
            "type": "string",
            "enum": _SCOPE_ENUM,
            "default": "current_page",
            "description": (
                "Which slice of the document to capture in the response "
                "snapshot.  Default `current_page`."
            ),
        },
        "paragraph_range": {
            "type": "array",
            "items": {"type": "integer"},
            "minItems": 2,
            "maxItems": 2,
            "description": (
                "1-based closed interval `[start, end]`.  Only honoured "
                "when `snapshot_scope=\"paragraph_range\"`."
            ),
        },
        "max_paragraphs": {
            "type": "integer",
            "description": (
                "Hard cap on paragraph count; mainly used when "
                "`snapshot_scope=\"full\"` to bound cost."
            ),
        },
        "return_screenshot": {
            "type": "boolean",
            "default": True,
            "description": "Include a PNG screenshot of the visible page.",
        },
        "current_page_only": {
            "type": "boolean",
            "description": (
                "Deprecated — `true` → `current_page`, `false` → `full`.  "
                "Prefer `snapshot_scope`."
            ),
        },
    }


# ==========================================================================
# Tool classes
# ==========================================================================


class _WordEngineTool(EngineTool):
    group: ClassVar[str] = "word"
    target: ClassVar[str] = "word"


class WordExecuteCode(_WordEngineTool):
    """Layer-3 fallback: run PowerShell / Python COM code against Word."""

    name = "word_execute_code"
    router_hint = (
        "Run PowerShell/Python COM code against Word (fallback when no skill "
        "fits).  Params: code, language?, timeout?, snapshot_scope? …"
    )
    router_detail = _WORD_EXECUTE_CODE_DETAIL
    is_destructive = True
    input_schema = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Source code to execute inside Word's COM session.",
            },
            "language": {
                "type": "string",
                "enum": ["PowerShell", "Python"],
                "default": "PowerShell",
            },
            "timeout": {"type": "integer", "default": 120},
            **_shared_scope_schema_props(),
        },
        "required": ["code"],
    }

    def build_tool_call(
        self,
        params: Dict[str, Any],
        planner_output: "PlannerOutput",
    ) -> ToolCall:
        """Emit a flat `execute_code` tool_call (matches the frontend Word
        dispatcher, which routes on `name ∈ {execute_code, execute_script,
        stop}`).  Pass every scope knob through verbatim so the Local Engine
        can honour it in the returned snapshot."""
        args = {k: v for k, v in params.items() if v is not None}
        args.setdefault("language", "PowerShell")
        args.setdefault("timeout", 120)
        args.setdefault("return_screenshot", True)
        return ToolCall(name="execute_code", args=args)


class WordExecuteScript(_WordEngineTool):
    """Layer-2 preferred path: run a vetted skill script against Word."""

    name = "word_execute_script"
    router_hint = (
        "Run a pre-authored skill script (from `skill_manifest`) against Word. "
        "Prefer over `word_execute_code` whenever a matching skill exists.  "
        "Params: skill_id, script_path, parameters, language?, timeout?, "
        "snapshot_scope? …"
    )
    router_detail = _WORD_EXECUTE_SCRIPT_DETAIL
    # Most skills mutate the document; flagged destructive for UI surfacing.
    is_destructive = True
    input_schema = {
        "type": "object",
        "properties": {
            "skill_id": {
                "type": "string",
                "description": "Skill identifier from the `skill_manifest`.",
            },
            "script_path": {
                "type": "string",
                "description": (
                    "Path to the script *relative to the skill root* (e.g. "
                    "`scripts/apply_headings.ps1`)."
                ),
            },
            "parameters": {
                "type": "object",
                "description": "Script-specific kwargs.  Exact shape depends on the skill.",
            },
            "language": {
                "type": "string",
                "enum": ["PowerShell", "Python"],
                "default": "PowerShell",
            },
            "timeout": {"type": "integer", "default": 120},
            **_shared_scope_schema_props(),
        },
        "required": ["skill_id", "script_path"],
    }

    def build_tool_call(
        self,
        params: Dict[str, Any],
        planner_output: "PlannerOutput",
    ) -> ToolCall:
        args = {k: v for k, v in params.items() if v is not None}
        args.setdefault("parameters", {})
        args.setdefault("language", "PowerShell")
        args.setdefault("timeout", 120)
        args.setdefault("return_screenshot", True)
        return ToolCall(name="execute_script", args=args)


TOOLS: List[_WordEngineTool] = [
    WordExecuteScript(),   # Layer 2 — preferred
    WordExecuteCode(),     # Layer 3 — fallback
]
