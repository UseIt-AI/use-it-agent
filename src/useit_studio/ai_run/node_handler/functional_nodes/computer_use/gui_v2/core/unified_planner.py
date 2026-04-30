"""
GUI Agent V2 - Unified Planner (Planner-Only 模式)

一次 LLM 调用同时完成规划和动作生成，实现 Planner-Only 架构。

优点：
- 减少 LLM 调用次数（1次 vs Planner+Actor 的 2次）
- 降低延迟和成本（减少一次图像传输）
- 上下文一致性更好（规划和动作在同一推理过程中完成）

包含两个实现：
- UnifiedPlanner: 有 guidance_steps（Teach Mode）
- UnifiedAutonomousPlanner: 无 guidance_steps（自主规划）
"""

import json
import os
from typing import Dict, Any, Optional, AsyncGenerator, List

from ..models import (
    UnifiedPlannerOutput, 
    ActionType, 
    CoordinateSystem,
    ReasoningDeltaEvent,
    PlanCompleteEvent,
    UnifiedCompleteEvent,
)
from ..utils.llm_client import VLMClient, LLMConfig
from ..utils.image_utils import resize_screenshot
from useit_studio.ai_run.utils.logger_utils import LoggerUtils


# ==================== Unified Planner Prompts (有 guidance_steps) ====================

UNIFIED_SYSTEM_PROMPT = """You are a helpful GUI automation agent for computer-use tasks on a {os_name} device.

You must perform TWO tasks in ONE response:
1. **Plan**: Analyze the screenshot and decide what action to take next
2. **Act**: Generate the precise action with exact coordinates/parameters

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

## Save Results (REQUIRED at completion)

When MilestoneCompleted=true, you MUST provide result output:
- `node_completion_summary`: Brief text summary (1-2 sentences)
- `result_markdown`: **REQUIRED** - The markdown report of this node's work
- `output_filename`: Descriptive filename ending in `.md`

## Coordinate System

Output coordinates in **normalized 0-1000 range**:
- (0, 0) = top-left corner
- (1000, 1000) = bottom-right corner
- To click center of a button at 50% width and 30% height, use x=500, y=300

## Action Types

- `click`: Single click at (x, y)
- `double_click`: Double click at (x, y)
- `type`: Type text (requires `text` field, no coordinates needed)
- `key`: Press key (requires `key` field, e.g., "enter", "tab", "escape", "ctrl+c")
- `scroll`: Scroll at (x, y) with scroll_x/scroll_y delta (positive scroll_y = scroll down)
- `move`: Move mouse to (x, y)
- `drag`: Drag from start to end; requires `path` (list of [x,y] points, at least 2, e.g. [[x1,y1],[x2,y2]])
- `wait`: Wait for a moment (use duration_ms)
- `stop`: Task completed, no action needed (use when MilestoneCompleted=true)"""


UNIFIED_USER_PROMPT = """Overall Task Goal: {task_description}

History Actions: 
{history_md}

{attached_files_section}

Current Milestone Objective: {milestone_objective}

{knowledge_section}
Guidance Trajectory Examples (within current milestone):
{guidance_steps}

## Output Format (JSON)

{{
    "Observation": str,           // Detailed observation of the current screenshot
    "Reasoning": str,             // Step-by-step reasoning about how to achieve the objective
    "Current Step": "(int, str)", // (step number, brief explanation)
    "Action": str | null,         // Natural language description of the action, OR null if completed
    "Expectation": str,           // Expected result after the action
    "MilestoneCompleted": bool,   // True ONLY if objective is ALREADY achieved
    "step_memory": str | null,    // Business data observed (NOT navigation state)
    "node_completion_summary": str | null,  // REQUIRED when MilestoneCompleted=true
    "result_markdown": str | null,          // REQUIRED when MilestoneCompleted=true
    "output_filename": str | null,          // REQUIRED when MilestoneCompleted=true
    
    // ACTION PARAMETERS (required when MilestoneCompleted=false)
    "action_type": str,           // click|double_click|type|key|scroll|move|drag|wait|stop
    "x": int | null,              // 0-1000 normalized X coordinate
    "y": int | null,              // 0-1000 normalized Y coordinate
    "text": str | null,           // Text to type (for type action)
    "key": str | null,            // Key name (for key action)
    "scroll_x": int | null,       // Horizontal scroll amount
    "scroll_y": int | null,       // Vertical scroll amount (positive = down)
    "path": list | null,          // Drag path: [[x1,y1],[x2,y2],...] at least 2 points (for drag action)
    "button": str | null          // Mouse button for click and drag: "left" (default) or "right"
}}

## CRITICAL RULES

1. **MilestoneCompleted + Action consistency:**
   - MilestoneCompleted=true AND Action=null AND action_type="stop": Goal ALREADY achieved
   - MilestoneCompleted=false AND Action="..." AND action_type="click|type|...": Action needed
   - NEVER set MilestoneCompleted=true with a non-stop action_type

2. **Coordinates:** Use normalized 0-1000 range. Identify the exact UI element center position.

3. **Follow Guidance:** Start from step 1 and complete step by step. DO NOT skip steps.

4. **One action at a time:** Only output ONE action per response.

Current Milestone Objective: {milestone_objective}

Based on the current screenshot, now start planning and generate the action:"""


