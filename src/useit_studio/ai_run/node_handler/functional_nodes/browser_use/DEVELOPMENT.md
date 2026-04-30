# Browser Use 模块开发文档

> **版本**: v1.0  
> **创建日期**: 2026-01-25  
> **作者**: AI Assistant  
> **参考**: `computer_use/gui_v2` 架构

---

## 1. 概述

Browser Use 是一个基于 Playwright 的浏览器自动化模块，允许 AI Agent 通过 DOM 元素索引（`index`）控制浏览器，而非传统的屏幕坐标方式。

### 1.1 与 Computer Use (GUI) 的核心区别

| 特性 | Computer Use (`target: 'gui'`) | Browser Use (`target: 'browser'`) |
|------|-------------------------------|----------------------------------|
| **定位方式** | 屏幕坐标 `[x, y]` | DOM 元素索引 `index` |
| **元素获取** | 截图 → VLM 识别坐标 | DOM 解析 → 返回可交互元素列表 |
| **依赖** | 截图 + VLM | Playwright + DOM Parser |
| **执行方式** | 模拟鼠标/键盘操作 | Playwright API 调用 |
| **多实例** | 不支持 | 支持 Session 管理 |
| **多标签页** | 不适用 | 支持 Tab 管理 |

### 1.2 核心优势

1. **精确定位**: 基于 DOM 元素，不受截图分辨率和 VLM 识别精度影响
2. **元素语义**: 返回元素的 tag、text、attributes 等语义信息，便于 AI 理解
3. **多实例隔离**: 支持同时操作多个独立浏览器实例
4. **状态可追踪**: 每次操作后返回完整的页面状态

---

## 2. 架构设计

### 2.1 分层架构（参考 gui_v2）

```
browser_use/
├── __init__.py           # 模块导出
├── models.py             # 数据模型（单一真相来源）
├── agent.py              # BrowserAgent（协调 Planner 和 Executor）
├── handler_v2.py         # Handler（实现 BaseNodeHandlerV2 接口）
├── core/
│   ├── __init__.py
│   ├── planner.py        # Planner（高层规划，决定做什么）
│   ├── executor.py       # Executor（执行动作，替代 Actor）
│   ├── session_manager.py # Session 管理器
│   └── dom_parser.py     # DOM 解析器
├── utils/
│   ├── __init__.py
│   ├── browser_client.py # Playwright 封装
│   └── element_utils.py  # 元素处理工具
├── prompts/
│   ├── __init__.py
│   └── browser_prompts.py # Prompt 模板
└── browserUseHandler.api.md  # API 接口文档
```

### 2.2 核心组件职责

```
┌─────────────────────────────────────────────────────────────────┐
│                      FlowProcessor                               │
│                           │                                       │
│                           ▼                                       │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                 BrowserNodeHandlerV2                         │ │
│  │  - 实现 BaseNodeHandlerV2 接口                               │ │
│  │  - 转换 NodeContext                                          │ │
│  │  - 发送标准事件流                                            │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                           │                                       │
│                           ▼                                       │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    BrowserAgent                              │ │
│  │  - 协调 Planner 和 Executor                                  │ │
│  │  - 管理 Session                                              │ │
│  │  - 提供流式/非流式接口                                       │ │
│  └─────────────────────────────────────────────────────────────┘ │
│              │                              │                     │
│              ▼                              ▼                     │
│  ┌──────────────────────┐    ┌──────────────────────────────────┐│
│  │      Planner         │    │          Executor                ││
│  │  - 观察页面状态      │    │  - 执行具体动作                  ││
│  │  - 决定下一步做什么  │    │  - 调用 Playwright API           ││
│  │  - 判断任务完成      │    │  - 返回执行结果                  ││
│  └──────────────────────┘    └──────────────────────────────────┘│
│                                           │                       │
│                                           ▼                       │
│                              ┌──────────────────────────────────┐│
│                              │       SessionManager             ││
│                              │  - 管理浏览器实例                ││
│                              │  - 管理标签页                    ││
│                              │  - 提供 Playwright Context       ││
│                              └──────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

### 2.3 数据流

```
1. FlowProcessor 调用 Handler
   ├─ 传入: NodeContext (node_id, query, screenshot_path, ...)
   └─ 期望: AsyncGenerator[Dict[str, Any], None]

2. Handler 创建 BrowserAgent
   ├─ 转换 NodeContext → BrowserContext
   └─ 调用 agent.step_streaming()

3. Agent 执行单步
   ├─ 3.1 获取页面状态 (page_state)
   │   └─ elements: [{index, tag, text, attributes, position}, ...]
   │
   ├─ 3.2 调用 Planner
   │   ├─ 输入: page_state + task_description + history
   │   └─ 输出: PlannerOutput (observation, reasoning, next_action, is_completed)
   │
   └─ 3.3 调用 Executor（如果未完成）
       ├─ 输入: planner.next_action + page_state
       └─ 输出: BrowserAction (name, args, result)

4. Handler 转换并输出事件
   ├─ cua_start, cua_delta, cua_update, cua_end
   ├─ tool_call (target: "browser")
   └─ node_complete
```

---

## 3. 数据模型设计 (`models.py`)

### 3.1 动作类型枚举

```python
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


class BrowserActionType(str, Enum):
    """浏览器动作类型"""
    # Session 管理
    CREATE_SESSION = "create_session"
    ATTACH_SESSION = "attach_session"
    LIST_SESSIONS = "list_sessions"
    CLOSE_SESSION = "close_session"
    
    # Tab 管理
    LIST_TABS = "list_tabs"
    CREATE_TAB = "create_tab"
    SWITCH_TAB = "switch_tab"
    CLOSE_TAB = "close_tab"
    
    # 导航
    GO_TO_URL = "go_to_url"
    GO_BACK = "go_back"
    GO_FORWARD = "go_forward"
    REFRESH = "refresh"
    
    # 元素交互
    CLICK_ELEMENT = "click_element"
    INPUT_TEXT = "input_text"
    
    # 滚动
    SCROLL_DOWN = "scroll_down"
    SCROLL_UP = "scroll_up"
    
    # 键盘
    PRESS_KEY = "press_key"
    
    # 其他
    WAIT = "wait"
    SCREENSHOT = "screenshot"
    PAGE_STATE = "page_state"
    EXTRACT_CONTENT = "extract_content"
    STOP = "stop"
```

### 3.2 元素模型

```python
@dataclass
class DOMElement:
    """DOM 元素"""
    index: int                           # 元素索引（用于交互）
    tag: str                             # HTML 标签
    text: str                            # 可见文本
    attributes: Dict[str, str]           # HTML 属性
    position: Optional[Dict[str, int]] = None  # 位置信息 {x, y, width, height}
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "tag": self.tag,
            "text": self.text,
            "attributes": self.attributes,
            "position": self.position,
        }
    
    def __str__(self) -> str:
        """用于 Prompt 的简洁表示"""
        attrs_str = " ".join(f'{k}="{v}"' for k, v in self.attributes.items())
        return f"[{self.index}] <{self.tag} {attrs_str}>{self.text}</{self.tag}>"
```

### 3.3 页面状态

```python
@dataclass
class PageState:
    """页面状态"""
    url: str
    title: str
    elements: List[DOMElement] = field(default_factory=list)
    screenshot_base64: Optional[str] = None
    
    @property
    def element_count(self) -> int:
        return len(self.elements)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "element_count": self.element_count,
            "elements": [e.to_dict() for e in self.elements],
        }
    
    def to_prompt_str(self, max_elements: int = 50) -> str:
        """生成用于 Prompt 的元素列表字符串"""
        lines = [f"URL: {self.url}", f"Title: {self.title}", "", "Interactive Elements:"]
        for elem in self.elements[:max_elements]:
            lines.append(str(elem))
        if len(self.elements) > max_elements:
            lines.append(f"... and {len(self.elements) - max_elements} more elements")
        return "\n".join(lines)
