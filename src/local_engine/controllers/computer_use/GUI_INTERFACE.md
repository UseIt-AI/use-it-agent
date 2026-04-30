# Local Engine GUI 接口文档

本文档基于当前实现整理，覆盖三类接口：

1. 业务 API（`api/v1/computer.py`）：给 GUI/Agent 使用的统一入口
2. 执行器接口（`controllers/computer_use/win_executor/app.py`）：HTTP + WebSocket
3. 内部调用接口（`controllers/computer_use/controller.py`）：`ComputerUseController.run_actions`

---

## 1. 服务概览（win_executor）

- 服务入口：`local_engine/controllers/computer_use/win_executor/app.py`
- 默认监听：`0.0.0.0:8080`
  - 环境变量：
    - `CUA_SERVER_HOST`（默认 `0.0.0.0`）
    - `CUA_SERVER_PORT`（默认 `8080`）
- 协议：HTTP + WebSocket
- CORS：全开放（`allow_origins=["*"]`）

### 1.1 坐标系统

所有鼠标坐标和截图尺寸都使用 **逻辑坐标（logical pixel）**，不是物理像素：

- 代码中显式调用 `SetProcessDpiAwareness(0)`（DPI Unaware）
- 在 Windows 缩放不是 100% 时，逻辑分辨率 < 物理分辨率
- 例如：物理 `2560x1440` + 125% 缩放 => 逻辑约 `2048x1152`

---

## 2. 业务 API（推荐给 GUI）

路由文件：`local_engine/api/v1/computer.py`

### 2.1 `POST /api/v1/computer/step`

统一动作执行入口，**支持 list of actions**。

- 请求字段：
  - `actions: List[Dict[str, Any]]`（必填）
  - `return_screenshot: bool`（可选，默认 `false`）
- 执行方式：
  - 按顺序执行 `actions`
  - 当前实现会继续执行后续动作，并在响应里按 action 维度返回 `ok/result/error`
- 返回字段：
  - `success: bool`（由所有 action 的 `ok` 聚合）
  - `data.action_results: []`
  - `data.screenshot`（仅 `return_screenshot=true` 时尝试返回）

**请求示例：**

```json
{
  "actions": [
    { "type": "click", "x": 100, "y": 200 },
    { "type": "type", "text": "hello" },
    { "type": "keypress", "keys": ["enter"] }
  ],
  "return_screenshot": true
}
```

**响应示例：**

```json
{
  "success": true,
  "data": {
    "action_results": [
      { "index": 0, "ok": true, "result": { "type": "click", "x": 100, "y": 200 } },
      { "index": 1, "ok": true, "result": { "type": "type", "text": "hello" } },
      { "index": 2, "ok": true, "result": { "type": "keypress", "keys": ["enter"] } }
    ],
    "screenshot": "base64..."
  }
}
```

### 2.2 `GET /api/v1/computer/screen`

获取屏幕逻辑分辨率与缩放信息。

### 2.3 `POST /api/v1/computer/screenshot`

快捷截图接口（本质是封装调用 screenshot action）。

---

## 3. 执行器 HTTP 接口（win_executor）

### 3.1 `GET /`

服务与能力探测。

**响应示例：**

```json
{
  "status": "ok",
  "service": "Windows Executor",
  "version": "1.0.0",
  "capabilities": {
    "pynput": true,
    "pillow": true,
    "windows_api": true
  }
}
```

### 3.2 `GET /health`

健康检查。

**响应示例：**

```json
{
  "status": "healthy"
}
```

### 3.3 `POST /cmd`

统一命令接口（主入口）。

**请求体：**

```json
{
  "command": "left_click",
  "params": {
    "x": 600,
    "y": 400
  }
}
```

`params` 可省略，默认 `{}`。

**通用响应：**

```json
{
  "success": true
}
```

失败时：

```json
{
  "success": false,
  "error": "..."
}
```

---

## 4. 执行器 WebSocket 接口

### 4.1 `WS /ws`

兼容 CUA SDK 的命令通道。单条消息格式与 `/cmd` 一致：

**客户端发送：**

