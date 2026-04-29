"""
Skill Script Executor - 共享的 Skill 脚本执行模块

所有 Office Controller（Excel / Word / PPT）共用此模块来执行预置脚本。

职责:
- resolve_skill_script : skill_id + script_path → 绝对路径
- build_powershell_params : 参数字典 → PowerShell 命令行参数
- build_python_params    : 参数字典 → Python 命令行参数
- execute_script_file    : 执行已存在的脚本文件
"""

import json as json_module
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# 默认 Skills 根目录
DEFAULT_SKILLS_BASE_DIR = Path(r"D:\startup\uesit\useit-agent-internal\SKILLS")


def resolve_skill_script(
    skills_base_dir: Path,
    skill_id: str,
    script_path: str,
) -> Path:
    r"""
    将 skill_id + script_path 解析为脚本文件的绝对路径。

    尝试两种目录命名:
      1. {skills_base_dir}/{skill_id}/
      2. {skills_base_dir}/skill-{skill_id}/

    Args:
        skills_base_dir: Skills 根目录
        skill_id: e.g. "66666666" 或 "preliminary-engineering-calculations"
        script_path: e.g. "scripts/create_column_chart.ps1"

    Returns:
        解析后的绝对路径

    Raises:
        FileNotFoundError: skill 目录或脚本文件不存在
    """
    logger.info(f"[SkillExecutor] Resolving: skill_id={skill_id}, script_path={script_path}")

    skill_dir = skills_base_dir / skill_id
    if not skill_dir.exists():
        skill_dir = skills_base_dir / f"skill-{skill_id}"

    if not skill_dir.exists():
        raise FileNotFoundError(
            f"Skill directory not found: tried '{skill_id}' and "
            f"'skill-{skill_id}' under {skills_base_dir}"
        )

    script_full_path = skill_dir / script_path
    if not script_full_path.exists():
        # List contents to help debug
        try:
            contents = [
                str(p.relative_to(skill_dir))
                for p in list(skill_dir.glob("**/*"))[:20]
            ]
            logger.error(
                f"[SkillExecutor] Script not found: {script_full_path}. "
                f"Available: {contents}"
            )
        except Exception:
            pass
        raise FileNotFoundError(f"Script not found: {script_full_path}")

    logger.info(f"[SkillExecutor] Resolved to: {script_full_path}")
    return script_full_path


def build_powershell_params(parameters: Dict[str, Any]) -> List[str]:
    """
    参数字典 → PowerShell 命令行参数。

    {"DataRange": "A1:C6", "ShowMarkers": True}
    → ["-DataRange", "A1:C6", "-ShowMarkers", "$true"]
    """
    params: List[str] = []
    for key, value in parameters.items():
        params.append(f"-{key}")
        if isinstance(value, bool):
            params.append("$true" if value else "$false")
        elif isinstance(value, str):
            params.append(value)
        else:
            params.append(str(value))
    return params


def build_python_params(parameters: Dict[str, Any]) -> List[str]:
    """
    参数字典 → Python 命令行参数。

    {"targetRow": 3, "verbose": True}
    → ["--targetRow", "3", "--verbose"]
    """
    params: List[str] = []
    for key, value in parameters.items():
        if isinstance(value, bool):
            if value:
                params.append(f"--{key}")
        else:
            params.append(f"--{key}")
            if isinstance(value, (dict, list)):
                params.append(json_module.dumps(value, ensure_ascii=False))
            else:
                params.append(str(value))
    return params


def build_params(parameters: Dict[str, Any], language: str) -> List[str]:
    """根据语言选择参数构建方式。"""
    if not parameters:
        return []
    if language.lower() == "powershell":
        return build_powershell_params(parameters)
    if language.lower() == "python":
        return build_python_params(parameters)
    return []


def execute_script_file(
    script_path: Path,
    params: List[str],
    language: str,
    timeout: int,
) -> Dict[str, Any]:
    """
    执行已存在的脚本文件（区别于 execute_code 的临时文件方式）。

    Returns:
        {"success": bool, "output": str, "error": str|None, "return_code": int}
    """
    try:
        if language.lower() == "powershell":
            params_str = " ".join(params) if params else ""
            ps_command = (
                f'[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; '
                f'& "{script_path}" {params_str}'
            )
            cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-Command", ps_command]
        else:
            cmd = [sys.executable, str(script_path)] + params

        logger.info(f"[SkillExecutor] Executing: {' '.join(cmd[:6])}...")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )

        if result.returncode == 0:
            logger.info("[SkillExecutor] Script execution successful")
            return {
                "success": True,
                "output": result.stdout,
                "error": None,
                "return_code": result.returncode,
            }

        error_parts = []
        if result.stderr:
            error_parts.append(f"[stderr] {result.stderr.strip()}")
        if result.stdout:
            error_parts.append(f"[stdout] {result.stdout.strip()}")
        if not error_parts:
            error_parts.append(f"Script failed with return code {result.returncode}")

        return {
            "success": False,
            "output": result.stdout,
            "error": "\n".join(error_parts),
            "return_code": result.returncode,
        }

    except subprocess.TimeoutExpired:
        logger.error(f"[SkillExecutor] Timeout after {timeout}s")
        return {
            "success": False,
            "output": "",
            "error": f"Execution timeout after {timeout} seconds",
            "return_code": -1,
        }
    except Exception as e:
        logger.error(f"[SkillExecutor] Execution error: {e}", exc_info=True)
        return {
            "success": False,
            "output": "",
            "error": str(e),
            "return_code": -1,
        }
