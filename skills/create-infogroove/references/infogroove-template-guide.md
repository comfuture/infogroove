# Infogroove Template Guide (Strict Mode)

Use this guide when authoring `def.json` and `data.json` with strict, reusable template rules.

## Required template skeleton

```json
{
  "name": "Title",
  "description": "Short summary",
  "properties": {
    "canvas": { "width": 1000, "height": 500 },
    "fontFamily": "Inter, Arial, sans-serif"
  },
  "schema": { "$schema": "https://json-schema.org/draft/2020-12/schema" },
  "template": []
}
```

## Strict authoring rules

1) `properties.canvas` is mandatory.
2) `properties.canvas.width` and `properties.canvas.height` must be finite positive numbers.
3) Prefer integer width/height values.
4) Avoid hard-coded geometry in `template` attributes when values can be derived from the canvas.
5) Move customizable visual values (for example `fill`, `stroke`, `strokeWidth`, text color, font sizes) into `properties` with semantic names.

## Canvas validation checklist

- Good: `"canvas": { "width": 1000, "height": 500 }`
- Bad: missing `canvas`
- Bad: `"width": "1000"` (string)
- Bad: `"height": 0` or negative numbers

## Relative geometry pattern

Prefer ratios in `properties`, then compute final geometry in `let`:

```json
{
  "properties": {
    "canvas": { "width": 1000, "height": 500 },
    "outerMarginRatio": 0.08,
    "ringRadiusRatio": 0.35
  },
  "template": [
    {
      "type": "circle",
      "let": {
        "centerX": "canvas.width / 2",
        "centerY": "canvas.height / 2",
        "radius": "min(canvas.width, canvas.height) * ringRadiusRatio"
      },
      "attributes": {
        "cx": "{centerX}",
        "cy": "{centerY}",
        "r": "{radius}"
      }
    }
  ]
}
```

## Style-token pattern (recommended)

Define style tokens in `properties` and reference them from `template`:

```json
{
  "properties": {
    "canvas": { "width": 1000, "height": 500 },
    "mainBgColor": "#0f172a",
    "subBgColor": "#1e293b",
    "fillColors": ["#38bdf8", "#34d399", "#f97316"],
    "labelColor": "#e2e8f0",
    "borderStrokeColor": "#94a3b8",
    "borderStrokeWidth": 2
  },
  "template": [
    {
      "type": "rect",
      "attributes": {
        "x": "0",
        "y": "0",
        "width": "100%",
        "height": "100%",
        "fill": "{mainBgColor}"
      }
    },
    {
      "type": "circle",
      "let": {
        "cx": "canvas.width / 2",
        "cy": "canvas.height / 2",
        "r": "min(canvas.width, canvas.height) * 0.3"
      },
      "attributes": {
        "cx": "{cx}",
        "cy": "{cy}",
        "r": "{r}",
        "fill": "{subBgColor}",
        "stroke": "{borderStrokeColor}",
        "strokeWidth": "{borderStrokeWidth}"
      }
    }
  ]
}
```

## Bad vs good (quick comparison)

Bad (hard-coded geometry and styles):

```json
{
  "type": "circle",
  "attributes": {
    "cx": "500",
    "cy": "250",
    "r": "180",
    "fill": "#1e293b",
    "stroke": "#94a3b8"
  }
}
```

Good (canvas-relative + property-driven):

```json
{
  "type": "circle",
  "let": {
    "cx": "canvas.width / 2",
    "cy": "canvas.height / 2",
    "r": "min(canvas.width, canvas.height) * ringRadiusRatio"
  },
  "attributes": {
    "cx": "{cx}",
    "cy": "{cy}",
    "r": "{r}",
    "fill": "{subBgColor}",
    "stroke": "{borderStrokeColor}"
  }
}
```

## Data shape

The CLI accepts either:

1) A JSON array of objects
2) An object with an `items` array

When rendering via the CLI, data is normalized to a list before validation. If you need schema validation in the CLI, prefer an array-shaped schema (or omit `schema` and validate externally).

## Repeat + let

```json
{
  "type": "text",
  "repeat": { "items": "items", "as": "row" },
  "let": {
    "label": "row.label",
    "y": "canvas.height * 0.15 + __index__ * (canvas.height * 0.08)"
  },
  "attributes": { "x": "{canvas.width * 0.1}", "y": "{y}", "fill": "{labelColor}" },
  "text": "{label}"
}
```

- `repeat.items` points to a collection in the current context.
- `repeat.as` names each item. Reserved helpers: `__index__`, `__count__`, `__first__`, `__last__`.
- `let` values can be expressions or `{placeholder}` strings.

## Placeholders and expressions

- Use `{...}` inside strings for expressions: `{canvas.width / 2}`.
- In `let`, a single placeholder string returns raw values (numbers, lists, dicts).
- In `attributes` and `text`, placeholder results become strings.

## Common element types

`rect`, `text`, `circle`, `line`, `ellipse`, `path`, `polygon`, `polyline`, `g`, `defs`,
`linearGradient`, `radialGradient`, `stop`, `tspan`.

## Example patterns

- Horizontal bars: `examples/horizontal-bars`
- Stat cards: `examples/stat-cards`
- Key messages: `examples/key-messages`
- Arc circles: `examples/arc-circles`
