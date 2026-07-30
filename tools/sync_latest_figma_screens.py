#!/usr/bin/env python3
"""Incrementally synchronize the latest Figma MCP screen manifests.

The script rebuilds only screens whose Figma source changed, using the same
reviewed semantic rules as the original MCP conversion. Home, Back, Recorder,
project settings, events, and all unchanged screens remain structurally exact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterator

from PIL import Image

from build_figma_screen import FONT_FILES as EXISTING_FONT_FILES
from build_mcp_screens import (
    MAIN_STYLE,
    NameAllocator,
    apply_figma_button_shadow,
    build_screen,
    find_screen_by_figma_id,
    iter_project_nodes,
    load_manifest_nodes,
    normalize_figma_sibling_order,
    normalize_switch_widgets,
    normalized_hash,
    visible_drop_shadow,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "guiguider_2.0.guiguider"
DEFAULT_MANIFEST = (
    ROOT / "tools" / "manifests" / "v3_20260725_latest" / "index.json"
)
DEFAULT_OVERRIDES = (
    ROOT / "tools" / "manifests" / "v1" / "semantic_overrides.json"
)
DEFAULT_OUTPUT = (
    ROOT
    / "tools"
    / "artifacts"
    / "figma_sync_20260725_v3"
    / "guiguider_2.0.v3_candidate.guiguider"
)
DEFAULT_REPORT = (
    ROOT
    / "tools"
    / "artifacts"
    / "figma_sync_20260725_v3"
    / "v3_sync_report.json"
)
OLD_V1 = ROOT / "tools" / "manifests" / "v1"
OLD_V2 = ROOT / "tools" / "manifests" / "v2_home_menu_20260725"

IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
EXPECTED_SCREEN_IDS = {
    "130:2",
    "71:3",
    "130:6",
    "243:234",
    "243:280",
    "243:328",
    "243:331",
    "243:361",
    "243:433",
    "243:524",
    "243:609",
    "243:187",
    "243:135",
    "217:2",
    "199:2",
}
SPECIALIZED_SCREEN_IDS = {"130:2", "71:3", "130:6"}
UNCHANGED_EXPECTED = {"130:2", "71:3", "243:328"}
MENU_ID = "130:6"
HOME_ID = "71:3"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-project", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--manifest-index", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--semantic-overrides", type=Path, default=DEFAULT_OVERRIDES)
    parser.add_argument("--output-project", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as stream:
        return json.load(stream)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, ensure_ascii=True, indent=2)
        stream.write("\n")


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def walk(nodes: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    for node in nodes:
        yield node
        children = node.get("children")
        if isinstance(children, list):
            yield from walk(children)


def screen_list(project: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        node
        for node in project["UI"]["screen_list"]
        if node.get("type") == "screen"
    ]


def read_manifest_directory(directory: Path) -> list[dict[str, Any]]:
    fragments = sorted(directory.glob("chunk_*.json"))
    assert fragments, f"No manifest chunks in {directory}"
    nodes: list[dict[str, Any]] = []
    expected_start = 0
    expected_total: int | None = None
    for fragment_path in fragments:
        fragment = load_json(fragment_path)
        chunk = fragment["chunk"]
        assert chunk["start"] == expected_start
        if expected_total is None:
            expected_total = chunk["total"]
        assert chunk["total"] == expected_total
        nodes.extend(fragment["nodes"])
        expected_start += len(fragment["nodes"])
    assert len(nodes) == expected_total
    return nodes


def old_manifest_nodes(screen_id: str) -> list[dict[str, Any]] | None:
    directory = screen_id.replace(":", "_")
    if screen_id in {"71:3", "130:6"}:
        return read_manifest_directory(OLD_V2 / directory)
    if screen_id == "130:2":
        return None
    return read_manifest_directory(OLD_V1 / directory)


def clean_value(value: Any) -> Any:
    if isinstance(value, list):
        return [clean_value(item) for item in value]
    if isinstance(value, dict):
        return {
            key: clean_value(item)
            for key, item in sorted(value.items())
            if key not in {"boundVariables", "styledSegments"}
        }
    return value


def common_text(text: dict[str, Any] | None) -> dict[str, Any] | None:
    if text is None:
        return None
    keys = (
        "characters",
        "fontName",
        "fontSize",
        "fontWeight",
        "textAlignHorizontal",
        "textAlignVertical",
        "lineHeight",
        "letterSpacing",
        "paragraphSpacing",
        "textAutoResize",
    )
    return clean_value({key: text.get(key) for key in keys})


def comparable_node(
    node: dict[str, Any],
    root_id: str,
) -> dict[str, Any]:
    return clean_value(
        {
            "parent_id": node.get("parent_id"),
            "order": node.get("order", 0),
            "name": node["name"],
            "type": node["type"],
            "x": 0 if node["id"] == root_id else node["x"],
            "y": 0 if node["id"] == root_id else node["y"],
            "width": node["width"],
            "height": node["height"],
            "visible": node.get("visible", True),
            "opacity": node.get("opacity", 1),
            "rotation": node.get("rotation", 0),
            "clipsContent": bool(node.get("clipsContent", False)),
            "layoutMode": node.get("layoutMode") or "NONE",
            "fills": node.get("fills", []),
            "strokes": node.get("strokes", []),
            "strokeWeight": node.get("strokeWeight", 0),
            "strokeAlign": node.get("strokeAlign") or "INSIDE",
            "cornerRadius": (
                node.get("cornerRadius")
                if node.get("cornerRadius") is not None
                else 0
            ),
            "cornerRadii": node.get("cornerRadii", []),
            "effects": node.get("effects", []),
            "text": common_text(node.get("text")),
        }
    )


def screen_diff(
    screen_id: str,
    old_nodes: list[dict[str, Any]] | None,
    new_nodes: list[dict[str, Any]],
) -> dict[str, Any]:
    if old_nodes is None:
        return {
            "figma_id": screen_id,
            "baseline": "no_previous_mcp_manifest",
            "added": [],
            "removed": [],
            "changed_nodes": [],
            "changed": False,
        }

    old_by_id = {node["id"]: node for node in old_nodes}
    new_by_id = {node["id"]: node for node in new_nodes}
    added = sorted(new_by_id.keys() - old_by_id.keys())
    removed = sorted(old_by_id.keys() - new_by_id.keys())
    changed_nodes: list[dict[str, Any]] = []
    for figma_id in sorted(old_by_id.keys() & new_by_id.keys()):
        old = comparable_node(old_by_id[figma_id], screen_id)
        new = comparable_node(new_by_id[figma_id], screen_id)
        fields = [key for key in new if old[key] != new[key]]
        if fields:
            changed_nodes.append(
                {
                    "figma_id": figma_id,
                    "name": new_by_id[figma_id]["name"],
                    "fields": fields,
                }
            )
    return {
        "figma_id": screen_id,
        "baseline": "previous_figma_mcp_manifest",
        "old_count": len(old_nodes),
        "new_count": len(new_nodes),
        "added": added,
        "removed": removed,
        "changed_nodes": changed_nodes,
        "changed": bool(added or removed or changed_nodes),
    }


def load_new_manifests(
    index_path: Path,
) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]], dict[str, dict[str, Any]]]:
    index = load_json(index_path)
    assert index["source"]["tool"] == "figma.use_figma"
    assert index["source"]["read_only"] is True
    assert {spec["id"] for spec in index["screens"]} == EXPECTED_SCREEN_IDS
    per_screen: dict[str, list[dict[str, Any]]] = {}
    all_nodes: dict[str, dict[str, Any]] = {}
    for spec in index["screens"]:
        nodes = load_manifest_nodes(index_path, spec)
        assert len(nodes) == spec["count"]
        ids = [node["id"] for node in nodes]
        assert len(ids) == len(set(ids))
        id_set = set(ids)
        orphans = [
            node["id"]
            for node in nodes
            if node.get("parent_id") and node["parent_id"] not in id_set
        ]
        assert not orphans, f"Orphan manifest nodes in {spec['id']}: {orphans}"
        for node in nodes:
            assert node["id"] not in all_nodes
            all_nodes[node["id"]] = node
        per_screen[spec["id"]] = nodes
    return index, per_screen, all_nodes


def prune_figma_ids(
    node: dict[str, Any],
    removed: set[str],
) -> list[dict[str, Any]]:
    deleted: list[dict[str, Any]] = []
    children = node.get("children")
    if not isinstance(children, list):
        return deleted
    kept: list[dict[str, Any]] = []
    for child in children:
        if child.get("figma_id") in removed:
            deleted.extend(
                {
                    "figma_id": descendant.get("figma_id"),
                    "name": descendant.get("name"),
                    "type": descendant.get("type"),
                }
                for descendant in walk([child])
            )
            continue
        deleted.extend(prune_figma_ids(child, removed))
        kept.append(child)
    node["children"] = kept
    return deleted


def screen_node_names(screen: dict[str, Any]) -> set[str]:
    return {node["name"] for node in walk([screen])}


def rebuild_changed_screens(
    project: dict[str, Any],
    index: dict[str, Any],
    per_screen: dict[str, list[dict[str, Any]]],
    changed_ids: set[str],
    overrides: dict[str, Any],
    report: dict[str, Any],
) -> list[dict[str, Any]]:
    rebuild_ids = changed_ids - SPECIALIZED_SCREEN_IDS
    specs = [spec for spec in index["screens"] if spec["id"] in rebuild_ids]
    replaced_names = set()
    for screen_id in rebuild_ids:
        replaced_names.update(
            screen_node_names(find_screen_by_figma_id(project, screen_id))
        )
    reserved_names = {
        node.get("name", "")
        for node in iter_project_nodes(project)
        if node.get("name", "") not in replaced_names
    }
    allocator = NameAllocator(reserved_names)
    rebuilt: list[dict[str, Any]] = []
    for spec in specs:
        old_screen = find_screen_by_figma_id(project, spec["id"])
        old_by_figma_id = {
            node["figma_id"]: node
            for node in walk([old_screen])
            if isinstance(node.get("figma_id"), str)
        }
        new_screen = build_screen(
            spec,
            per_screen[spec["id"]],
            overrides,
            allocator,
            report,
        )
        new_by_figma_id = {
            node["figma_id"]: node
            for node in walk([new_screen])
            if isinstance(node.get("figma_id"), str)
        }
        for figma_id in old_by_figma_id.keys() & new_by_figma_id.keys():
            assert old_by_figma_id[figma_id]["id"] == new_by_figma_id[figma_id]["id"]
            assert old_by_figma_id[figma_id]["name"] == new_by_figma_id[figma_id]["name"], (
                f"Stable GUI name changed for {figma_id}: "
                f"{old_by_figma_id[figma_id]['name']} -> "
                f"{new_by_figma_id[figma_id]['name']}"
            )
        position = project["UI"]["screen_list"].index(old_screen)
        project["UI"]["screen_list"][position] = new_screen
        rebuilt.append(
            {
                "figma_id": spec["id"],
                "name": new_screen["name"],
                "old_gui_node_count": len(old_by_figma_id),
                "new_gui_node_count": len(new_by_figma_id),
            }
        )
    return rebuilt


def validate_assets(
    project: dict[str, Any],
    overrides: dict[str, Any],
) -> dict[str, Any]:
    font_files = dict(EXISTING_FONT_FILES)
    font_files.update(overrides["font_files"])
    used_fonts: set[str] = set()
    image_count = 0
    transparent_images = 0
    for node in iter_project_nodes(project):
        style = node.get("style", {}).get(MAIN_STYLE, {})
        family = style.get("text_family")
        if family:
            used_fonts.add(family)
        if node.get("type") != "image":
            continue
        image_count += 1
        source = node.get("src", "").replace("\\", "/")
        assert source
        image_path = ROOT / source
        assert image_path.is_file(), f"Missing image: {source}"
        with Image.open(image_path) as image:
            assert image.format == "PNG"
            assert image.width > 0 and image.height > 0
            assert "A" in image.getbands(), f"Image lacks alpha: {source}"
            alpha_min, _ = image.getchannel("A").getextrema()
            if alpha_min < 255:
                transparent_images += 1

    unknown_fonts = used_fonts - font_files.keys()
    assert not unknown_fonts, f"Unmapped fonts: {sorted(unknown_fonts)}"
    for family in used_fonts:
        path = ROOT / "resources" / "font" / font_files[family]
        assert path.is_file(), f"Missing font: {path}"
    return {
        "image_count": image_count,
        "images_with_transparent_pixels": transparent_images,
        "font_families": sorted(used_fonts),
    }


def validate_project(
    before: dict[str, Any],
    after: dict[str, Any],
    per_screen: dict[str, list[dict[str, Any]]],
    changed_ids: set[str],
    overrides: dict[str, Any],
) -> dict[str, Any]:
    source_by_id = {
        node["id"]: node
        for manifest in per_screen.values()
        for node in manifest
    }
    assert before["projectSettings"] == after["projectSettings"]
    assert before["lvConf"] == after["lvConf"]
    assert before.get("metadata") == after.get("metadata")
    assert before["UI"].get("event_list") == after["UI"].get("event_list")
    assert before["UI"].get("variable_setting") == after["UI"].get("variable_setting")
    settings = after["projectSettings"]
    assert settings["lvglVersion"] == "9.4.0"
    assert (settings["width"], settings["height"]) == (960, 240)
    assert settings["targetConfig"]["colorDepth"] == 16
    assert settings["imageConfig"]["color_format"] == "RGB565A8"

    nodes = list(iter_project_nodes(after))
    names = [node.get("name", "") for node in nodes]
    ids = [node.get("id", "") for node in nodes]
    figma_ids = [
        node["figma_id"]
        for node in nodes
        if isinstance(node.get("figma_id"), str)
    ]
    assert all(IDENTIFIER.fullmatch(name) for name in names)
    assert len(names) == len(set(names)), "Duplicate GUI names"
    assert len(ids) == len(set(ids)), "Duplicate GUI IDs"
    assert len(figma_ids) == len(set(figma_ids)), "Duplicate Figma IDs"

    screens = screen_list(after)
    assert len(screens) == 15
    assert {screen["figma_id"] for screen in screens} == EXPECTED_SCREEN_IDS
    assert sum(bool(screen.get("default_screen")) for screen in screens) == 1
    assert find_screen_by_figma_id(after, HOME_ID)["default_screen"] is True
    for screen_id, manifest in per_screen.items():
        root = next(node for node in manifest if node["id"] == screen_id)
        assert (round(root["width"]), round(root["height"])) == (960, 240)

    before_hashes = {
        screen["figma_id"]: normalized_hash(screen)
        for screen in screen_list(before)
    }
    after_hashes = {
        screen["figma_id"]: normalized_hash(screen)
        for screen in screens
    }
    for screen_id in EXPECTED_SCREEN_IDS - changed_ids:
        assert before_hashes[screen_id] == after_hashes[screen_id], (
            f"Unchanged screen was modified: {screen_id}"
        )
    actually_changed_ids = {
        screen_id
        for screen_id in changed_ids
        if before_hashes[screen_id] != after_hashes[screen_id]
    }
    assert not actually_changed_ids or actually_changed_ids == changed_ids, (
        "Partial incremental update: "
        f"{sorted(actually_changed_ids)} != {sorted(changed_ids)}"
    )

    for node in nodes:
        node_type = node.get("type")
        name = node.get("name", "")
        if name.startswith("screen_"):
            assert node_type == "screen"
        if name.startswith(("btn_", "button_")):
            assert node_type == "button"
        if name.startswith("sw_"):
            assert node_type == "switch"
        if name.startswith("label_"):
            assert node_type == "label"
        if name.startswith("img_"):
            assert node_type == "image"
        if name.startswith(("cont_", "panel_", "decor_")):
            assert node_type == "container"
        if name.startswith(("led_", "indicator_")):
            assert node_type == "led"
        if node_type == "label":
            assert node["width_unit"] == node["height_unit"] == "px"
            assert node["width"] > 0 and node["height"] > 0
        if node_type == "button":
            source = source_by_id.get(node.get("figma_id"))
            if source is not None and visible_drop_shadow(source) is None:
                style = node["style"][MAIN_STYLE]
                for key in (
                    "shadow_opa",
                    "shadow_offset_x",
                    "shadow_offset_y",
                    "shadow_width",
                    "shadow_spread",
                ):
                    assert style.get(key) == 0, (
                        f"Unexpected inherited button shadow: "
                        f"{node['name']}.{key}"
                    )
        if node_type == "switch":
            style = node.get("style", {})
            assert {
                MAIN_STYLE,
                "LV_PART_INDICATOR|LV_STATE_DEFAULT",
                "LV_PART_INDICATOR|LV_STATE_CHECKED",
                "LV_PART_KNOB|LV_STATE_DEFAULT",
            }.issubset(style), f"Incomplete switch style: {node['name']}"
            assert not node.get("children"), (
                f"Figma knob must be folded into switch style: {node['name']}"
            )

    project_figma_ids = set(figma_ids)
    unknown_gui_sources = project_figma_ids - source_by_id.keys()
    assert not unknown_gui_sources, (
        f"GUI nodes missing from latest Figma source: "
        f"{sorted(unknown_gui_sources)}"
    )
    expected_switch_ids = {
        node["id"]
        for node in source_by_id.values()
        if node.get("name", "").lower().startswith("sw_")
    }
    actual_switch_ids = {
        node["figma_id"]
        for node in nodes
        if node.get("type") == "switch"
    }
    assert actual_switch_ids == expected_switch_ids

    assets = validate_assets(after, overrides)
    return {
        "screen_count": len(screens),
        "default_screen": "Home",
        "actually_changed_screen_ids": sorted(actually_changed_ids),
        "changed_screen_hashes": {
            screen_id: {
                "before": before_hashes[screen_id],
                "after": after_hashes[screen_id],
            }
            for screen_id in sorted(changed_ids)
        },
        "preserved_screen_hashes": {
            screen_id: after_hashes[screen_id]
            for screen_id in sorted(EXPECTED_SCREEN_IDS - changed_ids)
        },
        "assets": assets,
        "switch_count": len(actual_switch_ids),
    }


def main() -> None:
    args = parse_args()
    before = load_json(args.input_project)
    project = deepcopy(before)
    overrides = load_json(args.semantic_overrides)
    index, per_screen, all_manifest_nodes = load_new_manifests(
        args.manifest_index
    )
    diffs = [
        screen_diff(
            spec["id"],
            old_manifest_nodes(spec["id"]),
            per_screen[spec["id"]],
        )
        for spec in index["screens"]
    ]
    changed_ids = {
        diff["figma_id"]
        for diff in diffs
        if diff["changed"]
    }
    assert HOME_ID not in changed_ids, "Home changed; specialized review required"
    assert UNCHANGED_EXPECTED.isdisjoint(changed_ids)

    report: dict[str, Any] = {
        "schema_version": "figma-mcp-incremental-sync-report/v3",
        "source": {
            "manifest_index": str(args.manifest_index.resolve()),
            "snapshot_version": index["snapshot_version"],
            "tool": index["source"]["tool"],
            "read_only": index["source"]["read_only"],
        },
        "screen_diffs": diffs,
        "changed_screen_ids": sorted(changed_ids),
        "rebuilt_screens": [],
        "removed_gui_nodes": [],
        "semantic_pending": [],
        "skipped_nodes": [],
        "text_box_corrections": [],
        "button_text_expansions": [],
        "font_metric_width_expansions": [],
        "screen_background_corrections": [],
        "switch_style_sources": [],
        "button_shadow_normalizations": [],
        "switch_widget_normalizations": [],
        "figma_sibling_order_normalizations": [],
    }

    menu_diff = next(diff for diff in diffs if diff["figma_id"] == MENU_ID)
    assert not menu_diff["added"], "New HOME_MENU nodes require semantic review"
    assert not menu_diff["changed_nodes"], (
        "HOME_MENU common nodes changed; specialized style sync required"
    )
    if menu_diff["removed"]:
        menu = find_screen_by_figma_id(project, MENU_ID)
        present_removed = {
            node.get("figma_id")
            for node in walk([menu])
            if node.get("figma_id") in set(menu_diff["removed"])
        }
        report["removed_gui_nodes"] = prune_figma_ids(
            menu,
            set(menu_diff["removed"]),
        )
        removed_ids = {
            item["figma_id"] for item in report["removed_gui_nodes"]
        }
        assert removed_ids == present_removed

    report["rebuilt_screens"] = rebuild_changed_screens(
        project,
        index,
        per_screen,
        changed_ids,
        overrides,
        report,
    )
    report["button_shadow_normalizations"] = []
    for node in iter_project_nodes(project):
        if node.get("type") != "button":
            continue
        source = all_manifest_nodes.get(node.get("figma_id"))
        if source is None:
            continue
        before_style = deepcopy(node["style"][MAIN_STYLE])
        apply_figma_button_shadow(source, node)
        if node["style"][MAIN_STYLE] != before_style:
            report["button_shadow_normalizations"].append(
                {
                    "figma_id": node["figma_id"],
                    "name": node["name"],
                    "visible_figma_drop_shadow": (
                        visible_drop_shadow(source) is not None
                    ),
                }
            )
    report["switch_widget_normalizations"] = normalize_switch_widgets(
        project,
        all_manifest_nodes,
    )
    compat_index = {
        "missing_screens": [
            spec
            for spec in index["screens"]
            if spec["id"] in changed_ids - SPECIALIZED_SCREEN_IDS
        ]
    }
    report["figma_sibling_order_normalizations"] = (
        normalize_figma_sibling_order(
            project,
            all_manifest_nodes,
            compat_index,
        )
    )
    for screen in screen_list(project):
        screen["default_screen"] = screen.get("figma_id") == HOME_ID

    report["validation"] = validate_project(
        before,
        project,
        per_screen,
        changed_ids,
        overrides,
    )
    write_json(args.output_project, project)
    report["input_sha256"] = file_hash(args.input_project)
    report["output_sha256"] = file_hash(args.output_project)
    write_json(args.report, report)
    print(
        json.dumps(
            {
                "output": str(args.output_project),
                "report": str(args.report),
                "changed_screen_ids": sorted(changed_ids),
                "rebuilt_screens": len(report["rebuilt_screens"]),
                "removed_gui_nodes": len(report["removed_gui_nodes"]),
                "validation": report["validation"],
                "sha256": report["output_sha256"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
