import json

import pytest

from infogroove.core import Infogroove
from infogroove.exceptions import DataValidationError, RenderError
from infogroove.models import CanvasSpec, ElementSpec, RepeatSpec, TemplateSpec
from infogroove.renderer import InfogrooveRenderer


@pytest.fixture
def sample_template(tmp_path):
    return TemplateSpec(
        source_path=tmp_path / "def.json",
        canvas=CanvasSpec(width=200, height=100),
        template=[
            ElementSpec(
                type="rect",
                attributes={"width": "{canvas.width}", "height": "10", "class": "chart"},
            ),
            ElementSpec(
                type="text",
                attributes={"x": "{__index__ * gap}", "y": "20", "fontSize": "12"},
                text="{label}: {double}",
                repeat=RepeatSpec(
                    items="items",
                    alias="item",
                ),
                let={
                    "label": "item.label",
                    "double": "item.value * 2",
                    "gap": "gap",
                },
            ),
        ],
        properties={
            "canvas": {"width": 200, "height": 100},
            "gap": 24,
        },
        schema={
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "required": ["items"],
            "additionalProperties": False,
            "properties": {
                "items": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 5,
                    "items": {
                        "type": "object",
                        "required": ["label", "value"],
                        "properties": {
                            "label": {"type": "string"},
                            "value": {"type": "number"},
                        },
                        "additionalProperties": False,
                    },
                },
            },
        },
    )


def test_render_combines_canvas_and_items(sample_template):
    renderer = InfogrooveRenderer(sample_template)
    payload = {
        "items": [
            {"label": "A", "value": 3},
            {"label": "B", "value": 4},
        ]
    }
    svg_markup = renderer.render(payload)

    assert "class=\"chart\"" in svg_markup
    assert "A: 6" in svg_markup
    assert "B: 8" in svg_markup
    assert "font-size=\"12\"" in svg_markup


def test_translate_returns_node_specs(sample_template):
    renderer = InfogrooveRenderer(sample_template)
    payload = {"items": [{"label": "Only", "value": 9}]}

    node_specs = renderer.translate(payload)

    assert [node["type"] for node in node_specs] == ["rect", "text"]
    assert all("children" in node for node in node_specs)
    assert node_specs[1]["text"] == "Only: 18.0"
    # Ensure JSON roundtrip compatibility
    assert json.loads(json.dumps(node_specs, ensure_ascii=False)) == node_specs


def test_build_base_context_computes_metrics(sample_template):
    renderer = InfogrooveRenderer(sample_template)
    payload = {
        "items": [
            {"label": "A", "value": 5},
            {"label": "B", "value": 15},
        ]
    }

    context = renderer._build_base_context(payload)

    assert context["canvas"]["width"] == 200
    assert context["canvas"]["height"] == 100
    assert context["properties"].gap == 24
    assert context["values"] == [5, 15]
    assert context["maxValue"] == 15
    assert context["averageValue"] == 10


def test_repeat_context_injects_reserved_variables(sample_template):
    renderer = InfogrooveRenderer(sample_template)
    base_context = renderer._build_base_context(
        {"items": [{"label": "Hello", "value": 2}]}
    )
    repeat = sample_template.template[1].repeat
    assert repeat is not None

    frame = renderer._build_repeat_context(
        base_context,
        repeat,
        {"label": "Hello", "value": 2},
        index=0,
        total=1,
    )

    element = sample_template.template[1]
    bindings = renderer._evaluate_bindings(element.let, frame, label="element:text")
    frame.update(renderer._make_accessible_bindings(bindings))

    assert frame["__index__"] == 0
    assert frame["__first__"] is True
    assert frame["__last__"] is True
    assert frame["__total__"] == 1
    assert frame["__count__"] == 1
    assert frame["label"] == "Hello"
    assert frame["double"] == 4

    item_alias = frame["item"]
    assert item_alias["__index__"] == 0
    assert item_alias["__count__"] == 1
    assert item_alias["__total__"] == 1
    assert item_alias["__first__"] is True
    assert item_alias["__last__"] is True


def test_repeat_let_override_is_scoped(tmp_path):
    repeat = RepeatSpec(
        items="data",
        alias="row",
    )
    template = TemplateSpec(
        source_path=tmp_path / "def.json",
        canvas=CanvasSpec(width=100, height=100),
        template=[
            ElementSpec(
                type="rect",
                attributes={"fill": "{color}"},
                repeat=repeat,
                let={"color": "'blue'"},
            )
        ],
        properties={
            "canvas": {"width": 100, "height": 100},
            "color": "red",
        },
    )

    renderer = InfogrooveRenderer(template)
    base_context = renderer._build_base_context([{}])
    assert base_context["color"] == "red"
    assert base_context["properties"].color == "red"

    frame = renderer._build_repeat_context(base_context, repeat, {}, index=0, total=1)

    element = template.template[0]
    bindings = renderer._evaluate_bindings(element.let, frame, label="element:rect")
    frame.update(renderer._make_accessible_bindings(bindings))

    assert frame["color"] == "blue"
    assert frame["properties"].color == "red"
    assert base_context["color"] == "red"
    assert base_context["properties"].color == "red"


