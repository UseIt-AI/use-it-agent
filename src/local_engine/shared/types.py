"""
CUA Request Types 定义

AI Run 和 Local Engine 共享的类型定义和映射配置。
这是 Single Source of Truth，确保两端接口契约一致。
"""

from typing import TypedDict, Callable, Any
from enum import Enum


# ==================== Request Type 枚举 ====================

class CUARequestType(str, Enum):
    """
    所有支持的 CUA Request 类型

    使用枚举确保类型安全，避免拼写错误
    """
    # Excel 相关
    EXCEL_SNAPSHOT = "excel_snapshot"
    EXCEL_SHEET_NAMES = "excel_sheet_names"
    EXCEL_SHEET_SUMMARY = "excel_sheet_summary"

    # 未来扩展
    # AUTOCAD_LAYERS = "autocad_layers"
    # WORD_CONTEXT = "word_context"


# ==================== 参数类型定义 ====================

class ExcelSnapshotParams(TypedDict, total=False):
    """
    Excel Snapshot 请求参数

    AI Run 格式（发送）→ Local Engine 格式（接收）
    """
    # Required
    file_path: str                  # Excel 文件路径

    # Optional (AI Run 格式)
    application: str                # "excel" (用于路由，Local Engine 不使用)
    snapshot_type: str              # "full" | "partial"
    specific_sheet: str             # Sheet 名称 → 映射到 sheet_name
    include_formulas: bool          # 是否包含公式
    include_charts: bool            # 是否包含图表（Local Engine 暂不支持）
    include_formats: bool           # 是否包含格式
    max_rows: int                   # 最大行数
    table_range: str                # 表格范围（如 "A1:F360"）


class ExcelSheetNamesParams(TypedDict):
    """Excel Sheet Names 请求参数"""
    file_path: str                  # Excel 文件路径


class ExcelSheetSummaryParams(TypedDict):
    """Excel Sheet Summary 请求参数"""
    file_path: str                  # Excel 文件路径
    specific_sheet: str             # Sheet 名称


# ==================== Controller 映射配置 ====================

class ControllerMapping(TypedDict):
    """
    Controller 映射配置

    定义 request_type 如何映射到 Local Engine 的 controller 和 action
    """
    controller: str                 # Controller 名称（如 "excel"）
    action: str                     # Action 名称（如 "get_snapshot"）
    params_mapper: Callable[[dict], dict]  # 参数映射函数


def _map_excel_snapshot_params(params: dict) -> dict:
    """
    Excel Snapshot 参数映射

    AI Run 格式 → Local Engine Controller 格式
    """
    return {
        "file_path": params.get("file_path"),
        "sheet_name": params.get("specific_sheet", "Sheet1"),  # specific_sheet → sheet_name
        "include_formulas": params.get("include_formulas", True),
        "include_formats": params.get("include_formats", False),
        "max_rows": params.get("max_rows"),
        "table_range": params.get("table_range")
    }


def _map_excel_sheet_names_params(params: dict) -> dict:
    """Excel Sheet Names 参数映射"""
    return {
        "file_path": params.get("file_path")
    }


def _map_excel_sheet_summary_params(params: dict) -> dict:
    """Excel Sheet Summary 参数映射"""
    return {
        "file_path": params.get("file_path"),
        "sheet_name": params.get("specific_sheet", "Sheet1")
    }


# ==================== 集中定义映射关系 ====================

REQUEST_TYPE_MAPPING: dict[str, ControllerMapping] = {
    CUARequestType.EXCEL_SNAPSHOT: {
        "controller": "excel",
        "action": "get_snapshot",
        "params_mapper": _map_excel_snapshot_params
    },
    CUARequestType.EXCEL_SHEET_NAMES: {
        "controller": "excel",
        "action": "get_sheet_names",
        "params_mapper": _map_excel_sheet_names_params
    },
    CUARequestType.EXCEL_SHEET_SUMMARY: {
        "controller": "excel",
        "action": "get_sheet_summary",
        "params_mapper": _map_excel_sheet_summary_params
    }
}


# ==================== 验证函数 ====================

def validate_request_type(request_type: str) -> bool:
    """
    验证 request_type 是否支持

    Args:
        request_type: 请求类型字符串

    Returns:
        是否支持该类型
    """
    return request_type in REQUEST_TYPE_MAPPING


def get_supported_request_types() -> list[str]:
    """
    获取所有支持的 request types

    Returns:
        支持的请求类型列表
    """
    return [rt.value for rt in CUARequestType]
