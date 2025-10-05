from types import SimpleNamespace

import pytest
import sympy

from infogroove.exceptions import FormulaEvaluationError
from infogroove.formula import FormulaEngine


def test_formula_engine_evaluates_with_sympy_numbers():
    engine = FormulaEngine({"double": "value * 2", "offset": "double + 1"})

    results = engine.evaluate({"value": 3})

    assert results == {"double": 6, "offset": 7}


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
