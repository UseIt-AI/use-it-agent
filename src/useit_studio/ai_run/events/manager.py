"""
事件流管理器

负责管理事件流的生命周期，包括：
- 生成全局trace_id
- 转换事件格式
- 事件统计和监控
- 可选的消息落盘功能
"""

from typing import AsyncGenerator, Dict, Any, Optional, TYPE_CHECKING
import uuid
import logging
import time

from .schemas import StandardEvent, BaseStreamEvent
from .adapter import EventAdapter

if TYPE_CHECKING:
    from useit_studio.ai_run.utils.run_logger import StreamMessagePersister

logger = logging.getLogger(__name__)


class StreamEventManager:
    """
    事件流管理器

    使用示例:
        manager = StreamEventManager()
        raw_stream = useit_loop_async_langchain(...)
        standard_stream = manager.stream_events(raw_stream)

        async for event in standard_stream:
            yield event.dict()
    
    带落盘功能:
        from useit_studio.ai_run.utils.run_logger import RunLogger, StreamMessagePersister
        
        run_logger = RunLogger(task_id, workflow_id, run_log_dir)
        persister = StreamMessagePersister(run_logger)
        manager = StreamEventManager(trace_id=task_id, persister=persister)
        
        async for event in manager.stream_events(raw_stream):
            yield event.dict()  # 事件已自动落盘
    """

    def __init__(
        self,
        trace_id: Optional[str] = None,
        persister: Optional["StreamMessagePersister"] = None,
    ):
        """
        初始化事件流管理器

        Args:
            trace_id: 追踪ID，如果不提供则自动生成
            persister: 可选的流式消息落盘器，如果提供则自动落盘所有事件
        """
        self.trace_id = trace_id or f"trace_{uuid.uuid4().hex[:16]}"
        self.event_count = 0
        self.start_time = time.time()
        self.event_stats: Dict[str, int] = {}
        self._persister = persister

        logger.info(f"StreamEventManager initialized with trace_id: {self.trace_id}, persister={'enabled' if persister else 'disabled'}")

    async def stream_events(
        self,
        raw_event_stream: AsyncGenerator[Dict[str, Any], None],
        persist_level: str = "all",
    ) -> AsyncGenerator[StandardEvent, None]:
        """
        将原始事件流转换为标准事件流

        Args:
            raw_event_stream: 原始事件流（来自业务逻辑层）
            persist_level: 落盘层级 (all/workflow/node/step)，仅当 persister 存在时有效

        Yields:
            标准格式的事件
        """
        try:
            async for raw_event in raw_event_stream:
                # 转换为标准格式
                standard_event = EventAdapter.convert(raw_event, self.trace_id)

                if standard_event:
                    # 统计
                    self._update_stats(standard_event)
                    
                    # 落盘（如果启用）
                    if self._persister:
                        try:
                            self._persister.persist(standard_event.dict(), level=persist_level)
                        except Exception as persist_error:
                            logger.warning(f"Failed to persist event: {persist_error}")

                    # yield标准事件
                    yield standard_event
                else:
                    # 无法转换的事件，记录警告
                    logger.warning(f"Failed to convert event: {raw_event}")

        except Exception as e:
            logger.error(f"Error in stream_events: {e}", exc_info=True)
            # 发送错误事件
            from .schemas import ErrorEvent
            error_event = ErrorEvent(
                content=f"Stream error: {str(e)}",
                error_code="STREAM_ERROR",
                trace_id=self.trace_id
            )
            yield error_event

        finally:
            # 记录统计信息
            self._log_stats()

    def _update_stats(self, event: BaseStreamEvent) -> None:
        """更新事件统计"""
        self.event_count += 1
        event_type = event.type
        self.event_stats[event_type] = self.event_stats.get(event_type, 0) + 1

    def _log_stats(self) -> None:
        """记录统计信息"""
        elapsed_time = time.time() - self.start_time
        logger.info(
            f"Stream completed - trace_id: {self.trace_id}, "
            f"total_events: {self.event_count}, "
            f"elapsed_time: {elapsed_time:.2f}s"
        )
        logger.info(f"Event type distribution: {self.event_stats}")

    def get_stats(self) -> Dict[str, Any]:
        """
        获取当前统计信息

        Returns:
            统计信息字典
        """
        return {
            "trace_id": self.trace_id,
            "total_events": self.event_count,
            "elapsed_time": time.time() - self.start_time,
            "event_type_stats": self.event_stats.copy()
        }
