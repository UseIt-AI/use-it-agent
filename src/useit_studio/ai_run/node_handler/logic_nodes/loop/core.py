"""
Loop Node - 核心逻辑

包含 Loop 节点的核心处理逻辑：
1. LoopPlanner - 生成迭代计划
2. LoopEndEvaluator - 评估是否继续循环
"""

from __future__ import annotations

import json
from typing import Dict, Any, List, Optional, AsyncGenerator, TYPE_CHECKING

from useit_studio.ai_run.llm_utils import MessageBuilder
from useit_studio.ai_run.utils.logger_utils import LoggerUtils

from .models import (
    LoopContext,
    IterationPlanOutput,
    LoopEndDecision,
)

if TYPE_CHECKING:
    from useit_studio.ai_run.agent_loop.workflow.graph_manager import GraphManager

logger = LoggerUtils(component_name="LoopCore")


class LoopPlanner:
    """
    Loop Planner - 生成迭代计划
    
    职责：
    1. 分析循环目标和子节点描述
    2. 调用 LLM 生成迭代计划
    3. 支持流式输出
    """
    
    def __init__(
        self,
        model: str = "gpt-4o-mini",
        api_keys: Optional[Dict[str, str]] = None,
    ):
        self.model = model
        self.api_keys = api_keys or {}
    
    async def plan(
        self,
        context: LoopContext,
        screenshot_path: Optional[str] = None,
        log_dir: Optional[str] = None,
    ) -> IterationPlanOutput:
        """
        生成迭代计划（非流式）
        
        Args:
            context: Loop 上下文
            screenshot_path: 截图路径
            log_dir: 日志目录
            
        Returns:
            IterationPlanOutput
        """
        messages = self._build_messages(context, screenshot_path)
        system_prompt = self._get_system_prompt()
        
        try:
            from useit_studio.ai_run.llm_utils import call_llm
            
            response = await call_llm(
                messages=messages,
                model=self.model,
                system_prompt=system_prompt,
                api_key=self.api_keys.get("OPENAI_API_KEY"),
                temperature=0.3,
            )
            
            if not response or not response.content:
                raise ValueError("LLM returned empty response")
            
            # 解析 JSON 响应
            response_data = json.loads(response.content.strip())
            
            # 保存日志
            if log_dir:
                log_path = f"{log_dir}/loop_plan_{context.loop_id}.json"
                with open(log_path, "w") as f:
                    json.dump(response_data, f, indent=2, ensure_ascii=False)
            
            output = IterationPlanOutput.from_dict(response_data)
            
            # 限制最大迭代次数
            output.iteration_plan = output.iteration_plan[:context.max_iterations]
            
            return output
            
        except Exception as e:
            logger.logger.error(f"[LoopPlanner] Error: {e}", exc_info=True)
            # 返回默认计划
            return IterationPlanOutput(
                observation="Error occurred during planning",
                reasoning=str(e),
                iteration_plan=[
                    f"Iteration {i + 1}: {context.loop_goal}"
                    for i in range(context.max_iterations)
                ],
            )
    
    async def plan_streaming(
        self,
        context: LoopContext,
        screenshot_path: Optional[str] = None,
        log_dir: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        生成迭代计划（流式）
        
        Yields:
            - {"type": "reasoning_delta", "content": str}
            - {"type": "plan_complete", "content": IterationPlanOutput}
        """
        messages = self._build_messages(context, screenshot_path)
        system_prompt = self._get_system_prompt()
        
        try:
            from useit_studio.ai_run.llm_utils import stream_llm
            
            full_response = ""
            
            # stream_llm 返回 StreamChunk 对象
            async for chunk in stream_llm(
                messages=messages,
                model=self.model,
                system_prompt=system_prompt,
                api_key=self.api_keys.get("OPENAI_API_KEY"),
                temperature=0.3,
            ):
                # StreamChunk 有 content 和 chunk_type 属性
                if chunk and chunk.chunk_type == "text" and chunk.content:
                    full_response += chunk.content
                    yield {
                        "type": "reasoning_delta",
                        "content": chunk.content,
                        "source": "loop_planner",
                    }
                elif chunk and chunk.chunk_type == "error":
                    logger.logger.error(f"[LoopPlanner] Stream error: {chunk.content}")
            
            # 解析完整响应
            try:
                # 尝试提取 JSON（可能被 markdown 代码块包裹）
                json_str = full_response.strip()
                if json_str.startswith("```json"):
                    json_str = json_str[7:]
                if json_str.startswith("```"):
                    json_str = json_str[3:]
                if json_str.endswith("```"):
                    json_str = json_str[:-3]
                json_str = json_str.strip()
                
                response_data = json.loads(json_str)
                output = IterationPlanOutput.from_dict(response_data)
                output.iteration_plan = output.iteration_plan[:context.max_iterations]
            except json.JSONDecodeError as e:
                logger.logger.warning(f"[LoopPlanner] Failed to parse JSON: {e}, response: {full_response[:200]}")
                output = IterationPlanOutput(
                    observation="Failed to parse LLM response",
                    reasoning=full_response[:500],
                    iteration_plan=[
                        f"Iteration {i + 1}: {context.loop_goal}"
                        for i in range(context.max_iterations)
                    ],
                )
            
            # 保存日志
            if log_dir:
                log_path = f"{log_dir}/loop_plan_{context.loop_id}.json"
                try:
                    with open(log_path, "w") as f:
                        json.dump({
                            "raw_response": full_response,
                            "observation": output.observation,
                            "reasoning": output.reasoning,
                            "iteration_plan": output.iteration_plan,
                        }, f, indent=2, ensure_ascii=False)
                except Exception:
                    pass
            
            yield {
                "type": "plan_complete",
                "content": {
                    "observation": output.observation,
                    "reasoning": output.reasoning,
                    "iteration_plan": output.iteration_plan,
                },
            }
            
        except Exception as e:
            logger.logger.error(f"[LoopPlanner] Streaming error: {e}", exc_info=True)
            yield {
                "type": "error",
                "content": str(e),
            }
    
    def _build_messages(
        self,
        context: LoopContext,
        screenshot_path: Optional[str] = None,
    ) -> List[Any]:
        """构建 LLM 消息"""
        # 格式化子节点描述
        milestone_text = ""
        if context.sub_milestone_descriptions:
            milestone_text = "\n".join([
                f"- {desc}" for desc in context.sub_milestone_descriptions
            ])
        else:
            milestone_text = "(No sub-milestone descriptions available)"
        
        # 构建更详细的循环目标描述
        loop_goal_text = context.loop_goal
        if loop_goal_text.lower() in ["loop", "循环", ""]:
            # 如果 loop_goal 是通用名称，尝试从子节点描述推断
            if context.sub_milestone_descriptions:
                loop_goal_text = f"Repeat the following task for multiple items: {context.sub_milestone_descriptions[0]}"
            else:
                loop_goal_text = "Repeat the task for each item in the list"
        
        user_prompt = f"""You are planning iterations for a loop to achieve a goal.

## User's Request / Overall Task Context
{context.query or "(No user request provided)"}

## Previous Execution History
{context.history_md or "(No history available)"}

## Loop Goal / Description
{loop_goal_text}

## Sub-milestones in this Loop (tasks to repeat for each iteration)
{milestone_text}

## Instructions
Based on the user's request and the loop goal, determine WHAT items need to be iterated over.

For example:
- If the user wants to "query stock prices for Apple, Google, and Microsoft", you should create 3 iterations: one for each company.
- If the user wants to "process files A, B, C", you should create 3 iterations: one for each file.

**IMPORTANT**: 
1. Analyze the user's request to identify the LIST of items to iterate over.
2. Create one subtask for each item in the list.
3. Each subtask should be specific and actionable (e.g., "Query stock price for Apple (AAPL)").
4. Maximum iterations allowed: {context.max_iterations}

Return your response as **strict JSON only** (no markdown, no extra text):
{{
    "Observation": "What items/entities need to be processed in this loop",
    "Reasoning": "Why these items were identified and how they will be processed",
    "IterationPlan": ["Specific subtask 1", "Specific subtask 2", ...]
}}
"""
        
        content = [user_prompt]
        if screenshot_path:
            content.append(screenshot_path)
        
        return MessageBuilder.from_interleave_list(content)
    
    def _get_system_prompt(self) -> str:
        """获取系统提示"""
        return """You are a precise planner for loop iterations.
Your task is to analyze the user's request and identify the items that need to be processed in a loop.

Rules:
1. Carefully read the user's request to identify WHAT needs to be iterated (e.g., list of companies, files, URLs, etc.)
2. Create one specific subtask for each item identified
3. Each subtask should be clear, specific, and actionable
4. The number of subtasks should not exceed the maximum iterations
5. Output ONLY valid JSON - no markdown code blocks, no extra text, no explanations outside the JSON structure

Example: If user says "query stock prices for Apple, Google, Microsoft", your IterationPlan should be:
["Query stock price for Apple (AAPL)", "Query stock price for Google (GOOGL)", "Query stock price for Microsoft (MSFT)"]"""


class LoopEndEvaluator:
    """
    Loop End Evaluator - 评估是否继续循环
    
    职责：
    1. 检查迭代计划完成情况
    2. 决定是否继续循环
    """
    
    def evaluate(
        self,
        loop_id: str,
        current_iteration: int,
        iteration_plan: List[str],
        max_iterations: int,
    ) -> LoopEndDecision:
        """
        评估是否继续循环
        
        Args:
            loop_id: 循环 ID
            current_iteration: 当前迭代次数
            iteration_plan: 迭代计划
            max_iterations: 最大迭代次数
            
        Returns:
            LoopEndDecision
        """
        total_subtasks = len(iteration_plan) if iteration_plan else max_iterations
        
        # current_iteration 表示「刚完成的那一轮」的 0-based 下标，已完成次数 = current_iteration + 1。
        # 应继续当且仅当已完成次数 < 上限，即 (current_iteration + 1) < N，避免多跑一轮。
        if iteration_plan:
            should_continue = (current_iteration + 1) < len(iteration_plan)
            remaining = max(0, len(iteration_plan) - current_iteration - 1)
            
            if should_continue:
                current_subtask = iteration_plan[current_iteration] if current_iteration < len(iteration_plan) else ""
                return LoopEndDecision(
                    should_continue=True,
                    observation=f"Loop iteration {current_iteration + 1}/{total_subtasks} completed.",
                    reasoning=f"Continuing loop as there are {remaining} more subtasks to complete.",
                    action=f"Continue to next iteration. Current subtask: '{current_subtask}'",
                    current_iteration=current_iteration,
                    total_subtasks=total_subtasks,
                    remaining_subtasks=remaining,
                )
            else:
                return LoopEndDecision(
                    should_continue=False,
                    observation=f"Loop completed successfully. All {total_subtasks} subtasks finished.",
                    reasoning="All planned subtasks have been completed.",
                    action="Exiting loop after completing all planned tasks.",
                    current_iteration=current_iteration,
                    total_subtasks=total_subtasks,
                    remaining_subtasks=0,
                )
        else:
            # 没有迭代计划，按最大迭代次数执行（同上：已完成 = current_iteration+1）
            should_continue = (current_iteration + 1) < max_iterations
            remaining = max(0, max_iterations - current_iteration - 1)
            
            if should_continue:
                return LoopEndDecision(
                    should_continue=True,
                    observation=f"Loop iteration {current_iteration + 1}/{max_iterations} completed.",
                    reasoning=f"Continuing loop. {remaining} iterations remaining.",
                    action=f"Continue to iteration {current_iteration + 2}.",
                    current_iteration=current_iteration,
                    total_subtasks=max_iterations,
                    remaining_subtasks=remaining,
                )
            else:
                return LoopEndDecision(
                    should_continue=False,
                    observation=f"Loop completed. Maximum iterations ({max_iterations}) reached.",
                    reasoning="Maximum iterations reached.",
                    action="Exiting loop after maximum iterations.",
                    current_iteration=current_iteration,
                    total_subtasks=max_iterations,
                    remaining_subtasks=0,
                )


def collect_loop_milestone_descriptions(
    graph_manager: "GraphManager",
    loop_id: str,
) -> List[str]:
    """
    收集循环内所有 computer-use 节点的描述
    
    按执行顺序遍历循环内的节点，收集描述信息。
    
    Args:
        graph_manager: 图管理器
        loop_id: 循环 ID
        
    Returns:
        描述列表
    """
    if not loop_id:
        return []
    
    descriptions = []
    loop_start_id = f"{loop_id}start"
    
    visited = set()
    current_node_id = loop_start_id
    
    while current_node_id and current_node_id not in visited:
        visited.add(current_node_id)
        
        current_node_data = graph_manager.nodes.get(current_node_id)
        if not current_node_data:
            break
        
        node_type = current_node_data.get("data", {}).get("type")
        
        # 检查是否在循环内
        is_in_loop = (
            current_node_data.get("parentId") == loop_id or
            current_node_data.get("parentNode") == loop_id or
            current_node_data.get("data", {}).get("loop_id") == loop_id
        )
        
        if is_in_loop and node_type == "computer-use":
            # 提取描述
            description = current_node_data.get("data", {}).get("description", "").strip()
            
            if description:
                descriptions.append(description)
            else:
                # 尝试从 steps 构建描述
                steps = current_node_data.get("data", {}).get("steps", [])
                if steps:
                    step_descriptions = []
                    for step in steps:
                        if isinstance(step, dict):
                            step_content = step.get("content", "").strip()
                        else:
                            step_content = str(step).strip()
                        if step_content:
                            step_descriptions.append(step_content)
                    
                    if step_descriptions:
                        if len(step_descriptions) > 3:
                            combined = "; ".join(step_descriptions[:3]) + f" (and {len(step_descriptions)-3} more steps)"
                        else:
                            combined = "; ".join(step_descriptions)
                        descriptions.append(combined)
                else:
                    # 使用标题作为回退
                    title = current_node_data.get("data", {}).get("title", "").strip()
                    if title:
                        descriptions.append(f"Milestone: {title}")
        
        # 到达 loop-end 停止
        if node_type == "loop-end":
            break
        
        # 查找下一个节点
        next_node_id = None
        for edge in graph_manager.edges:
            if edge.get("source") == current_node_id:
                target_id = edge.get("target")
                target_node = graph_manager.nodes.get(target_id)
                if target_node:
                    target_in_loop = (
                        target_node.get("parentId") == loop_id or
                        target_node.get("parentNode") == loop_id or
                        target_node.get("data", {}).get("loop_id") == loop_id
                    )
                    if target_in_loop:
                        next_node_id = target_id
                        break
        
        current_node_id = next_node_id
        
        # 安全检查
        if len(visited) > 50:
            logger.logger.warning(f"Breaking loop traversal after {len(visited)} nodes")
            break
    
    return descriptions


__all__ = [
    "LoopPlanner",
    "LoopEndEvaluator",
    "collect_loop_milestone_descriptions",
]
