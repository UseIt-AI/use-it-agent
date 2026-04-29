# Browser Use 接口文档

> **目标读者**: Backend AI 开发者  
> **版本**: v1.0  
> **更新日期**: 2026-01-25

## 1. 概述

Browser Use 允许 AI 通过 `tool_call` 事件控制浏览器进行自动化操作。

### 1.1 核心特性

- **混合模式**: 支持单例模式（简单场景）和 Session 模式（多实例场景）
- **元素定位**: 基于 DOM 元素索引 `index`，无需坐标计算
- **多实例支持**: AI 可同时操作多个独立的浏览器实例
- **多标签页**: 每个浏览器实例可管理多个 Tab

### 1.2 与 Computer Use (GUI) 的区别

| 特性 | Computer Use (`target: 'gui'`) | Browser Use (`target: 'browser'`) |
|------|-------------------------------|----------------------------------|
| 定位方式 | 屏幕坐标 `[x, y]` | DOM 元素索引 `index` |
| 元素获取 | 截图 → AI 识别坐标 | API 返回可交互元素列表 |
| 多实例 | 不支持 | 支持 Session 管理 |
| 多标签页 | 不适用 | 支持 Tab 管理 |

---

## 2. tool_call 格式

### 2.1 基本格式

```json
{
  "type": "tool_call",
  "id": "call_xxxxxx",
  "target": "browser",
  "name": "<action_name>",
  "args": {
    // action 参数
  }
}
```

### 2.2 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | string | ✅ | 固定为 `"tool_call"` |
| `id` | string | ✅ | 唯一标识，用于回调。建议格式: `call_<uuid>` |
| `target` | string | ✅ | 固定为 `"browser"` |
| `name` | string | ✅ | 动作名称，见下文 |
| `args` | object | ✅ | 动作参数，见下文 |

---

## 3. 支持的 Actions

### 3.1 Session 管理

#### `create_session` - 创建新浏览器实例

```json
{
  "type": "tool_call",
  "id": "call_001",
  "target": "browser",
  "name": "create_session",
  "args": {
    "browser_type": "chrome",     // 可选: "chrome" | "edge" | "auto"，默认 "auto"
    "headless": false,            // 可选: 是否无头模式，默认 false
    "profile_directory": "Default", // 可选: 浏览器 Profile
    "initial_url": "https://google.com" // 可选: 初始 URL
  }
}
```

**返回**:
```json
{
  "status": "success",
  "result": {
    "session_id": "abc12345",
    "browser_type": "chrome",
    "profile": "Default",
    "created_at": "2026-01-25T10:00:00"
  }
}
```

---

#### `attach_session` - 接管已有浏览器 (CDP)

用于接管用户手动启动的浏览器（需启用 CDP 调试端口）。

```json
{
  "type": "tool_call",
  "id": "call_002",
  "target": "browser",
  "name": "attach_session",
  "args": {
    "cdp_url": "http://localhost:9222"  // 可选，默认 "http://localhost:9222"
  }
}
```

**返回**:
```json
{
  "status": "success",
  "result": {
    "session_id": "def67890",
    "cdp_url": "http://localhost:9222",
    "current_url": "https://example.com",
    "current_title": "Example Domain",
    "created_at": "2026-01-25T10:00:00"
  }
}
```

---

#### `list_sessions` - 列出所有浏览器实例

```json
{
  "type": "tool_call",
  "id": "call_003",
  "target": "browser",
  "name": "list_sessions",
  "args": {}
}
```

**返回**:
```json
{
  "status": "success",
  "result": {
    "sessions": [
      {
        "session_id": "abc12345",
        "connected": true,
        "connect_type": "connect",
        "browser_type": "chrome",
        "created_at": "2026-01-25T10:00:00"
      },
      {
        "session_id": "def67890",
        "connected": true,
        "connect_type": "attach",
        "cdp_url": "http://localhost:9222",
        "created_at": "2026-01-25T10:05:00"
      }
    ]
  }
}
```

---

#### `close_session` - 关闭浏览器实例

