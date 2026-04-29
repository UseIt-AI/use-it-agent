"""
AutoCAD Controller V2

参照 PPT Controller 架构设计：
- 对外暴露异步接口（与 FastAPI 兼容）
- 内部使用同步实现（COM 稳定性）
- 通过线程池桥接

支持的 Action 类型：
- draw_from_json: 从 JSON 数据绘制图纸
- execute_python_com: 执行 Python COM 代码
"""

from typing import Dict, Any, List, Optional, Tuple
import asyncio
import logging
import tempfile
import subprocess
import base64
import os

logger = logging.getLogger(__name__)

NOT_RUNNING_ERROR = "AutoCAD is not running. Please call 'launch' first to start AutoCAD."
NO_DOCUMENT_ERROR = "No document is open in AutoCAD. Please call 'open' or 'new' first."


class AutoCADNotRunningError(Exception):
    """AutoCAD 未运行时抛出"""
    def __init__(self):
        super().__init__(NOT_RUNNING_ERROR)


class AutoCADNoDocumentError(Exception):
    """AutoCAD 没有打开文档时抛出"""
    def __init__(self):
        super().__init__(NO_DOCUMENT_ERROR)


class AutoCADControllerV2:
    """
    AutoCAD Controller V2 - 参照 PPT Controller 架构
    
    混合架构：
    - 对外暴露异步接口
    - 内部使用同步 COM 实现
    - 通过 run_in_executor 桥接
    """
    
    def __init__(self):
        pass
    
    # ==================== 公共方法 - 启动 ====================
    
    async def launch(self) -> Dict[str, Any]:
        """
        启动或连接 AutoCAD 应用程序（不打开/新建文档）
        
        Returns:
            {
                "success": bool,
                "already_running": bool,
                "version": str or None,
                "document_count": int,
                "error": str or None
            }
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._launch_sync)
    
    # ==================== 公共方法 - 状态管理 ====================
    
    async def get_status(self) -> Dict[str, Any]:
        """
        检查 AutoCAD 是否运行，获取当前图纸信息和所有打开的文档列表
        
        Returns:
            {
                "running": bool,
                "has_document": bool,
                "document_count": int,
                "documents": [                    # 所有打开的文档列表
                    {
                        "name": "Drawing1.dwg",
                        "path": "C:/...",
                        "is_active": True,
                        "saved": bool,
                        "read_only": bool
                    },
                    ...
                ],
                "document_info": {...} or None    # 当前活动文档详情
            }
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._get_status_sync)
    
    async def activate_drawing(self, name: str = None, index: int = None) -> Dict[str, Any]:
        """
        切换到指定的文档
        
        Args:
            name: 文档名称（如 "Drawing1.dwg"）
            index: 文档索引（从 0 开始）
            
        注意：name 和 index 二选一，name 优先
        
        Returns:
            {
                "success": bool,
                "activated_document": str or None,
                "document_info": {...} or None,
                "error": str or None
            }
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            self._activate_drawing_sync,
            name,
            index
        )
    
    async def open_drawing(
        self, 
        file_path: str, 
        read_only: bool = False
    ) -> Dict[str, Any]:
        """
        打开 AutoCAD 图纸
        
        Args:
            file_path: 图纸文件路径
            read_only: 是否以只读方式打开
        
        Returns:
            {
                "success": bool,
                "document_info": {...} or None,
                "error": str or None
            }
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            self._open_drawing_sync,
            file_path,
            read_only
        )
    
    async def close_drawing(self, save: bool = False) -> Dict[str, Any]:
        """
        关闭当前图纸
        
        Args:
            save: 是否保存图纸
        
        Returns:
            {
                "success": bool,
                "closed_document": str or None,
                "error": str or None
            }
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            self._close_drawing_sync,
            save
        )
    
    async def new_drawing(self, template: str = None) -> Dict[str, Any]:
        """
        创建新图纸
        
        Args:
            template: 模板文件路径（可选）
        
        Returns:
            {
                "success": bool,
                "document_info": {...} or None,
                "error": str or None
            }
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            self._new_drawing_sync,
            template
        )
    
    # ==================== 公共方法 - 快照 ====================
    
    async def get_snapshot(
        self,
        include_content: bool = True,
        include_screenshot: bool = True,
        only_visible: bool = False,
        max_entities: int = None
    ) -> Dict[str, Any]:
        """
        获取当前图纸快照（核心接口）
        
        Args:
            include_content: 是否包含图纸内容（实体数据）
            include_screenshot: 是否包含截图
            only_visible: 是否只提取当前视图可见的实体
            max_entities: 最大实体数量限制
        
        Returns:
            {
                "document_info": {...},
                "content": {...},           # 如果 include_content=True
                "screenshot": "base64..."   # 如果 include_screenshot=True
            }
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            self._get_snapshot_sync,
            include_content,
            include_screenshot,
            only_visible,
            max_entities
        )
    
    # ==================== 公共方法 - 执行操作 ====================
    
    async     def step(
        self,
        action: str,
        data: Dict[str, Any] = None,
        code: str = None,
        timeout: int = 60,
        return_screenshot: bool = True
    ) -> Dict[str, Any]:
        """
        执行操作并返回更新后的快照（核心接口）
        
        Args:
            action: 操作类型
                - "draw_from_json": 从 JSON 数据绘制
                - "execute_python_com": 执行 Python COM 代码
            data: JSON 图纸数据（用于 draw_from_json）
            code: Python 代码（用于 execute_python_com）
            timeout: 超时时间（秒）
            return_screenshot: 是否返回截图
        
        Returns:
            {
                "execution": {
                    "success": bool,
                    "output": str,
                    "error": str or None,
                    "entities_created": int,
                    "entities_modified": int,
                    "entities_deleted": int
                },
                "snapshot": {...}
            }
        """
        loop = asyncio.get_running_loop()
        
        # 0. 先激活 AutoCAD 窗口
        await loop.run_in_executor(None, self._activate_autocad_window_sync)
        
        # 1. 执行操作
        execution_result = await loop.run_in_executor(
            None,
            self._execute_action_sync,
            action,
            data,
            code,
            timeout
        )
        
        # 2. 获取更新后的快照（失败不应掩盖执行结果）
        snapshot = None
        try:
            snapshot = await loop.run_in_executor(
                None,
                self._get_snapshot_sync,
                True,  # include_content
                return_screenshot,
                False,  # only_visible
                None   # max_entities
            )
        except Exception as e:
            logger.warning(f"[AutoCADController] Post-action snapshot failed: {e}")
            snapshot = {"error": str(e)}
        
        return {
            "execution": execution_result,
            "snapshot": snapshot
        }
    
    # ==================== 公共方法 - 标准件 ====================
    
    async def draw_standard_part(
        self,
        part_type: str,
        parameters: Dict[str, Any] = None,
        preset: str = None,
        position: Tuple[float, float] = (0, 0)
    ) -> Dict[str, Any]:
        """
        绘制参数化标准件
        
        Args:
            part_type: 标准件类型（如 "flange", "u_channel", "bolt"）
            parameters: 自定义参数
            preset: 预设规格（如 "DN200"）
            position: 插入位置
        
        Returns:
            {
                "success": bool,
                "part_type": str,
                "parameters_used": {...},
                "entities_created": int,
                "handles": [...]
            }
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            self._draw_standard_part_sync,
            part_type,
            parameters,
            preset,
            position
        )
    
    async def list_standard_parts(self) -> Dict[str, Any]:
        """
        列出所有可用的标准件及其参数
        
        Returns:
            {
                "parts": [
                    {
                        "type": "flange",
                        "description": "法兰盘",
                        "parameters": {...schema...},
                        "presets": ["DN50", "DN80", ...]
                    },
                    ...
                ]
            }
        """
        from .templates.registry import TemplateRegistry
        return {"parts": TemplateRegistry.list_all()}
    
    # ==================== 私有方法 - 同步 COM 操作 ====================
    
    def _launch_sync(self) -> Dict[str, Any]:
        """同步启动或连接 AutoCAD"""
        import pythoncom
        import win32com.client
        import time
        
        pythoncom.CoInitialize()
        try:
            already_running = False
            
            # 先尝试连接已有实例
            try:
                acad = win32com.client.GetActiveObject("AutoCAD.Application")
                already_running = True
                logger.info("[AutoCADController] Connected to existing AutoCAD instance")
            except Exception:
                # 没有运行中的实例，启动新的
                logger.info("[AutoCADController] Starting new AutoCAD instance...")
                acad = win32com.client.Dispatch("AutoCAD.Application")
                logger.info("[AutoCADController] AutoCAD instance created")
            
            acad.Visible = True
            
            # 等待 AutoCAD 窗口完全加载，然后置于前台并最大化
            self._wait_and_focus_autocad(acad, is_new_instance=not already_running)
            
            version = None
            try:
                version = acad.Version
            except Exception:
                pass
            
            doc_count = 0
            try:
                doc_count = acad.Documents.Count
            except Exception:
                pass
            
            logger.info(
                "[AutoCADController] Launch complete: already_running=%s, version=%s, docs=%d",
                already_running, version, doc_count
            )
            
            return {
                "success": True,
                "already_running": already_running,
                "version": version,
                "document_count": doc_count,
                "error": None
            }
            
        except Exception as e:
            error_msg = str(e).lower()
            logger.error(f"[AutoCADController] Failed to launch AutoCAD: {e}", exc_info=True)
            
            # 识别 COM 注册错误，给出友好提示
            if "class not registered" in error_msg or "invalid class string" in error_msg:
                friendly_error = (
                    "AutoCAD is not installed or not properly registered on this machine. "
                    "Please install AutoCAD and try again."
                )
            elif "access" in error_msg and "denied" in error_msg:
                friendly_error = (
                    "Access denied when trying to launch AutoCAD. "
                    "Please run with administrator privileges or check permissions."
                )
            else:
                friendly_error = f"Failed to launch AutoCAD: {e}"
            
            return {
                "success": False,
                "already_running": False,
                "version": None,
                "document_count": 0,
                "error": friendly_error
            }
        finally:
            pythoncom.CoUninitialize()
    
    def _get_status_sync(self) -> Dict[str, Any]:
        """同步获取 AutoCAD 状态，包括所有打开的文档列表"""
        import pythoncom
        import win32com.client
        
        pythoncom.CoInitialize()
        try:
            try:
                acad = win32com.client.GetActiveObject("AutoCAD.Application")
                
                doc_count = acad.Documents.Count
                has_document = doc_count > 0
                document_info = None
                documents = []
                
                # 获取所有打开的文档列表
                if has_document:
                    active_doc = acad.ActiveDocument
                    active_name = active_doc.Name
                    
                    for i in range(doc_count):
                        doc = acad.Documents.Item(i)
                        documents.append({
                            "index": i,
                            "name": doc.Name,
                            "path": doc.FullName if doc.Path else None,
                            "is_active": doc.Name == active_name,
                            "saved": doc.Saved,
                            "read_only": doc.ReadOnly
                        })
                    
                    # 当前活动文档详情
                    document_info = self._extract_document_info(acad, active_doc)
                
                return {
                    "running": True,
                    "has_document": has_document,
                    "document_count": doc_count,
                    "documents": documents,
                    "document_info": document_info
                }
            except Exception as e:
                logger.info(f"[AutoCADController] AutoCAD not running: {e}")
                return {
                    "running": False,
                    "has_document": False,
                    "document_count": 0,
                    "documents": [],
                    "document_info": None
                }
        finally:
            pythoncom.CoUninitialize()
    
    def _activate_drawing_sync(self, name: str = None, index: int = None) -> Dict[str, Any]:
        """同步切换到指定文档"""
        import pythoncom
        
        pythoncom.CoInitialize()
        try:
            acad = self._get_acad_connection()
            
            if acad.Documents.Count == 0:
                return {
                    "success": False,
                    "activated_document": None,
                    "document_info": None,
                    "error": NO_DOCUMENT_ERROR
                }
            
            target_doc = None
            
            # 按名称查找
            if name:
                for i in range(acad.Documents.Count):
                    doc = acad.Documents.Item(i)
                    if doc.Name == name or doc.Name.lower() == name.lower():
                        target_doc = doc
                        break
                
                if not target_doc:
                    # 列出可用文档
                    available = [acad.Documents.Item(i).Name for i in range(acad.Documents.Count)]
                    return {
                        "success": False,
                        "activated_document": None,
                        "document_info": None,
                        "error": f"Document not found: {name}. Available: {available}"
                    }
            
            # 按索引查找
            elif index is not None:
                if index < 0 or index >= acad.Documents.Count:
                    return {
                        "success": False,
                        "activated_document": None,
                        "document_info": None,
                        "error": f"Invalid index: {index}. Valid range: 0-{acad.Documents.Count - 1}"
                    }
                target_doc = acad.Documents.Item(index)
            
            else:
                return {
                    "success": False,
                    "activated_document": None,
                    "document_info": None,
                    "error": "Must specify either 'name' or 'index'"
                }
            
            # 激活文档
            target_doc.Activate()
            
            # 获取文档信息
            document_info = self._extract_document_info(acad, target_doc)
            
            logger.info(f"[AutoCADController] Activated document: {target_doc.Name}")
            
            return {
                "success": True,
                "activated_document": target_doc.Name,
                "document_info": document_info,
                "error": None
            }
            
        except Exception as e:
            logger.error(f"[AutoCADController] Failed to activate document: {e}", exc_info=True)
            return {
                "success": False,
                "activated_document": None,
                "document_info": None,
                "error": str(e)
            }
        finally:
            pythoncom.CoUninitialize()
    
    def _open_drawing_sync(self, file_path: str, read_only: bool = False) -> Dict[str, Any]:
        """同步打开图纸"""
        import pythoncom
        import win32com.client
        from pathlib import Path
        import time
        
        path = Path(file_path)
        if not path.exists():
            return {
                "success": False,
                "document_info": None,
                "error": f"File not found: {file_path}"
            }
        
        abs_path = str(path.absolute())
        
        pythoncom.CoInitialize()
        try:
            acad = self._get_acad_connection()
            acad.Visible = True
            
            # 打开图纸
            doc = acad.Documents.Open(abs_path, read_only)
            
            # 等待加载
            time.sleep(1)
            
            # 激活窗口
            acad.Activate()
            
            document_info = self._extract_document_info(acad, doc)
            
            logger.info(f"[AutoCADController] Opened drawing: {doc.Name}")
            
            return {
                "success": True,
                "document_info": document_info,
                "error": None
            }
            
        except Exception as e:
            logger.error(f"[AutoCADController] Failed to open drawing: {e}", exc_info=True)
            return {
                "success": False,
                "document_info": None,
                "error": str(e)
            }
        finally:
            pythoncom.CoUninitialize()
    
    def _close_drawing_sync(self, save: bool = False) -> Dict[str, Any]:
        """同步关闭图纸"""
        import pythoncom
        
        pythoncom.CoInitialize()
        try:
            acad = self._get_acad_connection()
            
            if acad.Documents.Count == 0:
                return {
                    "success": False,
                    "closed_document": None,
                    "error": NO_DOCUMENT_ERROR
                }
            
            doc = acad.ActiveDocument
            doc_name = doc.Name
            
            if save:
                doc.Save()
            
            doc.Close(save)
            
            logger.info(f"[AutoCADController] Closed document: {doc_name}, saved={save}")
            
            return {
                "success": True,
                "closed_document": doc_name,
                "error": None
            }
            
        except Exception as e:
            logger.error(f"[AutoCADController] Failed to close document: {e}", exc_info=True)
            return {
                "success": False,
                "closed_document": None,
                "error": str(e)
            }
        finally:
            pythoncom.CoUninitialize()
    
    def _new_drawing_sync(self, template: str = None) -> Dict[str, Any]:
        """同步创建新图纸"""
        import pythoncom
        
        pythoncom.CoInitialize()
        try:
            acad = self._get_acad_connection()
            acad.Visible = True
            
            if template:
                doc = acad.Documents.Add(template)
            else:
                doc = acad.Documents.Add()
            
            document_info = self._extract_document_info(acad, doc)
            
            logger.info(f"[AutoCADController] Created new document: {doc.Name}")
            
            return {
                "success": True,
                "document_info": document_info,
                "error": None
            }
            
        except Exception as e:
            logger.error(f"[AutoCADController] Failed to create document: {e}", exc_info=True)
            return {
                "success": False,
                "document_info": None,
                "error": str(e)
            }
        finally:
            pythoncom.CoUninitialize()
    
    def _activate_autocad_window_sync(self) -> None:
        """激活 AutoCAD 窗口并置于前台"""
        import pythoncom
        
        pythoncom.CoInitialize()
        try:
            acad = self._get_acad_connection()
            acad.Visible = True
            self._wait_and_focus_autocad(acad, is_new_instance=False)
            logger.info("[AutoCADController] AutoCAD window activated")
        except Exception as e:
            logger.warning(f"[AutoCADController] Failed to activate AutoCAD window: {e}")
        finally:
            pythoncom.CoUninitialize()
    
    def _get_snapshot_sync(
        self,
        include_content: bool,
        include_screenshot: bool,
        only_visible: bool,
        max_entities: int
    ) -> Dict[str, Any]:
        """同步获取图纸快照"""
        import pythoncom
        
        pythoncom.CoInitialize()
        try:
            acad, doc = self._get_acad_with_doc()
            
            # 1. 文档基本信息
            document_info = self._extract_document_info(acad, doc)
            
            result = {
                "document_info": document_info
            }
            
            # 2. 图纸内容
            if include_content:
                result["content"] = self._extract_content_sync(
                    acad, doc, only_visible, max_entities
                )
            
            # 3. 截图
            if include_screenshot:
                screenshot = self._take_screenshot_sync(acad)
                if screenshot:
                    result["screenshot"] = screenshot
            
            return result
            
        except Exception as e:
            logger.error(f"[AutoCADController] Snapshot error: {e}", exc_info=True)
            raise
        finally:
            pythoncom.CoUninitialize()
    
    def _extract_document_info(self, acad, doc) -> Dict[str, Any]:
        """提取文档基本信息"""
        try:
            model_space = doc.ModelSpace
            entity_count = model_space.Count
        except Exception:
            entity_count = -1
        
        try:
            layer_count = doc.Layers.Count
        except Exception:
            layer_count = -1
        
        # 获取边界
        bounds = None
        try:
            if entity_count > 0:
                min_x = min_y = float('inf')
                max_x = max_y = float('-inf')
                
                for entity in model_space:
                    try:
                        bbox = entity.GetBoundingBox()
                        min_pt, max_pt = bbox[0], bbox[1]
                        min_x = min(min_x, min_pt[0])
                        min_y = min(min_y, min_pt[1])
                        max_x = max(max_x, max_pt[0])
                        max_y = max(max_y, max_pt[1])
                    except:
                        continue
                
                if min_x != float('inf'):
                    bounds = {
                        "min": [min_x, min_y],
                        "max": [max_x, max_y]
                    }
        except Exception:
            pass
        
        return {
            "name": doc.Name,
            "path": doc.FullName if doc.Path else None,
            "saved": doc.Saved,
            "read_only": doc.ReadOnly,
            "entity_count": entity_count,
            "layer_count": layer_count,
            "bounds": bounds,
            "version": acad.Version
        }
    
    def _extract_content_sync(
        self,
        acad,
        doc,
        only_visible: bool,
        max_entities: int
    ) -> Dict[str, Any]:
        """提取图纸内容"""
        import math
        import win32com.client
        
        model_space = doc.ModelSpace
        
        # 图层颜色
        layer_colors = {}
        try:
            for layer in doc.Layers:
                layer_colors[layer.Name] = layer.Color
        except Exception as e:
            logger.warning(f"[AutoCADController] Failed to get layer colors: {e}")
        
        # 元素
        elements = {
            "lines": [],
            "circles": [],
            "arcs": [],
            "polylines": [],
            "texts": [],
            "dimensions": [],
            "blocks": [],
            "hatches": []
        }
        
        # 确定遍历源
        source_collection = model_space
        selection_set = None
        
        try:
            if only_visible:
                try:
                    # 获取当前视图边界
                    view_ctr = doc.GetVariable("VIEWCTR")
                    view_height = doc.GetVariable("VIEWSIZE")
                    screen_size = doc.GetVariable("SCREENSIZE")
                    aspect_ratio = screen_size[0] / screen_size[1]
                    view_width = view_height * aspect_ratio
                    
                    min_x = view_ctr[0] - (view_width / 2)
                    max_x = view_ctr[0] + (view_width / 2)
                    min_y = view_ctr[1] - (view_height / 2)
                    max_y = view_ctr[1] + (view_height / 2)
                    
                    min_pt = self._vt_point(min_x, min_y, 0)
                    max_pt = self._vt_point(max_x, max_y, 0)
                    
                    ss_name = "AI_Visible_Selection"
                    try:
                        doc.SelectionSets.Item(ss_name).Delete()
                    except:
                        pass
                    
                    selection_set = doc.SelectionSets.Add(ss_name)
                    selection_set.Select(0, min_pt, max_pt)  # acSelectionSetWindow = 0
                    
                    source_collection = selection_set
                    logger.info(f"[AutoCADController] Visible entities: {source_collection.Count}")
                except Exception as e:
                    logger.warning(f"[AutoCADController] Failed to create visible selection: {e}")
                    source_collection = model_space
            
            total = source_collection.Count
            if total == 0:
                return {
                    "layer_colors": layer_colors,
                    "elements": elements,
                    "summary": {"total_count": 0, "by_type": {}}
                }
            
            # 应用数量限制
            count = 0
            limit = max_entities if max_entities else total
            
            for entity in source_collection:
                if count >= limit:
                    break
                
                try:
                    etype = entity.ObjectName
                    layer = entity.Layer
                    color = entity.Color
                    handle = entity.Handle
                    
                    # 直线
                    if etype == "AcDbLine":
                        elements["lines"].append({
                            "handle": handle,
                            "start": list(entity.StartPoint),
                            "end": list(entity.EndPoint),
                            "layer": layer,
                            "color": color
                        })
                        count += 1
                    
                    # 圆
                    elif etype == "AcDbCircle":
                        elements["circles"].append({
                            "handle": handle,
                            "center": list(entity.Center),
                            "radius": entity.Radius,
                            "layer": layer,
                            "color": color
                        })
                        count += 1
                    
                    # 圆弧
                    elif etype == "AcDbArc":
                        elements["arcs"].append({
                            "handle": handle,
                            "center": list(entity.Center),
                            "radius": entity.Radius,
                            "start_angle": math.degrees(entity.StartAngle),
                            "end_angle": math.degrees(entity.EndAngle),
                            "layer": layer,
                            "color": color
                        })
                        count += 1
                    
                    # 多段线
                    elif etype == "AcDbPolyline":
                        coords = entity.Coordinates
                        vertices = []
                        for j in range(0, len(coords), 2):
                            if j + 1 < len(coords):
                                vertices.append([coords[j], coords[j+1]])
                        
                        elements["polylines"].append({
                            "handle": handle,
                            "vertices": vertices,
                            "closed": entity.Closed,
                            "layer": layer,
                            "color": color
                        })
                        count += 1
                    
                    # 文字
                    elif etype in ["AcDbText", "AcDbMText"]:
                        elements["texts"].append({
                            "handle": handle,
                            "text": entity.TextString,
                            "position": list(entity.InsertionPoint),
                            "height": entity.Height,
                            "layer": layer,
                            "color": color
                        })
                        count += 1
                    
                    # 标注
                    elif "Dimension" in etype:
                        dim_data = {
                            "handle": handle,
                            "type": etype,
                            "measurement": getattr(entity, 'Measurement', 0),
                            "text_override": getattr(entity, 'TextOverride', '') or "",
                            "layer": layer,
                            "color": color
                        }
                        
                        # 获取标注点
                        for attr in ['ExtLine1Point', 'XLine1Point']:
                            try:
                                val = getattr(entity, attr)
                                if val:
                                    dim_data['ext_line1_point'] = list(val)
                                    break
                            except:
                                continue
                        
                        for attr in ['ExtLine2Point', 'XLine2Point']:
                            try:
                                val = getattr(entity, attr)
                                if val:
                                    dim_data['ext_line2_point'] = list(val)
                                    break
                            except:
                                continue
                        
                        try:
                            dim_data['text_position'] = list(entity.TextPosition)
                        except:
                            pass
                        
                        elements["dimensions"].append(dim_data)
                        count += 1
                    
                    # 块引用
                    elif etype == "AcDbBlockReference":
                        elements["blocks"].append({
                            "handle": handle,
                            "name": entity.Name,
                            "position": list(entity.InsertionPoint),
                            "scale": [entity.XScaleFactor, entity.YScaleFactor, entity.ZScaleFactor],
                            "rotation": math.degrees(entity.Rotation),
                            "layer": layer,
                            "color": color
                        })
                        count += 1
                    
                    # 填充
                    elif etype == "AcDbHatch":
                        elements["hatches"].append({
                            "handle": handle,
                            "pattern_name": entity.PatternName,
                            "layer": layer,
                            "color": color
                        })
                        count += 1
                    
                except Exception as e:
                    continue
            
            # 统计摘要
            summary = {
                "total_count": count,
                "by_type": {}
            }
            for elem_type, elem_list in elements.items():
                if elem_list:
                    summary["by_type"][elem_type] = len(elem_list)
            
            return {
                "layer_colors": layer_colors,
                "elements": elements,
                "summary": summary
            }
            
        finally:
            if selection_set:
                try:
                    selection_set.Delete()
                except:
                    pass
    
    def _take_screenshot_sync(self, acad) -> Optional[str]:
        """截取 AutoCAD 窗口截图"""
        try:
            import win32gui
            import ctypes
            from ctypes import wintypes
            from PIL import ImageGrab
            import io
            
            # 查找 AutoCAD 窗口
            hwnd = None
            
            def find_autocad_window(hwnd_candidate, _):
                nonlocal hwnd
                try:
                    title = win32gui.GetWindowText(hwnd_candidate)
                    if "AutoCAD" in title and win32gui.IsWindowVisible(hwnd_candidate):
                        hwnd = hwnd_candidate
                        return False
                except Exception:
                    pass
                return True
            
            win32gui.EnumWindows(find_autocad_window, None)
            
            if not hwnd:
                try:
                    hwnd = int(acad.HWND)
                except Exception:
                    pass
            
            if not hwnd:
                logger.warning("[AutoCADController] Could not find AutoCAD window handle")
                return None
            
            # 将窗口置于前台
            try:
                win32gui.SetForegroundWindow(hwnd)
                import time
                time.sleep(0.3)
            except Exception:
                pass
            
            # 获取窗口区域（不含阴影）
            try:
                rect = wintypes.RECT()
                DWMWA_EXTENDED_FRAME_BOUNDS = 9
                ctypes.windll.dwmapi.DwmGetWindowAttribute(
                    hwnd,
                    DWMWA_EXTENDED_FRAME_BOUNDS,
                    ctypes.byref(rect),
                    ctypes.sizeof(rect)
                )
                left, top, right, bottom = rect.left, rect.top, rect.right, rect.bottom
            except Exception:
                left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            
            # 截图
            img = ImageGrab.grab(bbox=(left, top, right, bottom))
            
            # 压缩
            img = self._compress_image(img)
            
            # 转 base64
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=85)
            base64_str = base64.b64encode(buffer.getvalue()).decode('utf-8')
            
            logger.info(f"[AutoCADController] Screenshot captured: {right-left}x{bottom-top}")
            return base64_str
            
        except Exception as e:
            logger.warning(f"[AutoCADController] Screenshot failed: {e}", exc_info=True)
            return None
    
    def _compress_image(self, img, max_size: int = 1400):
        """压缩图片"""
        width, height = img.size
        max_dim = max(width, height)
        
        if max_dim > max_size:
            scale = max_size / max_dim
            new_width = int(width * scale)
            new_height = int(height * scale)
            img = img.resize((new_width, new_height), resample=3)  # LANCZOS
        
        return img
    
    def _execute_action_sync(
        self,
        action: str,
        data: Dict[str, Any],
        code: str,
        timeout: int
    ) -> Dict[str, Any]:
        """同步执行操作"""
        import pythoncom
        
        pythoncom.CoInitialize()
        try:
            acad, doc = self._get_acad_with_doc()
            model_space = doc.ModelSpace
            
            # 记录操作前的实体数量
            entities_before = model_space.Count
            
            result = {
                "success": False,
                "output": "",
                "error": None,
                "entities_created": 0,
                "entities_modified": 0,
                "entities_deleted": 0
            }
            
            if action == "draw_from_json":
                result = self._execute_draw_from_json(acad, doc, data)
            
            elif action == "execute_python_com":
                result = self._execute_python_com(acad, doc, code, timeout)
            
            else:
                result["error"] = f"Unknown action: {action}"
            
            # 计算实体变化
            entities_after = model_space.Count
            if result["success"]:
                result["entities_created"] = max(0, entities_after - entities_before)
            
            return result
            
        except Exception as e:
            logger.error(f"[AutoCADController] Action execution error: {e}", exc_info=True)
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "entities_created": 0,
                "entities_modified": 0,
                "entities_deleted": 0
            }
        finally:
            pythoncom.CoUninitialize()
    
    def _execute_draw_from_json(
        self,
        acad,
        doc,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行 draw_from_json"""
        from .actions.json_drawer import JsonDrawer
        import time
        
        try:
            drawer = JsonDrawer(acad, doc)
            result = drawer.draw(data)
            
            total_drawn = result.get('total_drawn', 0)
            if total_drawn > 0:
                try:
                    doc.Regen(1)  # acRegenAll = 1
                    acad.ZoomExtents()
                    time.sleep(0.5)
                except Exception as e:
                    logger.warning(f"[AutoCADController] ZoomExtents after draw failed: {e}")
            
            return {
                "success": True,
                "output": f"Drew {total_drawn} entities",
                "error": None,
                "entities_created": total_drawn,
                "entities_modified": 0,
                "entities_deleted": 0
            }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "entities_created": 0,
                "entities_modified": 0,
                "entities_deleted": 0
            }
    
    def _execute_python_com(
        self,
        acad,
        doc,
        code: str,
        timeout: int
    ) -> Dict[str, Any]:
        """执行 Python COM 代码"""
        from .actions.python_executor import PythonComExecutor
        
        try:
            executor = PythonComExecutor(acad, doc)
            result = executor.execute(code, timeout)
            return result
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "entities_created": 0,
                "entities_modified": 0,
                "entities_deleted": 0
            }
    
    
    def _draw_standard_part_sync(
        self,
        part_type: str,
        parameters: Dict[str, Any],
        preset: str,
        position: Tuple[float, float]
    ) -> Dict[str, Any]:
        """同步绘制标准件"""
        import pythoncom
        
        pythoncom.CoInitialize()
        try:
            acad, doc = self._get_acad_with_doc()
            
            # 获取模板
            from .templates.registry import TemplateRegistry
            template_class = TemplateRegistry.get(part_type)
            
            if not template_class:
                raise ValueError(f"Unknown part type: {part_type}")
            
            # 创建模板实例
            if preset:
                template = template_class.from_preset(preset)
            elif parameters:
                template = template_class(**parameters)
            else:
                template = template_class()
            
            # 验证参数
            errors = template.validate()
            if errors:
                raise ValueError(f"Invalid parameters: {', '.join(errors)}")
            
            # 生成 JSON 数据
            json_data = template.generate()
            
            # 应用位置偏移
            if position != (0, 0):
                json_data = self._offset_json_data(json_data, position)
            
            # 绘制
            from .actions.json_drawer import JsonDrawer
            drawer = JsonDrawer(acad, doc)
            result = drawer.draw(json_data)
            
            return {
                "success": True,
                "part_type": part_type,
                "parameters_used": template.get_parameters(),
                "entities_created": result.get('total_drawn', 0),
                "handles": result.get('handles', [])
            }
            
        except Exception as e:
            logger.error(f"[AutoCADController] Failed to draw standard part: {e}", exc_info=True)
            return {
                "success": False,
                "part_type": part_type,
                "parameters_used": {},
                "entities_created": 0,
                "handles": [],
                "error": str(e)
            }
        finally:
            pythoncom.CoUninitialize()
    
    def _offset_json_data(
        self,
        data: Dict[str, Any],
        offset: Tuple[float, float]
    ) -> Dict[str, Any]:
        """偏移 JSON 数据中的所有坐标"""
        dx, dy = offset
        
        elements = data.get("elements", {})
        
        # 偏移直线
        for line in elements.get("lines", []):
            line["start"][0] += dx
            line["start"][1] += dy
            line["end"][0] += dx
            line["end"][1] += dy
        
        # 偏移圆
        for circle in elements.get("circles", []):
            circle["center"][0] += dx
            circle["center"][1] += dy
        
        # 偏移圆弧
        for arc in elements.get("arcs", []):
            arc["center"][0] += dx
            arc["center"][1] += dy
        
        # 偏移多段线
        for polyline in elements.get("polylines", []):
            for vertex in polyline.get("vertices", []):
                vertex[0] += dx
                vertex[1] += dy
        
        # 偏移文字
        for text in elements.get("texts", []):
            text["position"][0] += dx
            text["position"][1] += dy
        
        # 偏移标注
        for dim in elements.get("dimensions", []):
            if "ext_line1_point" in dim:
                dim["ext_line1_point"][0] += dx
                dim["ext_line1_point"][1] += dy
            if "ext_line2_point" in dim:
                dim["ext_line2_point"][0] += dx
                dim["ext_line2_point"][1] += dy
            if "text_position" in dim:
                dim["text_position"][0] += dx
                dim["text_position"][1] += dy
        
        return data
    
    # ==================== 窗口管理 ====================
    
    def _find_autocad_hwnd(self, acad=None) -> Optional[int]:
        """查找 AutoCAD 主窗口句柄"""
        import win32gui
        
        hwnd = None
        
        def enum_callback(hwnd_candidate, _):
            nonlocal hwnd
            try:
                title = win32gui.GetWindowText(hwnd_candidate)
                if "AutoCAD" in title and win32gui.IsWindowVisible(hwnd_candidate):
                    hwnd = hwnd_candidate
                    return False
            except Exception:
                pass
            return True
        
        win32gui.EnumWindows(enum_callback, None)
        
        # fallback: 通过 COM 对象获取
        if not hwnd and acad:
            try:
                candidate = int(acad.HWND)
                if win32gui.IsWindow(candidate):
                    hwnd = candidate
            except Exception:
                pass
        
        return hwnd
    
    def _force_foreground_window(self, hwnd: int) -> bool:
        """
        强制将窗口置于前台。
        绕过 Windows 的 SetForegroundWindow 限制：
        后台进程需要通过 AttachThreadInput 临时关联到前台线程。
        """
        import win32gui
        import win32con
        import win32process
        import ctypes
        
        try:
            # 方法1: 先尝试直接 SetForegroundWindow
            win32gui.SetForegroundWindow(hwnd)
            return True
        except Exception:
            pass
        
        try:
            # 方法2: AttachThreadInput 绕过限制
            foreground_hwnd = win32gui.GetForegroundWindow()
            foreground_thread_id = win32process.GetWindowThreadProcessId(foreground_hwnd)[0]
            target_thread_id = win32process.GetWindowThreadProcessId(hwnd)[0]
            current_thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
            
            # 关联当前线程到前台线程
            if foreground_thread_id != current_thread_id:
                ctypes.windll.user32.AttachThreadInput(current_thread_id, foreground_thread_id, True)
            if target_thread_id != current_thread_id:
                ctypes.windll.user32.AttachThreadInput(current_thread_id, target_thread_id, True)
            
            try:
                win32gui.BringWindowToTop(hwnd)
                win32gui.SetForegroundWindow(hwnd)
                return True
            finally:
                # 解除关联
                if foreground_thread_id != current_thread_id:
                    ctypes.windll.user32.AttachThreadInput(current_thread_id, foreground_thread_id, False)
                if target_thread_id != current_thread_id:
                    ctypes.windll.user32.AttachThreadInput(current_thread_id, target_thread_id, False)
        except Exception:
            pass
        
        try:
            # 方法3: 模拟 ALT 键按下（使当前进程有权调用 SetForegroundWindow）
            ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)  # ALT down
            ctypes.windll.user32.keybd_event(0x12, 0, 2, 0)  # ALT up
            win32gui.SetForegroundWindow(hwnd)
            return True
        except Exception as e:
            logger.warning(f"[AutoCADController] All foreground methods failed: {e}")
            return False
    
    def _wait_and_focus_autocad(self, acad, is_new_instance: bool = False):
        """
        等待 AutoCAD 窗口完全就绪，然后最大化并置于前台。
        
        新启动的实例需要等待更久（窗口从无到有）。
        已有实例只需确认窗口存在。
        """
        import win32gui
        import win32con
        import time
        
        MAX_WAIT = 60 if is_new_instance else 10
        POLL_INTERVAL = 1
        waited = 0
        hwnd = None
        
        # 阶段1: 等待窗口出现
        while waited < MAX_WAIT:
            hwnd = self._find_autocad_hwnd(acad)
            if hwnd:
                break
            time.sleep(POLL_INTERVAL)
            waited += POLL_INTERVAL
            logger.info("[AutoCADController] Waiting for AutoCAD window... (%ds/%ds)", waited, MAX_WAIT)
        
        if not hwnd:
            logger.warning("[AutoCADController] AutoCAD window not found after %ds", MAX_WAIT)
            return
        
        logger.info("[AutoCADController] AutoCAD window found after %ds (hwnd=%s)", waited, hwnd)
        
        # 阶段2: 新实例需要额外等待窗口完全初始化（标题栏可能还在变化）
        if is_new_instance:
            time.sleep(3)
        
        # 阶段3: 最大化 + 前台聚焦
        try:
            # 如果窗口最小化，先还原
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                time.sleep(0.5)
            
            # 最大化窗口
            win32gui.ShowWindow(hwnd, win32con.SW_SHOWMAXIMIZED)
            time.sleep(0.3)
            
            # 置于前台
            success = self._force_foreground_window(hwnd)
            if success:
                logger.info("[AutoCADController] AutoCAD window maximized and brought to foreground")
            else:
                logger.warning("[AutoCADController] AutoCAD window maximized but foreground failed")
        except Exception as e:
            logger.warning(f"[AutoCADController] Window focus failed: {e}")
    
    # ==================== 辅助方法 ====================
    
    def _get_acad_connection(self):
        """
        获取已运行的 AutoCAD COM 对象。
        如果 AutoCAD 未运行，抛出 AutoCADNotRunningError（友好提示）。
        调用前必须已 CoInitialize。
        """
        import win32com.client
        try:
            return win32com.client.GetActiveObject("AutoCAD.Application")
        except Exception:
            raise AutoCADNotRunningError()
    
    def _get_acad_with_doc(self):
        """
        获取已运行的 AutoCAD COM 对象及活动文档。
        如果 AutoCAD 未运行，抛出 AutoCADNotRunningError。
        如果没有打开的文档，抛出 AutoCADNoDocumentError。
        调用前必须已 CoInitialize。
        """
        acad = self._get_acad_connection()
        if acad.Documents.Count == 0:
            raise AutoCADNoDocumentError()
        return acad, acad.ActiveDocument
    
    def _vt_point(self, x, y, z=0):
        """创建 COM 点坐标"""
        import win32com.client
        import pythoncom
        return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, (x, y, z))
    
    def _vt_float(self, data):
        """创建 COM 浮点数组"""
        import win32com.client
        import pythoncom
        return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, data)
