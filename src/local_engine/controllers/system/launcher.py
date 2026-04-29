"""
启动器 - 启动 exe 或 shell-verb (start:// 等)

安全注意：
- 只接受 .exe / .bat / .cmd / .com / .lnk 等明确的可执行格式，或 shell: 协议
- 不接受 "cmd.exe /c rm ..." 这种带 shell 命令串的参数
- args 必须是 list[str]，不在内部拼接 shell 命令
"""
import logging
import os
import shlex
import subprocess
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


_ALLOWED_EXE_SUFFIX = (".exe", ".bat", ".cmd", ".com", ".lnk", ".msi")


class Launcher:
    """进程启动器"""

    @staticmethod
    def launch(
        exe_path: str,
        args: Optional[List[str]] = None,
        cwd: Optional[str] = None,
        detached: bool = True,
    ) -> Dict[str, Any]:
        """
        启动一个可执行文件。

        Args:
            exe_path: 可执行文件完整路径（必须存在且后缀合法），或以 "shell:" 开头的 shell 协议
            args: 命令行参数列表（不会做 shell 解析）
            cwd:  工作目录
            detached: 是否脱离父进程独立运行（默认 True）

        Returns:
            {"success": True, "pid": 1234, "exe": "...", "args": [...]}
        """
        if not exe_path or not isinstance(exe_path, str):
            return {"success": False, "error": "exe_path required"}

        args = args or []
        if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
            return {"success": False, "error": "args must be list of strings"}

        # shell:* 协议（如 shell:AppsFolder\Microsoft.WindowsCalculator_xxx!App）走 os.startfile
        if exe_path.lower().startswith("shell:"):
            try:
                os.startfile(exe_path)
                return {"success": True, "exe": exe_path, "launched_via": "shell"}
            except Exception as e:
                return {"success": False, "error": f"shell launch failed: {e}"}

        # 标准 exe 启动
        if not os.path.exists(exe_path):
            return {"success": False, "error": f"exe not found: {exe_path}"}

        suffix = os.path.splitext(exe_path)[1].lower()
        if suffix not in _ALLOWED_EXE_SUFFIX:
            return {
                "success": False,
                "error": f"unsupported file type: {suffix} (allowed: {_ALLOWED_EXE_SUFFIX})",
            }

        # .lnk / .msi：走 os.startfile（shell 会按关联方式打开）
        if suffix in (".lnk", ".msi"):
            try:
                os.startfile(exe_path)
                logger.info(f"[Launcher] startfile: {exe_path}")
                return {"success": True, "exe": exe_path, "args": args, "launched_via": "startfile"}
            except Exception as e:
                return {"success": False, "error": f"startfile failed: {e}"}

        # exe / bat / cmd / com：走 subprocess.Popen
        try:
            popen_kwargs: Dict[str, Any] = {
                "cwd": cwd,
                "close_fds": True,
            }
            if detached and os.name == "nt":
                # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
                popen_kwargs["creationflags"] = 0x00000008 | 0x00000200

            cmd = [exe_path, *args]
            proc = subprocess.Popen(cmd, **popen_kwargs)

            logger.info(f"[Launcher] popen pid={proc.pid}: {exe_path} {shlex.join(args)}")
            return {
                "success": True,
                "pid": proc.pid,
                "exe": exe_path,
                "args": args,
                "launched_via": "popen",
            }
        except Exception as e:
            logger.error(f"[Launcher] popen failed: {e}")
            return {"success": False, "error": f"popen failed: {e}"}

    @staticmethod
    def launch_smart(
        name: Optional[str] = None,
        file: Optional[str] = None,
        exe_path: Optional[str] = None,
        args: Optional[List[str]] = None,
        cwd: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        AI 友好的启动入口，支持 3 种写法（至少提供一个）:

        1. ``{"name": "PowerPoint"}``           先按名字 find_exe 再 launch
        2. ``{"file": "C:/x.pptx"}``            用系统关联程序打开文件
        3. ``{"name": "PowerPoint", "file": "C:/x.pptx"}``  用指定程序打开文件
        4. ``{"exe_path": "C:/...POWERPNT.EXE"}``            精确启动（向后兼容）

        name 匹配到多个候选时，返回 ``ambiguous`` 错误 + 候选列表，
        让调用方（AI）看清单后挑一个具体的 exe_path 再次调用。
        """
        base_args: List[str] = list(args) if args else []

        # 1) 最精确：给了 exe_path，直接走
        if exe_path:
            full_args = base_args + ([file] if file else [])
            return Launcher.launch(exe_path=exe_path, args=full_args, cwd=cwd)

        # 2) 仅 file：走系统关联程序
        if file and not name:
            if not os.path.exists(file):
                return {"success": False, "error": f"file not found: {file}"}
            try:
                os.startfile(file)
                logger.info("[Launcher] startfile (association): %s", file)
                return {
                    "success": True,
                    "file": file,
                    "launched_via": "startfile_association",
                }
            except Exception as e:
                return {"success": False, "error": f"startfile failed: {e}"}

        # 3) 有 name (可能还带 file)：按名字 find_exe
        if name:
            # 延迟导入避免循环
            from .software_handler import SoftwareHandler

            finding = SoftwareHandler.find_exe(name_contains=name)
            if not finding.get("success"):
                return finding
            candidates: List[Dict[str, Any]] = finding.get("candidates", [])
            if not candidates:
                return {
                    "success": False,
                    "error": f"no installed software matches '{name}'",
                }

            chosen = Launcher._pick_best_candidate(name, candidates)

            # 多于 1 个，但我们用启发式挑了一个；也把候选一并返回，便于 AI 反悔
            launch_args = base_args + ([file] if file else [])
            result = Launcher.launch(exe_path=chosen["exe_path"], args=launch_args, cwd=cwd)
            if result.get("success"):
                result["matched_software"] = chosen.get("name", "")
                if len(candidates) > 1:
                    others = [c["name"] for c in candidates if c is not chosen][:4]
                    result["note"] = (
                        f"matched {len(candidates)} candidates, picked '{chosen['name']}' by heuristic; "
                        f"other candidates: {others}"
                    )
            return result

        return {
            "success": False,
            "error": "provide at least one of: name, file, exe_path",
        }

    @staticmethod
    def _pick_best_candidate(
        query: str,
        candidates: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        从 find_exe 候选里挑"最像用户意图"的那一个。

        启发式（从左到右优先级降低）：
        1. source == "app_paths" 优先（Win+R 真正能启动的 exe）
        2. 精确名字相等 > 首词相等 > 子串包含 > 其它
        3. 同档里名字更短的优先（避免 "Microsoft Office Tools ..." 抢走 "Microsoft Office"）
        """
        q = (query or "").strip().lower()

        def score(c: Dict[str, Any]) -> tuple:
            source_rank = 0 if c.get("source") == "app_paths" else 1
            name = (c.get("name") or "").strip().lower()
            if not name:
                return (source_rank, 9, 999, 999)
            if name == q:
                return (source_rank, 0, len(name), 0)
            first_word = name.split()[0] if name else ""
            if first_word == q:
                return (source_rank, 1, len(name), 0)
            if q in name:
                return (source_rank, 2, len(name), name.index(q))
            return (source_rank, 3, len(name), 0)

        return min(candidates, key=score)
