#!/usr/bin/env python3
"""Create a machine-local GUI Guider project from the public template."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE = ROOT / "project" / "guiguider_2.0.template.guiguider"
DEFAULT_OUTPUT = ROOT / "project" / "guiguider_2.0.guiguider"
TARGET_FONT_NAME = "AlibabaPuHuiTi2.ttf"
DEFAULT_PROJECT_NAME = "Figma_GuiGuider2_V9_4_local"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare a local GUI Guider project, install its external font, "
            "and replace the machine-specific projectPath."
        )
    )
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--project-name",
        default=DEFAULT_PROJECT_NAME,
        help="Independent local project name shown in GUI Guider.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing generated local project.",
    )
    parser.add_argument(
        "--font",
        type=Path,
        default=None,
        help=(
            "Path to Alibaba PuHuiTi 2.0 Regular TTF. "
            "May also be provided through GUI_GUIDER_FONT_PATH."
        ),
    )
    return parser.parse_args()


def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def local_project_id(project_name: str, output: Path) -> str:
    identity = f"{project_name}|{output.resolve()}".encode("utf-8")
    return "project-" + hashlib.sha256(identity).hexdigest()[:16].upper()


def main() -> None:
    args = parse_args()
    template = args.template.resolve()
    output = args.output.resolve()
    font = args.font
    if font is None:
        configured = os.environ.get("GUI_GUIDER_FONT_PATH")
        font = Path(configured) if configured else None

    if not template.is_file():
        raise FileNotFoundError(f"Template not found: {template}")
    if output.exists() and not args.force:
        raise FileExistsError(
            f"Output already exists: {output}\n"
            "Refusing to overwrite local GUI Guider edits. "
            "Pass --force only when replacement is intentional."
        )
    if font is None:
        raise SystemExit(
            "Missing --font. Download Alibaba PuHuiTi 2.0 Regular TTF and "
            "pass its path, or set GUI_GUIDER_FONT_PATH."
        )

    font = font.resolve()
    if not font.is_file():
        raise FileNotFoundError(f"Font not found: {font}")
    if font.suffix.lower() != ".ttf":
        raise ValueError("GUI Guider project requires the Regular .ttf file")

    project = json.loads(template.read_text(encoding="utf-8"))
    if "UI" not in project or "projectSettings" not in project:
        raise ValueError(f"Not a supported GUI Guider project: {template}")

    project["projectId"] = local_project_id(args.project_name, output)
    project["projectPath"] = str(output.parent)
    project["projectName"] = args.project_name

    target_font = output.parent / "resources" / "font" / TARGET_FONT_NAME
    target_font.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(font, target_font)
    atomic_write_json(output, project)

    screen_count = len(project["UI"].get("screen_list", []))
    print(f"Prepared: {output}")
    print(f"Project name: {project['projectName']}")
    print(f"Project ID: {project['projectId']}")
    print(f"Installed font: {target_font}")
    print(f"GUI Guider entries: {screen_count}")


if __name__ == "__main__":
    main()
