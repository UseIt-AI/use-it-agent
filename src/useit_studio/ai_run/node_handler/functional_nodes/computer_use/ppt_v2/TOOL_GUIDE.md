# PPT V2 Tool 开发指南

## 架构概览

```
ppt_v2/
├── core.py              # create_agent + _build_tool_registry（注册入口）
├── agent.py             # PPTEngineAgent — planner → tool dispatch
├── prompts.py           # Router Planner 的 system/user prompt（含 {action_table} 占位符）
├── models.py            # Planner/action/snapshot 数据模型
├── handler.py           # NodeHandler 桥接层
├── snapshot.py          # Slide 截图辅助
└── tools/
    ├── base.py          # PPTTool Protocol, LLMTool, PassthroughTool, ToolRegistry
    ├── passthrough.py   # 所有 PassthroughTool 实例 + StopTool
    ├── ppt_layout.py    # PPTLayoutTool（LLM 生成 SVG 布局）
    ├── code_execution.py# CodeExecutionTool（LLM 生成代码）
    └── native_chart.py  # NativeChartTool（LLM 生成图表数据）
```

## Tool 类型

| 类型 | 是否调 LLM | 适用场景 | 基类 |
|------|-----------|---------|------|
| **PassthroughTool** | 否 | 参数由 Router Planner 直接给出，无需二次处理 | `PassthroughTool` |
| **LLMTool** | 是 | 需要 LLM 生成复杂输出（SVG、代码、JSON 等） | `LLMTool` |
| **特殊 Tool** | 否 | 控制流（如 `StopTool` 终止循环） | 手动实现 `PPTTool` Protocol |

## 数据流

```
User Request
    ↓
Router Planner（选择 action + 提取 params + description）
    ↓
ToolRegistry.get(action_name) → PPTTool 实例
    ↓
tool.execute_streaming(ToolRequest)
    ↓
  yields:
    - {"type": "reasoning_delta", "content": "..."} （LLMTool 流式思考）
    - {"type": "tool_result", "result": ToolResult}
    ↓
PPTEngineAgent → 发送 tool_call 给前端/引擎
```

## 核心数据结构

### ToolRequest

Tool 的输入，由 Agent 从 Planner 输出构建：

```python
@dataclass
class ToolRequest:
    description: str          # Planner 给出的自然语言意图
    params: Dict[str, Any]    # Planner 给出的结构化参数
    screenshot_base64: str    # 当前 slide 截图
    slide_width: float        # 画布宽度（pt）
    slide_height: float       # 画布高度（pt）
    shapes_context: str       # 当前 slide 上的 shapes 描述
    attached_images: List[str]        # 用户附带的图片
    project_files_context: str        # 项目文件上下文
```

### ToolResult

Tool 的输出，直接映射为前端 `tool_call` 事件：

```python
@dataclass
class ToolResult:
    name: str = "step"            # 几乎总是 "step"，只有 StopTool 返回 "stop"
    args: Dict[str, Any] = {}     # 发送给前端/引擎的参数
    reasoning: str = ""           # 可选的推理文本（用于 UI 展示）
```

**`args` 的标准格式：**

```python
{
    "actions": [{"action": "tool_name", ...其他参数}],
    "return_screenshot": True,
    "current_slide_only": True,
}
```

## 添加 PassthroughTool

适用于不需要 LLM 调用的简单操作。

### 在 `tools/passthrough.py` 中添加

在 `register_passthrough_tools()` 函数内加一个 `registry.register(...)` 调用：

```python
registry.register(PassthroughTool(
    name="your_action_name",
    router_hint="Describe what this tool does. Params: param1 (type), param2 (type).",
))
```

如果需要对参数做变换，可以传 `build_args_fn`：

```python
registry.register(PassthroughTool(
    name="your_action_name",
    router_hint="...",
    build_args_fn=lambda params: {"new_key": params["old_key"] * 2},
))
```

**无需修改其他文件。** `name` 和 `router_hint` 会自动注入 Router Planner 的 action table。

## 添加 LLMTool

适用于需要独立 LLM 调用来生成复杂输出的操作。

### Step 1 — 新建 `tools/your_tool.py`

