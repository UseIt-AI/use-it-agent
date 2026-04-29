"""
RAG 检索工具模块

通过 HTTP 调用 RAG 服务，提供知识库检索功能。
支持 Query Extend（查询分解）+ 并行检索 + 结果聚合。
"""

from .tool import RAGTool, create_rag_tool, RAGSearchInput

__all__ = [
    "RAGTool",
    "create_rag_tool",
    "RAGSearchInput",
]
