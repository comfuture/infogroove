import json
from pathlib import Path

import pytest

from infogroove.exceptions import TemplateError
from infogroove.loader import _parse_template, load, load_path, loads
from infogroove.renderer import InfogrooveRenderer


def make_template_payload(**overrides):
    payload = {
        "properties": {
            "canvas": {"width": 800, "height": 600},
            "color": "#fff",
            "greeting": "hello",
        },
        "template": [
            {
                "type": "rect",
                "attributes": {"width": "10", "height": "20"},
            },
            {
                "type": "text",
                "attributes": {"x": "0", "y": "0"},
                "text": "{label}",
                "repeat": {
                    "items": "data",
                    "as": "item",
                },
                "let": {
                    "label": "item.label",
                    "line": "f'{__index__ + 1}. {item.label}'",
                },
            },
        ],
        "numElementsRange": [1, 3],
        "schema": {"type": "array"},
        "name": "Example",
        "description": "Demo",
        "version": "1.0",
    }
    payload.update(overrides)
    return payload


def test_load_path_returns_renderer(tmp_path):
    template_path = tmp_path / "def.json"
    template_path.write_text(json.dumps(make_template_payload()), encoding="utf-8")

    renderer = load_path(template_path)

    assert isinstance(renderer, InfogrooveRenderer)
    template = renderer.template

    assert template.source_path == template_path
    assert template.canvas.width == 800
    assert template.template[0].repeat is None
    assert template.template[1].repeat is not None
    assert template.properties["color"] == "#fff"
    assert template.properties["canvas"]["height"] == 600
    assert template.num_elements_range == (1, 3)
    assert template.schema == {"type": "array"}
    assert template.metadata == {
        "name": "Example",
        "description": "Demo",
        "version": "1.0",
    }


def test_load_accepts_file_objects(tmp_path):
    template_path = tmp_path / "def.json"
    template_path.write_text(json.dumps(make_template_payload()), encoding="utf-8")

    with template_path.open(encoding="utf-8") as handle:
        renderer = load(handle)

    assert renderer.template.source_path == template_path


def test_loads_accepts_raw_strings(tmp_path):
    payload = json.dumps(make_template_payload())
    renderer = loads(payload, source=tmp_path / "def.json")

    assert renderer.template.canvas.width == 800


def test_parse_template_requires_canvas_dimensions(tmp_path):
    payload = make_template_payload()
    payload["properties"]["canvas"] = {"width": 400}

    with pytest.raises(TemplateError, match="Both canvas width and height"):
        _parse_template(tmp_path / "def.json", payload)


@pytest.mark.parametrize(
    "mutator, message",
    [
        (lambda payload: payload.update({"properties": "oops"}), "'properties' must"),
        (lambda payload: payload["properties"].pop("canvas"), "'properties.canvas' must"),
        (lambda payload: payload["properties"].update({"canvas": "oops"}), "'properties.canvas' must"),
        (lambda payload: payload["properties"]["canvas"].pop("height"), "Both canvas width"),
        (lambda payload: payload.update({"template": {}}), "'template' must"),
        (lambda payload: payload.update({"template": [{"type": 1}]}), "Element definitions require"),
        (
            lambda payload: payload.update({"template": [{"type": "rect", "attributes": []}]}),
            "Element attributes must",
        ),
        (
            lambda payload: payload.update({"template": [{"type": "rect", "attributes": {}, "text": 1}]}),
            "Element text must",
        ),
        (
            lambda payload: payload["template"][1]["repeat"].update({"items": 3}),
            "Repeat bindings require",
        ),
        (
            lambda payload: payload["template"][1]["repeat"].update({"as": 1}),
            "Repeat bindings require",
        ),
        (
            lambda payload: payload["template"][1]["repeat"].update({"index": "idx"}),
            "Repeat 'index' is no longer supported; use __index__ helper variables",
        ),
        (
            lambda payload: payload["template"][1]["repeat"].update({"let": {}}),
            "Repeat declarations only accept 'items' and 'as'",
        ),
        (lambda payload: payload.update({"styles": {}}), "'styles' is no longer supported"),
    ],
)
def test_parse_template_validation_errors(tmp_path, mutator, message):
    payload = make_template_payload()
    mutator(payload)

    with pytest.raises(TemplateError) as exc:
        _parse_template(tmp_path / "def.json", payload)

    assert message in str(exc.value)
