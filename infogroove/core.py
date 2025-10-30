"""Core helpers for building Infogroove renderers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .loader import _parse_template
from .models import TemplateSpec
from .renderer import InfogrooveRenderer


class Infogroove:
    """Factory wrapper that produces ``InfogrooveRenderer`` instances."""

    def __new__(cls, template: TemplateSpec | Mapping[str, Any]) -> InfogrooveRenderer:
        if isinstance(template, TemplateSpec):
            return InfogrooveRenderer(template)
        if isinstance(template, Mapping):
            spec = _parse_template(Path("<inline>"), template)
            return InfogrooveRenderer(spec)
        raise TypeError("Infogroove expects a TemplateSpec or mapping definition")
