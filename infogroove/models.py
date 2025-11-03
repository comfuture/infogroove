"""Typed data structures that describe Infogroove templates."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, MutableMapping

from .utils import derive_schema_item_bounds


@dataclass(slots=True)
class CanvasSpec:
    """Pixel dimensions for the SVG viewport."""

    width: float
    height: float


@dataclass(slots=True)
class RepeatSpec:
    """Configuration for rendering an element repeatedly over a data collection."""

    items: str
    alias: str
    let: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ElementSpec:
    """Declarative description of a single SVG element."""

    type: str
    attributes: MutableMapping[str, str] = field(default_factory=dict)
    text: str | None = None
    repeat: RepeatSpec | None = None
    let: Mapping[str, Any] = field(default_factory=dict)
    children: list["ElementSpec"] = field(default_factory=list)


@dataclass(slots=True)
class TemplateSpec:
    """In-memory representation of a parsed template definition."""

    source_path: Path
    canvas: CanvasSpec
    template: list[ElementSpec]
    properties: Mapping[str, Any] = field(default_factory=dict)
    schema: Mapping[str, Any] | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def expected_range(self) -> tuple[int | None, int | None]:
        """Return the expected minimum and maximum item counts for consumers."""

        if self.schema is None:
            return (None, None)
        return derive_schema_item_bounds(self.schema)
