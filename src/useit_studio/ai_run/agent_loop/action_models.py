"""
Agent Loop data models.

Defines the state machine, action types, and context container
used by AgentLoop to track its position across multiple HTTP
round-trips.
"""

from __future__ import annotations

import uuid
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class OrchestratorState(str, Enum):
    """State machine for the orchestrator across HTTP round-trips."""
    ORCHESTRATING = "orchestrating"
    WAITING_APP_CALLBACK = "waiting_app_callback"
    WAITING_USER_RESPONSE = "waiting_user_response"
    EXECUTING_WORKFLOW = "executing_workflow"
    DONE = "done"


@dataclass
class AppActionCall:
    """An app action the orchestrator wants to execute on the frontend."""
    name: str
    args: Dict[str, Any]
    tool_call_id: str = field(default_factory=lambda: f"app_{uuid.uuid4().hex[:12]}")


@dataclass
class AskUserCall:
    """A pending ``ask_user`` question the orchestrator has sent to the UI.

    Mirrors :class:`AppActionCall` but carries the rendered prompt payload
    the frontend shows to the user.  The response comes back on the same
    ``execution_result`` callback endpoint under the ``user_response``
    key — see :meth:`AgentLoop._handle_user_response_callback`.
    """
    prompt: str
    kind: str = "confirm"  # "confirm" | "input" | "choose"
    options: List[Dict[str, Any]] = field(default_factory=list)
    default_option_id: Optional[str] = None
    allow_free_text: bool = False
    timeout_seconds: int = 0
    tool_call_id: str = field(default_factory=lambda: f"ask_{uuid.uuid4().hex[:12]}")


@dataclass
class WorkflowActionCall:
    """A workflow the orchestrator wants to run."""
    workflow_id: str
    workflow_name: str = ""


# ---------------------------------------------------------------------------
# Plan / Todo state — inspired by Claude Code's TodoWriteTool and Cursor's
# plan mode.  This is the **task-level scratchpad** that lives across HTTP
# round-trips alongside ``conversation``: it gives the planner LLM a
# stable, structured place to lay out a multi-step plan once and refer
# back to it on every subsequent turn instead of re-deriving it from
# free-text reasoning.
#
# A future PR ("plan_to_workflow") will read these items' ``suggested_*``
# hints and synthesise an executable workflow graph from them — that's
# the core differentiator of UseIt vs a generic coding agent.  This first
# PR only persists the plan and surfaces it in the prompt; it does NOT
# yet generate workflows.
# ---------------------------------------------------------------------------


# Allowed item statuses.  Mirrors Claude Code (``pending`` / ``in_progress``
# / ``completed``) plus an explicit ``cancelled`` for items the planner
# decides to drop mid-run (rather than silently deleting them, which would
# lose audit trail).
PLAN_ITEM_STATUSES: tuple = ("pending", "in_progress", "completed", "cancelled")


