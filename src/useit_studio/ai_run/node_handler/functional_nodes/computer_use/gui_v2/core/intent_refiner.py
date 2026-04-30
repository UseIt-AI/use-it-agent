"""
GUI Agent V2 - Intent Refiner (意图细化器)

负责将笼统的里程碑描述细化为具体的、上下文感知的目的。

使用场景：
1. 循环中的里程碑需要根据当前迭代生成不同的目的
2. 需要结合历史动作和当前状态来细化任务描述

例如：
- 原始描述："处理列表中的项目"
- 细化后（第2次迭代）："处理列表中的第2个项目：iPhone 15 Pro"
"""

from typing import Dict, Any, Optional, List

from ..utils.llm_client import VLMClient, LLMConfig
from useit_studio.ai_run.utils.logger_utils import LoggerUtils


# ==================== Prompt 模板 ====================

REFINER_SYSTEM_PROMPT = """You are an AI assistant that generates contextually-aware purposes for GUI milestones.

Your job is to refine the original milestone description based on:
1. The overall task context
2. Historical progress
3. Current loop iteration (if applicable)
4. Previous actions

Create a more specific and actionable purpose that clearly defines what needs to be done."""


REFINER_USER_PROMPT = """Overall Task: {overall_task}

Current Milestone: {milestone_title}
Original Description: {original_description}

{loop_info}

History Context:
{history_md}

Guidance Steps for this Milestone:
{guidance_steps}

Previous Actions for this Node:
{action_history}

Please generate a refined, contextually-aware purpose for this milestone that:
1. Considers the overall task context
2. Takes into account the historical progress
3. Is more specific and actionable than the original description
4. Considers the loop context if applicable
5. Uses simple, concise, and straightforward language
6. Clearly defines what specific state or result indicates this milestone is finished

Return only the refined purpose as a single paragraph, without any additional formatting or explanation. Keep it concise and crystal clear."""


class IntentRefiner:
    """
    意图细化器
    
    将笼统的里程碑描述细化为具体的、上下文感知的目的。
    """
    
    def __init__(
        self,
        model: str = "gemini-3-flash-preview",
        api_keys: Optional[Dict[str, str]] = None,
        max_tokens: int = 500,
        temperature: float = 0.1,
        node_id: str = "",  # 用于日志标识
    ):
        self.logger = LoggerUtils(component_name="IntentRefiner")
        self.node_id = node_id
        
        # 初始化 VLM 客户端（带角色标识）
        config = LLMConfig(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            role="intent_refiner",  # 标识这是 IntentRefiner
            node_id=node_id,
        )
        self.vlm = VLMClient(config=config, api_keys=api_keys, logger=self.logger)
    
    def set_node_id(self, node_id: str):
        """更新节点 ID（用于日志）"""
        self.node_id = node_id
        self.vlm.config.node_id = node_id
    
    async def refine(
        self,
        original_description: str,
        milestone_title: str = "",
        overall_task: str = "",
        history_md: str = "",
        guidance_steps: List[str] = None,
        action_history: List[str] = None,
        loop_context: Optional[Dict[str, Any]] = None,
        log_dir: Optional[str] = None,
    ) -> str:
        """
        细化里程碑描述
        
        Args:
            original_description: 原始的里程碑描述
            milestone_title: 里程碑标题
            overall_task: 整体任务描述
            history_md: 历史动作的 Markdown
            guidance_steps: 指导步骤列表
            action_history: 当前节点的历史动作
            loop_context: 循环上下文（如果在循环中）
            log_dir: 日志目录
            
        Returns:
            细化后的目的描述
        """
        try:
            # 构建提示
            user_prompt = self._build_prompt(
                original_description=original_description,
                milestone_title=milestone_title,
                overall_task=overall_task,
                history_md=history_md,
                guidance_steps=guidance_steps or [],
                action_history=action_history or [],
                loop_context=loop_context,
            )
            
            # 调用 VLM
            response = await self.vlm.call(
                prompt=user_prompt,
                system_prompt=REFINER_SYSTEM_PROMPT,
                log_dir=log_dir,
            )
            
            refined_purpose = response["content"].strip()
            
            if refined_purpose:
                self.logger.logger.info(f"[IntentRefiner] 细化完成: {refined_purpose[:100]}...")
                return refined_purpose
            else:
                # 返回带上下文的原始描述
                return self._generate_fallback(original_description, overall_task, loop_context)
                
        except Exception as e:
            self.logger.logger.error(f"[IntentRefiner] 细化失败: {e}")
            return self._generate_fallback(original_description, overall_task, loop_context)
    
    def _build_prompt(
        self,
        original_description: str,
        milestone_title: str,
        overall_task: str,
        history_md: str,
        guidance_steps: List[str],
        action_history: List[str],
        loop_context: Optional[Dict[str, Any]],
    ) -> str:
        """构建用户提示"""
        
        # 格式化指导步骤
        if guidance_steps:
            steps_str = "\n".join([f"{i+1}. {step}" for i, step in enumerate(guidance_steps)])
        else:
            steps_str = "No guidance steps available."
        
        # 格式化动作历史
        if action_history:
            history_str = "\n".join([f"{i+1}. {action}" for i, action in enumerate(action_history)])
        else:
            history_str = "No previous actions."
        
        # 格式化循环信息
        loop_info = ""
        if loop_context:
            loop_id = loop_context.get("loop_id", "")
            current_iter = loop_context.get("current_iteration", 0)
            max_iter = loop_context.get("max_iterations", 1)
            loop_goal = loop_context.get("loop_goal", "")
            iteration_plan = loop_context.get("iteration_plan", [])
            
            # 计算实际的迭代次数
            actual_max = len(iteration_plan) if iteration_plan else max_iter
            
            if iteration_plan and current_iter < len(iteration_plan):
                current_subtask = iteration_plan[current_iter]
                loop_info = f"Loop Context: This is iteration {current_iter + 1}/{actual_max}. Current subtask: {current_subtask}"
            elif loop_goal:
                loop_info = f"Loop Context: This is iteration {current_iter + 1}/{actual_max} with goal: {loop_goal}"
            else:
                loop_info = f"Loop Context: This is iteration {current_iter + 1}/{actual_max}"
        
        return REFINER_USER_PROMPT.format(
            overall_task=overall_task or "No overall task specified.",
            milestone_title=milestone_title or "Untitled Milestone",
            original_description=original_description,
            loop_info=loop_info,
            history_md=history_md or "No previous history.",
            guidance_steps=steps_str,
            action_history=history_str,
        )
    
    def _generate_fallback(
        self,
        original_description: str,
        overall_task: str,
        loop_context: Optional[Dict[str, Any]],
    ) -> str:
        """生成回退目的"""
        fallback = f"[Context: {overall_task}] {original_description}"
        
        if loop_context:
            current_iter = loop_context.get("current_iteration", 0)
            max_iter = loop_context.get("max_iterations", 1)
            fallback = f"[Iteration {current_iter + 1}/{max_iter}] {fallback}"
        
        return fallback


