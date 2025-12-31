"""Convert templates and data into SVG output using svg.py."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from inspect import signature
from typing import Any, Callable, Iterator

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
from .utils import (
    MappingAdapter,
    PLACEHOLDER_PATTERN,
    ensure_accessible,
    fill_placeholders,
    resolve_path,
    stringify,
    to_snake_case,
)

NodeSpec = dict[str, Any]


@dataclass(slots=True, frozen=True)
class RendererInput:
    """Resolved element data provided to renderer callables."""

    type: str
    attributes: Mapping[str, str]
    text: str | None
    children: tuple[NodeSpec, ...]
    spec: ElementSpec


ElementRenderer = Callable[[RendererInput, Mapping[str, Any]], list[NodeSpec]]


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


def _builtin_node_renderer(payload: RendererInput, _: Mapping[str, Any]) -> list[NodeSpec]:
    node: NodeSpec = {
        "type": payload.type,
        "attributes": dict(payload.attributes),
        "children": [child for child in payload.children],
    }
    if payload.text is not None:
        node["text"] = stringify(payload.text)
    return [node]


_ELEMENT_PARAMETERS: dict[str, set[str]] = {
    key: {name for name in signature(factory.__init__).parameters if name != "self"}
    for key, factory in SUPPORTED_ELEMENTS.items()
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

    def __init__(
        self,
        template: TemplateSpec,
        renderers: Mapping[str, ElementRenderer] | None = None,
    ) -> None:
        self._template = template
        self._renderers: dict[str, ElementRenderer] = {
            key: _builtin_node_renderer for key in SUPPORTED_ELEMENTS
        }
        if renderers:
            self.register_renderers(renderers)

    @property
    def template(self) -> TemplateSpec:
        """Return the underlying template specification."""

        return self._template

    def translate(self, data: Any) -> list[NodeSpec]:
        """Return the resolved node specifications without creating SVG markup."""

        payload = self._validate_data(data)
        base_context = self._build_base_context(payload)
        return self._translate_from_context(base_context)

    def render(self, data: Any) -> str:
        """Render the template with the supplied data and return SVG markup."""

        payload = self._validate_data(data)
        base_context = self._build_base_context(payload)
        width, height = self._resolve_canvas_dimensions(base_context)
        node_specs = self._translate_from_context(base_context)

        svg_root = SVG(width=width, height=height, elements=[])
        svg_nodes = [self._spec_to_svg(spec) for spec in node_specs]
        svg_root.elements = (svg_root.elements or []) + svg_nodes
        return svg_root.as_str()

    def register_renderer(self, element_type: str, renderer: ElementRenderer) -> None:
        """Register or override the renderer used for a specific element type."""

        if not isinstance(element_type, str) or not element_type:
            raise ValueError("Element type must be provided as a non-empty string")
        if not callable(renderer):
            raise TypeError("Renderer must be callable")
        self._renderers[element_type.lower()] = renderer

    def register_renderers(self, renderers: Mapping[str, ElementRenderer]) -> None:
        """Register multiple renderers in a single call."""

        for key, handler in renderers.items():
            self.register_renderer(key, handler)

    def _translate_from_context(self, base_context: Mapping[str, Any]) -> list[NodeSpec]:
        nodes: list[NodeSpec] = []
        for element in self._template.template:
            nodes.extend(self._render_to_nodes(element, base_context))
        return nodes

    def _resolve_canvas_dimensions(self, context: Mapping[str, Any]) -> tuple[float, float]:
        width = self._template.canvas.width
        height = self._template.canvas.height
        canvas_context = context.get("canvas")
        if isinstance(canvas_context, Mapping):
            try:
                width = float(canvas_context["width"])
                height = float(canvas_context["height"])
            except (KeyError, TypeError, ValueError):
                width = self._template.canvas.width
                height = self._template.canvas.height
        return width, height

    def _render_to_nodes(
        self,
        element: ElementSpec,
        context: Mapping[str, Any],
        *,
        ignore_repeat: bool = False,
    ) -> list[NodeSpec]:
        if element.repeat and not ignore_repeat:
            items, total = self._resolve_repeat_items(element.repeat, context)
            rendered: list[NodeSpec] = []
            for index, item in enumerate(items):
                frame = self._build_repeat_context(context, element.repeat, item, index, total)
                rendered.extend(self._render_to_nodes(element, frame, ignore_repeat=True))
            return rendered

        working_context = dict(context)
        if element.let:
            bindings = self._evaluate_bindings(element.let, working_context, label=f"element:{element.type}")
            accessible = self._make_accessible_bindings(bindings)
            working_context.update(accessible)
        child_nodes: list[NodeSpec] = []
        for child in element.children:
            child_nodes.extend(self._render_to_nodes(child, working_context))

        prepared_attributes = {
            key: fill_placeholders(value, working_context)
            for key, value in element.attributes.items()
        }
        text_value = fill_placeholders(element.text, working_context) if element.text is not None else None

        renderer = self._renderers.get(element.type.lower())
        if renderer is None:
            raise RenderError(f"Unsupported element type '{element.type}'")

        payload = RendererInput(
            type=element.type,
            attributes=prepared_attributes,
            text=text_value,
            children=tuple(child_nodes),
            spec=element,
        )

        try:
            outputs = renderer(payload, working_context)
        except RenderError:
            raise
        except Exception as exc:  # pragma: no cover - depends on custom renderer
            raise RenderError(f"Renderer for '{element.type}' failed: {exc}") from exc

        return self._normalise_renderer_outputs(outputs, element.type)

    def _normalise_renderer_outputs(self, outputs: Any, element_type: str) -> list[NodeSpec]:
        if outputs is None:
            return []
        if not isinstance(outputs, Sequence) or isinstance(outputs, (str, bytes)):
            raise RenderError(
                f"Renderer for '{element_type}' must return a sequence of node specifications"
            )
        resolved: list[NodeSpec] = []
        for index, candidate in enumerate(outputs):
            node = self._coerce_node_spec(candidate, f"{element_type}[{index}]")
            resolved.append(node)
        return resolved

    def _coerce_node_spec(self, candidate: Any, label: str) -> NodeSpec:
        if isinstance(candidate, Mapping):
            tag = candidate.get("type") or candidate.get("tag")
            if not isinstance(tag, str):
                raise RenderError(f"Renderer output '{label}' must declare a string 'type'")
            attributes_block = candidate.get("attributes") or {}
            if not isinstance(attributes_block, Mapping):
                raise RenderError(f"Renderer output '{label}.attributes' must be a mapping")
            children_block = candidate.get("children", [])
            children = self._coerce_children(children_block, f"{label}.children")
            node: NodeSpec = {
                "type": tag,
                "attributes": dict(attributes_block),
                "children": children,
            }
            if "text" in candidate and candidate["text"] is not None:
                node["text"] = str(candidate["text"])
            return node

        if isinstance(candidate, Sequence) and not isinstance(candidate, (str, bytes)):
            if not candidate:
                raise RenderError(f"Renderer output '{label}' must not be empty")
            tag = str(candidate[0])
            extras = list(candidate[1:])
            if len(extras) > 3:
                raise RenderError(
                    f"Renderer output '{label}' contains unexpected positional values"
                )

            attrs_block: Mapping[str, Any] | None = None
            text_value: str | None = None
            children_payload: Any | None = None

            for value in extras:
                if isinstance(value, Mapping):
                    if attrs_block is not None:
                        raise RenderError(
                            f"Renderer output '{label}' cannot declare multiple attribute blocks"
                        )
                    attrs_block = value
                    continue

                if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                    if children_payload is not None:
                        raise RenderError(
                            f"Renderer output '{label}' cannot declare multiple children blocks"
                        )
                    children_payload = value
                    continue

                if value is None:
                    if children_payload is not None:
                        raise RenderError(
                            f"Renderer output '{label}' cannot declare multiple children blocks"
                        )
                    children_payload = []
                    continue

                if text_value is not None:
                    raise RenderError(
                        f"Renderer output '{label}' cannot encode multiple text values"
                    )
                text_value = str(value)

            node: NodeSpec = {
                "type": tag,
                "attributes": dict(attrs_block or {}),
                "children": self._coerce_children(
                    children_payload if children_payload is not None else [],
                    f"{label}.children",
                ),
            }
            if text_value is not None:
                node["text"] = text_value
            return node

        raise RenderError(
            f"Renderer output '{label}' must be a mapping or sequence describing an element"
        )

    def _coerce_children(self, payload: Any, label: str) -> list[NodeSpec]:
        if payload in (None, []):
            return []
        if not isinstance(payload, Sequence) or isinstance(payload, (str, bytes)):
            raise RenderError(f"Renderer output '{label}' must be a sequence of child elements")
        children: list[NodeSpec] = []
        for index, child in enumerate(payload):
            children.append(self._coerce_node_spec(child, f"{label}[{index}]"))
        return children

    def _spec_to_svg(self, spec: NodeSpec) -> Any:
        element_type = spec.get("type")
        if not isinstance(element_type, str):
            raise RenderError("Renderer output is missing required 'type' value")
        factory = SUPPORTED_ELEMENTS.get(element_type.lower())
        if factory is None:
            raise RenderError(f"Unsupported element type '{element_type}'")

        raw_attributes = spec.get("attributes", {})
        if not isinstance(raw_attributes, Mapping):
            raise RenderError("Renderer output 'attributes' must be a mapping")

        param_names = _ELEMENT_PARAMETERS.get(element_type.lower(), set())
        prepared_attributes: dict[str, Any] = {}
        deferred_data: dict[str, Any] = {}
        extra_attributes: dict[str, Any] = {}

        for key, value in raw_attributes.items():
            if value is None:
                continue
            original_key = str(key)
            normalised_key = self._normalise_attribute_key(original_key)

            if normalised_key in {"data", "extra"} and isinstance(value, Mapping):
                prepared_attributes[normalised_key] = {
                    str(inner_key): self._stringify_attribute_value(inner_value)
                    for inner_key, inner_value in value.items()
                }
                continue

            if normalised_key in param_names:
                prepared_attributes[normalised_key] = self._stringify_attribute_value(value)
                continue

            if original_key.startswith("data-"):
                deferred_data[original_key.removeprefix("data-")] = self._stringify_attribute_value(value)
                continue

            extra_attributes[original_key] = self._stringify_attribute_value(value)

        if deferred_data:
            if "data" in param_names:
                existing_data = prepared_attributes.get("data")
                merged = dict(existing_data) if isinstance(existing_data, Mapping) else {}
                merged.update(deferred_data)
                prepared_attributes["data"] = merged
            else:
                extra_attributes.update({f"data-{key}": val for key, val in deferred_data.items()})

        if extra_attributes:
            if "extra" in param_names:
                existing_extra = prepared_attributes.get("extra")
                merged_extra = dict(existing_extra) if isinstance(existing_extra, Mapping) else {}
                merged_extra.update(extra_attributes)
                prepared_attributes["extra"] = merged_extra
            else:
                raise RenderError(
                    f"Element type '{element_type}' does not support arbitrary attributes {sorted(extra_attributes)}"
                )

        if factory in (Text, TSpan):
            text_value = self._stringify_text(spec.get("text"))
            node = factory(text=text_value, **prepared_attributes)
        else:
            node = factory(**prepared_attributes)
            text_payload = spec.get("text")
            if text_payload not in (None, ""):
                if hasattr(node, "elements"):
                    text_node = Text(text=self._stringify_text(text_payload))
                    existing = list(getattr(node, "elements", []) or [])
                    node.elements = existing + [text_node]
                else:
                    raise RenderError(
                        f"Element type '{element_type}' does not support embedded text content"
                    )

        children_payload = spec.get("children", [])
        if children_payload:
            if not hasattr(node, "elements"):
                raise RenderError(f"Element type '{element_type}' does not support nested children")
            child_nodes = [self._spec_to_svg(child) for child in children_payload]
            existing = list(getattr(node, "elements", []) or [])
            node.elements = existing + child_nodes

        return node

    @staticmethod
    def _stringify_attribute_value(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {
                str(key): InfogrooveRenderer._stringify_attribute_value(sub_value)
                for key, sub_value in value.items()
            }
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            return [InfogrooveRenderer._stringify_attribute_value(item) for item in value]
        if value is None:
            return ""
        return stringify(value)

    @staticmethod
    def _stringify_text(value: Any) -> str:
        if value is None:
            return ""
        return stringify(value)

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

    def _build_base_context(self, payload: Any) -> dict[str, Any]:
        context: dict[str, Any] = {}
        accessible_payload = ensure_accessible(payload)
        context["data"] = accessible_payload
        context["payload"] = accessible_payload

        primary_sequence: Sequence[Any] | None = None
        sequence_length: int | None = None

        if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes)):
            primary_sequence = payload
            sequence_length = len(payload)
            context["items"] = ensure_accessible(payload)
        elif isinstance(payload, Mapping):
            for key, value in payload.items():
                context[key] = ensure_accessible(value)
            default_items = payload.get("items")
            if isinstance(default_items, Sequence) and not isinstance(default_items, (str, bytes)):
                primary_sequence = default_items
                sequence_length = len(default_items)
                context.setdefault("items", ensure_accessible(default_items))

        metrics: dict[str, Any] = {}
        values: list[float] = []
        if primary_sequence is not None:
            for item in primary_sequence:
                if isinstance(item, Mapping):
                    candidate = item.get("value")
                    if isinstance(candidate, (int, float)):
                        values.append(candidate)

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

        if sequence_length is not None:
            metrics.setdefault("total", sequence_length)
            metrics.setdefault("count", sequence_length)

        if metrics:
            context.update(metrics)

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
            if PLACEHOLDER_PATTERN.search(value):
                match = PLACEHOLDER_PATTERN.fullmatch(value.strip())
                if match:
                    token = match.group(1).strip()
                    try:
                        return resolve_path(overlay, token)
                    except KeyError:
                        engine = FormulaEngine({name: token})
                        scope = _FormulaScope(overlay, base_context, resolved, bindings, name)
                        try:
                            return engine.evaluate(scope)[name]
                        except FormulaEvaluationError:
                            return value
                try:
                    return fill_placeholders(value, overlay)
                except KeyError:
                    return value
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

    def _validate_data(self, data: Any) -> Any:
        minimum, maximum = self._template.expected_range()
        if isinstance(data, Sequence) and not isinstance(data, (str, bytes)):
            if not all(isinstance(item, Mapping) for item in data):
                raise DataValidationError("Each data item must be a mapping")
            if minimum is not None or maximum is not None:
                count = len(data)
                if minimum is not None and count < minimum:
                    raise DataValidationError(f"Template requires at least {minimum} items (received {count})")
                if maximum is not None and count > maximum:
                    raise DataValidationError(f"Template accepts at most {maximum} items (received {count})")

        schema = self._template.schema
        if schema is not None:
            try:
                validate_jsonschema(data, schema)
            except JSONSchemaValidationError as exc:
                raise DataValidationError(
                    f"Input data does not satisfy the template schema: {exc.message}"
                ) from exc
            except SchemaError as exc:
                raise DataValidationError("Template schema definition is invalid") from exc
        return data

    @staticmethod
    def _normalise_attribute_key(key: str) -> str:
        key = key.replace("-", "_")
        if key == "class":
            return "class_"
        if any(ch.isupper() for ch in key):
            return to_snake_case(key)
        return key
