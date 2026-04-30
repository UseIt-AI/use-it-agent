"""
Main pipeline for PDF to Markdown conversion.
"""

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, List, Optional

import fitz  # PyMuPDF

from .extractors import CaptionExtractor, ElementExtractor, FigureExtractor, TableExtractor
from .models import DocumentResult, FigureRegion, PageResult, TableRegion
from .utils import ensure_dir, render_region, sanitize_filename, save_pixmap


class PipelineStage(Enum):
    """Stages of the PDF processing pipeline."""
    INIT = "init"
    OPEN_DOCUMENT = "open_document"
    PROCESS_PAGE = "process_page"
    EXTRACT_CAPTIONS = "extract_captions"
    EXTRACT_ELEMENTS = "extract_elements"
    FIND_FIGURES = "find_figures"
    FIND_TABLES = "find_tables"
    RENDER_FIGURES = "render_figures"
    RENDER_TABLES = "render_tables"
    GENERATE_MARKDOWN = "generate_markdown"
    COMPLETE = "complete"


@dataclass
class PipelineProgress:
    """Progress information for the pipeline."""
    stage: PipelineStage
    current_page: int = 0
    total_pages: int = 0
    current_figure: int = 0
    total_figures: int = 0
    current_table: int = 0
    total_tables: int = 0
    message: str = ""
    
    @property
    def percentage(self) -> float:
        """Calculate overall progress percentage."""
        if self.stage == PipelineStage.INIT:
            return 0.0
        elif self.stage == PipelineStage.OPEN_DOCUMENT:
            return 5.0
        elif self.stage in (
            PipelineStage.PROCESS_PAGE,
            PipelineStage.EXTRACT_CAPTIONS,
            PipelineStage.EXTRACT_ELEMENTS,
            PipelineStage.FIND_FIGURES,
            PipelineStage.FIND_TABLES,
        ):
            if self.total_pages > 0:
                page_progress = self.current_page / self.total_pages
                return 5.0 + page_progress * 60.0  # 5% to 65%
            return 5.0
        elif self.stage == PipelineStage.RENDER_FIGURES:
            if self.total_figures > 0:
                figure_progress = self.current_figure / self.total_figures
                return 65.0 + figure_progress * 15.0  # 65% to 80%
            return 65.0
        elif self.stage == PipelineStage.RENDER_TABLES:
            if self.total_tables > 0:
                table_progress = self.current_table / self.total_tables
                return 80.0 + table_progress * 15.0  # 80% to 95%
            return 80.0
        elif self.stage == PipelineStage.GENERATE_MARKDOWN:
            return 95.0
        elif self.stage == PipelineStage.COMPLETE:
            return 100.0
        return 0.0


@dataclass
class PipelineConfig:
    """Configuration for the PDF processing pipeline."""
    output_dir: Path = field(default_factory=lambda: Path("docling_output"))
    dpi: int = 300  # 300 DPI for high quality PPT display
    image_format: str = "png"  # "png" or "svg"
    max_pages: Optional[int] = None
    extract_tables: bool = True  # Whether to extract tables
    
    # Extractor settings
    caption_margin_threshold: int = 20
    min_drawing_area: float = 100
    max_text_chars: int = 100
    max_text_lines: int = 2
    header_margin: int = 60
    footer_margin: int = 60
    merge_threshold: float = 0.1
    figure_padding: int = 5
    table_padding: int = 5
    
    # S3 上传配置
    project_id: Optional[str] = None  # 项目 ID，用于 S3 上传
    chat_id: Optional[str] = None  # 会话 ID，用于 S3 上传
    enable_s3_upload: bool = True  # 是否启用 S3 上传


# Type alias for progress callback
ProgressCallback = Callable[[PipelineProgress], None]


