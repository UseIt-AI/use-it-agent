"""Word ToolPack —— Microsoft Word via Local Engine（/step 协议）。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..helpers import extract_snapshot_dict, has_any
from ..protocol import ToolPack

if TYPE_CHECKING:
    from useit_studio.ai_run.node_handler.base_v2 import NodeContext


class WordPack(ToolPack):
    name = "word"
    default_target = "word"
    router_fragment = (
        "- **word_\\***: Microsoft Word (via Local Engine `/step` + "
        "`/snapshot`).  Requires Word to be open on the user's machine.  "
        "Prefer `word_execute_script` (skill mode, vetted scripts) over "
        "`word_execute_code` (freeform PowerShell/Python); use `word_snapshot` "
        "to read the document — default to the smallest `snapshot_scope` "
        "that answers the question and only widen when necessary, because "
        "Word docs can be hundreds of pages."
    )

    @classmethod
    def detect_from_snapshot(cls, ctx: "NodeContext") -> bool:
        """Auto-enable when the snapshot looks like a Word document.

        Keys we check come from the Local Engine's Word snapshot schema:
        ``document_info`` is the top-level descriptor; ``paragraph_count``
        / ``outline`` appear in almost every Word snapshot scope; a raw
        ``word.*`` object sometimes lands under the app-typed key.
        """
        snap = extract_snapshot_dict(ctx)
        return has_any(
            snap,
            ["document_info", "paragraph_count", "outline", "word"],
        )
