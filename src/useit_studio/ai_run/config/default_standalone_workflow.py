"""独立模式下默认的最小工作流：start → agent → end。"""

from __future__ import annotations

from typing import Any, Dict


def get_default_minimal_workflow() -> Dict[str, Any]:
    """
    与前端 React Flow 兼容的精简图结构。
    节点逻辑类型放在 ``data.type``（与 GraphManager / FlowProcessor 一致）。
    """
    return {
        "nodes": [
            {
                "id": "standalone_start",
                "type": "start",
                "data": {
                    "type": "start",
                    "title": "Start",
                    "name": "Start",
                },
            },
            {
                "id": "standalone_agent",
                "type": "agentNode",
                "data": {
                    "type": "agent",
                    "title": "Agent",
                    "name": "Agent",
                },
            },
            {
                "id": "standalone_end",
                "type": "end",
                "data": {
                    "type": "end",
                    "title": "End",
                    "name": "End",
                },
            },
        ],
        "edges": [
            {"source": "standalone_start", "target": "standalone_agent"},
            {"source": "standalone_agent", "target": "standalone_end"},
        ],
    }
