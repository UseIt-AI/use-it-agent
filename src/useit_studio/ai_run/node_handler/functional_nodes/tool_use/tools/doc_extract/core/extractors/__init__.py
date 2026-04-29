"""
Extractors for different PDF elements.
"""

from .caption_extractor import CaptionExtractor
from .element_extractor import ElementExtractor
from .figure_extractor import FigureExtractor
from .table_extractor import TableExtractor

__all__ = [
    "CaptionExtractor",
    "ElementExtractor",
    "FigureExtractor",
    "TableExtractor",
]
