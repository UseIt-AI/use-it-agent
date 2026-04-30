"""
Agent Node 工具协议 —— Tool 是一等公民。

设计要点
--------
1. `AgentTool`（Protocol）是所有 tool 的契约；`BaseTool` 是默认实现基类。
2. `EngineTool` / `InlineTool` 两个直接子类，对应两种 `execution_mode`：
   - `engine`：产出 `ToolCall` 丢给前端 / Local Engine（PPT/Excel/Word/AutoCAD/
     GUI/Browser/Code）。
   - `inline`：在 handler 进程里直接 `await run()`，返回文本喂给下一轮 Planner
     （web_search / rag / doc_extract）。
3. `ToolPack` 是一个**很薄**的软件级共享参数对象，只承担三件事：
   - snapshot 自动加载（`detect_from_snapshot`）
   - 整组 API Key / Env 权限门
   - 共享 router_fragment（写进 system prompt 的一句话）
   每个具体 tool 的 schema/permission/payload 仍然由 tool 自己承载。
4. 每个 `tools/<software>/` 子包只需要两个文件：`_pack.py`（pack 子类）
   + `tools.py`（tool 类 + `TOOLS` 列表）。`tools/__init__.py` 自动扫描装配。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import (
    Any,
    AsyncGenerator,
    ClassVar,
    Dict,
    List,
    Literal,
    Optional,
    Protocol,
    TYPE_CHECKING,
    runtime_checkable,
)

if TYPE_CHECKING:
    from useit_studio.ai_run.node_handler.base_v2 import NodeContext
    from ..models import (
        PlannerOutput,
    )


# =============================================================================
# 1. 基础数据类型
# =============================================================================

ExecutionMode = Literal["engine", "inline"]


@dataclass
class ToolCall:
    """engine tool 产出的 tool_call 事件 payload（只含 name 和 args）。

    handler 拿到后会补上 target / id / type 等字段形成完整 tool_call 事件。
    """

    name: str
    args: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PermissionResult:
    """单次 tool 调用的权限判定结果。"""

    decision: Literal["allow", "ask", "deny"] = "allow"
    reason: str = ""
    updated_params: Optional[Dict[str, Any]] = None
    """允许权限层改写参数（例如把相对路径转绝对路径、脱敏等）；None 表示不改。"""


# =============================================================================
# 2. AgentTool Protocol —— 所有 tool 的对外契约
# =============================================================================


@runtime_checkable
class AgentTool(Protocol):
    """所有 Agent Node 工具必须满足的最小契约。"""

    name: str
    """唯一工具名，例如 "ppt_add_slide" / "gui_click" / "tool_web_search"。"""

    group: str
    """所属 ToolPack 的 name（如 "ppt"）。独立 inline tool 为空串。"""

    execution_mode: ExecutionMode
    target: str
    """engine tool_call 事件的 target；inline tool 为 ""。"""

    router_hint: str
    """写入 Router 的 action table 的一行描述。"""

    router_detail: str
    """详尽的 schema / 例子 / 使用指南（多行 Markdown），在 Router system prompt
    的 action table 之后作为独立 `### <tool_name>` 块注入。可为空串。"""

    input_schema: Dict[str, Any]
    """JSON Schema（面向未来 function_calling / 前端表单生成）。"""

    is_read_only: bool
    is_destructive: bool

    def is_enabled(self, ctx: "NodeContext") -> bool: ...

    def check_permission(
        self, ctx: "NodeContext", params: Dict[str, Any]
    ) -> PermissionResult: ...


# =============================================================================
# 3. ToolPack —— 软件级共享参数对象（很薄）
# =============================================================================


class ToolPack:
    """一类 tool 的"软件级"共享参数。

    子类只覆盖需要的字段；**不参与 tool 构造**，tool 自己是独立的类实例。

    Example
    -------
    >>> class PPTPack(ToolPack):
    ...     name = "ppt"
    ...     default_target = "ppt"
    ...     router_fragment = "- **ppt_\\***: PowerPoint via Local Engine."
    ...     @classmethod
    ...     def detect_from_snapshot(cls, ctx) -> bool:
    ...         return has_any(extract_snapshot_dict(ctx), ["presentation_info"])
    """

    name: ClassVar[str] = ""
    """pack 唯一名；tool.group 字段与此对齐。"""

    default_target: ClassVar[str] = ""
    """pack 下 engine tool 的默认 target（tool 可单独覆盖）。"""

    required_api_keys: ClassVar[List[str]] = []
    required_env_keys: ClassVar[List[str]] = []

    router_fragment: ClassVar[str] = ""
    """拼入 Router system prompt 的一句话能力说明。"""

    @classmethod
    def detect_from_snapshot(cls, ctx: "NodeContext") -> bool:
        """snapshot 自动启用钩子。默认不启用。"""
        return False


# =============================================================================
# 4. BaseTool / EngineTool / InlineTool —— 给具体 tool 继承的基类
# =============================================================================


class BaseTool:
    """所有具体 tool 的最小基类（满足 AgentTool Protocol）。"""

    name: ClassVar[str] = ""
    group: ClassVar[str] = ""
    execution_mode: ClassVar[ExecutionMode] = "engine"
    target: ClassVar[str] = ""
    router_hint: ClassVar[str] = ""
    router_detail: ClassVar[str] = ""
    input_schema: ClassVar[Dict[str, Any]] = {
        "type": "object",
        "properties": {},
    }
    is_read_only: ClassVar[bool] = False
    is_destructive: ClassVar[bool] = False

    def is_enabled(self, ctx: "NodeContext") -> bool:
        return True

    def check_permission(
        self, ctx: "NodeContext", params: Dict[str, Any]
    ) -> PermissionResult:
        return PermissionResult()


class EngineTool(BaseTool):
    """通过 tool_call 事件发到前端/Local Engine 执行的 tool。

    子类通常只需：
    - 设置 `name / router_hint / input_schema`
    - 如果协议不是 /step，覆盖 `build_tool_call`
    - 如果 action 名不等于 `name` 去前缀，覆盖 `action_name` property
    """

    execution_mode: ClassVar[ExecutionMode] = "engine"

    @property
    def action_name(self) -> str:
        """Local Engine 认识的原生 action 名（默认去掉 `<group>_` 前缀）。"""
        prefix = f"{self.group}_"
        if self.group and self.name.startswith(prefix):
            return self.name[len(prefix):]
        return self.name

    def build_tool_call(
        self,
        params: Dict[str, Any],
        planner_output: "PlannerOutput",
    ) -> ToolCall:
        """默认实现：/step 协议（ppt / excel / word / autocad 适用）。

        params 已由 handler 从 planner_output.tool_params 取出，不再嵌套。
        """
        params = dict(params)
        return_screenshot = params.pop("return_screenshot", True)
        current_slide_only = params.pop("current_slide_only", True)
        return ToolCall(
            name="step",
            args={
                "actions": [{"action": self.action_name, **params}],
                "return_screenshot": return_screenshot,
                "current_slide_only": current_slide_only,
            },
        )


class InlineTool(BaseTool):
    """在 handler 进程内直接 await 的服务端 tool。

    子类必须实现 `async def run(params, ctx) -> str`；返回文本会被写入
    last_execution_output 喂给下一步 Planner。
    """

    execution_mode: ClassVar[ExecutionMode] = "inline"
    target: ClassVar[str] = ""

    async def run(
        self, params: Dict[str, Any], ctx: "NodeContext"
    ) -> str:
        raise NotImplementedError(
            f"InlineTool subclass '{type(self).__name__}' must implement run()"
        )


class LLMEngineTool(EngineTool):
    """带独立 LLM 调用的 engine tool（两阶段 tool）。

    用于 **Router Planner 不适合亲自产出**的重型内容——典型场景：
    - 生成整张幻灯片的 SVG 布局（数千 token，需要专注的排版思考）
    - 规划 native chart 的 chart_type / data / bounding_box
    - 写 PowerShell / Python COM 代码（需要带一堆 pitfall 指南）

    两阶段工作流
    -------------
    1. **Router 侧**：`router_hint` / `router_detail` 只教 Router *何时* 选这个
       tool。Router 的 `Params` 只给"路由信息"——例如 `slide`、`render_mode`
       加一段自然语言 `Description`。
    2. **Tool 侧**：收到 Params 后调用自己独立的 LLM（带聚焦的 `system_prompt`），
       把 description 扩展成 SVG / chart JSON / code，再包成 ToolCall 下发给
       Local Engine。

    子类需要实现
    ------------
    - `system_prompt`: 聚焦的子 LLM system prompt（把老 LLMTool 的
      system_prompt 放这里即可）。
    - `_build_user_prompt(params, planner_output, ctx) -> str`
    - `_parse_llm_output(raw_text, params, planner_output, ctx) -> ToolCall`

    可选覆盖
    ---------
    - `preferred_model`: 强制使用某个模型（否则跟随 ctx.planner_model）
    - `max_tokens` / `temperature`

    sub-LLM 的流式 token 以 `{"type":"reasoning_delta","content":...}` 向上游
    吐出；完成时吐 `{"type":"tool_call","result":ToolCall}`。Handler 会把这些
    事件映射成 UI 能看到的 `cua_delta` + 最终的 `tool_call` 事件。
    """

    system_prompt: ClassVar[str] = ""
    preferred_model: ClassVar[Optional[str]] = None
    max_tokens: ClassVar[int] = 16384
    temperature: ClassVar[float] = 0.4

    def _build_user_prompt(
        self,
        params: Dict[str, Any],
        planner_output: "PlannerOutput",
        ctx: "NodeContext",
    ) -> str:
        raise NotImplementedError(
            f"LLMEngineTool '{type(self).__name__}' must implement _build_user_prompt()"
        )

    def _parse_llm_output(
        self,
        raw_text: str,
        params: Dict[str, Any],
        planner_output: "PlannerOutput",
        ctx: "NodeContext",
    ) -> ToolCall:
        raise NotImplementedError(
            f"LLMEngineTool '{type(self).__name__}' must implement _parse_llm_output()"
        )

    def build_tool_call(
        self,
        params: Dict[str, Any],
        planner_output: "PlannerOutput",
    ) -> ToolCall:
        """关闭同步路径：LLMEngineTool 必须走 produce_tool_call_streaming。"""
        raise RuntimeError(
            f"LLMEngineTool '{type(self).__name__}' cannot use synchronous "
            f"build_tool_call; handler must dispatch via produce_tool_call_streaming."
        )

    async def produce_tool_call_streaming(
        self,
        params: Dict[str, Any],
        planner_output: "PlannerOutput",
        ctx: "NodeContext",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """调一次子 LLM，流式吐 reasoning token，完成时吐 ToolCall。

        yield 事件：
        - `{"type": "reasoning_delta", "content": <str>}`
        - `{"type": "tool_call", "result": ToolCall}`
        - `{"type": "error", "content": <str>}`
        """
        from useit_studio.ai_run.node_handler.functional_nodes.computer_use.gui_v2.utils.llm_client import (
            LLMConfig,
            VLMClient,
        )
        from useit_studio.ai_run.utils.logger_utils import LoggerUtils

        try:
            user_prompt = self._build_user_prompt(params, planner_output, ctx)
        except Exception as e:  # noqa: BLE001
            yield {
                "type": "error",
                "content": f"[{self.name}] failed to build user prompt: {e}",
            }
            return

        node_data = (ctx.node_dict or {}).get("data", {}) if ctx.node_dict else {}
        model = self.preferred_model or node_data.get("model") or ctx.planner_model

        logger = LoggerUtils(component_name=f"LLMEngineTool:{self.name}")
        vlm = VLMClient(
            config=LLMConfig(
                model=model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                role=f"tool:{self.name}",
                node_id=ctx.node_id,
            ),
            api_keys=ctx.planner_api_keys,
            logger=logger,
        )

        screenshot_b64 = _extract_screenshot_base64(ctx)
        attached_images_b64 = _extract_attached_images_base64(ctx)

        full_content: List[str] = []
        try:
            async for chunk in vlm.stream(
                prompt=user_prompt,
                system_prompt=self.system_prompt,
                screenshot_base64=screenshot_b64,
                attached_images_base64=attached_images_b64 or None,
            ):
                ctype = chunk.get("type")
                if ctype == "delta":
                    content = chunk.get("content", "")
                    if isinstance(content, list):
                        content = "".join(str(c) for c in content)
                    full_content.append(content)
                    yield {"type": "reasoning_delta", "content": content}
                elif ctype == "complete":
                    raw_text = chunk.get("content") or "".join(full_content)
                    try:
                        tool_call = self._parse_llm_output(
                            raw_text, params, planner_output, ctx
                        )
                    except Exception as e:  # noqa: BLE001
                        yield {
                            "type": "error",
                            "content": f"[{self.name}] failed to parse LLM output: {e}",
                        }
                        return
                    yield {"type": "tool_call", "result": tool_call}
                    return
                elif ctype == "error":
                    yield {
                        "type": "error",
                        "content": f"[{self.name}] sub-LLM error: {chunk.get('content')}",
                    }
                    return
        except Exception as e:  # noqa: BLE001
            yield {
                "type": "error",
                "content": f"[{self.name}] sub-LLM stream failed: {e}",
            }
            return


def _extract_screenshot_base64(ctx: "NodeContext") -> Optional[str]:
    """Try a few canonical locations where the Local Engine snapshot keeps the
    current slide screenshot; return `None` if absent."""
    try:
        from .helpers import extract_snapshot_dict
    except ImportError:  # pragma: no cover
        return None
    snap = extract_snapshot_dict(ctx)
    for key in ("screenshot", "screenshot_base64"):
        v = snap.get(key) if isinstance(snap, dict) else None
        if isinstance(v, str) and v:
            return v.split(",", 1)[-1] if v.startswith("data:") else v
    return None


def _extract_attached_images_base64(ctx: "NodeContext") -> List[str]:
    """Flatten ctx.attached_images into raw base64 strings (strip data: prefix)."""
    out: List[str] = []
    for item in ctx.attached_images or []:
        if not isinstance(item, dict):
            continue
        v = item.get("base64")
        if not isinstance(v, str) or not v:
            continue
        if v.startswith("data:") and "," in v:
            v = v.split(",", 1)[1]
        out.append(v)
    return out