# ==================== 完成摘要生成器 ====================

SUMMARY_SYSTEM_PROMPT = """You are an AI assistant that generates concise completion summaries for GUI milestones.

Your job is to summarize what was accomplished in a single, clear sentence."""


SUMMARY_USER_PROMPT = """Overall Task: {overall_task}

Milestone Description: {milestone_description}

Guidance Steps:
{guidance_steps}

Action History:
{action_history}

Based on the action history above, generate a single sentence summary of what was accomplished in this milestone.
Keep it concise and factual. Focus on the actual outcome, not the steps taken.
Return only the summary sentence."""


class CompletionSummarizer:
    """
    完成摘要生成器
    
    当里程碑完成时，生成一句话摘要。
    """
    
    def __init__(
        self,
        model: str = "gemini-3-flash-preview",
        api_keys: Optional[Dict[str, str]] = None,
        max_tokens: int = 200,
        temperature: float = 0.0,
        node_id: str = "",  # 用于日志标识
    ):
        self.logger = LoggerUtils(component_name="CompletionSummarizer")
        self.node_id = node_id
        
        # 初始化 VLM 客户端（带角色标识）
        config = LLMConfig(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            role="completion_summarizer",  # 标识这是 CompletionSummarizer
            node_id=node_id,
        )
        self.vlm = VLMClient(config=config, api_keys=api_keys, logger=self.logger)
    
    def set_node_id(self, node_id: str):
        """更新节点 ID（用于日志）"""
        self.node_id = node_id
        self.vlm.config.node_id = node_id
    
    async def summarize(
        self,
        milestone_description: str,
        overall_task: str = "",
        guidance_steps: List[str] = None,
        action_history: List[str] = None,
        log_dir: Optional[str] = None,
    ) -> str:
        """
        生成完成摘要
        
        Args:
            milestone_description: 里程碑描述
            overall_task: 整体任务描述
            guidance_steps: 指导步骤
            action_history: 执行的动作历史
            log_dir: 日志目录
            
        Returns:
            一句话摘要
        """
        try:
            # 格式化指导步骤
            if guidance_steps:
                steps_str = "\n".join([f"{i+1}. {step}" for i, step in enumerate(guidance_steps)])
            else:
                steps_str = "No guidance steps."
            
            # 格式化动作历史
            if action_history:
                history_str = "\n".join([f"{i+1}. {action}" for i, action in enumerate(action_history)])
            else:
                history_str = "No actions recorded."
            
            user_prompt = SUMMARY_USER_PROMPT.format(
                overall_task=overall_task or "Sub-Task completed",
                milestone_description=milestone_description,
                guidance_steps=steps_str,
                action_history=history_str,
            )
            
            response = await self.vlm.call(
                prompt=user_prompt,
                system_prompt=SUMMARY_SYSTEM_PROMPT,
                log_dir=log_dir,
            )
            
            summary = response["content"].strip()
            
            if summary:
                return summary
            else:
                return f"Completed: {milestone_description}"
                
        except Exception as e:
            self.logger.logger.error(f"[CompletionSummarizer] 生成摘要失败: {e}")
            return f"Completed: {milestone_description}"
