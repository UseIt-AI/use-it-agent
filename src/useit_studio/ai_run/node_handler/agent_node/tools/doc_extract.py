"""tool_doc_extract —— 从本地 PDF 抽取文本（inline）。

独立 inline tool，一般在附件 PDF 被下载到本地后使用。
"""

from __future__ import annotations

from typing import Any, Dict, TYPE_CHECKING

from useit_studio.ai_run.utils.logger_utils import LoggerUtils

from .protocol import InlineTool, PermissionResult

if TYPE_CHECKING:
    from useit_studio.ai_run.node_handler.base_v2 import NodeContext

logger = LoggerUtils(component_name="Tool.doc_extract")


class DocExtractTool(InlineTool):
    name = "tool_doc_extract"
    group = ""
    router_hint = (
        "Extract text from a local PDF (use after an attached PDF was downloaded). "
        "Params: pdf_path (absolute path from attached_files section), "
        "max_pages (int, optional)."
    )
    is_read_only = True
    input_schema = {
        "type": "object",
        "properties": {
            "pdf_path": {"type": "string"},
            "max_pages": {"type": "integer", "minimum": 1},
        },
        "required": ["pdf_path"],
    }

    def check_permission(
        self, ctx: "NodeContext", params: Dict[str, Any]
    ) -> PermissionResult:
        if not params.get("pdf_path"):
            return PermissionResult(decision="deny", reason="pdf_path required")
        return PermissionResult()

    async def run(self, params: Dict[str, Any], ctx: "NodeContext") -> str:
        try:
            from useit_studio.ai_run.node_handler.functional_nodes.tool_use.tools.doc_extract.tool import (
                DocExtractTool as _VendorDocExtract,
            )
        except ImportError as e:
            return f"[doc_extract] import failed: {e}"

        pdf_path = params.get("pdf_path", "")
        if not pdf_path:
            return "[doc_extract] missing 'pdf_path' param"

        try:
            tool = _VendorDocExtract(
                project_id=ctx.project_id,
                chat_id=ctx.chat_id,
            )
            result = await tool.invoke(
                pdf_path=pdf_path,
                max_pages=params.get("max_pages"),
            )
            return str(result)[:20000]
        except Exception as e:  # noqa: BLE001
            logger.logger.warning(f"[tool_doc_extract] error: {e}")
            return f"[doc_extract] error: {e}"


TOOL = DocExtractTool()
