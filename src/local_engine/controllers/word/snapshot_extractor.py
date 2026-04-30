"""
Word SnapshotExtractor —— 把当前 Word 文档状态序列化成 AI 可读的 JSON。

## 为什么独立一个文件？
跟 PPT 的 `snapshot_extractor.py` 对齐。Word 文档可能有 100 页、几万段，
快照逻辑本身就够 400+ 行，再塞回 controller.py 会让主入口类难以阅读。

## 核心设计：scope 枚举（Word 特色）
原 WordController 只有一个 bool `current_page_only`，大文档完全不够用：
AI 想改第 5 章 2.1 节，不能每次都把全文读回来。

现在支持 6 种 scope，从轻到重：

    outline_only     标题树（几 KB 就够）—— 大文档必备，AI 先看全局结构
    current_page     当前页段落 + 样式 —— 默认值，跟旧行为兼容
    current_section  当前 section 范围
    selection        用户当前选区范围
    paragraph_range  指定段落 index 区间 (start, end)，AI 可精确取样
    full             全文 —— 显式请求才返回，避免误触 MB 级 payload

额外开关：
    include_outline / include_styles / include_bookmarks / include_toc
    include_screenshot
"""

from __future__ import annotations

import base64
import logging
from typing import Any, Dict, List, Literal, Optional, Tuple

from .constants import (
    WD_ACTIVE_END_PAGE_NUMBER,
    WD_ACTIVE_END_SECTION_NUMBER,
    WD_GOTO_ABSOLUTE,
    WD_GOTO_PAGE,
    WD_OUTLINE_LEVEL_BODY_TEXT,
    WD_STATISTIC_CHARACTERS,
    WD_STATISTIC_PAGES,
    WD_STATISTIC_PARAGRAPHS,
    WD_STATISTIC_WORDS,
    WD_UNDEFINED,
)
from .format_helpers import (
    alignment_name,
    color_to_hex,
    line_spacing_rule_name,
    safe_font_size,
    safe_round,
    tri_state_to_bool,
)

logger = logging.getLogger(__name__)


SnapshotScope = Literal[
    "outline_only",
    "current_page",
    "current_section",
    "selection",
    "paragraph_range",
    "full",
]


