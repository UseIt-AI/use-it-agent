"""
Logic Node Adapters - 将旧的 Logic Handler 适配为新的 V2 接口

这些适配器让现有的 Logic 节点 Handler 可以在新架构中使用，
无需修改原有代码。

适配策略：
1. 同步 handler -> 直接调用，包装结果
2. 异步 handler -> await 调用，包装结果
3. 统一输出 NodeCompleteEvent 格式

注意：Loop 相关节点已迁移到新架构，直接使用 V2 Handler。
"""

from __future__ import annotations

from typing import Dict, Any, List, AsyncGenerator, Optional
import asyncio

from useit_studio.ai_run.node_handler.base_v2 import (
    BaseNodeHandlerV2,
    NodeContext,
    NodeCompleteEvent,
    ErrorEvent,
)
from useit_studio.ai_run.utils.logger_utils import LoggerUtils

# 导入新的 Loop Handler V2
from useit_studio.ai_run.node_handler.logic_nodes.loop import (
    LoopNodeHandlerV2,
    LoopStartNodeHandlerV2,
    LoopEndNodeHandlerV2,
)


logger = LoggerUtils(component_name="LogicNodeAdapters")


class BaseLegacyAdapter(BaseNodeHandlerV2):
    """
    旧 Logic Handler 的基础适配器
    
    提供通用的适配逻辑：
    1. 创建旧 handler 实例
    2. 调用旧 handler 的 handle 方法
    3. 将结果转换为 NodeCompleteEvent
    """
    
    # 子类需要覆盖这些
    LEGACY_HANDLER_CLASS = None
    NODE_TYPES: List[str] = []
    
    @classmethod
    def supported_types(cls) -> List[str]:
        return cls.NODE_TYPES
    
    def _create_legacy_handler(self, ctx: NodeContext):
        """创建旧 handler 实例"""
        if self.LEGACY_HANDLER_CLASS is None:
            raise NotImplementedError("LEGACY_HANDLER_CLASS must be set")
        
        return self.LEGACY_HANDLER_CLASS(
            logger=ctx.flow_processor.logger,
            graph_manager=ctx.flow_processor.graph_manager,
            workflow_id=ctx.flow_processor.workflow_id,
            logging_dir=ctx.log_folder,
        )
    
    def _create_planner(self, ctx: NodeContext):
        """创建 Planner 实例（某些 Logic 节点需要）"""
        from useit_studio.ai_run.node_handler.functional_nodes.computer_use.gui.planner import FlowLogicPlanner
        return FlowLogicPlanner(
            model=ctx.planner_model,
            api_keys=ctx.planner_api_keys or {}
        )
    
    def _convert_result_to_event(
        self,
        ctx: NodeContext,
        result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """将旧 handler 的结果转换为 NodeCompleteEvent"""
        return NodeCompleteEvent(
            node_id=ctx.node_id,
            node_type=ctx.node_type,
            is_node_completed=result.get("is_node_completed", True),
            is_workflow_completed=result.get("is_workflow_completed", False),
            handler_result=result,
            chosen_branch_id=result.get("chosen_branch_id"),
            break_loop=result.get("break_loop"),
            next_node_id=result.get("next_node_id"),
            action_summary=result.get("Action", ""),
            node_completion_summary=result.get("node_completion_summary", ""),
        ).to_dict()


class StartNodeAdapter(BaseLegacyAdapter):
    """Start 节点适配器"""
    
    NODE_TYPES = ["start"]
    
    @classmethod
    def supported_types(cls) -> List[str]:
        return cls.NODE_TYPES
    
    async def execute(self, ctx: NodeContext) -> AsyncGenerator[Dict[str, Any], None]:
        """执行 Start 节点"""
        try:
            from useit_studio.ai_run.node_handler.logic_nodes.start import StartNodeHandler
            
            handler = StartNodeHandler(
                logger=ctx.flow_processor.logger,
                graph_manager=ctx.flow_processor.graph_manager,
                workflow_id=ctx.flow_processor.workflow_id,
                logging_dir=ctx.log_folder,
            )
            
            # Start 节点是同步的
            result = handler.handle(
                current_node=ctx.node_dict,
                current_state=ctx.node_state,
            )
            
            yield self._convert_result_to_event(ctx, result)
            
        except Exception as e:
            logger.logger.error(f"StartNodeAdapter error: {e}", exc_info=True)
            yield ErrorEvent(message=str(e), node_id=ctx.node_id).to_dict()


class EndNodeAdapter(BaseLegacyAdapter):
    """End 节点适配器"""
    
    NODE_TYPES = ["end"]
    
    @classmethod
    def supported_types(cls) -> List[str]:
        return cls.NODE_TYPES
    
    async def execute(self, ctx: NodeContext) -> AsyncGenerator[Dict[str, Any], None]:
        """执行 End 节点"""
        try:
            from useit_studio.ai_run.node_handler.logic_nodes.end import EndNodeHandler
            
            handler = EndNodeHandler(
                logger=ctx.flow_processor.logger,
                graph_manager=ctx.flow_processor.graph_manager,
                workflow_id=ctx.flow_processor.workflow_id,
                logging_dir=ctx.log_folder,
            )
            
            # End 节点是同步的
            result = handler.handle(
                current_node=ctx.node_dict,
                current_state=ctx.node_state,
            )
            
            yield self._convert_result_to_event(ctx, result)
            
        except Exception as e:
            logger.logger.error(f"EndNodeAdapter error: {e}", exc_info=True)
            yield ErrorEvent(message=str(e), node_id=ctx.node_id).to_dict()


class IfElseNodeAdapter(BaseLegacyAdapter):
    """If-Else 节点适配器"""
    
    NODE_TYPES = ["if-else"]
    
    @classmethod
    def supported_types(cls) -> List[str]:
        return cls.NODE_TYPES
    
    async def execute(self, ctx: NodeContext) -> AsyncGenerator[Dict[str, Any], None]:
        """执行 If-Else 节点"""
        try:
            from useit_studio.ai_run.node_handler.logic_nodes.if_else import IfElseNodeHandler
            
            handler = IfElseNodeHandler(
                logger=ctx.flow_processor.logger,
                graph_manager=ctx.flow_processor.graph_manager,
                workflow_id=ctx.flow_processor.workflow_id,
                logging_dir=ctx.log_folder,
            )
            
            # 创建 planner
            planner = self._create_planner(ctx)
            
            # If-Else 节点是异步的
            result = await handler.handle(
                planner=planner,
                current_node=ctx.node_dict,
                current_state=ctx.node_state,
                screenshot_path=ctx.screenshot_path,
                query=ctx.query,
            )
            
            yield self._convert_result_to_event(ctx, result)
            
        except Exception as e:
            logger.logger.error(f"IfElseNodeAdapter error: {e}", exc_info=True)
            yield ErrorEvent(message=str(e), node_id=ctx.node_id).to_dict()


class LoopNodeAdapter(LoopNodeHandlerV2):
    """
    Loop 节点适配器
    
    直接继承 LoopNodeHandlerV2，保持向后兼容的类名。
    """
    pass


class LoopStartNodeAdapter(LoopStartNodeHandlerV2):
    """
    Loop-Start 节点适配器
    
    直接继承 LoopStartNodeHandlerV2，保持向后兼容的类名。
    """
    pass


class LoopEndNodeAdapter(LoopEndNodeHandlerV2):
    """
    Loop-End 节点适配器
    
    直接继承 LoopEndNodeHandlerV2，保持向后兼容的类名。
    """
    pass


# ==================== 导出 ====================

__all__ = [
    # Legacy adapters
    "StartNodeAdapter",
    "EndNodeAdapter",
    "IfElseNodeAdapter",
    # Loop adapters (now using V2 handlers directly)
    "LoopNodeAdapter",
    "LoopStartNodeAdapter",
    "LoopEndNodeAdapter",
    # V2 handlers (direct export for convenience)
    "LoopNodeHandlerV2",
    "LoopStartNodeHandlerV2",
    "LoopEndNodeHandlerV2",
]
