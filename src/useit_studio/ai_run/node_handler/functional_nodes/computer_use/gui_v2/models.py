"""
GUI Agent V2 - 数据模型定义

所有数据结构的单一真相来源，清晰定义输入输出格式。
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum


class ActionType(str, Enum):
    """动作类型枚举"""
    CLICK = "click"
    DOUBLE_CLICK = "double_click"
    TYPE = "type"
    KEY = "key"
    SCROLL = "scroll"
    MOVE = "move"
    DRAG = "drag"
    WAIT = "wait"
    SCREENSHOT = "screenshot"
    STOP = "stop"  # 任务完成


class CoordinateSystem(str, Enum):
    """
    坐标系枚举
    
    用于标识坐标的类型，客户端根据此字段进行坐标转换。
    """
    NORMALIZED_1000 = "normalized_1000"  # Gemini 千分位坐标 (0-1000)，需要客户端转换
    SCREEN_PIXEL = "screen_pixel"  # 屏幕像素坐标，可直接使用


@dataclass
class DeviceAction:
    """
    设备动作 - Actor 的输出
    
    统一的动作格式，可直接发送给执行层。
    
    坐标系说明：
    - coordinate_system: 标识坐标的类型
    - NORMALIZED_1000: Gemini 输出的千分位坐标 (0-1000)，客户端需要转换：
        actual_x = (x / 1000.0) * screen_width
        actual_y = (y / 1000.0) * screen_height
    - SCREEN_PIXEL: 已经是屏幕像素坐标，可直接使用
    """
    action_type: ActionType
    x: Optional[int] = None
    y: Optional[int] = None
    text: Optional[str] = None
    key: Optional[str] = None
    scroll_x: int = 0
    scroll_y: int = 0
    duration_ms: int = 0
    coordinate_system: CoordinateSystem = CoordinateSystem.SCREEN_PIXEL  # 默认屏幕坐标
    # 拖拽：路径点列表，至少 2 个点 [[x1,y1],[x2,y2],...]，执行层会按 coordinate_system 转换
    path: Optional[List[List[int]]] = None
    button: Optional[str] = None  # 鼠标按键，如 "left"（默认）、"right"

    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典格式，与 engineering_agent (ComputerUseController) 协议对齐。

        - type: 动作类型（执行端会做 key->keypress 等别名映射）
        - x, y / coordinate, coordinate_system: 坐标及坐标系
        - text: 输入文本（type）
        - key + keys: 按键（执行端读 keys，双写避免 key/keys 歧义）
        - scroll_x, scroll_y: 滚动量（执行端读此二字段）
        - seconds: 等待秒数（wait 时；执行端读 seconds，由 duration_ms 换算）
        - path, button: 拖拽路径与鼠标键（drag）
        """
        result = {"type": self.action_type.value}
        
        if self.x is not None:
            result["x"] = self.x
        if self.y is not None:
            result["y"] = self.y
        if self.x is not None and self.y is not None:
            result["coordinate"] = [self.x, self.y]
            result["coordinate_system"] = self.coordinate_system.value
        
        if self.text:
            result["text"] = self.text
        # 按键：同时输出 key 与 keys，与执行端 keys 字段对齐，避免 key/keys 歧义
        if self.key:
            result["key"] = self.key
            result["keys"] = [self.key] if "+" not in self.key else self.key.split("+")
        # 滚动：执行端读 scroll_x/scroll_y，必须显式输出
        if self.scroll_x or self.scroll_y:
            result["scroll"] = [self.scroll_x, self.scroll_y]
            result["scroll_x"] = self.scroll_x
            result["scroll_y"] = self.scroll_y
        if self.duration_ms:
            result["duration_ms"] = self.duration_ms
        # 等待：执行端读 seconds（秒），由 duration_ms 换算
        if self.action_type == ActionType.WAIT and self.duration_ms:
            result["seconds"] = self.duration_ms / 1000.0
        if self.path is not None and len(self.path) >= 2:
            result["path"] = self.path
            result["coordinate_system"] = self.coordinate_system.value
        if self.button:
            result["button"] = self.button

        return result

    @classmethod
    def click(cls, x: int, y: int) -> "DeviceAction":
        return cls(action_type=ActionType.CLICK, x=x, y=y)
    
    @classmethod
    def double_click(cls, x: int, y: int) -> "DeviceAction":
        return cls(action_type=ActionType.DOUBLE_CLICK, x=x, y=y)
    
    @classmethod
    def type_text(cls, text: str) -> "DeviceAction":
        return cls(action_type=ActionType.TYPE, text=text)
    
    @classmethod
    def press_key(cls, key: str) -> "DeviceAction":
        return cls(action_type=ActionType.KEY, key=key)
    
    @classmethod
    def scroll(cls, x: int, y: int, scroll_x: int = 0, scroll_y: int = -3) -> "DeviceAction":
        return cls(action_type=ActionType.SCROLL, x=x, y=y, scroll_x=scroll_x, scroll_y=scroll_y)

    @classmethod
    def drag(cls, path: List[List[int]], button: str = "left") -> "DeviceAction":
        """path: 至少 2 个点 [[x1,y1],[x2,y2],...]"""
        return cls(action_type=ActionType.DRAG, path=path, button=button)

    @classmethod
    def stop(cls) -> "DeviceAction":
        return cls(action_type=ActionType.STOP)