```json
{
  "type": "tool_call",
  "id": "call_004",
  "target": "browser",
  "name": "close_session",
  "args": {
    "session_id": "abc12345"  // 必填
  }
}
```

**返回**:
```json
{
  "status": "success",
  "result": {
    "session_id": "abc12345",
    "closed": true
  }
}
```

---

### 3.2 Tab 管理

> **注意**: Tab 管理需要 `session_id`，仅在 Session 模式下可用。

#### `list_tabs` - 列出所有标签页

```json
{
  "type": "tool_call",
  "id": "call_010",
  "target": "browser",
  "name": "list_tabs",
  "args": {
    "session_id": "abc12345"  // 必填
  }
}
```

**返回**:
```json
{
  "status": "success",
  "result": {
    "tabs": [
      { "tab_id": "TAB_001", "url": "https://google.com", "title": "Google", "is_active": true },
      { "tab_id": "TAB_002", "url": "https://github.com", "title": "GitHub", "is_active": false }
    ]
  }
}
```

---

#### `create_tab` - 创建新标签页

```json
{
  "type": "tool_call",
  "id": "call_011",
  "target": "browser",
  "name": "create_tab",
  "args": {
    "session_id": "abc12345",   // 必填
    "url": "https://bing.com",  // 可选，默认 "about:blank"
    "switch_to": true           // 可选，是否切换到新 Tab，默认 true
  }
}
```

**返回**:
```json
{
  "status": "success",
  "result": {
    "tab_id": "TAB_003",
    "url": "https://bing.com",
    "is_active": true
  }
}
```

---

#### `switch_tab` - 切换到指定标签页

```json
{
  "type": "tool_call",
  "id": "call_012",
  "target": "browser",
  "name": "switch_tab",
  "args": {
    "session_id": "abc12345",  // 必填
    "tab_id": "TAB_002"        // 必填
  }
}
```

**返回**:
```json
{
  "status": "success",
  "result": {
    "tab_id": "TAB_002",
    "switched": true
  }
}
```

---

#### `close_tab` - 关闭标签页

```json
{
  "type": "tool_call",
  "id": "call_013",
  "target": "browser",
  "name": "close_tab",
  "args": {
    "session_id": "abc12345",  // 必填
    "tab_id": "TAB_002"        // 必填
  }
}
```

**返回**:
```json
{
  "status": "success",
  "result": {
    "tab_id": "TAB_002",
    "closed": true
  }
}
```

---

### 3.3 导航

#### `go_to_url` - 跳转到 URL

```json
{
  "type": "tool_call",
  "id": "call_020",
  "target": "browser",
  "name": "go_to_url",
  "args": {
    "url": "https://google.com",  // 必填
    "session_id": "abc12345"      // 可选: Session 模式下使用
  }
}
```

