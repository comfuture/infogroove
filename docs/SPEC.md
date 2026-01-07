# Infogroove Template Specification

This document defines the JSON template format used by Infogroove to generate
SVG infographics. It is written for both humans and AI agents who need a clear,
actionable reference to author new templates.

## 1. File format

- **Encoding:** UTF-8 JSON.
- **Root type:** JSON object.
- **Strictness:** Unknown top-level keys are ignored by the parser, but only the
  documented fields are supported by the renderer.

## 2. Top-level object

Required keys:

- `properties` (object)
- `template` (array)

Optional keys:

- `schema` (object; JSON Schema)
- `name` (string)
- `description` (string)
- `version` (string)

### 2.1 `properties`

`properties` is a required object containing reusable constants and the canvas
size. It **must** include a `canvas` object with numeric `width` and `height`.

Example:

```json
{
  "properties": {
    "canvas": { "width": 960, "height": 540 },
    "margin": 48,
    "font_family": "Inter, Arial, sans-serif",
    "palette": ["#111827", "#2563eb"]
  }
}
```

Notes:

- `canvas.width` and `canvas.height` must be numbers (not expressions).
- All other properties are injected into the rendering context as-is and can
  be referenced by placeholders or expressions.
- To enable deterministic randomness, set `properties.random_seed` (number) or
  provide a custom RNG object as `properties.random`.

### 2.2 `template`

`template` is an ordered list of element objects. Each element is rendered once
unless it includes a `repeat` block.

### 2.3 `schema` (optional)

`schema` is a JSON Schema definition used to validate incoming data. It is
validated at render time using `jsonschema`. Use `minItems`/`maxItems` on the
root collection (or nested collections) to declare expected input size.

Example (object with `items` array):

```json
{
  "schema": {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["items"],
    "properties": {
      "items": {
        "type": "array",
        "minItems": 1,
        "maxItems": 10,
        "items": {
          "type": "object",
          "required": ["label", "value"],
          "properties": {
            "label": { "type": "string" },
            "value": { "type": "number" }
          },
          "additionalProperties": false
        }
      }
    }
  }
}
```

### 2.4 Metadata fields

`name`, `description`, and `version` are preserved as metadata for downstream
tools. They do not affect rendering.

## 3. Element specification

Each element in `template` is an object with these fields:

- `type` (string, required)
- `attributes` (object, optional)
- `text` (string, optional)
- `let` (object, optional)
- `repeat` (object, optional)
- `children` (array, optional)

### 3.1 `type`

`type` is case-insensitive and must match a supported element type or a custom
renderer registered by the host application.

Built-in element types:

- `rect`, `text`, `circle`, `line`, `ellipse`
- `path`, `polygon`, `polyline`
- `g`, `defs`, `clipPath`
- `linearGradient`, `radialGradient`
- `stop`, `tspan`

If a template uses a custom type (for example `icon`), the application must
register a renderer for that type; otherwise rendering fails.

### 3.2 `attributes`

`attributes` is a mapping of SVG attributes to values. Values are converted to
strings and then processed for placeholders.

Example:

```json
{
  "type": "rect",
  "attributes": {
    "x": "{margin}",
    "y": "{bar_y}",
    "width": "{bar_width}",
    "height": "24",
    "fill": "{bar_color}",
    "rx": "8"
  }
}
```

Attribute name normalization:

- Hyphens are converted to underscores.
- `class` becomes `class_`.
- CamelCase is converted to snake_case.

This matches the expectations of `svg.py`. If an attribute is not supported by
the underlying SVG element, rendering will raise an error unless the element
supports an `extra` or `data` attribute mapping.

### 3.3 `text`

`text` is the text content for `text` or `tspan` elements. It can include
placeholders. For non-text elements, text is inserted as a nested `<text>`
node if the element supports children; otherwise it raises an error.

### 3.4 `children`

`children` is a list of nested element objects. Use this for grouping
(`g`), definitions (`defs`, gradients, clip paths), or any element that can
contain child nodes.

## 4. Placeholders and expressions

### 4.1 Placeholder syntax

Any string can include `{...}` placeholders. The content inside braces is an
expression evaluated against the current context.

Examples:

- `{canvas.width}`
- `{__index__ * 12}`
- `{items[0].label}`
- `{Math.sin(angle) * radius}`

In **attributes** and **text**, placeholder results are always stringified.
In **`let` bindings**, a string that is exactly a single placeholder (for
example `"{value}"`) returns the raw expression result (number, list, object,
etc.). If the placeholder appears inside a larger string, the result is
stringified and interpolated.

### 4.2 Expression environment

Expressions are evaluated with a restricted engine:

