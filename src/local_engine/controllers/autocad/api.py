from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional, Literal

import os
import json
import traceback

from controllers.autocad.controller import AutoCADController
from controllers.autocad.drawing_replicator import DrawingReplicator


router = APIRouter()


# ==================== Request/Response Models ====================

class EntityOperation(BaseModel):
    """单个实体的操作定义"""
    handle: str
    action: Literal["modify", "delete", "move", "copy"]
    properties: Optional[Dict[str, Any]] = None  # 用于 modify: {"text": "xxx", "height": 3.0}
    delta: Optional[List[float]] = None          # 用于 move/copy: [dx, dy, dz]


class ModifyEntitiesRequest(BaseModel):
    """批量修改实体的请求"""
    operations: List[EntityOperation]


class DrawRequest(BaseModel):
    """
    Cloud Backend 下发的最终绘图数据：
    { "filename1.json": { ... }, "filename2.json": { ... } }
    """

    drawing_data: dict
    draw_delay: float = 0.2  # 每个元素绘制后的延迟（秒），默认 0.05 秒，让用户能看到绘制过程


@router.post("/execute_drawing")
async def execute_drawing(request: DrawRequest):
    """
    Receive JSON drawing data from Cloud Backend and execute it in AutoCAD.
    This is a 'dumb' executor. It doesn't think, it just draws.
    """
    try:
        print(f"\n{'='*60}")
        print(f"[execute_drawing] 收到绘图请求")
        print(f"[execute_drawing] 组件数量: {len(request.drawing_data)}")
        print(f"[execute_drawing] 组件列表:")
        for fname in request.drawing_data.keys():
            content = request.drawing_data[fname]
            layer_count = len(content.get('layer_colors', {})) if isinstance(content, dict) else 0
            elements = content.get('elements', {}) if isinstance(content, dict) else {}
            total_elements = sum(len(v) for v in elements.values() if isinstance(v, list))
            print(f"  - {fname}: {layer_count} 图层, {total_elements} 元素")
        print(f"{'='*60}")

        # 1. Connect to AutoCAD
        cad_controller = AutoCADController()
        if not cad_controller.connect():
            # Try to start it? Or just fail?
            # Ideally we should try to start it if not running, but for now let's fail fast
            raise HTTPException(
                status_code=500,
                detail="Could not connect to AutoCAD. Please ensure it is running.",
            )

        results = []

        # 2. Iterate and Draw (按文件名排序以保证顺序)
        # request.drawing_data is expected to be Dict[filename, json_content_dict]
        sorted_files = sorted(request.drawing_data.keys())
        
        for idx, fname in enumerate(sorted_files):
            content = request.drawing_data[fname]
            print(f"\n[execute_drawing] 绘制组件 [{idx+1}/{len(sorted_files)}]: {fname}")
            
            # 验证数据结构
            if not isinstance(content, dict):
                print(f"  [ERROR] 内容不是字典类型: {type(content)}")
                results.append(f"Error {fname}: Invalid content type")
                continue
                
            if 'elements' not in content:
                print(f"  [ERROR] 缺少 'elements' 字段")
                results.append(f"Error {fname}: Missing 'elements' field")
                continue
            
            elements = content.get('elements', {})
            print(f"  [DEBUG] 元素统计:")
            print(f"    - lines: {len(elements.get('lines', []))}")
            print(f"    - circles: {len(elements.get('circles', []))}")
            print(f"    - arcs: {len(elements.get('arcs', []))}")
            print(f"    - polylines: {len(elements.get('polylines', []))}")
            print(f"    - texts: {len(elements.get('texts', []))}")
            print(f"    - dimensions: {len(elements.get('dimensions', []))}")
            
            try:
                import tempfile

                with tempfile.NamedTemporaryFile(
                    mode="w", delete=False, suffix=".json", encoding="utf-8"
                ) as tmp:
                    json.dump(content, tmp, ensure_ascii=False)
                    tmp_path = tmp.name

                # 创建复刻器，传入绘制延迟参数
                replicator = DrawingReplicator(json_file=tmp_path, draw_delay=request.draw_delay)
                replicator.cad = cad_controller
                # Execute drawing (只在第一个文件设置 DIMLFAC)
                replicator.replicate_all(setup_dimlfac=(idx == 0))

                # Cleanup
                os.unlink(tmp_path)
                results.append(f"Success: {fname}")
                print(f"  [OK] {fname} 绘制完成")

            except Exception as e:
                print(f"Error drawing {fname}: {e}")
                results.append(f"Error {fname}: {str(e)}")

        cad_controller.zoom_extents()
        return {"status": "success", "details": results}

    except Exception as e:
        error_msg = f"Error executing drawing: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=error_msg)


