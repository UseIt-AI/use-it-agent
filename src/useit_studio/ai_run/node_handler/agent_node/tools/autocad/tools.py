"""AutoCAD tools —— 完整迁移自 ``functional_nodes/computer_use/autocad``。

设计要点
--------
1. **协议**：AutoCAD Local Engine 不使用 ``/step`` 协议；每个 action 是一个
   扁平 tool_call（``name`` 直接是 ``draw_from_json`` / ``execute_python_com``
   / ``snapshot`` …）。所有 :class:`_AutoCADEngineTool` 子类覆写
   :meth:`build_tool_call` 让其产出扁平结构，**不要**走父类
   :class:`EngineTool` 的默认 ``/step`` 包装。
2. **工具拆分**：与 PPT/Excel/Word 平行，每个用户语义对应一个 tool；
   多个相关 action（open/close/new/activate；list/preset/draw 标准件）通过
   ``action`` 判别字段合并为一个 tool 以减小 action table 的噪声。
3. **router_detail**：每个 tool 携带的 router_detail 一并把
   ``functional_nodes/.../autocad/prompts.py`` 里的相关指南片段搬过来，
   让统一 Router Planner 看到完整的能力描述与坐标 / COM 注意事项。

迁移自 ``functional_nodes/computer_use/autocad/{prompts.py,handler.py,
core.py,autocadHandler.api.md}``。
"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, List, TYPE_CHECKING

from ..protocol import EngineTool, ToolCall

if TYPE_CHECKING:
    from ...models import (
        PlannerOutput,
    )


# ==========================================================================
# Base class — flat (NOT /step) tool_call protocol
# ==========================================================================


class _AutoCADEngineTool(EngineTool):
    """所有 AutoCAD engine tool 的共享基类。

    AutoCAD Local Engine（``/api/v1/autocad/v2/...``）期望的 tool_call payload
    形如::

        {"target": "autocad", "name": "<action>", "args": {...flat params...}}

    与 PPT/Word/Excel 用的 ``/step`` 协议（``{"name": "step", "args":
    {"actions": [{"action": ..., ...}]}}``）截然不同，因此必须覆写
    :meth:`build_tool_call`，**不能**继承 :class:`EngineTool` 的默认实现 ——
    那是 4/24 把 autocad_execute_code 接进 agent_node 时的核心 bug：
    /step 包装让 Local Engine 直接 4xx 把 code 丢回。
    """

    group: ClassVar[str] = "autocad"
    target: ClassVar[str] = "autocad"

    @property
    def action_name(self) -> str:
        """AutoCAD Local Engine 认识的原生 action 名（默认去掉 ``autocad_`` 前缀）。"""
        prefix = "autocad_"
        if self.name.startswith(prefix):
            return self.name[len(prefix):]
        return self.name

    def build_tool_call(
        self,
        params: Dict[str, Any],
        planner_output: "PlannerOutput",
    ) -> ToolCall:
        """扁平形态：``{name: "<action>", args: {...params}}``，不走 /step。

        子类如果需要把 ``action`` 判别字段映射成不同的 engine action（参考
        :class:`AutoCADDocument` / :class:`AutoCADStandardPart`），覆写本方法。
        """
        args = {k: v for k, v in params.items() if v is not None}
        return ToolCall(name=self.action_name, args=args)


# ==========================================================================
# Detail blocks — pieced into Router system prompt
# ==========================================================================

_AUTOCAD_PROTOCOL_DETAIL = r"""## AutoCAD Local Engine ——  `/api/v1/autocad/v2`

AutoCAD 走**扁平协议**：每个 `autocad_*` 工具直接对应一个 action（`draw_from_json` /
`execute_python_com` / `snapshot` …），与 PPT/Word/Excel 的 `/step` 协议**不同**。

### 决策优先级

**当 # Available Skills 存在时（首选 skill 的工作流）：**

