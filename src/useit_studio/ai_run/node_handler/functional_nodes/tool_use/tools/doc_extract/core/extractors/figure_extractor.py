"""
Figure region extraction using caption-anchored detection.

改进：基于字体特征检测正文和标题，避免将它们错误地包含在 Figure 区域中。
"""

import re
from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import fitz  # PyMuPDF

from ..models import Caption, CaptionType, FigureRegion, PageElement
from ..utils import rect_intersection_area, rect_union

# Alias for backward compatibility
FigureCaption = Caption


@dataclass
class FontStats:
    """页面字体统计信息"""
    body_font_size: Optional[float] = None  # 正文字体大小
    body_font_name: Optional[str] = None    # 正文字体名称
    title_font_sizes: List[float] = None    # 标题字体大小列表
    
    def __post_init__(self):
        if self.title_font_sizes is None:
            self.title_font_sizes = []


# 标题模式：匹配各种章节编号格式
# 常见格式：
# - 数字编号：如 "1.", "1.1.", "2.3.1", "1 Introduction"
# - 字母编号：如 "A.", "B.", "C.", "A.1", "A.1.2"（用于附录，必须有点号）
# - 罗马数字：如 "I.", "II.", "III.", "IV."（必须有点号，避免误匹配普通单词）
# - 带括号：如 "(1)", "(a)", "(A)"
# - 特殊关键词：如 "Abstract", "References", "Acknowledgments", "Appendix"
SECTION_TITLE_PATTERN = re.compile(
    r"^\s*("
    r"(\d+\.)+\s*\S|"                    # 1., 1.1., 2.3.1 (带点号)
    r"\d+\s+[A-Z][a-z]|"                 # 1 Introduction (数字+空格+大写开头单词)
    r"[A-Z]\.(\d+\.)*\s*\S|"             # A., A.1., A.1.2. (字母+点号，必须有点)
    r"[IVX]+\.\s*\S|"                    # I., II., III., IV. (罗马数字+点号)
    r"\(\d+\)\s*\S|"                     # (1), (2)
    r"\([a-zA-Z]\)\s*\S|"                # (a), (A)
    r"(Abstract|References|Acknowledgments?|Appendix|Bibliography|Conclusion|Introduction|Related Work|Methods?|Results?|Discussion|Experiments?|Implementation|Evaluation|Background|Preliminaries|Overview|Summary)\s*$"
    r")",
    re.IGNORECASE
)


