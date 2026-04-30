"""
AgentNodeHandler —— 统一功能节点处理器（骨架）

支持 node_type='agent' / 'agent-node'。具体的工具下沉到 `tools/*`，每个软件
一个子包（含 `_pack.py` + `tools.py`），独立 inline 工具放在 `tools/` 根目录
的单文件里。自动发现由 `tools/__init__.py` 完成。

本文件只负责：
1. 首次调用 vs tool_call 回调恢复
2. ToolFilter 解算启用 tool 子集
3. OfficePlanner 作为 Router Planner 跑一步
4. 内联 tool 的 inline 循环（最多 MAX_INLINE_ITERATIONS 步）
5. engine tool 的 tool_call 挂起 / 回调恢复
"""

from __future__ import annotations

import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional

from useit_studio.ai_run.node_handler.base_v2 import (
    BaseNodeHandlerV2,
    ErrorEvent,
    NodeCompleteEvent,
    NodeContext,
)
from .base_planner import (
    OfficePlanner,
    OfficePlannerConfig,
)
from .models import (
    AgentContext as PlannerAgentContext,
    OfficeAppType,
    PlannerOutput,
)
from useit_studio.ai_run.utils.logger_utils import LoggerUtils
from useit_studio.ai_run.utils.uia_render import format_desktop_snapshot

from .filter import ToolFilter
from .prompts import ROUTER_USER_PROMPT_TEMPLATE, build_router_system_prompt
from .tools import TOOL_BY_NAME, rewrite_legacy_tool_call
from .tools.protocol import EngineTool, InlineTool, LLMEngineTool, ToolCall

logger = LoggerUtils(component_name="AgentNodeHandler")


