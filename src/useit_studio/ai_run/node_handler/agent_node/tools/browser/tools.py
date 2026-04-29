"""Browser tools —— 扁平 payload `{name: action, args: {...}}` 协议。

完整迁移自 ``useit_ai_run.node_handler.functional_nodes.browser_use``：
- 连接管理：connect / attach / disconnect / status
- Tab 管理：list_tabs / create_tab / switch_tab / close_tab
- 导航：go_to_url / go_back / go_forward / refresh
- 元素交互：click_element / input_text
- 滚动 / 键盘：scroll_down / scroll_up / press_key
- 状态 / 抓取：page_state / screenshot / extract_content
- 等待：wait

Action 名严格对齐 ``BrowserActionType`` 枚举（前端 / Local Engine 直接 dispatch
这些字符串）；agent_node 工具名统一加 ``browser_`` 前缀，由 ``EngineTool.action_name``
自动剥离前缀转成 Local Engine 认识的原生 action。
"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, List, TYPE_CHECKING

from ..protocol import EngineTool, ToolCall

if TYPE_CHECKING:
    from ...models import (
        PlannerOutput,
    )


# ==========================================================================
# Router-side guidance shared across all browser_* tools
# ==========================================================================

_BROWSER_PIPELINE_DETAIL = r"""Browser automation Local Engine —
`/api/v1/browser/*`.

The browser engine talks to a Playwright / CDP instance running on the
user's machine.  Every action is dispatched as a flat tool_call
(`{name: <action>, args: {...}}`) and returns a fresh ``page_state``
(URL, title, indexed DOM elements, screenshot, tabs).

### Element addressing — DOM index, NOT pixels

Unlike the GUI engine, the browser engine does NOT take screen
coordinates.  The frontend's DOM parser tags every interactive element
with an ``index`` and exposes it in the latest ``page_state.elements``
list.  Always pick the index of the element you want to act on from the
freshest snapshot — never reuse stale indices from earlier turns.

### Required first-step protocol

The user's browser is **not** running yet on the first call.  You MUST
prepare the workspace before any other action:

1. ``browser_connect`` (or ``browser_attach`` if the user explicitly
   asked you to take over their already-open browser via CDP).  This
   spawns / attaches the engine.  After it returns, the snapshot will
   include ``page_state``.
2. If the snapshot has no ``page_state`` yet, call ``browser_page_state``
   to refresh it, OR ``browser_go_to_url`` directly when you already know
   the URL the user wants.
3. Only then click / type / extract.

Skipping step 1 → every subsequent action will fail with "no active
browser".  Re-issuing ``browser_connect`` after a successful connect →
spurious double-launch; check Agent Step History first.

### Reading the page_state snapshot

Each ``page_state`` carries:
- ``url``, ``title``
- ``elements: [{index, tag, text, attributes, position}, ...]`` — pick
  one ``index`` to interact with
- ``tabs: [{tab_index, title, url, is_active}, ...]`` and
  ``tab_count``, ``active_tab_index`` for multi-tab tasks
- ``screenshot`` (base64) — useful when the DOM tree is ambiguous

When the page is content-heavy and you need *text* (article body, table,
list of items) → call ``browser_extract_content``; the extracted text is
threaded back to the planner via ``last_execution_output`` so you can
reason on it next turn without paying for the full DOM again.

### Stopping

When the milestone is finished, set ``MilestoneCompleted: true`` and
return ``Action: "stop"``.  If you want to persist results to a file,
fill ``result_markdown`` + ``output_filename`` in the planner output —
the agent runtime will save it under the project's outputs.
"""


_CONNECT_DETAIL = (
    _BROWSER_PIPELINE_DETAIL
    + r"""

### browser_connect

Spawn a fresh browser controlled by the engine.  Use this on the very
first browser step unless the user asked you to take over their existing
browser (then use ``browser_attach`` instead).

```json
{"Action": "browser_connect",
 "Title": "Connect to browser",
 "Params": {
   "headless": false,
   "browser_type": "edge",
   "initial_url": "https://google.com"
 }}
```

- ``headless``: default ``false`` (visible window — most user-facing flows).
- ``browser_type``: one of ``edge`` (default) / ``chrome`` / ``firefox``.
- ``initial_url``: optional; if set, the engine navigates immediately and
  returns the page_state for that page.
"""
)


_GO_TO_URL_DETAIL = (
    _BROWSER_PIPELINE_DETAIL
    + r"""

### browser_go_to_url

Navigate the current tab to ``url``.  This also implicitly waits for
``DOMContentLoaded`` and returns the new ``page_state``.

```json
{"Action": "browser_go_to_url",
 "Params": {"url": "https://example.com/search?q=python"}}
```
"""
)


_CLICK_ELEMENT_DETAIL = (
    _BROWSER_PIPELINE_DETAIL
    + r"""

