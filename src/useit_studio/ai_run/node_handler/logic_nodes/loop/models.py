"""
Loop Node - 数据模型定义

包含 Loop 节点处理所需的所有数据模型。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional


@dataclass
class LoopContext:
    """
    Loop 执行上下文
    
    封装 Loop 节点执行所需的所有信息。
    """
    # 循环配置
    loop_id: str
    loop_goal: str
    max_iterations: int = 5
    
    # 当前状态
    current_iteration: int = 0
    iteration_plan: List[str] = field(default_factory=list)
    
    # 子节点描述
    sub_milestone_descriptions: List[str] = field(default_factory=list)
    
    # 历史信息
    history_md: str = ""
    query: str = ""
    
    @classmethod
    def from_node_dict(
        cls,
        node_dict: Dict[str, Any],
        node_state: Dict[str, Any],
        loop_id: str,
    ) -> "LoopContext":
        """从节点字典创建上下文"""
        node_data = node_dict.get("data", {})
        
        # 提取循环目标 - 优先使用 instruction 字段
        loop_goal = (
            node_data.get("instruction") or  # 最高优先级：instruction 字段
            node_data.get("condition") or
            node_data.get("description") or
            node_data.get("desc") or
            node_data.get("title") or
            node_dict.get("title") or
            "Loop goal not specified."
        )
        
        # 提取最大迭代次数 (支持 max_iteration 和 max_iterations 两种写法)
        max_iterations = node_data.get("max_iterations") or node_data.get("max_iteration", 5)
        if not isinstance(max_iterations, int) or max_iterations <= 0:
            max_iterations = 5
        
        # 获取当前迭代次数
        current_iteration = node_state.get("iteration", 0)
        
        # 获取已有的迭代计划
        iteration_plan = node_state.get(f"{loop_id}_iteration_plan", [])
        
        return cls(
            loop_id=loop_id,
            loop_goal=loop_goal,
            max_iterations=max_iterations,
            current_iteration=current_iteration,
            iteration_plan=iteration_plan,
        )


@dataclass
class IterationPlanOutput:
    """
    迭代计划输出
    
    LLM 生成的迭代计划结果。
    """
    observation: str = ""
    reasoning: str = ""
    iteration_plan: List[str] = field(default_factory=list)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IterationPlanOutput":
        """从字典创建"""
        observation = data.get("Observation", "")
        reasoning = data.get("Reasoning", "")
        
        # 灵活提取计划列表
        plan_value = None
        for key in ["IterationPlan", "IterationSubtasks", "Plan", "Subtasks"]:
            if key in data:
                plan_value = data[key]
                break
        
        iteration_plan = []
        if isinstance(plan_value, list):
            for item in plan_value:
                if isinstance(item, str):
                    iteration_plan.append(item)
                elif isinstance(item, dict):
                    text = item.get("title") or item.get("task") or item.get("name") or str(item)
                    iteration_plan.append(str(text))
                else:
                    iteration_plan.append(str(item))
        elif isinstance(plan_value, str):
            lines = [ln.strip(" -\t") for ln in plan_value.splitlines() if ln.strip()]
            iteration_plan.extend(lines)
        
        return cls(
            observation=observation,
            reasoning=reasoning,
            iteration_plan=iteration_plan,
        )


@dataclass
class LoopEndDecision:
    """
    Loop End 决策结果
    
    决定是否继续循环。
    """
    should_continue: bool
    observation: str = ""
    reasoning: str = ""
    action: str = ""
    
    # 当前进度
    current_iteration: int = 0
    total_subtasks: int = 0
    remaining_subtasks: int = 0


# ==================== 事件类型 ====================

@dataclass
class LoopPlanningEvent:
    """循环规划事件"""
    type: str = "loop_planning"
    loop_id: str = ""
    message: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "loop_id": self.loop_id,
            "message": self.message,
        }


@dataclass
class LoopIterationEvent:
    """循环迭代事件"""
    type: str = "loop_iteration"
    loop_id: str = ""
    iteration: int = 0
    total: int = 0
    subtask: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "loop_id": self.loop_id,
            "iteration": self.iteration,
            "total": self.total,
            "subtask": self.subtask,
        }


@dataclass
class LoopCompleteEvent:
    """循环完成事件"""
    type: str = "loop_complete"
    loop_id: str = ""
    total_iterations: int = 0
    summary: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "loop_id": self.loop_id,
            "total_iterations": self.total_iterations,
            "summary": self.summary,
        }


__all__ = [
    "LoopContext",
    "IterationPlanOutput",
    "LoopEndDecision",
    "LoopPlanningEvent",
    "LoopIterationEvent",
    "LoopCompleteEvent",
]
