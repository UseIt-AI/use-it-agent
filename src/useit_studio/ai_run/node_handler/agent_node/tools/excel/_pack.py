"""Excel ToolPack。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..helpers import extract_snapshot_dict, has_any
from ..protocol import ToolPack

if TYPE_CHECKING:
    from useit_studio.ai_run.node_handler.base_v2 import NodeContext


class ExcelPack(ToolPack):
    name = "excel"
    default_target = "excel"
    router_fragment = (
        "- **excel_\\***: Excel (via Local Engine). "
        "Requires Excel to be open on the user's machine."
    )

    @classmethod
    def detect_from_snapshot(cls, ctx: "NodeContext") -> bool:
        return has_any(
            extract_snapshot_dict(ctx),
            ["sheet_info", "workbook_info", "active_sheet"],
        )
