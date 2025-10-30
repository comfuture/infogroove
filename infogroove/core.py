"""Core helpers for building Infogroove renderers."""

from __future__ import annotations

from .models import TemplateSpec
from .renderer import InfogrooveRenderer


class Infogroove:
    """Factory wrapper that produces ``InfogrooveRenderer`` instances."""

    def __new__(cls, template: TemplateSpec) -> InfogrooveRenderer:
        return InfogrooveRenderer(template)