# ==================== 图纸数据获取 API ====================

@router.get("/visible_drawing_data")
async def get_visible_drawing_data(only_visible: bool = True):
    """
    获取当前 AutoCAD 可视区域的图形数据（带 handle）
    
    Args:
        only_visible: 是否只获取当前视图可见的实体，默认 True
        
    Returns:
        {
            "status": "success",
            "view_bounds": {"min": [x, y], "max": [x, y]},
            "layer_colors": {"图层名": 颜色值, ...},
            "elements": {
                "lines": [{"handle": "xxx", "start": [...], "end": [...], ...}],
                "circles": [...],
                "arcs": [...],
                "polylines": [...],
                "texts": [...],
                "dimensions": [...]
            },
            "summary": {
                "total_count": 123,
                "by_type": {"lines": 10, "circles": 5, ...}
            }
        }
    """
    try:
        print(f"\n{'='*60}")
        print(f"[visible_drawing_data] 收到请求，only_visible={only_visible}")
        
        cad = AutoCADController()
        if not cad.connect():
            raise HTTPException(
                status_code=500,
                detail="无法连接到 AutoCAD，请确保 AutoCAD 已打开并加载了图纸"
            )
        
        # 获取当前视图边界
        view_bounds = cad.get_current_view_bounds()
        
        # 提取图纸数据
        data = cad.extract_drawing_data(only_visible=only_visible)
        
        # 计算统计摘要
        summary = {
            "total_count": 0,
            "by_type": {}
        }
        for elem_type, elements in data.get("elements", {}).items():
            count = len(elements)
            summary["by_type"][elem_type] = count
            summary["total_count"] += count
        
        print(f"[visible_drawing_data] 提取完成，共 {summary['total_count']} 个实体")
        print(f"{'='*60}\n")
        
        return {
            "status": "success",
            "view_bounds": {
                "min": list(view_bounds[0]),
                "max": list(view_bounds[1])
            },
            "layer_colors": data.get("layer_colors", {}),
            "elements": data.get("elements", {}),
            "summary": summary
        }
        
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"获取图纸数据失败: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=error_msg)


# ==================== 批量修改实体 API ====================

