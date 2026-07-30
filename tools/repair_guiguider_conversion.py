#!/usr/bin/env python3
"""Repair the local Figma-to-GUI-Guider conversion without rebuilding screens.

This is deliberately an incremental repair tool.  It uses the versioned Figma
manifests as the source for text metrics/visibility, preserves the current
project tree and user edits, and only changes conversion defects that can be
verified from the source design.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import re
import sys
from collections import Counter
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator

from fontTools.ttLib import TTFont


ROOT = Path(__file__).resolve().parent.parent
MANIFEST_INDEX = ROOT / "tools" / "manifests" / "v5_local_raw_20260727_final" / "index.json"
MAIN_STYLE = "LV_PART_MAIN|LV_STATE_DEFAULT"
SCROLLABLE = "LV_OBJ_FLAG_SCROLLABLE"
HIDDEN = "LV_OBJ_FLAG_HIDDEN"
SCREEN_HEIGHT = 240
TEXT_WIDTH_RESERVE = 2
FONT_PATHS = {
    "Inter-Regular": ROOT / "resources" / "font" / "Inter-Regular.ttf",
    "Inter-Medium": ROOT / "resources" / "font" / "Inter-Medium.ttf",
    "IBMPlexMono-Regular": ROOT / "resources" / "font" / "IBMPlexMono-Regular.ttf",
    "IBMPlexMono-Medium": ROOT / "resources" / "font" / "IBMPlexMono-Medium.ttf",
    "IBMPlexSans-Regular": ROOT / "resources" / "font" / "IBMPlexSans-Regular.ttf",
    "IBMPlexSans-Light": ROOT / "resources" / "font" / "IBMPlexSans-Light.ttf",
    "AlibabaPuHuiTi1": ROOT / "resources" / "font" / "AlibabaPuHuiTi1.ttf",
    "AlibabaPuHuiTi1.ttf": ROOT / "resources" / "font" / "AlibabaPuHuiTi1.ttf",
}


def load_sync_module() -> Any:
    path = ROOT / "tools" / "sync_completed_figma_to_guiguider.py"
    spec = importlib.util.spec_from_file_location("completed_sync", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def walk(node: dict[str, Any], parent: dict[str, Any] | None = None) -> Iterator[tuple[dict[str, Any], dict[str, Any] | None]]:
    yield node, parent
    for child in node.get("children", []) or []:
        yield from walk(child, node)


def style(node: dict[str, Any]) -> dict[str, Any]:
    return node.setdefault("style", {}).setdefault(MAIN_STYLE, {})


def px(value: float | int | None) -> int:
    return int(float(value or 0) + 0.5)


def source_font(classes: str, fallback: str | None) -> tuple[str | None, str | None]:
    match = re.search(r"font-\['([^']+)'\]", classes)
    value = match.group(1) if match else fallback
    if not value:
        return None, None
    if ":" in value:
        family, weight = value.rsplit(":", 1)
        return family.strip(), weight.strip()
    return value.strip(), None


def class_px(classes: str, token: str) -> float | None:
    """Return a numeric Tailwind arbitrary pixel value without matching colors.

    ``text-[#d6d6cf]`` appears before ``text-[16px]`` in most Figma exports;
    the generic class parser therefore cannot be used for text size.
    """
    match = re.search(rf"(?:^|\s){re.escape(token)}-\[(-?[0-9.]+)px\]", classes)
    return float(match.group(1)) if match else None


def gui_font(family: str | None, weight: str | None, current: str | None) -> str:
    key = (family or "").lower()
    w = (weight or "").lower()
    if "ibm plex mono" in key:
        return "IBMPlexMono-Medium" if "medium" in w else "IBMPlexMono-Regular"
    if "ibm plex sans" in key:
        return "IBMPlexSans-Light" if "light" in w else "IBMPlexSans-Regular"
    if "alibaba" in key or "puhui" in key:
        return "AlibabaPuHuiTi1"
    if "inter" in key:
        return "Inter-Medium" if "medium" in w or "semi" in w or "bold" in w else "Inter-Regular"
    return current or "Inter-Medium"


@lru_cache(maxsize=None)
def font_metrics(font_path: str) -> tuple[int, dict[int, str], dict[str, tuple[int, int]]]:
    font = TTFont(font_path, lazy=True)
    return font["head"].unitsPerEm, font.getBestCmap() or {}, font["hmtx"].metrics


def rendered_text_width(text: str, family: str, size: int) -> float | None:
    path = FONT_PATHS.get(family)
    if path is None or not path.is_file():
        return None
    units_per_em, cmap, hmtx = font_metrics(str(path))
    notdef_width = hmtx.get(".notdef", (units_per_em, 0))[0]
    advance = 0
    for char in text:
        glyph = cmap.get(ord(char))
        advance += hmtx.get(glyph, (notdef_width, 0))[0] if glyph else notdef_width
    return advance * size / units_per_em


def ensure_text_width(node: dict[str, Any], parent: dict[str, Any] | None, report: dict[str, Any]) -> None:
    """Reserve enough width for LVGL's actual font advance.

    Figma accepts fractional glyph widths inside integer-sized text boxes.
    LVGL clips a label whose integer box is even a fraction narrower than the
    rendered text.  Keep the Figma position, add a two-pixel safety reserve,
    and never grow beyond the current parent.
    """
    text = str(node.get("text") or "")
    current_style = style(node)
    if not text or "\n" in text or current_style.get("text_align") != "LV_TEXT_ALIGN_LEFT":
        return
    size = int(current_style.get("text_size") or 0)
    family = str(current_style.get("text_family") or "")
    measured = rendered_text_width(text, family, size)
    if measured is None:
        return
    required = int(math.ceil(measured)) + TEXT_WIDTH_RESERVE
    before = int(node.get("width") or 0)
    if before >= required:
        return
    parent_width = int((parent or {}).get("width") or 0)
    available = parent_width - int(node.get("x") or 0) if parent_width > 0 else required
    after = min(required, available)
    if after <= before:
        report["text_width_unresolved"].append({
            "name": node.get("name"), "text": text, "width": before,
            "required": required, "available": available,
        })
        return
    node["width"] = after
    report["text_width_repairs"].append({
        "name": node.get("name"), "text": text, "before": before,
        "after": after, "measured": round(measured, 3), "family": family, "size": size,
    })


def source_metrics(sync: Any) -> tuple[dict[str, dict[str, Any]], dict[str, str | None]]:
    index = json.loads(MANIFEST_INDEX.read_text(encoding="utf-8"))
    metrics: dict[str, dict[str, Any]] = {}
    parents: dict[str, str | None] = {}
    for spec in index["roots"]:
        directory = MANIFEST_INDEX.parent / spec["directory"]
        raw_path = directory / "raw_context.txt"
        if raw_path.exists():
            _, metadata, tsx, _ = sync.extract_sections(raw_path.read_text(encoding="utf-8"))
            root = sync.parse_source_tree(metadata, tsx)
            for node in sync.iter_source(root):
                parents[node.id] = node.parent.id if node.parent else None
                if node.text is None:
                    continue
                family, weight = source_font(node.classes, node.font_family)
                metrics[node.id] = {
                    "x": px(node.x), "y": px(node.y), "width": px(node.width), "height": px(node.height),
                    "size": px(node.font_size or class_px(node.classes, "text") or 18),
                    "family": family, "weight": weight,
                    "line_height": px(node.line_height or class_px(node.classes, "leading") or 0),
                    "align": (node.text_align or ("CENTER" if "text-center" in node.classes else "RIGHT" if "text-right" in node.classes else "LEFT")).upper(),
                    "color": (node.fill or sync.parse_color_class(node.classes, "text-") or ("#d6d6cf", 255)),
                    "text": chr(0x2192) if node.id == "243:608" else node.text, "hidden": node.hidden,
                }
        else:
            payloads = [directory / "manifest.json"]
            if not payloads[0].exists():
                payloads = sorted(directory.glob("manifest_[0-9]*_[0-9]*.json"))
            rows: list[dict[str, Any]] = []
            for path in payloads:
                rows.extend(json.loads(path.read_text(encoding="utf-8"))["nodes"])
            for row in rows:
                parents[row["id"]] = row.get("p")
                text = row.get("t")
                if not text:
                    continue
                metrics[row["id"]] = {
                    "x": px(row.get("x")), "y": px(row.get("y")), "width": px(row.get("w")), "height": px(row.get("h")),
                    "size": px(text.get("fs") or 18), "family": text.get("ff"), "weight": text.get("fy"),
                    "line_height": px(text.get("lh") or 0), "align": (text.get("a") or "LEFT").upper(),
                    "color": tuple(row.get("f") or ("#d6d6cf", 255)), "text": text.get("c") or "", "hidden": not bool(row.get("v", True)),
                }
    return metrics, parents


def apply_source_text(project: dict[str, Any], metrics: dict[str, dict[str, Any]], source_parents: dict[str, str | None], report: dict[str, Any]) -> None:
    gui_parent: dict[str, str | None] = {}
    for screen in project["UI"]["screen_list"]:
        for node, parent in walk(screen):
            if node.get("figma_id"):
                gui_parent[node["figma_id"]] = parent.get("figma_id") if parent else None

    for screen in project["UI"]["screen_list"]:
        for node, parent in walk(screen):
            fid = node.get("figma_id")
            if node.get("type") != "label" or fid not in metrics:
                continue
            source = metrics[fid]
            current_style = style(node)
            before = (node.get("width"), node.get("height"), current_style.get("text_size"), current_style.get("text_family"), node.get("text"))
            # Geometry is only safe to restore when the source and GUI parent
            # relationship is the same.  Flattened semantic controls retain their
            # existing position but still receive exact text style and content.
            if gui_parent.get(fid) == source_parents.get(fid):
                node.update({"x": source["x"], "y": source["y"], "width": source["width"], "height": source["height"]})
            node["text"] = source["text"]
            mapped_family = (
                "AlibabaPuHuiTi1"
                if re.search(r"[\u3400-\u9fff]", source["text"])
                else gui_font(source["family"], source["weight"], current_style.get("text_family"))
            )
            current_style.update({
                "text_size": source["size"],
                "text_family": mapped_family,
                "text_align": f"LV_TEXT_ALIGN_{source['align']}",
                "text_color": source["color"][0],
                "text_opa": int(source["color"][1]),
                "pad_top": 0,
            })
            after = (node.get("width"), node.get("height"), current_style.get("text_size"), current_style.get("text_family"), node.get("text"))
            if after != before:
                report["text_metrics_repaired"].append({"figma_id": fid, "name": node.get("name"), "before": before, "after": after})
            ensure_text_width(node, parent, report)


def normalize_scroll_flags(project: dict[str, Any], report: dict[str, Any]) -> None:
    """Hide scrollbar visuals while preserving the required vertical scrolling.

    Most long pages own scrolling at screen level because their root content
    container is taller than 240 px.  A viewport embedded beside fixed content
    (HOME_MENU) keeps scrolling on that viewport instead.
    """
    def content_extent(node: dict[str, Any], base_y: int = 0) -> int:
        maximum = base_y + int(node.get("height") or 0)
        for child in node.get("children", []) or []:
            child_y = base_y + int(child.get("y") or 0)
            maximum = max(maximum, content_extent(child, child_y))
        return maximum

    def set_scrollable(node: dict[str, Any], enabled: bool) -> None:
        flags = list(node.get("remove_flag", []) or [])
        if enabled:
            flags = [flag for flag in flags if flag != SCROLLABLE]
        elif SCROLLABLE not in flags:
            flags.append(SCROLLABLE)
        node["remove_flag"] = flags
        node["scrollbar_mode"] = "LV_SCROLLBAR_MODE_OFF"

    for screen in project["UI"]["screen_list"]:
        children = screen.get("children", []) or []
        container_rows = [
            node
            for node, _ in walk(screen)
            if node is not screen and node.get("type") == "container"
        ]
        overflow_candidates: dict[int, tuple[dict[str, Any], int]] = {}
        for node in container_rows:
            node_height = int(node.get("height") or 0)
            node_content = max(
                (content_extent(child, int(child.get("y") or 0)) for child in node.get("children", []) or []),
                default=node_height,
            )
            # Ignore font-metric and border rounding (typically 1-8px).  A
            # real viewport has substantial content beyond its visible box.
            if node_height <= SCREEN_HEIGHT and node_content > node_height + 8:
                overflow_candidates[id(node)] = (node, node_content)

        def contains_candidate(node: dict[str, Any]) -> bool:
            return any(
                id(descendant) in overflow_candidates
                for child in node.get("children", []) or []
                for descendant, _ in walk(child)
            )

        # Prefer the deepest viewport.  For screen_info this selects list_cont
        # rather than making both the 240px root and its list scrollable.
        embedded_viewports = {
            node_id: row
            for node_id, row in overflow_candidates.items()
            if not contains_candidate(row[0])
        }
        direct_extent = max(
            (int(child.get("y") or 0) + int(child.get("height") or 0) for child in children),
            default=SCREEN_HEIGHT,
        )

        # A single 240px root whose descendants continue below the viewport is
        # a flattened long page (not an embedded scroll panel).  Restore the
        # root's logical height so screen scrolling can expose all content.
        if len(children) == 1 and not embedded_viewports:
            root = children[0]
            recursive_extent = content_extent(root, 0)
            root_y = int(root.get("y") or 0)
            local_extent = recursive_extent - root_y
            before_height = int(root.get("height") or 0)
            if before_height <= SCREEN_HEIGHT and local_extent > before_height and local_extent > SCREEN_HEIGHT:
                root["height"] = local_extent
                direct_extent = root_y + local_extent
                report["content_height_repairs"].append({
                    "screen": screen.get("name"), "container": root.get("name"),
                    "before": before_height, "after": local_extent,
                })

        screen_scrollable = direct_extent > SCREEN_HEIGHT
        set_scrollable(screen, screen_scrollable)
        if screen_scrollable:
            report["scrollable_screens"].append({
                "name": screen.get("name"), "content_height": direct_extent,
            })

        for node, _ in walk(screen):
            if node is screen or node.get("type") != "container":
                continue
            node_height = int(node.get("height") or 0)
            node_content = max(
                (content_extent(child, int(child.get("y") or 0)) for child in node.get("children", []) or []),
                default=node_height,
            )
            # Ordinary controls and long-page roots remain non-scrollable.
            embedded_viewport = id(node) in embedded_viewports
            set_scrollable(node, embedded_viewport)
            if embedded_viewport:
                report["scrollable_containers"].append({
                    "screen": screen.get("name"), "name": node.get("name"),
                    "viewport_height": node_height, "content_height": node_content,
                })


def apply_source_visibility(project: dict[str, Any], metrics: dict[str, dict[str, Any]], source_parents: dict[str, str | None], report: dict[str, Any]) -> None:
    # Source visibility is relevant for every converted object, not only text.
    # Build it from the manifest parent map plus text rows; for non-text nodes
    # the current project is preserved except for known Log defects below.
    for screen in project["UI"]["screen_list"]:
        for node, _ in walk(screen):
            fid = node.get("figma_id")
            if fid not in metrics:
                continue
            flags = list(node.get("remove_flag", []) or [])
            if metrics[fid]["hidden"]:
                if HIDDEN not in flags:
                    flags.append(HIDDEN)
            else:
                flags = [flag for flag in flags if flag != HIDDEN]
            node["remove_flag"] = flags

    # These two visible source containers were incorrectly emitted as hidden;
    # they hide the entire Log table even though their Figma counterparts are visible.
    for node, _ in (item for screen in project["UI"]["screen_list"] for item in walk(screen)):
        if node.get("figma_id") in {"366:219", "366:221"}:
            flags = [flag for flag in node.get("remove_flag", []) if flag != HIDDEN]
            node["remove_flag"] = flags
            report["visibility_repaired"].append(node.get("name"))


def find_by_name(project: dict[str, Any], name: str) -> dict[str, Any]:
    for screen in project["UI"]["screen_list"]:
        for node, _ in walk(screen):
            if node.get("name") == name:
                return node
    raise AssertionError(f"Missing expected object: {name}")


def set_group_icons(project: dict[str, Any], report: dict[str, Any]) -> None:
    def border(name: str, radius: int, color: str, opacity: int, bg_color: str = "#000000", bg_opa: int = 0) -> None:
        obj = find_by_name(project, name)
        st = style(obj)
        st.update({"radius": radius, "bg_color": bg_color, "bg_opa": bg_opa, "border_width": 2, "border_color": color, "border_opa": opacity, "clip_corner": 1})
        report["group_icon_repairs"].append(name)

    border("panel_group_info_icon", 12, "#d99613", 181)
    border("panel_group_apply_icon", 14, "#d99613", 181)
    border("panel_group_master_icon_box", 4, "#d99613", 120, "#2b2623", 99)
    # Let the label occupy the complete icon box.  A narrow glyph-sized label
    # can be mathematically centred in Figma while still appearing offset in
    # LVGL because the two renderers use different glyph side bearings.
    for name, text, size, width, height, x, y in (
        ("label_group_info_icon_text", "i", 12, 24, 16, 0, 4),
        ("label_group_apply_icon_text", chr(0x2192), 16, 28, 20, 0, 4),
        ("label_group_master_icon_text", "M", 13, 12, 16, 11, 9),
    ):
        label = find_by_name(project, name)
        label.update({"text": text, "width": width, "height": height, "x": x, "y": y})
        style(label).update({"text_size": size, "text_family": "Inter-Medium", "text_align": "LV_TEXT_ALIGN_CENTER", "pad_top": 0})
    # A two-pixel invisible reserve avoids LVGL clipping a source-perfect title
    # at the container's right boundary.
    display = find_by_name(project, "cont_section_display")
    display["width"] = 107
    report["preference_display_width"] = 107


def set_admin_default_state(project: dict[str, Any], report: dict[str, Any]) -> None:
    """Keep only the currently selected Admin sub-page visible.

    The three Admin sub-pages occupy the same coordinates.  Figma keeps all
    editing frames visible on the canvas, but GUI Guider must start with one
    state only or the later-created opaque page covers the selected page.
    """
    visibility = {
        "cont_Admin_InitPage1": False,
        "cont_Admin_InitPage2": False,
        "cont_Admin_InitPage3": True,
    }
    for name, visible in visibility.items():
        node = find_by_name(project, name)
        flags = list(node.get("remove_flag", []) or [])
        if visible:
            flags = [flag for flag in flags if flag != HIDDEN]
        elif HIDDEN not in flags:
            flags.append(HIDDEN)
        node["remove_flag"] = flags
        report["admin_default_state"].append({"name": name, "visible": visible})


def validate(project: dict[str, Any], metrics: dict[str, dict[str, Any]]) -> dict[str, Any]:
    names: list[str] = []
    visible_scrollbars: list[str] = []
    text_mismatch: list[str] = []
    visible_log: list[str] = []
    for screen in project["UI"]["screen_list"]:
        for node, _ in walk(screen):
            if node.get("name"):
                names.append(node["name"])
            if node.get("type") in {"screen", "container"} and node.get("scrollbar_mode") != "LV_SCROLLBAR_MODE_OFF":
                visible_scrollbars.append(node.get("name", "<unnamed>"))
            if node.get("type") == "label" and node.get("figma_id") in metrics:
                src = metrics[node["figma_id"]]
                if style(node).get("text_size") != src["size"]:
                    text_mismatch.append(node["name"])
            if node.get("figma_id") in {"366:219", "366:221"} and HIDDEN in node.get("remove_flag", []):
                visible_log.append(node["name"])
    assert len(names) == len(set(names)), "Duplicate GUI Guider names"
    assert not visible_scrollbars, f"Visible scrollbar modes remain: {visible_scrollbars[:10]}"
    assert not text_mismatch, f"Text size mismatches: {text_mismatch[:10]}"
    assert not visible_log, f"Visible Log nodes still hidden: {visible_log}"
    for name, expected in (("panel_group_info_icon", 2), ("panel_group_apply_icon", 2), ("panel_group_master_icon_box", 2)):
        assert style(find_by_name(project, name)).get("border_width") == expected
    for label_name, parent_name in (
        ("label_group_info_icon_text", "panel_group_info_icon"),
        ("label_group_apply_icon_text", "panel_group_apply_icon"),
    ):
        label = find_by_name(project, label_name)
        parent = find_by_name(project, parent_name)
        assert label.get("x") == 0
        assert label.get("width") == parent.get("width")
        assert style(label).get("text_align") == "LV_TEXT_ALIGN_CENTER"
    display = find_by_name(project, "cont_section_display")
    assert display.get("width") == 107

    admin_visibility = {
        name: HIDDEN not in (find_by_name(project, name).get("remove_flag") or [])
        for name in ("cont_Admin_InitPage1", "cont_Admin_InitPage2", "cont_Admin_InitPage3")
    }
    assert admin_visibility == {
        "cont_Admin_InitPage1": False,
        "cont_Admin_InitPage2": False,
        "cont_Admin_InitPage3": True,
    }, f"Unexpected Admin default state: {admin_visibility}"

    # GUI Guider creates siblings in reverse JSON order.  The opaque Log
    # backgrounds therefore belong at the end of the JSON child list so they
    # are created first and remain behind every row/header/control.
    log_container = find_by_name(project, "cont_log_366_219")
    log_order = [child.get("name") for child in log_container.get("children", []) or []]
    expected_log_backgrounds = ["label_toolbar_bg", "label_log_header_bg", "label_log_panel_bg"]
    assert log_order[-3:] == expected_log_backgrounds, (
        f"Log backgrounds are not behind content: {log_order[-6:]}"
    )
    scrollable_screens = [
        screen.get("name")
        for screen in project["UI"]["screen_list"]
        if SCROLLABLE not in (screen.get("remove_flag") or [])
    ]
    scrollable_containers = [
        node.get("name")
        for screen in project["UI"]["screen_list"]
        for node, _ in walk(screen)
        if node.get("type") == "container" and SCROLLABLE not in (node.get("remove_flag") or [])
    ]
    return {
        "unique_names": len(names),
        "text_nodes_matched": sum(1 for screen in project["UI"]["screen_list"] for node, _ in walk(screen) if node.get("type") == "label" and node.get("figma_id") in metrics),
        "visible_scrollbars": 0,
        "scrollable_screens": scrollable_screens,
        "scrollable_containers": scrollable_containers,
        "admin_visibility": admin_visibility,
        "log_background_order": log_order[-3:],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=ROOT / "guiguider_2.0.guiguider")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    sync = load_sync_module()
    metrics, source_parents = source_metrics(sync)
    project = json.loads(args.input.read_text(encoding="utf-8"))
    report: dict[str, Any] = {
        "input": str(args.input),
        "text_metrics_repaired": [],
        "text_width_repairs": [],
        "text_width_unresolved": [],
        "scroll_flags_added": [],
        "scrollable_screens": [],
        "scrollable_containers": [],
        "content_height_repairs": [],
        "visibility_repaired": [],
        "group_icon_repairs": [],
        "admin_default_state": [],
    }
    apply_source_text(project, metrics, source_parents, report)
    normalize_scroll_flags(project, report)
    apply_source_visibility(project, metrics, source_parents, report)
    set_group_icons(project, report)
    set_admin_default_state(project, report)
    report["validation"] = validate(project, metrics)
    report["font_families"] = Counter(
        style(node).get("text_family")
        for screen in project["UI"]["screen_list"]
        for node, _ in walk(screen)
        if node.get("type") == "label"
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(project, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["validation"], ensure_ascii=False))


if __name__ == "__main__":
    main()
