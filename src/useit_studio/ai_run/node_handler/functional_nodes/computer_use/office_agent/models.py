"""
Office Agent - 通用数据模型定义

所有 Office 应用（Word、Excel、PPT）共享的数据结构。
应用特定的 Snapshot 结构由各应用模块自行定义。
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Protocol, runtime_checkable
from enum import Enum


# ==================== 1. 枚举定义 ====================

class ActionType(str, Enum):
    """Office 动作类型"""
    EXECUTE_CODE = "execute_code"  # 执行 PowerShell/Python 代码
    STOP = "stop"  # 任务完成


class OfficeAppType(str, Enum):
    """Office 应用类型"""
    WORD = "word"
    EXCEL = "excel"
    POWERPOINT = "ppt"
    OUTLOOK = "outlook"  # 预留


# ==================== 2. Snapshot Protocol ====================

@runtime_checkable
class BaseSnapshot(Protocol):
    """
    Office 应用快照的基础协议
    
    所有应用的 Snapshot 都必须实现这些方法。
    具体的 Snapshot 结构由各应用模块定义。
    """
    
    @property
    def has_data(self) -> bool:
        """是否有有效数据"""
        ...
    
    @property
    def screenshot(self) -> Optional[str]:
        """base64 编码的截图（可选）"""
        ...
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        ...
    
    def to_context_format(self, max_items: int = 50, max_text_length: int = 200) -> str:
        """
        转换为 LLM 可用的文本格式
        
        Args:
            max_items: 最大条目数（段落/单元格/形状等）
            max_text_length: 文本最大长度
        
        Returns:
            格式化的文本描述
        """
        ...


# ==================== 3. Planner 输出 ====================

@dataclass
class PlannerOutput:
    """
    Planner 的输出 - 高层次的动作规划

    采用 <thinking> + JSON 混合格式：
    - thinking: 自由推理过程
    - next_action: 下一步动作
      - "actions"      → Mode A: 结构化 action 列表（PPT local engine 首选）
      - "execute_code" → Mode B: 执行 PowerShell/Python 代码
      - "skill"        → Mode C: 执行预置 Skill 脚本
      - "stop"         → 任务完成
    - title: 简短标题用于 UI
    - code: Mode B 可执行代码
    - actions: Mode A 结构化动作列表
    - is_milestone_completed: 任务是否完成
    """
    thinking: str = ""
    next_action: str = ""
    title: Optional[str] = None

    # Mode B: execute_code
    code: Optional[str] = None
    language: str = "PowerShell"

    # Mode A: structured actions (PPT local engine)
    actions: Optional[List[Dict[str, Any]]] = None

    # Router → Tool: description for LLM-powered tools, params for passthrough
    description: str = ""
    tool_params: Optional[Dict[str, Any]] = None

    # Mode C: skill
    skill_id: Optional[str] = None

    # /step 公共参数
    return_screenshot: bool = True
    current_slide_only: bool = True
    timeout: int = 120

    is_milestone_completed: bool = False
    completion_summary: Optional[str] = None

    # execute_script / read_file 相关字段（Word/Excel skill 模式）
    script_path: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    file_path: Optional[str] = None

    # 兼容旧字段
    observation: str = ""
    reasoning: str = ""

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "Thinking": self.thinking,
            "Action": self.next_action,
            "Title": self.title or self._generate_title(),
            "MilestoneCompleted": self.is_milestone_completed,
            "node_completion_summary": self.completion_summary,
            "Observation": self.observation,
            "Reasoning": self.reasoning,
        }
        # Mode A
        if self.actions is not None:
            result["Actions"] = self.actions
        # Router → Tool fields
        if self.description:
            result["Description"] = self.description
        if self.tool_params:
            result["Params"] = self.tool_params
        # Mode B
        if self.code:
            result["Code"] = self.code
            result["Language"] = self.language
        # Mode C
        if self.skill_id:
            result["SkillId"] = self.skill_id
        if self.script_path:
            result["ScriptPath"] = self.script_path
        if self.parameters:
            result["Parameters"] = self.parameters
        if self.file_path:
            result["FilePath"] = self.file_path
        return result

    def _generate_title(self) -> str:
        if not self.next_action:
            return "Task completed" if self.is_milestone_completed else ""
        action = self.next_action.strip()
        if len(action) > 50:
            return action[:47] + "..."
        return action

    @classmethod
    def from_dict(cls, data: Dict[str, Any], thinking: str = "") -> "PlannerOutput":
        """从 JSON 字典创建 PlannerOutput"""
        return cls(
            thinking=thinking or data.get("Thinking", ""),
            next_action=data.get("Action", ""),
            title=data.get("Title"),
            code=data.get("Code"),
            language=data.get("Language", "PowerShell"),
            actions=data.get("Actions"),
            description=data.get("Description", ""),
            tool_params=data.get("Params"),
            skill_id=data.get("SkillId"),
            return_screenshot=data.get("ReturnScreenshot", True),
            current_slide_only=data.get("CurrentSlideOnly", True),
            timeout=data.get("Timeout", 120),
            is_milestone_completed=data.get("MilestoneCompleted", False),
            completion_summary=data.get("node_completion_summary"),
            script_path=data.get("ScriptPath"),
            parameters=data.get("Parameters"),
            file_path=data.get("FilePath"),
            observation=data.get("Observation", ""),
            reasoning=data.get("Reasoning", ""),
        )


# ==================== 4. Office 动作 ====================

@dataclass
class OfficeAction:
    """
    Office 动作 - 执行的代码或停止信号
    
    通用于所有 Office 应用。
    """
    action_type: ActionType
    code: Optional[str] = None
    language: str = "PowerShell"

    def to_dict(self) -> Dict[str, Any]:
        result = {"type": self.action_type.value}
        if self.action_type == ActionType.EXECUTE_CODE:
            result["code"] = self.code
            result["language"] = self.language
        return result

    @classmethod
    def execute_code(cls, code: str, language: str = "PowerShell") -> "OfficeAction":
        """创建代码执行动作"""
        return cls(
            action_type=ActionType.EXECUTE_CODE,
            code=code,
            language=language,
        )

    @classmethod
    def stop(cls) -> "OfficeAction":
        """创建停止动作"""
        return cls(action_type=ActionType.STOP)


# ==================== 5. Agent 步骤结果 ====================

@dataclass
class AgentStep:
    """
    Agent 单步执行的完整结果
    """
    planner_output: PlannerOutput
    action: Optional[OfficeAction] = None
    reasoning_text: str = ""
    token_usage: Dict[str, int] = field(default_factory=dict)
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
            "token_usage": self.token_usage,
            "is_completed": self.is_completed,
            "error": self.error,
        }


# ==================== 6. Agent 上下文 ====================

@dataclass
class AgentContext:
    """
    Agent 上下文 - 包含决策所需的所有信息

    泛型化设计，snapshot 类型由具体应用决定。
    """
    user_goal: str                         # 用户输入的宏观目标
    node_instruction: str                  # 当前节点的具体指令
    current_snapshot: Optional[Any] = None # 具体类型由应用决定 (DocumentSnapshot, SheetSnapshot, etc.)
    history_md: str = ""                   # 工作流进度
    history: List[Dict[str, Any]] = field(default_factory=list)  # 动作历史
    attached_files_content: str = ""       # 附件文件内容（已格式化）
    attached_images: List[str] = field(default_factory=list)  # 附件图片 base64（不含 data URI 前缀）
    additional_context: str = ""           # 项目目录结构等额外上下文
    skills_prompt: str = ""                # Skills prompt（只包含 SKILL.md）
    last_execution_output: str = ""        # 上一步脚本/代码的 stdout 输出
    # Desktop snapshot rendered from uia_data — open_windows / installed_apps /
    # active_window.  Primary signal for the Router to avoid double-launch
    # and to supply hwnds to window_control actions.  Pre-formatted markdown;
    # empty string means "no desktop snapshot available this turn".
    desktop_snapshot: str = ""
    # Confirmed ``ask_user`` Q&A pairs that the orchestrator (or an
    # earlier agent_node in this workflow run) already resolved with
    # the user.  The planner treats each entry as a fixed commitment:
    # don't re-ask, don't second-guess.  List of
    # :class:`useit_ai_run.agent_loop.action_models.Clarification` —
    # typed as ``Any`` here to avoid a node_handler → agent_loop
    # import cycle at module load.
    clarifications: List[Any] = field(default_factory=list)

    def to_prompt(self, app_type: OfficeAppType = OfficeAppType.WORD) -> str:
        """
        转换为 Planner 的 prompt
        
        Args:
            app_type: 应用类型，用于生成应用特定的提示
        """
        lines = []
        
        # 1. 用户的宏观目标
        if self.user_goal:
            lines.append("## User's Overall Goal (Context Only)")
            lines.append(f"The user wants to: {self.user_goal}")
            lines.append("Note: This is the user's high-level goal. Your task is to complete the CURRENT NODE only.")
            lines.append("")
        
        # 2. 当前节点指令
        lines.append("## Current Node Instruction (YOUR GOAL)")
        if self.node_instruction:
            lines.append(self.node_instruction)
        else:
            lines.append(self.user_goal or "(No instruction provided)")
        lines.append("")

        # 2a. User Clarifications — fixed commitments the user already
        # confirmed at a higher layer (orchestrator ``ask_user`` or an
        # earlier node's ``ask_user``).  Rendered *before* the desktop
        # snapshot so the planner reads the user's intent before any
        # candidate list coming from ``open_windows`` — otherwise a
        # freshly-opened file or a stale window can outvote the user's
        # explicit pick and the whole disambiguation round-trip is
        # wasted.  Intentionally ABSENT when the list is empty — we
        # don't want a ghost section that trains the planner to expect
        # clarifications even when there aren't any.
        if self.clarifications:
            lines.append("## User Clarifications (confirmed by the user — do not re-ask)")
            for idx, clar in enumerate(self.clarifications, 1):
                q = _clar_field(clar, "question", "(question unavailable)")
                a = _clar_field(clar, "answer", "").strip()
                sid = _clar_field(clar, "selected_option_id", None)
                label = _clar_field(clar, "selected_option_label", None)
                free = _clar_field(clar, "free_text", None)
                src = _clar_field(clar, "source", "orchestrator")
                src_node = _clar_field(clar, "source_node_id", None)
                src_tag = f"{src}" + (f":{src_node}" if src_node else "")
                lines.append(f"{idx}. **Q** ({src_tag}): {q}")
                # Prefer the structured fields when present so the planner
                # sees e.g. ``[option `use_existing`]`` rather than parsing
                # the rendered sentence.
                summary_bits: List[str] = []
                if sid:
                    if label:
                        summary_bits.append(f"option `{sid}` ({label})")
                    else:
                        summary_bits.append(f"option `{sid}`")
                if free:
                    summary_bits.append(f"free-text: {free}")
                if summary_bits:
                    lines.append(f"   **A**: {'; '.join(summary_bits)}")
                elif a:
                    lines.append(f"   **A**: {a}")
                else:
                    lines.append("   **A**: (no answer captured)")
            lines.append(
                "**Treat every answer above as a fixed commitment.** Do not "
                "re-open the same question with `ask_user`; if a choice now "
                "conflicts with newer evidence, stop and explain before acting."
            )
            lines.append("")

        # 2b. Desktop snapshot (uia_data) — rendered BEFORE the app-specific
        # state so the Router sees `open_windows` / `installed_apps` early.
        # Without this the Router is blind: it can't tell whether the target
        # app is already running, and it has no hwnds to feed into
        # `system_window_control` for tiling / activation.
        if self.desktop_snapshot:
            lines.append(self.desktop_snapshot)
            lines.append("")

        # 3. 当前应用状态
        #
        # Only render this section when the caller actually handed us a
        # snapshot object.  The dedicated office handlers (ppt_v2, word_v2,
        # excel_v2, autocad) always pass ``current_snapshot=...`` — even an
        # empty one carries the "app is open but empty" signal via
        # ``has_data=False``.  The generic AgentNode router, however,
        # constructs ``AgentContext`` without a snapshot (it relies on
        # ``desktop_snapshot`` + tool-specific snapshots fetched on demand)
        # and passes a placeholder ``app_type=POWERPOINT``.  If we emit a
        # "No Ppt data available. The application may not be open." line
        # in that case the planner is actively misled — it will see
        # ``open_windows`` listing ``POWERPNT.EXE`` with an hwnd and *still*
        # believe PowerPoint is closed, because we told it so.  Skipping
        # the section entirely when ``current_snapshot`` is absent lets the
        # Router trust the authoritative ``open_windows`` evidence instead.
        app_name = app_type.value.title()
        if self.current_snapshot is not None:
            lines.append(f"## Current {app_name} State")
            if hasattr(self.current_snapshot, 'to_context_format'):
                lines.append(self.current_snapshot.to_context_format())
            elif hasattr(self.current_snapshot, 'has_data'):
                if self.current_snapshot.has_data:
                    lines.append(str(self.current_snapshot.to_dict()))
                else:
                    lines.append(
                        f"No {app_name} data available. The application may not be open."
                    )
            else:
                lines.append(str(self.current_snapshot))
            lines.append("")

        # 3b. PPT: highlight actual slide dimensions for SVG viewBox
        if app_type == OfficeAppType.POWERPOINT and self.current_snapshot:
            sw = getattr(self.current_snapshot, 'slide_width', None)
            sh = getattr(self.current_snapshot, 'slide_height', None)
            if sw and sh:
                lines.append(f"**Slide Canvas Size: {sw} × {sh} pt** — "
                             f"use `viewBox=\"0 0 {sw} {sh}\"` for all SVG output.")
                lines.append("")

        # 3c. Steps already executed in this node (prevents duplicate actions after resume)
        if self.history:
            lines.append("## Agent Step History (this node)")
            lines.append(
                "Operations already run before this decision. **Do not repeat the same actions "
                "unless you are fixing a failed step or intentionally replacing prior effects "
                "(e.g. after `clear_slide_animations`).**"
            )
            for i, h in enumerate(self.history[-20:], 1):
                summary = h.get("summary") or h.get("action") or "step"
                result = h.get("result", "")
                lines.append(f"{i}. {summary} — **{result}**")
            lines.append("")
        
        # 4. 项目目录结构（additional_context）
        if self.additional_context:
            lines.append("## Project Context")
            lines.append("The following shows the project directory structure and available files:")
            lines.append("```")
            lines.append(self.additional_context)
            lines.append("```")
            lines.append("")
        
        # 5. 附件文件内容
        if self.attached_files_content:
            lines.append(self.attached_files_content)
            lines.append("")
        
        # 6. 上一步执行输出
        if self.last_execution_output:
            lines.append("## Previous Step Execution Output")
            lines.append("The following is the stdout output from the last executed script/code:")
            lines.append("```")
            lines.append(self.last_execution_output)
            lines.append("```")
            lines.append("**IMPORTANT: Read this output carefully. If it contains structured data (e.g. JSON with status, row numbers, values), use it to decide your next action.**")
            lines.append("")

        # 7. 工作流进度
        if self.history_md:
            lines.append("## Workflow Progress")
            lines.append("The workflow below shows the overall plan. Your task is to complete the current node marked with [-->].")
            lines.append(self.history_md)
            lines.append("")

        return "\n".join(lines)


# ==================== 7. 流式事件类型 ====================

@dataclass
class ReasoningDeltaEvent:
    """推理过程的增量输出"""
    content: str
    source: str = "planner"  # "planner" or "actor"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "reasoning_delta",
            "content": self.content,
            "source": self.source,
        }


@dataclass
class PlanCompleteEvent:
    """Planner 规划完成事件"""
    planner_output: PlannerOutput

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "plan_complete",
            "content": self.planner_output.to_dict(),
        }


@dataclass
class ActionEvent:
    """Actor 生成动作事件"""
    action: OfficeAction

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "action",
            "action": self.action.to_dict(),
        }


@dataclass
class StepCompleteEvent:
    """单步执行完成事件"""
    step: AgentStep

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "step_complete",
            "content": self.step.to_dict(),
        }


@dataclass
class ErrorEvent:
    """错误事件"""
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "error",
            "content": self.message,
        }


def _clar_field(clar: Any, key: str, default: Any) -> Any:
    """Access a Clarification field defensively.

    ``AgentContext.clarifications`` is typed as ``List[Any]`` to avoid
    an import cycle back to ``agent_loop.action_models``.  Callers may
    therefore pass either a real :class:`Clarification` dataclass
    instance or a plain ``dict`` (e.g. when a future persistence layer
    rehydrates state from JSON).  Support both without forcing an
    import at render time.
    """
    if isinstance(clar, dict):
        return clar.get(key, default)
    return getattr(clar, key, default)
