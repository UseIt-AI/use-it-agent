"""
tools/__init__.py —— 自动发现所有 tool 与 ToolPack。

发现规则
--------
1. **子包**（含 `__init__.py` 的子目录，例如 `tools/ppt/`）视为一个 ToolPack：
   - `_pack.py` 必须定义一个 `ToolPack` 子类；
   - `tools.py` 必须导出 `TOOLS: List[AgentTool]`（或兼容形状）。
2. **单文件模块**（例如 `tools/web_search.py`）视为一个独立 inline tool：
   - 必须导出 `TOOL: AgentTool`。
3. `protocol.py` / `helpers.py` 自动被跳过（有前缀 `_` 的文件亦然）。

新增工具的步骤
--------------
- 新增一个软件能力：在 `tools/` 下建子包，照 `ppt/` 的模板填。
- 新增一个独立 inline 工具：在 `tools/` 下建一个 `<name>.py`，导出 `TOOL`。
- 不需要改本文件。
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Any, Callable, Dict, List, Tuple, Type

from useit_studio.ai_run.utils.logger_utils import LoggerUtils

from .protocol import AgentTool, ToolPack

logger = LoggerUtils(component_name="AgentNode.tools")

ALL_PACKS: List[Type[ToolPack]] = []
"""按发现顺序排列的全部 ToolPack 类。"""

PACK_BY_NAME: Dict[str, Type[ToolPack]] = {}
"""pack.name → ToolPack 类。"""

ALL_TOOLS: List[AgentTool] = []
"""按发现顺序排列的全部 AgentTool 实例（子包 tool + 独立 tool）。"""

TOOL_BY_NAME: Dict[str, AgentTool] = {}
"""tool.name → AgentTool 实例。"""

TOOL_TO_PACK: Dict[str, Type[ToolPack]] = {}
"""tool.name → 所属 ToolPack（独立 tool 不在此表）。"""


_SKIP_MODULES = frozenset({"protocol", "helpers", "image_gen"})


# ---------------------------------------------------------------------------
# Legacy tool-name aliases
# ---------------------------------------------------------------------------
# When we collapse multiple single-action tools into a single
# action-discriminated tool (e.g. ``ppt_add_slide`` → ``ppt_slide`` with
# ``action="add"``), stored conversation history and occasional hallucinations
# from the router LLM can still produce the old names.  This map rewrites
# those into their canonical new form before the handler dispatches.
#
# Value is ``(new_tool_name, transform)`` where ``transform(old_params)``
# returns the params dict to use with the new tool.
LegacyAliasFn = Callable[[Dict[str, Any]], Dict[str, Any]]
LEGACY_TOOL_ALIASES: Dict[str, Tuple[str, LegacyAliasFn]] = {
    # --- ppt_slide (add / delete / duplicate / move / goto) --------------
    "ppt_add_slide":       ("ppt_slide",       lambda p: {"action": "add",       **p}),
    "ppt_delete_slide":    ("ppt_slide",       lambda p: {"action": "delete",    **p}),
    "ppt_duplicate_slide": ("ppt_slide",       lambda p: {"action": "duplicate", **p}),
    "ppt_move_slide":      ("ppt_slide",       lambda p: {"action": "move",      **p}),
    "ppt_goto_slide":      ("ppt_slide",       lambda p: {"action": "goto",      **p}),
    # --- ppt_arrange_elements (align / reorder / group / ungroup) --------
    "ppt_align_elements":   ("ppt_arrange_elements", lambda p: {"action": "align",   **p}),
    "ppt_reorder_elements": ("ppt_arrange_elements", lambda p: {"action": "reorder", **p}),
    "ppt_group_elements":   ("ppt_arrange_elements", lambda p: {"action": "group",   **p}),
    "ppt_ungroup_elements": ("ppt_arrange_elements", lambda p: {"action": "ungroup", **p}),
    # --- ppt_insert (media / table) --------------------------------------
    "ppt_insert_media":        ("ppt_insert", lambda p: {"action": "media", **p}),
    "ppt_insert_native_table": ("ppt_insert", lambda p: {"action": "table", **p}),
    # --- ppt_animation (add / clear) -------------------------------------
    "ppt_add_shape_animation":   ("ppt_animation", lambda p: {"action": "add",   **p}),
    "ppt_clear_slide_animations": ("ppt_animation", lambda p: {"action": "clear", **p}),
    # --- ppt_document (open / close)  legacy direct names ----------------
    "ppt_open":  ("ppt_document", lambda p: {"action": "open",  **p}),
    "ppt_close": ("ppt_document", lambda p: {"action": "close", **p}),
    # --- autocad ---------------------------------------------------------
    # Old single autocad_execute_code (which also wrapped payload in /step)
    # has been replaced by autocad_execute_python_com (flat protocol).
    "autocad_execute_code":  ("autocad_execute_python_com", lambda p: dict(p)),
    # Legacy direct action names (when stored history skipped the autocad_ prefix
    # because the old engine tool went through /step's `actions[0].action`).
    "autocad_open":     ("autocad_document",      lambda p: {"action": "open",     **p}),
    "autocad_close":    ("autocad_document",      lambda p: {"action": "close",    **p}),
    "autocad_new":      ("autocad_document",      lambda p: {"action": "new",      **p}),
    "autocad_activate": ("autocad_document",      lambda p: {"action": "activate", **p}),
    "autocad_list_standard_parts":      ("autocad_standard_part", lambda p: {"action": "list",    **p}),
    "autocad_get_standard_part_presets": ("autocad_standard_part", lambda p: {"action": "presets", **p}),
    "autocad_draw_standard_part":       ("autocad_standard_part", lambda p: {"action": "draw",    **p}),
}


def rewrite_legacy_tool_call(
    tool_name: str,
    tool_params: Dict[str, Any] | None,
) -> Tuple[str, Dict[str, Any]]:
    """Rewrite a legacy ``tool_name`` (+ params) to its current canonical form.

    If ``tool_name`` is not a legacy alias, returns the inputs unchanged
    (params defensively copied).  Logs a warning when a rewrite happens so
    we can track LLMs drifting back to old names.
    """
    params = dict(tool_params or {})
    mapping = LEGACY_TOOL_ALIASES.get(tool_name)
    if mapping is None:
        return tool_name, params
    new_name, transform = mapping
    new_params = transform(params)
    logger.logger.warning(
        f"[tools] legacy alias rewrite: {tool_name} → {new_name} "
        f"(action={new_params.get('action')!r})"
    )
    return new_name, new_params


def _discover_pack_from_module(pack_mod) -> Type[ToolPack]:
    """从一个 `_pack.py` 模块里找唯一的 ToolPack 子类。"""
    candidates: List[Type[ToolPack]] = []
    for v in vars(pack_mod).values():
        if (
            isinstance(v, type)
            and issubclass(v, ToolPack)
            and v is not ToolPack
            and v.__module__ == pack_mod.__name__
        ):
            candidates.append(v)
    if not candidates:
        raise RuntimeError(
            f"No ToolPack subclass found in {pack_mod.__name__}; define one in _pack.py"
        )
    if len(candidates) > 1:
        raise RuntimeError(
            f"Multiple ToolPack subclasses in {pack_mod.__name__}: "
            f"{[c.__name__ for c in candidates]}"
        )
    return candidates[0]


def _register_pack_tools(pkg_mod) -> None:
    """处理一个 tool 子包（例如 `tools.ppt`）。"""
    pack_mod_name = pkg_mod.__name__ + "._pack"
    tools_mod_name = pkg_mod.__name__ + ".tools"
    try:
        pack_mod = importlib.import_module(pack_mod_name)
    except ImportError as e:
        logger.logger.warning(f"[tools] skip pack '{pkg_mod.__name__}': {e}")
        return
    try:
        tools_mod = importlib.import_module(tools_mod_name)
    except ImportError as e:
        logger.logger.warning(f"[tools] skip pack '{pkg_mod.__name__}': {e}")
        return

    pack_cls = _discover_pack_from_module(pack_mod)
    if not pack_cls.name:
        raise RuntimeError(f"ToolPack {pack_cls.__name__} has empty `name`")
    if pack_cls.name in PACK_BY_NAME:
        raise RuntimeError(
            f"Duplicate ToolPack name '{pack_cls.name}' "
            f"({PACK_BY_NAME[pack_cls.name].__name__} vs {pack_cls.__name__})"
        )
    ALL_PACKS.append(pack_cls)
    PACK_BY_NAME[pack_cls.name] = pack_cls

    raw = getattr(tools_mod, "TOOLS", None)
    if raw is None:
        logger.logger.warning(
            f"[tools] pack '{pack_cls.name}' has no TOOLS list in {tools_mod_name}"
        )
        return
    for tool in raw:
        _register_tool(tool, pack_cls=pack_cls)


def _register_standalone(mod) -> None:
    """处理一个独立 tool 模块（例如 `tools.web_search`）。"""
    tool = getattr(mod, "TOOL", None)
    if tool is None:
        logger.logger.warning(f"[tools] module '{mod.__name__}' has no TOOL constant; skipping")
        return
    _register_tool(tool, pack_cls=None)


def _register_tool(tool: AgentTool, pack_cls) -> None:
    if not getattr(tool, "name", ""):
        raise RuntimeError(f"Tool {type(tool).__name__} has empty name")
    if tool.name in TOOL_BY_NAME:
        raise RuntimeError(f"Duplicate tool name '{tool.name}'")
    ALL_TOOLS.append(tool)
    TOOL_BY_NAME[tool.name] = tool
    if pack_cls is not None:
        TOOL_TO_PACK[tool.name] = pack_cls
        if tool.group and tool.group != pack_cls.name:
            logger.logger.warning(
                f"[tools] tool '{tool.name}' group='{tool.group}' "
                f"!= pack.name='{pack_cls.name}'"
            )


def _discover() -> None:
    """扫描本包的所有直接子模块 / 子包。"""
    import useit_studio.ai_run.node_handler.agent_node.tools as _self

    for info in pkgutil.iter_modules(_self.__path__, prefix=_self.__name__ + "."):
        short = info.name.rsplit(".", 1)[-1]
        if short.startswith("_") or short in _SKIP_MODULES:
            continue
        try:
            mod = importlib.import_module(info.name)
        except ImportError as e:
            logger.logger.warning(f"[tools] import failed for {info.name}: {e}")
            continue
        if info.ispkg:
            _register_pack_tools(mod)
        else:
            _register_standalone(mod)


_discover()

logger.logger.info(
    f"[tools] discovered {len(ALL_TOOLS)} tool(s) across "
    f"{len(ALL_PACKS)} pack(s): "
    f"tools={[t.name for t in ALL_TOOLS]}"
)

__all__ = [
    "ALL_PACKS",
    "PACK_BY_NAME",
    "ALL_TOOLS",
    "TOOL_BY_NAME",
    "TOOL_TO_PACK",
    "LEGACY_TOOL_ALIASES",
    "rewrite_legacy_tool_call",
]
