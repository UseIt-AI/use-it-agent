"""
Capability Catalog

Converts frontend-provided app action schemas and workflow metadata
into OpenAI-format function/tool definitions that the orchestrator
LLM can call via ``call_with_tools``.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, List, Tuple

APP_ACTION_PREFIX = "app__"
WORKFLOW_RUN_TOOL = "workflow__run"
RESPOND_TOOL = "respond_to_user"
ASK_USER_TOOL = "ask_user"
"""Builtin tool that suspends the orchestrator and asks the user a
question via the frontend.  Response comes back on the same
``execution_result`` callback endpoint — see
:meth:`AgentLoop._handle_user_response_callback`."""

PLAN_WRITE_TOOL = "plan_write"
"""Builtin tool that lets the planner LLM write/replace the orchestrator's
task-level todo list.  Inline (no frontend round-trip): the new plan is
persisted onto :class:`OrchestratorContext.plan` and rendered back into
the planner's prompt on the next turn.  Inspired by Claude Code's
``TodoWrite`` and Cursor's plan-mode update mechanism."""

# Limit per-action parameter schema depth to keep token usage sane
_MAX_SCHEMA_STR_LEN = 3000

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Legacy tool aliases
# ---------------------------------------------------------------------------
#
# Frontend consolidated ``activate_window`` + ``launch_app`` into
# ``window_control`` + ``process_control`` (each now dispatches on an
# ``action`` field).  The new tool definitions are the only ones exposed to
# the planner going forward, but persisted conversation history can still
# contain the legacy names — when those messages are replayed the LLM tends
# to mimic them.  If we let those calls through verbatim they'd fall into the
# "unknown tool" branch and return ``(Unknown tool: …)`` to the user.
#
# Each alias entry maps ``old_full_name -> (new_full_name, arg_transform)``.
# ``arg_transform`` receives the original arg dict and must return the new
# one.  We put the synthesised ``action`` *before* ``**args`` so the LLM's
# own args win if for some reason it already supplied one.

_LEGACY_TOOL_ALIASES: Dict[
    str, Tuple[str, Callable[[Dict[str, Any]], Dict[str, Any]]]
] = {
    f"{APP_ACTION_PREFIX}activate_window": (
        f"{APP_ACTION_PREFIX}window_control",
        lambda args: {"action": "activate", **(args or {})},
    ),
    f"{APP_ACTION_PREFIX}launch_app": (
        f"{APP_ACTION_PREFIX}process_control",
        lambda args: {"action": "launch", **(args or {})},
    ),
}


# ---------------------------------------------------------------------------
# Backend-owned system tools
# ---------------------------------------------------------------------------
#
# These tools live in ``node_handler/agent_node/tools/system/`` so the
# AgentNode Router Planner sees them natively as ``system_*``.  The chat
# orchestrator re-exposes them under the ``app__`` prefix (so the existing
# frontend app-action handler keeps routing them to local-engine) but the
# schema comes from one canonical source — this module just adapts.
#
# The mapping below is (backend_tool_name -> orchestrator_tool_shortname).
# The orchestrator name gets ``APP_ACTION_PREFIX`` prepended.
_BACKEND_SYSTEM_TOOL_MAP: Dict[str, str] = {
    "system_window_control": "window_control",
    "system_process_control": "process_control",
}

# When the frontend still ships an app action with these names, we skip its
# copy in favour of the backend-authored schema (which is guaranteed
# complete, unlike the frontend's zod→JSONSchema output).
_REPLACED_BY_BACKEND_TOOL_NAMES: Tuple[str, ...] = tuple(
    _BACKEND_SYSTEM_TOOL_MAP.values()
)


def _build_backend_system_tools() -> List[Dict[str, Any]]:
    """Pull canonical system-tool schemas from the AgentNode tool registry
    and adapt them into OpenAI-format function defs for the chat
    orchestrator LLM.

    Returns
    -------
    list of ``{"type": "function", "function": {...}}`` entries.  Empty
    list if the registry cannot be imported for any reason — we degrade
    gracefully so the chat orchestrator still boots even if the agent
    node package has an import error.
    """
    try:
        # Imported lazily to avoid pulling the whole AgentNode tree at
        # module-import time (it eagerly discovers every pack on import).
        from useit_studio.ai_run.node_handler.agent_node.tools import (  # noqa: WPS433
            TOOL_BY_NAME,
        )
    except Exception as e:  # noqa: BLE001  — import-time failures are rare but non-fatal here.
        _logger.warning(
            "[capability_catalog] could not import AgentNode tool registry "
            "for backend system tools: %s", e,
        )
        return []

    out: List[Dict[str, Any]] = []
    for backend_name, short_name in _BACKEND_SYSTEM_TOOL_MAP.items():
        tool = TOOL_BY_NAME.get(backend_name)
        if tool is None:
            _logger.warning(
                "[capability_catalog] backend system tool %r not found "
                "in TOOL_BY_NAME; skipping.", backend_name,
            )
            continue

        schema = getattr(tool, "input_schema", None) or {"type": "object", "properties": {}}
        normalized = _normalize_schema(_ensure_object_schema(dict(schema)))

        description = getattr(tool, "router_hint", "") or ""
        detail = getattr(tool, "router_detail", "") or ""
        if detail:
            description = f"{description}\n\n{detail}" if description else detail

        out.append({
            "type": "function",
            "function": {
                "name": f"{APP_ACTION_PREFIX}{short_name}",
                "description": description,
                "parameters": normalized,
            },
        })
    return out


