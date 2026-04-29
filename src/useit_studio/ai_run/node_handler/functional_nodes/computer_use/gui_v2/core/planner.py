"""
GUI Agent V2 - Planner 核心逻辑

Planner 负责"思考"：
1. 观察当前截图
2. 结合任务目标和指导步骤
3. 决定下一步应该做什么（自然语言描述）

输出：PlannerOutput（包含 observation, reasoning, next_action 等）
"""

import json
import os
from typing import Dict, Any, Optional, AsyncGenerator, List

from ..models import PlannerOutput, ReasoningDeltaEvent, PlanCompleteEvent
from ..utils.llm_client import VLMClient, LLMConfig
from ..utils.image_utils import resize_screenshot
from useit_studio.ai_run.utils.logger_utils import LoggerUtils


# ==================== Prompt 模板 ====================

PLANNER_SYSTEM_PROMPT = """You are a helpful planning assistant for computer-use tasks on a {os_name} device.

Your job is to:
1. Observe the current screenshot
2. Follow the Guidance Trajectory to plan the next action
3. Output a JSON response with your observation, reasoning, and planned action

You should output JSON responses in the exact format specified. 
Carefully follow the Guidance Trajectory steps and constraints.

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


PLANNER_USER_PROMPT = """Overall Task Goal: {task_description}

History Actions: 
{history_md}

{attached_files_section}

Current Milestone Objective: {milestone_objective}

{knowledge_section}
Guidance Trajectory Examples (within current milestone):
{guidance_steps}

Output Format:
{{
    "Observation": str,  # the current state of the screenshot and history actions.
    "Reasoning": str,  # how to achieve the task, following one of the steps from guidance trajectories.
    "Current Step": "(int, str)",  # (the current step number, plus a brief explanation)
    "Action": str | null,  # "action_description and action_intent" OR null if milestone is completed. One action at a time.
    "Expectation": str,  # the expected result of the action (or empty if MilestoneCompleted is true).
    "MilestoneCompleted": bool,  # True ONLY if the screenshot ALREADY shows the milestone objective is achieved and NO action is needed.
    "step_memory": str | null,  # record business data observed (NOT navigation state)
    "node_completion_summary": str | null,  # REQUIRED when MilestoneCompleted=true: brief summary
    "result_markdown": str | null,  # REQUIRED when MilestoneCompleted=true: full markdown report
    "output_filename": str | null  # REQUIRED when MilestoneCompleted=true: filename like "report.md"
}}

**CRITICAL RULES for MilestoneCompleted and Action:**
- MilestoneCompleted = true AND Action = null: The screenshot ALREADY shows the goal is achieved. No action needed.
- MilestoneCompleted = false AND Action = "...": An action is needed to progress toward the goal.
- **NEVER** set MilestoneCompleted = true while also providing an Action. This is INVALID.
- Only set MilestoneCompleted = true when you can SEE in the current screenshot that the objective is ALREADY satisfied.
- If you need to perform an action to complete the milestone, set MilestoneCompleted = false.

**IMPORTANT NOTES:**
1. Carefully observe the screenshot, and read the guidance trajectories and history actions.
2. The Guidance Trajectory is a successful example of how to achieve the task. Follow the steps unless you encounter unexpected issues.
3. Start from step 1 and complete the task step by step. DO NOT skip any step.
4. You should only give one planning (to take one action) at a time.
5. Carefully determine the current step by comparing observation, action history with the Guidance Trajectory.
6. When one action consistently failed many times, consider using another way to achieve the same step.
7. MilestoneCompleted should ONLY be true when the current screenshot shows the goal is already achieved WITHOUT any further action.

Current Milestone Objective: {milestone_objective}