**返回**: 包含 `page_state` 和 `screenshot`，见 [通用返回格式](#4-通用返回格式)

---

#### `go_back` - 后退

```json
{
  "type": "tool_call",
  "id": "call_021",
  "target": "browser",
  "name": "go_back",
  "args": {
    "session_id": "abc12345"  // 可选
  }
}
```

---

#### `go_forward` - 前进

```json
{
  "type": "tool_call",
  "id": "call_022",
  "target": "browser",
  "name": "go_forward",
  "args": {
    "session_id": "abc12345"  // 可选
  }
}
```

---

#### `refresh` - 刷新页面

```json
{
  "type": "tool_call",
  "id": "call_023",
  "target": "browser",
  "name": "refresh",
  "args": {
    "session_id": "abc12345"  // 可选
  }
}
```

---

### 3.4 元素交互

> **重要**: 元素通过 `index` 定位，`index` 来自 `page_state.elements` 返回的元素列表。

#### `click_element` - 点击元素

```json
{
  "type": "tool_call",
  "id": "call_030",
  "target": "browser",
  "name": "click_element",
  "args": {
    "index": 5,               // 必填: 元素索引
    "session_id": "abc12345"  // 可选
  }
}
```

---

#### `input_text` - 输入文本

```json
{
  "type": "tool_call",
  "id": "call_031",
  "target": "browser",
  "name": "input_text",
  "args": {
    "index": 3,               // 必填: 元素索引
    "text": "Hello World",    // 必填: 要输入的文本
    "session_id": "abc12345"  // 可选
  }
}
```

---

### 3.5 滚动

#### `scroll_down` - 向下滚动

```json
{
  "type": "tool_call",
  "id": "call_040",
  "target": "browser",
  "name": "scroll_down",
  "args": {
    "amount": 500,            // 可选: 滚动像素数
    "session_id": "abc12345"  // 可选
  }
}
```

---

#### `scroll_up` - 向上滚动

```json
{
  "type": "tool_call",
  "id": "call_041",
  "target": "browser",
  "name": "scroll_up",
  "args": {
    "amount": 500,            // 可选
    "session_id": "abc12345"  // 可选
  }
}
```

---

### 3.6 键盘

#### `press_key` - 按键

```json
{
  "type": "tool_call",
  "id": "call_050",
  "target": "browser",
  "name": "press_key",
  "args": {
    "key": "Enter",           // 必填: 按键名称
    "session_id": "abc12345"  // 可选
  }
}
```

**支持的按键名称**:
- 特殊键: `Enter`, `Tab`, `Escape`, `Backspace`, `Delete`, `Space`
- 方向键: `ArrowUp`, `ArrowDown`, `ArrowLeft`, `ArrowRight`
- 功能键: `F1` ~ `F12`
- 修饰键组合: `Control+a`, `Control+c`, `Control+v`, `Alt+Tab`

---

### 3.7 其他操作

#### `wait` - 等待

```json
{
  "type": "tool_call",
  "id": "call_060",
  "target": "browser",
  "name": "wait",
  "args": {
    "seconds": 2  // 必填: 等待秒数
  }
}
```

---

#### `screenshot` - 截图

仅获取截图，不执行其他操作。

```json
{
  "type": "tool_call",
  "id": "call_061",
  "target": "browser",
  "name": "screenshot",
  "args": {
    "session_id": "abc12345"  // 可选
  }
}
```

---

#### `page_state` - 获取页面状态

获取当前页面的完整状态，包括 URL、标题、可交互元素列表。

```json
{
  "type": "tool_call",
  "id": "call_062",
  "target": "browser",
  "name": "page_state",
  "args": {
    "session_id": "abc12345",    // 可选
    "include_screenshot": true,  // 可选，默认 true
    "max_elements": 100          // 可选，最多返回的元素数量
  }
}
```

---

#### `extract_content` - 提取页面内容

```json
{
  "type": "tool_call",
  "id": "call_063",
  "target": "browser",
  "name": "extract_content",
  "args": {
    "selector": "article",     // 可选: CSS 选择器
    "session_id": "abc12345"   // 可选
  }
}
```

---

#### `stop` - 停止操作

用于中断当前操作流程。

```json
{
  "type": "tool_call",
  "id": "call_064",
  "target": "browser",
  "name": "stop",
  "args": {}
}
```

---

## 4. 通用返回格式

所有操作执行后（除 Session/Tab 管理外），都会返回以下格式：

```json
{
  "status": "success",
  "result": {
    "action_results": [
      { "index": 0, "ok": true, "result": null },
      { "index": 1, "ok": true, "result": null }
    ],
    "page_state": {
      "url": "https://google.com",
      "title": "Google",
      "element_count": 42,
      "elements": [
        {
          "index": 0,
          "tag": "input",
          "text": "",
          "attributes": { "type": "text", "name": "q", "placeholder": "Search..." },
          "position": { "x": 100, "y": 200, "width": 400, "height": 40 }
        },
        {
          "index": 1,
          "tag": "button",
          "text": "Google Search",
          "attributes": { "type": "submit" },
          "position": { "x": 200, "y": 260, "width": 120, "height": 36 }
        }
        // ... 更多元素
      ]
    },
    "screenshot": "<base64_encoded_png>"  // 截图
  }
}
```

### 4.1 错误返回

```json
{
  "status": "error",
  "error": "Element with index 999 not found"
}
```

---

## 5. 使用模式

### 5.1 单例模式（简单场景）

不传 `session_id`，使用默认浏览器连接。适合简单的单页面操作。

```json
// 步骤 1: 打开网页
{ "type": "tool_call", "id": "call_1", "target": "browser", "name": "go_to_url", "args": { "url": "https://google.com" }}

// 步骤 2: 在搜索框输入（假设搜索框 index=0）
{ "type": "tool_call", "id": "call_2", "target": "browser", "name": "input_text", "args": { "index": 0, "text": "OpenAI" }}

// 步骤 3: 点击搜索按钮（假设按钮 index=1）
{ "type": "tool_call", "id": "call_3", "target": "browser", "name": "click_element", "args": { "index": 1 }}
```

---

### 5.2 Session 模式（多实例场景）

适合需要同时操作多个网站、对比数据等场景。

```json
// 步骤 1: 创建两个浏览器实例
{ "type": "tool_call", "id": "call_1", "target": "browser", "name": "create_session", "args": { "browser_type": "chrome" }}
// → 返回 session_id: "browser_A"

{ "type": "tool_call", "id": "call_2", "target": "browser", "name": "create_session", "args": { "browser_type": "chrome" }}
// → 返回 session_id: "browser_B"

// 步骤 2: 在不同实例中打开不同网站
{ "type": "tool_call", "id": "call_3", "target": "browser", "name": "go_to_url", "args": { "session_id": "browser_A", "url": "https://amazon.com/dp/xxx" }}
{ "type": "tool_call", "id": "call_4", "target": "browser", "name": "go_to_url", "args": { "session_id": "browser_B", "url": "https://ebay.com/itm/xxx" }}

// 步骤 3: 分别获取价格信息
{ "type": "tool_call", "id": "call_5", "target": "browser", "name": "extract_content", "args": { "session_id": "browser_A", "selector": ".price" }}
{ "type": "tool_call", "id": "call_6", "target": "browser", "name": "extract_content", "args": { "session_id": "browser_B", "selector": ".price" }}

// 步骤 4: 完成后关闭
{ "type": "tool_call", "id": "call_7", "target": "browser", "name": "close_session", "args": { "session_id": "browser_A" }}
{ "type": "tool_call", "id": "call_8", "target": "browser", "name": "close_session", "args": { "session_id": "browser_B" }}
```

---

### 5.3 多标签页场景

```json
// 步骤 1: 创建 Session
{ "type": "tool_call", "id": "call_1", "target": "browser", "name": "create_session", "args": { "initial_url": "https://google.com" }}
// → 返回 session_id: "abc123"

// 步骤 2: 创建多个标签页
{ "type": "tool_call", "id": "call_2", "target": "browser", "name": "create_tab", "args": { "session_id": "abc123", "url": "https://github.com" }}
// → 返回 tab_id: "TAB_001"

{ "type": "tool_call", "id": "call_3", "target": "browser", "name": "create_tab", "args": { "session_id": "abc123", "url": "https://stackoverflow.com" }}
// → 返回 tab_id: "TAB_002"

// 步骤 3: 切换标签页
{ "type": "tool_call", "id": "call_4", "target": "browser", "name": "switch_tab", "args": { "session_id": "abc123", "tab_id": "TAB_001" }}

// 步骤 4: 在当前标签页操作
{ "type": "tool_call", "id": "call_5", "target": "browser", "name": "click_element", "args": { "session_id": "abc123", "index": 3 }}
```

---

## 6. 元素索引使用指南

### 6.1 获取元素列表

每次操作后会自动返回 `page_state.elements`，包含页面上所有可交互元素。

```json
{
  "elements": [
    { "index": 0, "tag": "input", "text": "", "attributes": { "placeholder": "Search" } },
    { "index": 1, "tag": "button", "text": "Submit", "attributes": {} },
    { "index": 2, "tag": "a", "text": "Sign In", "attributes": { "href": "/login" } }
  ]
}
```

### 6.2 定位策略

1. **通过文本**: 找 `text` 匹配的元素
2. **通过属性**: 找 `attributes.placeholder`、`attributes.name` 等匹配的元素
3. **通过标签**: 找 `tag` 为 `input`、`button`、`a` 等的元素

### 6.3 示例

```
用户指令: "点击登录按钮"

AI 思考过程:
1. 从 page_state.elements 中找 text 包含 "登录" 或 "Sign In" 的元素
2. 或者找 tag="button" 且 attributes 包含相关信息的元素
3. 找到 index=2 的 <a> 元素，text="Sign In"
4. 发送 click_element，index=2
```

---

## 7. 错误处理

### 7.1 常见错误

| 错误信息 | 原因 | 解决方案 |
|---------|------|---------|
| `session_id is required for close_session` | 关闭 Session 时未提供 ID | 补充 `session_id` 参数 |
| `tab_id is required for switch_tab` | 切换 Tab 时未提供 Tab ID | 补充 `tab_id` 参数 |
| `Element with index X not found` | 元素索引不存在 | 先调用 `page_state` 获取最新元素列表 |
| `Session X not found` | Session 已关闭或不存在 | 重新创建 Session |
| `Browser not connected` | 浏览器连接断开 | 重新 `create_session` 或 `attach_session` |

### 7.2 重试策略

1. **页面加载后元素未出现**: 增加 `wait` 操作
2. **元素索引变化**: 操作前先调用 `page_state` 获取最新列表
3. **Session 断开**: 重新创建 Session

---

## 8. 最佳实践

### 8.1 操作前获取状态

```json
// 先获取页面状态，确认元素列表
{ "type": "tool_call", "id": "call_1", "target": "browser", "name": "page_state", "args": {} }

// 根据返回的 elements 确定 index，再操作
{ "type": "tool_call", "id": "call_2", "target": "browser", "name": "click_element", "args": { "index": 5 }}
```

### 8.2 合理使用等待

```json
// 页面跳转后等待加载
{ "type": "tool_call", "id": "call_1", "target": "browser", "name": "go_to_url", "args": { "url": "https://example.com" }}
{ "type": "tool_call", "id": "call_2", "target": "browser", "name": "wait", "args": { "seconds": 1 }}
{ "type": "tool_call", "id": "call_3", "target": "browser", "name": "page_state", "args": {} }
```

### 8.3 清理资源

```json
// 任务完成后关闭 Session
{ "type": "tool_call", "id": "call_final", "target": "browser", "name": "close_session", "args": { "session_id": "abc123" }}
```

---

## 9. Action 速查表

| Action | 必填参数 | 可选参数 | 说明 |
|--------|---------|---------|------|
| `create_session` | - | `browser_type`, `headless`, `profile_directory`, `initial_url` | 创建浏览器实例 |
| `attach_session` | - | `cdp_url` | 接管已有浏览器 |
| `list_sessions` | - | - | 列出所有实例 |
| `close_session` | `session_id` | - | 关闭实例 |
| `list_tabs` | `session_id` | - | 列出标签页 |
| `create_tab` | `session_id` | `url`, `switch_to` | 创建标签页 |
| `switch_tab` | `session_id`, `tab_id` | - | 切换标签页 |
| `close_tab` | `session_id`, `tab_id` | - | 关闭标签页 |
| `go_to_url` | `url` | `session_id` | 跳转 URL |
| `go_back` | - | `session_id` | 后退 |
| `go_forward` | - | `session_id` | 前进 |
| `refresh` | - | `session_id` | 刷新 |
| `click_element` | `index` | `session_id` | 点击元素 |
| `input_text` | `index`, `text` | `session_id` | 输入文本 |
| `scroll_down` | - | `amount`, `session_id` | 向下滚动 |
| `scroll_up` | - | `amount`, `session_id` | 向上滚动 |
| `press_key` | `key` | `session_id` | 按键 |
| `wait` | `seconds` | - | 等待 |
| `screenshot` | - | `session_id` | 截图 |
| `page_state` | - | `session_id`, `include_screenshot`, `max_elements` | 获取页面状态 |
| `extract_content` | - | `selector`, `session_id` | 提取内容 |
| `stop` | - | - | 停止操作 |