1. 严格按 skill 的步骤顺序执行，**不要跳步**。
2. 用 `read_file`（通用 inline tool）按需加载 skill 的模板 / 参数 / 参考文档。
3. 如果 skill 提供了计算脚本，用 `run_skill_script` 把所有坐标 / 尺寸**一次性确
   定性地预计算**好；之后 `autocad_draw_from_json` 直接拿脚本输出来画 ——
   **不要**自己重新算坐标。
4. **每次只画一个组件**，画完等截图回来再画下一个；不要一次性塞多个组件进 `data`。

**当没有 # Available Skills 时：**

1. **Mode A first** —— `autocad_draw_from_json` 处理所有结构化绘图（直线、圆、
   弧、多段线、文字、标注）；可靠、确定性高、token 用量少。
2. **Mode B fallback** —— `autocad_execute_python_com` 处理 Mode A 不支持的
   操作（hatch / block / mirror / array / offset / 删除 / 修改实体属性 / AutoLISP）。
3. **Document lifecycle** —— `autocad_document` 一把覆盖 `open` / `close` /
   `new` / `activate`。
4. **状态/快照** —— `autocad_status` 检查是否在运行；`autocad_snapshot` 拉当前
   图纸内容 + 截图。

### 坐标与精度

- 坐标系：模型空间，单位由当前 .dwg 决定；通常用 mm 或 m。
- 精度要求：所有坐标 / 长度 / 角度保留 **2 位小数**；不要让 LLM "心算" 大数字。
- 颜色索引：`1=红 2=黄 3=绿 4=青 5=蓝 6=洋红 7=白/黑 256=ByLayer 0=ByBlock`。

### 通用规则

- 若用户 goal 提到了 .dwg 文件路径，必须 `autocad_document action="open"` 打开
  那个文件；**不要**默认 `action="new"` 创建空白图。
- 若 AutoCAD 未运行（desktop snapshot 没有 `AutoCAD.exe`），先 `autocad_launch`
  或 `system_process_control action="launch" name="AutoCAD"`。
- 执行成功后**不要重复**同一个 action —— 看 last_execution_output 的 SUCCESS 即
  推进到下一步。
"""


_AUTOCAD_DRAW_FROM_JSON_DETAIL = r"""使用 JSON 数据**一次性**绘制多个图形。Mode A，**首选**。

### 顶层 Args

| 参数 | 类型 | 说明 |
|------|------|------|
| `data` | object | `{ "layer_colors": {...}, "elements": {...} }` |
| `timeout` | int | 默认 60 秒 |
| `return_screenshot` | bool | 默认 true |

### `data.layer_colors`

`{ "图层名": <颜色索引>, ... }`，可选；引擎自动建立缺失的图层。

### `data.elements`

支持以下 6 类元素，每个元素都接受可选 `layer` (string) 与 `color` (int)：

#### `lines`
```json
{ "start": [x, y, z], "end": [x, y, z], "layer": "name", "color": 7 }
```

#### `circles`
```json
{ "center": [x, y, z], "radius": r, "layer": "name" }
```

#### `arcs`
```json
{ "center": [x, y, z], "radius": r,
  "start_angle": deg, "end_angle": deg, "layer": "name" }
```

#### `polylines`
```json
{ "vertices": [[x, y], ...], "closed": true, "layer": "name" }
```

#### `texts`
```json
{ "text": "content", "position": [x, y, z], "height": h, "layer": "name" }
```

#### `dimensions`

```json
// Aligned 对齐标注
{ "type": "Aligned", "point1": [...], "point2": [...], "text_position": [...] }
// Rotated 旋转标注
{ "type": "Rotated", "point1": [...], "point2": [...], "text_position": [...], "rotation": 90 }
// Radial 半径标注
{ "type": "Radial", "center": [...], "chord_point": [...] }
// Angular 角度标注
{ "type": "Angular", "center": [...], "point1": [...], "point2": [...], "text_position": [...] }
```

