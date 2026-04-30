"""
Document Extract Tool - 文档提取工具主类

从 PDF 文档中提取文本和图表（Figure）。
支持学术论文（ArXiv 等）的 Figure 自动检测和提取。

架构：
1. 基于 Caption 锚点检测 Figure 区域
2. 提取文本内容为 Markdown
3. 渲染 Figure 为 PNG/SVG 图片
4. 返回结构化数据供前端可视化
"""

import asyncio
import time
from pathlib import Path
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional

from langchain_core.tools import BaseTool as LangChainBaseTool, tool
from pydantic import BaseModel, Field

from .core import PDFPipeline, PipelineConfig, PipelineProgress
from .core.pipeline import PipelineStage
from useit_studio.ai_run.utils.logger_utils import LoggerUtils

logger = LoggerUtils(component_name="DocExtractTool")


# ==================== Document Extract 工具输入 Schema ====================

class DocExtractInput(BaseModel):
    """文档提取工具输入"""
    pdf_path: str = Field(description="Path to the PDF file to extract content from")
    output_dir: str = Field(
        default="doc_extract_output",
        description="Output directory for extracted content (markdown and figures)"
    )
    max_pages: Optional[int] = Field(
        default=None,
        description="Maximum number of pages to process (None for all pages)"
    )


# ==================== 进度回调类型 ====================

ProgressCallback = Callable[[Dict[str, Any]], None]


# ==================== Document Extract 工具实现 ====================

