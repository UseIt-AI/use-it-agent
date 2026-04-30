"""
PPT V2 — Native Chart Tool (LLM-powered)

Generates the data payload for ``insert_native_chart``.
The LLM decides chart type, data layout, title, and bounding box.
"""

from __future__ import annotations

from typing import Dict, Any, Optional

from .base import LLMTool, ToolRequest, ToolResult


# ============================================================================
# System prompt — chart-specific
# ============================================================================

CHART_SYSTEM_PROMPT = r"""You are a PowerPoint chart specialist. Given a description and slide state, generate the JSON payload for an `insert_native_chart` action.

## Chart Types

`column_clustered` | `column_stacked` | `bar_clustered` | `line` | `line_markers` | `pie` | `area` | `scatter`

## Data Format

A 2D array. First row = column headers, first column = row labels:

```json
[
    ["Category", "Q1", "Q2", "Q3"],
    ["Product A", 120, 150, 180],
    ["Product B", 90, 110, 140]
]
```

## Bounding Box

Position and size in PowerPoint points (pt):

```json
{"x": 100, "y": 100, "w": 500, "h": 300}
```

Ensure the chart fits within the slide dimensions and avoids overlapping existing shapes.

## Response Format

<thinking>
1. Determine the best chart type for the data.
2. Structure the data array.
3. Choose a reasonable bounding box.
</thinking>

```json
{
    "chart_type": "column_clustered",
    "bounding_box": {"x": 100, "y": 100, "w": 500, "h": 300},
    "data": [
        ["Category", "Series1", "Series2"],
        ["A", 10, 20],
        ["B", 30, 40]
    ],
    "title": "Chart Title",
    "handle_id": "my_chart"
}
```
"""


# ============================================================================
# NativeChartTool implementation
# ============================================================================

class NativeChartTool(LLMTool):
    """
    LLM-powered tool that produces ``insert_native_chart`` payloads.

    Better than layout markup for data-driven charts because PowerPoint's native chart
    engine handles axes, legends, and data labels automatically.
    """

    ROUTER_HINT = (
        "Insert a native PowerPoint chart (column, bar, line, pie, scatter, area). "
        "Better than layout rendering for data-driven charts. "
        "Provide Description of chart content and data source."
    )

    def __init__(
        self,
        *,
        model: str,
        api_keys: Optional[Dict[str, str]] = None,
        node_id: str = "",
        max_tokens: int = 8192,
    ):
        super().__init__(
            name="insert_native_chart",
            router_hint=self.ROUTER_HINT,
            system_prompt=CHART_SYSTEM_PROMPT,
            model=model,
            api_keys=api_keys,
            node_id=node_id,
            max_tokens=max_tokens,
        )

    # -- LLMTool interface ----------------------------------------------------

    def _build_user_prompt(self, request: ToolRequest) -> str:
        sw = request.slide_width
        sh = request.slide_height
        lines = [
            f"## Task\n\n{request.description}",
            f"\n## Slide Canvas: {sw} × {sh} pt",
        ]
        if request.shapes_context:
            lines.append(f"\n## Current Slide Shapes\n\n{request.shapes_context}")
        if request.project_files_context:
            lines.append(f"\n## Available Data\n\n```\n{request.project_files_context}\n```")

        lines.append(
            "\nThink in `<thinking>`, then output the chart JSON "
            "in a fenced code block."
        )
        return "\n".join(lines)

    def _parse_llm_output(self, raw_text: str, request: ToolRequest) -> ToolResult:
        reasoning = self._extract_thinking(raw_text)
        chart_json = self._extract_json(raw_text)

        slide = request.params.get("slide", "current")

        action: Dict[str, Any] = {"action": "insert_native_chart", "slide": slide}
        for key in ("chart_type", "bounding_box", "data", "title", "handle_id"):
            if key in chart_json:
                action[key] = chart_json[key]

        return ToolResult(
            name="step",
            args={
                "actions": [action],
                "return_screenshot": True,
                "current_slide_only": True,
            },
            reasoning=reasoning,
        )
