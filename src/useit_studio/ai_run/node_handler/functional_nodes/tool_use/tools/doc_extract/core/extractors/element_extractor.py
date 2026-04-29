"""
Page element extraction from PDF pages.
"""

from typing import List

import fitz  # PyMuPDF

from ..models import PageElement


class ElementExtractor:
    """Extracts page elements (images, drawings, short text) from PDF pages."""
    
    def __init__(
        self,
        min_drawing_area: float = 100,
        max_text_chars: int = 100,
        max_text_lines: int = 2,
    ):
        """
        Initialize the element extractor.
        
        Args:
            min_drawing_area: Minimum area for vector drawings to be included
            max_text_chars: Maximum characters for short text blocks
            max_text_lines: Maximum lines for short text blocks
        """
        self.min_drawing_area = min_drawing_area
        self.max_text_chars = max_text_chars
        self.max_text_lines = max_text_lines
    
    def extract(self, page: fitz.Page) -> List[PageElement]:
        """
        Extract all relevant page elements: images, drawings, short text.
        
        Args:
            page: The PDF page to extract elements from
            
        Returns:
            List of detected page elements
        """
        elements: List[PageElement] = []
        
        # Extract images
        elements.extend(self._extract_images(page))
        
        # Extract vector drawings
        elements.extend(self._extract_drawings(page))
        
        # Extract short text blocks
        elements.extend(self._extract_short_text(page))
        
        return elements
    
    def _extract_images(self, page: fitz.Page) -> List[PageElement]:
        """Extract image blocks from the page."""
        elements = []
        text_dict = page.get_text("dict")
        
        for block in text_dict.get("blocks", []):
            if block.get("type") == 1:  # image block
                elements.append(PageElement(
                    bbox=fitz.Rect(block["bbox"]),
                    element_type="image",
                ))
        
        return elements
    
    def _extract_drawings(self, page: fitz.Page) -> List[PageElement]:
        """Extract vector drawings from the page."""
        elements = []
        
        for drawing in page.get_drawings():
            rect = fitz.Rect(drawing["rect"])
            if not rect.is_empty and rect.get_area() > self.min_drawing_area:
                elements.append(PageElement(
                    bbox=rect,
                    element_type="drawing",
                ))
        
        return elements
    
    def _extract_short_text(self, page: fitz.Page) -> List[PageElement]:
        """Extract short text blocks (labels, sub-captions)."""
        elements = []
        text_dict = page.get_text("dict")
        
        for block in text_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            
            char_count = 0
            line_count = 0
            for line in block.get("lines", []):
                line_count += 1
                for span in line.get("spans", []):
                    char_count += len(span.get("text", ""))
            
            # Only short text (axis labels, sub-figure labels, etc.)
            if char_count <= self.max_text_chars and line_count <= self.max_text_lines:
                elements.append(PageElement(
                    bbox=fitz.Rect(block["bbox"]),
                    element_type="text",
                ))
        
        return elements