@dataclass
class PlannerOutput:
    """
    Planner 的输出 - 高层次的动作规划
    
    Planner 负责"想"，决定下一步做什么（自然语言描述）。
    """
    observation: str  # 对当前截图的观察
    reasoning: str  # 推理过程
    next_action: str  # 下一步动作的自然语言描述
    current_step: int = 1  # 当前步骤编号
    step_explanation: str = ""  # 当前步骤的解释
    expectation: str = ""  # 预期结果
    is_milestone_completed: bool = False  # 当前里程碑是否完成
    completion_summary: Optional[str] = None  # 完成时的摘要
    output_filename: Optional[str] = None  # 输出文件名 (如 "report.md")
    result_markdown: Optional[str] = None  # AI 主动生成的 markdown 文件内容
    step_memory: Optional[str] = None  # AI 的"小本本"：这一步记录的关键信息/笔记
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "Observation": self.observation,
            "Reasoning": self.reasoning,
            "Action": self.next_action,
            "Current Step": self.current_step,
            "Current Step Reason": self.step_explanation,
            "Expectation": self.expectation,
            "MilestoneCompleted": self.is_milestone_completed,
            "node_completion_summary": self.completion_summary,
            "output_filename": self.output_filename,
            "result_markdown": self.result_markdown,
            "step_memory": self.step_memory,
        }


@dataclass
class AgentStep:
    """
    Agent 单步执行的完整结果
    
    包含 Planner 的规划和 Actor 的执行结果。
    """
    planner_output: PlannerOutput
    device_action: Optional[DeviceAction] = None
    reasoning_text: str = ""  # Actor 的推理文本
    token_usage: Dict[str, int] = field(default_factory=dict)
    error: Optional[str] = None
    
    @property
    def is_completed(self) -> bool:
        """任务是否完成"""
        return self.planner_output.is_milestone_completed
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "planner": self.planner_output.to_dict(),
            "action": self.device_action.to_dict() if self.device_action else None,
            "reasoning": self.reasoning_text,
            "token_usage": self.token_usage,
            "is_completed": self.is_completed,
            "error": self.error,
        }


@dataclass
class NodeContext:
    """
    节点上下文 - Handler 传递给 Agent 的所有必要信息
    """
    node_id: str
    task_description: str  # 整体任务描述
    milestone_objective: str  # 当前里程碑目标
    guidance_steps: List[str] = field(default_factory=list)  # 指导步骤
    history_md: str = ""  # 历史动作的 Markdown（包含 working_memory）
    loop_context: Optional[Dict[str, Any]] = None  # 循环上下文（如果在循环中）
    knowledge_context: str = ""  # 外部知识上下文
    attached_files_content: str = ""  # 附件文件内容（已格式化）
    attached_images: List[str] = field(default_factory=list)  # 附件图片 base64（不含 data URI 前缀）


@dataclass
class TokenUsage:
    """Token 使用统计"""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0
    model: str = ""
    
    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            cost=self.cost + other.cost,
            model=self.model or other.model,
        )


# ==================== 流式事件类型 ====================

# 不使用 dataclass 继承，直接定义独立的事件类，避免字段顺序问题

@dataclass
class ReasoningDeltaEvent:
    """推理过程的增量输出"""
    content: str
    source: str = "planner"  # "planner" or "actor"
    event_type: str = "reasoning_delta"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.event_type,
            "content": self.content,
            "source": self.source,
        }


@dataclass
class PlanCompleteEvent:
    """Planner 规划完成事件"""
    planner_output: PlannerOutput
    event_type: str = "plan_complete"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.event_type,
            "content": self.planner_output.to_dict(),
        }


@dataclass
class ActionEvent:
    """Actor 生成动作事件"""
    action: DeviceAction
    event_type: str = "action"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.event_type,
            "action": self.action.to_dict(),
        }


@dataclass
class StepCompleteEvent:
    """单步执行完成事件"""
    step: AgentStep
    event_type: str = "step_complete"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.event_type,
            "content": self.step.to_dict(),
        }


