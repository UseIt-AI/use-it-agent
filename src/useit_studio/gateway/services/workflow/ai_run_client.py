"""
AIRunClient - AI_Run服务客户端
"""

import asyncio
import aiohttp
import json
import os
import uuid
from typing import AsyncGenerator, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


# 未开启 USEIT_FORWARD_THINKING_SSE 时，仍转发的 cua_delta（进度/结果卡片，非模型自由思考流）
_CUA_DELTA_KIND_THINKING_ALLOWLIST = frozenset(
    {
        "search_progress",
        "search_result",
        "extract_progress",
        "extract_result",
        "rag_progress",
    }
)


def _forward_thinking_sse_enabled() -> bool:
    """
    仅当 USEIT_FORWARD_THINKING_SSE=1/true/yes/on 时，向浏览器 SSE 转发模型思考类流
    （reasoning_delta；以及非白名单的 cua_delta，含 planner/actor 与 Agent 节点的 tool:*）。
    默认未设置则不转发上述内容。
    """
    v = os.getenv("USEIT_FORWARD_THINKING_SSE", "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _should_drop_thinking_stream_for_frontend(event: Dict[str, Any]) -> bool:
    if _forward_thinking_sse_enabled():
        return False
    et = event.get("type", "")
    if et == "reasoning_delta":
        return True
    if et != "cua_delta":
        return False
    role = (event.get("kind") or event.get("role") or "").strip().lower()
    if role in _CUA_DELTA_KIND_THINKING_ALLOWLIST:
        return False
    return True


class AIRunClient:
    """AI_Run 客户端：HTTP（独立服务）或与 web_app 同进程的直连。"""

    # ===== 事件过滤：前端可见事件类型（根据 message-schema-v4.md）=====
    FRONTEND_VISIBLE_EVENTS = {
        "text",
        "client_request",
        "tool_call",           # GUI/Office 动作执行请求（新标准格式）
        "cua_start",
        "cua_delta",
        "cua_update",
        "cua_request",  # 暂未实现，但预留
        "cua_end",
        "error",
        "workflow_completed",  # 工作流完成事件（AI Run 发送）
        "workflow_complete",   # 工作流完成事件（转换后）
        "workflow_progress",   # 工作流进度事件（节点切换通知）
        "node_start",          # 节点开始事件
        "node_end",            # 节点结束事件
        "node_complete",       # 节点完成事件（会被转换为 node_end）
    }

    def __init__(self, base_url: str = "http://localhost:8326", *, use_in_process: bool = False):
        self.base_url = base_url.rstrip("/")
        self.use_in_process = use_in_process
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        if self.use_in_process:
            return self
        timeout = aiohttp.ClientTimeout(
            total=300,
            connect=30,
            sock_read=120,
        )
        self.session = aiohttp.ClientSession(timeout=timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
            self.session = None

    async def _ensure_session(self):
        """确保会话存在"""
        if self.use_in_process:
            return
        if not self.session or self.session.closed:
            timeout = aiohttp.ClientTimeout(
                total=300,
                connect=30,
                sock_read=120,
            )
            self.session = aiohttp.ClientSession(timeout=timeout)

    async def _emit_one_orchestrator_event(
        self, event: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """将单条编排器原始事件转换为网关侧产出（与 HTTP SSE 解析后逻辑一致）。"""
        event_type = event.get("type", "")

        if event_type == "final_result":
            content = event.get("content", {})
            if isinstance(content, dict):
                step_usage = content.get("step_token_usage")
                if step_usage:
                    cs = step_usage.get("current_step") or {}
                    logger.info(
                        "[TokenUsage][Orchestrator] 来源=final_result step=%s",
                        cs.get("step_number"),
                    )
                    yield {
                        "type": "_internal_step_token_usage",
                        "step_token_usage": step_usage,
                    }
            return

        if event_type == "internal.step_token_usage":
            step_usage = event.get("content", {})
            if step_usage:
                cs = step_usage.get("current_step") or {}
                logger.info(
                    "[TokenUsage][Orchestrator] 来源=internal.step_token_usage step=%s",
                    cs.get("step_number"),
                )
                yield {
                    "type": "_internal_step_token_usage",
                    "step_token_usage": step_usage,
                }
            return

        if event_type in self.ORCHESTRATOR_VISIBLE_EVENTS:
            if not _should_drop_thinking_stream_for_frontend(event):
                yield event
            return
        if event_type == "done":
            yield event
            return
        if event_type.startswith("internal."):
            return
        if not _should_drop_thinking_stream_for_frontend(event):
            yield event

    async def stream_computer_use_action(
        self,
        instruction: str,
        screenshot_base64: Optional[str] = None,
        additional_context: Optional[str] = None,
        uia_data: Optional[Dict[str, Any]] = None,
        task_id: Optional[str] = None,
        workflow_id: Optional[str] = None,
        user_id: Optional[str] = None,
        project_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        execution_result: Optional[Dict[str, Any]] = None,  # tool_call 执行结果
        attached_files: Optional[list] = None,  # 附加的文件/文件夹列表
        attached_images: Optional[list] = None,  # 附加的图片列表（base64）
        user_api_keys: Optional[Dict[str, str]] = None,  # 用户自有 API 密钥
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        调用 AI_Run 的 ``POST /agent`` 编排器端点（与 ``stream_agent_action`` 一致）。

        此前直连 ``/generate_action_stream_langchain`` 的路径已移除；历史调用方仍可使用本方法名。
        """
        tid = task_id or str(uuid.uuid4())
        async for ev in self.stream_agent_action(
            query=instruction,
            task_id=tid,
            execution_result=execution_result,
            screenshot_base64=screenshot_base64,
            uia_data=uia_data,
            project_id=project_id,
            chat_id=chat_id,
            user_id=user_id,
            attached_files=attached_files,
            attached_images=attached_images,
            user_api_keys=user_api_keys,
            additional_context=additional_context,
            workflow_id=workflow_id,
        ):
            yield ev
    
    # ===== Orchestrator endpoint =====
    ORCHESTRATOR_VISIBLE_EVENTS = FRONTEND_VISIBLE_EVENTS | {
        "orchestrator_decision",
        "orchestrator_observation",
        "orchestrator_complete",
        "workflow_started",
    }

    async def stream_agent_action(
        self,
        query: str,
        task_id: str,
        *,
        execution_result: Optional[Dict[str, Any]] = None,
        screenshot_base64: Optional[str] = None,
        uia_data: Optional[Dict[str, Any]] = None,
        project_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        user_id: Optional[str] = None,
        attached_files: Optional[list] = None,
        attached_images: Optional[list] = None,
        user_api_keys: Optional[Dict[str, str]] = None,
        app_capabilities: Optional[list] = None,
        workflow_capabilities: Optional[list] = None,
        additional_context: Optional[str] = None,
        workflow_id: Optional[str] = None,
        workflow_run_id: Optional[str] = None,
        chat_history: Optional[list] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        调用 AI Run 编排器 ``POST /agent``，消费 SSE 事件流（与 ``stream_computer_use_action`` 协议相同）。
        同进程模式下直接调用 ``web_app.iter_agent_orchestrator_events``，不经 HTTP。
        """
        payload: Dict[str, Any] = {
            "query": query,
            "task_id": task_id,
        }
        if screenshot_base64:
            payload["screenshot"] = screenshot_base64
        if uia_data:
            payload["uia_data"] = uia_data
        if project_id:
            payload["project_id"] = project_id
        if chat_id:
            payload["chat_id"] = chat_id
        if user_id:
            payload["user_id"] = user_id
        if execution_result:
            payload["execution_result"] = execution_result
        if attached_files:
            payload["attached_files"] = attached_files
        if attached_images:
            payload["attached_images"] = attached_images
        if user_api_keys:
            payload["user_api_keys"] = user_api_keys
        if app_capabilities is not None:
            payload["app_capabilities"] = app_capabilities
        if workflow_capabilities is not None:
            payload["workflow_capabilities"] = workflow_capabilities
        if additional_context:
            payload["additional_context"] = additional_context
        if workflow_id:
            payload["workflow_id"] = workflow_id
        payload["workflow_run_id"] = workflow_run_id
        if chat_history:
            payload["chat_history"] = chat_history

        if self.use_in_process:
            logger.info("[AIRunClient] in-process orchestrator (no HTTP)")
            try:
                from useit_studio.ai_run.web_app import iter_agent_orchestrator_events

                async for event in iter_agent_orchestrator_events(payload):
                    async for out in self._emit_one_orchestrator_event(event):
                        yield out
            except asyncio.CancelledError:
                logger.info(
                    "[AIRunClient] orchestrator stream cancelled by client (stop/disconnect)"
                )
                raise
            except Exception as e:
                logger.error(f"Orchestrator stream failed: {e}")
                yield {"type": "error", "content": f"Orchestrator error: {str(e)}"}
            return

        await self._ensure_session()

        url = f"{self.base_url}/agent"
        logger.info(f"[AIRunClient] POST {url} (orchestrator)")

        try:
            async with self.session.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"AI_Run orchestrator error {response.status}: {error_text}")

                async for line in response.content:
                    line = line.decode("utf-8").strip()
                    if not line:
                        continue

                    if line.startswith("data: "):
                        json_str = line[6:]
                        if not json_str:
                            continue
                    else:
                        json_str = line

                    try:
                        event = json.loads(json_str)
                    except json.JSONDecodeError:
                        preview = line if len(line) <= 200 else f"{line[:200]}..."
                        logger.debug(
                            "Orchestrator stream: skipped line (not valid JSON after SSE strip or as NDJSON): %s",
                            preview,
                        )
                        continue

                    async for out in self._emit_one_orchestrator_event(event):
                        yield out

        except asyncio.CancelledError:
            logger.info("[AIRunClient] orchestrator stream cancelled by client (stop/disconnect)")
            raise
        except Exception as e:
            logger.error(f"Orchestrator stream failed: {e}")
            yield {"type": "error", "content": f"Orchestrator error: {str(e)}"}

    async def health_check(self) -> bool:
        """健康检查"""
        if self.use_in_process:
            try:
                from useit_studio.ai_run.runtime.state_store import StateStoreFactory

                StateStoreFactory.get_store()
                return True
            except Exception:
                return False

        created_here = False
        if not self.session or self.session.closed:
            timeout = aiohttp.ClientTimeout(
                total=300,
                connect=30,
                sock_read=60,
            )
            self.session = aiohttp.ClientSession(timeout=timeout)
            created_here = True

        try:
            async with self.session.get(f"{self.base_url}/health") as response:
                return response.status == 200
        except Exception:
            return False
        finally:
            if created_here and self.session and not self.session.closed:
                await self.session.close()
                self.session = None

    async def close(self):
        """关闭客户端"""
        if self.session and not self.session.closed:
            await self.session.close()
        self.session = None

    def __del__(self):
        """安全网：如果对象被垃圾回收但session未关闭，发出警告"""
        if getattr(self, "use_in_process", False):
            return
        if hasattr(self, "session") and self.session and not self.session.closed:
            logger.warning(
                "AIRunClient被回收但aiohttp session未关闭。请使用 'async with' 或显式调用 close()。"
            )


class CUAEventConverter:
    """CUA事件格式转换器

    注意：AI_Run 现在使用标准事件格式，此转换器仅做透传和验证。
    事件过滤工作在 AIRunClient 层完成。

    事件格式说明：
    - cua_delta: {type, cuaId, reasoning, kind} - 思考过程（planner/actor）
    - cua_update: {type, cuaId, content, kind} - 动作内容（actor）
    """

    # 前端可见事件类型（与 AIRunClient.FRONTEND_VISIBLE_EVENTS 保持一致）
    FRONTEND_VISIBLE_EVENTS = {
        "text",
        "client_request",
        "tool_call",           # GUI/Office 动作执行请求（新标准格式）
        "cua_start",
        "cua_delta",
        "cua_update",
        "cua_request",
        "cua_end",
        "error",
        "workflow_completed",
        "workflow_complete",
        "workflow_progress",
        "node_start",
        "node_end",
        "node_complete",
    }

    @staticmethod
    def convert_to_engineering_format(ai_run_event: Dict[str, Any]) -> Dict[str, Any]:
        """
        透传事件（AI_Run 已生成标准格式）

        注意：过滤工作在 AIRunClient 层完成

        Args:
            ai_run_event: AI_Run的标准格式事件

        Returns:
            Dict[str, Any]: 直接返回原事件
        """
        return ai_run_event

    @staticmethod
    def is_frontend_visible(event: Dict[str, Any]) -> bool:
        """判断事件是否对前端可见"""
        event_type = event.get("type", "")

        # internal.* 开头的都是内部事件
        if event_type.startswith("internal."):
            return False

        return event_type in CUAEventConverter.FRONTEND_VISIBLE_EVENTS

    @staticmethod
    def is_planner_event(event: Dict[str, Any]) -> bool:
        """判断是否是planner事件"""
        return (
            event.get("type") == "cua_delta" and
            event.get("kind") == "planner"
        )

    @staticmethod
    def is_actor_event(event: Dict[str, Any]) -> bool:
        """判断是否是actor事件"""
        return event.get("kind") == "actor"