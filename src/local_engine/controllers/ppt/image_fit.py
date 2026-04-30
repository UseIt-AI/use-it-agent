"""
根据 SVG preserveAspectRatio 语义与图片原始像素尺寸，计算 PowerPoint AddPicture 的 Left/Top/Width/Height。

- meet：等比缩放以完全落入边界框（与浏览器 SVG 一致），再按 xMin/xMid/xMax 对齐。
- slice：等比缩放以覆盖边界框（cover），再按对齐方式裁切多余部分（通过 PictureFormat.Crop*）。
- none / stretch：铺满边界框（可能变形），与旧版行为一致。
"""

from __future__ import annotations

import logging
import re
from typing import Optional, Tuple

from PIL import Image

logger = logging.getLogger(__name__)

# 对齐系数：min=0, mid=0.5, max=1
_ALIGN = {"min": 0.0, "mid": 0.5, "max": 1.0}


def get_image_pixel_size(path: str) -> Optional[Tuple[float, float]]:
    """读取图片自然宽高（像素）。失败时返回 None。"""
    try:
        with Image.open(path) as im:
            w, h = im.size
            if w <= 0 or h <= 0:
                return None
            return (float(w), float(h))
    except Exception as e:
        logger.warning("[image_fit] Cannot read image dimensions for %s: %s", path, e)
        return None


def _parse_align_token(token: str) -> Tuple[float, float]:
    m = re.match(r"x(?P<x>Min|Mid|Max)y(?P<y>Min|Mid|Max)", token.strip(), re.I)
    if not m:
        return (0.5, 0.5)
    return (_ALIGN[m.group("x").lower()], _ALIGN[m.group("y").lower()])


def parse_preserve_aspect_ratio(attr: Optional[str]) -> Tuple[str, float, float]:
    """
    解析 SVG preserveAspectRatio。

    返回:
        (mode, align_x, align_y)
        mode: "stretch" | "meet" | "slice"
        align_*: 0=min, 0.5=mid, 1=max
    """
    if not attr or not str(attr).strip():
        return ("meet", 0.5, 0.5)

    parts = str(attr).strip().split()
    i = 0
    if i < len(parts) and parts[i].lower() == "defer":
        i += 1
    if i >= len(parts):
        return ("meet", 0.5, 0.5)
    if parts[i].lower() == "none":
        return ("stretch", 0.5, 0.5)

    align_tok = parts[i]
    mode = "meet"
    if i + 1 < len(parts):
        m = parts[i + 1].lower()
        if m == "slice":
            mode = "slice"
        elif m == "meet":
            mode = "meet"

    ax, ay = _parse_align_token(align_tok)
    return (mode, ax, ay)


def compute_picture_rect(
    box_x: float,
    box_y: float,
    box_w: float,
    box_h: float,
    nat_w: float,
    nat_h: float,
    preserve_aspect_ratio: Optional[str],
) -> Tuple[float, float, float, float]:
    """
    计算 AddPicture 使用的矩形（与 SVG 边界框同一坐标系，一般为磅）。

    stretch：返回 (box_x, box_y, box_w, box_h)。
    meet：等比落入框内，按对齐偏移。
    slice：等比覆盖框，矩形可能大于框；调用方需再应用裁切。
    """
    if box_w <= 0 or box_h <= 0:
        return (box_x, box_y, max(box_w, 0.0), max(box_h, 0.0))
    if nat_w <= 0 or nat_h <= 0:
        return (box_x, box_y, box_w, box_h)

    mode, ax, ay = parse_preserve_aspect_ratio(preserve_aspect_ratio)
    if mode == "stretch":
        return (box_x, box_y, box_w, box_h)

    img_ratio = nat_w / nat_h
    box_ratio = box_w / box_h

    if mode == "meet":
        if img_ratio > box_ratio:
            fit_w = box_w
            fit_h = box_w / img_ratio
        else:
            fit_h = box_h
            fit_w = box_h * img_ratio
        left = box_x + (box_w - fit_w) * ax
        top = box_y + (box_h - fit_h) * ay
        return (left, top, fit_w, fit_h)

    # slice — cover
    if img_ratio > box_ratio:
        fit_h = box_h
        fit_w = box_h * img_ratio
    else:
        fit_w = box_w
        fit_h = box_w / img_ratio
    left = box_x + (box_w - fit_w) * ax
    top = box_y + (box_h - fit_h) * ay
    return (left, top, fit_w, fit_h)


def compute_slice_crop_in_points(
    box_x: float,
    box_y: float,
    box_w: float,
    box_h: float,
    left: float,
    top: float,
    fit_w: float,
    fit_h: float,
) -> Tuple[float, float, float, float]:
    """
    slice（cover）模式下，形状放在 (left,top)、尺寸 (fit_w, fit_h)，裁去落在目标框外的部分。

    返回 PictureFormat 的 CropLeft, CropTop, CropRight, CropBottom（磅）。
    """
    crop_l = max(0.0, box_x - left)
    crop_t = max(0.0, box_y - top)
    crop_r = max(0.0, (left + fit_w) - (box_x + box_w))
    crop_b = max(0.0, (top + fit_h) - (box_y + box_h))
    return (crop_l, crop_t, crop_r, crop_b)


def apply_picture_crop_com(shape, crop_l: float, crop_t: float, crop_r: float, crop_b: float) -> None:
    """对 COM Picture 形状设置 Crop（单位与 PowerPoint 一致，一般为磅）。"""
    if crop_l <= 0 and crop_t <= 0 and crop_r <= 0 and crop_b <= 0:
        return
    try:
        pf = shape.PictureFormat
        pf.CropLeft = crop_l
        pf.CropTop = crop_t
        pf.CropRight = crop_r
        pf.CropBottom = crop_b
    except Exception as e:
        logger.warning("[image_fit] Failed to apply crop: %s", e)
