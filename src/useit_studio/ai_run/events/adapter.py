"""
事件适配器 - 将旧格式事件转换为标准格式

负责将现有代码中的各种事件格式转换为统一的标准事件格式
"""

from typing import Dict, Any, Optional
import logging

from .schemas import (
    BaseStreamEvent,
    TextEvent,
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
    StandardEvent,
)

logger = logging.getLogger(__name__)


class EventAdapter:
    """
    事件适配器

    将各个层级（Loop, Planner, Actor）生成的旧格式事件转换为标准格式
    """

    @staticmethod
    def convert(raw_event: Dict[str, Any], trace_id: Optional[str] = None) -> Optional[StandardEvent]:
        """
        转换原始事件为标准格式

        Args:
            raw_event: 原始事件字典
            trace_id: 追踪ID

        Returns:
            标准格式事件，如果无法转换则返回None
        """
        event_type = raw_event.get("type")

        if not event_type:
            logger.warning(f"Event missing 'type' field: {raw_event}")
            return None

        # 根据事件类型选择转换方法
        converter_map = {
            # === 前端可见事件（直接映射）===
            "text": EventAdapter._convert_text_event,
            "cua_start": EventAdapter._convert_cua_start_event,
            "cua_delta": EventAdapter._convert_cua_delta_event,
            "cua_update": EventAdapter._convert_cua_update_event,
            "cua_request": EventAdapter._convert_cua_request_event,
            "cua_end": EventAdapter._convert_cua_end_event,
            "error": EventAdapter._convert_error_event,
            "workflow_completed": EventAdapter._convert_workflow_completed_event,
            "workflow_progress": EventAdapter._convert_workflow_progress_event,

            # === 前端可见的节点事件 ===
            "node_start": EventAdapter._convert_node_start_event,
            "node_end": EventAdapter._convert_node_end_event,
            "node_complete": EventAdapter._convert_node_complete_event,  # 也发送给前端

            # === 内部事件（转为 InternalNodeEvent）===
            "planner_complete": EventAdapter._convert_planner_complete_event,
            "tool_call": EventAdapter._convert_tool_call_event,
            "flow_control_complete": EventAdapter._convert_flow_control_complete_event,
            "functional_complete": EventAdapter._convert_functional_complete_event,
            "mcp_complete": EventAdapter._convert_mcp_complete_event,
            "tool_complete": EventAdapter._convert_tool_complete_event,

            # === AI Run 特定事件（转为内部事件）===
            "config_info": EventAdapter._convert_config_info_event,
            "status": EventAdapter._convert_status_event,
            "metadata": EventAdapter._convert_metadata_event,
            "final_result": EventAdapter._convert_final_result_event,
            "done": EventAdapter._convert_done_event,
        }

        converter = converter_map.get(event_type)

        if converter:
            try:
                event = converter(raw_event, trace_id)
                return event
            except Exception as e:
                logger.error(f"Failed to convert event {event_type}: {e}", exc_info=True)
                return None
        else:
            logger.debug(f"No converter for event type: {event_type}")
            return None

    # ==================== 直接映射的事件转换 ====================

    @staticmethod
    def _convert_text_event(raw: Dict[str, Any], trace_id: Optional[str]) -> TextEvent:
        """转换文本事件"""
        return TextEvent(
            delta=raw.get("delta", ""),
            trace_id=trace_id
        )

    @staticmethod
    def _convert_cua_start_event(raw: Dict[str, Any], trace_id: Optional[str]) -> CUAStartEvent:
        """转换CUA开始事件"""
        return CUAStartEvent(
            cuaId=raw.get("cuaId", ""),
            step=raw.get("step", 0),
            title=raw.get("title", ""),
            nodeId=raw.get("nodeId"),
            screenshotIndex=raw.get("screenshotIndex", 0),
            trace_id=trace_id
        )

    @staticmethod
    def _convert_cua_delta_event(raw: Dict[str, Any], trace_id: Optional[str]) -> CUADeltaEvent:
        """转换CUA增量事件"""
        # 兼容 "role" 和 "kind" 两种字段名
        kind = raw.get("kind") or raw.get("role", "planner")

        return CUADeltaEvent(
            cuaId=raw.get("cuaId", ""),
            reasoning=raw.get("reasoning", ""),
            kind=kind,
            trace_id=trace_id
        )

    @staticmethod
    def _convert_cua_update_event(raw: Dict[str, Any], trace_id: Optional[str]) -> CUAUpdateEvent:
        """转换CUA更新事件"""
        # 兼容 "role" 和 "kind" 两种字段名
        kind = raw.get("kind") or raw.get("role", "actor")

        return CUAUpdateEvent(
            cuaId=raw.get("cuaId", ""),
            content=raw.get("content", {}),
            kind=kind,
            trace_id=trace_id
        )

    @staticmethod
    def _convert_cua_request_event(raw: Dict[str, Any], trace_id: Optional[str]) -> CUARequestEvent:
        """转换CUA请求事件"""
        return CUARequestEvent(
            cuaId=raw.get("cuaId", ""),
            requestId=raw.get("requestId", ""),
            requestType=raw.get("requestType", ""),
            params=raw.get("params", {}),
            timeout=raw.get("timeout", 60),
            trace_id=trace_id
        )

    @staticmethod
    def _convert_cua_end_event(raw: Dict[str, Any], trace_id: Optional[str]) -> CUAEndEvent:
        """转换CUA结束事件"""
        # 兼容旧状态：部分代码会发 "failed"，但 schema 只接受 completed|error|action_generated
        status = raw.get("status", "completed")
        if status == "failed":
            status = "error"
        return CUAEndEvent(
            cuaId=raw.get("cuaId", ""),
            status=status,
            title=raw.get("title"),
            action=raw.get("action"),
            error=raw.get("error"),
            trace_id=trace_id
        )

    @staticmethod
    def _convert_error_event(raw: Dict[str, Any], trace_id: Optional[str]) -> ErrorEvent:
        """转换错误事件"""
        return ErrorEvent(
            content=raw.get("content", "") or raw.get("error", "") or raw.get("message", "Unknown error"),
            error_code=raw.get("error_code"),
            details=raw.get("details"),
            trace_id=trace_id
        )

    @staticmethod
    def _convert_workflow_completed_event(raw: Dict[str, Any], trace_id: Optional[str]) -> WorkflowCompleteEvent:
        """转换工作流完成事件（将 workflow_completed 转换为前端期望的 workflow_complete）"""
        return WorkflowCompleteEvent(
            trace_id=trace_id
        )

    @staticmethod
    def _convert_workflow_progress_event(raw: Dict[str, Any], trace_id: Optional[str]) -> WorkflowProgressEvent:
        """转换工作流进度事件（节点切换通知）"""
        return WorkflowProgressEvent(
            content=raw.get("content", {}),
            trace_id=trace_id
        )

    # ==================== 前端可见的节点事件 ====================

    @staticmethod
    def _convert_node_start_event(raw: Dict[str, Any], trace_id: Optional[str]) -> NodeStartEvent:
        """
        转换节点开始事件（发送给前端显示 Node 卡片）

        原始事件格式:
            {"type": "node_start", "nodeId": "...", "title": "...", "nodeType": "...", "instruction": "...", "progress": {...}}
        """
        return NodeStartEvent(
            nodeId=raw.get("nodeId", ""),
            title=raw.get("title", ""),
            nodeType=raw.get("nodeType", ""),
            instruction=raw.get("instruction"),
            progress=raw.get("progress"),
            trace_id=trace_id
        )

    @staticmethod
    def _convert_node_end_event(raw: Dict[str, Any], trace_id: Optional[str]) -> NodeEndEvent:
        """
        转换节点结束事件（发送给前端更新 Node 卡片状态）

        原始事件格式:
            {"type": "node_end", "nodeId": "...", "status": "completed|failed|error", "progress": {...}}
        """
        status = raw.get("status", "completed")
        # 兼容旧状态
        if status not in ["completed", "failed", "error"]:
            status = "completed"
        return NodeEndEvent(
            nodeId=raw.get("nodeId", ""),
            status=status,
            progress=raw.get("progress"),
            trace_id=trace_id
        )

    @staticmethod
    def _convert_node_complete_event(raw: Dict[str, Any], trace_id: Optional[str]) -> NodeEndEvent:
        """
        转换节点完成事件为前端可见的 NodeEndEvent

        原始事件格式（AI Run 发送）:
            {"type": "node_complete", "nodeId": "...", "status": "...", "result": {...}, "content": {...}}
        
        转换为前端期望的格式:
            {"type": "node_end", "nodeId": "...", "status": "completed|failed|error"}
        """
        # 尝试从不同位置获取 nodeId
        node_id = raw.get("nodeId") or raw.get("node_id", "")
        if not node_id:
            content = raw.get("content", {})
            if isinstance(content, dict):
                node_id = content.get("node_id", "")
        
        # 获取状态
        status = raw.get("status", "completed")
        if status not in ["completed", "failed", "error"]:
            # 检查 content 中的 is_node_completed
            content = raw.get("content", {})
            if isinstance(content, dict):
                is_completed = content.get("is_node_completed", True)
                status = "completed" if is_completed else "running"
            else:
                status = "completed"
        
        # 如果状态是 running，映射为 completed（前端 node_end 只接受 completed/failed/error）
        if status == "running":
            status = "completed"
        
        return NodeEndEvent(
            nodeId=node_id,
            status=status,
            progress=raw.get("progress"),
            trace_id=trace_id
        )

    # ==================== 需要转换的事件 ====================

    @staticmethod
    def _convert_planner_complete_event(raw: Dict[str, Any], trace_id: Optional[str]) -> InternalNodeEvent:
        """
        转换 Planner 完成事件为内部事件

        原始事件格式:
            {"type": "planner_complete", "content": {...}}
        """
        return InternalNodeEvent(
            type="internal.planner_complete",
            metadata=raw.get("content", {}),
            trace_id=trace_id
        )

    @staticmethod
    def _convert_tool_call_event(raw: Dict[str, Any], trace_id: Optional[str]) -> ToolCallEvent:
        """
        转换工具调用事件 - 直接透传，保持 tool_call 类型

        标准格式:
            {
                "type": "tool_call",
                "id": "call_xxx",
                "target": "gui" | "word" | "excel" | "ppt" | "browser" | "autocad" | "code",
                "name": "click" | "execute_code" | "execute_python" | ...,
                "args": {...}
            }
        """
        return ToolCallEvent(
            id=raw.get("id", ""),
            target=raw.get("target", "gui"),
            name=raw.get("name", ""),
            args=raw.get("args", {}),
            trace_id=trace_id
        )

    @staticmethod
    def _convert_flow_control_complete_event(raw: Dict[str, Any], trace_id: Optional[str]) -> InternalNodeEvent:
        """转换流控制完成事件为内部事件"""
        return InternalNodeEvent(
            type="internal.flow_control_complete",
            metadata=raw.get("content", {}),
            trace_id=trace_id
        )

    @staticmethod
    def _convert_functional_complete_event(raw: Dict[str, Any], trace_id: Optional[str]) -> InternalNodeEvent:
        """转换功能节点完成事件为内部事件"""
        return InternalNodeEvent(
            type="internal.functional_complete",
            metadata=raw.get("content", {}),
            trace_id=trace_id
        )

    @staticmethod
    def _convert_mcp_complete_event(raw: Dict[str, Any], trace_id: Optional[str]) -> InternalNodeEvent:
        """转换MCP完成事件为内部事件"""
        return InternalNodeEvent(
            type="internal.mcp_complete",
            metadata=raw.get("content", {}),
            trace_id=trace_id
        )

    @staticmethod
    def _convert_tool_complete_event(raw: Dict[str, Any], trace_id: Optional[str]) -> InternalNodeEvent:
        """转换工具完成事件为内部事件"""
        return InternalNodeEvent(
            type="internal.tool_complete",
            metadata=raw.get("content", {}),
            trace_id=trace_id
        )

    # ==================== AI Run 特定事件转换 ====================

    @staticmethod
    def _convert_config_info_event(raw: Dict[str, Any], trace_id: Optional[str]) -> InternalNodeEvent:
        """转换配置信息事件"""
        return InternalNodeEvent(
            type="internal.config_info",
            metadata=raw.get("content", {}),
            trace_id=trace_id
        )

    @staticmethod
    def _convert_status_event(raw: Dict[str, Any], trace_id: Optional[str]) -> InternalNodeEvent:
        """转换状态事件"""
        return InternalNodeEvent(
            type="internal.status",
            metadata={"message": raw.get("content", "")},
            trace_id=trace_id
        )

    @staticmethod
    def _convert_metadata_event(raw: Dict[str, Any], trace_id: Optional[str]) -> InternalNodeEvent:
        """转换元数据事件"""
        return InternalNodeEvent(
            type="internal.metadata",
            metadata=raw.get("content", {}),
            trace_id=trace_id
        )

    @staticmethod
    def _convert_final_result_event(raw: Dict[str, Any], trace_id: Optional[str]) -> InternalNodeEvent:
        """转换最终结果事件"""
        return InternalNodeEvent(
            type="internal.final_result",
            metadata=raw.get("content", {}),
            trace_id=trace_id
        )

    @staticmethod
    def _convert_done_event(raw: Dict[str, Any], trace_id: Optional[str]) -> InternalNodeEvent:
        """转换完成事件"""
        return InternalNodeEvent(
            type="internal.done",
            metadata={},
            trace_id=trace_id
        )
