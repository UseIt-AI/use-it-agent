"""
Loop Node Handler V2 - 循环容器节点处理器

处理 loop 类型节点，负责：
1. 初始化循环状态
2. 调用 LLM 生成迭代计划
3. 跳转到 loop-start 节点
"""

from __future__ import annotations

import uuid
from typing import Dict, Any, List, AsyncGenerator

from useit_studio.ai_run.node_handler.base_v2 import (
    BaseNodeHandlerV2,
    NodeContext,
    NodeCompleteEvent,
    ErrorEvent,
)
from useit_studio.ai_run.utils.logger_utils import LoggerUtils

from .models import (
    LoopContext,
    LoopPlanningEvent,
)
from .core import (
    LoopPlanner,
    collect_loop_milestone_descriptions,
)


logger = LoggerUtils(component_name="LoopNodeHandlerV2")


class LoopNodeHandlerV2(BaseNodeHandlerV2):
    """
    Loop 节点处理器 V2 - 循环容器节点
    
    处理 loop 类型节点，负责：
    1. 初始化循环状态
    2. 调用 LLM 生成迭代计划
    3. 跳转到 loop-start 节点
    """
    
    @classmethod
    def supported_types(cls) -> List[str]:
        return ["loop"]
    
    async def execute(self, ctx: NodeContext) -> AsyncGenerator[Dict[str, Any], None]:
        """执行 Loop 节点"""
        logger.logger.info(f"[LoopNodeHandlerV2] Starting loop node: {ctx.node_id}")
        
        cua_id = f"loop_{uuid.uuid4().hex[:8]}_{ctx.node_id}"
        
        try:
            node_data = ctx.node_dict.get("data", {})
            loop_id = ctx.node_id
            
            # 发送节点开始事件
            yield {
                "type": "node_start",
                "nodeId": ctx.node_id,
                "title": ctx.get_node_title(),
                "nodeType": ctx.node_type,
            }
            
            # 发送 cua_start 事件
            yield {
                "type": "cua_start",
                "cuaId": cua_id,
                "step": 1,
                "title": "Loop Planning",
                "nodeId": ctx.node_id,
            }
            
            # 创建 Loop 上下文
            loop_context = LoopContext.from_node_dict(
                node_dict=ctx.node_dict,
                node_state=ctx.node_state,
                loop_id=loop_id,
            )
            loop_context.query = ctx.query
            loop_context.history_md = ctx.history_md or ""
            
            # 收集子节点描述
            loop_context.sub_milestone_descriptions = collect_loop_milestone_descriptions(
                graph_manager=ctx.flow_processor.graph_manager,
                loop_id=loop_id,
            )
            
            logger.logger.info(
                f"[LoopNodeHandlerV2] Loop context: goal={loop_context.loop_goal[:50]}..., "
                f"max_iterations={loop_context.max_iterations}, "
                f"sub_milestones={len(loop_context.sub_milestone_descriptions)}"
            )
            
            # 发送规划事件
            yield LoopPlanningEvent(
                loop_id=loop_id,
                message=f"Planning iterations for: {loop_context.loop_goal[:100]}...",
            ).to_dict()
            
            # 创建 Planner 并生成迭代计划
            planner = LoopPlanner(
                model=ctx.planner_model,
                api_keys=ctx.planner_api_keys,
            )
            
            iteration_plan = []
            observation = ""
            reasoning = ""
            
            # 流式生成迭代计划
            planning_error = None
            async for event in planner.plan_streaming(
                context=loop_context,
                screenshot_path=ctx.screenshot_path,
                log_dir=ctx.log_folder,
            ):
                event_type = event.get("type", "")
                
                if event_type == "reasoning_delta":
                    yield {
                        "type": "cua_delta",
                        "cuaId": cua_id,
                        "reasoning": event.get("content", ""),
                        "kind": "loop_planner",
                    }
                
                elif event_type == "plan_complete":
                    content = event.get("content", {})
                    observation = content.get("observation", "")
                    reasoning = content.get("reasoning", "")
                    iteration_plan = content.get("iteration_plan", [])
                
                elif event_type == "error":
                    planning_error = event.get("content", "Unknown planning error")
                    logger.logger.error(f"[LoopNodeHandlerV2] Planning error: {planning_error}")
            
            # 如果规划失败且没有迭代计划，使用默认计划
            if planning_error and not iteration_plan:
                logger.logger.warning(f"[LoopNodeHandlerV2] Using fallback iteration plan due to error: {planning_error}")
                # 尝试从用户查询中推断迭代项
                iteration_plan = [
                    f"Iteration {i + 1}: {loop_context.loop_goal}"
                    for i in range(loop_context.max_iterations)
                ]
                observation = f"Planning failed: {planning_error}. Using default iterations."
                reasoning = "Fallback to default iteration plan."
            
            logger.logger.info(
                f"[LoopNodeHandlerV2] Generated iteration plan with {len(iteration_plan)} subtasks"
            )
            
            # 更新状态
            updated_state = dict(ctx.node_state)
            updated_state["iteration"] = 0
            updated_state["loop_id"] = loop_id
            updated_state[f"{loop_id}_iteration_plan"] = iteration_plan
            updated_state[f"{loop_id}_max_iterations"] = loop_context.max_iterations
            
            # 存储到 node_states
            # 注意：node_states[loop_id] 返回的是 internal_state 的副本，
            # 所以不能用 node_states[loop_id]["key"] = value 的方式设置值。
            # 必须使用 node_states[loop_id] = {...} 来触发 __setitem__，
            # 这样才能正确更新 internal_state。
            if ctx.flow_processor:
                node_states = ctx.flow_processor.node_states
                # 使用 __setitem__ 来更新状态，而不是修改 __getitem__ 返回的副本
                node_states[loop_id] = {
                    "iteration_plan": iteration_plan,
                    "current_subtask_index": 0,
                    "iteration": 0,
                }
            
            # 获取 loop-start 节点 ID
            # 优先从节点配置中获取，否则从图中查找
            start_node_id = node_data.get("start_node_id")
            if not start_node_id:
                # 从图中查找 parentId 或 parentNode 为当前 loop 的 loop-start 节点
                for nid, ndata in ctx.flow_processor.graph_manager.nodes.items():
                    parent_id = ndata.get("parentId") or ndata.get("parentNode")
                    node_type = ndata.get("data", {}).get("type") or ndata.get("type")
                    if parent_id == loop_id and node_type == "loop-start":
                        start_node_id = nid
                        break
            
            if not start_node_id:
                # 最后尝试默认命名格式
                start_node_id = f"{loop_id}start"
                logger.logger.warning(f"[LoopNodeHandlerV2] Could not find loop-start node, using default: {start_node_id}")
            
            # 发送 cua_end 事件
            yield {
                "type": "cua_end",
                "cuaId": cua_id,
                "status": "completed",
                "title": "Loop Planning",
                "action": {"type": "plan_complete"},
            }
            
            # 记录到 RuntimeStateManager
            if ctx.flow_processor:
                try:
                    ctx.flow_processor.runtime_state.record_node_action(
                        node_id=ctx.node_id,
                        thinking=reasoning,
                        title="Loop Planning",
                        observation=observation,
                        reasoning=reasoning,
                        action_type="loop_plan",
                        action_params={"iteration_plan": iteration_plan},
                        action_target=f"Planned {len(iteration_plan)} iterations",
                    )
                    ctx.flow_processor.runtime_state.complete_node_action(
                        node_id=ctx.node_id,
                        status="success",
                        result_observation=f"Generated {len(iteration_plan)} iteration subtasks",
                    )
                except Exception as e:
                    logger.logger.warning(f"[LoopNodeHandlerV2] Failed to record action: {e}")
            
            # 构建完成摘要
            node_completion_summary = (
                f"Prepared iteration plan with {len(iteration_plan)} subtasks for the loop:\n"
                + "\n".join([f"  {i+1}. {task}" for i, task in enumerate(iteration_plan[:5])])
                + (f"\n  ... and {len(iteration_plan) - 5} more" if len(iteration_plan) > 5 else "")
            )
            
            # 发送 node_complete 事件
            yield NodeCompleteEvent(
                node_id=ctx.node_id,
                node_type=ctx.node_type,
                is_node_completed=True,
                handler_result={
                    "Observation": observation,
                    "Reasoning": reasoning,
                    "Action": f"Planned {len(iteration_plan)} iteration subtasks.",
                    "is_node_completed": True,
                    "current_state": updated_state,
                    "break_loop": False,
                    "next_node_id": start_node_id,
                },
                action_summary="Loop Planning",
                node_completion_summary=node_completion_summary,
                next_node_id=start_node_id,
            ).to_dict()
            
        except Exception as e:
            error_msg = f"Loop node execution failed: {str(e)}"
            logger.logger.error(error_msg, exc_info=True)
            
            yield {
                "type": "cua_end",
                "cuaId": cua_id,
                "status": "error",
                "error": error_msg,
            }
            yield ErrorEvent(message=error_msg, node_id=ctx.node_id).to_dict()


__all__ = ["LoopNodeHandlerV2"]
