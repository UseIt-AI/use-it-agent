"""ask_user — 让 Router Planner 挂起并询问用户的 engine tool。

为什么是 ``EngineTool`` 而不是 ``InlineTool``
-----------------------------------------------
Planner 并不能"在自己的进程里等用户"——必须通过前端 UI 拿到用户输入。
``EngineTool`` 的协议正好是"产出一个 tool_call 事件 → 挂起 → 下一轮前端
用 execution_result 回传结果"，和 ``app__*`` / ``ppt_*`` 这些走 Local Engine
的 tool 是**完全一样的管道**，区别只是 ``target="user"``——前端看到这个
discriminator 时渲染 dialog 而不是调度 action handler。

不属于任何 ``ToolPack``
------------------------
和 ``web_search`` 一样是独立 tool（``group=""``），永远可用；
``filter.py`` 里独立 tool 不走 pack 白名单 / snapshot 检测的门，
只要 ``is_enabled(ctx)`` 返回 True 就进入 enabled_tools。

协议与 orchestrator 层 ``ask_user`` 完全对齐
---------------------------------------------
见 ``docs/ASK_USER_TOOL_CONTRACT.md``。前端只需要实现一份 dialog
渲染逻辑：orchestrator 层（``agent_loop/capability_catalog.py::ASK_USER_TOOL``）
和 agent_node 层（本文件）共享同一套 ``tool_call{target:"user"}`` payload
约定和同一份 ``execution_result.user_response`` 回调约定。
"""

from __future__ import annotations

from typing import Any, Dict, TYPE_CHECKING

from useit_studio.ai_run.utils.logger_utils import LoggerUtils

from .protocol import EngineTool, PermissionResult, ToolCall

if TYPE_CHECKING:
    from useit_studio.ai_run.node_handler.base_v2 import NodeContext
    from ..models import (
        PlannerOutput,
    )


logger = LoggerUtils(component_name="Tool.ask_user")


_KIND_ALIASES = {
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


ROUTER_DETAIL = """\
### ask_user

Pause and ask the user one specific question.  Use this **whenever any
of these hold** — do NOT try to guess past them:

1. **User explicitly asked to confirm / ask / verify** ("和我确认",
   "先问我", "ask me first", "which one do you mean", "check with me").
   Honour the request verbatim — do NOT execute and describe it
   afterwards.
2. **Target is ambiguous** and you cannot uniquely pick one from the
   user's text.  Includes: a prior tool result like ``"No X found
   matching 'foo'. Available: a, b, c, …"``; the user referred to
   "the file / that window / 那个文档" while multiple matches exist in
   the snapshot (e.g. 3 Excel windows open, 2 `.pptx` on the desktop);
   the user said "打开 PPT" / "open PPT" but `installed_apps` has
   several candidates (PowerPoint + WPS, etc.).  Show the top 3-6
   matches as options; use the candidate's real id / handle as the
   option `id` so you can act on the reply directly.  Do NOT retry
   the lookup with a different guess.
3. **Destructive, irreversible, or scope-creep action.** Delete /
   overwrite / mass-edit / close an unsaved window; the next step's
   natural scope is clearly larger than the user implied (batch /
   multi-doc when they named one); launching a long-running action.
   Confirm first.
4. **Validation tool surfaced a branching decision** — e.g.
   `ppt_verify_layout` found 3 overlap errors → "auto-fix / skip /
   abort?".

Do **not** use for chit-chat, progress narration, or to avoid a small
obviously-safe choice.  Do **not** re-ask after the user dismisses —
stop or pick a safe default.  One pending `ask_user` at a time.

**Params:**

- `prompt` (str, required): single short question, plain language.
- `kind` (str, required): `confirm` (2-3 discrete choices), `choose`
  (≥3 options; ideal for disambiguation lists), or `input` (free-form
  text).
- `options` (array of `{id, label}`): choices.  Required for `confirm`
  and `choose`; optional for `input` (quick-pick suggestions).  For
  disambiguation, set `id` to the candidate's id/handle and `label` to
  its display name.
- `default_option_id` (str, optional): id selected by keyboard Enter;
  must match one of the supplied option ids.
- `allow_free_text` (bool, optional): also show a text input beside the
  options.  Automatically true when `kind=input`.
- `timeout_seconds` (int, optional): auto-dismiss after N seconds.  0 =
  wait indefinitely (default).

**Next step after the user answers:** the planner sees the reply as
``Previous ask_user answer: selected option `<id>` …`` in
``last_execution_output`` and picks the next action accordingly.
Treat ``dismissed=true`` as "user declined to answer — stop now or
pick a safe default"."""


class AskUserTool(EngineTool):
    """Engine tool that suspends the agent node and asks the user."""

    name = "ask_user"
    group = ""  # standalone, no ToolPack
    target = "user"
    router_hint = (
        "Pause and ask the user.  Triggers: (a) user explicitly asked "
        "to confirm / ask / verify, (b) target is ambiguous — lookup "
        "multiple candidates, user said 'the file / 那个窗口' with "
        "several matches, or 'open PPT' with multiple apps installed, "
        "(c) destructive / irreversible / scope-creep / expensive "
        "action, (d) validation tool flagged a branching decision.  "
        "Params: prompt, kind=confirm|choose|input, options, "
        "default_option_id, allow_free_text, timeout_seconds."
    )
    router_detail = ROUTER_DETAIL
    is_read_only = True
    is_destructive = False
    input_schema = {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Short, specific question to show the user.",
            },
            "kind": {
                "type": "string",
                "enum": ["confirm", "choose", "input"],
                "description": (
                    "`confirm` for 2-3 discrete choices, `choose` for "
                    "picking 1 of >=3, `input` for free-form text."
                ),
            },
            "options": {
                "type": "array",
                "description": (
                    "Button / radio choices. Required for `confirm` and "
                    "`choose`; optional for `input`."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "label": {"type": "string"},
                    },
                    "required": ["id", "label"],
                },
            },
            "default_option_id": {
                "type": "string",
                "description": "Option id selected by keyboard Enter.",
            },
            "allow_free_text": {
                "type": "boolean",
                "description": (
                    "Also show a text input beside the options. "
                    "Automatically true when kind=input."
                ),
            },
            "timeout_seconds": {
                "type": "integer",
                "minimum": 0,
                "description": (
                    "Auto-dismiss after this many seconds (0 = wait "
                    "indefinitely)."
                ),
            },
        },
        "required": ["prompt", "kind"],
    }

    def is_enabled(self, ctx: "NodeContext") -> bool:
        return True

    def check_permission(
        self, ctx: "NodeContext", params: Dict[str, Any]
    ) -> PermissionResult:
        prompt = str((params or {}).get("prompt", "")).strip()
        if not prompt:
            return PermissionResult(
                decision="deny",
                reason="ask_user requires a non-empty `prompt`.",
            )
        kind_raw = str((params or {}).get("kind", "")).strip().lower()
        kind = _KIND_ALIASES.get(kind_raw, kind_raw)
        if kind not in ("confirm", "choose", "input"):
            return PermissionResult(
                decision="deny",
                reason=(
                    f"ask_user.kind must be one of confirm/choose/input; "
                    f"got {kind_raw!r}."
                ),
            )
        # Normalise into updated_params so the handler dispatches the
        # canonical payload regardless of what the LLM wrote.
        return PermissionResult(
            decision="allow",
            updated_params=normalize_ask_user_args(params or {}),
        )

    def build_tool_call(
        self,
        params: Dict[str, Any],
        planner_output: "PlannerOutput",
    ) -> ToolCall:
        # params has already been normalised by check_permission →
        # updated_params, so we can ship it verbatim.
        return ToolCall(name="ask_user", args=dict(params))