@dataclass
class PlanItem:
    """One actionable item on the orchestrator's task plan.

    Field design notes:

    * ``id`` is planner-assigned and stable across plan revisions so
      ``depends_on`` references survive partial updates.
    * ``content`` is the imperative form ("Open PowerPoint and load
      template").  ``active_form`` is the optional present-continuous
      form the UI can show while the item is in-progress ("Opening
      PowerPoint and loading template") — same convention as Claude
      Code's TodoWriteTool.
    * ``suggested_node_type`` / ``suggested_tool`` link the plan to the
      workflow node taxonomy in
      :mod:`useit_ai_run.agent_loop.workflow.node_types`.  Treat them as
      *hints only*: the planner is not forced to follow them, but they
      let a future ``plan_to_workflow`` tool (see project plan PR 3)
      synthesise a graph without re-prompting the LLM for node types.
    * ``depends_on`` carries the topology so the synthesiser can build
      fan-in / fan-out edges.  Empty ⇒ depends on whichever item
      precedes it textually.
    * ``notes`` is free-form scratch the planner can use to remember
      details across turns ("user wants 4:3 layout, NOT 16:9") — keeps
      that kind of context out of the imperative ``content``.
    """

    id: str
    content: str
    active_form: str = ""
    status: str = "pending"
    suggested_node_type: Optional[str] = None
    suggested_tool: Optional[str] = None
    depends_on: List[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "active_form": self.active_form,
            "status": self.status,
            "suggested_node_type": self.suggested_node_type,
            "suggested_tool": self.suggested_tool,
            "depends_on": list(self.depends_on),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlanItem":
        """Build a PlanItem from a dict, tolerating legacy / partial input."""
        status = str(data.get("status") or "pending").strip().lower()
        if status not in PLAN_ITEM_STATUSES:
            # Be lenient: unknown status from LLM drift -> ``pending`` so we
            # don't lose the item entirely.  Caller logs a warning.
            status = "pending"
        depends_raw = data.get("depends_on") or []
        if not isinstance(depends_raw, list):
            depends_raw = []
        depends = [str(x).strip() for x in depends_raw if str(x).strip()]
        return cls(
            id=str(data.get("id") or "").strip(),
            content=str(data.get("content") or "").strip(),
            active_form=str(data.get("active_form") or "").strip(),
            status=status,
            suggested_node_type=(
                str(data["suggested_node_type"]).strip()
                if data.get("suggested_node_type") else None
            ),
            suggested_tool=(
                str(data["suggested_tool"]).strip()
                if data.get("suggested_tool") else None
            ),
            depends_on=depends,
            notes=str(data.get("notes") or ""),
        )


@dataclass
class Clarification:
    """A confirmed ``ask_user`` Q&A that should travel with the task.

    Produced at TWO layers, consumed by any downstream planner that
    needs to know what the user already committed to:

    * **Orchestrator** — when :meth:`AgentLoop._handle_user_response_callback`
      folds the user's answer into :class:`OrchestratorContext.conversation`,
      the same answer is reified as a ``Clarification`` via
      :meth:`OrchestratorContext.extract_clarifications` and handed to
      ``FlowProcessor.step(clarifications=...)`` on every subsequent
      workflow step.
    * **Agent node** — when a Router-Planner-issued ``ask_user``
      completes, the node handler pushes a ``Clarification`` onto its
      :class:`FlowProcessor` so it's visible to *every subsequent
      node* in the same workflow run, not just the current planner
      loop.

    The rendered ``question``/``answer`` strings are what the
    downstream planner sees in its prompt's ``## User Clarifications``
    section, so keep them short and self-contained (no pronouns to
    context that won't be visible).  ``selected_option_id`` /
    ``selected_option_label`` are retained separately so a future
    planner can act on the *machine-readable* choice (e.g. pass an
    hwnd straight into ``system_window_control``) without
    round-tripping through free text.
    """
    question: str
    answer: str
    selected_option_id: Optional[str] = None
    selected_option_label: Optional[str] = None
    free_text: Optional[str] = None
    source: str = "orchestrator"  # "orchestrator" | "agent_node"
    source_node_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "question": self.question,
            "answer": self.answer,
            "selected_option_id": self.selected_option_id,
            "selected_option_label": self.selected_option_label,
            "free_text": self.free_text,
            "source": self.source,
            "source_node_id": self.source_node_id,
        }


@dataclass
class TextResponse:
    """A direct text reply to the user (no tool execution)."""
    content: str


@dataclass
class ConversationTurn:
    """One turn of orchestrator history (for multi-step planning)."""
    role: str  # "user" | "assistant" | "tool"
    content: str = ""
    tool_call_id: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    name: Optional[str] = None


