"""
AI Run 事件 Schema 定义

基于 message-schema-v4.md 定义的标准事件格式
所有事件使用 Pydantic 进行类型验证
"""

from typing import Any, Dict, Literal, Optional, Union
from pydantic import BaseModel, Field
from datetime import datetime
import time


class BaseStreamEvent(BaseModel):
    """所有流式事件的基类"""

    type: str
    timestamp: float = Field(default_factory=time.time)
    trace_id: Optional[str] = None

    class Config:
        extra = "allow"  # 允许额外字段，向后兼容


class TextEvent(BaseStreamEvent):
    """
    文本增量事件

    示例:
        {"type": "text", "delta": "好的，我来帮您操作 91 卫图助手。\\n\\n"}
    """

    type: Literal["text"] = "text"
    delta: str


class ClientRequestEvent(BaseStreamEvent):
    """
    请求客户端执行操作事件

    示例:
        {"type": "client_request", "requestId": "req_1", "action": "screenshot"}
    """

    type: Literal["client_request"] = "client_request"
    requestId: str
    action: str
    params: Optional[Dict[str, Any]] = None


class CUAStartEvent(BaseStreamEvent):
    """
    CUA (Computer Use Action) 步骤开始事件

    示例:
        {"type": "cua_start", "cuaId": "cua_1", "step": 1, "title": "第 1 步", "nodeId": "node_1", "screenshotIndex": 0}
    """

    type: Literal["cua_start"] = "cua_start"
    cuaId: str
    step: int
    title: str
    nodeId: Optional[str] = None  # 所属节点 ID
    screenshotIndex: Optional[int] = 0


class CUADeltaEvent(BaseStreamEvent):
    """
    CUA 思考过程增量事件

    示例:
        {"type": "cua_delta", "cuaId": "cua_1", "reasoning": "我看到了...", "kind": "planner"}
    """

    type: Literal["cua_delta"] = "cua_delta"
    cuaId: str
    reasoning: str
    kind: Literal["planner", "actor"]


class CUAUpdateEvent(BaseStreamEvent):
    """
    CUA 内容更新事件

    示例:
        {"type": "cua_update", "cuaId": "cua_1", "content": {"type": "click", "x": 500, "y": 100}, "kind": "actor"}
    """

    type: Literal["cua_update"] = "cua_update"
    cuaId: str
    content: Dict[str, Any]
    kind: Literal["planner", "actor"]


class CUARequestEvent(BaseStreamEvent):
    """
    CUA 请求数据事件

    用于请求客户端提供特定数据（如Excel快照、AutoCAD数据等）

    示例:
        {
            "type": "cua_request",
            "cuaId": "cua_2",
            "requestId": "req_excel_snapshot",
            "requestType": "excel_snapshot",
            "params": {
                "file_path": "C:\\Reports\\sales_data.xlsx",
                "application": "excel",
                "snapshot_type": "full"
            },
            "timeout": 60
        }
    """

    type: Literal["cua_request"] = "cua_request"
    cuaId: str
    requestId: str
    requestType: str
    params: Dict[str, Any]
    timeout: Optional[int] = 60


class CUAEndEvent(BaseStreamEvent):
    """
    CUA 步骤结束事件

    示例:
        {"type": "cua_end", "cuaId": "cua_1", "status": "completed", "title": "点击搜索框", "action": {...}}
    """

    type: Literal["cua_end"] = "cua_end"
    cuaId: str
    status: Literal["completed", "error", "action_generated"]
    title: Optional[str] = None
    action: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class ToolCallEvent(BaseStreamEvent):
    """
    工具调用事件 - 直接透传给前端执行
    
    标准格式:
        {
            "type": "tool_call",
            "id": "call_xxx",
            "target": "gui" | "word" | "excel" | "ppt" | "browser" | "autocad" | "code",
            "name": "click" | "type" | "execute_code" | "execute_python" | ...,
            "args": {...}
        }
    """
    
    type: Literal["tool_call"] = "tool_call"
    id: str
    target: str  # gui, word, excel, ppt
    name: str    # click, type, scroll, execute_code, etc.
    args: Dict[str, Any]


class ErrorEvent(BaseStreamEvent):
    """
    错误事件

    示例:
        {"type": "error", "content": "Failed to execute action", "error_code": "ACTION_FAILED"}
    """

    type: Literal["error"] = "error"
    content: str
    error_code: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class WorkflowCompleteEvent(BaseStreamEvent):
    """
    工作流完成事件

    示例:
        {"type": "workflow_complete"}
    
    注意：前端期望 "workflow_complete"（没有 d），而不是 "workflow_completed"
    """

    type: Literal["workflow_complete"] = "workflow_complete"


class WorkflowProgressEvent(BaseStreamEvent):
    """
    工作流进度事件（节点切换通知）

    示例:
        {"type": "workflow_progress", "content": {"next_node_id": "node_2", "is_workflow_completed": false}}
    """

    type: Literal["workflow_progress"] = "workflow_progress"
    content: Dict[str, Any]


class NodeStartEvent(BaseStreamEvent):
    """
    节点开始事件（发送给前端显示 Node 卡片）

    示例:
        {"type": "node_start", "nodeId": "node_1", "title": "执行电脑操作", "nodeType": "computer-use-gui"}
    """

    type: Literal["node_start"] = "node_start"
    nodeId: str
    title: str
    nodeType: str
    instruction: Optional[str] = None
    progress: Optional[Dict[str, Any]] = None


class NodeEndEvent(BaseStreamEvent):
    """
    节点结束事件（发送给前端更新 Node 卡片状态）

    示例:
        {"type": "node_end", "nodeId": "node_1", "status": "completed"}
    """

    type: Literal["node_end"] = "node_end"
    nodeId: str
    status: Literal["completed", "failed", "error"]
    progress: Optional[Dict[str, Any]] = None


# ==================== 内部事件（不发送给前端）====================

class InternalNodeEvent(BaseStreamEvent):
    """
    内部节点事件（仅用于后端日志和调试）

    这些事件不会发送给前端，仅在后端记录
    """

    type: Literal[
        "internal.node_start",
        "internal.node_complete",
        "internal.planner_complete",
        "internal.actor_complete",
        "internal.flow_control_complete",
        "internal.functional_complete",
        "internal.mcp_complete",
        "internal.tool_complete",
        # AI Run 特定内部事件
        "internal.config_info",
        "internal.status",
        "internal.metadata",
        "internal.final_result",
        "internal.done",
    ]
    node_id: Optional[str] = None
    node_type: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


# 联合类型，用于类型提示
StandardEvent = Union[
    TextEvent,
    ClientRequestEvent,
    CUAStartEvent,
    CUADeltaEvent,
    CUAUpdateEvent,
    CUARequestEvent,
    CUAEndEvent,
    ToolCallEvent,
    ErrorEvent,
    WorkflowCompleteEvent,
    WorkflowProgressEvent,
    NodeStartEvent,
    NodeEndEvent,
    InternalNodeEvent,
]
