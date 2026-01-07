import ast
import math
import random

import pytest

from infogroove.exceptions import FormulaEvaluationError
from infogroove.utils import (
    MappingAdapter,
    PLACEHOLDER_PATTERN,
    SequenceAdapter,
    default_eval_locals,
    ensure_accessible,
    fill_placeholders,
    find_dotted_tokens,
    prepare_expression_for_sympy,
    replace_tokens,
    resolve_path,
    tokenize_path,
    to_camel_case,
    to_snake_case,
    unwrap_accessible,
)


def test_sequence_and_mapping_adapters_expose_helpers():
    adapter = ensure_accessible({"items": [1, {"value": 3}]})
    assert isinstance(adapter, MappingAdapter)

    items = adapter["items"]
    assert isinstance(items, SequenceAdapter)
    values = list(items)
    assert values[0] == 1
    assert values[1]["value"] == 3
    assert items.length == 2

    with pytest.raises(AttributeError):
        _ = adapter.missing


def test_unwrap_accessible_returns_builtin_types():
    adapter = ensure_accessible({"items": [{"value": 1}, {"value": 2}]})

    unwrapped = unwrap_accessible(adapter)

    assert isinstance(unwrapped, dict)
    assert isinstance(unwrapped["items"], list)
    assert unwrapped["items"][0] == {"value": 1}


def test_tokenize_and_resolve_path_supports_indices():
    context = {
        "items": [
            {"value": 3, "meta": {"label": "A"}},
            {"value": 5, "meta": {"label": "B"}},
        ]
    }
    assert tokenize_path("items[1].meta.label") == ["items", "1", "meta", "label"]
    assert resolve_path(context, "items[1].meta.label") == "B"
    assert resolve_path(context, "items.length") == 2


def test_case_conversion_helpers():
    assert to_snake_case("CamelCase") == "camel_case"
    assert to_camel_case("some_value") == "someValue"


def test_find_and_replace_tokens_preserves_order():
    expression = "canvas.width + canvas.height"
    tokens = find_dotted_tokens(expression)
    assert tokens == ["canvas.width", "canvas.height"]

    replaced = replace_tokens(expression, {token: "x" for token in tokens})
    assert replaced == "x + x"


def test_prepare_expression_for_sympy_and_eval_namespace():
    context = {"metrics": {"maxValue": 3}, "value": 10}
    sanitized, locals_ = prepare_expression_for_sympy("metrics.maxValue + value", context)

    assert sanitized != "metrics.maxValue + value"  # dotted access replaced with placeholders
    placeholder = next(key for key in locals_ if key.startswith("__v"))
    assert locals_[placeholder] == 3
    assert locals_["value"] == 10

    safe_locals = default_eval_locals(context)
    assert safe_locals["abs"] is abs
    assert math is safe_locals["math"]
    assert safe_locals["metrics"]["maxValue"] == 3


def test_fill_placeholders_inserts_context_values():
    context = {"item": {"value": 5, "label": "Five"}}
    template = "Value={item.value} Label={item.label}"
    assert PLACEHOLDER_PATTERN.search(template)
    rendered = fill_placeholders(template, context)
    assert rendered == "Value=5 Label=Five"

    with pytest.raises(FormulaEvaluationError):
        fill_placeholders("{missing.value}", context)


def test_fill_placeholders_unwraps_adapter_results():
    context = {"items": [{"value": 1}, {"value": 2}]}

    rendered = fill_placeholders("{items}", context)

    assert ast.literal_eval(rendered) == [{"value": 1}, {"value": 2}]


def test_fill_placeholders_evaluates_inline_expressions():
    context = {
        "value": 7,
        "index": 2,
        "canvas": {"width": 120, "height": 80},
    }
    rendered = fill_placeholders(
        "Double={value * 2} Next={index + 1} Half={canvas.height / 2}",
        context,
    )

    assert rendered == "Double=14 Next=3 Half=40"

    with pytest.raises(FormulaEvaluationError):
        fill_placeholders("{missing + 1}", context)


def test_resolve_path_does_not_invoke_callables():
    calls: list[str] = []

    def marker():
        calls.append("called")
        return "value"

    context = {"value": marker}

    resolved = resolve_path(context, "value")

    assert resolved is marker
    assert calls == []


def test_fill_placeholders_supports_range_lists():
    context: dict[str, object] = {}

    assert fill_placeholders("{range(3)}", context) == "[0, 1, 2]"
    assert fill_placeholders("{range(1, 4)}", context) == "[1, 2, 3]"
    assert fill_placeholders("{range(1, 5, 2)}", context) == "[1, 3]"


def test_random_is_opt_in():
    with pytest.raises(FormulaEvaluationError):
        fill_placeholders("{Math.random()}", {})


def test_random_seed_provides_deterministic_sequence():
    context = {"properties": {"random_seed": 7}}

    first = float(fill_placeholders("{Math.random()}", context))
    second = float(fill_placeholders("{Math.random()}", context))
    assert first != second

    new_context = {"properties": {"random_seed": 7}}
    first_from_new = float(fill_placeholders("{Math.random()}", new_context))
    assert first == first_from_new

    rng = random.Random(7)
    assert first == rng.random()
    assert second == rng.random()