@dataclass
class OrchestratorContext:
    """
    Mutable state container that persists across HTTP round-trips.

    The orchestrator is stateful: one user request may require several
    round-trips (app action -> callback -> next decision -> ...).
    This context is cached in memory (keyed by task_id), the same way
    FlowProcessor instances are cached.
    """
    task_id: str
    state: OrchestratorState = OrchestratorState.ORCHESTRATING

    conversation: List[ConversationTurn] = field(default_factory=list)

    pending_app_action: Optional[AppActionCall] = None

    # The question the orchestrator is waiting on the user to answer.
    # Mutually exclusive with ``pending_app_action`` — while one is set the
    # other must be None.  Both are cleared back to None in their
    # respective callback handlers before resuming ``_plan_and_act``.
    pending_ask_user: Optional[AskUserCall] = None

    active_workflow_id: Optional[str] = None

    # The workflow the user selected in the UI (may be None)
    selected_workflow_id: Optional[str] = None

    app_capabilities: List[Dict[str, Any]] = field(default_factory=list)
    workflow_capabilities: List[Dict[str, Any]] = field(default_factory=list)

    step_count: int = 0
    max_steps: int = 20

    # --- Plan / todo scratchpad (PR 1) ---
    # Persisted across round-trips so the planner LLM can refer back to
    # its own multi-step plan without re-deriving it from free-text
    # reasoning each turn.  Written by the ``plan_write`` tool; rendered
    # back into the prompt by ``AgentLoop._build_planning_message``.
    #
    # ``plan_revision`` is a monotonically-increasing counter the logger
    # uses to detect stale snapshots; the LLM never sees it.
    plan: List[PlanItem] = field(default_factory=list)
    plan_revision: int = 0

    # --- Runtime environment snapshot (refreshed each round-trip) ---
    screenshot_path: str = ""
    uia_data: Dict[str, Any] = field(default_factory=dict)
    attached_files: List[Dict[str, Any]] = field(default_factory=list)
    attached_images: List[Dict[str, Any]] = field(default_factory=list)
    action_history: Dict[str, Any] = field(default_factory=dict)
    history_md: Optional[str] = None

    def add_user_message(self, content: str) -> None:
        if not self.conversation or self.conversation[-1].role != "user":
            self.conversation.append(ConversationTurn(role="user", content=content))

    def add_assistant_tool_call(self, tool_calls: List[Dict[str, Any]]) -> None:
        self.conversation.append(
            ConversationTurn(role="assistant", tool_calls=tool_calls)
        )

    def add_tool_result(self, tool_call_id: str, name: str, content: str) -> None:
        self.conversation.append(
            ConversationTurn(
                role="tool",
                content=content,
                tool_call_id=tool_call_id,
                name=name,
            )
        )

    def add_assistant_text(self, content: str) -> None:
        self.conversation.append(
            ConversationTurn(role="assistant", content=content)
        )

    def last_confirmed_workflow_switch(self) -> Optional[str]:
        """Return the most recent workflow_id the user approved switching to.

        The approval is evidenced by a successful ``app__switchWorkflow``
        tool result in the conversation — the frontend's confirmation
        that the UI selection was actually updated.  Without this
        evidence the orchestrator MUST NOT call ``workflow__run`` for
        an id that doesn't match the current ``selected_workflow_id``
        (see ``AgentLoop._plan_and_act`` workflow_action guard).

        We walk from the tail back so the *latest* switch wins when the
        user churned through multiple candidates.  The tool result's
        content is the JSON-serialised frontend payload
        (``{"success": true, "data": {"workflowId": "..."}, ...}``).
        A match requires both ``success == true`` and a non-empty
        ``workflowId`` — anything else (frontend error, cancelled
        dialog, schema drift) is ignored.
        """
        for turn in reversed(self.conversation):
            if turn.role != "tool":
                continue
            if turn.name != "app__switchWorkflow":
                continue
            payload: Dict[str, Any]
            try:
                import json as _json
                payload = _json.loads(turn.content or "")
                if not isinstance(payload, dict):
                    continue
            except Exception:  # noqa: BLE001 — malformed tool result shouldn't raise
                continue
            if not payload.get("success"):
                continue
            data = payload.get("data")
            wfid: Optional[str] = None
            if isinstance(data, dict):
                wfid = data.get("workflowId") or data.get("workflow_id")
            if not wfid:
                wfid = payload.get("workflowId") or payload.get("workflow_id")
            if wfid:
                return str(wfid)
        return None

    def extract_clarifications(self) -> List[Clarification]:
        """Walk the conversation and return one ``Clarification`` per
        answered ``ask_user`` round-trip.

        The pairing is done by ``tool_call_id``: every ``ask_user``
        assistant tool_call has an id that reappears on the ``tool``
        turn that holds the user's answer.  Dialogs the user dismissed
        are still recorded — agent_node should know the user declined
        to disambiguate, so it can pick a safe default or stop.

        Called from :meth:`AgentLoop._handle_workflow_step` on every
        workflow step so any answer the user gave in the most recent
        orchestration round is visible to the newly-invoked node.

        Keeping this derivation stateless (re-walk on every call) has
        two benefits: (1) we never have to keep a shadow list in sync
        with ``conversation``, and (2) replaying history — e.g. when
        an orchestrator is rehydrated from ``StateStore`` — produces
        an identical clarification list.
        """
        # Build an id -> {prompt, options} lookup from assistant turns
        # so we can render the question alongside the answer.
        ask_prompts: Dict[str, Dict[str, Any]] = {}
        for turn in self.conversation:
            if turn.role != "assistant" or not turn.tool_calls:
                continue
            for tc in turn.tool_calls:
                if tc.get("name") != "ask_user":
                    continue
                tid = tc.get("id")
                if not tid:
                    continue
                args = tc.get("args") or {}
                ask_prompts[tid] = {
                    "prompt": str(args.get("prompt") or "").strip(),
                    "options": args.get("options") or [],
                }

        out: List[Clarification] = []
        for turn in self.conversation:
            if turn.role != "tool" or turn.name != "ask_user":
                continue
            tid = turn.tool_call_id or ""
            pq = ask_prompts.get(tid, {})
            question = pq.get("prompt") or "(question unavailable)"
            answer_text = (turn.content or "").strip()

            # Best-effort extraction of option id/label from answer.
            sid, label = _parse_selected_option(answer_text, pq.get("options") or [])
            free = _parse_free_text(answer_text)
            out.append(Clarification(
                question=question,
                answer=answer_text,
                selected_option_id=sid,
                selected_option_label=label,
                free_text=free,
                source="orchestrator",
                source_node_id=None,
            ))
        return out

    # ------------------------------------------------------------------
    # Plan management
    # ------------------------------------------------------------------
    #
    # The planner's plan is full-replacement (one ``plan_write`` call
    # rewrites the entire list) — same canonical shape as Claude Code's
    # TodoWriteTool.  Partial updates were considered and rejected:
    # full replacement makes drift impossible to hide, makes diffs
    # trivial to render, and lets the LLM treat the plan as a normal
    # JSON document instead of an event log.

    def update_plan(self, items: List[PlanItem]) -> Dict[str, Any]:
        """Replace the current plan with ``items`` after lightweight repair.

        Repairs applied (mirrors the spirit of
        ``capability_catalog._normalize_ask_user_args``):

        * **At most one ``in_progress``.**  If the LLM marks several,
          keep the first one and downgrade the rest to ``pending``.
        * **Duplicate ids.**  Suffix with ``_<n>`` so ``depends_on``
          references at least disambiguate predictably.
        * **Empty content.**  Drop the item silently — there's nothing
          actionable.

        Returns a small summary dict the caller can pass back to the
        planner as the ``plan_write`` tool result so its next turn sees
        confirmation of what landed (and any auto-fixes that happened).
        """
        seen_ids: Dict[str, int] = {}
        repaired: List[PlanItem] = []
        in_progress_seen = False
        downgraded = 0
        for item in items:
            if not item.content:
                continue
            iid = item.id or f"step-{len(repaired) + 1}"
            if iid in seen_ids:
                seen_ids[iid] += 1
                iid = f"{iid}_{seen_ids[iid]}"
            else:
                seen_ids[iid] = 0
            item.id = iid
            if item.status == "in_progress":
                if in_progress_seen:
                    item.status = "pending"
                    downgraded += 1
                else:
                    in_progress_seen = True
            repaired.append(item)

        self.plan = repaired
        self.plan_revision += 1

        counts = {
            "total": len(repaired),
            "pending": sum(1 for i in repaired if i.status == "pending"),
            "in_progress": sum(1 for i in repaired if i.status == "in_progress"),
            "completed": sum(1 for i in repaired if i.status == "completed"),
            "cancelled": sum(1 for i in repaired if i.status == "cancelled"),
        }
        return {
            "revision": self.plan_revision,
            "counts": counts,
            "downgraded_extra_in_progress": downgraded,
        }

    def render_plan_for_prompt(self, max_recent_completed: int = 1) -> str:
        """Render the current plan as a markdown section for the LLM prompt.

        We do NOT include every completed item — token cost adds up over
        a long task.  By default we show:

        * every non-completed / non-cancelled item, AND
        * the ``max_recent_completed`` most-recently-finished items
          (so the planner knows what was just done)

        Items are rendered in their stored order (the planner's chosen
        ordering) so dependencies read top-down.  The current
        ``in_progress`` item (if any) is starred so the LLM knows which
        rung of the ladder it's on.
        """
        if not self.plan:
            return ""

        active: List[PlanItem] = []
        recent_completed: List[PlanItem] = []
        for item in self.plan:
            if item.status in ("pending", "in_progress"):
                active.append(item)
            elif item.status == "completed":
                recent_completed.append(item)
            # ``cancelled`` items are silently hidden from the prompt;
            # they're still in ``self.plan`` for logging/audit.

        recent_completed = recent_completed[-max_recent_completed:]

        if not active and not recent_completed:
            return ""

        lines: List[str] = [f"## Current Plan (revision {self.plan_revision})"]
        lines.append("")
        lines.append(
            "Use this plan as your task scratchpad.  When you start an item, "
            "call `plan_write` to mark it `in_progress` BEFORE you act.  When "
            "it's truly done (not partial), call `plan_write` again to mark "
            "it `completed`.  Exactly one item should be `in_progress` at a "
            "time."
        )
        lines.append("")
        if recent_completed:
            lines.append("### Recently completed")
            for item in recent_completed:
                lines.append(f"- [x] **{item.id}** — {item.content}")
            lines.append("")
        if active:
            lines.append("### To do")
            for item in active:
                marker = "▶" if item.status == "in_progress" else "•"
                bits = [f"{marker} **{item.id}** [{item.status}] — {item.content}"]
                hints: List[str] = []
                if item.suggested_node_type:
                    hints.append(f"node_type=`{item.suggested_node_type}`")
                if item.suggested_tool:
                    hints.append(f"tool=`{item.suggested_tool}`")
                if item.depends_on:
                    hints.append(f"after [{', '.join(item.depends_on)}]")
                if hints:
                    bits.append("  _" + " · ".join(hints) + "_")
                if item.notes:
                    bits.append(f"  _note:_ {item.notes}")
                lines.append("\n".join(bits))
        return "\n".join(lines)

    def plan_summary(self) -> Dict[str, Any]:
        """Compact dict used by loggers / events (NOT shown to the LLM)."""
        return {
            "revision": self.plan_revision,
            "items": [item.to_dict() for item in self.plan],
        }


