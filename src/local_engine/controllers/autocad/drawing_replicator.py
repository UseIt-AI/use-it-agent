"""
图纸复刻器类
支持按图层、元素类型等灵活复刻图纸
"""

from .controller import AutoCADController
import json
import win32com.client
import pythoncom
import os
import time
from typing import List, Optional, Dict, Any


class DrawingReplicator:
    """图纸复刻器 - 灵活复刻图纸的各个部分"""
    
    def __init__(self, json_file: str = 'drawing_with_dimensions.json', data: Optional[Dict] = None, draw_delay: float = 0.0):
        """
        初始化复刻器
        
        Args:
            json_file: JSON 数据文件路径
            data: 直接传入的 JSON 数据字典 (优先级高于 json_file)
            draw_delay: 每个元素绘制后的延迟时间（秒），用于让用户看到绘制过程
        """
        self.json_file = json_file
        self.data = data
        self.cad = None
        self.layer_colors = {}
        self.elements = {}
        self.draw_delay = draw_delay  # 绘制延迟（秒）
        
        # 加载数据
        if self.data:
            self._parse_data()
        else:
            self._load_data()
    
    def _load_data(self):
        """加载 JSON 数据"""
        try:
            if not self.json_file:
                return
                
            with open(self.json_file, 'r', encoding='utf-8') as f:
                self.data = json.load(f)
            
            self._parse_data()
            print(f"✅ 已加载数据: {self.json_file}")
            
        except FileNotFoundError:
            print(f"❌ 找不到文件: {self.json_file}")
            raise
        except Exception as e:
            print(f"❌ 加载数据失败: {e}")
            raise

    def _parse_data(self):
        """解析数据到内部结构"""
        if not self.data:
            return
            
        self.layer_colors = self.data.get('layer_colors', {})
        self.elements = self.data.get('elements', {})
        
        # 只有在非批量静默模式下才打印详细信息（或者这里简单打印）
        # print(f"   图层: {len(self.layer_colors)} 个")
    
    def connect(self) -> bool:
        """连接到 AutoCAD"""
        self.cad = AutoCADController()
        if self.cad.connect():
            print("✅ 已连接到 AutoCAD")
            return True
        else:
            print("❌ 无法连接到 AutoCAD")
            return False
    
    def get_available_layers(self) -> List[str]:
        """获取所有可用的图层名称"""
        return list(self.layer_colors.keys())
    
    def find_layers_by_keyword(self, keyword: str, case_sensitive: bool = False) -> List[str]:
        """
        按关键词查找图层
        
        Args:
            keyword: 关键词
            case_sensitive: 是否区分大小写
            
        Returns:
            匹配的图层名称列表
        """
        all_layers = self.get_available_layers()
        
        if case_sensitive:
            return [layer for layer in all_layers if keyword in layer]
        else:
            keyword_lower = keyword.lower()
            return [layer for layer in all_layers if keyword_lower in layer.lower()]
    
    def find_layers_by_keywords(self, keywords: List[str], match_any: bool = True, case_sensitive: bool = False) -> List[str]:
        """
        按多个关键词查找图层
        
        Args:
            keywords: 关键词列表
            match_any: True=匹配任意关键词, False=必须匹配所有关键词
            case_sensitive: 是否区分大小写
            
        Returns:
            匹配的图层名称列表
        """
        all_layers = self.get_available_layers()
        matched = []
        
        for layer in all_layers:
            layer_check = layer if case_sensitive else layer.lower()
            keywords_check = keywords if case_sensitive else [k.lower() for k in keywords]
            
            if match_any:
                # 匹配任意一个关键词
                if any(kw in layer_check for kw in keywords_check):
                    matched.append(layer)
            else:
                # 必须匹配所有关键词
                if all(kw in layer_check for kw in keywords_check):
                    matched.append(layer)
        
        return matched
    
    def exclude_layers_by_keyword(self, keyword: str, case_sensitive: bool = False) -> List[str]:
        """
        获取不包含指定关键词的图层
        
        Args:
            keyword: 要排除的关键词
            case_sensitive: 是否区分大小写
            
        Returns:
            不包含关键词的图层列表
        """
        all_layers = self.get_available_layers()
        
        if case_sensitive:
            return [layer for layer in all_layers if keyword not in layer]
        else:
            keyword_lower = keyword.lower()
            return [layer for layer in all_layers if keyword_lower not in layer.lower()]
    
    def get_elements_by_layer(self, layer_name: str) -> Dict[str, List]:
        """
        获取指定图层的所有元素
        
        Args:
            layer_name: 图层名称
            
        Returns:
            包含各类元素的字典
        """
        result = {
            'lines': [],
            'circles': [],
            'arcs': [],
            'polylines': [],
            'texts': [],
            'dimensions': []
        }
        
        # 过滤各类元素
        for element_type in result.keys():
            elements = self.elements.get(element_type, [])
            result[element_type] = [
                elem for elem in elements 
                if elem.get('layer') == layer_name
            ]
        
        return result
    
    def get_elements_by_layers(self, layer_names: List[str]) -> Dict[str, List]:
        """
        获取多个图层的所有元素
        
        Args:
            layer_names: 图层名称列表
            
        Returns:
            包含各类元素的字典
        """
        result = {
            'lines': [],
            'circles': [],
            'arcs': [],
            'polylines': [],
            'texts': [],
            'dimensions': []
        }
        
        # 过滤各类元素
        for element_type in result.keys():
            elements = self.elements.get(element_type, [])
            result[element_type] = [
                elem for elem in elements 
                if elem.get('layer') in layer_names
            ]
        
        return result
    
    def replicate_all(self, setup_dimlfac: bool = True):
        """
        复刻所有元素
        
        Args:
            setup_dimlfac: 是否设置 DIMLFAC = 1.0
        """
        if not self.cad:
            print("❌ 请先调用 connect() 连接 AutoCAD")
            return
        
        print("\n" + "=" * 80)
        print("🎨 开始复刻所有元素")
        print("=" * 80)
        
        # 设置文字样式
        self._setup_drawing_styles()

        # 设置标注参数
        if setup_dimlfac:
            self._setup_dimension_settings()
        
        # 创建图层
        self._create_layers(self.layer_colors)
        
        # 绘制所有元素
        self._draw_elements(
            self.elements.get('lines', []),
            self.elements.get('circles', []),
            self.elements.get('arcs', []),
            self.elements.get('polylines', []),
            self.elements.get('texts', []),
            self.elements.get('dimensions', [])
        )
        
        # 缩放视图
        print("\n调整视图...")
        self.cad.zoom_extents()
        
        print("\n" + "=" * 80)
        print("✅ 复刻完成！")
        print("=" * 80)
    
    def replicate_layer(self, layer_name: str, setup_dimlfac: bool = True):
        """
        复刻指定图层
        
        Args:
            layer_name: 图层名称
            setup_dimlfac: 是否设置 DIMLFAC = 1.0
        """
        if not self.cad:
            print("❌ 请先调用 connect() 连接 AutoCAD")
            return
        
        print("\n" + "=" * 80)
        print(f"🎨 复刻图层: {layer_name}")
        print("=" * 80)
        
        # 设置文字样式
        self._setup_drawing_styles()
        
        # 设置标注参数
        if setup_dimlfac:
            self._setup_dimension_settings()
        
        # 创建该图层
        if layer_name in self.layer_colors:
            self._create_layers({layer_name: self.layer_colors[layer_name]})
        
        # 获取该图层的元素
        elements = self.get_elements_by_layer(layer_name)
        
        # 统计
        total = sum(len(v) for v in elements.values())
        print(f"\n图层 '{layer_name}' 包含 {total} 个元素:")
        for elem_type, elems in elements.items():
            if elems:
                print(f"  - {elem_type}: {len(elems)}")
        
        if total == 0:
            print(f"\n⚠️  图层 '{layer_name}' 没有元素")
            return
        
        # 绘制元素
        self._draw_elements(
            elements['lines'],
            elements['circles'],
            elements['arcs'],
            elements['polylines'],
            elements['texts'],
            elements['dimensions']
        )
        
        # 缩放视图
        print("\n调整视图...")
        self.cad.zoom_extents()
        
        print("\n" + "=" * 80)
        print(f"✅ 图层 '{layer_name}' 复刻完成！")
        print("=" * 80)
    
    def replicate_layers(self, layer_names: List[str], setup_dimlfac: bool = True):
        """
        复刻多个指定图层
        
        Args:
            layer_names: 图层名称列表
            setup_dimlfac: 是否设置 DIMLFAC = 1.0
        """
        if not self.cad:
            print("❌ 请先调用 connect() 连接 AutoCAD")
            return
        
        print("\n" + "=" * 80)
        print(f"🎨 复刻图层: {', '.join(layer_names)}")
        print("=" * 80)
        
        # 设置文字样式
        self._setup_drawing_styles()
        
        # 设置标注参数
        if setup_dimlfac:
            self._setup_dimension_settings()
        
        # 创建这些图层
        layers_to_create = {
            name: color 
            for name, color in self.layer_colors.items() 
            if name in layer_names
        }
        self._create_layers(layers_to_create)
        
        # 获取这些图层的元素
        elements = self.get_elements_by_layers(layer_names)
        
        # 统计
        total = sum(len(v) for v in elements.values())
        print(f"\n共 {total} 个元素:")
        for elem_type, elems in elements.items():
            if elems:
                print(f"  - {elem_type}: {len(elems)}")
        
        if total == 0:
            print(f"\n⚠️  这些图层没有元素")
            return
        
        # 绘制元素
        self._draw_elements(
            elements['lines'],
            elements['circles'],
            elements['arcs'],
            elements['polylines'],
            elements['texts'],
            elements['dimensions']
        )
        
        # 缩放视图
        print("\n调整视图...")
        self.cad.zoom_extents()
        
        print("\n" + "=" * 80)
        print(f"✅ {len(layer_names)} 个图层复刻完成！")
        print("=" * 80)
    
    def replicate_elements(self, 
                          lines: bool = True,
                          circles: bool = True,
                          arcs: bool = True,
                          polylines: bool = True,
                          texts: bool = True,
                          dimensions: bool = True,
                          layers: Optional[List[str]] = None,
                          setup_dimlfac: bool = True):
        """
        按元素类型复刻
        
        Args:
            lines: 是否复刻直线
            circles: 是否复刻圆
            arcs: 是否复刻圆弧
            polylines: 是否复刻多段线
            texts: 是否复刻文字
            dimensions: 是否复刻标注
            layers: 只复刻指定图层（None 表示所有图层）
            setup_dimlfac: 是否设置 DIMLFAC = 1.0
        """
        if not self.cad:
            print("❌ 请先调用 connect() 连接 AutoCAD")
            return
        
        print("\n" + "=" * 80)
        print("🎨 按类型复刻元素")
        print("=" * 80)
        
        # 设置文字样式
        self._setup_drawing_styles()
        
        # 设置标注参数
        if setup_dimlfac and dimensions:
            self._setup_dimension_settings()
        
        # 创建图层
        if layers:
            layers_to_create = {
                name: color 
                for name, color in self.layer_colors.items() 
                if name in layers
            }
            self._create_layers(layers_to_create)
        else:
            self._create_layers(self.layer_colors)
        
        # 过滤元素
        def filter_by_layer(elements_list):
            if layers is None:
                return elements_list
            return [e for e in elements_list if e.get('layer') in layers]
        
        lines_list = filter_by_layer(self.elements.get('lines', [])) if lines else []
        circles_list = filter_by_layer(self.elements.get('circles', [])) if circles else []
        arcs_list = filter_by_layer(self.elements.get('arcs', [])) if arcs else []
        polylines_list = filter_by_layer(self.elements.get('polylines', [])) if polylines else []
        texts_list = filter_by_layer(self.elements.get('texts', [])) if texts else []
        dimensions_list = filter_by_layer(self.elements.get('dimensions', [])) if dimensions else []
        
        # 统计
        print("\n将复刻:")
        if lines: print(f"  ✓ 直线: {len(lines_list)}")
        if circles: print(f"  ✓ 圆: {len(circles_list)}")
        if arcs: print(f"  ✓ 圆弧: {len(arcs_list)}")
        if polylines: print(f"  ✓ 多段线: {len(polylines_list)}")
        if texts: print(f"  ✓ 文字: {len(texts_list)}")
        if dimensions: print(f"  ✓ 标注: {len(dimensions_list)}")
        
        # 绘制元素
        self._draw_elements(
            lines_list,
            circles_list,
            arcs_list,
            polylines_list,
            texts_list,
            dimensions_list
        )
        
        # 缩放视图
        print("\n调整视图...")
        self.cad.zoom_extents()
        
        print("\n" + "=" * 80)
        print("✅ 元素复刻完成！")
        print("=" * 80)
    
    def _setup_dimension_settings(self):
        """设置 AutoCAD 标注参数"""
        print("\n" + "=" * 80)
        print("设置 AutoCAD 标注参数")
        print("=" * 80)
        try:
            self.cad.doc.SetVariable("DIMLFAC", 1.0)
            print("✅ 已设置 DIMLFAC = 1.0（不自动缩放）")
        except Exception as e:
            print(f"⚠️  无法设置标注参数: {e}")
    
    def _setup_drawing_styles(self, font="仿宋", size=2.0):
        """
        创建并应用专用的文字和标注样式。
        """
        print("\n" + "=" * 80)
        print(f"创建并设置专用样式 -> 字体: '{font}', 大小: {size}")
        print("=" * 80)

        # 存储尺寸供其他方法使用
        self.dim_size = size

        text_style_name = "AI_Replicator_Text"
        dim_style_name = "AI_Replicator_Dim"

        # --- 1. 设置文字样式 ---
        text_style = None
        try:
            try:
                text_style = self.cad.doc.TextStyles.Item(text_style_name)
            except:
                text_style = self.cad.doc.TextStyles.Add(text_style_name)
            
            # 配置文字样式 (关键: 高度设为0，允许标注样式覆盖)
            text_style.SetFont(font, False, False, 0, 0)
            text_style.Height = 0.0
            self.cad.doc.ActiveTextStyle = text_style
            # 记录文字样式名，后续强制应用到所有文字/标注
            self.text_style_name = text_style_name
            print(f"✅ 文字样式 '{text_style_name}' 已配置并激活")

        except Exception as e:
            print(f"⚠️  无法创建或设置文字样式: {e}")
            return

        # --- 2. 设置标注样式 ---
        if text_style:
            self._setup_dimension_style(dim_style_name, text_style, size)
        else:
            print("⚠️ 文字样式对象未成功创建，跳过标注样式设置。")

    def _setup_dimension_style(self, dim_style_name: str, text_style_obj: Any, size: float):
        """
        配置并激活专用的标注样式。
        说明：部分 AutoCAD 版本通过 COM 不允许修改 DimStyle 的 TextHeight 等属性，
        因此这里只尽量确保样式存在并被激活，具体的文字高度 / 箭头大小在每个标注对象上单独设置。
        """
        print(f"\n--- DEBUG: 进入 _setup_dimension_style ---")
        try:
            name = getattr(text_style_obj, "Name", str(text_style_obj))
        except Exception:
            name = str(text_style_obj)
        print(f"--- DEBUG: 标注样式名: {dim_style_name}, 文字样式对象: {name}, 尺寸(仅供参考): {size}")

        try:
            # 创建或获取标注样式
            try:
                dim_style = self.cad.doc.DimStyles.Item(dim_style_name)
                print(f"--- DEBUG: 找到现有标注样式 '{dim_style_name}'")
            except:
                dim_style = self.cad.doc.DimStyles.Add(dim_style_name)
                print(f"--- DEBUG: 创建新标注样式 '{dim_style_name}'")
                # 尝试从当前样式复制基础设置，避免所有东西都重置
                try:
                    active_dim_style = self.cad.doc.ActiveDimStyle
                    if active_dim_style:
                        print(f"--- DEBUG: 从活动标注样式 '{active_dim_style.Name}' 复制设置")
                        dim_style.CopyFrom(active_dim_style)
                    else:
                        print("--- DEBUG: 未找到活动标注样式可供复制")
                except Exception:
                    print("--- DEBUG: 复制基础设置失败，忽略继续")

            # 不再在 DimStyle 上强行设置 TextHeight / ArrowheadSize，避免 COM 抛错
            print("--- DEBUG: 跳过在 DimStyle 上设置 TextHeight / ArrowheadSize，改为在标注实体上单独设置")

            # 激活我们专属的样式（如果允许）
            try:
                self.cad.doc.ActiveDimStyle = dim_style
                print("✅ 已激活专属标注样式")
            except Exception:
                print("⚠️  无法设置 ActiveDimStyle，忽略")

            print("--- DEBUG: 退出 _setup_dimension_style (完成，无错误) ---")

        except Exception as e:
            print(f"⚠️  _setup_dimension_style 执行时发生错误（已忽略）：{e}")
            print("--- DEBUG: 退出 _setup_dimension_style (失败，但不会影响后续标注对象的大小设置) ---")

    def _create_layers(self, layer_colors: Dict[str, int]):
        """创建图层"""
        print("\n创建图层...")
        for layer_name, color in layer_colors.items():
            try:
                try:
                    layer = self.cad.doc.Layers.Item(layer_name)
                    layer.Color = color
                except:
                    self.cad.create_layer(layer_name, color)
            except:
                pass
        print(f"  ✅ {len(layer_colors)} 个图层")
    
    def _draw_elements(self, lines, circles, arcs, polylines, texts, dimensions):
        """绘制所有元素"""
        print("\n绘制元素...")
        
        # 获取延迟时间
        delay = self.draw_delay
        
        # 直线
        if lines:
            count = 0
            for line in lines:
                try:
                    obj = self.cad.draw_line(tuple(line["start"]), tuple(line["end"]))
                    if obj:
                        obj.Layer = line.get('layer', '0')
                        if line.get('color', 256) != 256:
                            obj.Color = line['color']
                        count += 1
                        if delay > 0:
                            time.sleep(delay)
                except:
                    pass
            print(f"  ✅ 直线: {count}/{len(lines)}")
        
        # 圆
        if circles:
            count = 0
            for circle in circles:
                try:
                    obj = self.cad.draw_circle(tuple(circle["center"]), circle["radius"])
                    if obj:
                        obj.Layer = circle.get('layer', '0')
                        if circle.get('color', 256) != 256:
                            obj.Color = circle['color']
                        count += 1
                        if delay > 0:
                            time.sleep(delay)
                except:
                    pass
            print(f"  ✅ 圆: {count}/{len(circles)}")
        
        # 圆弧
        if arcs:
            count = 0
            for arc in arcs:
                try:
                    obj = self.cad.draw_arc(
                        tuple(arc["center"]),
                        arc["radius"],
                        arc["start_angle"],
                        arc["end_angle"]
                    )
                    if obj:
                        obj.Layer = arc.get('layer', '0')
                        if arc.get('color', 256) != 256:
                            obj.Color = arc['color']
                        count += 1
                        if delay > 0:
                            time.sleep(delay)
                except:
                    pass
            print(f"  ✅ 圆弧: {count}/{len(arcs)}")
        
        # 多段线
        if polylines:
            count = 0
            for polyline in polylines:
                try:
                    vertices = polyline['vertices']
                    layer = polyline.get('layer', '0')
                    color = polyline.get('color', 7)
                    
                    for i in range(len(vertices) - 1):
                        start = vertices[i] + [0.0]
                        end = vertices[i + 1] + [0.0]
                        obj = self.cad.draw_line(tuple(start), tuple(end))
                        if obj:
                            obj.Layer = layer
                            if color != 256:
                                obj.Color = color
                        if delay > 0:
                            time.sleep(delay)
                    
                    if polyline.get('closed', False) and len(vertices) > 2:
                        start = vertices[-1] + [0.0]
                        end = vertices[0] + [0.0]
                        obj = self.cad.draw_line(tuple(start), tuple(end))
                        if obj:
                            obj.Layer = layer
                            if color != 256:
                                obj.Color = color
                        if delay > 0:
                            time.sleep(delay)
                    
                    count += 1
                except:
                    pass
            print(f"  ✅ 多段线: {count}/{len(polylines)}")
        
        # 文字
        if texts:
            count = 0
            for text in texts:
                try:
                    # 使用统一的高度（dim_size）以保证与标注文字大小一致
                    text_height = getattr(self, "dim_size", text["height"])
                    obj = self.cad.add_text(
                        text["text"],
                        tuple(text["position"]),
                        text_height
                    )
                    if obj:
                        obj.Layer = text.get('layer', '0')
                        if text.get('color', 256) != 256:
                            obj.Color = text['color']
                        # 强制使用仿宋文字样式（如果可用）
                        try:
                            style_name = getattr(self, "text_style_name", None)
                            if style_name:
                                # 不同对象属性名可能不同，依次尝试
                                try:
                                    obj.StyleName = style_name
                                except Exception:
                                    try:
                                        obj.TextStyle = style_name
                                    except Exception:
                                        pass
                        except Exception:
                            pass
                        count += 1
                        if delay > 0:
                            time.sleep(delay)
                except:
                    pass
            print(f"  ✅ 文字: {count}/{len(texts)}")
        
        # 标注
        if dimensions:
            success = self._draw_dimensions(dimensions)
            print(f"  ✅ 标注: {success}/{len(dimensions)}")
    
    def _draw_dimensions(self, dimensions: List[Dict]) -> int:
        """
        绘制标注
        
        Returns:
            成功绘制的数量
        """
        if not dimensions:
            return 0
        
        print(f"\n  创建 {len(dimensions)} 个标注...")
        success_count = 0
        delay = self.draw_delay
        
        for i, dim in enumerate(dimensions, 1):
            try:
                dim_type = dim.get('type', '')
                layer = dim.get('layer', '标注')
                color = dim.get('color', 7)
                measurement = dim.get('measurement', 0)
                
                # 获取显示文字
                text_override = dim.get('text_override', '')
                if not text_override:
                    if measurement >= 1:
                        display_text = str(int(round(measurement)))
                    else:
                        display_text = f"{measurement:.2f}"
                else:
                    display_text = text_override
                
                dim_obj = None
                
                # 对齐标注
                if dim_type == 'AcDbAlignedDimension':
                    dim_obj = self._create_aligned_dimension(dim, display_text)
                
                # 旋转标注
                elif dim_type == 'AcDbRotatedDimension':
                    dim_obj = self._create_rotated_dimension(dim, display_text)
                
                # 角度标注 - 用文字表示
                elif 'Angular' in dim_type:
                    dim_obj = self._create_angular_text(dim, layer, color)
                
                # 半径标注 - 用文字 "R数值" 表示
                elif 'Radial' in dim_type:
                    dim_obj = self._create_radial_text(dim, layer, color)
                
                # 直径标注 - 用文字 "Φ数值" 表示
                elif 'Diameter' in dim_type:
                    dim_obj = self._create_diameter_text(dim, layer, color)
                
                # 设置属性
                if dim_obj:
                    try:
                        dim_obj.Layer = layer
                        if color != 256:
                            dim_obj.Color = color
                        success_count += 1
                        if delay > 0:
                            time.sleep(delay)
                    except:
                        pass
                        
            except Exception as e:
                pass
        
        return success_count
    
    def _create_aligned_dimension(self, dim: Dict, display_text: str):
        """创建对齐标注"""
        if 'ext_line1_point' not in dim or 'ext_line2_point' not in dim:
            return None
        
        pt1 = dim['ext_line1_point']
        pt2 = dim['ext_line2_point']
        
        if 'text_position' in dim:
            dim_pt = dim['text_position']
        else:
            mid_x = (pt1[0] + pt2[0]) / 2
            mid_y = (pt1[1] + pt2[1]) / 2
            dim_pt = [mid_x, mid_y + 10, 0.0]
        
        try:
            pt1_var = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, pt1)
            pt2_var = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, pt2)
            dim_pt_var = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, dim_pt)
            
            dim_obj = self.cad.model_space.AddDimAligned(pt1_var, pt2_var, dim_pt_var)
            dim_obj.TextOverride = display_text
            # 直接在标注对象上设置文字高度和箭头大小，避免依赖样式属性
            try:
                text_height = getattr(self, "dim_size", None)
                if text_height:
                    dim_obj.TextHeight = text_height
                # 箭头大小也随文字高度一起调整
                arrow_size = getattr(self, "dim_size", None)
                if arrow_size:
                    try:
                        dim_obj.ArrowheadSize = arrow_size
                    except Exception:
                        # 部分版本属性名可能不同，忽略失败
                        pass
                # 强制使用仿宋文字样式（如果可用）
                style_name = getattr(self, "text_style_name", None)
                if style_name:
                    try:
                        dim_obj.TextStyle = style_name
                    except Exception:
                        pass
            except Exception:
                pass
            
            return dim_obj
        except:
            return None
    
    def _create_rotated_dimension(self, dim: Dict, display_text: str):
        """创建旋转标注"""
        if 'ext_line1_point' not in dim or 'ext_line2_point' not in dim:
            return None
        
        pt1 = dim['ext_line1_point']
        pt2 = dim['ext_line2_point']
        
        if 'text_position' in dim:
            dim_pt = dim['text_position']
        else:
            mid_x = (pt1[0] + pt2[0]) / 2
            mid_y = (pt1[1] + pt2[1]) / 2
            dim_pt = [mid_x, mid_y + 10, 0.0]
        
        # 根据 is_horizontal 标志判断旋转角度
        # 如果没有这个标志，则使用 dim_rotation
        import math
        if 'is_horizontal' in dim:
            if dim['is_horizontal']:
                rotation_rad = 0  # 水平标注
            else:
                rotation_rad = math.pi / 2  # 垂直标注 (90°)
        else:
            rotation = dim.get('dim_rotation', 0)
            rotation_rad = math.radians(rotation)
        
        try:
            pt1_var = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, pt1)
            pt2_var = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, pt2)
            dim_pt_var = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, dim_pt)
            
            dim_obj = self.cad.model_space.AddDimRotated(pt1_var, pt2_var, dim_pt_var, rotation_rad)
            dim_obj.TextOverride = display_text
            # 直接在标注对象上设置文字高度和箭头大小，避免依赖样式属性
            try:
                text_height = getattr(self, "dim_size", None)
                if text_height:
                    dim_obj.TextHeight = text_height
                # 箭头大小也随文字高度一起调整
                arrow_size = getattr(self, "dim_size", None)
                if arrow_size:
                    try:
                        dim_obj.ArrowheadSize = arrow_size
                    except Exception:
                        pass
                # 强制使用仿宋文字样式（如果可用）
                style_name = getattr(self, "text_style_name", None)
                if style_name:
                    try:
                        dim_obj.TextStyle = style_name
                    except Exception:
                        pass
            except Exception:
                pass
            
            return dim_obj
        except:
            return None
    
    def _create_angular_text(self, dim: Dict, layer: str, color: int):
        """创建角度标注（用文字表示）"""
        if 'text_position' not in dim:
            return None
        
        try:
            import math
            measurement = dim.get('measurement', 0)
            text_override = dim.get('text_override', '')
            if text_override:
                text = text_override
            else:
                angle_deg = math.degrees(measurement)
                # 若为整数角度（如 12.0），显示为“12°”；否则保留 1 位小数
                angle_rounded = round(angle_deg, 1)
                if abs(angle_rounded - round(angle_rounded)) < 1e-6:
                    text = f"{int(round(angle_rounded))}°"
                else:
                    text = f"{angle_rounded:.1f}°"
            text_pos = dim['text_position']
            
            text_height = getattr(self, 'dim_size', 2.5)
            obj = self.cad.add_text(text, tuple(text_pos), text_height)
            # 强制使用仿宋文字样式（如果可用）
            try:
                style_name = getattr(self, "text_style_name", None)
                if style_name and obj:
                    try:
                        obj.StyleName = style_name
                    except Exception:
                        try:
                            obj.TextStyle = style_name
                        except Exception:
                            pass
            except Exception:
                pass
            return obj
        except:
            return None

    def _create_radial_text(self, dim: Dict, layer: str, color: int):
        """创建半径标注（用文字 R数值 表示）"""
        if 'text_position' not in dim:
            return None
        
        try:
            measurement = dim.get('measurement', 0)
            text_override = dim.get('text_override', '')
            
            if text_override:
                text = text_override
            else:
                # 格式化为 "R数值"
                if measurement >= 1:
                    text = f"R{int(round(measurement))}"
                else:
                    text = f"R{measurement:.2f}"
            
            text_pos = dim['text_position']
            text_height = getattr(self, 'dim_size', 2.0)
            obj = self.cad.add_text(text, tuple(text_pos), text_height)
            
            # 设置文字样式
            try:
                style_name = getattr(self, "text_style_name", None)
                if style_name and obj:
                    try:
                        obj.StyleName = style_name
                    except Exception:
                        try:
                            obj.TextStyle = style_name
                        except Exception:
                            pass
            except Exception:
                pass
            
            return obj
        except:
            return None

    def _create_diameter_text(self, dim: Dict, layer: str, color: int):
        """创建直径标注（用文字 Φ数值 表示）"""
        if 'text_position' not in dim:
            return None
        
        try:
            measurement = dim.get('measurement', 0)
            text_override = dim.get('text_override', '')
            
            if text_override:
                text = text_override
            else:
                # 格式化为 "Φ数值"
                if measurement >= 1:
                    text = f"Φ{int(round(measurement))}"
                else:
                    text = f"Φ{measurement:.2f}"
            
            text_pos = dim['text_position']
            text_height = getattr(self, 'dim_size', 2.0)
            obj = self.cad.add_text(text, tuple(text_pos), text_height)
            
            # 设置文字样式
            try:
                style_name = getattr(self, "text_style_name", None)
                if style_name and obj:
                    try:
                        obj.StyleName = style_name
                    except Exception:
                        try:
                            obj.TextStyle = style_name
                        except Exception:
                            pass
            except Exception:
                pass
            
            return obj
        except:
            return None


