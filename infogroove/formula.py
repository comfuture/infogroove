"""Formula evaluation powered by sympy with safe fallbacks."""

from __future__ import annotations

import ast
import re
from collections import ChainMap
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import sympy
from sympy.core.sympify import SympifyError

from .exceptions import FormulaEvaluationError
from .utils import (
    UnsafeExpressionError,
    find_dotted_tokens,
    find_identifier_tokens,
    resolve_path,
    safe_ast_eval,
    unwrap_accessible,
)

_EXPRESSION_CACHE_SIZE = 1024


@dataclass(frozen=True)
class _SympyPlan:
    dotted_tokens: tuple[str, ...]
    identifier_tokens: tuple[str, ...]
    token_pattern: re.Pattern[str] | None


@dataclass(frozen=True)
class _AstPlan:
    tree: ast.Expression | None
    syntax_error: SyntaxError | None
    identifier_tokens: tuple[str, ...]


def _compile_token_pattern(tokens: tuple[str, ...]) -> re.Pattern[str] | None:
    if not tokens:
        return None
    escaped = "|".join(re.escape(token) for token in sorted(tokens, key=len, reverse=True))
    return re.compile(escaped)


@lru_cache(maxsize=_EXPRESSION_CACHE_SIZE)
def _identifier_tokens(expression: str) -> tuple[str, ...]:
    return tuple(find_identifier_tokens(expression))


@lru_cache(maxsize=_EXPRESSION_CACHE_SIZE)
def _dotted_tokens(expression: str) -> tuple[str, ...]:
    return tuple(find_dotted_tokens(expression))


@lru_cache(maxsize=_EXPRESSION_CACHE_SIZE)
def _compile_sympy_plan(expression: str) -> _SympyPlan:
    dotted = _dotted_tokens(expression)
    identifiers = _identifier_tokens(expression)
    pattern = _compile_token_pattern(dotted)
    return _SympyPlan(dotted_tokens=dotted, identifier_tokens=identifiers, token_pattern=pattern)


@lru_cache(maxsize=_EXPRESSION_CACHE_SIZE)
def _compile_ast_plan(expression: str) -> _AstPlan:
    identifiers = _identifier_tokens(expression)
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        return _AstPlan(tree=None, syntax_error=exc, identifier_tokens=identifiers)
    return _AstPlan(tree=tree, syntax_error=None, identifier_tokens=identifiers)


def _prepare_sympy_expression(
    expression: str,
    context: Mapping[str, Any],
    plan: _SympyPlan,
) -> tuple[str, dict[str, Any]]:
    replacements: dict[str, str] = {}
    sympy_locals: dict[str, Any] = {}
    for token in plan.dotted_tokens:
        root = token.split(".", 1)[0]
        if root not in context:
            continue
        try:
            value = resolve_path(context, token)
        except KeyError:
            continue
        placeholder = f"__v{len(replacements)}"
        replacements[token] = placeholder
        sympy_locals[placeholder] = value
    if plan.token_pattern is None:
        sanitized = expression
    else:
        sanitized = plan.token_pattern.sub(
            lambda match: replacements.get(match.group(0), match.group(0)),
            expression,
        )
    for name in plan.identifier_tokens:
        if not name.isidentifier():
            continue
        try:
            value = context[name]
        except KeyError:
            continue
        sympy_locals.setdefault(name, value)
    return sanitized, sympy_locals


def _clear_expression_caches() -> None:
    _identifier_tokens.cache_clear()
    _dotted_tokens.cache_clear()
    _compile_sympy_plan.cache_clear()
    _compile_ast_plan.cache_clear()


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

    sympy_plan = _compile_sympy_plan(expression)
    sanitized, sympy_locals = _prepare_sympy_expression(expression, context, sympy_plan)
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
        ast_plan = _compile_ast_plan(expression)
        if ast_plan.syntax_error is not None:
            raise UnsafeExpressionError("Invalid expression syntax") from ast_plan.syntax_error
        raw_result = safe_ast_eval(
            expression,
            context,
            compiled=ast_plan.tree,
            identifiers=ast_plan.identifier_tokens,
        )
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
    value = unwrap_accessible(value)
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
