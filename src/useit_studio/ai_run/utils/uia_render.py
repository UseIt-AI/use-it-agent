"""
Desktop snapshot formatter used by every planner that consumes ``uia_data``.

The frontend sends ``uia_data`` with pre-formatted ``open_windows`` and
``installed_apps`` strings, plus legacy ``windows`` / ``active_window``
fields.  Every planner that chooses ``system_*`` / ``app__*`` actions
(chat orchestrator, AgentNode Router, deprecated Office handlers) needs
this rendered into its user prompt so the LLM can:

- copy `hwnd` verbatim into window-control actions;
- avoid double-launch when the target app is already in `open_windows`;
- verify post-action state on the next turn.

Historically only the chat orchestrator rendered this; the AgentNode
Router was blind (see bug in task
``260424-021120_agent_tid_92553b7c-...``: PowerPoint was already
running at `hwnd=128585542` but the Router couldn't see it and
launched a second instance).  Centralising the logic here fixes that
and makes sure future planners stay in sync.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


# Per-key budgets for inlining into a prompt.  ``open_windows`` easily
# blows past 2 KB on busy desktops (20+ windows) and MUST be preserved
# verbatim — that's where hwnds live.  ``installed_apps`` is looser.
_PER_KEY_MAX: Dict[str, int] = {
    "open_windows": 8000,
    "installed_apps": 4000,
}
_DEFAULT_MAX: int = 2000


def _hint_for(key: str, app_action_prefix: str) -> Optional[str]:
    """Inline hint that tells the LLM the field is *directly* consumable.

    Without this the planner often sees `hwnd` in `open_windows` but
    won't "trust" numbers it didn't construct itself — the hint closes
    that loop.  Action names are passed in via ``app_action_prefix`` so
    the chat orchestrator (``app__window_control``) and the AgentNode
    Router (``system_window_control``) can each get their own wording.
    """
    if key == "open_windows":
        if app_action_prefix == "app__":
            tool_name = "`app__window_control`"
        else:
            tool_name = "`system_window_control`"
        return (
            "(Each line starts with `hwnd=<N> pid=<N> <process_name>`. "
            f"Pass that `hwnd` verbatim to {tool_name} "
            "(e.g. `action=\"activate\"` / `\"minimize\"` / "
            "`\"close\"` / `\"set_topmost\"` / `\"tile\"`) — do NOT "
            "invent hwnds.)"
        )
    if key == "installed_apps":
        if app_action_prefix == "app__":
            tool_name = "`app__process_control`"
        else:
            tool_name = "`system_process_control`"
        return (
            f"(Use any entry here as the `name` argument to {tool_name} "
            "with `action=\"launch\"`.)"
        )
    return None


def format_desktop_snapshot(
    uia_data: Optional[Dict[str, Any]],
    *,
    app_action_prefix: str = "system_",
    max_other_keys: int = 5,
    heading: str = "## Desktop Environment",
) -> str:
    """Render a ``uia_data`` payload into a markdown section.

    Parameters
    ----------
    uia_data:
        The raw dict from the frontend.  May be ``None`` / empty.
    app_action_prefix:
        ``"system_"`` for the AgentNode Router (tools named
        ``system_window_control`` / ``system_process_control``), or
        ``"app__"`` for the chat orchestrator (tools named
        ``app__window_control`` / ``app__process_control``).  Only
        affects inline hint wording.
    max_other_keys:
        Hard cap on how many non-standard keys beyond the known ones
        we inline, so a chatty snapshot can't blow up the prompt.
    heading:
        Top-level markdown heading for the block.  Pass ``""`` to skip
        the heading (e.g. when splicing into an existing section).

    Returns
    -------
    str
        The rendered markdown block (no trailing newline), or ``""``
        when nothing worth rendering is present.
    """
    if not uia_data:
        return ""

    parts: List[str] = []

    # --- 1. Legacy windows / active_window (UIA tree form) --------------
    windows = uia_data.get("windows") or []
    active = uia_data.get("active_window") or ""
    if windows or active:
        parts.append("### Desktop Windows")
        if active:
            parts.append(f"Active window: {active}")
        if windows:
            for w in windows[:20]:
                if isinstance(w, dict):
                    title = w.get("title", w.get("name", str(w)))
                    parts.append(f"- {title}")
                else:
                    parts.append(f"- {w}")

    # --- 2. Pre-formatted open_windows / installed_apps + any extras ----
    skip_keys = {
        "windows",
        "active_window",
        # Diagnostic / provenance markers the frontend stamps on — not
        # useful to the LLM.
        "_frontend_ts",
        "_frontend_build",
        "_keys_collected",
    }
    other_keys = [k for k in uia_data if k not in skip_keys]
    for k in other_keys[:max_other_keys]:
        val = uia_data[k]
        if isinstance(val, str):
            val_str = val
        else:
            try:
                val_str = json.dumps(val, ensure_ascii=False, default=str)
            except Exception:
                val_str = str(val)
        max_len = _PER_KEY_MAX.get(k, _DEFAULT_MAX)
        if len(val_str) > max_len:
            val_str = (
                val_str[:max_len]
                + f"\n...(truncated, original {len(val_str)} chars)"
            )
        section = f"### {k}"
        hint = _hint_for(k, app_action_prefix)
        if hint:
            section += "\n" + hint + "\n"
        section += "\n" + val_str
        parts.append(section)

    if not parts:
        return ""

    if heading:
        return heading + "\n\n" + "\n\n".join(parts)
    return "\n\n".join(parts)


__all__ = ["format_desktop_snapshot"]
