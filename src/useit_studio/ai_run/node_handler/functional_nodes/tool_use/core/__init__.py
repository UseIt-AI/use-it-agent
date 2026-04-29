"""
Tool Use Node - Core 模块

包含 Agent 和 Planner 的实现。
采用 planner_only 模式。
"""

from typing import Optional, Dict, Any, List

from langchain_core.tools import BaseTool as LangChainBaseTool

from .planner_only.agent import ToolUseAgent
from .planner_only.planner import ToolUsePlanner


def create_agent(
    planner_model: str = "gpt-4o-mini",
    api_keys: Optional[Dict[str, str]] = None,
    tools: Optional[List[LangChainBaseTool]] = None,
    node_id: str = "",
) -> ToolUseAgent:
    """
    创建 Tool Use Agent 的工厂函数
    
    Args:
        planner_model: Planner 使用的模型
        api_keys: API 密钥字典
        tools: LangChain 工具列表
        node_id: 节点 ID
        
    Returns:
        ToolUseAgent 实例
    """
    return ToolUseAgent(
        planner_model=planner_model,
        api_keys=api_keys,
        tools=tools or [],
        node_id=node_id,
    )


__all__ = [
    "create_agent",
    "ToolUseAgent",
    "ToolUsePlanner",
]
