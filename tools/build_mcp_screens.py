#!/usr/bin/env python3
"""Incrementally add missing Figma MCP screens to a GUI Guider 2.0 project.

The source of truth for new screens is the versioned, read-only Figma MCP
manifest under tools/manifests. Existing GUI Guider screens and project
settings are preserved byte-for-byte at the JSON-object level. Ambiguous
business widgets are imported as visual containers and reported for later
semantic confirmation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterator

from PIL import Image

from build_figma_screen import (
    FONT_FILES as EXISTING_FONT_FILES,
    MAIN_STYLE,
    load_json,
    object_node,
    screen_node,
    stable_id,
    walk,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INDEX = ROOT / "tools" / "manifests" / "v1" / "index.json"
DEFAULT_OVERRIDES = (
    ROOT / "tools" / "manifests" / "v1" / "semantic_overrides.json"
)
DEFAULT_INPUT = ROOT / "guiguider_2.0.guiguider"
DEFAULT_BASELINE = (
    ROOT
    / "tools"
    / "artifacts"
    / "baseline_20260725"
    / "guiguider_2.0.before_12_screens.guiguider"
)

IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
EXISTING_SCREEN_IDS = {"71:3", "130:2", "130:6"}
EXPECTED_EXISTING_NAMES = {"Home", "Back", "HOME_MENU"}


def load_utf8_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as stream:
        return json.load(stream)


def round_px(value: float | int) -> int:
    return int(math.floor(float(value) + 0.5))


def clamp_byte(value: float) -> int:
    return max(0, min(255, round_px(value * 255)))


def rgb_to_hex(color: dict[str, Any] | None, default: str = "#000000") -> str:
    if not color:
        return default
    channels = [clamp_byte(float(color[key])) for key in ("r", "g", "b")]
    return "#" + "".join(f"{channel:02x}" for channel in channels)


def visible_solid(paints: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next(
        (
            paint
            for paint in paints
            if paint.get("type") == "SOLID" and paint.get("visible", True)
        ),
        None,
    )


def node_opacity(node: dict[str, Any]) -> int:
    if not node.get("visible", True):
        return 0
    return clamp_byte(float(node.get("opacity", 1)))


def radius_px(node: dict[str, Any]) -> int:
    radius = node.get("cornerRadius", 0)
    if isinstance(radius, (int, float)):
        return max(0, round_px(radius))
    radii = node.get("cornerRadii") or []
    numeric = [value for value in radii if isinstance(value, (int, float))]
    return max((round_px(value) for value in numeric), default=0)


def visual_style(node: dict[str, Any]) -> dict[str, Any]:
    fill = visible_solid(node.get("fills", []))
    stroke = visible_solid(node.get("strokes", []))
    style: dict[str, Any] = {
        "part": "LV_PART_MAIN",
        "state": "LV_STATE_DEFAULT",
        "opa": node_opacity(node),
        "radius": radius_px(node),
        "clip_corner": 1,
        "outline_width": 0,
        "outline_opa": 0,
        "pad_left": 0,
        "pad_right": 0,
        "pad_top": 0,
        "pad_bottom": 0,
    }

    if fill is None:
        style.update({"bg_color": "#000000", "bg_opa": 0})
    else:
        color = fill.get("color") or {}
        alpha = float(fill.get("opacity", 1)) * float(color.get("a", 1))
        style.update(
            {
                "bg_color": rgb_to_hex(color),
                "bg_opa": clamp_byte(alpha),
            }
        )

    stroke_width = node.get("strokeWeight", 0)
    if stroke is None or not isinstance(stroke_width, (int, float)):
        style.update({"border_width": 0, "border_opa": 0})
    else:
        color = stroke.get("color") or {}
        alpha = float(stroke.get("opacity", 1)) * float(color.get("a", 1))
        style.update(
            {
                "border_color": rgb_to_hex(color),
                "border_opa": clamp_byte(alpha),
                "border_width": max(0, round_px(stroke_width)),
            }
        )
    return {MAIN_STYLE: style}


def visible_drop_shadow(node: dict[str, Any]) -> dict[str, Any] | None:
    return next(
        (
            effect
            for effect in node.get("effects", [])
            if effect.get("type") == "DROP_SHADOW"
            and effect.get("visible", True)
        ),
        None,
    )


def apply_figma_button_shadow(
    source_node: dict[str, Any],
    target_node: dict[str, Any],
) -> bool:
    """Prevent LVGL's button theme from inventing an absent Figma shadow."""
    style = target_node["style"][MAIN_STYLE]
    before = deepcopy(style)
    effect = visible_drop_shadow(source_node)
    if effect is None:
        style.update(
            {
                "shadow_color": "#000000",
                "shadow_opa": 0,
                "shadow_offset_x": 0,
                "shadow_offset_y": 0,
                "shadow_width": 0,
                "shadow_spread": 0,
            }
        )
    else:
        color = effect.get("color") or {}
        offset = effect.get("offset") or {}
        style.update(
            {
                "shadow_color": rgb_to_hex(color),
                "shadow_opa": clamp_byte(float(color.get("a", 1))),
                "shadow_offset_x": round_px(offset.get("x", 0)),
                "shadow_offset_y": round_px(offset.get("y", 0)),
                "shadow_width": max(0, round_px(effect.get("radius", 0))),
                "shadow_spread": round_px(effect.get("spread", 0)),
            }
        )
    return style != before


