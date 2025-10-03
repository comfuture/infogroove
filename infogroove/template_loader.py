"""Loading and validating IGD template files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .exceptions import TemplateError
from .models import ElementSpec, ScreenSpec, TemplateSpec


def load_template(path: str | Path) -> TemplateSpec:
    """Load and parse an IGD template file from disk."""

    template_path = Path(path)
    try:
        raw_text = template_path.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - filesystem dependent
        raise TemplateError(f"Unable to read template '{template_path}'") from exc
    try:
        payload: Mapping[str, Any] = json.loads(raw_text)
    except json.JSONDecodeError as exc:  # pragma: no cover - depends on input
        raise TemplateError(f"Template '{template_path}' is not valid JSON") from exc
    return _parse_template(template_path, payload)


def _parse_template(path: Path, payload: Mapping[str, Any]) -> TemplateSpec:
    """Convert JSON data into a strongly typed :class:`TemplateSpec`."""

    screen_block = payload.get("screen") or {}
    if not isinstance(screen_block, Mapping):
        raise TemplateError("'screen' must be a mapping with width and height")
    width = screen_block.get("width") or payload.get("screenWidth")
    height = screen_block.get("height") or payload.get("screenHeight")
    if width is None or height is None:
        raise TemplateError("Both screen width and height must be provided")
    screen = ScreenSpec(width=float(width), height=float(height))

    elements_raw = payload.get("elements", [])
    if not isinstance(elements_raw, list):
        raise TemplateError("'elements' must be provided as a list")
    elements = [_parse_element(entry) for entry in elements_raw]

    formulas = payload.get("formulas", {})
    if not isinstance(formulas, Mapping):
        raise TemplateError("'formulas' must be a mapping of name to expression")
    styles = payload.get("styles", {})
    if not isinstance(styles, Mapping):
        raise TemplateError("'styles' must be a mapping when provided")

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
        screen=screen,
        elements=elements,
        formulas=dict(formulas),
        styles=dict(styles),
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
    scope = entry.get("scope", "item")
    if scope not in {"item", "canvas"}:
        raise TemplateError("Element scope must be either 'item' or 'canvas'")
    attributes = {key: str(value) for key, value in attributes_block.items()}
    return ElementSpec(type=element_type, attributes=attributes, text=text, scope=scope)
