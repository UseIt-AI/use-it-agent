"""
PowerPoint API 端点 - Microsoft PowerPoint 自动化

通过 COM 连接到已打开的 PowerPoint，支持用户和 AI 协作编辑演示文稿。

主要端点:
- GET  /api/v1/ppt/status     获取 PowerPoint 状态
- POST /api/v1/ppt/open       打开 PowerPoint 演示文稿
- POST /api/v1/ppt/close      关闭 PowerPoint 演示文稿
- POST /api/v1/ppt/snapshot   获取演示文稿快照
- POST /api/v1/ppt/step       统一执行入口（actions / code / skill 三选一）
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
import logging

from controllers.ppt.controller import PPTController
from .project import format_tree_as_text

logger = logging.getLogger(__name__)
router = APIRouter()

# 全局 Controller 实例
_controller: Optional[PPTController] = None


def _get_controller() -> PPTController:
    """获取 PowerPoint Controller 实例"""
    global _controller
    if _controller is None:
        _controller = PPTController()
    return _controller


# ==================== 请求模型 ====================

class SnapshotRequest(BaseModel):
    """获取演示文稿快照请求"""
    include_content: bool = Field(default=True, description="是否包含演示文稿内容")
    include_screenshot: bool = Field(default=True, description="是否包含截图")
    max_slides: Optional[int] = Field(default=None, description="最大幻灯片数（None=全部）")
    current_slide_only: bool = Field(default=False, description="是否只返回当前显示幻灯片的内容")
    # Project files 相关参数
    include_project_files: bool = Field(default=False, description="是否包含项目文件列表")
    project_path: Optional[str] = Field(default=None, description="项目根目录路径（include_project_files=true 时必填）")
    project_max_depth: int = Field(default=4, ge=1, le=10, description="项目文件遍历最大深度")
    project_max_files: int = Field(default=500, ge=1, le=2000, description="项目文件最大数量")


class StepRequest(BaseModel):
    """
    统一执行请求 - actions / code / skill 三选一

    - 传 actions:    走结构化 Action 路径（进程内 COM 直调，快速安全）
    - 传 code:       走原始代码执行路径（subprocess 执行 PowerShell/Python）
    - 传 skill_id + script_path: 走预置 Skill 脚本路径
    """
    # 模式 A: 结构化 Actions
    actions: Optional[List[Dict[str, Any]]] = Field(default=None, description="结构化 Action 列表")
    # 模式 B: 原始代码执行
    code: Optional[str] = Field(default=None, description="要执行的代码")
    # 模式 C: 预置 Skill 脚本
    skill_id: Optional[str] = Field(default=None, description="Skill ID")
    script_path: Optional[str] = Field(default=None, description="脚本相对路径")
    parameters: Optional[Dict[str, Any]] = Field(default=None, description="脚本参数")
    # 共享
    language: str = Field(default="PowerShell", description="语言：PowerShell 或 Python")
    timeout: int = Field(default=120, description="超时时间（秒）")
    # 通用
    return_screenshot: bool = Field(default=True, description="是否返回截图")
    current_slide_only: bool = Field(default=True, description="快照是否只返回当前幻灯片内容")
    # Project files 相关参数
    include_project_files: bool = Field(default=False, description="是否包含项目文件列表")
    project_path: Optional[str] = Field(default=None, description="项目根目录路径")
    project_max_depth: int = Field(default=4, ge=1, le=10, description="项目文件遍历最大深度")


class OpenPresentationRequest(BaseModel):
    """打开演示文稿请求"""
    file_path: str = Field(..., description="演示文稿路径")
    read_only: bool = Field(default=False, description="是否以只读方式打开")


class ClosePresentationRequest(BaseModel):
    """关闭演示文稿请求"""
    save: bool = Field(default=False, description="是否保存演示文稿")


# ==================== API 端点 ====================

@router.get("/status")
async def get_status() -> Dict[str, Any]:
    """
    获取 PowerPoint 状态
    
    检查 PowerPoint 是否运行，以及当前是否有打开的演示文稿。
    
    Returns:
        {
            "success": true,
            "data": {
                "running": true,
                "has_presentation": true,
                "presentation_info": {
                    "name": "演示文稿.pptx",
                    "path": "C:/Documents/演示文稿.pptx",
                    "saved": true,
                    "slide_count": 10,
                    "current_slide": 3,
                    ...
                }
            }
        }
    """
    logger.info("[PPT API] status")
    
    try:
        controller = _get_controller()
        status = await controller.get_status()
        return {"success": True, "data": status}
    except Exception as e:
        logger.error(f"[PPT API] status error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/open")
async def open_presentation(request: OpenPresentationRequest) -> Dict[str, Any]:
    """
    打开 PowerPoint 演示文稿
    
    如果 PowerPoint 未运行，会自动启动 PowerPoint。
    
    Args:
        request.file_path: 演示文稿路径
        request.read_only: 是否以只读方式打开
    
    Returns:
        {
            "success": true,
            "data": {
                "presentation_info": {
                    "name": "演示文稿.pptx",
                    "path": "C:/Documents/演示文稿.pptx",
                    "current_slide": 1,
                    "slide_count": 10,
                    ...
                }
            }
        }
    """
    logger.info(f"[PPT API] open: file_path={request.file_path}, read_only={request.read_only}")
    
    try:
        controller = _get_controller()
        result = await controller.open_presentation(
            file_path=request.file_path,
            read_only=request.read_only
        )
        
        if result["success"]:
            return {"success": True, "data": {"presentation_info": result["presentation_info"]}}
        else:
            raise HTTPException(status_code=400, detail=result["error"])
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PPT API] open error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/close")
async def close_presentation(request: ClosePresentationRequest = None) -> Dict[str, Any]:
    """
    关闭当前 PowerPoint 演示文稿
    
    Args:
        request.save: 是否保存演示文稿（默认不保存）
    
    Returns:
        {
            "success": true,
            "data": {
                "closed_presentation": "演示文稿.pptx"
            }
        }
    """
    if request is None:
        request = ClosePresentationRequest()
    
    logger.info(f"[PPT API] close: save={request.save}")
    
    try:
        controller = _get_controller()
        result = await controller.close_presentation(save=request.save)
        
        if result["success"]:
            return {"success": True, "data": {"closed_presentation": result["closed_presentation"]}}
        else:
            raise HTTPException(status_code=400, detail=result["error"])
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PPT API] close error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/snapshot")
async def get_snapshot(request: SnapshotRequest = None) -> Dict[str, Any]:
    """
    获取演示文稿快照
    
    获取当前打开演示文稿的内容和/或截图。
    
    Args:
        request.include_content: 是否包含演示文稿内容（幻灯片、形状等）
        request.include_screenshot: 是否包含演示文稿截图
        request.max_slides: 最大幻灯片数限制
        request.current_slide_only: 是否只返回当前幻灯片内容
    
    Returns:
        {
            "success": true,
            "data": {
                "presentation_info": {...},
                "content": {
                    "slides": [...],
                    "total_slides": 10
                },
                "screenshot": "base64..."
            }
        }
    """
    if request is None:
        request = SnapshotRequest()
    
    logger.info(f"[PPT API] snapshot: content={request.include_content}, screenshot={request.include_screenshot}, current_slide_only={request.current_slide_only}, include_project_files={request.include_project_files}")
    
    try:
        controller = _get_controller()
        snapshot = await controller.get_snapshot(
            include_content=request.include_content,
            include_screenshot=request.include_screenshot,
            max_slides=request.max_slides,
            current_slide_only=request.current_slide_only
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
                logger.warning(f"[PPT API] Failed to get project files: {e}")
                snapshot["project_files"] = f"Error: {str(e)}"
        
        return {"success": True, "data": snapshot}
    except ValueError as e:
        # 例如：没有打开的演示文稿
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[PPT API] snapshot error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/step")
async def step(request: StepRequest) -> Dict[str, Any]:
    """
    统一执行入口 — actions / code / skill 三选一

    模式 A: 结构化 Actions（进程内 COM 直调）
    ```json
    {"actions": [{"action": "render_ppt_layout", "slide": 1, "svg": "<svg .../>"}]}
    ```

    模式 B: 原始代码（subprocess 执行）
    ```json
    {"code": "$ppt = ...", "language": "PowerShell"}
    ```

    模式 C: 预置 Skill 脚本
    ```json
    {"skill_id": "66666666", "script_path": "scripts/create_chart.ps1", "parameters": {"DataRange": "A1:C6"}}
    ```
    """
    controller = _get_controller()

    try:
        if request.actions:
            logger.info(
                f"[PPT API] step(actions): {len(request.actions)} actions, "
                f"include_project_files={request.include_project_files}"
            )
            result = await controller.execute_actions(
                actions=request.actions,
                return_screenshot=request.return_screenshot,
                current_slide_only=request.current_slide_only,
            )
        elif request.code:
            logger.info(
                f"[PPT API] step(code): lang={request.language}, "
                f"code_len={len(request.code)}, "
                f"include_project_files={request.include_project_files}"
            )
            result = await controller.execute_code(
                code=request.code,
                language=request.language,
                timeout=request.timeout,
                return_screenshot=request.return_screenshot,
                current_slide_only=request.current_slide_only,
            )
        elif request.skill_id and request.script_path:
            logger.info(
                f"[PPT API] step(skill): skill_id={request.skill_id}, "
                f"script_path={request.script_path}, "
                f"lang={request.language}, "
                f"include_project_files={request.include_project_files}"
            )
            result = await controller.execute_script(
                skill_id=request.skill_id,
                script_path=request.script_path,
                parameters=request.parameters,
                language=request.language,
                timeout=request.timeout,
                return_screenshot=request.return_screenshot,
                current_slide_only=request.current_slide_only,
            )
        else:
            raise HTTPException(
                status_code=400,
                detail="Must provide 'actions', 'code', or 'skill_id'+'script_path'",
            )

        # 附带项目文件列表
        if request.include_project_files and request.project_path:
            try:
                project_tree = format_tree_as_text(
                    project_path=request.project_path,
                    max_depth=request.project_max_depth,
                )
                result["snapshot"]["project_files"] = project_tree
            except Exception as e:
                logger.warning(f"[PPT API] Failed to get project files: {e}")
                result["snapshot"]["project_files"] = f"Error: {str(e)}"

        success = result["execution"]["success"]
        return {
            "success": success,
            "data": result,
            "error": result["execution"]["error"] if not success else None,
        }
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[PPT API] step error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
