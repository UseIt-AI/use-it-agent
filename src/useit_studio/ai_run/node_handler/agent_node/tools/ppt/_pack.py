"""PPT ToolPack —— PowerPoint via Local Engine。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..helpers import extract_snapshot_dict, has_any
from ..protocol import ToolPack

if TYPE_CHECKING:
    from useit_studio.ai_run.node_handler.base_v2 import NodeContext


class PPTPack(ToolPack):
    name = "ppt"
    default_target = "ppt"
    router_fragment = (
        "- **ppt_\\***: PowerPoint (via Local Engine).  When the user "
        "references a specific `.pptx` path, call `ppt_document "
        "action=\"open\" file_path=...` FIRST — it auto-launches "
        "PowerPoint and opens the file.  Other `ppt_*` tools attach to "
        "the running instance via COM and will fail with `Operation "
        "unavailable` if no presentation is open yet."
    )

    @classmethod
    def detect_from_snapshot(cls, ctx: "NodeContext") -> bool:
        return has_any(extract_snapshot_dict(ctx), ["presentation_info", "slide_width"])
