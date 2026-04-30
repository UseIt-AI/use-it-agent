"""
Human-in-the-Loop Node Adapter - 将 HITL Handler 适配为 V2 接口

TODO: 实现完整的 Human-in-the-loop 节点适配器
目前这是一个占位文件，等待后续实现。
"""

from __future__ import annotations

from typing import Dict, Any, List, AsyncGenerator

from useit_studio.ai_run.node_handler.base_v2 import (
    BaseNodeHandlerV2,
    NodeContext,
    NodeCompleteEvent,
    ErrorEvent,
)
from useit_studio.ai_run.utils.logger_utils import LoggerUtils


logger = LoggerUtils(component_name="HumanInTheLoopAdapter")


class HumanInTheLoopAdapter(BaseNodeHandlerV2):
    """
    Human-in-the-Loop 节点适配器
    
    将现有的 HumanInTheLoopNodeHandler 适配为 V2 接口。
    """
    
    @classmethod
    def supported_types(cls) -> List[str]:
        return ["human-in-the-loop"]
    
    async def execute(self, ctx: NodeContext) -> AsyncGenerator[Dict[str, Any], None]:
        """执行 Human-in-the-Loop 节点"""
        try:
            from useit_studio.ai_run.node_handler.functional_nodes.human_in_the_loop.human_in_the_loop import HumanInTheLoopNodeHandler
            from useit_studio.ai_run.node_handler.functional_nodes.computer_use.gui.planner import FlowLogicPlanner
            
            # 创建 handler
            handler = HumanInTheLoopNodeHandler(
                logger=ctx.flow_processor.logger,
                graph_manager=ctx.flow_processor.graph_manager,
                workflow_id=ctx.flow_processor.workflow_id,
                logging_dir=ctx.log_folder,
            )
            
            # 创建 planner
            planner = FlowLogicPlanner(
                model=ctx.planner_model,
                api_keys=ctx.planner_api_keys or {}
            )
            
            # 调用 handler（HITL handler 是异步的）
            result = await handler.handle(
                planner=planner,
                current_node=ctx.node_dict,
                current_state=ctx.node_state,
                screenshot_path=ctx.screenshot_path,
                query=ctx.query,
                history_md=ctx.history_md,
            )
            
            # 转换为 NodeCompleteEvent
            yield NodeCompleteEvent(
                node_id=ctx.node_id,
                node_type=ctx.node_type,
                is_node_completed=result.get("is_node_completed", True),
                handler_result=result,
                chosen_branch_id=result.get("chosen_branch_id"),
                action_summary=result.get("Action", ""),
                node_completion_summary=result.get("node_completion_summary", ""),
            ).to_dict()
            
        except Exception as e:
            logger.logger.error(f"HumanInTheLoopAdapter error: {e}", exc_info=True)
            yield ErrorEvent(message=str(e), node_id=ctx.node_id).to_dict()
