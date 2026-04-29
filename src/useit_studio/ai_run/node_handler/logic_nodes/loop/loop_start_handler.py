"""
Loop Start Node Handler V2 - 循环开始节点处理器

处理 loop-start 类型节点，标记循环迭代的开始。
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

from .models import LoopIterationEvent


logger = LoggerUtils(component_name="LoopStartNodeHandlerV2")


class LoopStartNodeHandlerV2(BaseNodeHandlerV2):
    """
    Loop Start 节点处理器 V2
    
    处理 loop-start 类型节点，标记循环迭代的开始。
    """
    
    @classmethod
    def supported_types(cls) -> List[str]:
        return ["loop-start"]
    
    async def execute(self, ctx: NodeContext) -> AsyncGenerator[Dict[str, Any], None]:
        """执行 Loop Start 节点"""
        logger.logger.info(f"[LoopStartNodeHandlerV2] Starting loop-start node: {ctx.node_id}")
        
        try:
            node_data = ctx.node_dict.get("data", {})
            loop_id = node_data.get("loop_id") or ctx.node_dict.get("parentId") or ctx.node_dict.get("parentNode")
            
            logger.logger.info(
                f"[LoopStartNodeHandlerV2] loop_id={loop_id}, "
                f"node_dict keys={list(ctx.node_dict.keys())}, "
                f"parentId={ctx.node_dict.get('parentId')}, "
                f"parentNode={ctx.node_dict.get('parentNode')}"
            )
            
            # 获取当前迭代信息
            current_iteration = ctx.node_state.get("iteration", 0)
            iteration_plan = []
            
            if ctx.flow_processor and loop_id:
                node_states = ctx.flow_processor.node_states
                loop_state = node_states.get(loop_id, {})
                iteration_plan = loop_state.get("iteration_plan", [])
                current_iteration = loop_state.get("iteration", 0)
                
                logger.logger.info(
                    f"[LoopStartNodeHandlerV2] node_states keys={list(node_states.keys())}, "
                    f"loop_state={loop_state}, "
                    f"iteration_plan={iteration_plan[:3] if iteration_plan else []}, "
                    f"current_iteration={current_iteration}"
                )
            
            # 获取当前子任务
            current_subtask = ""
            if iteration_plan and current_iteration < len(iteration_plan):
                current_subtask = iteration_plan[current_iteration]
            
            # 发送迭代事件
            yield LoopIterationEvent(
                loop_id=loop_id or ctx.node_id,
                iteration=current_iteration + 1,
                total=len(iteration_plan) if iteration_plan else ctx.node_state.get(f"{loop_id}_max_iterations", 5),
                subtask=current_subtask,
            ).to_dict()
            
            # 构建摘要
            if current_subtask:
                summary = f"Starting iteration {current_iteration + 1}: {current_subtask}"
            else:
                summary = f"Starting loop iteration {current_iteration + 1}"
            
            # 发送 node_complete 事件
            yield NodeCompleteEvent(
                node_id=ctx.node_id,
                node_type=ctx.node_type,
                is_node_completed=True,
                handler_result={
                    "Observation": "",
                    "Reasoning": "",
                    "Action": "Starting a new loop iteration.",
                    "is_node_completed": True,
                    "current_state": ctx.node_state,
                },
                action_summary="Loop Start",
                node_completion_summary=summary,
            ).to_dict()
            
        except Exception as e:
            error_msg = f"Loop start node execution failed: {str(e)}"
            logger.logger.error(error_msg, exc_info=True)
            yield ErrorEvent(message=error_msg, node_id=ctx.node_id).to_dict()


__all__ = ["LoopStartNodeHandlerV2"]
