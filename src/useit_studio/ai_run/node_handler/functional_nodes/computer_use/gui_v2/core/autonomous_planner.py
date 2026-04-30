"""
GUI Agent V2 - Autonomous Planner (自主规划器)

用于处理**没有 guidance_steps** 的场景，完全自主规划下一步动作。

注意：原来的 Planner (planner.py) 就是 Teach Mode Planner，需要 guidance_steps。
本模块是为了补充无指导场景的能力。

使用场景：
- 无录制轨迹时：完全自主规划
- 动态任务：无法预先录制轨迹的场景
"""

import json
import os
from typing import Dict, Any, Optional, AsyncGenerator, List

from ..models import PlannerOutput, ReasoningDeltaEvent, PlanCompleteEvent
from ..utils.llm_client import VLMClient, LLMConfig
from ..utils.image_utils import resize_screenshot
from useit_studio.ai_run.utils.logger_utils import LoggerUtils


# ==================== Autonomous Mode Prompts ====================

AUTONOMOUS_SYSTEM_PROMPT = """You are a helpful planning assistant for computer-use tasks on a {os_name} device.

You are operating in **AUTONOMOUS MODE** - you must plan actions independently without pre-recorded guidance.

Your job is to:
1. Observe the current screenshot carefully
2. Understand the task objective
3. Plan the next logical action to achieve the goal
4. Output a JSON response with your observation, reasoning, and planned action

**IMPORTANT**: Think step by step. Consider what elements are visible on screen and how to interact with them to achieve the objective.

## Step Memory

Use `step_memory` ONLY to record **business-critical data** you observe on the screen.

**When to use:**
- You found target data (names, IDs, values, search results, extracted info)
- Information that won't be visible in subsequent screenshots but is essential
- Data that needs to be aggregated across steps

**When NOT to use:**
- Navigation progress ("opened menu", "clicked button") - this is already in action history
- UI state descriptions ("panel is open", "list expanded")
- Plans or intentions for next steps

**Example - Good:** "群成员: 张三、李四、王五; 群名: 家庭群 → 关系: 家人/亲戚"
**Example - Bad:** "已打开群信息面板，成员列表未完全展开" ← navigation state, not data

## Save Results (REQUIRED at completion)

When MilestoneCompleted=true, you MUST provide result output:

- `node_completion_summary`: Brief text summary (1-2 sentences) of what was accomplished
- `result_markdown`: **REQUIRED** - The markdown report of this node's work
- `output_filename`: Descriptive filename ending in `.md`

**Content guidelines for result_markdown:**
- For data collection tasks (search, extract, list): Include ALL collected data in structured format
- For operation tasks (click, navigate, configure): Brief summary of what was done and final state

The file will be saved to outputs folder automatically."""


AUTONOMOUS_USER_PROMPT = """Overall Task Goal: {task_description}

History Actions: 
{history_md}

{attached_files_section}

Current Milestone Objective: {milestone_objective}

{knowledge_section}

Output Format:
{{
    "Observation": str,  # Detailed observation of the current screenshot
    "Reasoning": str,  # Step-by-step reasoning about how to achieve the objective
    "Action": str | null,  # Specific action to take OR null if milestone completed
    "Expectation": str,  # Expected result after the action
    "MilestoneCompleted": bool,  # True ONLY if objective is ALREADY achieved
    "step_memory": str | null,  # record business data observed (NOT navigation state)
    "node_completion_summary": str | null,  # REQUIRED when MilestoneCompleted=true: brief summary
    "result_markdown": str | null,  # REQUIRED when MilestoneCompleted=true: full markdown report
    "output_filename": str | null  # REQUIRED when MilestoneCompleted=true: filename like "report.md"
}}

**CRITICAL RULES:**
1. MilestoneCompleted = true AND Action = null: Goal is ALREADY achieved, no action needed
2. MilestoneCompleted = false AND Action = "...": Action needed to progress
3. NEVER set MilestoneCompleted = true while providing an Action
4. Be specific about what element to interact with and how
5. Consider the history actions to avoid repeating failed attempts

Current Milestone Objective: {milestone_objective}

Based on the current screenshot, now start planning:"""


