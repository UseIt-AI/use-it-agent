"""
螺栓参数化模板
"""

from typing import Dict, Any, List
import math

from ..base import ParametricTemplate
from ..registry import TemplateRegistry


@TemplateRegistry.register("bolt")
class BoltTemplate(ParametricTemplate):
    """
    螺栓参数化模板
    
    绘制螺栓的侧视图，包括：
    - 螺栓头
    - 螺杆
    - 螺纹区域
    - 尺寸标注
    """
    
    # 预设规格（GB/T 5782 六角头螺栓）
    PRESETS = {
        "M6": {
            "nominal_diameter": 6,
            "head_height": 4,
            "head_width": 10,
            "shank_length": 20,
            "thread_length": 18
        },
        "M8": {
            "nominal_diameter": 8,
            "head_height": 5.3,
            "head_width": 13,
            "shank_length": 25,
            "thread_length": 22
        },
        "M10": {
            "nominal_diameter": 10,
            "head_height": 6.4,
            "head_width": 17,
            "shank_length": 30,
            "thread_length": 26
        },
        "M12": {
            "nominal_diameter": 12,
            "head_height": 7.5,
            "head_width": 19,
            "shank_length": 35,
            "thread_length": 30
        },
        "M16": {
            "nominal_diameter": 16,
            "head_height": 10,
            "head_width": 24,
            "shank_length": 45,
            "thread_length": 38
        },
        "M20": {
            "nominal_diameter": 20,
            "head_height": 12.5,
            "head_width": 30,
            "shank_length": 55,
            "thread_length": 46
        }
    }
    
    def __init__(
        self,
        nominal_diameter: float = 10,
        head_height: float = 6.4,
        head_width: float = 17,
        shank_length: float = 30,
        thread_length: float = 26,
        show_thread: bool = True,
        show_dimensions: bool = True,
        dim_text_height: float = 2.5
    ):
        """
        初始化螺栓模板
        
        Args:
            nominal_diameter: 公称直径 (mm)
            head_height: 头部高度 (mm)
            head_width: 头部宽度（对边距离）(mm)
            shank_length: 螺杆长度 (mm)
            thread_length: 螺纹长度 (mm)
            show_thread: 是否显示螺纹线
            show_dimensions: 是否显示标注
            dim_text_height: 标注文字高度
        """
        self.nominal_diameter = nominal_diameter
        self.head_height = head_height
        self.head_width = head_width
        self.shank_length = shank_length
        self.thread_length = thread_length
        self.show_thread = show_thread
        self.show_dimensions = show_dimensions
        self.dim_text_height = dim_text_height
    
    @classmethod
    def get_name(cls) -> str:
        return "bolt"
    
    @classmethod
    def get_description(cls) -> str:
        return "六角头螺栓 - GB/T 5782"
    
    @classmethod
    def get_parameters_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "nominal_diameter": {
                    "type": "number",
                    "description": "公称直径 (mm)",
                    "default": 10,
                    "enum": [6, 8, 10, 12, 16, 20, 24, 30]
                },
                "shank_length": {
                    "type": "number",
                    "description": "螺杆长度 (mm)",
                    "default": 30,
                    "minimum": 10,
                    "maximum": 300
                },
                "show_thread": {
                    "type": "boolean",
                    "description": "是否显示螺纹线",
                    "default": True
                },
                "show_dimensions": {
                    "type": "boolean",
                    "description": "是否显示标注",
                    "default": True
                }
            },
            "required": ["nominal_diameter", "shank_length"]
        }
    
    @classmethod
    def get_presets(cls) -> Dict[str, Dict[str, Any]]:
        return cls.PRESETS
    
    def validate(self) -> List[str]:
        errors = []
        
        if self.nominal_diameter <= 0:
            errors.append("公称直径必须大于0")
        
        if self.shank_length <= 0:
            errors.append("螺杆长度必须大于0")
        
        if self.thread_length > self.shank_length:
            errors.append("螺纹长度不能大于螺杆长度")
        
        if self.head_height <= 0:
            errors.append("头部高度必须大于0")
        
        return errors
    
    def get_parameters(self) -> Dict[str, Any]:
        return {
            "nominal_diameter": self.nominal_diameter,
            "head_height": self.head_height,
            "head_width": self.head_width,
            "shank_length": self.shank_length,
            "thread_length": self.thread_length,
            "show_thread": self.show_thread,
            "show_dimensions": self.show_dimensions,
            "dim_text_height": self.dim_text_height
        }
    
    def generate(self) -> Dict[str, Any]:
        """生成螺栓 JSON 数据（侧视图）"""
        
        elements = {
            "lines": [],
            "circles": [],
            "arcs": [],
            "polylines": [],
            "texts": [],
            "dimensions": []
        }
        
        d = self.nominal_diameter
        h = self.head_height
        s = self.head_width
        l = self.shank_length
        lt = self.thread_length
        
        # 螺栓头部（矩形）
        # 左上
        elements["lines"].append({
            "start": [-s/2, 0, 0],
            "end": [-s/2, h, 0],
            "layer": "轮廓",
            "color": 256
        })
        # 上边
        elements["lines"].append({
            "start": [-s/2, h, 0],
            "end": [s/2, h, 0],
            "layer": "轮廓",
            "color": 256
        })
        # 右边
        elements["lines"].append({
            "start": [s/2, h, 0],
            "end": [s/2, 0, 0],
            "layer": "轮廓",
            "color": 256
        })
        
        # 螺杆（矩形）
        # 左边
        elements["lines"].append({
            "start": [-d/2, 0, 0],
            "end": [-d/2, -l, 0],
            "layer": "轮廓",
            "color": 256
        })
        # 底边
        elements["lines"].append({
            "start": [-d/2, -l, 0],
            "end": [d/2, -l, 0],
            "layer": "轮廓",
            "color": 256
        })
        # 右边
        elements["lines"].append({
            "start": [d/2, -l, 0],
            "end": [d/2, 0, 0],
            "layer": "轮廓",
            "color": 256
        })
        
        # 头部与螺杆连接线
        elements["lines"].append({
            "start": [-s/2, 0, 0],
            "end": [-d/2, 0, 0],
            "layer": "轮廓",
            "color": 256
        })
        elements["lines"].append({
            "start": [d/2, 0, 0],
            "end": [s/2, 0, 0],
            "layer": "轮廓",
            "color": 256
        })
        
        # 螺纹区域（细线表示）
        if self.show_thread:
            thread_start = -l + lt
            # 螺纹边界线
            elements["lines"].append({
                "start": [-d/2, thread_start, 0],
                "end": [d/2, thread_start, 0],
                "layer": "螺纹",
                "color": 256
            })
            
            # 简化螺纹表示（几条斜线）
            num_threads = int(lt / (d * 0.5))
            for i in range(num_threads):
                y = -l + i * (lt / num_threads)
                elements["lines"].append({
                    "start": [-d/2, y, 0],
                    "end": [d/2, y + d * 0.3, 0],
                    "layer": "螺纹",
                    "color": 256
                })
        
        # 中心线
        elements["lines"].append({
            "start": [0, h + 5, 0],
            "end": [0, -l - 5, 0],
            "layer": "中心线",
            "color": 256
        })
        
        # 标注
        if self.show_dimensions:
            offset = 15
            
            # 总长度标注
            elements["dimensions"].append({
                "type": "AcDbAlignedDimension",
                "ext_line1_point": [-s/2 - offset, h, 0],
                "ext_line2_point": [-s/2 - offset, -l, 0],
                "text_position": [-s/2 - offset - 10, (h - l) / 2, 0],
                "measurement": h + l,
                "layer": "标注",
                "color": 256
            })
            
            # 直径标注
            elements["texts"].append({
                "text": f"M{int(d)}",
                "position": [d/2 + 5, -l/2, 0],
                "height": self.dim_text_height,
                "layer": "标注",
                "color": 256
            })
            
            # 螺杆长度标注
            elements["texts"].append({
                "text": f"L={int(l)}",
                "position": [d/2 + 5, -l/2 - self.dim_text_height * 2, 0],
                "height": self.dim_text_height,
                "layer": "标注",
                "color": 256
            })
        
        return {
            "layer_colors": {
                "轮廓": 7,      # 白色
                "螺纹": 8,      # 灰色
                "中心线": 2,   # 黄色
                "标注": 3      # 绿色
            },
            "elements": elements
        }
