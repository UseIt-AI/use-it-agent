"""
Document Extract 工具模块

从 PDF 文档中提取文本和图表。
支持学术论文（ArXiv 等）的 Figure 提取。
"""

from .tool import DocExtractTool, create_doc_extract_tool, DocExtractInput

__all__ = [
    "DocExtractTool",
    "create_doc_extract_tool",
    "DocExtractInput",
]
