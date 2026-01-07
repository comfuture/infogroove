from infogroove.core import Infogroove


def test_readme_attribute_values_require_placeholders():
    renderer = Infogroove(
        {
            "properties": {"canvas": {"width": 120, "height": 80}},
            "template": [
                {
                    "type": "rect",
                    "attributes": {
                        "x": "0",
                        "y": "0",
                        "width": "1 + 2",
                        "height": "{1 + 2}",
                    },
                }
            ],
        }
    )

    node_specs = renderer.translate({})

    assert node_specs[0]["attributes"]["width"] == "1 + 2"
    assert node_specs[0]["attributes"]["height"] == "3"


def test_readme_let_placeholder_fullmatch_returns_raw():
    renderer = Infogroove(
        {
            "properties": {"canvas": {"width": 120, "height": 80}},
            "template": [
                {
                    "type": "text",
                    "let": {
                        "base": "{items[0].value}",
                        "double": "base * 2",
                    },
                    "attributes": {"x": "0", "y": "0"},
                    "text": "{double}",
                }
            ],
        }
    )

    node_specs = renderer.translate({"items": [{"value": 3}]})

    assert node_specs[0]["text"] == "6"
