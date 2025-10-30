import json
from pathlib import Path

import pytest

from infogroove.exceptions import TemplateError
from infogroove.template_loader import _parse_template, load_template


def make_template_payload(**overrides):
    payload = {
        "variables": {
            "canvas": {"width": 800, "height": 600},
            "color": "#fff",
        },
        "elements": [
            {
                "type": "rect",
                "attributes": {"width": 10, "height": 20},
                "scope": "canvas",
            },
            {
                "type": "text",
                "attributes": {"x": 0, "y": 0},
                "text": "hello",
            },
        ],
        "formulas": {"double": "value * 2"},
        "numElementsRange": [1, 3],
        "schema": {"type": "array"},
        "name": "Example",
        "description": "Demo",
        "version": "1.0",
    }
    payload.update(overrides)
    return payload


def test_load_template_reads_and_parses(tmp_path):
    template_path = tmp_path / "def.json"
    template_path.write_text(json.dumps(make_template_payload()), encoding="utf-8")

    template = load_template(template_path)

    assert template.source_path == template_path
    assert template.canvas.width == 800
    assert template.elements[0].scope == "canvas"
    assert template.elements[1].text == "hello"
    assert template.formulas["double"] == "value * 2"
    assert template.variables["color"] == "#fff"
    assert template.variables["canvas"]["height"] == 600
    assert template.num_elements_range == (1, 3)
    assert template.schema == {"type": "array"}
    assert template.metadata == {
        "name": "Example",
        "description": "Demo",
        "version": "1.0",
    }


def test_parse_template_requires_canvas_dimensions(tmp_path):
    payload = make_template_payload()
    payload["variables"]["canvas"] = {"width": 400}

    with pytest.raises(TemplateError, match="Both canvas width and height"):
        _parse_template(tmp_path / "def.json", payload)


@pytest.mark.parametrize(
    "mutator, message",
    [
        (lambda payload: payload.update({"variables": "oops"}), "'variables' must"),
        (lambda payload: payload["variables"].pop("canvas"), "'variables.canvas' must"),
        (lambda payload: payload["variables"].update({"canvas": "oops"}), "'variables.canvas' must"),
        (lambda payload: payload["variables"].update({"canvas": {}}), "Both canvas width"),
        (lambda payload: payload.update({"screen": {"width": 1, "height": 2}}), "Canvas dimensions must"),
        (lambda payload: payload.update({"screenWidth": 100}), "Canvas dimensions must"),
        (lambda payload: payload.update({"elements": {}}), "'elements' must"),
        (lambda payload: payload.update({"elements": [{"type": 1}]}), "Element definitions require"),
        (
            lambda payload: payload.update({"elements": [{"type": "rect", "attributes": []}]}),
            "Element attributes must",
        ),
        (
            lambda payload: payload.update({"elements": [{"type": "rect", "attributes": {}, "text": 1}]}),
            "Element text must",
        ),
        (
            lambda payload: payload.update({"elements": [{"type": "rect", "attributes": {}, "scope": "row"}]}),
            "Element scope must",
        ),
        (lambda payload: payload.update({"formulas": []}), "'formulas' must"),
        (lambda payload: payload.update({"styles": {}}), "'styles' is no longer supported"),
    ],
)
def test_parse_template_validation_errors(tmp_path, mutator, message):
    payload = make_template_payload()
    mutator(payload)

    with pytest.raises(TemplateError) as exc:
        _parse_template(tmp_path / "def.json", payload)

    assert message in str(exc.value)
