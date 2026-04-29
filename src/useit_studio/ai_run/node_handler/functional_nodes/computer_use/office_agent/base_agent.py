"""
Office Agent - 通用 Agent 基类

Agent 是决策循环的核心，协调 Planner 完成任务。

决策循环：
1. 接收用户指令和初始快照
2. 循环执行：
   - Planner 分析状态，决定下一步并生成代码
   - 如果任务完成 → 结束
   - 发送代码执行 → 等待结果 → 更新状态 → 继续循环
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional, AsyncGenerator, List

from .models import (
    AgentContext,
    AgentStep,
    PlannerOutput,
    OfficeAction,
    ActionType,
    OfficeAppType,
    ReasoningDeltaEvent,
    PlanCompleteEvent,
    ActionEvent,
    ErrorEvent,
)
from .base_planner import OfficePlanner, OfficePlannerConfig
from useit_studio.ai_run.utils.logger_utils import LoggerUtils


@dataclass
class OfficeAgentConfig:
    """Agent 配置"""
    planner_model: str = "gpt-4o-mini"
    actor_model: str = "gpt-4o-mini"  # 保留兼容性，planner_only 模式不使用
    app_type: OfficeAppType = OfficeAppType.WORD
    max_tokens: int = 4096
    temperature: float = 0.0


class OfficeAgent:
    """
    Office Agent - 通用 Office 自动化 Agent
    
    职责：
    1. 调用 Planner 进行决策
    2. 管理决策循环
    3. 处理执行结果和状态更新
    
    使用方式：
        agent = OfficeAgent(
            config=OfficeAgentConfig(app_type=OfficeAppType.WORD),
            planner=word_planner,
            api_keys={"OPENAI_API_KEY": "..."}
        )
        
        async for event in agent.run(
            user_goal="打开文档",
            node_instruction="打开Word",
            initial_snapshot=snapshot,
        ):
            if event["type"] == "tool_call":
                # 发送代码到前端执行
                ...
    """
    
    def __init__(
        self,
        config: OfficeAgentConfig,
        planner: OfficePlanner,
        api_keys: Optional[Dict[str, str]] = None,
        node_id: str = "",
    ):
        """
        初始化 Agent
        
        Args:
            config: Agent 配置
            planner: Planner 实例（由工厂函数或子类提供）
            api_keys: API 密钥
            node_id: 节点 ID
        """
        self.config = config
        self.planner = planner
        self.api_keys = api_keys
        self.node_id = node_id
        self.logger = LoggerUtils(component_name=f"{config.app_type.value.title()}Agent")
        
        self.logger.logger.info(
            f"[{config.app_type.value.title()}Agent] 初始化完成 - Model: {config.planner_model}"
        )
    
    def set_node_id(self, node_id: str):
        """更新节点 ID"""
        self.node_id = node_id
        self.planner.set_node_id(node_id)

    def _build_tool_call_args(self, planner_output: PlannerOutput) -> tuple:
        """
        根据 planner_output 构建 tool_call 的 (name, args) 元组。

        子类可重写此方法以支持不同的执行模式（如 PPT local engine 的 Mode A/B/C）。

        Returns:
            (tool_call_name: str, tool_call_args: dict)
            返回 (None, None) 表示无法构建（上层应报错）。
        """
        tool_call_name = planner_output.next_action

        # Skill-based actions (Word/Excel): execute_script / read_file / read_default_reference
        if tool_call_name in ("execute_script", "read_file", "read_default_reference"):
            tool_call_args: dict = {}
            if tool_call_name == "execute_script":
                tool_call_args = {
                    "ScriptPath": planner_output.script_path or "",
                    "Parameters": planner_output.parameters or {},
                }
            elif tool_call_name == "read_file":
                tool_call_args = {
                    "FilePath": planner_output.file_path or "",
                }
            return tool_call_name, tool_call_args

        # execute_code via OfficeAction
        if planner_output.code:
            action = OfficeAction.execute_code(
                code=planner_output.code,
                language=planner_output.language or "PowerShell",
            )
            action_dict = action.to_dict()
            name = action_dict.get("type", "execute_code")
            args = {k: v for k, v in action_dict.items() if k != "type"}
            return name, args

        return None, None

    @staticmethod
    def _normalize_attached_images(
        attached_images: Optional[List[Dict[str, Any]]],
    ) -> List[str]:
        """将 attached_images 规范化为纯 base64 列表（移除 data URI 前缀）"""
        result: List[str] = []
        for item in (attached_images or []):
            if not isinstance(item, dict):
                continue
            raw = item.get("base64")
            if not isinstance(raw, str):
                continue
            value = raw.strip()
            if not value:
                continue
            if value.startswith("data:") and "," in value:
                value = value.split(",", 1)[1]
            result.append(value)
        return result

    async def run(
        self,
        user_goal: str = "",
        node_instruction: str = "",
        initial_snapshot: Optional[Any] = None,
        max_steps: int = 60,
        log_dir: Optional[str] = None,
        history_md: str = "",
        attached_files_content: str = "",
        attached_images: Optional[List[Dict[str, Any]]] = None,
        additional_context: str = "",
        skills_prompt: str = "",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        运行决策循环

        Args:
            user_goal: 用户输入的宏观目标
            node_instruction: 当前节点的具体指令
            initial_snapshot: 初始快照（类型由应用决定）
            max_steps: 最大步数
            log_dir: 日志目录
            history_md: 工作流历史记录
            attached_files_content: 附件文件内容
            attached_images: 附件图片列表（每项含 base64）
            additional_context: 项目目录结构等额外上下文
            skills_prompt: Skills prompt（只包含 SKILL.md）

        Yields:
            事件流：
            - {"type": "step_start", "step": int}
            - {"type": "reasoning_delta", ...}
            - {"type": "plan_complete", ...}
            - {"type": "tool_call", "action": {...}}
            - {"type": "wait_for_execution"}
            - {"type": "task_completed", "summary": str}
            - {"type": "error", ...}
        """
        display_instruction = node_instruction or user_goal
        app_name = self.config.app_type.value.title()
        self.logger.logger.info(f"[{app_name}Agent] 开始决策循环 - 节点指令: {display_instruction[:50]}...")

        # 初始化上下文
        context = AgentContext(
            user_goal=user_goal,
            node_instruction=node_instruction,
            current_snapshot=initial_snapshot,
            history_md=history_md,
            attached_files_content=attached_files_content,
            attached_images=self._normalize_attached_images(attached_images),
            additional_context=additional_context,
            skills_prompt=skills_prompt,
        )
        
        for step in range(1, max_steps + 1):
            self.logger.logger.info(f"[{app_name}Agent] Step {step}/{max_steps}")
            
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
                    f"[{app_name}Agent] Planner 决策 - Action: {planner_output.next_action}, "
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
                
                # 3. 构造 tool_call（子类可通过 _build_tool_call_args 扩展）
                tool_call_name, tool_call_args = self._build_tool_call_args(planner_output)

                if tool_call_name is None:
                    yield ErrorEvent(message="Planner returned action but no executable content").to_dict()
                    return

                # 仅对 execute_code 发出 ActionEvent（供前端显示代码预览）
                if tool_call_name == "execute_code" and planner_output.code:
                    action = OfficeAction.execute_code(
                        code=planner_output.code,
                        language=planner_output.language or "PowerShell",
                    )
                    yield ActionEvent(action=action).to_dict()
                
                # 4. 发送代码执行请求
                yield {
                    "type": "tool_call",
                    "id": f"call_{self.config.app_type.value}_{self.node_id}_{step}",
                    "target": self.config.app_type.value,
                    "name": tool_call_name,
                    "args": tool_call_args,
                }
                
                # 6. 等待执行结果
                response = yield {"type": "wait_for_execution"}
                
                if response is None:
                    self.logger.logger.info(f"[{app_name}Agent] 等待执行结果，暂停循环")
                    return
                
                execution_result, new_snapshot = response
                
                # 7. 更新上下文
                if new_snapshot:
                    context.current_snapshot = new_snapshot
                
                # 记录历史
                success = execution_result.get("success", False) if execution_result else False
                error = execution_result.get("error", "") if execution_result else ""
                
                summary = planner_output.title or "Execute code"
                if planner_output.actions:
                    names = [
                        a.get("action", "?")
                        for a in planner_output.actions
                        if isinstance(a, dict)
                    ]
                    if names:
                        summary = f"{summary} ({', '.join(names)})"
                context.history.append({
                    "action": planner_output.title or planner_output.next_action,
                    "summary": summary,
                    "result": "success" if success else f"failed: {error}",
                })
                
                self.logger.logger.info(
                    f"[{app_name}Agent] 执行结果 - Success: {success}, Error: {error}"
                )
                
            except Exception as e:
                self.logger.logger.error(f"[{app_name}Agent] Step {step} 失败: {e}", exc_info=True)
                yield ErrorEvent(message=str(e)).to_dict()
                return
        
        # 达到最大步数
        self.logger.logger.warning(f"[{app_name}Agent] 达到最大步数 {max_steps}")
        yield {"type": "max_steps_reached", "steps": max_steps}
    
    async def step(
        self,
        context: AgentContext,
        log_dir: Optional[str] = None,
    ) -> AgentStep:
        """
        执行单步（非流式）
        """
        app_name = self.config.app_type.value.title()
        
        try:
            # Planner 决策
            planner_output, token_usage = await self.planner.plan(context, log_dir)
            
            # 如果完成，返回 stop
            if planner_output.is_milestone_completed or planner_output.next_action == "stop":
                return AgentStep(
                    planner_output=planner_output,
                    action=OfficeAction.stop(),
                    reasoning_text="Task completed",
                    token_usage=token_usage,
                )
            
            # 构造 OfficeAction（仅 Mode B execute_code 需要；Mode A/C action=None）
            if planner_output.code:
                action: Optional[OfficeAction] = OfficeAction.execute_code(
                    code=planner_output.code,
                    language=planner_output.language or "PowerShell",
                )
                reasoning_text = f"Generated {action.language} code"
            elif planner_output.actions or planner_output.skill_id:
                action = None
                reasoning_text = f"Action: {planner_output.next_action}"
            else:
                action = OfficeAction.stop()
                reasoning_text = "No executable content"

            return AgentStep(
                planner_output=planner_output,
                action=action,
                reasoning_text=reasoning_text,
                token_usage=token_usage,
            )
            
        except Exception as e:
            self.logger.logger.error(f"[{app_name}Agent] step 失败: {e}", exc_info=True)
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
        执行单步（流式）
        
        Yields:
            - {"type": "reasoning_delta", ...}
            - {"type": "plan_complete", ...}
            - {"type": "action", ...}
            - {"type": "step_complete", ...}
            - {"type": "error", ...}
        """
        app_name = self.config.app_type.value.title()
        total_token_usage: Dict[str, int] = {}
        
        try:
            # Planner 流式决策
            planner_output: Optional[PlannerOutput] = None
            
            async for event in self.planner.plan_streaming(context, log_dir):
                yield event
                
                if event.get("type") == "plan_complete":
                    planner_output = PlannerOutput.from_dict(
                        event.get("content", {}),
                        thinking=event.get("content", {}).get("Thinking", "")
                    )
                    # 收集 token_usage
                    planner_tokens = event.get("token_usage", {})
                    for model, tokens in planner_tokens.items():
                        total_token_usage[model] = total_token_usage.get(model, 0) + tokens
            
            if not planner_output:
                yield {"type": "error", "content": "Planner did not return a valid result"}
                return
            
            self.logger.logger.info(
                f"[{app_name}Agent] Planner decision - Action: {planner_output.next_action}, "
                f"Code: {len(planner_output.code or '')} chars, "
                f"Completed: {planner_output.is_milestone_completed}"
            )
            
            # 如果完成
            if planner_output.is_milestone_completed or planner_output.next_action == "stop":
                yield {
                    "type": "step_complete",
                    "step": AgentStep(
                        planner_output=planner_output,
                        action=OfficeAction.stop(),
                        reasoning_text="Task completed",
                        token_usage=total_token_usage,
                    ),
                }
                return
            
            # 构造 tool_call（子类可通过 _build_tool_call_args 扩展）
            tool_call_name, tool_call_args = self._build_tool_call_args(planner_output)

            if tool_call_name is None:
                yield {"type": "error", "content": "Planner returned action but no executable content"}
                return

            # execute_code：经典 Office 路由；step：PPT/Local Engine 统一 POST /step（同样有 code）
            if planner_output.code and tool_call_name in ("execute_code", "step"):
                action: Optional[OfficeAction] = OfficeAction.execute_code(
                    code=planner_output.code,
                    language=planner_output.language or "PowerShell",
                )
                yield ActionEvent(action=action).to_dict()
            else:
                action = None

            yield {
                "type": "tool_call",
                "id": f"call_{self.config.app_type.value}_{self.node_id}_step",
                "target": self.config.app_type.value,
                "name": tool_call_name,
                "args": tool_call_args,
            }

            yield {
                "type": "step_complete",
                "step": AgentStep(
                    planner_output=planner_output,
                    action=action,
                    reasoning_text=f"Action: {tool_call_name}",
                    token_usage=total_token_usage,
                ),
            }
            
        except Exception as e:
            self.logger.logger.error(f"[{app_name}Agent] step_streaming failed: {e}", exc_info=True)
            yield {"type": "error", "content": str(e)}
