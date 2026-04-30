"""
Tool Use Node - 多步骤 LLM Tool Calling 节点

支持用户通过预定义工具（RAG、Web Search）完成复杂任务。
采用 planner_only 模式进行规划和执行。

核心特点：
1. 无需 Local Engine 交互 - 工具在服务端直接执行
2. 预定义工具集 - 用户可选择 RAG、Web Search 等工具
3. 多步骤执行 - Planner 做总体规划，一步一步执行
4. LangChain Tool Calling - 使用 LLM 的 tool calling 机制

目录结构：
- handler.py: Handler V2 实现（纯桥接层）
- models.py: 数据模型定义
- tools/: 预定义工具
  - base.py: 工具基类
  - rag_tool.py: RAG 检索工具
  - web_search_tool.py: Web 搜索工具
- core/: Agent 核心逻辑
  - planner_only/: Planner Only 模式实现
    - agent.py: Tool Use Agent
    - planner.py: Tool Use Planner
"""

from .handler import ToolUseNodeHandlerV2
from .models import (
    ToolType,
    ActionType,
    ToolConfig,
    ToolCallResult,
    PlannerOutput,
    AgentContext,
    AgentStep,
    ReasoningDeltaEvent,
    PlanCompleteEvent,
    ToolCallEvent,
    ToolResultEvent,
    FileTransferEvent,
    ErrorEvent,
)
from .core import create_agent, ToolUseAgent, ToolUsePlanner
from .tools import (
    ToolUseBaseTool,
    create_tool_from_config,
    RAGTool,
    create_rag_tool,
    WebSearchTool,
    create_web_search_tool,
)

__all__ = [
    # Handler
    "ToolUseNodeHandlerV2",
    
    # 枚举
    "ToolType",
    "ActionType",
    
    # 模型
    "ToolConfig",
    "ToolCallResult",
    "PlannerOutput",
    "AgentContext",
    "AgentStep",
    
    # 事件
    "ReasoningDeltaEvent",
    "PlanCompleteEvent",
    "ToolCallEvent",
    "ToolResultEvent",
    "FileTransferEvent",
    "ErrorEvent",
    
    # Core
    "create_agent",
    "ToolUseAgent",
    "ToolUsePlanner",
    
    # Tools
    "ToolUseBaseTool",
    "create_tool_from_config",
    "RAGTool",
    "create_rag_tool",
    "WebSearchTool",
    "create_web_search_tool",
]
