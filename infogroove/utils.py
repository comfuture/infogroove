"""Shared utility helpers used across the Infogroove package."""

from __future__ import annotations

import ast
import io
import keyword
import math
import random
import re
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


def unwrap_accessible(value: Any) -> Any:
    """Convert Mapping/Sequence adapters back to built-in container types."""

    if isinstance(value, MappingAdapter):
        return {key: unwrap_accessible(value[key]) for key in value}
    if isinstance(value, SequenceAdapter):
        return [unwrap_accessible(item) for item in value]
    return value


_unwrap_accessible = unwrap_accessible


def stringify(value: Any) -> str:
    """Convert scalars into user-friendly strings for placeholder expansion."""

    return str(value)


def derive_schema_item_bounds(schema: Mapping[str, Any]) -> tuple[int | None, int | None]:
    """Return ``(minItems, maxItems)`` for a JSON Schema array definition when available."""

    type_decl = schema.get("type")
    if _schema_may_be_array(type_decl) or "minItems" in schema or "maxItems" in schema:
        min_value = _coerce_non_negative_int(schema.get("minItems"))
        max_value = _coerce_non_negative_int(schema.get("maxItems"))
        return (min_value, max_value)

    if isinstance(type_decl, str) and type_decl == "object":
        properties = schema.get("properties")
        if isinstance(properties, Mapping):
            for key in ("items", "data", "values"):
                candidate = properties.get(key)
                if isinstance(candidate, Mapping):
                    bounds = derive_schema_item_bounds(candidate)
                    if bounds != (None, None):
                        return bounds
            for candidate in properties.values():
                if isinstance(candidate, Mapping):
                    bounds = derive_schema_item_bounds(candidate)
                    if bounds != (None, None):
                        return bounds

    return (None, None)


def _schema_may_be_array(type_decl: Any) -> bool:
    if isinstance(type_decl, str):
        return type_decl == "array"
    if isinstance(type_decl, Sequence) and not isinstance(type_decl, (str, bytes)):
        return any(item == "array" for item in type_decl if isinstance(item, str))
    return False


def _coerce_non_negative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float) and value.is_integer() and value >= 0:
        return int(value)
    return None


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
            if token in current:
                current = current[token]
                continue
            raise KeyError(token)
        if isinstance(current, Mapping):
            if token in current:
                current = current[token]
                continue
            raise KeyError(token)
        if isinstance(current, SequenceAdapter):
            if token.isdigit():
                current = current[int(token)]
                continue
            if token == "length":
                return len(current)
            raise KeyError(token)
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
    return current


class UnsafeExpressionError(ValueError):
    """Raised when a template expression includes unsupported syntax."""


_SAFE_BINOPS: dict[type[ast.operator], Any] = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.FloorDiv: lambda a, b: a // b,
    ast.Mod: lambda a, b: a % b,
    ast.Pow: lambda a, b: a**b,
}

_SAFE_UNARYOPS: dict[type[ast.unaryop], Any] = {
    ast.UAdd: lambda a: +a,
    ast.USub: lambda a: -a,
    ast.Not: lambda a: not a,
}

_SAFE_CMP_OPS: dict[type[ast.cmpop], Any] = {
    ast.Eq: lambda a, b: a == b,
    ast.NotEq: lambda a, b: a != b,
    ast.Lt: lambda a, b: a < b,
    ast.LtE: lambda a, b: a <= b,
    ast.Gt: lambda a, b: a > b,
    ast.GtE: lambda a, b: a >= b,
    ast.Is: lambda a, b: a is b,
    ast.IsNot: lambda a, b: a is not b,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}

_SAFE_CALLABLE_NAMES = {
    "abs",
    "min",
    "max",
    "round",
    "len",
    "sum",
    "int",
    "float",
    "str",
    "range",
}


def _range_list(*args: int) -> list[int]:
    r = range(*args)
    if len(r) > 10000:
        raise ValueError("Range size exceeds the maximum limit of 10000")
    return list(r)


