"""
Code API endpoints - 在本机执行 Python 代码
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from controllers.code.controller import CodeController
from .project import format_tree_as_text

router = APIRouter()

_controller: Optional[CodeController] = None


def _get_controller() -> CodeController:
    global _controller
    if _controller is None:
        _controller = CodeController()
    return _controller


class StepRequest(BaseModel):
    code: str = Field(..., description="要执行的 Python 代码")
    timeout: int = Field(default=120, ge=1, le=300, description="超时时间（秒）")
    cwd_mode: Literal["project", "temp"] = Field(
        default="project",
        description="project: 在项目目录执行; temp: 在当前工作目录执行",
    )
    project_path: Optional[str] = Field(
        default=None,
        description="项目目录路径（cwd_mode=project 时建议提供）",
    )
    artifacts_glob: Optional[List[str]] = Field(
        default=None,
        description="执行后要回传的文件匹配模式，如 ['*.csv', 'outputs/**/*.png']",
    )
    max_output_chars: int = Field(
        default=65536,
        ge=1024,
        le=500000,
        description="stdout/stderr 最大返回字符数",
    )
    script_path: Optional[str] = Field(
        default=None,
        description="相对项目 cwd 的 .py 路径；若提供则写入该文件并执行，执行后保留（禁止 .. 与绝对路径）",
    )
    include_project_files: bool = Field(
        default=False,
        description="是否在响应 data 中附带项目文件树（与 PPT snapshot 一致，需 project_path）",
    )
    project_max_depth: int = Field(
        default=4,
        ge=1,
        le=10,
        description="项目目录遍历最大深度（include_project_files=true 时生效）",
    )


@router.post("/step")
async def step(request: StepRequest) -> Dict[str, Any]:
    try:
        cwd: Optional[str] = None
        if request.cwd_mode == "project":
            if request.project_path:
                project_dir = Path(request.project_path).expanduser().resolve()
                if not project_dir.exists():
                    raise HTTPException(status_code=400, detail=f"project_path does not exist: {project_dir}")
                if not project_dir.is_dir():
                    raise HTTPException(status_code=400, detail=f"project_path is not a directory: {project_dir}")
                cwd = str(project_dir)
            else:
                cwd = str(Path.cwd().resolve())
        else:
            cwd = str(Path.cwd().resolve())

        controller = _get_controller()
        result = controller.execute_python(
            code=request.code,
            timeout=request.timeout,
            cwd=cwd,
            artifacts_glob=request.artifacts_glob,
            max_output_chars=request.max_output_chars,
            script_path=request.script_path,
        )
        # 与 PPT/Word 一致：可选附带项目文件树，供 Code Use / 回调注入 additional_context
        if (
            request.include_project_files
            and request.project_path
            and isinstance(result.get("data"), dict)
        ):
            try:
                project_tree = format_tree_as_text(
                    project_path=request.project_path,
                    max_depth=request.project_max_depth,
                )
                result["data"]["project_files"] = project_tree
            except Exception as exc:
                result["data"]["project_files"] = f"Error: {str(exc)}"
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
