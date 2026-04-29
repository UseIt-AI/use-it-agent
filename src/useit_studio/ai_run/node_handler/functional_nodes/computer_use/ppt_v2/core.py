"""
PowerPoint Agent V2 — Core Factory

Builds the PPTEngineAgent with:
  - A ToolRegistry holding all LLM-powered and passthrough tools
  - A Router Planner whose action table is auto-generated from the registry
"""

from typing import Optional, Dict

from ..office_agent import (
    OfficeAgentConfig,
    OfficePlanner,
    OfficePlannerConfig,
    OfficeAppType,
)
from .agent import PPTEngineAgent
from .prompts import ROUTER_SYSTEM_PROMPT, ROUTER_USER_PROMPT_TEMPLATE

from .tools.base import ToolRegistry
from .tools.ppt_layout import PPTLayoutTool
from .tools.code_execution import CodeExecutionTool
from .tools.native_chart import NativeChartTool
from .tools.passthrough import register_passthrough_tools


def _build_tool_registry(
    model: str,
    api_keys: Optional[Dict[str, str]],
    node_id: str,
) -> ToolRegistry:
    """Create and populate the tool registry."""
    registry = ToolRegistry()

    # LLM-powered tools (share the same model as the router planner)
    registry.register(PPTLayoutTool(model=model, api_keys=api_keys, node_id=node_id))
    registry.register(CodeExecutionTool(model=model, api_keys=api_keys, node_id=node_id))
    registry.register(NativeChartTool(model=model, api_keys=api_keys, node_id=node_id))

    # Simple passthrough tools
    register_passthrough_tools(registry)

    return registry


def create_agent(
    planner_model: str = "gpt-4o-mini",
    actor_model: str = "gpt-4o-mini",
    api_keys: Optional[Dict[str, str]] = None,
    node_id: str = "",
) -> PPTEngineAgent:
    """
    Factory function for PPTEngineAgent.

    Args:
        planner_model: Model used by the Router Planner AND LLM tools.
        actor_model: Reserved for compatibility; unused.
        api_keys: API key dictionary.
        node_id: Node ID for logging / billing.

    Returns:
        Fully wired PPTEngineAgent instance.
    """
    # 1. Build tool registry
    registry = _build_tool_registry(planner_model, api_keys, node_id)

    # 2. Build the initial system prompt (full detail for first step)
    router_system = ROUTER_SYSTEM_PROMPT.replace(
        "{action_table}",
        registry.build_router_action_table(has_elements=True),
    )

    # 3. Create the Router Planner (same OfficePlanner class, just lighter prompt)
    config = OfficeAgentConfig(
        planner_model=planner_model,
        actor_model=actor_model,
        app_type=OfficeAppType.POWERPOINT,
    )

    planner_config = OfficePlannerConfig(
        model=planner_model,
        max_tokens=32768,
        app_type=OfficeAppType.POWERPOINT,
    )

    planner = OfficePlanner(
        config=planner_config,
        api_keys=api_keys,
        node_id=node_id,
        system_prompt=router_system,
        user_prompt_template=ROUTER_USER_PROMPT_TEMPLATE,
    )

    # 4. Assemble the agent (pass prompt template for per-step dynamic rebuild)
    return PPTEngineAgent(
        config=config,
        planner=planner,
        tool_registry=registry,
        api_keys=api_keys,
        node_id=node_id,
        system_prompt_template=ROUTER_SYSTEM_PROMPT,
    )


# Backward-compatible alias
PPTAgent = PPTEngineAgent

__all__ = ["create_agent", "PPTAgent", "PPTEngineAgent"]
