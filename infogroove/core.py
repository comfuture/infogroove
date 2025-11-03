"""Core helpers for building Infogroove renderers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .loader import _parse_template
from .models import TemplateSpec
from .renderer import ElementRenderer, InfogrooveRenderer


class Infogroove:
    """Factory wrapper that produces ``InfogrooveRenderer`` instances."""

    def __new__(
        cls,
        template: TemplateSpec | Mapping[str, Any],
        *,
        renderers: Mapping[str, ElementRenderer] | None = None,
    ) -> InfogrooveRenderer:
        if isinstance(template, TemplateSpec):
            return InfogrooveRenderer(template, renderers=renderers)
        if isinstance(template, Mapping):
            spec = _parse_template(Path("<inline>"), template)
            return InfogrooveRenderer(spec, renderers=renderers)
        raise TypeError("Infogroove expects a TemplateSpec or mapping definition")
