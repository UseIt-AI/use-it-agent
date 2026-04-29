"""
AutoCAD API v1 路由

提供 AutoCAD V2 控制器的 API 接口
"""

from fastapi import APIRouter

# 导入 AutoCAD V2 的路由
from controllers.autocad_v2.api import router as autocad_v2_router

# 创建主路由
router = APIRouter()

# 包含 V2 路由（移除 prefix，因为在 router.py 中已经设置了 /autocad）
# autocad_v2_router 已经有 /autocad/v2 前缀，我们需要调整

# 直接导出 autocad_v2_router 的端点
# 由于 autocad_v2_router 已有 /autocad/v2 前缀，我们需要去掉它
# 或者在 router.py 中直接使用 autocad_v2_router

# 为了保持一致性，我们创建一个简单的转发路由
from controllers.autocad_v2.controller import AutoCADControllerV2, AutoCADNotRunningError, AutoCADNoDocumentError
from controllers.autocad_v2.api import (
    get_controller,
    StepRequest,
    OpenDrawingRequest,
    CloseDrawingRequest,
    NewDrawingRequest,
    SnapshotRequest,
    StandardPartRequest
)
from fastapi import HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)


# ==================== V2 API 端点 ====================

@router.post("/v2/launch")
async def launch_autocad():
    """启动或连接 AutoCAD 应用程序"""
    try:
        controller = get_controller()
        result = await controller.launch()
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to launch AutoCAD"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] launch_autocad error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/v2/status")
async def get_status():
    """获取 AutoCAD 状态"""
    try:
        controller = get_controller()
        return await controller.get_status()
    except Exception as e:
        logger.error(f"[API] get_status error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/v2/open")