# ==================== Unified Autonomous Planner Prompts (无 guidance_steps) ====================

UNIFIED_AUTONOMOUS_SYSTEM_PROMPT = """You are an autonomous GUI automation agent for computer-use tasks on a {os_name} device.

You are operating in **AUTONOMOUS MODE** - you must plan and act independently without pre-recorded guidance.

You must perform TWO tasks in ONE response:
1. **Plan**: Analyze the screenshot and decide what action to take next
2. **Act**: Generate the precise action with exact coordinates/parameters

## Step Memory

Use `step_memory` ONLY to record **business-critical data** you observe on the screen.

**When to use:**
- You found target data (names, IDs, values, search results, extracted info)
- Information that won't be visible in subsequent screenshots
- Data that needs to be aggregated across steps

**When NOT to use:**
- Navigation progress - this is already in action history
- UI state descriptions
- Plans or intentions for next steps

## Save Results (REQUIRED at completion)

When MilestoneCompleted=true, you MUST provide:
- `node_completion_summary`: Brief text summary (1-2 sentences)
- `result_markdown`: **REQUIRED** - The markdown report
- `output_filename`: Descriptive filename ending in `.md`

## Coordinate System

Output coordinates in **normalized 0-1000 range**:
- (0, 0) = top-left corner
- (1000, 1000) = bottom-right corner

## Action Types

- `click`: Single click at (x, y)
- `double_click`: Double click at (x, y)
- `type`: Type text (requires `text` field)
- `key`: Press key (requires `key` field)
- `scroll`: Scroll at (x, y) with scroll_x/scroll_y
- `move`: Move mouse to (x, y)
- `drag`: Drag from start to end; requires `path` (list of [x,y] points, at least 2, e.g. [[x1,y1],[x2,y2]])
- `wait`: Wait (use duration_ms)
- `stop`: Task completed"""


UNIFIED_AUTONOMOUS_USER_PROMPT = """Overall Task Goal: {task_description}

History Actions: 
{history_md}

{attached_files_section}

Current Milestone Objective: {milestone_objective}

{knowledge_section}

## Output Format (JSON)

{{
    "Observation": str,           // What you see on the screen
    "Reasoning": str,             // Your thought process
    "Action": str | null,         // Action description OR null if completed
    "Expectation": str,           // Expected result
    "MilestoneCompleted": bool,   // True ONLY if objective ALREADY achieved
    "step_memory": str | null,    // Business data observed
    "node_completion_summary": str | null,  // REQUIRED when MilestoneCompleted=true
    "result_markdown": str | null,          // REQUIRED when MilestoneCompleted=true
    "output_filename": str | null,          // REQUIRED when MilestoneCompleted=true
    
    // ACTION PARAMETERS
    "action_type": str,           // click|double_click|type|key|scroll|move|drag|wait|stop
    "x": int | null,              // 0-1000 normalized X coordinate
    "y": int | null,              // 0-1000 normalized Y coordinate
    "text": str | null,           // Text to type
    "key": str | null,            // Key name
    "scroll_x": int | null,       // Horizontal scroll
    "scroll_y": int | null,       // Vertical scroll (positive = down)
    "path": list | null,          // Drag path: [[x1,y1],[x2,y2],...] at least 2 points (for drag action)
    "button": str | null          // Mouse button for drag: "left" (default) or "right"
}}

## CRITICAL RULES

1. MilestoneCompleted=true AND action_type="stop": Goal ALREADY achieved
2. MilestoneCompleted=false AND action_type="click|type|...": Action needed
3. Consider history actions to avoid repeating failed attempts
4. Be specific about what element to interact with

Current Milestone Objective: {milestone_objective}

Based on the current screenshot, now start planning and generate the action:"""