```python
from __future__ import annotations
from typing import Dict, Any, Optional
from .base import LLMTool, ToolRequest, ToolResult


# System prompt — 定义 LLM 的角色和输出格式
MY_TOOL_SYSTEM_PROMPT = r"""You are a specialist for ...

## Response Format

<thinking>
Analyze the task step by step.
</thinking>

```json
{
    "key": "value"
}
```
"""


class MyNewTool(LLMTool):

    ROUTER_HINT = (
        "One-line description of what this tool does. "
        "Params: description of what the planner should provide."
    )

    def __init__(
        self,
        *,
        model: str,
        api_keys: Optional[Dict[str, str]] = None,
        node_id: str = "",
        max_tokens: int = 8192,
    ):
        super().__init__(
            name="my_action_name",
            router_hint=self.ROUTER_HINT,
            system_prompt=MY_TOOL_SYSTEM_PROMPT,
            model=model,
            api_keys=api_keys,
            node_id=node_id,
            max_tokens=max_tokens,
        )

    def _build_user_prompt(self, request: ToolRequest) -> str:
        """构建发给 LLM 的 user prompt。"""
        lines = [f"## Task\n\n{request.description}"]
        lines.append(f"\n## Slide Canvas: {request.slide_width} × {request.slide_height} pt")
        if request.shapes_context:
            lines.append(f"\n## Current Shapes\n\n{request.shapes_context}")
        if request.project_files_context:
            lines.append(f"\n## Data\n\n```\n{request.project_files_context}\n```")
        lines.append("\nThink in `<thinking>`, then output JSON in a fenced code block.")
        return "\n".join(lines)

    def _parse_llm_output(self, raw_text: str, request: ToolRequest) -> ToolResult:
        """解析 LLM 输出，构建 ToolResult。"""
        reasoning = self._extract_thinking(raw_text)
        payload = self._extract_json(raw_text)

        action = {"action": "my_action_name", **payload}

        return ToolResult(
            name="step",
            args={
                "actions": [action],
                "return_screenshot": True,
                "current_slide_only": True,
            },
            reasoning=reasoning,
        )
```

### Step 2 — 在 `core.py` 中注册

```python
from .tools.your_tool import MyNewTool

def _build_tool_registry(model, api_keys, node_id) -> ToolRegistry:
    registry = ToolRegistry()

    # 现有 tools...
    registry.register(PPTLayoutTool(model=model, api_keys=api_keys, node_id=node_id))
    registry.register(CodeExecutionTool(model=model, api_keys=api_keys, node_id=node_id))
    registry.register(NativeChartTool(model=model, api_keys=api_keys, node_id=node_id))

    # ← 新增
    registry.register(MyNewTool(model=model, api_keys=api_keys, node_id=node_id))

    register_passthrough_tools(registry)
    return registry
```

**无需手动修改 `prompts.py`。** `{action_table}` 占位符在运行时由 `ToolRegistry.build_router_action_table()` 自动生成。

## LLMTool 基类提供的辅助方法

| 方法 | 用途 |
|------|------|
| `_extract_thinking(text)` | 提取 `<thinking>...</thinking>` 中的内容 |
| `_extract_json(text)` | 从 fenced code block 或裸 JSON 中提取 dict |
| `_extract_layout_markup(text)` | 提取 `<svg>...</svg>` 布局标记 |

## 命名规范

| 项目 | 规范 | 示例 |
|------|------|------|
| `name` | snake_case，动词短语 | `render_ppt_layout`, `execute_code`, `insert_native_chart` |
| `router_hint` | 一句话描述 + `Params:` 列出参数 | `"Add a new slide. Params: layout (str), index (int)."` |
| `ToolResult.name` | 正常操作用 `"step"`，终止用 `"stop"` | — |
| 文件名 | snake_case，放在 `tools/` 下 | `native_chart.py`, `code_execution.py` |
| 类名 | PascalCase，以 `Tool` 结尾 | `NativeChartTool`, `CodeExecutionTool` |

## Checklist

- [ ] `name` 全局唯一
- [ ] `router_hint` 写清楚用途和参数
- [ ] LLMTool: 实现 `_build_user_prompt` 和 `_parse_llm_output`
- [ ] LLMTool: system prompt 中明确输出格式（`<thinking>` + fenced JSON/code）
- [ ] `ToolResult.args` 遵循 `{"actions": [...], "return_screenshot": ..., "current_slide_only": ...}` 格式
- [ ] 在 `core.py` 的 `_build_tool_registry` 中注册（LLMTool）或在 `passthrough.py` 的 `register_passthrough_tools` 中注册（PassthroughTool）
