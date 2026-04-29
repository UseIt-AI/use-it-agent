"""
Computer API 端点 - 桌面自动化

基于 step 模式的统一接口设计，与 Browser API 保持一致。

主要端点:
- POST /api/v1/computer/step         执行操作（主入口）
- GET  /api/v1/computer/screen       获取屏幕信息
- POST /api/v1/computer/screenshot   快捷截图

支持的 Action 类型:
- click: 点击 {"type": "click", "x": 100, "y": 200, "button": "left"}
- double_click: 双击 {"type": "double_click", "x": 100, "y": 200}
- type: 输入文字 {"type": "type", "text": "hello"}
- keypress: 按键 {"type": "keypress", "keys": ["ctrl", "a"]}
- scroll: 滚动 {"type": "scroll", "scroll_x": 0, "scroll_y": -3, "x": 500, "y": 300}
- move: 移动鼠标 {"type": "move", "x": 100, "y": 200}
- drag: 拖拽 {"type": "drag", "path": [[100,100], [400,300]], "button": "left"}
- screenshot: 截图 {"type": "screenshot", "resize": true}
- wait: 等待 {"type": "wait", "seconds": 1.0}
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
import logging

from controllers.computer_use.controller import ComputerUseController
from controllers.computer_use.handlers import ScreenHandler
from .project import format_tree_as_text

logger = logging.getLogger(__name__)
router = APIRouter()


# ==================== 请求模型 ====================

class StepRequest(BaseModel):
    """
    执行操作请求（主入口）
    
    支持单个或多个操作，顺序执行，遇错停止。
    """
    actions: List[Dict[str, Any]] = Field(..., description="Action 列表")
    return_screenshot: bool = Field(
        default=False, 
        description="执行完成后是否自动返回截图"
    )


class ScreenshotRequest(BaseModel):
    """截图请求"""
    resize: bool = Field(default=True, description="是否缩放到 1920x1080")
    # Project files 相关参数
    include_project_files: bool = Field(default=False, description="是否包含项目文件列表")
    project_path: Optional[str] = Field(default=None, description="项目根目录路径（include_project_files=true 时必填）")
    project_max_depth: int = Field(default=4, ge=1, le=10, description="项目文件遍历最大深度")
    project_max_files: int = Field(default=500, ge=1, le=2000, description="项目文件最大数量")


# ==================== API 端点 ====================

@router.post("/step")
async def step(request: StepRequest) -> Dict[str, Any]:
    """
    执行操作并返回结果（主入口）
    
    这是 AI Agent 的主要接口：
    1. 执行 1-N 个操作（顺序执行，遇错停止）
    2. 返回所有操作结果
    3. 可选：自动返回最终截图
    
    支持的 Action 类型:
    
    **鼠标操作**:
    - `{"type": "click", "x": 100, "y": 200, "button": "left|right|middle"}`
    - `{"type": "double_click", "x": 100, "y": 200, "button": "left"}`
    - `{"type": "move", "x": 100, "y": 200}`
    - `{"type": "drag", "path": [[100,100], [400,300]], "button": "left", "speed": 800}`
    - `{"type": "scroll", "scroll_x": 0, "scroll_y": -3, "x": 500, "y": 300}`
    
    **键盘操作**:
    - `{"type": "type", "text": "hello world"}`
    - `{"type": "keypress", "keys": ["ctrl", "a"]}`
    - `{"type": "keypress", "keys": ["enter"]}`
    
    **其他**:
    - `{"type": "screenshot", "resize": true}`
    - `{"type": "wait", "seconds": 1.0}`
    
    示例请求:
    ```json
    {
        "actions": [
            {"type": "click", "x": 100, "y": 200},
            {"type": "type", "text": "hello"},
            {"type": "keypress", "keys": ["enter"]}
        ],
        "return_screenshot": true
    }
    ```
    
    返回:
    ```json
    {
        "success": true,
        "data": {
            "action_results": [
                {"index": 0, "ok": true, "result": {"type": "click", ...}},
                {"index": 1, "ok": true, "result": {"type": "type", ...}},
                {"index": 2, "ok": true, "result": {"type": "keypress", ...}}
            ],
            "screenshot": "base64..."  // 仅当 return_screenshot=true
        }
    }
    ```
    """
    logger.info(f"[Computer API] step: {len(request.actions)} actions, return_screenshot={request.return_screenshot}")
    # DEBUG: 打印收到的 actions
    for i, action in enumerate(request.actions):
        logger.info(f"[Computer API] action[{i}]: {action}")
    
    if not request.actions:
        return {
            "success": True,
            "data": {
                "action_results": [],
                "message": "No actions to execute"
            }
        }
    
    try:
        controller = ComputerUseController()
        result = await controller.run_actions(request.actions)
        
        response_data = {
            "action_results": result.get("results", []),
        }
        
        # 如果请求返回截图，自动执行截图
        if request.return_screenshot:
            screenshot_result = await controller.run_actions([{"type": "screenshot", "resize": True}])
            if screenshot_result.get("status") == "ok" and screenshot_result.get("results"):
                first = screenshot_result["results"][0]
                if first.get("ok") and first.get("result", {}).get("image_base64"):
                    response_data["screenshot"] = first["result"]["image_base64"]
        
        # 判断整体是否成功
        all_ok = all(r.get("ok", False) for r in result.get("results", []))
        
        return {
            "success": result.get("status") == "ok" and all_ok,
            "data": response_data
        }
        
    except Exception as e:
        logger.error(f"[Computer API] step failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/screen")
async def get_screen_info() -> Dict[str, Any]:
    """
    获取屏幕信息（逻辑坐标系）
    
    返回逻辑分辨率，与 pynput 鼠标坐标、截图分辨率一致。
    
    Returns:
        {
            "success": true,
            "data": {
                "width": 1920,
                "height": 1080,
                "scale": 1.25,
                "scale_percent": 125,
                "physical_width": 2560,
                "physical_height": 1440,
                "coordinate_system": "logical"
            }
        }
    """
    result = ScreenHandler.get_screen_size()
    
    if not result.get("success"):
        error = result.get("error", "Unknown error")
        logger.error(f"[Computer API] get_screen_info failed: {error}")
        raise HTTPException(status_code=500, detail=f"Failed to get screen info: {error}")
    
    size = result["size"]
    physical = result["physical_size"]
    
    return {
        "success": True,
        "data": {
            "width": size["width"],
            "height": size["height"],
            "scale": result["scale"],
            "scale_percent": result["scale_percent"],
            "physical_width": physical["width"],
            "physical_height": physical["height"],
            "coordinate_system": "logical"
        }
    }


@router.post("/screenshot")
async def screenshot(request: ScreenshotRequest = None) -> Dict[str, Any]:
    """
    快捷截图接口
    
    这是一个便捷接口，等价于:
    POST /step {"actions": [{"type": "screenshot", "resize": true}]}
    
    Args:
        resize: 是否缩放到 1920x1080（默认 true）
    
    Returns:
        {
            "success": true,
            "data": {
                "type": "screenshot",
                "image_base64": "...",
                "resized": true
            }
        }
    """
    if request is None:
        request = ScreenshotRequest()
    
    logger.info(f"[Computer API] screenshot: resize={request.resize}")
    
    try:
        controller = ComputerUseController()
        result = await controller.run_actions([{
            "type": "screenshot",
            "resize": request.resize
        }])
        
        if result.get("status") == "ok" and result.get("results"):
            first_result = result["results"][0]
            if first_result.get("ok"):
                response_data = first_result.get("result", {})
                
                # 如果需要项目文件列表（使用紧凑 text 格式）
                if request.include_project_files and request.project_path:
                    try:
                        project_tree = format_tree_as_text(
                            project_path=request.project_path,
                            max_depth=request.project_max_depth,
                        )
                        response_data["project_files"] = project_tree
                    except Exception as e:
                        logger.warning(f"[Computer API] Failed to get project files: {e}")
                        response_data["project_files"] = f"Error: {str(e)}"
                
                return {"success": True, "data": response_data}
            else:
                return {"success": False, "error": first_result.get("error", "Unknown error")}
        
        return {"success": False, "error": result.get("message", "Execution failed")}
        
    except Exception as e:
        logger.error(f"[Computer API] screenshot failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