```

### 3.4 浏览器动作

```python
@dataclass
class BrowserAction:
    """浏览器动作 - Executor 的输出"""
    action_type: BrowserActionType
    args: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.action_type.value,
            **self.args,
        }
    
    def to_tool_call(self, call_id: str) -> Dict[str, Any]:
        """转换为标准 tool_call 格式"""
        return {
            "type": "tool_call",
            "id": call_id,
            "target": "browser",
            "name": self.action_type.value,
            "args": self.args,
        }
    
    # ==================== 工厂方法 ====================
    
    @classmethod
    def click(cls, index: int, session_id: Optional[str] = None) -> "BrowserAction":
        args = {"index": index}
        if session_id:
            args["session_id"] = session_id
        return cls(action_type=BrowserActionType.CLICK_ELEMENT, args=args)
    
    @classmethod
    def input_text(cls, index: int, text: str, session_id: Optional[str] = None) -> "BrowserAction":
        args = {"index": index, "text": text}
        if session_id:
            args["session_id"] = session_id
        return cls(action_type=BrowserActionType.INPUT_TEXT, args=args)
    
    @classmethod
    def go_to_url(cls, url: str, session_id: Optional[str] = None) -> "BrowserAction":
        args = {"url": url}
        if session_id:
            args["session_id"] = session_id
        return cls(action_type=BrowserActionType.GO_TO_URL, args=args)
    
    @classmethod
    def scroll_down(cls, amount: int = 500, session_id: Optional[str] = None) -> "BrowserAction":
        args = {"amount": amount}
        if session_id:
            args["session_id"] = session_id
        return cls(action_type=BrowserActionType.SCROLL_DOWN, args=args)
    
    @classmethod
    def press_key(cls, key: str, session_id: Optional[str] = None) -> "BrowserAction":
        args = {"key": key}
        if session_id:
            args["session_id"] = session_id
        return cls(action_type=BrowserActionType.PRESS_KEY, args=args)
    
    @classmethod
    def stop(cls) -> "BrowserAction":
        return cls(action_type=BrowserActionType.STOP, args={})
```

### 3.5 Planner 输出

```python
@dataclass
class BrowserPlannerOutput:
    """Planner 输出"""
    observation: str           # 对当前页面的观察
    reasoning: str             # 推理过程
    next_action: str           # 下一步动作的自然语言描述
    target_element: Optional[int] = None  # 目标元素索引（如果需要）
    is_milestone_completed: bool = False
    completion_summary: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "Observation": self.observation,
            "Reasoning": self.reasoning,
            "Action": self.next_action,
            "TargetElement": self.target_element,
            "MilestoneCompleted": self.is_milestone_completed,
            "node_completion_summary": self.completion_summary,
        }
```

### 3.6 Agent 步骤结果

```python
@dataclass
class BrowserAgentStep:
    """Agent 单步执行结果"""
    planner_output: BrowserPlannerOutput
    browser_action: Optional[BrowserAction] = None
    action_result: Optional[Dict[str, Any]] = None  # 动作执行结果
    page_state: Optional[PageState] = None          # 执行后的页面状态
    reasoning_text: str = ""
    token_usage: Dict[str, int] = field(default_factory=dict)
    error: Optional[str] = None
    
    @property
    def is_completed(self) -> bool:
        return self.planner_output.is_milestone_completed
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "planner": self.planner_output.to_dict(),
            "action": self.browser_action.to_dict() if self.browser_action else None,
            "action_result": self.action_result,
            "page_state": self.page_state.to_dict() if self.page_state else None,
            "reasoning": self.reasoning_text,
            "token_usage": self.token_usage,
            "is_completed": self.is_completed,
            "error": self.error,
        }
```

### 3.7 上下文模型

```python
@dataclass
class BrowserContext:
    """Browser Agent 上下文"""
    node_id: str
    task_description: str          # 整体任务描述
    milestone_objective: str       # 当前里程碑目标
    session_id: Optional[str] = None        # Session ID（多实例模式）
    initial_url: Optional[str] = None       # 初始 URL
    guidance_steps: List[str] = field(default_factory=list)
    history_md: str = ""
    loop_context: Optional[Dict[str, Any]] = None
```

---

## 4. 核心组件实现

### 4.1 SessionManager (`core/session_manager.py`)

负责浏览器实例和标签页的生命周期管理。

```python
"""
Session Manager - 浏览器实例管理

职责：
1. 创建/关闭浏览器实例
2. 接管已有浏览器 (CDP)
3. 管理多标签页
4. 提供 Playwright Page 对象
"""

import asyncio
import uuid
from datetime import datetime
from typing import Dict, Optional, Any, List
from dataclasses import dataclass, field

from playwright.async_api import async_playwright, Browser, BrowserContext, Page


@dataclass
class TabInfo:
    """标签页信息"""
    tab_id: str
    page: Page
    url: str = ""
    title: str = ""
    is_active: bool = False
    created_at: str = ""


@dataclass
class SessionInfo:
    """Session 信息"""
    session_id: str
    browser: Browser
    context: BrowserContext
    tabs: Dict[str, TabInfo] = field(default_factory=dict)
    active_tab_id: Optional[str] = None
    connect_type: str = "connect"  # "connect" or "attach"
    browser_type: str = "chromium"
    cdp_url: Optional[str] = None
    created_at: str = ""


