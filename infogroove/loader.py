"""Loading and validating template definition files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import IO, Any, Mapping

from .exceptions import TemplateError
from .models import CanvasSpec, ElementSpec, RepeatSpec, TemplateSpec
from .renderer import InfogrooveRenderer


def load(handle: IO[str]) -> InfogrooveRenderer:
    """Load an infographic definition from a text stream."""

    raw_text = handle.read()
    source_name = getattr(handle, "name", None)
    source_path = Path(source_name) if isinstance(source_name, str) and source_name else None
    template = _template_from_text(raw_text, source_path)
    return InfogrooveRenderer(template)


def loads(data: str, *, source: str | Path | None = None) -> InfogrooveRenderer:
    """Load an infographic definition from a JSON string."""

    source_path = Path(source) if source is not None else None
    template = _template_from_text(data, source_path)
    return InfogrooveRenderer(template)


def load_path(path: str | Path) -> InfogrooveRenderer:
    """Load and parse a template definition from a filesystem path."""

    template_path = Path(path)
    try:
        raw_text = template_path.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - filesystem dependent
        raise TemplateError(f"Unable to read template '{template_path}'") from exc
    template = _template_from_text(raw_text, template_path)
    return InfogrooveRenderer(template)


def _template_from_text(raw_text: str, source: Path | None) -> TemplateSpec:
    """Convert raw JSON text into a TemplateSpec, preserving source metadata."""

    label = str(source) if source is not None else "<memory>"
    try:
        payload: Mapping[str, Any] = json.loads(raw_text)
    except json.JSONDecodeError as exc:  # pragma: no cover - depends on input
        raise TemplateError(f"Template '{label}' is not valid JSON") from exc
    source_path = source or Path(label)
    return _parse_template(source_path, payload)


def _parse_template(path: Path, payload: Mapping[str, Any]) -> TemplateSpec:
    """Convert JSON data into a strongly typed :class:`TemplateSpec`."""

    if "styles" in payload:
        raise TemplateError("'styles' is no longer supported; move values under 'properties'")
    if "variables" in payload:
        raise TemplateError("'variables' is no longer supported; move values under 'properties'")
    if "let" in payload:
        raise TemplateError("'let' has been renamed to 'properties'")
    if "elements" in payload:
        raise TemplateError("'elements' has been renamed to 'template'")

    properties_block = payload.get("properties")
    if not isinstance(properties_block, Mapping):
        raise TemplateError("'properties' must be a mapping containing template bindings")
    properties = dict(properties_block)

    canvas_block = properties.get("canvas")
    if not isinstance(canvas_block, Mapping):
        raise TemplateError("'properties.canvas' must be a mapping with width and height")
    width = canvas_block.get("width")
    height = canvas_block.get("height")
    if width is None or height is None:
        raise TemplateError("Both canvas width and height must be provided")
    try:
        canvas_width = float(width)
        canvas_height = float(height)
    except (TypeError, ValueError) as exc:  # pragma: no cover - defensive mapping
        raise TemplateError("Canvas width and height must be numeric") from exc

    canvas = CanvasSpec(width=canvas_width, height=canvas_height)
    canvas_map = dict(canvas_block)
    canvas_map["width"] = canvas.width
    canvas_map["height"] = canvas.height
    properties["canvas"] = canvas_map

    template_block = payload.get("template", [])
    if not isinstance(template_block, list):
        raise TemplateError("'template' must be provided as a list of element mappings")
    template = [_parse_element(entry) for entry in template_block]

    range_block = payload.get("numElementsRange")
    range_tuple: tuple[int, int] | None = None
    if isinstance(range_block, list) and len(range_block) == 2:
        range_tuple = (int(range_block[0]), int(range_block[1]))

    schema_block = payload.get("schema") if isinstance(payload.get("schema"), Mapping) else None

    metadata = {
        key: payload[key]
        for key in ("name", "description", "version")
        if key in payload
    }

    return TemplateSpec(
        source_path=path,
        canvas=canvas,
        template=template,
        properties=dict(properties),
        num_elements_range=range_tuple,
        schema=schema_block,  # type: ignore[arg-type]
        metadata=metadata,
    )


def _parse_element(entry: Any) -> ElementSpec:
    """Convert a raw element definition into an :class:`ElementSpec`."""

    if not isinstance(entry, Mapping):
        raise TemplateError("Each element must be declared as a mapping")
    element_type = entry.get("type")
    if not isinstance(element_type, str):
        raise TemplateError("Element definitions require a string 'type'")
    attributes_block = entry.get("attributes", {})
    if not isinstance(attributes_block, Mapping):
        raise TemplateError("Element attributes must be a mapping")
    text = entry.get("text")
    if text is not None and not isinstance(text, str):
        raise TemplateError("Element text must be a string when provided")
    attributes = {key: str(value) for key, value in attributes_block.items()}

    if "scope" in entry:
        raise TemplateError("'scope' is no longer supported; use 'repeat' to control iteration")

    repeat_block = entry.get("repeat")
    repeat: RepeatSpec | None = None
    if repeat_block is not None:
        if not isinstance(repeat_block, Mapping):
            raise TemplateError("Element 'repeat' declarations must be provided as a mapping")
        items = repeat_block.get("items")
        alias = repeat_block.get("as")
        if not isinstance(items, str) or not items:
            raise TemplateError("Repeat bindings require a string 'items' path")
        if not isinstance(alias, str) or not alias:
            raise TemplateError("Repeat bindings require a string 'as' alias")
        if "index" in repeat_block:
            raise TemplateError("Repeat 'index' is no longer supported; use __index__ helper variables")
        extra_keys = {key for key in repeat_block if key not in {"items", "as"}}
        if extra_keys:
            raise TemplateError("Repeat declarations only accept 'items' and 'as'; move derived values under the element 'let' block")
        repeat = RepeatSpec(items=items, alias=alias)

    let_block = entry.get("let", {})
    if let_block is None:
        let_block = {}
    if not isinstance(let_block, Mapping):
        raise TemplateError("Element 'let' bindings must be declared as a mapping when provided")

    children_block = entry.get("children", [])
    if children_block is None:
        children = []
    elif isinstance(children_block, list):
        children = [_parse_element(child) for child in children_block]
    else:
        raise TemplateError("Element children must be declared as a list when provided")

    return ElementSpec(type=element_type, attributes=attributes, text=text, repeat=repeat, let=dict(let_block), children=children)
