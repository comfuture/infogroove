"""Formula evaluation powered by sympy with safe fallbacks."""

from __future__ import annotations

from collections import ChainMap
from typing import Any, Mapping

import sympy
from sympy.core.sympify import SympifyError

from .exceptions import FormulaEvaluationError
from .utils import default_eval_locals, prepare_expression_for_sympy


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
        """Evaluate a single formula, preferring sympy but falling back to Python."""

        sanitized, sympy_locals = prepare_expression_for_sympy(expression, context)
        sympy_error: Exception | None = None
        try:
            value = sympy.sympify(sanitized, locals=sympy_locals)
            if isinstance(value, sympy.Basic):
                if value.free_symbols:
                    raise SympifyError("Unresolved symbols")
                value = value.evalf() if value.is_real else value
            result = _coerce_sympy_result(value)
            if result is not None:
                return result
        except Exception as exc:  # pragma: no cover - depends on sympy runtime
            sympy_error = exc

        try:
            safe_locals = default_eval_locals(context, expression=expression)
            raw_result = eval(expression, {"__builtins__": {}}, safe_locals)
            return _unwrap_accessible(raw_result)
        except Exception as python_exc:
            raise FormulaEvaluationError(
                f"Failed to evaluate formula '{name}'"
            ) from (python_exc if sympy_error is None else sympy_error)


def _coerce_sympy_result(value: Any) -> Any | None:
    """Convert sympy results to pristine Python primitives when possible."""

    if isinstance(value, sympy.Integer):
        return int(value)
    if isinstance(value, sympy.Float):
        return float(value)
    if isinstance(value, sympy.Rational):
        return float(value)
    if isinstance(value, sympy.Basic):
        if value.is_Number:
            return float(value)
        return None
    return value


def _unwrap_accessible(value: Any) -> Any:
    """Extract raw values from mapped adapters used during evaluation."""

    if hasattr(value, "_mapping"):
        return {key: _unwrap_accessible(sub) for key, sub in value.items()}
    if hasattr(value, "_values"):
        return [_unwrap_accessible(sub) for sub in value]
    return value
