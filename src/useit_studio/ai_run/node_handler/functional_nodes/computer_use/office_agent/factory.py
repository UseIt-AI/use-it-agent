"""
Office Agent - 工厂函数

提供创建不同 Office 应用 Agent 的统一入口。
"""

from typing import Dict, Any, Optional

from .models import OfficeAppType
from .base_agent import OfficeAgent, OfficeAgentConfig
from .base_planner import OfficePlanner, OfficePlannerConfig


def create_office_agent(
    app_type: str,
    config: Optional[OfficeAgentConfig] = None,
    api_keys: Optional[Dict[str, str]] = None,
    node_id: str = "",
    mode: str = "planner_only",
) -> OfficeAgent:
    """
    创建 Office Agent 的工厂函数
    
    Args:
        app_type: 应用类型 ("word", "excel", "ppt")
        config: Agent 配置，如果为 None 则使用默认配置
        api_keys: API 密钥
        node_id: 节点 ID
        mode: 架构模式 ("planner_only" 推荐, "planner_actor" 可选)
        
    Returns:
        配置好的 OfficeAgent 实例
        
    Example:
        # 创建 Word Agent
        agent = create_office_agent(
            app_type="word",
            api_keys={"OPENAI_API_KEY": "..."}
        )
        
        # 创建 Excel Agent
        agent = create_office_agent(
            app_type="excel",
            config=OfficeAgentConfig(planner_model="gpt-4o"),
            api_keys={"OPENAI_API_KEY": "..."}
        )
    """
    # 解析应用类型
    app_type_enum = OfficeAppType(app_type.lower())
    
    # 使用默认配置或传入的配置
    if config is None:
        config = OfficeAgentConfig(app_type=app_type_enum)
    else:
        config.app_type = app_type_enum
    
    # 根据应用类型导入对应的 prompts
    system_prompt, user_prompt_template = _get_prompts_for_app(app_type_enum)
    
    # 创建 Planner
    planner_config = OfficePlannerConfig(
        model=config.planner_model,
        max_tokens=config.max_tokens,
        temperature=config.temperature,
        app_type=app_type_enum,
    )
    
    planner = OfficePlanner(
        config=planner_config,
        api_keys=api_keys,
        node_id=node_id,
        system_prompt=system_prompt,
        user_prompt_template=user_prompt_template,
    )
    
    # 创建 Agent
    agent = OfficeAgent(
        config=config,
        planner=planner,
        api_keys=api_keys,
        node_id=node_id,
    )
    
    return agent


def _get_prompts_for_app(app_type: OfficeAppType) -> tuple[str, str]:
    """
    获取应用对应的 prompts
    
    各应用的 prompts 现在位于各自的 node 文件夹中：
    - word_v2/prompts.py
    - excel_v2/prompts.py
    - ppt_v2/prompts.py
    
    Returns:
        (system_prompt, user_prompt_template)
    """
    if app_type == OfficeAppType.WORD:
        from ..word_v2.prompts import WORD_SYSTEM_PROMPT, WORD_USER_PROMPT_TEMPLATE
        return WORD_SYSTEM_PROMPT, WORD_USER_PROMPT_TEMPLATE
    
    elif app_type == OfficeAppType.EXCEL:
        from ..excel_v2.prompts import EXCEL_SYSTEM_PROMPT, EXCEL_USER_PROMPT_TEMPLATE
        return EXCEL_SYSTEM_PROMPT, EXCEL_USER_PROMPT_TEMPLATE
    
    elif app_type == OfficeAppType.POWERPOINT:
        from ..ppt_v2.prompts import PPT_SYSTEM_PROMPT, PPT_USER_PROMPT_TEMPLATE
        return PPT_SYSTEM_PROMPT, PPT_USER_PROMPT_TEMPLATE
    
    else:
        # 使用基础 prompt（保留作为后备）
        from .prompts.base_prompt import BASE_SYSTEM_PROMPT, BASE_USER_PROMPT_TEMPLATE
        return BASE_SYSTEM_PROMPT, BASE_USER_PROMPT_TEMPLATE
