"""
AutoCAD Agent - Core 模块

AutoCAD Agent 的核心实现。
与 PPT/Word/Excel 不同，AutoCAD 使用 HTTP API 而非 PowerShell COM。
"""

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Optional, Dict, Any, AsyncGenerator

from useit_studio.ai_run.node_handler.functional_nodes.computer_use.gui_v2.utils.llm_client import (
    VLMClient, LLMConfig
)
from useit_studio.ai_run.skills.skill_file_reader import SkillFileReader
from useit_studio.ai_run.utils.logger_utils import LoggerUtils

from .prompts import AUTOCAD_SYSTEM_PROMPT, AUTOCAD_USER_PROMPT_TEMPLATE
from .snapshot import AutoCADSnapshot


# ==================== 配置 ====================

@dataclass
class AutoCADAgentConfig:
    """AutoCAD Agent 配置"""
    planner_model: str = "gpt-4o-mini"
    max_tokens: int = 4096
    temperature: float = 0.0


@dataclass
class AutoCADPlannerOutput:
    """
    AutoCAD Planner 的输出
    
    与 Office Agent 不同，AutoCAD 输出的是 API 调用而非代码
    """
    thinking: str = ""
    action_name: str = ""  # API action name: draw_from_json, execute_python_com, etc.
    action_args: Dict[str, Any] = None
    title: Optional[str] = None
    is_milestone_completed: bool = False
    completion_summary: Optional[str] = None

    def __post_init__(self):
        if self.action_args is None:
            self.action_args = {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "Thinking": self.thinking,
            "Action": self.action_name,
            "Args": self.action_args,
            "Title": self.title or self._generate_title(),
            "MilestoneCompleted": self.is_milestone_completed,
            "node_completion_summary": self.completion_summary,
        }
    
    def _generate_title(self) -> str:
        """从 Action 生成简短标题"""
        if not self.action_name:
            return "Task completed" if self.is_milestone_completed else ""
        return self.action_name.replace("_", " ").title()

    @classmethod
    def from_dict(cls, data: Dict[str, Any], thinking: str = "") -> "AutoCADPlannerOutput":
        """从 JSON 字典创建 AutoCADPlannerOutput"""
        return cls(
            thinking=thinking or data.get("Thinking", ""),
            action_name=data.get("Action", ""),
            action_args=data.get("Args", {}),
            title=data.get("Title"),
            is_milestone_completed=data.get("MilestoneCompleted", False),
            completion_summary=data.get("node_completion_summary"),
        )


@dataclass
class AutoCADAction:
    """
    AutoCAD 动作 - API 调用
    """
    name: str  # API action name
    args: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.name,
            **self.args,
        }

    @classmethod
    def from_planner_output(cls, output: AutoCADPlannerOutput) -> "AutoCADAction":
        """从 Planner 输出创建 Action"""
        return cls(
            name=output.action_name,
            args=output.action_args or {},
        )


@dataclass
class AutoCADAgentStep:
    """
    AutoCAD Agent 单步执行的完整结果
    """
    planner_output: AutoCADPlannerOutput
    action: Optional[AutoCADAction] = None
    reasoning_text: str = ""
    error: Optional[str] = None

    @property
    def is_completed(self) -> bool:
        """任务是否完成"""
        return self.planner_output.is_milestone_completed

    def to_dict(self) -> Dict[str, Any]:
        return {
            "planner": self.planner_output.to_dict(),
            "action": self.action.to_dict() if self.action else None,
            "reasoning": self.reasoning_text,
            "is_completed": self.is_completed,
            "error": self.error,
        }


