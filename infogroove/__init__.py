"""Infogroove – programmable infographic generation utilities."""

from __future__ import annotations

from importlib import metadata
from typing import Mapping, Sequence

from .renderer import InfographicRenderer
from .template_loader import load_template

__all__ = [
    "InfographicRenderer",
    "load_template",
    "get_version",
    "render_svg",
]


def get_version() -> str:
    """Return the installed package version or ``"0.0.0"`` when unavailable."""

    try:
        return metadata.version("infogroove")
    except metadata.PackageNotFoundError:  # pragma: no cover - dev mode fallback
        return "0.0.0"


def render_svg(template_path: str, data: Sequence[Mapping[str, object]]) -> str:
    """Convenience helper to load a template and render it in a single call."""

    template = load_template(template_path)
    renderer = InfographicRenderer(template)
    return renderer.render(data)
