"""Convert templates and data into SVG output using svg.py."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Iterator

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
from .models import ElementSpec, RepeatSpec, TemplateSpec
from .utils import MappingAdapter, ensure_accessible, fill_placeholders, resolve_path, to_snake_case

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


class _OverlayMapping(Mapping[str, Any]):
    """Mapping overlay that lazily resolves dependent let bindings."""

    def __init__(
        self,
        base: Mapping[str, Any],
        resolved: dict[str, Any],
        bindings: Mapping[str, Any],
        resolver: Any,
    ) -> None:
        self._base = base
        self._resolved = resolved
        self._bindings = bindings
        self._resolver = resolver

    def __getitem__(self, key: str) -> Any:
        if key in self._resolved:
            return self._resolved[key]
        if key in self._base:
            return self._base[key]
        if key in self._bindings:
            return self._resolver(key)
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:  # type: ignore[override]
        seen: set[str] = set()
        for mapping in (self._base, self._resolved):
            for key in mapping:
                if key not in seen:
                    seen.add(key)
                    yield key
        for key in self._bindings:
            if key not in seen:
                yield key

    def __len__(self) -> int:
        keys = set(self._base) | set(self._resolved) | set(self._bindings)
        return len(keys)


class _FormulaScope(Mapping[str, Any]):
    """Mapping view passed into the formula engine during binding evaluation."""

    def __init__(
        self,
        overlay: _OverlayMapping,
        base: Mapping[str, Any],
        resolved: Mapping[str, Any],
        bindings: Mapping[str, Any],
        skip: str,
    ) -> None:
        self._overlay = overlay
        self._base = base
        self._resolved = resolved
        self._bindings = bindings
        self._skip = skip

    def __getitem__(self, key: str) -> Any:
        if key == self._skip:
            raise KeyError(key)
        return self._overlay[key]

    def __iter__(self) -> Iterator[str]:  # type: ignore[override]
        seen: set[str] = set()
        for mapping in (self._resolved, self._base):
            for key in mapping:
                if key == self._skip or key in seen:
                    continue
                seen.add(key)
                yield key

    def __len__(self) -> int:
        keys = set(self._base) | set(self._resolved)
        keys.discard(self._skip)
        return len(keys)

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str):  # pragma: no cover - defensive
            return False
        if key == self._skip:
            return False
        if key in self._resolved or key in self._base:
            return True
        return key in self._bindings


class InfogrooveRenderer:
    """Render SVG documents by combining templates with external data."""

    def __init__(self, template: TemplateSpec):
        self._template = template

    @property
    def template(self) -> TemplateSpec:
        """Return the underlying template specification."""

        return self._template

    def render(self, data: Sequence[Mapping[str, Any]]) -> str:
        """Render the template with the supplied data and return SVG markup."""

        dataset = self._validate_data(data)
        base_context = self._build_base_context(dataset)
        canvas_context = base_context.get("canvas")
        width = self._template.canvas.width
        height = self._template.canvas.height
        if isinstance(canvas_context, Mapping):
            try:
                width = float(canvas_context["width"])
                height = float(canvas_context["height"])
            except (KeyError, TypeError, ValueError):
                width = self._template.canvas.width
                height = self._template.canvas.height

        svg_root = SVG(width=width, height=height, elements=[])

        nodes: list[Any] = []
        for element in self._template.template:
            nodes.extend(self._render_to_nodes(element, base_context))

        svg_root.elements = (svg_root.elements or []) + nodes
        return svg_root.as_str()

    def _render_to_nodes(
        self,
        element: ElementSpec,
        context: Mapping[str, Any],
        *,
        ignore_repeat: bool = False,
    ) -> list[Any]:
        if element.repeat and not ignore_repeat:
            items, total = self._resolve_repeat_items(element.repeat, context)
            rendered: list[Any] = []
            for index, item in enumerate(items):
                frame = self._build_repeat_context(context, element.repeat, item, index, total)
                rendered.extend(self._render_to_nodes(element, frame, ignore_repeat=True))
            return rendered

        working_context = dict(context)
        if element.let:
            bindings = self._evaluate_bindings(element.let, working_context, label=f"element:{element.type}")
            accessible = self._make_accessible_bindings(bindings)
            working_context.update(accessible)

        node = self._create_node(element, working_context)

        if element.children:
            if not hasattr(node, "elements"):
                raise RenderError(f"Element type '{element.type}' does not support nested children")
            child_nodes: list[Any] = []
            for child in element.children:
                child_nodes.extend(self._render_to_nodes(child, working_context))
            existing = list(getattr(node, "elements", []) or [])
            node.elements = existing + child_nodes

        return [node]

    def _resolve_repeat_items(
        self,
        repeat: RepeatSpec,
        context: Mapping[str, Any],
    ) -> tuple[list[Any], int]:
        try:
            collection = resolve_path(context, repeat.items)
        except KeyError as exc:
            raise RenderError(f"Unable to resolve repeat items at '{repeat.items}'") from exc

        if isinstance(collection, Sequence):
            items = list(collection)
        else:
            try:
                items = list(collection)
            except TypeError as exc:  # pragma: no cover - defensive
                raise RenderError(f"Repeat items at '{repeat.items}' are not iterable") from exc

        return items, len(items)

    def _build_repeat_context(
        self,
        parent_context: Mapping[str, Any],
        repeat: RepeatSpec,
        item: Any,
        index: int,
        total: int,
    ) -> dict[str, Any]:
        frame = dict(parent_context)
        alias_binding: Any
        if isinstance(item, Mapping):
            alias_payload = dict(item)
            alias_payload.setdefault("__index__", index)
            alias_payload.setdefault("__count__", index + 1)
            alias_payload.setdefault("__total__", total)
            alias_payload.setdefault("__first__", index == 0)
            alias_payload.setdefault("__last__", index == total - 1)
            alias_binding = ensure_accessible(alias_payload)
        else:
            alias_binding = ensure_accessible(item)
        frame["__index__"] = index
        frame["__first__"] = index == 0
        frame["__last__"] = index == total - 1
        frame["__total__"] = total
        frame["__count__"] = index + 1

        frame[repeat.alias] = alias_binding

        return frame

    def _create_node(self, element: ElementSpec, context: Mapping[str, Any]) -> Any:
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

        return node

    def _build_base_context(self, dataset: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        length = len(dataset)
        accessible_data = ensure_accessible(dataset)
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

        context: dict[str, Any] = {
            "data": accessible_data,
            "items": accessible_data,
            "total": length,
            "count": length,
            **metrics,
        }

        properties = dict(self._template.properties)

        canvas_binding = properties.get("canvas")
        if isinstance(canvas_binding, Mapping):
            canvas_dict = {key: canvas_binding[key] for key in canvas_binding}
            try:
                canvas_dict["width"] = float(canvas_dict.get("width", self._template.canvas.width))
                canvas_dict["height"] = float(canvas_dict.get("height", self._template.canvas.height))
            except (TypeError, ValueError):
                canvas_dict.setdefault("width", self._template.canvas.width)
                canvas_dict.setdefault("height", self._template.canvas.height)
            properties["canvas"] = canvas_dict

        accessible_properties = self._make_accessible_bindings(properties)
        context.update(accessible_properties)
        properties_adapter = ensure_accessible(accessible_properties)
        context["properties"] = properties_adapter
        context["variables"] = properties_adapter  # backwards-friendly alias

        return context

    def _evaluate_bindings(
        self,
        bindings: Mapping[str, Any],
        base_context: Mapping[str, Any],
        *,
        label: str,
    ) -> dict[str, Any]:
        resolved: dict[str, Any] = {}
        resolving: set[str] = set()

        def resolve_key(name: str) -> Any:
            if name in resolved:
                return resolved[name]
            if name in resolving:
                raise RenderError(f"Circular let binding detected for '{label}.{name}'")
            if name not in bindings:
                raise KeyError(name)

            resolving.add(name)
            overlay = _OverlayMapping(base_context, resolved, bindings, resolve_key)
            try:
                value = self._evaluate_value(
                    name,
                    bindings[name],
                    overlay,
                    base_context,
                    resolved,
                    bindings,
                )
            finally:
                resolving.remove(name)
            resolved[name] = value
            return value

        for key in bindings:
            resolve_key(key)

        return resolved

    def _evaluate_value(
        self,
        name: str,
        value: Any,
        overlay: _OverlayMapping,
        base_context: Mapping[str, Any],
        resolved: Mapping[str, Any],
        bindings: Mapping[str, Any],
    ) -> Any:
        if isinstance(value, Mapping):
            return {
                key: self._evaluate_value(
                    f"{name}.{key}",
                    sub_value,
                    overlay,
                    base_context,
                    resolved,
                    bindings,
                )
                for key, sub_value in value.items()
            }

        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            return [
                self._evaluate_value(
                    f"{name}[{index}]",
                    item,
                    overlay,
                    base_context,
                    resolved,
                    bindings,
                )
                for index, item in enumerate(value)
            ]

        if isinstance(value, str):
            try:
                resolved_value = resolve_path(overlay, value)
                return resolved_value
            except KeyError:
                pass
            engine = FormulaEngine({name: value})
            scope = _FormulaScope(overlay, base_context, resolved, bindings, name)
            try:
                evaluated = engine.evaluate(scope)[name]
            except FormulaEvaluationError:
                return value
            return evaluated

        return value

    @staticmethod
    def _make_accessible_bindings(bindings: Mapping[str, Any]) -> dict[str, Any]:
        return {key: ensure_accessible(value) for key, value in bindings.items()}

    def _validate_data(self, data: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
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
        key = key.replace("-", "_")
        if key == "class":
            return "class_"
        if any(ch.isupper() for ch in key):
            return to_snake_case(key)
        return key
