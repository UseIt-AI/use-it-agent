"""
Data models for the docling pipeline.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, TYPE_CHECKING

import fitz  # PyMuPDF


class CaptionType(Enum):
    """Type of caption (Figure or Table)."""
    FIGURE = "figure"
    TABLE = "table"


@dataclass
class Caption:
    """A detected caption (Figure or Table) with its precise location."""
    bbox: fitz.Rect
    text: str
    item_id: str  # e.g., "1", "2a", "3"
    caption_type: CaptionType


# Alias for backward compatibility
FigureCaption = Caption


@dataclass
class PageElement:
    """Generic page element (image, drawing, or text)."""
    bbox: fitz.Rect
    element_type: str  # "image", "drawing", "text", "line"


@dataclass
class FigureRegion:
    """Detected figure region anchored by a caption."""
    bbox: fitz.Rect
    caption: Caption
    label: str
    page_number: int = 0


@dataclass
class TableRegion:
    """Detected table region anchored by a caption."""
    bbox: fitz.Rect
    caption: Caption
    label: str
    page_number: int = 0


@dataclass
class PageResult:
    """Result of processing a single page."""
    page_number: int
    text: str
    figures: list  # List[FigureRegion]
    tables: list = None  # List[TableRegion]
    captions_found: int = 0
    elements_found: int = 0
    
    def __post_init__(self):
        if self.tables is None:
            self.tables = []


@dataclass
class DocumentResult:
    """Result of processing an entire document."""
    pdf_path: str
    output_dir: str
    markdown_path: str
    total_pages: int
    pages_processed: int
    figures_extracted: list  # List[FigureRegion]
    tables_extracted: list = None  # List[TableRegion]
    title: str = ""
    
    # S3 上传结果
    s3_output_prefix: Optional[str] = None  # S3 输出前缀 (如 "projects/{project_id}/outputs/{pdf_name}/")
    s3_markdown_key: Optional[str] = None  # S3 markdown 文件 key
    s3_figure_keys: Optional[List[str]] = None  # S3 figure 文件 keys
    s3_table_keys: Optional[List[str]] = None  # S3 table 文件 keys
    
    def __post_init__(self):
        if self.tables_extracted is None:
            self.tables_extracted = []
        if self.s3_figure_keys is None:
            self.s3_figure_keys = []
        if self.s3_table_keys is None:
            self.s3_table_keys = []