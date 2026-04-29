"""
`useit_ai_run.node_handler.agent_node` package

Agent Node —— 统一的功能节点形态。

架构
----
一等公民是 **Tool**，不是 "Capability"。每个具体动作都是一个独立的
`AgentTool` 实例；软件级共享参数（snapshot 自动加载、API Key 门、router
fragment）放在非常薄的 `ToolPack` 子类里。

文件结构
--------
- handler.py          - 骨架：orchestrator（Filter → Planner → Dispatch）
- filter.py           - ToolFilter（permission ∩ (whitelist ∪ snapshot-detected)）
- prompts.py          - Router system prompt 模板 + action table 生成
- tools/              - 所有 tool 定义
    protocol.py       - AgentTool / BaseTool / EngineTool / InlineTool / ToolPack / ToolCall
    helpers.py        - has_any / extract_snapshot_dict / ...
    ppt/              - PowerPoint（/step 协议）
    excel/            - Excel
    word/             - Word
    autocad/          - AutoCAD
    gui/              - 通用 GUI（扁平 payload）
    browser/          - 浏览器自动化（扁平 payload）
    code/             - 本地 Python 执行（execute_python 协议）
    web_search.py     - 独立 inline tool
    rag.py            - 独立 inline tool
    doc_extract.py    - 独立 inline tool

新增工具
--------
- 新增一个软件能力：在 `tools/` 下 `cp -r ppt/ <new>/` 改三个字段。
- 新增一个独立 inline tool：在 `tools/` 根目录建 `<name>.py`，导出 `TOOL`。
- 不需要改任何现有文件；`tools/__init__.py` 会自动发现。
"""

from .filter import ToolFilter
from .tools import (
    ALL_PACKS,
    ALL_TOOLS,
    PACK_BY_NAME,
    TOOL_BY_NAME,
    TOOL_TO_PACK,
)
from .tools.protocol import (
    AgentTool,
    BaseTool,
    EngineTool,
    InlineTool,
    PermissionResult,
    ToolCall,
    ToolPack,
)


def __getattr__(name):
    """Lazy-load heavy symbols (PEP 562).

    `.handler` transitively imports OfficePlanner → LLM 栈（langchain / PIL /
    tiktoken ...）。延迟到真的要用 AgentNodeHandler 时再付这个代价；只想
    introspect tools / packs 时 `from useit_studio.ai_run.node_handler.agent_node
    import ALL_TOOLS` 几毫秒就返回。
    """
    if name == "AgentNodeHandler":
        from .handler import AgentNodeHandler as _H
        globals()["AgentNodeHandler"] = _H
        return _H
    raise AttributeError(f"module 'agent_node' has no attribute '{name}'")


__all__ = [
    "AgentNodeHandler",
    "ToolFilter",
    "AgentTool",
    "BaseTool",
    "EngineTool",
    "InlineTool",
    "ToolPack",
    "ToolCall",
    "PermissionResult",
    "ALL_PACKS",
    "ALL_TOOLS",
    "PACK_BY_NAME",
    "TOOL_BY_NAME",
    "TOOL_TO_PACK",
]
