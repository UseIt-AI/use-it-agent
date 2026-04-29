"""
Word Agent V2 - Core 模块

基于 office_agent 统一架构重构。

包含两种架构模式：
1. planner_only（推荐）: Planner 直接输出代码，单阶段
2. planner_actor: Planner + Actor 两阶段

使用 create_agent() 工厂函数创建 Agent。
"""

from typing import Optional, Dict, Any

from ...office_agent import (
    OfficeAgent,
    OfficeAgentConfig,
    OfficePlanner,
    OfficePlannerConfig,
    OfficeAppType,
)
from ..prompts import WORD_SYSTEM_PROMPT, WORD_USER_PROMPT_TEMPLATE


def create_agent(
    mode: str = "planner_only",
    planner_model: str = "gpt-4o-mini",
    actor_model: str = "gpt-4o-mini",
    api_keys: Optional[Dict[str, str]] = None,
    node_id: str = "",
) -> OfficeAgent:
    """
    创建 Word Agent 的工厂函数
    
    Args:
        mode: 架构模式
            - "planner_only": 单阶段模式，Planner 直接输出代码（推荐）
            - "planner_actor": 两阶段模式，Planner + Actor（暂不支持，使用 planner_only）
        planner_model: Planner 使用的模型
        actor_model: Actor 使用的模型（仅 planner_actor 模式使用）
        api_keys: API 密钥字典
        node_id: 节点 ID
        
    Returns:
        OfficeAgent 实例（配置为 Word 应用）
    """
    if mode == "planner_actor":
        # 为了向后兼容，planner_actor 模式暂时回退到旧实现
        from .planner_actor.agent import WordAgent as LegacyWordAgent
        return LegacyWordAgent(
            planner_model=planner_model,
            actor_model=actor_model,
            api_keys=api_keys,
            node_id=node_id,
        )
    
    # planner_only 模式：使用新的 office_agent 架构
    config = OfficeAgentConfig(
        planner_model=planner_model,
        actor_model=actor_model,
        app_type=OfficeAppType.WORD,
    )
    
    planner_config = OfficePlannerConfig(
        model=planner_model,
        app_type=OfficeAppType.WORD,
    )
    
    planner = OfficePlanner(
        config=planner_config,
        api_keys=api_keys,
        node_id=node_id,
        system_prompt=WORD_SYSTEM_PROMPT,
        user_prompt_template=WORD_USER_PROMPT_TEMPLATE,
    )
    
    return OfficeAgent(
        config=config,
        planner=planner,
        api_keys=api_keys,
        node_id=node_id,
    )


# 向后兼容：导出 WordAgent 类型
# 新代码应直接使用 OfficeAgent
class WordAgent(OfficeAgent):
    """
    Word Agent - Word 自动化 Agent
    
    这是 OfficeAgent 的别名，配置为 Word 应用。
    新代码建议直接使用 create_agent() 工厂函数。
    """
    
    def __init__(
        self,
        planner_model: str = "gpt-4o-mini",
        actor_model: str = "gpt-4o-mini",
        api_keys: Optional[Dict[str, str]] = None,
        node_id: str = "",
    ):
        """初始化 Word Agent"""
        config = OfficeAgentConfig(
            planner_model=planner_model,
            actor_model=actor_model,
            app_type=OfficeAppType.WORD,
        )
        
        planner_config = OfficePlannerConfig(
            model=planner_model,
            app_type=OfficeAppType.WORD,
        )
        
        planner = OfficePlanner(
            config=planner_config,
            api_keys=api_keys,
            node_id=node_id,
            system_prompt=WORD_SYSTEM_PROMPT,
            user_prompt_template=WORD_USER_PROMPT_TEMPLATE,
        )
        
        super().__init__(
            config=config,
            planner=planner,
            api_keys=api_keys,
            node_id=node_id,
        )


# 向后兼容导出
from .planner_only.planner import WordPlanner

__all__ = ["create_agent", "WordAgent", "WordPlanner", "OfficeAgent"]
