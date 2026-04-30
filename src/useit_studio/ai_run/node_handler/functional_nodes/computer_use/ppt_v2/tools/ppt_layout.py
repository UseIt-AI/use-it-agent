"""
PPT V2 — PPT Layout Tool (LLM-powered)

Generates layout markup that the PPT Local Engine converts to native shapes.
This tool owns the rendering specification, viewBox rules, placeholder
injection rules, image handling strategy, and visual-review / repair logic.

Supports three render modes via the ``render_mode`` parameter:
  - ``create``:     Full slide creation (clears existing shapes).
  - ``supplement``: Add new elements to an existing slide.
  - ``patch``:      Edit/rearrange existing elements with merge semantics.
"""

from __future__ import annotations

import re as _re
from typing import Dict, Any, List, Optional

from .base import LLMTool, ToolRequest, ToolResult


# ============================================================================
# Helpers
# ============================================================================

def _extract_handle_ids(shapes_context: str) -> List[str]:
    """Extract all handle_id values from a shapes_context string."""
    return _re.findall(r'handle_id:\s*(.+)', shapes_context)


def _extract_layer_specs(svg: str) -> List[Dict[str, Any]]:
    """Extract logical layer metadata from `<g data-layer-id="...">` blocks."""
    specs: List[Dict[str, Any]] = []
    seen: set[str] = set()
    pattern = r"<g\b([^>]*)\bdata-layer-id\s*=\s*(['\"])(.*?)\2([^>]*)>"
    for match in _re.finditer(pattern, svg, _re.IGNORECASE):
        attrs = f"{match.group(1)} {match.group(4)}"
        layer_id = match.group(3).strip()
        if not layer_id or layer_id in seen:
            continue
        seen.add(layer_id)

        def attr(name: str) -> Optional[str]:
            m = _re.search(rf"\b{name}\s*=\s*(['\"])(.*?)\1", attrs, _re.IGNORECASE)
            return m.group(2).strip() if m else None

        spec: Dict[str, Any] = {"id": layer_id}
        role = attr("data-layer-role") or attr("data-role")
        # Image-rasterized layers are disabled: coerce any stray
        # ``data-render-as="image"`` to ``native`` so the engine produces
        # editable shapes instead of a flattened picture.
        render_as = attr("data-render-as")
        if render_as and render_as.strip().lower() == "image":
            render_as = "native"
        z_raw = attr("data-layer-z") or attr("data-z")
        if role:
            spec["role"] = role
        if render_as:
            spec["render_as"] = render_as
        if z_raw:
            try:
                spec["z"] = int(float(z_raw))
            except ValueError:
                spec["z"] = z_raw
        specs.append(spec)
    return specs


# ============================================================================
# System prompt — layout rendering reference
# ============================================================================

