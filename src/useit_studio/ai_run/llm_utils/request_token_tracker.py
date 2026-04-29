"""
请求级 Token 追踪器

按 task_id 跨 step 累计 token 使用量，通过 ContextVar 让 unified_client 无需改函数签名即可记录。
数据仅在 AI_Run <-> Backend 之间流转，不发送到前端。
"""

from contextvars import ContextVar
from typing import Dict, Set, Any, Optional

# 模块级存储：按 task_id 持久化 tracker，跨多个 step 累加
_trackers: Dict[str, "WorkflowTokenTracker"] = {}

# ContextVar：指向当前请求的 tracker（asyncio 并发安全）
_current_tracker: ContextVar[Optional["WorkflowTokenTracker"]] = ContextVar(
    "current_request_token_tracker", default=None
)

# provider -> 对应的 API key 环境变量名（用于判断 key_source）
PROVIDER_KEY_MAP = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GOOGLE_API_KEY",
}


class WorkflowTokenTracker:
    """单个 workflow（task_id）的 token 累计追踪器"""

    def __init__(self, task_id: str):
        self.task_id = task_id
        self._user_key_names: Set[str] = set()
        # key: (model, key_source)  value: {input_tokens, output_tokens, total_tokens, call_count}
        self._usage: Dict[tuple, dict] = {}
        self._step_count = 0
        self._total_call_count = 0
        # 当前 step 的增量用量（begin_step 时重置）
        self._step_usage: Dict[tuple, dict] = {}
        self._step_call_count = 0

    def begin_step(self, user_api_keys: Optional[Dict] = None):
        """每个 step 开始时调用，更新当前 step 的 user_key_names，重置 step 级计数器"""
        self._step_count += 1
        self._user_key_names = set(user_api_keys.keys()) if user_api_keys else set()
        # 重置当前 step 的增量桶
        self._step_usage = {}
        self._step_call_count = 0

    def record(self, input_tokens: int, output_tokens: int, total_tokens: int, model: str, provider: str):
        """记录一次 LLM 调用的 token 使用量（同时写入累计和当前 step）"""
        key_name = PROVIDER_KEY_MAP.get(provider)
        key_source = "user" if key_name and key_name in self._user_key_names else "official"

        composite_key = (model, key_source)

        # --- 累计 ---
        if composite_key not in self._usage:
            self._usage[composite_key] = {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "call_count": 0,
            }
        entry = self._usage[composite_key]
        entry["input_tokens"] += input_tokens
        entry["output_tokens"] += output_tokens
        entry["total_tokens"] += total_tokens
        entry["call_count"] += 1
        self._total_call_count += 1

        # --- 当前 step 增量 ---
        if composite_key not in self._step_usage:
            self._step_usage[composite_key] = {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "call_count": 0,
            }
        step_entry = self._step_usage[composite_key]
        step_entry["input_tokens"] += input_tokens
        step_entry["output_tokens"] += output_tokens
        step_entry["total_tokens"] += total_tokens
        step_entry["call_count"] += 1
        self._step_call_count += 1

    def get_summary(self) -> Dict[str, Any]:
        """返回累计数据 + 当前 step 的增量数据"""
        usage_by_model = [
            {"model": model, "key_source": ks, **counts}
            for (model, ks), counts in self._usage.items()
        ]
        step_usage_by_model = [
            {"model": model, "key_source": ks, **counts}
            for (model, ks), counts in self._step_usage.items()
        ]
        return {
            "task_id": self.task_id,
            "step_count": self._step_count,
            "total_call_count": self._total_call_count,
            "total_input_tokens": sum(e["input_tokens"] for e in self._usage.values()),
            "total_output_tokens": sum(e["output_tokens"] for e in self._usage.values()),
            "total_tokens": sum(e["total_tokens"] for e in self._usage.values()),
            "usage_by_model": usage_by_model,
            # 当前 step 的增量
            "current_step": {
                "step_number": self._step_count,
                "call_count": self._step_call_count,
                "input_tokens": sum(e["input_tokens"] for e in self._step_usage.values()),
                "output_tokens": sum(e["output_tokens"] for e in self._step_usage.values()),
                "total_tokens": sum(e["total_tokens"] for e in self._step_usage.values()),
                "usage_by_model": step_usage_by_model,
            },
        }


def get_or_create(task_id: str) -> WorkflowTokenTracker:
    """获取或创建指定 task_id 的 tracker"""
    if task_id not in _trackers:
        _trackers[task_id] = WorkflowTokenTracker(task_id)
    return _trackers[task_id]


def set_current(tracker: WorkflowTokenTracker):
    """设置当前请求的 tracker（返回 token 用于后续 reset）"""
    return _current_tracker.set(tracker)


def get_current() -> Optional[WorkflowTokenTracker]:
    """获取当前请求的 tracker"""
    return _current_tracker.get()


def reset_current(token):
    """重置 ContextVar（tracker 本身保留在 _trackers dict 中）"""
    _current_tracker.reset(token)


def remove(task_id: str):
    """清理指定 task_id 的 tracker"""
    _trackers.pop(task_id, None)
