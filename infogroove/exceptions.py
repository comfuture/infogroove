"""Custom exception types for the Infogroove rendering pipeline."""

from __future__ import annotations


class TemplateError(Exception):
    """Raised when a template file cannot be parsed or fails structural validation."""


class DataValidationError(Exception):
    """Raised when runtime input data does not satisfy the template's requirements."""


class FormulaEvaluationError(Exception):
    """Raised when a formula cannot be evaluated with the provided context."""


class RenderError(Exception):
    """Raised when the renderer fails to materialise SVG elements from the template."""
