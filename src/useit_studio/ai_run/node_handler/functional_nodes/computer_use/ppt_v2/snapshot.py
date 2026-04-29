"""
PowerPoint Agent - 幻灯片快照

SlideSnapshot 是对 local engine 返回的原始 snapshot JSON 的薄包装。
不做字段映射/重命名，直接把原始数据传给 AI，避免字段名不匹配问题。

满足 BaseSnapshot Protocol:
  - .screenshot -> base64 截图
  - .has_data   -> 是否有有效数据
  - .to_context_format() -> 给 LLM 的文本
"""

import copy
import json
from typing import Optional, Dict, Any, List

# toon_format: token-efficient encoding for LLM prompts
# fallback 到紧凑 JSON（去掉缩进和多余空格）
def _json_encode(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':'))

try:
    from toon_format import encode as _toon_encode
    _toon_encode({"test": 1})
    toon_encode = _toon_encode
except (ImportError, NotImplementedError):
    toon_encode = _json_encode


class SlideSnapshot:
    """
    PowerPoint 快照 — 薄包装原始 dict。

    不解析成固定 dataclass，直接保留 local engine 返回的原始结构，
    这样无论 API 字段怎么变，都不会出现解析遗漏。
    """

    def __init__(self, raw: Dict[str, Any]):
        self._raw = raw

    # ─── Protocol properties ───────────────────────────────────

    @property
    def screenshot(self) -> Optional[str]:
        """base64 截图（可能在 snapshot 顶层或 content 层）"""
        s = self._raw.get("screenshot")
        if isinstance(s, str) and not s.startswith("[TRUNCATED"):
            return s
        return None

    @property
    def has_data(self) -> bool:
        return bool(self._raw.get("presentation_info") or self._raw.get("content"))

    @property
    def file_path(self) -> Optional[str]:
        pinfo = self._raw.get("presentation_info", {})
        return pinfo.get("path") or pinfo.get("name")

    # ─── Convenience accessors ─────────────────────────────────

    @property
    def raw(self) -> Dict[str, Any]:
        return self._raw

    @property
    def presentation_info(self) -> Dict[str, Any]:
        return self._raw.get("presentation_info", {})

    @property
    def current_slide(self) -> Optional[Dict[str, Any]]:
        content = self._raw.get("content", {})
        return content.get("current_slide") or self._raw.get("current_slide")

    @property
    def slide_width(self) -> Optional[float]:
        """Slide width in points (from presentation_info or current_slide)."""
        pinfo = self._raw.get("presentation_info", {})
        w = pinfo.get("slide_width")
        if w is not None and w > 0:
            return float(w)
        cs = (self._raw.get("content", {}).get("current_slide") or
              self._raw.get("current_slide") or {})
        w = cs.get("width")
        return float(w) if w is not None and w > 0 else None

    @property
    def slide_height(self) -> Optional[float]:
        """Slide height in points (from presentation_info or current_slide)."""
        pinfo = self._raw.get("presentation_info", {})
        h = pinfo.get("slide_height")
        if h is not None and h > 0:
            return float(h)
        cs = (self._raw.get("content", {}).get("current_slide") or
              self._raw.get("current_slide") or {})
        h = cs.get("height")
        return float(h) if h is not None and h > 0 else None

    @property
    def project_files(self) -> Optional[str]:
        return self._raw.get("project_files")

    # ─── Serialization ─────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        return self._raw

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SlideSnapshot":
        """
        从字典创建 SlideSnapshot。
        处理可能的外层包装（{success, data} 或 {data: {snapshot}}）。
        """
        if "success" in data and "data" in data:
            inner = data["data"]
            if isinstance(inner, dict) and "snapshot" in inner:
                data = inner["snapshot"]
            else:
                data = inner
        return cls(raw=data)

    @classmethod
    def empty(cls) -> "SlideSnapshot":
        return cls(raw={})

    # ─── LLM context ──────────────────────────────────────────

    def to_context_format(self, max_text_length: int = 300) -> str:
        """
        直接将原始 snapshot JSON 清理后给 LLM，不做字段重命名。
        1. 删除 screenshot (base64 太大)
        2. 分离 project_files (通过 prompt 的 Project Context 部分单独展示)
        3. 截断过长的 text 字段
        4. 去掉 null 值节省 token
        """
        if not self.has_data:
            return "No PowerPoint data available. The application may not be open."

        cleaned = copy.deepcopy(self._raw)

        cleaned.pop("screenshot", None)
        cleaned.pop("_screenshot_info", None)
        cleaned.pop("project_files", None)

        _truncate_long_strings(cleaned, max_text_length)
        _strip_null_values(cleaned)

        return toon_encode(cleaned)


# ─── 辅助 ─────────────────────────────────────────────────────

def _truncate_long_strings(obj: Any, max_len: int) -> None:
    """递归截断 dict/list 中过长的字符串值"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and len(v) > max_len:
                obj[k] = v[:max_len] + "..."
            else:
                _truncate_long_strings(v, max_len)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            if isinstance(item, str) and len(item) > max_len:
                obj[i] = item[:max_len] + "..."
            else:
                _truncate_long_strings(item, max_len)


def _strip_null_values(obj: Any) -> Any:
    """递归删除 dict 中值为 None 的键，减少无用 token"""
    if isinstance(obj, dict):
        keys_to_del = [k for k, v in obj.items() if v is None]
        for k in keys_to_del:
            del obj[k]
        for v in obj.values():
            _strip_null_values(v)
    elif isinstance(obj, list):
        for item in obj:
            _strip_null_values(item)


def slide_snapshot_from_dict(data: Dict[str, Any]) -> SlideSnapshot:
    """将字典转换为 SlideSnapshot（兼容入口）"""
    return SlideSnapshot.from_dict(data)


# ─── 向后兼容的名字 ───────────────────────────────────────────
# 旧代码可能 import 这些名字，给空实现避免 ImportError

class ShapeInfo:
    """Deprecated — SlideSnapshot 不再解析单个 shape"""
    pass

class SlideInfo:
    """Deprecated — SlideSnapshot 不再解析单个 slide"""
    pass

class PresentationInfo:
    """Deprecated — SlideSnapshot 不再解析 presentation_info"""
    pass
