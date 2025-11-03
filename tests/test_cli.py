import json
from pathlib import Path

import pytest

from infogroove import render_svg
from infogroove.cli import _load_data, _write_output, main
from infogroove.exceptions import DataValidationError


def test_load_data_supports_array_and_wrapped(tmp_path):
    array_path = tmp_path / "data.json"
    array_path.write_text(json.dumps([{"value": 1}]), encoding="utf-8")
    wrapped_path = tmp_path / "wrapped.json"
    wrapped_path.write_text(json.dumps({"items": [{"value": 2}]}), encoding="utf-8")

    assert _load_data(str(array_path)) == [{"value": 1}]
    assert _load_data(str(wrapped_path)) == [{"value": 2}]

    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text(json.dumps({"items": [1]}), encoding="utf-8")

    with pytest.raises(DataValidationError):
        _load_data(str(invalid_path))

    with pytest.raises(DataValidationError):
        _load_data(str(tmp_path / "missing.json"))


def test_write_output_handles_stdout(tmp_path, capsys):
    output_path = tmp_path / "output.svg"
    _write_output("<svg />", str(output_path))
    assert output_path.read_text(encoding="utf-8") == "<svg />"

    _write_output("<svg />", "-")
    captured = capsys.readouterr()
    assert "<svg />" in captured.out


def test_main_renders_svg_end_to_end(tmp_path):
    template_path = tmp_path / "def.json"
    template_path.write_text(
        json.dumps(
            {
                "properties": {"canvas": {"width": 100, "height": 100}},
                "template": [
                    {
                        "type": "text",
                        "attributes": {"x": "0", "y": "0"},
                        "text": "{item.label}",
                        "repeat": {"items": "data", "as": "item"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    data_path = tmp_path / "data.json"
    data_path.write_text(json.dumps([{"label": "Hello"}]), encoding="utf-8")
    output_path = tmp_path / "out.svg"
    exit_code = main(["-f", str(template_path), "-i", str(data_path), "-o", str(output_path)])

    assert exit_code == 0
    rendered = output_path.read_text(encoding="utf-8")
    assert "Hello" in rendered
    assert "svg" in rendered


@pytest.mark.parametrize(
    "payload",
    [
        "{}",
        "[1, 2, 3]",
        "not json",
    ],
)
def test_render_svg_helper(tmp_path, payload):
    template_path = tmp_path / "def.json"
    template_path.write_text(
        json.dumps(
            {
                "properties": {"canvas": {"width": 100, "height": 100}},
                "template": [
                    {
                        "type": "rect",
                        "attributes": {"width": "{canvas.width}", "height": "10"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    if payload == "not json":
        data_path = tmp_path / "broken.json"
        data_path.write_text(payload, encoding="utf-8")
        with pytest.raises(DataValidationError):
            _load_data(str(data_path))
        return

    data_path = tmp_path / "data.json"
    data_path.write_text(payload, encoding="utf-8")
    data = json.loads(payload)

    if isinstance(data, list):
        if all(isinstance(item, dict) for item in data):
            markup = render_svg(str(template_path), data)
            assert "svg" in markup
        else:
            with pytest.raises(DataValidationError):
                render_svg(str(template_path), data)
    else:
        with pytest.raises(DataValidationError):
            _load_data(str(data_path))