class SnapshotExtractor:
    """
    Word 文档快照提取器。被 WordController 持有，COM 对象每次外部传入
    （SnapshotExtractor 自己不管理 COM 连接生命周期）。
    """

    # ==================== 对外入口 ====================

    def get_snapshot(
        self,
        app,
        doc,
        scope: SnapshotScope = "current_page",
        paragraph_range: Optional[Tuple[int, int]] = None,
        max_paragraphs: Optional[int] = None,
        include_content: bool = True,
        include_screenshot: bool = True,
        include_outline: bool = False,
        include_styles: bool = False,
        include_bookmarks: bool = False,
        include_toc: bool = False,
    ) -> Dict[str, Any]:
        """
        Returns:
            {
                "document_info": {...},
                "content": {...}             # include_content
                "outline": [...]             # include_outline
                "styles": [...]              # include_styles
                "bookmarks": [...]           # include_bookmarks
                "toc": [...]                 # include_toc
                "screenshot": "base64"       # include_screenshot
            }
        """
        result: Dict[str, Any] = {
            "document_info": self.extract_document_info(app, doc),
        }

        if include_content:
            result["content"] = self._extract_content_by_scope(
                app, doc, scope, paragraph_range, max_paragraphs
            )

        # outline_only scope 会在 content 里塞 outline；为了让顶层
        # ``result["outline"]`` 在 outline_only / include_outline 两种入口下行为一致，
        # 这里把 content 里的 outline 也提到顶层（避免 AI 同时记两种路径）。
        if scope == "outline_only" and include_content:
            result.setdefault("outline", result["content"].get("outline", []))

        if include_outline:
            result["outline"] = self.extract_outline(doc)

        if include_styles:
            result["styles"] = self.extract_styles(doc)

        if include_bookmarks:
            result["bookmarks"] = self.extract_bookmarks(doc)

        if include_toc:
            result["toc"] = self.extract_toc(doc)

        if include_screenshot:
            screenshot = self.take_screenshot(app, doc)
            if screenshot:
                result["screenshot"] = screenshot

        return result

    # ==================== 基础信息 ====================

    def extract_document_info(self, app, doc) -> Dict[str, Any]:
        """文档级别元信息 —— 所有 scope 都会返回这块（便宜）。

        关键字段说明：
        - ``paragraph_count``       走 ``ComputeStatistics`` 得到的"用户感知"段落数，
                                    会跳过仅含分页符等的"空段落"。**仅供展示**。
        - ``paragraphs_total``      ``doc.Paragraphs.Count``：COM 段落集合的真实长度，
                                    AI 用 ``paragraph_range`` / outline 的
                                    ``paragraph_index`` 全部基于这个数。
                                    两者经常不相等（同一份文档统计 7、集合 36 都正常）。
        """
        try:
            page_count = doc.ComputeStatistics(WD_STATISTIC_PAGES)
            word_count = doc.ComputeStatistics(WD_STATISTIC_WORDS)
            character_count = doc.ComputeStatistics(WD_STATISTIC_CHARACTERS)
            paragraph_count = doc.ComputeStatistics(WD_STATISTIC_PARAGRAPHS)
        except Exception as e:
            logger.warning(f"[SnapshotExtractor] Failed to get statistics: {e}")
            page_count = word_count = character_count = paragraph_count = -1

        try:
            paragraphs_total = int(doc.Paragraphs.Count)
        except Exception as e:
            logger.warning(f"[SnapshotExtractor] Failed to get Paragraphs.Count: {e}")
            paragraphs_total = -1

        try:
            current_page = app.Selection.Information(WD_ACTIVE_END_PAGE_NUMBER)
        except Exception as e:
            logger.warning(f"[SnapshotExtractor] Failed to get current page: {e}")
            current_page = -1

        try:
            current_section = app.Selection.Information(WD_ACTIVE_END_SECTION_NUMBER)
        except Exception:
            current_section = -1

        try:
            selection_start = app.Selection.Start
            selection_end = app.Selection.End
        except Exception:
            selection_start = selection_end = -1

        try:
            content_end = int(doc.Content.End)
        except Exception:
            content_end = -1

        return {
            "name": doc.Name,
            "path": doc.FullName if doc.Path else None,
            "saved": doc.Saved,
            "current_page": current_page,
            "current_section": current_section,
            "page_count": page_count,
            "word_count": word_count,
            "character_count": character_count,
            "paragraph_count": paragraph_count,
            "paragraphs_total": paragraphs_total,
            "content_end": content_end,
            "selection": {"start": selection_start, "end": selection_end},
        }

    # ==================== scope 分发 ====================

    def _extract_content_by_scope(
        self,
        app,
        doc,
        scope: SnapshotScope,
        paragraph_range: Optional[Tuple[int, int]],
        max_paragraphs: Optional[int],
    ) -> Dict[str, Any]:
        """按 scope 挑范围，然后复用 _extract_range_content 做实际提取。"""
        if scope == "outline_only":
            # 特殊：不提取段落，直接给大纲树（小载荷）。
            # ``scope`` 字段保持和其他模式一致，方便消费方走同一条 dispatch。
            return {"scope": "outline_only", "outline": self.extract_outline(doc)}

        if scope == "current_page":
            start, end = self._resolve_current_page_range(app, doc)
            return self._extract_range_content(
                app, doc, start, end, scope="current_page",
                extra={"current_page": self._current_page_number(app)},
            )

        if scope == "current_section":
            start, end = self._resolve_current_section_range(app, doc)
            return self._extract_range_content(
                app, doc, start, end, scope="current_section",
            )

        if scope == "selection":
            start = app.Selection.Start
            end = app.Selection.End
            if start == end:
                # 空选区等价当前页（避免什么都不返回）
                logger.debug("[SnapshotExtractor] empty selection, fallback to current_page")
                start, end = self._resolve_current_page_range(app, doc)
                return self._extract_range_content(
                    app, doc, start, end, scope="selection_fallback_page",
                )
            return self._extract_range_content(app, doc, start, end, scope="selection")

        if scope == "paragraph_range":
            if not paragraph_range:
                raise ValueError("scope=paragraph_range requires paragraph_range=(start, end)")
            start, end = self._resolve_paragraph_range(doc, *paragraph_range)
            return self._extract_range_content(
                app, doc, start, end, scope="paragraph_range",
                extra={"paragraph_range": list(paragraph_range)},
            )

        if scope == "full":
            # 可能非常大 —— AI 要显式选 full 才触发
            return self._extract_full_content(doc, max_paragraphs)

        raise ValueError(f"unknown scope: {scope!r}")

    # ==================== range → content ====================

    def _extract_range_content(
        self,
        app,
        doc,
        start_pos: int,
        end_pos: int,
        scope: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """给定字符级 range (start_pos, end_pos)，提取该范围内的段落 / 表格。"""
        # 全文纯文本始终给（几 KB，AI 做上下文判断需要）
        try:
            full_text = doc.Content.Text
        except Exception:
            full_text = ""

        # 当前 range 的文本（带有限长度，防止 scope=full 时炸大）
        try:
            range_text = doc.Range(start_pos, end_pos).Text
        except Exception:
            range_text = ""

        paragraphs: List[Dict[str, Any]] = []
        para_count = 0
        try:
            para_count = int(doc.Paragraphs.Count)
            for i in range(1, para_count + 1):
                try:
                    para = doc.Paragraphs(i)
                    p_start = para.Range.Start
                    p_end = para.Range.End
                    # 区间整体落在范围之外就跳过；半重叠仍算命中（避免边界段落被漏掉）
                    if p_end <= start_pos or p_start >= end_pos:
                        continue
                    text = para.Range.Text.strip()
                    if text:
                        paragraphs.append(self._extract_paragraph_info(para, i))
                except Exception as e:
                    logger.debug(f"[SnapshotExtractor] paragraph {i} skipped: {e}")
        except Exception as e:
            logger.warning(f"[SnapshotExtractor] paragraphs enum failed: {e}")

        tables: List[Dict[str, Any]] = []
        try:
            for i in range(1, doc.Tables.Count + 1):
                try:
                    table = doc.Tables(i)
                    t_start = table.Range.Start
                    t_end = table.Range.End
                    if t_end > start_pos and t_start < end_pos:
                        tables.append(self._extract_table_info(table, i))
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"[SnapshotExtractor] tables enum failed: {e}")

        result = {
            "scope": scope,
            "text": full_text,           # 全文纯文本（便于 AI 理解上下文）
            "range_text": range_text,    # 当前 scope 范围内的文本
            "range": {"start": start_pos, "end": end_pos},
            "paragraphs": paragraphs,
            "tables": tables,
            "paragraphs_total": para_count,  # 全文段落集合长度，用于 paragraph_range 边界推算
        }
        if extra:
            result.update(extra)
        return result

    def _extract_full_content(
        self, doc, max_paragraphs: Optional[int]
    ) -> Dict[str, Any]:
        """
        scope=full 专用 —— 遍历全部段落，不做 range 过滤。
        max_paragraphs 起截断作用，超出时 truncated=True。
        """
        try:
            full_text = doc.Content.Text
        except Exception:
            full_text = ""

        paragraphs: List[Dict[str, Any]] = []
        para_count = 0
        try:
            para_count = doc.Paragraphs.Count
            limit = min(para_count, max_paragraphs) if max_paragraphs else para_count
            for i in range(1, limit + 1):
                try:
                    para = doc.Paragraphs(i)
                    text = para.Range.Text.strip()
                    if text:
                        paragraphs.append(self._extract_paragraph_info(para, i))
                except Exception as e:
                    logger.debug(f"[SnapshotExtractor] paragraph {i} skipped: {e}")
        except Exception as e:
            logger.warning(f"[SnapshotExtractor] full paragraphs enum failed: {e}")

        tables: List[Dict[str, Any]] = []
        try:
            for i in range(1, doc.Tables.Count + 1):
                try:
                    tables.append(self._extract_table_info(doc.Tables(i), i))
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"[SnapshotExtractor] full tables enum failed: {e}")

        return {
            "scope": "full",
            "text": full_text,
            "paragraphs": paragraphs,
            "tables": tables,
            "paragraphs_total": para_count,
            "truncated": max_paragraphs is not None and para_count > max_paragraphs,
        }

    # ==================== range 解析工具 ====================

    def _current_page_number(self, app) -> int:
        try:
            return int(app.Selection.Information(WD_ACTIVE_END_PAGE_NUMBER))
        except Exception:
            return -1

    def _resolve_current_page_range(self, app, doc) -> Tuple[int, int]:
        """
        当前页的 (start, end) 字符偏移。为避免 `Selection.GoTo` 导致页面
        滚动，这里走 `Range.GoTo`（返回 Range 对象不动 Selection）。
        """
        current_page = self._current_page_number(app)
        total_pages = doc.ComputeStatistics(WD_STATISTIC_PAGES)

        original_start = app.Selection.Start
        original_end = app.Selection.End

        try:
            temp_range = doc.Range(0, 0)
            start_range = temp_range.GoTo(WD_GOTO_PAGE, WD_GOTO_ABSOLUTE, current_page)
            start_pos = start_range.Start

            if current_page < total_pages:
                end_range = temp_range.GoTo(WD_GOTO_PAGE, WD_GOTO_ABSOLUTE, current_page + 1)
                end_pos = end_range.Start
            else:
                end_pos = doc.Content.End
        finally:
            # 恢复原 Selection，避免页面滚动
            try:
                app.Selection.SetRange(original_start, original_end)
            except Exception:
                pass

        return start_pos, end_pos

    def _resolve_current_section_range(self, app, doc) -> Tuple[int, int]:
        """当前节的 (start, end)。"""
        try:
            section_num = int(app.Selection.Information(WD_ACTIVE_END_SECTION_NUMBER))
            section = doc.Sections(section_num)
            return section.Range.Start, section.Range.End
        except Exception as e:
            logger.warning(f"[SnapshotExtractor] resolve section failed, falling back to doc: {e}")
            return 0, doc.Content.End

    def _resolve_paragraph_range(
        self, doc, para_start: int, para_end: int
    ) -> Tuple[int, int]:
        """
        段落 index → 字符 range。para_start/para_end 都是 1-based，包含。
        越界自动夹紧。
        """
        total = doc.Paragraphs.Count
        lo = max(1, min(para_start, total))
        hi = max(lo, min(para_end, total))
        start_pos = doc.Paragraphs(lo).Range.Start
        end_pos = doc.Paragraphs(hi).Range.End
        return start_pos, end_pos

    # ==================== 段落 / 表格细节 ====================

    def _extract_paragraph_info(self, para, index: int) -> Dict[str, Any]:
        """段落级丰富信息：文本 + 样式名 + 字体 + 段落格式 + 位置。"""
        info: Dict[str, Any] = {
            "index": index,
            "text": para.Range.Text.strip(),
            "style": None,
            "format": {},
            "font": {},
            "position": {},
        }

        try:
            if para.Style:
                info["style"] = para.Style.NameLocal
        except Exception:
            pass

        try:
            pf = para.Format
            info["format"] = {
                "alignment": alignment_name(pf.Alignment),
                "first_line_indent": safe_round(pf.FirstLineIndent),
                "left_indent": safe_round(pf.LeftIndent),
                "right_indent": safe_round(pf.RightIndent),
                "space_before": safe_round(pf.SpaceBefore),
                "space_after": safe_round(pf.SpaceAfter),
                "line_spacing": safe_round(pf.LineSpacing),
                "line_spacing_rule": line_spacing_rule_name(pf.LineSpacingRule),
                "outline_level": (
                    pf.OutlineLevel
                    if pf.OutlineLevel and pf.OutlineLevel != WD_UNDEFINED
                    else WD_OUTLINE_LEVEL_BODY_TEXT
                ),
            }
        except Exception as e:
            logger.debug(f"[SnapshotExtractor] paragraph.format read failed: {e}")

        try:
            font = para.Range.Font
            try:
                underline_raw = font.Underline
            except Exception:
                underline_raw = None
            if underline_raw is None or underline_raw == WD_UNDEFINED:
                underline_value: Optional[int] = None
            else:
                # 0 = 无下划线，1+ 为各种下划线类型；都保留原始 int 给 AI 判断。
                try:
                    underline_value = int(underline_raw)
                except Exception:
                    underline_value = None

            info["font"] = {
                "name": font.Name or None,
                "name_ascii": font.NameAscii or None,
                "name_far_east": font.NameFarEast or None,
                "size": safe_font_size(font.Size),
                "bold": tri_state_to_bool(font.Bold),
                "italic": tri_state_to_bool(font.Italic),
                "underline": underline_value,
                "color": color_to_hex(font.Color),
            }
        except Exception as e:
            logger.debug(f"[SnapshotExtractor] paragraph.font read failed: {e}")

        try:
            info["position"] = {
                "start": para.Range.Start,
                "end": para.Range.End,
            }
        except Exception:
            pass

        return info

    def _extract_table_info(self, table, index: int) -> Dict[str, Any]:
        """表格结构预览：行列数 + 位置 + 样式 + 3x3 预览。"""
        info: Dict[str, Any] = {
            "index": index,
            "rows": 0,
            "columns": 0,
            "position": {},
            "style": None,
            "cells_preview": [],
        }

        try:
            info["rows"] = table.Rows.Count
            info["columns"] = table.Columns.Count
        except Exception:
            pass

        try:
            info["position"] = {
                "start": table.Range.Start,
                "end": table.Range.End,
            }
        except Exception:
            pass

        try:
            if table.Style:
                info["style"] = str(table.Style)
        except Exception:
            pass

        try:
            max_rows = min(3, info["rows"])
            max_cols = min(3, info["columns"])
            for r in range(1, max_rows + 1):
                for c in range(1, max_cols + 1):
                    try:
                        cell = table.Cell(r, c)
                        text = cell.Range.Text.strip().replace("\r\x07", "").replace("\x07", "")
                        if text:
                            info["cells_preview"].append({
                                "row": r,
                                "col": c,
                                "text": text[:50],
                            })
                    except Exception:
                        pass
        except Exception:
            pass

        return info

    # ==================== 大纲 / 样式 / 书签 / TOC ====================

    def extract_outline(self, doc) -> List[Dict[str, Any]]:
        """
        提取标题树（Heading 1~9），每项带段落 index 和字符偏移。
        AI 可以用 `heading.path` 来定位 —— locator 引擎基础。

        返回的是"扁平列表 + level"，消费方可以自己建树。
        """
        outline: List[Dict[str, Any]] = []
        try:
            para_count = doc.Paragraphs.Count
            for i in range(1, para_count + 1):
                try:
                    para = doc.Paragraphs(i)
                    pf = para.Format
                    level = pf.OutlineLevel
                    # 1~9 才是标题，10 是正文
                    if not level or level == WD_UNDEFINED or level >= WD_OUTLINE_LEVEL_BODY_TEXT:
                        continue
                    text = para.Range.Text.strip()
                    if not text:
                        continue
                    outline.append({
                        "level": int(level),
                        "text": text,
                        "paragraph_index": i,
                        "range": {
                            "start": para.Range.Start,
                            "end": para.Range.End,
                        },
                        "style": para.Style.NameLocal if para.Style else None,
                    })
                except Exception as e:
                    logger.debug(f"[SnapshotExtractor] outline para {i} skipped: {e}")
        except Exception as e:
            logger.warning(f"[SnapshotExtractor] outline enum failed: {e}")
        return outline

    def extract_styles(self, doc) -> List[Dict[str, Any]]:
        """
        列出文档中定义的命名样式（供 AI 做 apply_style 时选用）。
        Word 样式表通常有 200+ 条，这里只返回 BuiltIn=False 的 + 常用内置标题样式。
        """
        styles: List[Dict[str, Any]] = []
        try:
            for i in range(1, doc.Styles.Count + 1):
                try:
                    st = doc.Styles(i)
                    # wdStyleTypeParagraph=1, wdStyleTypeCharacter=2, wdStyleTypeTable=3, wdStyleTypeList=4
                    st_type = getattr(st, "Type", 0)
                    name = st.NameLocal
                    if not name:
                        continue
                    styles.append({
                        "name": name,
                        "name_english": getattr(st, "NameEnglish", name),
                        "type": int(st_type),
                        "built_in": bool(getattr(st, "BuiltIn", False)),
                    })
                except Exception:
                    continue
        except Exception as e:
            logger.warning(f"[SnapshotExtractor] styles enum failed: {e}")
        return styles

    def extract_bookmarks(self, doc) -> List[Dict[str, Any]]:
        """列书签。"""
        bookmarks: List[Dict[str, Any]] = []
        try:
            for i in range(1, doc.Bookmarks.Count + 1):
                try:
                    bm = doc.Bookmarks(i)
                    bookmarks.append({
                        "name": bm.Name,
                        "range": {
                            "start": bm.Range.Start,
                            "end": bm.Range.End,
                        },
                    })
                except Exception:
                    continue
        except Exception as e:
            logger.warning(f"[SnapshotExtractor] bookmarks enum failed: {e}")
        return bookmarks

    def extract_toc(self, doc) -> List[Dict[str, Any]]:
        """
        列出已插入的目录（TablesOfContents）。注意这跟"自己建的大纲"是两回事：
        这里返回的是 Word 文档里实际存在的 TOC 对象。
        """
        tocs: List[Dict[str, Any]] = []
        try:
            for i in range(1, doc.TablesOfContents.Count + 1):
                try:
                    toc = doc.TablesOfContents(i)
                    tocs.append({
                        "index": i,
                        "range": {
                            "start": toc.Range.Start,
                            "end": toc.Range.End,
                        },
                        "lower_heading_level": getattr(toc, "LowerHeadingLevel", None),
                        "upper_heading_level": getattr(toc, "UpperHeadingLevel", None),
                    })
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"[SnapshotExtractor] TOC enum failed: {e}")
        return tocs

    # ==================== 截图（委托给共享 capture helper） ====================

    def take_screenshot(self, app, doc) -> Optional[str]:
        """
        走共享的 capture_hwnd_image —— PrintWindow / ImageGrab 混合策略，
        **不抢焦点**。失败返回 None。

        ``app.ActiveWindow.Hwnd`` 在某些版本/语言包下会抛 com_error，
        所以这里加了一层回退：通过 EnumWindows 找 ``WINWORD`` 进程的窗口。
        """
        try:
            from controllers.system.window_handler import capture_hwnd_image
            from controllers.computer_use.win_executor.handlers.image_utils import (
                compress_screenshot_from_pil,
            )

            hwnd = self._resolve_word_hwnd(app)
            if not hwnd:
                logger.warning("[SnapshotExtractor] Could not find Word window handle")
                return None

            img = capture_hwnd_image(hwnd, prefer_printwindow=False)
            if img is None:
                logger.warning("[SnapshotExtractor] capture_hwnd_image returned None")
                return None

            compressed = compress_screenshot_from_pil(img)
            return base64.b64encode(compressed).decode("utf-8")
        except Exception as e:
            logger.warning(f"[SnapshotExtractor] screenshot failed: {e}", exc_info=True)
            return None

    def _resolve_word_hwnd(self, app) -> Optional[int]:
        """优先 ActiveWindow.Hwnd，失败回退 EnumWindows 找 Word 顶级窗口。"""
        try:
            hwnd = int(app.ActiveWindow.Hwnd)
            if hwnd:
                return hwnd
        except Exception as e:
            logger.debug(f"[SnapshotExtractor] ActiveWindow.Hwnd unavailable: {e}")

        try:
            import win32gui
            import win32process

            try:
                import psutil
            except Exception:
                psutil = None  # type: ignore[assignment]

            found: List[int] = []

            def _enum_cb(h, _):
                try:
                    if not win32gui.IsWindowVisible(h):
                        return True
                    title = win32gui.GetWindowText(h) or ""
                    cls = win32gui.GetClassName(h) or ""
                    if cls.startswith("OpusApp") or "- Word" in title or " - Microsoft Word" in title:
                        if psutil is not None:
                            try:
                                _, pid = win32process.GetWindowThreadProcessId(h)
                                proc = psutil.Process(pid)
                                if proc.name().lower() == "winword.exe":
                                    found.append(h)
                            except Exception:
                                found.append(h)
                        else:
                            found.append(h)
                except Exception:
                    pass
                return True

            win32gui.EnumWindows(_enum_cb, None)
            if found:
                return found[0]
        except Exception as e:
            logger.debug(f"[SnapshotExtractor] EnumWindows fallback failed: {e}")

        return None
