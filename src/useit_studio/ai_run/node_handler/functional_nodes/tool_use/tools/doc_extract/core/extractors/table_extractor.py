"""
Table region extraction using caption-anchored detection.

Supports both caption positions:
1. Caption ABOVE the table (search downward)
2. Caption BELOW the table (search upward, like Figure)

Detection strategy:
- Try both directions and pick the one with more table-like content
- Table boundaries detected by:
  1. Lines/rectangles (table borders)
  2. Regular text grid patterns
  3. Next caption or body text paragraph
  
改进：
1. 基于字体特征检测正文和标题，避免将它们错误地包含在 Table 区域中
2. 不包含 table caption（与 Figure 保持一致）
3. 支持单栏/双栏布局判断
4. 支持排除区域机制
"""

import re
from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import fitz  # PyMuPDF

from ..models import Caption, CaptionType, PageElement, TableRegion
from ..utils import rect_intersection_area, rect_union


@dataclass
class FontStats:
    """页面字体统计信息"""
    body_font_size: Optional[float] = None
    body_font_name: Optional[str] = None
    title_font_sizes: List[float] = None
    
    def __post_init__(self):
        if self.title_font_sizes is None:
            self.title_font_sizes = []


# 标题模式（与 figure_extractor 保持一致）
SECTION_TITLE_PATTERN = re.compile(
    r"^\s*("
    r"(\d+\.)+\s*\S|"                    # 1., 1.1., 2.3.1
    r"\d+\s+[A-Z][a-z]|"                 # 1 Introduction
    r"[A-Z]\.(\d+\.)*\s*\S|"             # A., A.1., A.1.2.
    r"[IVX]+\.\s*\S|"                    # I., II., III., IV.
    r"\(\d+\)\s*\S|"                     # (1), (2)
    r"\([a-zA-Z]\)\s*\S|"                # (a), (A)
    r"(Abstract|References|Acknowledgments?|Appendix|Bibliography|Conclusion|Introduction|Related Work|Methods?|Results?|Discussion|Experiments?|Implementation|Evaluation|Background|Preliminaries|Overview|Summary)\s*$"
    r")",
    re.IGNORECASE
)


