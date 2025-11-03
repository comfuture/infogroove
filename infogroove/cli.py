"""Command line interface for Infogroove."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from .exceptions import DataValidationError, FormulaEvaluationError, RenderError, TemplateError
from .loader import load_path


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the ``infogroove`` CLI."""

    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        renderer = load_path(args.template)
        data = _load_data(args.input)
        if args.raw:
            nodes = renderer.translate(data)
            payload = json.dumps(nodes, ensure_ascii=False, indent=2)
            _write_output(payload + "\n", args.output)
        else:
            svg_markup = renderer.render(data)
            _write_output(svg_markup, args.output)
    except (TemplateError, DataValidationError, FormulaEvaluationError, RenderError) as exc:
        parser.exit(status=1, message=f"error: {exc}\n")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    """Create the argument parser used by the CLI entry point."""

    parser = argparse.ArgumentParser(description="Render infographic templates to SVG")
    parser.add_argument(
        "-f",
        "--template",
        required=True,
        help="Path to the template definition JSON file (e.g. def.json)",
    )
    parser.add_argument("-i", "--input", required=True, help="Path to the JSON data file")
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        help="Destination SVG file path or '-' for stdout",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Write the translated node specification as JSON instead of SVG markup",
    )
    return parser


def _load_data(path: str) -> list[dict[str, Any]]:
    """Load and validate the JSON payload driving the infographic."""

    data_path = Path(path)
    try:
        raw = data_path.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - filesystem dependent
        raise DataValidationError(f"Unable to read input data '{data_path}'") from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DataValidationError("Input data file is not valid JSON") from exc
    if isinstance(payload, list):
        if not all(isinstance(item, dict) for item in payload):
            raise DataValidationError("Each element in the data array must be an object")
        return payload
    if isinstance(payload, dict) and "items" in payload and isinstance(payload["items"], list):
        if not all(isinstance(item, dict) for item in payload["items"]):
            raise DataValidationError("Each element in the data array must be an object")
        return payload["items"]
    raise DataValidationError("Input data must be a JSON array of objects or contain an 'items' array")


def _write_output(markup: str, destination: str) -> None:
    """Persist the generated SVG either to disk or stdout."""

    if destination == "-":
        sys.stdout.write(markup)
        return
    output_path = Path(destination)
    output_path.write_text(markup, encoding="utf-8")


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())
