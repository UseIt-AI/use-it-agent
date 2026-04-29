# Browser Handler 设计文档

## 1. 概述

Browser Handler 负责处理与 Local Engine 的浏览器自动化通信，支持 Browser Use 场景。

### 1.1 与其他 Handler 的关系

| Handler | 目标应用 | 定位方式 | 典型场景 |
|---------|----------|----------|----------|
| `guiHandler` | 桌面 GUI | 屏幕坐标 `[x, y]` | Computer Use |
| `officeHandler` | Word/Excel/PPT | 代码执行 | Office 自动化 |
| `browserHandler` | 浏览器 | 元素索引 `index` | Browser Use |

### 1.2 核心特性

- **混合模式**：同时支持单例模式（简单场景）和 Session 模式（多实例场景）
- **AI 可控**：AI 可以显式创建/管理多个浏览器实例
- **向后兼容**：不传 `session_id` 时使用单例 API

---

## 2. Local Engine API 接口

### 2.1 单例模式 API（向后兼容）

| 方法 | 端点 | 描述 |
|------|------|------|
| GET | `/api/v1/browser/status` | 获取连接状态 |
| GET | `/api/v1/browser/browsers` | 获取已安装浏览器 |
| POST | `/api/v1/browser/connect` | 启动新浏览器并连接 |
| POST | `/api/v1/browser/attach` | 接管已有浏览器 (CDP) |
| POST | `/api/v1/browser/disconnect` | 断开连接 |
| POST | `/api/v1/browser/page_state` | 获取页面状态 |
| POST | `/api/v1/browser/step` | 执行操作 |
| POST | `/api/v1/browser/screenshot` | 截图 |

### 2.2 Session 管理 API（多实例）

| 方法 | 端点 | 描述 |
|------|------|------|
| POST | `/api/v1/browser/sessions` | 创建新 Session |
| POST | `/api/v1/browser/sessions/attach` | 通过 CDP 接管已有浏览器 |
| GET | `/api/v1/browser/sessions` | 列出所有 Sessions |
| GET | `/api/v1/browser/sessions/{session_id}` | 获取 Session 详情 |
| DELETE | `/api/v1/browser/sessions/{session_id}` | 关闭 Session |

### 2.3 Tab 管理 API

| 方法 | 端点 | 描述 |
|------|------|------|
| GET | `/api/v1/browser/sessions/{session_id}/tabs` | 获取所有 Tabs |
| POST | `/api/v1/browser/sessions/{session_id}/tabs` | 新建 Tab |
| POST | `/api/v1/browser/sessions/{session_id}/tabs/{tab_id}/focus` | 切换 Tab |
| DELETE | `/api/v1/browser/sessions/{session_id}/tabs/{tab_id}` | 关闭 Tab |

### 2.4 操作执行 API

| 方法 | 端点 | 描述 |
|------|------|------|
| POST | `/api/v1/browser/step` | 单例模式执行操作 |
| POST | `/api/v1/browser/sessions/{session_id}/step` | Session 模式执行操作 |

---

## 3. 支持的 Action 类型

### 3.1 Session 管理

```typescript
// 创建新浏览器实例
{ action: 'create_session', browser_type?: 'chrome' | 'edge' | 'auto', headless?: boolean }
// → 返回 { session_id: string }

// 通过 CDP 接管已有浏览器
{ action: 'attach_session', cdp_url: string }
// → 返回 { session_id: string }

// 列出所有实例
{ action: 'list_sessions' }
// → 返回 { sessions: SessionInfo[] }

// 关闭实例
{ action: 'close_session', session_id: string }
```

### 3.2 Tab 管理

```typescript
// 列出所有 Tab
{ action: 'list_tabs', session_id?: string }

// 创建新 Tab
{ action: 'create_tab', session_id?: string, url?: string, switch_to?: boolean }

// 切换到指定 Tab
{ action: 'switch_tab', session_id?: string, tab_id: string }

// 关闭 Tab
{ action: 'close_tab', session_id?: string, tab_id: string }
```

### 3.3 导航

```typescript
{ action: 'go_to_url', url: string, session_id?: string, tab_id?: string }
{ action: 'go_back', session_id?: string }
{ action: 'go_forward', session_id?: string }
{ action: 'refresh', session_id?: string }
```

### 3.4 元素交互（基于 index）

```typescript
// 点击元素
{ action: 'click_element', index: number, session_id?: string }

// 输入文本
{ action: 'input_text', index: number, text: string, session_id?: string }
```