@dataclass
class AutoCADAgentContext:
    """
    AutoCAD Agent 上下文
    """
    user_goal: str
    node_instruction: str
    current_snapshot: Optional[AutoCADSnapshot] = None
    history_md: str = ""
    attached_files_content: str = ""
    additional_context: str = ""
    skills_prompt: str = ""
    skill_reader: Optional[SkillFileReader] = None
    last_execution_result: Optional[Dict[str, Any]] = None

    def to_prompt(self) -> str:
        """转换为 Planner 的 prompt。

        顺序按 KV-cache 友好排列：静态在前 → 追加式在中 → 动态在后。
        相同的前缀在多步之间可复用 cache，减少重复计算。
        """
        lines = []

        # ── TIER 1: STATIC (同一节点内所有 step 完全一致) ──

        if self.user_goal:
            lines.append("## User's Overall Goal (Context Only)")
            lines.append(f"The user wants to: {self.user_goal}")
            lines.append("Note: This is the user's high-level goal. Your task is to complete the CURRENT NODE only.")
            lines.append("")

        lines.append("## Current Node Instruction (YOUR GOAL)")
        lines.append(self.node_instruction or self.user_goal or "(No instruction provided)")
        lines.append("")

        if self.attached_files_content:
            lines.append(self.attached_files_content)
            lines.append("")

        if self.additional_context:
            lines.append("## Project Context")
            lines.append("```")
            lines.append(self.additional_context)
            lines.append("```")
            lines.append("")

        # ── TIER 2: APPEND-ONLY (前缀稳定，尾部追加新条目) ──

        full_skills = self._get_full_skills_prompt()
        if full_skills:
            lines.append(full_skills)
            lines.append("")

        if self.history_md:
            lines.append("## Workflow Progress")
            lines.append("The workflow below shows the overall plan. Your task is to complete the current node marked with [-->].")
            lines.append(self.history_md)
            lines.append("")

        # ── TIER 3: DYNAMIC (每步都变，放最后避免破坏前缀缓存) ──

        if self.current_snapshot and self.current_snapshot.has_data:
            lines.append("## Current AutoCAD State")
            lines.append(self.current_snapshot.to_context_format())
            lines.append("")

        if self.last_execution_result:
            lines.append("## Last Action Result")
            result_to_show = {k: v for k, v in self.last_execution_result.items() if k != "screenshot" and v is not None}
            lines.append("```json")
            lines.append(json.dumps(result_to_show, indent=2, ensure_ascii=False))
            lines.append("```")
            lines.append("")

        return "\n".join(lines)

    def _get_full_skills_prompt(self) -> str:
        """Combine base skills prompt with dynamically accumulated file reads."""
        base = self.skills_prompt
        if self.skill_reader and self.skill_reader.accumulated_content:
            return base + self.skill_reader.accumulated_content_header + self.skill_reader.accumulated_content
        return base


# ==================== Planner ====================