### browser_click_element

Click the DOM element at ``index``.  Pick the index from the latest
``page_state.elements`` — re-using an old index after the page changed
will click the wrong thing or fail with "stale element".

```json
{"Action": "browser_click_element",
 "Title": "Click Search button",
 "Params": {"index": 12}}
```
"""
)


_INPUT_TEXT_DETAIL = (
    _BROWSER_PIPELINE_DETAIL
    + r"""

### browser_input_text

Type into the DOM input at ``index``.  The engine focuses the element
and replaces its current value.

```json
{"Action": "browser_input_text",
 "Params": {"index": 4, "text": "python tutorial"}}
```
"""
)


_EXTRACT_CONTENT_DETAIL = (
    _BROWSER_PIPELINE_DETAIL
    + r"""

### browser_extract_content

Pull human-readable text from the page (article bodies, lists, tables).
Use a CSS ``selector`` to scope to a region; omit it to extract the whole
``body``.  The extracted text is threaded back into your next
``last_execution_output`` block automatically.

```json
{"Action": "browser_extract_content",
 "Params": {"selector": "article.post-content"}}
```
"""
)


# ==========================================================================
# Base class — flat protocol
# ==========================================================================


class _BrowserEngineTool(EngineTool):
    """Browser shared base — flat ``{name, args}`` tool_call payload."""

    group: ClassVar[str] = "browser"
    target: ClassVar[str] = "browser"

    def build_tool_call(
        self, params: Dict[str, Any], planner_output: "PlannerOutput"
    ) -> ToolCall:
        return ToolCall(name=self.action_name, args=dict(params))


# ==========================================================================
# Connection lifecycle
# ==========================================================================


class BrowserConnect(_BrowserEngineTool):
    name = "browser_connect"
    router_hint = (
        "Spawn a new browser session.  REQUIRED first step.  Params: "
        "headless?, browser_type?, initial_url?."
    )
    router_detail = _CONNECT_DETAIL
    input_schema = {
        "type": "object",
        "properties": {
            "headless": {"type": "boolean", "default": False},
            "browser_type": {
                "type": "string",
                "enum": ["edge", "chrome", "firefox"],
                "default": "edge",
            },
            "initial_url": {
                "type": "string",
                "description": "Optional URL to load immediately after connect.",
            },
        },
    }


class BrowserAttach(_BrowserEngineTool):
    name = "browser_attach"
    router_hint = (
        "Attach to the user's already-open browser via CDP.  Params: cdp_url."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "cdp_url": {
                "type": "string",
                "description": "Chrome DevTools Protocol URL (e.g. ws://127.0.0.1:9222/...).",
            },
        },
        "required": ["cdp_url"],
    }


class BrowserDisconnect(_BrowserEngineTool):
    name = "browser_disconnect"
    router_hint = "Disconnect from the current browser session (no params)."
    is_destructive = True
    input_schema = {"type": "object", "properties": {}}


class BrowserStatus(_BrowserEngineTool):
    name = "browser_status"
    router_hint = "Read browser connection status (no params)."
    is_read_only = True
    input_schema = {"type": "object", "properties": {}}


# ==========================================================================
# Tab management
# ==========================================================================


class BrowserListTabs(_BrowserEngineTool):
    name = "browser_list_tabs"
    router_hint = "List all open tabs in the active session (no params)."
    is_read_only = True
    input_schema = {"type": "object", "properties": {}}


class BrowserCreateTab(_BrowserEngineTool):
    name = "browser_create_tab"
    router_hint = "Open a new tab.  Params: url? (optional initial URL)."
    input_schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
        },
    }


class BrowserSwitchTab(_BrowserEngineTool):
    name = "browser_switch_tab"
    router_hint = "Switch focus to a tab.  Params: tab_id (from page_state.tabs)."
    input_schema = {
        "type": "object",
        "properties": {
            "tab_id": {"type": "string"},
        },
        "required": ["tab_id"],
    }


class BrowserCloseTab(_BrowserEngineTool):
    name = "browser_close_tab"
    router_hint = "Close a tab.  Params: tab_id."
    is_destructive = True
    input_schema = {
        "type": "object",
        "properties": {
            "tab_id": {"type": "string"},
        },
        "required": ["tab_id"],
    }


# ==========================================================================
# Navigation
# ==========================================================================


class BrowserGoToUrl(_BrowserEngineTool):
    name = "browser_go_to_url"
    router_hint = "Navigate the current tab to a URL.  Params: url."
    router_detail = _GO_TO_URL_DETAIL
    input_schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
        },
        "required": ["url"],
    }


class BrowserGoBack(_BrowserEngineTool):
    name = "browser_go_back"
    router_hint = "Browser history: go back one step (no params)."
    input_schema = {"type": "object", "properties": {}}


class BrowserGoForward(_BrowserEngineTool):
    name = "browser_go_forward"
    router_hint = "Browser history: go forward one step (no params)."
    input_schema = {"type": "object", "properties": {}}


class BrowserRefresh(_BrowserEngineTool):
    name = "browser_refresh"
    router_hint = "Refresh the current page (no params)."
    input_schema = {"type": "object", "properties": {}}


# ==========================================================================
# Element interaction
# ==========================================================================


class BrowserClickElement(_BrowserEngineTool):
    name = "browser_click_element"
    router_hint = (
        "Click a DOM element by index from the latest page_state.elements.  "
        "Params: index."
    )
    router_detail = _CLICK_ELEMENT_DETAIL
    input_schema = {
        "type": "object",
        "properties": {
            "index": {"type": "integer"},
        },
        "required": ["index"],
    }


class BrowserInputText(_BrowserEngineTool):
    name = "browser_input_text"
    router_hint = (
        "Type into a DOM input by index.  Replaces existing value.  "
        "Params: index, text."
    )
    router_detail = _INPUT_TEXT_DETAIL
    input_schema = {
        "type": "object",
        "properties": {
            "index": {"type": "integer"},
            "text": {"type": "string"},
        },
        "required": ["index", "text"],
    }


# ==========================================================================
# Scrolling / keyboard / waiting
# ==========================================================================


class BrowserScrollDown(_BrowserEngineTool):
    name = "browser_scroll_down"
    router_hint = "Scroll the viewport down by `amount` px (default 500)."
    input_schema = {
        "type": "object",
        "properties": {
            "amount": {"type": "integer", "default": 500},
        },
    }


class BrowserScrollUp(_BrowserEngineTool):
    name = "browser_scroll_up"
    router_hint = "Scroll the viewport up by `amount` px (default 500)."
    input_schema = {
        "type": "object",
        "properties": {
            "amount": {"type": "integer", "default": 500},
        },
    }


class BrowserPressKey(_BrowserEngineTool):
    name = "browser_press_key"
    router_hint = (
        "Press a keyboard key or combo on the focused element.  Params: key "
        "(e.g. 'Enter', 'Tab', 'Control+a')."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "key": {"type": "string"},
        },
        "required": ["key"],
    }


class BrowserWait(_BrowserEngineTool):
    name = "browser_wait"
    router_hint = "Pause for `seconds` (default 2) — useful while a SPA loads."
    input_schema = {
        "type": "object",
        "properties": {
            "seconds": {"type": "number", "default": 2},
        },
    }


# ==========================================================================
# State capture / extraction
# ==========================================================================


class BrowserPageState(_BrowserEngineTool):
    name = "browser_page_state"
    router_hint = (
        "Refresh the indexed DOM snapshot (URL / title / elements / "
        "screenshot / tabs).  No params."
    )
    is_read_only = True
    input_schema = {"type": "object", "properties": {}}


class BrowserScreenshot(_BrowserEngineTool):
    name = "browser_screenshot"
    router_hint = (
        "Capture only a fresh screenshot (skip DOM parsing).  Cheaper than "
        "page_state when you just need to see the page."
    )
    is_read_only = True
    input_schema = {"type": "object", "properties": {}}


class BrowserExtractContent(_BrowserEngineTool):
    name = "browser_extract_content"
    router_hint = (
        "Extract human-readable text from the current page.  Params: "
        "selector? (CSS scope, default 'body')."
    )
    router_detail = _EXTRACT_CONTENT_DETAIL
    is_read_only = True
    input_schema = {
        "type": "object",
        "properties": {
            "selector": {
                "type": "string",
                "description": (
                    "Optional CSS selector to scope extraction.  Omit for "
                    "the full document body."
                ),
            },
        },
    }


TOOLS: List[_BrowserEngineTool] = [
    # Lifecycle
    BrowserConnect(),
    BrowserAttach(),
    BrowserDisconnect(),
    BrowserStatus(),
    # Tabs
    BrowserListTabs(),
    BrowserCreateTab(),
    BrowserSwitchTab(),
    BrowserCloseTab(),
    # Navigation
    BrowserGoToUrl(),
    BrowserGoBack(),
    BrowserGoForward(),
    BrowserRefresh(),
    # Interaction
    BrowserClickElement(),
    BrowserInputText(),
    # Scroll / keyboard / wait
    BrowserScrollDown(),
    BrowserScrollUp(),
    BrowserPressKey(),
    BrowserWait(),
    # State / extract
    BrowserPageState(),
    BrowserScreenshot(),
    BrowserExtractContent(),
]
