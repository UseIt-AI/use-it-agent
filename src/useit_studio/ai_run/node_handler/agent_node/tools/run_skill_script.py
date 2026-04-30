"""tool_run_skill_script —— 在服务器端执行 skill 自带的 Python 脚本（inline）。

迁移自 ``functional_nodes/computer_use/autocad/core.py:_run_skill_script``。

什么时候用
----------
Skill 经常带一段**纯计算**的 Python 脚本：把用户给的高层规格（``"R200"``、
``"1:25"``、各种标高）展开成具体坐标 / 尺寸表 / 元素 JSON。让 Planner 自
己心算这些是错位灾难现场，也不该走 AutoCAD COM —— 这是离线计算，不需要
任何 desktop 进程。

实现
----
- 用 ``SkillFileReader`` 解析 ``script_path``（搜遍所有已加载的 skill）。
- ``subprocess.run([sys.executable, script, base_dir], stdin=input_json,
  capture_output=True, text=True, timeout=...)`` 同步执行。
- 解析 stdout 为 JSON，作为 inline tool 输出回灌给 Planner。

为什么是 inline，不是 engine
---------------------------
原 AutoCAD 实现里这个 action 走 **本地** 执行，不下发 ``tool_call`` 也不挂
起 handler。脚本是 server 自带的可信代码（来自 skill 仓），结果一行 JSON
就能描述 —— 没必要绕一圈 frontend / Local Engine。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any, Dict, TYPE_CHECKING

from useit_studio.ai_run.skills import SkillFileReader
from useit_studio.ai_run.utils.logger_utils import LoggerUtils

from .protocol import InlineTool, PermissionResult

if TYPE_CHECKING:
    from useit_studio.ai_run.node_handler.base_v2 import NodeContext

logger = LoggerUtils(component_name="Tool.run_skill_script")

_DEFAULT_TIMEOUT_SEC = 30
_MAX_TIMEOUT_SEC = 300
_MAX_OUTPUT_CHARS = 20_000


class RunSkillScriptTool(InlineTool):
    name = "run_skill_script"
    group = ""  # standalone — generic skill helper
    router_hint = (
        "Run a Python helper script that ships with a skill; receives "
        "`input_json` on stdin, returns parsed JSON from stdout.  Use for "
        "deterministic coordinate / parameter pre-computation.  Params: "
        "script_path (str), input_json (object), timeout (int, optional)."
    )
    router_detail = (
        "## `run_skill_script` — Execute a Skill-Bundled Python Script\n\n"
        "Inline tool.  Runs `script_path` (relative to a skill's base "
        "directory) as a subprocess.  The script:\n"
        "1. Receives `input_json` (any JSON-serialisable object) on **stdin**.\n"
        "2. Prints a single JSON document on **stdout**.\n"
        "3. Receives the skill's base directory as `argv[1]` so it can locate "
        "sibling resource files.\n\n"
        "### When to use\n"
        "When a skill provides a calculation script (typical naming: "
        "`scripts/calculate_*.py`).  Use it to pre-compute coordinates / "
        "dimensions / payloads **before** any drawing call — the planner "
        "should *not* re-derive coordinates by hand.\n\n"
        "### Params\n"
        "```json\n"
        "{\n"
        "  \"script_path\": \"scripts/calculate_drawing.py\",\n"
        "  \"input_json\": {\n"
        "    \"spec\": \"R200\",\n"
        "    \"scale\": \"1:25\",\n"
        "    \"channel_bottom_elevation\": 1670.50\n"
        "  },\n"
        "  \"timeout\": 30\n"
        "}\n"
        "```\n\n"
        "The script's parsed JSON output appears as the next planner turn's "
        "`Last Action Result`.  Drop it directly into `autocad_draw_from_json` "
        "(or wherever) — do NOT recompute the values yourself."
    )
    is_read_only = False  # runs subprocess; treat as side-effecting just in case
    input_schema = {
        "type": "object",
        "properties": {
            "script_path": {
                "type": "string",
                "description": (
                    "Path relative to the skill's base directory, e.g. "
                    "`scripts/calculate_drawing.py`."
                ),
            },
            "input_json": {
                "type": "object",
                "description": (
                    "Arbitrary JSON-serialisable input handed to the script "
                    "via stdin.  Defaults to `{}`."
                ),
                "default": {},
            },
            "timeout": {
                "type": "integer",
                "default": _DEFAULT_TIMEOUT_SEC,
                "minimum": 1,
                "maximum": _MAX_TIMEOUT_SEC,
                "description": "Wall-clock seconds before the script is killed.",
            },
        },
        "required": ["script_path"],
    }

    def is_enabled(self, ctx: "NodeContext") -> bool:
        return bool(getattr(ctx, "skill_contents", None))

    def check_permission(
        self, ctx: "NodeContext", params: Dict[str, Any]
    ) -> PermissionResult:
        if not self.is_enabled(ctx):
            return PermissionResult(
                decision="deny",
                reason="No skills loaded on this node — `run_skill_script` is unavailable.",
            )
        if not params.get("script_path"):
            return PermissionResult(
                decision="deny", reason="Missing required param `script_path`."
            )
        return PermissionResult()

    async def run(self, params: Dict[str, Any], ctx: "NodeContext") -> str:
        script_path = str(params.get("script_path") or "").strip()
        input_json = params.get("input_json")
        if input_json is None:
            input_json = {}
        try:
            timeout = int(params.get("timeout") or _DEFAULT_TIMEOUT_SEC)
        except (TypeError, ValueError):
            timeout = _DEFAULT_TIMEOUT_SEC
        timeout = max(1, min(timeout, _MAX_TIMEOUT_SEC))

        if not script_path:
            return "[run_skill_script] missing `script_path` param."

        skill_contents = getattr(ctx, "skill_contents", None) or {}
        if not skill_contents:
            return "[run_skill_script] error: no skills loaded on this node."

        node_state = ctx.node_state if isinstance(ctx.node_state, dict) else {}
        reader = SkillFileReader.from_state(node_state, skill_contents)
        resolved = reader._resolve_path(script_path)
        if not resolved or not os.path.exists(resolved):
            return f"[run_skill_script] error: script not found: {script_path}"

        # Pass the skill base dir as argv[1] so the script can locate sibling files.
        # Use the *parent of the script's directory* — matches the original
        # AutoCAD agent behaviour (skill root, not script subdir).
        base_dir = os.path.dirname(os.path.dirname(resolved))

        try:
            stdin_blob = json.dumps(input_json, ensure_ascii=False)
        except Exception as e:  # noqa: BLE001
            return f"[run_skill_script] error: failed to encode input_json: {e}"

        try:
            proc = subprocess.run(
                [sys.executable, resolved, base_dir],
                input=stdin_blob,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return (
                f"[run_skill_script] error: script `{script_path}` exceeded "
                f"timeout of {timeout}s and was killed."
            )
        except Exception as e:  # noqa: BLE001
            logger.logger.warning(
                f"[run_skill_script] subprocess failed for {script_path}: {e}"
            )
            return f"[run_skill_script] error: failed to run script: {e}"

        if proc.returncode != 0:
            stderr_snippet = (proc.stderr or "")[:1000]
            return (
                f"[run_skill_script] script `{script_path}` exited with code "
                f"{proc.returncode}.\nstderr:\n{stderr_snippet}"
            )

        stdout = (proc.stdout or "").strip()
        if not stdout:
            stderr_snippet = (proc.stderr or "")[:500]
            return (
                f"[run_skill_script] script `{script_path}` produced no stdout. "
                f"stderr:\n{stderr_snippet}"
            )

        try:
            parsed = json.loads(stdout)
        except json.JSONDecodeError as e:
            return (
                f"[run_skill_script] script `{script_path}` stdout is not valid "
                f"JSON: {e}\nFirst 500 chars:\n{stdout[:500]}"
            )

        # Format for the planner — show the script identity + the JSON result.
        try:
            pretty = json.dumps(parsed, ensure_ascii=False, indent=2)
        except Exception:  # noqa: BLE001
            pretty = str(parsed)

        return (
            f"[run_skill_script] `{script_path}` completed successfully.\n"
            f"Result (JSON):\n```json\n{pretty[:_MAX_OUTPUT_CHARS]}\n```"
        )


TOOL = RunSkillScriptTool()
