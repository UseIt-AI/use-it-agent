"""
PPT V2 Tool System — Base Classes

PPTTool protocol, LLMTool / PassthroughTool base implementations,
ToolRequest / ToolResult data classes, and the ToolRegistry.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import (
    Any,
    AsyncGenerator,
    Callable,
    Dict,
    List,
    Optional,
    Protocol,
    runtime_checkable,
)

from useit_studio.ai_run.node_handler.functional_nodes.computer_use.gui_v2.utils.llm_client import (
    VLMClient,
    LLMConfig,
)
from useit_studio.ai_run.utils.logger_utils import LoggerUtils


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ToolRequest:
    """Carrier from the Router Planner to a Tool."""

    description: str = ""
    """Natural-language intent from the Router Planner (e.g. "Draw an org chart …")."""

    params: Dict[str, Any] = field(default_factory=dict)
    """Structured params forwarded from the Router Planner's JSON output."""

    screenshot_base64: Optional[str] = None
    slide_width: float = 960.0
    slide_height: float = 540.0
    shapes_context: str = ""
    attached_images: List[str] = field(default_factory=list)
    project_files_context: str = ""


@dataclass
class ToolResult:
    """What a tool returns — directly maps to a ``tool_call`` event."""

    name: str = "step"
    """tool_call name, almost always ``"step"`` for the PPT local engine."""

    args: Dict[str, Any] = field(default_factory=dict)
    """tool_call args sent to the frontend / engine."""

    reasoning: str = ""
    """Optional reasoning text for UI display (from an LLM tool's thinking)."""