def test_repeat_alias_reserved_helpers_progress(sample_template):
    renderer = InfogrooveRenderer(sample_template)
    base_context = renderer._build_base_context(
        {"items": [{"label": "A", "value": 1}, {"label": "B", "value": 2}]}
    )
    repeat = sample_template.template[1].repeat
    assert repeat is not None

    first_frame = renderer._build_repeat_context(
        base_context,
        repeat,
        {"label": "A", "value": 1},
        index=0,
        total=2,
    )
    second_frame = renderer._build_repeat_context(
        base_context,
        repeat,
        {"label": "B", "value": 2},
        index=1,
        total=2,
    )

    first_alias = first_frame["item"]
    assert first_alias["__index__"] == 0
    assert first_alias["__count__"] == 1
    assert first_alias["__total__"] == 2
    assert first_alias["__first__"] is True
    assert first_alias["__last__"] is False

    second_alias = second_frame["item"]
    assert second_alias["__index__"] == 1
    assert second_alias["__count__"] == 2
    assert second_alias["__total__"] == 2
    assert second_alias["__first__"] is False
    assert second_alias["__last__"] is True


def test_let_bindings_allow_forward_references(tmp_path):
    template = TemplateSpec(
        source_path=tmp_path / "def.json",
        canvas=CanvasSpec(width=100, height=100),
        template=[
            ElementSpec(
                type="polygon",
                attributes={"points": "{points}"},
                let={
                    "points": "{x},{top_y} {x + width},{top_y}",
                    "x": "10",
                    "top_y": "20",
                    "width": "30",
                },
            )
        ],
        properties={"canvas": {"width": 100, "height": 100}},
    )

    renderer = InfogrooveRenderer(template)
    node_specs = renderer.translate({})

    assert node_specs[0]["attributes"]["points"] == "10.0,20.0 40.0,20.0"


def test_validate_data_enforces_object_schema(sample_template):
    renderer = InfogrooveRenderer(sample_template)

    payload = {"items": [{"label": "A", "value": 1}]}
    assert renderer._validate_data(payload) == payload

    with pytest.raises(DataValidationError, match="schema"):
        renderer._validate_data({})

    with pytest.raises(DataValidationError, match="schema"):
        renderer._validate_data({"items": []})

    with pytest.raises(DataValidationError, match="schema"):
        renderer._validate_data([{"label": "A", "value": 1}])


def test_append_rejects_unknown_element(sample_template):
    bad_template = TemplateSpec(
        source_path=sample_template.source_path,
        canvas=sample_template.canvas,
        template=[ElementSpec(type="unknown", attributes={})],
        properties=dict(sample_template.properties),
    )
    renderer = InfogrooveRenderer(bad_template)

    with pytest.raises(RenderError, match="Unsupported element type"):
        renderer.render([{"value": 1}])


def test_validate_data_uses_json_schema(sample_template):
    template_with_schema = TemplateSpec(
        source_path=sample_template.source_path,
        canvas=sample_template.canvas,
        template=list(sample_template.template),
        properties=dict(sample_template.properties),
        schema={
            "type": "array",
            "minItems": 1,
            "maxItems": 4,
            "items": {
                "type": "object",
                "properties": {
                    "value": {"type": "number"},
                    "label": {"type": "string"},
                },
                "required": ["value", "label"],
                "additionalProperties": False,
            },
        },
    )
    renderer = InfogrooveRenderer(template_with_schema)

    valid = renderer._validate_data([{"value": 3, "label": "ok"}])
    assert valid == [{"value": 3, "label": "ok"}]

    with pytest.raises(DataValidationError, match="schema"):
        renderer._validate_data([{"value": "bad"}])

    with pytest.raises(DataValidationError, match="schema"):
        renderer._validate_data([{"label": "missing value"}])