class FigureExtractor:
    """Extracts figure regions from PDF pages using caption-anchored detection."""
    
    def __init__(
        self,
        header_margin: int = 60,
        merge_threshold: float = 0.1,
        padding: int = 5,
        body_font_size_tolerance: float = 0.5,  # 正文字体大小容差（收紧到 0.5pt）
        min_body_width_ratio: float = 0.5,      # 正文最小宽度比例
    ):
        """
        Initialize the figure extractor.
        
        Args:
            header_margin: Pixels to skip from page top (header area)
            merge_threshold: IoU threshold for merging overlapping regions
            padding: Pixels of padding around figure regions
            body_font_size_tolerance: 正文字体大小容差 (pt)，正文字体大小是固定的，容差应该很小
            min_body_width_ratio: 正文块最小宽度占页面宽度的比例
        """
        self.header_margin = header_margin
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
    ) -> List[FigureRegion]:
        """
        Extract figure regions from a page.
        
        Args:
            page: The PDF page
            captions: List of detected captions on the page (will filter to FIGURE type)
            elements: List of page elements (images, drawings, text)
            page_number: 1-based page number (used to apply first-page specific rules)
            
        Returns:
            List of detected figure regions
        """
        # Filter to only figure captions
        figure_captions = [
            c for c in captions 
            if not hasattr(c, 'caption_type') or c.caption_type == CaptionType.FIGURE
        ]
        
        if not figure_captions:
            return []
        
        # 先识别页面上的"排除区域"（标题、作者、正文、章节标题等）
        # 这些区域内的视觉元素不应该被包含到 figure 中
        # 注意：标题/作者区域的排除规则只适用于第一页
        excluded_regions = self._find_excluded_regions(page, is_first_page=(page_number == 1))
        
        page_regions: List[FigureRegion] = []
        
        for caption in figure_captions:
            other_captions = [c for c in captions if c is not caption]
            figure_bbox = self._find_figure_region_from_caption(
                caption=caption,
                elements=elements,
                page_rect=page.rect,
                page=page,
                other_captions=other_captions,
                excluded_regions=excluded_regions,
            )
            
            # Use item_id (new model) or figure_id (backward compat)
            fig_id = getattr(caption, 'item_id', None) or getattr(caption, 'figure_id', '')
            
            page_regions.append(FigureRegion(
                bbox=figure_bbox,
                caption=caption,
                label=f"figure_{fig_id}",
            ))
        
        # Merge overlapping regions
        return self._merge_overlapping_regions(page_regions)
    
    def _find_excluded_regions(
        self,
        page: fitz.Page,
        is_first_page: bool = False,
    ) -> List[fitz.Rect]:
        """
        识别页面上应该排除的区域（标题、作者、正文、章节标题等）。
        
        这些区域内的视觉元素（如作者信息里的 icon）不应该被包含到 figure 中。
        
        策略：
        1. 识别正文、章节标题等常规排除区域
        2. 仅在第一页：特殊处理页面顶部区域，将标题/作者区域整体排除
           这样可以排除作者信息中的小图标（如机构logo、GitHub链接等）
        
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
            
            # 将整个页面顶部区域（从页面顶部到第一个正文块）作为一个排除区域
            # 这样可以排除作者信息中的所有元素，包括小图标（机构logo、GitHub链接等）
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
        
        正文特征（必须同时满足）：
        1. 字体大小非常接近页面主要字体大小（±1pt）
        2. 宽度足够（>= 页面宽度的 30%）
        3. 有足够的内容（字符数 > 150 或行数 >= 4）
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
        
        # 内容检查（更严格）
        block_text = "".join(
            span.get("text", "")
            for line in lines
            for span in line.get("spans", [])
        )
        
        # 正文通常有较多内容（提高阈值）
        if len(block_text) > 150 or len(lines) >= 4:
            return True
        
        return False
    
    def _get_caption_layout_type(
        self,
        caption: FigureCaption,
        page_rect: fitz.Rect,
    ) -> str:
        """
        根据 caption 的位置判断 figure 的布局类型。
        
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
    
    def _find_figure_region_from_caption(
        self,
        caption: FigureCaption,
        elements: List[PageElement],
        page_rect: fitz.Rect,
        page: fitz.Page,
        other_captions: List[FigureCaption],
        excluded_regions: Optional[List[fitz.Rect]] = None,
    ) -> fitz.Rect:
        """
        From caption's top-left corner, expand upward and rightward to find the figure.
        
        Strategy:
        1. Determine layout type (full_width, left_column, right_column) from caption position
        2. Find upper boundary (page top or previous caption's bottom or body text bottom)
        3. Search within column bounds for image/drawing elements above caption
        4. Exclude elements that fall within excluded regions (title, author, body text, etc.)
        5. For text elements, only include those within figure image bounds
        """
        if excluded_regions is None:
            excluded_regions = []
        
        caption_top = caption.bbox.y0
        caption_left = caption.bbox.x0
        caption_right = caption.bbox.x1
        
        # 判断布局类型，确定水平搜索范围
        layout_type = self._get_caption_layout_type(caption, page_rect)
        horizontal_left, horizontal_right = self._get_horizontal_bounds_by_layout(
            layout_type, page_rect
        )
        
        # Determine initial upper boundary
        initial_upper_boundary = page_rect.y0 + self.header_margin
        
        for other in other_captions:
            if other.bbox.y1 < caption_top and other.bbox.y1 > initial_upper_boundary:
                # 只考虑同一栏内的 caption
                other_layout = self._get_caption_layout_type(other, page_rect)
                if other_layout == layout_type or layout_type == "full_width" or other_layout == "full_width":
                    has_horizontal_overlap = (
                        other.bbox.x0 < caption_right and other.bbox.x1 > caption_left
                    )
                    if has_horizontal_overlap:
                        initial_upper_boundary = other.bbox.y1
        
        # Find where visual elements start (topmost point) - 只在当前栏范围内搜索，排除已归属其他区域的元素
        visual_top = None
        for elem in elements:
            if elem.element_type in ("image", "drawing"):
                # 检查元素是否在当前栏的水平范围内
                if elem.bbox.x1 < horizontal_left or elem.bbox.x0 > horizontal_right:
                    continue
                # 排除落在排除区域内的元素
                if self._is_element_in_excluded_region(elem.bbox, excluded_regions):
                    continue
                if elem.bbox.y1 <= caption_top and elem.bbox.y0 >= initial_upper_boundary - 10:
                    if visual_top is None or elem.bbox.y0 < visual_top:
                        visual_top = elem.bbox.y0
        
        # Check for body text paragraphs above visual elements
        upper_boundary = initial_upper_boundary
        body_text_bottom = self._find_body_text_boundary(
            page, caption_top, caption_left, caption_right, visual_top=visual_top
        )
        if body_text_bottom is not None and body_text_bottom > upper_boundary:
            upper_boundary = body_text_bottom
        
        upper_boundary += 2  # Minimal padding
        
        # First pass: find visual elements (排除已归属其他区域的元素)
        visual_search_region = fitz.Rect(
            horizontal_left,
            upper_boundary,
            horizontal_right,
            caption_top,
        )
        
        visual_elements: List[fitz.Rect] = []
        for elem in elements:
            if elem.element_type not in ("image", "drawing"):
                continue
            # 排除落在排除区域内的元素（如作者信息里的 icon）
            if self._is_element_in_excluded_region(elem.bbox, excluded_regions):
                continue
            if elem.bbox.y1 <= caption_top and elem.bbox.y0 >= upper_boundary - 10:
                inter_area = rect_intersection_area(elem.bbox, visual_search_region)
                if inter_area > 0 and inter_area >= elem.bbox.get_area() * 0.3:
                    visual_elements.append(elem.bbox)
        
        if not visual_elements:
            # 没有找到视觉元素，返回 caption 上方的小区域，不包含 caption
            return fitz.Rect(
                caption_left,
                max(upper_boundary, caption_top - 50),
                caption_right,
                caption_top,  # 不包含 caption
            )
        
        # Determine figure bounds from visual elements
        fig_left = min(rect.x0 for rect in visual_elements)
        fig_right = max(rect.x1 for rect in visual_elements)
        fig_top = min(rect.y0 for rect in visual_elements)
        fig_bottom = max(rect.y1 for rect in visual_elements)  # 视觉元素的底部
        
        # Second pass: include text elements that are part of the figure
        # 判断逻辑：如果文本不是正文也不是标题，就是 figure 的一部分（图片标签、表头等）
        collected: List[fitz.Rect] = list(visual_elements)
        
        text_dict = page.get_text("dict")
        page_width = page.rect.width
        page_center_x = page_rect.x0 + page_width / 2
        font_stats = self._analyze_page_fonts(text_dict, page_width)
        
        for block in text_dict.get("blocks", []):
            if block.get("type") != 0:  # 只处理文本块
                continue
            
            bbox = block["bbox"]
            block_rect = fitz.Rect(bbox)
            
            # 垂直范围：在 upper_boundary 和 caption_top 之间
            if bbox[1] < upper_boundary - 5 or bbox[3] > caption_top:
                continue
            
            # 水平范围：必须在当前栏的范围内（使用 layout 确定的边界）
            if bbox[0] > horizontal_right + 10 or bbox[2] < horizontal_left - 10:
                continue
            
            # 检查文本块是否横跨页面（full_width）
            # 如果 figure 是单栏的，但文本块是横跨的，则排除
            block_spans_center = bbox[0] < page_center_x - 20 and bbox[2] > page_center_x + 20
            if layout_type != "full_width" and block_spans_center:
                # 单栏 figure 上方的横跨文本块（如标题、作者）不应该被包含
                continue
            
            # 获取文本块内容
            block_text = "".join(
                span.get("text", "")
                for line in block.get("lines", [])
                for span in line.get("spans", [])
            )
            
            # 特殊情况：位于视觉元素底部和 caption 之间的文字
            # 这些通常是子图说明，应该被包含进来
            is_between_figure_and_caption = (
                bbox[1] >= fig_bottom - 10  # 在视觉元素底部附近或之下
                and bbox[3] <= caption_top + 5  # 在 caption 之上
            )
            
            # 检查是否是子图标签（以 (a), (b), ✓, ✗ 等开头）
            is_sublabel = self._is_figure_sublabel(block_text)
            
            # 如果位于 figure 和 caption 之间，且是子图标签，直接包含
            if is_between_figure_and_caption and is_sublabel:
                collected.append(block_rect)
                continue
            
            # 判断是否是正文或标题
            is_body_or_title = self._is_body_or_title_block(block, font_stats, page_width)
            
            # 如果不是正文也不是标题，就是 figure 的一部分
            if not is_body_or_title:
                collected.append(block_rect)
        
        # Final bounds
        topmost = min(rect.y0 for rect in collected)
        bottommost = max(rect.y1 for rect in collected)
        rightmost = max(rect.x1 for rect in collected)
        leftmost = min(rect.x0 for rect in collected)
        
        # Build figure region - 只包含视觉元素区域，不包含 caption
        figure_region = fitz.Rect(
            leftmost,
            topmost,
            rightmost,
            bottommost,  # 使用视觉元素的底部
        )
        
        # 确保在页面范围内（不加额外 padding，避免截到周围文字）
        figure_region = fitz.Rect(
            max(page_rect.x0, figure_region.x0),
            max(page_rect.y0, figure_region.y0),
            min(page_rect.x1, figure_region.x1),
            min(page_rect.y1, figure_region.y1),
        )
        
        return figure_region
    
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
    
    def _get_horizontal_bounds(
        self,
        caption: FigureCaption,
        page_rect: fitz.Rect,
        other_captions: List[FigureCaption],
    ) -> tuple:
        """Determine horizontal search bounds based on caption position. (Legacy method)"""
        caption_left = caption.bbox.x0
        caption_right = caption.bbox.x1
        caption_width = caption_right - caption_left
        page_width = page_rect.width
        page_center_x = page_rect.x0 + page_width / 2
        
        # For short captions, extend search range more aggressively
        if caption_width < page_width * 0.4:
            margin = 50
            horizontal_left = page_rect.x0 + margin
            horizontal_right = page_rect.x1 - margin
        else:
            horizontal_left = caption_left - caption_width * 0.3
            horizontal_right = caption_right + caption_width * 0.3
        
        # Check for side-by-side captions
        caption_center_x = (caption_left + caption_right) / 2
        caption_in_left_half = caption_center_x < page_center_x
        
        for other in other_captions:
            other_center_x = (other.bbox.x0 + other.bbox.x1) / 2
            other_in_left_half = other_center_x < page_center_x
            
            if caption_in_left_half != other_in_left_half:
                if caption_in_left_half:
                    horizontal_right = min(horizontal_right, page_center_x - 10)
                else:
                    horizontal_left = max(horizontal_left, page_center_x + 10)
        
        # Ensure within page bounds
        horizontal_left = max(page_rect.x0, horizontal_left)
        horizontal_right = min(page_rect.x1, horizontal_right)
        
        return horizontal_left, horizontal_right
    
    def _find_body_text_boundary(
        self,
        page: fitz.Page,
        caption_top: float,
        caption_left: float,
        caption_right: float,
        visual_top: Optional[float] = None,
    ) -> Optional[float]:
        """
        Find body text or section titles above the caption that should serve as upper boundary.
        
        改进：通过字体特征识别正文和标题
        - 正文：字体大小接近页面主要字体，宽度较大
        - 标题：粗体，以章节编号开头（如 "1.", "3.1."）
        """
        text_dict = page.get_text("dict")
        page_width = page.rect.width
        
        # 分析页面字体，获取正文字体特征
        font_stats = self._analyze_page_fonts(text_dict, page_width)
        
        body_text_bottom = None
        
        for block in text_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            
            bbox = block["bbox"]
            if bbox[3] >= caption_top:
                continue
            
            # Only consider text above visual elements
            if visual_top is not None and bbox[3] > visual_top - 10:
                continue
            
            # 水平范围检查（放宽限制，因为正文可能跨越整个栏宽）
            if bbox[2] < caption_left - 100 or bbox[0] > caption_right + 100:
                continue
            
            lines = block.get("lines", [])
            if not lines:
                continue
            
            # 检查是否是正文或标题
            is_boundary_text = self._is_body_or_title_block(
                block, font_stats, page_width
            )
            
            if is_boundary_text:
                if body_text_bottom is None or bbox[3] > body_text_bottom:
                    body_text_bottom = bbox[3]
        
        return body_text_bottom
    
    def _analyze_page_fonts(self, text_dict: dict, page_width: float) -> FontStats:
        """
        分析页面字体，找出正文和标题的字体特征。
        
        策略：
        - 正文：统计"段落文本块"中最常见的字体大小
          段落文本块的特征：宽度较大、多行、有句子结束符
        - 标题：字体大小比正文大，通常是粗体 (flags 包含 bold)
        """
        font_sizes = []
        font_names = []
        bold_sizes = []  # 粗体字体大小（可能是标题）
        
        for block in text_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            
            bbox = block["bbox"]
            block_width = bbox[2] - bbox[0]
            lines = block.get("lines", [])
            
            # 只统计宽度较大的块（可能是正文）
            if block_width < page_width * 0.3:
                continue
            
            # 获取块的文本内容
            block_text = "".join(
                span.get("text", "")
                for line in lines
                for span in line.get("spans", [])
            )
            
            # 判断是否是"段落文本"：多行、有句子结束符、平均每行字符数较多
            # 这样可以排除 Figure 标签等短文本
            is_paragraph = (
                len(lines) >= 3 and
                any(c in block_text for c in ".?!。？！") and
                len(block_text) / len(lines) > 50 if len(lines) > 0 else False
            )
            
            for line in lines:
                for span in line.get("spans", []):
                    size = span.get("size", 0)
                    font = span.get("font", "")
                    flags = span.get("flags", 0)
                    
                    if size > 0:
                        # 四舍五入到 0.5pt
                        rounded_size = round(size * 2) / 2
                        
                        # 只有段落文本的字体才计入正文字体统计
                        if is_paragraph:
                            font_sizes.append(rounded_size)
                        
                        # 检查是否是粗体 (flags 的第 4 位表示 bold)
                        is_bold = (flags & 16) != 0
                        if is_bold:
                            bold_sizes.append(rounded_size)
                    
                    if font and is_paragraph:
                        font_names.append(font)
        
        stats = FontStats()
        
        if font_sizes:
            size_counter = Counter(font_sizes)
            # 最常见的字体大小作为正文字体
            stats.body_font_size = size_counter.most_common(1)[0][0]
        
        if font_names:
            font_counter = Counter(font_names)
            stats.body_font_name = font_counter.most_common(1)[0][0]
        
        if bold_sizes:
            # 粗体中比正文大的字体大小可能是标题
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
    ) -> bool:
        """
        判断一个文本块是否是正文、标题、文章标题或作者信息（应该排除在 Figure 之外）。
        
        正文特征：
        1. 字体大小接近页面主要字体大小（±tolerance）
        2. 宽度 >= 页面宽度的 min_body_width_ratio
        3. 字符数 > 40 或多行
        
        章节标题特征：
        1. 粗体 (flags & 16)
        2. 以章节编号开头（如 "1.", "3.1."）
        3. 字体大小 >= 正文字体大小
        
        文章标题/作者信息特征：
        1. 字体大小明显大于正文（> body_font_size + 2）
        2. 横跨页面宽度（width_ratio > 0.5）
        3. 位置在页面上部
        """
        lines = block.get("lines", [])
        if not lines:
            return False
        
        bbox = block["bbox"]
        block_width = bbox[2] - bbox[0]
        width_ratio = block_width / page_width
        
        # 获取第一行的文本和字体信息
        first_line = lines[0]
        first_spans = first_line.get("spans", [])
        if not first_spans:
            return False
        
        first_span = first_spans[0]
        first_size = first_span.get("size", 0)
        first_flags = first_span.get("flags", 0)
        is_bold = (first_flags & 16) != 0
        
        # 获取块的完整文本
        block_text = "".join(
            span.get("text", "")
            for line in lines
            for span in line.get("spans", [])
        )
        
        # === 检查是否是 Figure 子图标签 ===
        # 特征：以 "(a)", "(b)", "(1)", "(2)" 等开头
        # 这些是 Figure 的一部分，不应该被排除
        if self._is_figure_sublabel(block_text):
            return False
        
        # === 检查是否是文章标题或作者信息 ===
        # 特征：字体大小明显大于正文，且横跨页面
        if font_stats.body_font_size is not None:
            is_large_font = first_size > font_stats.body_font_size + 1.5
            is_wide = width_ratio >= 0.5
            
            if is_large_font and is_wide:
                # 很可能是文章标题或作者信息
                return True
        
        # === 检查是否是章节标题 ===
        # 章节标题的特征：
        # 1. 通常是粗体
        # 2. 以章节编号开头（数字、字母、罗马数字等）
        # 3. 字体大小 >= 正文字体大小
        # 4. 通常较短（< 200 字符）
        # 5. 单行或很少行
        
        # 检查是否以章节编号开头（不要求粗体，因为有些论文的章节标题不是粗体）
        if SECTION_TITLE_PATTERN.match(block_text):
            # 标题通常较短
            if len(block_text) < 200 and len(lines) <= 3:
                return True
        
        if is_bold:
            # 粗体文本，检查是否是标题
            # 检查字体大小是否是标题字体
            if font_stats.title_font_sizes and first_size in font_stats.title_font_sizes:
                # 标题通常较短
                if len(block_text) < 200:
                    return True
            
            # 粗体 + 字体比正文大 = 很可能是标题
            if font_stats.body_font_size is not None:
                if first_size > font_stats.body_font_size and len(block_text) < 200:
                    return True
        
        # === 检查是否是正文 ===
        # 特殊情况：字符数很少的文本块，即使宽度大也不是正文
        # 这种情况通常是 Figure 的标签（如 "CelebAHQ FFHQ LSUN-Churches..."）
        # 或者是 Figure 的列标签（如 "Samples 256² Guided Convolutional..."）
        # 正文通常有较多字符（每行平均 > 40 个字符）
        avg_chars_per_line = len(block_text) / len(lines) if len(lines) > 0 else 0
        if avg_chars_per_line < 40 and len(block_text) < 100:
            # 短文本，很可能是 Figure 的标签，不是正文
            return False
        
        # 特征1：宽度检查
        is_wide_enough = width_ratio >= self.min_body_width_ratio
        
        # 特征2：字体大小检查（允许有少量上标、下标、引用编号等小字体）
        # 检查大部分 span 的字体大小是否匹配正文字体
        font_size_match = True
        if font_stats.body_font_size is not None:
            matching_spans = 0
            total_spans = 0
            for line in lines:
                for span in line.get("spans", []):
                    span_size = span.get("size", 0)
                    total_spans += 1
                    if abs(span_size - font_stats.body_font_size) <= self.body_font_size_tolerance:
                        matching_spans += 1
            
            # 如果超过 70% 的 span 字体大小匹配，则认为是正文
            if total_spans > 0:
                font_size_match = (matching_spans / total_spans) >= 0.7
        
        # 特征3：内容检查
        char_count = len(block_text)
        has_enough_content = char_count > 40 or len(lines) >= 2
        
        # 综合判断：宽度足够 + 字体匹配 + 有足够内容
        if is_wide_enough and font_size_match and has_enough_content:
            return True
        
        # 备用判断：即使宽度不够，如果字符数很多也认为是正文
        if font_size_match and char_count > 80:
            return True
        
        return False
    
    def _is_figure_sublabel(self, text: str) -> bool:
        """
        判断文本是否是 Figure 的子图标签或说明文字。
        
        子图标签的特征：
        1. 以 "(a)", "(b)", "(1)", "(2)", "(i)", "(ii)" 等开头
        2. 或者以 "a)", "b)", "1)", "2)" 等开头
        3. 或者以 "(a-d)", "(e-f)" 等范围标签开头
        4. 通常是对子图的简短说明
        
        这些文字通常出现在 figure 图片和 caption 之间，是 figure 的一部分。
        """
        text = text.strip()
        if not text:
            return False
        
        # 子图标签模式
        sublabel_patterns = [
            # (a), (b), (c), ..., (z)
            r"^\s*\([a-zA-Z]\)",
            # (1), (2), (3), ...
            r"^\s*\(\d+\)",
            # (i), (ii), (iii), (iv), ...
            r"^\s*\([ivxIVX]+\)",
            # (a-d), (e-f), (1-3), ... 范围标签
            r"^\s*\([a-zA-Z]-[a-zA-Z]\)",
            r"^\s*\(\d+-\d+\)",
            # a), b), c), ... 无左括号
            r"^\s*[a-zA-Z]\)",
            # 1), 2), 3), ... 无左括号
            r"^\s*\d+\)",
            # ✓ 或 ✗ 开头（常见于案例研究）
            r"^\s*[✓✗]",
        ]
        
        for pattern in sublabel_patterns:
            if re.match(pattern, text):
                return True
        
        return False
    
    def _merge_overlapping_regions(
        self,
        regions: List[FigureRegion],
    ) -> List[FigureRegion]:
        """Merge regions that overlap significantly, but only if they belong to the same figure."""
        if not regions:
            return regions
        
        merged: List[FigureRegion] = []
        used = [False] * len(regions)
        
        for i, region in enumerate(regions):
            if used[i]:
                continue
            
            current_bbox = fitz.Rect(region.bbox)
            current_captions = [region.caption]
            cap_id = self._get_caption_id(region.caption)
            base_id = self._get_base_id(cap_id)
            
            changed = True
            while changed:
                changed = False
                for j, other in enumerate(regions):
                    if used[j] or i == j:
                        continue
                    
                    other_cap_id = self._get_caption_id(other.caption)
                    other_base_id = self._get_base_id(other_cap_id)
                    if other_base_id != base_id:
                        continue
                    
                    inter_area = rect_intersection_area(current_bbox, other.bbox)
                    min_area = min(current_bbox.get_area(), other.bbox.get_area())
                    
                    if min_area > 0 and inter_area / min_area >= self.merge_threshold:
                        current_bbox = rect_union(current_bbox, other.bbox)
                        current_captions.append(other.caption)
                        used[j] = True
                        changed = True
            
            first_cap_id = self._get_caption_id(current_captions[0])
            merged.append(FigureRegion(
                bbox=current_bbox,
                caption=current_captions[0],
                label=f"figure_{first_cap_id}",
            ))
            used[i] = True
        
        return merged
    
    @staticmethod
    def _get_caption_id(caption: Caption) -> str:
        """Get the ID from a caption (supports both old and new model)."""
        return getattr(caption, 'item_id', None) or getattr(caption, 'figure_id', '')
    
    @staticmethod
    def _get_base_id(item_id: str) -> str:
        """Extract base number, e.g., '6a' -> '6', '10' -> '10'."""
        match = re.match(r"(\d+)", item_id)
        return match.group(1) if match else item_id
