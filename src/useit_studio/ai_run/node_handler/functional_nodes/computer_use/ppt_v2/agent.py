"""
PPT Engine Agent

PPTEngineAgent is a subclass of OfficeAgent designed for the PPT Local Engine API.

It integrates a ToolRegistry so the Router Planner's decision is dispatched to
the correct tool (LLM-powered or passthrough).  The ``step_streaming`` override
handles async tool execution with UI-visible reasoning deltas.

Legacy Mode A/B/C routing is preserved as a fallback for backward compatibility.
"""

from typing import Optional, Dict, Any, Tuple, AsyncGenerator

from ..office_agent.base_agent import OfficeAgent, OfficeAgentConfig
from ..office_agent.models import (
    PlannerOutput,
    OfficeAction,
    ActionEvent,
    AgentStep,
    AgentContext,
    OfficeAppType,
)
from .tools.base import ToolRegistry, ToolRequest, ToolResult, LLMTool
from useit_studio.ai_run.utils.logger_utils import LoggerUtils


class PPTEngineAgent(OfficeAgent):
    """
    PPT Local Engine Agent — Router + Tool Registry architecture.

    The planner acts as a lightweight router; actual content generation
    (layout, code, chart data) is delegated to registered tools.
    """

    def __init__(
        self,
        *args,
        tool_registry: Optional[ToolRegistry] = None,
        system_prompt_template: str = "",
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self._ppt_logger = LoggerUtils(component_name="PPTEngineAgent")
        self.tool_registry = tool_registry or ToolRegistry()
        self._system_prompt_template = system_prompt_template

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _slide_has_elements(context: AgentContext) -> bool:
        """Return True if the current slide contains any shapes."""
        snapshot = context.current_snapshot
        if snapshot and hasattr(snapshot, "to_context_format"):
            ctx = snapshot.to_context_format()
            return bool(ctx and "handle_id" in ctx)
        return False

    # ------------------------------------------------------------------
    # Build a ToolRequest from PlannerOutput + AgentContext
    # ------------------------------------------------------------------

    def _build_tool_request(
        self,
        planner_output: PlannerOutput,
        context: AgentContext,
    ) -> ToolRequest:
        snapshot = context.current_snapshot
        screenshot = None
        shapes_ctx = ""
        sw, sh = 960.0, 540.0
        project_files = ""

        if snapshot:
            screenshot = getattr(snapshot, "screenshot", None)
            if hasattr(snapshot, "to_context_format"):
                shapes_ctx = snapshot.to_context_format()
            sw = getattr(snapshot, "slide_width", 960.0) or 960.0
            sh = getattr(snapshot, "slide_height", 540.0) or 540.0
            project_files = getattr(snapshot, "project_files", "") or ""

        return ToolRequest(
            description=planner_output.description or planner_output.title or "",
            params=planner_output.tool_params or {},
            screenshot_base64=screenshot,
            slide_width=sw,
            slide_height=sh,
            shapes_context=shapes_ctx,
            attached_images=context.attached_images or [],
            project_files_context=project_files or context.additional_context or "",
        )

    # ------------------------------------------------------------------
    # Override step_streaming: Router Planner → Tool dispatch
    # ------------------------------------------------------------------

    async def step_streaming(
        self,
        context: AgentContext,
        log_dir: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Single-step with streaming.

        1. Router Planner decides which tool + description/params.
        2. ToolRegistry dispatches to the right tool.
        3. LLM tools stream their reasoning; passthrough tools return immediately.
        """
        total_token_usage: Dict[str, int] = {}

        try:
            # ── 0. Dynamic prompt: trim detail sections for blank slides ──
            if self._system_prompt_template:
                has_elements = self._slide_has_elements(context)
                action_table = self.tool_registry.build_router_action_table(
                    has_elements=has_elements,
                )
                self.planner.system_prompt = self._system_prompt_template.replace(
                    "{action_table}", action_table,
                )

            # ── 1. Router Planner ────────────────────────────────────────
            planner_output: Optional[PlannerOutput] = None

            async for event in self.planner.plan_streaming(context, log_dir):
                yield event
                if event.get("type") == "plan_complete":
                    planner_output = PlannerOutput.from_dict(
                        event.get("content", {}),
                        thinking=event.get("content", {}).get("Thinking", ""),
                    )
                    planner_tokens = event.get("token_usage", {})
                    for model, tokens in planner_tokens.items():
                        total_token_usage[model] = total_token_usage.get(model, 0) + tokens

            if not planner_output:
                yield {"type": "error", "content": "Planner did not return a valid result"}
                return

            self._ppt_logger.logger.info(
                f"[PPTEngineAgent] Router decision — Action: {planner_output.next_action}, "
                f"Description: {(planner_output.description or '')[:60]}"
            )

            # ── 2. Check completion ──────────────────────────────────────
            if planner_output.is_milestone_completed or planner_output.next_action == "stop":
                yield {
                    "type": "step_complete",
                    "step": AgentStep(
                        planner_output=planner_output,
                        action=OfficeAction.stop(),
                        reasoning_text="Task completed",
                        token_usage=total_token_usage,
                    ),
                }
                return

            # ── 3. Tool dispatch ─────────────────────────────────────────
            tool = self.tool_registry.get(planner_output.next_action)

            if tool is not None:
                request = self._build_tool_request(planner_output, context)
                tool_result: Optional[ToolResult] = None

                async for event in tool.execute_streaming(request):
                    etype = event.get("type", "")
                    if etype == "reasoning_delta":
                        yield event
                    elif etype == "tool_result":
                        tool_result = event["result"]
                    elif etype == "error":
                        yield event
                        return

                if tool_result is None:
                    yield {"type": "error", "content": f"Tool '{planner_output.next_action}' returned no result"}
                    return

                # Emit tool_call event
                yield {
                    "type": "tool_call",
                    "id": f"call_ppt_{self.node_id}_step",
                    "target": "ppt",
                    "name": tool_result.name,
                    "args": tool_result.args,
                }

                yield {
                    "type": "step_complete",
                    "step": AgentStep(
                        planner_output=planner_output,
                        action=None,
                        reasoning_text=tool_result.reasoning or f"Tool: {planner_output.next_action}",
                        token_usage=total_token_usage,
                    ),
                }
                return

            # ── 4. Legacy fallback (Mode A/B/C) ─────────────────────────
            tool_call_name, tool_call_args = self._build_tool_call_args(planner_output)

            if tool_call_name is None:
                yield {"type": "error", "content": "Planner returned action but no executable content"}
                return

            if tool_call_name == "execute_code" and planner_output.code:
                action: Optional[OfficeAction] = OfficeAction.execute_code(
                    code=planner_output.code,
                    language=planner_output.language or "PowerShell",
                )
                yield ActionEvent(action=action).to_dict()
            else:
                action = None

            yield {
                "type": "tool_call",
                "id": f"call_ppt_{self.node_id}_step",
                "target": "ppt",
                "name": tool_call_name,
                "args": tool_call_args,
            }

            yield {
                "type": "step_complete",
                "step": AgentStep(
                    planner_output=planner_output,
                    action=action,
                    reasoning_text=f"Legacy action: {tool_call_name}",
                    token_usage=total_token_usage,
                ),
            }

        except Exception as e:
            self._ppt_logger.logger.error(f"[PPTEngineAgent] step_streaming failed: {e}", exc_info=True)
            yield {"type": "error", "content": str(e)}

    # ------------------------------------------------------------------
    # Legacy _build_tool_call_args (kept for backward compatibility)
    # ------------------------------------------------------------------

    def _build_tool_call_args(self, planner_output: PlannerOutput) -> Tuple[Optional[str], Optional[dict]]:
        action_name = planner_output.next_action

        # Mode A: structured actions
        if action_name == "actions" and planner_output.actions:
            self._ppt_logger.logger.info(
                f"[PPTEngineAgent] Legacy Mode A — {len(planner_output.actions)} action(s)"
            )
            args: Dict[str, Any] = {
                "actions": planner_output.actions,
                "return_screenshot": planner_output.return_screenshot,
                "current_slide_only": planner_output.current_slide_only,
            }
            return "step", args

        # Mode B: execute_code
        if planner_output.code:
            self._ppt_logger.logger.info(
                f"[PPTEngineAgent] Legacy Mode B — {planner_output.language} code "
                f"({len(planner_output.code)} chars)"
            )
            args = {
                "code": planner_output.code,
                "language": planner_output.language or "PowerShell",
                "return_screenshot": planner_output.return_screenshot,
                "current_slide_only": planner_output.current_slide_only,
                "timeout": planner_output.timeout,
            }
            return "step", args

        # Mode C: skill
        if action_name == "skill" and planner_output.skill_id:
            self._ppt_logger.logger.info(
                f"[PPTEngineAgent] Legacy Mode C — skill_id={planner_output.skill_id}"
            )
            args = {
                "skill_id": planner_output.skill_id,
                "script_path": planner_output.script_path or "",
                "parameters": planner_output.parameters or {},
                "language": planner_output.language or "PowerShell",
                "return_screenshot": planner_output.return_screenshot,
                "current_slide_only": planner_output.current_slide_only,
                "timeout": planner_output.timeout,
            }
            return "step", args

        # Word/Excel skill actions
        if action_name in ("execute_script", "read_file", "read_default_reference"):
            return super()._build_tool_call_args(planner_output)

        self._ppt_logger.logger.warning(
            f"[PPTEngineAgent] Cannot build tool_call: action={action_name!r}, "
            f"has_code={bool(planner_output.code)}, has_actions={bool(planner_output.actions)}"
        )
        return None, None
