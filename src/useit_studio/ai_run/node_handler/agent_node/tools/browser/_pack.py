"""Browser ToolPack."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..helpers import extract_snapshot_dict, has_any
from ..protocol import ToolPack

if TYPE_CHECKING:
    from useit_studio.ai_run.node_handler.base_v2 import NodeContext


class BrowserPack(ToolPack):
    """Browser automation via Local Engine.

    Flat ``{name: <action>, args: {...}}`` tool_call protocol — see
    ``tools.py`` for the full action set migrated from
    ``functional_nodes/browser_use``.
    """

    name = "browser"
    default_target = "browser"
    router_fragment = (
        "- **browser_\\***: DOM-indexed browser automation (connect / attach "
        "/ tabs / navigation / click_element / input_text / scroll / "
        "extract_content / page_state).  First step on any browser task "
        "MUST be `browser_connect` (or `browser_attach`).  Use the DOM "
        "`index` from the latest `page_state.elements` to interact — never "
        "screen pixels."
    )

    @classmethod
    def detect_from_snapshot(cls, ctx: "NodeContext") -> bool:
        """Auto-enable when the snapshot looks like a browser ``page_state``.

        Match a few canonical browser-only keys so we don't accidentally
        light up on PPT / Excel / Word snapshots that happen to mention
        ``url``.
        """
        snap = extract_snapshot_dict(ctx)
        return has_any(
            snap,
            [
                "page_state",
                "dom_elements",
                "tabs",
                "tab_count",
                "active_tab_index",
            ],
        )
