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
                    items="data",
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
    assert "font-size=\"12\"" in svg_markup


def test_build_base_context_computes_metrics(sample_template):
    renderer = InfogrooveRenderer(sample_template)
    dataset = [
        {"label": "A", "value": 5},
        {"label": "B", "value": 15},
    ]

    context = renderer._build_base_context(dataset)

    assert context["canvas"]["width"] == 200
    assert context["canvas"]["height"] == 100
    assert context["properties"].gap == 24
    assert context["values"] == [5, 15]
    assert context["maxValue"] == 15
    assert context["averageValue"] == 10


def test_repeat_context_injects_reserved_variables(sample_template):
    renderer = InfogrooveRenderer(sample_template)
    base_context = renderer._build_base_context([
        {"label": "Hello", "value": 2},
    ])
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
    base_context = renderer._build_base_context([
        {"label": "A", "value": 1},
        {"label": "B", "value": 2},
    ])
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
        num_elements_range=sample_template.num_elements_range,
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