class AutonomousPlanner:
    """
    Autonomous Planner - 自主规划器
    
    用于处理没有 guidance_steps 的场景，完全自主规划下一步动作。
    
    特性：
    1. 不依赖 guidance_steps
    2. 基于截图和任务目标自主推理
    3. 考虑历史动作避免重复失败
    """
    
    def __init__(
        self,
        model: str = "gemini-3-flash-preview",
        api_keys: Optional[Dict[str, str]] = None,
        max_tokens: int = 2048,
        temperature: float = 0.0,
        screen_max_side: int = 1024,
        os_name: str = "Windows",
        node_id: str = "",
    ):
        self.os_name = os_name
        self.screen_max_side = screen_max_side
        self.node_id = node_id
        self.logger = LoggerUtils(component_name="AutonomousPlanner")
        
        # 初始化 VLM 客户端
        config = LLMConfig(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            role="autonomous_planner",
            node_id=node_id,
        )
        self.vlm = VLMClient(config=config, api_keys=api_keys, logger=self.logger)
    
    def set_node_id(self, node_id: str):
        """更新节点 ID"""
        self.node_id = node_id
        self.vlm.config.node_id = node_id
    
    async def plan(
        self,
        screenshot_path: str,
        task_description: str,
        milestone_objective: str,
        guidance_steps: List[str] = None,  # 保留参数以保持接口一致，但不使用
        history_md: str = "",
        knowledge_context: str = "",
        log_dir: Optional[str] = None,
        attached_files_content: str = "",
        attached_images_base64: Optional[List[str]] = None,
    ) -> PlannerOutput:
        """
        非流式规划
        
        Args:
            screenshot_path: 当前截图路径
            task_description: 整体任务描述
            milestone_objective: 当前里程碑目标
            guidance_steps: 指导步骤（本 Planner 不使用，保留以保持接口一致）
            history_md: 历史动作 Markdown
            knowledge_context: 外部知识上下文
            log_dir: 日志目录
            attached_files_content: 附件文件内容
            
        Returns:
            PlannerOutput 对象
        """
        self.logger.logger.info("[AutonomousPlanner] 开始自主规划")
        
        # 准备截图
        resized_path = self._prepare_screenshot(screenshot_path, log_dir)
        
        # 构建 prompt
        system_prompt = AUTONOMOUS_SYSTEM_PROMPT.format(os_name=self.os_name)
        user_prompt = self._build_prompt(
            task_description=task_description,
            milestone_objective=milestone_objective,
            history_md=history_md,
            knowledge_context=knowledge_context,
            attached_files_content=attached_files_content,
        )
        
        # 调用 VLM
        response = await self.vlm.call(
            prompt=user_prompt,
            system_prompt=system_prompt,
            screenshot_path=resized_path,
            attached_images_base64=attached_images_base64,
            log_dir=log_dir,
        )
        
        # 解析响应
        return self._parse_response(response["content"])
    
    async def plan_streaming(
        self,
        screenshot_path: str,
        task_description: str,
        milestone_objective: str,
        guidance_steps: List[str] = None,  # 保留参数以保持接口一致，但不使用
        history_md: str = "",
        knowledge_context: str = "",
        log_dir: Optional[str] = None,
        attached_files_content: str = "",
        attached_images_base64: Optional[List[str]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式规划
        
        Yields:
            ReasoningDeltaEvent - 推理过程增量
            PlanCompleteEvent - 规划完成
        """
        self.logger.logger.info("[AutonomousPlanner] 开始流式自主规划")
        
        # 发送模式信息
        yield {
            "type": "status",
            "content": "Planning in autonomous mode...",
            "mode": "autonomous",
        }
        
        # 准备截图
        resized_path = self._prepare_screenshot(screenshot_path, log_dir)
        
        # 构建 prompt
        system_prompt = AUTONOMOUS_SYSTEM_PROMPT.format(os_name=self.os_name)
        user_prompt = self._build_prompt(
            task_description=task_description,
            milestone_objective=milestone_objective,
            history_md=history_md,
            knowledge_context=knowledge_context,
            attached_files_content=attached_files_content,
        )
        
        full_content = ""
        
        # 流式调用 VLM
        async for chunk in self.vlm.stream(
            prompt=user_prompt,
            system_prompt=system_prompt,
            screenshot_path=resized_path,
            attached_images_base64=attached_images_base64,
            log_dir=log_dir,
        ):
            if chunk["type"] == "delta":
                raw_content = chunk["content"]
                content = raw_content
                if isinstance(content, list):
                    content = "".join(str(c) for c in content)
                elif not isinstance(content, str):
                    content = str(content)
                full_content += content
                yield ReasoningDeltaEvent(content=content, source="planner").to_dict()
                
            elif chunk["type"] == "complete":
                planner_output = self._parse_response(full_content)
                yield PlanCompleteEvent(planner_output=planner_output).to_dict()
                
            elif chunk["type"] == "error":
                yield {"type": "error", "content": chunk["content"]}
    
    def _prepare_screenshot(self, screenshot_path: str, log_dir: Optional[str]) -> str:
        """准备截图"""
        if not screenshot_path or not os.path.exists(screenshot_path):
            raise ValueError(f"截图文件不存在: {screenshot_path}")
        
        if log_dir:
            output_path = os.path.join(log_dir, "autonomous_planner_screenshot.png")
        else:
            output_path = screenshot_path.replace(".png", "_resized.png")
        
        return resize_screenshot(screenshot_path, output_path, self.screen_max_side)
    
    def _build_prompt(
        self,
        task_description: str,
        milestone_objective: str,
        history_md: str,
        knowledge_context: str,
        attached_files_content: str = "",
    ) -> str:
        """构建 prompt"""
        knowledge_section = ""
        if knowledge_context:
            knowledge_section = f"External Knowledge:\n{knowledge_context}\n"
        
        return AUTONOMOUS_USER_PROMPT.format(
            task_description=task_description or "Complete the current milestone",
            history_md=history_md or "No previous actions.",
            attached_files_section=attached_files_content,
            milestone_objective=milestone_objective,
            knowledge_section=knowledge_section,
        )
    
    def _parse_response(self, response: str) -> PlannerOutput:
        """解析 LLM 响应"""
        try:
            parsed = self._extract_json(response)
            
            return PlannerOutput(
                observation=parsed.get("Observation", ""),
                reasoning=parsed.get("Reasoning", ""),
                next_action=parsed.get("Action") or "",
                current_step=1,  # 自主模式没有步骤跟踪
                step_explanation="",
                expectation=parsed.get("Expectation", ""),
                is_milestone_completed=parsed.get("MilestoneCompleted", False),
                completion_summary=parsed.get("node_completion_summary"),
                output_filename=parsed.get("output_filename"),
                result_markdown=parsed.get("result_markdown"),
                step_memory=parsed.get("step_memory"),
            )
            
        except Exception as e:
            self.logger.logger.error(f"解析 AutonomousPlanner 响应失败: {e}")
            return PlannerOutput(
                observation="Failed to parse response",
                reasoning=str(e),
                next_action="",
                is_milestone_completed=False,
            )
    
    def _extract_json(self, text: str) -> Dict[str, Any]:
        """从文本中提取 JSON"""
        text = text.strip()
        
        if text.startswith("{"):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass
        
        import re
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
        
        raise ValueError(f"无法从响应中提取 JSON: {text[:200]}...")


# ==================== 向后兼容别名 ====================

# 保留旧名称作为别名，避免破坏现有代码
TeachModePlanner = AutonomousPlanner
PlannerMode = None  # 不再需要，AutonomousPlanner 只有一种模式


def create_planner(
    model: str = "gemini-3-flash-preview",
    api_keys: Optional[Dict[str, str]] = None,
    **kwargs
) -> AutonomousPlanner:
    """
    创建 AutonomousPlanner 的工厂函数
    
    Args:
        model: 使用的模型
        api_keys: API 密钥
        **kwargs: 其他参数传递给 AutonomousPlanner
        
    Returns:
        AutonomousPlanner 实例
    """
    return AutonomousPlanner(
        model=model,
        api_keys=api_keys,
        **kwargs
    )
