"""
AutoCAD V2 参数化模板

标准件模板系统，支持：
- 参数化定义
- 预设规格
- JSON 数据生成
"""

from .base import ParametricTemplate
from .registry import TemplateRegistry

__all__ = ["ParametricTemplate", "TemplateRegistry"]