def rewrite_legacy_tool_call(
    tool_name: str,
    tool_args: Dict[str, Any],
) -> Tuple[str, Dict[str, Any]]:
    """Rewrite a legacy tool call into its consolidated equivalent.

    Returns ``(tool_name, tool_args)`` unchanged if no alias applies.
    """
    alias = _LEGACY_TOOL_ALIASES.get(tool_name)
    if alias is None:
        return tool_name, tool_args
    new_name, transform = alias
    try:
        new_args = transform(tool_args)
    except Exception:  # pragma: no cover — defensive
        new_args = dict(tool_args or {})
    _logger.info(
        "[capability_catalog] rewrote legacy tool call %s -> %s (action=%s)",
        tool_name, new_name, new_args.get("action"),
    )
    return new_name, new_args


def build_tool_definitions(
    app_capabilities: List[Dict[str, Any]],
    workflow_capabilities: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Build the unified tool list that the orchestrator LLM sees.

    Parameters
    ----------
    app_capabilities : list
        From frontend ``getActionSchemas()`` — each item has
        ``name``, ``description``, ``parameters`` (JSON Schema object).
    workflow_capabilities : list
        From frontend — each item has ``workflow_id``, ``name``,
        and optionally ``description``.

    Returns
    -------
    list of OpenAI-format tool dicts (``{"type": "function", "function": {...}}``).
    """
    tools: List[Dict[str, Any]] = []

    # --- Backend-owned system tools (desktop OS automation) ---
    #
    # ``system_window_control`` / ``system_process_control`` live in
    # :mod:`useit_ai_run.node_handler.agent_node.tools.system` so the
    # AgentNode Router Planner can also invoke them.  We surface them to
    # the chat orchestrator as ``app__window_control`` / ``app__process_control``
    # — the ``app__`` prefix keeps the frontend's existing app-action
    # dispatcher (``systemActions.ts`` → local-engine) wired up without any
    # frontend changes.
    #
    # Backend-authored schemas take precedence over anything the frontend
    # ships for these names (the old frontend zod→JSONSchema path was
    # dropping ``items.properties`` on nested arrays — see
    # ``_REPLACED_BY_BACKEND_TOOL_NAMES`` for the set we pre-empt).
    backend_system_tools = _build_backend_system_tools()
    tools.extend(backend_system_tools)

    replaced_app_names = _REPLACED_BY_BACKEND_TOOL_NAMES

    # --- App actions as individual tools ---
    for action in app_capabilities:
        name = action.get("name", "")
        if not name:
            continue

        if name in replaced_app_names:
            # Backend already authored a canonical schema for this tool —
            # skip the frontend copy to avoid duplicate registrations /
            # schema drift.
            _logger.debug(
                "[capability_catalog] skipping frontend-sent app action %r "
                "because backend system pack owns its schema.",
                name,
            )
            continue

        params = action.get("parameters") or {"type": "object", "properties": {}}
        # Guard against excessively large schemas that would waste tokens
        if len(json.dumps(params)) > _MAX_SCHEMA_STR_LEN:
            params = _simplify_schema(params)

        normalized = _normalize_schema(_ensure_object_schema(params))
        _warn_on_missing_array_items_before_normalize(name, params, normalized)

        tools.append({
            "type": "function",
            "function": {
                "name": f"{APP_ACTION_PREFIX}{name}",
                "description": action.get("description", ""),
                "parameters": normalized,
            },
        })

    # --- Workflow run as a single meta-tool ---
    if workflow_capabilities:
        workflow_enum = [w.get("workflow_id", "") for w in workflow_capabilities if w.get("workflow_id")]
        name_map_lines = [
            f"- {w.get('workflow_id', '???')}: {w.get('name', 'Unnamed')}"
            + (f" — {w['description']}" if w.get("description") else "")
            for w in workflow_capabilities
        ]
        name_map_str = "\n".join(name_map_lines)

        tools.append({
            "type": "function",
            "function": {
                "name": WORKFLOW_RUN_TOOL,
                "description": (
                    "Run an existing automation workflow. "
                    "Choose the workflow_id from the list below:\n"
                    f"{name_map_str}"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "workflow_id": {
                            "type": "string",
                            "description": "ID of the workflow to execute",
                            **({"enum": workflow_enum} if len(workflow_enum) <= 30 else {}),
                        },
                    },
                    "required": ["workflow_id"],
                },
            },
        })

    # --- Ask user (interactive confirmation / clarification) ---
    #
    # Suspends orchestration and renders a dialog on the frontend.  The
    # user's answer comes back as ``execution_result.user_response`` on the
    # same callback endpoint that app actions use (see
    # ``AgentLoop._handle_user_response_callback``).  This is a pause, not
    # a termination — after the user answers, planning resumes with the
    # answer folded into conversation history.
    tools.append({
        "type": "function",
        "function": {
            "name": ASK_USER_TOOL,
            "description": (
                "Pause and ask the user one question.  Use this WHENEVER "
                "any of these are true — do NOT try to guess past them:\n"
                "\n"
                "A. **User explicitly asked you to confirm / ask / "
                "verify** ('和我确认', 'ask me first', 'check with me', "
                "'which one do you mean').  Honour the request verbatim "
                "— do NOT proceed and tell the user afterwards.\n"
                "B. **Target is ambiguous** and you cannot uniquely "
                "pick one from the user's text.  Includes: lookup "
                "returned no match or multiple candidates "
                "(``No X found matching 'foo'. Available: a, b, c, …``); "
                "user referred to 'the file / that window / 那个 文档' "
                "and the snapshot shows several matches; user said "
                "'open PPT' with multiple matching apps installed "
                "(PowerPoint + WPS); user's pre-selected workflow "
                "conflicts with their chat message.  Show 3-6 closest "
                "candidates as options — do NOT guess with a new name.\n"
                "B1. **Workflow switch** is a mandatory `ask_user` case: "
                "if you want `workflow__run` with an id different from "
                "the currently selected one, you MUST `ask_user` first, "
                "THEN call `app__switchWorkflow` so the UI updates, THEN "
                "`workflow__run`.  The backend rejects a silent switch.\n"
                "C. **Destructive / irreversible / scope-creep / "
                "expensive** actions — delete, overwrite, mass-edit, "
                "close unsaved windows; actions whose scope is clearly "
                "larger than the user implied (batch / multi-doc when "
                "they named one item); long-running or costly "
                "workflows.  Confirm before executing.\n"
                "D. **Validation tool surfaced a branching decision** "
                "(e.g. `ppt_verify_layout` found overlap — ask "
                "'auto-fix / skip / abort').\n"
                "\n"
                "Do NOT use for chit-chat or progress updates — use "
                "`respond_to_user` for those.  Do NOT re-ask after the "
                "user dismisses.  One outstanding `ask_user` at a time.\n"
                "\n"
                "The UI blocks until the user answers, then you resume "
                "with their reply visible as a tool result.  Keep the "
                "prompt short (one specific question) and list 2-6 "
                "clear options.  When presenting lookup / ambiguity "
                "candidates, use option `id` = the candidate's id/handle "
                "so you can act on the reply immediately."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": (
                            "The question to show the user.  Keep it short "
                            "and specific — one question, plain language."
                        ),
                    },
                    "kind": {
                        "type": "string",
                        "enum": ["confirm", "choose", "input"],
                        "description": (
                            "`confirm` for yes/no or 2-3 discrete options; "
                            "`choose` for picking one from >=3 options; "
                            "`input` when you need free-form text.  Each "
                            "`kind` implies the UI widget the frontend "
                            "renders."
                        ),
                    },
                    "options": {
                        "type": "array",
                        "description": (
                            "Button / radio choices.  Required for "
                            "`confirm` and `choose`; optional for `input` "
                            "(supplies quick-pick suggestions)."
                        ),
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {
                                    "type": "string",
                                    "description": (
                                        "Stable option identifier echoed "
                                        "back in the response."
                                    ),
                                },
                                "label": {
                                    "type": "string",
                                    "description": (
                                        "Human-readable button/option "
                                        "label."
                                    ),
                                },
                            },
                            "required": ["id", "label"],
                        },
                    },
                    "default_option_id": {
                        "type": "string",
                        "description": (
                            "Option id selected by default (keyboard "
                            "Enter).  Must match one `options[*].id`."
                        ),
                    },
                    "allow_free_text": {
                        "type": "boolean",
                        "description": (
                            "If true, the UI also shows a text input next "
                            "to the options (useful for 'other, please "
                            "specify' patterns).  Defaults to false; "
                            "automatically true when `kind=input`."
                        ),
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "minimum": 0,
                        "description": (
                            "If > 0, the UI auto-dismisses after this many "
                            "seconds (returns `dismissed: true`).  0 = "
                            "wait indefinitely (default)."
                        ),
                    },
                },
                "required": ["prompt", "kind"],
            },
        },
    })

    # --- Plan write (task-level todo list scratchpad) ---
    #
    # This tool is inline: it does NOT cause a frontend round-trip and
    # does NOT suspend orchestration.  Calling it just rewrites
    # ``OrchestratorContext.plan`` and the orchestrator immediately
    # re-plans in the same SSE stream so the LLM can act on the next
    # item right away.  Full-replacement semantics (whole list at once)
    # mirror Claude Code's TodoWriteTool — partial updates would let
    # the model silently drop items.
    tools.append(_build_plan_write_tool())

    # --- Respond directly to user (text reply, no tool execution) ---
    tools.append({
        "type": "function",
        "function": {
            "name": RESPOND_TOOL,
            "description": (
                "Send a text response to the user. Use this when the request "
                "can be answered directly without calling any app action or "
                "workflow, OR after finishing all actions to provide a summary."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "The message to show the user",
                    },
                },
                "required": ["message"],
            },
        },
    })

    _log_tool_schemas(tools)
    return tools


# ---------------------------------------------------------------------------
# plan_write — task-level todo scratchpad (inline, no callback)
# ---------------------------------------------------------------------------

# Allowed values for ``status``.  Mirrors :data:`action_models.PLAN_ITEM_STATUSES`
# but duplicated here so this module has no import-time dependency on the
# rest of the agent_loop package — capability_catalog is loaded very
# early and used by tests in isolation.
_PLAN_STATUS_ENUM: Tuple[str, ...] = (
    "pending",
    "in_progress",
    "completed",
    "cancelled",
)


def _build_plan_write_tool() -> Dict[str, Any]:
    """OpenAI-format function definition for ``plan_write``.

    The description is intentionally *long* and example-heavy.  Empirically
    (Claude Code published their TodoWriteTool prompt at ~180 lines, Cursor
    ships a similar volume for their plan tool) terse descriptions cause
    the LLM to either (a) never use the tool at all, or (b) overuse it on
    trivial single-step requests.  The bulk of this prose is rules that
    pin those failure modes.
    """
    description = (
        "Maintain a task-level **todo list** for this user request.  Call "
        "this BEFORE you start working on a multi-step task, and call it "
        "AGAIN every time you start / finish an item so the list stays in "
        "sync with reality.  This is your private scratchpad — it is NOT "
        "shown to the user as a chat message; the orchestrator just renders "
        "it back into your next prompt.\n"
        "\n"
        "## When to use\n"
        "1. The user's request needs **3 or more distinct steps** to "
        "complete.\n"
        "2. The user explicitly asks for a plan / breakdown / checklist.\n"
        "3. The request spans **multiple applications** (e.g. read from "
        "Excel + draft in Word + send via browser).\n"
        "4. After receiving new instructions mid-task: **re-plan** by "
        "calling `plan_write` with an updated list.\n"
        "5. As the **first** call after you've understood a complex "
        "request — before any app/workflow action.\n"
        "\n"
        "## When NOT to use\n"
        "- Single trivial action (one app__ call, then respond).\n"
        "- Pure conversational reply.\n"
        "- The user has a workflow pre-selected AND the request maps "
        "cleanly to running it — call `workflow__run` instead.\n"
        "\n"
        "## Hard rules\n"
        "- **Full replacement**: every call replaces the whole list.  "
        "Always include items that are still pending, not just the new "
        "ones — anything you omit is gone.\n"
        "- **Exactly one `in_progress` at a time.**  Mark an item "
        "`in_progress` BEFORE you call the action that works on it.  "
        "Mark it `completed` IMMEDIATELY after the action succeeds — "
        "do NOT batch completions at the end.\n"
        "- **Don't fake completion.**  An item is `completed` only when "
        "fully done.  If an action failed or only partially succeeded, "
        "keep the item `in_progress` (or split it into a smaller item "
        "and add the remainder back as `pending`).\n"
        "- **Use `cancelled` instead of deleting** items the user no "
        "longer wants — keeps an audit trail.\n"
        "\n"
        "## Field guide for each todo\n"
        "- `id`: stable string id you assign (e.g. `step-1`, `open-ppt`); "
        "reused across plan revisions so `depends_on` references survive.\n"
        "- `content`: imperative form, what to do — e.g. \"Open the user's "
        "PowerPoint deck\".\n"
        "- `active_form` (optional): present-continuous form for UI — "
        "e.g. \"Opening the user's PowerPoint deck\".\n"
        "- `status`: one of `pending` / `in_progress` / `completed` / "
        "`cancelled`.\n"
        "- `suggested_node_type` (optional): the workflow node category "
        "you'd map this to if it had to run as a graph.  Pick one of: "
        "`computer-use-gui`, `computer-use-excel`, `computer-use-word`, "
        "`computer-use-ppt`, `computer-use-autocad`, `agent`, `tools`, "
        "`llm`, `web-search`, `mcp`.  Used by future `plan_to_workflow` "
        "synthesis — not required to act on the item now.\n"
        "- `suggested_tool` (optional): the most likely concrete tool "
        "name (e.g. `app__window_control`, `ppt_slide`).  Same purpose "
        "as above — a hint, not a commitment.\n"
        "- `depends_on` (optional): ids of items that must finish first.  "
        "Empty ⇒ depends on whatever item precedes it textually.\n"
        "- `notes` (optional): scratch space for details you want to "
        "remember across turns (e.g. \"user wants 4:3 not 16:9\").  "
        "Keep imperative steps in `content`, decisions/details in "
        "`notes`."
    )

    todo_item_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "id": {
                "type": "string",
                "description": (
                    "Stable identifier for this item.  Reuse the same id "
                    "across plan revisions so dependencies survive."
                ),
            },
            "content": {
                "type": "string",
                "description": (
                    "Imperative form — what to do, e.g. \"Open the user's "
                    "deck and add a title slide\"."
                ),
            },
            "active_form": {
                "type": "string",
                "description": (
                    "Present-continuous form shown while in_progress — "
                    "e.g. \"Opening the user's deck and adding a title "
                    "slide\".  Optional."
                ),
            },
            "status": {
                "type": "string",
                "enum": list(_PLAN_STATUS_ENUM),
                "description": (
                    "Current item status.  At most ONE item may be "
                    "`in_progress` per call."
                ),
            },
            "suggested_node_type": {
                "type": "string",
                "description": (
                    "Workflow node category this item would map to if "
                    "run as a graph.  See description for the allowed "
                    "values.  Optional hint for future plan_to_workflow "
                    "synthesis."
                ),
            },
            "suggested_tool": {
                "type": "string",
                "description": (
                    "Most-likely concrete tool name (e.g. "
                    "`app__window_control`, `ppt_slide`).  Optional hint."
                ),
            },
            "depends_on": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Ids of items that must complete before this one.  "
                    "Empty ⇒ depends on whatever precedes textually."
                ),
            },
            "notes": {
                "type": "string",
                "description": (
                    "Free-form scratch (decisions, user preferences, "
                    "constraints) you want to remember across turns."
                ),
            },
        },
        "required": ["id", "content", "status"],
    }

    return {
        "type": "function",
        "function": {
            "name": PLAN_WRITE_TOOL,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {
                    "todos": {
                        "type": "array",
                        "description": (
                            "The COMPLETE updated todo list.  Including an "
                            "item retains it; omitting it deletes it.  "
                            "Order is preserved as the planner's intended "
                            "sequence."
                        ),
                        "items": todo_item_schema,
                    },
                },
                "required": ["todos"],
            },
        },
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_tool_call(tool_name: str, tool_args: Dict[str, Any]):
    """
    Parse a tool call from the LLM into the appropriate action type.

    Returns a tuple ``(action_type, payload)`` where *action_type* is one of
    ``"app_action"``, ``"workflow_action"``, ``"respond"``.

    Legacy tool names (see ``_LEGACY_TOOL_ALIASES``) are transparently
    rewritten first, so persisted history that still references the old
    names keeps working end-to-end.
    """
    tool_name, tool_args = rewrite_legacy_tool_call(tool_name, tool_args)

    if tool_name.startswith(APP_ACTION_PREFIX):
        real_name = tool_name[len(APP_ACTION_PREFIX):]
        return "app_action", {"name": real_name, "args": tool_args}

    if tool_name == WORKFLOW_RUN_TOOL:
        return "workflow_action", {
            "workflow_id": tool_args.get("workflow_id", ""),
        }

    if tool_name == ASK_USER_TOOL:
        return "ask_user", _normalize_ask_user_args(tool_args)

    if tool_name == PLAN_WRITE_TOOL:
        return "plan", _normalize_plan_args(tool_args)

    if tool_name == RESPOND_TOOL:
        return "respond", {"message": tool_args.get("message", "")}

    # Unknown tool — treat as text response with a warning
    return "respond", {"message": f"(Unknown tool: {tool_name})"}


def _normalize_plan_args(args: Dict[str, Any]) -> Dict[str, Any]:
    """Coerce LLM-produced ``plan_write`` args into a uniform shape.

    The LLM occasionally emits the list directly under a different key
    (``items``, ``plan``, ``tasks``) instead of ``todos``, or wraps the
    list in an extra dict.  We accept any of those before downstream
    code (``OrchestratorContext.update_plan``) sees the payload, so
    history replays from older runs keep working.

    The shape returned here is intentionally minimal — just
    ``{"todos": [<raw item dict>, ...]}`` — because
    :meth:`OrchestratorContext.update_plan` already does the per-item
    repair (status enum coercion, in_progress dedup, etc.) via
    :meth:`PlanItem.from_dict`.  Doing it twice would just hide drift.
    """
    raw = args or {}
    todos: Any = raw.get("todos")
    if todos is None:
        for alt in ("items", "plan", "tasks", "todo"):
            if alt in raw:
                todos = raw.get(alt)
                break
    if isinstance(todos, dict):
        # Sometimes the LLM nests one more level: ``{"todos": {"items":
        # [...]}}``.  Drill down into the first list-valued field.
        nested = todos.get("items") or todos.get("todos") or todos.get("list")
        todos = nested if isinstance(nested, list) else []
    if not isinstance(todos, list):
        todos = []
    cleaned: List[Dict[str, Any]] = []
    for entry in todos:
        if isinstance(entry, dict):
            cleaned.append(entry)
        elif isinstance(entry, str) and entry.strip():
            # Shorthand: bare string -> minimal pending item.  Loses ids /
            # dependencies but at least the user's plan isn't dropped.
            cleaned.append({
                "id": f"step-{len(cleaned) + 1}",
                "content": entry.strip(),
                "status": "pending",
            })
    return {"todos": cleaned}


def _normalize_ask_user_args(args: Dict[str, Any]) -> Dict[str, Any]:
    """Coerce LLM-produced ``ask_user`` args into a safe, uniform shape.

    The LLM sometimes emits ``kind="yes_no"`` or ``kind="confirmation"``
    (not in the enum), drops ``options`` entirely, or passes ``options``
    as ``["Yes", "No"]`` instead of the declared object shape.  We fix
    those cases up in one place so downstream code (``_emit_ask_user``,
    frontend renderer) can trust the payload.
    """
    kind_raw = str(args.get("kind") or "confirm").strip().lower()
    kind_aliases = {
        "yes_no": "confirm",
        "yesno": "confirm",
        "confirmation": "confirm",
        "confirm": "confirm",
        "choice": "choose",
        "select": "choose",
        "choose": "choose",
        "text": "input",
        "freetext": "input",
        "free_text": "input",
        "input": "input",
    }
    kind = kind_aliases.get(kind_raw, "confirm")

    prompt = str(args.get("prompt") or "").strip()

    raw_opts = args.get("options") or []
    opts: List[Dict[str, Any]] = []
    if isinstance(raw_opts, list):
        for i, opt in enumerate(raw_opts):
            if isinstance(opt, dict):
                oid = str(opt.get("id") or opt.get("value") or f"opt_{i}").strip()
                label = str(opt.get("label") or opt.get("text") or oid).strip()
            else:
                oid = f"opt_{i}"
                label = str(opt).strip() or oid
            if not oid:
                continue
            opts.append({"id": oid, "label": label})

    # Default options for a naked "confirm" with nothing specified.
    if kind == "confirm" and not opts:
        opts = [
            {"id": "yes", "label": "Yes"},
            {"id": "no", "label": "No"},
        ]

    default_id = args.get("default_option_id")
    if default_id is not None:
        default_id = str(default_id).strip() or None
    if default_id and not any(o["id"] == default_id for o in opts):
        default_id = None

    allow_free_text = bool(args.get("allow_free_text", False))
    if kind == "input":
        allow_free_text = True

    try:
        timeout = int(args.get("timeout_seconds") or 0)
    except (TypeError, ValueError):
        timeout = 0
    timeout = max(0, timeout)

    return {
        "prompt": prompt,
        "kind": kind,
        "options": opts,
        "default_option_id": default_id,
        "allow_free_text": allow_free_text,
        "timeout_seconds": timeout,
    }


def _ensure_object_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure the top-level schema type is ``object``."""
    if schema.get("type") != "object":
        return {"type": "object", "properties": {}}
    return schema


def _simplify_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Produce a simpler schema when the original is too large."""
    props = schema.get("properties", {})
    simplified = {}
    for key, val in props.items():
        simplified[key] = {
            "type": val.get("type", "string"),
            "description": val.get("description", ""),
        }
    return {
        "type": "object",
        "properties": simplified,
        "required": schema.get("required", []),
    }


# ---------------------------------------------------------------------------
# Schema normalisation (Gemini-strict)
# ---------------------------------------------------------------------------
#
# Gemini's function-calling validator is stricter than OpenAI's / Anthropic's:
# every ``{"type": "array"}`` subschema MUST specify ``items``.  Frontend
# schemas occasionally omit it (or declare ``array`` without describing the
# element type), which causes the whole ``generateContent`` call to 400 with
# e.g. ``properties[hwnds].items: missing field``.
#
# We defensively normalise every incoming schema before exposing it to the
# LLM so one sloppy declaration can't take down the Gemini code path.  The
# injected ``items`` default is ``{}`` (= "any"); this keeps the tool usable
# without making up a wrong type.  Frontends SHOULD still declare correct
# ``items`` themselves for better LLM guidance — this is purely a safety net.

# JSON-Schema subschema keys that carry another schema directly.
_NESTED_SCHEMA_KEYS = ("items", "additionalProperties", "contains")
# Subschema keys that carry a *list* of schemas.
_NESTED_SCHEMA_LIST_KEYS = ("anyOf", "oneOf", "allOf")

# Keys to drop from every subschema before handing it to the LLM adapters.
#
# Why each one:
#   * ``$schema`` / ``$id`` / ``$ref`` / ``$defs`` / ``$comment`` — JSON-Schema
#     meta-keys that no LLM provider understands; Gemini in particular rejects
#     them outright.
#   * ``exclusiveMinimum`` / ``exclusiveMaximum`` — in JSON Schema draft-7
#     these are *numbers* (e.g. ``exclusiveMinimum: 0``).  Some versions of
#     ``langchain-google-genai`` 's dict→proto converter don't whitelist
#     them and, worse, treating them as unknown in an ``items`` subschema
#     causes the entire ``items`` to be silently dropped when building the
#     Gemini ``Schema`` proto — which is precisely how we land with
#     ``properties[hwnds].items: missing field`` 400s.
#
# Stripping these is harmless for OpenAI / Claude (they don't rely on them
# for function-call schema validation), and it makes the Gemini path
# bullet-proof against zod v4-style output that's technically correct draft-7.
_STRIP_KEYS: Tuple[str, ...] = (
    "$schema",
    "$id",
    "$ref",
    "$defs",
    "$comment",
    "exclusiveMinimum",
    "exclusiveMaximum",
)


# Fallback ``items`` schema when the frontend forgets to declare one.
#
# MUST have a concrete ``type`` — ``langchain-google-genai`` 's dict→proto
# Schema converter treats ``items: {}`` (no type) as invalid and silently
# drops the whole ``items`` field, which is what gets us back to Gemini's
# ``items: missing field`` 400.
#
# When we have no *context* (e.g. an array nested inside ``anyOf`` with no
# field name to anchor on), ``string`` is the safest universal type: every
# provider accepts it.  When we DO have a property name to anchor on, we
# try a light name-based heuristic (see ``_guess_array_items_by_key``)
# because the frontend's zod validator on the other side often expects
# integers / numbers / objects — emitting the right type keeps its
# post-call validation from rejecting the tool result.
_FALLBACK_ARRAY_ITEMS: Dict[str, Any] = {"type": "string"}

# Field-name substrings that strongly suggest the elements are integers.
# Order doesn't matter — first-match wins.  Keep this list conservative;
# false positives turn an LLM-generated string into a caller-side schema
# mismatch, which is at least caught by the frontend's own validator.
_INT_ARRAY_NAME_HINTS: Tuple[str, ...] = (
    "hwnd", "pid", "handle", "index", "indice",
    "count", "num", "nth", "tick",
    # Office integer ranges: ``paragraph_range``, ``row_range``,
    # ``column_range``, ``slide_range`` — always 1-based [start, end]
    # closed intervals of integers.  Added for the Word ``/step`` migration
    # (scope=paragraph_range) and aligns with the Excel / PPT equivalents.
    "range",
    # ``id`` is too eagerly matched (e.g. ``gids``, ``widths`` would collide
    # with substring matching), so it's intentionally NOT here.  We match
    # ``id`` as a WHOLE WORD separately below.
)

_FLOAT_ARRAY_NAME_HINTS: Tuple[str, ...] = (
    "ratio", "weight", "percent", "scale", "opacity", "alpha", "fraction",
    "threshold", "confidence", "score", "prob",
)

# Rectangle-like fields ("zones", "rects", "bounds"…) consistently carry
# ``{x, y, width, height}`` numeric proportions/pixels across our tools
# (``window_control.tile``, screenshot crop helpers, …).  When the frontend
# forgets to declare the element schema, emitting just ``{type: object}`` is
# useless — the LLM will happily produce empty objects and the frontend's
# Zod validator will 400 with ``zones.0.x: expected number, received
# undefined``.  Declaring the real shape here keeps Gemini happy AND teaches
# the LLM the right keys.
_RECT_ARRAY_NAME_HINTS: Tuple[str, ...] = (
    "zone", "rect", "bound", "region", "box",
)
_RECT_ITEMS_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "x": {"type": "number"},
        "y": {"type": "number"},
        "width": {"type": "number"},
        "height": {"type": "number"},
    },
    "required": ["x", "y", "width", "height"],
}

_OBJECT_ARRAY_NAME_HINTS: Tuple[str, ...] = (
    "window", "node", "entry", "record", "step",
    "config", "setting", "param", "option",
    # Office structured-action payloads (Word ``/step`` Layer-1 actions,
    # future PPT/Excel equivalents): ``actions: [{action, target, ...}, ...]``.
    # Without this hint the fallback collapses to ``string`` and Gemini then
    # rejects any object the LLM tries to put in the list.
    "action",
)


def _guess_array_items_by_key(key: str) -> Dict[str, Any]:
    """Heuristic: infer array element type from the property name.

    This is only invoked when the caller's schema declared ``{type:
    "array"}`` with no usable ``items``.  A correct schema always wins —
    we never override a type that was explicitly declared.
    """
    if not key:
        return dict(_FALLBACK_ARRAY_ITEMS)
    k = key.lower()

    # ``id`` / ``ids`` as whole word (avoid matching ``widths`` etc.).
    if k in {"id", "ids", "uid", "uids", "gid", "gids"}:
        return {"type": "integer"}

    for tok in _INT_ARRAY_NAME_HINTS:
        if tok in k:
            return {"type": "integer"}
    for tok in _FLOAT_ARRAY_NAME_HINTS:
        if tok in k:
            return {"type": "number"}
    # Rectangle-like arrays need the full element shape, not just ``type:
    # object`` — see ``_RECT_ITEMS_SCHEMA`` for rationale.
    for tok in _RECT_ARRAY_NAME_HINTS:
        if tok in k:
            # Deep-copy so callers that mutate the returned dict (and the
            # recursive walker in ``_normalize_schema``) don't poison the
            # template for subsequent tools.
            return {
                "type": "object",
                "properties": {
                    name: dict(spec)
                    for name, spec in _RECT_ITEMS_SCHEMA["properties"].items()
                },
                "required": list(_RECT_ITEMS_SCHEMA["required"]),
            }
    for tok in _OBJECT_ARRAY_NAME_HINTS:
        if tok in k:
            return {"type": "object"}
    return dict(_FALLBACK_ARRAY_ITEMS)


def _normalize_schema(schema: Any) -> Any:
    """Recursively normalise a JSON-Schema fragment for LLM adapter safety.

    - Ensures every ``{"type": "array"}`` subschema has a concrete
      ``items`` field (defaults to ``_FALLBACK_ARRAY_ITEMS`` — see there for
      why we can't use ``{}``).
    - Strips meta / draft-7-only keys listed in ``_STRIP_KEYS`` that are
      known to confuse downstream LangChain converters.
    - Recurses through ``properties``, ``items``, ``anyOf``, ``oneOf``,
      ``allOf``, ``additionalProperties``, ``contains``.

    Non-dict values are returned unchanged, so this is safe to call on
    anything parsed from JSON.
    """
    if not isinstance(schema, dict):
        return schema

    out: Dict[str, Any] = {k: v for k, v in schema.items() if k not in _STRIP_KEYS}

    # Fix array-missing-items at this level (AFTER strip so we don't
    # re-introduce it by accident).
    if out.get("type") == "array":
        items = out.get("items")
        # Treat both missing items AND ``items: {}`` as invalid: the empty
        # dict is still a no-schema schema that downstream converters
        # (notably ``langchain-google-genai``) drop entirely, leaving
        # Gemini to 400 with ``items: missing field``.
        if not isinstance(items, dict) or not items:
            out["items"] = dict(_FALLBACK_ARRAY_ITEMS)

    # Recurse into properties.  When a property is an array whose ``items``
    # we just replaced with the generic ``string`` fallback, use the
    # property name to upgrade the guess — the frontend's own zod validator
    # typically expects something more specific than ``string`` (e.g.
    # ``hwnds`` wants ``integer``) and will otherwise reject the LLM's
    # tool_call.
    props = out.get("properties")
    if isinstance(props, dict):
        new_props: Dict[str, Any] = {}
        for k, v in props.items():
            nv = _normalize_schema(v)
            if (
                isinstance(nv, dict)
                and nv.get("type") == "array"
                and nv.get("items") == _FALLBACK_ARRAY_ITEMS
            ):
                nv = dict(nv)
                nv["items"] = _guess_array_items_by_key(k)
            new_props[k] = nv
        out["properties"] = new_props

    # Recurse into single-schema children (items / additionalProperties /
    # contains).  ``additionalProperties`` can also be a bool — leave that.
    for key in _NESTED_SCHEMA_KEYS:
        child = out.get(key)
        if isinstance(child, dict):
            out[key] = _normalize_schema(child)

    # Recurse into list-of-schema children (anyOf / oneOf / allOf).
    for key in _NESTED_SCHEMA_LIST_KEYS:
        lst = out.get(key)
        if isinstance(lst, list):
            out[key] = [_normalize_schema(item) for item in lst]

    return out


def _collect_arrays_missing_items(schema: Any, path: str = "") -> List[str]:
    """Walk ``schema`` and return JSON-pointer-ish paths where an array is
    declared without ``items``.  Used for diagnostic logging.
    """
    found: List[str] = []
    if not isinstance(schema, dict):
        return found
    if schema.get("type") == "array" and "items" not in schema:
        found.append(path or "<root>")

    props = schema.get("properties")
    if isinstance(props, dict):
        for k, v in props.items():
            found.extend(_collect_arrays_missing_items(v, f"{path}.properties[{k}]"))

    for key in _NESTED_SCHEMA_KEYS:
        child = schema.get(key)
        if isinstance(child, dict):
            found.extend(_collect_arrays_missing_items(child, f"{path}.{key}"))

    for key in _NESTED_SCHEMA_LIST_KEYS:
        lst = schema.get(key)
        if isinstance(lst, list):
            for i, item in enumerate(lst):
                found.extend(_collect_arrays_missing_items(item, f"{path}.{key}[{i}]"))

    return found


_ALREADY_WARNED_TOOLS: set = set()


def _warn_on_missing_array_items_before_normalize(
    tool_name: str, raw_params: Dict[str, Any], normalized: Dict[str, Any],
) -> None:
    """If the frontend-sent schema for ``tool_name`` had arrays without
    ``items``, emit a WARN log so we can catch frontend regressions early.

    (The missing ``items`` will still be auto-patched by ``_normalize_schema``
    so the LLM call continues to work — this is purely for visibility.)

    To help the frontend team debug *why* their zod output lost ``items``,
    we dump the full raw schema ONCE per tool per process so it shows up
    in logs without flooding every request.  We also log which element
    type we guessed for each offending field so callers can audit the
    heuristic at a glance.
    """
    paths = _collect_arrays_missing_items(raw_params)
    if not paths:
        return

    # Show what we ended up putting in items for each top-level property.
    guesses: List[str] = []
    norm_props = normalized.get("properties", {}) if isinstance(normalized, dict) else {}
    for p in paths:
        # ``p`` looks like ``.properties[hwnds]`` or deeper; extract the
        # last ``properties[<key>]`` component as a display hint.
        key: str = ""
        marker = ".properties["
        if marker in p:
            key = p.rsplit(marker, 1)[1].rstrip("]")
        guessed_type = "?"
        if key and isinstance(norm_props.get(key), dict):
            items = norm_props[key].get("items") or {}
            guessed_type = items.get("type", "?")
        guesses.append(f"{p}→items.type={guessed_type}")

    _logger.warning(
        "[capability_catalog] tool %r sent arrays without `items`: %s — "
        "auto-patched so the LLM call still works; frontend schema should "
        "declare the element type explicitly.",
        tool_name, guesses,
    )
    if tool_name not in _ALREADY_WARNED_TOOLS:
        _ALREADY_WARNED_TOOLS.add(tool_name)
        try:
            raw_json = json.dumps(raw_params, ensure_ascii=False)
        except (TypeError, ValueError):
            raw_json = repr(raw_params)
        _logger.warning(
            "[capability_catalog] first-time dump of %r raw parameters "
            "(please share with frontend team): %s",
            tool_name, raw_json,
        )


def _log_tool_schemas(tools: List[Dict[str, Any]]) -> None:
    """Debug-level dump of every tool schema actually handed to the LLM.

    Useful when debugging provider-side schema errors (e.g. Gemini's
    ``properties[…].items: missing field``): turn on DEBUG logging for
    this module and grep for the tool name.
    """
    if not _logger.isEnabledFor(logging.DEBUG):
        return
    for i, tool in enumerate(tools):
        fn = tool.get("function", tool)
        name = fn.get("name", "?")
        try:
            params_json = json.dumps(fn.get("parameters", {}), ensure_ascii=False)
        except (TypeError, ValueError):
            params_json = repr(fn.get("parameters"))
        _logger.debug(
            "[capability_catalog] tool[%d] %s parameters=%s",
            i, name, params_json,
        )
