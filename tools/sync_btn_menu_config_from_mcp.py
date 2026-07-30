#!/usr/bin/env python3
"""Synchronize only HOME_MENU/btn_menu_config's default main style.

The live Figma node is supplied by a read-only figma.use_figma manifest.
Geometry, children, events, IDs, project settings, and every other screen are
treated as immutable inputs.
"""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterator

from sync_home_menu_from_mcp import (
    EXPECTED_SCREEN_IDS,
    MAIN_STYLE,
    canonical_hash,
    file_hash,
    project_screens,
    visual_style,
    write_json,
)


ROOT = Path(__file__).resolve().parents[1]
TARGET_FIGMA_ID = "176:12"
TARGET_NAME = "btn_menu_config"
MENU_FIGMA_ID = "130:6"
DEFAULT_INPUT = ROOT / "guiguider_2.0.guiguider"
DEFAULT_MANIFEST = (
    ROOT
    / "tools"
    / "manifests"
    / "btn_menu_config_20260725"
    / "176_12.json"
)
DEFAULT_OUTPUT = (
    ROOT
    / "tools"
    / "artifacts"
    / "btn_menu_config_sync_20260725"
    / "guiguider_2.0.btn_menu_config_candidate.guiguider"
)
DEFAULT_REPORT = (
    ROOT
    / "tools"
    / "artifacts"
    / "btn_menu_config_sync_20260725"
    / "btn_menu_config_sync_report.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-project", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-project", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as stream:
        return json.load(stream)


def walk(nodes: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    for node in nodes:
        yield node
        children = node.get("children")
        if isinstance(children, list):
            yield from walk(children)


def project_nodes(project: dict[str, Any]) -> list[dict[str, Any]]:
    return list(walk(project["UI"]["screen_list"]))


def find_node(project: dict[str, Any], figma_id: str) -> dict[str, Any]:
    matches = [
        node
        for node in project_nodes(project)
        if node.get("figma_id") == figma_id
    ]
    assert len(matches) == 1, f"Expected one GUI node for Figma ID {figma_id}"
    return matches[0]


def find_screen(project: dict[str, Any], figma_id: str) -> dict[str, Any]:
    matches = [
        screen
        for screen in project_screens(project)
        if screen.get("figma_id") == figma_id
    ]
    assert len(matches) == 1, f"Expected one screen for Figma ID {figma_id}"
    return matches[0]


def report_template() -> dict[str, Any]:
    return {
        "mixed_corner_radius_reductions": [],
        "gradient_stop_reductions": [],
        "unsupported_inner_shadows": [],
        "unsupported_label_shadows": [],
        "font_fallbacks": [],
        "preserved_font_baseline_compensation": [],
    }


def assert_project_invariants(project: dict[str, Any]) -> None:
    settings = project["projectSettings"]
    assert settings["lvglVersion"] == "9.4.0"
    assert (settings["width"], settings["height"]) == (960, 240)
    assert settings["targetConfig"]["colorDepth"] == 16
    assert settings["imageConfig"]["color_format"] == "RGB565A8"

    screens = project_screens(project)
    assert len(screens) == 15
    assert {screen["figma_id"] for screen in screens} == EXPECTED_SCREEN_IDS
    defaults = [screen for screen in screens if screen.get("default_screen")]
    assert len(defaults) == 1
    assert defaults[0]["figma_id"] == "71:3"
    # GUI Guider 2.0 stores the canvas dimensions once in projectSettings;
    # screen objects intentionally do not duplicate width/height fields.

    all_nodes = project_nodes(project)
    names = [node["name"] for node in all_nodes]
    ids = [node["id"] for node in all_nodes]
    figma_ids = [
        node["figma_id"]
        for node in all_nodes
        if isinstance(node.get("figma_id"), str)
    ]
    assert len(names) == len(set(names)), "Duplicate GUI names"
    assert len(ids) == len(set(ids)), "Duplicate GUI IDs"
    assert len(figma_ids) == len(set(figma_ids)), "Duplicate Figma IDs"


def masked_project(project: dict[str, Any]) -> dict[str, Any]:
    masked = deepcopy(project)
    target = find_node(masked, TARGET_FIGMA_ID)
    target["style"][MAIN_STYLE] = "<TARGET_MAIN_STYLE>"
    return masked


def changed_fields(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    return {
        key: {"before": before.get(key), "after": after.get(key)}
        for key in sorted(set(before) | set(after))
        if before.get(key) != after.get(key)
    }


def main() -> None:
    args = parse_args()
    before = load_json(args.input_project)
    manifest = load_json(args.manifest)
    source = manifest["node"]

    assert manifest["source"]["tool"] == "figma.use_figma"
    assert manifest["source"]["read_only"] is True
    assert source["id"] == TARGET_FIGMA_ID
    assert source["parent_id"] == "176:11"
    assert source["name"] == TARGET_NAME
    assert source["type"] == "FRAME"

    assert_project_invariants(before)
    target_before = find_node(before, TARGET_FIGMA_ID)
    assert target_before["name"] == TARGET_NAME
    assert target_before["type"] == "button"
    assert (
        target_before["x"],
        target_before["y"],
        target_before["width"],
        target_before["height"],
    ) == (
        source["x"],
        source["y"],
        source["width"],
        source["height"],
    ), "Style-only sync refused because Figma geometry changed"
    assert [child["figma_id"] for child in target_before["children"]] == source[
        "child_ids"
    ], "Style-only sync refused because Figma child order changed"

    before_children_hash = canonical_hash(target_before["children"])
    before_screen_hashes = {
        screen["figma_id"]: canonical_hash(screen)
        for screen in project_screens(before)
    }
    before_masked_hash = canonical_hash(masked_project(before))
    before_style = deepcopy(target_before["style"][MAIN_STYLE])

    after = deepcopy(before)
    target_after = find_node(after, TARGET_FIGMA_ID)
    conversion_report = report_template()
    new_style = visual_style(source, target_after, conversion_report)
    target_after["style"][MAIN_STYLE] = new_style

    # The conversion is deliberately idempotent.
    repeat_report = report_template()
    assert visual_style(source, target_after, repeat_report) == new_style

    assert_project_invariants(after)
    assert canonical_hash(masked_project(after)) == before_masked_hash, (
        "Unexpected project mutation outside btn_menu_config main style"
    )
    assert canonical_hash(target_after["children"]) == before_children_hash
    assert {
        screen["figma_id"]: canonical_hash(screen)
        for screen in project_screens(after)
        if screen["figma_id"] != MENU_FIGMA_ID
    } == {
        screen_id: screen_hash
        for screen_id, screen_hash in before_screen_hashes.items()
        if screen_id != MENU_FIGMA_ID
    }
    assert before["projectSettings"] == after["projectSettings"]
    assert before["lvConf"] == after["lvConf"]
    assert before.get("metadata") == after.get("metadata")
    assert before["UI"].get("event_list") == after["UI"].get("event_list")
    assert before["UI"].get("variable_setting") == after["UI"].get(
        "variable_setting"
    )

    write_json(args.output_project, after)
    report = {
        "source": manifest["source"],
        "target": {
            "screen_figma_id": MENU_FIGMA_ID,
            "figma_id": TARGET_FIGMA_ID,
            "name": TARGET_NAME,
        },
        "input_project": str(args.input_project),
        "output_project": str(args.output_project),
        "input_sha256": file_hash(args.input_project),
        "output_sha256": file_hash(args.output_project),
        "changed_style_fields": changed_fields(before_style, new_style),
        "before_style": before_style,
        "after_style": new_style,
        "conversion_notes": conversion_report,
        "validation": {
            "screen_count": 15,
            "default_screen": "Home",
            "project_canvas_960x240": True,
            "only_target_main_style_changed": True,
            "target_children_unchanged": True,
            "project_settings_unchanged": True,
            "lv_conf_unchanged": True,
            "events_unchanged": True,
            "variables_unchanged": True,
            "second_style_pass_identical": True,
        },
    }
    write_json(args.report, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