def normalize_ask_user_args(args: Dict[str, Any]) -> Dict[str, Any]:
    """Coerce LLM-produced ``ask_user`` args into a safe, uniform shape.

    Shared with the orchestrator-layer normaliser
    (``agent_loop.capability_catalog._normalize_ask_user_args``); kept
    as a separate copy here to avoid an ``agent_node → agent_loop``
    import cycle (agent_loop already depends on nothing from
    agent_node).  The logic must stay in sync — changes to either copy
    should be mirrored in the other.
    """
    kind_raw = str(args.get("kind") or "confirm").strip().lower()
    kind = _KIND_ALIASES.get(kind_raw, "confirm")

    prompt = str(args.get("prompt") or "").strip()

    raw_opts = args.get("options") or []
    opts: list[dict] = []
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


def render_user_response(execution_result: Dict[str, Any]) -> str:
    """Turn the frontend's ``execution_result`` into planner-readable text.

    Accepts both the preferred nested shape
    (``execution_result.user_response = {selected_option_id, free_text,
    dismissed}``) and a flat fallback (fields at the top level).  Used
    by ``AgentNodeHandler._compose_last_execution_output`` to surface
    the actual choice to the Router Planner instead of a generic
    ``SUCCESS / Payload keys: [...]`` blob.
    """
    if not isinstance(execution_result, dict):
        return "Previous ask_user answer: (no payload)"

    nested = execution_result.get("user_response")
    if isinstance(nested, dict):
        payload = nested
    else:
        payload = {
            k: execution_result.get(k)
            for k in ("selected_option_id", "free_text", "dismissed")
            if k in execution_result
        }

    if bool(payload.get("dismissed")):
        return (
            "Previous ask_user answer: user DISMISSED the dialog "
            "(timeout / Esc / closed). Do NOT re-ask — either stop now "
            "or proceed with a safe default."
        )

    sid = payload.get("selected_option_id")
    if sid is not None:
        sid = str(sid).strip() or None
    ft = payload.get("free_text") or ""
    if not isinstance(ft, str):
        ft = str(ft)
    ft = ft.strip()

    parts: list[str] = ["Previous ask_user answer:"]
    if sid:
        parts.append(f"selected option `{sid}`.")
    if ft:
        parts.append(f"free-text reply: {ft}")
    if len(parts) == 1:
        parts.append("(empty reply — treat as dismissed)")
    return " ".join(parts)


TOOL = AskUserTool()
