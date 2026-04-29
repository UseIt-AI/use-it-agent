"""
PPT V2 Tool Registry

Tools are the execution units dispatched by the Router Planner.
Each tool is self-describing (name + router_hint) and the Router Planner's
action table is auto-generated from whatever tools are registered.

Two kinds of tools:
  - LLMTool: has its own VLMClient + focused prompt (Layout, Code, Chart)
  - PassthroughTool: no LLM, directly forwards router params
"""

from .base import (
    PPTTool,
    LLMTool,
    PassthroughTool,
    ToolRegistry,
    ToolRequest,
    ToolResult,
)

__all__ = [
    "PPTTool",
    "LLMTool",
    "PassthroughTool",
    "ToolRegistry",
    "ToolRequest",
    "ToolResult",
]