class SessionManager:
    """Session 管理器"""
    
    def __init__(self):
        self._sessions: Dict[str, SessionInfo] = {}
        self._playwright = None
        self._default_session_id: Optional[str] = None
    
    async def _ensure_playwright(self):
        """确保 Playwright 已初始化"""
        if self._playwright is None:
            self._playwright = await async_playwright().start()
    
    async def create_session(
        self,
        browser_type: str = "chromium",
        headless: bool = False,
        profile_directory: Optional[str] = None,
        initial_url: Optional[str] = None,
    ) -> SessionInfo:
        """创建新的浏览器 Session"""
        await self._ensure_playwright()
        
        session_id = f"session_{uuid.uuid4().hex[:8]}"
        
        # 选择浏览器类型
        browser_launcher = getattr(self._playwright, browser_type, self._playwright.chromium)
        
        # 启动浏览器
        browser = await browser_launcher.launch(headless=headless)
        
        # 创建上下文
        context_options = {}
        if profile_directory:
            context_options["storage_state"] = profile_directory
        context = await browser.new_context(**context_options)
        
        # 创建初始页面
        page = await context.new_page()
        tab_id = f"TAB_{uuid.uuid4().hex[:6]}"
        
        if initial_url:
            await page.goto(initial_url)
        
        # 创建 Session 信息
        session = SessionInfo(
            session_id=session_id,
            browser=browser,
            context=context,
            connect_type="connect",
            browser_type=browser_type,
            created_at=datetime.now().isoformat(),
        )
        
        # 添加初始 Tab
        session.tabs[tab_id] = TabInfo(
            tab_id=tab_id,
            page=page,
            url=page.url,
            title=await page.title(),
            is_active=True,
            created_at=datetime.now().isoformat(),
        )
        session.active_tab_id = tab_id
        
        self._sessions[session_id] = session
        
        # 如果是第一个 session，设为默认
        if self._default_session_id is None:
            self._default_session_id = session_id
        
        return session
    
    async def attach_session(self, cdp_url: str = "http://localhost:9222") -> SessionInfo:
        """接管已有浏览器 (CDP)"""
        await self._ensure_playwright()
        
        session_id = f"session_{uuid.uuid4().hex[:8]}"
        
        # 通过 CDP 连接
        browser = await self._playwright.chromium.connect_over_cdp(cdp_url)
        
        # 获取默认上下文
        contexts = browser.contexts
        context = contexts[0] if contexts else await browser.new_context()
        
        # 获取现有页面
        pages = context.pages
        
        session = SessionInfo(
            session_id=session_id,
            browser=browser,
            context=context,
            connect_type="attach",
            cdp_url=cdp_url,
            created_at=datetime.now().isoformat(),
        )
        
        # 添加现有页面为 Tab
        for i, page in enumerate(pages):
            tab_id = f"TAB_{uuid.uuid4().hex[:6]}"
            session.tabs[tab_id] = TabInfo(
                tab_id=tab_id,
                page=page,
                url=page.url,
                title=await page.title(),
                is_active=(i == 0),
                created_at=datetime.now().isoformat(),
            )
            if i == 0:
                session.active_tab_id = tab_id
        
        self._sessions[session_id] = session
        
        if self._default_session_id is None:
            self._default_session_id = session_id
        
        return session
    
    def get_session(self, session_id: Optional[str] = None) -> Optional[SessionInfo]:
        """获取 Session"""
        sid = session_id or self._default_session_id
        return self._sessions.get(sid) if sid else None
    
    def get_active_page(self, session_id: Optional[str] = None) -> Optional[Page]:
        """获取当前活动页面"""
        session = self.get_session(session_id)
        if not session or not session.active_tab_id:
            return None
        tab = session.tabs.get(session.active_tab_id)
        return tab.page if tab else None
    
    async def create_tab(
        self,
        session_id: str,
        url: Optional[str] = None,
        switch_to: bool = True,
    ) -> TabInfo:
        """创建新标签页"""
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        page = await session.context.new_page()
        if url:
            await page.goto(url)
        
        tab_id = f"TAB_{uuid.uuid4().hex[:6]}"
        tab = TabInfo(
            tab_id=tab_id,
            page=page,
            url=page.url,
            title=await page.title(),
            is_active=switch_to,
            created_at=datetime.now().isoformat(),
        )
        
        session.tabs[tab_id] = tab
        
        if switch_to:
            # 更新活动状态
            if session.active_tab_id:
                old_tab = session.tabs.get(session.active_tab_id)
                if old_tab:
                    old_tab.is_active = False
            session.active_tab_id = tab_id
        
        return tab
    
    async def switch_tab(self, session_id: str, tab_id: str) -> bool:
        """切换标签页"""
        session = self.get_session(session_id)
        if not session or tab_id not in session.tabs:
            return False
        
        # 更新活动状态
        for tid, tab in session.tabs.items():
            tab.is_active = (tid == tab_id)
        session.active_tab_id = tab_id
        
        # 将页面带到前台
        tab = session.tabs[tab_id]
        await tab.page.bring_to_front()
        
        return True
    
    async def close_tab(self, session_id: str, tab_id: str) -> bool:
        """关闭标签页"""
        session = self.get_session(session_id)
        if not session or tab_id not in session.tabs:
            return False
        
        tab = session.tabs[tab_id]
        await tab.page.close()
        del session.tabs[tab_id]
        
        # 如果关闭的是活动 Tab，切换到其他 Tab
        if session.active_tab_id == tab_id:
            remaining_tabs = list(session.tabs.keys())
            if remaining_tabs:
                session.active_tab_id = remaining_tabs[0]
                session.tabs[remaining_tabs[0]].is_active = True
            else:
                session.active_tab_id = None
        
        return True
    
    async def close_session(self, session_id: str) -> bool:
        """关闭 Session"""
        session = self.get_session(session_id)
        if not session:
            return False
        
        await session.browser.close()
        del self._sessions[session_id]
        
        if self._default_session_id == session_id:
            remaining = list(self._sessions.keys())
            self._default_session_id = remaining[0] if remaining else None
        
        return True
    
    def list_sessions(self) -> List[Dict[str, Any]]:
        """列出所有 Session"""
        return [
            {
                "session_id": s.session_id,
                "connected": True,
                "connect_type": s.connect_type,
                "browser_type": s.browser_type,
                "cdp_url": s.cdp_url,
                "tab_count": len(s.tabs),
                "created_at": s.created_at,
            }
            for s in self._sessions.values()
        ]
    
    async def cleanup(self):
        """清理所有资源"""
        for session_id in list(self._sessions.keys()):
            await self.close_session(session_id)
        
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
```

### 4.2 DOMParser (`core/dom_parser.py`)

解析页面 DOM，提取可交互元素。

```python
"""
DOM Parser - 页面元素解析

职责：
1. 解析页面 DOM
2. 提取可交互元素
3. 生成元素索引
"""

from typing import List, Dict, Any, Optional
from playwright.async_api import Page

from ..models import DOMElement, PageState


# 可交互元素选择器
INTERACTIVE_SELECTORS = [
    "a[href]",
    "button",
    "input",
    "textarea",
    "select",
    "[onclick]",
    "[role='button']",
    "[role='link']",
    "[role='checkbox']",
    "[role='radio']",
    "[role='textbox']",
    "[role='combobox']",
    "[role='menuitem']",
    "[tabindex]:not([tabindex='-1'])",
]