class UnifiedPlannerBase:
    """Unified Planner 基类"""
    
    def __init__(
        self,
        model: str = "gemini-3-flash-preview",
        api_keys: Optional[Dict[str, str]] = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        screen_max_side: int = 1024,
        os_name: str = "Windows",
        node_id: str = "",
    ):
        self.os_name = os_name
        self.screen_max_side = screen_max_side
        self.node_id = node_id
        self.logger = LoggerUtils(component_name=self.__class__.__name__)
        
        # 初始化 VLM 客户端
        config = LLMConfig(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            role="unified_planner",
            node_id=node_id,
        )
        self.vlm = VLMClient(config=config, api_keys=api_keys, logger=self.logger)
    
    def set_node_id(self, node_id: str):
        """更新节点 ID"""
        self.node_id = node_id
        self.vlm.config.node_id = node_id
    
    def _prepare_screenshot(self, screenshot_path: str, log_dir: Optional[str]) -> str:
        """准备截图（调整大小）"""
        if not screenshot_path or not os.path.exists(screenshot_path):
            raise ValueError(f"截图文件不存在: {screenshot_path}")
        
        if log_dir:
            output_path = os.path.join(log_dir, "unified_planner_screenshot.png")
        else:
            output_path = screenshot_path.replace(".png", "_unified_resized.png")
        
        return resize_screenshot(screenshot_path, output_path, self.screen_max_side)
    
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
    
    def _parse_action_type(self, action_type_str: str) -> Optional[ActionType]:
        """解析动作类型"""
        if not action_type_str:
            return None
        
        action_type_str = action_type_str.lower().strip()
        
        # 映射表
        action_map = {
            "click": ActionType.CLICK,
            "double_click": ActionType.DOUBLE_CLICK,
            "doubleclick": ActionType.DOUBLE_CLICK,
            "type": ActionType.TYPE,
            "key": ActionType.KEY,
            "scroll": ActionType.SCROLL,
            "move": ActionType.MOVE,
            "drag": ActionType.DRAG,
            "wait": ActionType.WAIT,
            "stop": ActionType.STOP,
            "screenshot": ActionType.SCREENSHOT,
        }
        
        return action_map.get(action_type_str)
    
    def _parse_response(self, response: str) -> UnifiedPlannerOutput:
        """解析 LLM 响应为 UnifiedPlannerOutput"""
        try:
            parsed = self._extract_json(response)
            
            # 解析 Current Step
            current_step = 1
            step_explanation = ""
            current_step_raw = parsed.get("Current Step", "(1, '')")
            
            if isinstance(current_step_raw, str):
                try:
                    content = current_step_raw.strip("()")
                    parts = content.split(",", 1)
                    current_step = int(parts[0].strip())
                    if len(parts) > 1:
                        step_explanation = parts[1].strip().strip("'\"")
                except (ValueError, IndexError):
                    pass
            elif isinstance(current_step_raw, (int, float)):
                current_step = int(current_step_raw)
            
            # 解析动作类型
            action_type = self._parse_action_type(parsed.get("action_type", ""))
            
            # 如果 MilestoneCompleted=true 但没有 action_type，设置为 stop
            is_completed = parsed.get("MilestoneCompleted", False)
            if is_completed and action_type is None:
                action_type = ActionType.STOP
            
            # 解析 drag 专用字段
            path = parsed.get("path")
            button = parsed.get("button")
            
            # drag 校验：path 必须至少 2 个点，否则降级为 stop
            if action_type == ActionType.DRAG:
                if not path or not isinstance(path, list) or len(path) < 2:
                    self.logger.logger.warning(
                        f"[UnifiedPlanner] drag action 的 path 无效（至少需要 2 个点，收到: {path}），降级为 stop"
                    )
                    action_type = ActionType.STOP
                    path = None
            
            return UnifiedPlannerOutput(
                # 规划部分
                observation=parsed.get("Observation", ""),
                reasoning=parsed.get("Reasoning", ""),
                next_action_description=parsed.get("Action") or "",
                current_step=current_step,
                step_explanation=step_explanation,
                expectation=parsed.get("Expectation", ""),
                is_milestone_completed=is_completed,
                completion_summary=parsed.get("node_completion_summary"),
                output_filename=parsed.get("output_filename"),
                result_markdown=parsed.get("result_markdown"),
                step_memory=parsed.get("step_memory"),
                # 动作部分
                action_type=action_type,
                x=parsed.get("x"),
                y=parsed.get("y"),
                text=parsed.get("text"),
                key=parsed.get("key"),
                scroll_x=parsed.get("scroll_x", 0) or 0,
                scroll_y=parsed.get("scroll_y", 0) or 0,
                duration_ms=parsed.get("duration_ms", 0) or 0,
                coordinate_system=CoordinateSystem.NORMALIZED_1000,
                path=path,
                button=button,
            )
            
        except Exception as e:
            self.logger.logger.error(f"解析 UnifiedPlanner 响应失败: {e}")
            return UnifiedPlannerOutput(
                observation="Failed to parse response",
                reasoning=str(e),
                next_action_description="",
                is_milestone_completed=False,
                action_type=ActionType.STOP,
            )


