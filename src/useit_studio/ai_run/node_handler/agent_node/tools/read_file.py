"""tool_read_file —— 按需读取 skill 资源文件（inline，跨调用持久化）。

迁移自 ``functional_nodes/computer_use/autocad/core.py:_read_skill_file``。

为什么是独立 inline tool（不放在 autocad 子包下）
------------------------------------------------
``ctx.get_skills_prompt()`` 渲染出的 prompt 里明确告诉 Planner "If you need to
access scripts or detailed documentation mentioned in the skills, use the
read_file tool" —— 但 agent_node 之前**根本没有这个 tool**，于是 Planner 一
旦想读 skill 文件就只能瞎写一个 `read_file` action，被 handler 当作未知工
具拒绝。AutoCAD / Excel / Word 共享同一个 skill 系统，所以放在通用入口 ——
任何带 ``skill_contents`` 的节点都能用。

跨步持久化
----------
``SkillFileReader`` 自身就支持 ``get_state() / from_state()``，状态字段为
``read_files_list`` / ``read_files_content``。本工具：

1. 用 ``SkillFileReader.from_state(ctx.node_state, ctx.skill_contents)`` 恢复；
2. ``read_file(...)`` 后把新状态**写回**到 ``ctx.node_state``（顶层键）；
3. ``agent_node/handler.py`` 在构造 planner ``skills_prompt`` 时，把
   ``accumulated_content`` 拼到 ``ctx.get_skills_prompt()`` 后面 —— 这样**每
   一步都看得到所有已读文件**，不会随 last_execution_output 翻新而丢失（这正
   是原 ``AutoCADAgentContext._get_full_skills_prompt`` 干的事）。
"""

from __future__ import annotations

from typing import Any, Dict, TYPE_CHECKING

from useit_studio.ai_run.skills import SkillFileReader
from useit_studio.ai_run.utils.logger_utils import LoggerUtils

from .protocol import InlineTool, PermissionResult

if TYPE_CHECKING:
    from useit_studio.ai_run.node_handler.base_v2 import NodeContext

logger = LoggerUtils(component_name="Tool.read_file")


class ReadFileTool(InlineTool):
    name = "read_file"
    group = ""  # standalone — independent of any pack
    router_hint = (
        "Read a file from the active skill's base directory.  Use this to "
        "load templates, parameter specs, or reference docs mentioned in "
        "`# Available Skills`.  Params: file_path (str), skill_name (str, "
        "optional)."
    )
    router_detail = (
        "## `read_file` — Read a Skill Resource File\n\n"
        "Inline tool.  Reads `file_path` (relative to the skill's base "
        "directory) from any loaded skill and surfaces the content in the "
        "next planner turn under `# Previously Read Skill Resources`.  "
        "**De-duplicated**: re-reading the same path is a no-op and returns "
        "`is_cached=true` instead of the content again.\n\n"
        "### When to use\n"
        "- The skills section says \"see `scripts/foo.py`\" or \"see "
        "`specs/R200/parameters.json`\".\n"
        "- You need a template / reference doc / parameter file before "
        "drawing or computing.\n"
        "- You want a deterministic value source instead of inventing "
        "coordinates yourself.\n\n"
        "### Params\n"
        "```json\n"
        "{\"file_path\": \"specs/R150/parameters.json\"}\n"
        "// optional second skill: {\"file_path\": \"...\", \"skill_name\": \"skill-66\"}\n"
        "```\n\n"
        "The file content (truncated to 50K chars) is appended to the "
        "rolling skills section and is visible across **all subsequent "
        "steps** — no need to read it again."
    )
    is_read_only = True
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": (
                    "Path relative to the skill's base directory, e.g. "
                    "`scripts/calculate.py` or `specs/R200/parameters.json`."
                ),
            },
            "skill_name": {
                "type": "string",
                "description": (
                    "Optional. Which skill to read from when multiple are "
                    "loaded.  If omitted, the reader searches all skills in "
                    "registration order."
                ),
            },
        },
        "required": ["file_path"],
    }

    def is_enabled(self, ctx: "NodeContext") -> bool:
        # Only useful when at least one skill is loaded.
        return bool(getattr(ctx, "skill_contents", None))

    def check_permission(
        self, ctx: "NodeContext", params: Dict[str, Any]
    ) -> PermissionResult:
        if not self.is_enabled(ctx):
            return PermissionResult(
                decision="deny",
                reason="No skills loaded on this node — `read_file` is unavailable.",
            )
        if not params.get("file_path"):
            return PermissionResult(
                decision="deny", reason="Missing required param `file_path`."
            )
        return PermissionResult()

    async def run(self, params: Dict[str, Any], ctx: "NodeContext") -> str:
        file_path = str(params.get("file_path") or "").strip()
        skill_name = params.get("skill_name") or None
        if not file_path:
            return "[read_file] missing `file_path` param."

        node_state = ctx.node_state if isinstance(ctx.node_state, dict) else {}
        skill_contents = getattr(ctx, "skill_contents", None) or {}

        reader = SkillFileReader.from_state(node_state, skill_contents)
        result = reader.read_file(file_path, skill_name=skill_name)

        # Persist state back into ctx.node_state — handler.py reads these top-level
        # keys when composing the next skills_prompt.  Mutating in place avoids
        # forcing every inline tool to thread state through return values.
        if isinstance(ctx.node_state, dict):
            state = reader.get_state()
            ctx.node_state["read_files_list"] = state["read_files_list"]
            ctx.node_state["read_files_content"] = state["read_files_content"]

        if not result.success:
            logger.logger.warning(
                f"[read_file] failed to read {file_path}: {result.error}"
            )
            return f"[read_file] error: {result.error}"

        if result.is_cached:
            return (
                f"[read_file] file `{file_path}` was already read earlier; "
                f"its content remains visible under "
                f"`# Previously Read Skill Resources`. Proceed to the next step."
            )

        # Return the formatted block (also already accumulated into the
        # reader state for cross-step visibility).
        return result.content


TOOL = ReadFileTool()
