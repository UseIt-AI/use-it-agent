"""
PPT V2 — Code Execution Tool (LLM-powered)

Generates PowerShell / Python code executed via subprocess.
Used as a fallback when structured actions cannot express the logic.
"""

from __future__ import annotations

import re
from typing import Dict, Any, Optional

from .base import LLMTool, ToolRequest, ToolResult


# ============================================================================
# System prompt — focused on PowerShell / Python via COM
# ============================================================================

CODE_SYSTEM_PROMPT = r"""You are a PowerPoint code-execution specialist. Generate PowerShell (or Python) code that will be executed via subprocess to manipulate the active PowerPoint presentation.

## PowerShell COM Patterns

```powershell
# Connect to PowerPoint
try {
    $ppt = [System.Runtime.InteropServices.Marshal]::GetActiveObject("PowerPoint.Application")
} catch {
    $ppt = New-Object -ComObject PowerPoint.Application
}
$ppt.Visible = $true

# Access active presentation
$presentation = $ppt.ActivePresentation

# Slide access (1-indexed)
$slide = $presentation.Slides(1)
$currentSlide = $ppt.ActiveWindow.View.Slide

# Save
$presentation.Save()
```

## Python COM Patterns

```python
import win32com.client

ppt = win32com.client.GetActiveObject("PowerPoint.Application")
pres = ppt.ActivePresentation
slide = pres.Slides(1)

# Find shape by name
shape = None
for s in slide.Shapes:
    if s.Name == "target_name":
        shape = s
        break
```

## IMPORTANT — Prefer `update_element` over COM code for text formatting

Before writing COM code for text formatting, consider using `update_element` instead:
- **Per-segment formatted text**: `update_element` with `rich_text` property
- **Gradient text**: `rich_text` segments support `fill_gradient`
- **Keyword highlighting**: `update_element` with `text_formats` property
- **Gradient borders**: `update_element` with `line_gradient` property

Only write COM code if the task genuinely requires loops, conditionals, or operations
that `update_element` cannot handle.

## COM API Pitfalls (CRITICAL — read before writing code)

1. **Text gradient/fill — MUST use TextFrame2, NEVER TextFrame:**
   - `shape.TextFrame.TextRange.Font` → OLD `Font` class, NO `.Fill` property.
   - `shape.TextFrame2.TextRange.Font.Fill` → CORRECT (`Font2` with `FillFormat`).
   - Code using `TextFrame.TextRange.Font.Fill` will throw `<unknown>.Fill` silently.

2. **Per-character gradient — late-bound COM often fails:**
   Late-bound CDispatch often fails to resolve `.Font.Fill` on `Characters()` sub-ranges.
   Use early binding: `ppt = win32com.client.gencache.EnsureDispatch("PowerPoint.Application")`
   Or apply to WHOLE text range when possible:
   ```python
   tf2 = shape.TextFrame2
   tr = tf2.TextRange
   tr.Font.Fill.Visible = True
   tr.Font.Fill.TwoColorGradient(1, 1)  # msoGradientHorizontal
   tr.Font.Fill.ForeColor.RGB = 0x004DFF  # #FF4D00 in BGR
   tr.Font.Fill.GradientStops(2).Color.RGB = 0x00D7FF  # #FFD700 in BGR
   ```

3. **Gradient border (Line.Fill) — does NOT exist in COM:**
   `shape.Line.Fill` is not accessible. Use `update_element` with `line_gradient` instead.

4. **Color values in COM are BGR, not RGB:**
   `#FF4D00` → `R + G*256 + B*65536` = `255 + 77*256 + 0*65536` = `0x004DFF`

5. **Per-character solid color (no gradient):**
   ```python
   tr = shape.TextFrame2.TextRange
   part1 = tr.Characters(1, split_pos)       # 1-indexed
   part1.Font.Color.RGB = 0x004DFF           # orange in BGR
   part2 = tr.Characters(split_pos + 1, rest_len)
   part2.Font.Color.RGB = 0xFFFFFF           # white
   ```
   `.Font.Color.RGB` works on both TextFrame and TextFrame2 sub-ranges.

6. **Animations — NEVER write COM animation code:**
   Use the `add_shape_animation` / `clear_slide_animations` structured actions instead.
   They handle all COM constants, Exit flags, and trigger ordering correctly.

## Rules

- Use `$true`/`$false` instead of MsoTriState enums (avoids TypeNotFound errors).
- Use single quotes for string literals containing special characters.
- Always wrap in try-catch for error handling.
- Print a short summary at the end so the agent can read stdout.
- Output MUST be complete, runnable code — no placeholders or TODOs.
- When an operation fails, print the actual error message — do NOT silently swallow exceptions.

## Response Format

<thinking>
1. Understand what needs to be done.
2. Plan the COM operations.
3. Check COM pitfalls above for the APIs involved.
</thinking>

Then output the code in a fenced code block:

```powershell
# Your code here
```

Or for Python:

```python
# Your code here
```
"""