class AgentNodeHandler(BaseNodeHandlerV2):
    """统一的功能节点 handler。"""

    MAX_INLINE_ITERATIONS = 4
    """单次 handler 调用最多允许的 inline 步数（防死循环 / token 爆炸）。
    engine 步触发后会直接 return 挂起，不计入此上限。"""

    @classmethod
    def supported_types(cls) -> List[str]:
        return ["agent", "agent-node"]

    async def execute(  # type: ignore[override]
        self, ctx: NodeContext
    ) -> AsyncGenerator[Dict[str, Any], None]:
        cua_base = f"agent_{uuid.uuid4().hex[:8]}_{ctx.node_id}"
        node_state = ctx.node_state or {}
        handler_state = node_state.get("handler_result", {}) or {}

        # Restore SkillFileReader state (`read_files_list` /
        # ``read_files_content``) onto the **top-level** ``ctx.node_state`` so
        # that ``read_file`` / ``run_skill_script`` inline tools can rebuild a
        # ``SkillFileReader`` via ``from_state`` on every step.  Without this,
        # accumulated reads from a previous suspension would be invisible and
        # the planner would either re-read or hallucinate.
        if isinstance(ctx.node_state, dict):
            for _key in ("read_files_list", "read_files_content"):
                if _key not in ctx.node_state and _key in handler_state:
                    ctx.node_state[_key] = handler_state[_key]

        try:
            # Persists only inline-tool outputs (e.g. ``tool_web_search``,
            # ``ppt_verify_layout``) across engine-tool suspensions.  **Do
            # not** store the full composed ``last_execution_output`` here
            # — that included engine snapshots and caused exponential
            # duplication in ``_compose_last_execution_output`` (see log
            # 260424-181324: stacked ``Previous tool_call`` blocks).
            #
            # Lifecycle: an inline-tool output is meant to bridge **one**
            # engine suspension so the planner can act on it on the next
            # wake-up.  Once the planner has consumed it (composed into
            # the next prompt) it must NOT be re-injected on later
            # suspensions — otherwise stale ``ppt_verify_layout`` reports
            # haunt the planner forever and trigger the
            # "fix-the-same-thing-9-times" loop seen in trajectory
            # 260426-035415 (verify ran once at step 4, the same 2-error
            # report kept appearing in steps 5–14, the planner kept
            # re-issuing ``ppt_render_ppt_layout`` "Fix Left Content
            # Layout and Overlaps").  We track whether
            # ``inline_persist`` was produced in **this** invocation
            # (``inline_persist_fresh``); only fresh values carry across
            # the next suspension.
            inline_persist = str(handler_state.get("inline_last_execution_output") or "")
            inline_persist_fresh = False

            if handler_state.get("is_node_completed") and ctx.execution_result is None:
                yield NodeCompleteEvent(
                    node_id=ctx.node_id,
                    node_type=ctx.node_type,
                    is_node_completed=True,
                    handler_result=handler_state,
                    action_summary="Already completed",
                    node_completion_summary=handler_state.get(
                        "node_completion_summary", "Agent node completed"
                    ),
                ).to_dict()
                return

            if self._is_first_call(ctx) and ctx.execution_result is None:
                yield {
                    "type": "node_start",
                    "nodeId": ctx.node_id,
                    "title": ctx.get_node_title(),
                    "nodeType": ctx.node_type,
                    "instruction": ctx.get_node_instruction(),
                }

            enabled_tools = ToolFilter(ctx).resolve()
            if not enabled_tools:
                yield ErrorEvent(
                    message=(
                        "Agent node has no enabled tools. "
                        "Check node.data.groups / capabilities and API keys."
                    ),
                    node_id=ctx.node_id,
                ).to_dict()
                return

            planner = OfficePlanner(
                config=OfficePlannerConfig(
                    model=self._resolve_model(ctx),
                    max_tokens=8192,
                    app_type=OfficeAppType.POWERPOINT,  # 占位；本路径不依赖 app_type 定制
                ),
                api_keys=ctx.planner_api_keys,
                node_id=ctx.node_id,
                system_prompt=build_router_system_prompt(enabled_tools),
                user_prompt_template=ROUTER_USER_PROMPT_TEMPLATE,
            )

            # Promote a just-received ``ask_user`` answer into a
            # cross-node :class:`Clarification` *before* anything else
            # — this is the only hook where we still have both the
            # original prompt/options (stashed in ``handler_state``
            # when we suspended) and the fresh ``ctx.execution_result``
            # carrying the reply.  Running this once per callback
            # invocation guarantees later nodes see the answer the
            # first time they plan.
            self._maybe_record_ask_user_clarification(ctx, handler_state)

            last_execution_output = self._compose_last_execution_output(
                ctx, handler_state, inline_tail=inline_persist
            )
            inline_history: List[Dict[str, Any]] = list(
                handler_state.get("inline_history", [])
            )
            # Reconcile the last ``pending`` entry with ``ctx.execution_result``.
            #
            # When an engine tool is dispatched we append a history entry with
            # ``result="pending"`` (see below) and suspend.  On the next
            # invocation we must flip that entry to ``success`` / ``failed``
            # based on what the frontend reported, otherwise the planner's
            # "Agent Step History" block keeps showing it as pending and the
            # planner — legitimately following the "don't repeat unless
            # fixing a failed step" rule — reads pending as "not yet done"
            # and re-emits the exact same action.  This was the primary
            # driver of the PowerPoint-activate infinite loop (see log
            # ``260424-102742_agent_tid_0345b3dc``, 15 steps all
            # ``system_window_control`` despite every activate returning
            # ``is_foreground: true``).
            self._reconcile_pending_history(inline_history, ctx.execution_result)

            for _ in range(self.MAX_INLINE_ITERATIONS):
                step_count = self._increment_step_count(ctx)
                cua_id = f"{cua_base}_step{step_count}"

                yield {
                    "type": "cua_start",
                    "cuaId": cua_id,
                    "step": step_count,
                    "title": f"Agent step {step_count}",
                    "nodeId": ctx.node_id,
                }

                planner_output: Optional[PlannerOutput] = None
                async for ev in self._run_planner(
                    planner, ctx, inline_history, last_execution_output, cua_id
                ):
                    if ev.get("_planner_output") is not None:
                        planner_output = ev["_planner_output"]
                    else:
                        yield ev
                        if ev.get("type") == "error":
                            return

                if planner_output is None:
                    yield ErrorEvent(
                        message="Planner produced no output",
                        node_id=ctx.node_id,
                    ).to_dict()
                    return

                action_name = (planner_output.next_action or "").strip()
                title = planner_output.title or action_name or "Agent step"

                if action_name == "stop" or planner_output.is_milestone_completed:
                    async for ev in self._emit_stop(
                        ctx, cua_id, title, planner_output, inline_history
                    ):
                        yield ev
                    return

                # Rewrite legacy tool names (e.g. ``ppt_add_slide`` →
                # ``ppt_slide`` with ``action="add"``) so saved history and
                # occasional LLM drift still dispatch correctly.
                action_name, rewritten_params = rewrite_legacy_tool_call(
                    action_name, planner_output.tool_params
                )
                if planner_output.tool_params != rewritten_params:
                    planner_output.tool_params = rewritten_params

                tool = TOOL_BY_NAME.get(action_name)
                enabled_names = {t.name for t in enabled_tools}
                if tool is None or tool.name not in enabled_names:
                    err = (
                        f"Planner chose unknown or disabled action '{action_name}'. "
                        f"Valid: {sorted(enabled_names)}"
                    )
                    logger.logger.warning(f"[AgentNodeHandler] {err}")
                    inline_history.append({
                        "action": action_name,
                        "summary": title,
                        "result": f"failed: {err[:200]}",
                    })
                    last_execution_output = err
                    yield {
                        "type": "cua_end",
                        "cuaId": cua_id,
                        "status": "error",
                        "error": err,
                    }
                    continue

                params = dict(planner_output.tool_params or {})

                perm = tool.check_permission(ctx, params)
                if perm.decision == "deny":
                    err = f"Permission denied for '{tool.name}': {perm.reason}"
                    logger.logger.warning(f"[AgentNodeHandler] {err}")
                    inline_history.append({
                        "action": action_name,
                        "summary": title,
                        "result": f"denied: {perm.reason[:200]}",
                    })
                    last_execution_output = err
                    yield {
                        "type": "cua_end",
                        "cuaId": cua_id,
                        "status": "error",
                        "error": err,
                    }
                    continue
                if perm.updated_params is not None:
                    params = perm.updated_params

                if isinstance(tool, InlineTool):
                    output_text = await self._run_inline_tool(tool, params, ctx)
                    inline_history.append({
                        "action": action_name,
                        "summary": title,
                        "result": "success",
                    })
                    yield {
                        "type": "cua_update",
                        "cuaId": cua_id,
                        "content": {"type": action_name, "params": params},
                        "kind": "actor",
                    }
                    yield {
                        "type": "cua_end",
                        "cuaId": cua_id,
                        "status": "completed",
                        "title": title,
                        "action": {"type": action_name, "params": params},
                    }
                    last_execution_output = (
                        f"[{action_name}] output:\n{output_text[:10000]}"
                    )
                    inline_persist = last_execution_output
                    inline_persist_fresh = True
                    continue

                if not isinstance(tool, EngineTool):
                    err = (
                        f"Tool '{tool.name}' has unsupported execution_mode "
                        f"'{getattr(tool, 'execution_mode', '?')}'"
                    )
                    logger.logger.error(f"[AgentNodeHandler] {err}")
                    yield ErrorEvent(message=err, node_id=ctx.node_id).to_dict()
                    return

                if isinstance(tool, LLMEngineTool):
                    tool_call: Optional[ToolCall] = None
                    sub_failed = False
                    async for ev in tool.produce_tool_call_streaming(
                        params, planner_output, ctx
                    ):
                        etype = ev.get("type")
                        if etype == "reasoning_delta":
                            yield {
                                "type": "cua_delta",
                                "cuaId": cua_id,
                                "reasoning": ev.get("content", ""),
                                "kind": f"tool:{tool.name}",
                            }
                        elif etype == "tool_call":
                            tool_call = ev.get("result")
                        elif etype == "error":
                            sub_failed = True
                            err = ev.get("content", f"{tool.name} sub-LLM failed")
                            logger.logger.warning(f"[AgentNodeHandler] {err}")
                            inline_history.append({
                                "action": action_name,
                                "summary": title,
                                "result": f"failed: {err[:200]}",
                            })
                            last_execution_output = err
                            yield {
                                "type": "cua_end",
                                "cuaId": cua_id,
                                "status": "error",
                                "error": err,
                            }
                    if sub_failed:
                        continue
                    if tool_call is None:
                        err = f"LLMEngineTool '{tool.name}' did not produce a tool_call"
                        logger.logger.warning(f"[AgentNodeHandler] {err}")
                        inline_history.append({
                            "action": action_name,
                            "summary": title,
                            "result": f"failed: {err[:200]}",
                        })
                        last_execution_output = err
                        yield {
                            "type": "cua_end",
                            "cuaId": cua_id,
                            "status": "error",
                            "error": err,
                        }
                        continue
                else:
                    tool_call = tool.build_tool_call(params, planner_output)
                tool_call_id = f"call_{cua_id}"

                yield {
                    "type": "cua_update",
                    "cuaId": cua_id,
                    "content": {"type": tool_call.name, **tool_call.args},
                    "kind": "actor",
                }
                yield {
                    "type": "tool_call",
                    "id": tool_call_id,
                    "target": tool.target,
                    "name": tool_call.name,
                    "args": tool_call.args,
                }
                yield {
                    "type": "cua_end",
                    "cuaId": cua_id,
                    "status": "completed",
                    "title": title,
                    "action": {"type": tool_call.name, **tool_call.args},
                }

                inline_history.append({
                    "action": action_name,
                    "summary": title,
                    "result": "pending",
                })

                # When suspending on an ``ask_user`` call we must retain
                # its rendered args (prompt + options) so the next
                # invocation can pair the user's answer with the original
                # question and turn the pair into a cross-node
                # :class:`Clarification`.  See
                # :meth:`_maybe_record_ask_user_clarification`.
                extra_state: Dict[str, Any] = {}
                if tool.name == "ask_user":
                    extra_state["last_ask_user_args"] = dict(tool_call.args or {})

                yield NodeCompleteEvent(
                    node_id=ctx.node_id,
                    node_type=ctx.node_type,
                    is_node_completed=False,
                    handler_result={
                        "is_node_completed": False,
                        "waiting_for_execution": True,
                        "last_tool_call_id": tool_call_id,
                        "last_action": action_name,
                        "last_tool": tool.name,
                        "last_target": tool.target,
                        "inline_history": inline_history,
                        **extra_state,
                        # Carry any inline tool output (e.g. ``tool_web_search``,
                        # ``ppt_verify_layout``) that was produced earlier
                        # in **this same invocation** across the suspension
                        # boundary.  Without this the next invocation's
                        # ``_compose_last_execution_output`` only sees the
                        # engine tool's ``ctx.execution_result`` and the
                        # planner loses visibility of the inline result —
                        # which caused the orchestrator to re-issue
                        # identical ``tool_web_search`` calls every time
                        # it resumed from an engine tool suspension.
                        #
                        # IMPORTANT: only persist when the value was
                        # produced in this invocation
                        # (``inline_persist_fresh``).  Stale inline output
                        # inherited from a *prior* invocation must NOT be
                        # re-saved — otherwise the same observation
                        # (e.g. a verify_layout error report) gets
                        # re-injected across many engine suspensions and
                        # the planner keeps "fixing" something that's
                        # already fixed.  See trajectory
                        # 260426-035415 root cause.
                        "last_execution_output": last_execution_output,
                        "inline_last_execution_output": (
                            inline_persist if inline_persist_fresh else ""
                        ),
                        **self._skill_reads_state(ctx),
                    },
                    action_summary=title,
                ).to_dict()
                return

            yield NodeCompleteEvent(
                node_id=ctx.node_id,
                node_type=ctx.node_type,
                is_node_completed=False,
                handler_result={
                    "is_node_completed": False,
                    "inline_history": inline_history,
                    "last_execution_output": last_execution_output,
                    "inline_last_execution_output": (
                        inline_persist if inline_persist_fresh else ""
                    ),
                    "note": "reached MAX_INLINE_ITERATIONS; continuing next invocation",
                    **self._skill_reads_state(ctx),
                },
                action_summary="agent step batch",
            ).to_dict()

        except Exception as e:  # noqa: BLE001
            logger.logger.error(f"[AgentNodeHandler] unexpected error: {e}", exc_info=True)
            yield ErrorEvent(
                message=f"Agent node execution failed: {e}",
                node_id=ctx.node_id,
            ).to_dict()

    async def _run_inline_tool(
        self, tool: InlineTool, params: Dict[str, Any], ctx: NodeContext
    ) -> str:
        try:
            result = await tool.run(params, ctx)
            if isinstance(result, str):
                return result
            return str(result)[:20000]
        except Exception as e:  # noqa: BLE001
            logger.logger.warning(f"[InlineTool:{tool.name}] runner failed: {e}")
            return f"[{tool.name}] error: {e}"

    def _resolve_model(self, ctx: NodeContext) -> str:
        data = (ctx.node_dict or {}).get("data", {}) or {}
        return data.get("model") or ctx.planner_model or "gpt-4o-mini"

    async def _run_planner(
        self,
        planner: OfficePlanner,
        ctx: NodeContext,
        inline_history: List[Dict[str, Any]],
        last_execution_output: str,
        cua_id: str,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """跑一次 Planner.plan_streaming，把 reasoning_delta / plan_complete 转成
        handler 层 cua_* 事件。成功时通过 `_planner_output` 键把 PlannerOutput
        返回给调用方。"""
        # Render the desktop snapshot (open_windows / installed_apps /
        # active_window) so the Router can see what's already running and
        # which hwnds are available — crucial for avoiding double-launch
        # and for wiring `system_window_control` tile / activate calls.
        desktop_snapshot = format_desktop_snapshot(
            getattr(ctx, "uia_data", None),
            app_action_prefix="system_",
        )

        # Visual-first judgment: prepend the latest rendered window
        # screenshot (from the previous engine tool's snapshot) to the
        # attached_images list so the multimodal planner can SEE the
        # current document state instead of imagining bboxes from JSON.
        # Order is intentional — render first, then user-supplied
        # references — so the prompt's "labelled `current_render`"
        # pointer maps to the first image and downstream `attached_images`
        # entries remain the user's references in their original order.
        attached_images = list(self._extract_attached_images(ctx))
        last_render = self._extract_last_render_screenshot(ctx)
        if last_render:
            attached_images.insert(0, last_render)

        context_obj = PlannerAgentContext(
            user_goal=ctx.query or "",
            node_instruction=ctx.get_node_instruction(),
            history_md=(ctx.history_md or self._safe_history_md(ctx)),
            history=inline_history[-20:],
            attached_files_content=await self._safe_attached_files(ctx),
            attached_images=attached_images,
            additional_context=ctx.additional_context or "",
            skills_prompt=self._compose_skills_prompt(ctx),
            last_execution_output=last_execution_output,
            desktop_snapshot=desktop_snapshot,
            clarifications=list(ctx.clarifications or []),
        )

        async for ev in planner.plan_streaming(context_obj, ctx.log_folder):
            et = ev.get("type", "")
            if et == "reasoning_delta":
                yield {
                    "type": "cua_delta",
                    "cuaId": cua_id,
                    "reasoning": ev.get("content", ""),
                    "kind": ev.get("source", "planner"),
                }
            elif et == "plan_complete":
                yield {
                    "type": "planner_complete",
                    "content": {"vlm_plan": ev.get("content", {})},
                }
                yield {"_planner_output": PlannerOutput.from_dict(ev.get("content", {}))}
            elif et == "error":
                yield {
                    "type": "cua_end",
                    "cuaId": cua_id,
                    "status": "error",
                    "error": ev.get("content", "planner error"),
                }
                yield ErrorEvent(
                    message=ev.get("content", "planner error"),
                    node_id=ctx.node_id,
                ).to_dict()
                return

    async def _emit_stop(
        self,
        ctx: NodeContext,
        cua_id: str,
        title: str,
        planner_output: PlannerOutput,
        inline_history: List[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        yield {
            "type": "cua_end",
            "cuaId": cua_id,
            "status": "completed",
            "title": title,
            "action": {"type": "stop"},
        }
        completion_summary = (
            planner_output.completion_summary or "Agent node completed"
        )
        yield NodeCompleteEvent(
            node_id=ctx.node_id,
            node_type=ctx.node_type,
            is_node_completed=True,
            handler_result={
                "is_node_completed": True,
                "inline_history": inline_history,
                "node_completion_summary": completion_summary,
                **self._skill_reads_state(ctx),
            },
            action_summary=title,
            node_completion_summary=completion_summary,
        ).to_dict()

    def _extract_attached_images(self, ctx: NodeContext) -> List[str]:
        imgs: List[str] = []
        for item in ctx.attached_images or []:
            if not isinstance(item, dict):
                continue
            raw = item.get("base64")
            if not isinstance(raw, str):
                continue
            v = raw.strip()
            if not v:
                continue
            if v.startswith("data:") and "," in v:
                v = v.split(",", 1)[1]
            imgs.append(v)
        return imgs

    def _safe_history_md(self, ctx: NodeContext) -> str:
        try:
            return ctx.get_history_md() or ""
        except Exception:  # noqa: BLE001
            return ""

    @staticmethod
    def _skill_reads_state(ctx: NodeContext) -> Dict[str, Any]:
        """Return the ``read_files_list`` / ``read_files_content`` dict (if any).

        These keys are written by the ``read_file`` inline tool onto
        ``ctx.node_state``; we mirror them into every ``handler_result`` we
        emit so the next invocation's :meth:`_compose_skills_prompt` finds
        them — both in the suspended-on-engine case and in the
        ``waiting_for_execution=False`` end-of-batch case.
        """
        node_state = ctx.node_state or {}
        out: Dict[str, Any] = {}
        for key in ("read_files_list", "read_files_content"):
            val = node_state.get(key)
            if val is None:
                # Fallback: read straight from the previous handler_result
                # in case nothing was added this invocation.
                val = node_state.get("handler_result", {}).get(key)
            if val is not None:
                out[key] = val
        return out

    def _compose_skills_prompt(self, ctx: NodeContext) -> str:
        """Combine the static SKILL.md prompt with previously-read skill files.

        Skill workflows often span many planner turns (read parameter file →
        run a calculation script → draw component A → draw component B …).
        ``SkillFileReader`` accumulates each ``read_file`` output into a
        single rolling block (``Previously Read Skill Resources``) — we pin
        that block to the bottom of the skills section so the planner sees
        its previous reads on **every** step, not just the one immediately
        following the ``read_file`` call.

        Mirrors :func:`AutoCADAgentContext._get_full_skills_prompt` from the
        old per-app handler.
        """
        try:
            base = ctx.get_skills_prompt() if hasattr(ctx, "get_skills_prompt") else ""
        except Exception:  # noqa: BLE001
            base = ""

        node_state = ctx.node_state or {}
        accumulated = (
            node_state.get("read_files_content")
            or node_state.get("handler_result", {}).get("read_files_content")
            or ""
        )
        if not accumulated:
            return base

        read_list = (
            node_state.get("read_files_list")
            or node_state.get("handler_result", {}).get("read_files_list")
            or []
        )
        header = (
            f"\n\n## Previously Read Skill Resources ({len(read_list)} items)\n"
        )
        return (base or "") + header + accumulated

    async def _safe_attached_files(self, ctx: NodeContext) -> str:
        try:
            if hasattr(ctx, "get_attached_files_content"):
                return await ctx.get_attached_files_content()
        except Exception as e:  # noqa: BLE001
            logger.logger.warning(f"[AgentNodeHandler] attached files read failed: {e}")
        return ""

    @staticmethod
    def _reconcile_pending_history(
        inline_history: List[Dict[str, Any]],
        execution_result: Optional[Dict[str, Any]],
    ) -> None:
        """Flip the trailing ``pending`` entry to ``success`` / ``failed``.

        ``inline_history`` is the rolling log shown to the Router Planner
        as ``## Agent Step History``.  Engine-tool dispatches append a
        ``pending`` entry before suspending; this reconciler runs at the
        start of the next invocation so the planner sees the true
        outcome instead of a perpetually-pending row.
        """
        if not inline_history:
            return
        last = inline_history[-1]
        if not isinstance(last, dict) or last.get("result") != "pending":
            return
        if not isinstance(execution_result, dict) or not execution_result:
            # No resumed payload to reconcile against (rare — can happen
            # if the frontend hung up without sending ``execution_result``).
            # Leave as pending so the next planner call can still
            # notice something's off.
            return
        success = execution_result.get("success")
        if success is None:
            status_val = str(execution_result.get("status", "")).lower()
            success = status_val in ("success", "ok")
        if success:
            last["result"] = "success"
        else:
            err = execution_result.get("error") or execution_result.get("message") or ""
            err_short = str(err)[:160] if err else "non-success status"
            last["result"] = f"failed: {err_short}"

    def _maybe_record_ask_user_clarification(
        self, ctx: NodeContext, handler_state: Dict[str, Any]
    ) -> None:
        """If ``ctx.execution_result`` is an ``ask_user`` reply, reify
        it as a :class:`Clarification` and push it onto the workflow's
        ``FlowProcessor`` so *subsequent* nodes see it.

        Within the *current* node's planner loop the answer is already
        re-surfaced through ``last_execution_output`` (see
        :meth:`_compose_last_execution_output`), so we don't need to
        inject it into the current ``AgentContext`` — but every
        downstream node's first plan must start with the answer
        visible in its own ``## User Clarifications`` block.

        Gated on ``handler_state["last_tool"] == "ask_user"`` or the
        presence of a ``user_response`` key, mirroring the detection
        already used inside ``_compose_last_execution_output``.  We do
        this unconditionally (even if the user "dismissed" the
        dialog) — downstream nodes need to know the user declined to
        disambiguate so they can pick a safe default rather than
        loop.
        """
        er = ctx.execution_result
        if not isinstance(er, dict) or not er:
            return
        last_tool = str(handler_state.get("last_tool") or "")
        if last_tool != "ask_user" and "user_response" not in er:
            return

        try:
            from useit_studio.ai_run.agent_loop.action_models import (
                Clarification,
                _parse_selected_option,
                _parse_free_text,
            )
            from .tools.ask_user import render_user_response
        except Exception as exc:  # noqa: BLE001
            logger.logger.warning(
                "[AgentNodeHandler] clarification promotion skipped: %s", exc
            )
            return

        ask_args = handler_state.get("last_ask_user_args") or {}
        question = str(ask_args.get("prompt") or "").strip() or "(question unavailable)"
        options = ask_args.get("options") or []

        try:
            rendered = render_user_response(er)
        except Exception as exc:  # noqa: BLE001
            rendered = f"(render failed: {exc})"

        sid, label = _parse_selected_option(rendered, options)
        free = _parse_free_text(rendered)

        clar = Clarification(
            question=question,
            answer=rendered,
            selected_option_id=sid,
            selected_option_label=label,
            free_text=free,
            source="agent_node",
            source_node_id=ctx.node_id,
        )
        try:
            ctx.flow_processor.add_node_clarification(clar)
        except Exception as exc:  # noqa: BLE001
            logger.logger.warning(
                "[AgentNodeHandler] add_node_clarification failed: %s", exc
            )
            return
        logger.logger.info(
            "[AgentNodeHandler] recorded ask_user clarification "
            "(node=%s, option=%s, free_text=%s)",
            ctx.node_id, sid, bool(free),
        )

    def _compose_last_execution_output(
        self,
        ctx: NodeContext,
        handler_state: Dict[str, Any],
        *,
        inline_tail: str = "",
    ) -> str:
        """把前端回传的 execution_result / 可跨挂起保留的 inline 输出组成 last_execution_output。

        ``inline_tail`` 只应包含上一步**内联工具**（如 ``tool_web_search``）的
        文本，不要传入整段历史化的 ``last_execution_output``（那会重复堆叠
        引擎快照和 layout 报告）。
        """
        chunks: List[str] = []
        er = ctx.execution_result
        if isinstance(er, dict) and er:
            # Special case: the previous tool_call was ``ask_user``.  The
            # generic ``Payload keys: [...]`` rendering hides the actual
            # selection from the planner; pull the option + free-text out
            # so the next planning turn can act on the answer directly.
            last_tool = str(handler_state.get("last_tool") or "")
            if last_tool == "ask_user" or "user_response" in er:
                try:
                    from .tools.ask_user import render_user_response  # local import to avoid cycle
                    chunks.append(render_user_response(er))
                except Exception as e:  # noqa: BLE001
                    chunks.append(f"Previous ask_user answer: (render failed: {e})")
                if inline_tail:
                    chunks.append(str(inline_tail))
                return "\n\n".join(chunks)

            success = er.get("success")
            if success is None:
                status_val = str(er.get("status", "")).lower()
                success = status_val in ("success", "ok")
            chunks.append(
                f"Previous tool_call result: "
                f"{'SUCCESS' if success else 'FAILED'}\n"
                f"Payload keys: {list(er.keys())[:10]}"
            )
            err = er.get("error") or ""
            if err:
                chunks.append(f"Error: {err}")
            snap = er.get("snapshot")
            if snap is None and isinstance(er.get("data"), dict):
                snap = er["data"].get("snapshot")
            if isinstance(snap, dict):
                # NOTE: we deliberately do NOT dump the full snapshot JSON
                # (presentation_info / content.elements[].bounds / …) into
                # the planner's text prompt anymore.  That metadata-only
                # signal turned out to be a poor substitute for vision
                # — the model would try to imagine "does this list of
                # bboxes match the reference image?" and consistently get
                # it wrong (see investigation in conversation around
                # 260426).  Instead we surface a TINY one-liner here and
                # rely on the rendered-slide screenshot being attached as
                # an image to the multimodal call (see
                # ``_extract_last_render_screenshot`` and ``_run_planner``).
                pointer = self._compose_visual_pointer(snap)
                if pointer:
                    chunks.append(pointer)
                # Auto-run the PPT layout inspector on any returned PPT
                # snapshot.  If it finds issues, surface the one-line
                # headline so the planner is nudged to call
                # `ppt_verify_layout` (or fix directly).  This is a
                # belt-and-suspenders measure on top of the dedicated
                # verify tool — we don't want the model to silently
                # `stop` on a broken slide just because it forgot to
                # verify.
                auto_warn = self._auto_layout_warning(snap)
                if auto_warn:
                    chunks.append(auto_warn)
        if inline_tail:
            chunks.append(str(inline_tail))
        return "\n\n".join(chunks)

    @staticmethod
    def _auto_layout_warning(snapshot: Dict[str, Any]) -> str:
        """Return a one-line layout headline for PPT snapshots; empty if n/a.

        Kept deliberately terse — the full breakdown is available via
        ``ppt_verify_layout``.  Here we only surface "you have problems,
        go check" so the planner doesn't skip verification.
        """
        # Only run for PPT-shaped snapshots; Excel / Word / AutoCAD have
        # their own layouts this checker doesn't understand.
        is_ppt = (
            isinstance(snapshot.get("presentation_info"), dict)
            or isinstance(snapshot.get("content"), dict)
            and isinstance(snapshot["content"].get("current_slide"), dict)
        )
        if not is_ppt:
            return ""
        try:
            from .tools.ppt.layout_inspector import inspect_snapshot
        except Exception:  # noqa: BLE001
            return ""
        try:
            report = inspect_snapshot(snapshot)
        except Exception as e:  # noqa: BLE001
            logger.logger.debug(f"[layout_inspector] auto-check skipped: {e}")
            return ""
        if not report.has_issues:
            return ""
        # Phrased as a *hint*, not a verdict — the bbox geometry check is a
        # cheap pre-pass; the actual ship/no-ship judgment is the visual
        # `ppt_verify_layout` review (vision LLM over the rendered slide).
        # Some of these geometry flags are false positives that the visual
        # review will dismiss (e.g. `y=-6.67` on a logical wrapper that the
        # screenshot shows comfortably on-canvas).  We surface the count
        # so the planner knows there's *something* to look at, but the
        # tool call is the source of truth.
        return (
            f"ℹ Engine geometry pre-pass flagged {report.error_count} "
            f"error(s) and {report.warning_count} warning(s) on the "
            f"current slide.  These are HINTS — call `ppt_verify_layout` "
            f"for the visual review (which compares the rendered "
            f"screenshot with the user's reference image and decides "
            f"what's actually a defect).  Do this **before `stop`**."
        )

    @staticmethod
    def _compose_visual_pointer(snapshot: Dict[str, Any]) -> str:
        """Pointer to the attached screenshot + a *compact* handle inventory.

        Two responsibilities, kept narrow:

        1. Tell the planner that the rendered window is attached as an
           image (labelled ``current_render``) and that fidelity / quality
           judgments must come from looking at that pixel content, not
           from numbers.  This part is the "visual-first" stance from the
           260426 redesign.
        2. List the *addressable* handle inventory of the current slide —
           one line per element, ``handle_id | type | "first 30 chars of
           text"`` — so when the planner picks ``ppt_update_element`` it
           passes a handle that ACTUALLY EXISTS in the slide right now.
           This was the single biggest cause of the
           "update_element fails → fall back to render_mode='create' →
           handles get renamed → next update_element fails again" loop
           we hit in trajectory 260426-022634 (`hero-text.*` vs
           ``hero-content.*``).

        Deliberately *excluded* (and stays excluded — we learned the hard
        way that the model uses these for visual-fidelity guesses):

          * bounds / x / y / w / h
          * fill / line / font colours and sizes
          * z-order, rotation, layer hierarchy

        The inventory here is a *registry of what is editable*, NOT a
        layout description.  All visual judgment still comes from the
        attached screenshot.
        """
        if not isinstance(snapshot, dict):
            return ""

        lines: List[str] = []

        pres = snapshot.get("presentation_info") if isinstance(
            snapshot.get("presentation_info"), dict
        ) else None
        content = snapshot.get("content") if isinstance(
            snapshot.get("content"), dict
        ) else None

        cur_slide = (content or {}).get("current_slide") if content else None
        elements: List[Dict[str, Any]] = []
        if isinstance(cur_slide, dict) and isinstance(cur_slide.get("elements"), list):
            elements = [e for e in cur_slide["elements"] if isinstance(e, dict)]

        if pres or content:
            sw = (pres or {}).get("slide_width")
            sh = (pres or {}).get("slide_height")
            cur = (pres or {}).get("current_slide")
            cnt = (pres or {}).get("slide_count")

            facts: List[str] = []
            if isinstance(sw, (int, float)) and isinstance(sh, (int, float)):
                facts.append(f"canvas={int(sw)}×{int(sh)}pt")
            if cur is not None:
                facts.append(f"slide={cur}/{cnt if cnt is not None else '?'}")
            if elements:
                facts.append(f"elements={len(elements)}")

            if facts:
                lines.append("Current document state: " + ", ".join(facts) + ".")

        has_shot = bool(snapshot.get("screenshot") or snapshot.get("screenshot_base64"))
        if has_shot:
            lines.append(
                "**The rendered application window is attached as an image** "
                "(labelled `current_render`).  "
                "Judge the current state — fidelity vs. the reference, "
                "alignment, overflow, visual quality — by **looking at it**, "
                "not by imagining bbox numbers.  Per-element bbox / colour / "
                "font dumps are intentionally omitted because metadata-only "
                "judgment is unreliable."
            )
        else:
            lines.append(
                "(No rendered screenshot returned this turn.  If you need "
                "to inspect the document state visually, request a "
                "snapshot — do NOT guess fidelity from history alone.)"
            )

        # Handle inventory — IDs only, no geometry.  This is the registry
        # the planner must use when picking handle_ids for update_element /
        # delete_element / arrange_elements; handle_ids drift on every
        # render_mode='create' so historical handles in earlier turns are
        # often stale.
        if elements:
            inventory_lines = AgentNodeHandler._format_handle_inventory(elements)
            if inventory_lines:
                lines.append("")
                lines.append(
                    "## Editable handle inventory (current slide)\n"
                    "Use these `handle_id`s — and ONLY these — when calling "
                    "`ppt_update_element` / `ppt_delete_element` / "
                    "`ppt_arrange_elements`.  Handles you remember from "
                    "earlier turns may have been invalidated by a "
                    "`render_mode='create'` render and will fail with "
                    "\"Shape not found\".\n"
                )
                lines.extend(inventory_lines)

        return "\n".join(lines)

    @staticmethod
    def _format_handle_inventory(
        elements: List[Dict[str, Any]],
        *,
        max_lines: int = 60,
        text_preview_len: int = 30,
    ) -> List[str]:
        """Render an inventory line per element: ``- `handle_id` | type | "preview"``.

        Skips elements that have no usable handle_id (no point listing
        something the planner can't address).  Caps at ``max_lines`` to
        keep token budget bounded; appends an ellipsis line when truncated.
        """
        out: List[str] = []
        seen = 0
        total_addressable = 0
        for el in elements:
            hid = el.get("handle_id") or el.get("id") or el.get("name")
            if not hid:
                continue
            total_addressable += 1
            if seen >= max_lines:
                continue
            tn = el.get("type_name") or el.get("type") or "shape"
            txt = el.get("text") or ""
            if not isinstance(txt, str):
                txt = ""
            txt = txt.strip().replace("\n", " ")
            if len(txt) > text_preview_len:
                txt = txt[: text_preview_len - 1] + "…"
            preview = f' | "{txt}"' if txt else ""
            out.append(f"- `{hid}` | {tn}{preview}")
            seen += 1
        if total_addressable > seen:
            out.append(
                f"- …and {total_addressable - seen} more addressable "
                f"element(s) omitted (cap={max_lines}).  Re-run a snapshot "
                f"action if you need a specific one not listed."
            )
        return out

    @staticmethod
    def _extract_last_render_screenshot(ctx: NodeContext) -> Optional[str]:
        """Return base64 PNG of the latest engine-tool's rendered window.

        Pulled from ``ctx.execution_result.snapshot.screenshot`` (or the
        ``data.snapshot`` variant some controllers use).  Empty / missing
        → ``None``.  This is what we attach as a *second* image to the
        planner's multimodal call so it can actually see what got drawn,
        instead of judging from JSON bboxes alone.
        """
        er = getattr(ctx, "execution_result", None)
        if not isinstance(er, dict):
            return None
        snap = er.get("snapshot")
        if snap is None and isinstance(er.get("data"), dict):
            snap = er["data"].get("snapshot")
        if not isinstance(snap, dict):
            return None
        for key in ("screenshot", "screenshot_base64"):
            v = snap.get(key)
            if isinstance(v, str) and v.strip():
                s = v.strip()
                if s.startswith("data:") and "," in s:
                    s = s.split(",", 1)[1]
                return s
        return None
