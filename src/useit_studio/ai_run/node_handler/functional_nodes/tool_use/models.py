"""
Tool Use Node - 数据模型定义

定义 Tool Use 节点所需的所有数据结构。
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum


# ==================== 1. 枚举定义 ====================

class ToolType(str, Enum):
    """可用的工具类型"""
    RAG = "rag"
    WEB_SEARCH = "web_search"
    FILE_SYSTEM = "file_system"  # 文件系统工具，通过 S3 读取项目文件
    FILE_TRANSFER = "file_transfer"  # 内部使用，任务结束时传输文件
    DOC_EXTRACT = "doc_extract"  # 文档提取工具，从 PDF 提取文本、图表


class ActionType(str, Enum):
    """动作类型"""
    TOOL_CALL = "tool_call"  # 调用工具
    STOP = "stop"  # 任务完成


# ==================== 2. 工具配置 ====================

@dataclass
class ToolConfig:
    """工具配置"""
    tool_type: ToolType
    enabled: bool = True
    config: Dict[str, Any] = field(default_factory=dict)
    # RAG 配置示例: {"index_path": "...", "top_k": 5}
    # Web Search 配置示例: {"max_results": 10}

    @classmethod
    def from_dict(cls, data) -> "ToolConfig":
        """
        从字典或字符串创建
        
        支持两种格式：
        1. 字符串: "web_search" -> ToolConfig(tool_type=WEB_SEARCH)
        2. 字典: {"type": "web_search", "enabled": true, "config": {...}}
        """
        # 如果是字符串，直接作为工具类型
        if isinstance(data, str):
            tool_type_str = data
            enabled = True
            config = {}
        else:
            # 字典格式
            tool_type_str = data.get("type", data.get("tool_type", ""))
            enabled = data.get("enabled", True)
            config = data.get("config", {})
        
        try:
            tool_type = ToolType(tool_type_str)
        except ValueError:
            tool_type = ToolType.RAG  # 默认
        
        return cls(
            tool_type=tool_type,
            enabled=enabled,
            config=config,
        )


# ==================== 3. 工具调用结果 ====================

@dataclass
class ToolCallResult:
    """工具调用结果"""
    tool_name: str
    tool_args: Dict[str, Any]
    result: str
    success: bool = True
    error: Optional[str] = None
    call_id: str = ""
    structured_data: Optional[Dict[str, Any]] = None  # 结构化数据（供前端可视化）

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "tool_name": self.tool_name,
            "tool_args": self.tool_args,
            "result": self.result,
            "success": self.success,
            "error": self.error,
            "call_id": self.call_id,
        }
        if self.structured_data:
            data["structured_data"] = self.structured_data
        return data


# ==================== 4. Planner 输出 ====================

@dataclass
class PlannerOutput:
    """
    Planner 输出
    
    与 Word V2 类似，但不包含代码，而是包含工具调用信息。
    使用 LangChain 的 tool_calls 格式。
    """
    thinking: str = ""
    next_action: str = ""  # "tool_call" 或 "stop"
    title: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)  # LangChain tool_calls
    is_milestone_completed: bool = False
    completion_summary: Optional[str] = None
    files_to_transfer: List[str] = field(default_factory=list)  # 任务完成时需要传输的文件
    
    # 任务完成时的 markdown 输出
    result_markdown: Optional[str] = None  # markdown 内容
    result_filename: Optional[str] = None  # markdown 文件名 (如 "search_results.md")
    
    # 兼容旧字段
    observation: str = ""
    reasoning: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "Thinking": self.thinking,
            "Action": self.next_action,
            "Title": self.title or self._generate_title(),
            "ToolCalls": self.tool_calls,
            "MilestoneCompleted": self.is_milestone_completed,
            "node_completion_summary": self.completion_summary,
            "files_to_transfer": self.files_to_transfer,
            "result_markdown": self.result_markdown,
            "result_filename": self.result_filename,
            "Observation": self.observation,
            "Reasoning": self.reasoning,
        }
    
    def _generate_title(self) -> str:
        """从 Action 生成简短标题"""
        if self.tool_calls:
            tool_names = [tc.get("name", "") for tc in self.tool_calls]
            return f"Call {', '.join(tool_names)}"
        if self.is_milestone_completed:
            return "Task completed"
        return self.next_action or ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any], thinking: str = "") -> "PlannerOutput":
        """从字典创建"""
        return cls(
            thinking=thinking or data.get("Thinking", ""),
            next_action=data.get("Action", ""),
            title=data.get("Title"),
            tool_calls=data.get("ToolCalls", []),
            is_milestone_completed=data.get("MilestoneCompleted", False),
            completion_summary=data.get("node_completion_summary"),
            files_to_transfer=data.get("files_to_transfer", []),
            result_markdown=data.get("result_markdown"),
            result_filename=data.get("result_filename"),
            observation=data.get("Observation", ""),
            reasoning=data.get("Reasoning", ""),
        )


# ==================== 5. Agent 上下文 ====================

@dataclass
class AgentContext:
    """
    Agent 上下文 - 包含决策所需的所有信息
    """
    user_goal: str
    node_instruction: str
    tool_results: List[ToolCallResult] = field(default_factory=list)  # 历史工具调用结果
    history_md: str = ""  # 工作流进度
    history: List[Dict[str, Any]] = field(default_factory=list)  # 动作历史
    available_tools: List[str] = field(default_factory=list)  # 可用工具名称列表
    attached_files_content: str = ""  # 附件文件内容（已格式化）

    def to_prompt(self) -> str:
        """转换为 Planner 的 prompt"""
        lines = []
        
        # 1. 用户目标
        if self.user_goal:
            lines.append("## User's Overall Goal")
            lines.append(self.user_goal)
            lines.append("")
        
        # 2. 当前节点指令
        lines.append("## Current Node Instruction (YOUR GOAL)")
        lines.append(self.node_instruction or self.user_goal or "(No instruction provided)")
        lines.append("")
        
        # 3. 可用工具
        if self.available_tools:
            lines.append("## Available Tools")
            for tool_name in self.available_tools:
                lines.append(f"- {tool_name}")
            lines.append("")
        
        # 4. 历史工具调用结果
        if self.tool_results:
            lines.append("## Previous Tool Results")
            for i, result in enumerate(self.tool_results, 1):
                lines.append(f"### Step {i}: {result.tool_name}")
                lines.append(f"**Arguments:** {result.tool_args}")
                if result.success:
                    # 截断长结果
                    result_text = result.result
                    if len(result_text) > 2000:
                        result_text = result_text[:2000] + "\n... (truncated)"
                    lines.append(f"**Result:**\n{result_text}")
                else:
                    lines.append(f"**Error:** {result.error}")
                lines.append("")
        
        # 5. 工作流进度
        if self.history_md:
            lines.append("## Workflow Progress")
            lines.append(self.history_md)
            lines.append("")
        
        # 6. 附件文件内容
        if self.attached_files_content:
            lines.append(self.attached_files_content)
            lines.append("")
        
        return "\n".join(lines)


# ==================== 6. Agent 步骤结果 ====================

@dataclass
class AgentStep:
    """Agent 单步执行结果"""
    planner_output: PlannerOutput
    tool_results: List[ToolCallResult] = field(default_factory=list)
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
            "tool_results": [r.to_dict() for r in self.tool_results],
            "reasoning": self.reasoning_text,
            "token_usage": self.token_usage,
            "is_completed": self.is_completed,
            "error": self.error,
        }


# ==================== 7. 事件模型 ====================

@dataclass
class ReasoningDeltaEvent:
    """推理过程的增量输出"""
    content: str
    source: str = "planner"

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
class ToolCallEvent:
    """工具调用事件"""
    tool_name: str
    tool_args: Dict[str, Any]
    call_id: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "tool_call",
            "id": self.call_id,
            "name": self.tool_name,
            "args": self.tool_args,
        }


@dataclass
class ToolResultEvent:
    """工具结果事件"""
    tool_name: str
    result: str
    success: bool
    call_id: str
    error: Optional[str] = None
    structured_data: Optional[Dict[str, Any]] = None  # 结构化数据（供前端可视化）

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "type": "tool_result",
            "id": self.call_id,
            "name": self.tool_name,
            "result": self.result,
            "success": self.success,
            "error": self.error,
        }
        if self.structured_data:
            data["structured_data"] = self.structured_data
        return data


@dataclass
class FileTransferEvent:
    """文件传输事件（任务结束时）"""
    files: List[str]
    target: str = "local"
    status: str = "pending"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "file_transfer",
            "files": self.files,
            "target": self.target,
            "status": self.status,
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


@dataclass
class SearchProgressEvent:
    """
    搜索进度事件 - 用于 Web Search 工具的流式进度显示
    
    阶段:
    - decomposing: 正在分解查询
    - queries_ready: 子查询准备完成，显示所有查询
    - searching: 正在搜索中（并行）
    - search_done: 单个搜索完成
    - aggregating: 正在聚合结果
    - completed: 搜索全部完成
    """
    stage: str  # decomposing, queries_ready, searching, search_done, aggregating, completed
    message: str
    queries: Optional[List[Dict[str, Any]]] = None  # 查询列表，每个包含 {query, status, results_count}
    current_query: Optional[str] = None  # 当前正在处理的查询
    total_results: int = 0
    elapsed_time: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "type": "search_progress",
            "stage": self.stage,
            "message": self.message,
        }
        if self.queries is not None:
            data["queries"] = self.queries
        if self.current_query is not None:
            data["current_query"] = self.current_query
        if self.total_results > 0:
            data["total_results"] = self.total_results
        if self.elapsed_time > 0:
            data["elapsed_time"] = round(self.elapsed_time, 2)
        return data


@dataclass
class RAGProgressEvent:
    """
    RAG 搜索进度事件 - 用于 RAG 工具的流式进度显示
    
    阶段:
    - searching: 正在搜索知识库
    - completed: 搜索完成
    """
    stage: str  # searching, completed
    message: str
    query: Optional[str] = None  # 当前查询
    total_results: int = 0
    elapsed_time: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "type": "rag_progress",
            "stage": self.stage,
            "message": self.message,
        }
        if self.query is not None:
            data["query"] = self.query
        if self.total_results > 0:
            data["total_results"] = self.total_results
        if self.elapsed_time > 0:
            data["elapsed_time"] = round(self.elapsed_time, 2)
        return data


# ==================== 导出 ====================

__all__ = [
    # 枚举
    "ToolType",
    "ActionType",
    # 配置
    "ToolConfig",
    # 结果
    "ToolCallResult",
    "PlannerOutput",
    "AgentContext",
    "AgentStep",
    # 事件
    "ReasoningDeltaEvent",
    "SearchProgressEvent",
    "RAGProgressEvent",
    "PlanCompleteEvent",
    "ToolCallEvent",
    "ToolResultEvent",
    "FileTransferEvent",
    "ErrorEvent",
]
