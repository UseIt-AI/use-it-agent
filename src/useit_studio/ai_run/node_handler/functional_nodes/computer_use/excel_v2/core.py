"""
Excel Agent V2 - Core 模块

基于 office_agent 统一架构实现。
"""

from typing import Optional, Dict, Any

from ..office_agent import (
    OfficeAgent,
    OfficeAgentConfig,
    OfficePlanner,
    OfficePlannerConfig,
    OfficeAppType,
)
from .prompts import EXCEL_SYSTEM_PROMPT, EXCEL_USER_PROMPT_TEMPLATE


def create_agent(
    planner_model: str = "gpt-4o-mini",
    actor_model: str = "gpt-4o-mini",
    api_keys: Optional[Dict[str, str]] = None,
    node_id: str = "",
) -> OfficeAgent:
    """
    创建 Excel Agent 的工厂函数
    
    Args:
        planner_model: Planner 使用的模型
        actor_model: Actor 使用的模型（保留兼容性，不使用）
        api_keys: API 密钥字典
        node_id: 节点 ID
        
    Returns:
        OfficeAgent 实例（配置为 Excel 应用）
    """
    config = OfficeAgentConfig(
        planner_model=planner_model,
        actor_model=actor_model,
        app_type=OfficeAppType.EXCEL,
    )
    
    planner_config = OfficePlannerConfig(
        model=planner_model,
        app_type=OfficeAppType.EXCEL,
    )
    
    planner = OfficePlanner(
        config=planner_config,
        api_keys=api_keys,
        node_id=node_id,
        system_prompt=EXCEL_SYSTEM_PROMPT,
        user_prompt_template=EXCEL_USER_PROMPT_TEMPLATE,
    )
    
    return OfficeAgent(
        config=config,
        planner=planner,
        api_keys=api_keys,
        node_id=node_id,
    )


class ExcelAgent(OfficeAgent):
    """
    Excel Agent - Excel 自动化 Agent
    
    这是 OfficeAgent 的别名，配置为 Excel 应用。
    """
    
    def __init__(
        self,
        planner_model: str = "gpt-4o-mini",
        actor_model: str = "gpt-4o-mini",
        api_keys: Optional[Dict[str, str]] = None,
        node_id: str = "",
    ):
        """初始化 Excel Agent"""
        config = OfficeAgentConfig(
            planner_model=planner_model,
            actor_model=actor_model,
            app_type=OfficeAppType.EXCEL,
        )
        
        planner_config = OfficePlannerConfig(
            model=planner_model,
            app_type=OfficeAppType.EXCEL,
        )
        
        planner = OfficePlanner(
            config=planner_config,
            api_keys=api_keys,
            node_id=node_id,
            system_prompt=EXCEL_SYSTEM_PROMPT,
            user_prompt_template=EXCEL_USER_PROMPT_TEMPLATE,
        )
        
        super().__init__(
            config=config,
            planner=planner,
            api_keys=api_keys,
            node_id=node_id,
        )


__all__ = ["create_agent", "ExcelAgent"]