async def open_drawing(request: OpenDrawingRequest):
    """打开图纸"""
    try:
        controller = get_controller()
        result = await controller.open_drawing(
            file_path=request.file_path,
            read_only=request.read_only
        )
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result.get("error"))
        return result
    except HTTPException:
        raise
    except (AutoCADNotRunningError, AutoCADNoDocumentError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[API] open_drawing error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/v2/close")
async def close_drawing(request: CloseDrawingRequest):
    """关闭图纸"""
    try:
        controller = get_controller()
        result = await controller.close_drawing(save=request.save)
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result.get("error"))
        return result
    except HTTPException:
        raise
    except (AutoCADNotRunningError, AutoCADNoDocumentError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[API] close_drawing error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class ActivateDrawingRequest(BaseModel):
    """切换文档请求"""
    name: Optional[str] = None
    index: Optional[int] = None


@router.post("/v2/activate")
async def activate_drawing(request: ActivateDrawingRequest):
    """
    切换到指定的文档
    
    Args:
        name: 文档名称（如 "Drawing1.dwg"）
        index: 文档索引（从 0 开始）
        
    注意：name 和 index 二选一，name 优先
    
    示例请求：
    ```json
    {"name": "Drawing1.dwg"}
    ```
    或
    ```json
    {"index": 0}
    ```
    """
    try:
        controller = get_controller()
        result = await controller.activate_drawing(
            name=request.name,
            index=request.index
        )
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result.get("error"))
        return result
    except HTTPException:
        raise
    except (AutoCADNotRunningError, AutoCADNoDocumentError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[API] activate_drawing error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/v2/new")
async def new_drawing(request: NewDrawingRequest):
    """新建图纸"""
    try:
        controller = get_controller()
        result = await controller.new_drawing(template=request.template)
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result.get("error"))
        return result
    except HTTPException:
        raise
    except (AutoCADNotRunningError, AutoCADNoDocumentError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[API] new_drawing error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/v2/snapshot")
async def get_snapshot(
    include_content: bool = True,
    include_screenshot: bool = True,
    only_visible: bool = False,
    max_entities: Optional[int] = None
):
    """获取图纸快照"""
    try:
        controller = get_controller()
        return await controller.get_snapshot(
            include_content=include_content,
            include_screenshot=include_screenshot,
            only_visible=only_visible,
            max_entities=max_entities
        )
    except (AutoCADNotRunningError, AutoCADNoDocumentError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[API] get_snapshot error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/v2/snapshot")
async def get_snapshot_post(request: SnapshotRequest):
    """获取图纸快照（POST）"""
    try:
        controller = get_controller()
        return await controller.get_snapshot(
            include_content=request.include_content,
            include_screenshot=request.include_screenshot,
            only_visible=request.only_visible,
            max_entities=request.max_entities
        )
    except (AutoCADNotRunningError, AutoCADNoDocumentError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[API] get_snapshot error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/v2/step")
async def step(request: StepRequest):
    """
    执行操作并返回快照（核心接口）
    
    支持的 action:
    - draw_from_json: 从 JSON 数据绘制
    - execute_python_com: 执行 Python COM 代码
    """
    try:
        controller = get_controller()
        return await controller.step(
            action=request.action,
            data=request.data,
            code=request.code,
            timeout=request.timeout,
            return_screenshot=request.return_screenshot
        )
    except (AutoCADNotRunningError, AutoCADNoDocumentError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[API] step error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 标准件 API ====================

@router.get("/v2/standard_parts")
async def list_standard_parts():
    """列出所有标准件"""
    try:
        controller = get_controller()
        return await controller.list_standard_parts()
    except Exception as e:
        logger.error(f"[API] list_standard_parts error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/v2/standard_parts/{part_type}/draw")
async def draw_standard_part(part_type: str, request: StandardPartRequest):
    """绘制标准件"""
    try:
        controller = get_controller()
        result = await controller.draw_standard_part(
            part_type=part_type,
            parameters=request.parameters,
            preset=request.preset,
            position=request.position
        )
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error"))
        return result
    except HTTPException:
        raise
    except (AutoCADNotRunningError, AutoCADNoDocumentError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[API] draw_standard_part error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/v2/standard_parts/{part_type}/presets")
async def get_part_presets(part_type: str):
    """获取标准件预设规格"""
    try:
        from controllers.autocad_v2.templates.registry import TemplateRegistry
        template_class = TemplateRegistry.get(part_type)
        if not template_class:
            raise HTTPException(status_code=404, detail=f"Part type not found: {part_type}")
        return {
            "part_type": part_type,
            "presets": template_class.get_presets()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] get_part_presets error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 兼容旧 API ====================

@router.post("/v2/execute_drawing")
async def execute_drawing(request: Dict[str, Any]):
    """兼容旧版 execute_drawing API"""
    try:
        controller = get_controller()
        drawing_data = request.get("drawing_data", {})
        
        if drawing_data and not any(k in drawing_data for k in ["layer_colors", "elements"]):
            results = []
            for fname, content in sorted(drawing_data.items()):
                result = await controller.step(
                    action="draw_from_json",
                    data=content,
                    return_screenshot=False
                )
                results.append({
                    "file": fname,
                    "success": result["execution"]["success"],
                    "entities_created": result["execution"]["entities_created"]
                })
            return {"status": "success", "details": results}
        else:
            result = await controller.step(
                action="draw_from_json",
                data=drawing_data,
                return_screenshot=False
            )
            return {
                "status": "success" if result["execution"]["success"] else "error",
                "details": [f"Drew {result['execution']['entities_created']} entities"]
            }
    except (AutoCADNotRunningError, AutoCADNoDocumentError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[API] execute_drawing error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/v2/visible_drawing_data")
async def get_visible_drawing_data(only_visible: bool = True):
    """兼容旧版 visible_drawing_data API"""
    try:
        controller = get_controller()
        result = await controller.get_snapshot(
            include_content=True,
            include_screenshot=False,
            only_visible=only_visible
        )
        return {
            "status": "success",
            "view_bounds": result["document_info"].get("bounds", {"min": [0, 0], "max": [0, 0]}),
            "layer_colors": result.get("content", {}).get("layer_colors", {}),
            "elements": result.get("content", {}).get("elements", {}),
            "summary": result.get("content", {}).get("summary", {})
        }
    except (AutoCADNotRunningError, AutoCADNoDocumentError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[API] get_visible_drawing_data error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