class UnifiedPlanner(UnifiedPlannerBase):
    """
    Unified Planner - 有 guidance_steps 的 Planner-Only 模式
    
    适用于有录制轨迹的 Teach Mode 场景。
    """
    
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
    ) -> UnifiedPlannerOutput:
        """
        非流式规划 + 动作生成
        
        Returns:
            UnifiedPlannerOutput 包含规划和动作
        """
        self.logger.logger.info("[UnifiedPlanner] 开始规划 (Teach Mode)")
        
        # 准备截图
        resized_path = self._prepare_screenshot(screenshot_path, log_dir)
        
        # 构建 prompt
        system_prompt = UNIFIED_SYSTEM_PROMPT.format(os_name=self.os_name)
        user_prompt = self._build_prompt(
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
        流式规划 + 动作生成
        
        Yields:
            ReasoningDeltaEvent - 推理过程增量
            PlanCompleteEvent - 规划完成（兼容）
            UnifiedCompleteEvent - 包含完整输出
        """
        self.logger.logger.info("[UnifiedPlanner] 开始流式规划 (Teach Mode)")
        
        # 发送模式信息
        yield {
            "type": "status",
            "content": "Planning in unified mode (with guidance)...",
            "mode": "unified",
        }
        
        # 准备截图
        resized_path = self._prepare_screenshot(screenshot_path, log_dir)
        
        # 构建 prompt
        system_prompt = UNIFIED_SYSTEM_PROMPT.format(os_name=self.os_name)
        user_prompt = self._build_prompt(
            task_description=task_description,
            milestone_objective=milestone_objective,
            guidance_steps=guidance_steps,
            history_md=history_md,
            knowledge_context=knowledge_context,
            attached_files_content=attached_files_content,
        )
        
        full_content = ""
        token_usage = {}
        
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
                yield ReasoningDeltaEvent(content=content, source="unified_planner").to_dict()
                
            elif chunk["type"] == "complete":
                token_usage = chunk.get("token_usage", {})
                unified_output = self._parse_response(full_content)
                
                # 发送 plan_complete 事件（兼容现有前端）
                yield PlanCompleteEvent(
                    planner_output=unified_output.to_planner_output()
                ).to_dict()
                
                # 发送 unified_complete 事件（包含完整输出）
                yield UnifiedCompleteEvent(
                    unified_output=unified_output,
                    token_usage=token_usage,
                ).to_dict()
                
            elif chunk["type"] == "error":
                yield {"type": "error", "content": chunk["content"]}
    
    def _build_prompt(
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
        
        return UNIFIED_USER_PROMPT.format(
            task_description=task_description or "Complete the current milestone",
            history_md=history_md or "No previous actions.",
            attached_files_section=attached_files_content,
            milestone_objective=milestone_objective,
            knowledge_section=knowledge_section,
            guidance_steps=steps_str,
        )


class UnifiedAutonomousPlanner(UnifiedPlannerBase):
    """
    Unified Autonomous Planner - 无 guidance_steps 的 Planner-Only 模式
    
    适用于完全自主规划的场景。
    """
    
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
    ) -> UnifiedPlannerOutput:
        """
        非流式规划 + 动作生成
        
        Returns:
            UnifiedPlannerOutput 包含规划和动作
        """
        self.logger.logger.info("[UnifiedAutonomousPlanner] 开始自主规划")
        
        # 准备截图
        resized_path = self._prepare_screenshot(screenshot_path, log_dir)
        
        # 构建 prompt
        system_prompt = UNIFIED_AUTONOMOUS_SYSTEM_PROMPT.format(os_name=self.os_name)
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
        流式规划 + 动作生成
        
        Yields:
            ReasoningDeltaEvent - 推理过程增量
            PlanCompleteEvent - 规划完成（兼容）
            UnifiedCompleteEvent - 包含完整输出
        """
        self.logger.logger.info("[UnifiedAutonomousPlanner] 开始流式自主规划")
        
        # 发送模式信息
        yield {
            "type": "status",
            "content": "Planning in unified autonomous mode...",
            "mode": "unified_autonomous",
        }
        
        # 准备截图
        resized_path = self._prepare_screenshot(screenshot_path, log_dir)
        
        # 构建 prompt
        system_prompt = UNIFIED_AUTONOMOUS_SYSTEM_PROMPT.format(os_name=self.os_name)
        user_prompt = self._build_prompt(
            task_description=task_description,
            milestone_objective=milestone_objective,
            history_md=history_md,
            knowledge_context=knowledge_context,
            attached_files_content=attached_files_content,
        )
        
        full_content = ""
        token_usage = {}
        
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
                yield ReasoningDeltaEvent(content=content, source="unified_autonomous_planner").to_dict()
                
            elif chunk["type"] == "complete":
                token_usage = chunk.get("token_usage", {})
                unified_output = self._parse_response(full_content)
                
                # 发送 plan_complete 事件（兼容现有前端）
                yield PlanCompleteEvent(
                    planner_output=unified_output.to_planner_output()
                ).to_dict()
                
                # 发送 unified_complete 事件（包含完整输出）
                yield UnifiedCompleteEvent(
                    unified_output=unified_output,
                    token_usage=token_usage,
                ).to_dict()
                
            elif chunk["type"] == "error":
                yield {"type": "error", "content": chunk["content"]}
    
    def _build_prompt(
        self,
        task_description: str,
        milestone_objective: str,
        history_md: str,
        knowledge_context: str,
        attached_files_content: str = "",
    ) -> str:
        """构建用户提示"""
        # 知识上下文部分
        knowledge_section = ""
        if knowledge_context:
            knowledge_section = f"External Knowledge:\n{knowledge_context}\n"
        
        return UNIFIED_AUTONOMOUS_USER_PROMPT.format(
            task_description=task_description or "Complete the current milestone",
            history_md=history_md or "No previous actions.",
            attached_files_section=attached_files_content,
            milestone_objective=milestone_objective,
            knowledge_section=knowledge_section,
        )


# ==================== 工厂函数 ====================

def create_unified_planner(
    model: str = "gemini-3-flash-preview",
    api_keys: Optional[Dict[str, str]] = None,
    has_guidance: bool = True,
    **kwargs
) -> UnifiedPlannerBase:
    """
    创建 UnifiedPlanner 的工厂函数
    
    Args:
        model: 使用的模型
        api_keys: API 密钥
        has_guidance: 是否有 guidance_steps
        **kwargs: 其他参数
        
    Returns:
        UnifiedPlanner 或 UnifiedAutonomousPlanner 实例
    """
    if has_guidance:
        return UnifiedPlanner(model=model, api_keys=api_keys, **kwargs)
    else:
        return UnifiedAutonomousPlanner(model=model, api_keys=api_keys, **kwargs)
