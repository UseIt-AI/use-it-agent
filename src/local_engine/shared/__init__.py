"""
Shared Types Package

共享类型定义，供 AI_Run 和 Local Engine 使用
"""

__version__ = "1.0.0"

from .types import (
    CUARequestType,
    REQUEST_TYPE_MAPPING,
    ExcelSnapshotParams,
    ExcelSheetNamesParams,
    ExcelSheetSummaryParams,
    validate_request_type,
    get_supported_request_types,
)

__all__ = [
    "CUARequestType",
    "REQUEST_TYPE_MAPPING",
    "ExcelSnapshotParams",
    "ExcelSheetNamesParams",
    "ExcelSheetSummaryParams",
    "validate_request_type",
    "get_supported_request_types",
]
