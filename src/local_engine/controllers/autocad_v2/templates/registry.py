"""
模板注册表
"""

from typing import Dict, Type, List, Any, Optional
import logging

from .base import ParametricTemplate

logger = logging.getLogger(__name__)


class TemplateRegistry:
    """
    模板注册表（单例）
    
    负责：
    1. 注册和管理所有参数化模板
    2. 提供模板查询接口
    """
    
    _templates: Dict[str, Type[ParametricTemplate]] = {}
    
    @classmethod
    def register(cls, name: str = None):
        """
        装饰器：注册模板
        
        用法:
            @TemplateRegistry.register("flange")
            class FlangeTemplate(ParametricTemplate):
                ...
        
        或者不传参数，使用类的 get_name() 方法:
            @TemplateRegistry.register()
            class FlangeTemplate(ParametricTemplate):
                ...
        """
        def decorator(template_class: Type[ParametricTemplate]):
            template_name = name or template_class.get_name()
            cls._templates[template_name] = template_class
            logger.info(f"[TemplateRegistry] Registered template: {template_name}")
            return template_class
        return decorator
    
    @classmethod
    def get(cls, name: str) -> Optional[Type[ParametricTemplate]]:
        """获取模板类"""
        return cls._templates.get(name)
    
    @classmethod
    def list_all(cls) -> List[Dict[str, Any]]:
        """
        列出所有模板及其信息
        
        Returns:
            [
                {
                    "type": "flange",
                    "description": "法兰盘",
                    "parameters": {...schema...},
                    "presets": ["DN50", "DN100", ...]
                },
                ...
            ]
        """
        result = []
        for name, template_class in cls._templates.items():
            try:
                result.append({
                    "type": name,
                    "description": template_class.get_description(),
                    "parameters": template_class.get_parameters_schema(),
                    "presets": list(template_class.get_presets().keys())
                })
            except Exception as e:
                logger.warning(f"[TemplateRegistry] Error getting info for {name}: {e}")
        return result
    
    @classmethod
    def get_names(cls) -> List[str]:
        """获取所有模板名称"""
        return list(cls._templates.keys())


# 自动导入并注册模板
def _auto_register_templates():
    """自动导入模板模块"""
    try:
        from . import mechanical
        from . import hydraulic
        logger.info(f"[TemplateRegistry] Templates registered: {list(TemplateRegistry._templates.keys())}")
    except ImportError as e:
        logger.warning(f"[TemplateRegistry] Failed to import templates: {e}")


# 模块加载时自动注册模板
_auto_register_templates()
