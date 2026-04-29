"""GUI ToolPack。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..helpers import extract_snapshot_dict, has_any
from ..protocol import ToolPack

if TYPE_CHECKING:
    from useit_studio.ai_run.node_handler.base_v2 import NodeContext


class GUIPack(ToolPack):
    name = "gui"
    default_target = "gui"
    router_fragment = (
        "- **gui_\\***: Generic desktop GUI (click / type / key / scroll / screenshot). "
        "Use when a task needs a GUI app that doesn't have a dedicated capability."
    )

    @classmethod
    def detect_from_snapshot(cls, ctx: "NodeContext") -> bool:
        return has_any(extract_snapshot_dict(ctx), ["screenshot_base64", "screen_size"])
