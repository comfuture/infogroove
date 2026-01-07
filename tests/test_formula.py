from types import SimpleNamespace

import pytest
import sympy

from infogroove.exceptions import FormulaEvaluationError
from infogroove import formula as formula_module
from infogroove.formula import FormulaEngine, evaluate_expression


def test_formula_engine_evaluates_with_sympy_numbers():
    engine = FormulaEngine({"double": "value * 2", "offset": "double + 1"})

    results = engine.evaluate({"value": 3})

    assert results == {"double": 6, "offset": 7}


def test_evaluate_expression_unwraps_accessible_containers():
    context = {"items": [{"value": 1}, {"value": 2}]}

    result = evaluate_expression("items", context)

    assert isinstance(result, list)
    assert result == [{"value": 1}, {"value": 2}]


def test_formula_engine_falls_back_to_python_eval(monkeypatch):
    engine = FormulaEngine({"total": "sum(items)"})

    def boom(*args, **kwargs):  # pragma: no cover - patched in test
        raise sympy.SympifyError("fail")

    monkeypatch.setattr(sympy, "sympify", boom)
    items = [1, 2, 3]
    results = engine.evaluate({"items": items})

    assert results["total"] == sum(items)


def test_formula_engine_raises_on_failure(monkeypatch):
    engine = FormulaEngine({"bad": "items['missing']"})

    def boom(*args, **kwargs):
        raise sympy.SympifyError("fail")

    monkeypatch.setattr(sympy, "sympify", boom)

    with pytest.raises(FormulaEvaluationError):
        engine.evaluate({"items": [{}]})


def test_expression_cache_reuses_sympy_tokens(monkeypatch):
    formula_module._clear_expression_caches()
    calls = {"dotted": 0}

    original = formula_module.find_dotted_tokens

    def wrapped(expression: str):
        calls["dotted"] += 1
        return original(expression)

    monkeypatch.setattr(formula_module, "find_dotted_tokens", wrapped)

    assert evaluate_expression("value * 2", {"value": 2}) == 4
    assert evaluate_expression("value * 2", {"value": 3}) == 6

    assert calls["dotted"] == 1


def test_expression_cache_reuses_ast_parse(monkeypatch):
    formula_module._clear_expression_caches()
    calls = {"parse": 0}

    original = formula_module.ast.parse

    def wrapped(*args, **kwargs):
        calls["parse"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(formula_module.ast, "parse", wrapped)

    def boom(*args, **kwargs):  # pragma: no cover - patched in test
        raise sympy.SympifyError("fail")

    monkeypatch.setattr(sympy, "sympify", boom)

    assert evaluate_expression("value + 1", {"value": 1}) == 2
    first_count = calls["parse"]

    assert evaluate_expression("value + 1", {"value": 2}) == 3

    assert calls["parse"] == first_count
