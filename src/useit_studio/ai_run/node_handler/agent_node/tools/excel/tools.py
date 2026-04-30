"""Excel tools —— /step 协议。"""

from __future__ import annotations

from typing import ClassVar

from ..protocol import EngineTool


class _ExcelEngineTool(EngineTool):
    group: ClassVar[str] = "excel"
    target: ClassVar[str] = "excel"


class ExcelExecuteCode(_ExcelEngineTool):
    name = "excel_execute_code"
    router_hint = (
        "Run PowerShell against Excel COM (read/write cells, formulas, charts, formatting). "
        "Params: code, language ('PowerShell' | 'Python')."
    )
    is_destructive = True
    input_schema = {
        "type": "object",
        "properties": {
            "code": {"type": "string"},
            "language": {"type": "string", "default": "PowerShell"},
        },
        "required": ["code"],
    }


class ExcelReadRange(_ExcelEngineTool):
    name = "excel_read_range"
    router_hint = "Read a cell range as JSON. Params: sheet, range (e.g. 'A1:D10')."
    is_read_only = True
    input_schema = {
        "type": "object",
        "properties": {
            "sheet": {"type": "string"},
            "range": {"type": "string"},
        },
        "required": ["range"],
    }


TOOLS = [ExcelExecuteCode(), ExcelReadRange()]
