import math

import pytest

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

    with pytest.raises(KeyError):
        fill_placeholders("{missing.value}", context)


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

    assert rendered == "Double=14 Next=3 Half=40.0"

    with pytest.raises(KeyError):
        fill_placeholders("{missing + 1}", context)
