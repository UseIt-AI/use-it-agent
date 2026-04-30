"""
Caption extraction from PDF pages.
"""

import re
from typing import List, Tuple

import fitz  # PyMuPDF

from ..models import Caption, CaptionType

# Alias for backward compatibility
FigureCaption = Caption


class CaptionExtractor:
    """Extracts figure and table captions from PDF pages."""
    
    # Pattern: "Figure 1", "Fig. 2", "图 3", "Figure 1a", "Fig. 2-b" etc.
    FIGURE_PATTERN = re.compile(
        r"^\s*(Figure|Fig\.?|图)\s*(\d+[a-zA-Z]?)",
        re.IGNORECASE
    )
    
    # Pattern: "Table 1", "Tab. 2", "表 3", "Table 1a" etc.
    TABLE_PATTERN = re.compile(
        r"^\s*(Table|Tab\.?|表)\s*(\d+[a-zA-Z]?)",
        re.IGNORECASE
    )
    
    SENTENCE_ENDINGS = ".?!。？！"
    
    def __init__(self, margin_threshold: int = 20):
        """
        Initialize the caption extractor.
        
        Args:
            margin_threshold: Pixels threshold for detecting line end
        """
        self.margin_threshold = margin_threshold
    
    def extract(self, page: fitz.Page) -> List[Caption]:
        """
        Find figure captions by searching for "Figure X" / "Fig. X" / "图 X" at line start.
        Uses paragraph ending detection (punctuation + short line) to find caption boundaries.
        
        Args:
            page: The PDF page to extract captions from
            
        Returns:
            List of detected figure captions
        """
        return self.extract_figure_captions(page)
    
    def extract_figure_captions(self, page: fitz.Page) -> List[Caption]:
        """Extract only figure captions."""
        return self._extract_captions_by_pattern(
            page, self.FIGURE_PATTERN, CaptionType.FIGURE
        )
    
    def extract_table_captions(self, page: fitz.Page) -> List[Caption]:
        """Extract only table captions."""
        return self._extract_captions_by_pattern(
            page, self.TABLE_PATTERN, CaptionType.TABLE
        )
    
    def extract_all_captions(self, page: fitz.Page) -> Tuple[List[Caption], List[Caption]]:
        """
        Extract both figure and table captions.
        
        Returns:
            Tuple of (figure_captions, table_captions)
        """
        figure_captions = self.extract_figure_captions(page)
        table_captions = self.extract_table_captions(page)
        return figure_captions, table_captions
    
    def _extract_captions_by_pattern(
        self,
        page: fitz.Page,
        pattern: re.Pattern,
        caption_type: CaptionType,
    ) -> List[Caption]:
        """Extract captions matching a specific pattern."""
        captions: List[Caption] = []
        
        text_dict = page.get_text("dict")
        for block in text_dict.get("blocks", []):
            if block.get("type") != 0:  # text block only
                continue
            
            lines = block.get("lines", [])
            if not lines:
                continue
            
            # Check first line of block for caption pattern
            first_line = lines[0]
            spans = first_line.get("spans", [])
            if not spans:
                continue
            
            # Combine text from all spans in the line
            line_text = "".join(span.get("text", "") for span in spans)
            match = pattern.match(line_text)
            
            if match:
                caption = self._extract_caption_from_block(
                    block, lines, match.group(2).strip(), caption_type
                )
                if caption:
                    captions.append(caption)
        
        return captions
    
    def _extract_caption_from_block(
        self,
        block: dict,
        lines: List[dict],
        item_id: str,
        caption_type: CaptionType,
    ) -> Caption:
        """Extract a single caption from a text block."""
        # Get block's right margin (maximum x1 of all lines)
        block_right_margin = max(line["bbox"][2] for line in lines)
        
        # Collect caption lines until we find end of paragraph
        caption_lines = []
        caption_text_parts = []
        avg_line_height = lines[0]["bbox"][3] - lines[0]["bbox"][1]
        
        for i, line in enumerate(lines):
            curr_text = "".join(s.get("text", "") for s in line.get("spans", []))
            
            # Check line spacing (if not first line)
            if i > 0:
                prev_line = lines[i - 1]
                gap = line["bbox"][1] - prev_line["bbox"][3]
                
                # Large gap indicates new paragraph - stop
                if gap > avg_line_height * 0.8:
                    break
            
            caption_lines.append(line)
            caption_text_parts.append(curr_text)
            
            # Check if this line ends the paragraph
            # But don't stop on the first line (e.g., "Figure 2." needs continuation)
            if i > 0 and self._is_line_end_of_paragraph(line, block_right_margin):
                break
        
        # Build bbox from caption lines only
        if caption_lines:
            x0 = min(line["bbox"][0] for line in caption_lines)
            y0 = min(line["bbox"][1] for line in caption_lines)
            x1 = max(line["bbox"][2] for line in caption_lines)
            y1 = max(line["bbox"][3] for line in caption_lines)
            caption_bbox = fitz.Rect(x0, y0, x1, y1)
            
            return Caption(
                bbox=caption_bbox,
                text=" ".join(caption_text_parts).strip(),
                item_id=item_id,
                caption_type=caption_type,
            )
        
        return None
    
    def _is_line_end_of_paragraph(self, line: dict, block_right_margin: float) -> bool:
        """
        Check if a line ends a paragraph by looking for:
        1. Ends with sentence-ending punctuation (. ? ! 。)
        2. The line doesn't extend to the right margin (has whitespace on the right)
        """
        spans = line.get("spans", [])
        if not spans:
            return False
        
        line_text = "".join(s.get("text", "") for s in spans).strip()
        if not line_text:
            return False
        
        # Check if ends with sentence-ending punctuation
        if line_text[-1] not in self.SENTENCE_ENDINGS:
            return False
        
        # Check if line is shorter than the block's right margin (not a full line)
        line_right = line["bbox"][2]
        
        if line_right < block_right_margin - self.margin_threshold:
            return True
        
        return False
