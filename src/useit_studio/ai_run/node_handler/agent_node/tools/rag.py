"""tool_rag —— 项目级 RAG 检索（inline）。

独立 inline tool：RAG_URL 环境变量 + OPENAI_API_KEY 齐备才启用。
"""

from __future__ import annotations

import os
from typing import Any, Dict, TYPE_CHECKING

from useit_studio.ai_run.utils.logger_utils import LoggerUtils

from .protocol import InlineTool, PermissionResult

if TYPE_CHECKING:
    from useit_studio.ai_run.node_handler.base_v2 import NodeContext

logger = LoggerUtils(component_name="Tool.rag")


class RAGTool(InlineTool):
    name = "tool_rag"
    group = ""
    router_hint = (
        "Retrieve from this project's uploaded documents via RAG. "
        "Params: query (str), top_k (int, default 5)."
    )
    is_read_only = True
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "top_k": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20},
        },
        "required": ["query"],
    }

    def is_enabled(self, ctx: "NodeContext") -> bool:
        keys = ctx.planner_api_keys or {}
        has_openai = bool(keys.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY"))
        has_rag_url = bool(os.getenv("RAG_URL"))
        return has_openai and has_rag_url

    def check_permission(
        self, ctx: "NodeContext", params: Dict[str, Any]
    ) -> PermissionResult:
        if not self.is_enabled(ctx):
            return PermissionResult(
                decision="deny", reason="OPENAI_API_KEY or RAG_URL missing"
            )
        return PermissionResult()

    async def run(self, params: Dict[str, Any], ctx: "NodeContext") -> str:
        try:
            from useit_studio.ai_run.node_handler.functional_nodes.tool_use.tools.rag.tool import (
                RAGTool as _VendorRAG,
            )
        except ImportError as e:
            return f"[rag] import failed: {e}"

        query = params.get("query", "")
        if not query:
            return "[rag] missing 'query' param"

        api_keys = ctx.planner_api_keys or {}
        try:
            tool = _VendorRAG(
                rag_url=os.getenv("RAG_URL", ""),
                openai_api_key=api_keys.get("OPENAI_API_KEY", "")
                or os.getenv("OPENAI_API_KEY", ""),
            )
            result = await tool.invoke(
                query=query,
                top_k=int(params.get("top_k", 5) or 5),
                project_id=ctx.project_id,
                chat_id=ctx.chat_id,
            )
            return str(result)[:20000]
        except Exception as e:  # noqa: BLE001
            logger.logger.warning(f"[tool_rag] error: {e}")
            return f"[rag] error: {e}"


TOOL = RAGTool()
