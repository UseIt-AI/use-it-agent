"""
Browser Use - 元素过滤器（规则引擎版）

处理 Pipeline（按顺序执行）：
    Step 0: 噪音过滤 — 移除 1x1 跟踪像素、aria-hidden 隐藏元素
    Step 1: 重叠元素合并 — 位置重叠时保留上层元素（mask > cover）
    Step 2: 弹窗检测 — 标记弹窗/模态框内的元素
    Step 3: 去重 — 相同文本的元素只保留第一个
    Step 4: 智能截断 — 弹窗元素优先保留，超出 max_count 的部分丢弃
    Step 5: 恢复 DOM 顺序 — 按原始 index 排序输出

设计原则：
- 每一步是独立的确定性规则，不做模糊评分
- 完整保留 DOM 所有属性，不裁剪信息
- 规则可通过 FilterConfig 单独开关
"""

from typing import List, Dict, Set, Tuple, Any
from dataclasses import dataclass, field

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..models import DOMElement


# ==================== 关键词常量 ====================

# 上层元素的 class 关键词（遮罩、覆盖层）
OVERLAY_CLASS_KEYWORDS = frozenset({
    'mask', 'overlay', 'front', 'top', 'above',
})

# 底层元素的 class 关键词（背景、底图）
BACKGROUND_CLASS_KEYWORDS = frozenset({
    'cover', 'bg', 'background', 'backdrop', 'under', 'bottom', 'behind',
})

# 弹窗容器的 class 关键词
POPUP_CLASS_KEYWORDS = (
    'dialog', 'modal', 'popup', 'overlay', 'drawer',
    'layer', 'toast', 'dropdown', 'popover', 'sheet',
)

# 弹窗容器的 role 属性值
POPUP_ROLES = frozenset({'dialog', 'alertdialog'})


# ==================== 配置 ====================

@dataclass
class FilterConfig:
    """过滤器配置"""

    # 最大元素数量
    max_count: int = 100

    # Pipeline 开关
    filter_noise: bool = True           # Step 0
    resolve_overlaps: bool = True       # Step 1
    boost_popups: bool = True           # Step 2
    enable_deduplication: bool = True   # Step 3
    preserve_order: bool = True         # Step 5

    # Step 1 参数
    overlap_threshold: float = 0.75     # 重叠判定阈值（0-1，基于较小元素面积的重叠比例）
    overlap_size_ratio: float = 0.3     # 面积相似度下限（小面积/大面积 < 此值 → 视为包含关系，跳过）


# ==================== 过滤器主类 ====================

