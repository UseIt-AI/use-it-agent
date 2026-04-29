"""
U型渠参数化模板
"""

from typing import Dict, Any, List

from ..base import ParametricTemplate
from ..registry import TemplateRegistry


@TemplateRegistry.register("u_channel")
class UChannelTemplate(ParametricTemplate):
    """
    U型渠参数化模板
    
    用于绘制 U 型灌溉渠道的横断面图，包括：
    - 渠道轮廓
    - 壁厚
    - 底板
    - 尺寸标注
    """
    
    # 预设规格
    PRESETS = {
        "U30": {
            "width": 300,
            "height": 300,
            "wall_thickness": 50,
            "bottom_thickness": 60
        },
        "U40": {
            "width": 400,
            "height": 400,
            "wall_thickness": 60,
            "bottom_thickness": 70
        },
        "U50": {
            "width": 500,
            "height": 500,
            "wall_thickness": 70,
            "bottom_thickness": 80
        },
        "U60": {
            "width": 600,
            "height": 550,
            "wall_thickness": 80,
            "bottom_thickness": 90
        },
        "U80": {
            "width": 800,
            "height": 700,
            "wall_thickness": 100,
            "bottom_thickness": 110
        },
        "U100": {
            "width": 1000,
            "height": 800,
            "wall_thickness": 120,
            "bottom_thickness": 130
        }
    }
    
    def __init__(
        self,
        width: float = 500,
        height: float = 500,
        wall_thickness: float = 70,
        bottom_thickness: float = 80,
        show_dimensions: bool = True,
        show_hatch: bool = False,
        dim_text_height: float = 2.5,
        dim_offset: float = 15
    ):
        """
        初始化 U 型渠模板
        
        Args:
            width: 渠道内宽 (mm)
            height: 渠道内高 (mm)
            wall_thickness: 壁厚 (mm)
            bottom_thickness: 底板厚度 (mm)
            show_dimensions: 是否显示标注
            show_hatch: 是否显示填充（混凝土）
            dim_text_height: 标注文字高度
            dim_offset: 标注偏移距离
        """
        self.width = width
        self.height = height
        self.wall_thickness = wall_thickness
        self.bottom_thickness = bottom_thickness
        self.show_dimensions = show_dimensions
        self.show_hatch = show_hatch
        self.dim_text_height = dim_text_height
        self.dim_offset = dim_offset
    
    @classmethod
    def get_name(cls) -> str:
        return "u_channel"
    
    @classmethod
    def get_description(cls) -> str:
        return "U型渠 - 灌溉渠道横断面"
    
    @classmethod
    def get_parameters_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "width": {
                    "type": "number",
                    "description": "渠道内宽 (mm)",
                    "default": 500,
                    "minimum": 100,
                    "maximum": 3000
                },
                "height": {
                    "type": "number",
                    "description": "渠道内高 (mm)",
                    "default": 500,
                    "minimum": 100,
                    "maximum": 2000
                },
                "wall_thickness": {
                    "type": "number",
                    "description": "壁厚 (mm)",
                    "default": 70,
                    "minimum": 30,
                    "maximum": 300
                },
                "bottom_thickness": {
                    "type": "number",
                    "description": "底板厚度 (mm)",
                    "default": 80,
                    "minimum": 40,
                    "maximum": 400
                },
                "show_dimensions": {
                    "type": "boolean",
                    "description": "是否显示标注",
                    "default": True
                },
                "show_hatch": {
                    "type": "boolean",
                    "description": "是否显示填充",
                    "default": False
                }
            },
            "required": ["width", "height"]
        }
    
    @classmethod
    def get_presets(cls) -> Dict[str, Dict[str, Any]]:
        return cls.PRESETS
    
    def validate(self) -> List[str]:
        errors = []
        
        if self.width <= 0:
            errors.append("渠道宽度必须大于0")
        
        if self.height <= 0:
            errors.append("渠道高度必须大于0")
        
        if self.wall_thickness <= 0:
            errors.append("壁厚必须大于0")
        
        if self.bottom_thickness <= 0:
            errors.append("底板厚度必须大于0")
        
        if self.wall_thickness > self.width / 2:
            errors.append("壁厚不能超过渠道宽度的一半")
        
        return errors
    
    def get_parameters(self) -> Dict[str, Any]:
        return {
            "width": self.width,
            "height": self.height,
            "wall_thickness": self.wall_thickness,
            "bottom_thickness": self.bottom_thickness,
            "show_dimensions": self.show_dimensions,
            "show_hatch": self.show_hatch,
            "dim_text_height": self.dim_text_height,
            "dim_offset": self.dim_offset
        }
    
    def generate(self) -> Dict[str, Any]:
        """生成 U 型渠 JSON 数据（横断面）"""
        
        elements = {
            "lines": [],
            "circles": [],
            "arcs": [],
            "polylines": [],
            "texts": [],
            "dimensions": []
        }
        
        W = self.width
        H = self.height
        T = self.wall_thickness
        B = self.bottom_thickness
        
        # 计算关键点
        # 外轮廓
        outer_total_width = W + 2 * T
        outer_total_height = H + B
        
        # 外轮廓点（从左下角开始，顺时针）
        outer_points = [
            (0, 0),                         # 左下
            (outer_total_width, 0),         # 右下
            (outer_total_width, outer_total_height),  # 右上
            (outer_total_width - T, outer_total_height),  # 右内上
            (outer_total_width - T, B),     # 右内下
            (T, B),                         # 左内下
            (T, outer_total_height),        # 左内上
            (0, outer_total_height),        # 左上
        ]
        
        # 绘制外轮廓
        for i in range(len(outer_points)):
            start = outer_points[i]
            end = outer_points[(i + 1) % len(outer_points)]
            elements["lines"].append({
                "start": [start[0], start[1], 0],
                "end": [end[0], end[1], 0],
                "layer": "轮廓",
                "color": 256
            })
        
        # 中心线
        center_x = outer_total_width / 2
        elements["lines"].append({
            "start": [center_x, -10, 0],
            "end": [center_x, outer_total_height + 10, 0],
            "layer": "中心线",
            "color": 256
        })
        
        # 标注
        if self.show_dimensions:
            offset = self.dim_offset
            
            # 内宽标注
            elements["dimensions"].append({
                "type": "AcDbAlignedDimension",
                "ext_line1_point": [T, B, 0],
                "ext_line2_point": [T + W, B, 0],
                "text_position": [center_x, B + offset, 0],
                "measurement": W,
                "layer": "标注",
                "color": 256
            })
            
            # 内高标注
            elements["dimensions"].append({
                "type": "AcDbAlignedDimension",
                "ext_line1_point": [T + W + offset, B, 0],
                "ext_line2_point": [T + W + offset, outer_total_height, 0],
                "text_position": [T + W + offset + 10, B + H/2, 0],
                "measurement": H,
                "layer": "标注",
                "color": 256
            })
            
            # 总宽标注
            elements["dimensions"].append({
                "type": "AcDbAlignedDimension",
                "ext_line1_point": [0, -offset, 0],
                "ext_line2_point": [outer_total_width, -offset, 0],
                "text_position": [center_x, -offset - 10, 0],
                "measurement": outer_total_width,
                "layer": "标注",
                "color": 256
            })
            
            # 总高标注
            elements["dimensions"].append({
                "type": "AcDbAlignedDimension",
                "ext_line1_point": [-offset, 0, 0],
                "ext_line2_point": [-offset, outer_total_height, 0],
                "text_position": [-offset - 10, outer_total_height/2, 0],
                "measurement": outer_total_height,
                "layer": "标注",
                "color": 256
            })
            
            # 壁厚标注
            elements["texts"].append({
                "text": f"t={int(T)}",
                "position": [T/2, outer_total_height/2, 0],
                "height": self.dim_text_height,
                "layer": "标注",
                "color": 256
            })
            
            # 底板厚度标注
            elements["texts"].append({
                "text": f"b={int(B)}",
                "position": [center_x, B/2, 0],
                "height": self.dim_text_height,
                "layer": "标注",
                "color": 256
            })
        
        return {
            "layer_colors": {
                "轮廓": 7,      # 白色
                "中心线": 2,   # 黄色
                "标注": 3,     # 绿色
                "填充": 8      # 灰色
            },
            "elements": elements
        }