# 示例使用
if __name__ == "__main__":
    print("=" * 80)
    print("🎨 图纸复刻器")
    print("=" * 80)
    print()
    print("请选择复刻模式:")
    print("  1. 单文件交互模式 (操作 drawing_with_dimensions.json)")
    print("  2. U型渠模板批量复刻 (操作 u_channel_template/ 目录下所有.json文件)")
    print()
    
    main_choice = input("请选择 (1/2) [默认: 2]: ").strip() or '2'

    if main_choice == '1':
        # --- 原来的交互模式 ---
        print("\n--- 启动单文件交互模式 ---")
        replicator = DrawingReplicator()
        
        if not replicator.connect():
            input("按任意键退出...")
            exit()
        
        print()
        print("=" * 80)
        print("可用功能演示")
        print("=" * 80)
        print()
        print("1. 查看所有图层")
        layers = replicator.get_available_layers()
        print(f"   图层列表: {', '.join(layers)}")
        
        print()
        print("2. 选择复刻模式:")
        print("   a. 复刻所有元素")
        print("   b. 复刻单个图层")
        print("   c. 复刻多个图层")
        print("   d. 按类型复刻")
        print()
        
        choice = input("请选择 (a/b/c/d) [默认: a]: ").strip().lower() or 'a'
        
        if choice == 'a':
            replicator.replicate_all()
        
        elif choice == 'b':
            print(f"\n可用图层: {', '.join(layers)}")
            layer = input("请输入图层名称: ").strip()
            if layer:
                replicator.replicate_layer(layer)
        
        elif choice == 'c':
            print(f"\n可用图层: {', '.join(layers)}")
            layer_input = input("请输入图层名称（用逗号分隔）: ").strip()
            if layer_input:
                layer_list = [l.strip() for l in layer_input.split(',')]
                replicator.replicate_layers(layer_list)
        
        elif choice == 'd':
            print("\n选择要复刻的元素类型:")
            lines = input("  直线? (y/n) [y]: ").strip().lower() != 'n'
            circles = input("  圆? (y/n) [y]: ").strip().lower() != 'n'
            arcs = input("  圆弧? (y/n) [y]: ").strip().lower() != 'n'
            polylines = input("  多段线? (y/n) [y]: ").strip().lower() != 'n'
            texts = input("  文字? (y/n) [y]: ").strip().lower() != 'n'
            dimensions = input("  标注? (y/n) [y]: ").strip().lower() != 'n'
            
            layer_input = input("\n  只复刻特定图层? (留空=全部): ").strip()
            selected_layers = None
            if layer_input:
                selected_layers = [l.strip() for l in layer_input.split(',')]
            
            replicator.replicate_elements(
                lines=lines,
                circles=circles,
                arcs=arcs,
                polylines=polylines,
                texts=texts,
                dimensions=dimensions,
                layers=selected_layers
            )

    elif main_choice == '2':
        # --- 新增的批量模式 ---
        print("\n--- 启动U型渠模板批量复刻 ---")
        
        import urllib.request
        
        template_data = {}
        
        # 1. 尝试从 Backend API 获取 (优先)
        backend_url = "http://localhost:8001/api/templates/u_channel_template/excavated_canal"
        print(f"正在尝试从后端获取模板数据: {backend_url} ...")
        
        try:
            with urllib.request.urlopen(backend_url, timeout=2) as response:
                if response.status == 200:
                    template_data = json.loads(response.read().decode('utf-8'))
                    print(f"✅ 成功从 API 获取 {len(template_data)} 个模板文件。")
        except Exception as e:
            print(f"⚠️  无法连接到后端 API: {e}")
            print("   尝试使用本地文件系统作为后备...")
            
            # 2. 降级到本地文件查找
            possible_paths = [
                'backend/drawing/u_channel_template/excavated_canal',
                '../../backend/drawing/u_channel_template/excavated_canal',
                'u_channel_template/excavated_canal',
                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'backend/drawing/u_channel_template/excavated_canal')
            ]
            template_dir = None
            for path in possible_paths:
                if os.path.isdir(os.path.abspath(path)):
                    template_dir = os.path.abspath(path)
                    break
            
            if template_dir:
                print(f"✅ 找到本地目录: {template_dir}")
                json_files = sorted([f for f in os.listdir(template_dir) if f.endswith('.json')])
                for fname in json_files:
                    try:
                        with open(os.path.join(template_dir, fname), 'r', encoding='utf-8') as f:
                            template_data[fname] = json.load(f)
                    except:
                        pass
            else:
                print("❌ 错误: 无法获取模板数据 (API 连接失败且本地目录不存在)")
                input("按任意键退出...")
                exit()

        if not template_data:
            print("❌ 错误: 未找到有效的模板数据。")
            input("按任意键退出...")
            exit()

        # 连接一次CAD
        cad_controller = AutoCADController()
        if not cad_controller.connect():
            input("按任意键退出...")
            exit()

        print(f"✅ 成功连接到AutoCAD, 准备绘制 {len(template_data)} 个部件。")
        
        # 循环绘制
        # 对文件名排序以保证绘制顺序 (API 返回的是字典，顺序不一定保证，所以要手动排序)
        sorted_files = sorted(template_data.keys())
        
        for i, file_name in enumerate(sorted_files):
            print(f"\n--- 正在绘制: {file_name} [{i+1}/{len(sorted_files)}] ---")
            
            # 使用直接传入 data 的方式初始化，不再依赖文件路径
            replicator = DrawingReplicator(json_file=None, data=template_data[file_name])
            replicator.cad = cad_controller  # 注入已连接的控制器
            
            # 仅在第一次设置标注全局比例
            replicator.replicate_all(setup_dimlfac=(i == 0))

        print("\n" + "=" * 80)
        print("✅ 所有模板部件复刻完成!")
        print("=" * 80)
        cad_controller.zoom_extents()

    else:
        print("❌ 无效选择。")

    print()
    input("完成！按任意键退出...")
