"""
Web Search 工具模块

采用 Query 分解 + 并行搜索架构。
支持 Tavily API。
"""

from .tool import WebSearchTool, create_web_search_tool, WebSearchInput

__all__ = [
    "WebSearchTool",
    "create_web_search_tool",
    "WebSearchInput",
]