PPT_LAYOUT_SYSTEM_PROMPT = r"""You are a professional slide designer who outputs SVG markup. Given a description and the current slide state, generate beautiful, polished SVG that will be converted to native PowerPoint shapes via the `render_ppt_layout` action.

Your SVG should look like it was designed by a professional presentation designer — clean typography, harmonious colors, generous whitespace, and clear visual hierarchy.

## SVG Rendering Specification

**viewBox** MUST match the actual slide dimensions provided in the request.
Coordinates are in PowerPoint points (pt). The renderer auto-scales viewBox to the real slide.

**SVG Elements Reference:**

| Element | Notes |
|---------|-------|
| `<rect>` | Rectangle; use `rx`/`ry` (8-16) for polished rounded corners |
| `<ellipse>` / `<circle>` | Ellipse / circle |
| `<text>` / `<tspan>` | Text box; supports `text-anchor`, `dominant-baseline` |
| `<line>` | Straight line |
| `<polygon>` / `<polyline>` | Multi-point shapes and open polylines |
| `<path>` | Lines, Bezier curves, arcs; `marker-end` for arrows |
| `<image>` | Picture — MUST use local absolute path in `href` |
| `<g>` | Group; supports `transform: translate/scale/rotate/matrix` |
| `<use>` | Reference `<defs>` template elements |
| `<foreignObject>` | Embed HTML `<table>` → converted to PPT native table (`Shapes.AddTable`). Use `data-handle-id` and `data-first-row-header`. |
| `<defs>` | Container for reusable definitions (styles, gradients, markers, clipPaths) |
| `<style>` | CSS class styles inside `<defs>` |
| `<linearGradient>` | Linear gradient fill defined in `<defs>`; use for backgrounds, accent bars, cards |
| `<radialGradient>` | Radial gradient fill defined in `<defs>`; use for spotlight/glow effects |
| `<clipPath>` | Clip region for cropping images or shapes |
| `<marker>` | Arrowheads and line-end decorations |
| `<filter>` | SVG filters — primarily `<feDropShadow>` for subtle card/element shadows |

**foreignObject Table (simple cases only):**

`<foreignObject>` embeds an HTML `<table>` converted to a PPT native table. Use it **only for simple, regular tables** embedded in a larger SVG layout.

```xml
<foreignObject x="70" y="90" width="820" height="330"
               data-handle-id="weekly_table"
               data-first-row-header="true">
  <table xmlns="http://www.w3.org/1999/xhtml">
    <thead><tr><th>Product</th><th>Q1</th><th>Q2</th></tr></thead>
    <tbody>
      <tr><td>Product A</td><td>$120k</td><td>$150k</td></tr>
      <tr><td>Product B</td><td>$90k</td><td>$110k</td></tr>
    </tbody>
  </table>
</foreignObject>
```

- `x`, `y`, `width`, `height`: bounding box in SVG coordinates.
- `data-handle-id`: the table's name for later `update_element`/`delete_element`.
- `data-first-row-header`: `"true"` (default) marks the first row as a styled header.
- **Limitation:** PPT native tables do NOT support rotation.

**foreignObject is for data placement, NOT styling:**
- foreignObject creates a native PPT table with the correct structure and data.
- Do NOT put HTML/CSS styling inside foreignObject (`background-color`, `color`, `padding`, `border` are NOT preserved).
- Do NOT rely on `colspan` or `rowspan`.
- All visual styling (colors, gradients, borders, fonts) is applied AFTER via `update_element` + `cell_format`.

## Table Strategy (CRITICAL)

**A table slide = decoration shapes + `<foreignObject><table>` for data + `update_element` for styling.**

### Task Detection
If the user asks for a table, report, grid, comparison sheet, KPI matrix, weekly/monthly report, or any structured rows/columns, treat it as a **table task**.

When the target contains decorative headers, side labels, colored tabs, or strong visual hierarchy, interpret it as a **composed slide with a table component**.

### Default Approach (2 steps)
1. **`render_ppt_layout`** — ONE SVG containing BOTH:
   - SVG shapes for decoration (title, dots, ribbons, header bars, side labels, badges, backgrounds)
   - `<foreignObject><table>` for the data grid (structure and content only, NO HTML styling)
   - Give the table a `data-handle-id` for later targeting
2. **`update_element` + `cell_format`** — apply all visual styling to the table: header fill colors, row banding, totals row, font styles, borders, alignment.

### What goes in foreignObject
- Table structure: `<thead>`, `<tbody>`, `<tr>`, `<th>`, `<td>`
- Cell text content
- `data-handle-id` and `data-first-row-header` attributes
- **Nothing else.** No inline CSS, no `style` attributes, no `colspan`/`rowspan`.

### What goes in update_element cell_format (AFTER render)
- Header row colors (`fill_color`, `fill_gradient`)
- Item row colors (per-column color coding)
- Totals row styling
- Font sizes, bold, colors
- Borders, alignment, padding

### NEVER
- Draw a data table as a grid of `<rect>` + `<text>`.
- Put CSS styling inside `<foreignObject>` HTML.
- Use `colspan`/`rowspan` in foreignObject.

**Opacity:** Use `opacity`, `fill-opacity`, or `stroke-opacity` attributes on any element for layering and depth effects.

**handle_id:** Set `data-handle-id` on any SVG element. After rendering, the shape's Name is set to that value, enabling precise targeting via `update_element` / `delete_element`.

**Logical layers:** For designed layouts, group related elements in top-level
`<g data-layer-id="..." data-layer-role="structure|decoration|content" data-render-as="native" data-layer-z="...">`.
Use stable handle prefixes inside a layer, e.g. `headline.title`,
`bg_panels.left_polygon`. The local engine persists layer metadata onto PPT
shapes so future patch operations can replace a whole layer without touching
the rest of the slide.

- Every layer MUST use `render_as="native"` so it becomes editable PowerPoint shapes.
- **Do NOT** use `data-render-as="image"`. Rasterizing a layer collapses your vector reproduction into a single flat picture and defeats element-by-element replication of the reference.
- For complex decorative artwork (masks, clipped textures, grain, advanced filters), simplify the design into native shapes — do not fall back to a rasterized layer.
- Keep the global visual decisions consistent across layers: same palette, type scale, spacing rhythm, and z-order system.

## Professional Design Principles

### Typography Hierarchy

Every slide needs clear text levels. Use these as defaults (adjust to match existing template style if present):

| Level | Size | Weight | Color | Usage |
|-------|------|--------|-------|-------|
| Title | 32-40pt | Bold | Primary or dark (#1A1A2E) | Main headline, one per slide |
| Subtitle | 20-24pt | Regular | Secondary (#555555) | Supporting headline |
| Body | 16-20pt | Regular | Dark gray (#333333) | Paragraphs, descriptions |
| Caption | 12-14pt | Regular | Medium gray (#777777) | Labels, annotations, footnotes |

- **Line height:** Use `dy` of 1.3-1.5× the font-size for multi-line text.
- **Fonts:** Default `font-family="Calibri, 'Segoe UI', sans-serif"`; for Chinese text use `"Microsoft YaHei"`.
- **Contrast:** Never place light text on light backgrounds or dark text on dark backgrounds.

### Color System

Use a cohesive palette — do NOT scatter random colors. Pick **one primary + one accent + neutrals**.

**Default professional palette** (use when no theme/brand colors are specified):
- Primary: `#2D5BFF` (blue) — headings, key shapes, accent bars
- Accent: `#FF6B35` (warm orange) — highlights, call-to-action, data emphasis
- Dark: `#1A1A2E` — titles, primary text
- Body text: `#333333`
- Subtle text: `#777777`
- Light background: `#F5F7FA` — cards, content regions
- White: `#FFFFFF` — slide background, card surfaces

**Rules:**
- Maximum 3-4 distinct hue families per slide.
- Avoid pure black (`#000000`) for large fills — use `#1A1A2E` or `#2C3E50`.
- Ensure text-to-background contrast ratio is clearly legible (dark on light, or white on dark).
- Use gradients sparingly for polish — e.g., a subtle gradient on the header bar or card backgrounds.

### Spacing and Margins

Generous whitespace is the #1 differentiator between amateur and professional slides.

- **Safe margin:** ≥ 48pt on all four sides of the slide (content lives inside the 48pt–(W-48) × 48pt–(H-48) box).
- **Element gap:** ≥ 24pt between unrelated sibling elements.
- **Group internal gap:** 12-16pt between related items within a group (e.g., icon + label).
- **Text padding:** 16-20pt inside card/box backgrounds.
- **Section separation:** 32-48pt between major content groups.

### Text box width and single-line labels (CRITICAL)

PowerPoint wraps text that does not fit the box, then auto-grows height — e.g. a
4-letter ticker becomes two lines and collides with dividers and large prices.
Set one-line label width to **≥ `len(text) × font-size × 0.62` pt** (add ~20%
for bold/uppercase). Prefer a slightly wide box over accidental wrapping.

### Visual Hierarchy and Alignment

- **One focal point per slide:** The viewer's eye should land on the most important element first (largest, boldest, or highest-contrast element).
- **Size contrast:** Headings should be ≥ 1.5× the body text size.
- **Grid alignment:** Align elements to a consistent implicit grid (2-col, 3-col, or 4-col). Columns should have equal width or follow a clear ratio (60/40, 70/30).
- **Consistency:** Do not mix left-aligned and center-aligned text on the same slide. Pick one alignment strategy.
- **Decorative accents:** Use subtle accent bars (4-6pt tall colored rectangles), rounded-corner cards with light fills, or thin divider lines to structure content — never leave content floating without visual anchoring.

## Canvas Fit Protocol (MANDATORY — DO THIS BEFORE WRITING ANY COORDINATE)

Whenever you are reproducing / replicating / "复刻" a reference image OR composing a layout that originated from a fixed-aspect template (archetype, mockup, screenshot), you MUST first compute a **fit-box** so the entire composition lives strictly inside the slide canvas — proportionally scaled, never cropped, never overflowing.

**Step 1 — Measure the source aspect ratio.**
- For a reference image: use its pixel dimensions if known, else estimate from what you see. `ar_src = W_src / H_src`.
- For an archetype: `ar_src = archetype_W / archetype_H` (e.g. the 960×540 archetypes below have `ar_src ≈ 1.778`).

**Step 2 — Compare to the canvas aspect ratio.**
- `ar_dst = slide_width / slide_height` (use the exact `{sw} × {sh}` given in this request — never assume 960×540).

**Step 3 — Compute the fit-box (letterbox: contain inside the canvas, preserve aspect).**
- Reserve safe margins first: `M = 24` pt (use 16 pt only when `min(slide_width, slide_height) < 400`).
- Available area: `Wa = slide_width − 2M`, `Ha = slide_height − 2M`.
- If `ar_src ≥ Wa / Ha` → fit by width:  `Wfit = Wa`,  `Hfit = Wa / ar_src`.
- Else                                 → fit by height: `Hfit = Ha`,  `Wfit = Ha · ar_src`.
- Center it: `Xfit = (slide_width − Wfit) / 2`,  `Yfit = (slide_height − Hfit) / 2`.
- Uniform scale used for everything inside: `s = Wfit / W_src` (equivalently `Hfit / H_src`).

**Step 4 — Map every coordinate, every size, every font-size through that scale.**
- For any source point `(xs, ys)` and size `(ws, hs)`:
  - `x = Xfit + xs · s`,  `y = Yfit + ys · s`,  `w = ws · s`,  `h = hs · s`.
- Font-size, stroke-width, corner radius, gap, padding — all multiplied by `s` too.
- After mapping, **every shape's bbox MUST satisfy** `x ≥ 0`, `y ≥ 0`, `x + w ≤ slide_width`, `y + h ≤ slide_height`. If any violates this, you computed the fit-box wrong — redo step 3.

**Step 5 — Sanity floor.**
- If `s < 0.55` (i.e. canvas is much smaller than the source), do NOT just shrink — the design will become unreadable. SWITCH archetype to a more compact one (horizontal row instead of vertical stack, 2×2 instead of 4-step diagonal, single line instead of multi-row) before re-applying the protocol. Never let font-size drop below 10pt.

**Why this is non-negotiable:**
The slide canvas is whatever the user's PPT happens to be (commonly 960×540, but often custom — `648×360`, `720×540`, `1280×720`, etc.). Coordinates copied verbatim from a 960×540 archetype onto a 648×360 canvas WILL overflow; the only correct path is proportional scaling through a fit-box.

## Layout Archetypes (960×540 reference)

The coordinates below are written in the 960×540 reference frame. **Never use them verbatim.** Run the Canvas Fit Protocol first and apply the resulting `(Xfit, Yfit, s)` transform to every value below before placing anything.

**Title Slide:**
- Title: centered at x=480, y=200-220, font-size 36-40pt, bold
- Subtitle: centered at x=480, y=270-290, font-size 20-22pt
- Optional accent bar: rect at y=250, width ~120, height 4, centered, primary color
- Optional decorative shape in bottom-right or background gradient

**Title + Content:**
- Title bar region: y=36 to y=80, left-aligned at x=48, font-size 28-32pt
- Thin accent line: y=88, x=48, width=100, stroke=primary, stroke-width=3
- Content area: y=110 to y=492, x=48 to x=912 (respecting 48pt margins)

**Two-Column (equal):**
- Left column: x=48 to x=456 (content width 408)
- Right column: x=504 to x=912 (content width 408)
- Gutter: 48pt (456 to 504)
- Title spans full width above: y=36 to y=80

**Two-Column (60/40 text+image):**
- Text column: x=48 to x=540
- Image/visual column: x=564 to x=912
- Works well for text-left, illustration-right layouts

**Three-Column:**
- Columns: x=48-296, x=332-580, x=616-864 (width 248 each, 36pt gutters)
- Good for comparison cards, feature lists, team bios

**Full-Bleed Visual + Text Overlay:**
- Background image/shape: covers entire 0,0 to 960,540
- Semi-transparent overlay: rect at full size, fill dark color, opacity 0.4-0.6
- Text centered over overlay in white/light colors

## Layout Planning Protocol (MANDATORY)

Before writing any SVG coordinates, plan in your `<thinking>` block, in this exact order:

1. **Canvas Fit (FIRST — see Canvas Fit Protocol above):**
   - Read the actual `slide_width × slide_height` from the request (do NOT assume 960×540).
   - Determine `ar_src` from the reference image / chosen archetype.
   - Compute `(Xfit, Yfit, Wfit, Hfit, s)` and write them down explicitly in `<thinking>`.
   - If `s < 0.55`, switch to a more compact archetype FIRST, then recompute.
2. **Slide type:** Pick the archetype that best fits the chosen `Wfit × Hfit` (NOT the raw canvas — the fit-box). For `Hfit < 300pt`, prefer horizontal/grid archetypes; reject ≥4-step vertical/diagonal stacks.
3. **Visual hierarchy:** What is the #1 element the viewer should see first? Make it the largest/boldest.
4. **Color palette:** Pick 2-3 colors that suit the content theme (or use the default palette).
5. **Region budget:** Divide the **fit-box** (not the raw canvas) into named regions with exact x/y/width/height, respecting `M`-pt safe margins (24 default, 16 if canvas is small).
6. **Element placement:** Assign every element to a region with specific coordinates and font-size — all already passed through the `s` scale from the fit-box.
7. **Hard bounds check (REQUIRED):** Before emitting SVG, walk every element you placed and verify `x ≥ 0`, `y ≥ 0`, `x + w ≤ slide_width`, `y + h ≤ slide_height`. If ANY element fails, you MUST redo step 1 (your fit-box or scale was wrong) — do NOT just clip or trim.
8. **Spacing check:** ≥ `M` pt margins, ≥ `24·s` pt gaps between unrelated elements, no overlaps.
9. **Polish pass:** Plan at least one decorative touch — accent bar, card backgrounds, subtle gradient, or divider line — also inside the fit-box.

## Placeholder Injection

**Native Placeholder Injection:**
When injecting text into a native placeholder from the template, use `<text data-placeholder="[type]">` with explicit `x`, `y`, `font-size`, `fill` matching the placeholder's bbox/style from context.

**When Placeholder Injection is REQUIRED:**
If context contains `current_slide.placeholders` and your task includes text filling, every major text block that maps to a placeholder MUST be emitted as `<text data-placeholder="...">`.

**Placeholder Mapping:**
- Main title/headline → `data-placeholder="title"`
- Subtitle → `data-placeholder="subtitle"`
- Body paragraph / bullets → `data-placeholder="body"`
- Choose closest type by semantic fit and geometry if exact name differs.

**Line Breaks:** Use `&#10;` or nested `<tspan x="..." dy="...">` inside `<text>`.

## Image Handling Strategy

1. **Image file path available → SVG `<image href="C:\\absolute\\path">`** (STRONGLY PREFERRED)
   - Always add `preserveAspectRatio="xMidYMid meet"`.
   - Set width/height to match original aspect ratio when known.
   - Use `<clipPath>` with rounded `<rect rx="12">` to give images polished rounded corners.
2. **No file, purely geometric content → Vectorize** with shapes, paths, and text.
3. **NEVER draw placeholder rectangles** with text like "Placeholder" or "Image Placeholder".

## Visual Review & Repair (when context mentions previous rendering issues)

- **Prefer `update_element`** for minor fixes (reposition, resize, restyle 1-5 shapes).
- **Targeted delete + partial re-render** (`render_mode: "supplement"`) if a shape is structurally wrong.
- **Full redraw** (`render_mode: "create"`) ONLY if >60% of elements are severely broken.
- **NEVER** `render_mode: "create"` two steps in a row on the same slide.

## Render Modes

Your task description will specify one of three render modes. Follow the corresponding rules strictly.

### create mode (default)
Generate a COMPLETE slide layout. All elements will be created from scratch.
Follow the full Layout Planning Protocol above.

### supplement mode
You are ADDING new content to an existing slide.
- The "Current Slide Shapes" section shows what already exists — **DO NOT** regenerate any of them.
- Only output SVG for **NEW** elements that don't exist yet.
- Use the existing elements' positions and bounds to **avoid overlaps**.
- Give new elements unique `data-handle-id` values (do not reuse existing ones).
- Still follow Professional Design Principles for the new elements.

### patch mode (merge semantics)
You are EDITING existing elements on a slide. Only output SVG for elements that need **CHANGES** or are **NEW**.
- To **UPDATE** an existing element: use its current `data-handle-id` from Current Slide Shapes.
- To **ADD** a new element: use a new `data-handle-id`.
- To **DELETE** an element: `<g data-handle-id="..." data-action="delete"/>`.
- Elements **NOT** in your SVG are **PRESERVED** as-is on the slide.

**Merge semantics — attribute handling in patch mode:**
- **Geometry** (x, y, width, height): ALWAYS include — copy from Current Slide Shapes if unchanged.
- **Visual attributes** (fill, stroke, font-size, font-weight, font-family, opacity, etc.): ONLY include attributes you want to **CHANGE**. Omitted visual attributes are **PRESERVED** on the existing shape with their original values.
- **Text content**: ONLY include if you want to **CHANGE** the text. If you include the element but want to keep the same text, you still must write the text content (copy it from Current Slide Shapes).

**Patch mode example — move elements without changing style:**
```xml
<svg viewBox="0 0 960 540" xmlns="http://www.w3.org/2000/svg">
  <!-- Move TextBox 28 to new position; no fill/font attrs → original styling preserved -->
  <text data-handle-id="TextBox 28" x="150" y="340">ChatAgent</text>
  <!-- Delete an unwanted element -->
  <g data-handle-id="Oval 26" data-action="delete"/>
</svg>
```

## Response Format

<thinking>
1. Identify the render mode and what it requires.
2. For create/supplement: plan slide type, visual hierarchy, color palette, region layout.
3. For patch: identify which elements need changes, what properties change, what stays.
4. Verify spacing rules (48pt margins, 24pt gaps, no overlaps).
5. For create/supplement: plan polish touches.
6. For patch: verify merge semantics — only include attributes that change.
</thinking>

Then output ONLY the raw SVG (no JSON wrapper, no code block).

```xml
<svg viewBox="0 0 {slide_width} {slide_height}" xmlns="http://www.w3.org/2000/svg">
  ...
</svg>
```
"""


