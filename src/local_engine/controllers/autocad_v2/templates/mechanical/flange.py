"""
法兰盘参数化模板
"""

from typing import Dict, Any, List
import math

from ..base import ParametricTemplate
from ..registry import TemplateRegistry


@TemplateRegistry.register("flange")
class FlangeTemplate(ParametricTemplate):
    """
    法兰盘参数化模板
    
    用于绘制标准法兰盘的俯视图，包括：
    - 外圆
    - 内圆（管道孔）
    - 螺栓孔
    - 中心线
    - 尺寸标注
    """
    
    # 预设规格（GB/T 9119-2010 PN1.0）
    PRESETS = {
        "DN50": {
            "outer_diameter": 140,
            "inner_diameter": 57,
            "bolt_circle_diameter": 110,
            "bolt_count": 4,
            "bolt_hole_diameter": 14
        },
        "DN80": {
            "outer_diameter": 185,
            "inner_diameter": 89,
            "bolt_circle_diameter": 150,
            "bolt_count": 4,
            "bolt_hole_diameter": 18
        },
        "DN100": {
            "outer_diameter": 210,
            "inner_diameter": 108,
            "bolt_circle_diameter": 170,
            "bolt_count": 8,
            "bolt_hole_diameter": 18
        },
        "DN150": {
            "outer_diameter": 280,
            "inner_diameter": 159,
            "bolt_circle_diameter": 240,
            "bolt_count": 8,
            "bolt_hole_diameter": 22
        },
        "DN200": {
            "outer_diameter": 335,
            "inner_diameter": 219,
            "bolt_circle_diameter": 295,
            "bolt_count": 8,
            "bolt_hole_diameter": 22
        },
        "DN250": {
            "outer_diameter": 390,
            "inner_diameter": 273,
            "bolt_circle_diameter": 350,
            "bolt_count": 12,
            "bolt_hole_diameter": 22
        },
        "DN300": {
            "outer_diameter": 440,
            "inner_diameter": 325,
            "bolt_circle_diameter": 400,
            "bolt_count": 12,
            "bolt_hole_diameter": 22
        }
    }
    
    def __init__(
        self,
        outer_diameter: float = 200,
        inner_diameter: float = 100,
        bolt_circle_diameter: float = 160,
        bolt_count: int = 8,
        bolt_hole_diameter: float = 18,
        show_centerline: bool = True,
        show_dimensions: bool = True,
        dim_text_height: float = 2.5
    ):
        """
        初始化法兰模板
        
        Args:
            outer_diameter: 外径 (mm)
            inner_diameter: 内径 (mm)
            bolt_circle_diameter: 螺栓圆直径 (mm)
            bolt_count: 螺栓数量
            bolt_hole_diameter: 螺栓孔直径 (mm)
            show_centerline: 是否显示中心线
            show_dimensions: 是否显示标注
            dim_text_height: 标注文字高度
        """
        self.outer_diameter = outer_diameter
        self.inner_diameter = inner_diameter
        self.bolt_circle_diameter = bolt_circle_diameter
        self.bolt_count = bolt_count
        self.bolt_hole_diameter = bolt_hole_diameter
        self.show_centerline = show_centerline
        self.show_dimensions = show_dimensions
        self.dim_text_height = dim_text_height
    
    @classmethod
    def get_name(cls) -> str:
        return "flange"
    
    @classmethod
    def get_description(cls) -> str:
        return "法兰盘 - 管道连接用标准法兰"
    
    @classmethod
    def get_parameters_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "outer_diameter": {
                    "type": "number",
                    "description": "外径 (mm)",
                    "default": 200,
                    "minimum": 50,
                    "maximum": 2000
                },
                "inner_diameter": {
                    "type": "number",
                    "description": "内径 (mm)",
                    "default": 100,
                    "minimum": 20,
                    "maximum": 1900
                },
                "bolt_circle_diameter": {
                    "type": "number",
                    "description": "螺栓圆直径 (mm)",
                    "default": 160
                },
                "bolt_count": {
                    "type": "integer",
                    "description": "螺栓数量",
                    "default": 8,
                    "enum": [4, 6, 8, 12, 16, 20, 24]
                },
                "bolt_hole_diameter": {
                    "type": "number",
                    "description": "螺栓孔直径 (mm)",
                    "default": 18
                },
                "show_centerline": {
                    "type": "boolean",
                    "description": "是否显示中心线",
                    "default": True
                },
                "show_dimensions": {
                    "type": "boolean",
                    "description": "是否显示标注",
                    "default": True
                }
            },
            "required": ["outer_diameter", "inner_diameter"]
        }
    
    @classmethod
    def get_presets(cls) -> Dict[str, Dict[str, Any]]:
        return cls.PRESETS
    
    def validate(self) -> List[str]:
        errors = []
        
        if self.inner_diameter >= self.outer_diameter:
            errors.append("内径必须小于外径")
        
        if self.bolt_circle_diameter <= self.inner_diameter:
            errors.append("螺栓圆直径必须大于内径")
        
        if self.bolt_circle_diameter >= self.outer_diameter:
            errors.append("螺栓圆直径必须小于外径")
        
        if self.bolt_hole_diameter >= (self.outer_diameter - self.bolt_circle_diameter) / 2:
            errors.append("螺栓孔直径过大")
        
        if self.bolt_count < 4:
            errors.append("螺栓数量至少为4")
        
        return errors
    
    def get_parameters(self) -> Dict[str, Any]:
        return {
            "outer_diameter": self.outer_diameter,
            "inner_diameter": self.inner_diameter,
            "bolt_circle_diameter": self.bolt_circle_diameter,
            "bolt_count": self.bolt_count,
            "bolt_hole_diameter": self.bolt_hole_diameter,
            "show_centerline": self.show_centerline,
            "show_dimensions": self.show_dimensions,
            "dim_text_height": self.dim_text_height
        }
    
    def generate(self) -> Dict[str, Any]:
        """生成法兰盘 JSON 数据"""
        
        elements = {
            "lines": [],
            "circles": [],
            "arcs": [],
            "polylines": [],
            "texts": [],
            "dimensions": []
        }
        
        R_outer = self.outer_diameter / 2
        R_inner = self.inner_diameter / 2
        R_bolt = self.bolt_circle_diameter / 2
        R_hole = self.bolt_hole_diameter / 2
        
        # 1. 外圆
        elements["circles"].append({
            "center": [0, 0, 0],
            "radius": R_outer,
            "layer": "轮廓",
            "color": 256
        })
        
        # 2. 内圆
        elements["circles"].append({
            "center": [0, 0, 0],
            "radius": R_inner,
            "layer": "轮廓",
            "color": 256
        })
        
        # 3. 螺栓孔
        angle_step = 360 / self.bolt_count
        for i in range(self.bolt_count):
            angle_rad = math.radians(i * angle_step)
            cx = R_bolt * math.cos(angle_rad)
            cy = R_bolt * math.sin(angle_rad)
            elements["circles"].append({
                "center": [cx, cy, 0],
                "radius": R_hole,
                "layer": "螺栓孔",
                "color": 256
            })
        
        # 4. 中心线
        if self.show_centerline:
            extend = 10  # 中心线延伸长度
            
            # 水平中心线
            elements["lines"].append({
                "start": [-R_outer - extend, 0, 0],
                "end": [R_outer + extend, 0, 0],
                "layer": "中心线",
                "color": 256
            })
            
            # 垂直中心线
            elements["lines"].append({
                "start": [0, -R_outer - extend, 0],
                "end": [0, R_outer + extend, 0],
                "layer": "中心线",
                "color": 256
            })
        
        # 5. 标注
        if self.show_dimensions:
            offset = 20  # 标注偏移
            
            # 外径标注
            elements["dimensions"].append({
                "type": "AcDbDiametricDimension",
                "measurement": self.outer_diameter,
                "text_position": [R_outer + offset, offset, 0],
                "text_override": f"Φ{int(self.outer_diameter)}",
                "layer": "标注",
                "color": 256
            })
            
            # 内径标注
            elements["dimensions"].append({
                "type": "AcDbDiametricDimension",
                "measurement": self.inner_diameter,
                "text_position": [R_inner + offset, -offset, 0],
                "text_override": f"Φ{int(self.inner_diameter)}",
                "layer": "标注",
                "color": 256
            })
            
            # 螺栓圆标注
            elements["texts"].append({
                "text": f"PCD Φ{int(self.bolt_circle_diameter)}",
                "position": [R_bolt + offset, R_bolt, 0],
                "height": self.dim_text_height,
                "layer": "标注",
                "color": 256
            })
            
            # 螺栓孔标注
            elements["texts"].append({
                "text": f"{self.bolt_count}-Φ{int(self.bolt_hole_diameter)}",
                "position": [R_bolt + offset, R_bolt - self.dim_text_height * 2, 0],
                "height": self.dim_text_height,
                "layer": "标注",
                "color": 256
            })
        
        return {
            "layer_colors": {
                "轮廓": 7,      # 白色
                "螺栓孔": 1,    # 红色
                "中心线": 2,   # 黄色
                "标注": 3      # 绿色
            },
            "elements": elements
        }
