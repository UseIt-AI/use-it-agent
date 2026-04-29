"""
Utility functions for the docling pipeline.
"""

import base64
from pathlib import Path
from typing import List

import fitz  # PyMuPDF


def ensure_dir(path: Path) -> None:
    """Create directory if it doesn't exist."""
    path.mkdir(parents=True, exist_ok=True)


def sanitize_filename(name: str) -> str:
    """Convert a string to a safe filename."""
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in name)
    return safe.strip("_") or "document"


def rect_union(a: fitz.Rect, b: fitz.Rect) -> fitz.Rect:
    """Return the union of two rectangles."""
    return fitz.Rect(
        min(a.x0, b.x0),
        min(a.y0, b.y0),
        max(a.x1, b.x1),
        max(a.y1, b.y1),
    )


def rect_intersection_area(a: fitz.Rect, b: fitz.Rect) -> float:
    """Calculate the intersection area of two rectangles."""
    inter = a & b
    if inter is None or inter.is_empty:
        return 0.0
    return max(0.0, inter.get_area())


def svg_wrap_png(png_bytes: bytes, width: int, height: int) -> str:
    """Wrap PNG bytes in an SVG container."""
    encoded = base64.b64encode(png_bytes).decode("ascii")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">\n'
        f'  <image width="{width}" height="{height}" href="data:image/png;base64,{encoded}"/>\n'
        "</svg>\n"
    )


def save_pixmap(pixmap: fitz.Pixmap, output_path: Path, image_format: str) -> None:
    """Save a pixmap to file in the specified format."""
    if image_format == "png":
        output_path.write_bytes(pixmap.tobytes("png"))
    elif image_format == "svg":
        svg_payload = svg_wrap_png(pixmap.tobytes("png"), pixmap.width, pixmap.height)
        output_path.write_text(svg_payload, encoding="utf-8")
    else:
        raise ValueError(f"Unsupported image format: {image_format}")


def render_region(page: fitz.Page, bbox: fitz.Rect, dpi: int) -> fitz.Pixmap:
    """Render a region of a page to a pixmap."""
    matrix = fitz.Matrix(dpi / 72, dpi / 72)
    return page.get_pixmap(matrix=matrix, clip=bbox, alpha=False)
