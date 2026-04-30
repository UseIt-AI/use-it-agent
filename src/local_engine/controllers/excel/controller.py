"""
Excel Controller for Local Engine Architecture

通过 COM 连接到已打开的 Microsoft Excel，支持：
- 获取工作簿快照（内容 + 截图）
- 执行代码操作工作簿
- 用户和 AI 协作编辑
"""

from typing import Dict, Any, List, Optional
from pathlib import Path
import asyncio
import logging
import subprocess
import sys
import tempfile
import base64

logger = logging.getLogger(__name__)


class ExcelController:
    """
    Excel Controller - Microsoft Excel 自动化控制器

    通过 COM 连接到已打开的 Excel 实例，每次操作独立连接。

    Supported Actions:
    - status: 检查 Excel 是否运行
    - snapshot: 获取工作簿快照（内容 + 截图）
    - step: 统一执行接口，支持两种模式：
        * execute_code: 执行代码字符串
        * execute_script: 执行 skill 中的脚本文件
    """

    def __init__(self, skills_base_dir: Optional[str] = None):
        """
        初始化 ExcelController

        Args:
            skills_base_dir: Skills 基础目录（默认：AI_Run/SKILLS）
        """
        # 配置 Skills 目录
        if skills_base_dir:
            self.skills_base_dir = Path(skills_base_dir)
        else:
            # 默认路径：AI_Run/SKILLS
            # 从 engineering_agent/local_engine/controllers/excel/controller.py 向上找到 AI_Run/

            self.skills_base_dir = Path(r"D:\startup\uesit\useit-agent-internal\SKILLS")

        logger.info(f"[ExcelController] Skills base directory: {self.skills_base_dir}")
    
    # ==================== 公共方法 ====================
    
    async def get_status(self) -> Dict[str, Any]:
        """
        检查 Excel 是否运行，获取当前工作簿信息
        
        Returns:
            {
                "running": bool,
                "has_workbook": bool,
                "workbook_info": {...} or None
            }
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._get_status_sync)
    
    async def open_workbook(self, file_path: str, read_only: bool = False) -> Dict[str, Any]:
        """
        打开 Excel 工作簿
        
        如果 Excel 未运行，会自动启动 Excel。
        
        Args:
            file_path: 工作簿路径
            read_only: 是否以只读方式打开
        
        Returns:
            {
                "success": bool,
                "workbook_info": {...} or None,
                "error": str or None
            }
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            self._open_workbook_sync,
            file_path,
            read_only
        )
    
    async def close_workbook(self, save: bool = False) -> Dict[str, Any]:
        """
        关闭当前 Excel 工作簿
        
        Args:
            save: 是否保存工作簿
        
        Returns:
            {
                "success": bool,
                "closed_workbook": str or None,
                "error": str or None
            }
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            self._close_workbook_sync,
            save
        )
    
    async def get_snapshot(
        self,
        include_content: bool = True,
        include_screenshot: bool = True,
        max_rows: Optional[int] = None,
        max_cols: Optional[int] = None,
        current_sheet_only: bool = False,
        visible_only: bool = False
    ) -> Dict[str, Any]:
        """
        获取当前工作簿快照

        Args:
            include_content: 是否包含工作表内容
            include_screenshot: 是否包含截图
            max_rows: 最大行数（None=自动检测使用范围）
            max_cols: 最大列数（None=自动检测使用范围）
            current_sheet_only: 是否只返回当前活动工作表的内容
            visible_only: 是否只返回可见行+上下2行context

        Returns:
            {
                "workbook_info": {...},
                "content": {...},      # 如果 include_content=True
                "screenshot": "base64" # 如果 include_screenshot=True
            }
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            self._get_snapshot_sync,
            include_content,
            include_screenshot,
            max_rows,
            max_cols,
            current_sheet_only,
            visible_only
        )
    
    async def step(
        self,
        code: Optional[str] = None,
        skill_id: Optional[str] = None,
        script_path: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
        language: str = "PowerShell",
        timeout: int = 120,
        return_screenshot: bool = True,
        current_sheet_only: bool = True,
        visible_only: bool = True
    ) -> Dict[str, Any]:
        """
        统一的执行接口：执行代码或脚本，并返回更新后的快照

        根据参数自动判断执行类型：
        - 如果提供 code：执行代码（execute_code）
        - 如果提供 script_path：执行脚本（execute_script）

        Args:
            code: 要执行的代码字符串（execute_code 模式）
            skill_id: Skill ID，如 "66666666"（execute_script 模式）
            script_path: 脚本相对路径，如 "scripts/create_column_chart.ps1"（execute_script 模式）
            parameters: 脚本参数字典（execute_script 模式）
            language: "PowerShell" 或 "Python"
            timeout: 超时时间（秒）
            return_screenshot: 是否返回截图
            current_sheet_only: 快照是否只返回当前工作表内容
            visible_only: Snapshot只返回可见行+上下2行context

        Returns:
            {
                "execution": {
                    "success": bool,
                    "output": str,
                    "error": str or None,
                    "return_code": int
                },
                "snapshot": {...}
            }
        """
        loop = asyncio.get_running_loop()

        try:
            # 激活 Excel 窗口
            await loop.run_in_executor(None, self._activate_excel_window_sync)

            # 判断执行类型
            if code is not None:
                # Mode 1: 执行代码（execute_code）
                logger.info(f"[ExcelController] step() Mode 1: execute_code, code length: {len(code)}")
                execution_result = await loop.run_in_executor(
                    None,
                    self._execute_code_sync,
                    code,
                    language,
                    timeout
                )

            elif script_path is not None:
                # Mode 2: 执行脚本（execute_script）
                logger.info(f"[ExcelController] step() Mode 2: execute_script")
                logger.info(f"  - skill_id: {skill_id or '66666666'}")
                logger.info(f"  - script_path: {script_path}")
                logger.info(f"  - parameters: {parameters}")
                logger.info(f"  - language: {language}")
                logger.info(f"  - timeout: {timeout}")

                # 解析脚本路径
                try:
                    script_full_path = self._get_skill_script_path(skill_id or "66666666", script_path)
                    logger.info(f"[ExcelController] Script resolved to: {script_full_path}")
                except FileNotFoundError as e:
                    logger.error(f"[ExcelController] Script path resolution failed: {e}")
                    raise

                # 构建参数列表
                params = []
                if parameters:
                    if language.lower() == "powershell":
                        params = self._build_powershell_params(parameters)
                        logger.info(f"[ExcelController] PowerShell params built: {params}")
                    elif language.lower() == "python":
                        params = self._build_python_params(parameters)
                        logger.info(f"[ExcelController] Python params built: {params}")
                    else:
                        logger.info(f"[ExcelController] Unknown language '{language}', no params built")
                else:
                    logger.info(f"[ExcelController] No parameters to build")

                # 执行脚本
                logger.info(f"[ExcelController] About to execute script...")
                execution_result = await loop.run_in_executor(
                    None,
                    self._execute_script_file,
                    script_full_path,
                    params,
                    language,
                    timeout
                )
                logger.info(f"[ExcelController] Script execution completed, success={execution_result.get('success')}")

            else:
                error_msg = "Must provide either 'code' or 'script_path'"
                logger.error(f"[ExcelController] {error_msg}")
                raise ValueError(error_msg)

            # 获取更新后的快照
            logger.info(f"[ExcelController] Execution completed, getting snapshot...")
            try:
                snapshot = await loop.run_in_executor(
                    None,
                    self._get_snapshot_sync,
                    True,
                    return_screenshot,
                    None,
                    None,
                    current_sheet_only,
                    visible_only
                )
                logger.info(f"[ExcelController] ✓ Snapshot retrieved successfully")
            except Exception as snapshot_error:
                logger.error(f"[ExcelController] Failed to get snapshot: {snapshot_error}", exc_info=True)
                # 即使快照失败，也返回执行结果
                snapshot = {"error": str(snapshot_error)}

            result = {
                "execution": execution_result,
                "snapshot": snapshot
            }
            logger.info(f"[ExcelController] step() completed: execution_success={execution_result.get('success')}, has_snapshot={snapshot is not None}")
            return result

        except FileNotFoundError as e:
            error_msg = f"Script not found: {e}"
            logger.error(f"[ExcelController] {error_msg}")
            return {
                "execution": {
                    "success": False,
                    "output": "",
                    "error": str(e),
                    "return_code": -1,
                    "error_code": "SCRIPT_NOT_FOUND"
                },
                "snapshot": None
            }
        except Exception as e:
            error_msg = f"Step execution failed: {e}"
            logger.error(f"[ExcelController] {error_msg}", exc_info=True)
            return {
                "execution": {
                    "success": False,
                    "output": "",
                    "error": str(e),
                    "return_code": -1
                },
                "snapshot": None
            }
    
    # ==================== 私有方法 - COM 操作 ====================
    
    def _open_workbook_sync(self, file_path: str, read_only: bool = False) -> Dict[str, Any]:
        """
        同步打开 Excel 工作簿
        
        如果 Excel 未运行，会自动启动。
        如果文件已经打开，会激活该工作簿而不是重新打开。
        """
        import pythoncom
        import win32com.client
        import time
        import os
        
        # 检查文件是否存在
        path = Path(file_path)
        if not path.exists():
            return {
                "success": False,
                "workbook_info": None,
                "error": f"File not found: {file_path}"
            }
        
        # 获取文件的绝对路径（规范化）
        abs_path = str(path.absolute())
        normalized_path = os.path.normpath(abs_path).lower()
        
        pythoncom.CoInitialize()
        try:
            # 尝试连接已运行的 Excel
            try:
                app = win32com.client.GetActiveObject("Excel.Application")
                logger.info("[ExcelController] Connected to existing Excel instance")
                
                # 检查文件是否已经打开
                existing_wb = None
                for i in range(1, app.Workbooks.Count + 1):
                    wb = app.Workbooks(i)
                    # 检查 FullName（完整路径）是否匹配
                    try:
                        wb_full_name = wb.FullName
                        if wb_full_name:
                            wb_path = os.path.normpath(wb_full_name).lower()
                            if wb_path == normalized_path:
                                existing_wb = wb
                                logger.info(f"[ExcelController] Workbook already open: {wb.Name}")
                                break
                    except Exception as e:
                        logger.warning(f"[ExcelController] Failed to get FullName for workbook {i}: {e}")
                        continue
                
                if existing_wb:
                    # 文件已经打开，激活它
                    existing_wb.Activate()
                    
                    workbook_info = self._extract_workbook_info(app, existing_wb)
                    return {
                        "success": True,
                        "workbook_info": workbook_info,
                        "error": None
                    }
                    
            except Exception:
                # Excel 未运行，创建新实例
                logger.info("[ExcelController] Starting new Excel instance")
                app = win32com.client.Dispatch("Excel.Application")
            
            # 确保 Excel 可见
            app.Visible = True
            
            # 打开工作簿
            # Workbooks.Open(Filename, UpdateLinks, ReadOnly, ...)
            wb = app.Workbooks.Open(
                abs_path,
                0,  # UpdateLinks: 0=不更新链接
                read_only  # ReadOnly
            )
            
            # 等待工作簿加载
            time.sleep(0.5)
            
            # 激活窗口
            app.Visible = True
            
            # 获取工作簿信息
            workbook_info = self._extract_workbook_info(app, wb)
            
            logger.info(f"[ExcelController] Opened workbook: {wb.Name}")
            
            return {
                "success": True,
                "workbook_info": workbook_info,
                "error": None
            }
            
        except Exception as e:
            logger.error(f"[ExcelController] Failed to open workbook: {e}", exc_info=True)
            return {
                "success": False,
                "workbook_info": None,
                "error": str(e)
            }
        finally:
            pythoncom.CoUninitialize()
    
    def _close_workbook_sync(self, save: bool = False) -> Dict[str, Any]:
        """
        同步关闭当前 Excel 工作簿
        
        Args:
            save: 是否保存工作簿
        """
        import pythoncom
        import win32com.client
        
        pythoncom.CoInitialize()
        try:
            app = win32com.client.GetActiveObject("Excel.Application")
            
            if app.Workbooks.Count == 0:
                return {
                    "success": False,
                    "closed_workbook": None,
                    "error": "No workbook is open"
                }
            
            wb = app.ActiveWorkbook
            wb_name = wb.Name
            
            # 关闭工作簿
            # Close(SaveChanges, Filename, RouteWorkbook)
            wb.Close(save)
            
            logger.info(f"[ExcelController] Closed workbook: {wb_name}, saved={save}")
            
            return {
                "success": True,
                "closed_workbook": wb_name,
                "error": None
            }
            
        except Exception as e:
            logger.error(f"[ExcelController] Failed to close workbook: {e}", exc_info=True)
            return {
                "success": False,
                "closed_workbook": None,
                "error": str(e)
            }
        finally:
            pythoncom.CoUninitialize()
    
    def _activate_excel_window_sync(self) -> None:
        """
        激活 Excel 窗口（取消最小化、置于前台）
        
        在执行代码前调用，确保用户能看到操作过程
        """
        import pythoncom
        import win32com.client
        import time
        
        pythoncom.CoInitialize()
        try:
            app = win32com.client.GetActiveObject("Excel.Application")
            app = win32com.client.Dispatch(app)

            # 确保 Excel 可见
            app.Visible = True
            
            # 取消最小化 (xlNormal = -4143, xlMinimized = -4140, xlMaximized = -4137)
            try:
                if app.WindowState == -4140:  # xlMinimized
                    app.WindowState = -4143  # xlNormal
            except Exception:
                pass
            
            # 激活窗口（Excel 没有 Activate 方法，但可以通过设置 Visible 和操作窗口）
            try:
                if app.ActiveWindow:
                    app.ActiveWindow.Activate()
            except Exception:
                pass
            
            # 等待窗口激活
            time.sleep(0.2)
            
            logger.info("[ExcelController] Excel window activated")
            
        except Exception as e:
            logger.warning(f"[ExcelController] Failed to activate Excel window: {e}")
            # 不抛出异常，继续执行代码
        finally:
            pythoncom.CoUninitialize()
    
    def _get_status_sync(self) -> Dict[str, Any]:
        """同步获取 Excel 状态"""
        import pythoncom
        import win32com.client
        
        pythoncom.CoInitialize()
        try:
            app = win32com.client.GetActiveObject("Excel.Application")
            app = win32com.client.Dispatch(app)

            has_workbook = app.Workbooks.Count > 0
            workbook_info = None
            
            if has_workbook:
                wb = app.ActiveWorkbook
                workbook_info = self._extract_workbook_info(app, wb)
            
            return {
                "running": True,
                "has_workbook": has_workbook,
                "workbook_info": workbook_info
            }
        except Exception as e:
            logger.info(f"[ExcelController] Excel not running or no access: {e}")
            return {
                "running": False,
                "has_workbook": False,
                "workbook_info": None
            }
        finally:
            pythoncom.CoUninitialize()
    
    def _get_snapshot_sync(
        self,
        include_content: bool,
        include_screenshot: bool,
        max_rows: Optional[int],
        max_cols: Optional[int],
        current_sheet_only: bool = False,
        visible_only: bool = False
    ) -> Dict[str, Any]:
        """同步获取工作簿快照"""
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        try:
            app = win32com.client.GetActiveObject("Excel.Application")
            # Re-wrap via Dispatch to ensure proper COM proxy on this thread
            app = win32com.client.Dispatch(app)

            if app.Workbooks.Count == 0:
                raise ValueError("No workbook is open in Excel")

            wb = app.ActiveWorkbook

            # 1. 工作簿基本信息（包含当前工作表名称）
            workbook_info = self._extract_workbook_info(app, wb)

            result = {
                "workbook_info": workbook_info
            }

            # 2. 工作表内容
            if include_content:
                if current_sheet_only:
                    result["content"] = self._extract_current_sheet_content(app, wb, max_rows, max_cols, visible_only=visible_only)
                else:
                    result["content"] = self._extract_all_sheets_content(wb, max_rows, max_cols)
            
            # 3. 截图
            if include_screenshot:
                screenshot = self._take_screenshot_sync(app, wb)
                if screenshot:
                    result["screenshot"] = screenshot
            
            return result
            
        except Exception as e:
            logger.error(f"[ExcelController] Snapshot error: {e}", exc_info=True)
            raise
        finally:
            pythoncom.CoUninitialize()
    
    def _extract_workbook_info(self, app, wb) -> Dict[str, Any]:
        """提取工作簿基本信息（包含当前工作表名称）"""
        # 获取所有工作表名称
        sheet_names = []
        try:
            for i in range(1, wb.Sheets.Count + 1):
                sheet_names.append(wb.Sheets(i).Name)
        except Exception as e:
            logger.warning(f"[ExcelController] Failed to get sheet names: {e}")
        
        # 获取当前工作表名称
        try:
            current_sheet = app.ActiveSheet.Name if app.ActiveSheet else None
        except Exception as e:
            logger.warning(f"[ExcelController] Failed to get current sheet: {e}")
            current_sheet = None
        
        # 获取当前工作表索引
        current_sheet_index = -1
        if current_sheet and current_sheet in sheet_names:
            current_sheet_index = sheet_names.index(current_sheet) + 1  # 1-based
        
        return {
            "name": wb.Name,
            "path": wb.FullName if wb.Path else None,
            "saved": wb.Saved,
            "current_sheet": current_sheet,
            "current_sheet_index": current_sheet_index,
            "sheet_count": len(sheet_names),
            "sheet_names": sheet_names,
        }
    
    def _extract_all_sheets_content(
        self,
        wb,
        max_rows: Optional[int],
        max_cols: Optional[int]
    ) -> Dict[str, Any]:
        """提取所有工作表的内容"""
        sheets = []
        
        for i in range(1, wb.Sheets.Count + 1):
            try:
                sheet = wb.Sheets(i)
                sheet_info = self._extract_sheet_info(sheet, i, max_rows, max_cols)
                sheets.append(sheet_info)
            except Exception as e:
                logger.warning(f"[ExcelController] Failed to read sheet {i}: {e}")
        
        return {
            "sheets": sheets,
            "total_sheets": wb.Sheets.Count
        }
    
    def _extract_current_sheet_content(
        self,
        app,
        wb,
        max_rows: Optional[int],
        max_cols: Optional[int],
        visible_only: bool = False
    ) -> Dict[str, Any]:
        """
        提取当前活动工作表的内容（包含详细信息）
        """
        try:
            # 获取当前工作表
            current_sheet = app.ActiveSheet
            current_sheet_name = current_sheet.Name

            total_sheets = wb.Sheets.Count

            # 获取当前工作表索引
            current_sheet_index = -1
            for i in range(1, total_sheets + 1):
                if wb.Sheets(i).Name == current_sheet_name:
                    current_sheet_index = i
                    break

            # 获取当前工作表的详细信息
            sheet_info = self._extract_sheet_info(current_sheet, current_sheet_index, max_rows, max_cols, detailed=True, visible_only=visible_only)
            
            # 获取所有工作表的摘要（方便 AI 理解完整上下文）
            all_sheets_summary = []
            for i in range(1, total_sheets + 1):
                try:
                    sheet = wb.Sheets(i)
                    used_range = sheet.UsedRange
                    all_sheets_summary.append({
                        "index": i,
                        "name": sheet.Name,
                        "used_rows": used_range.Rows.Count if used_range else 0,
                        "used_cols": used_range.Columns.Count if used_range else 0
                    })
                except Exception:
                    all_sheets_summary.append({
                        "index": i,
                        "name": None,
                        "used_rows": 0,
                        "used_cols": 0
                    })
            
            logger.info(f"[ExcelController] Current sheet: {current_sheet_name} ({current_sheet_index}/{total_sheets})")
            
            return {
                "current_sheet": sheet_info,
                "current_sheet_index": current_sheet_index,
                "current_sheet_name": current_sheet_name,
                "total_sheets": total_sheets,
                "all_sheets_summary": all_sheets_summary
            }
            
        except Exception as e:
            logger.error(f"[ExcelController] Failed to extract current sheet content: {e}", exc_info=True)
            # 降级到提取所有工作表
            return self._extract_all_sheets_content(wb, max_rows, max_cols)
    
    def _extract_sheet_info(
        self,
        sheet,
        index: int,
        max_rows: Optional[int],
        max_cols: Optional[int],
        detailed: bool = False,
        visible_only: bool = False,
        context_rows: int = 2
    ) -> Dict[str, Any]:
        """
        提取工作表的详细信息

        Args:
            sheet: Excel Worksheet 对象
            index: 工作表索引
            max_rows: 最大行数
            max_cols: 最大列数
            detailed: 是否提取详细信息
            visible_only: 是否只返回可见行+上下context行
            context_rows: visible_only模式下上下额外行数

        Returns:
            包含工作表详细信息的字典
        """
        info = {
            "index": index,
            "name": sheet.Name,
            "used_range": {},
            "data": [],
            "formulas": [],
            "merged_cells": [],
            "charts": []
        }

        try:
            # 获取使用范围
            used_range = sheet.UsedRange
            if used_range:
                total_rows = used_range.Rows.Count
                total_cols = used_range.Columns.Count

                info["used_range"] = {
                    "start_row": used_range.Row,
                    "start_col": used_range.Column,
                    "rows": total_rows,
                    "cols": total_cols,
                    "address": used_range.Address
                }

                # 计算实际读取范围
                actual_cols = total_cols
                if max_cols:
                    actual_cols = min(actual_cols, max_cols)
                actual_cols = min(actual_cols, 26)

                start_col = used_range.Column

                if visible_only:
                    # visible_only 模式：只读取可见行 + 上下 context_rows 行
                    window = sheet.Application.ActiveWindow
                    vis = window.VisibleRange
                    first_vis_row = vis.Row
                    last_vis_row = first_vis_row + vis.Rows.Count - 1

                    used_start = used_range.Row
                    used_end = used_range.Row + total_rows - 1

                    start_row = max(used_start, first_vis_row - context_rows)
                    end_row = min(used_end, last_vis_row + context_rows)
                    actual_rows = end_row - start_row + 1

                    # Always include header row (row 1 or used_range start) if not already in range
                    include_header_separately = (start_row > used_start)

                    info["visible_range"] = {
                        "first_visible_row": first_vis_row,
                        "last_visible_row": last_vis_row,
                        "start_row_with_context": start_row,
                        "end_row_with_context": end_row,
                        "header_included_separately": include_header_separately,
                    }
                else:
                    # 默认模式：从 used_range 开始读取
                    actual_rows = total_rows
                    if max_rows:
                        actual_rows = min(actual_rows, max_rows)
                    actual_rows = min(actual_rows, 100)
                    start_row = used_range.Row
                    include_header_separately = False

                # 如果需要单独包含 header 行（visible_only 模式下 header 不在可见范围内）
                header_data = None
                if visible_only and include_header_separately:
                    header_range = sheet.Range(
                        sheet.Cells(used_range.Row, start_col),
                        sheet.Cells(used_range.Row, start_col + actual_cols - 1)
                    )
                    raw_header = header_range.Value
                    header_data = self._normalize_range_values(raw_header, 1, actual_cols)

                # 获取要读取的范围
                read_range = sheet.Range(
                    sheet.Cells(start_row, start_col),
                    sheet.Cells(start_row + actual_rows - 1, start_col + actual_cols - 1)
                )
                
                # 批量读取值和公式
                raw_values = read_range.Value
                raw_formulas = read_range.Formula

                # 处理返回值（可能是单个值、一维元组或二维元组）
                data = self._normalize_range_values(raw_values, actual_rows, actual_cols)
                formulas = self._extract_formulas_from_range(raw_formulas, actual_rows, actual_cols)

                # 如果有单独的 header 行，插到 data 最前面
                if header_data:
                    data = header_data + data

                info["data"] = data
                info["formulas"] = formulas[:50]  # 限制公式数量，避免 token 过多

                # 记录数据起始行号（让 AI 知道 data[0] 对应 Excel 的哪一行）
                if visible_only:
                    if header_data:
                        info["data_start_row"] = used_range.Row  # header row
                        info["data_row_mapping"] = (
                            f"Row 0 = Excel row {used_range.Row} (header), "
                            f"Row 1..{len(data)-1} = Excel rows {start_row}..{start_row + actual_rows - 1}"
                        )
                    else:
                        info["data_start_row"] = start_row
                        info["data_row_mapping"] = (
                            f"Row 0..{len(data)-1} = Excel rows {start_row}..{start_row + actual_rows - 1}"
                        )

                # 标记是否被截断
                info["truncated"] = (total_rows > actual_rows or total_cols > actual_cols)
                if info["truncated"]:
                    info["truncated_info"] = {
                        "original_rows": total_rows,
                        "original_cols": total_cols,
                        "returned_rows": actual_rows,
                        "returned_cols": actual_cols
                    }
                
        except Exception as e:
            logger.warning(f"[ExcelController] Failed to read used range: {e}")
        
        # 获取合并单元格信息
        if detailed:
            try:
                merged_areas = sheet.UsedRange.MergeCells
                if merged_areas:
                    # 遍历所有合并区域
                    for area in sheet.UsedRange.MergeArea:
                        info["merged_cells"].append({
                            "address": area.Address,
                            "rows": area.Rows.Count,
                            "cols": area.Columns.Count
                        })
            except Exception:
                pass
        
        # 获取图表信息
        try:
            for i in range(1, sheet.ChartObjects().Count + 1):
                chart_obj = sheet.ChartObjects(i)
                info["charts"].append({
                    "index": i,
                    "name": chart_obj.Name,
                    "left": chart_obj.Left,
                    "top": chart_obj.Top,
                    "width": chart_obj.Width,
                    "height": chart_obj.Height
                })
        except Exception:
            pass
        
        return info
    
    def _normalize_range_values(self, raw_values, rows: int, cols: int) -> List[List[Any]]:
        """
        规范化 Range.Value 返回的数据
        
        Range.Value 可能返回：
        - None: 空范围
        - 单个值: 1x1 范围
        - 一维元组: 1xN 或 Nx1 范围
        - 二维元组: MxN 范围
        
        统一转换为二维列表
        """
        if raw_values is None:
            return [[None] * cols for _ in range(rows)]
        
        # 单个值
        if not isinstance(raw_values, tuple):
            return [[self._normalize_cell_value(raw_values)]]
        
        # 一维元组（单行或单列）
        if not isinstance(raw_values[0], tuple):
            # 单行
            if rows == 1:
                return [[self._normalize_cell_value(v) for v in raw_values]]
            # 单列
            else:
                return [[self._normalize_cell_value(v)] for v in raw_values]
        
        # 二维元组
        result = []
        for row_data in raw_values:
            result.append([self._normalize_cell_value(v) for v in row_data])
        return result
    
    def _normalize_cell_value(self, value) -> Any:
        """规范化单个单元格的值"""
        if value is None:
            return None
        
        # 处理日期
        if hasattr(value, 'strftime'):
            return value.strftime('%Y-%m-%d %H:%M:%S')
        
        # 处理浮点数（如果是整数则转为整数）
        if isinstance(value, float):
            if value == int(value):
                return int(value)
            # 限制小数位数
            return round(value, 6)
        
        # 字符串限制长度（避免超长文本占用太多 token）
        if isinstance(value, str) and len(value) > 200:
            return value[:200] + "..."
        
        return value
    
    def _extract_formulas_from_range(self, raw_formulas, rows: int, cols: int) -> List[Dict[str, Any]]:
        """
        从 Range.Formula 返回的数据中提取公式
        
        只返回包含公式的单元格（以 = 开头）
        """
        formulas = []
        
        if raw_formulas is None:
            return formulas
        
        # 单个值
        if not isinstance(raw_formulas, tuple):
            if isinstance(raw_formulas, str) and raw_formulas.startswith('='):
                formulas.append({"row": 1, "col": 1, "formula": raw_formulas})
            return formulas
        
        # 一维元组
        if not isinstance(raw_formulas[0], tuple):
            for i, f in enumerate(raw_formulas):
                if isinstance(f, str) and f.startswith('='):
                    if rows == 1:
                        formulas.append({"row": 1, "col": i + 1, "formula": f})
                    else:
                        formulas.append({"row": i + 1, "col": 1, "formula": f})
            return formulas
        
        # 二维元组
        for r, row_data in enumerate(raw_formulas):
            for c, f in enumerate(row_data):
                if isinstance(f, str) and f.startswith('='):
                    formulas.append({"row": r + 1, "col": c + 1, "formula": f})
        
        return formulas
    
    def _take_screenshot_sync(self, app, wb) -> Optional[str]:
        """
        截取 Excel 窗口截图
        
        使用 PIL.ImageGrab 截取 Excel 窗口区域，并压缩到 ~300KB
        """
        try:
            import win32gui
            import ctypes
            from ctypes import wintypes
            from PIL import ImageGrab
            import time
            from controllers.computer_use.win_executor.handlers.image_utils import compress_screenshot_from_pil
            
            # Excel 的窗口句柄获取
            hwnd = None
            
            # 方法1: 通过窗口标题查找
            def find_excel_window(hwnd_candidate, _):
                nonlocal hwnd
                try:
                    title = win32gui.GetWindowText(hwnd_candidate)
                    # Excel 窗口标题通常包含工作簿名称和 "Excel"
                    if "Excel" in title and win32gui.IsWindowVisible(hwnd_candidate):
                        hwnd = hwnd_candidate
                        return False  # 停止枚举
                except Exception:
                    pass
                return True  # 继续枚举
            
            win32gui.EnumWindows(find_excel_window, None)
            
            if not hwnd:
                # 方法2: 尝试直接从 Application 获取
                try:
                    hwnd = int(app.Hwnd)
                except Exception:
                    pass
            
            if not hwnd:
                logger.warning("[ExcelController] Could not find Excel window handle")
                return None
            
            # 将窗口置于前台并等待一下
            try:
                win32gui.SetForegroundWindow(hwnd)
                time.sleep(0.3)  # 等待窗口激活
            except Exception:
                pass  # 可能失败，继续尝试截图
            
            # 使用 DwmGetWindowAttribute 获取不含阴影的窗口区域
            try:
                # DWMWA_EXTENDED_FRAME_BOUNDS = 9
                rect = wintypes.RECT()
                DWMWA_EXTENDED_FRAME_BOUNDS = 9
                ctypes.windll.dwmapi.DwmGetWindowAttribute(
                    hwnd,
                    DWMWA_EXTENDED_FRAME_BOUNDS,
                    ctypes.byref(rect),
                    ctypes.sizeof(rect)
                )
                left, top, right, bottom = rect.left, rect.top, rect.right, rect.bottom
            except Exception:
                # 降级到普通方法
                left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            
            # 使用 ImageGrab 截取指定区域
            img = ImageGrab.grab(bbox=(left, top, right, bottom))
            original_size = f"{right-left}x{bottom-top}"
            
            # 压缩截图（长边超过 1568 则缩放到 1400，JPEG 压缩到 ~300KB）
            compressed_bytes = compress_screenshot_from_pil(img)
            base64_str = base64.b64encode(compressed_bytes).decode('utf-8')
            
            logger.info(f"[ExcelController] Screenshot captured: {original_size}, compressed to {len(compressed_bytes)/1024:.1f}KB")
            return base64_str
            
        except Exception as e:
            logger.warning(f"[ExcelController] Screenshot failed: {e}", exc_info=True)
            return None
    
    # ==================== 私有方法 - 代码执行 ====================
    
    def _execute_code_sync(
        self,
        code: str,
        language: str,
        timeout: int
    ) -> Dict[str, Any]:
        """
        同步执行代码
        
        Returns:
            {
                "success": bool,
                "output": str,
                "error": str or None,
                "return_code": int
            }
        """
        code_file = None
        
        try:
            # 创建临时文件
            suffix = ".ps1" if language.lower() == "powershell" else ".py"
            encoding = 'utf-8-sig' if language.lower() == "powershell" else 'utf-8'
            
            with tempfile.NamedTemporaryFile(
                mode='w',
                suffix=suffix,
                delete=False,
                encoding=encoding
            ) as f:
                f.write(code)
                code_file = f.name
            
            logger.info(f"[ExcelController] Code written to: {code_file}")
            
            # 执行代码
            if language.lower() == "powershell":
                cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-File", code_file]
            else:
                cmd = [sys.executable, code_file]
            
            logger.info(f"[ExcelController] Executing: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding='utf-8',
                errors='replace'
            )
            
            if result.returncode == 0:
                logger.info("[ExcelController] Code execution successful")
                return {
                    "success": True,
                    "output": result.stdout,
                    "error": None,
                    "return_code": result.returncode
                }
            else:
                logger.error(f"[ExcelController] Code execution failed: {result.stderr}")
                return {
                    "success": False,
                    "output": result.stdout,
                    "error": result.stderr,
                    "return_code": result.returncode
                }
        
        except subprocess.TimeoutExpired:
            logger.error(f"[ExcelController] Code execution timeout after {timeout}s")
            return {
                "success": False,
                "output": "",
                "error": f"Execution timeout after {timeout} seconds",
                "return_code": -1
            }
        except Exception as e:
            logger.error(f"[ExcelController] Code execution error: {e}", exc_info=True)
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "return_code": -1
            }
        finally:
            # 清理临时文件
            if code_file:
                try:
                    Path(code_file).unlink()
                except Exception:
                    pass

    # ==================== 私有方法 - Skill 脚本执行 ====================

    def _get_skill_script_path(self, skill_id: str, script_path: str) -> Path:
        r"""
        获取 skill 脚本的完整路径

        Args:
            skill_id: "66666666"
            script_path: "scripts/create_column_chart.ps1"

        Returns:
            Path: D:\develop\Useit-New\AI_Run\SKILLS\skill-66666666\scripts\create_column_chart.ps1

        Raises:
            FileNotFoundError: 如果 skill 目录或脚本文件不存在
        """
        logger.info(f"[ExcelController] Resolving script path...")
        logger.info(f"  skills_base_dir: {self.skills_base_dir}")
        logger.info(f"  skill_id: {skill_id}")
        logger.info(f"  script_path: {script_path}")

        # 构建 skill 目录路径（兼容两种命名格式）
        # 1. 先尝试直接用 skill_id 作为目录名（如 "preliminary-engineering-calculations"）
        # 2. 再尝试 "skill-{id}" 格式（如 "skill-66666666"）
        skill_dir = self.skills_base_dir / skill_id
        if not skill_dir.exists():
            skill_dir = self.skills_base_dir / f"skill-{skill_id}"
        logger.info(f"  skill_dir: {skill_dir}")

        if not skill_dir.exists():
            error_msg = f"Skill directory not found: tried '{skill_id}' and 'skill-{skill_id}' under {self.skills_base_dir}"
            logger.error(f"[ExcelController] {error_msg}")
            raise FileNotFoundError(error_msg)

        logger.info(f"[ExcelController] ✓ Skill directory exists")

        # 构建脚本完整路径
        script_full_path = skill_dir / script_path
        logger.info(f"  script_full_path: {script_full_path}")

        if not script_full_path.exists():
            error_msg = f"Script not found: {script_full_path}"
            logger.error(f"[ExcelController] {error_msg}")
            # 列出目录内容帮助调试
            try:
                contents = list(skill_dir.glob("**/*"))
                logger.error(f"[ExcelController] Available files in skill directory:")
                for item in contents[:20]:  # 限制显示前 20 个
                    logger.error(f"  - {item.relative_to(skill_dir)}")
            except Exception as e:
                logger.error(f"[ExcelController] Could not list directory contents: {e}")
            raise FileNotFoundError(error_msg)

        logger.info(f"[ExcelController] ✓ Script file exists: {script_full_path}")
        return script_full_path

    def _build_powershell_params(self, parameters: Dict[str, Any]) -> List[str]:
        """
        将参数字典转换为 PowerShell 命令行参数

        Args:
            parameters: {
                "DataRange": "A1:C6",
                "ChartTitle": "Monthly Sales",
                "ChartLeft": 200,
                "ShowMarkers": True
            }

        Returns:
            ["-DataRange", "A1:C6", "-ChartTitle", "Monthly Sales", "-ChartLeft", "200", "-ShowMarkers", "$true"]
        """
        logger.info(f"[ExcelController] Building PowerShell params from: {parameters}")
        params = []

        for key, value in parameters.items():
            params.append(f"-{key}")

            # 类型转换
            if isinstance(value, bool):
                params.append("$true" if value else "$false")
            elif isinstance(value, str):
                # subprocess.run with list handles quoting automatically on Windows
                params.append(value)
            else:
                # 数字直接转字符串
                params.append(str(value))

        logger.info(f"[ExcelController] PowerShell params built: {params}")
        logger.info(f"[ExcelController] Command line args: {' '.join(params)}")
        return params

    def _build_python_params(self, parameters: Dict[str, Any]) -> List[str]:
        """
        将参数字典转换为 Python 命令行参数

        支持两种传递方式：
        - 如果只有一个参数且 key 是 "json"，则直接传递 JSON 字符串
        - 否则转换为 --key value 格式

        Args:
            parameters: {
                "targetRow": 3,
                "Layout": "B",
                "verbose": True
            }

        Returns:
            ["--targetRow", "3", "--Layout", "B", "--verbose"]
        """
        import json as json_module

        logger.info(f"[ExcelController] Building Python params from: {parameters}")
        params = []

        for key, value in parameters.items():
            if isinstance(value, bool):
                if value:
                    params.append(f"--{key}")
                # False booleans: skip (argparse store_true pattern)
            else:
                params.append(f"--{key}")
                if isinstance(value, (dict, list)):
                    params.append(json_module.dumps(value, ensure_ascii=False))
                else:
                    params.append(str(value))

        logger.info(f"[ExcelController] Python params built: {params}")
        return params

    def _execute_script_file(
        self,
        script_path: Path,
        params: List[str],
        language: str,
        timeout: int
    ) -> Dict[str, Any]:
        """
        执行脚本文件（已存在的文件，不是临时代码）

        与 _execute_code_sync 的区别：
        - _execute_code_sync: 接收代码字符串，创建临时文件执行
        - _execute_script_file: 接收已存在的文件路径，直接执行

        Args:
            script_path: 脚本文件完整路径
            params: 命令行参数列表
            language: "PowerShell" 或 "Python"
            timeout: 超时时间

        Returns:
            {
                "success": bool,
                "output": str,
                "error": str or None,
                "return_code": int
            }
        """
        try:
            # 构建命令
            if language.lower() == "powershell":
                # 使用 -Command 包装，先设置 UTF-8 编码再执行脚本
                # 这样可以确保输出是 UTF-8 编码，避免中文乱码
                params_str = ' '.join(params) if params else ''
                ps_command = f'[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; & "{script_path}" {params_str}'
                cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-Command", ps_command]
            else:
                cmd = [sys.executable, str(script_path)] + params

            logger.info(f"[ExcelController] Executing script...")
            logger.info(f"  Script path: {script_path}")
            logger.info(f"  Command: {' '.join(cmd)}")
            logger.info(f"  Timeout: {timeout}s")

            # 执行命令
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding='utf-8',
                errors='replace'
            )

            # 详细记录执行结果
            logger.info(f"[ExcelController] Script execution completed:")
            logger.info(f"  Return code: {result.returncode}")
            logger.info(f"  Stdout length: {len(result.stdout)} chars")
            logger.info(f"  Stderr length: {len(result.stderr)} chars")

            if result.returncode == 0:
                logger.info("[ExcelController] ✓ Script execution successful")
                if result.stdout:
                    logger.info(f"[ExcelController] Stdout: {result.stdout[:500]}")
                return {
                    "success": True,
                    "output": result.stdout,
                    "error": None,
                    "return_code": result.returncode
                }
            else:
                logger.error(f"[ExcelController] ✗ Script execution failed (return code: {result.returncode})")
                if result.stdout:
                    logger.error(f"[ExcelController] Stdout: {result.stdout}")
                if result.stderr:
                    logger.error(f"[ExcelController] Stderr: {result.stderr}")
                
                # 构建详细的错误信息，包含 stdout 和 stderr，方便 agent debug
                error_parts = []
                if result.stderr:
                    error_parts.append(f"[stderr] {result.stderr.strip()}")
                if result.stdout:
                    # stdout 可能包含脚本的错误输出（如 Write-Host "Error: ..."）
                    error_parts.append(f"[stdout] {result.stdout.strip()}")
                if not error_parts:
                    error_parts.append(f"Script failed with return code {result.returncode}")
                
                detailed_error = "\n".join(error_parts)
                
                return {
                    "success": False,
                    "output": result.stdout,
                    "error": detailed_error,
                    "return_code": result.returncode
                }

        except subprocess.TimeoutExpired:
            logger.error(f"[ExcelController] Script execution timeout after {timeout}s")
            return {
                "success": False,
                "output": "",
                "error": f"Execution timeout after {timeout} seconds",
                "return_code": -1
            }
        except Exception as e:
            logger.error(f"[ExcelController] Script execution error: {e}", exc_info=True)
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "return_code": -1
            }
