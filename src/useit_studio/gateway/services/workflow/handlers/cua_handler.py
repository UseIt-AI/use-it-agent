"""
CUA Request 处理器 - 处理 cua_request 事件（Bypass 模式）
"""
import asyncio
import logging
from typing import Any, Dict

import httpx

from ..constants import CUA_REQUEST_TIMEOUT, HTTP_REQUEST_TIMEOUT
from ..interaction_manager import WorkflowInteractionManager

logger = logging.getLogger(__name__)


class CUARequestHandler:
    """
    处理 cua_request 事件（纯 Bypass 模式）
    
    职责：
    1. 等待 Local Engine 返回数据（Frontend 负责转发给 Local Engine）
    2. 将数据发送回 AI Run
    
    注意：
    - Frontend 会自动将 cua_request 转发给 Local Engine
    - Local Engine 负责路由、参数映射和执行
    - Backend 只做等待和回调
    """

    def __init__(self, ai_run_url: str, *, use_in_process: bool = False):
        self.ai_run_url = ai_run_url
        self.use_in_process = use_in_process

    async def handle(
        self,
        request_event: Dict[str, Any],
        interaction_manager: WorkflowInteractionManager,
    ) -> None:
        """
        处理 cua_request（异步，不阻塞事件流）
        
        Args:
            request_event: cua_request 事件
            interaction_manager: 交互管理器
        """
        request_id = request_event.get("requestId")
        request_type = request_event.get("requestType")
        timeout = request_event.get("timeout", CUA_REQUEST_TIMEOUT)

        logger.info(f"[CUAHandler] 开始处理: request_id={request_id}, type={request_type}")

        try:
            if not interaction_manager:
                raise ValueError("interaction_manager is required for cua_request")

            # 等待 Local Engine 返回数据
            result_data = await interaction_manager.wait_for_result(
                request_id,
                timeout=timeout
            )

            logger.info(
                f"[CUAHandler] 收到 Local Engine 数据: request_id={request_id}, "
                f"size={len(str(result_data)) if result_data else 0} bytes"
            )

            # 发送给 AI Run
            await self._send_to_ai_run(request_id, result_data)
            logger.info(f"[CUAHandler] 处理成功: request_id={request_id}")

        except asyncio.TimeoutError:
            error_msg = f"请求超时：timeout={timeout}s"
            logger.error(f"[CUAHandler] 超时: request_id={request_id}")
            await self._send_error_to_ai_run(request_id, error_msg)

        except Exception as e:
            error_msg = f"请求失败：{str(e)}"
            logger.error(f"[CUAHandler] 失败: request_id={request_id}, error={e}", exc_info=True)
            await self._send_error_to_ai_run(request_id, error_msg)

    async def _send_to_ai_run(self, request_id: str, data: Dict[str, Any]) -> None:
        """将数据发送给 AI Run 回调端点"""
        payload = {
            "data": data,
            "error": None,
        }

        if self.use_in_process:
            logger.info(f"[CUAHandler] 发送到 AI Run: in_process request_id={request_id}")
            from useit_studio.ai_run.web_app import deliver_cua_request_response

            if deliver_cua_request_response(request_id, payload) != "ok":
                raise RuntimeError(
                    f"CUA 进程内投递失败: request_id={request_id} 未找到或已结束"
                )
            logger.info(f"[CUAHandler] 发送成功: request_id={request_id}")
            return

        url = f"{self.ai_run_url}/ai-run/request-response/{request_id}"
        logger.info(f"[CUAHandler] 发送到 AI Run: url={url}")

        async with httpx.AsyncClient(timeout=HTTP_REQUEST_TIMEOUT) as client:
            try:
                resp = await client.post(
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                resp.raise_for_status()
                logger.info(f"[CUAHandler] 发送成功: request_id={request_id}")
            except Exception as e:
                logger.error(f"[CUAHandler] 发送失败: {e}", exc_info=True)
                raise

    async def _send_error_to_ai_run(self, request_id: str, error_message: str) -> None:
        """通知 AI Run 请求失败"""
        payload = {
            "data": None,
            "error": error_message,
        }

        if self.use_in_process:
            logger.info(f"[CUAHandler] 发送错误到 AI Run: in_process request_id={request_id}")
            from useit_studio.ai_run.web_app import deliver_cua_request_response

            deliver_cua_request_response(request_id, payload)
            logger.info(f"[CUAHandler] 发送错误成功: request_id={request_id}")
            return

        url = f"{self.ai_run_url}/ai-run/request-response/{request_id}"

        async with httpx.AsyncClient(timeout=HTTP_REQUEST_TIMEOUT) as client:
            try:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                logger.info(f"[CUAHandler] 发送错误成功: request_id={request_id}")
            except Exception as e:
                logger.error(f"[CUAHandler] 发送错误失败: {e}", exc_info=True)
