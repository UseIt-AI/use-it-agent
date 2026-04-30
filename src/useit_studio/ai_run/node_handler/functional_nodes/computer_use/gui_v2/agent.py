"""
GUI Agent V2 - Agent 主流程

Agent 是 Planner 和 Actor 的协调者：
1. 接收任务上下文
2. 调用 Planner 进行规划
3. 如果任务未完成，调用 Actor 执行
4. 返回执行结果

这是 GUI Agent 的核心入口点。

Planner 选择策略：
- "unified_auto"（默认）: Planner-Only 模式，一次调用完成规划和动作生成
  - 有 guidance_steps -> 使用 UnifiedPlanner
  - 无 guidance_steps -> 使用 UnifiedAutonomousPlanner
- "unified": 强制使用 UnifiedPlanner（有 guidance，Planner-Only）
- "unified_autonomous": 强制使用 UnifiedAutonomousPlanner（无 guidance，Planner-Only）
- "auto": 传统模式，Planner + Actor 两次调用
- "default": 强制使用原始 Planner（Teach Mode，需要 guidance_steps）
- "autonomous": 强制使用 AutonomousPlanner（自主规划，不需要 guidance_steps）
"""

from typing import Dict, Any, Optional, AsyncGenerator, List, Union
from enum import Enum

from .models import (
    NodeContext,
    AgentStep,
    PlannerOutput,
    DeviceAction,
    ActionType,
    ReasoningDeltaEvent,
    PlanCompleteEvent,
    ActionEvent,
    StepCompleteEvent,
    ErrorEvent,
    UnifiedPlannerOutput,
)
from .core.planner import Planner
from .core.actor import Actor
from .core.intent_refiner import IntentRefiner, CompletionSummarizer
from .core.autonomous_planner import AutonomousPlanner
from .core.unified_planner import UnifiedPlanner, UnifiedAutonomousPlanner
from useit_studio.ai_run.utils.logger_utils import LoggerUtils


class PlannerType(str, Enum):
    """Planner 类型枚举"""
    AUTO = "auto"  # 自动选择：有 guidance 用 Planner，无 guidance 用 AutonomousPlanner
    DEFAULT = "default"  # 原始 Planner（Teach Mode，需要 guidance_steps）
    AUTONOMOUS = "autonomous"  # AutonomousPlanner（自主规划，不需要 guidance_steps）
    
    # Planner-Only 模式（一次调用完成规划和动作生成）
    UNIFIED = "unified"  # Unified Planner（有 guidance，Planner-Only）
    UNIFIED_AUTO = "unified_auto"  # Unified Auto（根据 guidance 自动选择 Unified Planner）
    UNIFIED_AUTONOMOUS = "unified_autonomous"  # Unified Autonomous（无 guidance，Planner-Only）
    
    # 向后兼容别名
    TEACH_MODE = "autonomous"  # 旧名称，等同于 AUTONOMOUS


