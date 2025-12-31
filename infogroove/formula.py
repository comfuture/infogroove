"""Formula evaluation powered by sympy with safe fallbacks."""

from __future__ import annotations

from collections import ChainMap
from collections.abc import Mapping, Sequence
from typing import Any

import sympy
from sympy.core.sympify import SympifyError

from .exceptions import FormulaEvaluationError
from .utils import _unwrap_accessible, prepare_expression_for_sympy, safe_ast_eval


class FormulaEngine:
    """Compile and evaluate template formulas within a controlled namespace."""

    def __init__(self, formulas: Mapping[str, str]):
        self._formulas = dict(formulas)

    def evaluate(self, context: Mapping[str, Any]) -> dict[str, Any]:
        """Evaluate every formula with the provided context."""

        results: dict[str, Any] = {}
        for name, expression in self._formulas.items():
            scope = ChainMap(results, context)
            results[name] = self._evaluate_single(name, expression, scope)
        return results

    def _evaluate_single(self, name: str, expression: str, context: Mapping[str, Any]) -> Any:
        """Evaluate a single formula, preferring sympy but falling back to safe AST eval."""

        return evaluate_expression(expression, context, label=f"formula '{name}'")


def evaluate_expression(
    expression: str,
    context: Mapping[str, Any],
    *,
    label: str | None = None,
) -> Any:
    """Evaluate a template expression with sympy first, then a safe AST fallback."""

    sanitized, sympy_locals = prepare_expression_for_sympy(expression, context)
    try:
        value = sympy.sympify(sanitized, locals=sympy_locals)
        if isinstance(value, sympy.Basic) and value.free_symbols:
            raise SympifyError("Unresolved symbols")
        result = _coerce_sympy_result(value)
        if result is not None:
            return result
    except Exception:  # pragma: no cover - depends on sympy runtime
        pass

    try:
        raw_result = safe_ast_eval(expression, context)
        return _normalise_value(raw_result)
    except Exception as ast_exc:
        message = f"Failed to evaluate expression '{expression}'"
        if label:
            message = f"{label}: {message}"
        raise FormulaEvaluationError(message) from ast_exc


def _coerce_integral(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _normalise_value(value: Any) -> Any:
    value = _unwrap_accessible(value)
    if isinstance(value, Mapping):
        return {key: _normalise_value(sub) for key, sub in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [_normalise_value(item) for item in value]
    return _coerce_integral(value)


def _coerce_sympy_result(value: Any) -> Any | None:
    """Convert sympy results to pristine Python primitives when possible."""

    if isinstance(value, sympy.Integer):
        return int(value)
    if isinstance(value, sympy.Rational):
        return int(value.p) if value.q == 1 else float(value)
    if isinstance(value, sympy.Float):
        raw = float(value)
        return int(raw) if raw.is_integer() else raw
    if isinstance(value, sympy.Basic):
        if value.is_Number:
            raw = float(value)
            return int(raw) if raw.is_integer() else raw
        return None
    return _coerce_integral(value)
