"""System ToolPack —— 桌面 OS 自动化（窗口 + 进程）。

Rationale
---------
This pack wraps what used to be the ``app__window_control`` /
``app__launch_app`` frontend-only app actions.  The capabilities are
fundamentally OS-level automation (same layer as :mod:`..gui` and
:mod:`..browser`), so they belong here alongside those packs.  Moving
them into a proper tool pack lets:

1. The **chat orchestrator** keep calling them (via
   :mod:`useit_ai_run.agent_loop.capability_catalog`, which now injects
   the pack's schemas into the orchestrator's tool list) — importantly,
   the schemas are now authored in Python and guaranteed to be complete
   (no more missing ``items.properties`` on ``zones`` etc.).

2. The **AgentNode Router Planner** invoke them natively as
   ``system_window_control`` / ``system_process_control`` — so a
   workflow node can arrange windows / launch apps as part of a larger
   plan.

Target routing
--------------
``target="app"`` is deliberately reused (not a new ``"system"`` target)
to stay compatible with the existing frontend handler at
``src/features/chat/handlers/appActions/actions/systemActions.ts`` —
the HTTP plumbing that forwards to the local-engine's
``/system/window-control`` and ``/system/process-control`` endpoints is
already in place there.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..protocol import ToolPack

if TYPE_CHECKING:
    from useit_studio.ai_run.node_handler.base_v2 import NodeContext


class SystemPack(ToolPack):
    name = "system"
    default_target = "app"
    router_fragment = (
        "- **system_\\***: Desktop OS automation — launch apps / open files "
        "(`system_process_control`), list / activate / minimise / maximise / "
        "close / pin-on-top / precisely position windows, and tile multiple "
        "windows side-by-side (`system_window_control`).  Use before any "
        "task that needs a specific desktop window or app in a known state."
    )

    @classmethod
    def detect_from_snapshot(cls, ctx: "NodeContext") -> bool:
        """System tools are always useful — they don't depend on a specific
        software being open.  Return True unconditionally.
        """
        return True
