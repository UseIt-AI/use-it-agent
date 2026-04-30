"""
Tool Call 处理器 - 处理 tool_call 事件（新标准格式）
"""
import asyncio
import logging
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional

from ..constants import CALLBACK_TIMEOUT, TOOL_CALL_TIMEOUT
from ..interaction_manager import WorkflowInteractionManager
from ..utils.message_logger import log_message
from .screenshot_handler import ScreenshotHandler

logger = logging.getLogger(__name__)


class ToolCallHandler:
    """
    处理 tool_call 事件
    
    新格式 tool_call: 
    {
        type: "tool_call", 
        id: "...", 
        target: "gui"|"word"|..., 
        name: "click"|"execute_code"|..., 
        args: {...}
    }
    
    Frontend 直接处理并回调，Backend 等待回调结果
    """

    def __init__(self, screenshot_handler: ScreenshotHandler):
        self.screenshot_handler = screenshot_handler

    async def wait_for_callback(
        self,
        tool_call_id: str,
        target: str,
        name: str,
        interaction_manager: WorkflowInteractionManager,
        timeout: float = TOOL_CALL_TIMEOUT,
    ) -> Dict[str, Any]:
        """
        等待 tool_call 回调结果
        
        Args:
            tool_call_id: tool_call 的唯一标识
            target: 目标类型 (gui/word/excel 等)
            name: 动作名称
            interaction_manager: 交互管理器
            timeout: 超时时间
            
        Returns:
            包含执行结果和截图的字典
        """
        logger.info(f"[ToolCallHandler] 等待回调: id={tool_call_id}, target={target}, name={name}")
        print(f"[PERF] 🕐 开始等待 tool_call 回调 id={tool_call_id[:8]}... {target}.{name}")
        
        try:
            result_data = await interaction_manager.wait_for_result(tool_call_id, timeout=timeout)
            
            # 打印回调数据大小
            import json as _json
            result_json_str = _json.dumps(result_data, ensure_ascii=False, default=str)
            result_size_kb = len(result_json_str.encode('utf-8')) / 1024
            logger.info(f"[ToolCallHandler] 收到回调数据 大小: {result_size_kb:.2f}KB")
            print(f"[PERF] 📦 收到 tool_call 回调数据 大小: {result_size_kb:.2f}KB")
            
            # 记录回调
            log_message("RECV", {
                "type": "tool_call_callback",
                "tool_call_id": tool_call_id,
                "target": target,
                "name": name,
                "result_data": result_data,
            }, context="tool_call_callback")
            
            # 提取截图
            screenshot = self.screenshot_handler.extract_from_callback(result_data)
            # 提取项目文件列表
            project_files = self.screenshot_handler.extract_project_files(result_data)
            
            logger.info(f"[ToolCallHandler] 回调成功: id={tool_call_id}, has_screenshot={screenshot is not None}, has_project_files={project_files is not None}")
            
            return {
                "success": True,
                "tool_call_id": tool_call_id,
                "target": target,
                "name": name,
                "result": result_data,
                "screenshot": screenshot,
                "project_files": project_files,
                "error": None,
            }
            
        except asyncio.TimeoutError:
            logger.error(f"[ToolCallHandler] 回调超时: id={tool_call_id}")
            return {
                "success": False,
                "tool_call_id": tool_call_id,
                "target": target,
                "name": name,
                "result": None,
                "screenshot": None,
                "error": "timeout",
            }
        except Exception as e:
            logger.error(f"[ToolCallHandler] 回调失败: id={tool_call_id}, error={e}")
            return {
                "success": False,
                "tool_call_id": tool_call_id,
                "target": target,
                "name": name,
                "result": None,
                "screenshot": None,
                "error": str(e),
            }

    def is_stop_action(self, event: Dict[str, Any]) -> bool:
        """检查是否是 stop 动作"""
        return event.get("name") == "stop"

    def parse_tool_call(self, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        解析 tool_call 事件
        
        Args:
            event: tool_call 事件
            
        Returns:
            解析后的信息，如果不是有效的 tool_call 则返回 None
        """
        tool_call_id = event.get("id")
        target = event.get("target")
        name = event.get("name")
        
        if not (tool_call_id and target and name):
            return None
        
        return {
            "tool_call_id": tool_call_id,
            "target": target,
            "name": name,
            "args": event.get("args", {}),
        }


class ActionExecutor:
    """
    动作执行器 - 通过 SSE 请求前端执行动作（旧格式兼容）
    """

    def __init__(self, screenshot_handler: ScreenshotHandler):
        self.screenshot_handler = screenshot_handler

    async def execute_via_sse(
        self,
        actions: List[Dict[str, Any]],
        interaction_manager: WorkflowInteractionManager,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        通过 SSE 请求前端执行动作
        
        Args:
            actions: 要执行的动作列表
            interaction_manager: 交互管理器
            
        Yields:
            - client_request 事件（发给前端）
            - _internal_action_result 事件（内部使用）
        """
        if not interaction_manager:
            logger.error("[ActionExecutor] interaction_manager 未提供")
            yield {
                "type": "_internal_action_result",
                "success": False,
                "screenshot_base64": None,
                "error": "interaction_manager not provided"
            }
            return
        
        request_id = str(uuid.uuid4())
        
        client_request_event = {
            "type": "client_request",
            "requestId": request_id,
            "action": "execute_actions",
            "params": {"actions": actions}
        }
        
        action_types = [a.get("type", "unknown") for a in actions]
        logger.info(f"[ActionExecutor] 发送请求: request_id={request_id}, actions={action_types}")
        
        # 详细打印 scroll 动作参数
        for a in actions:
            if a.get("type") == "scroll":
                logger.info(f"[ActionExecutor] scroll 动作详情: {a}")
        
        log_message("SEND", client_request_event, context="execute_actions")
        yield client_request_event
        
        # 等待回调
        try:
            result_data = await interaction_manager.wait_for_result(request_id, timeout=CALLBACK_TIMEOUT)
            
            # 打印回调数据大小
            import json as _json
            result_json_str = _json.dumps(result_data, ensure_ascii=False, default=str)
            result_size_kb = len(result_json_str.encode('utf-8')) / 1024
            logger.info(f"[ActionExecutor] 收到动作执行回调 大小: {result_size_kb:.2f}KB")
            print(f"[PERF] 📦 收到动作执行回调 大小: {result_size_kb:.2f}KB")
            
            log_message("RECV", {
                "type": "callback_result",
                "request_id": request_id,
                "result_data": result_data,
            }, context="callback_from_frontend")
            
            screenshot_base64 = self.screenshot_handler.extract_from_callback(result_data)
            
            logger.info(f"[ActionExecutor] 收到回调: has_screenshot={screenshot_base64 is not None}")
            
            yield {
                "type": "_internal_action_result",
                "success": True,
                "screenshot_base64": screenshot_base64,
                "results": result_data.get("results") if isinstance(result_data, dict) else None,
                "error": None
            }
            
        except asyncio.TimeoutError:
            logger.error(f"[ActionExecutor] 请求超时: request_id={request_id}")
            yield {
                "type": "_internal_action_result",
                "success": False,
                "screenshot_base64": None,
                "error": "timeout"
            }
        except Exception as e:
            logger.error(f"[ActionExecutor] 请求失败: {e}")
            yield {
                "type": "_internal_action_result",
                "success": False,
                "screenshot_base64": None,
                "error": str(e)
            }