class DocExtractTool:
    """
    文档提取工具 - PDF Figure 提取
    
    架构：基于 Caption 锚点的 Figure 检测
    - 检测 "Figure X" / "Fig. X" / "图 X" 等 Caption
    - 从 Caption 向上搜索视觉元素
    - 合并相关的图片、矢量图和标签文本
    - 渲染为高质量图片
    - 返回结构化数据
    """
    
    name: str = "doc_extract"
    description: str = (
        "Extract text and figures from PDF documents. "
        "Use this tool when you need to analyze academic papers, extract figures, "
        "or convert PDF content to structured markdown format."
    )
    
    def __init__(
        self,
        output_dir: str = "doc_extract_output",
        dpi: int = 200,
        image_format: str = "png",
        max_pages: Optional[int] = None,
        project_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        enable_s3_upload: bool = True,
    ):
        """
        初始化文档提取工具
        
        Args:
            output_dir: 默认输出目录
            dpi: 图片渲染 DPI
            image_format: 图片格式 ("png" or "svg")
            max_pages: 最大处理页数
            project_id: 项目 ID，用于 S3 上传
            chat_id: 会话 ID，用于 S3 上传
            enable_s3_upload: 是否启用 S3 上传
        """
        self.default_output_dir = output_dir
        self.dpi = dpi
        self.image_format = image_format
        self.max_pages = max_pages
        self.project_id = project_id
        self.chat_id = chat_id
        self.enable_s3_upload = enable_s3_upload
        
        logger.logger.info(
            f"[DocExtractTool] Initialized (dpi={dpi}, format={image_format}, s3_upload={enable_s3_upload})"
        )
    
    @classmethod
    def from_config(
        cls,
        config: Dict[str, Any],
        api_keys: Optional[Dict[str, str]] = None,
        project_id: Optional[str] = None,
        chat_id: Optional[str] = None,
    ) -> "DocExtractTool":
        """从配置创建实例"""
        return cls(
            output_dir=config.get("output_dir", "doc_extract_output"),
            dpi=config.get("dpi", 200),
            image_format=config.get("image_format", "png"),
            max_pages=config.get("max_pages"),
            project_id=project_id,
            chat_id=chat_id,
            enable_s3_upload=config.get("enable_s3_upload", True),
        )
    
    # ==================== 主提取方法（带流式进度）====================
    
    async def extract_with_progress(
        self,
        pdf_path: str,
        output_dir: Optional[str] = None,
        max_pages: Optional[int] = None,
        on_progress: Optional[ProgressCallback] = None,
    ) -> Dict[str, Any]:
        """
        执行完整的文档提取流程（带进度回调）
        
        流程：
        1. 打开 PDF 文档
        2. 逐页提取 Caption 和视觉元素
        3. 检测 Figure 区域
        4. 渲染 Figure 图片
        5. 生成 Markdown 输出
        """
        start_time = time.time()
        
        pdf_path_obj = Path(pdf_path)
        out_dir = Path(output_dir or self.default_output_dir)
        pages_limit = max_pages or self.max_pages
        
        logger.logger.info(f"[DocExtractTool] Starting extraction: {pdf_path}")
        
        # 创建进度转换回调
        def progress_adapter(progress: PipelineProgress):
            if on_progress:
                on_progress({
                    "type": "extract_progress",
                    "stage": progress.stage.value,
                    "message": progress.message,
                    "percentage": progress.percentage,
                    "current_page": progress.current_page,
                    "total_pages": progress.total_pages,
                    "current_figure": progress.current_figure,
                    "total_figures": progress.total_figures,
                })
        
        # 配置 Pipeline
        config = PipelineConfig(
            output_dir=out_dir,
            dpi=self.dpi,
            image_format=self.image_format,
            max_pages=pages_limit,
            project_id=self.project_id,
            chat_id=self.chat_id,
            enable_s3_upload=self.enable_s3_upload,
        )
        
        # 在线程池中运行同步代码
        pipeline = PDFPipeline(config=config, progress_callback=progress_adapter)
        
        # 异步执行
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, pipeline.process, pdf_path_obj)
        
        total_time = time.time() - start_time
        
        # 构建结构化响应
        structured_result = {
            "pdf_path": str(result.pdf_path),
            "title": result.title,
            "output_dir": str(result.output_dir),
            "markdown_path": str(result.markdown_path),
            "total_pages": result.total_pages,
            "pages_processed": result.pages_processed,
            "figures": [
                {
                    "label": fig.label,
                    "caption": fig.caption.text,
                    "figure_id": getattr(fig.caption, 'item_id', None) or getattr(fig.caption, 'figure_id', ''),
                    "page_number": fig.page_number,
                    "image_path": f"{result.output_dir}/figures/{fig.label}.{self.image_format}",
                }
                for fig in result.figures_extracted
            ],
            "tables": [
                {
                    "label": tbl.label,
                    "caption": tbl.caption.text,
                    "table_id": getattr(tbl.caption, 'item_id', None) or getattr(tbl.caption, 'table_id', ''),
                    "page_number": tbl.page_number,
                    "image_path": f"{result.output_dir}/tables/{tbl.label}.{self.image_format}",
                }
                for tbl in result.tables_extracted
            ],
            "metadata": {
                "figures_count": len(result.figures_extracted),
                "tables_count": len(result.tables_extracted),
                "total_time": round(total_time, 2),
                "dpi": self.dpi,
                "image_format": self.image_format,
            },
            # S3 上传结果
            "s3": {
                "output_prefix": result.s3_output_prefix,
                "markdown_key": result.s3_markdown_key,
                "figure_keys": result.s3_figure_keys or [],
                "table_keys": result.s3_table_keys or [],
            } if result.s3_output_prefix else None,
        }
        
        logger.logger.info(
            f"[DocExtractTool] Extraction completed: "
            f"{len(result.figures_extracted)} figures in {total_time:.2f}s"
        )
        
        return structured_result
    
    # ==================== 流式提取（AsyncGenerator）====================
    
    async def extract_streaming(
        self,
        pdf_path: str,
        output_dir: Optional[str] = None,
        max_pages: Optional[int] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行文档提取，流式返回进度事件
        """
        events_queue: asyncio.Queue = asyncio.Queue()
        
        def on_progress(event: Dict[str, Any]):
            events_queue.put_nowait(event)
        
        # 启动提取任务
        extract_task = asyncio.create_task(
            self.extract_with_progress(
                pdf_path=pdf_path,
                output_dir=output_dir,
                max_pages=max_pages,
                on_progress=on_progress,
            )
        )
        
        # 流式返回进度事件
        while not extract_task.done():
            try:
                event = await asyncio.wait_for(events_queue.get(), timeout=0.1)
                yield event
            except asyncio.TimeoutError:
                continue
        
        # 获取最终结果
        result = await extract_task
        
        # 发送完成事件
        yield {
            "type": "extract_complete",
            "result": result,
        }
    
    # ==================== 原有方法（保持兼容）====================
    
    async def extract(
        self,
        pdf_path: str,
        output_dir: Optional[str] = None,
        max_pages: Optional[int] = None,
    ) -> Dict[str, Any]:
        """执行文档提取（无进度回调）"""
        return await self.extract_with_progress(
            pdf_path=pdf_path,
            output_dir=output_dir,
            max_pages=max_pages,
            on_progress=None,
        )
    
    async def invoke(
        self,
        pdf_path: str,
        output_dir: str = "doc_extract_output",
        max_pages: Optional[int] = None,
    ) -> str:
        """调用提取并返回格式化文本（供 LLM 阅读）"""
        try:
            data = await self.extract(pdf_path, output_dir, max_pages)
            return self._format_for_llm(data)
            
        except Exception as e:
            logger.logger.error(f"[DocExtractTool] Extraction failed: {e}", exc_info=True)
            return f"Error extracting document: {str(e)}"
    
    async def invoke_with_structured_data(
        self,
        pdf_path: str,
        output_dir: str = "doc_extract_output",
        max_pages: Optional[int] = None,
    ) -> Dict[str, Any]:
        """调用提取并返回结构化数据（供前端渲染）"""
        try:
            data = await self.extract(pdf_path, output_dir, max_pages)
            text = self._format_for_llm(data)
            
            return {
                "text": text,
                "structured_data": {
                    "result_type": "doc_extract",
                    **data,
                }
            }
            
        except Exception as e:
            logger.logger.error(f"[DocExtractTool] Extraction failed: {e}", exc_info=True)
            return {
                "text": f"Error: {str(e)}",
                "structured_data": None,
            }
    
    def _format_for_llm(self, data: Dict[str, Any]) -> str:
        """将提取结果格式化为 LLM 可读的文本"""
        lines = []
        
        lines.append(f"**Document:** {data.get('title', 'Untitled')}")
        lines.append(f"**Source:** `{data.get('pdf_path', '')}`")
        lines.append(f"**Pages processed:** {data.get('pages_processed', 0)}/{data.get('total_pages', 0)}")
        lines.append("")
        
        figures = data.get("figures", [])
        if figures:
            lines.append(f"**Extracted {len(figures)} figure(s):**")
            lines.append("")
            
            for i, fig in enumerate(figures, 1):
                lines.append(f"### [{i}] {fig.get('label', 'figure')}")
                lines.append(f"**Caption:** {fig.get('caption', '')[:200]}...")
                lines.append(f"**Page:** {fig.get('page_number', 'N/A')}")
                lines.append(f"**Image:** `{fig.get('image_path', '')}`")
                lines.append("")
        else:
            lines.append("No figures detected in the document.")
        
        lines.append(f"**Markdown output:** `{data.get('markdown_path', '')}`")
        lines.append(f"**Output directory:** `{data.get('output_dir', '')}`")
        
        metadata = data.get("metadata", {})
        if metadata:
            lines.append("")
            lines.append(f"*Extraction completed in {metadata.get('total_time', 0)}s*")
        
        return "\n".join(lines)
    
    # ==================== LangChain 工具转换 ====================
    
    def as_langchain_tool(self) -> LangChainBaseTool:
        """转换为 LangChain 工具"""
        extract_tool = self
        
        @tool("doc_extract", args_schema=DocExtractInput)
        async def doc_extract(
            pdf_path: str,
            output_dir: str = "doc_extract_output",
            max_pages: Optional[int] = None,
        ) -> str:
            """
            Extract text and figures from PDF documents.
            
            Use this tool when you need to:
            - Extract figures from academic papers
            - Convert PDF content to markdown
            - Analyze document structure
            - Get high-quality figure images
            
            The extraction will automatically:
            1. Detect figure captions (Figure X, Fig. X, 图 X, etc.)
            2. Locate visual elements above captions
            3. Merge related images, drawings, and labels
            4. Render figures as high-quality images
            5. Generate structured markdown output
            
            Args:
                pdf_path: Path to the PDF file
                output_dir: Directory for output files (default: doc_extract_output)
                max_pages: Maximum pages to process (None for all)
            """
            return await extract_tool.invoke(
                pdf_path=pdf_path,
                output_dir=output_dir,
                max_pages=max_pages,
            )
        
        return doc_extract


# ==================== 工厂函数 ====================

def create_doc_extract_tool(
    config: Dict[str, Any],
    api_keys: Optional[Dict[str, str]] = None,
    project_id: Optional[str] = None,
    chat_id: Optional[str] = None,
) -> LangChainBaseTool:
    """
    创建 Document Extract LangChain 工具
    
    Args:
        config: Document Extract 配置
            - output_dir: 输出目录 (default: "doc_extract_output")
            - dpi: 图片 DPI (default: 200)
            - image_format: 图片格式 "png" or "svg" (default: "png")
            - max_pages: 最大页数 (default: None)
            - enable_s3_upload: 是否启用 S3 上传 (default: True)
        api_keys: API 密钥字典（当前未使用）
        project_id: 项目 ID，用于 S3 上传
        chat_id: 会话 ID，用于 S3 上传
        
    Returns:
        LangChain 工具实例
    """
    doc_extract = DocExtractTool.from_config(config, api_keys, project_id, chat_id)
    return doc_extract.as_langchain_tool()