# ==================== Streaming Event Types ====================
# Aligned with office_agent/models.py event conventions so that
# backend and frontend can handle Agent Loop and Office Agent
# events through a single code-path.


@dataclass
class PlannerDecision:
    """
    The planning result produced by the Agent Loop's LLM call.

    Mirrors ``PlannerOutput`` from office_agent but adapted for the
    orchestrator's function-calling approach.
    """
    action_type: str = ""       # "app_action" | "workflow_action" | "ask_user" | "respond" | ""
    tool_name: str = ""         # e.g. "app__createWorkflow", "workflow__run", "ask_user", "respond_to_user"
    tool_args: Dict[str, Any] = field(default_factory=dict)
    tool_call_id: str = ""
    thinking: str = ""          # LLM reasoning text (when available)
    is_completed: bool = False
    completion_summary: str = ""
    elapsed_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "Action": self.action_type,
            "ToolName": self.tool_name,
            "ToolArgs": self.tool_args,
            "ToolCallId": self.tool_call_id,
            "Thinking": self.thinking,
            "MilestoneCompleted": self.is_completed,
            "node_completion_summary": self.completion_summary,
        }


@dataclass
class StepStartEvent:
    step: int

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "step_start", "step": self.step}


@dataclass
class ReasoningDeltaEvent:
    content: str
    source: str = "planner"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "reasoning_delta",
            "content": self.content,
            "source": self.source,
        }


