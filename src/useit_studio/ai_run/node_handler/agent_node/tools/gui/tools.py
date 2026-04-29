"""GUI tools —— 扁平 payload: {name: action, args: {...}}（不是 /step）。"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, TYPE_CHECKING

from ..protocol import EngineTool, ToolCall

if TYPE_CHECKING:
    from ...models import (
        PlannerOutput,
    )


class _GUIEngineTool(EngineTool):
    """GUI 共享基类：覆盖 build_tool_call 成扁平协议。"""

    group: ClassVar[str] = "gui"
    target: ClassVar[str] = "gui"

    def build_tool_call(
        self, params: Dict[str, Any], planner_output: "PlannerOutput"
    ) -> ToolCall:
        return ToolCall(name=self.action_name, args=dict(params))


class GUIClick(_GUIEngineTool):
    name = "gui_click"
    router_hint = "Mouse click on a screen coordinate. Params: x, y, button ('left'/'right')."
    input_schema = {
        "type": "object",
        "properties": {
            "x": {"type": "integer"},
            "y": {"type": "integer"},
            "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"},
        },
        "required": ["x", "y"],
    }


class GUIType(_GUIEngineTool):
    name = "gui_type"
    router_hint = "Type text at the current focus. Params: text."
    input_schema = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    }


class GUIKey(_GUIEngineTool):
    name = "gui_key"
    router_hint = "Press a key or key combo. Params: keys (e.g. 'ctrl+s')."
    input_schema = {
        "type": "object",
        "properties": {"keys": {"type": "string"}},
        "required": ["keys"],
    }


class GUIScroll(_GUIEngineTool):
    name = "gui_scroll"
    router_hint = "Scroll the screen. Params: x, y, direction, amount."
    input_schema = {
        "type": "object",
        "properties": {
            "x": {"type": "integer"},
            "y": {"type": "integer"},
            "direction": {"type": "string", "enum": ["up", "down", "left", "right"]},
            "amount": {"type": "integer", "default": 3},
        },
        "required": ["direction"],
    }


class GUIScreenshot(_GUIEngineTool):
    name = "gui_screenshot"
    router_hint = "Capture a fresh screenshot."
    is_read_only = True
    input_schema = {"type": "object", "properties": {}}


TOOLS = [GUIClick(), GUIType(), GUIKey(), GUIScroll(), GUIScreenshot()]
