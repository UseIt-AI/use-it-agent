"""
Skill File Reader - 文件按需读取器（有状态，跨 handler 调用持久化）

职责：
1. 路径解析（从 SkillContent 中查找）
2. 文件读取（带大小限制和截断）
3. 去重（已读文件不重复读取）
4. 默认参考文档加载
5. 状态序列化 / 反序列化（跨 handler 调用持久化）
6. 格式化内容（直接可注入 prompt）

不负责：
- 事件 emit（cua_start/end、NodeCompleteEvent 由各 handler 处理）
- Prompt 组装（由 AgentContext + Planner 处理）

用法（在各 handler 中）：
    from useit_studio.ai_run.skills import SkillFileReader

    # 1. 从 node_state 恢复（鲁棒：兼容多种存储位置）
    reader = SkillFileReader.from_state(ctx.node_state, ctx.skill_contents)

    # 2. 读取文件
    result = reader.read_file("scripts/chart_examples.py")
    if not result.success: handle_error(result.error)

    # 3. 注入 prompt
    attached_files_content += reader.accumulated_content

    # 4. 持久化（每次 NodeCompleteEvent 必带）
    handler_result = {..., **reader.get_state()}
"""

import os
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, List, Optional

from .skill_loader import SkillContent

logger = logging.getLogger(__name__)


@dataclass
class ReadResult:
    """
    文件读取结果

    Attributes:
        success: 是否成功
        content: 格式化后的内容块（直接可注入 prompt）
        is_cached: True = 已读过，本次跳过（不消耗 IO）
        error: 失败原因
    """
    success: bool
    content: str = ""
    is_cached: bool = False
    error: str = ""


