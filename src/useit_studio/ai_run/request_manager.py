"""
CUA Request Manager

管理 cua_request 的 Future，用于 AI Run Node 请求前端数据的异步等待机制。
"""

import asyncio
import logging
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)


class RequestManager:
    """
    管理 cua_request 的 Future

    职责：
    - 创建请求和对应的 Future
    - 等待响应
    - 处理超时和错误
    """

    def __init__(self):
        # request_id -> Future
        self._pending_requests: Dict[str, asyncio.Future] = {}

    def create_request(self, request_id: str) -> asyncio.Future:
        """
        创建请求，返回 Future

        Args:
            request_id: 请求唯一标识

        Returns:
            asyncio.Future: 等待数据的 Future
        """
        if request_id in self._pending_requests:
            logger.warning(f"[RequestManager] Request {request_id} already exists, replacing")

        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._pending_requests[request_id] = future

        logger.info(f"[RequestManager] Created request: {request_id}")
        return future

    async def wait_for_response(
        self,
        request_id: str,
        timeout: float = 60.0
    ) -> Any:
        """
        等待响应数据

        Args:
            request_id: 请求ID
            timeout: 超时时间（秒）

        Returns:
            响应数据

        Raises:
            asyncio.TimeoutError: 超时
            ValueError: 请求不存在
        """
        if request_id not in self._pending_requests:
            raise ValueError(f"Request {request_id} not found")

        future = self._pending_requests[request_id]

        try:
            logger.info(f"[RequestManager] Waiting for response: {request_id} (timeout={timeout}s)")
            result = await asyncio.wait_for(future, timeout=timeout)
            logger.info(f"[RequestManager] Received response: {request_id}")
            return result
        except asyncio.TimeoutError:
            logger.error(f"[RequestManager] Request {request_id} timed out after {timeout}s")
            raise
        finally:
            # 清理
            self._pending_requests.pop(request_id, None)

    def resolve_request(self, request_id: str, data: Any) -> bool:
        """
        解决请求（设置 Future 结果）

        Args:
            request_id: 请求ID
            data: 响应数据

        Returns:
            bool: 是否成功
        """
        if request_id not in self._pending_requests:
            logger.warning(f"[RequestManager] Request {request_id} not found for resolve")
            return False

        future = self._pending_requests[request_id]
        if not future.done():
            future.set_result(data)
            logger.info(f"[RequestManager] Resolved request: {request_id}")
            return True
        else:
            logger.warning(f"[RequestManager] Request {request_id} already resolved")
            return False

    def reject_request(self, request_id: str, error_message: str) -> bool:
        """
        拒绝请求（设置 Future 异常）

        Args:
            request_id: 请求ID
            error_message: 错误信息

        Returns:
            bool: 是否成功
        """
        if request_id not in self._pending_requests:
            logger.warning(f"[RequestManager] Request {request_id} not found for reject")
            return False

        future = self._pending_requests[request_id]
        if not future.done():
            future.set_exception(Exception(error_message))
            logger.info(f"[RequestManager] Rejected request: {request_id}, error: {error_message}")
            return True
        else:
            logger.warning(f"[RequestManager] Request {request_id} already done")
            return False

    def get_pending_count(self) -> int:
        """获取待处理请求数量"""
        return len(self._pending_requests)

    def clear_all(self):
        """清理所有待处理请求（通常在服务关闭时调用）"""
        count = len(self._pending_requests)
        if count > 0:
            logger.warning(f"[RequestManager] Clearing {count} pending requests")
            for request_id, future in self._pending_requests.items():
                if not future.done():
                    future.set_exception(Exception("Service shutdown"))
            self._pending_requests.clear()


# 全局单例实例
request_manager = RequestManager()