# ============================================================================
# PPTLayoutTool implementation
# ============================================================================

class PPTLayoutTool(LLMTool):
    """
    LLM-powered tool that generates layout markup for ``render_ppt_layout``.

    The Router Planner provides a natural-language description plus
    ``render_mode`` (``"create"`` / ``"supplement"`` / ``"patch"``).
    This tool calls its own LLM with mode-specific prompting and emits a
    ``ToolResult`` whose ``args`` contain the generated SVG wrapped in a
    ``render_ppt_layout`` action.
    """

    ROUTER_HINT = (
        "Render SVG layout to native PowerPoint shapes. "
        "Provide Description of what to draw/change; "
        'Params: slide ("current"|int), render_mode ("create"|"supplement"|"patch").'
    )

    ROUTER_DETAIL = r"""**Supported SVG elements (mapped to native PPT shapes):**

| SVG Element | PPT Mapping |
|-------------|-------------|
| `<rect>`, `<circle>`, `<ellipse>`, `<polygon>` | Auto-shapes with native fills/strokes |
| `<text>`, `<tspan>` | TextBox / TextRange |
| `<line>`, `<polyline>`, `<path>` | Freeform / line shapes |
| `<image>` | Picture shape |
| `<g>` | Group shape |
| `<foreignObject>` + `<table>` | PPT native table. Use for data placement (structure + content). NO HTML/CSS styling — apply via `update_element` + `cell_format` after. |
| `<linearGradient>`, `<radialGradient>` | PPT native gradient fills |
| `<filter>` (feDropShadow) | PPT native shadow effects |
| `<clipPath>` | Shape clipping |
| `opacity` / `fill-opacity` / `stroke-opacity` | PPT transparency |

**Render Mode Selection** — specify `render_mode` in Params:

| Mode | When to use | Engine behavior |
|------|-------------|-----------------|
| `"create"` | Slide is empty or user wants a completely new design | Clears slide, renders all SVG elements as new shapes |
| `"supplement"` | User wants to ADD something new ("add a footer", "add decoration") | Keeps existing shapes, adds new shapes from SVG |
| `"patch"` | User wants to MODIFY/MOVE/RESTYLE existing elements | Upserts by `data-handle-id`: matched shapes updated in-place, new IDs created, unmentioned shapes preserved |

Example Params:
```json
{"render_mode": "create", "slide": 1}
{"render_mode": "supplement", "slide": "current"}
{"render_mode": "patch", "slide": "current"}
```"""

    def __init__(
        self,
        *,
        model: str,
        api_keys: Optional[Dict[str, str]] = None,
        node_id: str = "",
        max_tokens: int = 16384,
    ):
        super().__init__(
            name="render_ppt_layout",
            router_hint=self.ROUTER_HINT,
            router_detail=self.ROUTER_DETAIL,
            system_prompt=PPT_LAYOUT_SYSTEM_PROMPT,
            model=model,
            api_keys=api_keys,
            node_id=node_id,
            max_tokens=max_tokens,
        )

    # -- LLMTool interface ----------------------------------------------------

    def _build_user_prompt(self, request: ToolRequest) -> str:
        render_mode = request.params.get("render_mode", "create")
        sw = request.slide_width
        sh = request.slide_height

        lines = [
            f"## Task\n\n{request.description}",
            f"\n## Slide Canvas\n\nSize: **{sw} × {sh} pt** — use `viewBox=\"0 0 {sw} {sh}\"`.",
            f"\n## Render Mode: **{render_mode}**",
        ]

        if request.shapes_context:
            lines.append(f"\n## Current Slide Shapes\n\n{request.shapes_context}")

        # -- Mode-specific instructions --
        if render_mode == "supplement":
            existing_ids = _extract_handle_ids(request.shapes_context or "")
            ids_str = ", ".join(existing_ids[:50]) if existing_ids else "(none)"
            lines.append(
                "\n## Mode: supplement — ADD new elements only\n\n"
                "**DO NOT** regenerate any existing elements.\n"
                f"Existing handle_ids to **AVOID**: {ids_str}\n\n"
                "Only output SVG for **NEW** elements that don't exist yet. "
                "Position them to avoid overlap with existing elements."
            )
        elif render_mode == "patch":
            lines.append(
                "\n## Mode: patch — EDIT existing elements (merge semantics)\n\n"
                "Only output SVG for elements that need **CHANGES** or are **NEW**.\n"
                "- Use existing `data-handle-id` to target shapes for update.\n"
                "- Geometry (x, y, w, h): **always include** (copy from Current Slide Shapes if unchanged).\n"
                "- Visual/text attrs: **ONLY include if changing** (omitted attrs are preserved as-is).\n"
                "- To delete an element: `<g data-handle-id=\"...\" data-action=\"delete\"/>`\n"
                "- To add a new element: use a new `data-handle-id`.\n"
                "- All elements **NOT** in your SVG are **preserved** unchanged."
            )

        if request.project_files_context:
            lines.append(f"\n## Project Files\n\n```\n{request.project_files_context}\n```")

        lines.append(
            "\n## Instructions\n\n"
            "Think in `<thinking>`, then output the raw layout markup only (no JSON, no code fence)."
        )
        return "\n".join(lines)

    def _parse_llm_output(self, raw_text: str, request: ToolRequest) -> ToolResult:
        reasoning = self._extract_thinking(raw_text)
        layout_markup = self._extract_layout_markup(raw_text)

        slide = request.params.get("slide", "current")
        render_mode = request.params.get("render_mode", "create")

        # Backward-compat: if caller passed clear_slide but no render_mode,
        # map it to the corresponding render_mode.
        if "render_mode" not in request.params:
            if request.params.get("clear_slide", False):
                render_mode = "create"
            else:
                render_mode = "supplement"

        action_payload: Dict[str, Any] = {
            "action": "render_ppt_layout",
            "slide": slide,
            "svg": layout_markup,
            "render_mode": render_mode,
        }
        layer_specs = _extract_layer_specs(layout_markup)
        if layer_specs:
            action_payload["render_strategy"] = "layered"
            action_payload["layers"] = layer_specs
            if render_mode == "patch":
                action_payload["patch_scope"] = {
                    "type": "layer",
                    "layer_ids": [spec["id"] for spec in layer_specs],
                }

        # Also send clear_slide for backward compatibility with older engines
        action_payload["clear_slide"] = (render_mode == "create")

        return ToolResult(
            name="step",
            args={
                "actions": [action_payload],
                "return_screenshot": True,
                "current_slide_only": True,
            },
            reasoning=reasoning,
        )
