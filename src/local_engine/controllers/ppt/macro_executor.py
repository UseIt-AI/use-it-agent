"""
PPT Macro Executor - 高级原生对象创建

处理图表、表格、媒体等需要调用 PPT 原生引擎的复杂操作。
大模型只需提供结构化数据（二维数组、文件路径等），由此模块处理所有 COM 细节。

支持的 Macros:
- insert_native_chart : 插入原生图表（柱状、折线、饼图、散点等）
- insert_native_table : 插入原生表格
- insert_media        : 插入图片/媒体文件
"""

import logging
import os
from typing import Any, Dict, List, Optional

from .constants import (
    CHART_TYPES,
    DEFAULT_TABLE_STYLE,
    MSO_GRADIENT_FROM_CENTER,
    MSO_GRADIENT_HORIZONTAL,
    parse_color,
    resolve_table_style,
)

logger = logging.getLogger(__name__)


class MacroExecutor:
    """处理图表、表格、媒体等原生 PPT 对象的创建"""

    # ==================== Chart ====================

    def insert_chart(
        self,
        slide,
        chart_type: str,
        bounds: Dict[str, float],
        data_matrix: List[List],
        title: Optional[str] = None,
        style: Optional[int] = None,
        handle_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        插入原生 PPT 图表。

        PPT 的 AddChart2 会自动处理坐标轴、图例、配色。

        Args:
            slide: COM Slide object
            chart_type: 图表类型名称（见 constants.CHART_TYPES）
            bounds: {"x": float, "y": float, "w": float, "h": float} (points)
            data_matrix: 二维数组，第一行为 header
                e.g. [["季度","营收","利润"], ["Q1",100,20], ["Q2",150,35]]
            title: 图表标题（可选）
            style: 图表样式索引（可选，1-based）
            handle_id: 设置 Shape.Name

        Returns:
            {"success": bool, "handle_id": str|None, "error": str|None}
        """
        xl_type = CHART_TYPES.get(chart_type)
        if xl_type is None:
            return {
                "success": False,
                "handle_id": None,
                "error": f"Unknown chart type: {chart_type}. Available: {list(CHART_TYPES.keys())}",
            }

        x = bounds.get("x", 0)
        y = bounds.get("y", 0)
        w = bounds.get("w", 400)
        h = bounds.get("h", 300)

        if not data_matrix or len(data_matrix) < 2:
            return {
                "success": False,
                "handle_id": None,
                "error": "data_matrix must have at least 2 rows (header + data)",
            }

        try:
            chart_style = style if style else -1
            shape = slide.Shapes.AddChart2(
                chart_style, xl_type, x, y, w, h, True
            )

            chart = shape.Chart
            cd = chart.ChartData
            cd.Activate()

            wb = cd.Workbook
            ws = wb.Worksheets(1)

            # Clear existing data
            ws.Cells.Clear()

            # Write data_matrix into the chart's embedded worksheet
            num_rows = len(data_matrix)
            num_cols = len(data_matrix[0]) if data_matrix else 0

            for r_idx, row in enumerate(data_matrix):
                for c_idx, val in enumerate(row):
                    ws.Cells(r_idx + 1, c_idx + 1).Value = val

            # Set data range so the chart references only the written cells
            if num_cols > 1 and num_rows > 1:
                range_str = f"A1:{_col_letter(num_cols)}{num_rows}"
                try:
                    cd.SetRange(ws.Range(range_str))
                except Exception:
                    try:
                        chart.SetSourceData(ws.Range(range_str))
                    except Exception:
                        pass

            wb.Close(False)

            # Set title
            if title:
                chart.HasTitle = True
                chart.ChartTitle.Text = title

            if handle_id:
                shape.Name = handle_id

            logger.info(
                f"[MacroExecutor] Inserted chart: type={chart_type}, "
                f"data={num_rows}x{num_cols}, handle={handle_id}"
            )

            return {
                "success": True,
                "handle_id": handle_id or shape.Name,
                "error": None,
            }

        except Exception as e:
            logger.error(f"[MacroExecutor] insert_chart failed: {e}", exc_info=True)
            return {"success": False, "handle_id": None, "error": str(e)}

    # ==================== Table ====================

    def insert_table(
        self,
        slide,
        bounds: Dict[str, float],
        data_matrix: List[List],
        style: Optional[str] = None,
        first_row_header: bool = True,
        first_col: bool = False,
        banded_rows: bool = True,
        banded_cols: bool = False,
        handle_id: Optional[str] = None,
        cell_format: Optional[List[Dict]] = None,
        font_size: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        插入原生 PPT 表格并填充数据。

        Args:
            slide: COM Slide object
            bounds: {"x","y","w","h"} (points)
            data_matrix: 二维数组
            style: 样式名称（如 "no_style"）或 GUID，
                   None → 使用 DEFAULT_TABLE_STYLE
            first_row_header: 首行标记为表头
            first_col: 首列加粗
            banded_rows: 行条带
            banded_cols: 列条带
            handle_id: Shape.Name
            cell_format: 单元格格式化列表，每项:
                {"row":int, "col":int, "fill_color":str, "font_color":str,
                 "font_bold":bool, "font_size":float, "align":str}
                row/col 为 1-based
            font_size: 全表默认字号
        """
        if not data_matrix or not data_matrix[0]:
            return {
                "success": False,
                "handle_id": None,
                "error": "data_matrix must not be empty",
            }

        num_rows = len(data_matrix)
        num_cols = max(len(row) for row in data_matrix)
        x = bounds.get("x", 0)
        y = bounds.get("y", 0)
        w = bounds.get("w", 400)
        h = bounds.get("h", 200)

        try:
            shape = slide.Shapes.AddTable(num_rows, num_cols, x, y, w, h)
            table = shape.Table

            # Apply table style
            effective_style = style or DEFAULT_TABLE_STYLE
            style_guid = resolve_table_style(effective_style)
            if style_guid:
                try:
                    table.ApplyStyle(style_guid)
                except Exception as e:
                    logger.warning(f"[MacroExecutor] ApplyStyle failed ({effective_style}): {e}")

            # Table flags
            table.FirstRow = first_row_header
            table.FirstCol = first_col
            table.HorizBanding = banded_rows
            table.VertBanding = banded_cols

            # Fill data
            for r_idx, row in enumerate(data_matrix):
                for c_idx, val in enumerate(row):
                    if c_idx < num_cols:
                        cell = table.Cell(r_idx + 1, c_idx + 1)
                        tr = cell.Shape.TextFrame.TextRange
                        tr.Text = str(val) if val is not None else ""
                        if font_size:
                            tr.Font.Size = font_size

            # Cell-level formatting
            if cell_format:
                self._apply_cell_format(table, cell_format, num_rows, num_cols)

            if handle_id:
                shape.Name = handle_id

            logger.info(
                f"[MacroExecutor] Inserted table: {num_rows}x{num_cols}, "
                f"style={effective_style}, handle={handle_id}"
            )

            return {
                "success": True,
                "handle_id": handle_id or shape.Name,
                "error": None,
            }

        except Exception as e:
            logger.error(f"[MacroExecutor] insert_table failed: {e}", exc_info=True)
            return {"success": False, "handle_id": None, "error": str(e)}

    @staticmethod
    def _apply_cell_format(
        table, cell_format: List[Dict], num_rows: int, num_cols: int
    ) -> None:
        """Apply per-cell formatting (fill, gradient, borders, font, alignment)."""
        TEXT_ALIGN_MAP = {"left": 1, "center": 2, "right": 3}

        for fmt in cell_format:
            row = fmt.get("row")
            col = fmt.get("col")
            if not row or not col or row > num_rows or col > num_cols:
                continue

            try:
                cell = table.Cell(row, col)
                cell_shape = cell.Shape
                tr = cell_shape.TextFrame.TextRange

                fill_gradient = fmt.get("fill_gradient")
                if fill_gradient:
                    MacroExecutor._apply_fill_gradient(cell_shape, fill_gradient)

                fill_color = fmt.get("fill_color")
                if fill_color:
                    color_val = parse_color(fill_color)
                    if color_val is not None:
                        cell_shape.Fill.Solid()
                        cell_shape.Fill.ForeColor.RGB = color_val

                if "fill_transparency" in fmt:
                    cell_shape.Fill.Transparency = float(fmt["fill_transparency"])

                line_color = fmt.get("line_color")
                if line_color:
                    color_val = parse_color(line_color)
                    if color_val is not None:
                        cell_shape.Line.Visible = True
                        cell_shape.Line.ForeColor.RGB = color_val

                if "line_transparency" in fmt:
                    cell_shape.Line.Transparency = float(fmt["line_transparency"])

                if "line_weight" in fmt:
                    cell_shape.Line.Weight = float(fmt["line_weight"])

                font_color = fmt.get("font_color")
                if font_color:
                    color_val = parse_color(font_color)
                    if color_val is not None:
                        try:
                            tr.Font.Color.RGB = color_val
                        except Exception:
                            pass
                        try:
                            tr.Font.Fill.Visible = True
                            tr.Font.Fill.Solid()
                            tr.Font.Fill.ForeColor.RGB = color_val
                        except Exception:
                            pass

                if fmt.get("font_bold") is not None:
                    tr.Font.Bold = bool(fmt["font_bold"])

                if fmt.get("font_italic") is not None:
                    tr.Font.Italic = bool(fmt["font_italic"])

                fs = fmt.get("font_size")
                if fs:
                    tr.Font.Size = fs

                font_name = fmt.get("font_name")
                if font_name:
                    tr.Font.Name = font_name

                align = fmt.get("align")
                if align and align in TEXT_ALIGN_MAP:
                    tr.ParagraphFormat.Alignment = TEXT_ALIGN_MAP[align]

                if "margin_left" in fmt:
                    cell_shape.TextFrame.MarginLeft = float(fmt["margin_left"])
                if "margin_right" in fmt:
                    cell_shape.TextFrame.MarginRight = float(fmt["margin_right"])
                if "margin_top" in fmt:
                    cell_shape.TextFrame.MarginTop = float(fmt["margin_top"])
                if "margin_bottom" in fmt:
                    cell_shape.TextFrame.MarginBottom = float(fmt["margin_bottom"])

            except Exception as e:
                logger.warning(
                    f"[MacroExecutor] cell_format ({row},{col}) failed: {e}"
                )

    @staticmethod
    def _apply_fill_gradient(shape, gradient: Dict) -> None:
        """Apply a gradient fill to a table cell shape."""
        stops = gradient.get("stops", [])
        if len(stops) < 2:
            raise ValueError("fill_gradient requires at least 2 stops")

        stops = sorted(stops, key=lambda s: s["position"])
        grad_type = gradient.get("type", "linear")
        fill = shape.Fill

        if grad_type == "radial":
            fill.TwoColorGradient(MSO_GRADIENT_FROM_CENTER, 1)
        else:
            fill.TwoColorGradient(MSO_GRADIENT_HORIZONTAL, 1)

        gs = fill.GradientStops
        c0 = parse_color(stops[0]["color"]) or 0
        cN = parse_color(stops[-1]["color"]) or 0
        gs(1).Color.RGB = c0
        gs(1).Position = float(stops[0]["position"])
        gs(1).Transparency = 1.0 - float(stops[0].get("opacity", 1.0))
        gs(2).Color.RGB = cN
        gs(2).Position = float(stops[-1]["position"])
        gs(2).Transparency = 1.0 - float(stops[-1].get("opacity", 1.0))

        for stop in stops[1:-1]:
            c = parse_color(stop["color"]) or 0
            pos = float(stop["position"])
            gs.Insert(c, pos)
            for idx in range(1, gs.Count + 1):
                if abs(gs(idx).Position - pos) < 0.005:
                    gs(idx).Transparency = 1.0 - float(stop.get("opacity", 1.0))
                    break

        if grad_type != "radial":
            fill.GradientAngle = float(gradient.get("angle", 0)) % 360

    # ==================== Media (Image/Video) ====================

    def insert_media(
        self,
        slide,
        media_path: str,
        bounds: Dict[str, float],
        handle_id: Optional[str] = None,
        link_to_file: bool = False,
        preserve_aspect_ratio: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        插入图片或媒体文件。

        Args:
            slide: COM Slide object
            media_path: 文件绝对路径
            bounds: {"x": float, "y": float, "w": float, "h": float} (points)
            handle_id: 设置 Shape.Name
            link_to_file: 是否链接而非嵌入
            preserve_aspect_ratio: 与 SVG 相同语义；未传时默认 xMidYMid meet（等比落入框内并居中）。
                传入 "none" 则铺满边界框（可能拉伸）。视频忽略此参数。

        Returns:
            {"success": bool, "handle_id": str|None, "error": str|None}
        """
        media_path = os.path.normpath(os.path.abspath(media_path))

        if not os.path.exists(media_path):
            return {
                "success": False,
                "handle_id": None,
                "error": f"File not found: {media_path}",
            }

        x = bounds.get("x", 0)
        y = bounds.get("y", 0)
        w = bounds.get("w", 200)
        h = bounds.get("h", 200)
        par = (
            preserve_aspect_ratio
            if preserve_aspect_ratio is not None
            else "xMidYMid meet"
        )

        try:
            ext = os.path.splitext(media_path)[1].lower()

            if ext in (".mp4", ".avi", ".wmv", ".mov", ".m4v"):
                shape = slide.Shapes.AddMediaObject2(
                    media_path, link_to_file, True, x, y, w, h
                )
            else:
                nat = get_image_pixel_size(media_path)
                mode, _, _ = parse_preserve_aspect_ratio(par)
                if nat:
                    left, top, pw, ph = compute_picture_rect(
                        x, y, w, h, nat[0], nat[1], par
                    )
                else:
                    left, top, pw, ph = x, y, w, h
                shape = slide.Shapes.AddPicture(
                    media_path,
                    LinkToFile=link_to_file,
                    SaveWithDocument=not link_to_file,
                    Left=left,
                    Top=top,
                    Width=pw,
                    Height=ph,
                )
                if nat and mode == "slice":
                    cl, ct, cr, cb = compute_slice_crop_in_points(
                        x, y, w, h, left, top, pw, ph
                    )
                    apply_picture_crop_com(shape, cl, ct, cr, cb)

            if handle_id:
                shape.Name = handle_id

            logger.info(f"[MacroExecutor] Inserted media: {media_path}, handle={handle_id}")

            return {
                "success": True,
                "handle_id": handle_id or shape.Name,
                "error": None,
            }

        except Exception as e:
            logger.error(f"[MacroExecutor] insert_media failed: {e}", exc_info=True)
            return {"success": False, "handle_id": None, "error": str(e)}


# ==================== Helpers ====================

def _col_letter(col_num: int) -> str:
    """Convert 1-based column number to Excel column letter (1=A, 26=Z, 27=AA)."""
    result = ""
    while col_num > 0:
        col_num -= 1
        result = chr(65 + col_num % 26) + result
        col_num //= 26
    return result
