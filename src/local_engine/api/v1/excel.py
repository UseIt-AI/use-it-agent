"""
Excel API 端点 - Microsoft Excel 自动化

通过 COM 连接到已打开的 Excel，支持用户和 AI 协作编辑工作簿。

主要端点:
- GET  /api/v1/excel/status     获取 Excel 状态
- POST /api/v1/excel/open       打开工作簿
- POST /api/v1/excel/close      关闭工作簿
- POST /api/v1/excel/snapshot   获取工作簿快照
- POST /api/v1/excel/step       执行代码并返回更新后的快照
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
import logging

from controllers.excel.controller import ExcelController
from .project import format_tree_as_text

logger = logging.getLogger(__name__)
router = APIRouter()

# 全局 Controller 实例
_controller: Optional[ExcelController] = None


def _get_controller() -> ExcelController:
    """获取 Excel Controller 实例"""
    global _controller
    if _controller is None:
        _controller = ExcelController()
    return _controller


# ==================== 请求模型 ====================

class SnapshotRequest(BaseModel):
    """获取工作簿快照请求"""
    include_content: bool = Field(default=True, description="是否包含工作表内容")
    include_screenshot: bool = Field(default=True, description="是否包含截图")
    max_rows: Optional[int] = Field(default=None, description="最大行数（None=自动检测）")
    max_cols: Optional[int] = Field(default=None, description="最大列数（None=自动检测）")
    current_sheet_only: bool = Field(default=True, description="是否只返回当前工作表的内容")
    visible_only: bool = Field(default=True, description="Snapshot只返回可见行+上下2行context")
    # Project files 相关参数
    include_project_files: bool = Field(default=False, description="是否包含项目文件列表")
    project_path: Optional[str] = Field(default=None, description="项目根目录路径（include_project_files=true 时必填）")
    project_max_depth: int = Field(default=4, ge=1, le=10, description="项目文件遍历最大深度")
    project_max_files: int = Field(default=500, ge=1, le=2000, description="项目文件最大数量")


class StepRequest(BaseModel):
    """
    执行代码/脚本请求

    支持两种模式：
    1. execute_code: 提供 code 参数，执行代码字符串
    2. execute_script: 提供 script_path 参数，执行 skill 中的脚本
    """
    # Mode 1: execute_code
    code: Optional[str] = Field(default=None, description="要执行的代码（execute_code 模式）")

    # Mode 2: execute_script
    skill_id: Optional[str] = Field(default=None, description="Skill ID，如 '66666666'（execute_script 模式）")
    script_path: Optional[str] = Field(default=None, description="脚本相对路径，如 'scripts/create_column_chart.ps1'（execute_script 模式）")
    parameters: Optional[Dict[str, Any]] = Field(default=None, description="脚本参数字典（execute_script 模式）")

    # 通用参数
    language: str = Field(default="PowerShell", description="语言：PowerShell 或 Python")
    timeout: int = Field(default=120, description="超时时间（秒）")
    return_screenshot: bool = Field(default=True, description="是否返回截图")
    current_sheet_only: bool = Field(default=True, description="快照是否只返回当前工作表内容")
    visible_only: bool = Field(default=True, description="Snapshot只返回可见行+上下2行context")

    # Project files 相关参数
    include_project_files: bool = Field(default=False, description="是否包含项目文件列表")
    project_path: Optional[str] = Field(default=None, description="项目根目录路径（include_project_files=true 时必填）")
    project_max_depth: int = Field(default=4, ge=1, le=10, description="项目文件遍历最大深度")


class OpenWorkbookRequest(BaseModel):
    """打开工作簿请求"""
    file_path: str = Field(..., description="工作簿路径")
    read_only: bool = Field(default=False, description="是否以只读方式打开")


class CloseWorkbookRequest(BaseModel):
    """关闭工作簿请求"""
    save: bool = Field(default=False, description="是否保存工作簿")


# ==================== API 端点 ====================

@router.get("/status")
async def get_status() -> Dict[str, Any]:
    """
    获取 Excel 状态
    
    检查 Excel 是否运行，以及当前是否有打开的工作簿。
    
    Returns:
        {
            "success": true,
            "data": {
                "running": true,
                "has_workbook": true,
                "workbook_info": {
                    "name": "数据.xlsx",
                    "path": "C:/Documents/数据.xlsx",
                    "saved": true,
                    "sheet_count": 3,
                    "current_sheet": "Sheet1",
                    "sheet_names": ["Sheet1", "Sheet2", "Sheet3"]
                }
            }
        }
    """
    logger.info("[Excel API] status")
    
    try:
        controller = _get_controller()
        status = await controller.get_status()
        return {"success": True, "data": status}
    except Exception as e:
        logger.error(f"[Excel API] status error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/open")
async def open_workbook(request: OpenWorkbookRequest) -> Dict[str, Any]:
    """
    打开 Excel 工作簿
    
    如果 Excel 未运行，会自动启动 Excel。
    
    Args:
        request.file_path: 工作簿路径
        request.read_only: 是否以只读方式打开
    
    Returns:
        {
            "success": true,
            "data": {
                "workbook_info": {
                    "name": "数据.xlsx",
                    "path": "C:/Documents/数据.xlsx",
                    "sheet_count": 3,
                    "current_sheet": "Sheet1",
                    ...
                }
            }
        }
    """
    logger.info(f"[Excel API] open: file_path={request.file_path}, read_only={request.read_only}")
    
    try:
        controller = _get_controller()
        result = await controller.open_workbook(
            file_path=request.file_path,
            read_only=request.read_only
        )
        
        if result["success"]:
            return {"success": True, "data": {"workbook_info": result["workbook_info"]}}
        else:
            raise HTTPException(status_code=400, detail=result["error"])
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Excel API] open error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/close")
async def close_workbook(request: CloseWorkbookRequest = None) -> Dict[str, Any]:
    """
    关闭当前 Excel 工作簿
    
    Args:
        request.save: 是否保存工作簿（默认不保存）
    
    Returns:
        {
            "success": true,
            "data": {
                "closed_workbook": "数据.xlsx"
            }
        }
    """
    if request is None:
        request = CloseWorkbookRequest()
    
    logger.info(f"[Excel API] close: save={request.save}")
    
    try:
        controller = _get_controller()
        result = await controller.close_workbook(save=request.save)
        
        if result["success"]:
            return {"success": True, "data": {"closed_workbook": result["closed_workbook"]}}
        else:
            raise HTTPException(status_code=400, detail=result["error"])
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Excel API] close error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/snapshot")
async def get_snapshot(request: SnapshotRequest = None) -> Dict[str, Any]:
    """
    获取工作簿快照
    
    获取当前打开工作簿的内容和/或截图。
    
    Args:
        request.include_content: 是否包含工作表内容（数据、公式等）
        request.include_screenshot: 是否包含截图
        request.max_rows: 最大行数限制
        request.max_cols: 最大列数限制
        request.current_sheet_only: 是否只返回当前工作表
    
    Returns:
        {
            "success": true,
            "data": {
                "workbook_info": {...},
                "content": {
                    "current_sheet": {...},
                    "all_sheets_summary": [...]
                },
                "screenshot": "base64..."
            }
        }
    """
    if request is None:
        request = SnapshotRequest()
    
    logger.info(f"[Excel API] snapshot: content={request.include_content}, screenshot={request.include_screenshot}, current_sheet_only={request.current_sheet_only}, include_project_files={request.include_project_files}")
    
    try:
        controller = _get_controller()
        snapshot = await controller.get_snapshot(
            include_content=request.include_content,
            include_screenshot=request.include_screenshot,
            max_rows=request.max_rows,
            max_cols=request.max_cols,
            current_sheet_only=request.current_sheet_only,
            visible_only=request.visible_only
        )
        
        # 如果需要项目文件列表（使用紧凑 text 格式）
        if request.include_project_files and request.project_path:
            try:
                project_tree = format_tree_as_text(
                    project_path=request.project_path,
                    max_depth=request.project_max_depth,
                )
                snapshot["project_files"] = project_tree
            except Exception as e:
                logger.warning(f"[Excel API] Failed to get project files: {e}")
                snapshot["project_files"] = f"Error: {str(e)}"
        
        return {"success": True, "data": snapshot}
    except ValueError as e:
        # 例如：没有打开的工作簿
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[Excel API] snapshot error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/step")
async def step(request: StepRequest) -> Dict[str, Any]:
    """
    统一执行接口：执行代码或脚本，并返回更新后的快照

    支持两种模式：
    1. **execute_code 模式**: 提供 code 参数，执行代码字符串
    2. **execute_script 模式**: 提供 script_path 参数，执行 skill 中的脚本

    ## Mode 1: execute_code

    示例 PowerShell 代码（操作已打开的 Excel）:
    ```powershell
    $excel = [Runtime.InteropServices.Marshal]::GetActiveObject("Excel.Application")
    $ws = $excel.ActiveSheet

    # 在当前工作表写入数据
    $ws.Cells(1, 1).Value = "项目"
    $ws.Cells(1, 2).Value = "数量"
    $ws.Cells(1, 3).Value = "价格"

    # 设置表头样式
    $headerRange = $ws.Range("A1:C1")
    $headerRange.Font.Bold = $true
    $headerRange.Interior.Color = 0xFFE699
    ```

    ## Mode 2: execute_script

    示例请求:
    ```json
    {
        "script_path": "scripts/create_column_chart.ps1",
        "parameters": {
            "DataRange": "A1:B10",
            "ChartTitle": "Monthly Sales",
            "ChartLeft": 200,
            "ChartTop": 50
        }
    }
    ```

    Args:
        request.code: 要执行的代码（execute_code 模式）
        request.script_path: 脚本路径（execute_script 模式）
        request.skill_id: Skill ID（execute_script 模式，可选，默认 66666666）
        request.parameters: 脚本参数（execute_script 模式）
        request.language: "PowerShell" 或 "Python"
        request.timeout: 超时时间（秒）
        request.return_screenshot: 是否返回截图
        request.current_sheet_only: 快照是否只返回当前工作表

    Returns:
        {
            "success": true,
            "data": {
                "execution": {
                    "success": true,
                    "output": "...",
                    "error": null,
                    "return_code": 0
                },
                "snapshot": {...}
            }
        }
    """
    # 判断模式
    if request.code:
        mode = "execute_code"
        logger.info(f"[Excel API] step (execute_code): lang={request.language}, code_len={len(request.code)}")
    elif request.script_path:
        mode = "execute_script"
        logger.info(f"[Excel API] step (execute_script): script_path={request.script_path}, skill_id={request.skill_id}, params={request.parameters}")
    else:
        raise HTTPException(status_code=400, detail="Must provide either 'code' or 'script_path'")

    try:
        controller = _get_controller()
        result = await controller.step(
            code=request.code,
            skill_id=request.skill_id,
            script_path=request.script_path,
            parameters=request.parameters,
            language=request.language,
            timeout=request.timeout,
            return_screenshot=request.return_screenshot,
            current_sheet_only=request.current_sheet_only,
            visible_only=request.visible_only
        )
        
        # 如果需要项目文件列表（使用紧凑 text 格式）
        if request.include_project_files and request.project_path:
            try:
                project_tree = format_tree_as_text(
                    project_path=request.project_path,
                    max_depth=request.project_max_depth,
                )
                # 确保 snapshot 存在再赋值
                if result.get("snapshot") is not None:
                    result["snapshot"]["project_files"] = project_tree
                    logger.info(f"[Excel API] step: 附带项目文件列表，长度={len(project_tree)}")
            except Exception as e:
                logger.warning(f"[Excel API] Failed to get project files: {e}")
                if result.get("snapshot") is not None:
                    result["snapshot"]["project_files"] = f"Error: {str(e)}"
        
        # 判断整体成功与否
        success = result["execution"]["success"]
        
        return {
            "success": success,
            "data": result,
            "error": result["execution"]["error"] if not success else None
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[Excel API] step error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
