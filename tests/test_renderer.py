from dataclasses import replace

import pytest

from infogroove.core import Infogroove
from infogroove.exceptions import DataValidationError, RenderError
from infogroove.models import CanvasSpec, ElementSpec, TemplateSpec
from infogroove.renderer import InfogrooveRenderer


@pytest.fixture
def sample_template(tmp_path):
    return TemplateSpec(
        source_path=tmp_path / "def.json",
        canvas=CanvasSpec(width=200, height=100),
        elements=[
            ElementSpec(
                type="rect",
                attributes={"width": "{canvas.width}", "height": "10", "class": "chart"},
                scope="canvas",
            ),
            ElementSpec(
                type="text",
                attributes={"x": "{index}", "y": "20", "fontSize": "12"},
                text="{label}: {double}",
                scope="item",
            ),
        ],
        formulas={"double": "value * 2", "label": "item['label']"},
        variables={
            "canvas": {"width": 200, "height": 100},
            "fill": "#000",
        },
        num_elements_range=(1, 5),
    )


def test_render_combines_canvas_and_items(sample_template):
    renderer = InfogrooveRenderer(sample_template)
    svg_markup = renderer.render([
        {"label": "A", "value": 3},
        {"label": "B", "value": 4},
    ])

    assert "class=\"chart\"" in svg_markup
    assert "A: 6" in svg_markup
    assert "B: 8" in svg_markup
    assert "font-size=\"12\"" in svg_markup  # camelCase attributes converted to kebab in svg.py


def test_build_base_context_computes_metrics(sample_template):
    renderer = InfogrooveRenderer(sample_template)
    dataset = [
        {"label": "A", "value": 5},
        {"label": "B", "value": 15},
    ]

    context = renderer._build_base_context(dataset)

    assert context["canvasWidth"] == 200
    assert context["canvas"]["height"] == 100
    assert context["fill"] == "#000"
    assert context["variables"]["fill"] == "#000"
    assert context["values"] == [5, 15]
    assert context["maxValue"] == 15
    assert context["averageValue"] == 10


def test_build_item_context_infers_defaults(sample_template):
    renderer = InfogrooveRenderer(sample_template)
    base = renderer._build_base_context([{"value": 2, "text": "Hello"}])

    context = renderer._build_item_context(base, {"value": 2, "text": "Hello"}, index=0, total=1)

    assert context["index"] == 0
    assert context["oneBasedIndex"] == 1
    assert context["label"] == "Hello"
    assert context["value"] == 2


def test_validate_data_checks_sequence(sample_template):
    renderer = InfogrooveRenderer(sample_template)

    with pytest.raises(DataValidationError, match="sequence of mappings"):
        renderer._validate_data({"not": "a sequence"})

    with pytest.raises(DataValidationError, match="must be a mapping"):
        renderer._validate_data([{"ok": 1}, 2])

    with pytest.raises(DataValidationError, match="at least 1"):
        renderer._validate_data([])

    with pytest.raises(DataValidationError, match="at most 5"):
        renderer._validate_data([{"value": 1}] * 6)


def test_append_rejects_unknown_element(sample_template):
    bad_template = TemplateSpec(
        source_path=sample_template.source_path,
        canvas=sample_template.canvas,
        elements=[ElementSpec(type="unknown", attributes={})],
        formulas={},
        variables=dict(sample_template.variables),
    )
    renderer = InfogrooveRenderer(bad_template)

    with pytest.raises(RenderError, match="Unsupported element type"):
        renderer.render([{"value": 1}])


def test_validate_data_uses_json_schema(sample_template):
    template_with_schema = replace(
        sample_template,
        schema={
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"value": {"type": "number"}},
                "required": ["value"],
            },
        },
    )
    renderer = InfogrooveRenderer(template_with_schema)

    valid = renderer._validate_data([{"value": 3}])
    assert valid == [{"value": 3}]

    with pytest.raises(DataValidationError, match="schema"):
        renderer._validate_data([{"value": "bad"}])


def test_infogroove_factory_returns_renderer(sample_template):
    renderer = Infogroove(sample_template)

    assert isinstance(renderer, InfogrooveRenderer)
    assert renderer.template is sample_template


def test_infogroove_factory_accepts_mapping():
    renderer = Infogroove(
        {
            "variables": {
                "canvas": {"width": 120, "height": 40},
                "gap": 10,
            },
            "formulas": {"x": "index * gap"},
            "elements": [
                {"type": "circle", "attributes": {"cx": "{x}", "cy": "20", "r": "5"}},
            ],
        }
    )

    markup = renderer.render([{}] * 3)

    assert markup.count("<circle") == 3


def test_render_supports_inline_attribute_expressions():
    renderer = Infogroove(
        {
            "variables": {"canvas": {"width": 60, "height": 80}},
            "elements": [
                {
                    "type": "circle",
                    "attributes": {
                        "cx": "{index * 10}",
                        "cy": "{canvas.height / 2}",
                        "r": "5",
                    },
                }
            ],
        }
    )

    markup = renderer.render([{}, {}])

    assert "cx=\"0\"" in markup
    assert "cx=\"10\"" in markup
    assert "cy=\"40.0\"" in markup
