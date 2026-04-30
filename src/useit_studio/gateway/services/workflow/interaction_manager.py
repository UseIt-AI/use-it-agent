import asyncio
import time
import datetime
from typing import Dict, Any, Optional

# 早到结果的最大保留时间（秒），防止内存泄漏
_EARLY_RESULT_TTL = 300.0


class WorkflowInteractionManager:
    """
    工作流交互管理器
    
    用于处理服务端工作流与客户端的异步交互（如请求客户端截图、执行动作等）
    
    设计要点 —— 早到结果缓冲:
        tool_call 事件通过 SSE yield 给前端后，executor 仍在消费 AI Run 的
        后续 SSE 事件（如 S3 上传导致的 file_transfer），尚未调用 wait_for_result()。
        若前端在此期间已执行完动作并回调 submit_result()，原实现会因找不到 Future
        而返回 False（404），导致回调丢失、流程卡住直到超时。
        
        修复方案：submit_result() 发现无 Future 时，将结果暂存到 _early_results；
        wait_for_result() 开始等待前先查缓冲，命中则立即返回。
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(WorkflowInteractionManager, cls).__new__(cls)
            cls._instance._pending_requests = {}
            cls._instance._early_results = {}
        return cls._instance

    def __init__(self):
        # request_id -> Future
        if not hasattr(self, "_pending_requests"):
            self._pending_requests: Dict[str, asyncio.Future] = {}
        # request_id -> (result, timestamp)  —— 早到结果缓冲区
        if not hasattr(self, "_early_results"):
            self._early_results: Dict[str, tuple] = {}

    async def wait_for_result(self, request_id: str, timeout: float = 60.0) -> Any:
        """等待客户端返回结果"""
        perf_wait_start = time.time()
        perf_wait_time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        print(f"[PERF_MANAGER] 🕐 开始等待结果 [时间: {perf_wait_time_str}] request_id={request_id[:8]}...")
        
        # ===== 检查早到结果缓冲区 =====
        if request_id in self._early_results:
            result, buffered_at = self._early_results.pop(request_id)
            early_wait = time.time() - buffered_at
            print(
                f"[PERF_MANAGER] ⚡ 命中早到结果缓冲 [时间: {perf_wait_time_str}] "
                f"request_id={request_id[:8]}... [缓冲等待: {early_wait:.3f}s]"
            )
            return result
        
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._pending_requests[request_id] = future
        
        try:
            result = await asyncio.wait_for(future, timeout)
            perf_wait_end = time.time()
            perf_wait_duration = perf_wait_end - perf_wait_start
            perf_wait_end_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            print(f"[PERF_MANAGER] ✅ 等待完成 [时间: {perf_wait_end_str}] [耗时: {perf_wait_duration:.3f}s] request_id={request_id[:8]}...")
            return result
        finally:
            self._pending_requests.pop(request_id, None)

    def submit_result(self, request_id: str, result: Any) -> bool:
        """提交客户端返回的结果"""
        perf_submit_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        if request_id in self._pending_requests:
            future = self._pending_requests[request_id]
            if not future.done():
                future.set_result(result)
                print(f"[PERF_MANAGER] ✅ Future.set_result 完成 [时间: {perf_submit_time}] request_id={request_id[:8]}...")
            return True
        
        # ===== 早到结果：Future 尚未创建，先缓冲 =====
        # 这种情况发生在 executor 还在消费 AI Run SSE 事件（如 S3 上传），
        # 尚未调用 wait_for_result()，但前端已经执行完动作并回调。
        self._early_results[request_id] = (result, time.time())
        self._cleanup_stale_early_results()
        print(
            f"[PERF_MANAGER] 📦 早到结果已缓冲 [时间: {perf_submit_time}] "
            f"request_id={request_id[:8]}... [缓冲区大小: {len(self._early_results)}]"
        )
        return True

    def _cleanup_stale_early_results(self) -> None:
        """清理过期的早到结果，防止内存泄漏"""
        now = time.time()
        stale_keys = [
            k for k, (_, ts) in self._early_results.items()
            if now - ts > _EARLY_RESULT_TTL
        ]
        for k in stale_keys:
            del self._early_results[k]
            print(f"[PERF_MANAGER] 🗑️ 清理过期早到结果: request_id={k[:8]}...")