@dataclass
class ErrorEvent:
    """错误事件"""
    message: str
    event_type: str = "error"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.event_type,
            "content": self.message,
        }


# ==================== Planner-Only 模式数据模型 ====================

@dataclass
class UnifiedPlannerOutput:
    """
    Unified Planner 的输出 - Planner-Only 模式
    
    一次 LLM 调用同时完成规划和动作生成：
    - 规划部分：observation, reasoning, next_action_description 等
    - 动作部分：action_type, x, y, text, key 等
    
    优点：
    - 减少 LLM 调用次数（1次 vs 2次）
    - 降低延迟和成本
    - 上下文一致性更好
    """
    # === 规划部分 ===
    observation: str  # 对当前截图的观察
    reasoning: str  # 推理过程
    next_action_description: str  # 下一步动作的自然语言描述
    
    current_step: int = 1  # 当前步骤编号
    step_explanation: str = ""  # 当前步骤的解释
    expectation: str = ""  # 预期结果
    
    is_milestone_completed: bool = False  # 当前里程碑是否完成
    completion_summary: Optional[str] = None  # 完成时的摘要
    output_filename: Optional[str] = None  # 输出文件名
    result_markdown: Optional[str] = None  # AI 生成的 markdown 内容
    step_memory: Optional[str] = None  # 这一步记录的关键信息
    
    # === 动作部分 ===
    action_type: Optional[ActionType] = None  # 动作类型
    x: Optional[int] = None  # 坐标 x (千分位 0-1000)
    y: Optional[int] = None  # 坐标 y (千分位 0-1000)
    text: Optional[str] = None  # 输入文本 (type 动作)
    key: Optional[str] = None  # 按键名称 (key 动作)
    scroll_x: int = 0  # 水平滚动量
    scroll_y: int = 0  # 垂直滚动量
    duration_ms: int = 0  # 等待时间
    path: Optional[List[List[int]]] = None  # 拖拽路径 [[x1,y1],[x2,y2],...] (drag 动作)
    button: Optional[str] = None  # 鼠标按键 "left"/"right" (drag 动作)
    
    # === 元数据 ===
    coordinate_system: CoordinateSystem = CoordinateSystem.NORMALIZED_1000  # 默认千分位坐标
    
    def to_device_action(self) -> Optional[DeviceAction]:
        """
        转换为 DeviceAction（兼容现有执行流程）
        
        Returns:
            DeviceAction 对象，如果 action_type 为空则返回 None
        """
        if self.action_type is None:
            return None
        
        return DeviceAction(
            action_type=self.action_type,
            x=self.x,
            y=self.y,
            text=self.text,
            key=self.key,
            scroll_x=self.scroll_x,
            scroll_y=self.scroll_y,
            duration_ms=self.duration_ms,
            coordinate_system=self.coordinate_system,
            path=self.path,
            button=self.button,
        )
    
    def to_planner_output(self) -> PlannerOutput:
        """
        转换为 PlannerOutput（兼容现有流程）
        
        Returns:
            PlannerOutput 对象
        """
        return PlannerOutput(
            observation=self.observation,
            reasoning=self.reasoning,
            next_action=self.next_action_description,
            current_step=self.current_step,
            step_explanation=self.step_explanation,
            expectation=self.expectation,
            is_milestone_completed=self.is_milestone_completed,
            completion_summary=self.completion_summary,
            output_filename=self.output_filename,
            result_markdown=self.result_markdown,
            step_memory=self.step_memory,
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        result = {
            # 规划部分
            "Observation": self.observation,
            "Reasoning": self.reasoning,
            "Action": self.next_action_description,
            "Current Step": self.current_step,
            "Current Step Reason": self.step_explanation,
            "Expectation": self.expectation,
            "MilestoneCompleted": self.is_milestone_completed,
            "node_completion_summary": self.completion_summary,
            "output_filename": self.output_filename,
            "result_markdown": self.result_markdown,
            "step_memory": self.step_memory,
            # 动作部分
            "action_type": self.action_type.value if self.action_type else None,
            "x": self.x,
            "y": self.y,
            "text": self.text,
            "key": self.key,
            "scroll_x": self.scroll_x,
            "scroll_y": self.scroll_y,
            "coordinate_system": self.coordinate_system.value,
            "path": self.path,
            "button": self.button,
        }
        return result


@dataclass
class UnifiedCompleteEvent:
    """Unified Planner 规划完成事件"""
    unified_output: UnifiedPlannerOutput
    token_usage: Dict[str, int] = field(default_factory=dict)
    event_type: str = "unified_complete"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.event_type,
            "output": self.unified_output,
            "token_usage": self.token_usage,
        }
