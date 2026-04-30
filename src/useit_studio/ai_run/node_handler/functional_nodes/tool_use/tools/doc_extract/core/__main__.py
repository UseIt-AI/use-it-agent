"""
Command-line interface for the docling pipeline.
"""

import argparse
import sys
from pathlib import Path

from .pipeline import PDFPipeline, PipelineConfig, PipelineProgress, PipelineStage


def create_progress_printer() -> callable:
    """Create a progress callback that prints to stdout."""
    last_stage = [None]
    
    def print_progress(progress: PipelineProgress):
        # Only print when stage changes or during figure rendering
        if progress.stage != last_stage[0] or progress.stage == PipelineStage.RENDER_FIGURES:
            percentage = progress.percentage
            print(f"[{percentage:5.1f}%] {progress.message}")
            last_stage[0] = progress.stage
    
    return print_progress


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        description="Extract PDF figures using caption-anchored detection.",
        prog="python -m docling",
    )
    parser.add_argument("pdf_path", type=Path, help="Path to input PDF.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("docling_output"),
        help="Output directory for markdown and assets.",
    )
    parser.add_argument("--dpi", type=int, default=200, help="Render DPI for figures.")
    parser.add_argument(
        "--image-format",
        choices=["png", "svg"],
        default="png",
        help="Output format for figures (svg wraps PNG).",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Limit processing to first N pages.",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress progress output.",
    )
    return parser


def main() -> int:
    """Main entry point."""
    parser = build_arg_parser()
    args = parser.parse_args()
    
    if not args.pdf_path.exists():
        print(f"Error: PDF not found: {args.pdf_path}", file=sys.stderr)
        return 1
    
    config = PipelineConfig(
        output_dir=args.output_dir,
        dpi=args.dpi,
        image_format=args.image_format,
        max_pages=args.max_pages,
    )
    
    progress_callback = None if args.quiet else create_progress_printer()
    
    pipeline = PDFPipeline(config=config, progress_callback=progress_callback)
    
    try:
        result = pipeline.process(args.pdf_path)
        
        if not args.quiet:
            print()
            print(f"Markdown saved to: {result.markdown_path}")
            print(f"Figures extracted: {len(result.figures_extracted)}")
            for fig in result.figures_extracted:
                print(f"  - {fig.label}: {fig.caption.text[:50]}...")
        
        return 0
    
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