```json
{
  "command": "get_screen_info",
  "params": {}
}
```

**服务端返回：**

```json
{
  "success": true,
  "logical_size": {
    "width": 2048,
    "height": 1152
  },
  "physical_size": {
    "width": 2560,
    "height": 1440
  },
  "scale": 1.25,
  "dpi": 120
}
```

JSON 解析失败时：

```json
{
  "success": false,
  "error": "Invalid JSON: ..."
}
```

---

## 5. 执行器命令清单（`command`）

命令分发定义见 `win_executor/app.py` 中 `COMMAND_HANDLERS`。

## 5.1 元信息

### `version`
- params：无
- 返回：
  - `protocol_version`
  - `package_version`
  - `server`

---

## 5.2 鼠标

### `left_click` / `right_click` / `middle_click`
- params：
  - `x?: int`
  - `y?: int`
- 返回：`{ "success": true }`

### `double_click`
- params：
  - `x?: int`
  - `y?: int`
  - `button?: "left" | "right" | "middle"`（默认 `left`）

### `mouse_move` / `move_cursor`
- params：
  - `x: int`
  - `y: int`
- 返回：
  - 成功：`{ "success": true }`
  - 缺参：`{ "success": false, "error": "x and y required" }`

### `mouse_down` / `mouse_up`
- params：
  - `button?: "left" | "right" | "middle"`（默认 `left`）
  - `x?: int`
  - `y?: int`

### `drag`
- params（支持两种）：
  1. 折线路径：
     - `path: [[x1,y1],[x2,y2],...]`
     - `button?: string`
     - `speed?: number`（像素/秒）
  2. 起止/偏移：
     - `start_x?: int`（兼容 `x`）
     - `start_y?: int`（兼容 `y`）
     - `end_x?: int`
     - `end_y?: int`
     - `dx?: int`（兼容 `offset_x`）
     - `dy?: int`（兼容 `offset_y`）
- 返回（成功）：
  - `success`
  - `path_points`
  - `total_length`
  - `duration`

### `drag_to`
- params：
  - `x: int`
  - `y: int`

### `scroll`
- params：
  - `dx?: int`（兼容 `scroll_x`，默认 0）
  - `dy?: int`（兼容 `scroll_y`，默认 0）
  - `x?: int`
  - `y?: int`

### `scroll_down` / `scroll_up`
- params：
  - `clicks?: int`（默认 `3`）

### `get_cursor_position`
- params：无
- 返回：

```json
{
  "success": true,
  "position": {
    "x": 100,
    "y": 200
  }
}
```

---

## 5.3 键盘

### `type` / `type_text`
- params：
  - `text: string`
- 说明：
  - 内部通过剪贴板 + `Ctrl+V` 粘贴，支持中文/Unicode

### `key` / `press_key`
- params：
  - `key: string`

### `key_down` / `key_up`
- params：
  - `key: string`

### `hotkey` / `key_combination`
- params（两种格式都支持）：
  - `keys: "ctrl+c"` 或 `["ctrl","c"]`
  - 兼容字段：`combination`

---

## 5.4 屏幕

### `screenshot`
- params：当前未读取外部压缩参数（直接走默认压缩）
- 返回：
  - `success`
  - `image_data`（base64）
  - `width`（原始逻辑宽）
  - `height`（原始逻辑高）
  - `compressed`（是否压缩）

### `get_screen_size`
- 返回：
  - `size: {width, height}`（逻辑分辨率）
  - `scale` / `scale_percent` / `dpi`
  - `physical_size`
  - `coordinate_system: "logical"`

### `get_screen_info`
- 返回（兼容格式）：
  - `logical_size`
  - `physical_size`
  - `scale` / `scale_percent` / `dpi`
  - `coordinate_system: "logical"`

---

## 5.5 剪贴板

### `get_clipboard`
- 返回：
  - `success`
  - `content`

### `set_clipboard`
- params：
  - `text: string`

### `copy_to_clipboard`
- 当前实现行为：等价于 `get_clipboard`（返回读取结果，不是写入）

---

## 5.6 文件系统

