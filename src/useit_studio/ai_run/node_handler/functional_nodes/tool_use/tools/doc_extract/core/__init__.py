"""
Docling - PDF to Markdown converter with figure and table extraction.

A modular pipeline for extracting text, figures and tables from PDF documents,
particularly optimized for academic papers (ArXiv, etc.).
"""

from .pipeline import PDFPipeline, PipelineConfig, PipelineProgress
from .models import Caption, CaptionType, FigureCaption, FigureRegion, PageElement, TableRegion

__all__ = [
    "PDFPipeline",
    "PipelineConfig",
    "PipelineProgress",
    "Caption",
    "CaptionType",
    "FigureCaption",
    "FigureRegion",
    "TableRegion",
    "PageElement",
]

__version__ = "0.2.0"
