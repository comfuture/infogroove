---
name: create-infogroove
description: Create or update Infogroove infographic templates and sample data files, then render SVG outputs. Use when a user asks to generate/modify infogroove `def.json` + `data.json`, create new infographic directories, or render SVGs from Infogroove templates.
---

# Create Infogroove

## Overview

Create or modify Infogroove template definitions (`def.json`) and data payloads (`data.json`), then render an SVG via `uvx infogroove` using the bundled script.

## Workflow

### 1) Gather requirements

- Identify the infographic intent (chart type, layout, tone, colors).
- Capture the data fields and expected data shape (array of objects or `{ "items": [...] }`).
- Confirm canvas size and any typography or palette constraints.
- Identify which visual attributes should remain user-customizable (for example background, fills, strokes, text colors, and emphasis colors).

### 2) Decide output location

- Default to `./infographics/<slug>/` under the agent's current working directory.
- Use a path-safe, lowercase slug (letters, digits, hyphens) derived from the infographic name.
- If the user provides a specific path or an existing infographic directory, use that instead.

Target files:

- `def.json`
- `data.json`
- `<slug>.svg` (rendered output)

### 3) Author or update `def.json`

- Use the template structure from `references/infogroove-template-guide.md`.
- Always include `properties.canvas.width` and `properties.canvas.height`.
- Treat `properties.canvas` as mandatory and strict:
  - `width` and `height` must be finite positive numbers.
  - Prefer integer values and avoid `0`, negative values, `null`, or strings.
- Compute geometry from the canvas whenever possible:
  - Prefer expressions like `{canvas.width * 0.5}` or `{min(canvas.width, canvas.height) * 0.35}`.
  - Avoid hard-coded absolute geometry in element attributes when a relative value can be used.
  - Move reusable layout constants to named `properties` keys (for example `outerMarginRatio`, `cardGapRatio`), then derive final pixels in `let`.
- Keep style attributes data-driven:
  - Avoid hard-coded `fill`, `stroke`, `strokeWidth`, `fontSize`, and similar values directly in template attributes.
  - Define these as semantically named properties (for example `mainBgColor`, `subBgColor`, `fillColors`, `axisStrokeColor`) and reference them in template placeholders.
- Add a `schema` that matches the intended input data.
- Use `repeat` + `let` to keep element definitions compact.
- When rendering via the CLI, prefer array-shaped schemas (or omit `schema`) because input is normalized to a list.

If editing an existing template, keep prior keys unless the user requests a redesign.

### 4) Author or update `data.json`

- Provide realistic sample data that matches the `schema`.
- If the template expects `{ "items": [...] }`, keep that structure consistent.

### 5) Render SVG

Use the bundled script to render with `uvx`:

```bash
skills/create-infogroove/scripts/render_infogroove.py \
  -f ./infographics/<slug>/def.json \
  -i ./infographics/<slug>/data.json \
  -o ./infographics/<slug>/<slug>.svg
```

- For stdout output, pass `-o -`.
- Re-render after every structural edit to confirm output.

### 6) Validate and iterate

- Ensure the SVG renders and visually matches intent.
- Confirm strict template requirements are still met:
  - `properties.canvas.width` and `properties.canvas.height` exist and are valid numbers.
  - Element geometry is primarily derived from canvas-based expressions.
  - Customizable style values are defined in `properties` and referenced from `template`.
- Tighten layout, spacing, and colors as needed.
- Update `schema` when data shape changes.

## Prerequisites

The rendering script uses `uvx`. If the target system does not have Python or
uv installed, install them first:

- Python: https://docs.astral.sh/uv/guides/install-python/
- uv: https://docs.astral.sh/uv/getting-started/installation/

## Resources

### scripts/

- `render_infogroove.py`: Render SVG via `uvx infogroove` without requiring a local install.

### references/

- `infogroove-template-guide.md`: Strict authoring guide for required canvas settings, relative geometry patterns, style-token conventions, and examples.

### assets/

Example template definitions copied from the repo examples for quick starting points:

- [`blue-parallelograms.json`](assets/blue-parallelograms.json)
- [`key-messages.json`](assets/key-messages.json)
- [`stat-cards.json`](assets/stat-cards.json)
