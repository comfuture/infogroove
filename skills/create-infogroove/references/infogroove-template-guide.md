# Infogroove Template Quick Guide

Use this as a fast reference when authoring `def.json` and `data.json`.

## Template skeleton

```json
{
  "name": "Title",
  "description": "Short summary",
  "properties": {
    "canvas": { "width": 960, "height": 540 },
    "font_family": "Inter, Arial, sans-serif",
    "palette": ["#111827", "#2563eb"]
  },
  "schema": { "$schema": "https://json-schema.org/draft/2020-12/schema" },
  "template": []
}
```

- `properties.canvas.width/height` must be numbers.
- Other `properties` become template variables.
- `schema` is optional but recommended for data validation.

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
    "y": "margin + __index__ * 24"
  },
  "attributes": { "x": "{margin}", "y": "{y}" },
  "text": "{label}"
}
```

- `repeat.items` points to a collection in the current context.
- `repeat.as` names each item. Reserved helpers: `__index__`, `__count__`, `__first__`, `__last__`.
- `let` values can be expressions or `{placeholder}` strings.

## Placeholders and expressions

- Use `{...}` inside strings for expressions: `{canvas.width / 2}`.
- In `let`, a single placeholder string returns raw values (numbers, lists, dicts).
- In `attributes`/`text`, placeholder results become strings.

## Common element types

`rect`, `text`, `circle`, `line`, `ellipse`, `path`, `polygon`, `polyline`, `g`, `defs`,
`linearGradient`, `radialGradient`, `stop`, `tspan`.

## Example patterns

- Horizontal bars: `examples/horizontal-bars`
- Stat cards: `examples/stat-cards`
- Key messages: `examples/key-messages`
- Arc circles: `examples/arc-circles`