### 综合示例：带标注的矩形

```json
{
  "Action": "autocad_draw_from_json",
  "Params": {
    "data": {
      "layer_colors": {"轮廓": 7, "标注": 3, "文字": 1},
      "elements": {
        "lines": [
          {"start": [0, 0, 0], "end": [200, 0, 0], "layer": "轮廓"},
          {"start": [200, 0, 0], "end": [200, 100, 0], "layer": "轮廓"},
          {"start": [200, 100, 0], "end": [0, 100, 0], "layer": "轮廓"},
          {"start": [0, 100, 0], "end": [0, 0, 0], "layer": "轮廓"}
        ],
        "dimensions": [
          {"type": "Aligned", "point1": [0, 0, 0], "point2": [200, 0, 0],
           "text_position": [100, -20, 0], "layer": "标注"}
        ],
        "texts": [
          {"text": "矩形示例", "position": [100, 110, 0],
           "height": 8, "layer": "文字"}
        ]
      }
    },
    "return_screenshot": true
  }
}
```

### 行为约束

- **每次只绘制一个组件**：复杂图纸拆成多个 `autocad_draw_from_json`，每次后
  等待 screenshot 验证。
- **不要逐元素调用**：能合并的 lines / circles 一次发完，省 round-trip。
"""


_AUTOCAD_EXECUTE_PYTHON_COM_DETAIL = r"""执行 Python COM 代码 —— Mode B 兜底，仅在 `autocad_draw_from_json`
不支持的场景使用（hatch / block / mirror / offset / array / 修改 / 删除 /
AutoLISP via `doc.SendCommand`）。

### Args

| 参数 | 类型 | 说明 |
|------|------|------|
| `code` | string | 完整可执行的 Python 代码（含必要的 `import`） |
| `timeout` | int | 默认 60 秒 |
| `return_screenshot` | bool | 默认 true |

### 预置变量

代码运行时上下文已经注入以下对象，**直接使用、不要重新创建**：

| 变量 | 类型 | 说明 |
|------|------|------|
| `acad` | `AutoCAD.Application` | AutoCAD 应用 |
| `doc` | `AutoCAD.Document` | 当前激活文档 |
| `ms` | `AutoCAD.ModelSpace` | 当前模型空间 |
| `vtPoint(x, y, z)` | helper | 构造 COM 三维点 |
| `vtFloat([...])` | helper | 构造 COM float 数组 |

### 高频示例

#### 填充（Hatch）
```python
import array
pts = array.array('d', [0, 0, 100, 0, 100, 100, 0, 100])
pline = ms.AddLightWeightPolyline(pts)
pline.Closed = True
hatch = ms.AddHatch(0, 'ANSI31', True)
hatch.AppendOuterLoop([pline])
hatch.Evaluate()
```

#### 修改实体属性
```python
for entity in ms:
    if entity.ObjectName == 'AcDbLine':
        entity.Color = 1  # 红
```

#### 删除全部实体
```python
for entity in list(ms):
    entity.Delete()
```

#### 插入块
```python
block_ref = ms.InsertBlock(vtPoint(50, 50, 0), 'MyBlock', 1, 1, 1, 0)
```

#### 镜像 / 偏移 / 阵列
```python
line = ms.AddLine(vtPoint(0, 0, 0), vtPoint(100, 50, 0))
mirrored = line.Mirror(vtPoint(50, 0, 0), vtPoint(50, 100, 0))
```

#### 调命令行（AutoLISP）
```python
doc.SendCommand('ZOOM E\n')   # 缩放到范围
doc.SendCommand('REGEN\n')    # 重生成
doc.SendCommand('QSAVE\n')    # 保存
```
> **注意**：`SendCommand` 字符串末尾的 `\n` 必须有，等同于回车。

### 注意事项

