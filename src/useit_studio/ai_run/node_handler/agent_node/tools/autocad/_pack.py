"""AutoCAD ToolPack —— AutoCAD via Local Engine（flat tool_call 协议）。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..helpers import extract_snapshot_dict, has_any
from ..protocol import ToolPack

if TYPE_CHECKING:
    from useit_studio.ai_run.node_handler.base_v2 import NodeContext


class AutoCADPack(ToolPack):
    """AutoCAD ToolPack —— 通过 Local Engine 控制 AutoCAD。

    与 Word/Excel/PPT 不同，AutoCAD Local Engine **不使用 `/step` 协议**：
    每个 action 是一个独立的扁平 tool_call（``name`` 直接是 ``draw_from_json`` /
    ``execute_python_com`` / ``snapshot`` …），由 :class:`_AutoCADEngineTool`
    覆写 :meth:`build_tool_call` 以扁平形式下发。

    snapshot 自动启用规则
    --------------------
    AutoCAD snapshot 顶层关键字段：``status`` / ``document_info`` /
    ``content`` / ``screenshot``。任一存在即视为 AutoCAD 在用 ——
    历史代码里写的是 ``drawing_info`` / ``entities``，那些 key 在真实
    snapshot 里并不存在，因此从未触发过自动加载，导致 Router 看不到
    ``autocad_*`` 工具。这里改成与 :file:`computer_use/autocad/snapshot.py`
    的 ``AutoCADSnapshot.from_dict`` 实际识别的 key 一致。
    """

    name = "autocad"
    default_target = "autocad"
    router_fragment = (
        "- **autocad_\\***: AutoCAD drawings via Local Engine (status / "
        "snapshot / launch / open / close / new / draw_from_json / "
        "execute_python_com / standard parts).  Prefer "
        "`autocad_draw_from_json` for primitives (lines / circles / arcs / "
        "polylines / texts / dimensions); fall back to "
        "`autocad_execute_python_com` for hatches, blocks, arrays, mirroring, "
        "deletion, AutoLISP."
    )

    @classmethod
    def detect_from_snapshot(cls, ctx: "NodeContext") -> bool:
        snap = extract_snapshot_dict(ctx)
        if not isinstance(snap, dict):
            return False
        # 1) Full AutoCADSnapshot shape (document_info / content / status).
        if has_any(snap, ["document_info", "content"]):
            return True
        # 2) Nested status block from the dataclass dump.
        status = snap.get("status")
        if isinstance(status, dict) and (
            "running" in status or "documents" in status
        ):
            return True
        # 3) Status-only API response: ``{running, version, documents}`` is
        #    surfaced flat at the top of the merged snapshot dict.
        if "running" in snap and "documents" in snap:
            return True
        return False
