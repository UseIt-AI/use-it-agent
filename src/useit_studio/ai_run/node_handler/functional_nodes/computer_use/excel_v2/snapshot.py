"""
Excel Agent - 工作表快照数据结构

SheetSnapshot 实现了 BaseSnapshot Protocol，
用于表示 Excel 工作表的状态。
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

# 导入 toon_format 用于压缩输出
import json

def _json_encode(obj):
    """JSON fallback encoder - 使用紧凑格式以节省 token"""
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':'))

from toon_format import encode as _toon_encode
try:
    # 测试是否实际可用
    _toon_encode({"test": 1})
    toon_encode = _toon_encode
except (ImportError, NotImplementedError):
    toon_encode = _json_encode


# ==================== 单元格信息 ====================

@dataclass
class CellInfo:
    """
    单元格信息
    """
    row: int                            # 行号 (1-indexed)
    col: int                            # 列号 (1-indexed)
    col_letter: str = ""                # 列字母 (A, B, C, ...)
    value: Any = None                   # 单元格值
    formula: Optional[str] = None       # 公式（如果有）
    data_type: str = "n"                # 数据类型 (n=number, s=string, b=boolean, d=date)
    is_merged: bool = False             # 是否是合并单元格的一部分
    format: Optional[str] = None        # 数字格式

    @property
    def address(self) -> str:
        """获取单元格地址 (如 A1)"""
        return f"{self.col_letter}{self.row}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "row": self.row,
            "col": self.col,
            "col_letter": self.col_letter,
            "value": self.value,
            "formula": self.formula,
            "data_type": self.data_type,
            "is_merged": self.is_merged,
            "format": self.format,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CellInfo":
        return cls(
            row=data.get("row", 1),
            col=data.get("col", 1),
            col_letter=data.get("col_letter", data.get("col", "")),
            value=data.get("value"),
            formula=data.get("formula"),
            data_type=data.get("data_type", "n"),
            is_merged=data.get("is_merged", False),
            format=data.get("format"),
        )


# ==================== 工作表信息 ====================

@dataclass
class SheetInfo:
    """
    工作表信息
    """
    name: str                           # 工作表名称
    index: int = 1                      # 工作表索引 (1-indexed)
    is_active: bool = False             # 是否是活动工作表
    row_count: int = 0                  # 已使用的行数
    col_count: int = 0                  # 已使用的列数

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "index": self.index,
            "is_active": self.is_active,
            "row_count": self.row_count,
            "col_count": self.col_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SheetInfo":
        return cls(
            name=data.get("name", "Sheet1"),
            index=data.get("index", 1),
            is_active=data.get("is_active", False),
            row_count=data.get("row_count", 0),
            col_count=data.get("col_count", 0),
        )


# ==================== 工作簿信息 ====================

@dataclass
class WorkbookInfo:
    """
    工作簿基本信息
    """
    name: str                           # 工作簿名称
    path: Optional[str] = None          # 工作簿完整路径
    saved: bool = True                  # 是否已保存
    sheet_count: int = 1                # 工作表数量
    active_sheet: str = "Sheet1"        # 活动工作表名称

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "saved": self.saved,
            "sheet_count": self.sheet_count,
            "active_sheet": self.active_sheet,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkbookInfo":
        return cls(
            name=data.get("name", "Unknown"),
            path=data.get("path"),
            saved=data.get("saved", True),
            sheet_count=data.get("sheet_count", 1),
            active_sheet=data.get("active_sheet", "Sheet1"),
        )


# ==================== 工作表快照 ====================

@dataclass
class SheetSnapshot:
    """
    Excel 工作表快照
    
    实现 BaseSnapshot Protocol。
    """
    workbook_info: WorkbookInfo
    sheet_info: SheetInfo
    cells: List[CellInfo] = field(default_factory=list)
    merged_cells: List[str] = field(default_factory=list)  # 合并区域列表，如 ["A1:B2", "C3:D4"]
    _screenshot: Optional[str] = None

    @property
    def screenshot(self) -> Optional[str]:
        """base64 编码的截图"""
        return self._screenshot

    @property
    def has_data(self) -> bool:
        """是否有有效数据"""
        return self.workbook_info.name != "NO_WORKBOOK"

    @property
    def file_path(self) -> Optional[str]:
        """获取文件路径"""
        return self.workbook_info.path or self.workbook_info.name

    @property
    def dimensions(self) -> Dict[str, int]:
        """获取数据维度"""
        return {
            "rows": self.sheet_info.row_count,
            "cols": self.sheet_info.col_count,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workbook_info": self.workbook_info.to_dict(),
            "sheet_info": self.sheet_info.to_dict(),
            "cells": [c.to_dict() for c in self.cells],
            "merged_cells": self.merged_cells,
            "screenshot": self._screenshot,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SheetSnapshot":
        """
        从字典创建 SheetSnapshot
        
        支持两种格式:
        1. 标准格式: {workbook_info, sheet_info, cells}
        2. Local Engine 格式: {workbook_info, content: {current_sheet: {data: [[...]]}}}
        """
        # 解析 workbook_info
        workbook_data = data.get("workbook_info", {})
        workbook_info = WorkbookInfo.from_dict(workbook_data)
        
        # 检查是否是 Local Engine 格式 (content.current_sheet.data)
        content = data.get("content", {})
        current_sheet_data = content.get("current_sheet", {})
        
        if current_sheet_data and "data" in current_sheet_data:
            # Local Engine 格式: 从 content.current_sheet 解析
            sheet_info = cls._parse_sheet_info_from_content(current_sheet_data, workbook_data)
            cells = cls._parse_cells_from_2d_array(current_sheet_data.get("data", []))
            merged_cells = current_sheet_data.get("merged_cells", [])
        else:
            # 标准格式
            sheet_data = data.get("sheet_info", {})
            sheet_info = SheetInfo.from_dict(sheet_data)
            
            # 解析 cells
            cells = []
            for cell_data in data.get("cells", []):
                cells.append(CellInfo.from_dict(cell_data))
            
            merged_cells = data.get("merged_cells", [])
        
        screenshot = data.get("screenshot")
        
        return cls(
            workbook_info=workbook_info,
            sheet_info=sheet_info,
            cells=cells,
            merged_cells=merged_cells,
            _screenshot=screenshot,
        )
    
    @classmethod
    def _parse_sheet_info_from_content(cls, current_sheet: Dict[str, Any], workbook_data: Dict[str, Any]) -> SheetInfo:
        """从 Local Engine 格式的 current_sheet 解析 SheetInfo"""
        used_range = current_sheet.get("used_range", {})
        return SheetInfo(
            name=current_sheet.get("name", workbook_data.get("current_sheet", "Sheet1")),
            index=current_sheet.get("index", workbook_data.get("current_sheet_index", 1)),
            is_active=True,  # current_sheet 就是活动工作表
            row_count=used_range.get("rows", 0),
            col_count=used_range.get("cols", 0),
        )
    
    @classmethod
    def _parse_cells_from_2d_array(cls, data: List[List[Any]], max_rows: int = 100, max_cols: int = 50) -> List[CellInfo]:
        """
        从二维数组解析单元格列表
        
        Args:
            data: 二维数组，data[row][col] 是单元格值
            max_rows: 最大行数限制（避免过大）
            max_cols: 最大列数限制
        
        Returns:
            CellInfo 列表
        """
        cells = []
        
        for row_idx, row in enumerate(data[:max_rows]):
            if not row:
                continue
            for col_idx, value in enumerate(row[:max_cols]):
                if value is None:
                    continue
                
                col_letter = col_to_letter(col_idx + 1)
                
                # 判断数据类型
                if isinstance(value, bool):
                    data_type = "b"
                elif isinstance(value, (int, float)):
                    data_type = "n"
                elif isinstance(value, str):
                    if value.startswith("="):
                        data_type = "n"  # 公式
                    else:
                        data_type = "s"
                else:
                    data_type = "s"
                
                # 检查是否是公式
                formula = None
                if isinstance(value, str) and value.startswith("="):
                    formula = value
                
                cells.append(CellInfo(
                    row=row_idx + 1,
                    col=col_idx + 1,
                    col_letter=col_letter,
                    value=value,
                    formula=formula,
                    data_type=data_type,
                ))
        
        return cells

    @classmethod
    def empty(cls) -> "SheetSnapshot":
        """创建空的工作表快照"""
        return cls(
            workbook_info=WorkbookInfo(name="NO_WORKBOOK"),
            sheet_info=SheetInfo(name="Sheet1"),
        )

    def to_context_format(self, max_items: int = 100, max_text_length: int = 50) -> str:
        """
        转换为 LLM 可用的纯文本格式（避免 JSON 转义问题）

        Args:
            max_items: 最大单元格数量
            max_text_length: 单元格值最大长度

        Returns:
            格式化的文本描述
        """
        result_parts = []

        # 1. 工作簿信息（纯文本 key=value 格式）
        result_parts.append("# Workbook Information")
        wb = self.workbook_info
        result_parts.append(f"name={wb.name}, path={wb.path}, saved={wb.saved}, sheet_count={wb.sheet_count}, active_sheet={wb.active_sheet}")
        result_parts.append("")

        # 2. 工作表信息（纯文本格式）
        result_parts.append("# Sheet Information")
        si = self.sheet_info
        result_parts.append(f"name={si.name}, index={si.index}, is_active={si.is_active}, row_count={si.row_count}, col_count={si.col_count}")
        result_parts.append("")

        # 3. 数据预览（按行分组的表格格式）
        if self.cells:
            result_parts.append("# Data Preview")

            # 按行分组单元格
            rows_data: Dict[int, List[CellInfo]] = {}
            for cell in self.cells[:max_items]:
                if cell.row not in rows_data:
                    rows_data[cell.row] = []
                rows_data[cell.row].append(cell)

            # 输出每行数据（格式: Row N: val1 | val2 | val3）
            for row_num in sorted(rows_data.keys()):
                row_cells = sorted(rows_data[row_num], key=lambda c: c.col)
                values = []
                for cell in row_cells:
                    val = cell.value
                    # 截断过长的值
                    if isinstance(val, str) and len(val) > max_text_length:
                        val = val[:max_text_length] + "..."
                    # 处理公式
                    if cell.formula:
                        values.append(f"{val}[={cell.formula}]")
                    else:
                        values.append(str(val) if val is not None else "")
                result_parts.append(f"Row {row_num}: " + " | ".join(values))

            if len(self.cells) > max_items:
                result_parts.append(f"# ... ({len(self.cells) - max_items} more cells)")
            result_parts.append("")

        # 4. 合并单元格（简单列表格式）
        if self.merged_cells:
            result_parts.append("# Merged Cells")
            result_parts.append(", ".join(self.merged_cells[:20]))
            if len(self.merged_cells) > 20:
                result_parts.append(f"# ... ({len(self.merged_cells) - 20} more)")
            result_parts.append("")

        return "\n".join(result_parts)


# ==================== 辅助函数 ====================

def sheet_snapshot_from_dict(data: Dict[str, Any]) -> SheetSnapshot:
    """将字典转换为 SheetSnapshot"""
    return SheetSnapshot.from_dict(data)


def col_to_letter(col_num: int) -> str:
    """将列号转换为字母（1 -> A, 27 -> AA）"""
    result = ""
    while col_num > 0:
        col_num -= 1
        result = chr(col_num % 26 + ord('A')) + result
        col_num //= 26
    return result


def letter_to_col(letters: str) -> int:
    """将字母转换为列号（A -> 1, AA -> 27）"""
    result = 0
    for char in letters.upper():
        result = result * 26 + (ord(char) - ord('A') + 1)
    return result