class GUIAgent:
    """
    GUI Agent - Computer Use Agent 的核心实现
    
    职责：
    1. 协调 Planner 和 Actor
    2. 管理单步执行流程
    3. 提供流式输出接口
    
    使用方式：
        agent = GUIAgent(api_keys={"OPENAI_API_KEY": "..."})
        
        # 流式执行
        async for event in agent.step_streaming(context, screenshot_path):
            print(event)
        
        # 非流式执行
        result = await agent.step(context, screenshot_path)
        
        # Planner-Only 模式（一次调用）
        agent = GUIAgent(planner_type="unified_auto")
    """
    
    def __init__(
        self,
        planner_model: str = "gemini-3-flash-preview",
        actor_model: str = "gemini-3-flash-preview",
        api_keys: Optional[Dict[str, str]] = None,
        os_name: str = "Windows",
        screen_max_side: int = 1024,
        enable_intent_refiner: bool = False,
        enable_completion_summary: bool = True,
        node_id: str = "",  # 用于日志标识
        actor_streaming: bool = False,  # Actor 是否使用流式输出，默认关闭
        planner_type: Union[str, PlannerType] = PlannerType.UNIFIED_AUTO,  # Planner 类型，默认 Planner-Only 模式
    ):
        """
        初始化 GUI Agent
        
        Args:
            planner_model: Planner 使用的模型
            actor_model: Actor 使用的模型（Planner-Only 模式下不使用）
            api_keys: API 密钥字典
            os_name: 操作系统名称
            screen_max_side: 截图最大边长
            enable_intent_refiner: 是否启用意图细化器（用于循环场景）
            enable_completion_summary: 是否启用完成摘要生成
            node_id: 节点 ID（用于日志标识）
            actor_streaming: Actor 是否使用流式输出（默认 False，直接返回结果更稳定）
            planner_type: Planner 类型
                - "auto" / PlannerType.AUTO: 自动选择（有 guidance 用 Planner，无则用 AutonomousPlanner）
                - "default" / PlannerType.DEFAULT: 原始 Planner（Teach Mode，需要 guidance_steps）
                - "autonomous" / PlannerType.AUTONOMOUS: AutonomousPlanner（自主规划）
                - "unified" / PlannerType.UNIFIED: Unified Planner（有 guidance，Planner-Only）
                - "unified_auto" / PlannerType.UNIFIED_AUTO: Unified Auto（自动选择，Planner-Only）
                - "unified_autonomous" / PlannerType.UNIFIED_AUTONOMOUS: Unified Autonomous（无 guidance，Planner-Only）
        """
        self.logger = LoggerUtils(component_name="GUIAgent")
        self.api_keys = api_keys
        self.planner_model = planner_model
        self.os_name = os_name
        self.screen_max_side = screen_max_side
        self.enable_intent_refiner = enable_intent_refiner
        self.enable_completion_summary = enable_completion_summary
        self.node_id = node_id
        self.actor_streaming = actor_streaming
        
        # 解析 planner_type
        if isinstance(planner_type, str):
            try:
                planner_type = PlannerType(planner_type)
            except ValueError:
                self.logger.logger.warning(f"未知的 planner_type: {planner_type}，使用默认值 auto")
                planner_type = PlannerType.AUTO
        self.planner_type = planner_type
        
        # 判断是否是 Planner-Only 模式
        self.is_unified_mode = planner_type in (
            PlannerType.UNIFIED, 
            PlannerType.UNIFIED_AUTO, 
            PlannerType.UNIFIED_AUTONOMOUS
        )
        
        # 初始化 Planner（根据模式）
        self._default_planner: Optional[Planner] = None
        self._autonomous_planner: Optional[AutonomousPlanner] = None
        self._unified_planner: Optional[UnifiedPlanner] = None
        self._unified_autonomous_planner: Optional[UnifiedAutonomousPlanner] = None
        
        if planner_type == PlannerType.DEFAULT:
            self._default_planner = Planner(
                model=planner_model,
                api_keys=api_keys,
                os_name=os_name,
                screen_max_side=screen_max_side,
                node_id=node_id,
            )
        elif planner_type in (PlannerType.AUTONOMOUS, PlannerType.TEACH_MODE):
            self._autonomous_planner = AutonomousPlanner(
                model=planner_model,
                api_keys=api_keys,
                os_name=os_name,
                screen_max_side=screen_max_side,
                node_id=node_id,
            )
        elif planner_type == PlannerType.UNIFIED:
            self._unified_planner = UnifiedPlanner(
                model=planner_model,
                api_keys=api_keys,
                os_name=os_name,
                screen_max_side=screen_max_side,
                node_id=node_id,
            )
        elif planner_type == PlannerType.UNIFIED_AUTONOMOUS:
            self._unified_autonomous_planner = UnifiedAutonomousPlanner(
                model=planner_model,
                api_keys=api_keys,
                os_name=os_name,
                screen_max_side=screen_max_side,
                node_id=node_id,
            )
        # AUTO 和 UNIFIED_AUTO 模式：延迟初始化，按需创建
        
        # 初始化 Actor（Planner-Only 模式下不需要）
        self.actor: Optional[Actor] = None
        if not self.is_unified_mode:
            self.actor = Actor(
                model=actor_model,
                api_keys=api_keys,
                os_name=os_name,
                screen_max_side=screen_max_side,
                node_id=node_id,
            )
        
        # 可选组件（按需初始化，带节点 ID）
        self.intent_refiner: Optional[IntentRefiner] = None
        self.completion_summarizer: Optional[CompletionSummarizer] = None
        
        if enable_intent_refiner:
            self.intent_refiner = IntentRefiner(
                model=planner_model,
                api_keys=api_keys,
                node_id=node_id,
            )
        
        if enable_completion_summary:
            self.completion_summarizer = CompletionSummarizer(
                model=planner_model,
                api_keys=api_keys,
                node_id=node_id,
            )
        
        mode_desc = "Planner-Only" if self.is_unified_mode else "Planner+Actor"
        self.logger.logger.info(
            f"[GUIAgent] 初始化完成 - Mode: {mode_desc}, PlannerType: {planner_type.value}, "
            f"Planner: {planner_model}, Actor: {actor_model if not self.is_unified_mode else 'N/A'}, "
            f"IntentRefiner: {enable_intent_refiner}, CompletionSummary: {enable_completion_summary}"
        )
    
    def _has_valid_guidance_steps(self, guidance_steps: List[str]) -> bool:
        """检查是否有有效的 guidance_steps"""
        if not guidance_steps:
            return False
        # 过滤掉空字符串
        valid_steps = [s for s in guidance_steps if s and s.strip()]
        return len(valid_steps) > 0
    
    def _get_planner(self, guidance_steps: List[str]) -> Union[Planner, AutonomousPlanner]:
        """
        根据 planner_type 和 guidance_steps 获取合适的 Planner（传统模式）
        
        AUTO 模式逻辑：
        - 有 guidance_steps -> 使用原始 Planner（更精确地跟踪步骤）
        - 无 guidance_steps -> 使用 AutonomousPlanner（自主规划）
        """
        if self.planner_type == PlannerType.DEFAULT:
            if self._default_planner is None:
                self._default_planner = Planner(
                    model=self.planner_model,
                    api_keys=self.api_keys,
                    os_name=self.os_name,
                    screen_max_side=self.screen_max_side,
                    node_id=self.node_id,
                )
            return self._default_planner
        
        elif self.planner_type in (PlannerType.AUTONOMOUS, PlannerType.TEACH_MODE):
            if self._autonomous_planner is None:
                self._autonomous_planner = AutonomousPlanner(
                    model=self.planner_model,
                    api_keys=self.api_keys,
                    os_name=self.os_name,
                    screen_max_side=self.screen_max_side,
                    node_id=self.node_id,
                )
            return self._autonomous_planner
        
        else:  # AUTO 模式
            has_guidance = self._has_valid_guidance_steps(guidance_steps)
            
            if has_guidance:
                # 有 guidance -> 使用原始 Planner
                if self._default_planner is None:
                    self._default_planner = Planner(
                        model=self.planner_model,
                        api_keys=self.api_keys,
                        os_name=self.os_name,
                        screen_max_side=self.screen_max_side,
                        node_id=self.node_id,
                    )
                self.logger.logger.info("[GUIAgent] AUTO 模式：检测到 guidance_steps，使用原始 Planner")
                return self._default_planner
            else:
                # 无 guidance -> 使用 AutonomousPlanner
                if self._autonomous_planner is None:
                    self._autonomous_planner = AutonomousPlanner(
                        model=self.planner_model,
                        api_keys=self.api_keys,
                        os_name=self.os_name,
                        screen_max_side=self.screen_max_side,
                        node_id=self.node_id,
                    )
                self.logger.logger.info("[GUIAgent] AUTO 模式：无 guidance_steps，使用 AutonomousPlanner")
                return self._autonomous_planner
    
    def _get_unified_planner(self, guidance_steps: List[str]) -> Union[UnifiedPlanner, UnifiedAutonomousPlanner]:
        """
        根据 planner_type 和 guidance_steps 获取合适的 Unified Planner（Planner-Only 模式）
        
        UNIFIED_AUTO 模式逻辑：
        - 有 guidance_steps -> 使用 UnifiedPlanner
        - 无 guidance_steps -> 使用 UnifiedAutonomousPlanner
        """
        if self.planner_type == PlannerType.UNIFIED:
            if self._unified_planner is None:
                self._unified_planner = UnifiedPlanner(
                    model=self.planner_model,
                    api_keys=self.api_keys,
                    os_name=self.os_name,
                    screen_max_side=self.screen_max_side,
                    node_id=self.node_id,
                )
            return self._unified_planner
        
        elif self.planner_type == PlannerType.UNIFIED_AUTONOMOUS:
            if self._unified_autonomous_planner is None:
                self._unified_autonomous_planner = UnifiedAutonomousPlanner(
                    model=self.planner_model,
                    api_keys=self.api_keys,
                    os_name=self.os_name,
                    screen_max_side=self.screen_max_side,
                    node_id=self.node_id,
                )
            return self._unified_autonomous_planner
        
        else:  # UNIFIED_AUTO 模式
            has_guidance = self._has_valid_guidance_steps(guidance_steps)
            
            if has_guidance:
                # 有 guidance -> 使用 UnifiedPlanner
                if self._unified_planner is None:
                    self._unified_planner = UnifiedPlanner(
                        model=self.planner_model,
                        api_keys=self.api_keys,
                        os_name=self.os_name,
                        screen_max_side=self.screen_max_side,
                        node_id=self.node_id,
                    )
                self.logger.logger.info("[GUIAgent] UNIFIED_AUTO 模式：检测到 guidance_steps，使用 UnifiedPlanner")
                return self._unified_planner
            else:
                # 无 guidance -> 使用 UnifiedAutonomousPlanner
                if self._unified_autonomous_planner is None:
                    self._unified_autonomous_planner = UnifiedAutonomousPlanner(
                        model=self.planner_model,
                        api_keys=self.api_keys,
                        os_name=self.os_name,
                        screen_max_side=self.screen_max_side,
                        node_id=self.node_id,
                    )
                self.logger.logger.info("[GUIAgent] UNIFIED_AUTO 模式：无 guidance_steps，使用 UnifiedAutonomousPlanner")
                return self._unified_autonomous_planner
    
    def set_node_id(self, node_id: str):
        """
        更新节点 ID（用于日志）
        
        在执行不同节点时调用此方法更新日志标识。
        """
        self.node_id = node_id
        if self._default_planner:
            self._default_planner.set_node_id(node_id)
        if self._autonomous_planner:
            self._autonomous_planner.set_node_id(node_id)
        if self._unified_planner:
            self._unified_planner.set_node_id(node_id)
        if self._unified_autonomous_planner:
            self._unified_autonomous_planner.set_node_id(node_id)
        if self.actor:
            self.actor.set_node_id(node_id)
        if self.intent_refiner:
            self.intent_refiner.set_node_id(node_id)
        if self.completion_summarizer:
            self.completion_summarizer.set_node_id(node_id)
    
    async def refine_intent(
        self,
        context: NodeContext,
        log_dir: Optional[str] = None,
    ) -> str:
        """
        细化里程碑意图（用于循环场景）
        
        Args:
            context: 节点上下文
            log_dir: 日志目录
            
        Returns:
            细化后的目的描述
        """
        if not self.intent_refiner:
            # 如果未启用，直接返回原始目标
            return context.milestone_objective
        
        return await self.intent_refiner.refine(
            original_description=context.milestone_objective,
            milestone_title=context.node_id,
            overall_task=context.task_description,
            history_md=context.history_md,
            guidance_steps=context.guidance_steps,
            loop_context=context.loop_context,
            log_dir=log_dir,
        )
    
    async def generate_completion_summary(
        self,
        context: NodeContext,
        action_history: List[str] = None,
        log_dir: Optional[str] = None,
    ) -> str:
        """
        生成完成摘要
        
        Args:
            context: 节点上下文
            action_history: 执行的动作历史（如果为 None，会尝试从 context.history_md 解析）
            log_dir: 日志目录
            
        Returns:
            一句话摘要
        """
        if not self.completion_summarizer:
            return f"Completed: {context.milestone_objective}"
        
        # 如果没有传入 action_history，尝试从 history_md 解析
        if action_history is None and context.history_md:
            # history_md 是 Markdown 格式，直接作为字符串传递
            # CompletionSummarizer 会处理
            action_history = [context.history_md]
        
        return await self.completion_summarizer.summarize(
            milestone_description=context.milestone_objective,
            overall_task=context.task_description,
            guidance_steps=context.guidance_steps,
            action_history=action_history,
            log_dir=log_dir,
        )
    
    async def step(
        self,
        context: NodeContext,
        screenshot_path: str,
        log_dir: Optional[str] = None,
        action_history: List[str] = None,
    ) -> AgentStep:
        """
        执行单步（非流式）
        
        Args:
            context: 节点上下文
            screenshot_path: 当前截图路径
            log_dir: 日志目录
            action_history: 当前节点的动作历史（用于生成完成摘要）
            
        Returns:
            AgentStep 包含完整的执行结果
        """
        self.logger.logger.info(f"[GUIAgent] 开始执行步骤 - Node: {context.node_id}, Unified: {self.is_unified_mode}")
        
        total_token_usage: Dict[str, int] = {}
        
        try:
            # Step 0: 如果启用了意图细化且在循环中，先细化目标
            milestone_objective = context.milestone_objective
            if self.enable_intent_refiner and context.loop_context:
                milestone_objective = await self.refine_intent(context, log_dir)
                self.logger.logger.info(f"[GUIAgent] 意图细化完成: {milestone_objective[:100]}...")
            
            # ========== Planner-Only 模式 ==========
            if self.is_unified_mode:
                return await self._step_unified(
                    context=context,
                    screenshot_path=screenshot_path,
                    milestone_objective=milestone_objective,
                    log_dir=log_dir,
                    action_history=action_history,
                )
            
            # ========== 传统模式：Planner + Actor ==========
            # Step 1: 获取合适的 Planner 并规划
            planner = self._get_planner(context.guidance_steps)
            planner_output = await planner.plan(
                screenshot_path=screenshot_path,
                task_description=context.task_description,
                milestone_objective=milestone_objective,
                guidance_steps=context.guidance_steps,
                history_md=context.history_md,
                knowledge_context=context.knowledge_context,
                log_dir=log_dir,
                attached_files_content=context.attached_files_content,
                attached_images_base64=context.attached_images,
            )
            
            self.logger.logger.info(
                f"[GUIAgent] Planner 完成 - MilestoneCompleted: {planner_output.is_milestone_completed}"
            )
            
            # 如果里程碑已完成
            if planner_output.is_milestone_completed:
                # 生成完成摘要
                completion_summary = None
                if self.enable_completion_summary:
                    completion_summary = await self.generate_completion_summary(
                        context, action_history, log_dir
                    )
                    planner_output.completion_summary = completion_summary
                
                return AgentStep(
                    planner_output=planner_output,
                    device_action=DeviceAction.stop(),
                    reasoning_text="Milestone completed",
                    token_usage=total_token_usage,
                )
            
            # Step 2: Actor 执行
            device_action, actor_reasoning, actor_tokens = await self.actor.act(
                instruction=planner_output.next_action,
                screenshot_path=screenshot_path,
                log_dir=log_dir,
                attached_images_base64=context.attached_images,
            )
            
            # 合并 token 使用
            for model, tokens in actor_tokens.items():
                total_token_usage[model] = total_token_usage.get(model, 0) + tokens
            
            self.logger.logger.info(
                f"[GUIAgent] Actor 完成 - Action: {device_action.action_type.value}"
            )
            
            return AgentStep(
                planner_output=planner_output,
                device_action=device_action,
                reasoning_text=actor_reasoning,
                token_usage=total_token_usage,
            )
            
        except Exception as e:
            self.logger.logger.error(f"[GUIAgent] 执行失败: {e}")
            return AgentStep(
                planner_output=PlannerOutput(
                    observation="Error occurred",
                    reasoning=str(e),
                    next_action="",
                    is_milestone_completed=False,
                ),
                error=str(e),
                token_usage=total_token_usage,
            )
    
    async def _step_unified(
        self,
        context: NodeContext,
        screenshot_path: str,
        milestone_objective: str,
        log_dir: Optional[str] = None,
        action_history: List[str] = None,
    ) -> AgentStep:
        """
        Planner-Only 模式的单步执行
        
        一次 LLM 调用完成规划和动作生成。
        """
        total_token_usage: Dict[str, int] = {}
        
        # 获取合适的 Unified Planner
        planner = self._get_unified_planner(context.guidance_steps)
        
        # 一次调用完成规划和动作生成
        unified_output = await planner.plan(
            screenshot_path=screenshot_path,
            task_description=context.task_description,
            milestone_objective=milestone_objective,
            guidance_steps=context.guidance_steps,
            history_md=context.history_md,
            knowledge_context=context.knowledge_context,
            log_dir=log_dir,
            attached_files_content=context.attached_files_content,
            attached_images_base64=context.attached_images,
        )
        
        self.logger.logger.info(
            f"[GUIAgent] UnifiedPlanner 完成 - MilestoneCompleted: {unified_output.is_milestone_completed}, "
            f"ActionType: {unified_output.action_type.value if unified_output.action_type else 'None'}"
        )
        
        # 转换为 PlannerOutput 和 DeviceAction
        planner_output = unified_output.to_planner_output()
        device_action = unified_output.to_device_action()
        
        # 如果里程碑已完成，生成完成摘要
        if unified_output.is_milestone_completed:
            if self.enable_completion_summary and not planner_output.completion_summary:
                completion_summary = await self.generate_completion_summary(
                    context, action_history, log_dir
                )
                planner_output.completion_summary = completion_summary
            
            # 确保返回 stop 动作
            if device_action is None:
                device_action = DeviceAction.stop()
        
        return AgentStep(
            planner_output=planner_output,
            device_action=device_action,
            reasoning_text=unified_output.reasoning,
            token_usage=total_token_usage,
        )
    
    async def step_streaming(
        self,
        context: NodeContext,
        screenshot_path: str,
        log_dir: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行单步（流式）
        
        Yields:
            各种事件字典:
            - {"type": "reasoning_delta", "content": str, "source": "planner"|"actor"|"unified_planner"}
            - {"type": "plan_complete", "content": {...}}
            - {"type": "action", "action": {...}}
            - {"type": "step_complete", "content": {...}}
            - {"type": "error", "content": str}
        """
        self.logger.logger.info(f"[GUIAgent] 开始流式执行 - Node: {context.node_id}, Unified: {self.is_unified_mode}")
        
        # ========== Planner-Only 模式 ==========
        if self.is_unified_mode:
            async for event in self._step_streaming_unified(context, screenshot_path, log_dir):
                yield event
            return
        
        # ========== 传统模式：Planner + Actor ==========
        total_token_usage: Dict[str, int] = {}
        planner_output: Optional[PlannerOutput] = None
        device_action: Optional[DeviceAction] = None
        actor_reasoning = ""
        
        try:
            # Step 1: 获取合适的 Planner 并流式规划
            planner = self._get_planner(context.guidance_steps)
            yield {"type": "status", "content": "Start planning..."}
            
            async for event in planner.plan_streaming(
                screenshot_path=screenshot_path,
                task_description=context.task_description,
                milestone_objective=context.milestone_objective,
                guidance_steps=context.guidance_steps,
                history_md=context.history_md,
                knowledge_context=context.knowledge_context,
                log_dir=log_dir,
                attached_files_content=context.attached_files_content,
                attached_images_base64=context.attached_images,
            ):
                yield event
                
                # 捕获 plan_complete 事件
                if event.get("type") == "plan_complete":
                    content = event.get("content", {})
                    planner_output = PlannerOutput(
                        observation=content.get("Observation", ""),
                        reasoning=content.get("Reasoning", ""),
                        next_action=content.get("Action") or "",
                        current_step=content.get("Current Step", 1),
                        step_explanation=content.get("Current Step Reason", ""),
                        expectation=content.get("Expectation", ""),
                        is_milestone_completed=content.get("MilestoneCompleted", False),
                    )
            
            if not planner_output:
                yield ErrorEvent(message="Planner 未返回有效结果").to_dict()
                return
            
            # 验证 MilestoneCompleted 和 Action 的一致性
            # 规则：MilestoneCompleted=true 时 Action 必须为空，否则强制修正
            has_action = bool(planner_output.next_action and planner_output.next_action.strip())
            
            if planner_output.is_milestone_completed and has_action:
                # 矛盾情况：声称完成但还有 Action
                # 强制修正：设置为未完成，继续执行 Action
                self.logger.logger.warning(
                    f"[GUIAgent] 检测到矛盾：MilestoneCompleted=true 但 Action 不为空。"
                    f"强制设置 MilestoneCompleted=false，继续执行 Action: {planner_output.next_action[:50]}..."
                )
                planner_output.is_milestone_completed = False
            
            # 如果里程碑已完成且没有 Action，直接返回（跳过 Actor）
            if planner_output.is_milestone_completed and not has_action:
                self.logger.logger.info("[GUIAgent] 里程碑已完成且无 Action，跳过 Actor")
                
                # 生成完成摘要
                if self.enable_completion_summary:
                    try:
                        completion_summary = await self.generate_completion_summary(
                            context, action_history=None, log_dir=log_dir
                        )
                        planner_output.completion_summary = completion_summary
                        self.logger.logger.info(f"[GUIAgent] 生成完成摘要: {completion_summary}")
                    except Exception as e:
                        self.logger.logger.warning(f"[GUIAgent] 生成完成摘要失败: {e}")
                        planner_output.completion_summary = f"Completed: {context.milestone_objective}"
                
                device_action = DeviceAction.stop()
                yield ActionEvent(action=device_action).to_dict()
                yield StepCompleteEvent(
                    step=AgentStep(
                        planner_output=planner_output,
                        device_action=device_action,
                        reasoning_text="Milestone completed - no action needed",
                        token_usage=total_token_usage,
                    )
                ).to_dict()
                return
            
            # Step 2: Actor 执行（只有当需要执行 Action 时才调用）
            print(f"[GUIAgent DEBUG] 准备执行 Actor, planner_output.is_milestone_completed={planner_output.is_milestone_completed}, has_action={has_action}, next_action={planner_output.next_action[:100] if planner_output.next_action else 'None'}")
            yield {"type": "status", "content": "Start generating action..."}
            
            if self.actor_streaming:
                # 流式执行 Actor
                async for event in self.actor.act_streaming(
                    instruction=planner_output.next_action,
                    screenshot_path=screenshot_path,
                    log_dir=log_dir,
                    attached_images_base64=context.attached_images,
                ):
                    yield event
                    
                    # 捕获 actor_complete 事件
                    if event.get("type") == "actor_complete":
                        action_dict = event.get("action", {})
                        
                        action_type_str = action_dict.get("type", "stop")
                        try:
                            action_type = ActionType(action_type_str)
                        except ValueError:
                            action_type = ActionType.STOP
                        
                        coord = action_dict.get("coordinate", [None, None])
                        device_action = DeviceAction(
                            action_type=action_type,
                            x=coord[0] if len(coord) > 0 else None,
                            y=coord[1] if len(coord) > 1 else None,
                            text=action_dict.get("text"),
                            key=action_dict.get("key"),
                        )
                        actor_reasoning = event.get("reasoning", "")
                        
                        # 合并 token 使用
                        actor_tokens = event.get("token_usage", {})
                        for model, tokens in actor_tokens.items():
                            total_token_usage[model] = total_token_usage.get(model, 0) + tokens
                    
                    # 捕获错误事件
                    elif event.get("type") == "error":
                        yield ErrorEvent(message=event.get("content", "Actor error")).to_dict()
                        return
            else:
                # 非流式执行 Actor（默认，更稳定）
                try:
                    print(f"[GUIAgent DEBUG] 开始非流式 Actor 执行")
                    device_action, actor_reasoning, actor_tokens = await self.actor.act(
                        instruction=planner_output.next_action,
                        screenshot_path=screenshot_path,
                        log_dir=log_dir,
                        attached_images_base64=context.attached_images,
                    )
                    print(f"[GUIAgent DEBUG] Actor 执行完成, device_action={device_action.action_type.value if device_action else 'None'}")
                    
                    # 合并 token 使用
                    for model, tokens in actor_tokens.items():
                        total_token_usage[model] = total_token_usage.get(model, 0) + tokens
                    
                    # 发送 action 事件（保持与流式一致的事件格式）
                    action_event = ActionEvent(action=device_action).to_dict()
                    print(f"[GUIAgent DEBUG] 发送 action 事件: {action_event}")
                    yield action_event
                    
                except Exception as e:
                    self.logger.logger.error(f"[GUIAgent] Actor 执行失败: {e}")
                    yield ErrorEvent(message=f"Actor 执行失败: {e}").to_dict()
                    return
            
            # 发送最终完成事件
            self.logger.logger.info(f"[GUIAgent] 发送 step_complete 事件, device_action={device_action.action_type.value if device_action else 'None'}")
            yield StepCompleteEvent(
                step=AgentStep(
                    planner_output=planner_output,
                    device_action=device_action,
                    reasoning_text=actor_reasoning,
                    token_usage=total_token_usage,
                )
            ).to_dict()
            
        except Exception as e:
            self.logger.logger.error(f"[GUIAgent] 流式执行失败: {e}")
            yield ErrorEvent(message=str(e)).to_dict()
    
    async def _step_streaming_unified(
        self,
        context: NodeContext,
        screenshot_path: str,
        log_dir: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Planner-Only 模式的流式执行
        
        一次 LLM 调用完成规划和动作生成。
        """
        total_token_usage: Dict[str, int] = {}
        unified_output: Optional[UnifiedPlannerOutput] = None
        
        try:
            # 获取合适的 Unified Planner
            planner = self._get_unified_planner(context.guidance_steps)
            yield {"type": "status", "content": "Start unified planning (Planner-Only mode)..."}
            
            # 流式调用 Unified Planner
            async for event in planner.plan_streaming(
                screenshot_path=screenshot_path,
                task_description=context.task_description,
                milestone_objective=context.milestone_objective,
                guidance_steps=context.guidance_steps,
                history_md=context.history_md,
                knowledge_context=context.knowledge_context,
                log_dir=log_dir,
                attached_files_content=context.attached_files_content,
                attached_images_base64=context.attached_images,
            ):
                # 转发 reasoning_delta 和 plan_complete 事件
                if event.get("type") in ("reasoning_delta", "plan_complete", "status"):
                    yield event
                
                # 捕获 unified_complete 事件
                elif event.get("type") == "unified_complete":
                    unified_output = event.get("output")
                    total_token_usage = event.get("token_usage", {})
                
                elif event.get("type") == "error":
                    yield event
                    return
            
            if not unified_output:
                yield ErrorEvent(message="UnifiedPlanner 未返回有效结果").to_dict()
                return
            
            # 转换为 PlannerOutput 和 DeviceAction
            planner_output = unified_output.to_planner_output()
            device_action = unified_output.to_device_action()
            
            # 验证一致性
            has_action = unified_output.action_type is not None and unified_output.action_type != ActionType.STOP
            
            if unified_output.is_milestone_completed and has_action:
                # 矛盾情况：强制修正
                self.logger.logger.warning(
                    f"[GUIAgent] Unified 模式检测到矛盾：MilestoneCompleted=true 但有非 stop 动作。"
                    f"强制设置 MilestoneCompleted=false"
                )
                unified_output.is_milestone_completed = False
                planner_output.is_milestone_completed = False
            
            # 如果里程碑已完成
            if unified_output.is_milestone_completed:
                self.logger.logger.info("[GUIAgent] Unified 模式：里程碑已完成")
                
                # 生成完成摘要
                if self.enable_completion_summary and not planner_output.completion_summary:
                    try:
                        completion_summary = await self.generate_completion_summary(
                            context, action_history=None, log_dir=log_dir
                        )
                        planner_output.completion_summary = completion_summary
                    except Exception as e:
                        self.logger.logger.warning(f"[GUIAgent] 生成完成摘要失败: {e}")
                        planner_output.completion_summary = f"Completed: {context.milestone_objective}"
                
                # 确保有 stop 动作
                if device_action is None:
                    device_action = DeviceAction.stop()
            
            # 发送 action 事件
            if device_action:
                if device_action.action_type.value == "drag":
                    self.logger.logger.info(
                        f"[GUIAgent] Unified 模式发送 action: drag, path: {device_action.path}"
                    )
                else:
                    self.logger.logger.info(
                        f"[GUIAgent] Unified 模式发送 action: {device_action.action_type.value}, "
                        f"坐标: ({device_action.x}, {device_action.y})"
                    )
                yield ActionEvent(action=device_action).to_dict()
            
            # 发送 step_complete 事件
            yield StepCompleteEvent(
                step=AgentStep(
                    planner_output=planner_output,
                    device_action=device_action,
                    reasoning_text=unified_output.reasoning,
                    token_usage=total_token_usage,
                )
            ).to_dict()
            
        except Exception as e:
            self.logger.logger.error(f"[GUIAgent] Unified 模式流式执行失败: {e}")
            yield ErrorEvent(message=str(e)).to_dict()


# ==================== 便捷函数 ====================

async def run_gui_agent_step(
    node_id: str,
    task_description: str,
    milestone_objective: str,
    screenshot_path: str,
    guidance_steps: List[str] = None,
    history_md: str = "",
    api_keys: Optional[Dict[str, str]] = None,
    planner_model: str = "gemini-3-flash-preview",
    actor_model: str = "gemini-3-flash-preview",
    log_dir: Optional[str] = None,
) -> AgentStep:
    """
    便捷函数：执行单步 GUI Agent
    
    适合简单场景的快速调用。
    """
    agent = GUIAgent(
        planner_model=planner_model,
        actor_model=actor_model,
        api_keys=api_keys,
    )
    
    context = NodeContext(
        node_id=node_id,
        task_description=task_description,
        milestone_objective=milestone_objective,
        guidance_steps=guidance_steps or [],
        history_md=history_md,
    )
    
    return await agent.step(context, screenshot_path, log_dir)