class SkillFileReader:
    """
    Skill 文件按需读取器（有状态）

    核心设计：
    - 每个 handler 调用链维护一个 reader 实例
    - 通过 get_state() / from_state() 跨调用持久化
    - accumulated_content 直接追加到 attached_files_content 即可
    """

    MAX_FILE_SIZE = 50_000  # 50K chars

    def __init__(self, skill_contents: Optional[Dict[str, SkillContent]] = None):
        self._skill_contents: Dict[str, SkillContent] = skill_contents or {}
        self._read_keys: List[str] = []  # 去重标识（文件路径 or 特殊 key）
        self._accumulated: str = ""       # 累积的格式化内容

    # ========================================================================
    # 核心 API
    # ========================================================================

    def read_file(self, file_path: str, skill_name: Optional[str] = None) -> ReadResult:
        """
        读取 skill 文件

        自动处理：去重 → 路径解析 → 读取 → 截断 → 格式化 → 追加

        Args:
            file_path: 相对于 skill base_dir 的路径，如 "scripts/chart_examples.py"
            skill_name: 可选，指定从哪个 skill 读取

        Returns:
            ReadResult（success=True 时 content 为格式化后的内容块）
        """
        # 去重
        if file_path in self._read_keys:
            logger.debug(f"File already read (cached): {file_path}")
            return ReadResult(success=True, is_cached=True)

        # 路径解析
        full_path = self._resolve_path(file_path, skill_name)
        if not full_path:
            return ReadResult(
                success=False,
                error=f"File not found in any skill: {file_path}",
            )

        if not os.path.exists(full_path):
            return ReadResult(
                success=False,
                error=f"File not found at resolved path: {full_path}",
            )

        # 读取
        try:
            content = Path(full_path).read_text(encoding="utf-8")
        except Exception as e:
            return ReadResult(success=False, error=f"Failed to read {file_path}: {e}")

        # 截断
        if len(content) > self.MAX_FILE_SIZE:
            content = content[: self.MAX_FILE_SIZE] + "\n\n[... content truncated ...]"
            logger.warning(f"File {file_path} truncated to {self.MAX_FILE_SIZE} chars")

        # 格式化（增强版：带时间戳和清晰分隔）
        timestamp = self._get_timestamp()
        detected_skill = skill_name or self._detect_skill_name(file_path)
        block = f"""
---

### Skill File: {file_path}

**Source**: {detected_skill}
**Read at**: {timestamp}

```
{content}
```
"""

        # 记录
        self._read_keys.append(file_path)
        self._accumulated += block

        logger.info(f"Read skill file: {file_path} ({len(content)} chars)")
        return ReadResult(success=True, content=block)

    def read_default_reference(
        self, content: str, label: str = "Default Reference"
    ) -> ReadResult:
        """
        加载默认参考文档

        content 由各 app 的 prompts.py 提供（如 DEFALUT_SKILL_REFERENCE_PROMPT）。
        label 用于去重标识和显示标题。

        Args:
            content: 参考文档原始内容
            label: 标识名（如 "Excel COM API Reference"）

        Returns:
            ReadResult
        """
        key = f"__ref__{label}"
        if key in self._read_keys:
            logger.debug(f"Default reference already loaded (cached): {label}")
            return ReadResult(success=True, is_cached=True)

        # 格式化（增强版：带时间戳和类型标识）
        timestamp = self._get_timestamp()
        block = f"""
---

### {label}

**Type**: Default Reference (Lazy Loaded)
**Read at**: {timestamp}

{content}
"""

        self._read_keys.append(key)
        self._accumulated += block

        logger.info(f"Loaded default reference: {label} ({len(content)} chars)")
        return ReadResult(success=True, content=block)

    def find_skill_id(self, script_path: str) -> Optional[str]:
        """
        查找包含指定脚本的 skill ID

        用于 execute_script action，确定脚本属于哪个 skill。

        Args:
            script_path: 脚本相对路径

        Returns:
            skill ID（纯数字部分，如 "66666666"）或 None
        """
        for sid, skill in self._skill_contents.items():
            resource_path = skill.get_resource_path(script_path)
            if os.path.exists(resource_path):
                # skill_contents 的 key 是 skill name（如 "skill-66666666"）
                # controller 期望纯 ID（如 "66666666"），需要去除 "skill-" 前缀
                if sid.startswith("skill-"):
                    return sid[6:]
                return sid
        return None

    # ========================================================================
    # Prompt 注入
    # ========================================================================

    @property
    def accumulated_content(self) -> str:
        """
        所有已读取内容（格式化后）

        用法：skills_prompt += reader.accumulated_content_header + reader.accumulated_content
        """
        return self._accumulated

    @property
    def accumulated_content_header(self) -> str:
        """
        已读文件的标题头（用于追加到 skills_prompt）

        Returns:
            如果有已读文件，返回标题头；否则返回空字符串
        """
        if not self._accumulated:
            return ""

        count = len(self._read_keys)
        return f"\n\n## Previously Read Skill Resources ({count} items)\n"

    @property
    def read_files_list(self) -> List[str]:
        """已读文件/资源标识列表"""
        return list(self._read_keys)

    # ========================================================================
    # 状态持久化
    # ========================================================================

    def get_state(self) -> Dict[str, Any]:
        """
        序列化状态 → 存入 handler_result

        用法：
            yield NodeCompleteEvent(
                handler_result={..., **reader.get_state()},
            )

        Returns:
            包含 read_files_list 和 read_files_content 的字典
        """
        return {
            "read_files_list": list(self._read_keys),
            "read_files_content": self._accumulated,
        }

    @classmethod
    def from_state(
        cls,
        node_state: Dict[str, Any],
        skill_contents: Optional[Dict[str, SkillContent]] = None,
    ) -> "SkillFileReader":
        """
        从 node_state 恢复（鲁棒设计：兼容多种存储位置）

        查找优先级：
        1. node_state 顶层（某些框架直接合并 handler_result）
        2. node_state["handler_result"] 内（标准嵌套结构）

        Args:
            node_state: 节点状态字典
            skill_contents: SkillContent 字典（用于后续读取）

        Returns:
            恢复后的 SkillFileReader 实例
        """
        reader = cls(skill_contents)

        hr = node_state.get("handler_result", {})

        # read_files_list：优先顶层，fallback 到 handler_result
        reader._read_keys = (
            node_state.get("read_files_list")
            or hr.get("read_files_list")
            or []
        )
        # 确保是 list 的副本（避免意外修改）
        reader._read_keys = list(reader._read_keys)

        # read_files_content：优先顶层，fallback 到 handler_result
        reader._accumulated = (
            node_state.get("read_files_content")
            or hr.get("read_files_content")
            or ""
        )

        if reader._read_keys:
            logger.info(
                f"SkillFileReader restored: {len(reader._read_keys)} files, "
                f"{len(reader._accumulated)} chars accumulated"
            )

        return reader

    # ========================================================================
    # 内部方法
    # ========================================================================

    def _resolve_path(
        self, file_path: str, skill_name: Optional[str] = None
    ) -> Optional[str]:
        """
        从 skill_contents 中解析文件完整路径

        优先使用指定的 skill_name，否则遍历所有 skills 查找。
        """
        if not self._skill_contents:
            return None

        # 指定了 skill_name
        if skill_name and skill_name in self._skill_contents:
            return self._skill_contents[skill_name].get_resource_path(file_path)

        # 遍历所有 skills 查找存在的文件
        for skill in self._skill_contents.values():
            candidate = skill.get_resource_path(file_path)
            if os.path.exists(candidate):
                return candidate

        return None

    def _detect_skill_name(self, file_path: str) -> str:
        """
        自动检测文件属于哪个 skill

        Args:
            file_path: 文件相对路径

        Returns:
            skill 名称或 "Auto-detected"
        """
        if not self._skill_contents:
            return "Auto-detected"

        for skill_name, skill in self._skill_contents.items():
            candidate = skill.get_resource_path(file_path)
            if os.path.exists(candidate):
                return skill_name

        return "Auto-detected"

    def _get_timestamp(self) -> str:
        """
        获取当前时间戳

        Returns:
            格式化的时间戳字符串
        """
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
