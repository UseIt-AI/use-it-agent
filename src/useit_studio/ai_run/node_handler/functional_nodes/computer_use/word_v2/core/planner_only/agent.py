"""
Word Agent V2 - Planner Only 模式

简化版 Agent：只调用 Planner，Planner 直接输出代码。

决策循环：
1. 接收用户指令和初始文档快照
2. 循环执行：
   - Planner 分析状态，决定下一步并生成代码
   - 如果任务完成 → 结束
   - 发送代码执行 → 等待结果 → 更新状态 → 继续循环
"""

from typing import Dict, Any, Optional, AsyncGenerator

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
from useit_studio.ai_run.utils.logger_utils import LoggerUtils


class WordAgent:
    """
    Word Agent - Planner Only 模式
    
    简化版实现：Planner 直接输出代码，无需 Actor。
    
    职责：
    1. 调用 Planner 进行决策
    2. Planner 输出包含 Code，直接用于执行
    3. 管理决策循环
    """
    
    def __init__(
        self,
        planner_model: str = "gpt-4o-mini",
        actor_model: str = "gpt-4o-mini",  # 保留参数兼容性，但不使用
        api_keys: Optional[Dict[str, str]] = None,
        node_id: str = "",
    ):
        """
        初始化 Word Agent (Planner Only)
        
        Args:
            planner_model: Planner 使用的模型
            actor_model: 保留参数兼容性，Planner Only 模式不使用
            api_keys: API 密钥字典
            node_id: 节点 ID（用于日志标识）
        """
        self.logger = LoggerUtils(component_name="WordAgent")
        self.api_keys = api_keys
        self.node_id = node_id
        
        # 初始化 Planner（单一组件）
        self.planner = WordPlanner(
            model=planner_model,
            api_keys=api_keys,
            node_id=node_id,
        )
        
        self.logger.logger.info(
            f"[WordAgent] 初始化完成 (Planner Only) - Model: {planner_model}"
        )
    
    def set_node_id(self, node_id: str):
        """更新节点 ID（用于日志）"""
        self.node_id = node_id
        self.planner.set_node_id(node_id)
    
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
            history_md=history_md,
            attached_files_content=attached_files_content,
        )
        
        for step in range(1, max_steps + 1):
            self.logger.logger.info(f"[WordAgent] Step {step}/{max_steps}")
            
            yield {"type": "step_start", "step": step}
            
            try:
                # 1. Planner 决策（包含代码）
                planner_output: Optional[PlannerOutput] = None
                
                async for event in self.planner.plan_streaming(context, log_dir):
                    yield event
                    
                    if event.get("type") == "plan_complete":
                        planner_output = PlannerOutput.from_dict(event.get("content", {}))
                
                if not planner_output:
                    yield ErrorEvent(message="Planner did not return a valid result").to_dict()
                    return
                
                self.logger.logger.info(
                    f"[WordAgent] Planner 决策 - Action: {planner_output.next_action}, "
                    f"Code: {len(planner_output.code or '')} chars, "
                    f"Completed: {planner_output.is_milestone_completed}"
                )
                
                # 2. 检查是否完成
                if planner_output.is_milestone_completed or planner_output.next_action == "stop":
                    yield {
                        "type": "task_completed",
                        "summary": planner_output.completion_summary or "Task completed",
                    }
                    return
                
                # 3. 构造 WordAction
                if planner_output.code:
                    action = WordAction.execute_code(
                        code=planner_output.code,
                        language=planner_output.language or "PowerShell"
                    )
                else:
                    # 没有代码，可能是错误
                    yield ErrorEvent(message="Planner returned execute_code but no code").to_dict()
                    return
                
                # 4. 发送 action 事件（给前端显示）
                yield ActionEvent(action=action).to_dict()
                
                # 5. 发送代码执行请求（标准 tool_call 格式）
                action_dict = action.to_dict()
                yield {
                    "type": "tool_call",
                    "id": f"call_word_{self.node_id}_{step}",
                    "target": "word",
                    "name": action_dict.get("type", "execute_code"),
                    "args": {k: v for k, v in action_dict.items() if k != "type"},
                }
                
                # 6. 等待执行结果
                response = yield {"type": "wait_for_execution"}
                
                if response is None:
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
                    "action": planner_output.title or planner_output.next_action,
                    "summary": planner_output.title or "Execute code",
                    "result": "success" if success else f"failed: {error}",
                })
                
                self.logger.logger.info(
                    f"[WordAgent] 执行结果 - Success: {success}, Error: {error}"
                )
                
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
            if planner_output.is_milestone_completed or planner_output.next_action == "stop":
                return AgentStep(
                    planner_output=planner_output,
                    action=WordAction.stop(),
                    reasoning_text="Task completed",
                )
            
            # 3. 从 Planner 输出构造 WordAction
            if planner_output.code:
                action = WordAction.execute_code(
                    code=planner_output.code,
                    language=planner_output.language or "PowerShell"
                )
            else:
                action = WordAction.stop()
            
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
                    next_action="execute_code",
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
                f"[WordAgent] Planner decision - Action: {planner_output.next_action}, "
                f"Code: {len(planner_output.code or '')} chars, "
                f"Completed: {planner_output.is_milestone_completed}"
            )
            
            # 2. 如果完成，返回 stop
            if planner_output.is_milestone_completed or planner_output.next_action == "stop":
                yield {
                    "type": "step_complete",
                    "step": AgentStep(
                        planner_output=planner_output,
                        action=WordAction.stop(),
                        reasoning_text="Task completed",
                    ),
                }
                return
            
            # 3. 从 Planner 输出构造 WordAction
            if planner_output.code:
                action = WordAction.execute_code(
                    code=planner_output.code,
                    language=planner_output.language or "PowerShell"
                )
            else:
                action = WordAction.stop()
            
            # 4. 发送 action 事件
            yield ActionEvent(action=action).to_dict()
            
            # 5. 返回完整的 step 结果
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
    max_steps: int = 60,
    log_dir: Optional[str] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    便捷函数：运行 Word Agent (Planner Only)
    
    Args:
        user_goal: 用户输入的宏观目标
        node_instruction: 当前节点的具体指令
    """
    agent = WordAgent(
        planner_model=planner_model,
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
