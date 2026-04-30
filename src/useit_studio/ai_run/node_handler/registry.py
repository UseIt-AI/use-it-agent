"""
Node Handler Registry - 统一的节点处理器注册表

提供节点类型到 Handler 的映射，支持：
1. 自动注册默认 handlers
2. 运行时动态注册
3. 按 node_type 获取 handler

使用方式：
    # 获取单例
    registry = NodeHandlerRegistry.get_instance()
    
    # 获取 handler
    handler = registry.get_handler("computer-use-gui")
    
    # 注册自定义 handler
    registry.register(MyCustomHandler())
"""

from __future__ import annotations

from typing import Dict, List, Optional, Type
import logging

from .base_v2 import BaseNodeHandlerV2, NodeContext


logger = logging.getLogger(__name__)


class NodeHandlerRegistry:
    """
    节点处理器注册表（单例）
    
    管理所有节点类型到 Handler 的映射。
    """
    
    _instance: Optional["NodeHandlerRegistry"] = None
    _initialized: bool = False
    
    def __init__(self):
        self._handlers: Dict[str, BaseNodeHandlerV2] = {}
        self._handler_classes: Dict[str, Type[BaseNodeHandlerV2]] = {}
    
    @classmethod
    def get_instance(cls) -> "NodeHandlerRegistry":
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        
        # 延迟初始化默认 handlers
        if not cls._initialized:
            cls._instance._register_defaults()
            cls._initialized = True
        
        return cls._instance
    
    @classmethod
    def reset(cls):
        """重置单例（主要用于测试）"""
        cls._instance = None
        cls._initialized = False
    
    def register(self, handler: BaseNodeHandlerV2):
        """
        注册一个 handler 实例
        
        Args:
            handler: Handler 实例
        """
        for node_type in handler.supported_types():
            self._handlers[node_type] = handler
            logger.debug(f"Registered handler for node type: {node_type}")
    
    def register_class(self, handler_class: Type[BaseNodeHandlerV2]):
        """
        注册一个 handler 类（延迟实例化）
        
        Args:
            handler_class: Handler 类
        """
        for node_type in handler_class.supported_types():
            self._handler_classes[node_type] = handler_class
            logger.debug(f"Registered handler class for node type: {node_type}")
    
    def get_handler(self, node_type: str) -> Optional[BaseNodeHandlerV2]:
        """
        获取指定节点类型的 handler
        
        Args:
            node_type: 节点类型
            
        Returns:
            Handler 实例，如果未找到则返回 None
        """
        logger.info(f"[Registry] get_handler called with node_type='{node_type}'")
        logger.info(f"[Registry] Available handlers: {list(self._handlers.keys())}")
        logger.info(f"[Registry] Available handler classes: {list(self._handler_classes.keys())}")
        
        # 优先从实例缓存获取
        if node_type in self._handlers:
            handler = self._handlers[node_type]
            logger.info(f"[Registry] Found handler in cache: {handler.__class__.__name__}")
            return handler
        
        # 尝试从类注册表实例化
        if node_type in self._handler_classes:
            handler = self._handler_classes[node_type]()
            self._handlers[node_type] = handler
            logger.info(f"[Registry] Instantiated handler from class: {handler.__class__.__name__}")
            return handler
        
        logger.warning(f"[Registry] No handler found for node_type='{node_type}'")
        return None
    
    def has_handler(self, node_type: str) -> bool:
        """检查是否有指定节点类型的 handler"""
        return node_type in self._handlers or node_type in self._handler_classes
    
    def get_supported_types(self) -> List[str]:
        """获取所有支持的节点类型"""
        types = set(self._handlers.keys())
        types.update(self._handler_classes.keys())
        return sorted(types)
    
    def _register_defaults(self):
        """仅注册本地开源三节点：start、end、agent（含 agent-node）。"""
        logger.info("Registering local OSS node handlers (start, end, agent)...")
        from .logic_nodes.adapters import StartNodeAdapter, EndNodeAdapter
        from .agent_node.handler import AgentNodeHandler

        self.register(StartNodeAdapter())
        self.register(EndNodeAdapter())
        self.register(AgentNodeHandler())
        logger.info("Registered handlers: %s", self.get_supported_types())


# ==================== 便捷函数 ====================

def get_handler(node_type: str) -> Optional[BaseNodeHandlerV2]:
    """
    便捷函数：获取指定节点类型的 handler
    
    Args:
        node_type: 节点类型
        
    Returns:
        Handler 实例
    """
    return NodeHandlerRegistry.get_instance().get_handler(node_type)


def register_handler(handler: BaseNodeHandlerV2):
    """
    便捷函数：注册一个 handler
    
    Args:
        handler: Handler 实例
    """
    NodeHandlerRegistry.get_instance().register(handler)
