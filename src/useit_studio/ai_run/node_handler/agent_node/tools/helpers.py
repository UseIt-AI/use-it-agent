"""
Agent Node 工具包公用 helper

- `has_any(d, keys)`       : 字典里是否有任一 key
- `extract_snapshot_dict(ctx)` : 从 NodeContext 多路径挖出 snapshot
- `flat_payload_from_step(...)` : 把 /step 风格的 actions[0] 拍扁成 {name, args}
"""

from __future__ import annotations

from typing import Any, Dict, List, TYPE_CHECKING, Tuple

if TYPE_CHECKING:
    from useit_studio.ai_run.node_handler.base_v2 import NodeContext


def has_any(d: Any, keys: List[str]) -> bool:
    """字典中存在任一 key；None / 非 dict 返回 False。"""
    return isinstance(d, dict) and any(k in d for k in keys)


def extract_snapshot_dict(ctx: "NodeContext") -> Dict[str, Any]:
    """从 ctx 尽力挖出 snapshot 字典，兼容多种嵌套格式。

    覆盖路径（后面的 key 不覆盖前面已有的）：
    - ctx.execution_result
    - ctx.execution_result["snapshot"]
    - ctx.execution_result["data"]
    - ctx.execution_result["data"]["snapshot"]
    - ctx.node_state["snapshot"]
    """
    candidates: List[Any] = []
    er = ctx.execution_result
    if isinstance(er, dict):
        candidates.append(er)
        if isinstance(er.get("snapshot"), dict):
            candidates.append(er["snapshot"])
        if isinstance(er.get("data"), dict):
            candidates.append(er["data"])
            if isinstance(er["data"].get("snapshot"), dict):
                candidates.append(er["data"]["snapshot"])
    ns = ctx.node_state or {}
    if isinstance(ns.get("snapshot"), dict):
        candidates.append(ns["snapshot"])

    merged: Dict[str, Any] = {}
    for c in candidates:
        if isinstance(c, dict):
            for k, v in c.items():
                if k not in merged:
                    merged[k] = v
    return merged


def flat_payload_from_params(
    action_name: str, params: Dict[str, Any]
) -> Tuple[str, Dict[str, Any]]:
    """把参数字典拍扁成 {type: action, ...params}（GUI / Browser 用）。

    返回 (name, args) 两元组，供 EngineTool.build_tool_call 使用。
    """
    return action_name, dict(params)
