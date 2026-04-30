"""Slide renderer package: converts SVG markup into PowerPoint native shapes."""

from .core import SlideRenderer

# Backward-compatible alias
SVGRenderer = SlideRenderer

__all__ = ["SlideRenderer", "SVGRenderer"]
