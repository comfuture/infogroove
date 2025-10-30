# Infogroove Main Idea

Infogroove is an infographic generation framework that turns declarative template
definitions into SVG output by combining structured templates, evaluated formulas,
and external datasets. The current implementation keeps the spirit of the
original plan while refining the template format and rendering pipeline so that
it integrates cleanly with `sympy` and `svg.py`.

## Template Structure (definition JSON)

Each template is a UTF-8 JSON document. The loader (`loader.load` / `loader.loads`)
parses the payload into strongly-typed models that the renderer consumes.

- **variables** – Required mapping of reusable constants. It must contain
  `canvas` with viewport `width` and `height`, and can expose any additional
  values (e.g. `margin`, `palette`, `fontFamily`). Variables are available both
  under the `variables` object and as top-level names, so `{radius}` and
  `{variables.radius}` resolve to the same value.
- **formulas** – Mapping of named expressions. Expressions run through the
  `FormulaEngine`, which prefers `sympy.sympify` and transparently falls back to
  a sandboxed Python `eval` when symbolic parsing fails.
- **elements** – Ordered list of SVG element descriptors. Each entry provides a
  `type` (rect, text, polygon, path, etc.), an `attributes` dictionary whose
  values may contain placeholders, optional `text` content for text nodes, and
  an optional `scope` (`"canvas"` renders once, `"item"` renders per data row).
- **numElementsRange** – Optional `[min, max]` constraint that is enforced
  against the input data length.
- **schema** – Optional JSON Schema definition. During rendering the schema is
  validated with `jsonschema.validate` to guarantee shape correctness.
- **metadata** – Non-functional fields (`name`, `description`, `version`) are
  preserved on the template for downstream tooling.

### Example

```jsonc
{
  "name": "Horizontal Bar Chart",
  "variables": {
    "canvas": { "width": 960, "height": 540 },
    "margin": 64,
    "barHeight": 38,
    "background": "#f8fafc",
    "fontFamily": "Inter, Arial, sans-serif",
    "colors": ["#4338ca", "#2563eb", "#10b981"]
  },
  "formulas": {
    "spanWidth": "canvas.width - 2 * margin",
    "barWidth": "spanWidth * (value / maxValue)",
    "barY": "margin + index * (barHeight + 20)",
    "colorIndex": "index % colors.length",
    "barColor": "colors[colorIndex]"
  },
  "elements": [
    {
      "type": "rect",
      "scope": "canvas",
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
      "attributes": {
        "x": "{margin}",
        "y": "{barY}",
        "width": "{barWidth}",
        "height": "{barHeight}",
        "fill": "{barColor}"
      }
    },
    {
      "type": "text",
      "attributes": {
        "x": "{margin}",
        "y": "{barY}",
        "dominantBaseline": "middle",
        "fontFamily": "{fontFamily}"
      },
      "text": "{label}"
    }
  ]
}
```

Attribute values are stored separately rather than as raw SVG strings (an
adjustment from the initial plan). This keeps placeholder fills predictable,
lets the renderer normalise attribute names (e.g. `class` → `class_`), and lets
`svg.py` build the DOM safely.

## Programmatic Usage

Infogroove ships a lightweight loader so applications can embed templates
without shelling out to the CLI. The two helper functions mirror `json.load` and
`json.loads`:

```python
from infogroove.loader import load, loads

with open("examples/arc-circles/def.json", encoding="utf-8") as fh:
    infographic = load(fh)

svg_markup = infographic.render([{"label": "Launch", "value": 42}])

other = loads(template_json_string)
image = other.render(dataset)
```

Both functions return an `InfogrooveRenderer`. The underlying `TemplateSpec`
is still accessible via `renderer.template` when projects need to inspect
metadata.

## Data Supply and Validation

Input data is expected to be an ordered sequence of mappings (`list[dict]`).
The CLI loader also accepts `{ "items": [...] }` wrappers as a convenience.
Before any rendering happens, the renderer:

1. Converts the sequence into a list and checks that every entry is a mapping.
2. Enforces `numElementsRange` boundaries when the template declares them.
3. Validates the payload against the optional JSON Schema.

These checks produce `DataValidationError` exceptions when requirements are not
met.

## Rendering Context and Formulas

The renderer builds a base context that is shared by every element:

- Canvas metrics are exposed in multiple naming styles:
  `canvas.width`, `canvasWidth`, `canvas_width`, etc.
- Variables are merged into the context with lightweight adapter classes
  (`MappingAdapter`, `SequenceAdapter`) so dotted access works alongside item
  access.
- Dataset statistics (`values`, `maxValue`, `minValue`, `averageValue`) are
  automatically computed when numeric `value` fields are present.
- The full dataset is accessible via `data`, `items`, and `count`/`total`.

For each row, the item context extends the base values with:

- Index aliases: `index`, `idx`, `oneBasedIndex`, `position`.
- The raw item as `item` and `record`, plus top-level keys merged in.
- A `label` fallback sourced from `text` or `label` when present.
- A `value` fallback when the item only contains numeric fields.

Formulas are evaluated with the combined context. Dotted lookups inside
expressions are rewritten into symbol placeholders before calling `sympy`, and
the same adapters allow expressions such as `palette.length` or
`items[0].value` to work. When all formulas for the current scope have run,
their results are merged back into the context for placeholder substitution.

The evaluation namespace whitelists common Python builtins (`abs`, `min`,
`max`, `round`, …), math functions (both `math` and a JS-style `Math` shim),
and protects against arbitrary code execution by clearing `__builtins__`.

## Placeholder Resolution

Template strings use `{path.to.value}` placeholders. Paths support dot access,
array indices (`items[3].value`), mixed casing (snake ↔ camel), and a synthetic
`length` property. Missing values raise `KeyError` so template authors discover
typos early. The substitution step runs for every attribute and for the text
content of textual elements.

## Rendering Flow

1. **Load template** – `loader.load_path` reads the definition file and returns an
   `InfogrooveRenderer` instance.
2. **Create renderer** – the `InfogrooveRenderer` prepared by the loader
   initialises the `FormulaEngine`.
3. **Validate data** – The incoming dataset is checked against range limits and
   optional JSON Schema requirements.
4. **Render canvas elements** – Elements scoped to `"canvas"` are rendered once
   with the base context; formulas are evaluated but item data is not injected.
5. **Render item elements** – For each data record the renderer builds an item
   context, evaluates formulas, fills placeholders, and appends SVG nodes.
6. **Emit SVG** – The assembled `svg.py.SVG` tree is serialised via `as_str()`.

Failures in template parsing, data validation, formula evaluation, or element
materialisation raise domain-specific exceptions (`TemplateError`,
`DataValidationError`, `FormulaEvaluationError`, `RenderError`) that the CLI
surfaces as readable error messages.

## Tooling

- The `infogroove` CLI accepts `-f/--template`, `-i/--input`, and `-o/--output`
  flags to render templates from the command line. Passing `-` as the output
  streams SVG to stdout.
- Library consumers can call `infogroove.render_svg(template_path, data)` to
  perform the entire load/validate/render cycle in a single helper function.

This architecture stays faithful to the original plan—templates, elements,
formulas, variables, and schemas remain the core concepts—while reflecting the
codebase’s current shape and safety guardrails.