### 3.5 滚动

```typescript
{ action: 'scroll_down', amount?: number, session_id?: string }
{ action: 'scroll_up', amount?: number, session_id?: string }
```

### 3.6 键盘

```typescript
{ action: 'press_key', key: string, session_id?: string }
```

### 3.7 其他

```typescript
{ action: 'wait', seconds: number }
{ action: 'screenshot', session_id?: string }
{ action: 'extract_content', selector?: string, session_id?: string }
{ action: 'page_state', session_id?: string }  // 获取页面状态
{ action: 'stop' }  // 停止操作
```

---

## 4. tool_call 格式

### 4.1 Backend → Frontend

```typescript
interface BrowserToolCall {
  type: 'tool_call';
  id: string;                    // 唯一 ID，用于回调
  target: 'browser';
  name: BrowserActionName;
  args: {
    // Session 管理
    session_id?: string;         // 操作哪个 session（不提供则使用单例）
    browser_type?: string;       // create_session 用
    cdp_url?: string;            // attach_session 用
    headless?: boolean;          // create_session 用
    
    // Tab 管理
    tab_id?: string;
    switch_to?: boolean;
    
    // 导航
    url?: string;
    
    // 元素交互
    index?: number;
    text?: string;
    
    // 滚动
    amount?: number;
    
    // 键盘
    key?: string;
    
    // 等待
    seconds?: number;
    
    // 提取内容
    selector?: string;
  };
}
```

### 4.2 Frontend → Backend 回调

```typescript
// POST /api/v1/workflow/callback/{id}
interface BrowserCallbackPayload {
  status: 'success' | 'error';
  result?: {
    // Session 管理结果
    session_id?: string;
    sessions?: SessionInfo[];
    
    // Tab 管理结果
    tab_id?: string;
    tabs?: TabInfo[];
    
    // 操作结果
    action_results?: ActionResult[];
    
    // 页面状态（执行动作后自动返回）
    page_state?: {
      url: string;
      title: string;
      elements: ElementInfo[];
      element_count: number;
    };
    
    // 截图（base64）
    screenshot?: string;
  };
  error?: string;
}
```

---

## 5. 实现细节

### 5.1 路由逻辑

```typescript
// router.ts 中添加
case 'browser':
  result = await browserHandler.handleToolCall(
    currentUrl, name, args, setMessages, botMessageId
  );
  break;
```

### 5.2 API 端点选择逻辑

```typescript
// browserHandler.ts
async function handleToolCall(currentUrl, name, args, ...) {
  // 1. Session 管理动作 → 专用端点
  if (name === 'create_session') {
    return POST(`${currentUrl}/api/v1/browser/sessions`, args);
  }
  if (name === 'close_session') {
    return DELETE(`${currentUrl}/api/v1/browser/sessions/${args.session_id}`);
  }
  if (name === 'list_sessions') {
    return GET(`${currentUrl}/api/v1/browser/sessions`);
  }
  
  // 2. Tab 管理动作 → Session 端点（需要 session_id）
  if (name === 'create_tab' && args.session_id) {
    return POST(`${currentUrl}/api/v1/browser/sessions/${args.session_id}/tabs`, args);
  }
  
  // 3. 普通操作 → 根据是否有 session_id 选择端点
  const action = { action: name, ...args };
  
  if (args.session_id) {
    // Session 模式
    return POST(`${currentUrl}/api/v1/browser/sessions/${args.session_id}/step`, { actions: [action] });
  } else {
    // 单例模式
    return POST(`${currentUrl}/api/v1/browser/step`, { actions: [action] });
  }
}
```

### 5.3 截图处理

截图处理与 `guiHandler` 类似，存入 `message.screenshots` 数组。

**注意**：Browser Use 复用 `'cua'` card type，因为两者在概念上类似：
- 都是 Agent 驱动的操作
- 都需要截图展示
- 都有步骤序号

```typescript
if (pageState?.screenshot_base64) {
  setMessages((prev) =>
    prev.map((msg) => {
      if (msg.id !== botMessageId) return msg;
      
      const screenshots = msg.screenshots || [];
      const newIndex = screenshots.length;
      
      // 找到第一个没有 screenshotIndex 的 CUA card
      // Browser Use 复用 'cua' card type
      const updatedBlocks = msg.blocks.map((block) => {
        if (block.type === 'card' && 
            block.card.type === 'cua' && 
            block.card.screenshotIndex === undefined) {
          return {
            ...block,
            card: { ...block.card, screenshotIndex: newIndex },
          };
        }
        return block;
      });
      
      return {
        ...msg,
        screenshots: [...screenshots, pageState.screenshot_base64],
        blocks: updatedBlocks,
      };
    })
  );
}
```

