"""
Event Adapter - 事件格式适配器

将 Workflow 内部事件转换为前端消息格式
"""

import uuid
from typing import Any, Dict, Optional


class EventAdapter:
    """
    事件格式适配器
    
    将后端事件格式转换为前端格式：
    - token -> text
    - workflow_start/complete/error -> 工作流生命周期事件
    - step_start/complete/error -> node_start/end
    - client_action_request -> client_request
    
    注意：CUA 事件 (cua_start/delta/update/end) 由 AI_Run 直接发出，原样透传。
    """
    
    def __init__(self):
        # 跟踪当前活跃的 Node
        self._current_node_id: Optional[str] = None
    
    def reset(self):
        """重置状态（新消息开始时调用）"""
        self._current_node_id = None
    
    def adapt(self, event: Dict[str, Any]) -> list[Dict[str, Any]]:
        """
        将单个事件转换为前端格式
        
        Args:
            event: 原始事件
            
        Returns:
            转换后的事件列表（一个原始事件可能产生多个事件）
        """
        event_type = event.get("type")
        content = event.get("content")
        
        # ==================== 文本事件 ====================
        if event_type == "token":
            return [{
                "type": "text",
                "delta": content or ""
            }]
        
        # ==================== 错误事件 ====================
        if event_type == "error":
            return [{
                "type": "error",
                "message": content or "Unknown error",
                "code": event.get("code")
            }]
        
        # ==================== 工作流事件 ====================
        if event_type == "workflow_start":
            # 工作流开始，不发送额外文本
            return []
        
        if event_type == "workflow_complete" or event_type == "workflow_completed":
            # 发送 workflow_complete 事件，前端会添加 CompletionBlock
            # 注意：AI Run 发送 "workflow_completed"，前端期望 "workflow_complete"
            return [{
                "type": "workflow_complete"
            }]
        
        if event_type == "workflow_error":
            error_msg = content.get("error") if isinstance(content, dict) else str(content)
            return [{
                "type": "error",
                "message": f"工作流错误: {error_msg}"
            }]
        
        # ==================== 步骤/节点事件 ====================
        if event_type == "step_start":
            if isinstance(content, dict):
                node_id = content.get("step_id", f"node_{uuid.uuid4().hex[:8]}")
                self._current_node_id = node_id
                
                # 确定节点类型
                step_name = content.get("step_name", "")
                node_type = "general"
                if "RAG" in step_name or "检索" in step_name:
                    node_type = "rag"
                elif "Export" in step_name or "导出" in step_name:
                    node_type = "export"
                elif "CUA" in step_name:
                    node_type = "cua"
                
                return [{
                    "type": "node_start",
                    "nodeId": node_id,
                    "title": content.get("step_name", "步骤"),
                    "nodeType": node_type,
                    "progress": {
                        "current": content.get("step_index", 1),
                        "total": content.get("total_steps"),
                        "message": content.get("description", "")
                    }
                }]
            return []
        
        if event_type == "step_complete":
            if isinstance(content, dict):
                node_id = content.get("step_id", self._current_node_id)
                results = [{
                    "type": "node_end",
                    "nodeId": node_id,
                    "status": "completed",
                    "progress": {
                        "current": content.get("step_index", 1),
                        "message": "完成"
                    }
                }]
                self._current_node_id = None
                return results
            return []
        
        if event_type == "step_error":
            if isinstance(content, dict):
                node_id = content.get("step_id", self._current_node_id)
                return [{
                    "type": "node_end",
                    "nodeId": node_id,
                    "status": "failed",
                    "progress": {
                        "message": content.get("error", "步骤执行失败")
                    }
                }]
            return []
        
        # ==================== 客户端请求事件 ====================
        if event_type == "client_action_request":
            if isinstance(content, dict):
                return [{
                    "type": "client_request",
                    "requestId": content.get("request_id", str(uuid.uuid4())),
                    "action": content.get("action", "screenshot"),
                    "params": content.get("params")
                }]
            return []
        
        # ==================== 忽略的事件（不发送给前端）====================
        if event_type in ["screenshots", "markdown_report", "status", "screenshot_received"]:
            # screenshots: 前端从 message.screenshots 获取
            # markdown_report: 内部事件
            # status: 内部状态，不需要显示
            # screenshot_received: 内部确认事件
            return []
        
        # _internal_* 事件是 executor 内部使用的，不发送给前端
        if event_type.startswith("_internal_"):
            return []
        
        # ==================== 项目信息事件 ====================
        if event_type == "project_info":
            # 项目信息事件，前端可能需要，保持原样
            return [event]
        
        # ==================== 默认：保持原样 ====================
        # 对于未识别的事件类型（包括 cua_start/delta/update/end, node_start/end），原样透传
        return [event]
    
    def finalize(self) -> list[Dict[str, Any]]:
        """
        结束适配，返回任何需要清理的事件
        """
        return []


def create_adapter() -> EventAdapter:
    """
    创建新的适配器实例
    """
    return EventAdapter()
