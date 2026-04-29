"""
Loop End Node Handler V2 - 循环结束节点处理器

处理 loop-end 类型节点，决定是否继续循环。
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

from .models import (
    LoopIterationEvent,
    LoopCompleteEvent,
)
from .core import LoopEndEvaluator


logger = LoggerUtils(component_name="LoopEndNodeHandlerV2")


class LoopEndNodeHandlerV2(BaseNodeHandlerV2):
    """
    Loop End 节点处理器 V2
    
    处理 loop-end 类型节点，决定是否继续循环。
    """
    
    @classmethod
    def supported_types(cls) -> List[str]:
        return ["loop-end"]
    
    async def execute(self, ctx: NodeContext) -> AsyncGenerator[Dict[str, Any], None]:
        """执行 Loop End 节点"""
        logger.logger.info(f"[LoopEndNodeHandlerV2] Starting loop-end node: {ctx.node_id}")
        
        try:
            node_data = ctx.node_dict.get("data", {})
            parent_loop_id = ctx.node_dict.get("parentId") or ctx.node_dict.get("parentNode")
            
            logger.logger.info(
                f"[LoopEndNodeHandlerV2] parent_loop_id={parent_loop_id}, "
                f"node_dict keys={list(ctx.node_dict.keys())}"
            )
            
            # 获取循环信息
            loop_node = None
            max_iterations = 5
            
            if ctx.flow_processor and parent_loop_id:
                loop_node = ctx.flow_processor.graph_manager.get_milestone_by_id(parent_loop_id)
                if loop_node:
                    max_iterations = loop_node.get("data", {}).get("max_iteration", 5)
            
            # 获取迭代计划和当前迭代
            iteration_plan = []
            current_iteration = ctx.node_state.get("iteration", 0)
            
            if ctx.flow_processor and parent_loop_id:
                node_states = ctx.flow_processor.node_states
                loop_state = node_states.get(parent_loop_id, {})
                iteration_plan = loop_state.get("iteration_plan", [])
                current_iteration = loop_state.get("iteration", current_iteration)
                
                logger.logger.info(
                    f"[LoopEndNodeHandlerV2] node_states keys={list(node_states.keys())}, "
                    f"loop_state={loop_state}, "
                    f"iteration_plan length={len(iteration_plan)}, "
                    f"current_iteration={current_iteration}"
                )
            
            # 评估是否继续循环
            evaluator = LoopEndEvaluator()
            decision = evaluator.evaluate(
                loop_id=parent_loop_id or ctx.node_id,
                current_iteration=current_iteration,
                iteration_plan=iteration_plan,
                max_iterations=max_iterations,
            )
            
            logger.logger.info(
                f"[LoopEndNodeHandlerV2] Decision: should_continue={decision.should_continue}, "
                f"iteration={current_iteration}/{decision.total_subtasks}"
            )
            
            # 更新状态
            if ctx.flow_processor and parent_loop_id:
                node_states = ctx.flow_processor.node_states
                # 注意：node_states[loop_id] 返回的是 internal_state 的副本，
                # 必须使用 node_states[loop_id] = {...} 来触发 __setitem__
                
                # 获取当前状态
                current_state = node_states.get(parent_loop_id, {})
                
                if decision.should_continue:
                    # 增加迭代计数 - 保留其他状态（如 iteration_plan）
                    current_state["iteration"] = current_iteration + 1
                    current_state["current_subtask_index"] = current_iteration + 1
                else:
                    # 标记完成
                    current_state["iteration"] = decision.total_subtasks
                    current_state["completed"] = True
                
                # 使用 __setitem__ 更新状态
                node_states[parent_loop_id] = current_state
            
            # 发送事件
            if decision.should_continue:
                yield LoopIterationEvent(
                    loop_id=parent_loop_id or ctx.node_id,
                    iteration=current_iteration + 1,
                    total=decision.total_subtasks,
                    subtask=f"Continuing to iteration {current_iteration + 2}",
                ).to_dict()
            else:
                yield LoopCompleteEvent(
                    loop_id=parent_loop_id or ctx.node_id,
                    total_iterations=decision.total_subtasks,
                    summary=decision.observation,
                ).to_dict()
            
            # 发送 node_complete 事件
            yield NodeCompleteEvent(
                node_id=ctx.node_id,
                node_type=ctx.node_type,
                is_node_completed=True,
                handler_result={
                    "Observation": decision.observation,
                    "Reasoning": decision.reasoning,
                    "Action": decision.action,
                    "is_node_completed": True,
                    "current_state": ctx.node_state,
                    "break_loop": not decision.should_continue,
                },
                break_loop=not decision.should_continue,
                action_summary="Loop End",
                node_completion_summary=decision.action,
            ).to_dict()
            
        except Exception as e:
            error_msg = f"Loop end node execution failed: {str(e)}"
            logger.logger.error(error_msg, exc_info=True)
            yield ErrorEvent(message=error_msg, node_id=ctx.node_id).to_dict()


__all__ = ["LoopEndNodeHandlerV2"]
