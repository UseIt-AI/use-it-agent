"""
参数化模板基类
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional


class ParametricTemplate(ABC):
    """
    参数化模板基类
    
    所有标准件模板必须继承此类并实现核心方法。
    """
    
    @classmethod
    @abstractmethod
    def get_name(cls) -> str:
        """返回模板名称（如 "flange"）"""
        pass
    
    @classmethod
    @abstractmethod
    def get_description(cls) -> str:
        """返回模板描述"""
        pass
    
    @classmethod
    @abstractmethod
    def get_parameters_schema(cls) -> Dict[str, Any]:
        """
        返回参数的 JSON Schema
        
        Returns:
            {
                "type": "object",
                "properties": {
                    "param1": {
                        "type": "number",
                        "description": "参数1说明",
                        "default": 100,
                        "minimum": 10,
                        "maximum": 1000
                    },
                    ...
                },
                "required": ["param1", "param2"]
            }
        """
        pass
    
    @classmethod
    def get_presets(cls) -> Dict[str, Dict[str, Any]]:
        """
        返回预设规格
        
        Returns:
            {
                "DN50": {"outer_diameter": 140, "inner_diameter": 57, ...},
                "DN100": {...},
                ...
            }
        """
        return {}
    
    @classmethod
    def from_preset(cls, preset_name: str) -> "ParametricTemplate":
        """
        从预设规格创建模板实例
        
        Args:
            preset_name: 预设名称（如 "DN200"）
        
        Returns:
            模板实例
        """
        presets = cls.get_presets()
        if preset_name not in presets:
            raise ValueError(f"Unknown preset: {preset_name}. Available: {list(presets.keys())}")
        
        return cls(**presets[preset_name])
    
    @abstractmethod
    def validate(self) -> List[str]:
        """
        验证参数
        
        Returns:
            错误消息列表，空列表表示验证通过
        """
        pass
    
    @abstractmethod
    def get_parameters(self) -> Dict[str, Any]:
        """
        返回当前参数值
        
        Returns:
            参数字典
        """
        pass
    
    @abstractmethod
    def generate(self) -> Dict[str, Any]:
        """
        生成 JSON 图纸数据
        
        Returns:
            {
                "layer_colors": {...},
                "elements": {
                    "lines": [...],
                    "circles": [...],
                    ...
                }
            }
        """
        pass
    
    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典（用于序列化）
        """
        return {
            "name": self.get_name(),
            "description": self.get_description(),
            "parameters": self.get_parameters(),
            "schema": self.get_parameters_schema(),
            "presets": list(self.get_presets().keys())
        }
