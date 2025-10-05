import json
from pathlib import Path

import pytest

from infogroove.exceptions import TemplateError
from infogroove.template_loader import _parse_template, load_template


def make_template_payload(**overrides):
    payload = {
        "screen": {"width": 800, "height": 600},
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
        "styles": {"color": "#fff"},
        "numElementsRange": [1, 3],
        "schema": {"type": "array"},
        "name": "Example",
        "description": "Demo",
        "version": "1.0",
    }
    payload.update(overrides)
    return payload


def test_load_template_reads_and_parses(tmp_path):
    template_path = tmp_path / "template.igd"
    template_path.write_text(json.dumps(make_template_payload()), encoding="utf-8")

    template = load_template(template_path)

    assert template.source_path == template_path
    assert template.screen.width == 800
    assert template.elements[0].scope == "canvas"
    assert template.elements[1].text == "hello"
    assert template.formulas["double"] == "value * 2"
    assert template.styles["color"] == "#fff"
    assert template.num_elements_range == (1, 3)
    assert template.schema == {"type": "array"}
    assert template.metadata == {
        "name": "Example",
        "description": "Demo",
        "version": "1.0",
    }


def test_parse_template_accepts_screen_fallbacks(tmp_path):
    payload = make_template_payload(screen={}, screenWidth=400, screenHeight=500)
    template = _parse_template(tmp_path / "template.igd", payload)

    assert template.screen.width == 400
    assert template.screen.height == 500


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"screen": "oops"}, "'screen' must be a mapping"),
        ({"screen": {}}, "Both screen width"),
        ({"elements": {}}, "'elements' must"),
        (
            {"elements": [{"type": 1}]},
            "Element definitions require",
        ),
        (
            {"elements": [{"type": "rect", "attributes": []}]},
            "Element attributes must",
        ),
        (
            {"elements": [{"type": "rect", "attributes": {}, "text": 1}]},
            "Element text must",
        ),
        (
            {"elements": [{"type": "rect", "attributes": {}, "scope": "row"}]},
            "Element scope must",
        ),
        ({"formulas": []}, "'formulas' must"),
        ({"styles": []}, "'styles' must"),
    ],
)
def test_parse_template_validation_errors(tmp_path, overrides, message):
    payload = make_template_payload(**overrides)

    with pytest.raises(TemplateError) as exc:
        _parse_template(tmp_path / "template.igd", payload)

    assert message in str(exc.value)