class AutoCADPlanner:
    """
    AutoCAD Planner - 规划器
    
    分析当前状态并决定下一步 API 调用
    """
    
    def __init__(
        self,
        config: AutoCADAgentConfig,
        api_keys: Optional[Dict[str, str]] = None,
        node_id: str = "",
    ):
        self.config = config
        self.node_id = node_id
        self.logger = LoggerUtils(component_name="AutoCADPlanner")
        
        # 初始化 VLM 客户端
        llm_config = LLMConfig(
            model=config.planner_model,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            role="autocad_planner",
            node_id=node_id,
        )
        self.vlm = VLMClient(config=llm_config, api_keys=api_keys, logger=self.logger)
    
    def set_node_id(self, node_id: str):
        """更新节点 ID"""
        self.node_id = node_id
        self.vlm.config.node_id = node_id
    
    async def plan_streaming(
        self,
        context: AutoCADAgentContext,
        log_dir: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式规划
        
        Yields:
            - {"type": "reasoning_delta", "content": str, "source": "planner"}
            - {"type": "plan_complete", "content": dict}
            - {"type": "error", "content": str}
        """
        user_prompt = self._build_user_prompt(context)
        
        # 从 context 中提取截图
        screenshot_base64 = None
        if context.current_snapshot and context.current_snapshot.screenshot:
            screenshot_base64 = context.current_snapshot.screenshot
            self.logger.logger.info("[AutoCADPlanner] Using screenshot for planning")
        
        full_content = ""
        
        async for chunk in self.vlm.stream(
            prompt=user_prompt,
            system_prompt=AUTOCAD_SYSTEM_PROMPT,
            screenshot_base64=screenshot_base64,
            log_dir=log_dir,
        ):
            if chunk["type"] == "delta":
                content = chunk["content"]
                if isinstance(content, list):
                    content = "".join(str(c) for c in content)
                full_content += content
                yield {
                    "type": "reasoning_delta",
                    "content": content,
                    "source": "planner",
                }
                
            elif chunk["type"] == "complete":
                planner_output = self._parse_response(full_content)
                yield {
                    "type": "plan_complete",
                    "content": planner_output.to_dict(),
                }
                
            elif chunk["type"] == "error":
                yield {"type": "error", "content": chunk["content"]}
    
    def _build_user_prompt(self, context: AutoCADAgentContext) -> str:
        """构建用户提示"""
        context_text = context.to_prompt()
        return AUTOCAD_USER_PROMPT_TEMPLATE.format(context=context_text)
    
    def _parse_response(self, response: str) -> AutoCADPlannerOutput:
        """解析 LLM 响应"""
        try:
            # 1. 提取 <thinking> 内容
            thinking = self._extract_thinking(response)
            
            # 2. 提取 JSON
            parsed = self._extract_json(response)
            
            # 3. 创建 PlannerOutput
            output = AutoCADPlannerOutput(
                thinking=thinking,
                action_name=parsed.get("Action", ""),
                action_args=parsed.get("Args", {}),
                title=parsed.get("Title"),
                is_milestone_completed=parsed.get("MilestoneCompleted", False),
                completion_summary=parsed.get("node_completion_summary"),
            )
            
            # 强制校验：非 stop 时 MilestoneCompleted 必须为 false
            if output.action_name != "stop" and output.is_milestone_completed:
                self.logger.logger.warning(
                    f"[AutoCADPlanner] 修正 MilestoneCompleted: Action='{output.action_name}'，强制设为 false"
                )
                output.is_milestone_completed = False
            
            self.logger.logger.info(
                f"[AutoCADPlanner] Parsed - Action: {output.action_name}, "
                f"Args: {len(str(output.action_args))} chars, "
                f"Completed: {output.is_milestone_completed}"
            )
            return output
            
        except Exception as e:
            self.logger.logger.error(f"解析 Planner 响应失败: {e}")
            return AutoCADPlannerOutput(
                thinking=f"Parse error: {str(e)}",
                action_name="status",
                action_args={},
                is_milestone_completed=False,
            )
    
    def _extract_thinking(self, text: str) -> str:
        """提取 <thinking> 标签内容"""
        thinking_match = re.search(r'<thinking>(.*?)</thinking>', text, re.DOTALL | re.IGNORECASE)
        if thinking_match:
            return thinking_match.group(1).strip()
        
        # 如果没有标签，提取 JSON 之前的内容
        json_start = text.find("{")
        if json_start > 0:
            potential_thinking = text[:json_start]
            potential_thinking = re.sub(r'```(?:json)?\s*$', '', potential_thinking, flags=re.MULTILINE)
            potential_thinking = potential_thinking.strip()
            if potential_thinking and len(potential_thinking) > 20:
                return potential_thinking
        
        return ""
    
    def _extract_json(self, text: str) -> Dict[str, Any]:
        """从文本中提取 JSON"""
        text = text.strip()
        
        # 直接尝试解析
        if text.startswith("{"):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass
        
        # 从 ```json 块中提取
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        # 提取第一个 { 到最后一个 }
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
        
        raise ValueError(f"无法从响应中提取 JSON: {text[:200]}...")


# ==================== Agent ====================

class AutoCADAgent:
    """
    AutoCAD Agent - AutoCAD 自动化 Agent
    
    职责：
    1. 调用 Planner 进行决策
    2. 管理决策循环
    3. 生成 tool_call 事件供前端执行
    """
    
    def __init__(
        self,
        config: AutoCADAgentConfig,
        api_keys: Optional[Dict[str, str]] = None,
        node_id: str = "",
    ):
        self.config = config
        self.api_keys = api_keys
        self.node_id = node_id
        self.logger = LoggerUtils(component_name="AutoCADAgent")
        
        self.planner = AutoCADPlanner(
            config=config,
            api_keys=api_keys,
            node_id=node_id,
        )
        
        self.logger.logger.info(
            f"[AutoCADAgent] 初始化完成 - Model: {config.planner_model}"
        )
    
    def set_node_id(self, node_id: str):
        """更新节点 ID"""
        self.node_id = node_id
        self.planner.set_node_id(node_id)

    def _read_skill_file(
        self, context: AutoCADAgentContext, file_path: str,
    ) -> Dict[str, Any]:
        """Read a skill resource file using the shared SkillFileReader.

        The reader accumulates content internally; ``to_prompt()`` picks it up
        via ``_get_full_skills_prompt()`` — no manual prompt patching needed.
        """
        reader = context.skill_reader
        if not reader:
            return {"status": "error", "error": "No skill_reader available on context"}

        result = reader.read_file(file_path)

        if result.success:
            if result.is_cached:
                return {
                    "status": "success",
                    "note": f"File '{file_path}' was already read. "
                            "Its content is available in the Skills section above. "
                            "Proceed to the next workflow step.",
                }
            return {"status": "success", "content": result.content}

        return {"status": "error", "error": result.error}

    def _run_skill_script(
        self,
        context: AutoCADAgentContext,
        script_path: str,
        input_json: Dict[str, Any],
        timeout: int = 30,
    ) -> Dict[str, Any]:
        """Execute a Python script from the skill's directory.

        The script receives ``input_json`` via stdin and must print a JSON
        result to stdout.  The skill's base directory is passed as the first
        CLI argument so the script can locate sibling resource files.

        Returns a dict with ``status``, and either ``result`` (parsed JSON
        from stdout) or ``error``.
        """
        reader = context.skill_reader
        if not reader:
            return {"status": "error", "error": "No skill_reader available on context"}

        resolved = reader._resolve_path(script_path)
        if not resolved or not os.path.exists(resolved):
            return {"status": "error", "error": f"Script not found: {script_path}"}

        base_dir = str(os.path.dirname(os.path.dirname(resolved)))

        try:
            proc = subprocess.run(
                [sys.executable, resolved, base_dir],
                input=json.dumps(input_json, ensure_ascii=False),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return {"status": "error", "error": f"Script timed out after {timeout}s"}
        except Exception as e:
            return {"status": "error", "error": f"Failed to run script: {e}"}

        if proc.returncode != 0:
            stderr_snippet = (proc.stderr or "")[:500]
            return {
                "status": "error",
                "error": f"Script exited with code {proc.returncode}: {stderr_snippet}",
            }

        try:
            result = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return {
                "status": "error",
                "error": f"Script output is not valid JSON: {proc.stdout[:300]}",
            }

        return {"status": "success", "result": result}

    async def run(
        self,
        user_goal: str = "",
        node_instruction: str = "",
        initial_snapshot: Optional[AutoCADSnapshot] = None,
        max_steps: int = 60,
        log_dir: Optional[str] = None,
        history_md: str = "",
        attached_files_content: str = "",
        additional_context: str = "",
        skills_prompt: str = "",
        skill_reader: Optional[SkillFileReader] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        运行决策循环
        
        Yields:
            事件流：
            - {"type": "step_start", "step": int}
            - {"type": "reasoning_delta", ...}
            - {"type": "plan_complete", ...}
            - {"type": "action", "action": {...}}
            - {"type": "tool_call", ...}
            - {"type": "wait_for_execution"}
            - {"type": "task_completed", "summary": str}
            - {"type": "error", ...}
        """
        display_instruction = node_instruction or user_goal
        self.logger.logger.info(f"[AutoCADAgent] 开始决策循环 - 节点指令: {display_instruction[:50]}...")
        
        # 初始化上下文
        context = AutoCADAgentContext(
            user_goal=user_goal,
            node_instruction=node_instruction,
            current_snapshot=initial_snapshot,
            history_md=history_md,
            attached_files_content=attached_files_content,
            additional_context=additional_context,
            skills_prompt=skills_prompt,
            skill_reader=skill_reader,
        )
        
        for step in range(1, max_steps + 1):
            self.logger.logger.info(f"[AutoCADAgent] Step {step}/{max_steps}")
            
            yield {"type": "step_start", "step": step}
            
            try:
                # 1. Planner 决策
                planner_output: Optional[AutoCADPlannerOutput] = None
                
                async for event in self.planner.plan_streaming(context, log_dir):
                    yield event
                    
                    if event.get("type") == "plan_complete":
                        planner_output = AutoCADPlannerOutput.from_dict(event.get("content", {}))
                
                if not planner_output:
                    yield {"type": "error", "content": "Planner did not return a valid result"}
                    return
                
                self.logger.logger.info(
                    f"[AutoCADAgent] Planner 决策 - Action: {planner_output.action_name}, "
                    f"Completed: {planner_output.is_milestone_completed}"
                )
                
                # 2. 检查是否完成
                if planner_output.is_milestone_completed or planner_output.action_name == "stop":
                    yield {
                        "type": "task_completed",
                        "summary": planner_output.completion_summary or "Task completed",
                    }
                    return
                
                # 3. 构造 Action
                action = AutoCADAction.from_planner_output(planner_output)

                # 3a. Local actions (no round-trip to local engine)
                if action.name == "read_file":
                    file_path = action.args.get("file_path", "")
                    self.logger.logger.info(f"[AutoCADAgent] read_file: {file_path}")
                    result = self._read_skill_file(context, file_path)
                    self.logger.logger.info(
                        f"[AutoCADAgent] read_file result: status={result.get('status')}, "
                        f"len={len(result.get('content', ''))}"
                    )
                    yield {
                        "type": "action",
                        "action": {"type": "read_file", "file_path": file_path},
                    }
                    context.last_execution_result = result
                    continue

                if action.name == "run_skill_script":
                    script_path = action.args.get("script_path", "")
                    input_json = action.args.get("input_json", {})
                    self.logger.logger.info(f"[AutoCADAgent] run_skill_script: {script_path}")
                    result = self._run_skill_script(context, script_path, input_json)
                    self.logger.logger.info(
                        f"[AutoCADAgent] run_skill_script result: status={result.get('status')}"
                    )
                    yield {
                        "type": "action",
                        "action": {"type": "run_skill_script", "script_path": script_path},
                    }
                    context.last_execution_result = result
                    continue

                # 4. 发送 action 事件
                yield {
                    "type": "action",
                    "action": action.to_dict(),
                }
                
                # 5. 发送 tool_call 请求
                yield {
                    "type": "tool_call",
                    "id": f"call_autocad_{self.node_id}_{step}",
                    "target": "autocad",
                    "name": action.name,
                    "args": action.args,
                }
                
                # 6. 等待执行结果
                response = yield {"type": "wait_for_execution"}
                
                if response is None:
                    self.logger.logger.info("[AutoCADAgent] 等待执行结果，暂停循环")
                    return
                
                execution_result, new_snapshot = response
                
                # 7. 更新上下文
                if new_snapshot:
                    context.current_snapshot = new_snapshot
                
                self.logger.logger.info(
                    f"[AutoCADAgent] 执行结果 - Success: {execution_result.get('success', False) if execution_result else False}"
                )
                
            except Exception as e:
                self.logger.logger.error(f"[AutoCADAgent] Step {step} 失败: {e}", exc_info=True)
                yield {"type": "error", "content": str(e)}
                return
        
        # 达到最大步数
        self.logger.logger.warning(f"[AutoCADAgent] 达到最大步数 {max_steps}")
        yield {"type": "max_steps_reached", "steps": max_steps}
    
    async def step_streaming(
        self,
        context: AutoCADAgentContext,
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
        try:
            # Planner 流式决策
            planner_output: Optional[AutoCADPlannerOutput] = None
            
            async for event in self.planner.plan_streaming(context, log_dir):
                yield event
                
                if event.get("type") == "plan_complete":
                    planner_output = AutoCADPlannerOutput.from_dict(
                        event.get("content", {}),
                        thinking=event.get("content", {}).get("Thinking", "")
                    )
            
            if not planner_output:
                yield {"type": "error", "content": "Planner did not return a valid result"}
                return
            
            self.logger.logger.info(
                f"[AutoCADAgent] Planner decision - Action: {planner_output.action_name}, "
                f"Completed: {planner_output.is_milestone_completed}"
            )
            
            # 如果完成
            if planner_output.is_milestone_completed or planner_output.action_name == "stop":
                yield {
                    "type": "step_complete",
                    "step": AutoCADAgentStep(
                        planner_output=planner_output,
                        action=None,
                        reasoning_text="Task completed",
                    ),
                }
                return
            
            # 构造 Action
            action = AutoCADAction.from_planner_output(planner_output)

            # Local actions — handle without round-trip
            if action.name == "read_file":
                file_path = action.args.get("file_path", "")
                self.logger.logger.info(f"[AutoCADAgent] step read_file: {file_path}")
                result = self._read_skill_file(context, file_path)

                yield {
                    "type": "action",
                    "action": {"type": "read_file", "file_path": file_path},
                }
                yield {
                    "type": "step_complete",
                    "step": AutoCADAgentStep(
                        planner_output=planner_output,
                        action=action,
                        reasoning_text=f"Read file: {file_path}",
                    ),
                    "local_action_result": result,
                }
                return

            if action.name == "run_skill_script":
                script_path = action.args.get("script_path", "")
                input_json = action.args.get("input_json", {})
                self.logger.logger.info(f"[AutoCADAgent] step run_skill_script: {script_path}")
                result = self._run_skill_script(context, script_path, input_json)

                yield {
                    "type": "action",
                    "action": {"type": "run_skill_script", "script_path": script_path},
                }
                yield {
                    "type": "step_complete",
                    "step": AutoCADAgentStep(
                        planner_output=planner_output,
                        action=action,
                        reasoning_text=f"Run script: {script_path}",
                    ),
                    "local_action_result": result,
                }
                return

            # 发送 action 事件
            yield {
                "type": "action",
                "action": action.to_dict(),
            }
            
            # 返回完整的 step 结果
            yield {
                "type": "step_complete",
                "step": AutoCADAgentStep(
                    planner_output=planner_output,
                    action=action,
                    reasoning_text=f"Execute {action.name}",
                ),
            }
            
        except Exception as e:
            self.logger.logger.error(f"[AutoCADAgent] step_streaming failed: {e}", exc_info=True)
            yield {"type": "error", "content": str(e)}


# ==================== 工厂函数 ====================

def create_agent(
    planner_model: str = "gpt-4o-mini",
    api_keys: Optional[Dict[str, str]] = None,
    node_id: str = "",
) -> AutoCADAgent:
    """
    创建 AutoCAD Agent 的工厂函数
    
    Args:
        planner_model: Planner 使用的模型
        api_keys: API 密钥字典
        node_id: 节点 ID
        
    Returns:
        AutoCADAgent 实例
    """
    config = AutoCADAgentConfig(
        planner_model=planner_model,
    )
    
    return AutoCADAgent(
        config=config,
        api_keys=api_keys,
        node_id=node_id,
    )


__all__ = [
    "AutoCADAgentConfig",
    "AutoCADPlannerOutput",
    "AutoCADAction",
    "AutoCADAgentStep",
    "AutoCADAgentContext",
    "AutoCADPlanner",
    "AutoCADAgent",
    "create_agent",
]
