"""
Browser Use Controller
基于 browser-use 官方库的浏览器控制模块

官方文档:
- https://github.com/browser-use/browser-use
- https://docs.browser-use.com/customize/browser/real-browser

主要组件:
- BrowserConfig: 浏览器配置（连接真实浏览器）
- BrowserController: 浏览器控制器（执行操作）
- API 路由: FastAPI HTTP 接口

使用方法:
    # 1. 获取 Profile 列表
    GET /api/v1/browser/profiles
    
    # 2. 连接浏览器
    POST /api/v1/browser/connect
    {
        "browser_type": "chrome",
        "profile_directory": "Profile 5",
        "headless": false
    }
    
    # 3. 执行操作（支持单步或多步）
    POST /api/v1/browser/step
    {
        "actions": [
            {"action": "go_to_url", "url": "https://example.com"},
            {"action": "click_element", "index": 3}
        ]
    }
    
    # 返回: {"action_results": [...], "page_state": {...}}
"""

from .config import (
    BrowserConfig,
    BrowserType,
    BrowserProfile,
    get_default_config,
)

from .controller import (
    BrowserController,
    get_controller,
    reset_controller,
)

__all__ = [
    # 配置
    "BrowserConfig",
    "BrowserType",
    "BrowserProfile",
    "get_default_config",
    # 控制器
    "BrowserController",
    "get_controller",
    "reset_controller",
]
