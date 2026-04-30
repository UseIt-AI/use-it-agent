"""
节点类型常量定义

定义所有支持的节点类型，使用 {category}-{subcategory} 命名规范。
"""

# ==================== 新的节点类型定义 ====================

# Computer Use 相关节点类型（使用 computer-use- 前缀）
COMPUTER_USE_GUI_NODE_TYPE = "computer-use-gui"
COMPUTER_USE_EXCEL_NODE_TYPE = "computer-use-excel"
COMPUTER_USE_AUTOCAD_NODE_TYPE = "computer-use-autocad"
COMPUTER_USE_WORD_NODE_TYPE = "computer-use-word"
COMPUTER_USE_PPT_NODE_TYPE = "computer-use-ppt"
COMPUTER_USE_POWERPOINT_NODE_TYPE = "computer-use-powerpoint"

# 所有 Computer Use 节点类型（用于分组判断）
COMPUTER_USE_NODE_TYPES = {
    COMPUTER_USE_GUI_NODE_TYPE,
    COMPUTER_USE_EXCEL_NODE_TYPE,
    COMPUTER_USE_AUTOCAD_NODE_TYPE,
    COMPUTER_USE_WORD_NODE_TYPE,
    COMPUTER_USE_PPT_NODE_TYPE,
    COMPUTER_USE_POWERPOINT_NODE_TYPE,
}

# 流控制节点类型
FLOW_CONTROL_NODE_TYPES = {
    "start",
    "end",
    "if-else",
    "loop",
    "loop-start",
    "loop-end"
}

# 工具节点类型
TOOL_NODE_TYPES = {
    "knowledge-retrieval",
    "tools"
}

# 功能节点类型
FUNCTIONAL_NODE_TYPES = {
    "llm",
    "human-in-the-loop",
    "web-search",
}

# MCP 节点类型
MCP_NODE_TYPES = {
    "mcp"
}

# ==================== 向后兼容 ====================
# 保留旧的常量名，方便渐进式迁移

# 旧的 COMPUTER_USE_NODE_TYPE（集合形式，包含旧的节点类型）
COMPUTER_USE_NODE_TYPE_LEGACY = {
    # legacy / canonical
    "computer-use",
    # be tolerant to underscore variants if any graphs use them
    "computer_use",
}

# 为了兼容现有代码，COMPUTER_USE_NODE_TYPE 指向新旧类型的并集
COMPUTER_USE_NODE_TYPE = COMPUTER_USE_NODE_TYPES | COMPUTER_USE_NODE_TYPE_LEGACY

# ==================== 工具函数 ====================

def is_computer_use_node(node_type: str) -> bool:
    """判断是否是 Computer Use 类节点"""
    return node_type.startswith("computer-use") or node_type.startswith("computer_use")

def is_flow_control_node(node_type: str) -> bool:
    """判断是否是流控制节点"""
    return node_type in FLOW_CONTROL_NODE_TYPES

def is_functional_node(node_type: str) -> bool:
    """判断是否是功能节点"""
    return node_type in FUNCTIONAL_NODE_TYPES

def get_node_category(node_type: str) -> str:
    """
    从 node_type 提取类别（前缀）

    示例：
        get_node_category("computer-use-gui") -> "computer-use"
        get_node_category("flow-control-loop") -> "flow-control"
    """
    if "-" in node_type:
        # 处理 computer-use-gui 格式（取前两部分作为 category）
        parts = node_type.split("-")
        if len(parts) >= 3 and parts[0] == "computer" and parts[1] == "use":
            return "computer-use"
        elif len(parts) >= 3 and parts[0] == "flow" and parts[1] == "control":
            return "flow-control"
        # 其他情况取第一部分
        return parts[0]
    return "unknown"

def get_node_subcategory(node_type: str) -> str:
    """
    从 node_type 提取子类别（后缀）

    示例：
        get_node_subcategory("computer-use-gui") -> "gui"
        get_node_subcategory("computer-use-excel") -> "excel"
    """
    if "-" in node_type:
        parts = node_type.split("-")
        # computer-use-gui -> gui
        if len(parts) >= 3 and parts[0] == "computer" and parts[1] == "use":
            return "-".join(parts[2:])
        # flow-control-loop -> loop
        elif len(parts) >= 3 and parts[0] == "flow" and parts[1] == "control":
            return "-".join(parts[2:])
        # 其他情况取最后一部分
        elif len(parts) >= 2:
            return parts[-1]
    return ""

def normalize_computer_use_node_type(node_dict: dict) -> str:
    """
    标准化 Computer Use 节点类型

    将旧格式的节点 (type: "computer-use" + action_type) 转换为新格式 (type: "computer-use-{subtype}")

    参数：
        node_dict: 节点字典，包含 data.type 和可选的 data.action_type

    返回：
        标准化的节点类型字符串

    示例：
        输入: {"data": {"type": "computer-use", "action_type": "gui"}}
        输出: "computer-use-gui"

        输入: {"data": {"type": "computer-use-excel"}}
        输出: "computer-use-excel"
    """
    node_data = node_dict.get("data", {})
    node_type = node_data.get("type", "")

    # 如果已经是新格式（computer-use-gui, computer-use-excel 等），直接返回
    if node_type in COMPUTER_USE_NODE_TYPES:
        return node_type

    # 如果是旧格式（computer-use 或 computer_use），读取 action_type
    if node_type in COMPUTER_USE_NODE_TYPE_LEGACY:
        action_type = node_data.get("action_type", "gui")

        # 映射 action_type 到新的节点类型
        action_type_mapping = {
            "gui": COMPUTER_USE_GUI_NODE_TYPE,
            "excel": COMPUTER_USE_EXCEL_NODE_TYPE,
            "autocad": COMPUTER_USE_AUTOCAD_NODE_TYPE,
            "word": COMPUTER_USE_WORD_NODE_TYPE,
            "ppt": COMPUTER_USE_PPT_NODE_TYPE,
            "powerpoint": COMPUTER_USE_POWERPOINT_NODE_TYPE,
        }

        return action_type_mapping.get(action_type, COMPUTER_USE_GUI_NODE_TYPE)

    # 其他情况直接返回原类型
    return node_type

__all__ = [
    # 新的节点类型常量
    "COMPUTER_USE_GUI_NODE_TYPE",
    "COMPUTER_USE_EXCEL_NODE_TYPE",
    "COMPUTER_USE_AUTOCAD_NODE_TYPE",
    "COMPUTER_USE_WORD_NODE_TYPE",
    "COMPUTER_USE_PPT_NODE_TYPE",
    "COMPUTER_USE_POWERPOINT_NODE_TYPE",
    "COMPUTER_USE_NODE_TYPES",

    # 原有节点类型常量
    "FLOW_CONTROL_NODE_TYPES",
    "TOOL_NODE_TYPES",
    "COMPUTER_USE_NODE_TYPE",  # 兼容旧代码
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