@dataclass
class PlanCompleteEvent:
    decision: PlannerDecision

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "plan_complete",
            "content": self.decision.to_dict(),
        }


@dataclass
class StepCompleteEvent:
    step: int
    action_type: str = ""
    tool_name: str = ""
    token_usage: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "step_complete",
            "content": {
                "step": self.step,
                "action_type": self.action_type,
                "tool_name": self.tool_name,
            },
            "token_usage": self.token_usage,
        }


@dataclass
class TaskCompletedEvent:
    summary: str = "Task completed"

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "task_completed", "summary": self.summary}


@dataclass
class ErrorEvent:
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "error", "content": self.message}


# ---------------------------------------------------------------------------
# Internal: parse a rendered ask_user answer string
# ---------------------------------------------------------------------------
#
# The orchestrator renders answers via
# ``AgentLoop._format_user_response_for_planner`` in these exact shapes:
#   * "User selected option `<id>` (`label`)."
#   * "User selected option `<id>`."
#   * "User free-text reply: <text>"
#   * "User dismissed the question..."
# The agent_node side renders via ``tools.ask_user.render_user_response`` in:
#   * "Previous ask_user answer: selected option `<id>`."
#   * "Previous ask_user answer: ... free-text reply: <text>"
#   * "Previous ask_user answer: user DISMISSED the dialog..."
# We accept both so extraction is robust regardless of which layer
# produced the Clarification source string.
import re as _re  # noqa: E402

_OPTION_ID_RE = _re.compile(r"selected option\s+`([^`]+)`", _re.IGNORECASE)
_OPTION_LABEL_RE = _re.compile(r"selected option\s+`[^`]+`\s*\(`?([^`)]+?)`?\)", _re.IGNORECASE)
_FREE_TEXT_RE = _re.compile(r"free-text reply:\s*(.+)$", _re.IGNORECASE | _re.MULTILINE)


def _parse_selected_option(
    rendered: str, options: List[Dict[str, Any]],
) -> "tuple[Optional[str], Optional[str]]":
    m = _OPTION_ID_RE.search(rendered or "")
    if not m:
        return None, None
    sid = m.group(1).strip() or None
    label = None
    lm = _OPTION_LABEL_RE.search(rendered or "")
    if lm:
        label = lm.group(1).strip() or None
    if not label and sid:
        label = next(
            (str(o.get("label") or "") for o in options if o.get("id") == sid),
            None,
        )
    return sid, label


def _parse_free_text(rendered: str) -> Optional[str]:
    m = _FREE_TEXT_RE.search(rendered or "")
    if not m:
        return None
    val = m.group(1).strip()
    return val or None