---

## 6. 使用示例

### 6.1 简单场景（单例模式）

```json
// AI 发送
{ "type": "tool_call", "id": "call_1", "target": "browser", "name": "go_to_url", "args": { "url": "https://google.com" }}

// Frontend 调用
POST /api/v1/browser/step
{ "actions": [{ "action": "go_to_url", "url": "https://google.com" }] }
```

### 6.2 多实例场景（Session 模式）

```json
// 1. 创建两个浏览器实例
{ "type": "tool_call", "id": "call_1", "target": "browser", "name": "create_session", "args": { "browser_type": "chrome" }}
// → { "session_id": "abc123" }

{ "type": "tool_call", "id": "call_2", "target": "browser", "name": "create_session", "args": { "browser_type": "edge" }}
// → { "session_id": "def456" }

// 2. 在不同实例中操作
{ "type": "tool_call", "id": "call_3", "target": "browser", "name": "go_to_url", "args": { "session_id": "abc123", "url": "https://google.com" }}
{ "type": "tool_call", "id": "call_4", "target": "browser", "name": "go_to_url", "args": { "session_id": "def456", "url": "https://bing.com" }}

// 3. 在某个实例中创建多个 Tab
{ "type": "tool_call", "id": "call_5", "target": "browser", "name": "create_tab", "args": { "session_id": "abc123", "url": "https://github.com" }}

// 4. 完成后关闭
{ "type": "tool_call", "id": "call_6", "target": "browser", "name": "close_session", "args": { "session_id": "abc123" }}
{ "type": "tool_call", "id": "call_7", "target": "browser", "name": "close_session", "args": { "session_id": "def456" }}
```

---

## 7. 与 Computer Use (guiHandler) 的对比

| 方面 | Computer Use | Browser Use |
|------|--------------|-------------|
| **定位方式** | 屏幕坐标 `[x, y]` | DOM 元素索引 `index` |
| **元素获取** | 截图 → AI 识别坐标 | API 返回可交互元素列表 |
| **截图时机** | 动作后主动截图 | `page_state` 自动包含 |
| **返回数据** | 仅截图 | 截图 + 元素列表 |
| **多实例** | 不支持 | 支持（Session 管理） |
| **多标签页** | 不适用 | 支持（Tab 管理） |
| **复杂度** | 需要视觉 AI 解析 | 直接使用元素索引 |

---

## 8. 文件结构

```
frontend/src/features/chat/handlers/localEngine/
├── index.ts                    # 统一导出
├── types.ts                    # 类型定义 (需扩展)
├── router.ts                   # 路由入口 (需扩展)
├── guiHandler.ts               # GUI 操作处理 (已有)
├── officeHandler.ts            # Office 操作处理 (已有)
├── browserHandler.ts           # 🆕 Browser Use 操作处理
└── browserHandler.md           # 本文档
```

---

## 9. 改动清单

| 文件 | 操作 | 描述 |
|------|------|------|
| `browserHandler.ts` | 新增 | Browser Use 操作处理器 |
| `browserHandler.md` | 新增 | 本设计文档 |
| `types.ts` | 修改 | 添加 Browser 相关类型定义 |
| `router.ts` | 修改 | 添加 `browser` 路由分支 |
| `index.ts` | 修改 | 导出 `browserHandler` |

---

## 10. 后续扩展

### 10.1 Chat 级别自动管理（可选）

如果需要更简化的体验，可以在 Chat 级别自动管理 Session：

```typescript
// ChatContext 中
interface ChatState {
  chatId: string;
  browserSessionId?: string;  // 自动创建的 session
}

// 第一次收到 browser tool_call 时自动创建
if (!chatState.browserSessionId && target === 'browser') {
  const { session_id } = await browserHandler.createSession(currentUrl);
  chatState.browserSessionId = session_id;
}

// Chat 关闭时自动清理
onChatClose(() => {
  if (chatState.browserSessionId) {
    browserHandler.closeSession(currentUrl, chatState.browserSessionId);
  }
});
```

### 10.2 UI 组件（可选）

- `BrowserCard`：显示浏览器操作状态和截图
- `BrowserSessionPanel`：显示当前 Session 列表和状态