1. 代码必须**完整、可运行**，不要用占位符或 TODO。
2. 失败时 **抛出实际异常 / `print` 错误信息**，不要静默吞掉 —— Router 需要从 stdout
   读到错误才能纠错。
3. 优先 `autocad_draw_from_json`，本工具用作"做不到时的兜底"。
"""


_AUTOCAD_SNAPSHOT_DETAIL = r"""读取当前图纸的元素列表 + 截图，**只读**。

### Args

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `include_content` | bool | true | 是否包含图元数据（lines / circles / ...） |
| `include_screenshot` | bool | true | 是否包含 base64 截图 |
| `only_visible` | bool | false | 只提取当前可见区域内的图元 |
| `max_entities` | int | null | 限制返回的图元数量（防止 token 爆炸） |

返回 payload：`{document_info, content: {layer_colors, elements, summary}, screenshot}`。

### 何时使用

- 在不熟悉的 .dwg 上动手前，先 `autocad_snapshot` 看一眼有什么；
- `autocad_draw_from_json` / `autocad_execute_python_com` 已经默认带截图返回，
  不需要再额外调用 snapshot。
"""


_AUTOCAD_STATUS_DETAIL = r"""检查 AutoCAD 进程状态 + 当前打开的文档列表，**只读**。

返回 payload 顶层会带 `running` / `version` / `documents`。

### 何时使用

如果 desktop snapshot 已经在 `open_windows` 列出了 `AutoCAD.exe`，**不需要**
再调 `autocad_status` —— 直接进入第一个真正动手的 action。本工具仅在以下
场景有用：

1. desktop snapshot 不可信（旧缓存 / 无 uia_data）
2. 出错信息怀疑 AutoCAD 已经退出
3. 需要枚举所有打开文档的 `path`（之后用 `autocad_document action="activate"` 切换）
"""


_AUTOCAD_LAUNCH_DETAIL = r"""启动 AutoCAD 进程。

仅在以下情况调用：
- desktop snapshot **没有** `AutoCAD.exe` 进程；且
- `autocad_status` 返回 `running: false`。

> **不要**和 `system_process_control action="launch" name="AutoCAD"` 重复 ——
> 优先用 `system_process_control`，因为它能用 `installed_apps` 里的官方启动
> 路径；本工具仅作为 AutoCAD Local Engine 自身的备用启动通道。
"""


_AUTOCAD_DOCUMENT_DETAIL = r"""图纸生命周期：`open` / `close` / `new` / `activate`。

| action | 必填 | 选填 | 说明 |
|--------|------|------|------|
| `open` | `file_path` | `read_only` (bool) | 打开 .dwg 文件 |
| `close` | — | `save` (bool) | 关闭当前激活文档；`save=true` 保存后再关 |
| `new` | — | `template` (.dwt 路径) | 新建空白图纸（可选模板） |
| `activate` | `name` 或 `index` | — | 切换激活文档（按文件名或 1-based 索引） |

示例：

```json
{"Action": "autocad_document",
 "Params": {"action": "open", "file_path": "C:\\Projects\\example.dwg"}}

{"Action": "autocad_document",
 "Params": {"action": "close", "save": true}}

{"Action": "autocad_document",
 "Params": {"action": "new", "template": "C:\\Templates\\A3.dwt"}}

{"Action": "autocad_document",
 "Params": {"action": "activate", "name": "Drawing2.dwg"}}
```

### 重要规则

- 用户 goal 里若提到了某个 .dwg 路径，**必须**用 `action="open"` 打开它，
  **不要**默认 `action="new"` 创建空白图。
- `close` + `save=false` 是不可逆操作，应在 `ask_user` 确认后再发。
"""


_AUTOCAD_STANDARD_PART_DETAIL = r"""标准件库：`list` / `presets` / `draw`。

| action | 必填 | 选填 | 说明 |
|--------|------|------|------|
| `list` | — | — | 列出所有可用标准件类型（法兰 / 阀门 / …） |
| `presets` | `part_type` | — | 列出某个标准件的预设规格（DN50 / DN100 / …） |
| `draw` | `part_type`, `position` | `preset` 或 `parameters` | 绘制一个标准件实例 |

