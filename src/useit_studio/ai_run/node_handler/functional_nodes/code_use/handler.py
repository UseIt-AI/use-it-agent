"""
Code Use Node Handler

目标：
1. 根据节点指令生成 Python 代码
2. 通过 tool_call(target=code, name=execute_python) 交给前端/Local Engine 在用户电脑执行
3. 收到 execution_result 后完成节点
"""

from __future__ import annotations

import os
import re
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from useit_studio.ai_run.llm_utils import call_llm
from useit_studio.ai_run.node_handler.base_v2 import (
    BaseNodeHandlerV2,
    ErrorEvent,
    NodeCompleteEvent,
    NodeContext,
)
from useit_studio.ai_run.utils.logger_utils import LoggerUtils


logger = LoggerUtils(component_name="CodeUseNodeHandlerV2")


def _api_key_for_planner_model(model: str, api_keys: Optional[Dict[str, str]]) -> Optional[str]:
    """与 GUI VLMClient 一致：按模型名从 planner_api_keys / 环境变量选取密钥。"""
    keys = api_keys or {}
    ml = (model or "").lower()
    if "gemini" in ml or "google" in ml:
        return keys.get("GOOGLE_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if "claude" in ml or "anthropic" in ml:
        return (
            keys.get("ANTHROPIC_API_KEY")
            or keys.get("CLAUDE_API_KEY")
            or os.getenv("ANTHROPIC_API_KEY")
            or os.getenv("CLAUDE_API_KEY")
        )
    return keys.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")


class CodeUseNodeHandlerV2(BaseNodeHandlerV2):
    @classmethod
    def supported_types(cls) -> List[str]:
        return ["code-use", "code_use"]

    async def execute(self, ctx: NodeContext) -> AsyncGenerator[Dict[str, Any], None]:
        cua_id = f"code_{uuid.uuid4().hex[:8]}_{ctx.node_id}"
        handler_state = ctx.node_state.get("handler_result", {}) if ctx.node_state else {}

        try:
            # 防止重复执行：已经完成且没有新回调时，直接返回完成事件
            if handler_state.get("is_node_completed") and ctx.execution_result is None:
                completion_summary = handler_state.get("node_completion_summary", "Code execution completed")
                yield NodeCompleteEvent(
                    node_id=ctx.node_id,
                    node_type=ctx.node_type,
                    is_node_completed=True,
                    handler_result=handler_state,
                    action_summary="Already completed",
                    node_completion_summary=completion_summary,
                ).to_dict()
                return

            # 首次进入节点，发送 node_start
            if self._is_first_call(ctx):
                yield {
                    "type": "node_start",
                    "nodeId": ctx.node_id,
                    "title": ctx.get_node_title(),
                    "nodeType": ctx.node_type,
                    "instruction": ctx.get_node_instruction(),
                }

            # 有 execution_result：处理回调并结束节点
            if ctx.execution_result is not None:
                async for event in self._handle_execution_callback(ctx, cua_id, ctx.execution_result):
                    yield event
                return

            # 没有 execution_result：如果已在等待执行，重发上次 tool_call（避免重复生成代码）
            if handler_state.get("waiting_for_execution") and handler_state.get("last_generated_code"):
                code = handler_state["last_generated_code"]
                tool_call_id = handler_state.get("last_tool_call_id") or f"call_code_{ctx.node_id}_{uuid.uuid4().hex[:8]}"
                timeout = int(handler_state.get("timeout", 60))
                artifacts_glob = handler_state.get("artifacts_glob") or ["outputs/**/*", "*.csv", "*.json", "*.txt", "*.png"]
                max_output_chars = int(handler_state.get("max_output_chars", 65536))
                async for event in self._emit_code_tool_call(
                    ctx=ctx,
                    cua_id=cua_id,
                    code=code,
                    tool_call_id=tool_call_id,
                    timeout=timeout,
                    artifacts_glob=artifacts_glob,
                    max_output_chars=max_output_chars,
                    title="Re-send python execution",
                ):
                    yield event
                return

            # 生成 Python 代码并发起 tool_call
            generated_code, model_reasoning = await self._generate_python_code(ctx)
            tool_call_id = f"call_code_{ctx.node_id}_{uuid.uuid4().hex[:8]}"
            timeout = 60
            artifacts_glob = ["outputs/**/*", "*.csv", "*.json", "*.txt", "*.png", "*.md"]
            max_output_chars = 65536

            async for event in self._emit_code_tool_call(
                ctx=ctx,
                cua_id=cua_id,
                code=generated_code,
                tool_call_id=tool_call_id,
                timeout=timeout,
                artifacts_glob=artifacts_glob,
                max_output_chars=max_output_chars,
                title="Execute Python on local machine",
                reasoning=model_reasoning,
            ):
                yield event

        except Exception as exc:
            error_msg = f"Code Use node execution failed: {exc}"
            logger.logger.error(error_msg, exc_info=True)
            yield {
                "type": "cua_end",
                "cuaId": cua_id,
                "status": "error",
                "error": error_msg,
            }
            yield ErrorEvent(message=error_msg, node_id=ctx.node_id).to_dict()

    async def _generate_python_code(self, ctx: NodeContext) -> Tuple[str, str]:
        instruction = ctx.get_node_instruction() or ctx.query or ""
        history_md = ctx.get_history_md() if ctx.flow_processor else ""
        attached_files_content = ""
        if hasattr(ctx, "get_attached_files_content"):
            attached_files_content = await ctx.get_attached_files_content(max_files=2)

        system_prompt = (
            "You are a senior Python engineer.\n"
            "Generate executable Python code for the user's task.\n"
            "Rules:\n"
            "1) Return only Python code in one fenced code block.\n"
            "2) Do not ask questions.\n"
            "3) Prefer standard library.\n"
            "4) Save outputs to ./outputs when useful.\n"
            "5) Print concise progress and final result."
        )

        user_prompt = (
            f"User goal:\n{ctx.query or '(empty)'}\n\n"
            f"Node instruction:\n{instruction}\n\n"
            f"Workflow context:\n{history_md or '(none)'}\n\n"
            f"Attached files context:\n{attached_files_content or '(none)'}\n\n"
            "Now produce Python code."
        )

        response = await call_llm(
            messages=[user_prompt],
            model=ctx.planner_model,
            system_prompt=system_prompt,
            api_key=_api_key_for_planner_model(ctx.planner_model, ctx.planner_api_keys),
            temperature=0.2,
            max_tokens=3000,
        )
        raw = (response.content or "").strip()
        code = self._extract_code_block(raw) or raw
        if not code.strip():
            raise ValueError("LLM returned empty python code")
        return code, (raw[:400] + ("..." if len(raw) > 400 else ""))

    async def _emit_code_tool_call(
        self,
        ctx: NodeContext,
        cua_id: str,
        code: str,
        tool_call_id: str,
        timeout: int,
        artifacts_glob: List[str],
        max_output_chars: int,
        title: str,
        reasoning: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        step_cua_id = f"{cua_id}_exec"
        action_dict = {
            "type": "execute_python",
            "timeout": timeout,
            "cwd_mode": "project",
            "artifacts_glob": artifacts_glob,
        }

        yield {
            "type": "cua_start",
            "cuaId": step_cua_id,
            "step": 1,
            "title": title,
            "nodeId": ctx.node_id,
        }
        yield {
            "type": "cua_delta",
            "cuaId": step_cua_id,
            "reasoning": reasoning or "Generate Python and execute on local machine.",
            "kind": "planner",
        }
        yield {
            "type": "cua_update",
            "cuaId": step_cua_id,
            "content": action_dict,
            "kind": "planner",
        }
        yield {
            "type": "tool_call",
            "id": tool_call_id,
            "target": "code",
            "name": "execute_python",
            "args": {
                "code": code,
                "timeout": timeout,
                "cwd_mode": "project",
                "artifacts_glob": artifacts_glob,
                "max_output_chars": max_output_chars,
            },
        }
        yield {
            "type": "cua_end",
            "cuaId": step_cua_id,
            "status": "completed",
            "title": title,
            "action": action_dict,
        }

        yield NodeCompleteEvent(
            node_id=ctx.node_id,
            node_type=ctx.node_type,
            is_node_completed=False,
            handler_result={
                "is_node_completed": False,
                "waiting_for_execution": True,
                "last_tool_call_id": tool_call_id,
                "last_generated_code": code,
                "timeout": timeout,
                "artifacts_glob": artifacts_glob,
                "max_output_chars": max_output_chars,
            },
            action_summary=title,
            node_completion_summary="Waiting local Python execution result",
        ).to_dict()

    async def _handle_execution_callback(
        self,
        ctx: NodeContext,
        cua_id: str,
        execution_result: Dict[str, Any],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        success, summary, result_payload = self._summarize_execution_result(execution_result)
        step_cua_id = f"{cua_id}_result"

        yield {
            "type": "cua_start",
            "cuaId": step_cua_id,
            "step": 2,
            "title": "Receive local execution result",
            "nodeId": ctx.node_id,
        }
        yield {
            "type": "cua_delta",
            "cuaId": step_cua_id,
            "reasoning": summary,
            "kind": "planner",
        }
        yield {
            "type": "cua_end",
            "cuaId": step_cua_id,
            "status": "completed" if success else "error",
            "title": "Python execution completed" if success else "Python execution failed",
        }

        yield NodeCompleteEvent(
            node_id=ctx.node_id,
            node_type=ctx.node_type,
            is_node_completed=True,
            handler_result={
                "is_node_completed": True,
                "success": success,
                "execution_result": result_payload,
                "node_completion_summary": summary,
            },
            action_summary="Local Python executed" if success else "Local Python failed",
            node_completion_summary=summary,
        ).to_dict()

    def _summarize_execution_result(self, execution_result: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        status = str(execution_result.get("status") or "").lower()
        error = execution_result.get("error")
        result = execution_result.get("result")
        payload = result if isinstance(result, dict) else execution_result

        stdout = str(payload.get("stdout") or "")
        stderr = str(payload.get("stderr") or "")
        exit_code = payload.get("exit_code")
        timed_out = bool(payload.get("timed_out", False))

        status_success = status == "success" or status == ""
        payload_success = (not timed_out) and (exit_code in (0, None))
        success = status_success and payload_success and not error

        stdout_preview = stdout[:400].strip()
        stderr_preview = stderr[:400].strip()

        if success:
            summary = "Python executed successfully."
            if stdout_preview:
                summary += f"\nstdout: {stdout_preview}"
            if payload.get("artifacts"):
                summary += f"\nartifacts: {len(payload.get('artifacts', []))} files"
        else:
            summary = "Python execution failed."
            if timed_out:
                summary += " timed out."
            if exit_code not in (None, 0):
                summary += f" exit_code={exit_code}."
            if error:
                summary += f" error={error}"
            elif stderr_preview:
                summary += f" stderr={stderr_preview}"
        return success, summary.strip(), payload

    def _extract_code_block(self, text: str) -> Optional[str]:
        # 优先 python fenced block
        match = re.search(r"```python\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        # 其次任意 fenced block
        match = re.search(r"```\s*(.*?)```", text, flags=re.DOTALL)
        if match:
            return match.group(1).strip()
        return None
