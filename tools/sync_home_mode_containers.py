#!/usr/bin/env python3
"""Safely upsert the final Figma List/Arb mode containers into Home."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Iterator

import sync_completed_figma_to_guiguider as converter


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROJECT = ROOT / "guiguider_2.0.guiguider"
DEFAULT_MANIFEST_ROOT = (
    ROOT / "tools" / "manifests" / "home_modes_final_20260727"
)
DEFAULT_OUTPUT = (
    ROOT
    / "tools"
    / "artifacts"
    / "figma_sync_20260727_completed"
    / "guiguider_2.0.home_modes_candidate.guiguider"
)
DEFAULT_REPORT = (
    ROOT
    / "tools"
    / "artifacts"
    / "figma_sync_20260727_completed"
    / "home_modes_report.json"
)

MODE_SPECS = [
    {
        "id": "525:35",
        "name": "cont_Arb",
        "target_name": "cont_home_arb",
        "kind": "home_container",
        "directory": "525_35",
    },
    {
        "id": "525:2",
        "name": "cont_list",
        "target_name": "cont_home_list",
        "kind": "home_container",
        "directory": "525_2",
    },
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def iter_objects(nodes: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    for node in nodes:
        yield node
        yield from iter_objects(node.get("children", []))


def find_one(nodes: list[dict[str, Any]], *, name: str) -> dict[str, Any]:
    matches = [node for node in iter_objects(nodes) if node.get("name") == name]
    if len(matches) != 1:
        raise AssertionError(f"Expected one {name}, found {len(matches)}")
    return matches[0]


def remove_figma_roots(
    nodes: list[dict[str, Any]], figma_ids: set[str]
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for node in nodes:
        if node.get("figma_id") in figma_ids:
            continue
        node = copy.deepcopy(node)
        node["children"] = remove_figma_roots(
            node.get("children", []), figma_ids
        )
        result.append(node)
    return result


def screen_hash(screen: dict[str, Any]) -> str:
    data = json.dumps(
        screen, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=DEFAULT_PROJECT)
    parser.add_argument("--manifest-root", type=Path, default=DEFAULT_MANIFEST_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project = json.loads(args.project.read_text(encoding="utf-8"))
    screens = project["UI"]["screen_list"]

    home = find_one(screens, name="Home")
    back = find_one(screens, name="Back")
    menu = find_one(screens, name="HOME_MENU")
    preserved_before = {
        "Back": screen_hash(back),
        "HOME_MENU": screen_hash(menu),
    }
    home_before = screen_hash(home)
    existing_mode_roots = {
        node.get("figma_id")
        for node in iter_objects([home])
        if node.get("figma_id") in {spec["id"] for spec in MODE_SPECS}
    }

    existing_names = {
        node["figma_id"]: node["name"]
        for node in iter_objects(screens)
        if node.get("figma_id") and node.get("name")
    }
    mode_subtree_ids: set[str] = set()
    for node in iter_objects(screens):
        if node.get("figma_id") in {spec["id"] for spec in MODE_SPECS}:
            mode_subtree_ids.update(
                child["figma_id"]
                for child in iter_objects([node])
                if child.get("figma_id")
            )
    reserved = {
        node["name"]
        for node in iter_objects(screens)
        if node.get("name")
        and node.get("figma_id") not in mode_subtree_ids
    }
    allocator = converter.NameAllocator(reserved)
    conversion_report: dict[str, Any] = {
        "flattened_nodes": [],
        "text_box_corrections": [],
        "assets": [],
        "semantic_pending": [],
    }

    built_modes: list[dict[str, Any]] = []
    for spec in MODE_SPECS:
        source = converter.parse_compact_tree(
            args.manifest_root / spec["directory"],
            converter.legacy_asset_urls(spec),
        )
        built = converter.build_screen(
            spec, source, allocator, existing_names, conversion_report
        )
        built["name"] = spec["target_name"]
        built["x"] = 0
        built["y"] = 40
        built["width"] = 320
        built["height"] = 152
        built["hidden"] = True
        built["opacity"] = 0
        built["scrollbar_mode"] = "OFF"
        built["remove_flag"] = ["LV_OBJ_FLAG_SCROLLABLE"]
        built_modes.append(built)

    home["children"] = remove_figma_roots(
        home.get("children", []), {spec["id"] for spec in MODE_SPECS}
    )
    panel_settings = find_one(home.get("children", []), name="panel_settings")
    children = panel_settings.get("children", [])
    insert_at = next(
        index
        for index, child in enumerate(children)
        if child.get("name") == "panel_setpoints"
    )
    # GUI Guider stores this child stack in reverse Figma z-order.
    panel_settings["children"] = (
        children[:insert_at] + built_modes[::-1] + children[insert_at:]
    )

    all_nodes = list(iter_objects(screens))
    names = [node.get("name") for node in all_nodes if node.get("name")]
    ids = [node.get("id") for node in all_nodes if node.get("id")]
    figma_ids = [
        node.get("figma_id") for node in all_nodes if node.get("figma_id")
    ]
    assert len(names) == len(set(names))
    assert len(ids) == len(set(ids))
    assert len(figma_ids) == len(set(figma_ids))
    assert screen_hash(back) == preserved_before["Back"]
    assert screen_hash(menu) == preserved_before["HOME_MENU"]
    if existing_mode_roots != {spec["id"] for spec in MODE_SPECS}:
        assert home_before != screen_hash(home)

    panel_names = [child["name"] for child in panel_settings["children"]]
    expected_slice = ["cont_home_list", "cont_home_arb", "panel_setpoints"]
    start = panel_names.index("cont_home_list")
    assert panel_names[start : start + 3] == expected_slice
    for figma_id in ("525:2", "525:35"):
        matches = [node for node in all_nodes if node.get("figma_id") == figma_id]
        assert len(matches) == 1
        node = matches[0]
        assert (node["x"], node["y"], node["width"], node["height"]) == (
            0,
            40,
            320,
            152,
        )
        assert node["hidden"] is True and node["opacity"] == 0
    home_mode_labels = [
        node
        for node in all_nodes
        if node.get("type") == "label"
        and node.get("figma_id", "").startswith("525:")
    ]
    assert home_mode_labels
    for label in home_mode_labels:
        family = label["style"][converter.MAIN_STYLE]["text_family"]
        assert family == "Inter-Medium"
        assert (ROOT / "resources" / "font" / f"{family}.ttf").exists()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(project, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    report = {
        "schema_version": "figma-home-mode-sync-report/v1",
        "input_project": str(args.project.resolve()),
        "input_sha256": sha256(args.project),
        "output_project": str(args.output.resolve()),
        "output_sha256": sha256(args.output),
        "home_hash_before": home_before,
        "home_hash_after": screen_hash(home),
        "preserved_screen_hashes": preserved_before,
        "inserted": [
            {
                "figma_id": node["figma_id"],
                "name": node["name"],
                "size": [node["width"], node["height"]],
                "position": [node["x"], node["y"]],
                "hidden": node["hidden"],
            }
            for node in built_modes
        ],
        "panel_settings_child_order": panel_names,
        "conversion": conversion_report,
        "validation": {
            "unique_names": len(names),
            "unique_ids": len(ids),
            "unique_figma_ids": len(figma_ids),
            "back_unchanged": True,
            "home_menu_unchanged": True,
        },
    }
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