def test_validate_data_schema_supports_nested_collections(tmp_path):
    template = TemplateSpec(
        source_path=tmp_path / "def.json",
        canvas=CanvasSpec(width=100, height=100),
        template=[
            ElementSpec(
                type="g",
                repeat=RepeatSpec(items="data", alias="entry"),
                children=[
                    ElementSpec(
                        type="g",
                        repeat=RepeatSpec(items="entry.points", alias="point"),
                    )
                ],
            )
        ],
        properties={"canvas": {"width": 100, "height": 100}},
        schema={
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["label", "values", "points"],
                "additionalProperties": False,
                "properties": {
                    "label": {"type": "string"},
                    "values": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "number"},
                    },
                    "points": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "required": ["x", "y"],
                            "additionalProperties": False,
                            "properties": {
                                "x": {"type": "number"},
                                "y": {"type": "number"},
                            },
                        },
                    },
                },
            },
        },
    )
    renderer = InfogrooveRenderer(template)

    valid_payload = [
        {
            "label": "A",
            "values": [1, 3, 5],
            "points": [{"x": 0, "y": 0}, {"x": 1.5, "y": 2}],
        }
    ]
    assert renderer._validate_data(valid_payload) == valid_payload

    with pytest.raises(DataValidationError, match="schema"):
        renderer._validate_data(
            [
                {
                    "label": "A",
                    "values": [],
                    "points": [{"x": 0, "y": 0}],
                }
            ]
        )

    with pytest.raises(DataValidationError, match="schema"):
        renderer._validate_data(
            [
                {
                    "label": "A",
                    "values": [1, 2],
                    "points": [{"x": 0}],
                }
            ]
        )


def test_infogroove_factory_returns_renderer(sample_template):
    renderer = Infogroove(sample_template)

    assert isinstance(renderer, InfogrooveRenderer)
    assert renderer.template is sample_template


def test_infogroove_factory_accepts_mapping():
    renderer = Infogroove(
        {
            "properties": {
                "canvas": {"width": 120, "height": 40},
                "gap": 10,
            },
            "template": [
                {
                    "type": "circle",
                    "attributes": {"cx": "{cx}", "cy": "20", "r": "5"},
                    "repeat": {
                        "items": "data",
                        "as": "row",
                    },
                    "let": {
                        "cx": "__index__ * properties.gap",
                    },
                }
            ],
        }
    )

    markup = renderer.render([{}, {}, {}])

    assert markup.count("<circle") == 3


def test_render_supports_inline_attribute_expressions():
    renderer = Infogroove(
        {
            "properties": {"canvas": {"width": 60, "height": 80}},
            "template": [
                {
                    "type": "circle",
                    "attributes": {
                        "cx": "{__index__ * 10}",
                        "cy": "{canvas.height / 2}",
                        "r": "5",
                    },
                    "repeat": {"items": "data", "as": "item"},
                }
            ],
        }
    )

    markup = renderer.render([{}, {}])

    assert "cx=\"0\"" in markup
    assert "cx=\"10\"" in markup
    assert "cy=\"40.0\"" in markup


def test_custom_renderer_handles_icon_elements(tmp_path):
    template = TemplateSpec(
        source_path=tmp_path / "def.json",
        canvas=CanvasSpec(width=96, height=96),
        template=[
            ElementSpec(
                type="icon",
                attributes={"name": "{item.name}", "size": "{size}"},
                repeat=RepeatSpec(items="icons", alias="item"),
            )
        ],
        properties={"canvas": {"width": 96, "height": 96}, "size": 24},
    )

    renderer = InfogrooveRenderer(template)

    def fake_icon_renderer(payload, context):
        icon_name = payload.attributes["name"]
        size = payload.attributes.get("size", "24")
        if icon_name == "heart":
            shape = {
                "type": "path",
                "attributes": {"d": "M1 1 L2 2 L1 3 Z"},
            }
        else:
            shape = {
                "type": "polygon",
                "attributes": {"points": "0,0 2,0 1,2"},
            }
        wrapper = {
            "type": "g",
            "attributes": {"data-icon": icon_name, "data-size": size},
            "children": [shape],
        }
        return [wrapper]

    renderer.register_renderer("icon", fake_icon_renderer)

    payload = {"icons": [{"name": "heart"}, {"name": "star"}]}

    node_specs = renderer.translate(payload)

    assert len(node_specs) == 2
    assert node_specs[0]["attributes"]["data-icon"] == "heart"
    assert node_specs[0]["children"][0]["type"] == "path"
    assert node_specs[1]["attributes"]["data-icon"] == "star"
    assert node_specs[1]["children"][0]["type"] == "polygon"

    svg_markup = renderer.render(payload)

    assert "data-icon=\"heart\"" in svg_markup
    assert "data-icon=\"star\"" in svg_markup
    assert "<path d=\"M1 1 L2 2 L1 3 Z\"" in svg_markup