# ---------------------------------------------------------------------------
# PPTTool Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class PPTTool(Protocol):
    """
    Minimal protocol every PPT tool must satisfy.

    ``ToolRegistry`` only depends on this protocol so that both LLM-powered
    and passthrough tools can be registered uniformly.
    """

    @property
    def name(self) -> str:
        """Unique action name, e.g. ``"render_ppt_layout"``."""
        ...

    @property
    def router_hint(self) -> str:
        """One-line description injected into the Router Planner's action table."""
        ...

    async def execute(self, request: ToolRequest) -> ToolResult:
        """Execute and return a result (non-streaming)."""
        ...

    async def execute_streaming(
        self, request: ToolRequest
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Execute with streaming.

        Yields dicts with at least a ``"type"`` key:
        - ``{"type": "reasoning_delta", "content": "..."}``
        - ``{"type": "tool_result", "result": ToolResult}``
        """
        ...  # pragma: no cover


# ---------------------------------------------------------------------------
# LLMTool — base for tools that need their own LLM call
# ---------------------------------------------------------------------------

class LLMTool:
    """
    Base class for tools that own a VLMClient and a focused prompt pair.

    Subclasses must override:
    - ``_build_user_prompt(request)``
    - ``_parse_llm_output(raw_text, request) -> ToolResult``
    """

    def __init__(
        self,
        *,
        name: str,
        router_hint: str,
        system_prompt: str,
        model: str,
        api_keys: Optional[Dict[str, str]] = None,
        node_id: str = "",
        max_tokens: int = 16384,
        router_detail: str = "",
    ):
        self._name = name
        self._router_hint = router_hint
        self._router_detail = router_detail
        self._system_prompt = system_prompt
        self._logger = LoggerUtils(component_name=f"Tool:{name}")

        llm_config = LLMConfig(
            model=model,
            max_tokens=max_tokens,
            temperature=0.4,
            role=f"ppt_tool_{name}",
            node_id=node_id,
        )
        self.vlm = VLMClient(config=llm_config, api_keys=api_keys, logger=self._logger)

    # -- Protocol properties --------------------------------------------------

    @property
    def name(self) -> str:
        return self._name

    @property
    def router_hint(self) -> str:
        return self._router_hint

    @property
    def router_detail(self) -> str:
        return self._router_detail

    # -- Abstract interface (subclass must implement) -------------------------

    def _build_user_prompt(self, request: ToolRequest) -> str:
        raise NotImplementedError

    def _parse_llm_output(self, raw_text: str, request: ToolRequest) -> ToolResult:
        raise NotImplementedError

    # -- Concrete execute / execute_streaming ---------------------------------

    async def execute(self, request: ToolRequest) -> ToolResult:
        prompt = self._build_user_prompt(request)
        response = await self.vlm.call(
            prompt=prompt,
            system_prompt=self._system_prompt,
            screenshot_base64=request.screenshot_base64,
            attached_images_base64=request.attached_images or None,
        )
        return self._parse_llm_output(response["content"], request)

    async def execute_streaming(
        self, request: ToolRequest
    ) -> AsyncGenerator[Dict[str, Any], None]:
        prompt = self._build_user_prompt(request)

        full_content = ""
        _thinking_open = False
        _thinking_close = False

        async for chunk in self.vlm.stream(
            prompt=prompt,
            system_prompt=self._system_prompt,
            screenshot_base64=request.screenshot_base64,
            attached_images_base64=request.attached_images or None,
        ):
            if chunk["type"] == "delta":
                content = chunk["content"]
                if isinstance(content, list):
                    content = "".join(str(c) for c in content)
                full_content += content

                if not _thinking_open and "<thinking>" in full_content:
                    _thinking_open = True
                should_send = _thinking_open and not _thinking_close
                if not _thinking_close and "</thinking>" in full_content:
                    _thinking_close = True

                if should_send:
                    yield {
                        "type": "reasoning_delta",
                        "content": content,
                        "source": f"tool:{self._name}",
                    }

            elif chunk["type"] == "complete":
                result = self._parse_llm_output(full_content, request)
                yield {"type": "tool_result", "result": result}

            elif chunk["type"] == "error":
                yield {"type": "error", "content": chunk["content"]}

    # -- Helpers available to subclasses --------------------------------------

    @staticmethod
    def _extract_thinking(text: str) -> str:
        m = re.search(r"<thinking>(.*?)</thinking>", text, re.DOTALL | re.IGNORECASE)
        return m.group(1).strip() if m else ""

    @staticmethod
    def _extract_json(text: str) -> Dict[str, Any]:
        """Best-effort JSON extraction (code-block aware)."""
        m = re.search(r"```(?:json)?\s*(\{.+\})\s*```", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
        raise ValueError(f"Cannot extract JSON from tool output: {text[:200]}…")

    @staticmethod
    def _extract_layout_markup(text: str) -> str:
        """Extract the first layout markup block from LLM output."""
        m = re.search(r"(<svg[\s\S]*?</svg>)", text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
        raise ValueError("No layout markup found in tool output")


# ---------------------------------------------------------------------------
# PassthroughTool — no LLM, directly forward router params
# ---------------------------------------------------------------------------

class PassthroughTool:
    """
    Tool that maps Router Planner params straight into a ``tool_call``.

    The optional *build_args_fn* can reshape ``params`` before emission;
    if omitted the params are forwarded verbatim.
    """

    def __init__(
        self,
        *,
        name: str,
        router_hint: str,
        build_args_fn: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
        router_detail: str = "",
    ):
        self._name = name
        self._router_hint = router_hint
        self._router_detail = router_detail
        self._build_args_fn = build_args_fn

    @property
    def name(self) -> str:
        return self._name

    @property
    def router_hint(self) -> str:
        return self._router_hint

    @property
    def router_detail(self) -> str:
        return self._router_detail

    async def execute(self, request: ToolRequest) -> ToolResult:
        params = dict(request.params)
        return_screenshot = params.pop("return_screenshot", True)
        current_slide_only = params.pop("current_slide_only", True)

        if self._build_args_fn:
            result = self._build_args_fn(params)
        else:
            result = params

        if isinstance(result, list):
            actions = [{"action": self._name, **p} for p in result]
        else:
            actions = [{"action": self._name, **result}]

        return ToolResult(
            name="step",
            args={
                "actions": actions,
                "return_screenshot": return_screenshot,
                "current_slide_only": current_slide_only,
            },
        )

    async def execute_streaming(
        self, request: ToolRequest
    ) -> AsyncGenerator[Dict[str, Any], None]:
        result = await self.execute(request)
        yield {"type": "tool_result", "result": result}


# ---------------------------------------------------------------------------
# ToolRegistry
# ---------------------------------------------------------------------------

class ToolRegistry:
    """
    Holds registered ``PPTTool`` instances and dispatches by action name.

    The Router Planner's action table is auto-generated from whatever
    tools are registered — no manual prompt maintenance required.
    """

    def __init__(self) -> None:
        self._tools: Dict[str, PPTTool] = {}

    def register(self, tool: PPTTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[PPTTool]:
        return self._tools.get(name)

    @property
    def tool_names(self) -> List[str]:
        return list(self._tools.keys())

    # Tools whose detailed reference is only useful when the slide already
    # contains elements (editing/styling scenarios).  On a blank slide these
    # sections are omitted to save prompt tokens.
    _DETAIL_NEEDS_ELEMENTS = frozenset({
        "update_element", "execute_code", "align_elements",
        "reorder_elements", "add_shape_animation",
    })

    def build_router_action_table(self, *, has_elements: bool = True) -> str:
        """
        Auto-generate the action reference for the Router Planner.

        Produces two sections:
        1. A bullet-list summary of every tool (from ``router_hint``).
        2. Expanded reference sections for tools that provide ``router_detail``
           — conditionally filtered by *has_elements*.

        When *has_elements* is ``False`` (blank slide), detailed references for
        editing-only tools (``update_element``, ``execute_code``) are omitted.
        """
        summary_lines: List[str] = []
        detail_blocks: List[str] = []
        for tool in self._tools.values():
            summary_lines.append(f"- **{tool.name}**: {tool.router_hint}")
            detail = getattr(tool, "router_detail", "")
            if detail:
                if not has_elements and tool.name in self._DETAIL_NEEDS_ELEMENTS:
                    continue
                detail_blocks.append(f"### {tool.name}\n\n{detail}")

        result = "\n".join(summary_lines)
        if detail_blocks:
            result += "\n\n" + "\n\n---\n\n".join(detail_blocks)
        return result
