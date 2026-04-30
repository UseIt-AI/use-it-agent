"""
AutoCAD V2 API 路由

提供 RESTful API 接口，支持：
- 状态管理
- 快照获取
- 操作执行（三种 Action 类型）
- 标准件绘制
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List, Optional, Literal, Tuple
import logging
import traceback

from .controller import AutoCADControllerV2, AutoCADNotRunningError, AutoCADNoDocumentError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/autocad/v2", tags=["AutoCAD V2"])

# 全局控制器实例
_controller: Optional[AutoCADControllerV2] = None


def get_controller() -> AutoCADControllerV2:
    """获取控制器实例"""
    global _controller
    if _controller is None:
        _controller = AutoCADControllerV2()
    return _controller


# ==================== 请求/响应模型 ====================

class StepRequest(BaseModel):
    """step 接口请求"""
    action: Literal["draw_from_json", "execute_python_com"]
    data: Optional[Dict[str, Any]] = None      # 用于 draw_from_json
    code: Optional[str] = None                  # 用于 execute_python_com
    timeout: int = 60
    return_screenshot: bool = True


class OpenDrawingRequest(BaseModel):
    """打开图纸请求"""
    file_path: str
    read_only: bool = False


class CloseDrawingRequest(BaseModel):
    """关闭图纸请求"""
    save: bool = False


class NewDrawingRequest(BaseModel):
    """新建图纸请求"""
    template: Optional[str] = None


class SnapshotRequest(BaseModel):
    """快照请求"""
    include_content: bool = True
    include_screenshot: bool = True
    only_visible: bool = False
    max_entities: Optional[int] = None


class StandardPartRequest(BaseModel):
    """标准件绘制请求"""
    parameters: Optional[Dict[str, Any]] = None
    preset: Optional[str] = None
    position: Tuple[float, float] = (0, 0)


# ==================== API 端点 ====================

@router.post("/launch")
async def launch_autocad():
    """
    启动或连接 AutoCAD 应用程序
    
    如果 AutoCAD 已在运行，则连接到现有实例；否则启动新实例。
    不会打开或新建任何文档。
    
    Returns:
        {
            "success": bool,
            "already_running": bool,
            "version": str or None,
            "document_count": int,
            "error": str or None
        }
    """
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


@router.get("/status")
async def get_status():
    """
    获取 AutoCAD 状态
    
    Returns:
        {
            "running": bool,
            "has_document": bool,
            "document_info": {...} or None
        }
    """
    try:
        controller = get_controller()
        result = await controller.get_status()
        return result
    except Exception as e:
        logger.error(f"[API] get_status error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/open")
async def open_drawing(request: OpenDrawingRequest):
    """
    打开图纸
    
    Args:
        file_path: 图纸文件路径
        read_only: 是否只读打开
    """
    try:
        controller = get_controller()
        result = await controller.open_drawing(
            file_path=request.file_path,
            read_only=request.read_only
        )
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result.get("error", "Failed to open drawing"))
        
        return result
    except HTTPException:
        raise
    except (AutoCADNotRunningError, AutoCADNoDocumentError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[API] open_drawing error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/close")
async def close_drawing(request: CloseDrawingRequest):
    """
    关闭当前图纸
    
    Args:
        save: 是否保存
    """
    try:
        controller = get_controller()
        result = await controller.close_drawing(save=request.save)
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result.get("error", "Failed to close drawing"))
        
        return result
    except HTTPException:
        raise
    except (AutoCADNotRunningError, AutoCADNoDocumentError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[API] close_drawing error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/new")
async def new_drawing(request: NewDrawingRequest):
    """
    创建新图纸
    
    Args:
        template: 模板文件路径（可选）
    """
    try:
        controller = get_controller()
        result = await controller.new_drawing(template=request.template)
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result.get("error", "Failed to create drawing"))
        
        return result
    except HTTPException:
        raise
    except (AutoCADNotRunningError, AutoCADNoDocumentError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[API] new_drawing error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/snapshot")
async def get_snapshot(
    include_content: bool = True,
    include_screenshot: bool = True,
    only_visible: bool = False,
    max_entities: Optional[int] = None
):
    """
    获取图纸快照
    
    Args:
        include_content: 是否包含图纸内容
        include_screenshot: 是否包含截图
        only_visible: 是否只提取可见区域
        max_entities: 最大实体数量
    """
    try:
        controller = get_controller()
        result = await controller.get_snapshot(
            include_content=include_content,
            include_screenshot=include_screenshot,
            only_visible=only_visible,
            max_entities=max_entities
        )
        return result
    except (AutoCADNotRunningError, AutoCADNoDocumentError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[API] get_snapshot error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/snapshot")
async def get_snapshot_post(request: SnapshotRequest):
    """
    获取图纸快照（POST 版本）
    """
    try:
        controller = get_controller()
        result = await controller.get_snapshot(
            include_content=request.include_content,
            include_screenshot=request.include_screenshot,
            only_visible=request.only_visible,
            max_entities=request.max_entities
        )
        return result
    except (AutoCADNotRunningError, AutoCADNoDocumentError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[API] get_snapshot error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/step")
async def step(request: StepRequest):
    """
    执行操作并返回快照（核心接口）
    
    支持的 action 类型：
    - draw_from_json: 从 JSON 数据绘制
    - execute_python_com: 执行 Python COM 代码（可通过 doc.SendCommand() 执行 AutoCAD 命令）
    
    示例请求：
    
    1. draw_from_json:
    ```json
    {
        "action": "draw_from_json",
        "data": {
            "layer_colors": {"轮廓": 7},
            "elements": {
                "lines": [{"start": [0,0,0], "end": [100,0,0], "layer": "轮廓"}]
            }
        }
    }
    ```
    
    2. execute_python_com:
    ```json
    {
        "action": "execute_python_com",
        "code": "line = ms.AddLine(vtPoint(0,0,0), vtPoint(100,100,0))"
    }
    ```
    """
    try:
        controller = get_controller()
        
        logger.info(f"[API] step: action={request.action}")
        
        result = await controller.step(
            action=request.action,
            data=request.data,
            code=request.code,
            timeout=request.timeout,
            return_screenshot=request.return_screenshot
        )
        
        return result
    
    except (AutoCADNotRunningError, AutoCADNoDocumentError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[API] step error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 标准件 API ====================

@router.get("/standard_parts")
async def list_standard_parts():
    """
    列出所有可用的标准件
    
    Returns:
        {
            "parts": [
                {
                    "type": "flange",
                    "description": "法兰盘",
                    "parameters": {...schema...},
                    "presets": ["DN50", "DN100", ...]
                },
                ...
            ]
        }
    """
    try:
        controller = get_controller()
        result = await controller.list_standard_parts()
        return result
    except Exception as e:
        logger.error(f"[API] list_standard_parts error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/standard_parts/{part_type}/draw")
async def draw_standard_part(part_type: str, request: StandardPartRequest):
    """
    绘制标准件
    
    Args:
        part_type: 标准件类型（如 "flange", "bolt", "u_channel"）
        parameters: 自定义参数
        preset: 预设规格（如 "DN200", "M10"）
        position: 插入位置
    
    示例请求：
    
    1. 使用预设规格:
    ```json
    {
        "preset": "DN200"
    }
    ```
    
    2. 自定义参数:
    ```json
    {
        "parameters": {
            "outer_diameter": 300,
            "inner_diameter": 150,
            "bolt_count": 12
        }
    }
    ```
    """
    try:
        controller = get_controller()
        
        logger.info(f"[API] draw_standard_part: type={part_type}, preset={request.preset}")
        
        result = await controller.draw_standard_part(
            part_type=part_type,
            parameters=request.parameters,
            preset=request.preset,
            position=request.position
        )
        
        if not result.get("success"):
            raise HTTPException(
                status_code=400, 
                detail=result.get("error", f"Failed to draw {part_type}")
            )
        
        return result
        
    except HTTPException:
        raise
    except (AutoCADNotRunningError, AutoCADNoDocumentError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[API] draw_standard_part error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/standard_parts/{part_type}/presets")
async def get_part_presets(part_type: str):
    """
    获取标准件的预设规格列表
    
    Args:
        part_type: 标准件类型
    
    Returns:
        {
            "part_type": "flange",
            "presets": {
                "DN50": {"outer_diameter": 140, ...},
                "DN100": {...},
                ...
            }
        }
    """
    try:
        from .templates.registry import TemplateRegistry
        
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

@router.post("/execute_drawing")
async def execute_drawing(request: Dict[str, Any]):
    """
    兼容旧版 execute_drawing API
    
    将请求转换为 step(action="draw_from_json")
    """
    try:
        controller = get_controller()
        
        drawing_data = request.get("drawing_data", {})
        draw_delay = request.get("draw_delay", 0.0)
        
        # 如果是多文件格式，合并处理
        if drawing_data and not any(k in drawing_data for k in ["layer_colors", "elements"]):
            # 多文件格式：{"file1.json": {...}, "file2.json": {...}}
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
            
            return {
                "status": "success",
                "details": results
            }
        else:
            # 单文件格式
            result = await controller.step(
                action="draw_from_json",
                data=drawing_data,
                return_screenshot=False
            )
            
            return {
                "status": "success" if result["execution"]["success"] else "error",
                "details": [f"Drew {result['execution']['entities_created']} entities"]
            }
            
    except Exception as e:
        logger.error(f"[API] execute_drawing error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/visible_drawing_data")
async def get_visible_drawing_data(only_visible: bool = True):
    """
    兼容旧版 visible_drawing_data API
    """
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
        
    except Exception as e:
        logger.error(f"[API] get_visible_drawing_data error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