- **Operators:** `+ - * / // % **`, comparisons, boolean `and/or`, ternary.
- **Indexing:** `foo[0]`, `foo["key"]`, and slicing.
- **Literals:** strings, numbers, lists, dicts, tuples.
- **Allowed functions:** `abs`, `min`, `max`, `round`, `len`, `sum`,
  `int`, `float`, `str`, `range` (max 10,000 items).
- **Math:** `math` and `Math` (with `floor`, `ceil`, `sin`, `cos`, `tan`,
  `sqrt`, `pow`, `pi`, `tau`).
- **Random:** `random` or `Math.random()` if a seeded RNG is provided.

Private attributes and arbitrary function calls are blocked.

### 4.3 Path resolution

`repeat.items` and dotted names in expressions are resolved through a path
resolver that supports:

- Dot notation: `entry.value`
- Bracket notation: `entry["value"]`, `colors[2]`
- `length` property on lists or objects: `items.length`

## 5. `let` bindings

`let` is an object that defines derived bindings scoped to the element. Values
can be strings (expressions), arrays, or nested objects.

String evaluation rules:

- If the string contains `{...}` placeholders, placeholder expansion is used.
- If the string is exactly one placeholder, the raw expression result is
  returned (not stringified).
- Otherwise the entire string is treated as an expression.

Key properties:

- **Lazy evaluation:** bindings are computed only when referenced.
- **Forward references:** you can reference bindings declared later.
- **Cycle detection:** circular references raise an error.

Example:

```json
{
  "type": "polygon",
  "let": {
    "x": "10",
    "top_y": "20",
    "width": "30",
    "points": "{x},{top_y} {x + width},{top_y}"
  },
  "attributes": { "points": "{points}" }
}
```

## 6. `repeat` blocks

`repeat` renders an element (and its children) once per item in a collection.

```json
{
  "type": "text",
  "repeat": { "items": "items", "as": "row" },
  "let": { "label": "row.label" },
  "attributes": { "x": "{__index__ * 24}", "y": "40" },
  "text": "{label}"
}
```

`repeat` fields:

- `items` (string, required): path to the iterable collection.
- `as` (string, required): alias for the current item.
- `let` (object, optional): per-iteration bindings evaluated before the
  element-level `let`.

Reserved helpers available inside repeats:

- `__index__` (0-based index)
- `__count__` (1-based index)
- `__total__` (number of items)
- `__first__` (boolean)
- `__last__` (boolean)

If the iterated item is a mapping, the alias also exposes these helpers (e.g.
`row.__index__`).

## 7. Rendering context

The base context always includes:

- `data` / `payload`: the raw input payload.
- `properties`: the top-level properties object (also available as `variables`).
- `canvas.width` / `canvas.height`.

If the payload is:

- **An array:** it becomes `items`, and metrics are computed from `item.value`.
- **An object with `items`:** the `items` array becomes the primary sequence.

Computed metrics (when numeric `value` fields exist):

- `values` / `item_values`: list of numeric values
- `maxValue`, `minValue`, `averageValue`
- `count` / `total` (length of the primary sequence)

## 8. Validation and errors

Validation occurs in this order:

1. If the payload is an array, every entry must be an object.
2. `minItems` / `maxItems` bounds derived from `schema` are enforced.
3. JSON Schema validation is applied if `schema` is provided.

Common error sources:

- Missing `properties.canvas.width`/`height`.
- Unsupported element types.
- Invalid `repeat.items` path.
- Unsupported attributes for a given SVG element.
- Circular `let` bindings or invalid expressions.

## 9. Deprecated or unsupported keys

The following keys are rejected by the loader:

- Top-level: `styles`, `variables`, `let`, `elements`, `numElementsRange`
- Element-level: `scope`
- Repeat-level: `index`

Use `properties`, `template`, and `schema` as described above instead.

## 10. Minimal working template

```json
{
  "name": "Minimal Example",
  "properties": {
    "canvas": { "width": 400, "height": 200 },
    "title_color": "#111827"
  },
  "schema": {
    "type": "array",
    "minItems": 1,
    "items": {
      "type": "object",
      "required": ["label"],
      "properties": { "label": { "type": "string" } },
      "additionalProperties": false
    }
  },
  "template": [
    {
      "type": "text",
      "attributes": {
        "x": "24",
        "y": "80",
        "fontSize": "28",
        "fill": "{title_color}"
      },
      "text": "{items[0].label}"
    }
  ]
}
```

## 11. Authoring checklist

- Define `properties.canvas` with numeric `width` and `height`.
- Decide the input data shape and encode it in `schema`.
- Use `repeat` for iteration; avoid implicit loops.
- Put shared calculations in `let`, quick math in placeholders.
- Stick to supported SVG element types or register custom renderers.
- Keep attribute names aligned with SVG/`svg.py` expectations.