class DOMParser:
    """DOM 解析器"""
    
    @staticmethod
    async def parse_page(
        page: Page,
        max_elements: int = 100,
        include_screenshot: bool = True,
    ) -> PageState:
        """
        解析页面，提取可交互元素
        
        Args:
            page: Playwright Page 对象
            max_elements: 最多返回的元素数量
            include_screenshot: 是否包含截图
            
        Returns:
            PageState 对象
        """
        # 获取基本信息
        url = page.url
        title = await page.title()
        
        # 提取可交互元素
        elements = await DOMParser._extract_interactive_elements(page, max_elements)
        
        # 截图
        screenshot_base64 = None
        if include_screenshot:
            screenshot_bytes = await page.screenshot(type="png")
            import base64
            screenshot_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")
        
        return PageState(
            url=url,
            title=title,
            elements=elements,
            screenshot_base64=screenshot_base64,
        )
    
    @staticmethod
    async def _extract_interactive_elements(
        page: Page,
        max_elements: int = 100,
    ) -> List[DOMElement]:
        """提取可交互元素"""
        
        # 使用 JavaScript 提取元素信息
        js_code = """
        () => {
            const selectors = %s;
            const elements = [];
            const seen = new Set();
            
            for (const selector of selectors) {
                const nodes = document.querySelectorAll(selector);
                for (const node of nodes) {
                    // 跳过隐藏元素
                    if (!node.offsetParent && node.tagName !== 'BODY') continue;
                    
                    // 跳过已处理的元素
                    const key = node.outerHTML.slice(0, 100);
                    if (seen.has(key)) continue;
                    seen.add(key);
                    
                    const rect = node.getBoundingClientRect();
                    
                    // 跳过不可见元素
                    if (rect.width === 0 || rect.height === 0) continue;
                    
                    // 提取属性
                    const attrs = {};
                    for (const attr of node.attributes) {
                        if (['id', 'class', 'name', 'type', 'placeholder', 'value', 
                             'href', 'aria-label', 'title', 'role'].includes(attr.name)) {
                            attrs[attr.name] = attr.value.slice(0, 100);
                        }
                    }
                    
                    elements.push({
                        tag: node.tagName.toLowerCase(),
                        text: (node.innerText || node.textContent || '').slice(0, 100).trim(),
                        attributes: attrs,
                        position: {
                            x: Math.round(rect.x),
                            y: Math.round(rect.y),
                            width: Math.round(rect.width),
                            height: Math.round(rect.height),
                        },
                    });
                    
                    if (elements.length >= %d) break;
                }
                if (elements.length >= %d) break;
            }
            
            return elements;
        }
        """ % (INTERACTIVE_SELECTORS, max_elements, max_elements)
        
        raw_elements = await page.evaluate(js_code)
        
        # 转换为 DOMElement
        elements = []
        for i, elem in enumerate(raw_elements):
            elements.append(DOMElement(
                index=i,
                tag=elem["tag"],
                text=elem["text"],
                attributes=elem["attributes"],
                position=elem["position"],
            ))
        
        return elements
    
    @staticmethod
    async def get_element_by_index(page: Page, index: int) -> Optional[Any]:
        """
        根据索引获取元素
        
        注意：这需要在解析时存储元素引用，或重新查找
        """
        # 重新执行选择器并获取对应索引的元素
        js_code = """
        (index) => {
            const selectors = %s;
            let count = 0;
            const seen = new Set();
            
            for (const selector of selectors) {
                const nodes = document.querySelectorAll(selector);
                for (const node of nodes) {
                    if (!node.offsetParent && node.tagName !== 'BODY') continue;
                    
                    const key = node.outerHTML.slice(0, 100);
                    if (seen.has(key)) continue;
                    seen.add(key);
                    
                    const rect = node.getBoundingClientRect();
                    if (rect.width === 0 || rect.height === 0) continue;
                    
                    if (count === index) {
                        return {
                            // 返回唯一选择器
                            xpath: getXPath(node),
                        };
                    }
                    count++;
                }
            }
            return null;
            
            function getXPath(element) {
                if (element.id) return `//*[@id="${element.id}"]`;
                if (element === document.body) return '/html/body';
                
                let ix = 0;
                const siblings = element.parentNode ? element.parentNode.childNodes : [];
                for (let i = 0; i < siblings.length; i++) {
                    const sibling = siblings[i];
                    if (sibling === element) {
                        return getXPath(element.parentNode) + '/' + element.tagName.toLowerCase() + '[' + (ix + 1) + ']';
                    }
                    if (sibling.nodeType === 1 && sibling.tagName === element.tagName) {
                        ix++;
                    }
                }
            }
        }
        """ % INTERACTIVE_SELECTORS
        
        result = await page.evaluate(js_code, index)
        if result and result.get("xpath"):
            return await page.query_selector(f"xpath={result['xpath']}")
        return None
```

### 4.3 Executor (`core/executor.py`)

执行浏览器动作。

```python
"""
Browser Executor - 动作执行器

职责：
1. 解析 Planner 输出的自然语言动作
2. 转换为具体的 BrowserAction
3. 调用 Playwright API 执行
4. 返回执行结果和新页面状态
"""

from typing import Dict, Any, Optional, Tuple
from playwright.async_api import Page

from ..models import BrowserAction, BrowserActionType, PageState
from .session_manager import SessionManager
from .dom_parser import DOMParser
from useit_ai_run.utils.logger_utils import LoggerUtils


class BrowserExecutor:
    """浏览器动作执行器"""
    
    def __init__(
        self,
        session_manager: SessionManager,
        logger: Optional[LoggerUtils] = None,
    ):
        self.session_manager = session_manager
        self.logger = logger or LoggerUtils(component_name="BrowserExecutor")
    
    async def execute(
        self,
        action: BrowserAction,
        session_id: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], PageState]:
        """
        执行浏览器动作
        
        Args:
            action: 要执行的动作
            session_id: Session ID（可选）
            
        Returns:
            (action_result, new_page_state)
        """
        # 从 action.args 获取 session_id（如果有）
        sid = action.args.get("session_id") or session_id
        
        page = self.session_manager.get_active_page(sid)
        if not page and action.action_type not in [
            BrowserActionType.CREATE_SESSION,
            BrowserActionType.ATTACH_SESSION,
            BrowserActionType.LIST_SESSIONS,
        ]:
            raise ValueError("No active page. Create or attach a session first.")
        
        action_type = action.action_type
        args = action.args
        result = {"ok": True, "result": None}
        
        try:
            # ==================== Session 管理 ====================
            if action_type == BrowserActionType.CREATE_SESSION:
                session = await self.session_manager.create_session(
                    browser_type=args.get("browser_type", "chromium"),
                    headless=args.get("headless", False),
                    profile_directory=args.get("profile_directory"),
                    initial_url=args.get("initial_url"),
                )
                result["result"] = {
                    "session_id": session.session_id,
                    "browser_type": session.browser_type,
                    "created_at": session.created_at,
                }
                page = self.session_manager.get_active_page(session.session_id)
            
            elif action_type == BrowserActionType.ATTACH_SESSION:
                session = await self.session_manager.attach_session(
                    cdp_url=args.get("cdp_url", "http://localhost:9222"),
                )
                result["result"] = {
                    "session_id": session.session_id,
                    "cdp_url": session.cdp_url,
                    "created_at": session.created_at,
                }
                page = self.session_manager.get_active_page(session.session_id)
            
            elif action_type == BrowserActionType.LIST_SESSIONS:
                result["result"] = {"sessions": self.session_manager.list_sessions()}
            
            elif action_type == BrowserActionType.CLOSE_SESSION:
                closed = await self.session_manager.close_session(args["session_id"])
                result["result"] = {"session_id": args["session_id"], "closed": closed}
            
            # ==================== Tab 管理 ====================
            elif action_type == BrowserActionType.CREATE_TAB:
                tab = await self.session_manager.create_tab(
                    session_id=sid,
                    url=args.get("url"),
                    switch_to=args.get("switch_to", True),
                )
                result["result"] = {
                    "tab_id": tab.tab_id,
                    "url": tab.url,
                    "is_active": tab.is_active,
                }
                page = tab.page
            
            elif action_type == BrowserActionType.SWITCH_TAB:
                switched = await self.session_manager.switch_tab(
                    session_id=sid,
                    tab_id=args["tab_id"],
                )
                result["result"] = {"tab_id": args["tab_id"], "switched": switched}
                if switched:
                    page = self.session_manager.get_active_page(sid)
            
            elif action_type == BrowserActionType.CLOSE_TAB:
                closed = await self.session_manager.close_tab(
                    session_id=sid,
                    tab_id=args["tab_id"],
                )
                result["result"] = {"tab_id": args["tab_id"], "closed": closed}
                page = self.session_manager.get_active_page(sid)
            
            elif action_type == BrowserActionType.LIST_TABS:
                session = self.session_manager.get_session(sid)
                tabs = []
                if session:
                    for tab_id, tab in session.tabs.items():
                        tabs.append({
                            "tab_id": tab_id,
                            "url": tab.url,
                            "title": tab.title,
                            "is_active": tab.is_active,
                        })
                result["result"] = {"tabs": tabs}
            
            # ==================== 导航 ====================
            elif action_type == BrowserActionType.GO_TO_URL:
                await page.goto(args["url"], wait_until="domcontentloaded")
                result["result"] = {"url": page.url}
            
            elif action_type == BrowserActionType.GO_BACK:
                await page.go_back()
                result["result"] = {"url": page.url}
            
            elif action_type == BrowserActionType.GO_FORWARD:
                await page.go_forward()
                result["result"] = {"url": page.url}
            
            elif action_type == BrowserActionType.REFRESH:
                await page.reload()
                result["result"] = {"url": page.url}
            
            # ==================== 元素交互 ====================
            elif action_type == BrowserActionType.CLICK_ELEMENT:
                element = await DOMParser.get_element_by_index(page, args["index"])
                if not element:
                    raise ValueError(f"Element with index {args['index']} not found")
                await element.click()
                result["result"] = {"index": args["index"], "clicked": True}
            
            elif action_type == BrowserActionType.INPUT_TEXT:
                element = await DOMParser.get_element_by_index(page, args["index"])
                if not element:
                    raise ValueError(f"Element with index {args['index']} not found")
                # 清空后输入
                await element.fill("")
                await element.fill(args["text"])
                result["result"] = {"index": args["index"], "text": args["text"]}
            
            # ==================== 滚动 ====================
            elif action_type == BrowserActionType.SCROLL_DOWN:
                amount = args.get("amount", 500)
                await page.evaluate(f"window.scrollBy(0, {amount})")
                result["result"] = {"scrolled": amount}
            
            elif action_type == BrowserActionType.SCROLL_UP:
                amount = args.get("amount", 500)
                await page.evaluate(f"window.scrollBy(0, -{amount})")
                result["result"] = {"scrolled": -amount}
            
            # ==================== 键盘 ====================
            elif action_type == BrowserActionType.PRESS_KEY:
                await page.keyboard.press(args["key"])
                result["result"] = {"key": args["key"]}
            
            # ==================== 其他 ====================
            elif action_type == BrowserActionType.WAIT:
                import asyncio
                await asyncio.sleep(args["seconds"])
                result["result"] = {"waited": args["seconds"]}
            
            elif action_type == BrowserActionType.SCREENSHOT:
                # 只返回截图，在 PageState 中
                pass
            
            elif action_type == BrowserActionType.PAGE_STATE:
                # 只获取页面状态，不执行操作
                pass
            
            elif action_type == BrowserActionType.EXTRACT_CONTENT:
                selector = args.get("selector")
                if selector:
                    content = await page.inner_text(selector)
                else:
                    content = await page.inner_text("body")
                result["result"] = {"content": content[:5000]}  # 限制长度
            
            elif action_type == BrowserActionType.STOP:
                result["result"] = {"stopped": True}
            
            else:
                raise ValueError(f"Unknown action type: {action_type}")
        
        except Exception as e:
            self.logger.logger.error(f"[BrowserExecutor] 执行失败: {e}")
            result = {"ok": False, "error": str(e)}
        
        # 获取新页面状态
        new_page_state = None
        if page:
            try:
                new_page_state = await DOMParser.parse_page(
                    page,
                    max_elements=args.get("max_elements", 100),
                    include_screenshot=args.get("include_screenshot", True),
                )
            except Exception as e:
                self.logger.logger.warning(f"[BrowserExecutor] 获取页面状态失败: {e}")
        
        return result, new_page_state
