"""
ToolFilter —— 运行时解算启用的 tool 子集。

算法（干净版，无 LLM 预分类）
----------------------------
对每个 AgentTool：
1. **权限门**：
   - 若 tool 属于某 Pack：Pack 的 `required_api_keys / required_env_keys`
     必须齐全。
   - Tool 自己的 `is_enabled(ctx)` 必须返回 True（独立 inline tool 用这个
     门控自己的 API key）。
2. **白名单 / 自动加载**（仅对有 pack 的 tool 生效；独立 inline tool 默认全量）：
   - 若 node.data.capabilities / groups 指定了白名单：tool.group 必须在里面。
   - 若未指定白名单：tool.group 必须满足 `Pack.detect_from_snapshot(ctx)`
     返回 True，**或** 白名单完全为空（视作"全部可用"）。

显式白名单（node.data.groups）与 snapshot 自动加载为"或"关系：
显式点亮的组永远可用；snapshot 检测到额外组时也自动纳入。

为何不做 LLM 预路由
-------------------
Planner 本身就会从 action table 里只挑自己要的；`router_hint` 一行 ≈ 一句，
40 个 tool ≈ 2k token，完全可接受。省下的那次 LLM round-trip 远比几百 token
宝贵；而且 LLM 预路由选错了没法补救。
"""

from __future__ import annotations

import os
from typing import List, Optional, Set, TYPE_CHECKING, Type

from useit_studio.ai_run.utils.logger_utils import LoggerUtils

from .tools import ALL_TOOLS, PACK_BY_NAME, TOOL_TO_PACK
from .tools.protocol import AgentTool, ToolPack

if TYPE_CHECKING:
    from useit_studio.ai_run.node_handler.base_v2 import NodeContext

logger = LoggerUtils(component_name="ToolFilter")


class ToolFilter:
    """根据 NodeContext 求解启用的 AgentTool 子集。"""

    def __init__(self, ctx: "NodeContext"):
        self.ctx = ctx

    def resolve(self) -> List[AgentTool]:
        whitelist_groups = self._whitelist_groups()
        has_explicit_whitelist = bool(whitelist_groups)

        enabled: List[AgentTool] = []
        detected_cache: dict = {}

        for tool in ALL_TOOLS:
            pack_cls: Optional[Type[ToolPack]] = TOOL_TO_PACK.get(tool.name)

            if pack_cls is not None and not self._pack_permitted(pack_cls):
                continue

            if not tool.is_enabled(self.ctx):
                continue

            if pack_cls is not None:
                group = pack_cls.name
                if has_explicit_whitelist:
                    if group not in whitelist_groups:
                        if group not in detected_cache:
                            detected_cache[group] = self._safe_detect(pack_cls)
                        if not detected_cache[group]:
                            continue
                else:
                    pass

            enabled.append(tool)

        logger.logger.info(
            f"[ToolFilter] whitelist_groups={sorted(whitelist_groups)} "
            f"enabled_tools={[t.name for t in enabled]}"
        )
        return enabled

    def _whitelist_groups(self) -> Set[str]:
        data = (self.ctx.node_dict or {}).get("data", {}) or {}
        raw = (
            data.get("groups")
            or data.get("capabilities")
            or data.get("allowed_capabilities")
        )
        if not raw:
            return set()
        if isinstance(raw, str):
            raw = [raw]
        requested = {str(x).lower() for x in raw}
        known = set(PACK_BY_NAME.keys())
        return requested & known

    def _pack_permitted(self, pack_cls: Type[ToolPack]) -> bool:
        api_keys = self.ctx.planner_api_keys or {}
        missing_api = [k for k in pack_cls.required_api_keys if not api_keys.get(k)]
        missing_env = [k for k in pack_cls.required_env_keys if not os.getenv(k)]
        if missing_api or missing_env:
            logger.logger.debug(
                f"[ToolFilter] pack '{pack_cls.name}' missing "
                f"api={missing_api} env={missing_env}"
            )
            return False
        return True

    def _safe_detect(self, pack_cls: Type[ToolPack]) -> bool:
        try:
            return pack_cls.detect_from_snapshot(self.ctx)
        except Exception as e:  # noqa: BLE001
            logger.logger.warning(
                f"[ToolFilter] detect_from_snapshot '{pack_cls.name}' failed: {e}"
            )
            return False
