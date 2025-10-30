"""Convert templates and data into SVG output using svg.py."""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from jsonschema import ValidationError as JSONSchemaValidationError
from jsonschema import SchemaError
from jsonschema import validate as validate_jsonschema

from svg import (
    Circle,
    ClipPath,
    Defs,
    Ellipse,
    G,
    Line,
    LinearGradient,
    Path,
    Polygon,
    Polyline,
    RadialGradient,
    Rect,
    SVG,
    Stop,
    TSpan,
    Text,
)

from .exceptions import DataValidationError, FormulaEvaluationError, RenderError
from .formula import FormulaEngine
from .models import ElementSpec, TemplateSpec
from .utils import fill_placeholders, to_snake_case

SUPPORTED_ELEMENTS = {
    "rect": Rect,
    "text": Text,
    "circle": Circle,
    "line": Line,
    "ellipse": Ellipse,
    "path": Path,
    "polygon": Polygon,
    "polyline": Polyline,
    "g": G,
    "clippath": ClipPath,
    "defs": Defs,
    "lineargradient": LinearGradient,
    "radialgradient": RadialGradient,
    "stop": Stop,
    "tspan": TSpan,
}


class InfogrooveRenderer:
    """Render SVG documents by combining templates with external data."""

    def __init__(self, template: TemplateSpec):
        self._template = template
        self._engine = FormulaEngine(template.formulas)

    @property
    def template(self) -> TemplateSpec:
        """Return the underlying template specification."""

        return self._template

    def render(self, data: Sequence[Mapping[str, Any]]) -> str:
        """Render the template with the supplied data and return SVG markup."""

        dataset = self._validate_data(data)
        base_context = self._build_base_context(dataset)
        svg_root = SVG(
            width=self._template.canvas.width,
            height=self._template.canvas.height,
            elements=[],
        )
        self._render_canvas_elements(svg_root, base_context)
        self._render_item_elements(svg_root, base_context, dataset)
        return svg_root.as_str()

    def _render_canvas_elements(self, svg_root: SVG, base_context: Mapping[str, Any]) -> None:
        """Render non-repeating elements that only depend on the global context."""
        for element in self._elements_for_scope("canvas"):
            context = dict(base_context)
            try:
                evaluated = self._engine.evaluate(context)
            except FormulaEvaluationError:
                evaluated = {}
            context.update(evaluated)
            self._append(svg_root, element, context)

    def _render_item_elements(
        self,
        svg_root: SVG,
        base_context: Mapping[str, Any],
        dataset: Sequence[Mapping[str, Any]],
    ) -> None:
        """Render templated elements once for every record in the dataset."""
        total = len(dataset)
        for index, item in enumerate(dataset):
            context = self._build_item_context(base_context, item, index, total)
            evaluated = self._engine.evaluate(context)
            context.update(evaluated)
            for element in self._elements_for_scope("item"):
                item_context = dict(context)
                self._append(svg_root, element, item_context)

    def _append(self, svg_root: SVG, element: ElementSpec, context: Mapping[str, Any]) -> None:
        """Instantiate an SVG element from the template definition and attach it."""
        node = self._create_node(element, context)
        if svg_root.elements is None:
            svg_root.elements = []
        svg_root.elements.append(node)

    def _create_node(self, element: ElementSpec, context: Mapping[str, Any]) -> Any:
        """Instantiate an SVG node (and any nested children) from a template element."""

        factory = SUPPORTED_ELEMENTS.get(element.type.lower())
        if factory is None:
            raise RenderError(f"Unsupported element type '{element.type}'")

        prepared_attributes = {
            self._normalise_attribute_key(key): fill_placeholders(value, context)
            for key, value in element.attributes.items()
        }

        if factory in (Text, TSpan):
            text_value = fill_placeholders(element.text or "", context)
            node = factory(text=text_value, **prepared_attributes)
        else:
            node = factory(**prepared_attributes)

        if element.children:
            if not hasattr(node, "elements"):
                raise RenderError(f"Element type '{element.type}' does not support nested children")
            child_nodes = [self._create_node(child, context) for child in element.children]
            existing = list(getattr(node, "elements", []) or [])
            node.elements = existing + child_nodes

        return node

    def _elements_for_scope(self, scope: str) -> Iterable[ElementSpec]:
        """Return the subset of elements matching the provided scope value."""
        return [element for element in self._template.elements if element.scope == scope]

    def _build_base_context(self, dataset: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        """Create the global context shared by all elements and formulas."""
        variables = dict(self._template.variables)
        canvas_map = dict(variables.get("canvas", {})) if isinstance(variables.get("canvas"), Mapping) else {}
        width = float(canvas_map.get("width", self._template.canvas.width))
        height = float(canvas_map.get("height", self._template.canvas.height))
        canvas_map.update({"width": width, "height": height})
        variables["canvas"] = canvas_map
        values = [
            item.get("value")
            for item in dataset
            if isinstance(item, Mapping) and isinstance(item.get("value"), (int, float))
        ]
        metrics: dict[str, Any] = {}
        if values:
            metrics.update(
                {
                    "item_values": values,
                    "values": values,
                    "maxValue": max(values),
                    "minValue": min(values),
                    "averageValue": sum(values) / len(values),
                }
            )
        return {
            "data": dataset,
            "items": dataset,
            "total": len(dataset),
            "count": len(dataset),
            "canvas": canvas_map,
            "canvasWidth": width,
            "canvasHeight": height,
            "canvas_width": width,
            "canvas_height": height,
            **metrics,
            **{key: value for key, value in variables.items() if key != "canvas"},
            "variables": variables,
        }

    def _build_item_context(
        self,
        base_context: Mapping[str, Any],
        item: Mapping[str, Any],
        index: int,
        total: int,
    ) -> dict[str, Any]:
        """Blend the base context with per-item details for formula evaluation."""
        context = dict(base_context)
        context.update({
            "index": index,
            "idx": index,
            "oneBasedIndex": index + 1,
            "position": index + 1,
            "item": item,
            "record": item,
            "total": total,
            "count": total,
        })
        context.update(item)
        if (
            "value" not in context
            and item
            and all(isinstance(v, (int, float)) for v in item.values())
        ):
            context["value"] = next(iter(item.values()))
        context.setdefault("label", item.get("text") or item.get("label"))
        return context

    def _validate_data(self, data: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
        """Ensure the incoming data sequence can safely drive the template."""
        if not isinstance(data, Sequence):
            raise DataValidationError("Input data must be an ordered sequence of mappings")
        dataset = list(data)
        if not all(isinstance(item, Mapping) for item in dataset):
            raise DataValidationError("Each data item must be a mapping")
        minimum, maximum = self._template.expected_range()
        count = len(dataset)
        if minimum is not None and count < minimum:
            raise DataValidationError(f"Template requires at least {minimum} items (received {count})")
        if maximum is not None and count > maximum:
            raise DataValidationError(f"Template accepts at most {maximum} items (received {count})")

        schema = self._template.schema
        if schema is not None:
            try:
                validate_jsonschema(dataset, schema)
            except JSONSchemaValidationError as exc:
                raise DataValidationError(
                    f"Input data does not satisfy the template schema: {exc.message}"
                ) from exc
            except SchemaError as exc:
                raise DataValidationError("Template schema definition is invalid") from exc
        return dataset

    @staticmethod
    def _normalise_attribute_key(key: str) -> str:
        """Translate template attribute keys to svg.py-friendly parameter names."""
        key = key.replace("-", "_")
        if key == "class":
            return "class_"
        if any(ch.isupper() for ch in key):
            return to_snake_case(key)
        return key
