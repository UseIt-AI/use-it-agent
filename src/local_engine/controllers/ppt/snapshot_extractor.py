"""
PPT Snapshot Extractor - 演示文稿快照采集

负责从 PowerPoint COM 对象中提取结构化内容和截图。
由 PPTController 调用，不直接管理 COM 连接生命周期。

当 current_slide_only=True 时，返回的内容与 get_current_context 同等丰富：
  handle_id、fill/line 颜色、字体详情、rotation、z_order、占位符、背景色。
AI 每次执行后即可拿到完整感知信息，无需额外调用 get_current_context。
"""

import base64
import json
import logging
from typing import Any, Dict, List, Optional

from .constants import (
    PLACEHOLDER_TYPES,
    SHAPE_TYPE_NAMES,
    color_int_to_hex,
    parse_color,
)
from .renderer.linter import LayoutLinter

logger = logging.getLogger(__name__)


class SnapshotExtractor:
    """PPT 快照采集：内容提取 + 截图"""

    def get_snapshot(
        self,
        app,
        pres,
        include_content: bool,
        include_screenshot: bool,
        max_slides: Optional[int],
        current_slide_only: bool = False,
    ) -> Dict[str, Any]:
        """
        采集演示文稿快照。

        Args:
            app: COM PowerPoint.Application
            pres: COM Presentation
            include_content: 是否包含内容
            include_screenshot: 是否包含截图
            max_slides: 最大幻灯片数
            current_slide_only: 只返回当前幻灯片
        """
        result: Dict[str, Any] = {
            "presentation_info": self.extract_presentation_info(app, pres)
        }

        if include_content:
            if current_slide_only:
                result["content"] = self._extract_current_slide_content(app, pres)
            else:
                result["content"] = self._extract_content(pres, max_slides)

        if include_screenshot:
            screenshot = self.take_screenshot(app, pres)
            if screenshot:
                result["screenshot"] = screenshot

        return result

    # ==================== Presentation Info ====================

    def extract_presentation_info(self, app, pres) -> Dict[str, Any]:
        """提取演示文稿基本信息（包含当前幻灯片编号）"""
        try:
            slide_count = pres.Slides.Count
        except Exception as e:
            logger.warning(f"[SnapshotExtractor] Failed to get slide count: {e}")
            slide_count = -1

        try:
            if app.ActiveWindow and app.ActiveWindow.View:
                current_slide = app.ActiveWindow.View.Slide.SlideIndex
            else:
                current_slide = 1
        except Exception as e:
            logger.warning(f"[SnapshotExtractor] Failed to get current slide: {e}")
            current_slide = -1

        try:
            slide_width = pres.PageSetup.SlideWidth
            slide_height = pres.PageSetup.SlideHeight
        except Exception:
            slide_width = slide_height = -1

        return {
            "name": pres.Name,
            "path": pres.FullName if pres.Path else None,
            "saved": pres.Saved,
            "current_slide": current_slide,
            "slide_count": slide_count,
            "slide_width": slide_width,
            "slide_height": slide_height,
        }

    # ==================== Content Extraction ====================

    def _extract_content(self, pres, max_slides: Optional[int]) -> Dict[str, Any]:
        """提取演示文稿内容"""
        slides = []
        slide_count = pres.Slides.Count
        limit = min(slide_count, max_slides) if max_slides else slide_count

        for i in range(1, limit + 1):
            try:
                slide = pres.Slides(i)
                slide_info = self._extract_slide_info(slide, i)
                slides.append(slide_info)
            except Exception as e:
                logger.warning(f"[SnapshotExtractor] Failed to read slide {i}: {e}")

        return {
            "slides": slides,
            "total_slides": slide_count,
            "truncated": max_slides is not None and slide_count > max_slides,
        }

    def _extract_current_slide_content(self, app, pres) -> Dict[str, Any]:
        """
        提取当前幻灯片的完整上下文（与 get_current_context 同等丰富）。

        包含：slide 元信息、占位符、所有元素（handle_id / 颜色 / 字体 / z_order）、
        背景色、备注、全幻灯片标题摘要。
        """
        try:
            current_slide_index = 1
            if app.ActiveWindow and app.ActiveWindow.View:
                current_slide_index = app.ActiveWindow.View.Slide.SlideIndex

            total_slides = pres.Slides.Count
            slide = pres.Slides(current_slide_index)

            # Slide dimensions
            slide_width = pres.PageSetup.SlideWidth
            slide_height = pres.PageSetup.SlideHeight

            # Layout name (try real name first, fallback to number)
            layout_name = None
            try:
                layout_name = slide.CustomLayout.Name
            except Exception:
                try:
                    layout_name = str(slide.Layout)
                except Exception:
                    pass

            # Background color
            background = None
            try:
                bg_fill = slide.Background.Fill
                if bg_fill.Type == 1:  # msoFillSolid
                    background = color_int_to_hex(bg_fill.ForeColor.RGB)
            except Exception:
                pass

            # Placeholders
            placeholders = self._extract_placeholders(slide)

            # Collect selected shape names + text selection info first
            selected_names, selection_info = self._get_selection_context(app)

            # All elements (rich detail, with selected flag)
            elements = []
            try:
                for i in range(1, slide.Shapes.Count + 1):
                    shape = slide.Shapes(i)
                    elem = self._extract_shape_detailed(shape, i)
                    if elem.get("handle_id") in selected_names:
                        elem["selected"] = True
                    elements.append(elem)
            except Exception as e:
                logger.warning(f"[SnapshotExtractor] Failed to read shapes: {e}")

            # Notes
            notes = None
            try:
                np = slide.NotesPage
                if np.Shapes.Count >= 2:
                    notes_text = np.Shapes(2).TextFrame.TextRange.Text.strip()
                    if notes_text:
                        notes = notes_text
            except Exception:
                pass

            # Blueprint declared by the LLM on previous render_ppt_layout call
            blueprint = self._extract_blueprint(slide)
            # Auto-lint: validate rendered shapes against blueprint declarations.
            # Always run (even with empty blueprint) so out-of-bounds shapes are
            # surfaced regardless of whether layers were declared.
            try:
                lint_input = [
                    {
                        "handle_id": e.get("handle_id"),
                        "layer_id": e.get("layer_id"),
                        "bounds": e.get("bounds"),
                        "fill_color": e.get("fill_color"),
                        "line_color": e.get("line_color"),
                    }
                    for e in elements
                ]
                layout_issues = LayoutLinter.lint(
                    lint_input, slide_width, slide_height, blueprint
                )
            except Exception as e:
                logger.warning(f"[SnapshotExtractor] Layout linter failed: {e}")
                layout_issues = []

            # All slides summary (title + all text boxes)
            all_slides_summary = []
            for i in range(1, total_slides + 1):
                try:
                    s = pres.Slides(i)
                    title = self._get_slide_title(s)
                    texts = self._collect_slide_texts(s)
                    all_slides_summary.append({"index": i, "title": title, "texts": texts})
                except Exception:
                    all_slides_summary.append({"index": i, "title": None, "texts": []})

            logger.info(f"[SnapshotExtractor] Current slide {current_slide_index}/{total_slides}")

            return {
                "current_slide": {
                    "index": current_slide_index,
                    "width": round(slide_width, 2),
                    "height": round(slide_height, 2),
                    "layout": layout_name,
                    "background": background,
                    "title": self._get_slide_title(slide),
                    "placeholders": placeholders,
                    "elements": elements,
                    "notes": notes,
                    "selection": selection_info,
                    "blueprint": blueprint,
                    "layout_issues": layout_issues,
                },
                "current_slide_index": current_slide_index,
                "total_slides": total_slides,
                "all_slides_summary": all_slides_summary,
            }

        except Exception as e:
            logger.error(
                f"[SnapshotExtractor] Failed to extract current slide content: {e}",
                exc_info=True,
            )
            return self._extract_content(pres, max_slides=10)

    def _extract_placeholders(self, slide) -> List[Dict[str, Any]]:
        """提取幻灯片占位符信息"""
        placeholders: List[Dict[str, Any]] = []
        seen: set = set()

        def _append_placeholder(ph_obj, fallback_name: Optional[str] = None) -> None:
            """Read placeholder info from a COM shape-like object and append if unique."""
            try:
                ph_type_raw = ph_obj.PlaceholderFormat.Type
            except Exception:
                return

            try:
                name = ph_obj.Name
            except Exception:
                name = None
            if not name:
                name = fallback_name or f"placeholder_{len(placeholders) + 1}"

            try:
                bounds = {
                    "x": round(ph_obj.Left, 2),
                    "y": round(ph_obj.Top, 2),
                    "w": round(ph_obj.Width, 2),
                    "h": round(ph_obj.Height, 2),
                }
            except Exception:
                bounds = {"x": 0.0, "y": 0.0, "w": 0.0, "h": 0.0}

            ph_info: Dict[str, Any] = {
                "type": PLACEHOLDER_TYPES.get(ph_type_raw, f"type_{ph_type_raw}"),
                "name": name,
                "bounds": bounds,
                "has_content": False,
                "text": "",
            }

            try:
                if ph_obj.HasTextFrame and ph_obj.TextFrame.HasText:
                    ph_info["has_content"] = True
                    ph_info["text"] = ph_obj.TextFrame.TextRange.Text.strip()
            except Exception:
                pass

            # Dedup by type + geometry; name is often unstable across templates.
            dedup_key = (
                ph_info["type"],
                bounds["x"], bounds["y"], bounds["w"], bounds["h"],
            )
            if dedup_key in seen:
                return
            seen.add(dedup_key)
            placeholders.append(ph_info)

        try:
            for i in range(1, slide.Placeholders.Count + 1):
                _append_placeholder(slide.Placeholders(i), fallback_name=f"placeholder_{i}")
        except Exception as e:
            logger.warning(f"[SnapshotExtractor] Failed to read placeholders: {e}")

        # Fallback/补充：某些模板中 Slide.Placeholders 为空，但 Shapes 中仍可读到 PlaceholderFormat。
        try:
            for i in range(1, slide.Shapes.Count + 1):
                shape = slide.Shapes(i)
                is_placeholder = False
                try:
                    is_placeholder = shape.Type == 14  # msoPlaceholder
                except Exception:
                    pass
                if not is_placeholder:
                    try:
                        _ = shape.PlaceholderFormat.Type
                        is_placeholder = True
                    except Exception:
                        pass
                if is_placeholder:
                    _append_placeholder(shape, fallback_name=f"shape_placeholder_{i}")
        except Exception as e:
            logger.warning(f"[SnapshotExtractor] Failed to read placeholders from shapes: {e}")

        return placeholders

    # ==================== Selection Extraction ====================

    _SELECTION_TYPES = {
        0: "none",       # ppSelectionNone
        1: "slides",     # ppSelectionSlides
        2: "shapes",     # ppSelectionShapes
        3: "text",       # ppSelectionText
    }

    def _get_selection_context(self, app) -> tuple:
        """
        提取选区上下文：选中的 shape 名称集合 + 轻量 selection 摘要。

        Returns:
            (selected_names: set[str], selection_info: dict|None)

        selected_names 用于在 elements 列表中标记 selected=True。
        selection_info 只保留不可从 elements 推断的信息（选区类型、选中文字）。
        """
        selected_names: set = set()
        selection_info: Optional[Dict[str, Any]] = None

        try:
            sel = app.ActiveWindow.Selection
            sel_type = sel.Type
            type_name = self._SELECTION_TYPES.get(sel_type, f"type_{sel_type}")

            if sel_type in (2, 3):  # ppSelectionShapes or ppSelectionText
                try:
                    sr = sel.ShapeRange
                    for i in range(1, sr.Count + 1):
                        selected_names.add(sr(i).Name)
                except Exception as e:
                    logger.warning(f"[SnapshotExtractor] Failed to read ShapeRange: {e}")

            if sel_type == 3:  # ppSelectionText — record highlighted text
                try:
                    selection_info = {
                        "type": type_name,
                        "selected_text": sel.TextRange.Text,
                        "shape_handle_id": sel.ShapeRange(1).Name,
                    }
                except Exception as e:
                    logger.warning(f"[SnapshotExtractor] Failed to read TextRange: {e}")

            if selection_info is None and selected_names:
                selection_info = {"type": type_name}

        except Exception as e:
            logger.warning(f"[SnapshotExtractor] Failed to read selection: {e}")

        return selected_names, selection_info

    # ==================== Slide / Shape Extraction ====================

    def _extract_slide_info(self, slide, index: int, detailed: bool = False) -> Dict[str, Any]:
        """
        提取幻灯片概览信息（轻量级，用于多幻灯片列表）。

        只保留 AI 关心的内容：标题、所有文本、是否有表格/图表、备注。
        表格内容直接转为 markdown。
        """
        info: Dict[str, Any] = {
            "index": index,
            "title": self._get_slide_title(slide),
            "texts": [],
            "has_table": False,
            "has_chart": False,
            "notes": None,
        }

        try:
            for i in range(1, slide.Shapes.Count + 1):
                shape = slide.Shapes(i)
                try:
                    if shape.HasTable:
                        info["has_table"] = True
                        md = self._table_to_markdown(shape.Table)
                        if md:
                            info["texts"].append(md)
                        continue
                except Exception:
                    pass
                try:
                    if shape.HasChart:
                        info["has_chart"] = True
                        continue
                except Exception:
                    pass
                try:
                    if shape.HasTextFrame and shape.TextFrame.HasText:
                        text = shape.TextFrame.TextRange.Text.strip()
                        if text:
                            info["texts"].append(text)
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"[SnapshotExtractor] Failed to read shapes on slide {index}: {e}")

        try:
            notes_page = slide.NotesPage
            if notes_page.Shapes.Count >= 2:
                notes_text = notes_page.Shapes(2).TextFrame.TextRange.Text
                info["notes"] = notes_text.strip() if notes_text else None
        except Exception:
            pass

        return info

    def _extract_shape_detailed(self, shape, index: int) -> Dict[str, Any]:
        """提取形状的完整上下文（detailed 模式，与 action_executor.get_current_context 对齐）"""
        info: Dict[str, Any] = {
            "index": index,
            "handle_id": None,
            "type": None,
            "type_name": None,
            "bounds": {},
            "text": None,
            "font": None,
            "fill_color": None,
            "line_color": None,
            "line_weight": None,
            "rotation": 0,
            "z_order": None,
            "layer_id": None,
            "layer_role": None,
            "render_as": None,
            "layer_z": None,
        }

        try:
            info["handle_id"] = shape.Name
        except Exception:
            pass

        layer_meta = self._extract_layer_metadata(shape, info.get("handle_id"))
        info.update(layer_meta)

        try:
            type_id = shape.Type
            info["type"] = type_id
            info["type_name"] = SHAPE_TYPE_NAMES.get(type_id, f"type_{type_id}")
        except Exception:
            pass

        try:
            info["bounds"] = {
                "x": round(shape.Left, 2),
                "y": round(shape.Top, 2),
                "w": round(shape.Width, 2),
                "h": round(shape.Height, 2),
            }
        except Exception:
            pass

        try:
            info["rotation"] = round(shape.Rotation, 2)
        except Exception:
            pass

        try:
            info["z_order"] = shape.ZOrderPosition
        except Exception:
            pass

        # Text + Font (with per-run detection for mixed formatting)
        try:
            if shape.HasTextFrame and shape.TextFrame.HasText:
                full_text = shape.TextFrame.TextRange.Text
                info["text"] = full_text.strip()

                # Scan per-character to detect mixed formatting runs
                runs = self._extract_text_runs(shape)
                if runs and len(runs) > 1:
                    # Mixed formatting — return per-run info so Planner
                    # can see that different segments have different colors.
                    info["font"] = {"mixed": True}
                    info["rich_text"] = runs
                else:
                    # Uniform formatting — single font dict
                    try:
                        first_para = shape.TextFrame.TextRange.Paragraphs(1)
                        font = first_para.Font
                        info["font"] = {
                            "name": font.Name if font.Name else None,
                            "size": font.Size if font.Size > 0 else None,
                            "bold": bool(font.Bold) if font.Bold != -2 else None,
                            "italic": bool(font.Italic) if font.Italic != -2 else None,
                            "color": None,
                        }
                        try:
                            info["font"]["color"] = color_int_to_hex(font.Color.RGB)
                        except Exception:
                            pass
                    except Exception:
                        pass

                # Detect text gradient via TextFrame2
                try:
                    tf2_fill = shape.TextFrame2.TextRange.Font.Fill
                    if tf2_fill.Type == 3:  # msoFillGradient
                        info["font_fill_type"] = "gradient"
                        info["font_gradient"] = self._extract_gradient(tf2_fill)
                except Exception:
                    pass
        except Exception:
            pass

        # Fill
        try:
            fill = shape.Fill
            if fill.Type == 1:  # msoFillSolid
                info["fill_color"] = color_int_to_hex(fill.ForeColor.RGB)
            elif fill.Type == 3:  # msoFillGradient
                info["fill_type"] = "gradient"
                info["fill_gradient"] = self._extract_gradient(fill)
            elif fill.Type == 5:  # msoFillBackground (no fill)
                info["fill_color"] = "none"
        except Exception:
            pass

        # Line
        try:
            line = shape.Line
            if line.Visible:
                try:
                    info["line_color"] = color_int_to_hex(line.ForeColor.RGB)
                except Exception:
                    pass
                try:
                    info["line_weight"] = round(line.Weight, 2)
                except Exception:
                    pass
                try:
                    line_fill_type = line.Fill.Type if hasattr(line, 'Fill') else None
                    if line_fill_type == 3:  # msoFillGradient
                        info["line_fill_type"] = "gradient"
                except Exception:
                    pass
        except Exception:
            pass

        # Table / Chart
        try:
            if shape.HasTable:
                t = shape.Table
                info["table"] = {
                    "rows": t.Rows.Count,
                    "columns": t.Columns.Count,
                    "markdown": self._table_to_markdown(t),
                }
        except Exception:
            pass
        try:
            if shape.HasChart:
                info["has_chart"] = True
        except Exception:
            pass

        return info

    @staticmethod
    def _shape_tag(shape, key: str) -> Optional[str]:
        try:
            value = shape.Tags.Item(key)
            if value:
                return str(value)
        except Exception:
            return None
        return None

    @staticmethod
    def _extract_blueprint(slide) -> List[Dict[str, Any]]:
        """Read the blueprint layer declarations stored on slide.Tags.

        Mirrors ``SlideRenderer._save_blueprint``: the JSON payload is split
        into ``useit_blueprint_<i>`` chunks with the count in
        ``useit_blueprint_n``.
        """
        try:
            n_str = slide.Tags("useit_blueprint_n") or ""
        except Exception:
            return []
        if not n_str:
            return []
        try:
            n = int(n_str)
        except Exception:
            return []
        parts: List[str] = []
        for i in range(n):
            try:
                parts.append(slide.Tags(f"useit_blueprint_{i}") or "")
            except Exception:
                return []
        payload = "".join(parts)
        if not payload:
            return []
        try:
            data = json.loads(payload)
        except Exception:
            return []
        return data if isinstance(data, list) else []

    def _extract_layer_metadata(
        self,
        shape,
        handle_id: Optional[str],
    ) -> Dict[str, Any]:
        layer_id = self._shape_tag(shape, "useit_layer_id")
        layer_role = self._shape_tag(shape, "useit_layer_role")
        render_as = self._shape_tag(shape, "useit_render_as")
        layer_z_raw = self._shape_tag(shape, "useit_layer_z")

        if not layer_id and handle_id and "." in handle_id:
            layer_id = handle_id.split(".", 1)[0] or None

        layer_z: Any = layer_z_raw
        if layer_z_raw is not None:
            try:
                layer_z = int(float(layer_z_raw))
            except (TypeError, ValueError):
                layer_z = layer_z_raw

        return {
            "layer_id": layer_id,
            "layer_role": layer_role,
            "render_as": render_as,
            "layer_z": layer_z,
        }

    @staticmethod
    def _extract_text_runs(shape) -> Optional[List[Dict]]:
        """Detect per-character font formatting and return runs if mixed.

        Scans characters of the text range. Adjacent characters with the
        same (color, bold, italic, size) are merged into one run.
        Returns a list of run dicts, or ``None`` if all characters share
        the same formatting (i.e. not mixed).

        Each run: ``{"text": "...", "font_color": "#RRGGBB",
        "font_bold": bool, "font_size": float}``
        """
        try:
            tr = shape.TextFrame.TextRange
            total = len(tr.Text)
            if total == 0:
                return None

            runs: List[Dict] = []
            prev_key = None
            seg_start = 1  # COM is 1-based
            max_chars = min(total, 500)  # cap to avoid perf issues

            for ci in range(1, max_chars + 1):
                c = tr.Characters(ci, 1)
                font = c.Font
                try:
                    rgb = font.Color.RGB
                    color_hex = color_int_to_hex(rgb)
                except Exception:
                    color_hex = None
                try:
                    bold = bool(font.Bold) if font.Bold != -2 else None
                except Exception:
                    bold = None
                try:
                    size = font.Size if font.Size > 0 else None
                except Exception:
                    size = None

                key = (color_hex, bold, size)
                if key != prev_key:
                    if prev_key is not None:
                        seg_text = tr.Characters(seg_start, ci - seg_start).Text
                        run: Dict[str, Any] = {"text": seg_text}
                        if prev_key[0]:
                            run["font_color"] = prev_key[0]
                        if prev_key[1] is not None:
                            run["font_bold"] = prev_key[1]
                        if prev_key[2] is not None:
                            run["font_size"] = prev_key[2]
                        runs.append(run)
                    prev_key = key
                    seg_start = ci

            # Final segment
            if prev_key is not None:
                seg_text = tr.Characters(seg_start, max_chars - seg_start + 1).Text
                run = {"text": seg_text}
                if prev_key[0]:
                    run["font_color"] = prev_key[0]
                if prev_key[1] is not None:
                    run["font_bold"] = prev_key[1]
                if prev_key[2] is not None:
                    run["font_size"] = prev_key[2]
                runs.append(run)

            # Only return if there are multiple distinct runs
            if len(runs) > 1:
                return runs
            return None
        except Exception:
            return None

    @staticmethod
    def _extract_gradient(fill_obj) -> Optional[Dict]:
        """Extract gradient info from a COM FillFormat object into a dict.

        Returns a dict like::
            {"type": "linear", "angle": 45,
             "stops": [{"position": 0, "color": "#FF4D00", "opacity": 1.0}, ...]}

        GradientStops may be inaccessible on TextFrame2 Font.Fill for mixed
        ranges; in that case returns partial info (type + angle, no stops).
        """
        result: Dict[str, Any] = {}

        grad_type = "linear"
        try:
            if fill_obj.GradientStyle == 7:  # msoGradientFromCenter
                grad_type = "radial"
        except Exception:
            pass
        result["type"] = grad_type

        if grad_type == "linear":
            try:
                result["angle"] = round(fill_obj.GradientAngle, 1)
            except Exception:
                pass

        try:
            gs = fill_obj.GradientStops
            stops = []
            for i in range(1, gs.Count + 1):
                stop = gs(i)
                stops.append({
                    "position": round(stop.Position, 3),
                    "color": color_int_to_hex(stop.Color.RGB),
                    "opacity": round(1.0 - stop.Transparency, 2),
                })
            result["stops"] = stops
        except Exception:
            pass

        return result if result.get("type") else None

    def _table_to_markdown(self, table, max_rows: int = 20) -> str:
        """
        将 COM Table 对象转为 markdown 表格字符串。

        Args:
            table: COM Table object
            max_rows: 最大行数（防止超大表格爆 token）
        """
        try:
            num_rows = min(table.Rows.Count, max_rows)
            num_cols = table.Columns.Count

            rows: List[List[str]] = []
            for r in range(1, num_rows + 1):
                row: List[str] = []
                for c in range(1, num_cols + 1):
                    try:
                        cell_text = table.Cell(r, c).Shape.TextFrame.TextRange.Text.strip()
                        cell_text = cell_text.replace("|", "\\|").replace("\n", " ")
                        row.append(cell_text[:80])
                    except Exception:
                        row.append("")
                rows.append(row)

            if not rows:
                return ""

            lines: List[str] = []
            lines.append("| " + " | ".join(rows[0]) + " |")
            lines.append("| " + " | ".join("---" for _ in rows[0]) + " |")
            for row in rows[1:]:
                lines.append("| " + " | ".join(row) + " |")

            if table.Rows.Count > max_rows:
                lines.append(f"| ... ({table.Rows.Count - max_rows} more rows) |")

            return "\n".join(lines)
        except Exception as e:
            logger.warning(f"[SnapshotExtractor] table_to_markdown failed: {e}")
            return ""

    def _collect_slide_texts(self, slide) -> List[str]:
        """收集幻灯片上所有文本框的文字内容（用于 all_slides_summary）"""
        texts: List[str] = []
        try:
            for i in range(1, slide.Shapes.Count + 1):
                shape = slide.Shapes(i)
                try:
                    if shape.HasTable:
                        md = self._table_to_markdown(shape.Table)
                        if md:
                            texts.append(md)
                        continue
                except Exception:
                    pass
                try:
                    if shape.HasTextFrame and shape.TextFrame.HasText:
                        text = shape.TextFrame.TextRange.Text.strip()
                        if text:
                            texts.append(text)
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"[SnapshotExtractor] _collect_slide_texts failed: {e}")
        return texts

    def _get_slide_title(self, slide) -> Optional[str]:
        """获取幻灯片标题"""
        try:
            if slide.Shapes.HasTitle:
                title_shape = slide.Shapes.Title
                if title_shape.HasTextFrame:
                    return title_shape.TextFrame.TextRange.Text.strip()
        except Exception:
            pass

        try:
            for i in range(1, slide.Shapes.Count + 1):
                shape = slide.Shapes(i)
                if shape.HasTextFrame:
                    text = shape.TextFrame.TextRange.Text.strip()
                    if text:
                        return text[:100]
        except Exception:
            pass

        return None

    # ==================== Screenshot ====================

    def take_screenshot(self, app, pres) -> Optional[str]:
        """
        截取 PowerPoint 窗口截图。

        走共享的 `capture_hwnd_image`：PrintWindow / ImageGrab 混合策略，
        **不抢用户焦点**。用户如果正在 Word 里打字，这次截图不会打断。
        """
        try:
            import win32gui
            from controllers.system.window_handler import capture_hwnd_image
            from controllers.computer_use.win_executor.handlers.image_utils import (
                compress_screenshot_from_pil,
            )

            hwnd = None

            def find_ppt_window(hwnd_candidate, _):
                nonlocal hwnd
                try:
                    title = win32gui.GetWindowText(hwnd_candidate)
                    if "PowerPoint" in title and win32gui.IsWindowVisible(hwnd_candidate):
                        hwnd = hwnd_candidate
                        return False
                except Exception:
                    pass
                return True

            win32gui.EnumWindows(find_ppt_window, None)

            if not hwnd:
                try:
                    hwnd = int(app.HWND)
                except Exception:
                    pass

            if not hwnd:
                logger.warning("[SnapshotExtractor] Could not find PowerPoint window handle")
                return None

            # prefer_printwindow=False：PPT 一般是前台可见的，ImageGrab 质量更好；
            # 被遮挡时会自动回退 PrintWindow。全程不会 SetForegroundWindow。
            img = capture_hwnd_image(hwnd, prefer_printwindow=False)
            if img is None:
                logger.warning("[SnapshotExtractor] capture_hwnd_image returned None")
                return None

            original_size = f"{img.width}x{img.height}"
            compressed_bytes = compress_screenshot_from_pil(img)
            base64_str = base64.b64encode(compressed_bytes).decode("utf-8")

            logger.info(
                f"[SnapshotExtractor] Screenshot captured: {original_size}, "
                f"compressed to {len(compressed_bytes) / 1024:.1f}KB"
            )
            return base64_str

        except Exception as e:
            logger.warning(f"[SnapshotExtractor] Screenshot failed: {e}", exc_info=True)
            return None