### `file_exists`
- params：`path: string`
- 返回：`exists: boolean`

### `directory_exists`
- params：`path: string`
- 返回：`exists: boolean`

### `list_dir`
- params：`path?: string`（默认 `"."`）
- 返回：`entries: string[]`

### `read_text`
- params：
  - `path: string`
  - `encoding?: string`（默认 `utf-8`）
- 返回：`content: string`

### `write_text`
- params：
  - `path: string`
  - `content: string`
  - `encoding?: string`

### `read_bytes`
- params：`path: string`
- 返回：`content: string`（base64）

### `write_bytes`
- params：
  - `path: string`
  - `content: string`（base64）

### `get_file_size`
- params：`path: string`
- 返回：`size: number`

### `delete_file`
- params：`path: string`

### `create_dir`
- params：`path: string`

### `delete_dir`
- params：`path: string`

### `run_command`
- params：
  - `command: string`
  - `timeout?: int`（默认 `30` 秒）
- 返回：
  - `stdout`
  - `stderr`
  - `return_code`

---

## 5.7 窗口

### `get_accessibility_tree`
- 返回：
  - `tree.role`
  - `tree.title`
  - `tree.position`
  - `tree.size`
  - `tree.children[]`（子窗口简要信息）

### `find_element`
- params：
  - `title: string`
- 返回：
  - 成功：`element`（窗口位置与尺寸）
  - 失败：`{ "success": false, "error": "Element not found" }`

---

## 6. 内部动作接口（ComputerUseController）

- 文件：`local_engine/controllers/computer_use/controller.py`
- 对象：`ComputerUseController`
- 主方法：
  - `await run_actions(actions: List[Dict[str, Any]]) -> Dict[str, Any>`

`run_actions` 用于执行一组 GUI/Code 动作，返回：

```json
{
  "status": "ok",
  "results": [
    {
      "index": 0,
      "ok": true,
      "result": {}
    },
    {
      "index": 1,
      "ok": false,
      "error": "..."
    }
  ]
}
```

## 6.1 支持的动作类型（`type`）

- `click`
- `double_click`
- `drag`
- `move`
- `scroll`
- `keypress`
- `type`
- `screenshot`
- `wait`
- `screen_info` / `get_screen_info` / `get_screen_size`
- `code`（目前仅路由 `excel`）

## 6.2 上游兼容规则（AI_Run）

控制器会做自动兼容转换：

- `action` -> `type`
- `position`/`coordinate` -> `x`,`y`
- `INPUT/TYPE` 的 `value` -> `text`
- `KEY/KEYPRESS` 的 `value` -> `keys`
- `SCROLL` 的 `value=[sx,sy]` -> `scroll_x`,`scroll_y`
- `WAIT` 的 `value(ms)` -> `seconds`
- 别名：`input -> type`、`key -> keypress`、`doubleclick -> double_click` 等

## 6.3 特殊字段

### `coordinate_system: "normalized_1000"`

若动作携带该字段，控制器会将千分位坐标映射到当前逻辑屏幕坐标系。

---

## 7. 错误处理与返回约定

- 未识别命令：`{ "success": false, "error": "Unknown command: ..." }`
- Handler 异常：统一捕获并返回 `success=false + error`
- 依赖缺失（如 `pynput`、`PIL`、`pywin32`）：相关命令返回失败

---

## 8. 已知行为（按当前代码）

1. `copy_to_clipboard` 当前映射到 `get_clipboard`（读取而非写入）。
2. `mouse_move`/`drag_to` 的参数检查使用 `if p.get("x") and p.get("y")`，当坐标为 `0` 时会被判定为缺参。
3. `/cmd` 的 `screenshot` 不读取 `params.compress`，固定调用 `ScreenHandler.screenshot()` 默认压缩。
4. `POST /api/v1/computer/step` 支持批量 `actions`，并返回逐条执行结果；整体 `success` 由各 action 的 `ok` 聚合得到。

如需修正以上行为，建议在 `win_executor/app.py` 中调整 `COMMAND_HANDLERS` 参数映射逻辑。

