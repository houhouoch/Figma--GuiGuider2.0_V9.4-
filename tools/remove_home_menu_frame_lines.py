#!/usr/bin/env python3
"""Remove the exposed right/bottom frame lines from HOME_MENU.

The lines are the HOME_MENU screen's one-pixel main-part border, not the
scrollbars of cont_menu_function or cont_menu_content. This updater changes
only the screen border width and opacity, preserving all user-edited children.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MAIN_STYLE = "LV_PART_MAIN|LV_STATE_DEFAULT"
TARGET_FIGMA_ID = "130:6"
TARGET_NAME = "HOME_MENU"
DEFAULT_INPUT = ROOT / "guiguider_2.0.guiguider"
DEFAULT_OUTPUT = (
    ROOT
    / "tools"
    / "artifacts"
    / "home_menu_scrollbar_fix_20260727"
    / "guiguider_2.0.no_home_menu_frame_lines.guiguider"
)
DEFAULT_REPORT = (
    ROOT
    / "tools"
    / "artifacts"
    / "home_menu_scrollbar_fix_20260727"
    / "home_menu_frame_lines_report.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-project", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-project", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as stream:
        return json.load(stream)


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def screens(project: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        node
        for node in project["UI"]["screen_list"]
        if node.get("type") == "screen"
    ]


def find_target(project: dict[str, Any]) -> dict[str, Any]:
    matches = [
        screen
        for screen in screens(project)
        if screen.get("figma_id") == TARGET_FIGMA_ID
    ]
    assert len(matches) == 1, "Expected exactly one HOME_MENU screen"
    target = matches[0]
    assert target.get("name") == TARGET_NAME
    return target


def masked_project(project: dict[str, Any]) -> dict[str, Any]:
    masked = deepcopy(project)
    style = find_target(masked)["style"][MAIN_STYLE]
    style["border_width"] = "<MASKED>"
    style["border_opa"] = "<MASKED>"
    return masked


def main() -> None:
    args = parse_args()
    before = load_json(args.input_project)
    assert len(screens(before)) == 15
    target_before = find_target(before)
    style_before = deepcopy(target_before["style"][MAIN_STYLE])

    # The child containers already have LV_SCROLLBAR_MODE_OFF. The visible
    # right/bottom lines come from this parent screen border.
    for figma_id in ("176:2", "176:10", "176:11"):
        matches: list[dict[str, Any]] = []

        def visit(node: dict[str, Any]) -> None:
            if node.get("figma_id") == figma_id:
                matches.append(node)
            for child in node.get("children", []):
                visit(child)

        visit(target_before)
        assert len(matches) == 1
        assert matches[0].get("scrollbar_mode") == "LV_SCROLLBAR_MODE_OFF"

    after = deepcopy(before)
    style_after = find_target(after)["style"][MAIN_STYLE]
    style_after["border_width"] = 0
    style_after["border_opa"] = 0

    assert canonical_hash(masked_project(after)) == canonical_hash(
        masked_project(before)
    ), "Unexpected mutation outside HOME_MENU screen border"
    assert len(screens(after)) == 15
    assert sum(bool(screen.get("default_screen")) for screen in screens(after)) == 1
    assert next(
        screen for screen in screens(after) if screen.get("default_screen")
    ).get("figma_id") == "71:3"

    # A second pass must make no structural change.
    repeat = deepcopy(after)
    repeat_style = find_target(repeat)["style"][MAIN_STYLE]
    repeat_style["border_width"] = 0
    repeat_style["border_opa"] = 0
    assert repeat == after

    write_json(args.output_project, after)
    report = {
        "diagnosis": (
            "The exposed right and bottom gray lines were the HOME_MENU "
            "screen main-part border, not child-container scrollbars."
        ),
        "target": {
            "figma_id": TARGET_FIGMA_ID,
            "name": TARGET_NAME,
            "style_part": MAIN_STYLE,
        },
        "input_project": str(args.input_project),
        "output_project": str(args.output_project),
        "input_sha256": file_hash(args.input_project),
        "output_sha256": file_hash(args.output_project),
        "changes": {
            "border_width": {
                "before": style_before.get("border_width"),
                "after": style_after.get("border_width"),
            },
            "border_opa": {
                "before": style_before.get("border_opa"),
                "after": style_after.get("border_opa"),
            },
        },
        "validation": {
            "only_home_menu_screen_border_changed": True,
            "manual_child_edits_preserved": True,
            "menu_child_scrollbars_already_off": True,
            "screen_count": 15,
            "default_screen": "Home",
            "second_pass_identical": True,
        },
    }
    write_json(args.report, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
