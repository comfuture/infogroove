"""Typed data structures that describe Infogroove templates."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Mapping, MutableMapping

Scope = Literal["item", "canvas"]


@dataclass(slots=True)
class ScreenSpec:
    """Pixel dimensions for the SVG viewport."""

    width: float
    height: float


@dataclass(slots=True)
class ElementSpec:
    """Declarative description of a single SVG element."""

    type: str
    attributes: MutableMapping[str, str] = field(default_factory=dict)
    text: str | None = None
    scope: Scope = "item"


@dataclass(slots=True)
class TemplateSpec:
    """In-memory representation of a parsed IGD template."""

    source_path: Path
    screen: ScreenSpec
    elements: list[ElementSpec]
    formulas: Mapping[str, str]
    styles: Mapping[str, Any] = field(default_factory=dict)
    num_elements_range: tuple[int, int] | None = None
    schema: Mapping[str, Any] | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def expected_range(self) -> tuple[int | None, int | None]:
        """Return the expected minimum and maximum item counts for consumers."""

        if self.num_elements_range is None:
            return (None, None)
        return self.num_elements_range
