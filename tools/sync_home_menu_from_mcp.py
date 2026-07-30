#!/usr/bin/env python3
"""Synchronize the existing Home and HOME_MENU screens from Figma MCP manifests.

This updater deliberately mutates only the two existing screen subtrees. It
keeps GUI Guider widget types, stable IDs, events, image sources, baseline text
compensation, and the reviewed scroll-decoration reparenting intact.
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


ROOT = Path(__file__).resolve().parents[1]
MAIN_STYLE = "LV_PART_MAIN|LV_STATE_DEFAULT"
DEFAULT_INPUT = ROOT / "guiguider_2.0.guiguider"
DEFAULT_MANIFEST = (
    ROOT / "tools" / "manifests" / "v2_home_menu_20260725" / "index.json"
)
DEFAULT_OUTPUT = (
    ROOT
    / "tools"
    / "artifacts"
    / "home_menu_sync_20260725"
    / "guiguider_2.0.home_menu_candidate.guiguider"
)
DEFAULT_REPORT = (
    ROOT
    / "tools"
    / "artifacts"
    / "home_menu_sync_20260725"
    / "home_menu_sync_report.json"
)

TARGET_SCREEN_IDS = {"71:3", "130:6"}
EXPECTED_SCREEN_IDS = {
    "71:3",
    "130:2",
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
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# The live MCP manifest shows one real layout change. Other apparent Home
# coordinate differences are the existing 1 px LVGL border compensation.
GEOMETRY_UPDATES = {
    "72:3": {"width": 542},
}

FONT_MAP = {
    ("IBM Plex Sans", "Regular"): ("IBMPlexSans-Regular", None),
    ("IBM Plex Sans", "Light"): ("IBMPlexSans-Light", None),
    # No IBM Plex Sans Medium TTF is present in the project. The reviewed
    # existing project already used the same-family Regular face for this one
    # 23 px menu title, so retain that real local font instead of inventing one.
    ("IBM Plex Sans", "Medium"): (
        "IBMPlexSans-Regular",
        "IBM Plex Sans Medium is not installed; retained same-family Regular",
    ),
    ("IBM Plex Mono", "Regular"): ("IBMPlexMono-Regular", None),
    ("IBM Plex Mono", "Medium"): ("IBMPlexMono-Medium", None),
    ("Alibaba PuHuiTi 2.0", "55 Regular"): ("AlibabaPuHuiTi1", None),
}
FONT_FILES = {
    "AlibabaPuHuiTi1": "AlibabaPuHuiTi1.ttf",
    "IBMPlexMono-Medium": "IBMPlexMono-Medium.ttf",
    "IBMPlexMono-Regular": "IBMPlexMono-Regular.ttf",
    "IBMPlexSans-Light": "IBMPlexSans-Light.ttf",
    "IBMPlexSans-Regular": "IBMPlexSans-Regular.ttf",
    "Inter-Medium": "Inter-Medium.ttf",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-project", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--manifest-index", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-project", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as stream:
        return json.load(stream)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def round_px(value: float | int) -> int:
    return int(math.floor(float(value) + 0.5))


def clamp_byte(value: float) -> int:
    return max(0, min(255, round_px(float(value) * 255)))


def rgb_to_hex(color: dict[str, Any] | None) -> str:
    color = color or {}
    channels = [clamp_byte(color.get(key, 0)) for key in ("r", "g", "b")]
    return "#" + "".join(f"{channel:02x}" for channel in channels)


def canonical_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


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


def project_screens(project: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        node
        for node in project["UI"]["screen_list"]
        if node.get("type") == "screen"
    ]


def find_screen(project: dict[str, Any], figma_id: str) -> dict[str, Any]:
    matches = [
        screen
        for screen in project_screens(project)
        if screen.get("figma_id") == figma_id
    ]
    assert len(matches) == 1, f"Expected one screen for Figma ID {figma_id}"
    return matches[0]


def load_manifest_nodes(
    manifest_index: Path,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    index = load_json(manifest_index)
    assert index["source"]["tool"] == "figma.use_figma"
    assert index["source"]["read_only"] is True
    assert {screen["id"] for screen in index["screens"]} == TARGET_SCREEN_IDS

    by_id: dict[str, dict[str, Any]] = {}
    for screen in index["screens"]:
        nodes: list[dict[str, Any]] = []
        directory = manifest_index.parent / screen["directory"]
        for chunk_index in range(screen["chunks"]):
            chunk = directory / f"chunk_{chunk_index:02d}.json"
            payload = load_json(chunk)
            nodes.extend(payload["nodes"])

        assert len(nodes) == screen["count"], (
            f"Manifest count mismatch for {screen['id']}: "
            f"{len(nodes)} != {screen['count']}"
        )
        ids = [node["id"] for node in nodes]
        assert len(ids) == len(set(ids)), f"Duplicate manifest IDs in {screen['id']}"
        id_set = set(ids)
        assert screen["id"] in id_set
        orphans = [
            node["id"]
            for node in nodes
            if node.get("parent_id") and node["parent_id"] not in id_set
        ]
        assert not orphans, f"Orphan manifest nodes in {screen['id']}: {orphans}"
        overlap = set(ids) & by_id.keys()
        assert not overlap, f"Cross-screen duplicate manifest IDs: {sorted(overlap)}"
        by_id.update({node["id"]: node for node in nodes})
    return index, by_id


def first_visible(
    paints: list[dict[str, Any]],
    paint_types: set[str],
) -> dict[str, Any] | None:
    return next(
        (
            paint
            for paint in paints
            if paint.get("type") in paint_types and paint.get("visible", True)
        ),
        None,
    )


def radius_px(node: dict[str, Any], report: dict[str, Any]) -> int:
    radius = node.get("cornerRadius")
    if isinstance(radius, (int, float)):
        return max(0, round_px(radius))

    radii = [
        round_px(value)
        for value in (node.get("cornerRadii") or [])
        if isinstance(value, (int, float))
    ]
    if len(set(radii)) > 1:
        report["mixed_corner_radius_reductions"].append(
            {
                "figma_id": node["id"],
                "name": node["name"],
                "source": radii,
                "target": max(radii),
            }
        )
    return max(radii, default=0)


def add_fill_style(
    style: dict[str, Any],
    source: dict[str, Any],
    report: dict[str, Any],
) -> None:
    paints = source.get("fills") or []
    gradient = first_visible(paints, {"GRADIENT_LINEAR"})
    solid = first_visible(paints, {"SOLID"})

    if gradient is not None:
        stops = sorted(
            gradient.get("gradientStops") or [],
            key=lambda stop: stop.get("position", 0),
        )
        if len(stops) >= 2:
            first = stops[0]
            last = stops[-1]
            first_color = first.get("color") or {}
            last_color = last.get("color") or {}
            transform = gradient.get("gradientTransform") or [[1, 0, 0], [0, 1, 0]]
            dx = transform[0][0] if transform and transform[0] else 1
            dy = transform[1][0] if len(transform) > 1 and transform[1] else 0
            direction = "LV_GRAD_DIR_HOR" if abs(dx) >= abs(dy) else "LV_GRAD_DIR_VER"
            style.update(
                {
                    "bg_color": rgb_to_hex(first_color),
                    "bg_main_opa": clamp_byte(
                        gradient.get("opacity", 1) * first_color.get("a", 1)
                    ),
                    "bg_main_stop": clamp_byte(first.get("position", 0)),
                    "bg_grad_color": rgb_to_hex(last_color),
                    "bg_grad_opa": clamp_byte(
                        gradient.get("opacity", 1) * last_color.get("a", 1)
                    ),
                    "bg_grad_stop": clamp_byte(last.get("position", 1)),
                    "bg_grad_dir": direction,
                }
            )
            if len(stops) > 2:
                report["gradient_stop_reductions"].append(
                    {
                        "figma_id": source["id"],
                        "name": source["name"],
                        "source_stop_count": len(stops),
                        "target_stop_count": 2,
                    }
                )
            return

    if solid is not None:
        color = solid.get("color") or {}
        style.update(
            {
                "bg_color": rgb_to_hex(color),
                "bg_opa": clamp_byte(
                    solid.get("opacity", 1) * color.get("a", 1)
                ),
            }
        )
    else:
        style.update({"bg_color": "#000000", "bg_opa": 0})


def add_border_style(style: dict[str, Any], source: dict[str, Any]) -> None:
    stroke = first_visible(source.get("strokes") or [], {"SOLID"})
    weight = source.get("strokeWeight", 0)
    if stroke is None or not isinstance(weight, (int, float)) or weight <= 0:
        style.update({"border_width": 0, "border_opa": 0})
        return

    color = stroke.get("color") or {}
    style.update(
        {
            "border_color": rgb_to_hex(color),
            "border_opa": clamp_byte(
                stroke.get("opacity", 1) * color.get("a", 1)
            ),
            "border_width": max(1, round_px(weight)),
        }
    )


def visible_effect(
    source: dict[str, Any],
    effect_type: str,
) -> dict[str, Any] | None:
    return next(
        (
            effect
            for effect in (source.get("effects") or [])
            if effect.get("type") == effect_type and effect.get("visible", True)
        ),
        None,
    )


def add_shadow_style(
    style: dict[str, Any],
    source: dict[str, Any],
    target: dict[str, Any],
    report: dict[str, Any],
) -> None:
    inner = visible_effect(source, "INNER_SHADOW")
    drop = visible_effect(source, "DROP_SHADOW")
    if inner is not None:
        report["unsupported_inner_shadows"].append(
            {
                "figma_id": source["id"],
                "name": source["name"],
                "reason": "LVGL 9.4 object shadow is outer-only",
            }
        )

    # LVGL shadows the label rectangle rather than the glyph outline. Keeping
    # those Figma effects would create a visible box, so they stay disabled.
    if drop is not None and target.get("type") == "label":
        report["unsupported_label_shadows"].append(
            {
                "figma_id": source["id"],
                "name": source["name"],
                "reason": "LVGL object shadow would surround the text box",
            }
        )
        drop = None

    if drop is None:
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
        return

    color = drop.get("color") or {}
    offset = drop.get("offset") or {}
    style.update(
        {
            "shadow_color": rgb_to_hex(color),
            "shadow_opa": clamp_byte(color.get("a", 1)),
            "shadow_offset_x": round_px(offset.get("x", 0)),
            "shadow_offset_y": round_px(offset.get("y", 0)),
            "shadow_width": max(0, round_px(drop.get("radius", 0))),
            "shadow_spread": round_px(drop.get("spread", 0)),
        }
    )


def font_family(
    source: dict[str, Any],
    report: dict[str, Any],
) -> str:
    font_name = (source.get("text") or {}).get("fontName") or {}
    key = (font_name.get("family"), font_name.get("style"))
    assert key in FONT_MAP, f"Unmapped Figma font: {key} on {source['id']}"
    family, fallback_reason = FONT_MAP[key]
    if fallback_reason:
        record = {
            "figma_id": source["id"],
            "name": source["name"],
            "source": {"family": key[0], "style": key[1]},
            "target": family,
            "reason": fallback_reason,
        }
        if record not in report["font_fallbacks"]:
            report["font_fallbacks"].append(record)
    return family


def text_style(
    source: dict[str, Any],
    target: dict[str, Any],
    report: dict[str, Any],
) -> dict[str, Any]:
    text = source.get("text") or {}
    fill = first_visible(source.get("fills") or [], {"SOLID"})
    color = (fill or {}).get("color") or {}
    align = {
        "LEFT": "LV_TEXT_ALIGN_LEFT",
        "CENTER": "LV_TEXT_ALIGN_CENTER",
        "RIGHT": "LV_TEXT_ALIGN_RIGHT",
        "JUSTIFIED": "LV_TEXT_ALIGN_LEFT",
    }.get(text.get("textAlignHorizontal"), "LV_TEXT_ALIGN_LEFT")
    style: dict[str, Any] = {
        "part": "LV_PART_MAIN",
        "state": "LV_STATE_DEFAULT",
        "opa": 0 if not source.get("visible", True) else clamp_byte(source.get("opacity", 1)),
        "border_width": 0,
        "border_opa": 0,
        "outline_width": 0,
        "outline_opa": 0,
        "text_color": rgb_to_hex(color),
        "text_opa": clamp_byte(
            (fill or {}).get("opacity", 1) * color.get("a", 1)
        ),
        "text_size": max(1, round_px(text.get("fontSize", 14))),
        "text_family": font_family(source, report),
        "text_align": align,
    }
    letter_spacing = text.get("letterSpacing") or {}
    if letter_spacing.get("unit") == "PIXELS":
        spacing = round_px(letter_spacing.get("value", 0))
        if spacing:
            style["text_letter_space"] = spacing

    old_main = (target.get("style") or {}).get(MAIN_STYLE, {})
    if "pad_top" in old_main:
        style["pad_top"] = old_main["pad_top"]
        report["preserved_font_baseline_compensation"].append(
            {
                "figma_id": source["id"],
                "name": source["name"],
                "pad_top": old_main["pad_top"],
            }
        )
    add_shadow_style(style, source, target, report)
    return style


def visual_style(
    source: dict[str, Any],
    target: dict[str, Any],
    report: dict[str, Any],
) -> dict[str, Any]:
    if target.get("type") == "label":
        return text_style(source, target, report)

    style: dict[str, Any] = {
        "part": "LV_PART_MAIN",
        "state": "LV_STATE_DEFAULT",
        "opa": 0 if not source.get("visible", True) else clamp_byte(source.get("opacity", 1)),
        "radius": radius_px(source, report),
        "outline_width": 0,
        "outline_opa": 0,
    }
    if target.get("type") not in {"image"}:
        style.update(
            {
                "clip_corner": 1,
                "pad_left": 0,
                "pad_right": 0,
                "pad_top": 0,
                "pad_bottom": 0,
            }
        )
        add_fill_style(style, source, report)
        add_border_style(style, source)
    else:
        style.update({"border_width": 0, "border_opa": 0})

    add_shadow_style(style, source, target, report)
    return style


def sync_target_screens(
    project: dict[str, Any],
    manifest_nodes: dict[str, dict[str, Any]],
    report: dict[str, Any],
) -> None:
    for screen_id in sorted(TARGET_SCREEN_IDS):
        screen = find_screen(project, screen_id)
        target_nodes = list(walk([screen]))
        target_by_figma_id = {
            node["figma_id"]: node
            for node in target_nodes
            if isinstance(node.get("figma_id"), str)
        }
        source_ids = {
            figma_id
            for figma_id, node in manifest_nodes.items()
            if figma_id == screen_id
            or _belongs_to_screen(figma_id, screen_id, manifest_nodes)
        }
        assert set(target_by_figma_id) == source_ids, (
            f"Target/manifest Figma ID mismatch for {screen_id}: "
            f"missing={sorted(source_ids - set(target_by_figma_id))}, "
            f"extra={sorted(set(target_by_figma_id) - source_ids)}"
        )

        for figma_id, target in target_by_figma_id.items():
            source = manifest_nodes[figma_id]
            before_style = deepcopy((target.get("style") or {}).get(MAIN_STYLE))
            target.setdefault("style", {})[MAIN_STYLE] = visual_style(
                source,
                target,
                report,
            )
            if before_style != target["style"][MAIN_STYLE]:
                report["style_updates"].append(
                    {
                        "screen_figma_id": screen_id,
                        "figma_id": figma_id,
                        "name": target["name"],
                    }
                )

            if target.get("type") == "label":
                target["text"] = (source.get("text") or {}).get("characters", "")

            if figma_id in GEOMETRY_UPDATES:
                before = {
                    key: target.get(key)
                    for key in GEOMETRY_UPDATES[figma_id]
                }
                for key, value in GEOMETRY_UPDATES[figma_id].items():
                    target[key] = value
                    target[f"{key}_unit"] = "px"
                after = {
                    key: target.get(key)
                    for key in GEOMETRY_UPDATES[figma_id]
                }
                if before != after:
                    report["geometry_updates"].append(
                        {
                            "screen_figma_id": screen_id,
                            "figma_id": figma_id,
                            "name": target["name"],
                            "before": before,
                            "after": after,
                        }
                    )


def _belongs_to_screen(
    figma_id: str,
    screen_id: str,
    nodes: dict[str, dict[str, Any]],
) -> bool:
    current = nodes[figma_id]
    while current.get("parent_id"):
        parent_id = current["parent_id"]
        if parent_id == screen_id:
            return True
        current = nodes[parent_id]
    return figma_id == screen_id


def validate_images_and_fonts(
    project: dict[str, Any],
) -> dict[str, Any]:
    used_fonts: set[str] = set()
    image_count = 0
    alpha_images = 0
    target_image_objects = {
        id(node)
        for screen_id in TARGET_SCREEN_IDS
        for node in walk([find_screen(project, screen_id)])
        if node.get("type") == "image"
    }
    transparent_target_images = 0
    for node in walk(project["UI"]["screen_list"]):
        style = (node.get("style") or {}).get(MAIN_STYLE, {})
        family = style.get("text_family")
        if family:
            used_fonts.add(family)

        if node.get("type") != "image":
            continue
        image_count += 1
        source = node.get("src", "").replace("\\", "/")
        assert source, f"Missing image source for {node.get('name')}"
        image_path = ROOT / source
        assert image_path.is_file(), f"Missing image: {source}"
        with Image.open(image_path) as image:
            assert image.width > 0 and image.height > 0
            assert image.format == "PNG", f"Image is not PNG: {source}"
            assert "A" in image.getbands(), f"Image has no alpha channel: {source}"
            alpha_images += 1
            if id(node) in target_image_objects:
                alpha_min, _ = image.getchannel("A").getextrema()
                assert alpha_min < 255, (
                    f"Target image lost transparent pixels: {source}"
                )
                transparent_target_images += 1

    unknown_fonts = used_fonts - FONT_FILES.keys()
    assert not unknown_fonts, f"Unknown font families: {sorted(unknown_fonts)}"
    for family in used_fonts:
        font_path = ROOT / "resources" / "font" / FONT_FILES[family]
        assert font_path.is_file(), f"Missing font file: {font_path}"
    return {
        "image_count": image_count,
        "png_with_alpha_count": alpha_images,
        "target_images_with_transparency": transparent_target_images,
        "font_families": sorted(used_fonts),
    }


def validate(
    before: dict[str, Any],
    after: dict[str, Any],
    manifest_nodes: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    assert after["projectSettings"] == before["projectSettings"]
    assert after["lvConf"] == before["lvConf"]
    assert after.get("metadata") == before.get("metadata")
    settings = after["projectSettings"]
    assert settings["lvglVersion"] == "9.4.0"
    assert (settings["width"], settings["height"]) == (960, 240)
    assert settings["targetConfig"]["colorDepth"] == 16
    assert settings["imageConfig"]["color_format"] == "RGB565A8"

    nodes = list(walk(after["UI"]["screen_list"]))
    names = [node.get("name", "") for node in nodes]
    ids = [node.get("id", "") for node in nodes]
    figma_ids = [
        node["figma_id"]
        for node in nodes
        if isinstance(node.get("figma_id"), str)
    ]
    assert all(IDENTIFIER.fullmatch(name) for name in names), (
        f"Invalid C identifiers: "
        f"{[name for name in names if not IDENTIFIER.fullmatch(name)]}"
    )
    assert len(names) == len(set(names)), "Duplicate GUI Guider names"
    assert len(ids) == len(set(ids)), "Duplicate GUI Guider IDs"
    assert len(figma_ids) == len(set(figma_ids)), "Duplicate Figma IDs"

    screens = project_screens(after)
    assert len(screens) == 15
    assert {screen.get("figma_id") for screen in screens} == EXPECTED_SCREEN_IDS
    assert sum(bool(screen.get("default_screen")) for screen in screens) == 1
    assert find_screen(after, "71:3")["default_screen"] is True
    for screen_id in TARGET_SCREEN_IDS:
        root = manifest_nodes[screen_id]
        assert (round_px(root["width"]), round_px(root["height"])) == (960, 240)

    preserved_screen_hashes: dict[str, str] = {}
    for screen in project_screens(before):
        screen_id = screen["figma_id"]
        if screen_id in TARGET_SCREEN_IDS:
            continue
        before_hash = canonical_hash(screen)
        after_hash = canonical_hash(find_screen(after, screen_id))
        assert before_hash == after_hash, f"Unexpected screen change: {screen_id}"
        preserved_screen_hashes[screen_id] = after_hash

    before_non_ui = deepcopy(before)
    after_non_ui = deepcopy(after)
    before_non_ui.pop("UI")
    after_non_ui.pop("UI")
    assert before_non_ui == after_non_ui, "Non-UI project data changed"
    assert before["UI"].get("event_list") == after["UI"].get("event_list")
    assert before["UI"].get("variable_setting") == after["UI"].get("variable_setting")

    for node in nodes:
        if node.get("type") == "label":
            assert node.get("width_unit") == node.get("height_unit") == "px"
            assert node.get("width", 0) > 0 and node.get("height", 0) > 0
        if node.get("type") == "button":
            style = node["style"][MAIN_STYLE]
            source = manifest_nodes.get(node.get("figma_id"))
            if source is not None and visible_effect(source, "DROP_SHADOW") is None:
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

    assets = validate_images_and_fonts(after)
    return {
        "screen_count": len(screens),
        "default_screen": "Home",
        "preserved_screen_hashes": dict(sorted(preserved_screen_hashes.items())),
        "target_screen_hashes_before": {
            screen_id: canonical_hash(find_screen(before, screen_id))
            for screen_id in sorted(TARGET_SCREEN_IDS)
        },
        "target_screen_hashes_after": {
            screen_id: canonical_hash(find_screen(after, screen_id))
            for screen_id in sorted(TARGET_SCREEN_IDS)
        },
        "assets": assets,
    }


def main() -> None:
    args = parse_args()
    before = load_json(args.input_project)
    project = deepcopy(before)
    index, manifest_nodes = load_manifest_nodes(args.manifest_index)
    report: dict[str, Any] = {
        "schema_version": "figma-mcp-home-menu-sync-report/v1",
        "source": {
            "manifest_index": str(args.manifest_index.resolve()),
            "snapshot_version": index["snapshot_version"],
            "tool": index["source"]["tool"],
            "read_only": index["source"]["read_only"],
        },
        "scope": {
            "updated_screen_figma_ids": sorted(TARGET_SCREEN_IDS),
            "preserved_screen_figma_ids": sorted(
                EXPECTED_SCREEN_IDS - TARGET_SCREEN_IDS
            ),
        },
        "style_updates": [],
        "geometry_updates": [],
        "gradient_stop_reductions": [],
        "mixed_corner_radius_reductions": [],
        "unsupported_inner_shadows": [],
        "unsupported_label_shadows": [],
        "font_fallbacks": [],
        "preserved_font_baseline_compensation": [],
    }
    sync_target_screens(project, manifest_nodes, report)
    report["validation"] = validate(before, project, manifest_nodes)
    write_json(args.output_project, project)
    report["input_sha256"] = file_hash(args.input_project)
    report["output_sha256"] = file_hash(args.output_project)
    write_json(args.report, report)
    print(
        json.dumps(
            {
                "output": str(args.output_project),
                "report": str(args.report),
                "style_updates": len(report["style_updates"]),
                "geometry_updates": len(report["geometry_updates"]),
                "validation": report["validation"],
                "sha256": report["output_sha256"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