`draw` 的两种规格选择方式（二选一）：

```json
// 用预设
{"Action": "autocad_standard_part",
 "Params": {"action": "draw", "part_type": "flange",
            "preset": "DN100", "position": [100, 100]}}

// 用自定义参数
{"Action": "autocad_standard_part",
 "Params": {"action": "draw", "part_type": "flange",
            "parameters": {"dn": 80, "pn": 16, "d": 200, "k": 160},
            "position": [200, 100]}}
```
"""


# ==========================================================================
# Read-only tools
# ==========================================================================


class AutoCADStatus(_AutoCADEngineTool):
    """读 AutoCAD 进程状态（轻量）。"""

    name = "autocad_status"
    router_hint = (
        "Check whether AutoCAD is running + list open documents (read-only). "
        "Skip if desktop snapshot already shows `AutoCAD.exe` in `open_windows`."
    )
    router_detail = _AUTOCAD_PROTOCOL_DETAIL + "\n\n" + _AUTOCAD_STATUS_DETAIL
    is_read_only = True
    input_schema = {
        "type": "object",
        "properties": {},
    }


class AutoCADSnapshot(_AutoCADEngineTool):
    """读当前图纸内容 + 截图（中等开销）。"""

    name = "autocad_snapshot"
    router_hint = (
        "Read the current drawing's elements + screenshot (read-only). "
        "Most action tools already return a snapshot — only call this when you "
        "need a fresh look without modifying anything."
    )
    router_detail = _AUTOCAD_PROTOCOL_DETAIL + "\n\n" + _AUTOCAD_SNAPSHOT_DETAIL
    is_read_only = True
    input_schema = {
        "type": "object",
        "properties": {
            "include_content": {
                "type": "boolean",
                "default": True,
                "description": "Include element list (lines / circles / ...).",
            },
            "include_screenshot": {
                "type": "boolean",
                "default": True,
                "description": "Include base64 PNG screenshot.",
            },
            "only_visible": {
                "type": "boolean",
                "default": False,
                "description": "Only extract entities visible in the current viewport.",
            },
            "max_entities": {
                "type": "integer",
                "description": "Cap on the number of entities returned.",
            },
        },
    }


class AutoCADLaunch(_AutoCADEngineTool):
    """启动 AutoCAD 进程（备用）。"""

    name = "autocad_launch"
    router_hint = (
        "Start the AutoCAD process via the Local Engine.  "
        "Prefer `system_process_control action=\"launch\"` when possible; this "
        "tool is the AutoCAD-specific fallback."
    )
    router_detail = _AUTOCAD_PROTOCOL_DETAIL + "\n\n" + _AUTOCAD_LAUNCH_DETAIL
    is_destructive = True  # Boots a new process — flagged for UI surfacing.
    input_schema = {
        "type": "object",
        "properties": {},
    }


# ==========================================================================
# Drawing — Mode A (preferred)
# ==========================================================================


class AutoCADDrawFromJSON(_AutoCADEngineTool):
    """Mode A —— 用 JSON 描述一次性绘制多个图元。"""

    name = "autocad_draw_from_json"
    router_hint = (
        "PRIMARY drawing tool.  Pass structured JSON (lines / circles / arcs / "
        "polylines / texts / dimensions) to draw shapes in one shot.  "
        "Params: data {layer_colors, elements}, timeout?, return_screenshot?."
    )
    router_detail = _AUTOCAD_PROTOCOL_DETAIL + "\n\n" + _AUTOCAD_DRAW_FROM_JSON_DETAIL
    is_destructive = True
    input_schema = {
        "type": "object",
        "properties": {
            "data": {
                "type": "object",
                "description": (
                    "Structured drawing payload.  Top-level keys: "
                    "`layer_colors` (dict, optional) and `elements` (dict; one or more of "
                    "`lines`/`circles`/`arcs`/`polylines`/`texts`/`dimensions`)."
                ),
            },
            "timeout": {
                "type": "integer",
                "default": 60,
                "description": "Seconds before the engine cancels the action.",
            },
            "return_screenshot": {
                "type": "boolean",
                "default": True,
                "description": "Return a fresh screenshot after drawing.",
            },
        },
        "required": ["data"],
    }


# ==========================================================================
# Drawing — Mode B (escape hatch)
# ==========================================================================


class AutoCADExecutePythonCom(_AutoCADEngineTool):
    """Mode B —— 执行 Python COM 代码（hatch / block / 修改 / 删除 / AutoLISP）。"""

    name = "autocad_execute_python_com"
    router_hint = (
        "Escape hatch: run Python COM code against AutoCAD (hatch, blocks, "
        "mirror/array/offset, entity modification, deletion, AutoLISP via "
        "doc.SendCommand).  Use ONLY when `autocad_draw_from_json` cannot do "
        "the job.  Params: code, timeout?, return_screenshot?."
    )
    router_detail = (
        _AUTOCAD_PROTOCOL_DETAIL + "\n\n" + _AUTOCAD_EXECUTE_PYTHON_COM_DETAIL
    )
    is_destructive = True
    input_schema = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": (
                    "Complete, runnable Python COM code.  `acad` / `doc` / `ms` / "
                    "`vtPoint(x,y,z)` / `vtFloat([...])` are pre-injected."
                ),
            },
            "timeout": {
                "type": "integer",
                "default": 60,
            },
            "return_screenshot": {
                "type": "boolean",
                "default": True,
            },
        },
        "required": ["code"],
    }


# ==========================================================================
# Document lifecycle (open / close / new / activate)
# ==========================================================================


_AUTOCAD_DOCUMENT_ACTION_TO_ENGINE: Dict[str, str] = {
    "open": "open",
    "close": "close",
    "new": "new",
    "activate": "activate",
}


class AutoCADDocument(_AutoCADEngineTool):
    """图纸生命周期 —— `action` 判别 open / close / new / activate。"""

    name = "autocad_document"
    router_hint = (
        "Drawing lifecycle: open / close / new / activate.  Discriminate on "
        "`action`; see router_detail for per-action params."
    )
    router_detail = _AUTOCAD_PROTOCOL_DETAIL + "\n\n" + _AUTOCAD_DOCUMENT_DETAIL
    is_destructive = True  # close+save=false is destructive.
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": list(_AUTOCAD_DOCUMENT_ACTION_TO_ENGINE.keys()),
                "description": "Lifecycle operation.",
            },
            "file_path": {
                "type": "string",
                "description": "action=open only.  Absolute path to the .dwg file.",
            },
            "read_only": {
                "type": "boolean",
                "description": "action=open only.  Open the file read-only.",
            },
            "save": {
                "type": "boolean",
                "description": "action=close only.  Save before closing.",
            },
            "template": {
                "type": "string",
                "description": "action=new only.  Optional .dwt template path.",
            },
            "name": {
                "type": "string",
                "description": "action=activate only.  Document name to activate.",
            },
            "index": {
                "type": "integer",
                "description": "action=activate only.  1-based index in the documents list.",
            },
        },
        "required": ["action"],
    }

    def build_tool_call(
        self,
        params: Dict[str, Any],
        planner_output: "PlannerOutput",
    ) -> ToolCall:
        params = dict(params)
        action_key = params.pop("action", None)
        engine_action = _AUTOCAD_DOCUMENT_ACTION_TO_ENGINE.get(action_key)
        if engine_action is None:
            raise ValueError(
                f"autocad_document: invalid action {action_key!r}; "
                f"expected one of {list(_AUTOCAD_DOCUMENT_ACTION_TO_ENGINE)}"
            )
        if engine_action == "open" and not params.get("file_path"):
            raise ValueError("autocad_document action='open' requires `file_path`.")
        if engine_action == "activate" and not (
            params.get("name") or params.get("index") is not None
        ):
            raise ValueError(
                "autocad_document action='activate' requires `name` or `index`."
            )
        args = {k: v for k, v in params.items() if v is not None}
        return ToolCall(name=engine_action, args=args)


# ==========================================================================
# Standard parts (list / presets / draw)
# ==========================================================================


_AUTOCAD_STANDARD_PART_ACTION_TO_ENGINE: Dict[str, str] = {
    "list": "list_standard_parts",
    "presets": "get_standard_part_presets",
    "draw": "draw_standard_part",
}


class AutoCADStandardPart(_AutoCADEngineTool):
    """标准件库 —— `action` 判别 list / presets / draw。"""

    name = "autocad_standard_part"
    router_hint = (
        "Standard parts library: list available types / list presets for one "
        "type / draw an instance.  Discriminate on `action`."
    )
    router_detail = _AUTOCAD_PROTOCOL_DETAIL + "\n\n" + _AUTOCAD_STANDARD_PART_DETAIL
    is_destructive = True  # `draw` mutates the drawing.
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": list(_AUTOCAD_STANDARD_PART_ACTION_TO_ENGINE.keys()),
                "description": "Operation: list / presets / draw.",
            },
            "part_type": {
                "type": "string",
                "description": "action=presets/draw only.  e.g. `flange`, `valve`.",
            },
            "preset": {
                "type": "string",
                "description": "action=draw only.  Preset name (e.g. `DN100`).",
            },
            "parameters": {
                "type": "object",
                "description": (
                    "action=draw only.  Custom parameter dict (alternative to "
                    "`preset`).  Shape depends on `part_type`."
                ),
            },
            "position": {
                "type": "array",
                "items": {"type": "number"},
                "description": (
                    "action=draw only.  Insertion point — `[x, y]` or `[x, y, z]`."
                ),
            },
        },
        "required": ["action"],
    }

    def build_tool_call(
        self,
        params: Dict[str, Any],
        planner_output: "PlannerOutput",
    ) -> ToolCall:
        params = dict(params)
        action_key = params.pop("action", None)
        engine_action = _AUTOCAD_STANDARD_PART_ACTION_TO_ENGINE.get(action_key)
        if engine_action is None:
            raise ValueError(
                f"autocad_standard_part: invalid action {action_key!r}; "
                f"expected one of {list(_AUTOCAD_STANDARD_PART_ACTION_TO_ENGINE)}"
            )
        if engine_action == "get_standard_part_presets" and not params.get("part_type"):
            raise ValueError(
                "autocad_standard_part action='presets' requires `part_type`."
            )
        if engine_action == "draw_standard_part":
            if not params.get("part_type"):
                raise ValueError(
                    "autocad_standard_part action='draw' requires `part_type`."
                )
            if not (params.get("preset") or params.get("parameters")):
                raise ValueError(
                    "autocad_standard_part action='draw' requires `preset` or "
                    "`parameters`."
                )
            if "position" not in params:
                raise ValueError(
                    "autocad_standard_part action='draw' requires `position`."
                )
        args = {k: v for k, v in params.items() if v is not None}
        return ToolCall(name=engine_action, args=args)


# ==========================================================================
# Registry
# ==========================================================================

TOOLS: List[_AutoCADEngineTool] = [
    # read-only / lightweight
    AutoCADStatus(),
    AutoCADSnapshot(),
    AutoCADLaunch(),
    # drawing
    AutoCADDrawFromJSON(),       # Mode A — preferred
    AutoCADExecutePythonCom(),   # Mode B — escape hatch
    # document lifecycle (open / close / new / activate)
    AutoCADDocument(),
    # standard parts (list / presets / draw)
    AutoCADStandardPart(),
]