class ElementFilter:
    """
    元素过滤器（规则引擎版）

    每一步是一个独立的规则，按 Pipeline 顺序执行。
    规则只做"对/错"判断，不做模糊打分。
    """

    def __init__(self, config: FilterConfig = None):
        self.config = config or FilterConfig()

    def filter_elements(
        self,
        elements: List['DOMElement'],
        max_count: int = None,
        debug: bool = False
    ) -> Tuple[List['DOMElement'], Dict[str, Any]]:
        """
        主入口：按 Pipeline 过滤元素列表

        Args:
            elements: 原始元素列表
            max_count: 最大保留数量（覆盖 config.max_count）
            debug: 是否返回调试信息

        Returns:
            (过滤后的元素列表, 调试信息字典)
        """
        if not elements:
            return [], {}

        max_count = max_count or self.config.max_count

        debug_info: Dict[str, Any] = {
            'total_elements': len(elements),
            'filtered_out': [],
            'pipeline_stats': {},
        }

        result = list(elements)

        # ── Step 0: 噪音过滤 ──
        if self.config.filter_noise:
            result = self._step0_filter_noise(result, debug_info, debug)
        debug_info['pipeline_stats']['after_step0_noise'] = len(result)

        # ── Step 1: 重叠元素合并 ──
        if self.config.resolve_overlaps:
            result = self._step1_resolve_overlaps(result, debug_info, debug)
        debug_info['pipeline_stats']['after_step1_overlap'] = len(result)

        # ── Step 2: 弹窗检测（标记，不移除）──
        popup_indices: Set[int] = set()
        if self.config.boost_popups:
            popup_indices = self._step2_detect_popup_elements(result)
        debug_info['pipeline_stats']['popup_element_count'] = len(popup_indices)

        # ── Step 3: 去重 ──
        if self.config.enable_deduplication:
            result = self._step3_deduplicate(result, debug_info, debug)
        debug_info['pipeline_stats']['after_step3_dedup'] = len(result)

        # ── Step 4: 智能截断（弹窗元素优先保留）──
        if len(result) > max_count:
            result = self._step4_smart_truncate(
                result, max_count, popup_indices, debug_info, debug
            )
        debug_info['pipeline_stats']['after_step4_truncate'] = len(result)

        # ── Step 5: 恢复 DOM 顺序 ──
        if self.config.preserve_order:
            result.sort(key=lambda e: e.index)

        debug_info['filtered_count'] = len(result)
        debug_info['removed_count'] = len(elements) - len(result)

        return result, debug_info

    # ================================================================
    #  Step 0: 噪音过滤
    # ================================================================

    def _step0_filter_noise(
        self,
        elements: List['DOMElement'],
        debug_info: Dict[str, Any],
        debug: bool
    ) -> List['DOMElement']:
        """移除明显的噪音元素：1x1 跟踪像素、aria-hidden 隐藏元素"""
        valid = []
        for elem in elements:
            if self._is_noise(elem):
                if debug:
                    debug_info['filtered_out'].append({
                        'index': elem.index,
                        'step': 0,
                        'reason': 'Noise (tracking pixel or aria-hidden)',
                        'tag': elem.tag,
                    })
            else:
                valid.append(elem)
        return valid

    @staticmethod
    def _is_noise(elem: 'DOMElement') -> bool:
        pos = elem.position
        if pos:
            if pos.get('width', 0) <= 1 and pos.get('height', 0) <= 1:
                return True
        if elem.attributes.get('aria-hidden') == 'true':
            return True
        return False

    # ================================================================
    #  Step 1: 重叠元素合并（mask > cover）
    # ================================================================

    def _step1_resolve_overlaps(
        self,
        elements: List['DOMElement'],
        debug_info: Dict[str, Any],
        debug: bool
    ) -> List['DOMElement']:
        """
        检测位置重叠的元素对，保留上层元素。

        典型场景：
          cover(153) 底层图片 + mask(154) 可交互遮罩层
          → 两者 bbox 高度重叠 → 移除 cover，保留 mask

        判定规则：
          1. 两个元素的 bounding box 重叠率 ≥ 阈值
          2. 根据 class 关键词（overlay/mask > cover/background）判断上下层
          3. 兜底：DOM 顺序靠后的在上层（CSS 默认堆叠顺序）
        """
        if len(elements) < 2:
            return elements

        threshold = self.config.overlap_threshold
        to_remove: Set[int] = set()

        # 只对有 position 数据的元素做比较
        positioned = [(i, e) for i, e in enumerate(elements) if e.position]

        for i in range(len(positioned)):
            _, elem_a = positioned[i]
            if elem_a.index in to_remove:
                continue

            for j in range(i + 1, len(positioned)):
                _, elem_b = positioned[j]
                if elem_b.index in to_remove:
                    continue

                overlap = self._calc_overlap_ratio(elem_a, elem_b)
                if overlap >= threshold:
                    bottom = self._determine_bottom_element(elem_a, elem_b)
                    top = elem_b if bottom is elem_a else elem_a
                    to_remove.add(bottom.index)

                    if debug:
                        debug_info['filtered_out'].append({
                            'index': bottom.index,
                            'step': 1,
                            'reason': (
                                f'Overlapping with [{top.index}] '
                                f'(ratio={overlap:.0%}, '
                                f'kept={top.index} class="{top.attributes.get("class", "")}", '
                                f'removed={bottom.index} class="{bottom.attributes.get("class", "")}")'
                            ),
                            'tag': bottom.tag,
                        })

        return [e for e in elements if e.index not in to_remove]

    def _calc_overlap_ratio(self, a: 'DOMElement', b: 'DOMElement') -> float:
        """
        计算两个元素的重叠比例（基于较小元素的面积）。

        返回 0.0 ~ 1.0，1.0 表示较小元素完全被较大元素覆盖。

        额外检查：如果两个元素面积差距过大（小/大 < overlap_size_ratio），
        说明是包含关系（如按钮在容器内），而非 cover/mask 重叠，直接返回 0。
        """
        pa, pb = a.position, b.position
        if not pa or not pb:
            return 0.0

        area_a = pa.get('width', 0) * pa.get('height', 0)
        area_b = pb.get('width', 0) * pb.get('height', 0)

        larger_area = max(area_a, area_b)
        smaller_area = min(area_a, area_b)
        if larger_area <= 0 or smaller_area <= 0:
            return 0.0

        # ── 面积相似度检查 ──
        # 如果一个元素远大于另一个，这是"包含"关系（如按钮在弹窗容器内），
        # 不是 cover/mask 重叠，直接跳过
        size_ratio = smaller_area / larger_area
        if size_ratio < self.config.overlap_size_ratio:
            return 0.0

        # ── 计算交集矩形 ──
        x1 = max(pa.get('x', 0), pb.get('x', 0))
        y1 = max(pa.get('y', 0), pb.get('y', 0))
        x2 = min(pa.get('x', 0) + pa.get('width', 0),
                 pb.get('x', 0) + pb.get('width', 0))
        y2 = min(pa.get('y', 0) + pa.get('height', 0),
                 pb.get('y', 0) + pb.get('height', 0))

        if x1 >= x2 or y1 >= y2:
            return 0.0

        intersection = (x2 - x1) * (y2 - y1)
        return intersection / smaller_area

    @staticmethod
    def _determine_bottom_element(
        a: 'DOMElement', b: 'DOMElement'
    ) -> 'DOMElement':
        """
        判断哪个元素在底层（应被移除）。

        优先级：
          1. class 关键词明确判定（overlay/mask vs cover/background）
          2. 兜底：DOM index 小的在底层（CSS 默认堆叠：后渲染在上）
        """
        a_cls = a.attributes.get('class', '').lower()
        b_cls = b.attributes.get('class', '').lower()

        a_is_overlay = any(kw in a_cls for kw in OVERLAY_CLASS_KEYWORDS)
        b_is_overlay = any(kw in b_cls for kw in OVERLAY_CLASS_KEYWORDS)
        a_is_bg = any(kw in a_cls for kw in BACKGROUND_CLASS_KEYWORDS)
        b_is_bg = any(kw in b_cls for kw in BACKGROUND_CLASS_KEYWORDS)

        # 情况 1：一方明确是 overlay，另一方明确是 background
        if a_is_overlay and b_is_bg:
            return b
        if b_is_overlay and a_is_bg:
            return a

        # 情况 2：一方明确是 overlay
        if a_is_overlay and not b_is_overlay:
            return b
        if b_is_overlay and not a_is_overlay:
            return a

        # 情况 3：一方明确是 background
        if a_is_bg and not b_is_bg:
            return a
        if b_is_bg and not a_is_bg:
            return b

        # 兜底：DOM index 大的在上层（CSS 默认堆叠顺序）
        return a if a.index < b.index else b

    # ================================================================
    #  Step 2: 弹窗检测
    # ================================================================

    def _step2_detect_popup_elements(
        self, elements: List['DOMElement']
    ) -> Set[int]:
        """
        检测弹窗/模态框内的元素，返回它们的 index 集合。

        策略：
          1. 找到弹窗容器（通过 class / role 关键词）
          2. 获取容器的 bounding box
          3. 中心点落在容器 bbox 内的元素 → 标记为弹窗元素
        """
        popup_indices: Set[int] = set()
        popup_containers: List['DOMElement'] = []

        # 第一遍：找出弹窗容器
        for elem in elements:
            cls = elem.attributes.get('class', '').lower()
            role = elem.attributes.get('role', '').lower()

            is_popup = (
                any(kw in cls for kw in POPUP_CLASS_KEYWORDS)
                or role in POPUP_ROLES
            )

            if is_popup and elem.position:
                popup_containers.append(elem)
                popup_indices.add(elem.index)

        if not popup_containers:
            return popup_indices

        # 第二遍：找出位于弹窗 bbox 内的子元素
        for elem in elements:
            if elem.index in popup_indices:
                continue
            if not elem.position:
                continue

            for container in popup_containers:
                if self._is_center_inside(elem.position, container.position):
                    popup_indices.add(elem.index)
                    break  # 匹配到一个容器即可

        return popup_indices

    @staticmethod
    def _is_center_inside(
        inner: Dict[str, int], outer: Dict[str, int]
    ) -> bool:
        """判断 inner 元素的中心点是否落在 outer 的 bbox 内"""
        cx = inner.get('x', 0) + inner.get('width', 0) / 2
        cy = inner.get('y', 0) + inner.get('height', 0) / 2

        ox = outer.get('x', 0)
        oy = outer.get('y', 0)
        ow = outer.get('width', 0)
        oh = outer.get('height', 0)

        return (ox <= cx <= ox + ow) and (oy <= cy <= oy + oh)

    # ================================================================
    #  Step 3: 去重
    # ================================================================

    def _step3_deduplicate(
        self,
        elements: List['DOMElement'],
        debug_info: Dict[str, Any],
        debug: bool
    ) -> List['DOMElement']:
        """
        去重：相同文本的元素只保留第一个。

        text key 策略：
          - 有文本 → 用完整文本
          - 无文本但有 aria-label → 用 aria-label
          - 都没有 → 用 tag:index（不去重）
        """
        seen: Dict[str, int] = {}
        result = []

        for elem in elements:
            key = self._get_text_key(elem)

            if key not in seen:
                seen[key] = elem.index
                result.append(elem)
            else:
                if debug:
                    debug_info['filtered_out'].append({
                        'index': elem.index,
                        'step': 3,
                        'reason': f'Duplicate text (kept index {seen[key]})',
                        'tag': elem.tag,
                        'text': (elem.text[:50] if elem.text else ''),
                    })

        return result

    @staticmethod
    def _get_text_key(elem: 'DOMElement') -> str:
        text = elem.text.strip()
        if text:
            return f"text:{text}"

        aria_label = elem.attributes.get('aria-label', '').strip()
        if aria_label:
            return f"aria:{aria_label}"

        # 无明确文本标识 → 唯一 key，不去重
        return f"unique:{elem.tag}:{elem.index}"

    # ================================================================
    #  Step 4: 智能截断
    # ================================================================

    def _step4_smart_truncate(
        self,
        elements: List['DOMElement'],
        max_count: int,
        popup_indices: Set[int],
        debug_info: Dict[str, Any],
        debug: bool
    ) -> List['DOMElement']:
        """
        智能截断：弹窗元素优先保留。

        策略：
          1. 弹窗元素全部优先保留（但不超过 max_count）
          2. 剩余名额按原始顺序给非弹窗元素
        """
        popup_elems = [e for e in elements if e.index in popup_indices]
        normal_elems = [e for e in elements if e.index not in popup_indices]

        # 弹窗元素优先，但也不能超过 max_count
        kept_popup = popup_elems[:max_count]
        remaining_slots = max_count - len(kept_popup)
        kept_normal = normal_elems[:remaining_slots]

        result = kept_popup + kept_normal

        if debug:
            kept_set = {e.index for e in result}
            for elem in elements:
                if elem.index not in kept_set:
                    debug_info['filtered_out'].append({
                        'index': elem.index,
                        'step': 4,
                        'reason': (
                            f'Truncated (max_count={max_count}, '
                            f'popup_kept={len(kept_popup)}, '
                            f'normal_kept={len(kept_normal)})'
                        ),
                        'tag': elem.tag,
                    })

        return result

    # ================================================================
    #  工具方法
    # ================================================================

    @staticmethod
    def get_full_element_info(elem: 'DOMElement') -> Dict[str, Any]:
        """获取元素的完整信息（不裁剪任何属性）"""
        return {
            'index': elem.index,
            'tag': elem.tag,
            'text': elem.text,
            'attributes': elem.attributes.copy() if elem.attributes else {},
            'position': elem.position.copy() if elem.position else None,
            'xpath': getattr(elem, 'xpath', None),
            'parent_index': getattr(elem, 'parent_index', None),
        }

    def get_all_elements_full_info(
        self, elements: List['DOMElement']
    ) -> List[Dict[str, Any]]:
        """获取所有元素的完整信息列表"""
        return [self.get_full_element_info(e) for e in elements]


# ==================== 默认实例 & 便捷函数 ====================

_default_filter = ElementFilter()


def filter_elements(
    elements: List['DOMElement'],
    max_count: int = None,
    config: FilterConfig = None,
    debug: bool = False
) -> Tuple[List['DOMElement'], Dict[str, Any]]:
    """
    便捷函数：过滤元素列表（主接口，向后兼容）

    Args:
        elements: 原始元素列表
        max_count: 最大保留数量
        config: 过滤配置
        debug: 是否返回调试信息

    Returns:
        (过滤后的元素列表, 调试信息字典)
    """
    if config:
        f = ElementFilter(config)
    else:
        f = _default_filter
    return f.filter_elements(elements, max_count, debug=debug)


def get_elements_full_info(
    elements: List['DOMElement'],
    config: FilterConfig = None
) -> List[Dict[str, Any]]:
    """便捷函数：获取所有元素的完整信息"""
    if config:
        f = ElementFilter(config)
    else:
        f = _default_filter
    return f.get_all_elements_full_info(elements)
