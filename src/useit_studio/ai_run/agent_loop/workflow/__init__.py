"""Workflow graph, node types, and flow processing utilities.

Convenience exports so callers can import from the package root:

    from useit_studio.ai_run.agent_loop.workflow import (
        FlowProcessor, GraphManager,
        FLOW_CONTROL_NODE_TYPES, TOOL_NODE_TYPES,
        COMPUTER_USE_NODE_TYPE, FUNCTIONAL_NODE_TYPES,
    )
"""

from .flow_processor import FlowProcessor
from .graph_manager import GraphManager
from .node_types import (
    # 新的 Computer Use 节点类型常量
    COMPUTER_USE_GUI_NODE_TYPE,
    COMPUTER_USE_EXCEL_NODE_TYPE,
    COMPUTER_USE_AUTOCAD_NODE_TYPE,
    COMPUTER_USE_WORD_NODE_TYPE,
    COMPUTER_USE_NODE_TYPES,

    # 原有节点类型常量
    FLOW_CONTROL_NODE_TYPES,
    TOOL_NODE_TYPES,
    COMPUTER_USE_NODE_TYPE,  # 兼容旧代码（包含新旧类型）
    FUNCTIONAL_NODE_TYPES,
    MCP_NODE_TYPES,

    # 工具函数
    is_computer_use_node,
    is_flow_control_node,
    is_functional_node,
    get_node_category,
    get_node_subcategory,
    normalize_computer_use_node_type,
)

__all__ = [
    "FlowProcessor",
    "GraphManager",

    # 新的 Computer Use 节点类型
    "COMPUTER_USE_GUI_NODE_TYPE",
    "COMPUTER_USE_EXCEL_NODE_TYPE",
    "COMPUTER_USE_AUTOCAD_NODE_TYPE",
    "COMPUTER_USE_WORD_NODE_TYPE",
    "COMPUTER_USE_NODE_TYPES",

    # 原有节点类型
    "FLOW_CONTROL_NODE_TYPES",
    "TOOL_NODE_TYPES",
    "COMPUTER_USE_NODE_TYPE",
    "FUNCTIONAL_NODE_TYPES",
    "MCP_NODE_TYPES",

    # 工具函数
    "is_computer_use_node",
    "is_flow_control_node",
    "is_functional_node",
    "get_node_category",
    "get_node_subcategory",
    "normalize_computer_use_node_type",
]
