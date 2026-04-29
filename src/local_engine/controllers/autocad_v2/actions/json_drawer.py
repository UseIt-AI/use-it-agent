"""
JSON Drawer - 从 JSON 数据绘制图纸

Action: draw_from_json
"""

from typing import Dict, Any, List
import math
import logging
import time

logger = logging.getLogger(__name__)


class JsonDrawer:
    """
    从 JSON 数据绘制图纸
    
    JSON 格式:
    {
        "layer_colors": {"图层名": 颜色值, ...},
        "elements": {
            "lines": [...],
            "circles": [...],
            "arcs": [...],
            "polylines": [...],
            "texts": [...],
            "dimensions": [...]
        }
    }
    """
    
    def __init__(self, acad, doc, draw_delay: float = 0.0):
        """
        初始化
        
        Args:
            acad: AutoCAD Application 对象
            doc: AutoCAD Document 对象
            draw_delay: 每个元素绘制后的延迟（秒）
        """
        self.acad = acad
        self.doc = doc
        self.model_space = doc.ModelSpace
        self.draw_delay = draw_delay
        self.handles = []  # 记录创建的实体句柄
        self._chinese_style_name = None  # 中文文字样式名
        self._arc_centers = []  # 记录已绘制的圆弧/圆的圆心信息 [(center, radius), ...]
        self._ensure_chinese_text_style()
    
    def draw(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        绘制 JSON 数据
        
        Args:
            data: JSON 图纸数据
        
        Returns:
            {
                "total_drawn": int,
                "by_type": {...},
                "handles": [...]
            }
        """
        self.handles = []
        self._arc_centers = []  # 清空已记录的圆心信息
        
        # 创建图层
        layer_colors = data.get("layer_colors", {})
        self._create_layers(layer_colors)
        
        # 获取元素
        elements = data.get("elements", {})
        
        # 绘制统计
        stats = {
            "lines": 0,
            "circles": 0,
            "arcs": 0,
            "polylines": 0,
            "texts": 0,
            "dimensions": 0
        }
        
        # 绘制直线
        for line in elements.get("lines", []):
            if self._draw_line(line):
                stats["lines"] += 1
        
        # 绘制圆
        for circle in elements.get("circles", []):
            if self._draw_circle(circle):
                stats["circles"] += 1
        
        # 绘制圆弧
        for arc in elements.get("arcs", []):
            if self._draw_arc(arc):
                stats["arcs"] += 1
        
        # 绘制多段线
        for polyline in elements.get("polylines", []):
            if self._draw_polyline(polyline):
                stats["polylines"] += 1
        
        # 绘制文字
        for text in elements.get("texts", []):
            if self._draw_text(text):
                stats["texts"] += 1
        
        # 绘制标注
        for dim in elements.get("dimensions", []):
            if self._draw_dimension(dim):
                stats["dimensions"] += 1
        
        total = sum(stats.values())
        
        logger.info(f"[JsonDrawer] Drew {total} entities: {stats}")
        
        return {
            "total_drawn": total,
            "by_type": stats,
            "handles": self.handles
        }
    
    def _ensure_chinese_text_style(self):
        """确保存在支持中文的文字样式"""
        style_name = "Chinese_Style"
        
        try:
            # 检查是否已存在
            try:
                style = self.doc.TextStyles.Item(style_name)
                self._chinese_style_name = style_name
                logger.info(f"[JsonDrawer] Using existing text style: {style_name}")
                return
            except:
                pass
            
            # 创建新样式
            style = self.doc.TextStyles.Add(style_name)
            
            # 尝试设置支持中文的字体
            # 优先级: 1. TrueType字体(最可靠) 2. SHX字体
            chinese_fonts = [
                # TrueType 字体 (Windows 自带)
                ("SimSun", True),      # 宋体
                ("SimHei", True),      # 黑体
                ("Microsoft YaHei", True),  # 微软雅黑
                ("Arial Unicode MS", True),
                # SHX 字体 (AutoCAD 工程字体)
                ("hztxt.shx", False),
                ("gbcbig.shx", False),
            ]
            
            font_set = False
            for font_name, is_ttf in chinese_fonts:
                try:
                    if is_ttf:
                        # TrueType 字体
                        style.fontFile = font_name
                    else:
                        # SHX 字体
                        style.fontFile = font_name
                        # 对于 SHX，可能需要设置大字体
                        try:
                            style.BigFontFile = "gbcbig.shx"
                        except:
                            pass
                    font_set = True
                    logger.info(f"[JsonDrawer] Created text style '{style_name}' with font '{font_name}'")
                    break
                except Exception as e:
                    logger.debug(f"[JsonDrawer] Font '{font_name}' not available: {e}")
                    continue
            
            if font_set:
                self._chinese_style_name = style_name
            else:
                logger.warning("[JsonDrawer] No Chinese font available, text may show as '???'")
                self._chinese_style_name = None
                
        except Exception as e:
            logger.warning(f"[JsonDrawer] Failed to create Chinese text style: {e}")
            self._chinese_style_name = None
    
    def _has_chinese(self, text: str) -> bool:
        """检查文字是否包含中文字符"""
        for char in text:
            if '\u4e00' <= char <= '\u9fff':
                return True
        return False
    
    def _find_arc_center_for_radial_dim(self, text_pos: List[float], actual_radius: float, measurement: float):
        """
        从已绘制的圆弧/圆中查找匹配的圆心
        
        Args:
            text_pos: 标注文字位置
            actual_radius: 实际半径值
            measurement: 标注测量值（可能包含比例因子）
        
        Returns:
            圆心坐标 [x, y, z] 或 None
        """
        if not self._arc_centers:
            return None
        
        # 查找最匹配的圆弧/圆
        # 匹配条件：1) 圆心到 text_pos 的距离接近半径 2) 半径值接近
        best_match = None
        best_score = float('inf')
        
        for center, radius in self._arc_centers:
            # 计算圆心到 text_pos 的距离
            dx = text_pos[0] - center[0]
            dy = text_pos[1] - center[1]
            dist_to_center = math.sqrt(dx*dx + dy*dy)
            
            # 计算匹配分数：距离差异 + 半径差异
            radius_diff = abs(radius - actual_radius)
            # 如果 text_pos 在圆弧附近（距离圆心约等于半径），则匹配
            dist_diff = abs(dist_to_center - radius)
            
            # 综合评分（越小越好）
            score = radius_diff + dist_diff * 0.1
            
            # 如果半径很接近，且 text_pos 在圆弧附近，认为是匹配的
            if radius_diff < max(actual_radius * 0.1, 1.0) and dist_diff < max(radius * 0.2, 2.0):
                if score < best_score:
                    best_score = score
                    best_match = center
        
        if best_match:
            logger.debug(f"[JsonDrawer] Found matching arc center {best_match} for radial dimension")
            return best_match
        
        return None
    
    def _create_layers(self, layer_colors: Dict[str, int]):
        """创建图层"""
        for layer_name, color in layer_colors.items():
            try:
                try:
                    layer = self.doc.Layers.Item(layer_name)
                    layer.Color = color
                except:
                    layer = self.doc.Layers.Add(layer_name)
                    layer.Color = color
            except Exception as e:
                logger.warning(f"[JsonDrawer] Failed to create layer {layer_name}: {e}")
    
    def _draw_line(self, line: Dict) -> bool:
        """绘制直线"""
        try:
            start = line["start"]
            end = line["end"]
            
            obj = self.model_space.AddLine(
                self._vt_point(start[0], start[1], start[2] if len(start) > 2 else 0),
                self._vt_point(end[0], end[1], end[2] if len(end) > 2 else 0)
            )
            
            self._apply_properties(obj, line)
            self.handles.append(obj.Handle)
            
            if self.draw_delay > 0:
                time.sleep(self.draw_delay)
            
            return True
        except Exception as e:
            logger.warning(f"[JsonDrawer] Failed to draw line: {e}")
            return False
    
    def _draw_circle(self, circle: Dict) -> bool:
        """绘制圆"""
        try:
            center = circle["center"]
            radius = circle["radius"]
            
            obj = self.model_space.AddCircle(
                self._vt_point(center[0], center[1], center[2] if len(center) > 2 else 0),
                radius
            )
            
            # 记录圆心信息（用于半径标注查找）
            self._arc_centers.append((center, radius))
            
            self._apply_properties(obj, circle)
            self.handles.append(obj.Handle)
            
            if self.draw_delay > 0:
                time.sleep(self.draw_delay)
            
            return True
        except Exception as e:
            logger.warning(f"[JsonDrawer] Failed to draw circle: {e}")
            return False
    
    def _draw_arc(self, arc: Dict) -> bool:
        """绘制圆弧"""
        try:
            center = arc["center"]
            radius = arc["radius"]
            start_angle = math.radians(arc["start_angle"])
            end_angle = math.radians(arc["end_angle"])
            
            obj = self.model_space.AddArc(
                self._vt_point(center[0], center[1], center[2] if len(center) > 2 else 0),
                radius,
                start_angle,
                end_angle
            )
            
            # 记录圆心信息（用于半径标注查找）
            self._arc_centers.append((center, radius))
            
            self._apply_properties(obj, arc)
            self.handles.append(obj.Handle)
            
            if self.draw_delay > 0:
                time.sleep(self.draw_delay)
            
            return True
        except Exception as e:
            logger.warning(f"[JsonDrawer] Failed to draw arc: {e}")
            return False
    
    def _draw_polyline(self, polyline: Dict) -> bool:
        """绘制多段线（用直线模拟）"""
        try:
            vertices = polyline["vertices"]
            layer = polyline.get("layer", "0")
            color = polyline.get("color", 256)
            closed = polyline.get("closed", False)
            
            drawn = 0
            
            # 绘制各段
            for i in range(len(vertices) - 1):
                start = vertices[i] + [0.0] if len(vertices[i]) == 2 else vertices[i]
                end = vertices[i + 1] + [0.0] if len(vertices[i + 1]) == 2 else vertices[i + 1]
                
                obj = self.model_space.AddLine(
                    self._vt_point(start[0], start[1], start[2] if len(start) > 2 else 0),
                    self._vt_point(end[0], end[1], end[2] if len(end) > 2 else 0)
                )
                obj.Layer = layer
                if color != 256:
                    obj.Color = color
                self.handles.append(obj.Handle)
                drawn += 1
                
                if self.draw_delay > 0:
                    time.sleep(self.draw_delay)
            
            # 闭合
            if closed and len(vertices) > 2:
                start = vertices[-1] + [0.0] if len(vertices[-1]) == 2 else vertices[-1]
                end = vertices[0] + [0.0] if len(vertices[0]) == 2 else vertices[0]
                
                obj = self.model_space.AddLine(
                    self._vt_point(start[0], start[1], start[2] if len(start) > 2 else 0),
                    self._vt_point(end[0], end[1], end[2] if len(end) > 2 else 0)
                )
                obj.Layer = layer
                if color != 256:
                    obj.Color = color
                self.handles.append(obj.Handle)
                drawn += 1
            
            return drawn > 0
        except Exception as e:
            logger.warning(f"[JsonDrawer] Failed to draw polyline: {e}")
            return False
    
    def _draw_text(self, text: Dict) -> bool:
        """绘制文字"""
        try:
            content = text["text"]
            position = text["position"]
            height = text.get("height", 2.5)
            
            obj = self.model_space.AddText(
                content,
                self._vt_point(position[0], position[1], position[2] if len(position) > 2 else 0),
                height
            )
            
            # 如果包含中文且有中文样式，应用中文样式
            if self._has_chinese(content) and self._chinese_style_name:
                try:
                    obj.StyleName = self._chinese_style_name
                except Exception as e:
                    logger.debug(f"[JsonDrawer] Failed to set Chinese style: {e}")
            
            self._apply_properties(obj, text)
            self.handles.append(obj.Handle)
            
            if self.draw_delay > 0:
                time.sleep(self.draw_delay)
            
            return True
        except Exception as e:
            logger.warning(f"[JsonDrawer] Failed to draw text: {e}")
            return False
    
    def _draw_dimension(self, dim: Dict) -> bool:
        """绘制标注"""
        try:
            dim_type = dim.get("type", "")
            
            # 对齐标注
            if dim_type == "AcDbAlignedDimension":
                return self._draw_aligned_dimension(dim)
            
            # 旋转标注
            elif dim_type == "AcDbRotatedDimension":
                return self._draw_rotated_dimension(dim)
            
            # 半径标注
            elif dim_type == "AcDbRadialDimension" or "Radial" in dim_type:
                return self._draw_radial_dimension(dim)
            
            # 直径标注
            elif dim_type == "AcDbDiametricDimension" or "Diameter" in dim_type:
                return self._draw_diametric_dimension(dim)
            
            # 三点角度标注
            elif dim_type == "AcDb3PointAngularDimension":
                return self._draw_3point_angular_dimension(dim)
            
            # 两线角度标注
            elif dim_type == "AcDb2LineAngularDimension":
                return self._draw_2line_angular_dimension(dim)
            
            # 其他角度标注（fallback 到文字）
            elif "Angular" in dim_type:
                return self._draw_angular_text(dim)
            
            else:
                logger.warning(f"[JsonDrawer] Unknown dimension type: {dim_type}")
                return False
                
        except Exception as e:
            logger.warning(f"[JsonDrawer] Failed to draw dimension: {e}")
            return False
    
    def _draw_aligned_dimension(self, dim: Dict) -> bool:
        """绘制对齐标注"""
        if "ext_line1_point" not in dim or "ext_line2_point" not in dim:
            return False
        
        pt1 = dim["ext_line1_point"]
        pt2 = dim["ext_line2_point"]
        
        if "text_position" in dim:
            dim_pt = dim["text_position"]
        else:
            mid_x = (pt1[0] + pt2[0]) / 2
            mid_y = (pt1[1] + pt2[1]) / 2
            dim_pt = [mid_x, mid_y + 10, 0.0]
        
        obj = self.model_space.AddDimAligned(
            self._vt_point(pt1[0], pt1[1], pt1[2] if len(pt1) > 2 else 0),
            self._vt_point(pt2[0], pt2[1], pt2[2] if len(pt2) > 2 else 0),
            self._vt_point(dim_pt[0], dim_pt[1], dim_pt[2] if len(dim_pt) > 2 else 0)
        )
        
        # 设置文字覆盖
        measurement = dim.get("measurement", 0)
        text_override = dim.get("text_override", "")
        if text_override:
            obj.TextOverride = text_override
        elif measurement:
            if measurement >= 1:
                obj.TextOverride = str(int(round(measurement)))
            else:
                obj.TextOverride = f"{measurement:.2f}"
        
        self._apply_properties(obj, dim)
        self.handles.append(obj.Handle)
        
        if self.draw_delay > 0:
            time.sleep(self.draw_delay)
        
        return True
    
    def _draw_rotated_dimension(self, dim: Dict) -> bool:
        """绘制旋转标注"""
        if "ext_line1_point" not in dim or "ext_line2_point" not in dim:
            return False
        
        pt1 = dim["ext_line1_point"]
        pt2 = dim["ext_line2_point"]
        
        if "text_position" in dim:
            dim_pt = dim["text_position"]
        else:
            mid_x = (pt1[0] + pt2[0]) / 2
            mid_y = (pt1[1] + pt2[1]) / 2
            dim_pt = [mid_x, mid_y + 10, 0.0]
        
        # 确定旋转角度
        if "is_horizontal" in dim:
            rotation_rad = 0 if dim["is_horizontal"] else math.pi / 2
        else:
            rotation = dim.get("dim_rotation", 0)
            rotation_rad = math.radians(rotation)
        
        obj = self.model_space.AddDimRotated(
            self._vt_point(pt1[0], pt1[1], pt1[2] if len(pt1) > 2 else 0),
            self._vt_point(pt2[0], pt2[1], pt2[2] if len(pt2) > 2 else 0),
            self._vt_point(dim_pt[0], dim_pt[1], dim_pt[2] if len(dim_pt) > 2 else 0),
            rotation_rad
        )
        
        # 设置文字覆盖
        measurement = dim.get("measurement", 0)
        text_override = dim.get("text_override", "")
        if text_override:
            obj.TextOverride = text_override
        elif measurement:
            if measurement >= 1:
                obj.TextOverride = str(int(round(measurement)))
            else:
                obj.TextOverride = f"{measurement:.2f}"
        
        self._apply_properties(obj, dim)
        self.handles.append(obj.Handle)
        
        if self.draw_delay > 0:
            time.sleep(self.draw_delay)
        
        return True
    
    def _draw_radial_dimension(self, dim: Dict) -> bool:
        """绘制半径标注（真正的标注对象）"""
        try:
            # 需要找到圆弧的圆心和标注点
            # 从 text_position 和 measurement 推算
            text_pos = dim.get("text_position")
            if not text_pos:
                return self._draw_radial_text_fallback(dim)
            
            measurement = dim.get("measurement", 0)
            scale_factor = dim.get("linear_scale_factor", 1.0)
            
            # 实际半径 = measurement / scale_factor
            actual_radius = measurement / scale_factor if scale_factor else measurement
            
            # 尝试从关联的圆弧获取圆心
            center = dim.get("center")
            if not center:
                # 没有圆心信息，尝试从已绘制的圆弧/圆中查找
                center = self._find_arc_center_for_radial_dim(text_pos, actual_radius, measurement)
                if not center:
                    # 仍然找不到，fallback 到文字
                    logger.debug(f"[JsonDrawer] No center found for radial dimension, fallback to text")
                    return self._draw_radial_text_fallback(dim)
            
            # 计算圆弧上的点（从圆心到 text_position 方向）
            dx = text_pos[0] - center[0]
            dy = text_pos[1] - center[1]
            dist = math.sqrt(dx*dx + dy*dy)
            if dist < 1e-6:
                return self._draw_radial_text_fallback(dim)
            
            # 圆弧上的点
            chord_pt = [
                center[0] + dx / dist * actual_radius,
                center[1] + dy / dist * actual_radius,
                0.0
            ]
            
            obj = self.model_space.AddDimRadial(
                self._vt_point(center[0], center[1], center[2] if len(center) > 2 else 0),
                self._vt_point(chord_pt[0], chord_pt[1], chord_pt[2] if len(chord_pt) > 2 else 0),
                actual_radius
            )
            
            # 设置文字覆盖
            text_override = dim.get("text_override", "")
            if text_override:
                obj.TextOverride = text_override
            elif measurement and scale_factor != 1.0:
                # 如果有比例因子，显示换算后的值
                obj.TextOverride = f"R{int(round(measurement))}" if measurement >= 1 else f"R{measurement:.2f}"
            
            self._apply_properties(obj, dim)
            self.handles.append(obj.Handle)
            return True
            
        except Exception as e:
            logger.warning(f"[JsonDrawer] Radial dimension failed, fallback to text: {e}")
            return self._draw_radial_text_fallback(dim)
    
    def _draw_radial_text_fallback(self, dim: Dict) -> bool:
        """绘制半径标注（文字 fallback）"""
        if "text_position" not in dim:
            return False
        
        measurement = dim.get("measurement", 0)
        text_override = dim.get("text_override", "")
        
        if text_override:
            text = text_override
        else:
            if measurement >= 1:
                text = f"R{int(round(measurement))}"
            else:
                text = f"R{measurement:.2f}"
        
        text_pos = dim["text_position"]
        height = dim.get("text_height", 2.5)
        
        obj = self.model_space.AddText(
            text,
            self._vt_point(text_pos[0], text_pos[1], text_pos[2] if len(text_pos) > 2 else 0),
            height
        )
        
        self._apply_properties(obj, dim)
        self.handles.append(obj.Handle)
        return True
    
    def _draw_diametric_dimension(self, dim: Dict) -> bool:
        """绘制直径标注（真正的标注对象）"""
        try:
            # 需要圆弧上的两个对称点
            center = dim.get("center")
            text_pos = dim.get("text_position")
            measurement = dim.get("measurement", 0)
            scale_factor = dim.get("linear_scale_factor", 1.0)
            
            if not center or not text_pos:
                return self._draw_diameter_text_fallback(dim)
            
            actual_diameter = measurement / scale_factor if scale_factor else measurement
            actual_radius = actual_diameter / 2
            
            # 计算直径两端点
            dx = text_pos[0] - center[0]
            dy = text_pos[1] - center[1]
            dist = math.sqrt(dx*dx + dy*dy)
            if dist < 1e-6:
                return self._draw_diameter_text_fallback(dim)
            
            # 归一化方向
            nx, ny = dx / dist, dy / dist
            
            chord_pt1 = [center[0] + nx * actual_radius, center[1] + ny * actual_radius, 0.0]
            chord_pt2 = [center[0] - nx * actual_radius, center[1] - ny * actual_radius, 0.0]
            
            obj = self.model_space.AddDimDiametric(
                self._vt_point(chord_pt1[0], chord_pt1[1], 0),
                self._vt_point(chord_pt2[0], chord_pt2[1], 0),
                actual_radius  # leader length
            )
            
            text_override = dim.get("text_override", "")
            if text_override:
                obj.TextOverride = text_override
            elif measurement and scale_factor != 1.0:
                obj.TextOverride = f"Φ{int(round(measurement))}" if measurement >= 1 else f"Φ{measurement:.2f}"
            
            self._apply_properties(obj, dim)
            self.handles.append(obj.Handle)
            return True
            
        except Exception as e:
            logger.warning(f"[JsonDrawer] Diametric dimension failed, fallback to text: {e}")
            return self._draw_diameter_text_fallback(dim)
    
    def _draw_diameter_text_fallback(self, dim: Dict) -> bool:
        """绘制直径标注（文字 fallback）"""
        if "text_position" not in dim:
            return False
        
        measurement = dim.get("measurement", 0)
        text_override = dim.get("text_override", "")
        
        if text_override:
            text = text_override
        else:
            if measurement >= 1:
                text = f"Φ{int(round(measurement))}"
            else:
                text = f"Φ{measurement:.2f}"
        
        text_pos = dim["text_position"]
        height = dim.get("text_height", 2.5)
        
        obj = self.model_space.AddText(
            text,
            self._vt_point(text_pos[0], text_pos[1], text_pos[2] if len(text_pos) > 2 else 0),
            height
        )
        
        self._apply_properties(obj, dim)
        self.handles.append(obj.Handle)
        return True
    
    def _draw_3point_angular_dimension(self, dim: Dict) -> bool:
        """绘制三点角度标注（真正的标注对象）"""
        try:
            # 三点角度标注需要：顶点 + 两个端点
            vertex = dim.get("anglevertex")
            pt1 = dim.get("extline1endpoint")
            pt2 = dim.get("extline2endpoint")
            text_pos = dim.get("text_position")
            
            if not vertex or not pt1 or not pt2:
                return self._draw_angular_text(dim)
            
            obj = self.model_space.AddDim3PointAngular(
                self._vt_point(vertex[0], vertex[1], vertex[2] if len(vertex) > 2 else 0),
                self._vt_point(pt1[0], pt1[1], pt1[2] if len(pt1) > 2 else 0),
                self._vt_point(pt2[0], pt2[1], pt2[2] if len(pt2) > 2 else 0),
                self._vt_point(text_pos[0], text_pos[1], text_pos[2] if len(text_pos) > 2 else 0) if text_pos else self._vt_point(vertex[0], vertex[1] + 10, 0)
            )
            
            text_override = dim.get("text_override", "")
            if text_override:
                obj.TextOverride = text_override
            
            self._apply_properties(obj, dim)
            self.handles.append(obj.Handle)
            return True
            
        except Exception as e:
            logger.warning(f"[JsonDrawer] 3-point angular dimension failed, fallback to text: {e}")
            return self._draw_angular_text(dim)
    
    def _draw_2line_angular_dimension(self, dim: Dict) -> bool:
        """绘制两线角度标注（真正的标注对象）"""
        try:
            # 两线角度标注需要：两条线的端点
            line1_start = dim.get("extline1startpoint") or dim.get("ext_line1_point")
            line1_end = dim.get("extline1endpoint")
            line2_start = dim.get("extline2startpoint") or dim.get("ext_line2_point")
            line2_end = dim.get("extline2endpoint")
            text_pos = dim.get("text_position")
            
            if not all([line1_start, line1_end, line2_start, line2_end]):
                return self._draw_angular_text(dim)
            
            # AddDimAngular 需要：顶点、两条线上的点、标注弧位置
            # 计算两线交点作为顶点
            vertex = self._line_intersection(line1_start, line1_end, line2_start, line2_end)
            if not vertex:
                return self._draw_angular_text(dim)
            
            obj = self.model_space.AddDimAngular(
                self._vt_point(vertex[0], vertex[1], 0),
                self._vt_point(line1_end[0], line1_end[1], line1_end[2] if len(line1_end) > 2 else 0),
                self._vt_point(line2_end[0], line2_end[1], line2_end[2] if len(line2_end) > 2 else 0),
                self._vt_point(text_pos[0], text_pos[1], text_pos[2] if len(text_pos) > 2 else 0) if text_pos else self._vt_point(vertex[0], vertex[1] + 10, 0)
            )
            
            text_override = dim.get("text_override", "")
            if text_override:
                obj.TextOverride = text_override
            
            self._apply_properties(obj, dim)
            self.handles.append(obj.Handle)
            return True
            
        except Exception as e:
            logger.warning(f"[JsonDrawer] 2-line angular dimension failed, fallback to text: {e}")
            return self._draw_angular_text(dim)
    
    def _line_intersection(self, p1, p2, p3, p4):
        """计算两条线段的交点"""
        x1, y1 = p1[0], p1[1]
        x2, y2 = p2[0], p2[1]
        x3, y3 = p3[0], p3[1]
        x4, y4 = p4[0], p4[1]
        
        denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        if abs(denom) < 1e-10:
            return None  # 平行线
        
        t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
        
        x = x1 + t * (x2 - x1)
        y = y1 + t * (y2 - y1)
        
        return [x, y, 0.0]
    
    def _draw_angular_text(self, dim: Dict) -> bool:
        """绘制角度标注（用文字）"""
        if "text_position" not in dim:
            return False
        
        measurement = dim.get("measurement", 0)
        text_override = dim.get("text_override", "")
        
        if text_override:
            text = text_override
        else:
            angle_deg = math.degrees(measurement)
            angle_rounded = round(angle_deg, 1)
            if abs(angle_rounded - round(angle_rounded)) < 1e-6:
                text = f"{int(round(angle_rounded))}°"
            else:
                text = f"{angle_rounded:.1f}°"
        
        text_pos = dim["text_position"]
        height = dim.get("text_height", 2.5)
        
        obj = self.model_space.AddText(
            text,
            self._vt_point(text_pos[0], text_pos[1], text_pos[2] if len(text_pos) > 2 else 0),
            height
        )
        
        self._apply_properties(obj, dim)
        self.handles.append(obj.Handle)
        
        return True
    
    def _apply_properties(self, obj, data: Dict):
        """应用通用属性"""
        try:
            if "layer" in data:
                obj.Layer = data["layer"]
            if "color" in data and data["color"] != 256:
                obj.Color = data["color"]
        except Exception:
            pass
    
    def _vt_point(self, x, y, z=0):
        """创建 COM 点坐标"""
        import win32com.client
        import pythoncom
        return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, (x, y, z))
