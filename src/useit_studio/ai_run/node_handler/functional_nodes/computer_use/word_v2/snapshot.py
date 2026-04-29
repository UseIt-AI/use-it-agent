"""
Word Agent - 文档快照数据结构

DocumentSnapshot 实现了 BaseSnapshot Protocol，
用于表示 Word 文档的状态。
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

# 导入 toon_format 用于压缩输出
try:
    from toon_format import encode as toon_encode
except ImportError:
    # 如果 toon_format 不可用，使用 json
    import json
    def toon_encode(obj):
        return json.dumps(obj, ensure_ascii=False, indent=2)


# ==================== 文档信息 ====================

@dataclass
class DocumentInfo:
    """
    文档基本信息
    
    对应前端 _extract_document_info 返回的结构
    """
    name: str                           # 文档名称
    path: Optional[str] = None          # 文档完整路径
    saved: bool = True                  # 是否已保存
    current_page: int = 1               # 当前页码
    page_count: int = 1                 # 总页数
    word_count: int = 0                 # 字数
    character_count: int = 0            # 字符数
    paragraph_count: int = 0            # 段落数

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "saved": self.saved,
            "current_page": self.current_page,
            "page_count": self.page_count,
            "word_count": self.word_count,
            "character_count": self.character_count,
            "paragraph_count": self.paragraph_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DocumentInfo":
        return cls(
            name=data.get("name", "Unknown"),
            path=data.get("path"),
            saved=data.get("saved", True),
            current_page=data.get("current_page", 1),
            page_count=data.get("page_count", 1),
            word_count=data.get("word_count", 0),
            character_count=data.get("character_count", 0),
            paragraph_count=data.get("paragraph_count", 0),
        )


@dataclass
class ParagraphInfo:
    """段落信息（含样式）"""
    index: int                          # 段落索引
    text: str                           # 段落文本
    style: str = "Normal"               # 样式名称
    font_name: Optional[str] = None     # 字体名称
    font_size: Optional[float] = None   # 字体大小
    is_bold: bool = False               # 是否加粗
    is_italic: bool = False             # 是否斜体
    alignment: str = "Left"             # 对齐方式

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "text": self.text,
            "style": self.style,
            "font_name": self.font_name,
            "font_size": self.font_size,
            "is_bold": self.is_bold,
            "is_italic": self.is_italic,
            "alignment": self.alignment,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ParagraphInfo":
        return cls(
            index=data.get("index", 0),
            text=data.get("text", ""),
            style=data.get("style", "Normal"),
            font_name=data.get("font_name"),
            font_size=data.get("font_size"),
            is_bold=data.get("is_bold", False),
            is_italic=data.get("is_italic", False),
            alignment=data.get("alignment", "Left"),
        )


@dataclass
class TableInfo:
    """表格信息"""
    index: int                          # 表格索引
    rows: int                           # 行数
    cols: int                           # 列数
    cells: List[Dict[str, Any]] = field(default_factory=list)  # 单元格数据

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "rows": self.rows,
            "cols": self.cols,
            "cells": self.cells,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TableInfo":
        return cls(
            index=data.get("index", 0),
            rows=data.get("rows", 0),
            cols=data.get("cols", 0),
            cells=data.get("cells", []),
        )


@dataclass
class DocumentContent:
    """
    文档内容
    
    保存原始数据，不做结构转换，确保所有信息都传递给 AI。
    """
    text: str = ""                      # 全文档文本
    paragraphs_raw: List[Dict[str, Any]] = field(default_factory=list)  # 原始段落数据
    tables_raw: List[Dict[str, Any]] = field(default_factory=list)      # 原始表格数据
    current_page: int = 1               # 当前页码
    total_pages: int = 1                # 总页数
    page_range: str = ""                # 页面范围

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "paragraphs": self.paragraphs_raw,
            "tables": self.tables_raw,
            "current_page": self.current_page,
            "total_pages": self.total_pages,
            "page_range": self.page_range,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DocumentContent":
        return cls(
            text=data.get("text", ""),
            paragraphs_raw=data.get("paragraphs", []),
            tables_raw=data.get("tables", []),
            current_page=data.get("current_page", 1),
            total_pages=data.get("total_pages", 1),
            page_range=data.get("page_range", ""),
        )
    
    @property
    def paragraphs(self) -> List[ParagraphInfo]:
        """兼容属性"""
        return [ParagraphInfo.from_dict(p) for p in self.paragraphs_raw]
    
    @property
    def tables(self) -> List[TableInfo]:
        """兼容属性"""
        return [TableInfo.from_dict(t) for t in self.tables_raw]


# ==================== 文档快照 ====================

@dataclass
class DocumentSnapshot:
    """
    Word 文档快照
    
    实现 BaseSnapshot Protocol。
    前端请求时自动附带（如果 Word 已打开）。
    """
    document_info: DocumentInfo
    content: Optional[DocumentContent] = None
    _screenshot: Optional[str] = None  # base64 编码的截图

    @property
    def screenshot(self) -> Optional[str]:
        """base64 编码的截图"""
        return self._screenshot

    @property
    def has_data(self) -> bool:
        """是否有有效数据"""
        return self.document_info.name != "NO_DOCUMENT"

    @property
    def file_path(self) -> Optional[str]:
        """获取文件路径"""
        return self.document_info.path or self.document_info.name

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "document_info": self.document_info.to_dict(),
        }
        if self.content:
            result["content"] = self.content.to_dict()
        if self._screenshot:
            result["screenshot"] = self._screenshot
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DocumentSnapshot":
        """从字典创建 DocumentSnapshot"""
        doc_info_data = data.get("document_info", {})
        document_info = DocumentInfo.from_dict(doc_info_data)
        
        content = None
        content_data = data.get("content")
        if content_data:
            content = DocumentContent.from_dict(content_data)
        
        screenshot = data.get("screenshot")
        
        return cls(
            document_info=document_info,
            content=content,
            _screenshot=screenshot,
        )

    @classmethod
    def empty(cls) -> "DocumentSnapshot":
        """创建空的文档快照（Word 未打开时）"""
        return cls(
            document_info=DocumentInfo(name="NO_DOCUMENT"),
        )

    def to_context_format(self, max_items: int = 50, max_text_length: int = 200) -> str:
        """
        转换为 LLM 可用的文本格式
        
        实现 BaseSnapshot Protocol 的方法。
        
        Args:
            max_items: 最大段落数量
            max_text_length: 段落文本最大长度
        
        Returns:
            格式化的文本描述
        """
        result_parts = []
        
        # 1. 文档基本信息
        result_parts.append("# Document Information")
        result_parts.append(toon_encode(self.document_info.to_dict()))
        result_parts.append("")
        
        # 2. 文档内容
        if self.content:
            content = self.content
            
            # 页面信息
            page_info = {
                "current_page": content.current_page,
                "total_pages": content.total_pages,
            }
            if content.page_range:
                page_info["page_range"] = content.page_range
            
            result_parts.append("# Current Page")
            result_parts.append(toon_encode(page_info))
            result_parts.append("")
            
            # 段落信息
            if content.paragraphs_raw:
                result_parts.append("# Paragraphs")
                
                para_list = []
                for para in content.paragraphs_raw[:max_items]:
                    para_copy = dict(para)
                    if "text" in para_copy and len(para_copy["text"]) > max_text_length:
                        para_copy["text"] = para_copy["text"][:max_text_length] + "..."
                    para_list.append(para_copy)
                
                result_parts.append(toon_encode(para_list))
                
                if len(content.paragraphs_raw) > max_items:
                    result_parts.append(f"# ... ({len(content.paragraphs_raw) - max_items} more paragraphs)")
                result_parts.append("")
            
            # 表格信息
            if content.tables_raw:
                result_parts.append("# Tables")
                tables_to_show = content.tables_raw[:5]
                result_parts.append(toon_encode(tables_to_show))
                
                if len(content.tables_raw) > 5:
                    result_parts.append(f"# ... ({len(content.tables_raw) - 5} more tables)")
                result_parts.append("")
            
            # 全文本
            if not content.paragraphs_raw and content.text:
                result_parts.append("# Document Text")
                text_preview = content.text[:2000]
                if len(content.text) > 2000:
                    text_preview += f"\n... ({len(content.text) - 2000} more characters)"
                result_parts.append(f"text: {text_preview}")
                result_parts.append("")
        
        return "\n".join(result_parts)


# ==================== 辅助函数 ====================

def document_snapshot_from_dict(data: Dict[str, Any]) -> DocumentSnapshot:
    """将字典转换为 DocumentSnapshot"""
    return DocumentSnapshot.from_dict(data)