def figma_switch_style(
    track_node: dict[str, Any],
    knob_node: dict[str, Any],
) -> dict[str, Any]:
    track_style = visual_style(track_node)[MAIN_STYLE]
    track_style["anim_duration"] = 0

    indicator_default = {
        "part": "LV_PART_INDICATOR",
        "state": "LV_STATE_DEFAULT",
        "opa": node_opacity(track_node),
        "radius": radius_px(track_node),
        "bg_color": track_style["bg_color"],
        "bg_opa": 0,
        "border_width": 0,
        "border_opa": 0,
        "outline_width": 0,
        "outline_opa": 0,
    }
    indicator_checked = deepcopy(indicator_default)
    indicator_checked["state"] = "LV_STATE_CHECKED"

    knob_style = visual_style(knob_node)[MAIN_STYLE]
    knob_style.update(
        {
            "part": "LV_PART_KNOB",
            "state": "LV_STATE_DEFAULT",
            "pad_left": -max(0, round_px(knob_node["x"])),
            "pad_right": -max(
                0,
                round_px(
                    float(track_node["height"])
                    - float(knob_node["x"])
                    - float(knob_node["width"])
                ),
            ),
            "pad_top": -max(0, round_px(knob_node["y"])),
            "pad_bottom": -max(
                0,
                round_px(
                    float(track_node["height"])
                    - float(knob_node["y"])
                    - float(knob_node["height"])
                ),
            ),
            "shadow_color": "#000000",
            "shadow_opa": 0,
            "shadow_offset_x": 0,
            "shadow_offset_y": 0,
            "shadow_width": 0,
            "shadow_spread": 0,
        }
    )
    return {
        MAIN_STYLE: track_style,
        "LV_PART_INDICATOR|LV_STATE_DEFAULT": indicator_default,
        "LV_PART_INDICATOR|LV_STATE_CHECKED": indicator_checked,
        "LV_PART_KNOB|LV_STATE_DEFAULT": knob_style,
    }


def line_height_px(text: dict[str, Any]) -> int:
    line_height = text.get("lineHeight")
    if isinstance(line_height, dict) and line_height.get("unit") == "PIXELS":
        return max(1, math.ceil(float(line_height["value"])))
    font_size = float(text.get("fontSize") or 14)
    return max(1, math.ceil(font_size * 1.2))


def text_style(
    node: dict[str, Any],
    overrides: dict[str, Any],
) -> dict[str, Any]:
    text = node["text"]
    fill = visible_solid(node.get("fills", []))
    color = (fill or {}).get("color") or {"r": 1, "g": 1, "b": 1}
    font_name = text.get("fontName")
    if not isinstance(font_name, dict):
        raise AssertionError(f"Mixed or missing font on Figma text node {node['id']}")
    font_key = f"{font_name.get('family')}|{font_name.get('style')}"
    family = overrides["font_mappings"].get(font_key)
    if family is None:
        raise AssertionError(f"Unmapped Figma font {font_key} on {node['id']}")
    align = {
        "LEFT": "LV_TEXT_ALIGN_LEFT",
        "CENTER": "LV_TEXT_ALIGN_CENTER",
        "RIGHT": "LV_TEXT_ALIGN_RIGHT",
        "JUSTIFIED": "LV_TEXT_ALIGN_LEFT",
    }.get(text.get("textAlignHorizontal"), "LV_TEXT_ALIGN_LEFT")
    fill_alpha = float((fill or {}).get("opacity", 1)) * float(color.get("a", 1))
    return {
        MAIN_STYLE: {
            "part": "LV_PART_MAIN",
            "state": "LV_STATE_DEFAULT",
            "opa": node_opacity(node),
            "border_width": 0,
            "border_opa": 0,
            "outline_width": 0,
            "outline_opa": 0,
            "text_color": rgb_to_hex(color, "#ffffff"),
            "text_opa": clamp_byte(fill_alpha),
            "text_size": max(1, round_px(text.get("fontSize") or 14)),
            "text_family": family,
            "text_align": align,
            "pad_top": 0,
        }
    }


def iter_project_nodes(project: dict[str, Any]) -> Iterator[dict[str, Any]]:
    yield from walk(project["UI"]["screen_list"])