class _AstEvaluator:
    def __init__(
        self,
        names: Mapping[str, Any],
        callable_names: set[str],
        allowed_attribute_bases: tuple[Any, ...],
        allowed_attribute_callables: set[Any],
    ) -> None:
        self._names = names
        self._callable_names = callable_names
        self._allowed_attribute_bases = allowed_attribute_bases
        self._allowed_attribute_callables = allowed_attribute_callables

    def evaluate(self, node: ast.AST) -> Any:
        return self._eval(node)

    def _eval(self, node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return self._eval(node.body)
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id in self._names:
                return self._names[node.id]
            raise NameError(node.id)
        if isinstance(node, ast.BinOp):
            op = _SAFE_BINOPS.get(type(node.op))
            if op is None:
                raise UnsafeExpressionError("Unsupported binary operator")
            return op(self._eval(node.left), self._eval(node.right))
        if isinstance(node, ast.UnaryOp):
            op = _SAFE_UNARYOPS.get(type(node.op))
            if op is None:
                raise UnsafeExpressionError("Unsupported unary operator")
            return op(self._eval(node.operand))
        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                for value in node.values:
                    evaluated = self._eval(value)
                    if not evaluated:
                        return evaluated
                return evaluated
            if isinstance(node.op, ast.Or):
                for value in node.values:
                    evaluated = self._eval(value)
                    if evaluated:
                        return evaluated
                return evaluated
            raise UnsafeExpressionError("Unsupported boolean operator")
        if isinstance(node, ast.Compare):
            left = self._eval(node.left)
            for op, comparator in zip(node.ops, node.comparators, strict=False):
                handler = _SAFE_CMP_OPS.get(type(op))
                if handler is None:
                    raise UnsafeExpressionError("Unsupported comparison operator")
                right = self._eval(comparator)
                if not handler(left, right):
                    return False
                left = right
            return True
        if isinstance(node, ast.IfExp):
            return self._eval(node.body) if self._eval(node.test) else self._eval(node.orelse)
        if isinstance(node, ast.Attribute):
            value = self._eval(node.value)
            if node.attr.startswith("_"):
                raise UnsafeExpressionError("Access to private attributes is not allowed")
            try:
                return getattr(value, node.attr)
            except AttributeError as exc:
                raise UnsafeExpressionError(f"Unknown attribute '{node.attr}'") from exc
        if isinstance(node, ast.Subscript):
            value = self._eval(node.value)
            if isinstance(node.slice, ast.Slice):
                lower = self._eval(node.slice.lower) if node.slice.lower else None
                upper = self._eval(node.slice.upper) if node.slice.upper else None
                step = self._eval(node.slice.step) if node.slice.step else None
                return value[slice(lower, upper, step)]
            index = self._eval(node.slice)
            return value[index]
        if isinstance(node, ast.Call):
            func = node.func
            args = [self._eval(arg) for arg in node.args]
            kwargs = {kw.arg: self._eval(kw.value) for kw in node.keywords}
            if isinstance(func, ast.Name):
                if func.id not in self._callable_names:
                    raise UnsafeExpressionError(f"Calling '{func.id}' is not allowed")
                target = self._names[func.id]
            elif isinstance(func, ast.Attribute):
                base = self._eval(func.value)
                if not any(base is candidate for candidate in self._allowed_attribute_bases):
                    raise UnsafeExpressionError("Calling attributes on this object is not allowed")
                if func.attr.startswith("_"):
                    raise UnsafeExpressionError("Access to private attributes is not allowed")
                target = getattr(base, func.attr)
                if target not in self._allowed_attribute_callables:
                    raise UnsafeExpressionError(f"Calling '{func.attr}' is not allowed")
            else:
                raise UnsafeExpressionError("Unsupported call target")
            if not callable(target):
                raise UnsafeExpressionError("Call target is not callable")
            return target(*args, **kwargs)
        if isinstance(node, ast.List):
            return [self._eval(item) for item in node.elts]
        if isinstance(node, ast.Tuple):
            return tuple(self._eval(item) for item in node.elts)
        if isinstance(node, ast.Dict):
            return {self._eval(key): self._eval(value) for key, value in zip(node.keys, node.values, strict=False)}
        if isinstance(node, ast.Set):
            return {self._eval(item) for item in node.elts}
        if isinstance(node, ast.JoinedStr):
            raise UnsafeExpressionError("f-strings are not supported")
        raise UnsafeExpressionError(f"Unsupported expression node: {type(node).__name__}")


def safe_ast_eval(
    expression: str,
    context: Mapping[str, Any],
    *,
    compiled: ast.AST | None = None,
    identifiers: Sequence[str] | None = None,
) -> Any:
    """Evaluate a Python-like expression using a restricted AST evaluator."""

    if compiled is None:
        try:
            tree = ast.parse(expression, mode="eval")
        except SyntaxError as exc:
            raise UnsafeExpressionError("Invalid expression syntax") from exc
    else:
        tree = compiled

    if identifiers is None:
        safe_locals = default_eval_locals(context, expression=expression)
    else:
        safe_locals = default_eval_locals(context, identifiers=identifiers)
    callable_names = {
        name for name in _SAFE_CALLABLE_NAMES if name in safe_locals and callable(safe_locals[name])
    }
    allowed_attribute_bases = tuple(
        base
        for base in (safe_locals.get("math"), safe_locals.get("random"), safe_locals.get("Math"))
        if base is not None
    )
    allowed_attribute_callables: set[Any] = set()
    for base in allowed_attribute_bases:
        for attr in dir(base):
            if attr.startswith("_"):
                continue
            value = getattr(base, attr)
            if callable(value):
                allowed_attribute_callables.add(value)
    evaluator = _AstEvaluator(
        safe_locals,
        callable_names,
        allowed_attribute_bases,
        allowed_attribute_callables,
    )
    return evaluator.evaluate(tree)


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


def find_identifier_tokens(expression: str) -> list[str]:
    """Return unique identifier tokens used in an expression."""

    def _ast_identifiers(source: str) -> list[str]:
        try:
            parsed = ast.parse(source, mode="eval")
        except SyntaxError:
            return []
        return [
            node.id
            for node in ast.walk(parsed)
            if isinstance(node, ast.Name) and not keyword.iskeyword(node.id)
        ]

    try:
        parsed = ast.parse(expression, mode="eval")
    except SyntaxError:
        parsed = None

    if parsed is not None:
        return list(dict.fromkeys(_ast_identifiers(expression)))

    names: list[str] = []
    reader = io.StringIO(expression).readline
    prev_type: int | None = None
    prev_string: str | None = None
    for token in tokenize.generate_tokens(reader):
        tok_type, tok_string = token.type, token.string
        if tok_type == tokenize.STRING:
            prefix = tok_string.split("\"", 1)[0].split("'", 1)[0]
            if "f" in prefix.lower():
                names.extend(_ast_identifiers(tok_string))
        if tok_type == tokenize.NAME:
            if not keyword.iskeyword(tok_string) and not (
                prev_type == tokenize.OP and prev_string == "."
            ):
                names.append(tok_string)
        prev_type, prev_string = tok_type, tok_string
    return list(dict.fromkeys(names))


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
    for name in find_identifier_tokens(expression):
        if not name.isidentifier():
            continue
        try:
            value = context[name]
        except KeyError:
            continue
        sympy_locals.setdefault(name, value)
    return sanitized, sympy_locals


def default_eval_locals(
    context: Mapping[str, Any],
    expression: str | None = None,
    *,
    identifiers: Sequence[str] | None = None,
) -> dict[str, Any]:
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
        "range": _range_list,
    }
    if expression is None and identifiers is None:
        safe_locals.update({key: ensure_accessible(value) for key, value in context.items()})
    safe_locals.setdefault("math", math)
    random_source = _resolve_random_source(context)
    if random_source is not None:
        safe_locals.setdefault("random", random_source)
    math_namespace: dict[str, Any] = {
        "floor": math.floor,
        "ceil": math.ceil,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "sqrt": math.sqrt,
        "pow": math.pow,
        "pi": math.pi,
        "tau": math.tau,
    }
    if random_source is not None:
        math_namespace["random"] = random_source.random
    safe_locals.setdefault("Math", SimpleNamespace(**math_namespace))
    names = identifiers
    if names is None and expression:
        names = find_identifier_tokens(expression)
    if names:
        for name in names:
            try:
                safe_locals[name] = ensure_accessible(context[name])
            except KeyError:
                continue
    return safe_locals


