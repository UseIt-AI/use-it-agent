"""Code ToolPack —— 无 snapshot 自动加载（本地 Python 执行）。"""

from __future__ import annotations

from ..protocol import ToolPack


class CodePack(ToolPack):
    name = "code"
    default_target = "code"
    router_fragment = (
        "- **code_execute_python**: Run arbitrary Python on the user's machine. "
        "Use for data processing, file I/O, local scripts."
    )