# ============================================================================
# CodeExecutionTool implementation
# ============================================================================

class CodeExecutionTool(LLMTool):
    """
    LLM-powered tool that generates executable PowerShell/Python code.

    The Router Planner supplies a description of what needs to happen;
    this tool's LLM writes the actual code.
    """

    ROUTER_HINT = (
        "Execute PowerShell/Python code via subprocess — last resort for logic not covered by other tools. "
        'Provide Description; optional Params: language ("PowerShell"|"Python"), timeout (int).'
    )

    ROUTER_DETAIL = r"""**Prefer `update_element` for ALL styling operations** (gradient fills, borders, shadows, rich text, text formatting). Only use `execute_code` for conditional logic, loops, or operations no structured tool supports.

**COM API Pitfalls:**

1. **Text gradient fill — use TextFrame2, NOT TextFrame:**
   `shape.TextFrame.TextRange.Font` has NO `.Fill` property.
   Correct: `shape.TextFrame2.TextRange.Font.Fill`.

2. **Gradient border (`Line.Fill`) — NOT accessible via COM:**
   Use `update_element` with `line_gradient` instead.

3. **Color values in COM are BGR, not RGB:**
   `#FF4D00` → `R + G*256 + B*65536` = `255 + 77*256 + 0*65536`

4. **Animations — use `add_shape_animation` instead of code.**
   NEVER write COM animation code. The structured action handles all constants and flags correctly."""

    def __init__(
        self,
        *,
        model: str,
        api_keys: Optional[Dict[str, str]] = None,
        node_id: str = "",
        max_tokens: int = 8192,
    ):
        super().__init__(
            name="execute_code",
            router_hint=self.ROUTER_HINT,
            router_detail=self.ROUTER_DETAIL,
            system_prompt=CODE_SYSTEM_PROMPT,
            model=model,
            api_keys=api_keys,
            node_id=node_id,
            max_tokens=max_tokens,
        )

    # -- LLMTool interface ----------------------------------------------------

    def _build_user_prompt(self, request: ToolRequest) -> str:
        language = request.params.get("language", "PowerShell")
        lines = [
            f"## Task\n\n{request.description}",
            f"\nPreferred language: **{language}**",
        ]
        if request.shapes_context:
            lines.append(f"\n## Current Slide State\n\n{request.shapes_context}")
        if request.project_files_context:
            lines.append(f"\n## Project Files\n\n```\n{request.project_files_context}\n```")

        lines.append(
            "\nThink in `<thinking>`, then output the complete code "
            "in a fenced code block."
        )
        return "\n".join(lines)

    def _parse_llm_output(self, raw_text: str, request: ToolRequest) -> ToolResult:
        reasoning = self._extract_thinking(raw_text)
        code, language = self._extract_code(raw_text, request)

        return ToolResult(
            name="step",
            args={
                "code": code,
                "language": language,
                "return_screenshot": True,
                "current_slide_only": True,
                "timeout": request.params.get("timeout", 120),
            },
            reasoning=reasoning,
        )

    # -- Helpers --------------------------------------------------------------

    @staticmethod
    def _extract_code(text: str, request: ToolRequest) -> tuple[str, str]:
        """Extract code from the first fenced code block and detect language."""
        default_lang = request.params.get("language", "PowerShell")

        m = re.search(
            r"```(\w+)?\s*\n(.*?)```", text, re.DOTALL
        )
        if m:
            detected_lang = (m.group(1) or "").strip().lower()
            code = m.group(2).strip()
            if detected_lang in ("python", "py"):
                return code, "Python"
            if detected_lang in ("powershell", "ps1", "ps"):
                return code, "PowerShell"
            return code, default_lang

        # Fallback: everything after </thinking>
        idx = text.find("</thinking>")
        if idx != -1:
            code = text[idx + len("</thinking>"):].strip()
            if code:
                return code, default_lang

        return text.strip(), default_lang
