"""
AutoCAD 控制器
使用 COM 接口控制 AutoCAD
"""
import win32com.client
import pythoncom
from typing import Optional, Tuple, List, Dict, Any
import math
import json
import os


class AutoCADController:
    """AutoCAD 控制器类"""
    
    def __init__(self):
        self.acad = None
        self.doc = None
        self.model_space = None
        
    def connect(self) -> bool:
        """
        连接到正在运行的 AutoCAD 实例
        
        Returns:
            bool: 连接成功返回 True，否则返回 False
        """
        try:
            # 初始化 COM 库 (特别是在多线程环境或Web服务中需要)
            pythoncom.CoInitialize()
            
            # 尝试获取已经运行的 AutoCAD 实例
            self.acad = win32com.client.Dispatch("AutoCAD.Application")
            # 设置为可见，有时可以避免后台挂起或权限问题
            self.acad.Visible = True
            print(f"成功连接到 AutoCAD {self.acad.Version}")
            
            # 获取当前活动文档
            self.doc = self.acad.ActiveDocument
            print(f"当前文档: {self.doc.Name}")
            
            # 获取模型空间
            self.model_space = self.doc.ModelSpace
            
            return True
        except Exception as e:
            print(f"连接失败: {e}")
            print("请确保 AutoCAD 已经打开！")
            return False

    def vtPoint(self, x, y, z=0):
        """[Helper] 将坐标转换为 AutoCAD COM 接口需要的 Variant 数组"""
        return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, (x, y, z))

    def vtFloat(self, data):
        """[Helper] 将列表转换为 AutoCAD COM 接口需要的 Variant 浮点数组"""
        return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, data)

    def vtInt(self, data):
        """[Helper] 将列表转换为 AutoCAD COM 接口需要的 Variant 整数数组"""
        return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_I2, data)

    def vtVariant(self, data):
        """[Helper] 将列表转换为 AutoCAD COM 接口需要的 Variant 变体数组"""
        return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_VARIANT, data)

    def get_entity(self, handle: str):
        """
        [Helper] 根据 Handle 获取 COM 实体对象
        这是编辑操作的基础，AI 可以通过这个方法拿到对象后直接调用 COM 方法 (如 .Move, .Delete)
        """
        try:
            return self.doc.HandleToObject(handle)
        except Exception as e:
            print(f"无法找到实体 {handle}: {e}")
            return None

    def get_current_view_bounds(self) -> Tuple[Tuple[float, float], Tuple[float, float]]:
        """
        获取当前视图的可视范围 (WCS坐标)
        
        Returns:
            ((min_x, min_y), (max_x, max_y))
        """
        try:
            # 获取当前视图中心 (UCS)
            view_ctr = self.doc.GetVariable("VIEWCTR") # 返回 (x, y, z)
            # 获取当前视图高度
            view_height = self.doc.GetVariable("VIEWSIZE")
            # 获取屏幕像素尺寸，计算宽高比
            screen_size = self.doc.GetVariable("SCREENSIZE") # 返回 (width, height)
            aspect_ratio = screen_size[0] / screen_size[1]
            
            view_width = view_height * aspect_ratio
            
            # 计算边界 (假设视图没有旋转，简单计算)
            # 注意：VIEWCTR 通常是 UCS 坐标，但在 2D 绘图中通常与 WCS 一致或容易转换
            # 这里简化处理，假设用户在标准俯视图
            
            min_x = view_ctr[0] - (view_width / 2)
            max_x = view_ctr[0] + (view_width / 2)
            min_y = view_ctr[1] - (view_height / 2)
            max_y = view_ctr[1] + (view_height / 2)
            
            return ((min_x, min_y), (max_x, max_y))
        except Exception as e:
            print(f"获取视图范围失败: {e}")
            return ((0,0), (0,0))
    
    def start_autocad(self) -> bool:
        """
        启动新的 AutoCAD 实例（如果没有运行）
        
        Returns:
            bool: 启动成功返回 True，否则返回 False
        """
        try:
            self.acad = win32com.client.Dispatch("AutoCAD.Application")
            self.acad.Visible = True
            
            # 创建新文档或获取当前文档
            if self.acad.Documents.Count == 0:
                self.doc = self.acad.Documents.Add()
            else:
                self.doc = self.acad.ActiveDocument
                
            self.model_space = self.doc.ModelSpace
            print(f"AutoCAD 已启动，版本: {self.acad.Version}")
            return True
        except Exception as e:
            print(f"启动失败: {e}")
            return False
    
    def execute_command(self, command: str):
        """
        执行 AutoCAD 命令
        
        Args:
            command: AutoCAD 命令字符串
        """
        try:
            self.doc.SendCommand(command + "\n")
            print(f"执行命令: {command}")
        except Exception as e:
            print(f"命令执行失败: {e}")
    
    def draw_line(self, start_point: Tuple[float, float, float], 
                  end_point: Tuple[float, float, float]):
        """
        绘制直线
        
        Args:
            start_point: 起点坐标 (x, y, z)
            end_point: 终点坐标 (x, y, z)
        """
        try:
            line = self.model_space.AddLine(
                win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, start_point),
                win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, end_point)
            )
            print(f"绘制直线: {start_point} -> {end_point}")
            return line
        except Exception as e:
            print(f"绘制直线失败: {e}")
            return None
    
    def draw_circle(self, center: Tuple[float, float, float], radius: float):
        """
        绘制圆
        
        Args:
            center: 圆心坐标 (x, y, z)
            radius: 半径
        """
        try:
            circle = self.model_space.AddCircle(
                win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, center),
                radius
            )
            print(f"绘制圆: 圆心{center}, 半径{radius}")
            return circle
        except Exception as e:
            print(f"绘制圆失败: {e}")
            return None
    
    def draw_arc(self, center: Tuple[float, float, float], radius: float, 
                 start_angle_deg: float, end_angle_deg: float):
        """
        绘制圆弧
        
        Args:
            center: 圆心坐标 (x, y, z)
            radius: 半径
            start_angle_deg: 起始角度（度）
            end_angle_deg: 结束角度（度）
        """
        try:
            start_angle_rad = math.radians(start_angle_deg)
            end_angle_rad = math.radians(end_angle_deg)
            
            arc = self.model_space.AddArc(
                win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, center),
                radius,
                start_angle_rad,
                end_angle_rad
            )
            print(f"绘制圆弧: 圆心{center}, 半径{radius}, 角度 {start_angle_deg}° -> {end_angle_deg}°")
            return arc
        except Exception as e:
            print(f"绘制圆弧失败: {e}")
            return None
    
    def draw_rectangle(self, corner1: Tuple[float, float], 
                       corner2: Tuple[float, float]):
        """
        绘制矩形
        
        Args:
            corner1: 第一个角点 (x, y)
            corner2: 对角点 (x, y)
        """
        try:
            x1, y1 = corner1
            x2, y2 = corner2
            
            # 绘制四条边
            lines = []
            lines.append(self.draw_line((x1, y1, 0), (x2, y1, 0)))
            lines.append(self.draw_line((x2, y1, 0), (x2, y2, 0)))
            lines.append(self.draw_line((x2, y2, 0), (x1, y2, 0)))
            lines.append(self.draw_line((x1, y2, 0), (x1, y1, 0)))
            
            print(f"绘制矩形: {corner1} -> {corner2}")
            return lines
        except Exception as e:
            print(f"绘制矩形失败: {e}")
            return None
    
    def add_text(self, text: str, position: Tuple[float, float, float], 
                 height: float = 2.5):
        """
        添加文字
        
        Args:
            text: 文字内容
            position: 插入点坐标 (x, y, z)
            height: 文字高度
        """
        try:
            text_obj = self.model_space.AddText(
                text,
                win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, position),
                height
            )
            print(f"添加文字: '{text}' at {position}")
            return text_obj
        except Exception as e:
            print(f"添加文字失败: {e}")
            return None
    
    def zoom_extents(self):
        """缩放到全部显示"""
        try:
            self.acad.ZoomExtents()
            print("缩放到全部显示")
        except Exception as e:
            print(f"缩放失败: {e}")
    
    def save_as(self, file_path: str):
        """
        另存为文件
        
        Args:
            file_path: 保存路径（完整路径）
        """
        try:
            self.doc.SaveAs(file_path)
            print(f"文件已保存: {file_path}")
        except Exception as e:
            print(f"保存失败: {e}")
    
    def get_all_layers(self) -> List[str]:
        """
        获取所有图层名称
        
        Returns:
            List[str]: 图层名称列表
        """
        try:
            layers = []
            for layer in self.doc.Layers:
                layers.append(layer.Name)
            print(f"共有 {len(layers)} 个图层")
            return layers
        except Exception as e:
            print(f"获取图层失败: {e}")
            return []
    
    def create_layer(self, layer_name: str, color: int = 7):
        """
        创建新图层
        
        Args:
            layer_name: 图层名称
            color: 颜色索引 (1-255)
        """
        try:
            layer = self.doc.Layers.Add(layer_name)
            layer.Color = color
            print(f"创建图层: {layer_name}")
            return layer
        except Exception as e:
            print(f"创建图层失败: {e}")
            return None
    
    def set_active_layer(self, layer_name: str):
        """
        设置当前图层
        
        Args:
            layer_name: 图层名称
        """
        try:
            self.doc.ActiveLayer = self.doc.Layers.Item(layer_name)
            print(f"切换到图层: {layer_name}")
        except Exception as e:
            print(f"设置图层失败: {e}")
    
    def get_entity_count(self) -> int:
        """
        获取模型空间中的实体数量
        
        Returns:
            int: 实体数量
        """
        try:
            count = self.model_space.Count
            print(f"模型空间中有 {count} 个实体")
            return count
        except Exception as e:
            print(f"获取实体数量失败: {e}")
            return 0
    
    def get_drawing_info(self) -> dict:
        """
        获取当前图纸的详细信息
        
        Returns:
            dict: 包含图纸信息的字典
        """
        try:
            info = {
                # 基本信息
                '文件名': self.doc.Name,
                '完整路径': self.doc.FullName if hasattr(self.doc, 'FullName') else '未保存',
                'AutoCAD版本': self.acad.Version,
                
                # 文档状态
                '是否已保存': not self.doc.Saved,
                '是否只读': self.doc.ReadOnly,
                
                # 图层信息
                '图层总数': self.doc.Layers.Count,
                '当前图层': self.doc.ActiveLayer.Name,
                
                # 实体信息
                '模型空间实体数': self.model_space.Count,
                '图纸空间实体数': self.doc.PaperSpace.Count if hasattr(self.doc, 'PaperSpace') else 0,
                
                # 单位设置
                '插入单位': self.doc.GetVariable("INSUNITS"),
                '测量单位': self.doc.GetVariable("MEASUREMENT"),
                
                # 图形界限
                'LimMin': (self.doc.GetVariable("LIMMIN")[0], self.doc.GetVariable("LIMMIN")[1]),
                'LimMax': (self.doc.GetVariable("LIMMAX")[0], self.doc.GetVariable("LIMMAX")[1]),
            }
            
            return info
        except Exception as e:
            print(f"获取图纸信息失败: {e}")
            return {}
    
    def print_drawing_info(self):
        """打印当前图纸的详细信息（格式化输出）"""
        info = self.get_drawing_info()
        if not info:
            return
        
        print("\n" + "=" * 60)
        print("当前图纸信息")
        print("=" * 60)
        
        for key, value in info.items():
            if isinstance(value, tuple):
                print(f"{key:20s}: ({value[0]:.2f}, {value[1]:.2f})")
            elif isinstance(value, bool):
                print(f"{key:20s}: {'是' if value else '否'}")
            else:
                print(f"{key:20s}: {value}")
        
        print("=" * 60 + "\n")
    
    def get_layer_details(self) -> List[dict]:
        """
        获取所有图层的详细信息
        
        Returns:
            List[dict]: 图层信息列表
        """
        try:
            layers_info = []
            for layer in self.doc.Layers:
                layer_info = {
                    '名称': layer.Name,
                    '颜色': layer.Color,
                    '线型': layer.Linetype,
                    '是否开启': layer.LayerOn,
                    '是否冻结': layer.Freeze,
                    '是否锁定': layer.Lock,
                }
                layers_info.append(layer_info)
            
            return layers_info
        except Exception as e:
            print(f"获取图层详情失败: {e}")
            return []
    
    def print_layer_details(self):
        """打印所有图层的详细信息"""
        layers = self.get_layer_details()
        if not layers:
            return
        
        print("\n" + "=" * 80)
        print(f"图层详情 (共 {len(layers)} 个图层)")
        print("=" * 80)
        print(f"{'名称':<20} {'颜色':<8} {'开启':<8} {'冻结':<8} {'锁定':<8}")
        print("-" * 80)
        
        for layer in layers:
            print(f"{layer['名称']:<20} "
                  f"{layer['颜色']:<8} "
                  f"{'✓' if layer['是否开启'] else '✗':<8} "
                  f"{'✓' if layer['是否冻结'] else '✗':<8} "
                  f"{'✓' if layer['是否锁定'] else '✗':<8}")
        
        print("=" * 80 + "\n")
    
    def get_entities_by_type(self) -> dict:
        """
        统计模型空间中各类实体的数量
        
        Returns:
            dict: 实体类型及其数量
        """
        try:
            entity_types = {}
            for entity in self.model_space:
                entity_type = entity.ObjectName
                entity_types[entity_type] = entity_types.get(entity_type, 0) + 1
            
            return entity_types
        except Exception as e:
            print(f"获取实体类型统计失败: {e}")
            return {}
    
    def print_entity_statistics(self):
        """打印实体统计信息"""
        entities = self.get_entities_by_type()
        if not entities:
            print("模型空间为空")
            return
        
        print("\n" + "=" * 50)
        print("实体统计")
        print("=" * 50)
        
        # 中文名称映射
        type_names = {
            'AcDbLine': '直线',
            'AcDbCircle': '圆',
            'AcDbArc': '圆弧',
            'AcDbPolyline': '多段线',
            'AcDbText': '文字',
            'AcDbMText': '多行文字',
            'AcDbHatch': '填充',
            'AcDbBlockReference': '块参照',
        }
        
        total = sum(entities.values())
        for entity_type, count in sorted(entities.items(), key=lambda x: x[1], reverse=True):
            type_name = type_names.get(entity_type, entity_type)
            percentage = (count / total * 100) if total > 0 else 0
            print(f"{type_name:<15} : {count:>6} ({percentage:>5.1f}%)")
        
        print("-" * 50)
        print(f"{'总计':<15} : {total:>6}")
        print("=" * 50 + "\n")
    
    def get_bounds(self) -> Tuple[Tuple[float, float], Tuple[float, float]]:
        """
        获取所有实体的边界范围
        
        Returns:
            Tuple: ((min_x, min_y), (max_x, max_y))
        """
        try:
            if self.model_space.Count == 0:
                return ((0, 0), (0, 0))
            
            min_x = min_y = float('inf')
            max_x = max_y = float('-inf')
            
            for entity in self.model_space:
                try:
                    # 获取实体的边界框
                    bounds = entity.GetBoundingBox()
                    min_point = bounds[0]
                    max_point = bounds[1]
                    
                    min_x = min(min_x, min_point[0])
                    min_y = min(min_y, min_point[1])
                    max_x = max(max_x, max_point[0])
                    max_y = max(max_y, max_point[1])
                except:
                    continue
            
            return ((min_x, min_y), (max_x, max_y))
        except Exception as e:
            print(f"获取边界失败: {e}")
            return ((0, 0), (0, 0))
    
    def print_bounds(self):
        """打印图纸边界信息"""
        bounds = self.get_bounds()
        if bounds == ((0, 0), (0, 0)):
            print("无法获取边界信息")
            return
        
        min_point, max_point = bounds
        width = max_point[0] - min_point[0]
        height = max_point[1] - min_point[1]
        
        print("\n" + "=" * 50)
        print("图纸边界")
        print("=" * 50)
        print(f"最小点: ({min_point[0]:.2f}, {min_point[1]:.2f})")
        print(f"最大点: ({max_point[0]:.2f}, {max_point[1]:.2f})")
        print(f"宽度: {width:.2f}")
        print(f"高度: {height:.2f}")
        print(f"面积: {width * height:.2f}")
        print("=" * 50 + "\n")
    
    def get_layouts(self) -> List[dict]:
        """
        获取所有布局（包括模型空间）
        
        Returns:
            List[dict]: 布局信息列表
        """
        try:
            layouts_info = []
            for layout in self.doc.Layouts:
                layout_info = {
                    '名称': layout.Name,
                    '是否模型空间': layout.ModelType,
                    '图块名称': layout.Block.Name if hasattr(layout, 'Block') else 'N/A',
                }
                layouts_info.append(layout_info)
            
            return layouts_info
        except Exception as e:
            print(f"获取布局失败: {e}")
            return []
    
    def get_viewports_count(self, layout_name: str = None) -> int:
        """
        获取指定布局中的视口数量
        
        Args:
            layout_name: 布局名称，如果为None则使用当前布局
            
        Returns:
            int: 视口数量
        """
        try:
            if layout_name:
                layout = self.doc.Layouts.Item(layout_name)
            else:
                layout = self.doc.ActiveLayout
            
            # 获取布局的图块
            block = layout.Block
            
            # 统计视口数量
            viewport_count = 0
            for entity in block:
                if entity.ObjectName == "AcDbViewport":
                    viewport_count += 1
            
            return viewport_count
        except Exception as e:
            print(f"获取视口数量失败: {e}")
            return 0
    
    def get_all_viewports_info(self) -> dict:
        """
        获取所有布局的视口信息
        
        Returns:
            dict: {布局名称: 视口数量}
        """
        try:
            viewports_info = {}
            
            for layout in self.doc.Layouts:
                # 跳过模型空间
                if layout.ModelType:
                    continue
                
                # 获取该布局的视口数量
                block = layout.Block
                viewport_count = 0
                
                for entity in block:
                    if entity.ObjectName == "AcDbViewport":
                        viewport_count += 1
                
                # AutoCAD图纸空间默认有一个大视口（通常不计入），所以减1
                # 如果只有1个或0个，说明没有实际的小图纸视口
                actual_viewports = max(0, viewport_count - 1)
                
                if viewport_count > 0:  # 只记录有视口的布局
                    viewports_info[layout.Name] = {
                        '总视口数': viewport_count,
                        '实际小图纸数': actual_viewports
                    }
            
            return viewports_info
        except Exception as e:
            print(f"获取视口信息失败: {e}")
            return {}
    
    def print_layouts_and_viewports(self):
        """打印所有布局和视口信息"""
        try:
            print("\n" + "=" * 70)
            print("布局和视口分析")
            print("=" * 70)
            
            # 获取布局信息
            layouts = self.get_layouts()
            print(f"\n总布局数: {len(layouts)}")
            
            # 分类显示
            model_layouts = [l for l in layouts if l['是否模型空间']]
            paper_layouts = [l for l in layouts if not l['是否模型空间']]
            
            print(f"  - 模型空间: {len(model_layouts)} 个")
            print(f"  - 图纸空间(布局): {len(paper_layouts)} 个")
            
            # 获取视口信息
            viewports_info = self.get_all_viewports_info()
            
            if viewports_info:
                print("\n" + "-" * 70)
                print("各布局的视口统计:")
                print("-" * 70)
                print(f"{'布局名称':<20} {'总视口数':<12} {'实际小图纸数':<15}")
                print("-" * 70)
                
                total_viewports = 0
                total_actual = 0
                
                for layout_name, info in viewports_info.items():
                    print(f"{layout_name:<20} {info['总视口数']:<12} {info['实际小图纸数']:<15}")
                    total_viewports += info['总视口数']
                    total_actual += info['实际小图纸数']
                
                print("-" * 70)
                print(f"{'总计':<20} {total_viewports:<12} {total_actual:<15}")
                print("=" * 70)
                
                # 结论
                if total_actual > 0:
                    print(f"\n✅ 检测到 {total_actual} 个小图纸视口")
                    print(f"   分布在 {len(viewports_info)} 个布局中")
                else:
                    print("\n❌ 未检测到小图纸视口")
                    print("   可能所有内容都在模型空间中")
            else:
                print("\n❌ 未检测到图纸空间布局")
                print("   所有内容都在模型空间中")
            
            print()
            
        except Exception as e:
            print(f"打印布局信息失败: {e}")
    
    def get_blocks_count(self) -> dict:
        """
        获取图块统计信息
        
        Returns:
            dict: {图块名称: 引用次数}
        """
        try:
            blocks_count = {}
            
            # 遍历模型空间中的所有实体
            for entity in self.model_space:
                if entity.ObjectName == "AcDbBlockReference":
                    block_name = entity.Name
                    blocks_count[block_name] = blocks_count.get(block_name, 0) + 1
            
            return blocks_count
        except Exception as e:
            print(f"获取图块统计失败: {e}")
            return {}
    
    def print_blocks_statistics(self):
        """打印图块统计信息"""
        blocks = self.get_blocks_count()
        
        if not blocks:
            print("\n模型空间中没有图块")
            return
        
        print("\n" + "=" * 60)
        print("图块统计")
        print("=" * 60)
        print(f"{'图块名称':<35} {'引用次数':<10}")
        print("-" * 60)
        
        # 按引用次数排序
        sorted_blocks = sorted(blocks.items(), key=lambda x: x[1], reverse=True)
        total = sum(blocks.values())
        
        for block_name, count in sorted_blocks:
            percentage = (count / total * 100) if total > 0 else 0
            print(f"{block_name:<35} {count:<10} ({percentage:>5.1f}%)")
        
        print("-" * 60)
        print(f"{'总计':<35} {total:<10}")
        print("=" * 60 + "\n")
    
    def analyze_drawing_structure(self):
        """
        综合分析图纸结构（包括布局、视口、图块等）
        """
        print("\n" + "=" * 70)
        print("📐 图纸结构综合分析")
        print("=" * 70)
        
        # 1. 基本信息
        info = self.get_drawing_info()
        print(f"\n【基本信息】")
        print(f"文件名: {info.get('文件名', 'N/A')}")
        print(f"模型空间实体数: {info.get('模型空间实体数', 0)}")
        print(f"图纸空间实体数: {info.get('图纸空间实体数', 0)}")
        
        # 2. 布局和视口分析
        print(f"\n【布局分析】")
        viewports_info = self.get_all_viewports_info()
        total_small_drawings = sum(v['实际小图纸数'] for v in viewports_info.values())
        
        if viewports_info:
            print(f"图纸空间布局数: {len(viewports_info)}")
            for layout_name, vp_info in viewports_info.items():
                print(f"  - {layout_name}: {vp_info['实际小图纸数']} 个小图纸")
            print(f"\n🎯 总计: {total_small_drawings} 个小图纸视口")
        else:
            print("未使用图纸空间布局")
            print("🎯 总计: 0 个小图纸视口")
        
        # 3. 图块分析
        print(f"\n【图块分析】")
        blocks = self.get_blocks_count()
        if blocks:
            print(f"图块类型数: {len(blocks)}")
            print(f"图块引用总数: {sum(blocks.values())}")
            # 显示最常用的3个图块
            top_blocks = sorted(blocks.items(), key=lambda x: x[1], reverse=True)[:3]
            print("最常用的图块:")
            for block_name, count in top_blocks:
                print(f"  - {block_name}: {count} 次")
        else:
            print("未使用图块")
        
        # 4. 实体分布
        print(f"\n【实体分布】")
        entities = self.get_entities_by_type()
        if entities:
            total_entities = sum(entities.values())
            print(f"实体类型数: {len(entities)}")
            print(f"实体总数: {total_entities}")
            # 显示占比最高的3种实体
            top_entities = sorted(entities.items(), key=lambda x: x[1], reverse=True)[:3]
            type_names = {
                'AcDbLine': '直线',
                'AcDbCircle': '圆',
                'AcDbArc': '圆弧',
                'AcDbPolyline': '多段线',
                'AcDbText': '文字',
                'AcDbMText': '多行文字',
            }
            print("主要实体类型:")
            for entity_type, count in top_entities:
                type_name = type_names.get(entity_type, entity_type)
                percentage = (count / total_entities * 100)
                print(f"  - {type_name}: {count} ({percentage:.1f}%)")
        
        # 5. 结论
        print(f"\n{'=' * 70}")
        print("📊 结论:")
        if total_small_drawings > 0:
            print(f"✅ 这是一张包含 {total_small_drawings} 个小图纸的综合图纸")
            print(f"   分布在 {len(viewports_info)} 个图纸布局中")
        elif info.get('图纸空间实体数', 0) > 0:
            print("⚠️  图纸空间有内容，但未使用标准视口")
            print("   可能使用了其他方式组织图纸")
        else:
            print("ℹ️  这是一张单一的模型空间图纸")
            print("   所有内容都在模型空间中，未使用图纸布局")
        
        print("=" * 70 + "\n")
    
    def extract_drawing_data(self, only_visible: bool = False) -> Dict[str, Any]:
        """
        提取当前模型空间的所有图形实体数据
        
        Args:
            only_visible: 是否只提取当前视图范围内可见的实体
            
        Returns:
            dict: 包含 layer_colors 和 elements 的字典
        """
        data = {
            "layer_colors": {},
            "elements": {
                "lines": [],
                "circles": [],
                "arcs": [],
                "polylines": [],
                "texts": [],
                "dimensions": []
            }
        }

        if not self.model_space:
             return data

        print(f"开始提取图纸数据 (只提取可见区域: {only_visible})...")

        # 1. 提取图层颜色信息
        try:
            for layer in self.doc.Layers:
                data["layer_colors"][layer.Name] = layer.Color
        except Exception as e:
            print(f"提取图层信息失败: {e}")

        # 2. 确定遍历源 (模型空间 或 选择集)
        source_collection = self.model_space
        selection_set = None

        try:
            if only_visible:
                try:
                    # 获取当前视图边界
                    bounds = self.get_current_view_bounds()
                    min_pt = self.vtPoint(bounds[0][0], bounds[0][1], 0)
                    max_pt = self.vtPoint(bounds[1][0], bounds[1][1], 0)
                    
                    # 创建唯一的选择集名称
                    ss_name = "AI_Visible_Selection"
                    try:
                        self.doc.SelectionSets.Item(ss_name).Delete()
                    except:
                        pass
                        
                    selection_set = self.doc.SelectionSets.Add(ss_name)
                    # acSelectionSetWindow = 0
                    # 使用窗口选择
                    selection_set.Select(0, min_pt, max_pt)
                    
                    source_collection = selection_set
                    print(f"当前视图范围内包含 {source_collection.Count} 个实体")
                except Exception as e:
                    print(f"创建可视区域选择集失败，将回退到全图提取: {e}")
                    source_collection = self.model_space

            total = source_collection.Count
            if total == 0:
                print("没有找到实体")
                return data

            print(f"发现 {total} 个实体，正在处理...")
            
            for i, entity in enumerate(source_collection):
                try:
                    etype = entity.ObjectName
                    layer = entity.Layer
                    color = entity.Color # 256 is ByLayer
                    handle = entity.Handle # 获取实体句柄

                    # 直线
                    if etype == "AcDbLine":
                        data["elements"]["lines"].append({
                            "handle": handle,
                            "start": list(entity.StartPoint),
                            "end": list(entity.EndPoint),
                            "layer": layer,
                            "color": color
                        })
                    
                    # 圆
                    elif etype == "AcDbCircle":
                        data["elements"]["circles"].append({
                            "handle": handle,
                            "center": list(entity.Center),
                            "radius": entity.Radius,
                            "layer": layer,
                            "color": color
                        })
                    
                    # 圆弧
                    elif etype == "AcDbArc":
                        # COM 接口返回的是弧度，模板通常需要角度（度）
                        data["elements"]["arcs"].append({
                            "handle": handle,
                            "center": list(entity.Center),
                            "radius": entity.Radius,
                            "start_angle": math.degrees(entity.StartAngle),
                            "end_angle": math.degrees(entity.EndAngle),
                            "layer": layer,
                            "color": color
                        })
                    
                    # 多段线 (LWPolyline)
                    elif etype == "AcDbPolyline":
                        # Coordinates 返回扁平数组 [x1, y1, x2, y2, ...]
                        coords = entity.Coordinates
                        vertices = []
                        # 2D 多段线通常每两个一组
                        # 注意：如果是 3D Polyline (AcDb3dPolyline) 结构不同，这里主要处理 LWPolyline
                        step = 2
                        if len(coords) % 2 != 0:
                             # 防御性编程，如果读出来不对劲
                             pass
                        
                        for j in range(0, len(coords), step):
                            if j + 1 < len(coords):
                                vertices.append([coords[j], coords[j+1]])
                        
                        data["elements"]["polylines"].append({
                            "handle": handle,
                            "vertices": vertices,
                            "closed": entity.Closed,
                            "layer": layer,
                            "color": color
                        })
                    
                    # 文字
                    elif etype in ["AcDbText", "AcDbMText"]:
                        data["elements"]["texts"].append({
                            "handle": handle,
                            "text": entity.TextString,
                            "position": list(entity.InsertionPoint),
                            "height": entity.Height,
                            "layer": layer,
                            "color": color
                        })

                    # 标注 (完整导出，支持重建)
                    elif "Dimension" in etype:
                        dim_data = {
                            "handle": handle,
                            "type": etype,
                            "text_override": getattr(entity, 'TextOverride', '') or "",
                            "measurement": getattr(entity, 'Measurement', 0),
                            "layer": layer,
                            "color": color
                        }
                        
                        # 尝试获取各种标注点坐标（COM对象用try-except更可靠）
                        # 尺寸界线端点1
                        for attr in ['ExtLine1Point', 'XLine1Point', 'ExtLine1StartPoint']:
                            try:
                                val = getattr(entity, attr)
                                if val is not None:
                                    dim_data['ext_line1_point'] = list(val)
                                    break
                            except:
                                continue
                        
                        # 尺寸界线端点2
                        for attr in ['ExtLine2Point', 'XLine2Point', 'ExtLine2StartPoint']:
                            try:
                                val = getattr(entity, attr)
                                if val is not None:
                                    dim_data['ext_line2_point'] = list(val)
                                    break
                            except:
                                continue
                        
                        # 角度标注的额外点
                        for attr in ['ExtLine1EndPoint', 'ExtLine2EndPoint', 'AngleVertex', 'ExtLine1StartPoint', 'ExtLine2StartPoint']:
                            try:
                                val = getattr(entity, attr)
                                if val is not None:
                                    dim_data[attr.lower()] = list(val)
                            except:
                                continue
                        
                        # 半径/直径标注的特殊属性
                        if 'Radial' in etype or 'Diameter' in etype:
                            for attr in ['Center', 'ChordPoint', 'LeaderEndPoint']:
                                try:
                                    val = getattr(entity, attr)
                                    if val is not None:
                                        dim_data[attr.lower()] = list(val)
                                except:
                                    continue
                        
                        # 文字位置
                        try:
                            dim_data['text_position'] = list(entity.TextPosition)
                        except:
                            pass
                        
                        # 旋转角度
                        try:
                            dim_data['dim_rotation'] = math.degrees(entity.Rotation)
                        except:
                            dim_data['dim_rotation'] = 0.0
                        
                        # 线性比例因子
                        try:
                            dim_data['linear_scale_factor'] = entity.LinearScaleFactor
                        except:
                            pass
                        
                        # 对于旋转标注，用 BoundingBox 的长宽比推算端点
                        if etype == 'AcDbRotatedDimension' and 'ext_line1_point' not in dim_data:
                            try:
                                # 保存原始的文字大小和箭头大小
                                orig_text_height = None
                                orig_arrow_size = None
                                try:
                                    orig_text_height = entity.TextHeight
                                    orig_arrow_size = entity.ArrowheadSize
                                except:
                                    pass
                                
                                # 临时将文字和箭头设置为很小的值，减少对 BoundingBox 的影响
                                try:
                                    entity.TextHeight = 0.01
                                    entity.ArrowheadSize = 0.01
                                    entity.Update()
                                except:
                                    pass
                                
                                # 计算 BoundingBox
                                min_pt, max_pt = entity.GetBoundingBox()
                                min_pt = list(min_pt)
                                max_pt = list(max_pt)
                                
                                # 恢复原始的文字大小和箭头大小
                                try:
                                    if orig_text_height is not None:
                                        entity.TextHeight = orig_text_height
                                    if orig_arrow_size is not None:
                                        entity.ArrowheadSize = orig_arrow_size
                                    entity.Update()
                                except:
                                    pass
                                
                                # 保存原始尺寸信息
                                if orig_text_height is not None:
                                    dim_data['text_height'] = orig_text_height
                                if orig_arrow_size is not None:
                                    dim_data['arrow_size'] = orig_arrow_size
                                
                                # 计算边界框的宽度和高度
                                box_width = max_pt[0] - min_pt[0]
                                box_height = max_pt[1] - min_pt[1]
                                
                                # 根据长宽比判断是水平还是垂直标注
                                if box_width > box_height:
                                    # 宽度 > 高度 → 水平标注
                                    # 用 BoundingBox 的 X 范围作为端点
                                    y_pos = min_pt[1]  # 用底部 Y 坐标
                                    dim_data['ext_line1_point'] = [min_pt[0], y_pos, 0.0]
                                    dim_data['ext_line2_point'] = [max_pt[0], y_pos, 0.0]
                                    dim_data['is_horizontal'] = True
                                else:
                                    # 高度 > 宽度 → 垂直标注
                                    # 用 BoundingBox 的 Y 范围作为端点
                                    x_pos = min_pt[0]  # 用左侧 X 坐标
                                    dim_data['ext_line1_point'] = [x_pos, min_pt[1], 0.0]
                                    dim_data['ext_line2_point'] = [x_pos, max_pt[1], 0.0]
                                    dim_data['is_horizontal'] = False
                                
                                # 保存边界框信息（调试用）
                                dim_data['bounding_box_min'] = min_pt
                                dim_data['bounding_box_max'] = max_pt
                            except:
                                pass
                        
                        data["elements"]["dimensions"].append(dim_data)

                except Exception as e_ent:
                    # 个别实体失败不影响整体
                    # print(f"跳过实体 {i}: {e_ent}")
                    continue
            
            print(f"提取完成。")
            print(f"  - 直线: {len(data['elements']['lines'])}")
            print(f"  - 圆: {len(data['elements']['circles'])}")
            print(f"  - 圆弧: {len(data['elements']['arcs'])}")
            print(f"  - 多段线: {len(data['elements']['polylines'])}")
            print(f"  - 文字: {len(data['elements']['texts'])}")
            
            return data

        except Exception as e:
            print(f"提取过程发生错误: {e}")
            return data
        finally:
            # 清理选择集
            if selection_set:
                try:
                    selection_set.Delete()
                except:
                    pass

    def save_as_template(self, file_path: str):
        """
        将当前图纸内容保存为 JSON 模板文件
        
        Args:
            file_path: 保存路径 (例如 'my_template.json')
        """
        data = self.extract_drawing_data()
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"[OK] 模板已保存至: {file_path}")
        except Exception as e:
            print(f"[ERROR] 保存模板失败: {e}")

    def close(self):
        """关闭连接"""
        try:
            if self.doc:
                print("连接已关闭")
                self.doc = None
                self.acad = None
                self.model_space = None
        except Exception as e:
            print(f"关闭失败: {e}")


if __name__ == "__main__":
    # 示例使用
    cad = AutoCADController()
    
    # 连接到运行中的 AutoCAD
    if cad.connect():
        print("\n开始绘制示例图形...")
        
        # 绘制一个矩形
        cad.draw_rectangle((0, 0), (100, 50))
        
        # 绘制一个圆
        cad.draw_circle((50, 25, 0), 15)
        
        # 添加文字
        cad.add_text("Hello AutoCAD!", (10, 60, 0), 5)
        
        # 缩放到全部显示
        cad.zoom_extents()
        
        # 获取图层信息
        layers = cad.get_all_layers()
        print(f"图层列表: {layers}")
        
        # 获取实体数量
        cad.get_entity_count()
        
        print("\n绘制完成！")