def _is_random_source(value: Any) -> bool:
    random_attr = getattr(value, "random", None)
    return callable(random_attr)


def _seeded_random(context: Mapping[str, Any], seed: Any) -> Any:
    if isinstance(context, MutableMapping):
        existing = context.get("__random__")
        if _is_random_source(existing):
            return existing
        rng = random.Random(seed)
        context["__random__"] = rng
        return rng
    return random.Random(seed)


def _resolve_random_source(context: Mapping[str, Any]) -> Any | None:
    if not isinstance(context, Mapping):
        return None
    existing = context.get("__random__")
    if _is_random_source(existing):
        return existing
    existing_callable = context.get("__random_callable__")
    if callable(existing_callable):
        return existing_callable
    properties = context.get("properties") if "properties" in context else context.get("variables")
    if isinstance(properties, Mapping):
        candidate = properties.get("random")
        if _is_random_source(candidate):
            return candidate
        if "random_seed" in properties:
            rng = _seeded_random(context, properties["random_seed"])
            return _wrap_random_callable(context, rng)
    candidate = context.get("random")
    if _is_random_source(candidate):
        return candidate
    if "random_seed" in context:
        rng = _seeded_random(context, context["random_seed"])
        return _wrap_random_callable(context, rng)
    return None


class _RandomAdapter:
    def __init__(self, rng: random.Random) -> None:
        self._rng = rng
        self.random = rng.random


def _wrap_random_callable(context: Mapping[str, Any], rng: random.Random) -> Any:
    adapter = _RandomAdapter(rng)
    if isinstance(context, MutableMapping):
        context["__random_callable__"] = adapter
    return adapter


def fill_placeholders(
    template: str,
    context: Mapping[str, Any],
    *,
    label: str | None = None,
) -> str:
    """Inject context values into ``{placeholder}`` slots within a template string."""

    def _replacement(match: re.Match[str]) -> str:
        token = match.group(1).strip()
        from .formula import evaluate_expression

        value = evaluate_expression(token, context, label=label)
        return "" if value is None else stringify(value)

    return PLACEHOLDER_PATTERN.sub(_replacement, template)