@router.post("/modify_entities")
async def modify_entities(request: ModifyEntitiesRequest):
    """
    批量修改 AutoCAD 实体
    
    支持的操作类型：
    - modify: 修改实体属性
    - delete: 删除实体
    - move: 移动实体
    - copy: 复制实体
    
    请求示例:
    {
        "operations": [
            {
                "handle": "2F8",
                "action": "modify",
                "properties": {"text": "新文字", "height": 3.0}
            },
            {
                "handle": "2F9",
                "action": "delete"
            },
            {
                "handle": "2FA",
                "action": "move",
                "delta": [10.0, 20.0, 0.0]
            }
        ]
    }
    
    Returns:
        {
            "status": "success",
            "results": [
                {"handle": "2F8", "status": "success", "action": "modify"},
                {"handle": "2F9", "status": "success", "action": "delete"},
                {"handle": "2FA", "status": "error", "action": "move", "error": "..."}
            ],
            "summary": {"success": 2, "failed": 1}
        }
    """
    try:
        print(f"\n{'='*60}")
        print(f"[modify_entities] 收到批量修改请求，共 {len(request.operations)} 个操作")
        
        cad = AutoCADController()
        if not cad.connect():
            raise HTTPException(
                status_code=500,
                detail="无法连接到 AutoCAD，请确保 AutoCAD 已打开"
            )
        
        results = []
        success_count = 0
        failed_count = 0
        
        for op in request.operations:
            result = {"handle": op.handle, "action": op.action}
            
            try:
                # 获取实体
                entity = cad.get_entity(op.handle)
                if not entity:
                    raise ValueError(f"找不到句柄为 {op.handle} 的实体")
                
                etype = entity.ObjectName
                print(f"  [{op.action}] handle={op.handle}, type={etype}")
                
                # 执行操作
                if op.action == "delete":
                    entity.Delete()
                    result["status"] = "success"
                    
                elif op.action == "move":
                    if not op.delta or len(op.delta) < 2:
                        raise ValueError("move 操作需要提供 delta 参数 [dx, dy, dz]")
                    dx, dy = op.delta[0], op.delta[1]
                    dz = op.delta[2] if len(op.delta) > 2 else 0
                    
                    # 使用 COM 的 Move 方法
                    from_pt = cad.vtPoint(0, 0, 0)
                    to_pt = cad.vtPoint(dx, dy, dz)
                    entity.Move(from_pt, to_pt)
                    result["status"] = "success"
                    
                elif op.action == "copy":
                    if not op.delta or len(op.delta) < 2:
                        raise ValueError("copy 操作需要提供 delta 参数 [dx, dy, dz]")
                    dx, dy = op.delta[0], op.delta[1]
                    dz = op.delta[2] if len(op.delta) > 2 else 0
                    
                    from_pt = cad.vtPoint(0, 0, 0)
                    to_pt = cad.vtPoint(dx, dy, dz)
                    new_entity = entity.Copy()
                    new_entity.Move(from_pt, to_pt)
                    result["status"] = "success"
                    result["new_handle"] = new_entity.Handle
                    
                elif op.action == "modify":
                    if not op.properties:
                        raise ValueError("modify 操作需要提供 properties 参数")
                    
                    props = op.properties
                    
                    # 根据实体类型应用修改
                    if etype in ["AcDbText", "AcDbMText"]:
                        if "text" in props:
                            entity.TextString = props["text"]
                        if "height" in props:
                            entity.Height = props["height"]
                        if "position" in props:
                            pos = props["position"]
                            entity.InsertionPoint = cad.vtPoint(pos[0], pos[1], pos[2] if len(pos) > 2 else 0)
                        if "rotation" in props:
                            entity.Rotation = props["rotation"]
                            
                    elif etype == "AcDbLine":
                        if "start" in props:
                            pt = props["start"]
                            entity.StartPoint = cad.vtPoint(pt[0], pt[1], pt[2] if len(pt) > 2 else 0)
                        if "end" in props:
                            pt = props["end"]
                            entity.EndPoint = cad.vtPoint(pt[0], pt[1], pt[2] if len(pt) > 2 else 0)
                        if "layer" in props:
                            entity.Layer = props["layer"]
                        if "color" in props:
                            entity.Color = props["color"]
                            
                    elif etype == "AcDbCircle":
                        if "center" in props:
                            pt = props["center"]
                            entity.Center = cad.vtPoint(pt[0], pt[1], pt[2] if len(pt) > 2 else 0)
                        if "radius" in props:
                            entity.Radius = props["radius"]
                        if "layer" in props:
                            entity.Layer = props["layer"]
                            
                    elif etype == "AcDbArc":
                        if "center" in props:
                            pt = props["center"]
                            entity.Center = cad.vtPoint(pt[0], pt[1], pt[2] if len(pt) > 2 else 0)
                        if "radius" in props:
                            entity.Radius = props["radius"]
                        if "start_angle" in props:
                            import math
                            entity.StartAngle = math.radians(props["start_angle"])
                        if "end_angle" in props:
                            import math
                            entity.EndAngle = math.radians(props["end_angle"])
                            
                    elif etype == "AcDbPolyline":
                        # 多段线修改比较复杂，这里支持修改单个顶点
                        if "vertex_index" in props and "vertex_position" in props:
                            idx = props["vertex_index"]
                            pos = props["vertex_position"]
                            entity.SetCoordinate(idx, cad.vtFloat(pos[:2]))
                        if "layer" in props:
                            entity.Layer = props["layer"]
                    
                    # 通用属性
                    if "layer" in props and etype not in ["AcDbPolyline"]:  # 避免重复设置
                        try:
                            entity.Layer = props["layer"]
                        except:
                            pass
                    if "color" in props:
                        try:
                            entity.Color = props["color"]
                        except:
                            pass
                    
                    result["status"] = "success"
                    
                else:
                    raise ValueError(f"不支持的操作类型: {op.action}")
                
                success_count += 1
                
            except Exception as e:
                result["status"] = "error"
                result["error"] = str(e)
                failed_count += 1
                print(f"    [ERROR] {e}")
            
            results.append(result)
        
        # 刷新显示
        try:
            cad.doc.Regen(1)  # acActiveViewport = 1
        except:
            pass
        
        print(f"[modify_entities] 完成，成功: {success_count}，失败: {failed_count}")
        print(f"{'='*60}\n")
        
        return {
            "status": "success" if failed_count == 0 else "partial",
            "results": results,
            "summary": {
                "success": success_count,
                "failed": failed_count
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"批量修改失败: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=error_msg)


