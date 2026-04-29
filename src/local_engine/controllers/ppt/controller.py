"""
PowerPoint Controller for Local Engine Architecture

通过 COM 连接到已打开的 Microsoft PowerPoint，支持：
- 获取演示文稿快照（内容 + 截图）
- 执行结构化 Actions / 原始代码 / 预置 Skill 脚本
- 用户和 AI 协作编辑
"""

from typing import Dict, Any, List, Optional
from pathlib import Path
import asyncio
import logging
import subprocess
import sys
import tempfile

from .action_executor import PPTActionExecutor
from .snapshot_extractor import SnapshotExtractor
from controllers.shared.skill_executor import (
    resolve_skill_script,
    build_params,
    execute_script_file,
    DEFAULT_SKILLS_BASE_DIR,
)

logger = logging.getLogger(__name__)


class PPTController:
    """
    PowerPoint Controller - Microsoft PowerPoint 自动化控制器

    通过 COM 连接到已打开的 PowerPoint 实例，每次操作独立连接。

    Public Methods:
    - get_status()          检查 PowerPoint 是否运行
    - get_snapshot()        获取演示文稿快照（内容 + 截图）
    - execute_actions()     执行结构化 actions（进程内 COM 直调）
    - execute_code()        执行原始代码（subprocess 执行）
    - execute_script()      执行预置 Skill 脚本
    """

    def __init__(self):
        self._action_executor = PPTActionExecutor()
        self._snapshot = SnapshotExtractor()

    # ==================== 公共方法 ====================

    async def get_status(self) -> Dict[str, Any]:
        """
        检查 PowerPoint 是否运行，获取当前演示文稿信息

        Returns:
            {"running": bool, "has_presentation": bool, "presentation_info": {...}|None}
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._get_status_sync)

    async def open_presentation(self, file_path: str, read_only: bool = False) -> Dict[str, Any]:
        """
        打开 PowerPoint 演示文稿

        如果 PowerPoint 未运行，会自动启动 PowerPoint。

        Returns:
            {"success": bool, "presentation_info": {...}|None, "error": str|None}
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._open_presentation_sync, file_path, read_only)

    async def close_presentation(self, save: bool = False) -> Dict[str, Any]:
        """
        关闭当前 PowerPoint 演示文稿

        Returns:
            {"success": bool, "closed_presentation": str|None, "error": str|None}
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._close_presentation_sync, save)

    async def get_snapshot(
        self,
        include_content: bool = True,
        include_screenshot: bool = True,
        max_slides: Optional[int] = None,
        current_slide_only: bool = False,
    ) -> Dict[str, Any]:
        """
        获取当前演示文稿快照

        Returns:
            {"presentation_info": {...}, "content": {...}, "screenshot": "base64"}
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._get_snapshot_sync,
            include_content, include_screenshot, max_slides, current_slide_only,
        )

    async def execute_actions(
        self,
        actions: List[Dict[str, Any]],
        return_screenshot: bool = True,
        current_slide_only: bool = True,
    ) -> Dict[str, Any]:
        """
        执行结构化 actions 并返回更新后的快照

        三层架构中第一层（结构化 Action）和第二层（宏指令）的统一入口。
        所有操作直接通过 COM 在进程内执行，无需启动子进程。

        Returns:
            {"execution": {...}, "snapshot": {...}}
        """
        return await self._execute_and_snapshot(
            self._execute_action_sync, [actions],
            return_screenshot, current_slide_only,
        )

    async def execute_code(
        self,
        code: str,
        language: str = "PowerShell",
        timeout: int = 120,
        return_screenshot: bool = True,
        current_slide_only: bool = True,
    ) -> Dict[str, Any]:
        """
        执行原始代码（PowerShell/Python）并返回更新后的快照

        通过 subprocess 写临时文件执行，适用于第三层（动态代码）场景。

        Returns:
            {"execution": {...}, "snapshot": {...}}
        """
        return await self._execute_and_snapshot(
            self._execute_code_sync, [code, language, timeout],
            return_screenshot, current_slide_only,
        )

    async def execute_script(
        self,
        skill_id: str,
        script_path: str,
        parameters: Optional[Dict[str, Any]] = None,
        language: str = "PowerShell",
        timeout: int = 120,
        return_screenshot: bool = True,
        current_slide_only: bool = True,
    ) -> Dict[str, Any]:
        """
        执行预置 Skill 脚本并返回更新后的快照

        通过 shared.skill_executor 解析 skill_id → 脚本绝对路径，再 subprocess 执行。

        Returns:
            {"execution": {...}, "snapshot": {...}}
        """
        return await self._execute_and_snapshot(
            self._execute_script_sync,
            [skill_id, script_path, parameters or {}, language, timeout],
            return_screenshot, current_slide_only,
        )

    # ==================== 执行模板 ====================

    async def _execute_and_snapshot(
        self,
        sync_fn,
        sync_args: list,
        return_screenshot: bool,
        current_slide_only: bool,
    ) -> Dict[str, Any]:
        """三条执行管线的统一骨架：激活窗口 → 执行 → 快照"""
        loop = asyncio.get_running_loop()

        await loop.run_in_executor(None, self._activate_ppt_window_sync)

        execution_result = await loop.run_in_executor(None, sync_fn, *sync_args)

        snapshot = await loop.run_in_executor(
            None, self._get_snapshot_sync,
            True, return_screenshot, None, current_slide_only,
        )

        return {"execution": execution_result, "snapshot": snapshot}

    # ==================== 同步执行方法 ====================

    def _execute_action_sync(self, actions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """同步执行结构化 actions"""
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        try:
            app = win32com.client.GetActiveObject("PowerPoint.Application")

            if app.Presentations.Count == 0:
                return {
                    "success": False,
                    "results": [],
                    "error": "No presentation is open in PowerPoint",
                }

            pres = app.ActivePresentation
            return self._action_executor.execute_actions(app, pres, actions)

        except Exception as e:
            logger.error(f"[PPTController] execute_action failed: {e}", exc_info=True)
            return {"success": False, "results": [], "error": str(e)}
        finally:
            pythoncom.CoUninitialize()

    def _execute_code_sync(self, code: str, language: str, timeout: int) -> Dict[str, Any]:
        """同步执行原始代码（写临时文件 + subprocess）"""
        code_file = None

        try:
            suffix = ".ps1" if language.lower() == "powershell" else ".py"
            encoding = "utf-8-sig" if language.lower() == "powershell" else "utf-8"

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=suffix, delete=False, encoding=encoding,
            ) as f:
                f.write(code)
                code_file = f.name

            logger.info(f"[PPTController] Code written to: {code_file}")

            if language.lower() == "powershell":
                cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-File", code_file]
            else:
                cmd = [sys.executable, code_file]

            logger.info(f"[PPTController] Executing: {' '.join(cmd)}")

            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=timeout, encoding="utf-8", errors="replace",
            )

            if result.returncode == 0:
                logger.info("[PPTController] Code execution successful")
                return {
                    "success": True,
                    "output": result.stdout,
                    "error": None,
                    "return_code": result.returncode,
                }
            else:
                logger.error(f"[PPTController] Code execution failed: {result.stderr}")
                return {
                    "success": False,
                    "output": result.stdout,
                    "error": result.stderr,
                    "return_code": result.returncode,
                }

        except subprocess.TimeoutExpired:
            logger.error(f"[PPTController] Code execution timeout after {timeout}s")
            return {
                "success": False, "output": "",
                "error": f"Execution timeout after {timeout} seconds",
                "return_code": -1,
            }
        except Exception as e:
            logger.error(f"[PPTController] Code execution error: {e}", exc_info=True)
            return {"success": False, "output": "", "error": str(e), "return_code": -1}
        finally:
            if code_file:
                try:
                    Path(code_file).unlink()
                except Exception:
                    pass

    def _execute_script_sync(
        self, skill_id: str, script_path: str,
        parameters: Dict[str, Any], language: str, timeout: int,
    ) -> Dict[str, Any]:
        """同步解析 + 执行 Skill 脚本"""
        try:
            full_path = resolve_skill_script(DEFAULT_SKILLS_BASE_DIR, skill_id, script_path)
            params = build_params(parameters, language)
            return execute_script_file(full_path, params, language, timeout)
        except FileNotFoundError as e:
            logger.error(f"[PPTController] Skill script not found: {e}")
            return {"success": False, "output": "", "error": str(e), "return_code": -1}
        except Exception as e:
            logger.error(f"[PPTController] execute_script error: {e}", exc_info=True)
            return {"success": False, "output": "", "error": str(e), "return_code": -1}

    # ==================== COM 管理 ====================

    def _get_snapshot_sync(
        self,
        include_content: bool,
        include_screenshot: bool,
        max_slides: Optional[int],
        current_slide_only: bool = False,
    ) -> Dict[str, Any]:
        """同步获取演示文稿快照（COM 连接包装）"""
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        try:
            app = win32com.client.GetActiveObject("PowerPoint.Application")
            if app.Presentations.Count == 0:
                raise ValueError("No presentation is open in PowerPoint")
            pres = app.ActivePresentation
            return self._snapshot.get_snapshot(
                app, pres, include_content, include_screenshot,
                max_slides, current_slide_only,
            )
        except Exception as e:
            logger.error(f"[PPTController] Snapshot error: {e}", exc_info=True)
            raise
        finally:
            pythoncom.CoUninitialize()

    def _get_status_sync(self) -> Dict[str, Any]:
        """同步获取 PowerPoint 状态"""
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        try:
            app = win32com.client.GetActiveObject("PowerPoint.Application")
            has_presentation = app.Presentations.Count > 0
            presentation_info = None
            if has_presentation:
                pres = app.ActivePresentation
                presentation_info = self._snapshot.extract_presentation_info(app, pres)
            return {
                "running": True,
                "has_presentation": has_presentation,
                "presentation_info": presentation_info,
            }
        except Exception as e:
            logger.info(f"[PPTController] PowerPoint not running or no access: {e}")
            return {"running": False, "has_presentation": False, "presentation_info": None}
        finally:
            pythoncom.CoUninitialize()

    def _activate_ppt_window_sync(self) -> None:
        """激活 PowerPoint 窗口（取消最小化、置于前台）"""
        import pythoncom
        import win32com.client
        import time

        pythoncom.CoInitialize()
        try:
            app = win32com.client.GetActiveObject("PowerPoint.Application")
            app.Visible = True
            if app.ActiveWindow.WindowState == 2:  # ppWindowMinimized
                app.ActiveWindow.WindowState = 1  # ppWindowNormal
            app.Activate()
            time.sleep(0.2)
            logger.info("[PPTController] PowerPoint window activated")
        except Exception as e:
            logger.warning(f"[PPTController] Failed to activate PowerPoint window: {e}")
        finally:
            pythoncom.CoUninitialize()

    def _open_presentation_sync(self, file_path: str, read_only: bool = False) -> Dict[str, Any]:
        """同步打开 PowerPoint 演示文稿"""
        import pythoncom
        import win32com.client
        import time
        import os

        path = Path(file_path)
        if not path.exists():
            return {"success": False, "presentation_info": None, "error": f"File not found: {file_path}"}

        abs_path = str(path.absolute())
        normalized_path = os.path.normpath(abs_path).lower()

        pythoncom.CoInitialize()
        try:
            try:
                app = win32com.client.GetActiveObject("PowerPoint.Application")
                logger.info("[PPTController] Connected to existing PowerPoint instance")

                existing_pres = None
                for i in range(1, app.Presentations.Count + 1):
                    pres = app.Presentations(i)
                    try:
                        pres_full_name = pres.FullName
                        if pres_full_name:
                            pres_path = os.path.normpath(pres_full_name).lower()
                            if pres_path == normalized_path:
                                existing_pres = pres
                                logger.info(f"[PPTController] Presentation already open: {pres.Name}")
                                break
                    except Exception as e:
                        logger.warning(f"[PPTController] Failed to get FullName for presentation {i}: {e}")
                        continue

                if existing_pres:
                    try:
                        existing_pres.Windows(1).Activate()
                    except Exception:
                        pass

                    presentation_info = self._snapshot.extract_presentation_info(app, existing_pres)
                    return {"success": True, "presentation_info": presentation_info, "error": None}

            except Exception:
                logger.info("[PPTController] Starting new PowerPoint instance")
                app = win32com.client.Dispatch("PowerPoint.Application")

            app.Visible = True
            app.Presentations.Open(abs_path, read_only, False, True)
            time.sleep(1)

            pres = app.ActivePresentation
            try:
                pres.Windows(1).Activate()
            except Exception:
                pass

            presentation_info = self._snapshot.extract_presentation_info(app, pres)
            logger.info(f"[PPTController] Opened presentation: {pres.Name}")
            return {"success": True, "presentation_info": presentation_info, "error": None}

        except Exception as e:
            logger.error(f"[PPTController] Failed to open presentation: {e}", exc_info=True)
            return {"success": False, "presentation_info": None, "error": str(e)}
        finally:
            pythoncom.CoUninitialize()

    def _close_presentation_sync(self, save: bool = False) -> Dict[str, Any]:
        """同步关闭当前 PowerPoint 演示文稿"""
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        try:
            app = win32com.client.GetActiveObject("PowerPoint.Application")

            if app.Presentations.Count == 0:
                return {"success": False, "closed_presentation": None, "error": "No presentation is open"}

            pres = app.ActivePresentation
            pres_name = pres.Name

            if save:
                pres.Save()
            pres.Close()

            logger.info(f"[PPTController] Closed presentation: {pres_name}, saved={save}")
            return {"success": True, "closed_presentation": pres_name, "error": None}

        except Exception as e:
            logger.error(f"[PPTController] Failed to close presentation: {e}", exc_info=True)
            return {"success": False, "closed_presentation": None, "error": str(e)}
        finally:
            pythoncom.CoUninitialize()
