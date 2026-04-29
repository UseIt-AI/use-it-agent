"""tool_web_search —— Tavily 搜索（inline）。

独立 inline tool，不属于任何 ToolPack：它的启用只取决于 TAVILY_API_KEY 是否
可用，不关心软件 snapshot。auto-discovery 会把单文件 module 直接视为一个
独立 tool（路径：tools/web_search.py → `TOOL` 常量）。
"""

from __future__ import annotations

import os
from typing import Any, Dict, TYPE_CHECKING

from useit_studio.ai_run.utils.logger_utils import LoggerUtils

from .protocol import InlineTool, PermissionResult

if TYPE_CHECKING:
    from useit_studio.ai_run.node_handler.base_v2 import NodeContext

logger = LoggerUtils(component_name="Tool.web_search")


class WebSearchTool(InlineTool):
    name = "tool_web_search"
    group = ""
    router_hint = (
        "Search the web (Tavily) and return top results. "
        "Params: query (str), max_results (int, default 5)."
    )
    is_read_only = True
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20},
        },
        "required": ["query"],
    }

    def is_enabled(self, ctx: "NodeContext") -> bool:
        keys = ctx.planner_api_keys or {}
        return bool(keys.get("TAVILY_API_KEY") or os.getenv("TAVILY_API_KEY"))

    def check_permission(
        self, ctx: "NodeContext", params: Dict[str, Any]
    ) -> PermissionResult:
        if not self.is_enabled(ctx):
            return PermissionResult(decision="deny", reason="TAVILY_API_KEY not configured")
        return PermissionResult()

    async def run(self, params: Dict[str, Any], ctx: "NodeContext") -> str:
        try:
            from useit_studio.ai_run.node_handler.functional_nodes.tool_use.tools.web_search.tool import (
                WebSearchTool as _VendorWebSearch,
            )
        except ImportError as e:
            return f"[web_search] import failed: {e}"

        query = params.get("query", "")
        max_results = int(params.get("max_results", 5) or 5)
        if not query:
            return "[web_search] missing 'query' param"

        api_keys = ctx.planner_api_keys or {}
        api_key = api_keys.get("TAVILY_API_KEY") or os.getenv("TAVILY_API_KEY", "")
        if not api_key:
            return "[web_search] TAVILY_API_KEY not configured"

        try:
            tool = _VendorWebSearch(
                api_key=api_key,
                openai_api_key=api_keys.get("OPENAI_API_KEY", "") or os.getenv("OPENAI_API_KEY", ""),
            )
            result = await tool.invoke(query=query, max_results=max_results)
            return str(result)[:20000]
        except Exception as e:  # noqa: BLE001
            logger.logger.warning(f"[tool_web_search] error: {e}")
            return f"[web_search] error: {e}"


TOOL = WebSearchTool()