```

### 4.4 Planner (`core/planner.py`)

高层规划，决定下一步做什么。

```python
"""
Browser Planner - 高层规划

职责：
1. 观察当前页面状态（URL、标题、元素列表）
2. 结合任务目标和历史，推理下一步
3. 输出自然语言的动作描述和目标元素索引

输入：PageState + task_description + history
输出：BrowserPlannerOutput
"""

from typing import Dict, Any, Optional, List, AsyncGenerator
import json

from ..models import BrowserPlannerOutput, PageState
from useit_ai_run.node_handler.functional_nodes.computer_use.gui_v2.utils.llm_client import VLMClient, LLMConfig
from useit_ai_run.utils.logger_utils import LoggerUtils


BROWSER_PLANNER_SYSTEM_PROMPT = """You are an AI assistant that helps users navigate web pages. You observe the current page state and decide what action to take next.

You will receive:
1. The current page URL and title
2. A list of interactive elements with their indices
3. The user's goal
4. The history of previous actions

Your job is to:
1. Observe the current page state
2. Reason about what to do next
3. Decide on the next action
4. Identify the target element (if any) by its index

Output Format (JSON):
{
    "Observation": "What you see on the page",
    "Reasoning": "Your thought process",
    "Action": "Natural language description of the action (e.g., 'Click the search box', 'Type hello in the input field')",
    "TargetElement": <element_index or null>,
    "MilestoneCompleted": <true if the milestone is complete, false otherwise>
}

Important:
- Use the element INDEX (a number) to identify elements
- If the task is complete, set MilestoneCompleted to true and Action to empty string
- Be concise in your observations and reasoning
"""


BROWSER_PLANNER_USER_PROMPT = """## Current Page State
{page_state}

## Task Goal
{task_goal}

## Milestone Objective
{milestone_objective}

## Previous Actions
{history}

Now analyze the page and decide the next action. Output JSON only:"""