Based on the current screenshot, now start planning:"""


class Planner:
    """
    GUI Agent Planner
    
    负责高层次的任务规划，决定下一步应该做什么。
    """
    
    def __init__(
        self,
        model: str = "gemini-3-flash-preview",
        api_keys: Optional[Dict[str, str]] = None,
        max_tokens: int = 2048,
        temperature: float = 0.0,
        screen_max_side: int = 1024,
        os_name: str = "Windows",
        node_id: str = "",  # 用于日志标识
    ):
        self.os_name = os_name
        self.screen_max_side = screen_max_side
        self.node_id = node_id
        self.logger = LoggerUtils(component_name="Planner")
        
        # 初始化 VLM 客户端（带角色标识）
        config = LLMConfig(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            role="planner",  # 标识这是 Planner
            node_id=node_id,
        )
        self.vlm = VLMClient(config=config, api_keys=api_keys, logger=self.logger)
    
    def set_node_id(self, node_id: str):
        """更新节点 ID（用于日志）"""
        self.node_id = node_id
        self.vlm.config.node_id = node_id
    
    async def plan(
        self,
        screenshot_path: str,
        task_description: str,
        milestone_objective: str,
        guidance_steps: List[str],
        history_md: str = "",
        knowledge_context: str = "",
        log_dir: Optional[str] = None,
        attached_files_content: str = "",
        attached_images_base64: Optional[List[str]] = None,
    ) -> PlannerOutput:
        """
        非流式规划
        
        Returns:
            PlannerOutput 对象
        """
        # 准备截图
        resized_path = self._prepare_screenshot(screenshot_path, log_dir)
        
        # 构建提示
        system_prompt = PLANNER_SYSTEM_PROMPT.format(os_name=self.os_name)
        user_prompt = self._build_user_prompt(
            task_description=task_description,
            milestone_objective=milestone_objective,
            guidance_steps=guidance_steps,
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
        guidance_steps: List[str],
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
        # 准备截图
        resized_path = self._prepare_screenshot(screenshot_path, log_dir)
        
        # 构建提示
        system_prompt = PLANNER_SYSTEM_PROMPT.format(os_name=self.os_name)
        user_prompt = self._build_user_prompt(
            task_description=task_description,
            milestone_objective=milestone_objective,
            guidance_steps=guidance_steps,
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
                # 详细日志：记录原始 content 的类型
                self.logger.logger.debug(
                    f"[Planner.stream] chunk content type={type(raw_content).__name__}, "
                    f"preview={str(raw_content)[:100] if raw_content else 'None'}"
                )
                content = raw_content
                # 确保 content 是字符串（Gemini 可能返回列表）
                if isinstance(content, list):
                    self.logger.logger.debug(f"[Planner.stream] Converting list with {len(content)} items to str")
                    content = "".join(str(c) for c in content)
                elif not isinstance(content, str):
                    self.logger.logger.debug(f"[Planner.stream] Converting {type(content).__name__} to str")
                    content = str(content)
                full_content += content
                yield ReasoningDeltaEvent(content=content, source="planner").to_dict()
                
            elif chunk["type"] == "complete":
                # 解析完整响应
                planner_output = self._parse_response(full_content)
                yield PlanCompleteEvent(planner_output=planner_output).to_dict()
                
            elif chunk["type"] == "error":
                yield {"type": "error", "content": chunk["content"]}
    
    def _prepare_screenshot(self, screenshot_path: str, log_dir: Optional[str]) -> str:
        """准备截图（调整大小）"""
        if not screenshot_path or not os.path.exists(screenshot_path):
            raise ValueError(f"截图文件不存在: {screenshot_path}")
        
        if log_dir:
            output_path = os.path.join(log_dir, "planner_screenshot.png")
        else:
            output_path = screenshot_path.replace(".png", "_resized.png")
        
        return resize_screenshot(screenshot_path, output_path, self.screen_max_side)
    
    def _build_user_prompt(
        self,
        task_description: str,
        milestone_objective: str,
        guidance_steps: List[str],
        history_md: str,
        knowledge_context: str,
        attached_files_content: str = "",
    ) -> str:
        """构建用户提示"""
        # 格式化指导步骤
        if guidance_steps:
            steps_str = "\n".join([f"Step [{i+1}]: {step}" for i, step in enumerate(guidance_steps)])
        else:
            steps_str = "No guidance steps provided. Use your best judgment."
        
        # 知识上下文部分
        knowledge_section = ""
        if knowledge_context:
            knowledge_section = f"External Knowledge:\n{knowledge_context}\n"
        
        return PLANNER_USER_PROMPT.format(
            task_description=task_description or "Complete the current milestone",
            history_md=history_md or "No previous actions.",
            attached_files_section=attached_files_content,
            milestone_objective=milestone_objective,
            knowledge_section=knowledge_section,
            guidance_steps=steps_str,
        )
    
    def _parse_response(self, response: str) -> PlannerOutput:
        """解析 LLM 响应为 PlannerOutput"""
        try:
            # 尝试解析 JSON
            parsed = self._extract_json(response)
            
            # 解析 Current Step
            current_step = 1
            step_explanation = ""
            current_step_raw = parsed.get("Current Step", "(1, '')")
            
            if isinstance(current_step_raw, str):
                # 格式: "(1, 'explanation')"
                try:
                    # 简单解析
                    content = current_step_raw.strip("()")
                    parts = content.split(",", 1)
                    current_step = int(parts[0].strip())
                    if len(parts) > 1:
                        step_explanation = parts[1].strip().strip("'\"")
                except (ValueError, IndexError):
                    pass
            elif isinstance(current_step_raw, (int, float)):
                current_step = int(current_step_raw)
            
            return PlannerOutput(
                observation=parsed.get("Observation", ""),
                reasoning=parsed.get("Reasoning", ""),
                next_action=parsed.get("Action") or "",
                current_step=current_step,
                step_explanation=step_explanation,
                expectation=parsed.get("Expectation", ""),
                is_milestone_completed=parsed.get("MilestoneCompleted", False),
                completion_summary=parsed.get("node_completion_summary"),
                output_filename=parsed.get("output_filename"),
                result_markdown=parsed.get("result_markdown"),
                step_memory=parsed.get("step_memory"),
            )
            
        except Exception as e:
            self.logger.logger.error(f"解析 Planner 响应失败: {e}")
            # 返回默认值
            return PlannerOutput(
                observation="Failed to parse response",
                reasoning=str(e),
                next_action="",
                is_milestone_completed=False,
            )
    
    def _extract_json(self, text: str) -> Dict[str, Any]:
        """从文本中提取 JSON"""
        text = text.strip()
        
        # 直接尝试解析
        if text.startswith("{"):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass
        
        # 尝试从 ```json 块中提取
        import re
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        # 尝试提取第一个 { 到最后一个 }
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
        
        raise ValueError(f"无法从响应中提取 JSON: {text[:200]}...")
