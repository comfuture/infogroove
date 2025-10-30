"""Shared utility helpers used across the Infogroove package."""

from __future__ import annotations

import io
import math
import random
import re
import textwrap
import tokenize
from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Iterator

PLACEHOLDER_PATTERN = re.compile(r"\{([^{}]+)\}")


@dataclass(slots=True)
class SequenceAdapter(Sequence[Any]):
    """Read-only adapter that exposes helper attributes for list-like data."""

    _values: Sequence[Any]

    def __iter__(self) -> Iterator[Any]:  # type: ignore[override]
        for value in self._values:
            yield ensure_accessible(value)

    def __getitem__(self, index: int) -> Any:  # type: ignore[override]
        return ensure_accessible(self._values[index])

    def __len__(self) -> int:  # type: ignore[override]
        return len(self._values)

    @property
    def length(self) -> int:
        """Expose the Pythonic length for compatibility with template formulas."""

        return len(self._values)


@dataclass(slots=True)
class MappingAdapter(Mapping[str, Any]):
    """Mapping wrapper that supports dot-attribute access semantics."""

    _mapping: Mapping[str, Any]

    def __getitem__(self, key: str) -> Any:
        return ensure_accessible(self._mapping[key])

    def __iter__(self) -> Iterator[str]:
        return iter(self._mapping)

    def __len__(self) -> int:
        return len(self._mapping)

    def __getattr__(self, item: str) -> Any:
        if item == "length":
            return len(self._mapping)
        try:
            return self.__getitem__(item)
        except KeyError as exc:  # pragma: no cover - mirrors dict lookup
            raise AttributeError(item) from exc


def ensure_accessible(value: Any) -> Any:
    """Wrap mappings and sequences so template authors can use dotted lookups."""

    if isinstance(value, Mapping) and not isinstance(value, MappingAdapter):
        return MappingAdapter(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, SequenceAdapter)):
        return SequenceAdapter(value)
    return value


def tokenize_path(expression: str) -> list[str]:
    """Split a dotted and bracketed path into individual navigation tokens."""

    tokens: list[str] = []
    buffer: list[str] = []
    index_buffer: list[str] = []
    in_index = False
    for char in expression:
        if in_index:
            if char == "]":
                tokens.append("".join(index_buffer).strip("'\" "))
                index_buffer.clear()
                in_index = False
            else:
                index_buffer.append(char)
            continue
        if char == ".":
            if buffer:
                tokens.append("".join(buffer))
                buffer.clear()
            continue
        if char == "[":
            if buffer:
                tokens.append("".join(buffer))
                buffer.clear()
            in_index = True
            continue
        buffer.append(char)
    if buffer:
        tokens.append("".join(buffer))
    return [token for token in tokens if token]


def resolve_path(context: Mapping[str, Any], path: str) -> Any:
    """Resolve a dotted path against a nested mapping/sequence context."""

    tokens = tokenize_path(path)
    current: Any = context
    for idx, token in enumerate(tokens):
        is_last = idx == len(tokens) - 1
        if token == "length" and hasattr(current, "__len__"):
            return len(current)
        if isinstance(current, MappingAdapter):
            current = current[token]
            continue
        if isinstance(current, Mapping):
            if token in current:
                current = current[token]
                continue
            snake = to_snake_case(token)
            camel = to_camel_case(token)
            for candidate in (snake, camel):
                if candidate in current:
                    current = current[candidate]
                    break
            else:
                raise KeyError(token)
            continue
        if isinstance(current, SequenceAdapter):
            current = current[int(token)] if token.isdigit() else getattr(current, token)
            continue
        if isinstance(current, Sequence) and not isinstance(current, (str, bytes)):
            if token.isdigit():
                current = current[int(token)]
                continue
            if token == "length":
                return len(current)
            raise KeyError(token)
        try:
            current = getattr(current, token)
        except AttributeError as exc:  # pragma: no cover - defensive fallback
            raise KeyError(token) from exc
        if callable(current) and is_last:
            current = current()
    return current


def to_snake_case(text: str) -> str:
    """Convert camelCase or PascalCase strings into snake_case names."""
    return re.sub(r"([A-Z])", lambda match: "_" + match.group(1).lower(), text).lstrip("_")


def to_camel_case(text: str) -> str:
    """Convert snake_case strings into lower camel-case equivalents."""
    parts = text.split("_")
    return parts[0] + "".join(piece.title() for piece in parts[1:]) if parts else text


def find_dotted_tokens(expression: str) -> list[str]:
    """Return dotted tokens discovered via lexical scanning of an expression."""

    dotted: list[str] = []
    sequence: list[str] = []
    reader = io.StringIO(expression).readline
    for token in tokenize.generate_tokens(reader):
        tok_type, tok_string = token.type, token.string
        if tok_type == tokenize.NAME:
            sequence.append(tok_string)
            continue
        if tok_type == tokenize.OP and tok_string == ".":
            sequence.append(tok_string)
            continue
        if len(sequence) >= 3 and "." in sequence:
            dotted.append("".join(sequence))
        sequence = []
    if len(sequence) >= 3 and "." in sequence:
        dotted.append("".join(sequence))
    # Preserve order while removing duplicates.
    return list(dict.fromkeys(dotted))


def replace_tokens(expression: str, replacements: Mapping[str, str]) -> str:
    """Replace many tokens in one pass while preventing partial replacements."""

    if not replacements:
        return expression
    pattern = re.compile("|".join(re.escape(token) for token in sorted(replacements, key=len, reverse=True)))
    return pattern.sub(lambda match: replacements[match.group(0)], expression)


def prepare_expression_for_sympy(expression: str, context: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    """Produce a sympy-friendly expression and locals from template context."""

    tokens = find_dotted_tokens(expression)
    replacements: dict[str, str] = {}
    sympy_locals: dict[str, Any] = {}
    for token in tokens:
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
    sanitized = replace_tokens(expression, replacements)
    for key, value in context.items():
        if isinstance(key, str) and key.isidentifier():
            sympy_locals.setdefault(key, value)
    return sanitized, sympy_locals


def default_eval_locals(context: Mapping[str, Any]) -> dict[str, Any]:
    """Build a safe evaluation namespace for Python's :func:`eval`."""

    safe_locals: dict[str, Any] = {
        "abs": abs,
        "min": min,
        "max": max,
        "round": round,
        "len": len,
        "sum": sum,
        "int": int,
        "float": float,
        "str": str,
    }
    safe_locals.update({key: ensure_accessible(value) for key, value in context.items()})
    safe_locals.setdefault("math", math)
    safe_locals.setdefault("random", random)
    safe_locals.setdefault("textwrap", textwrap)
    safe_locals.setdefault(
        "Math",
        SimpleNamespace(
            floor=math.floor,
            ceil=math.ceil,
            sin=math.sin,
            cos=math.cos,
            tan=math.tan,
            sqrt=math.sqrt,
            pow=math.pow,
            pi=math.pi,
            tau=math.tau,
            random=random.random,
        ),
    )
    return safe_locals


def fill_placeholders(template: str, context: Mapping[str, Any]) -> str:
    """Inject context values into ``{placeholder}`` slots within a template string."""

    def _replacement(match: re.Match[str]) -> str:
        token = match.group(1).strip()
        value = resolve_path(context, token)
        return "" if value is None else str(value)

    return PLACEHOLDER_PATTERN.sub(_replacement, template)
