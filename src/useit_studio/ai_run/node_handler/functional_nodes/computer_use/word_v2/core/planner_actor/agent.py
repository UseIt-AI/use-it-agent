"""
Word Agent V2 - Agent 主流程

Agent 是 Planner 和 Actor 的协调者，实现完整的决策循环：

1. 接收用户指令和初始文档快照
2. 循环执行：
   - Planner 分析状态，决定下一步
   - 如果任务完成 → 结束
   - Actor 生成代码 → 发送执行 → 等待结果 → 更新状态 → 继续循环

对齐 GUI Agent 的设计模式。
"""

from typing import Dict, Any, Optional, AsyncGenerator, List

from ...models import (
    NodeContext,
    AgentContext,
    AgentStep,
    PlannerOutput,
    WordAction,
    ActionType,
    DocumentSnapshot,
    ReasoningDeltaEvent,
    PlanCompleteEvent,
    ActionEvent,
    StepCompleteEvent,
    ErrorEvent,
)
from .planner import WordPlanner
from .actor import WordActor
from useit_studio.ai_run.utils.logger_utils import LoggerUtils


class WordAgent:
    """
    Word Agent - Word 自动化的核心实现
    
    职责：
    1. 协调 Planner 和 Actor
    2. 管理决策循环（观察 → 规划 → 执行 → 观察 → ...）
    3. 提供流式输出接口
    
    使用方式：
        agent = WordAgent(api_keys={"OPENAI_API_KEY": "..."})
        
        # 运行决策循环
        async for event in agent.run(
            user_instruction="把第一段加粗",
            initial_snapshot=snapshot,
        ):
            if event["type"] == "tool_call":
                # 发送代码到前端执行
                result = await execute_on_frontend(event)
                # 发送结果回 agent
                await agent.send_execution_result(result, new_snapshot)
            else:
                # 处理其他事件
                print(event)
    """
    
    def __init__(
        self,
        planner_model: str = "gpt-4o-mini",
        actor_model: str = "gpt-4o-mini",
        api_keys: Optional[Dict[str, str]] = None,
        node_id: str = "",
    ):
        """
        初始化 Word Agent
        
        Args:
            planner_model: Planner 使用的模型
            actor_model: Actor 使用的模型
            api_keys: API 密钥字典
            node_id: 节点 ID（用于日志标识）
        """
        self.logger = LoggerUtils(component_name="WordAgent")
        self.api_keys = api_keys
        self.node_id = node_id
        
        # 初始化 Planner
        self.planner = WordPlanner(
            model=planner_model,
            api_keys=api_keys,
            node_id=node_id,
        )
        
        # 初始化 Actor
        self.actor = WordActor(
            model=actor_model,
            api_keys=api_keys,
            node_id=node_id,
        )
        
        self.logger.logger.info(
            f"[WordAgent] 初始化完成 - Planner: {planner_model}, Actor: {actor_model}"
        )
    
    def set_node_id(self, node_id: str):
        """更新节点 ID（用于日志）"""
        self.node_id = node_id
        self.planner.set_node_id(node_id)
        self.actor.set_node_id(node_id)
    
    async def run(
        self,
        user_goal: str = "",
        node_instruction: str = "",
        initial_snapshot: Optional[DocumentSnapshot] = None,
        max_steps: int = 60,
        log_dir: Optional[str] = None,
        history_md: str = "",
        attached_files_content: str = "",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        运行决策循环
        
        这是一个协程生成器，使用 yield/send 模式与调用者交互：
        - yield 事件给调用者
        - 调用者通过 send() 返回执行结果
        
        Args:
            user_goal: 用户输入的宏观目标（可能跨越多个节点）
            node_instruction: 当前节点的具体指令（来自 workflow 定义）
            initial_snapshot: 前端附带的初始快照
            max_steps: 最大步数
            log_dir: 日志目录
            history_md: AIMarkdownTransformer 生成的工作流历史记录
            attached_files_content: 附件文件内容
            
        Yields:
            各种事件：
            - {"type": "step_start", "step": int}
            - {"type": "reasoning_delta", ...}
            - {"type": "plan_complete", ...}
            - {"type": "action", ...}
            - {"type": "tool_call", "action": {...}}  # 需要前端执行
            - {"type": "wait_for_execution"}  # 等待执行结果
            - {"type": "task_completed", "summary": str}
            - {"type": "error", ...}
        """
        display_instruction = node_instruction or user_goal
        self.logger.logger.info(f"[WordAgent] 开始决策循环 - 节点指令: {display_instruction[:50]}...")
        
        # 初始化上下文
        context = AgentContext(
            user_goal=user_goal,
            node_instruction=node_instruction,
            current_snapshot=initial_snapshot,
            attached_files_content=attached_files_content,
            history_md=history_md,
        )
        
        for step in range(1, max_steps + 1):
            self.logger.logger.info(f"[WordAgent] Step {step}/{max_steps}")
            
            yield {"type": "step_start", "step": step}
            
            try:
                # 1. Planner 决策
                planner_output: Optional[PlannerOutput] = None
                
                async for event in self.planner.plan_streaming(context, log_dir):
                    yield event
                    
                    if event.get("type") == "plan_complete":
                        planner_output = PlannerOutput.from_dict(event.get("content", {}))
                
                if not planner_output:
                    yield ErrorEvent(message="Planner did not return a valid result").to_dict()
                    return
                
                self.logger.logger.info(
                    f"[WordAgent] Planner 决策 - Action: {planner_output.next_action[:50]}..., "
                    f"Completed: {planner_output.is_milestone_completed}"
                )
                
                # 2. 检查是否完成
                if planner_output.is_milestone_completed:
                    yield {
                        "type": "task_completed",
                        "summary": planner_output.completion_summary or "Task completed",
                    }
                    return
                
                # 3. Actor 生成代码
                action: Optional[WordAction] = None
                
                async for event in self.actor.act_streaming(
                    planner_output=planner_output,
                    document_snapshot=context.current_snapshot,
                    log_dir=log_dir,
                ):
                    yield event
                    
                    if event.get("type") == "action":
                        action_dict = event.get("action", {})
                        action = WordAction(
                            action_type=ActionType(action_dict.get("type", "stop")),
                            code=action_dict.get("code"),
                            language=action_dict.get("language", "PowerShell"),
                        )
                
                if not action:
                    yield ErrorEvent(message="Actor did not return a valid action").to_dict()
                    return
                
                # 4. 如果是 STOP，结束
                if action.action_type == ActionType.STOP:
                    yield {
                        "type": "task_completed",
                        "summary": planner_output.completion_summary or "Task completed",
                    }
                    return
                
                # 5. 发送代码执行请求（标准 tool_call 格式）
                action_dict = action.to_dict()
                yield {
                    "type": "tool_call",
                    "id": f"call_word_{self.node_id}_{step}",
                    "target": "word",
                    "name": action_dict.get("type", "execute_code"),
                    "args": {k: v for k, v in action_dict.items() if k != "type"},
                }
                
                # 6. 等待执行结果（调用者通过 send() 返回）
                # 返回格式: (execution_result, new_snapshot)
                response = yield {"type": "wait_for_execution"}
                
                if response is None:
                    # 如果没有收到响应，说明调用者要暂停循环
                    self.logger.logger.info("[WordAgent] 等待执行结果，暂停循环")
                    return
                
                execution_result, new_snapshot = response
                
                # 7. 更新上下文
                if new_snapshot:
                    context.current_snapshot = new_snapshot
                
                # 记录历史
                success = execution_result.get("success", False) if execution_result else False
                error = execution_result.get("error", "") if execution_result else ""
                
                context.history.append({
                    "action": planner_output.next_action,
                    "summary": planner_output.next_action,
                    "result": "success" if success else f"failed: {error}",
                })
                
                self.logger.logger.info(
                    f"[WordAgent] 执行结果 - Success: {success}, Error: {error}"
                )
                
                # 8. 继续循环
                
            except Exception as e:
                self.logger.logger.error(f"[WordAgent] Step {step} 失败: {e}", exc_info=True)
                yield ErrorEvent(message=str(e)).to_dict()
                return
        
        # 达到最大步数
        self.logger.logger.warning(f"[WordAgent] 达到最大步数 {max_steps}")
        yield {"type": "max_steps_reached", "steps": max_steps}
    
    async def step(
        self,
        context: AgentContext,
        log_dir: Optional[str] = None,
    ) -> AgentStep:
        """
        执行单步（非流式，用于简单场景）
        
        Args:
            context: Agent 上下文
            log_dir: 日志目录
            
        Returns:
            AgentStep 包含完整的执行结果
        """
        try:
            # 1. Planner 决策
            planner_output = await self.planner.plan(context, log_dir)
            
            # 2. 如果完成，返回 stop
            if planner_output.is_milestone_completed:
                return AgentStep(
                    planner_output=planner_output,
                    action=WordAction.stop(),
                    reasoning_text="Task completed",
                )
            
            # 3. Actor 生成代码
            action = await self.actor.act(
                planner_output=planner_output,
                document_snapshot=context.current_snapshot,
                log_dir=log_dir,
            )
            
            return AgentStep(
                planner_output=planner_output,
                action=action,
                reasoning_text=f"Generated {action.language} code",
            )
            
        except Exception as e:
            self.logger.logger.error(f"[WordAgent] step 失败: {e}", exc_info=True)
            return AgentStep(
                planner_output=PlannerOutput(
                    observation="Error occurred",
                    reasoning=str(e),
                    next_action="Retry",
                    is_milestone_completed=False,
                ),
                error=str(e),
            )
    
    async def step_streaming(
        self,
        context: AgentContext,
        log_dir: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行单步（流式，用于回调处理）
        
        Yields:
            - {"type": "reasoning_delta", "content": str, "source": "planner"}
            - {"type": "plan_complete", "content": {...}}
            - {"type": "action", "action": {...}}
            - {"type": "step_complete", "step": AgentStep}
            - {"type": "error", "content": str}
        """
        try:
            # 1. Planner 流式决策
            planner_output: Optional[PlannerOutput] = None
            
            async for event in self.planner.plan_streaming(context, log_dir):
                yield event
                
                if event.get("type") == "plan_complete":
                    planner_output = PlannerOutput.from_dict(
                        event.get("content", {}),
                        thinking=event.get("content", {}).get("Thinking", "")
                    )
            
            if not planner_output:
                yield {"type": "error", "content": "Planner did not return a valid result"}
                return
            
            self.logger.logger.info(
                f"[WordAgent] Planner decision - Action: {planner_output.next_action[:50] if planner_output.next_action else '(none)'}..., "
                f"Completed: {planner_output.is_milestone_completed}"
            )
            
            # 2. 如果完成，返回 stop
            if planner_output.is_milestone_completed:
                yield {
                    "type": "step_complete",
                    "step": AgentStep(
                        planner_output=planner_output,
                        action=WordAction.stop(),
                        reasoning_text="Task completed",
                    ),
                }
                return
            
            # 3. Actor 流式生成代码
            action: Optional[WordAction] = None
            
            async for event in self.actor.act_streaming(
                planner_output=planner_output,
                document_snapshot=context.current_snapshot,
                log_dir=log_dir,
            ):
                yield event
                
                if event.get("type") == "action":
                    action_dict = event.get("action", {})
                    action = WordAction(
                        action_type=ActionType(action_dict.get("type", "stop")),
                        code=action_dict.get("code"),
                        language=action_dict.get("language", "PowerShell"),
                    )
            
            if not action:
                yield {"type": "error", "content": "Actor did not return a valid action"}
                return
            
            # 4. 返回完整的 step 结果
            yield {
                "type": "step_complete",
                "step": AgentStep(
                    planner_output=planner_output,
                    action=action,
                    reasoning_text=f"Generated {action.language} code",
                ),
            }
            
        except Exception as e:
            self.logger.logger.error(f"[WordAgent] step_streaming failed: {e}", exc_info=True)
            yield {"type": "error", "content": str(e)}


# ==================== 便捷函数 ====================

async def run_word_agent(
    user_goal: str = "",
    node_instruction: str = "",
    initial_snapshot: Optional[DocumentSnapshot] = None,
    api_keys: Optional[Dict[str, str]] = None,
    planner_model: str = "gpt-4o-mini",
    actor_model: str = "gpt-4o-mini",
    max_steps: int = 60,
    log_dir: Optional[str] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    便捷函数：运行 Word Agent
    
    Args:
        user_goal: 用户输入的宏观目标
        node_instruction: 当前节点的具体指令
    """
    agent = WordAgent(
        planner_model=planner_model,
        actor_model=actor_model,
        api_keys=api_keys,
    )
    
    async for event in agent.run(
        user_goal=user_goal,
        node_instruction=node_instruction,
        initial_snapshot=initial_snapshot,
        max_steps=max_steps,
        log_dir=log_dir,
    ):
        yield event