def normalized_hash(node: dict[str, Any]) -> str:
    payload = json.dumps(
        node,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_manifest_nodes(
    index_path: Path,
    screen_spec: dict[str, Any],
) -> list[dict[str, Any]]:
    screen_dir = index_path.parent / screen_spec["id"].replace(":", "_")
    fragments = sorted(screen_dir.glob("chunk_*.json"))
    assert len(fragments) == screen_spec["chunks"], (
        f"Unexpected fragment count for {screen_spec['id']}: "
        f"{len(fragments)} != {screen_spec['chunks']}"
    )
    nodes: list[dict[str, Any]] = []
    expected_start = 0
    expected_total: int | None = None
    for fragment_path in fragments:
        fragment = load_utf8_json(fragment_path)
        assert fragment["source"]["root_id"] == screen_spec["id"]
        assert fragment["source"]["tool"] == "figma.use_figma"
        chunk = fragment["chunk"]
        assert chunk["start"] == expected_start
        if expected_total is None:
            expected_total = chunk["total"]
        assert chunk["total"] == expected_total
        nodes.extend(fragment["nodes"])
        expected_start += len(fragment["nodes"])
    assert len(nodes) == screen_spec["count"] == expected_total
    ids = [node["id"] for node in nodes]
    assert len(ids) == len(set(ids)), f"Duplicate Figma IDs in {screen_spec['id']}"
    return nodes


def load_all_manifest_nodes(
    index_path: Path,
    index: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    nodes: dict[str, dict[str, Any]] = {}
    for screen_spec in index["missing_screens"]:
        for node in load_manifest_nodes(index_path, screen_spec):
            assert node["id"] not in nodes, f"Duplicate manifest node {node['id']}"
            nodes[node["id"]] = node
    return nodes


def should_skip(node: dict[str, Any], overrides: dict[str, Any]) -> str | None:
    for rule in overrides.get("skip_rules", []):
        if node.get("type") != rule.get("type"):
            continue
        width_ok = "max_width" not in rule or float(node["width"]) <= float(
            rule["max_width"]
        )
        height_ok = "max_height" not in rule or float(node["height"]) <= float(
            rule["max_height"]
        )
        if width_ok and height_ok:
            return rule["reason"]
    return None


def match_widget_rule(
    node: dict[str, Any],
    overrides: dict[str, Any],
) -> dict[str, Any] | None:
    for rule in overrides.get("widget_rules", []):
        if re.search(rule["name_regex"], node["name"], re.IGNORECASE):
            return rule
    return None


def asset_filename(node: dict[str, Any], overrides: dict[str, Any]) -> str:
    for rule in overrides.get("asset_rules", []):
        if re.fullmatch(rule["name_regex"], node["name"], re.IGNORECASE):
            return rule["output"]
    raise AssertionError(
        f"No reviewed local asset mapping for image {node['id']} {node['name']}"
    )


def sanitize(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    if not value:
        return "node"
    if value[0].isdigit():
        return f"n_{value}"
    return value.lower()


class NameAllocator:
    def __init__(self, reserved: set[str]) -> None:
        self.used = set(reserved)

    def allocate(self, candidate: str, figma_id: str) -> str:
        candidate = sanitize(candidate)
        if candidate not in self.used:
            self.used.add(candidate)
            return candidate
        suffix = sanitize(figma_id.replace(":", "_"))
        unique = f"{candidate}_{suffix}"
        counter = 2
        while unique in self.used:
            unique = f"{candidate}_{suffix}_{counter}"
            counter += 1
        self.used.add(unique)
        return unique


def source_suffix(name: str) -> str:
    return re.sub(
        r"^(screen_|btn_|button_|label_|unit_|cont_|container_|panel_|decor_|"
        r"img_|image_|indicator_|led_|ddlist_|sw_)",
        "",
        name,
        flags=re.IGNORECASE,
    )


def target_name(
    node: dict[str, Any],
    target_type: str,
    screen_slug: str,
    by_id: dict[str, dict[str, Any]],
    allocator: NameAllocator,
) -> str:
    source_name = node["name"]
    if target_type == "screen":
        return allocator.allocate(f"screen_{screen_slug}", node["id"])

    if target_type == "label":
        parent = by_id.get(node.get("parent_id"))
        parent_name = parent["name"] if parent else source_name
        if source_name.lower().startswith(("label_", "unit_")):
            suffix = source_suffix(source_name)
        elif parent_name.lower().startswith(("label_", "unit_")):
            suffix = source_suffix(parent_name)
        elif parent_name.lower().startswith(("btn_", "button_")):
            suffix = f"{source_suffix(parent_name)}_text"
        elif parent_name.lower().startswith(("cont_", "ddlist_", "sw_")):
            suffix = f"{source_suffix(parent_name)}_text"
        else:
            suffix = f"text_{node['id'].replace(':', '_')}"
        return allocator.allocate(f"label_{screen_slug}_{suffix}", node["id"])

    suffix = source_suffix(source_name)
    if target_type == "button":
        candidate = f"btn_{screen_slug}_{suffix}"
    elif target_type == "switch":
        candidate = f"sw_{screen_slug}_{suffix}"
    elif target_type == "image":
        candidate = f"img_{screen_slug}_{suffix}"
    elif target_type == "led":
        candidate = f"led_{screen_slug}_{suffix}"
    elif source_name.lower() == "cont":
        candidate = f"cont_{screen_slug}_root"
    elif source_name.lower().startswith("label_"):
        candidate = f"panel_{screen_slug}_{suffix}"
    elif source_name.lower().startswith("decor_"):
        candidate = f"decor_{screen_slug}_{suffix}"
    elif source_name.lower().startswith("ddlist_"):
        candidate = f"cont_{screen_slug}_{suffix}_dropdown"
    elif source_name.lower().startswith("img_"):
        candidate = f"decor_{screen_slug}_{suffix}"
    else:
        candidate = f"cont_{screen_slug}_{suffix}"
    return allocator.allocate(candidate, node["id"])


def build_screen(
    screen_spec: dict[str, Any],
    manifest_nodes: list[dict[str, Any]],
    overrides: dict[str, Any],
    allocator: NameAllocator,
    report: dict[str, Any],
) -> dict[str, Any]:
    by_id = {node["id"]: node for node in manifest_nodes}
    root = by_id[screen_spec["id"]]
    assert root["type"] == "FRAME"
    assert (round_px(root["width"]), round_px(root["height"])) == (960, 240)

    children_by_parent: dict[str, list[dict[str, Any]]] = {}
    for node in manifest_nodes:
        parent_id = node.get("parent_id")
        if parent_id:
            children_by_parent.setdefault(parent_id, []).append(node)
    for children in children_by_parent.values():
        # GUI Guider paints the first JSON sibling last (front-most), while
        # Figma's child order increases toward the front. Store siblings in
        # descending Figma order so overlapping labels, switches, and
        # decorative layers keep the same visual stacking.
        children.sort(key=lambda node: node["order"], reverse=True)

    screen_name = overrides["screen_names"][screen_spec["id"]]
    screen_slug = source_suffix(screen_name)

    def convert(node: dict[str, Any]) -> dict[str, Any] | None:
        reason = should_skip(node, overrides)
        if reason is not None:
            assert not children_by_parent.get(node["id"]), (
                f"Cannot skip parent node {node['id']} with children"
            )
            report["skipped_nodes"].append(
                {"figma_id": node["id"], "name": node["name"], "reason": reason}
            )
            return None

        if node["id"] == root["id"]:
            target_type = "screen"
        elif node["type"] == "TEXT":
            target_type = "label"
        elif node.get("image"):
            target_type = "image"
        else:
            rule = match_widget_rule(node, overrides)
            target_type = rule["target_type"] if rule else "container"
            if rule and rule.get("pending_semantic"):
                report["semantic_pending"].append(
                    {
                        "figma_id": node["id"],
                        "source_name": node["name"],
                        "imported_as": target_type,
                        "pending_semantic": rule["pending_semantic"],
                    }
                )

        name = (
            screen_name
            if target_type == "screen"
            else target_name(node, target_type, screen_slug, by_id, allocator)
        )
        source_children = children_by_parent.get(node["id"], [])
        if target_type == "switch":
            assert len(source_children) == 1, (
                f"Switch {node['id']} must have exactly one Figma knob child"
            )
            knob_node = source_children[0]
            assert knob_node["name"].lower().endswith("_knob")
            assert not children_by_parent.get(knob_node["id"])
            converted_children = []
        else:
            converted_children = [
                converted
                for child in source_children
                if (converted := convert(child)) is not None
            ]

        if target_type == "screen":
            screen_style = visual_style(node)
            rendering = overrides["screen_rendering"]
            main_style = screen_style[MAIN_STYLE]
            main_style["bg_color"] = rendering["background_color"]
            main_style["bg_opa"] = rendering["background_opacity"]
            report["screen_background_corrections"].append(
                {
                    "figma_id": node["id"],
                    "target_name": name,
                    "background_color": main_style["bg_color"],
                    "background_opacity": main_style["bg_opa"],
                    "reason": rendering["reason"],
                }
            )
            return screen_node(
                node["id"],
                name,
                screen_style,
                converted_children,
                default_screen=False,
            )

        x = round_px(node["x"])
        y = round_px(node["y"])
        width = max(1, round_px(node["width"]))
        height = max(1, round_px(node["height"]))

        if target_type == "label":
            parent = by_id.get(node.get("parent_id"))
            if (
                parent
                and parent["name"].lower().startswith(("btn_", "button_"))
                and node["text"].get("textAlignHorizontal") == "CENTER"
            ):
                source_box = {"x": x, "width": width}
                x = 0
                width = max(1, round_px(parent["width"]))
                report["button_text_expansions"].append(
                    {
                        "figma_id": node["id"],
                        "source_name": node["name"],
                        "source_box": source_box,
                        "target_box": {"x": x, "width": width},
                    }
                )
            elif parent:
                parent_width = max(1, round_px(parent["width"]))
                left_extra = min(6, max(0, x))
                right_space = max(0, parent_width - (x + width))
                right_extra = min(6, right_space)
                if left_extra or right_extra:
                    source_box = {"x": x, "width": width}
                    x -= left_extra
                    width += left_extra + right_extra
                    report["font_metric_width_expansions"].append(
                        {
                            "figma_id": node["id"],
                            "source_name": node["name"],
                            "source_box": source_box,
                            "target_box": {"x": x, "width": width},
                        }
                    )
            min_height = line_height_px(node["text"])
            if height < min_height:
                report["text_box_corrections"].append(
                    {
                        "figma_id": node["id"],
                        "source_name": node["name"],
                        "source_height": height,
                        "required_height": min_height,
                    }
                )
                height = min_height
            result = object_node(
                node["id"],
                name,
                "label",
                x,
                y,
                width,
                height,
                text_style(node, overrides),
            )
            result["static_text"] = False
            result["text"] = node["text"]["characters"]
            return result

        if target_type == "image":
            assert not converted_children, f"Image node {node['id']} has children"
            filename = asset_filename(node, overrides)
            style = {
                MAIN_STYLE: {
                    "part": "LV_PART_MAIN",
                    "state": "LV_STATE_DEFAULT",
                    "opa": node_opacity(node),
                    "radius": 0,
                    "border_width": 0,
                    "border_opa": 0,
                    "outline_width": 0,
                    "outline_opa": 0,
                }
            }
            result = object_node(
                node["id"],
                name,
                "image",
                x,
                y,
                width,
                height,
                style,
            )
            result["src"] = f"resources\\image\\{filename}"
            return result

        if target_type == "switch":
            style = figma_switch_style(node, knob_node)
            report["switch_style_sources"].append(
                {
                    "figma_id": node["id"],
                    "source_name": node["name"],
                    "knob_figma_id": knob_node["id"],
                    "knob_source_name": knob_node["name"],
                }
            )
        else:
            style = visual_style(node)
        result = object_node(
            node["id"],
            name,
            target_type,
            x,
            y,
            width,
            height,
            style,
            children=converted_children,
            scrollbar_mode=(
                "LV_SCROLLBAR_MODE_OFF" if target_type == "container" else None
            ),
        )
        if target_type == "button":
            apply_figma_button_shadow(node, result)
        return result

    built = convert(root)
    assert built is not None
    return built


def screen_identity(node: dict[str, Any]) -> tuple[str | None, str | None]:
    return node.get("figma_id"), node.get("name")


def missing_screen_specs(
    project: dict[str, Any],
    index: dict[str, Any],
    overrides: dict[str, Any],
) -> list[dict[str, Any]]:
    screens = [
        node
        for node in project["UI"]["screen_list"]
        if node.get("type") == "screen"
    ]
    existing_ids = {node.get("figma_id") for node in screens}
    existing_names = {node.get("name") for node in screens}
    result = []
    for spec in index["missing_screens"]:
        target_name_value = overrides["screen_names"][spec["id"]]
        if spec["id"] in existing_ids:
            continue
        if target_name_value in existing_names:
            raise AssertionError(
                f"Screen name collision: {target_name_value} exists with another Figma ID"
            )
        result.append(spec)
    return result


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, ensure_ascii=True, indent=2)
        stream.write("\n")


def find_screen_by_figma_id(
    project: dict[str, Any],
    figma_id: str,
) -> dict[str, Any]:
    matches = [
        node
        for node in project["UI"]["screen_list"]
        if node.get("type") == "screen" and node.get("figma_id") == figma_id
    ]
    assert len(matches) == 1, f"Expected one screen for Figma ID {figma_id}"
    return matches[0]


def normalize_button_theme_inheritance(
    project: dict[str, Any],
    manifest_nodes: dict[str, dict[str, Any]],
    overrides: dict[str, Any],
) -> list[dict[str, Any]]:
    reviewed = overrides["existing_button_effects"]
    reviewed_drop = set(reviewed["visible_drop_shadow_figma_ids"])
    reviewed_none = set(reviewed["no_visible_drop_shadow_figma_ids"])
    assert not (reviewed_drop & reviewed_none), "Conflicting reviewed button effects"

    changes: list[dict[str, Any]] = []
    classified_existing: set[str] = set()
    for node in iter_project_nodes(project):
        if node.get("type") != "button":
            continue
        figma_id = node.get("figma_id")
        assert isinstance(figma_id, str), f"Button without Figma ID: {node.get('name')}"
        if figma_id in reviewed_drop:
            classified_existing.add(figma_id)
            continue
        if figma_id in reviewed_none:
            source_node = {"effects": []}
            classified_existing.add(figma_id)
        else:
            source_node = manifest_nodes.get(figma_id)
            assert source_node is not None, (
                f"Button effect is not classified by Figma source: "
                f"{node.get('name')} ({figma_id})"
            )
        if apply_figma_button_shadow(source_node, node):
            changes.append(
                {
                    "figma_id": figma_id,
                    "name": node["name"],
                    "visible_figma_drop_shadow": (
                        visible_drop_shadow(source_node) is not None
                    ),
                }
            )

    present_reviewed = {
        node.get("figma_id")
        for node in iter_project_nodes(project)
        if node.get("type") == "button"
        and node.get("figma_id") in reviewed_drop | reviewed_none
    }
    assert classified_existing == present_reviewed
    return changes


def normalize_switch_widgets(
    project: dict[str, Any],
    manifest_nodes: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    switch_sources = {
        figma_id: source
        for figma_id, source in manifest_nodes.items()
        if source.get("name", "").lower().startswith("sw_")
    }
    child_sources: dict[str, list[dict[str, Any]]] = {}
    for source in manifest_nodes.values():
        child_sources.setdefault(source.get("parent_id", ""), []).append(source)

    project_by_figma_id = {
        node.get("figma_id"): node
        for node in iter_project_nodes(project)
        if isinstance(node.get("figma_id"), str)
    }
    changes: list[dict[str, Any]] = []
    for figma_id, source in switch_sources.items():
        target = project_by_figma_id.get(figma_id)
        assert target is not None, f"Missing switch target for Figma node {figma_id}"
        knobs = child_sources.get(figma_id, [])
        assert len(knobs) == 1, f"Switch {figma_id} must have one knob"
        knob = knobs[0]
        assert knob["name"].lower().endswith("_knob")

        before = deepcopy(target)
        old_name = target["name"]
        if old_name.startswith("cont_") and old_name.endswith("_switch"):
            target["name"] = f"sw_{old_name[5:-7]}"
        else:
            assert old_name.startswith("sw_"), (
                f"Unexpected switch target name: {old_name}"
            )
        target["type"] = "switch"
        target["style"] = figma_switch_style(source, knob)
        target["children"] = []
        target.pop("scrollbar_mode", None)
        if target != before:
            changes.append(
                {
                    "figma_id": figma_id,
                    "old_name": old_name,
                    "name": target["name"],
                    "knob_figma_id": knob["id"],
                }
            )

    return changes


def normalize_figma_sibling_order(
    project: dict[str, Any],
    manifest_nodes: dict[str, dict[str, Any]],
    index: dict[str, Any],
) -> list[dict[str, Any]]:
    new_screen_ids = {spec["id"] for spec in index["missing_screens"]}
    changes: list[dict[str, Any]] = []

    def reorder(node: dict[str, Any], screen_id: str) -> None:
        children = node.get("children")
        if not isinstance(children, list) or len(children) < 2:
            if isinstance(children, list):
                for child in children:
                    reorder(child, screen_id)
            return

        before = [child.get("figma_id") for child in children]
        assert all(
            isinstance(child.get("figma_id"), str)
            and child["figma_id"] in manifest_nodes
            for child in children
        ), f"Unmapped child in MCP screen {screen_id}: {node.get('name')}"
        children.sort(
            key=lambda child: manifest_nodes[child["figma_id"]]["order"],
            reverse=True,
        )
        after = [child["figma_id"] for child in children]
        if after != before:
            changes.append(
                {
                    "screen_figma_id": screen_id,
                    "parent_figma_id": node.get("figma_id"),
                    "parent_name": node.get("name"),
                    "before": before,
                    "after": after,
                }
            )
        for child in children:
            reorder(child, screen_id)

    for screen in project["UI"]["screen_list"]:
        screen_id = screen.get("figma_id")
        if screen.get("type") == "screen" and screen_id in new_screen_ids:
            reorder(screen, screen_id)
    return changes


def validate_project(
    project: dict[str, Any],
    baseline: dict[str, Any],
    existing_screen_snapshot: dict[str, Any],
    index: dict[str, Any],
    overrides: dict[str, Any],
    manifest_nodes: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    settings = project["projectSettings"]
    assert settings == baseline["projectSettings"], "Project settings changed"
    assert settings["lvglVersion"] == "9.4.0"
    assert (settings["width"], settings["height"]) == (960, 240)
    assert settings["targetConfig"]["colorDepth"] == 16
    assert settings["imageConfig"]["color_format"] == "RGB565A8"

    nodes = list(iter_project_nodes(project))
    names = [node.get("name", "") for node in nodes]
    ids = [node.get("id", "") for node in nodes]
    figma_ids = [
        node["figma_id"] for node in nodes if isinstance(node.get("figma_id"), str)
    ]
    assert all(IDENTIFIER.fullmatch(name) for name in names), (
        f"Invalid C names: {[name for name in names if not IDENTIFIER.fullmatch(name)]}"
    )
    assert len(names) == len(set(names)), "Duplicate GUI Guider names"
    assert len(ids) == len(set(ids)), "Duplicate GUI Guider IDs"
    assert len(figma_ids) == len(set(figma_ids)), "Duplicate Figma IDs"

    screens = [node for node in nodes if node.get("type") == "screen"]
    expected_ids = EXISTING_SCREEN_IDS | {
        spec["id"] for spec in index["missing_screens"]
    }
    assert len(screens) == 15
    assert {node.get("figma_id") for node in screens} == expected_ids
    assert sum(bool(node.get("default_screen")) for node in screens) == 1
    assert next(node for node in screens if node["name"] == "Home")[
        "default_screen"
    ]
    expected_background = overrides["screen_rendering"]
    for screen in screens:
        if screen.get("figma_id") in EXISTING_SCREEN_IDS:
            continue
        style = screen["style"][MAIN_STYLE]
        assert style["bg_color"] == expected_background["background_color"]
        assert style["bg_opa"] == expected_background["background_opacity"]

    expected_baseline = deepcopy(existing_screen_snapshot)
    normalize_button_theme_inheritance(
        expected_baseline,
        manifest_nodes,
        overrides,
    )
    for figma_id in EXISTING_SCREEN_IDS:
        before = find_screen_by_figma_id(expected_baseline, figma_id)
        after = find_screen_by_figma_id(project, figma_id)
        assert normalized_hash(before) == normalized_hash(after), (
            f"Existing screen changed unexpectedly: {figma_id}"
        )

    font_files = dict(EXISTING_FONT_FILES)
    font_files.update(overrides["font_files"])
    existing_node_figma_ids = {
        child.get("figma_id")
        for existing_id in EXISTING_SCREEN_IDS
        for child in walk([find_screen_by_figma_id(project, existing_id)])
        if child.get("figma_id")
    }
    used_fonts: set[str] = set()
    image_count = 0
    label_count = 0
    for node in nodes:
        style = node.get("style", {}).get(MAIN_STYLE, {})
        family = style.get("text_family")
        if family:
            used_fonts.add(family)

        name = node.get("name", "")
        node_type = node.get("type")
        if node_type == "button":
            figma_id = node.get("figma_id")
            source = manifest_nodes.get(figma_id)
            no_drop_shadow = (
                figma_id
                in set(
                    overrides["existing_button_effects"][
                        "no_visible_drop_shadow_figma_ids"
                    ]
                )
                or (source is not None and visible_drop_shadow(source) is None)
            )
            if no_drop_shadow:
                for key in (
                    "shadow_opa",
                    "shadow_offset_x",
                    "shadow_offset_y",
                    "shadow_width",
                    "shadow_spread",
                ):
                    assert style.get(key) == 0, (
                        f"Inherited button shadow not disabled: {name}.{key}"
                    )
        if name.startswith(("screen_",)) and node_type != "screen":
            raise AssertionError(f"{name} must be a screen")
        if name.startswith(("btn_", "button_")) and node_type != "button":
            raise AssertionError(f"{name} must be a button")
        if name.startswith("sw_") and node_type != "switch":
            raise AssertionError(f"{name} must be a switch")
        if name.startswith("label_") and node_type != "label":
            raise AssertionError(f"{name} must be a label")
        if name.startswith("img_") and node_type != "image":
            raise AssertionError(f"{name} must be an image")
        if name.startswith(("cont_", "panel_", "decor_")) and node_type != "container":
            raise AssertionError(f"{name} must be a container")
        if name.startswith(("led_", "indicator_")) and node_type != "led":
            raise AssertionError(f"{name} must be an LED")

        if node_type == "label":
            label_count += 1
            assert node["width_unit"] == node["height_unit"] == "px"
            assert node["width"] > 0 and node["height"] > 0, (
                f"Invalid label box: {name}"
            )

        if node_type == "image":
            image_count += 1
            source = node.get("src", "").replace("\\", "/")
            assert source, f"Missing image source for {name}"
            path = ROOT / source
            assert path.is_file(), f"Missing image file {source}"
            if node.get("figma_id") not in existing_node_figma_ids:
                with Image.open(path) as image:
                    assert image.size == (node["width"], node["height"]), (
                        f"Image size mismatch for {name}: "
                        f"{image.size} != {(node['width'], node['height'])}"
                    )
                    assert "A" in image.getbands(), f"Image alpha missing: {source}"
                    assert image.getchannel("A").getextrema()[0] < 255, (
                        f"Image has no transparent pixels: {source}"
                    )

    switch_sources = {
        figma_id: source
        for figma_id, source in manifest_nodes.items()
        if source.get("name", "").lower().startswith("sw_")
    }
    project_switches = {
        node.get("figma_id"): node
        for node in nodes
        if node.get("type") == "switch"
    }
    assert set(project_switches) == set(switch_sources)
    for figma_id, switch in project_switches.items():
        assert switch["name"].startswith("sw_")
        assert switch.get("children") == []
        assert "scrollbar_mode" not in switch
        assert set(switch["style"]) == {
            MAIN_STYLE,
            "LV_PART_INDICATOR|LV_STATE_DEFAULT",
            "LV_PART_INDICATOR|LV_STATE_CHECKED",
            "LV_PART_KNOB|LV_STATE_DEFAULT",
        }
        source_knob_ids = {
            source["id"]
            for source in manifest_nodes.values()
            if source.get("parent_id") == figma_id
        }
        assert len(source_knob_ids) == 1
        assert not (source_knob_ids & set(figma_ids)), (
            f"Switch knob must be folded into KNOB style: {figma_id}"
        )

    new_screen_ids = {spec["id"] for spec in index["missing_screens"]}
    for screen in screens:
        if screen.get("figma_id") not in new_screen_ids:
            continue
        for parent in walk([screen]):
            children = parent.get("children")
            if not isinstance(children, list) or len(children) < 2:
                continue
            orders = [
                manifest_nodes[child["figma_id"]]["order"]
                for child in children
            ]
            assert orders == sorted(orders, reverse=True), (
                f"GUI Guider sibling order does not match Figma: "
                f"{parent.get('name')}"
            )

    direct_font_files = {
        family
        for family in used_fonts
        if (ROOT / "resources" / "font" / family).is_file()
    }
    unknown_fonts = used_fonts - set(font_files) - direct_font_files
    assert not unknown_fonts, f"Unmapped GUI Guider fonts: {sorted(unknown_fonts)}"
    for family in used_fonts:
        path = ROOT / "resources" / "font" / font_files.get(family, family)
        assert path.is_file(), f"Missing font file: {path.name}"

    return {
        "screens": len(screens),
        "nodes": len(nodes),
        "labels": label_count,
        "images": image_count,
        "switches": len(project_switches),
        "fonts": sorted(used_fonts),
        "project_settings_preserved": True,
        "existing_screen_hashes_preserved_except_reviewed_button_shadow_guard": True,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-project", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-project", type=Path, required=True)
    parser.add_argument("--baseline-project", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--manifest-index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--semantic-overrides", type=Path, default=DEFAULT_OVERRIDES)
    parser.add_argument("--report", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project = load_json(args.input_project)
    existing_screen_snapshot = deepcopy(project)
    baseline = load_json(args.baseline_project)
    index = load_utf8_json(args.manifest_index)
    overrides = load_utf8_json(args.semantic_overrides)
    manifest_nodes = load_all_manifest_nodes(args.manifest_index, index)
    report: dict[str, Any] = {
        "schema_version": "figma-mcp-conversion-report/v1",
        "input_project": str(args.input_project.resolve()),
        "output_project": str(args.output_project.resolve()),
        "manifest_index": str(args.manifest_index.resolve()),
        "added_screens": [],
        "semantic_pending": [],
        "skipped_nodes": [],
        "text_box_corrections": [],
        "button_text_expansions": [],
        "font_metric_width_expansions": [],
        "screen_background_corrections": [],
        "button_shadow_normalizations": [],
        "switch_widget_normalizations": [],
        "switch_style_sources": [],
        "figma_sibling_order_normalizations": [],
    }

    reserved_names = {node.get("name", "") for node in iter_project_nodes(project)}
    allocator = NameAllocator(reserved_names)
    missing = missing_screen_specs(project, index, overrides)
    for screen_spec in missing:
        screen_manifest_nodes = load_manifest_nodes(args.manifest_index, screen_spec)
        screen = build_screen(
            screen_spec,
            screen_manifest_nodes,
            overrides,
            allocator,
            report,
        )
        project["UI"]["screen_list"].append(screen)
        report["added_screens"].append(
            {
                "figma_id": screen_spec["id"],
                "source_name": screen_spec["name"],
                "target_name": screen["name"],
            }
        )

    report["button_shadow_normalizations"] = normalize_button_theme_inheritance(
        project,
        manifest_nodes,
        overrides,
    )
    report["switch_widget_normalizations"] = normalize_switch_widgets(
        project,
        manifest_nodes,
    )
    report["figma_sibling_order_normalizations"] = normalize_figma_sibling_order(
        project,
        manifest_nodes,
        index,
    )
    validation = validate_project(
        project,
        baseline,
        existing_screen_snapshot,
        index,
        overrides,
        manifest_nodes,
    )
    report["validation"] = validation
    report["difference"] = {
        "requested_missing_screens": len(index["missing_screens"]),
        "actually_added": len(report["added_screens"]),
        "already_present": len(index["missing_screens"]) - len(missing),
    }

    write_json(args.output_project, project)
    report_path = args.report or args.output_project.with_suffix(
        args.output_project.suffix + ".report.json"
    )
    write_json(report_path, report)
    print(
        f"Wrote {args.output_project} "
        f"(added {len(report['added_screens'])} missing screens)"
    )
    print(
        "Validated: 15 unique screens; Home default; LVGL 9.4; 960x240; "
        "RGB565A8; names/IDs/parents; fonts/images; reviewed button shadows"
    )


if __name__ == "__main__":
    main()
