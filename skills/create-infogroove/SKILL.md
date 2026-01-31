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
- Tighten layout, spacing, and colors as needed.
- Update `schema` when data shape changes.

## Resources

### scripts/

- `render_infogroove.py`: Render SVG via `uvx infogroove` without requiring a local install.

### references/

- `infogroove-template-guide.md`: Quick reference for the template spec, data shapes, and examples.
