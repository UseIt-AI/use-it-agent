"""
Agent Loop Logger

Structured on-disk logging for the Agent Loop decision cycle.

Layout per task:
    {log_root}/{YYMMDD-HHMMSS}_agent_tid_{task_id}/
        session_info.json
        stream_messages.jsonl
        step_001/  (request.json, prompt.md, response.json, context_snapshot.json)
        step_002/  (callback_input.json, request.json, ...)
        step_003_workflow/  (decision.json + RunLogger takes over)
        summary.json

All write operations are wrapped in try/except so logging failures
never break the main execution flow.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import logging

logger = logging.getLogger(__name__)

UTC_PLUS_8 = timezone(timedelta(hours=8))


class AgentLoopLogger:
    """Structured per-task logger for AgentLoop."""

    def __init__(self, task_id: str, log_root: str = ""):
        self.task_id = task_id
        self._log_root = log_root or os.getenv("RUN_LOG_DIR", "logs/useit_ai_run_logs")
        self._task_dir: Optional[str] = None
        self._current_step_dir: Optional[str] = None
        self._current_step_num: int = 0
        self._event_seq: int = 0
        self._session_start = time.time()

    # ------------------------------------------------------------------
    # Directory management
    # ------------------------------------------------------------------

    @property
    def task_dir(self) -> str:
        """Lazily create the task root directory on first access."""
        if self._task_dir is None:
            now = datetime.now(UTC_PLUS_8)
            ts = now.strftime("%y%m%d-%H%M%S")
            dirname = f"{ts}_agent_tid_{self.task_id}"
            self._task_dir = os.path.join(self._log_root, dirname)
            os.makedirs(self._task_dir, exist_ok=True)
        return self._task_dir

    def start_step(self, step_num: int, suffix: str = "") -> str:
        """Create a step subdirectory and return its path."""
        self._current_step_num = step_num
        name = f"step_{step_num:03d}"
        if suffix:
            name = f"{name}_{suffix}"
        self._current_step_dir = os.path.join(self.task_dir, name)
        os.makedirs(self._current_step_dir, exist_ok=True)
        return self._current_step_dir

    def get_step_dir(self) -> Optional[str]:
        """Return the current step directory (for passing to FlowProcessor/RunLogger)."""
        return self._current_step_dir

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def log_session_info(
        self,
        planner_model: str = "",
        app_capability_count: int = 0,
        workflow_capability_count: int = 0,
        selected_workflow_id: str = "",
    ) -> None:
        """Write session_info.json at the task root."""
        info = {
            "task_id": self.task_id,
            "created_at": _now_iso(),
            "planner_model": planner_model,
            "app_capability_count": app_capability_count,
            "workflow_capability_count": workflow_capability_count,
            "selected_workflow_id": selected_workflow_id or None,
        }
        _write_json(os.path.join(self.task_dir, "session_info.json"), info)

    def log_summary(
        self,
        total_steps: int,
        final_state: str,
        total_token_usage: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Write summary.json at the task root when the task completes."""
        elapsed = time.time() - self._session_start
        summary = {
            "task_id": self.task_id,
            "completed_at": _now_iso(),
            "total_steps": total_steps,
            "final_state": final_state,
            "elapsed_seconds": round(elapsed, 2),
            "total_events": self._event_seq,
            "total_token_usage": total_token_usage or {},
        }
        _write_json(os.path.join(self.task_dir, "summary.json"), summary)

    def log_incoming_request(
        self,
        request_data: Dict[str, Any],
        http_round: Optional[int] = None,
    ) -> None:
        """Persist the raw HTTP body received from the frontend.

        Writes ``incoming_request.json`` at the task root so we can tell,
        after the fact, exactly what the frontend sent us (most importantly
        whether ``uia_data`` / ``screenshot`` were included and what they
        looked like).

        Large binary-ish fields (``screenshot``) are replaced with a short
        length summary so the file stays diff-friendly.  Every other field
        — including the full ``uia_data`` payload — is preserved verbatim.

        If the endpoint is called multiple times for the same task (app
        action callbacks, follow-up messages, etc.) each body is appended
        to ``incoming_requests.jsonl`` in addition to overwriting the
        single-shot ``incoming_request.json`` (which always reflects the
        most recent body).
        """
        try:
            scrubbed = _scrub_request_body(request_data)
            summary = {
                "received_at": _now_iso(),
                "task_id": self.task_id,
                "http_round": http_round,
                "has_uia_data": bool(request_data.get("uia_data")),
                "uia_data_keys": sorted(list((request_data.get("uia_data") or {}).keys()))
                    if isinstance(request_data.get("uia_data"), dict) else None,
                "uia_data_json_bytes": len(json.dumps(
                    request_data.get("uia_data") or {}, ensure_ascii=False, default=str,
                )),
                "has_screenshot": bool(request_data.get("screenshot")),
                "screenshot_bytes": len(request_data["screenshot"])
                    if isinstance(request_data.get("screenshot"), str) else 0,
                "body": scrubbed,
            }
            _write_json(
                os.path.join(self.task_dir, "incoming_request.json"),
                summary,
            )
            try:
                line_path = os.path.join(self.task_dir, "incoming_requests.jsonl")
                with open(line_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(summary, ensure_ascii=False, default=str) + "\n")
            except Exception as exc:
                logger.warning("[AgentLoopLogger] append incoming_requests.jsonl failed: %s", exc)
        except Exception as exc:
            logger.warning("[AgentLoopLogger] log_incoming_request failed: %s", exc)

    # ------------------------------------------------------------------
    # LLM call logging (per step)
    # ------------------------------------------------------------------

    def log_llm_request(
        self,
        system_prompt: str,
        user_message: str,
        tools: List[Dict[str, Any]],
        model: str,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> None:
        """Write request.json + prompt.md for the current step."""
        if not self._current_step_dir:
            return

        request_data = {
            "timestamp": _now_iso(),
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "system_prompt_length": len(system_prompt),
            "user_message_length": len(user_message),
            "tool_count": len(tools),
            "system_prompt": system_prompt,
            "user_message": user_message,
            "tools": tools,
        }
        _write_json(os.path.join(self._current_step_dir, "request.json"), request_data)

        self._write_prompt_md(system_prompt, user_message, tools, model, temperature, max_tokens)

    def log_llm_response(
        self,
        content: str = "",
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        token_usage: Optional[Dict[str, Any]] = None,
        finish_reason: str = "",
        model: str = "",
        elapsed_ms: int = 0,
    ) -> None:
        """Write response.json for the current step."""
        if not self._current_step_dir:
            return

        response_data = {
            "timestamp": _now_iso(),
            "model": model,
            "finish_reason": finish_reason,
            "elapsed_ms": elapsed_ms,
            "content": content,
            "tool_calls": tool_calls or [],
            "token_usage": token_usage or {},
        }
        _write_json(os.path.join(self._current_step_dir, "response.json"), response_data)

    # ------------------------------------------------------------------
    # Callback / observation logging
    # ------------------------------------------------------------------

    def log_callback_input(self, execution_result: Optional[Dict[str, Any]]) -> None:
        """Write callback_input.json when handling an app action callback."""
        if not self._current_step_dir:
            return
        data = {
            "timestamp": _now_iso(),
            "execution_result": execution_result,
        }
        _write_json(os.path.join(self._current_step_dir, "callback_input.json"), data)

    def log_workflow_decision(self, workflow_id: str, decision_info: Dict[str, Any]) -> None:
        """Write decision.json when Agent Loop delegates to a workflow."""
        if not self._current_step_dir:
            return
        data = {
            "timestamp": _now_iso(),
            "workflow_id": workflow_id,
            **decision_info,
        }
        _write_json(os.path.join(self._current_step_dir, "decision.json"), data)

    # ------------------------------------------------------------------
    # Context snapshot
    # ------------------------------------------------------------------

    def log_context_snapshot(self, ctx: Any) -> None:
        """Serialize and write the OrchestratorContext at the current step."""
        if not self._current_step_dir:
            return
        try:
            snapshot = {
                "timestamp": _now_iso(),
                "task_id": ctx.task_id,
                "state": ctx.state.value if hasattr(ctx.state, "value") else str(ctx.state),
                "step_count": ctx.step_count,
                "selected_workflow_id": ctx.selected_workflow_id,
                "active_workflow_id": ctx.active_workflow_id,
                "pending_app_action": (
                    {"name": ctx.pending_app_action.name, "args": ctx.pending_app_action.args}
                    if ctx.pending_app_action else None
                ),
                "plan_revision": getattr(ctx, "plan_revision", 0),
                "plan": [
                    item.to_dict() for item in getattr(ctx, "plan", []) or []
                ],
                "conversation_length": len(ctx.conversation),
                "conversation": [
                    {
                        "role": turn.role,
                        "content": turn.content[:500] if turn.content else "",
                        "tool_call_id": turn.tool_call_id,
                        "tool_calls": turn.tool_calls,
                        "name": turn.name,
                    }
                    for turn in ctx.conversation
                ],
            }
            _write_json(
                os.path.join(self._current_step_dir, "context_snapshot.json"),
                snapshot,
            )
        except Exception as e:
            logger.warning("Failed to log context snapshot: %s", e)

    # ------------------------------------------------------------------
    # Event stream (JSONL)
    # ------------------------------------------------------------------

    def append_event(self, event: Dict[str, Any]) -> None:
        """Append one event to the root stream_messages.jsonl."""
        try:
            self._event_seq += 1
            record = {
                "seq": self._event_seq,
                "timestamp": _now_iso(),
                **event,
            }
            filepath = os.path.join(self.task_dir, "stream_messages.jsonl")
            with open(filepath, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        except Exception as e:
            logger.warning("Failed to append event: %s", e)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _write_prompt_md(
        self,
        system_prompt: str,
        user_message: str,
        tools: List[Dict[str, Any]],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> None:
        """Write a human-readable prompt.md for the current step."""
        if not self._current_step_dir:
            return
        try:
            lines = [
                f"# Agent Loop Step {self._current_step_num} — {_now_iso()}",
                "",
                f"## Model",
                f"{model} | temperature={temperature} | max_tokens={max_tokens}",
                "",
                "## System Prompt",
                "",
                system_prompt,
                "",
                "## User Message (conversation history)",
                "",
                user_message,
                "",
                f"## Tools ({len(tools)} total)",
                "",
            ]
            for i, tool in enumerate(tools, 1):
                name = tool.get("name", "?")
                desc = tool.get("description", "")
                if len(desc) > 120:
                    desc = desc[:117] + "..."
                lines.append(f"{i}. **{name}**: {desc}")

            filepath = os.path.join(self._current_step_dir, "prompt.md")
            with open(filepath, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        except Exception as e:
            logger.warning("Failed to write prompt.md: %s", e)


# ======================================================================
# Module-level helpers
# ======================================================================

def _now_iso() -> str:
    return datetime.now(UTC_PLUS_8).isoformat(timespec="seconds")


def _write_json(filepath: str, data: Any) -> None:
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        logger.warning("Failed to write %s: %s", filepath, e)


# ``screenshot`` is base64 and typically 200KB-1MB; ``attached_images`` can also
# carry base64 data URLs.  Replace them with a short length summary so the
# persisted body remains human-readable and diff-friendly while every other
# field (most importantly ``uia_data``) is preserved verbatim.
_BINARY_LIKE_KEYS = {"screenshot"}


def _scrub_request_body(body: Any) -> Any:
    if isinstance(body, dict):
        out: Dict[str, Any] = {}
        for k, v in body.items():
            if k in _BINARY_LIKE_KEYS and isinstance(v, str):
                out[k] = f"<base64 omitted, {len(v)} chars>"
            elif k == "attached_images" and isinstance(v, list):
                out[k] = [_scrub_attached_image(item) for item in v]
            else:
                out[k] = _scrub_request_body(v)
        return out
    if isinstance(body, list):
        return [_scrub_request_body(x) for x in body]
    return body


def _scrub_attached_image(item: Any) -> Any:
    if isinstance(item, dict):
        scrubbed = {}
        for k, v in item.items():
            if isinstance(v, str) and v.startswith("data:") and len(v) > 200:
                scrubbed[k] = f"<data-url omitted, {len(v)} chars>"
            elif isinstance(v, str) and len(v) > 2000:
                scrubbed[k] = v[:200] + f"...<truncated, {len(v)} chars total>"
            else:
                scrubbed[k] = v
        return scrubbed
    if isinstance(item, str) and len(item) > 2000:
        return item[:200] + f"...<truncated, {len(item)} chars total>"
    return item
