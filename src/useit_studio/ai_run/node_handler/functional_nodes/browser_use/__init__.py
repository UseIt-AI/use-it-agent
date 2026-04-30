"""
Browser Use - 浏览器自动化模块

基于 DOM 元素索引的浏览器自动化。

架构说明：
- 后端：调用 Planner 分析页面状态，输出 tool_call 事件
- 前端：执行浏览器操作，返回页面状态（URL、标题、元素列表、截图）

与 Computer Use (GUI) 的区别：
- GUI: 基于屏幕坐标 [x, y]，使用 VLM + Actor 识别和定位
- Browser: 基于 DOM 元素索引，前端提供元素列表，Planner 直接输出索引

使用示例:

    from browser_use import BrowserAgent, BrowserContext, PageState
    
    # 前端返回的页面状态
    page_state = PageState.from_dict({
        "url": "https://google.com",
        "title": "Google",
        "elements": [
            {"index": 0, "tag": "input", "text": "", "attributes": {"placeholder": "Search"}},
            {"index": 1, "tag": "button", "text": "Google Search"},
        ],
        "screenshot": "<base64>",
    })
    
    agent = BrowserAgent(
        planner_model="gpt-4o",
        api_keys={"OPENAI_API_KEY": "..."},
    )
    
    context = BrowserContext(
        node_id="node_1",
        task_description="在 Google 上搜索 Python",
        milestone_objective="打开 Google 并输入搜索词",
        page_state=page_state,
    )
    
    # 流式执行
    async for event in agent.step_streaming(context):
        if event["type"] == "tool_call":
            # 发送给前端执行
            print(event)
"""

# 核心类
from .agent import BrowserAgent
from .handler import BrowserNodeHandler

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

__all__ = [
    # 主要入口
    "BrowserAgent",
    "BrowserNodeHandler",
    
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
]
