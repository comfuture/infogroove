# Infogroove Architecture Overview

Infogroove turns declarative JSON templates into SVG output. This document
describes the current grammar and renderer pipeline so template authors and
integrators understand how values move from the definition file to the final
graphics.

## Template Structure

Each template is a UTF-8 JSON document. The loader (`loader.load`,
`loader.loads`, or `loader.load_path`) parses the payload into strongly typed
models that the renderer consumes.

- **`properties`** – Required mapping of reusable constants. It must contain
  a `canvas` object with viewport `width` and `height`, and can expose any
  additional values (e.g. `margin`, `palette`, `fontFamily`). Properties are
  injected into the rendering context verbatim, so strings such as
  `"Inter, Arial, sans-serif"` remain literal.
- **`template`** – Ordered list of element descriptors. Each entry provides a
  `type` (rect, text, polygon, path, etc.), an `attributes` dictionary whose
  values may contain placeholders, optional `text` content, optional `let`
  bindings, optional `repeat` declarations, and optional `children`.
- **`numElementsRange`** – Optional `[min, max]` constraint that is enforced
  against the input data length.
- **`schema`** – Optional JSON Schema definition validated at render time to
  guarantee input shape correctness.
- **`metadata`** – Optional informational fields (`name`, `description`,
  `version`) preserved for downstream tooling.

### Example

```json
{
  "name": "Horizontal Bar Chart",
  "properties": {
    "canvas": { "width": 960, "height": 540 },
    "margin": 64,
    "barHeight": 38,
    "fontFamily": "Inter, Arial, sans-serif",
    "colors": ["#4338ca", "#2563eb", "#10b981"],
    "background": "#f8fafc"
  },
  "template": [
    {
      "type": "rect",
      "attributes": {
        "x": "0",
        "y": "0",
        "width": "100%",
        "height": "100%",
        "fill": "{background}"
      }
    },
    {
      "type": "rect",
      "repeat": {"items": "items", "as": "row"},
      "let": {
        "span_width": "canvas.width - 2 * margin",
        "bar_width": "span_width * (row.value / maxValue)",
        "bar_y": "margin + __index__ * (bar_height + 20)",
        "color_index": "__index__ % colors.length",
        "bar_color": "colors[color_index]"
      },
      "attributes": {
        "x": "{margin}",
        "y": "{bar_y}",
        "width": "{bar_width}",
        "height": "{bar_height}",
        "fill": "{bar_color}"
      }
    }
  ]
}
```

Element `let` blocks run after any repeat context has been prepared. The
bindings they produce become available to the element itself and to any child
elements.

## Programmatic Usage

The loader returns an `InfogrooveRenderer`. Applications can call `render`
with a sequence of mappings to produce SVG markup. The convenience helper
`infogroove.render_svg(path, data)` performs the load/validate/render cycle in
one step for filesystem templates.

## Data Validation

Before rendering begins the renderer:

1. Materialises the incoming data into a list and ensures each entry is a
   mapping.
2. Enforces `numElementsRange` boundaries when present.
3. Validates against the optional JSON Schema.

Violations raise `DataValidationError` so the CLI and embedding applications
can surface helpful messages.

## Rendering Context

The base context contains:

- Canvas metrics exposed in the `canvas` mapping (`canvas.width`,
  `canvas.height`).
- All entries from `properties`, wrapped in lightweight adapter classes so
  both dotted access and key lookup are available.
- The dataset itself under `data`/`items` plus aggregate metrics (`values`,
  `maxValue`, `minValue`, `averageValue`) when numeric values are present.

For each repeat iteration the renderer creates a frame that adds:

- Reserved helpers (`__index__`, `__count__`, `__total__`, `__first__`,
  `__last__`).
- The current item under the declared alias (with the same helpers reflected on
  the alias when the item is a mapping).
- Element `let` bindings evaluated lazily when referenced.

Placeholder strings (`"{path.to.value}"`) resolve against the current context
and support dot access, list indices, camel↔snake name matching, and a synthetic
`length` property. Missing placeholders raise `KeyError` to catch mistakes
early.

## Rendering Flow

1. Load template and create an `InfogrooveRenderer`.
2. Validate the incoming data sequence.
3. Build the base context from `properties` and dataset metrics.
4. Render non-repeating elements once using the base context.
5. For each repeat declaration, iterate the resolved collection, augment the
   context with reserved helpers and element-level `let` results, and render
   the element graph.
6. Serialise the assembled `svg.py` DOM via `as_str()`.

Errors in template parsing, data validation, formula evaluation, or element
materialisation raise domain-specific exceptions (`TemplateError`,
`DataValidationError`, `FormulaEvaluationError`, `RenderError`).

## CLI

The `infogroove` CLI accepts `-f/--template`, `-i/--input`, and `-o/--output.
` Passing `-` as the output path streams SVG to stdout, which is useful for
tooling pipelines.

## Summary

The current grammar favours clarity:

- `properties` hold literal assignments.
- Element-level `let` blocks express derived values at precise scopes.
- Reserved helpers (`__index__`, etc.) remove the need for ad-hoc loop aliases.

These rules allow templates to stay concise while remaining predictable and
safe to evaluate.
