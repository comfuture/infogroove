#!/usr/bin/env python3
"""Render an Infogroove template via uvx.

This script is intended for Agent Skills workflows. It shells out to `uvx infogroove`
so Infogroove does not need to be installed in the current environment.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render an Infogroove template using uvx infogroove"
    )
    parser.add_argument("-f", "--template", required=True, help="Path to def.json")
    parser.add_argument("-i", "--input", required=True, help="Path to data.json")
    parser.add_argument(
        "-o",
        "--output",
        default="-",
        help="Destination SVG path or '-' for stdout (default: -)",
    )
    parser.add_argument(
        "--cwd",
        default=None,
        help="Optional working directory to run uvx in",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    uvx = shutil.which("uvx")
    if not uvx:
        sys.stderr.write("error: uvx not found in PATH. Install uv or add uvx to PATH.\n")
        return 1

    output = args.output
    if output != "-":
        output_path = Path(output)
        if output_path.parent:
            output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        uvx,
        "infogroove",
        "-f",
        args.template,
        "-i",
        args.input,
        "-o",
        output,
    ]
    run_kwargs = {}
    if args.cwd:
        run_kwargs["cwd"] = args.cwd
    result = subprocess.run(cmd, **run_kwargs)
    return int(result.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
