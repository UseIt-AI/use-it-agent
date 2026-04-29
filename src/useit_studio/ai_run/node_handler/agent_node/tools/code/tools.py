"""Code tools —— execute_python 专用协议。"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, TYPE_CHECKING

from ..protocol import EngineTool, ToolCall

if TYPE_CHECKING:
    from ...models import (
        PlannerOutput,
    )


class CodeExecutePython(EngineTool):
    """`execute_python` Local Engine 协议：name 固定 "execute_python"，args 拍扁。

    Planner 有时会把代码塞进 `planner_output.code` 而非 `tool_params["code"]`，
    这里两处兜底。
    """

    name = "code_execute_python"
    group: ClassVar[str] = "code"
    target: ClassVar[str] = "code"
    is_destructive = True  # 本地执行任意代码，默认危险
    router_hint = (
        "Run arbitrary Python on the user's machine (project cwd). "
        "Params: code (str), timeout (int seconds, default 120), artifacts_glob (optional)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "code": {"type": "string"},
            "timeout": {"type": "integer", "default": 120},
            "cwd_mode": {"type": "string", "default": "project"},
            "artifacts_glob": {"type": "string", "default": "**/*"},
            "max_output_chars": {"type": "integer", "default": 8000},
        },
        "required": ["code"],
    }

    def build_tool_call(
        self, params: Dict[str, Any], planner_output: "PlannerOutput"
    ) -> ToolCall:
        code = params.get("code", "") or getattr(planner_output, "code", "") or ""
        return ToolCall(
            name="execute_python",
            args={
                "code": code,
                "timeout": int(params.get("timeout", 120) or 120),
                "cwd_mode": params.get("cwd_mode", "project"),
                "artifacts_glob": params.get("artifacts_glob", "**/*"),
                "max_output_chars": int(params.get("max_output_chars", 8000) or 8000),
            },
        )


TOOLS = [CodeExecutePython()]
