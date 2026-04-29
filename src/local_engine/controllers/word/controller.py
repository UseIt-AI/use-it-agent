"""
Word Controller for Local Engine Architecture

通过 COM 连接到已打开的 Microsoft Word，支持三层执行架构：
- Layer 1: 结构化 Actions（WordActionExecutor，进程内 COM）—— 下一个 batch
- Layer 2: 预置 Skill 脚本（通过 shared.skill_executor）
- Layer 3: 原始代码（subprocess 执行 PowerShell / Python，兜底）

同时提供 status / open / close / snapshot 基础能力。
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from controllers.shared.skill_executor import (
    DEFAULT_SKILLS_BASE_DIR,
    build_params,
    execute_script_file,
    resolve_skill_script,
)

from .constants import (
    WD_DO_NOT_SAVE_CHANGES,
    WD_SAVE_CHANGES,
    WD_WINDOW_STATE_MINIMIZE,
    WD_WINDOW_STATE_NORMAL,
)
from .snapshot_extractor import SnapshotExtractor, SnapshotScope

logger = logging.getLogger(__name__)


class WordController:
    """
    Microsoft Word 自动化控制器。

    Public Methods:
    - get_status()          检查 Word 是否运行
    - open_document()       打开文档（已打开则激活）
    - close_document()      关闭当前文档
    - get_snapshot()        获取文档快照（多种 scope）
    - execute_code()        Layer 3：执行 PowerShell/Python 代码
    - execute_script()      Layer 2：执行预置 Skill 脚本
    - execute_actions()     Layer 1：执行结构化 actions —— 占位，batch 2 实现
    """

    def __init__(self):
        self._snapshot = SnapshotExtractor()
        self._action_executor = None  # batch 2 会注入 WordActionExecutor

    # ==================== 对外 async 入口 ====================

    async def get_status(self) -> Dict[str, Any]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._get_status_sync)

    async def open_document(
        self, file_path: str, read_only: bool = False
    ) -> Dict[str, Any]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._open_document_sync, file_path, read_only
        )

    async def close_document(self, save: bool = False) -> Dict[str, Any]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._close_document_sync, save)

    async def get_snapshot(
        self,
        scope: SnapshotScope = "current_page",
        paragraph_range: Optional[Tuple[int, int]] = None,
        max_paragraphs: Optional[int] = None,
        include_content: bool = True,
        include_screenshot: bool = True,
        include_outline: bool = False,
        include_styles: bool = False,
        include_bookmarks: bool = False,
        include_toc: bool = False,
    ) -> Dict[str, Any]:
        """
        获取当前文档快照。

        scope 用法（见 SnapshotExtractor 的文档字符串）：
        - outline_only / current_page / current_section / selection / paragraph_range / full

        paragraph_range 仅在 scope='paragraph_range' 时使用，(para_start, para_end) 1-based 闭区间。
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            self._get_snapshot_sync,
            scope,
            paragraph_range,
            max_paragraphs,
            include_content,
            include_screenshot,
            include_outline,
            include_styles,
            include_bookmarks,
            include_toc,
        )

    async def execute_code(
        self,
        code: str,
        language: str = "PowerShell",
        timeout: int = 120,
        return_screenshot: bool = True,
        snapshot_scope: SnapshotScope = "current_page",
    ) -> Dict[str, Any]:
        """Layer 3：执行原始代码（subprocess）并返回更新后的快照。"""
        return await self._execute_and_snapshot(
            self._execute_code_sync,
            [code, language, timeout],
            return_screenshot,
            snapshot_scope,
        )

    async def execute_script(
        self,
        skill_id: str,
        script_path: str,
        parameters: Optional[Dict[str, Any]] = None,
        language: str = "PowerShell",
        timeout: int = 120,
        return_screenshot: bool = True,
        snapshot_scope: SnapshotScope = "current_page",
    ) -> Dict[str, Any]:
        """
        Layer 2：执行预置 Skill 脚本并返回更新后的快照。

        skill_id + script_path 由 shared.skill_executor 解析成绝对路径后
        subprocess 执行。对齐 PPT 的 execute_script 实现。
        """
        return await self._execute_and_snapshot(
            self._execute_script_sync,
            [skill_id, script_path, parameters or {}, language, timeout],
            return_screenshot,
            snapshot_scope,
        )

    async def execute_actions(
        self,
        actions: List[Dict[str, Any]],
        return_screenshot: bool = True,
        snapshot_scope: SnapshotScope = "current_page",
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Layer 1：执行结构化 actions —— 占位实现。

        batch 2 会接入 WordActionExecutor。当前先返回明确错误，避免 AI 误以为
        能用。dry_run 字段预留，先占位不生效。
        """
        return {
            "execution": {
                "success": False,
                "results": [],
                "error": (
                    "Layer 1 (structured actions) not yet implemented. "
                    "Use execute_code (Layer 3) or execute_script (Layer 2) for now."
                ),
                "not_implemented": True,
            },
            "snapshot": await self.get_snapshot(scope=snapshot_scope, include_screenshot=return_screenshot),
        }

    # ==================== 执行管线骨架（对齐 PPT） ====================

    async def _execute_and_snapshot(
        self,
        sync_fn,
        sync_args: list,
        return_screenshot: bool,
        snapshot_scope: SnapshotScope,
    ) -> Dict[str, Any]:
        """激活窗口 → 执行 → 快照。"""
        loop = asyncio.get_running_loop()

        await loop.run_in_executor(None, self._activate_word_window_sync)

        execution_result = await loop.run_in_executor(None, sync_fn, *sync_args)

        snapshot = await loop.run_in_executor(
            None,
            self._get_snapshot_sync,
            snapshot_scope,
            None,     # paragraph_range
            None,     # max_paragraphs
            True,     # include_content
            return_screenshot,
            False, False, False, False,  # outline/styles/bookmarks/toc
        )

        return {"execution": execution_result, "snapshot": snapshot}

    # ==================== 同步 COM 实现 ====================

    def _get_status_sync(self) -> Dict[str, Any]:
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        try:
            app = win32com.client.GetActiveObject("Word.Application")
            has_document = app.Documents.Count > 0
            document_info = None
            if has_document:
                document_info = self._snapshot.extract_document_info(app, app.ActiveDocument)
            return {
                "running": True,
                "has_document": has_document,
                "document_info": document_info,
            }
        except Exception as e:
            logger.info(f"[WordController] Word not running or no access: {e}")
            return {"running": False, "has_document": False, "document_info": None}
        finally:
            pythoncom.CoUninitialize()

    def _get_snapshot_sync(
        self,
        scope: SnapshotScope,
        paragraph_range: Optional[Tuple[int, int]],
        max_paragraphs: Optional[int],
        include_content: bool,
        include_screenshot: bool,
        include_outline: bool,
        include_styles: bool,
        include_bookmarks: bool,
        include_toc: bool,
    ) -> Dict[str, Any]:
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        try:
            app = win32com.client.GetActiveObject("Word.Application")
            if app.Documents.Count == 0:
                raise ValueError("No document is open in Word")
            doc = app.ActiveDocument
            return self._snapshot.get_snapshot(
                app, doc,
                scope=scope,
                paragraph_range=paragraph_range,
                max_paragraphs=max_paragraphs,
                include_content=include_content,
                include_screenshot=include_screenshot,
                include_outline=include_outline,
                include_styles=include_styles,
                include_bookmarks=include_bookmarks,
                include_toc=include_toc,
            )
        except Exception as e:
            logger.error(f"[WordController] Snapshot error: {e}", exc_info=True)
            raise
        finally:
            pythoncom.CoUninitialize()

    def _activate_word_window_sync(self) -> None:
        """激活 Word 窗口 —— 把最小化的 Word 恢复正常，确保用户看得到进度。"""
        import time

        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        try:
            app = win32com.client.GetActiveObject("Word.Application")
            app.Visible = True
            if app.ActiveWindow.WindowState == WD_WINDOW_STATE_MINIMIZE:
                app.ActiveWindow.WindowState = WD_WINDOW_STATE_NORMAL
            app.Activate()
            time.sleep(0.2)
            logger.info("[WordController] Word window activated")
        except Exception as e:
            logger.warning(f"[WordController] Failed to activate Word window: {e}")
        finally:
            pythoncom.CoUninitialize()

    def _open_document_sync(
        self, file_path: str, read_only: bool = False
    ) -> Dict[str, Any]:
        import os
        import time

        import pythoncom
        import win32com.client

        path = Path(file_path)
        if not path.exists():
            return {
                "success": False,
                "document_info": None,
                "error": f"File not found: {file_path}",
            }

        abs_path = str(path.absolute())
        normalized_path = os.path.normpath(abs_path).lower()

        pythoncom.CoInitialize()
        try:
            try:
                app = win32com.client.GetActiveObject("Word.Application")
                logger.info("[WordController] Connected to existing Word instance")

                # 检查文件是否已经打开
                existing_doc = None
                for i in range(1, app.Documents.Count + 1):
                    doc = app.Documents(i)
                    try:
                        full_name = doc.FullName
                        if full_name and os.path.normpath(full_name).lower() == normalized_path:
                            existing_doc = doc
                            logger.info(f"[WordController] Document already open: {doc.Name}")
                            break
                    except Exception as e:
                        logger.warning(f"[WordController] Failed to read FullName for doc {i}: {e}")
                        continue

                if existing_doc:
                    existing_doc.Activate()
                    return {
                        "success": True,
                        "document_info": self._snapshot.extract_document_info(app, existing_doc),
                        "error": None,
                    }

            except Exception:
                logger.info("[WordController] Starting new Word instance")
                app = win32com.client.Dispatch("Word.Application")

            app.Visible = True
            doc = app.Documents.Open(abs_path, False, read_only)
            time.sleep(1)
            app.Activate()

            return {
                "success": True,
                "document_info": self._snapshot.extract_document_info(app, doc),
                "error": None,
            }
        except Exception as e:
            logger.error(f"[WordController] Failed to open document: {e}", exc_info=True)
            return {"success": False, "document_info": None, "error": str(e)}
        finally:
            pythoncom.CoUninitialize()

    def _close_document_sync(self, save: bool = False) -> Dict[str, Any]:
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        try:
            app = win32com.client.GetActiveObject("Word.Application")
            if app.Documents.Count == 0:
                return {
                    "success": False,
                    "closed_document": None,
                    "error": "No document is open",
                }
            doc = app.ActiveDocument
            doc_name = doc.Name
            doc.Close(WD_SAVE_CHANGES if save else WD_DO_NOT_SAVE_CHANGES)
            logger.info(f"[WordController] Closed document: {doc_name}, saved={save}")
            return {"success": True, "closed_document": doc_name, "error": None}
        except Exception as e:
            logger.error(f"[WordController] Failed to close document: {e}", exc_info=True)
            return {"success": False, "closed_document": None, "error": str(e)}
        finally:
            pythoncom.CoUninitialize()

    # ==================== Layer 3: 原始代码 ====================

    def _execute_code_sync(
        self, code: str, language: str, timeout: int
    ) -> Dict[str, Any]:
        """同步执行代码（写临时文件 + subprocess），返回 execution result。"""
        code_file = None
        try:
            suffix = ".ps1" if language.lower() == "powershell" else ".py"
            encoding = "utf-8-sig" if language.lower() == "powershell" else "utf-8"

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=suffix, delete=False, encoding=encoding,
            ) as f:
                f.write(code)
                code_file = f.name

            logger.info(f"[WordController] Code written to: {code_file}")

            if language.lower() == "powershell":
                cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-File", code_file]
            else:
                cmd = [sys.executable, code_file]

            logger.info(f"[WordController] Executing: {' '.join(cmd)}")
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=timeout, encoding="utf-8", errors="replace",
            )

            if result.returncode == 0:
                logger.info("[WordController] Code execution successful")
                return {
                    "success": True,
                    "output": result.stdout,
                    "error": None,
                    "return_code": result.returncode,
                }
            logger.error(f"[WordController] Code execution failed: {result.stderr}")
            return {
                "success": False,
                "output": result.stdout,
                "error": result.stderr,
                "return_code": result.returncode,
            }

        except subprocess.TimeoutExpired:
            logger.error(f"[WordController] Code execution timeout after {timeout}s")
            return {
                "success": False, "output": "",
                "error": f"Execution timeout after {timeout} seconds",
                "return_code": -1,
            }
        except Exception as e:
            logger.error(f"[WordController] Code execution error: {e}", exc_info=True)
            return {"success": False, "output": "", "error": str(e), "return_code": -1}
        finally:
            if code_file:
                try:
                    Path(code_file).unlink()
                except Exception:
                    pass

    # ==================== Layer 2: Skill 脚本 ====================

    def _execute_script_sync(
        self,
        skill_id: str,
        script_path: str,
        parameters: Dict[str, Any],
        language: str,
        timeout: int,
    ) -> Dict[str, Any]:
        """通过 shared.skill_executor 解析 + subprocess 执行预置 Skill。"""
        try:
            full_path = resolve_skill_script(DEFAULT_SKILLS_BASE_DIR, skill_id, script_path)
            params = build_params(parameters, language)
            return execute_script_file(full_path, params, language, timeout)
        except FileNotFoundError as e:
            logger.error(f"[WordController] Skill script not found: {e}")
            return {"success": False, "output": "", "error": str(e), "return_code": -1}
        except Exception as e:
            logger.error(f"[WordController] execute_script error: {e}", exc_info=True)
            return {"success": False, "output": "", "error": str(e), "return_code": -1}