class PDFPipeline:
    """
    Main pipeline for processing PDF documents.
    
    Provides a modular, stage-based approach to PDF processing with
    progress reporting for UI integration.
    """
    
    def __init__(
        self,
        config: Optional[PipelineConfig] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ):
        """
        Initialize the pipeline.
        
        Args:
            config: Pipeline configuration
            progress_callback: Optional callback for progress updates
        """
        self.config = config or PipelineConfig()
        self.progress_callback = progress_callback
        
        # Initialize extractors
        self.caption_extractor = CaptionExtractor(
            margin_threshold=self.config.caption_margin_threshold
        )
        self.element_extractor = ElementExtractor(
            min_drawing_area=self.config.min_drawing_area,
            max_text_chars=self.config.max_text_chars,
            max_text_lines=self.config.max_text_lines,
        )
        self.figure_extractor = FigureExtractor(
            header_margin=self.config.header_margin,
            merge_threshold=self.config.merge_threshold,
            padding=self.config.figure_padding,
        )
        self.table_extractor = TableExtractor(
            header_margin=self.config.header_margin,
            footer_margin=self.config.footer_margin,
            merge_threshold=self.config.merge_threshold,
            padding=self.config.table_padding,
        )
    
    def _report_progress(self, progress: PipelineProgress) -> None:
        """Report progress to the callback if set."""
        if self.progress_callback:
            self.progress_callback(progress)
    
    def process(self, pdf_path: Path) -> DocumentResult:
        """
        Process a PDF document.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            DocumentResult with processing results
        """
        # Stage: Init
        self._report_progress(PipelineProgress(
            stage=PipelineStage.INIT,
            message=f"Starting processing: {pdf_path.name}"
        ))
        
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        
        # Stage: Open document
        self._report_progress(PipelineProgress(
            stage=PipelineStage.OPEN_DOCUMENT,
            message="Opening PDF document..."
        ))
        
        doc = fitz.open(pdf_path)
        base_name = sanitize_filename(pdf_path.stem)
        
        # Setup output directories
        output_dir = self.config.output_dir
        if not output_dir.is_absolute():
            output_dir = Path(os.getcwd()) / output_dir
        
        base_output_dir = output_dir / base_name
        text_out_path = base_output_dir / f"{base_name}.md"
        figures_dir = base_output_dir / "figures"
        
        ensure_dir(base_output_dir)
        ensure_dir(figures_dir)
        
        # Process pages
        total_pages = doc.page_count
        if self.config.max_pages is not None:
            total_pages = min(total_pages, self.config.max_pages)
        
        page_results: List[PageResult] = []
        all_figure_regions: List[FigureRegion] = []
        all_table_regions: List[TableRegion] = []
        
        for page_index in range(total_pages):
            page_result = self._process_page(
                doc=doc,
                page_index=page_index,
                total_pages=total_pages,
            )
            page_results.append(page_result)
            all_figure_regions.extend(page_result.figures)
            all_table_regions.extend(page_result.tables)
        
        # Create tables directory if needed
        tables_dir = base_output_dir / "tables"
        if all_table_regions:
            ensure_dir(tables_dir)
        
        # Stage: Render figures
        self._report_progress(PipelineProgress(
            stage=PipelineStage.RENDER_FIGURES,
            total_figures=len(all_figure_regions),
            message=f"Rendering {len(all_figure_regions)} figures..."
        ))
        
        used_figure_ids: dict[str, int] = {}
        
        for i, region in enumerate(all_figure_regions):
            self._report_progress(PipelineProgress(
                stage=PipelineStage.RENDER_FIGURES,
                current_figure=i + 1,
                total_figures=len(all_figure_regions),
                message=f"Rendering figure {i + 1}/{len(all_figure_regions)}..."
            ))
            
            # Generate unique label
            base_id = self._get_caption_id(region.caption)
            if base_id not in used_figure_ids:
                used_figure_ids[base_id] = 1
                unique_label = f"figure_{base_id}"
            else:
                used_figure_ids[base_id] += 1
                unique_label = f"figure_{base_id}_v{used_figure_ids[base_id]}"
            
            region.label = unique_label
            
            # Render and save
            page = doc.load_page(region.page_number - 1)
            output_path = figures_dir / f"{unique_label}.{self.config.image_format}"
            pixmap = render_region(page, region.bbox, self.config.dpi)
            save_pixmap(pixmap, output_path, self.config.image_format)
        
        # Stage: Render tables
        if all_table_regions:
            self._report_progress(PipelineProgress(
                stage=PipelineStage.RENDER_TABLES,
                total_tables=len(all_table_regions),
                message=f"Rendering {len(all_table_regions)} tables..."
            ))
            
            used_table_ids: dict[str, int] = {}
            
            for i, region in enumerate(all_table_regions):
                self._report_progress(PipelineProgress(
                    stage=PipelineStage.RENDER_TABLES,
                    current_table=i + 1,
                    total_tables=len(all_table_regions),
                    message=f"Rendering table {i + 1}/{len(all_table_regions)}..."
                ))
                
                # Generate unique label
                base_id = self._get_caption_id(region.caption)
                if base_id not in used_table_ids:
                    used_table_ids[base_id] = 1
                    unique_label = f"table_{base_id}"
                else:
                    used_table_ids[base_id] += 1
                    unique_label = f"table_{base_id}_v{used_table_ids[base_id]}"
                
                region.label = unique_label
                
                # Render and save
                page = doc.load_page(region.page_number - 1)
                output_path = tables_dir / f"{unique_label}.{self.config.image_format}"
                pixmap = render_region(page, region.bbox, self.config.dpi)
                save_pixmap(pixmap, output_path, self.config.image_format)
        
        # Stage: Generate markdown
        self._report_progress(PipelineProgress(
            stage=PipelineStage.GENERATE_MARKDOWN,
            message="Generating markdown output..."
        ))
        
        markdown_content = self._generate_markdown(
            doc=doc,
            pdf_path=pdf_path,
            page_results=page_results,
            figures=all_figure_regions,
            tables=all_table_regions,
        )
        text_out_path.write_text(markdown_content, encoding="utf-8")
        
        # Stage: Complete
        result = DocumentResult(
            pdf_path=str(pdf_path),
            output_dir=str(base_output_dir),
            markdown_path=str(text_out_path),
            total_pages=doc.page_count,
            pages_processed=total_pages,
            figures_extracted=all_figure_regions,
            tables_extracted=all_table_regions,
            title=doc.metadata.get("title") or base_name,
        )
        
        # S3 上传
        if self.config.enable_s3_upload and self.config.project_id:
            s3_result = self._upload_to_s3(
                base_name=base_name,
                base_output_dir=base_output_dir,
                text_out_path=text_out_path,
                figures_dir=figures_dir,
                tables_dir=tables_dir,
                all_figure_regions=all_figure_regions,
                all_table_regions=all_table_regions,
            )
            if s3_result:
                result.s3_output_prefix = s3_result.get("prefix")
                result.s3_markdown_key = s3_result.get("markdown_key")
                result.s3_figure_keys = s3_result.get("figure_keys", [])
                result.s3_table_keys = s3_result.get("table_keys", [])
        
        self._report_progress(PipelineProgress(
            stage=PipelineStage.COMPLETE,
            message=f"Complete! Extracted {len(all_figure_regions)} figures, {len(all_table_regions)} tables."
        ))
        
        doc.close()
        return result
    
    @staticmethod
    def _get_caption_id(caption) -> str:
        """Get the ID from a caption (supports both old and new model)."""
        return getattr(caption, 'item_id', None) or getattr(caption, 'figure_id', '')
    
    def _process_page(
        self,
        doc: fitz.Document,
        page_index: int,
        total_pages: int,
    ) -> PageResult:
        """Process a single page."""
        page_number = page_index + 1
        page = doc.load_page(page_index)
        
        # Stage: Process page
        self._report_progress(PipelineProgress(
            stage=PipelineStage.PROCESS_PAGE,
            current_page=page_number,
            total_pages=total_pages,
            message=f"Processing page {page_number}/{total_pages}..."
        ))
        
        # Extract text
        page_text = page.get_text("text").strip()
        
        # Stage: Extract captions
        self._report_progress(PipelineProgress(
            stage=PipelineStage.EXTRACT_CAPTIONS,
            current_page=page_number,
            total_pages=total_pages,
            message=f"Extracting captions from page {page_number}..."
        ))
        
        # Extract both figure and table captions
        figure_captions, table_captions = self.caption_extractor.extract_all_captions(page)
        all_captions = figure_captions + table_captions
        
        if not all_captions:
            return PageResult(
                page_number=page_number,
                text=page_text,
                figures=[],
                tables=[],
                captions_found=0,
                elements_found=0,
            )
        
        # Stage: Extract elements
        self._report_progress(PipelineProgress(
            stage=PipelineStage.EXTRACT_ELEMENTS,
            current_page=page_number,
            total_pages=total_pages,
            message=f"Extracting elements from page {page_number}..."
        ))
        
        elements = self.element_extractor.extract(page)
        
        # Stage: Find figures
        figures = []
        if figure_captions:
            self._report_progress(PipelineProgress(
                stage=PipelineStage.FIND_FIGURES,
                current_page=page_number,
                total_pages=total_pages,
                message=f"Finding figures on page {page_number}..."
            ))
            
            figures = self.figure_extractor.extract(page, all_captions, elements, page_number=page_number)
            
            # Set page number for each figure
            for fig in figures:
                fig.page_number = page_number
        
        # Stage: Find tables
        tables = []
        if table_captions and self.config.extract_tables:
            self._report_progress(PipelineProgress(
                stage=PipelineStage.FIND_TABLES,
                current_page=page_number,
                total_pages=total_pages,
                message=f"Finding tables on page {page_number}..."
            ))
            
            tables = self.table_extractor.extract(page, all_captions, elements, page_number=page_number)
            
            # Set page number for each table
            for tbl in tables:
                tbl.page_number = page_number
        
        return PageResult(
            page_number=page_number,
            text=page_text,
            figures=figures,
            tables=tables,
            captions_found=len(all_captions),
            elements_found=len(elements),
        )
    
    def _generate_markdown(
        self,
        doc: fitz.Document,
        pdf_path: Path,
        page_results: List[PageResult],
        figures: List[FigureRegion],
        tables: Optional[List[TableRegion]] = None,
    ) -> str:
        """Generate markdown content from processing results."""
        lines: List[str] = []
        tables = tables or []
        
        title = doc.metadata.get("title") or pdf_path.stem
        lines.append(f"# {title}")
        lines.append("")
        lines.append(f"Source: `{pdf_path}`")
        lines.append(f"Total pages: {doc.page_count}")
        lines.append("")
        
        # Page content
        for result in page_results:
            lines.append(f"## Page {result.page_number}")
            lines.append("")
            lines.append(result.text)
            lines.append("")
        
        # Figures section
        if figures:
            lines.append("## Figures")
            lines.append("")
            for fig in figures:
                rel_path = f"figures/{fig.label}.{self.config.image_format}"
                lines.append(f"![{fig.label}]({rel_path})")
                lines.append(f"*{fig.caption.text}*")
                lines.append("")
        
        # Tables section
        if tables:
            lines.append("## Tables")
            lines.append("")
            for tbl in tables:
                rel_path = f"tables/{tbl.label}.{self.config.image_format}"
                lines.append(f"![{tbl.label}]({rel_path})")
                lines.append(f"*{tbl.caption.text}*")
                lines.append("")
        
        return "\n".join(lines).strip() + "\n"
    
    def _upload_to_s3(
        self,
        base_name: str,
        base_output_dir: Path,
        text_out_path: Path,
        figures_dir: Path,
        tables_dir: Path,
        all_figure_regions: List[FigureRegion],
        all_table_regions: List[TableRegion],
    ) -> Optional[dict]:
        """
        上传提取结果到 S3
        
        S3 目录结构:
            projects/{project_id}/outputs/{pdf_name_date}/
            ├── {pdf_name_date}.md
            ├── figures/
            │   ├── figure_1.png
            │   └── figure_2.png
            └── tables/
                ├── table_1.png
                └── table_2.png
        
        Args:
            base_name: PDF 文件名（不含扩展名）
            base_output_dir: 本地输出目录
            text_out_path: markdown 文件路径
            figures_dir: figures 目录路径
            tables_dir: tables 目录路径
            all_figure_regions: 所有 figure 区域
            all_table_regions: 所有 table 区域
            
        Returns:
            包含 S3 keys 的字典，失败返回 None
        """
        try:
            from datetime import datetime
            from useit_studio.ai_run.utils.s3_uploader import get_s3_uploader, _get_s3_client
            
            # 检查 S3 客户端是否可用
            if _get_s3_client() is None:
                print("[PDFPipeline] S3 client not available, skip upload")
                return None
            
            uploader = get_s3_uploader()
            project_id = self.config.project_id
            
            # 添加日期时间后缀
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            folder_name = f"{base_name}_{timestamp}"
            
            # 构建 S3 前缀
            # 格式: projects/{project_id}/outputs/{pdf_name_date}/
            s3_prefix = f"projects/{project_id}/outputs/{folder_name}"
            
            result = {
                "prefix": s3_prefix,
                "markdown_key": None,
                "figure_keys": [],
                "table_keys": [],
            }
            
            # 1. 上传 markdown 文件
            if text_out_path.exists():
                md_s3_key = f"{s3_prefix}/{folder_name}.md"
                success = uploader._upload_file_sync(
                    str(text_out_path),
                    md_s3_key,
                    "text/markdown"
                )
                if success:
                    result["markdown_key"] = md_s3_key
                    print(f"[PDFPipeline] Uploaded markdown to S3: {md_s3_key}")
            
            # 2. 上传 figures
            for fig in all_figure_regions:
                fig_filename = f"{fig.label}.{self.config.image_format}"
                fig_local_path = figures_dir / fig_filename
                
                if fig_local_path.exists():
                    fig_s3_key = f"{s3_prefix}/figures/{fig_filename}"
                    content_type = "image/png" if self.config.image_format == "png" else "image/svg+xml"
                    success = uploader._upload_file_sync(
                        str(fig_local_path),
                        fig_s3_key,
                        content_type
                    )
                    if success:
                        result["figure_keys"].append(fig_s3_key)
                        print(f"[PDFPipeline] Uploaded figure to S3: {fig_s3_key}")
            
            # 3. 上传 tables
            for tbl in all_table_regions:
                tbl_filename = f"{tbl.label}.{self.config.image_format}"
                tbl_local_path = tables_dir / tbl_filename
                
                if tbl_local_path.exists():
                    tbl_s3_key = f"{s3_prefix}/tables/{tbl_filename}"
                    content_type = "image/png" if self.config.image_format == "png" else "image/svg+xml"
                    success = uploader._upload_file_sync(
                        str(tbl_local_path),
                        tbl_s3_key,
                        content_type
                    )
                    if success:
                        result["table_keys"].append(tbl_s3_key)
                        print(f"[PDFPipeline] Uploaded table to S3: {tbl_s3_key}")
            
            print(f"[PDFPipeline] S3 upload complete: "
                  f"1 markdown, {len(result['figure_keys'])} figures, {len(result['table_keys'])} tables")
            
            return result
            
        except Exception as e:
            print(f"[PDFPipeline] S3 upload error: {e}")
            return None