class TableExtractor:
    """Extracts table regions from PDF pages using caption-anchored detection."""
    
    def __init__(
        self,
        header_margin: int = 60,
        footer_margin: int = 60,
        merge_threshold: float = 0.1,
        padding: int = 5,
        body_font_size_tolerance: float = 0.5,
        min_body_width_ratio: float = 0.3,  # Table 场景下降低阈值，因为双栏布局
    ):
        """
        Initialize the table extractor.
        
        Args:
            header_margin: Pixels to skip from page top (header area)
            footer_margin: Pixels to skip from page bottom (footer area)
            merge_threshold: IoU threshold for merging overlapping regions
            padding: Pixels of padding around table regions
            body_font_size_tolerance: 正文字体大小容差 (pt)
            min_body_width_ratio: 正文块最小宽度占页面宽度的比例
        """
        self.header_margin = header_margin
        self.footer_margin = footer_margin
        self.merge_threshold = merge_threshold
        self.padding = padding
        self.body_font_size_tolerance = body_font_size_tolerance
        self.min_body_width_ratio = min_body_width_ratio
    
    def extract(
        self,
        page: fitz.Page,
        captions: List[Caption],
        elements: List[PageElement],
        page_number: int = 1,
    ) -> List[TableRegion]:
        """
        Extract table regions from a page.
        
        Args:
            page: The PDF page
            captions: List of detected table captions on the page
            elements: List of page elements (images, drawings, text)
            page_number: 1-based page number (used to apply first-page specific rules)
            
        Returns:
            List of detected table regions
        """
        # Filter to only table captions
        table_captions = [c for c in captions if c.caption_type == CaptionType.TABLE]
        
        if not table_captions:
            return []
        
        # 识别页面上的"排除区域"（标题、作者、正文、章节标题等）
        excluded_regions = self._find_excluded_regions(page, is_first_page=(page_number == 1))
        
        page_regions: List[TableRegion] = []
        
        for caption in table_captions:
            other_captions = [c for c in captions if c is not caption]
            table_bbox = self._find_table_region_from_caption(
                caption=caption,
                elements=elements,
                page_rect=page.rect,
                page=page,
                other_captions=other_captions,
                excluded_regions=excluded_regions,
            )
            
            page_regions.append(TableRegion(
                bbox=table_bbox,
                caption=caption,
                label=f"table_{caption.item_id}",
            ))
        
        # Merge overlapping regions
        return self._merge_overlapping_regions(page_regions)
    
    def _get_caption_layout_type(
        self,
        caption: Caption,
        page_rect: fitz.Rect,
    ) -> str:
        """
        根据 caption 的位置判断 table 的布局类型。
        
        判断逻辑：
        - 如果 caption 横跨页面中心（左边在左半边，右边在右半边）→ "full_width"（单栏或双栏横跨）
        - 如果 caption 完全在左半边 → "left_column"（双栏左栏）
        - 如果 caption 完全在右半边 → "right_column"（双栏右栏）
        
        Returns:
            "full_width", "left_column", or "right_column"
        """
        page_center_x = page_rect.x0 + page_rect.width / 2
        margin = 20  # 容差
        
        caption_left = caption.bbox.x0
        caption_right = caption.bbox.x1
        
        # 判断 caption 是否横跨页面中心
        spans_center = caption_left < page_center_x - margin and caption_right > page_center_x + margin
        
        if spans_center:
            return "full_width"
        elif caption_right < page_center_x + margin:
            return "left_column"
        else:
            return "right_column"
    
    def _get_horizontal_bounds_by_layout(
        self,
        layout_type: str,
        page_rect: fitz.Rect,
    ) -> Tuple[float, float]:
        """
        根据布局类型确定水平搜索范围。
        
        Args:
            layout_type: "full_width", "left_column", or "right_column"
            page_rect: 页面矩形
            
        Returns:
            (horizontal_left, horizontal_right)
        """
        page_center_x = page_rect.x0 + page_rect.width / 2
        margin = 30  # 页边距
        column_gap = 10  # 栏间距
        
        if layout_type == "full_width":
            # 单栏或双栏横跨：搜索整个页面宽度
            return page_rect.x0 + margin, page_rect.x1 - margin
        elif layout_type == "left_column":
            # 双栏左栏：只搜索左半边
            return page_rect.x0 + margin, page_center_x - column_gap
        else:  # right_column
            # 双栏右栏：只搜索右半边
            return page_center_x + column_gap, page_rect.x1 - margin
    
    def _find_excluded_regions(
        self,
        page: fitz.Page,
        is_first_page: bool = False,
    ) -> List[fitz.Rect]:
        """
        识别页面上应该排除的区域（标题、作者、正文、章节标题等）。
        
        这些区域内的元素不应该被包含到 table 中。
        
        Args:
            page: PDF 页面
            is_first_page: 是否是第一页（第一页有标题和作者信息需要特殊处理）
        
        Returns:
            List of rectangles representing excluded regions
        """
        excluded: List[fitz.Rect] = []
        
        text_dict = page.get_text("dict")
        page_width = page.rect.width
        page_height = page.rect.height
        font_stats = self._analyze_page_fonts(text_dict, page_width)
        
        # 仅在第一页应用标题/作者区域的排除规则
        header_region_bottom = 0
        if is_first_page:
            # 找到第一个正文块的位置（用于确定标题/作者区域的下边界）
            first_body_top = None
            for block in text_dict.get("blocks", []):
                if block.get("type") != 0:
                    continue
                bbox = block["bbox"]
                # 检查是否是正文（字体大小匹配，宽度足够）
                if self._is_body_text_block(block, font_stats, page_width):
                    first_body_top = bbox[1]
                    break
            
            # 如果没有找到正文，使用页面高度的 1/4 作为标题区域
            header_region_bottom = first_body_top if first_body_top else page_height * 0.25
            
            # 将整个页面顶部区域作为一个排除区域
            header_exclusion_zone = fitz.Rect(
                page.rect.x0,
                page.rect.y0,
                page.rect.x1,
                header_region_bottom + 10,
            )
            excluded.append(header_exclusion_zone)
        
        for block in text_dict.get("blocks", []):
            if block.get("type") != 0:  # 只处理文本块
                continue
            
            bbox = block["bbox"]
            
            # 如果是第一页，页面顶部区域已经整体排除，跳过
            if is_first_page and bbox[3] <= header_region_bottom + 10:
                continue
            
            # 判断这个文本块是否是应该排除的类型（正文、章节标题等）
            if self._is_body_or_title_block(block, font_stats, page_width):
                excluded.append(fitz.Rect(bbox))
        
        return excluded
    
    def _is_body_text_block(
        self,
        block: dict,
        font_stats: FontStats,
        page_width: float,
    ) -> bool:
        """
        判断一个文本块是否是正文（用于确定标题区域的下边界）。
        """
        lines = block.get("lines", [])
        if not lines:
            return False
        
        bbox = block["bbox"]
        block_width = bbox[2] - bbox[0]
        width_ratio = block_width / page_width
        
        # 宽度检查
        if width_ratio < 0.3:
            return False
        
        # 字体大小检查（更严格：±1pt）
        if font_stats.body_font_size is not None:
            first_span = lines[0].get("spans", [{}])[0]
            first_size = first_span.get("size", 0)
            if abs(first_size - font_stats.body_font_size) > 1:
                return False
        
        # 内容检查
        block_text = "".join(
            span.get("text", "")
            for line in lines
            for span in line.get("spans", [])
        )
        
        # 正文通常有较多内容
        if len(block_text) > 150 or len(lines) >= 4:
            return True
        
        return False
    
    def _is_element_in_excluded_region(
        self,
        elem_bbox: fitz.Rect,
        excluded_regions: List[fitz.Rect],
    ) -> bool:
        """
        检查一个元素是否落在排除区域内。
        
        如果元素的大部分面积（>50%）在某个排除区域内，则认为它属于该区域。
        """
        elem_area = elem_bbox.get_area()
        if elem_area <= 0:
            return False
        
        for region in excluded_regions:
            inter_area = rect_intersection_area(elem_bbox, region)
            if inter_area > elem_area * 0.5:
                return True
        
        return False
    
    def _find_table_region_from_caption(
        self,
        caption: Caption,
        elements: List[PageElement],
        page_rect: fitz.Rect,
        page: fitz.Page,
        other_captions: List[Caption],
        excluded_regions: Optional[List[fitz.Rect]] = None,
    ) -> fitz.Rect:
        """
        Find table region by trying both directions:
        1. Search BELOW caption (caption at top)
        2. Search ABOVE caption (caption at bottom, like Figure)
        
        Pick the direction with more table-like content.
        不包含 caption 本身。
        """
        if excluded_regions is None:
            excluded_regions = []
        
        # 判断布局类型
        layout_type = self._get_caption_layout_type(caption, page_rect)
        horizontal_left, horizontal_right = self._get_horizontal_bounds_by_layout(
            layout_type, page_rect
        )
        
        # Try searching below (caption at top)
        region_below, score_below = self._search_below_caption(
            caption, page_rect, page, other_captions, layout_type,
            horizontal_left, horizontal_right, excluded_regions
        )
        
        # Try searching above (caption at bottom)
        region_above, score_above = self._search_above_caption(
            caption, elements, page_rect, page, other_captions, layout_type,
            horizontal_left, horizontal_right, excluded_regions
        )
        
        # Pick the better result
        if score_above > score_below:
            return region_above
        else:
            return region_below
    
    def _search_below_caption(
        self,
        caption: Caption,
        page_rect: fitz.Rect,
        page: fitz.Page,
        other_captions: List[Caption],
        layout_type: str,
        horizontal_left: float,
        horizontal_right: float,
        excluded_regions: List[fitz.Rect],
    ) -> Tuple[fitz.Rect, float]:
        """
        Search BELOW the caption for table content.
        Returns (region, score) where score indicates confidence.
        不包含 caption 本身。
        """
        caption_bottom = caption.bbox.y1
        caption_left = caption.bbox.x0
        caption_right = caption.bbox.x1
        
        # Determine lower boundary
        lower_boundary = page_rect.y1 - self.footer_margin
        
        # Check for other captions below (只考虑同一栏内的 caption)
        for other in other_captions:
            if other.bbox.y0 > caption_bottom and other.bbox.y0 < lower_boundary:
                other_layout = self._get_caption_layout_type(other, page_rect)
                if other_layout == layout_type or layout_type == "full_width" or other_layout == "full_width":
                    has_horizontal_overlap = (
                        other.bbox.x0 < caption_right + 50 and other.bbox.x1 > caption_left - 50
                    )
                    if has_horizontal_overlap:
                        lower_boundary = other.bbox.y0
        
        # 分析页面字体
        text_dict = page.get_text("dict")
        page_width = page_rect.width
        font_stats = self._analyze_page_fonts(text_dict, page_width)
        
        # Check for body text below
        body_text_top = self._find_body_text_boundary_filtered(
            page, caption_bottom, lower_boundary, caption_left, caption_right,
            direction="below", font_stats=font_stats, excluded_regions=excluded_regions
        )
        if body_text_top is not None and body_text_top < lower_boundary:
            lower_boundary = body_text_top
        
        lower_boundary -= 2
        
        # Search region (使用基于布局的水平边界)
        search_region = fitz.Rect(
            horizontal_left,
            caption_bottom,
            horizontal_right,
            lower_boundary,
        )
        
        # Find table elements (排除正文和标题)
        table_elements, line_count = self._find_table_elements_in_region_filtered(
            page, search_region, caption_bottom, lower_boundary, font_stats, excluded_regions
        )
        
        if not table_elements:
            # No content found below - 返回 caption 下方的小区域，不包含 caption
            fallback_region = fitz.Rect(
                caption_left,
                caption_bottom,  # 从 caption 底部开始，不包含 caption
                caption_right,
                min(lower_boundary, caption_bottom + 50),
            )
            return fallback_region, 0.0
        
        # Calculate bounds
        table_left = min(rect.x0 for rect in table_elements)
        table_right = max(rect.x1 for rect in table_elements)
        table_top = min(rect.y0 for rect in table_elements)
        table_bottom = max(rect.y1 for rect in table_elements)
        
        # Score based on: element count, line count, region size
        content_height = table_bottom - caption_bottom
        score = len(table_elements) * 0.5 + line_count * 2.0 + content_height * 0.01
        
        # Build region - 不包含 caption
        # 注意：top 方向不能低于 caption_bottom，否则会截到 caption
        table_region = fitz.Rect(
            min(table_left, caption_left),
            max(table_top, caption_bottom + 2),  # 确保不低于 caption 底部
            max(table_right, caption_right),
            table_bottom,
        )
        
        # Add padding，但 top 方向要限制不低于 caption_bottom
        table_region = self._apply_padding_with_limit(
            table_region, page_rect, min_top=caption_bottom + 2
        )
        
        return table_region, score
    
    def _search_above_caption(
        self,
        caption: Caption,
        elements: List[PageElement],
        page_rect: fitz.Rect,
        page: fitz.Page,
        other_captions: List[Caption],
        layout_type: str,
        horizontal_left: float,
        horizontal_right: float,
        excluded_regions: List[fitz.Rect],
    ) -> Tuple[fitz.Rect, float]:
        """
        Search ABOVE the caption for table content (like Figure extraction).
        Returns (region, score) where score indicates confidence.
        
        改进：
        1. 排除正文、标题和 Figure caption
        2. 使用布局类型判断
        3. 使用排除区域
        4. 不包含 caption 本身
        """
        caption_top = caption.bbox.y0
        caption_left = caption.bbox.x0
        caption_right = caption.bbox.x1
        
        # Determine upper boundary
        upper_boundary = page_rect.y0 + self.header_margin
        
        # Check for other captions above (只考虑同一栏内的 caption)
        for other in other_captions:
            if other.bbox.y1 < caption_top and other.bbox.y1 > upper_boundary:
                other_layout = self._get_caption_layout_type(other, page_rect)
                if other_layout == layout_type or layout_type == "full_width" or other_layout == "full_width":
                    has_horizontal_overlap = (
                        other.bbox.x0 < caption_right and other.bbox.x1 > caption_left
                    )
                    if has_horizontal_overlap:
                        upper_boundary = other.bbox.y1
        
        # 分析页面字体
        text_dict = page.get_text("dict")
        page_width = page_rect.width
        page_center_x = page_rect.x0 + page_width / 2
        font_stats = self._analyze_page_fonts(text_dict, page_width)
        
        # 关键改进：找到上方最近的 Figure caption 或段落文本作为边界
        # 注意：这里只排除真正的段落文本（有完整句子的连续文本），不排除表格行
        for block in text_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            
            bbox = block["bbox"]
            # 只考虑在 caption 上方、当前 upper_boundary 下方的文本块
            if bbox[3] >= caption_top or bbox[3] <= upper_boundary:
                continue
            
            # 检查是否在同一栏（使用布局类型判断）
            block_center_x = (bbox[0] + bbox[2]) / 2
            in_same_column = True
            if layout_type == "left_column" and block_center_x > page_center_x:
                in_same_column = False
            elif layout_type == "right_column" and block_center_x < page_center_x:
                in_same_column = False
            
            if not in_same_column:
                continue
            
            block_text = "".join(
                span.get("text", "")
                for line in block.get("lines", [])
                for span in line.get("spans", [])
            )
            
            # 如果是 Figure caption，以它的底部作为新的上边界
            if self._is_figure_caption(block_text):
                if bbox[3] > upper_boundary:
                    upper_boundary = bbox[3]
                continue
            
            # 只排除真正的段落文本（有完整句子的连续文本），不排除表格行
            # 使用更严格的判断：必须是多行、有句子结束符、平均每行字符数较多
            if self._is_paragraph_text_block(block):
                if bbox[3] > upper_boundary:
                    upper_boundary = bbox[3]
        
        upper_boundary += 2
        
        # Search region (使用基于布局的水平边界)
        search_region = fitz.Rect(
            horizontal_left,
            upper_boundary,
            horizontal_right,
            caption_top,
        )
        
        # Find table elements (排除正文和标题)
        table_elements, line_count = self._find_table_elements_in_region_filtered(
            page, search_region, upper_boundary, caption_top, font_stats, excluded_regions
        )
        
        if not table_elements:
            # No content found above - 返回 caption 上方的小区域，不包含 caption
            fallback_region = fitz.Rect(
                caption_left,
                max(upper_boundary, caption_top - 50),
                caption_right,
                caption_top,  # 不包含 caption
            )
            return fallback_region, 0.0
        
        # Calculate bounds
        table_left = min(rect.x0 for rect in table_elements)
        table_right = max(rect.x1 for rect in table_elements)
        table_top = min(rect.y0 for rect in table_elements)
        table_bottom = max(rect.y1 for rect in table_elements)
        
        # Score based on: element count, line count, region size
        content_height = caption_top - table_top
        score = len(table_elements) * 0.5 + line_count * 2.0 + content_height * 0.01
        
        # Build region - 不包含 caption
        # 注意：bottom 方向不能超过 caption_top，否则会截到 caption
        table_region = fitz.Rect(
            min(table_left, caption_left),
            table_top,
            max(table_right, caption_right),
            min(table_bottom, caption_top - 2),  # 确保不超过 caption 顶部
        )
        
        # Add padding，但 bottom 方向要限制不超过 caption_top
        table_region = self._apply_padding_with_limit(
            table_region, page_rect, max_bottom=caption_top - 2
        )
        
        return table_region, score
    
    def _find_table_elements_in_region(
        self,
        page: fitz.Page,
        search_region: fitz.Rect,
        y_min: float,
        y_max: float,
    ) -> Tuple[List[fitz.Rect], int]:
        """
        Find table-like elements within a search region.
        Returns (elements, line_count) where line_count indicates table lines.
        """
        table_elements: List[fitz.Rect] = []
        line_count = 0
        
        # Collect lines/rectangles (table borders)
        for drawing in page.get_drawings():
            rect = fitz.Rect(drawing["rect"])
            
            # Skip truly empty rects, but allow lines (width or height can be 0)
            if rect.width <= 0 and rect.height <= 0:
                continue
            
            # Check if drawing is within vertical bounds
            if rect.y0 >= y_min - 5 and rect.y1 <= y_max + 5:
                # Check horizontal overlap with search region
                if rect.x1 < search_region.x0 or rect.x0 > search_region.x1:
                    continue
                
                # Detect horizontal lines (important for tables!)
                width = rect.width
                height = rect.height
                
                if width > 20 and height < 3:  # Horizontal line
                    line_count += 1
                    # Expand the line rect slightly so it has area for merging
                    expanded_rect = fitz.Rect(rect.x0, rect.y0 - 2, rect.x1, rect.y1 + 2)
                    table_elements.append(expanded_rect)
                elif height > 20 and width < 3:  # Vertical line
                    line_count += 1
                    expanded_rect = fitz.Rect(rect.x0 - 2, rect.y0, rect.x1 + 2, rect.y1)
                    table_elements.append(expanded_rect)
                elif rect.get_area() > 10:  # Other shapes with area
                    table_elements.append(rect)
        
        # Collect text blocks within search region (table cells)
        text_dict = page.get_text("dict")
        for block in text_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            
            bbox = fitz.Rect(block["bbox"])
            if bbox.y0 >= y_min - 5 and bbox.y1 <= y_max + 5:
                inter_area = rect_intersection_area(bbox, search_region)
                if inter_area > 0 and inter_area >= bbox.get_area() * 0.3:
                    table_elements.append(bbox)
        
        return table_elements, line_count
    
    def _find_table_elements_in_region_filtered(
        self,
        page: fitz.Page,
        search_region: fitz.Rect,
        y_min: float,
        y_max: float,
        font_stats: FontStats,
        excluded_regions: Optional[List[fitz.Rect]] = None,
    ) -> Tuple[List[fitz.Rect], int]:
        """
        Find table-like elements within a search region, excluding body text and titles.
        改进版本：排除正文、标题和排除区域内的元素。
        """
        if excluded_regions is None:
            excluded_regions = []
        
        table_elements: List[fitz.Rect] = []
        line_count = 0
        page_width = page.rect.width
        
        # Collect lines/rectangles (table borders)
        for drawing in page.get_drawings():
            rect = fitz.Rect(drawing["rect"])
            
            if rect.width <= 0 and rect.height <= 0:
                continue
            
            if rect.y0 >= y_min - 5 and rect.y1 <= y_max + 5:
                if rect.x1 < search_region.x0 or rect.x0 > search_region.x1:
                    continue
                
                # 排除落在排除区域内的元素
                if self._is_element_in_excluded_region(rect, excluded_regions):
                    continue
                
                width = rect.width
                height = rect.height
                
                if width > 20 and height < 3:
                    line_count += 1
                    expanded_rect = fitz.Rect(rect.x0, rect.y0 - 2, rect.x1, rect.y1 + 2)
                    table_elements.append(expanded_rect)
                elif height > 20 and width < 3:
                    line_count += 1
                    expanded_rect = fitz.Rect(rect.x0 - 2, rect.y0, rect.x1 + 2, rect.y1)
                    table_elements.append(expanded_rect)
                elif rect.get_area() > 10:
                    table_elements.append(rect)
        
        # Collect text blocks within search region
        # 注意：对于 Table 提取，我们只排除明显的段落文本和 Figure caption
        # 不要用 _is_body_or_title_block，因为它会把表格行也排除掉
        text_dict = page.get_text("dict")
        for block in text_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            
            bbox = fitz.Rect(block["bbox"])
            if bbox.y0 >= y_min - 5 and bbox.y1 <= y_max + 5:
                inter_area = rect_intersection_area(bbox, search_region)
                if inter_area > 0 and inter_area >= bbox.get_area() * 0.3:
                    # 排除落在排除区域内的元素
                    if self._is_element_in_excluded_region(bbox, excluded_regions):
                        continue
                    
                    block_text = "".join(
                        span.get("text", "")
                        for line in block.get("lines", [])
                        for span in line.get("spans", [])
                    )
                    
                    # 排除 Figure caption
                    if self._is_figure_caption(block_text):
                        continue
                    
                    # 排除明显的段落文本（有完整句子的连续文本）
                    if self._is_paragraph_text_block(block):
                        continue
                    
                    table_elements.append(bbox)
        
        return table_elements, line_count
    
    def _find_body_text_boundary_filtered(
        self,
        page: fitz.Page,
        y_start: float,
        y_end: float,
        caption_left: float,
        caption_right: float,
        direction: str = "below",
        font_stats: Optional[FontStats] = None,
        excluded_regions: Optional[List[fitz.Rect]] = None,
    ) -> Optional[float]:
        """
        Find body text paragraphs that should serve as boundary.
        改进版本：使用字体分析和排除区域。
        """
        if excluded_regions is None:
            excluded_regions = []
        
        text_dict = page.get_text("dict")
        page_width = page.rect.width
        
        if font_stats is None:
            font_stats = self._analyze_page_fonts(text_dict, page_width)
        
        boundary = None
        caption_width = caption_right - caption_left
        
        for block in text_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            
            bbox = block["bbox"]
            block_rect = fitz.Rect(bbox)
            
            if direction == "below":
                if bbox[1] <= y_start or bbox[1] >= y_end:
                    continue
            else:  # above
                if bbox[3] >= y_end or bbox[3] <= y_start:
                    continue
            
            # 排除落在排除区域内的元素
            if self._is_element_in_excluded_region(block_rect, excluded_regions):
                continue
            
            # Horizontal overlap check
            block_left = bbox[0]
            block_right = bbox[2]
            block_center_x = (block_left + block_right) / 2
            
            overlap_left = max(caption_left, block_left)
            overlap_right = min(caption_right, block_right)
            overlap_width = max(0, overlap_right - overlap_left)
            
            min_overlap = caption_width * 0.3
            center_in_range = caption_left - 20 <= block_center_x <= caption_right + 20
            
            if overlap_width < min_overlap and not center_in_range:
                continue
            
            # 使用字体分析判断是否是正文或标题
            if self._is_body_or_title_block(block, font_stats, page_width):
                if direction == "below":
                    if boundary is None or bbox[1] < boundary:
                        boundary = bbox[1]
                else:
                    if boundary is None or bbox[3] > boundary:
                        boundary = bbox[3]
        
        return boundary
    
    
    def _apply_padding(self, region: fitz.Rect, page_rect: fitz.Rect) -> fitz.Rect:
        """Apply padding to a region while staying within page bounds."""
        return fitz.Rect(
            max(page_rect.x0, region.x0 - self.padding),
            max(page_rect.y0, region.y0 - self.padding),
            min(page_rect.x1, region.x1 + self.padding),
            min(page_rect.y1, region.y1 + self.padding),
        )
    
    def _apply_padding_with_limit(
        self,
        region: fitz.Rect,
        page_rect: fitz.Rect,
        min_top: Optional[float] = None,
        max_bottom: Optional[float] = None,
    ) -> fitz.Rect:
        """
        Apply padding to a region with additional limits to avoid overlapping with caption.
        
        Args:
            region: The region to pad
            page_rect: Page bounds
            min_top: Minimum y0 value (to avoid overlapping with caption above)
            max_bottom: Maximum y1 value (to avoid overlapping with caption below)
        """
        new_x0 = max(page_rect.x0, region.x0 - self.padding)
        new_y0 = max(page_rect.y0, region.y0 - self.padding)
        new_x1 = min(page_rect.x1, region.x1 + self.padding)
        new_y1 = min(page_rect.y1, region.y1 + self.padding)
        
        # Apply additional limits
        if min_top is not None:
            new_y0 = max(new_y0, min_top)
        if max_bottom is not None:
            new_y1 = min(new_y1, max_bottom)
        
        return fitz.Rect(new_x0, new_y0, new_x1, new_y1)
    
    def _merge_overlapping_regions(
        self,
        regions: List[TableRegion],
    ) -> List[TableRegion]:
        """Merge regions that overlap significantly, but only if they belong to the same table."""
        if not regions:
            return regions
        
        merged: List[TableRegion] = []
        used = [False] * len(regions)
        
        for i, region in enumerate(regions):
            if used[i]:
                continue
            
            current_bbox = fitz.Rect(region.bbox)
            current_captions = [region.caption]
            base_id = self._get_base_table_id(region.caption.item_id)
            
            changed = True
            while changed:
                changed = False
                for j, other in enumerate(regions):
                    if used[j] or i == j:
                        continue
                    
                    other_base_id = self._get_base_table_id(other.caption.item_id)
                    if other_base_id != base_id:
                        continue
                    
                    inter_area = rect_intersection_area(current_bbox, other.bbox)
                    min_area = min(current_bbox.get_area(), other.bbox.get_area())
                    
                    if min_area > 0 and inter_area / min_area >= self.merge_threshold:
                        current_bbox = rect_union(current_bbox, other.bbox)
                        current_captions.append(other.caption)
                        used[j] = True
                        changed = True
            
            merged.append(TableRegion(
                bbox=current_bbox,
                caption=current_captions[0],
                label=f"table_{current_captions[0].item_id}",
            ))
            used[i] = True
        
        return merged
    
    @staticmethod
    def _get_base_table_id(table_id: str) -> str:
        """Extract base table number, e.g., '2a' -> '2', '10' -> '10'."""
        match = re.match(r"(\d+)", table_id)
        return match.group(1) if match else table_id
    
    def _analyze_page_fonts(self, text_dict: dict, page_width: float) -> FontStats:
        """分析页面字体，找出正文和标题的字体特征。"""
        font_sizes = []
        font_names = []
        bold_sizes = []
        
        for block in text_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            
            bbox = block["bbox"]
            block_width = bbox[2] - bbox[0]
            
            if block_width < page_width * 0.3:
                continue
            
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    size = span.get("size", 0)
                    font = span.get("font", "")
                    flags = span.get("flags", 0)
                    
                    if size > 0:
                        rounded_size = round(size * 2) / 2
                        font_sizes.append(rounded_size)
                        
                        is_bold = (flags & 16) != 0
                        if is_bold:
                            bold_sizes.append(rounded_size)
                    
                    if font:
                        font_names.append(font)
        
        stats = FontStats()
        
        if font_sizes:
            size_counter = Counter(font_sizes)
            stats.body_font_size = size_counter.most_common(1)[0][0]
        
        if font_names:
            font_counter = Counter(font_names)
            stats.body_font_name = font_counter.most_common(1)[0][0]
        
        if bold_sizes:
            bold_counter = Counter(bold_sizes)
            for size, _ in bold_counter.most_common(5):
                if stats.body_font_size is None or size >= stats.body_font_size:
                    stats.title_font_sizes.append(size)
        
        return stats
    
    def _is_body_or_title_block(
        self,
        block: dict,
        font_stats: FontStats,
        page_width: float,
        body_font_size_tolerance: float = 0.5,
    ) -> bool:
        """
        判断一个文本块是否是正文或标题（应该排除在 Table 之外）。
        与 figure_extractor 保持一致的逻辑。
        """
        lines = block.get("lines", [])
        if not lines:
            return False
        
        bbox = block["bbox"]
        block_width = bbox[2] - bbox[0]
        width_ratio = block_width / page_width
        
        first_line = lines[0]
        first_spans = first_line.get("spans", [])
        if not first_spans:
            return False
        
        first_span = first_spans[0]
        first_size = first_span.get("size", 0)
        first_flags = first_span.get("flags", 0)
        is_bold = (first_flags & 16) != 0
        
        block_text = "".join(
            span.get("text", "")
            for line in lines
            for span in line.get("spans", [])
        )
        
        # === 检查是否是文章标题或作者信息 ===
        if font_stats.body_font_size is not None:
            is_large_font = first_size > font_stats.body_font_size + 1.5
            is_wide = width_ratio >= 0.5
            
            if is_large_font and is_wide:
                return True
        
        # === 检查是否是章节标题 ===
        if SECTION_TITLE_PATTERN.match(block_text):
            if len(block_text) < 200 and len(lines) <= 3:
                return True
        
        if is_bold:
            if font_stats.title_font_sizes and first_size in font_stats.title_font_sizes:
                if len(block_text) < 200:
                    return True
            
            if font_stats.body_font_size is not None:
                if first_size > font_stats.body_font_size and len(block_text) < 200:
                    return True
        
        # === 检查是否是正文 ===
        # 短文本（标签）不是正文
        avg_chars_per_line = len(block_text) / len(lines) if len(lines) > 0 else 0
        if avg_chars_per_line < 40 and len(block_text) < 100:
            return False
        
        # 宽度检查
        is_wide_enough = width_ratio >= 0.3  # Table 场景下降低阈值，因为双栏布局
        
        # 字体大小检查
        font_size_match = True
        if font_stats.body_font_size is not None:
            matching_spans = 0
            total_spans = 0
            for line in lines:
                for span in line.get("spans", []):
                    span_size = span.get("size", 0)
                    total_spans += 1
                    if abs(span_size - font_stats.body_font_size) <= body_font_size_tolerance:
                        matching_spans += 1
            
            if total_spans > 0:
                font_size_match = (matching_spans / total_spans) >= 0.7
        
        # 内容检查
        char_count = len(block_text)
        has_enough_content = char_count > 40 or len(lines) >= 2
        
        if is_wide_enough and font_size_match and has_enough_content:
            return True
        
        if font_size_match and char_count > 80:
            return True
        
        return False
    
    def _is_figure_caption(self, block_text: str) -> bool:
        """检查文本是否是 Figure caption。"""
        return bool(re.match(r"^\s*(Figure|Fig\.?)\s+\d+", block_text, re.IGNORECASE))
    
    def _is_paragraph_text_block(self, block: dict) -> bool:
        """
        判断一个文本块是否是段落文本（应该作为 Table 的上边界）。
        
        与 _is_body_or_title_block 不同，这个方法更严格：
        - 必须有多行连续文本
        - 必须有句子结束符（. ? !）
        - 平均每行字符数较多（>50）
        
        这样可以避免把表格行误判为段落文本。
        """
        lines = block.get("lines", [])
        if not lines:
            return False
        
        # 获取完整文本
        block_text = "".join(
            span.get("text", "")
            for line in lines
            for span in line.get("spans", [])
        )
        
        # 检查是否是章节标题
        if SECTION_TITLE_PATTERN.match(block_text):
            if len(block_text) < 200 and len(lines) <= 3:
                return True
        
        # 段落文本的特征：
        # 1. 多行（>=3行）
        # 2. 有句子结束符
        # 3. 平均每行字符数较多（>50）
        # 4. 总字符数较多（>200）
        
        has_sentence_ending = any(c in block_text for c in ".?!。？！")
        avg_chars_per_line = len(block_text) / len(lines) if len(lines) > 0 else 0
        
        # 严格的段落判断
        if len(lines) >= 3 and has_sentence_ending and avg_chars_per_line > 50 and len(block_text) > 200:
            return True
        
        # 较宽松的判断：如果有很多文本且有句子结束符
        if len(block_text) > 300 and has_sentence_ending and avg_chars_per_line > 40:
            return True
        
        return False