class BrowserPlanner:
    """Browser Planner"""
    
    def __init__(
        self,
        model: str = "gpt-4o",
        api_keys: Optional[Dict[str, str]] = None,
        max_tokens: int = 2048,
        temperature: float = 0.0,
        node_id: str = "",
    ):
        self.model = model
        self.node_id = node_id
        self.logger = LoggerUtils(component_name="BrowserPlanner")
        
        config = LLMConfig(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            role="browser_planner",
            node_id=node_id,
        )
        self.vlm = VLMClient(config=config, api_keys=api_keys, logger=self.logger)
    
    def set_node_id(self, node_id: str):
        """更新节点 ID"""
        self.node_id = node_id
        self.vlm.config.node_id = node_id
    
    async def plan(
        self,
        page_state: PageState,
        task_description: str,
        milestone_objective: str,
        history_md: str = "",
        log_dir: Optional[str] = None,
    ) -> BrowserPlannerOutput:
        """
        非流式规划
        
        Args:
            page_state: 当前页面状态
            task_description: 整体任务描述
            milestone_objective: 当前里程碑目标
            history_md: 历史动作 Markdown
            log_dir: 日志目录
            
        Returns:
            BrowserPlannerOutput
        """
        user_prompt = BROWSER_PLANNER_USER_PROMPT.format(
            page_state=page_state.to_prompt_str(max_elements=50),
            task_goal=task_description,
            milestone_objective=milestone_objective,
            history=history_md or "No previous actions",
        )
        
        response = await self.vlm.call(
            prompt=user_prompt,
            system_prompt=BROWSER_PLANNER_SYSTEM_PROMPT,
            screenshot_base64=page_state.screenshot_base64,
            log_dir=log_dir,
        )
        
        return self._parse_response(response["content"])
    
    async def plan_streaming(
        self,
        page_state: PageState,
        task_description: str,
        milestone_objective: str,
        history_md: str = "",
        log_dir: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式规划
        
        Yields:
            - {"type": "reasoning_delta", "content": str, "source": "planner"}
            - {"type": "plan_complete", "content": {...}}
        """
        user_prompt = BROWSER_PLANNER_USER_PROMPT.format(
            page_state=page_state.to_prompt_str(max_elements=50),
            task_goal=task_description,
            milestone_objective=milestone_objective,
            history=history_md or "No previous actions",
        )
        
        full_content = ""
        
        async for chunk in self.vlm.stream(
            prompt=user_prompt,
            system_prompt=BROWSER_PLANNER_SYSTEM_PROMPT,
            screenshot_base64=page_state.screenshot_base64,
            log_dir=log_dir,
        ):
            if chunk["type"] == "delta":
                full_content += chunk["content"]
                yield {
                    "type": "reasoning_delta",
                    "content": chunk["content"],
                    "source": "planner",
                }
            
            elif chunk["type"] == "complete":
                planner_output = self._parse_response(full_content)
                yield {
                    "type": "plan_complete",
                    "content": planner_output.to_dict(),
                }
    
    def _parse_response(self, response: str) -> BrowserPlannerOutput:
        """解析 LLM 响应"""
        try:
            # 提取 JSON
            parsed = self._extract_json(response)
            
            return BrowserPlannerOutput(
                observation=parsed.get("Observation", ""),
                reasoning=parsed.get("Reasoning", ""),
                next_action=parsed.get("Action", ""),
                target_element=parsed.get("TargetElement"),
                is_milestone_completed=parsed.get("MilestoneCompleted", False),
            )
        
        except Exception as e:
            self.logger.logger.error(f"解析 Planner 响应失败: {e}, 原始: {response[:300]}")
            return BrowserPlannerOutput(
                observation="Parse error",
                reasoning=str(e),
                next_action="",
                is_milestone_completed=False,
            )
    
    def _extract_json(self, text: str) -> Dict[str, Any]:
        """从文本中提取 JSON"""
        text = text.strip()
        
        # 直接尝试解析
        if text.startswith("{"):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass
        
        # 尝试从 ```json 块中提取
        import re
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        # 尝试提取第一个 { 到最后一个 }
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
        
        raise ValueError(f"无法从响应中提取 JSON: {text[:200]}...")
```

---

## 5. Agent 实现 (`agent.py`)

```python
"""
Browser Agent - 浏览器自动化 Agent

Agent 是 Planner 和 Executor 的协调者：
1. 接收任务上下文
2. 调用 Planner 进行规划
3. 调用 Executor 执行动作
4. 返回执行结果
"""

from typing import Dict, Any, Optional, AsyncGenerator, List

from .models import (
    BrowserContext,
    BrowserAgentStep,
    BrowserPlannerOutput,
    BrowserAction,
    BrowserActionType,
    PageState,
)
from .core.planner import BrowserPlanner
from .core.executor import BrowserExecutor
from .core.session_manager import SessionManager
from .core.dom_parser import DOMParser
from useit_ai_run.utils.logger_utils import LoggerUtils


class BrowserAgent:
    """
    Browser Agent
    
    职责：
    1. 协调 Planner 和 Executor
    2. 管理 Session
    3. 提供流式/非流式接口
    """
    
    def __init__(
        self,
        planner_model: str = "gpt-4o",
        api_keys: Optional[Dict[str, str]] = None,
        node_id: str = "",
        session_manager: Optional[SessionManager] = None,
    ):
        self.logger = LoggerUtils(component_name="BrowserAgent")
        self.node_id = node_id
        
        # Session 管理器（可共享）
        self.session_manager = session_manager or SessionManager()
        
        # Planner
        self.planner = BrowserPlanner(
            model=planner_model,
            api_keys=api_keys,
            node_id=node_id,
        )
        
        # Executor
        self.executor = BrowserExecutor(
            session_manager=self.session_manager,
            logger=self.logger,
        )
        
        self.logger.logger.info(f"[BrowserAgent] 初始化完成 - Planner: {planner_model}")
    
    def set_node_id(self, node_id: str):
        """更新节点 ID"""
        self.node_id = node_id
        self.planner.set_node_id(node_id)
    
    async def step(
        self,
        context: BrowserContext,
        log_dir: Optional[str] = None,
    ) -> BrowserAgentStep:
        """
        执行单步（非流式）
        """
        self.logger.logger.info(f"[BrowserAgent] 开始执行步骤 - Node: {context.node_id}")
        
        try:
            # Step 1: 获取/创建 Session
            session_id = context.session_id
            if not session_id:
                # 如果没有 session，创建一个
                session = await self.session_manager.create_session(
                    initial_url=context.initial_url,
                )
                session_id = session.session_id
                context.session_id = session_id
            
            # Step 2: 获取页面状态
            page = self.session_manager.get_active_page(session_id)
            page_state = await DOMParser.parse_page(page)
            
            # Step 3: Planner 规划
            planner_output = await self.planner.plan(
                page_state=page_state,
                task_description=context.task_description,
                milestone_objective=context.milestone_objective,
                history_md=context.history_md,
                log_dir=log_dir,
            )
            
            self.logger.logger.info(
                f"[BrowserAgent] Planner 完成 - MilestoneCompleted: {planner_output.is_milestone_completed}"
            )
            
            # 如果里程碑已完成
            if planner_output.is_milestone_completed:
                return BrowserAgentStep(
                    planner_output=planner_output,
                    browser_action=BrowserAction.stop(),
                    page_state=page_state,
                    reasoning_text="Milestone completed",
                )
            
            # Step 4: 解析并执行动作
            action = self._parse_action(planner_output)
            action.args["session_id"] = session_id
            
            action_result, new_page_state = await self.executor.execute(action, session_id)
            
            self.logger.logger.info(
                f"[BrowserAgent] Executor 完成 - Action: {action.action_type.value}"
            )
            
            return BrowserAgentStep(
                planner_output=planner_output,
                browser_action=action,
                action_result=action_result,
                page_state=new_page_state,
            )
        
        except Exception as e:
            self.logger.logger.error(f"[BrowserAgent] 执行失败: {e}")
            return BrowserAgentStep(
                planner_output=BrowserPlannerOutput(
                    observation="Error occurred",
                    reasoning=str(e),
                    next_action="",
                    is_milestone_completed=False,
                ),
                error=str(e),
            )
    
    async def step_streaming(
        self,
        context: BrowserContext,
        log_dir: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行单步（流式）
        
        Yields:
            - {"type": "status", "content": str}
            - {"type": "reasoning_delta", "content": str, "source": "planner"}
            - {"type": "plan_complete", "content": {...}}
            - {"type": "action", "action": {...}}
            - {"type": "step_complete", "content": {...}}
            - {"type": "error", "content": str}
        """
        self.logger.logger.info(f"[BrowserAgent] 开始流式执行 - Node: {context.node_id}")
        
        planner_output: Optional[BrowserPlannerOutput] = None
        
        try:
            # Step 1: 获取/创建 Session
            yield {"type": "status", "content": "Initializing browser session..."}
            
            session_id = context.session_id
            if not session_id:
                session = await self.session_manager.create_session(
                    initial_url=context.initial_url,
                )
                session_id = session.session_id
                context.session_id = session_id
            
            # Step 2: 获取页面状态
            yield {"type": "status", "content": "Analyzing page..."}
            
            page = self.session_manager.get_active_page(session_id)
            page_state = await DOMParser.parse_page(page)
            
            # Step 3: 流式 Planner
            yield {"type": "status", "content": "Planning next action..."}
            
            async for event in self.planner.plan_streaming(
                page_state=page_state,
                task_description=context.task_description,
                milestone_objective=context.milestone_objective,
                history_md=context.history_md,
                log_dir=log_dir,
            ):
                yield event
                
                if event.get("type") == "plan_complete":
                    content = event.get("content", {})
                    planner_output = BrowserPlannerOutput(
                        observation=content.get("Observation", ""),
                        reasoning=content.get("Reasoning", ""),
                        next_action=content.get("Action", ""),
                        target_element=content.get("TargetElement"),
                        is_milestone_completed=content.get("MilestoneCompleted", False),
                    )
            
            if not planner_output:
                yield {"type": "error", "content": "Planner did not return a valid result"}
                return
            
            # 如果里程碑已完成
            if planner_output.is_milestone_completed:
                action = BrowserAction.stop()
                yield {"type": "action", "action": action.to_dict()}
                yield {
                    "type": "step_complete",
                    "content": BrowserAgentStep(
                        planner_output=planner_output,
                        browser_action=action,
                        page_state=page_state,
                        reasoning_text="Milestone completed",
                    ).to_dict(),
                }
                return
            
            # Step 4: 执行动作
            yield {"type": "status", "content": "Executing action..."}
            
            action = self._parse_action(planner_output)
            action.args["session_id"] = session_id
            
            yield {"type": "action", "action": action.to_dict()}
            
            action_result, new_page_state = await self.executor.execute(action, session_id)
            
            # 发送完成事件
            yield {
                "type": "step_complete",
                "content": BrowserAgentStep(
                    planner_output=planner_output,
                    browser_action=action,
                    action_result=action_result,
                    page_state=new_page_state,
                ).to_dict(),
            }
        
        except Exception as e:
            self.logger.logger.error(f"[BrowserAgent] 流式执行失败: {e}")
            yield {"type": "error", "content": str(e)}
    
    def _parse_action(self, planner_output: BrowserPlannerOutput) -> BrowserAction:
        """
        解析 Planner 输出为 BrowserAction
        
        基于 Planner 的自然语言描述和目标元素索引，
        推断具体的动作类型和参数。
        """
        action_text = planner_output.next_action.lower()
        target_index = planner_output.target_element
        
        # 简单的关键词匹配（可以用更复杂的 NLU）
        if "click" in action_text:
            if target_index is not None:
                return BrowserAction.click(target_index)
            # 如果没有目标索引但有点击意图，可能需要更多信息
            raise ValueError("Click action requires a target element index")
        
        elif "type" in action_text or "input" in action_text or "enter" in action_text:
            # 提取要输入的文本
            # 假设格式类似 "Type 'hello' in the search box"
            import re
            text_match = re.search(r"['\"](.+?)['\"]", planner_output.next_action)
            text = text_match.group(1) if text_match else ""
            
            if target_index is not None:
                return BrowserAction.input_text(target_index, text)
            raise ValueError("Input action requires a target element index")
        
        elif "scroll down" in action_text:
            return BrowserAction.scroll_down()
        
        elif "scroll up" in action_text:
            return BrowserAction(action_type=BrowserActionType.SCROLL_UP, args={"amount": 500})
        
        elif "go to" in action_text or "navigate" in action_text:
            # 提取 URL
            import re
            url_match = re.search(r"https?://\S+", planner_output.next_action)
            if url_match:
                return BrowserAction.go_to_url(url_match.group())
            raise ValueError("Go to URL action requires a URL")
        
        elif "press" in action_text or "key" in action_text:
            # 提取按键
            key_keywords = ["enter", "tab", "escape", "backspace", "delete"]
            for key in key_keywords:
                if key in action_text:
                    return BrowserAction.press_key(key.capitalize())
            raise ValueError("Press key action requires a key name")
        
        elif "wait" in action_text:
            return BrowserAction(action_type=BrowserActionType.WAIT, args={"seconds": 2})
        
        elif "back" in action_text:
            return BrowserAction(action_type=BrowserActionType.GO_BACK, args={})
        
        elif "refresh" in action_text or "reload" in action_text:
            return BrowserAction(action_type=BrowserActionType.REFRESH, args={})
        
        else:
            # 默认点击（如果有目标元素）
            if target_index is not None:
                return BrowserAction.click(target_index)
            
            # 无法解析
            self.logger.logger.warning(f"无法解析动作: {planner_output.next_action}")
            return BrowserAction.stop()
    
    async def cleanup(self):
        """清理资源"""
        await self.session_manager.cleanup()
```

---

## 6. Handler 实现 (`handler_v2.py`)

```python
"""
Browser Node Handler V2 - 符合新架构的 Browser 节点处理器

职责：
1. 实现 BaseNodeHandlerV2 接口
2. 将 NodeContext 转换为 BrowserContext
3. 调用 BrowserAgent 执行
4. 将事件转换为统一格式
"""

from __future__ import annotations

import uuid
from typing import Dict, Any, List, AsyncGenerator, Optional

from useit_ai_run.node_handler.base_v2 import (
    BaseNodeHandlerV2,
    NodeContext as V2NodeContext,
    NodeCompleteEvent,
    ErrorEvent,
)
from useit_ai_run.utils.logger_utils import LoggerUtils

from .agent import BrowserAgent
from .models import BrowserContext, BrowserAgentStep


logger = LoggerUtils(component_name="BrowserNodeHandlerV2")


class BrowserNodeHandlerV2(BaseNodeHandlerV2):
    """
    Browser 节点处理器 V2
    
    支持的节点类型：
    - browser-use
    - computer-use-browser
    """
    
    @classmethod
    def supported_types(cls) -> List[str]:
        return ["browser-use", "computer-use-browser"]
    
    async def execute(self, ctx: V2NodeContext) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行 Browser 节点
        """
        logger.logger.info(f"[BrowserNodeHandlerV2] 开始执行节点: {ctx.node_id}")
        
        cua_id = f"cua_{uuid.uuid4().hex[:8]}_{ctx.node_id}"
        
        try:
            # Step 1: 发送节点开始事件
            if self._is_first_call(ctx):
                yield {
                    "type": "node_start",
                    "nodeId": ctx.node_id,
                    "title": ctx.get_node_title(),
                    "nodeType": ctx.node_type,
                    "instruction": ctx.get_node_instruction(),
                }
            
            # Step 2: 计算步数
            step_count = self._increment_step_count(ctx)
            
            # Step 3: 发送 CUA 开始事件
            yield {
                "type": "cua_start",
                "cuaId": cua_id,
                "step": step_count,
                "title": ctx.get_node_title(),
                "nodeId": ctx.node_id,
            }
            
            # Step 4: 创建 BrowserAgent
            agent = BrowserAgent(
                planner_model=ctx.planner_model,
                api_keys=ctx.planner_api_keys,
                node_id=ctx.node_id,
            )
            
            # Step 5: 转换为 BrowserContext
            browser_context = self._convert_to_browser_context(ctx)
            
            # Step 6: 执行 Agent（流式）
            agent_step: Optional[BrowserAgentStep] = None
            planner_output_dict: Dict[str, Any] = {}
            
            async for event in agent.step_streaming(
                context=browser_context,
                log_dir=ctx.log_folder,
            ):
                event_type = event.get("type", "")
                
                # 转发推理事件
                if event_type == "reasoning_delta":
                    yield {
                        "type": "cua_delta",
                        "cuaId": cua_id,
                        "reasoning": event.get("content", ""),
                        "kind": event.get("source", "planner"),
                    }
                
                # 转发规划完成事件
                elif event_type == "plan_complete":
                    planner_output_dict = event.get("content", {})
                    yield {
                        "type": "planner_complete",
                        "content": {"vlm_plan": planner_output_dict},
                    }
                
                # 转发动作事件
                elif event_type == "action":
                    action = event.get("action", {})
                    yield {
                        "type": "cua_update",
                        "cuaId": cua_id,
                        "content": action,
                        "kind": "executor",
                    }
                    # 标准 tool_call 格式
                    yield {
                        "type": "tool_call",
                        "id": f"call_{cua_id}_{step_count}",
                        "target": "browser",
                        "name": action.get("type", "unknown"),
                        "args": {k: v for k, v in action.items() if k != "type"},
                    }
                
                # 捕获最终结果
                elif event_type == "step_complete":
                    content = event.get("content", {})
                    agent_step = self._parse_step_complete(content)
                
                # 转发状态事件
                elif event_type == "status":
                    yield {
                        "type": "status",
                        "content": event.get("content", ""),
                    }
                
                # 转发错误
                elif event_type == "error":
                    yield {
                        "type": "cua_end",
                        "cuaId": cua_id,
                        "status": "error",
                        "error": event.get("content", "Unknown error"),
                    }
                    yield ErrorEvent(
                        message=event.get("content", "Unknown error"),
                        node_id=ctx.node_id,
                    ).to_dict()
                    return
            
            # Step 7: 处理最终结果
            if agent_step:
                is_completed = agent_step.is_completed
                action_dict = agent_step.browser_action.to_dict() if agent_step.browser_action else {}
                
                action_title = self._generate_action_title(action_dict)
                
                yield {
                    "type": "cua_end",
                    "cuaId": cua_id,
                    "status": "completed",
                    "title": action_title,
                    "action": action_dict,
                }
                
                handler_result = agent_step.planner_output.to_dict() if agent_step.planner_output else {}
                handler_result["is_node_completed"] = is_completed
                handler_result["action"] = action_dict
                
                yield NodeCompleteEvent(
                    node_id=ctx.node_id,
                    node_type=ctx.node_type,
                    is_node_completed=is_completed,
                    handler_result=handler_result,
                    action_summary=action_title,
                    node_completion_summary=handler_result.get("node_completion_summary", ""),
                ).to_dict()
            else:
                yield {
                    "type": "cua_end",
                    "cuaId": cua_id,
                    "status": "error",
                    "error": "Agent did not return a valid result",
                }
                yield ErrorEvent(
                    message="Agent did not return a valid result",
                    node_id=ctx.node_id,
                ).to_dict()
            
            # 清理资源
            await agent.cleanup()
        
        except Exception as e:
            error_msg = f"Browser 节点执行失败: {str(e)}"
            logger.logger.error(error_msg, exc_info=True)
            
            yield {
                "type": "cua_end",
                "cuaId": cua_id,
                "status": "error",
                "error": error_msg,
            }
            yield ErrorEvent(message=error_msg, node_id=ctx.node_id).to_dict()
    
    def _convert_to_browser_context(self, ctx: V2NodeContext) -> BrowserContext:
        """将 V2 NodeContext 转换为 BrowserContext"""
        return BrowserContext(
            node_id=ctx.node_id,
            task_description=ctx.query,
            milestone_objective=ctx.get_node_instruction(),
            initial_url=ctx.node_dict.get("data", {}).get("initial_url"),
            guidance_steps=self._get_guidance_steps(ctx.node_dict),
            history_md=ctx.get_history_md() if hasattr(ctx, 'get_history_md') else (ctx.history_md or ""),
            loop_context=ctx.get_loop_context(),
        )
    
    def _get_guidance_steps(self, node_dict: Dict[str, Any]) -> List[str]:
        """从节点配置中提取指导步骤"""
        if node_dict.get("milestone_steps"):
            return node_dict["milestone_steps"]
        return []
    
    def _parse_step_complete(self, content: Dict[str, Any]) -> BrowserAgentStep:
        """解析 step_complete 事件内容"""
        from .models import BrowserPlannerOutput, BrowserAction, BrowserActionType
        
        planner_dict = content.get("planner", {})
        planner_output = BrowserPlannerOutput(
            observation=planner_dict.get("Observation", ""),
            reasoning=planner_dict.get("Reasoning", ""),
            next_action=planner_dict.get("Action", ""),
            target_element=planner_dict.get("TargetElement"),
            is_milestone_completed=planner_dict.get("MilestoneCompleted", False),
            completion_summary=planner_dict.get("node_completion_summary"),
        )
        
        action_dict = content.get("action")
        browser_action = None
        if action_dict:
            action_type_str = action_dict.get("type", "stop")
            try:
                action_type = BrowserActionType(action_type_str)
            except ValueError:
                action_type = BrowserActionType.STOP
            browser_action = BrowserAction(
                action_type=action_type,
                args={k: v for k, v in action_dict.items() if k != "type"},
            )
        
        return BrowserAgentStep(
            planner_output=planner_output,
            browser_action=browser_action,
            action_result=content.get("action_result"),
            reasoning_text=content.get("reasoning", ""),
            token_usage=content.get("token_usage", {}),
            error=content.get("error"),
        )
    
    def _generate_action_title(self, action: Optional[Dict[str, Any]]) -> str:
        """生成用户友好的动作标题"""
        if not action:
            return "Completed"
        
        action_type = action.get("type", "").lower()
        
        if action_type == "click_element":
            return f"Click element [{action.get('index', '?')}]"
        elif action_type == "input_text":
            text = action.get("text", "")[:15]
            return f"Type: {text}..."
        elif action_type == "go_to_url":
            url = action.get("url", "")[:30]
            return f"Navigate: {url}..."
        elif action_type == "scroll_down":
            return "Scroll down"
        elif action_type == "scroll_up":
            return "Scroll up"
        elif action_type == "press_key":
            return f"Press: {action.get('key', '')}"
        elif action_type == "stop":
            return "Sub-Task Completed"
        else:
            return f"Action: {action_type}"
```

---

## 7. 模块导出 (`__init__.py`)

```python
"""
Browser Use - 浏览器自动化模块

基于 Playwright 的浏览器自动化，支持 DOM 元素索引定位。

使用示例:

    from browser_use import BrowserAgent, BrowserContext
    
    agent = BrowserAgent(
        planner_model="gpt-4o",
        api_keys={"OPENAI_API_KEY": "..."},
    )
    
    context = BrowserContext(
        node_id="node_1",
        task_description="在 Google 上搜索 Python",
        milestone_objective="打开 Google 并输入搜索词",
        initial_url="https://google.com",
    )
    
    # 流式执行
    async for event in agent.step_streaming(context):
        print(event)
"""

# 核心类
from .agent import BrowserAgent
from .handler_v2 import BrowserNodeHandlerV2

# 数据模型
from .models import (
    BrowserActionType,
    DOMElement,
    PageState,
    BrowserAction,
    BrowserPlannerOutput,
    BrowserAgentStep,
    BrowserContext,
)

# 核心组件
from .core.planner import BrowserPlanner
from .core.executor import BrowserExecutor
from .core.session_manager import SessionManager
from .core.dom_parser import DOMParser

__all__ = [
    # 主要入口
    "BrowserAgent",
    "BrowserNodeHandlerV2",
    
    # 数据模型
    "BrowserActionType",
    "DOMElement",
    "PageState",
    "BrowserAction",
    "BrowserPlannerOutput",
    "BrowserAgentStep",
    "BrowserContext",
    
    # 核心组件
    "BrowserPlanner",
    "BrowserExecutor",
    "SessionManager",
    "DOMParser",
]
```

---

## 8. 依赖要求

在 `requirements.txt` 中添加：

```
playwright>=1.40.0
```

安装 Playwright 浏览器：

```bash
playwright install chromium
```

---

## 9. 与 GUI 模块的对比

| 模块 | GUI (`gui_v2`) | Browser Use |
|------|---------------|-------------|
| **定位方式** | 屏幕坐标 `[x, y]` | DOM 索引 `index` |
| **Planner 输入** | 截图 + VLM | 截图 + 元素列表 + VLM |
| **Actor/Executor** | 生成坐标动作 | 调用 Playwright API |
| **状态获取** | 截图 | PageState (URL, title, elements) |
| **多实例** | 不支持 | SessionManager |
| **多标签页** | 不适用 | Tab 管理 |

---

## 10. 待实现功能

1. **高级元素定位**: 支持 CSS 选择器、XPath 等
2. **智能等待**: 自动等待页面加载、元素出现
3. **iframe 支持**: 处理嵌套框架
4. **文件上传/下载**: 支持文件操作
5. **Cookie/Session 持久化**: 登录状态保持
6. **错误恢复**: 自动重试、回滚机制
7. **性能优化**: 元素缓存、批量操作

---

## 11. 测试计划

1. **单元测试**: 各核心组件的独立测试
2. **集成测试**: 完整流程的端到端测试
3. **性能测试**: 大量元素页面的解析性能
4. **兼容性测试**: 不同浏览器、不同网站的兼容性
