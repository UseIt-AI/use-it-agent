"""tools/autocad —— AutoCAD via Local Engine（**flat** tool_call 协议）。

完整覆盖 ``functional_nodes/computer_use/autocad`` 的 V2 API：
``status`` / ``snapshot`` / ``launch`` / ``draw_from_json`` /
``execute_python_com`` / 文档生命周期 / 标准件库。

注意：AutoCAD 不同于 PPT/Excel/Word —— 不走 ``/step`` 协议，每个 action
都是一个扁平 ``{name: <action>, args: {...}}`` 的 tool_call；详见
:mod:`.tools` 中 ``_AutoCADEngineTool.build_tool_call`` 的覆写。
"""

from ._pack import AutoCADPack
from .tools import TOOLS

__all__ = ["AutoCADPack", "TOOLS"]
