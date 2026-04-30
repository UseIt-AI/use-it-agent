"""
Code Controller

在独立 Python 子进程中执行用户代码，避免污染 Local Engine 主进程。
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 日志中展示的代码最大字符数（避免单条日志过大）
_LOG_CODE_PREVIEW_CHARS = 2000


def _resolve_script_path_under_work_dir(work_dir: Path, script_path: str) -> Path:
    """
    将相对路径解析为 work_dir 下的绝对路径，禁止逃逸（..、绝对路径、非 .py）。
    """
    work_resolved = work_dir.resolve()
    raw = (script_path or "").strip().replace("\\", "/")
    if not raw:
        raise ValueError("script_path is empty")
    rel = Path(raw)
    if rel.is_absolute():
        raise ValueError("script_path must be relative to project cwd")
    if ".." in rel.parts:
        raise ValueError("script_path must not contain '..'")
    if rel.suffix.lower() != ".py":
        raise ValueError("script_path must end with .py")
    candidate = (work_resolved / rel).resolve()
    try:
        candidate.relative_to(work_resolved)
    except ValueError as exc:
        raise ValueError("script_path escapes cwd") from exc
    return candidate


def _resolve_bundled_ffmpeg_bin_dir() -> Optional[Path]:
    """
    返回应 prepend 到 PATH 的目录，使子进程内 shutil.which('ffmpeg') 能找到可执行文件。

    优先级：
    1. 环境变量 LOCAL_ENGINE_FFMPEG_EXE：指向 ffmpeg.exe 的绝对或相对路径
    2. 与 local-engine 仓库同级的前端内置路径：../useit-studio-frontend/resources/bin/ffmpeg.exe
    """
    configured = os.environ.get("LOCAL_ENGINE_FFMPEG_EXE", "").strip()
    if configured:
        candidate = Path(configured).expanduser().resolve()
        if candidate.is_file():
            return candidate.parent
        logger.warning(
            "LOCAL_ENGINE_FFMPEG_EXE is set but file not found: %s",
            candidate,
        )

    engine_root = Path(__file__).resolve().parent.parent.parent
    bundled_exe = engine_root.parent / "useit-studio-frontend" / "resources" / "bin" / "ffmpeg.exe"
    if bundled_exe.is_file():
        return bundled_exe.parent

    return None


class CodeController:
    """通用 Python 代码执行控制器（子进程模式）。"""

    DEFAULT_TIMEOUT_SECONDS = 120
    MAX_TIMEOUT_SECONDS = 300
    DEFAULT_MAX_OUTPUT_CHARS = 65536
    MAX_PREVIEW_BYTES = 4096
    MAX_ARTIFACTS = 20

    def execute_python(
        self,
        code: str,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        cwd: Optional[str] = None,
        artifacts_glob: Optional[List[str]] = None,
        max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS,
        script_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        执行 Python 代码并返回结构化结果。

        script_path: 相对 cwd 的路径；若提供则写入该文件并执行，执行后保留文件。
        未提供时使用临时文件，执行后删除。
        """
        if not code or not code.strip():
            return {
                "success": False,
                "data": None,
                "error": "code is empty",
            }

        safe_timeout = max(1, min(int(timeout), self.MAX_TIMEOUT_SECONDS))
        safe_max_output = max(1024, int(max_output_chars))

        work_dir = self._resolve_work_dir(cwd)
        command_prefix = self._resolve_python_command_prefix()

        delete_script_after_run = True
        script_rel_display: Optional[str] = None

        if script_path and script_path.strip():
            script_abs = _resolve_script_path_under_work_dir(work_dir, script_path)
            script_abs.parent.mkdir(parents=True, exist_ok=True)
            script_abs.write_text(code, encoding="utf-8")
            script_path_obj = script_abs
            delete_script_after_run = False
            try:
                script_rel_display = script_abs.resolve().relative_to(work_dir.resolve()).as_posix()
            except ValueError:
                script_rel_display = script_path.strip().replace("\\", "/")
        else:
            # 使用临时文件保存代码，避免命令行转义问题
            script_file = tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=".py",
                prefix="useit_code_",
                delete=False,
                dir=str(work_dir),
            )
            script_path_obj = Path(script_file.name)
            script_file.write(code)
            script_file.flush()
            script_file.close()

        try:
            command = command_prefix + ["-I", "-B", str(script_path_obj)]
            env = self._build_sanitized_env()

            started_at = time.time()
            timed_out = False
            exit_code = -1
            stdout = ""
            stderr = ""

            try:
                proc = subprocess.run(
                    command,
                    cwd=str(work_dir),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=safe_timeout,
                    env=env,
                )
                exit_code = proc.returncode
                stdout = proc.stdout or ""
                stderr = proc.stderr or ""
            except subprocess.TimeoutExpired as exc:
                timed_out = True
                stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
                stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
                exit_code = -1

            duration_ms = int((time.time() - started_at) * 1000)
            stdout_text, stdout_truncated = self._truncate_text(stdout, safe_max_output)
            stderr_text, stderr_truncated = self._truncate_text(stderr, safe_max_output)
            artifacts = self._collect_artifacts(work_dir, artifacts_glob or [])

            success = (not timed_out) and (exit_code == 0)
            code_len = len(code)
            if code_len <= _LOG_CODE_PREVIEW_CHARS:
                code_preview = code
                preview_truncated = False
            else:
                code_preview = code[:_LOG_CODE_PREVIEW_CHARS] + "\n... [code truncated for log]"
                preview_truncated = True
            logger.info(
                "[CodeController] Python executed: success=%s exit_code=%s timed_out=%s duration_ms=%s "
                "cwd=%s python=%s timeout_s=%s code_chars=%s preview_truncated=%s\n--- executed code ---\n%s\n--- end ---",
                success,
                exit_code,
                timed_out,
                duration_ms,
                work_dir,
                command_prefix[0],
                safe_timeout,
                code_len,
                preview_truncated,
                code_preview,
            )

            result = {
                "success": success,
                "data": {
                    "stdout": stdout_text,
                    "stderr": stderr_text,
                    "exit_code": exit_code,
                    "timed_out": timed_out,
                    "duration_ms": duration_ms,
                    "stdout_truncated": stdout_truncated,
                    "stderr_truncated": stderr_truncated,
                    "cwd": str(work_dir),
                    "artifacts": artifacts,
                    "python_command": command_prefix[0],
                    "script_path": script_rel_display,
                },
                "error": None
                if success
                else self._build_error_message(timed_out, exit_code, stderr_text, stdout_text),
            }
            return result
        finally:
            if delete_script_after_run:
                try:
                    script_path_obj.unlink(missing_ok=True)
                except Exception:
                    # 清理失败不影响主流程
                    pass

    def _resolve_work_dir(self, cwd: Optional[str]) -> Path:
        if cwd:
            resolved = Path(cwd).expanduser().resolve()
            if not resolved.exists():
                raise ValueError(f"cwd does not exist: {resolved}")
            if not resolved.is_dir():
                raise ValueError(f"cwd is not a directory: {resolved}")
            return resolved
        return Path.cwd().resolve()

    def _resolve_python_command_prefix(self) -> List[str]:
        configured = os.environ.get("LOCAL_ENGINE_PYTHON_EXECUTABLE")
        if configured:
            return [configured]

        python_executable = shutil.which("python")
        if python_executable:
            return [python_executable]

        py_launcher = shutil.which("py")
        if py_launcher:
            return [py_launcher, "-3"]

        raise RuntimeError("Python executable not found. Set LOCAL_ENGINE_PYTHON_EXECUTABLE.")

    def _build_sanitized_env(self) -> Dict[str, str]:
        allowed_env_keys = [
            "SYSTEMROOT",
            "WINDIR",
            "PATH",
            "TEMP",
            "TMP",
            "USERNAME",
            "USERPROFILE",
            "HOMEDRIVE",
            "HOMEPATH",
            "COMSPEC",
            "PATHEXT",
            "PROGRAMDATA",
            "APPDATA",
            "LOCALAPPDATA",
            "NUMBER_OF_PROCESSORS",
            "PROCESSOR_ARCHITECTURE",
            "PROCESSOR_IDENTIFIER",
        ]

        env: Dict[str, str] = {}
        for key in allowed_env_keys:
            value = os.environ.get(key)
            if value is not None:
                env[key] = value

        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"

        ffmpeg_bin_dir = _resolve_bundled_ffmpeg_bin_dir()
        if ffmpeg_bin_dir is not None:
            sep = os.pathsep
            existing = env.get("PATH", "")
            env["PATH"] = f"{ffmpeg_bin_dir}{sep}{existing}" if existing else str(ffmpeg_bin_dir)

        return env

    def _truncate_text(self, text: str, max_chars: int) -> Tuple[str, bool]:
        if len(text) <= max_chars:
            return text, False
        suffix = "\n... [truncated]"
        keep = max(0, max_chars - len(suffix))
        return text[:keep] + suffix, True

    def _collect_artifacts(self, work_dir: Path, patterns: List[str]) -> List[Dict[str, Any]]:
        if not patterns:
            return []

        artifacts: List[Dict[str, Any]] = []
        seen: set[str] = set()

        for pattern in patterns:
            if not pattern:
                continue
            for matched in work_dir.glob(pattern):
                if len(artifacts) >= self.MAX_ARTIFACTS:
                    return artifacts
                if not matched.is_file():
                    continue

                try:
                    resolved = matched.resolve()
                    rel = resolved.relative_to(work_dir)
                except Exception:
                    # 只允许 work_dir 内文件
                    continue

                rel_key = rel.as_posix()
                if rel_key in seen:
                    continue
                seen.add(rel_key)

                size_bytes = resolved.stat().st_size
                preview = self._safe_read_preview(resolved)
                artifacts.append(
                    {
                        "path": rel_key,
                        "size_bytes": size_bytes,
                        "preview": preview,
                        "preview_truncated": size_bytes > self.MAX_PREVIEW_BYTES,
                    }
                )

        return artifacts

    def _safe_read_preview(self, path: Path) -> str:
        try:
            with open(path, "rb") as f:
                raw = f.read(self.MAX_PREVIEW_BYTES)
            # 含大量空字节通常为二进制
            if raw.count(b"\x00") > 4:
                return "[binary content omitted]"
            return raw.decode("utf-8", errors="replace")
        except Exception as exc:
            return f"[failed to read preview: {exc}]"

    def _build_error_message(
        self,
        timed_out: bool,
        exit_code: int,
        stderr: str,
        stdout: str,
    ) -> str:
        if timed_out:
            return "python execution timed out"
        if stderr.strip():
            return stderr.strip()
        out = (stdout or "").strip()
        if out:
            # 许多脚本用 print 报告错误后 sys.exit(1)，stderr 为空
            tail_chars = 3000
            tail = out[-tail_chars:] if len(out) > tail_chars else out
            prefix = "... " if len(out) > tail_chars else ""
            return f"{prefix}{tail}\n(exit_code={exit_code})"
        return f"python execution failed with exit_code={exit_code}"

