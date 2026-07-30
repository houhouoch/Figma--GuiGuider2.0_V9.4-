#!/usr/bin/env python3
"""Validate a full Figma MCP -> GUI Guider candidate conversion."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterator

from PIL import Image, ImageChops, ImageEnhance, ImageStat

import sync_completed_figma_to_guiguider as sync


ROOT = Path(__file__).resolve().parent.parent
MAIN_STYLE = sync.MAIN_STYLE


def walk(
    nodes: list[dict[str, Any]],
    parent: dict[str, Any] | None = None,
) -> Iterator[tuple[dict[str, Any], dict[str, Any] | None]]:
    for node in nodes:
        yield node, parent
        yield from walk(node.get("children", []) or [], node)


def parse_source(spec: dict[str, Any], index_path: Path) -> sync.SourceNode:
    source_dir = index_path.parent / spec["directory"]
    raw = source_dir / "raw_context.txt"
    if raw.is_file():
        _, metadata, tsx, _ = sync.extract_sections(raw.read_text(encoding="utf-8"))
        supplements = sorted(source_dir.glob("*_supplement.tsx"))
        if supplements:
            tsx = "\n".join(
                [tsx, *[path.read_text(encoding="utf-8") for path in supplements]]
            )
        return sync.parse_source_tree(metadata, tsx)
    return sync.parse_compact_tree(source_dir, sync.legacy_asset_urls(spec))


def screenshot_similarity(reference: Path, actual: Path) -> float:
    left = Image.open(reference).convert("RGB")
    right = Image.open(actual).convert("RGB")
    if right.size != left.size:
        right = right.resize(left.size)
    difference = ImageChops.difference(left, right)
    mean = sum(ImageStat.Stat(difference).mean) / 3
    return 1.0 - mean / 255.0


def absolute_source_box(node: sync.SourceNode) -> tuple[int, int, int, int]:
    x = node.x
    y = node.y
    parent = node.parent
    while parent is not None:
        x += parent.x
        y += parent.y
        parent = parent.parent
    return (
        round(x),
        round(y),
        round(x + node.width),
        round(y + node.height),
    )


def union_box(
    nodes: list[sync.SourceNode],
    size: tuple[int, int] = (960, 240),
) -> tuple[int, int, int, int] | None:
    if not nodes:
        return None
    boxes = [absolute_source_box(node) for node in nodes]
    x1 = max(0, min(box[0] for box in boxes))
    y1 = max(0, min(box[1] for box in boxes))
    x2 = min(size[0], max(box[2] for box in boxes))
    y2 = min(size[1], max(box[3] for box in boxes))
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def crop_similarity(
    reference: Path,
    actual: Path,
    box: tuple[int, int, int, int],
) -> float:
    left = Image.open(reference).convert("RGB")
    right = Image.open(actual).convert("RGB")
    if right.size != left.size:
        right = right.resize(left.size)
    difference = ImageChops.difference(left.crop(box), right.crop(box))
    mean = sum(ImageStat.Stat(difference).mean) / 3
    return 1.0 - mean / 255.0


def write_heatmap(reference: Path, actual: Path, output: Path) -> None:
    left = Image.open(reference).convert("RGB")
    right = Image.open(actual).convert("RGB")
    if right.size != left.size:
        right = right.resize(left.size)
    difference = ImageChops.difference(left, right)
    heat = ImageEnhance.Contrast(difference).enhance(3.0)
    output.parent.mkdir(parents=True, exist_ok=True)
    heat.save(output)


def is_cjk(value: str | None) -> bool:
    return bool(value and re.search(r"[\u3400-\u9fff]", value))


def visual_regions(root: sync.SourceNode) -> dict[str, tuple[int, int, int, int]]:
    nodes = list(sync.iter_source(root))
    by_name = {node.name.lower(): node for node in nodes}
    groups: dict[str, list[sync.SourceNode]] = {
        "voltage_value": [
            node
            for node in nodes
            if node.name.lower() in {"panel_voltage", "label_vout"}
        ],
        "current_value": [
            node
            for node in nodes
            if node.name.lower() in {"panel_current", "label_iout"}
        ],
        "units": [
            node
            for node in nodes
            if node.name.lower() in {"unit_vout", "unit_iout"}
        ],
        "titles": [
            node
            for node in nodes
            if any(
                token in node.name.lower()
                for token in ("title", "heading", "header")
            )
        ],
        "menu_icons": [
            node
            for node in nodes
            if "menu" in node.name.lower()
            and (node.image_hash or node.name.lower().startswith("img_"))
        ],
        "bottom_status": [
            node
            for node in nodes
            if absolute_source_box(node)[1] >= 180
            and any(
                token in node.name.lower()
                for token in ("status", "mode", "footer", "bottom")
            )
        ],
        "chinese_text": [
            node for node in nodes if node.tag == "text" and is_cjk(node.text)
        ],
        "critical_buttons": [
            node
            for node in nodes
            if node.name.lower().startswith(("btn_", "button_"))
        ],
    }
    regions: dict[str, tuple[int, int, int, int]] = {}
    for name, members in groups.items():
        box = union_box(members)
        if box is not None:
            regions[name] = box
    if root.id == "71:3":
        for region_name, node_name in {
            "voltage_value": "panel_voltage",
            "current_value": "panel_current",
            "units": "panel_measurements",
            "bottom_status": "panel_mode",
        }.items():
            node = by_name.get(node_name)
            if node is not None:
                regions[region_name] = absolute_source_box(node)
    return regions


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Figma -> GUI Guider 候选工程验证",
        "",
        f"- 页面：{report['screen_count']}",
        f"- SourceNode：{report['source_node_count']}",
        f"- 候选对象：{report['candidate_node_count']}",
        f"- 最低整页相似度：{report['minimum_visual_similarity']:.6f}",
        f"- 既有基线：{report['visual_baseline']:.6f}",
        f"- 相对基线：{report['minimum_visual_similarity_delta']:+.6f}",
        f"- 阻断项：{len(report['blocking_issues'])}",
        "",
        "## 页面相似度",
        "",
        "| 页面 | Figma ID | 整页 | 最低局部 |",
        "|---|---|---:|---:|",
    ]
    regions_by_id = {
        row["figma_id"]: row for row in report["regional_visual_similarity"]
    }
    for row in report["visual_similarity"]:
        regional = regions_by_id.get(row["figma_id"], {})
        region_scores = [
            item["score"] for item in regional.get("regions", [])
        ]
        minimum = min(region_scores) if region_scores else None
        minimum_text = f"{minimum:.6f}" if minimum is not None else "-"
        lines.append(
            f"| {row['name']} | `{row['figma_id']}` | "
            f"{row['score']:.6f} | {minimum_text} |"
        )
    lines.extend(["", "## 阻断项", ""])
    if report["blocking_issues"]:
        for item in report["blocking_issues"]:
            lines.append(f"- `{item['category']}`: {item['detail']}")
    else:
        lines.append("- 无自动校验阻断项。")
    lines.extend(
        [
            "",
            "## 说明",
            "",
            "- 热图位于报告同级 `heatmaps` 目录。",
            "- 本报告是静态 Schema 与轻量渲染校验，不等同于 GUI Guider 实际打开保存验证。",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--manifest-index", type=Path, required=True)
    parser.add_argument("--render-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--report-md", type=Path)
    parser.add_argument("--heatmap-dir", type=Path)
    parser.add_argument("--baseline-project", type=Path)
    parser.add_argument("--visual-baseline", type=float, default=0.940617)
    args = parser.parse_args()

    project = sync.load_json(args.project)
    index = sync.load_json(args.manifest_index)
    expected_root_ids = {row["id"] for row in index["roots"]}
    screens = [
        row
        for row in project["UI"]["screen_list"]
        if row.get("figma_id") in expected_root_ids
    ]
    candidate_rows = list(walk(screens))
    candidate_by_figma = {
        node["figma_id"]: (node, parent)
        for node, parent in candidate_rows
        if node.get("figma_id")
    }
    source_by_figma: dict[str, sync.SourceNode] = {}
    source_roots: dict[str, sync.SourceNode] = {}
    for spec in index["roots"]:
        root = parse_source(spec, args.manifest_index)
        source_roots[spec["id"]] = root
        source_by_figma.update(
            {node.id: node for node in sync.iter_source(root)}
        )

    text_missing: list[str] = []
    text_value_mismatches: list[dict[str, Any]] = []
    text_size_mismatches: list[dict[str, Any]] = []
    parent_mismatches: list[dict[str, Any]] = []
    visibility_mismatches: list[dict[str, Any]] = []
    intentionally_flattened = {
        node.id
        for root in source_roots.values()
        for node in sync.iter_source(root)
        if sync.is_transparent_text_wrapper(node)
    }
    switch_style_nodes = {
        child.id
        for root in source_roots.values()
        for node in sync.iter_source(root)
        if sync.classify(node, root) == "switch"
        for child in node.children
    }
    permitted_missing = intentionally_flattened | switch_style_nodes
    unexpected_source_missing = sorted(
        set(source_by_figma) - set(candidate_by_figma) - permitted_missing
    )
    permitted_candidate_extras = {
        f"{spec['id']}:overlay_content"
        for spec in index["roots"]
        if spec.get("kind") == "overlay"
    }
    unexpected_candidate_extras = sorted(
        set(candidate_by_figma) - set(source_by_figma) - permitted_candidate_extras
    )
    for figma_id, source in source_by_figma.items():
        target_row = candidate_by_figma.get(figma_id)
        if source.tag == "text" and source.text is not None:
            if not target_row:
                text_missing.append(figma_id)
                continue
            target = target_row[0]
            if target.get("text") != source.text:
                text_value_mismatches.append(
                    {
                        "figma_id": figma_id,
                        "source": source.text,
                        "target": target.get("text"),
                    }
                )
            expected_size = sync.label_style(source)[MAIN_STYLE]["text_size"]
            actual_size = target.get("style", {}).get(MAIN_STYLE, {}).get(
                "text_size"
            )
            if actual_size != expected_size:
                text_size_mismatches.append(
                    {
                        "figma_id": figma_id,
                        "source": expected_size,
                        "target": actual_size,
                    }
                )
        if not target_row:
            continue
        target, target_parent = target_row
        expected_hidden = source.hidden
        root_id = next(
            (
                root
                for root, visibility in sync.SEMANTIC_VISIBILITY.items()
                if figma_id in visibility
            ),
            None,
        )
        if root_id:
            expected_hidden = not sync.SEMANTIC_VISIBILITY[root_id][figma_id]
        actual_hidden = sync.HIDDEN in (target.get("add_flag") or [])
        if actual_hidden != expected_hidden:
            visibility_mismatches.append(
                {
                    "figma_id": figma_id,
                    "expected_hidden": expected_hidden,
                    "actual_hidden": actual_hidden,
                }
            )
        expected_parent = source.parent
        while expected_parent and expected_parent.id not in candidate_by_figma:
            expected_parent = expected_parent.parent
        expected_parent_id = expected_parent.id if expected_parent else None
        actual_parent_id = (
            target_parent.get("figma_id") if target_parent else None
        )
        overlay_parent = (
            f"{expected_parent_id}:overlay_content"
            if expected_parent_id is not None
            else None
        )
        if actual_parent_id not in {expected_parent_id, overlay_parent}:
            parent_mismatches.append(
                {
                    "figma_id": figma_id,
                    "expected_parent": expected_parent_id,
                    "actual_parent": actual_parent_id,
                }
            )

    layer_order_mismatches: list[dict[str, Any]] = []
    overlay_root_ids = {
        spec["id"] for spec in index["roots"] if spec.get("kind") == "overlay"
    }
    for root_id, root in source_roots.items():
        for source_parent in sync.iter_source(root):
            if not source_parent.children:
                continue
            parent_figma_id = (
                f"{root_id}:overlay_content"
                if source_parent.id == root_id and root_id in overlay_root_ids
                else source_parent.id
            )
            target_parent_row = candidate_by_figma.get(parent_figma_id)
            if target_parent_row is None:
                continue
            expected_order: list[str] = []
            parent_is_switch = sync.classify(source_parent, root) == "switch"
            for child in source_parent.children:
                if parent_is_switch:
                    continue
                if sync.is_transparent_text_wrapper(child):
                    expected_order.append(child.children[0].id)
                else:
                    expected_order.append(child.id)
            expected_order.reverse()
            actual_order = [
                child.get("figma_id")
                for child in target_parent_row[0].get("children", []) or []
                if child.get("figma_id") in set(expected_order)
            ]
            if actual_order != expected_order:
                layer_order_mismatches.append(
                    {
                        "parent_figma_id": source_parent.id,
                        "parent_name": source_parent.name,
                        "expected": expected_order,
                        "actual": actual_order,
                    }
                )

    names = [node.get("name") for node, _ in candidate_rows]
    object_ids = [node.get("id") for node, _ in candidate_rows]
    figma_ids = [
        node.get("figma_id")
        for node, _ in candidate_rows
        if node.get("figma_id")
    ]
    invalid_identifiers = [
        name
        for name in names
        if not name or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", str(name))
    ]
    font_mismatches = [
        node.get("name")
        for node, _ in candidate_rows
        if node.get("type") == "label"
        and node.get("style", {}).get(MAIN_STYLE, {}).get("text_family")
        != "AlibabaPuHuiTi2.0.ttf"
    ]
    scrollbar_mismatches = [
        node.get("name")
        for node, _ in candidate_rows
        if node.get("type") in {"screen", "container"}
        and node.get("scrollbar_mode") != "LV_SCROLLBAR_MODE_OFF"
    ]
    invalid_labels = [
        node.get("name")
        for node, _ in candidate_rows
        if node.get("type") == "label"
        and (int(node.get("width") or 0) <= 0 or int(node.get("height") or 0) <= 0)
    ]
    image_resource_issues: list[dict[str, Any]] = []
    image_resources: set[str] = set()
    for node, _ in candidate_rows:
        if node.get("type") != "image":
            continue
        src = node.get("src")
        if not src:
            image_resource_issues.append(
                {"name": node.get("name"), "issue": "missing src"}
            )
            continue
        resource = ROOT / str(src).replace("\\", "/")
        if not resource.is_file():
            image_resource_issues.append(
                {
                    "name": node.get("name"),
                    "issue": "file not found",
                    "src": src,
                }
            )
            continue
        try:
            _, _, alpha = sync.png_has_alpha(resource)
        except Exception as error:  # noqa: BLE001 - report malformed resources.
            image_resource_issues.append(
                {
                    "name": node.get("name"),
                    "issue": f"invalid PNG: {error}",
                    "src": src,
                }
            )
            continue
        if not alpha:
            image_resource_issues.append(
                {
                    "name": node.get("name"),
                    "issue": "PNG lacks alpha",
                    "src": src,
                }
            )
        image_resources.add(str(src).replace("\\", "/"))

    horizontal_scroll_risks: list[dict[str, Any]] = []
    for node, parent in candidate_rows:
        if parent is None:
            continue
        if sync.SCROLLABLE in (parent.get("remove_flag") or []):
            continue
        right = int(node.get("x") or 0) + int(node.get("width") or 0)
        left = int(node.get("x") or 0)
        parent_width = int(parent.get("width") or 960)
        if left < 0 or right > parent_width + 1:
            horizontal_scroll_risks.append(
                {
                    "parent": parent.get("name"),
                    "child": node.get("name"),
                    "left": left,
                    "right": right,
                    "parent_width": parent_width,
                }
            )

    project_settings = project.get("projectSettings") or {}
    target_config = project_settings.get("targetConfig") or {}
    project_configuration_ok = (
        project_settings.get("lvglVersion") == "9.4.0"
        and project_settings.get("width") == 960
        and project_settings.get("height") == 240
        and target_config.get("colorDepth") == 16
        and target_config.get("display_name") == "RGB565"
    )
    defaults = [
        screen.get("name")
        for screen in screens
        if screen.get("default_screen")
    ]
    baseline_non_screen_unchanged: bool | None = None
    baseline_business_unchanged: bool | None = None
    if args.baseline_project:
        baseline = sync.load_json(args.baseline_project)
        baseline_non_screen = json.loads(json.dumps(baseline))
        candidate_non_screen = json.loads(json.dumps(project))
        baseline_non_screen["UI"]["screen_list"] = []
        candidate_non_screen["UI"]["screen_list"] = []
        baseline_non_screen_unchanged = baseline_non_screen == candidate_non_screen
        baseline_business_unchanged = (
            baseline["UI"].get("event_list") == project["UI"].get("event_list")
            and baseline["UI"].get("variable_setting")
            == project["UI"].get("variable_setting")
        )

    text_box_metric_issues: list[dict[str, Any]] = []
    centered_text_issues: list[dict[str, Any]] = []
    for node, parent in candidate_rows:
        if node.get("type") != "label":
            continue
        style = node.get("style", {}).get(MAIN_STYLE, {})
        text = str(node.get("text") or "")
        size = int(style.get("text_size") or 0)
        measured_width, line_height = sync.rendered_text_metrics(text, size)
        if size < 80:
            available_height = (
                int(parent.get("height") or line_height)
                if parent is not None
                else line_height
            )
            expected_height = min(line_height, max(1, available_height))
            if int(node.get("height") or 0) < expected_height:
                text_box_metric_issues.append(
                    {
                        "name": node.get("name"),
                        "axis": "height",
                        "actual": node.get("height"),
                        "expected_min": expected_height,
                    }
                )
        if measured_width and "\n" not in text and parent is not None:
            available_width = max(
                int(node.get("width") or 0),
                int(parent.get("width") or 0) - int(node.get("x") or 0),
            )
            expected_width = min(measured_width + 4, available_width)
            if int(node.get("width") or 0) < expected_width:
                text_box_metric_issues.append(
                    {
                        "name": node.get("name"),
                        "axis": "width",
                        "actual": node.get("width"),
                        "expected_min": expected_width,
                    }
                )
        parent_name = str(parent.get("name") or "").lower() if parent else ""
        if (
            parent is not None
            and int(parent.get("width") or 0) <= 40
            and int(parent.get("height") or 0) <= 40
            and ("badge" in parent_name or "icon" in parent_name)
        ):
            x_offset = abs(
                2 * int(node.get("x") or 0)
                + int(node.get("width") or 0)
                - int(parent.get("width") or 0)
            )
            y_offset = abs(
                2 * int(node.get("y") or 0)
                + int(node.get("height") or 0)
                - int(parent.get("height") or 0)
            )
            if x_offset > 1 or y_offset > 1:
                centered_text_issues.append(
                    {
                        "name": node.get("name"),
                        "parent": parent.get("name"),
                        "x_half_pixel_offset": x_offset,
                        "y_half_pixel_offset": y_offset,
                    }
                )
    group_info_icon = candidate_by_figma.get("243:591")
    group_info_icon_style = (
        group_info_icon[0].get("style", {}).get(MAIN_STYLE, {})
        if group_info_icon
        else {}
    )
    group_info_icon_border_ok = bool(
        group_info_icon
        and int(group_info_icon_style.get("border_width") or 0) > 0
        and int(group_info_icon_style.get("border_opa") or 0) > 0
        and group_info_icon_style.get("border_color") not in {None, "#000000"}
    )
    stale_nav_edges = [
        name for name in names if name and "decor_nav_right_edge" in name
    ]
    delay_badge_ids = {
        "243:401",
        "243:399",
        "243:397",
        "243:395",
        "243:393",
        "243:391",
    }
    delay_badge_center_offsets = []
    for node, parent in candidate_rows:
        if node.get("figma_id") not in delay_badge_ids:
            continue
        assert parent is not None
        offset = abs(
            2 * int(node.get("x") or 0)
            + int(node.get("width") or 0)
            - int(parent.get("width") or 0)
        )
        delay_badge_center_offsets.append(
            {"name": node.get("name"), "half_pixel_offset": offset}
        )

    similarities = []
    regional_similarities = []
    visual_missing: list[str] = []
    heatmap_dir = args.heatmap_dir or args.report.parent / "heatmaps"
    for spec in index["roots"]:
        reference = ROOT / spec["screenshot"]
        actual = args.render_dir / f"{spec['id'].replace(':', '_')}.png"
        if not reference.is_file() or not actual.is_file():
            visual_missing.append(spec["id"])
            continue
        similarities.append(
            {
                "figma_id": spec["id"],
                "name": spec["name"],
                "score": round(screenshot_similarity(reference, actual), 6),
            }
        )
        heatmap_path = heatmap_dir / f"{spec['id'].replace(':', '_')}.png"
        write_heatmap(reference, actual, heatmap_path)
        regions = []
        for region_name, box in visual_regions(source_roots[spec["id"]]).items():
            regions.append(
                {
                    "name": region_name,
                    "box": list(box),
                    "score": round(crop_similarity(reference, actual, box), 6),
                }
            )
        regional_similarities.append(
            {
                "figma_id": spec["id"],
                "name": spec["name"],
                "heatmap": str(heatmap_path.resolve()),
                "regions": sorted(regions, key=lambda row: row["score"]),
            }
        )
    similarities.sort(key=lambda row: row["score"])
    regional_similarities.sort(key=lambda row: row["figma_id"])

    duplicate_names = sorted(
        {name for name in names if names.count(name) > 1}
    )
    duplicate_object_ids = sorted(
        {object_id for object_id in object_ids if object_ids.count(object_id) > 1}
    )
    duplicate_figma_ids = sorted(
        {figma_id for figma_id in figma_ids if figma_ids.count(figma_id) > 1}
    )
    minimum_visual = min(
        (row["score"] for row in similarities),
        default=0.0,
    )
    all_region_scores = [
        {
            "figma_id": page["figma_id"],
            "page": page["name"],
            **region,
        }
        for page in regional_similarities
        for region in page["regions"]
    ]
    regional_failures = [
        row for row in all_region_scores if row["score"] < 0.65
    ]

    blocking_issues: list[dict[str, Any]] = []

    def block(category: str, detail: Any) -> None:
        blocking_issues.append({"category": category, "detail": detail})

    checks = [
        (len(screens) != len(expected_root_ids), "screen_count", len(screens)),
        (not project_configuration_ok, "project_configuration", project_settings),
        (defaults != ["Home"], "default_screen", defaults),
        (bool(duplicate_names), "duplicate_names", duplicate_names[:20]),
        (
            bool(duplicate_object_ids),
            "duplicate_object_ids",
            duplicate_object_ids[:20],
        ),
        (
            bool(duplicate_figma_ids),
            "duplicate_figma_ids",
            duplicate_figma_ids[:20],
        ),
        (
            bool(invalid_identifiers),
            "invalid_c_identifiers",
            invalid_identifiers[:20],
        ),
        (
            bool(unexpected_source_missing),
            "unexpected_source_nodes_missing",
            unexpected_source_missing[:20],
        ),
        (
            bool(unexpected_candidate_extras),
            "unexpected_candidate_nodes",
            unexpected_candidate_extras[:20],
        ),
        (bool(text_missing), "text_missing", text_missing[:20]),
        (
            bool(text_value_mismatches),
            "text_value_mismatches",
            text_value_mismatches[:20],
        ),
        (
            bool(text_size_mismatches),
            "text_size_mismatches",
            text_size_mismatches[:20],
        ),
        (bool(font_mismatches), "font_mismatches", font_mismatches[:20]),
        (bool(parent_mismatches), "parent_mismatches", parent_mismatches[:20]),
        (
            bool(layer_order_mismatches),
            "layer_order_mismatches",
            layer_order_mismatches[:20],
        ),
        (
            bool(visibility_mismatches),
            "visibility_mismatches",
            visibility_mismatches[:20],
        ),
        (
            bool(scrollbar_mismatches),
            "scrollbar_mismatches",
            scrollbar_mismatches[:20],
        ),
        (
            bool(image_resource_issues),
            "image_resource_issues",
            image_resource_issues[:20],
        ),
        (bool(invalid_labels), "invalid_labels", invalid_labels[:20]),
        (
            bool(text_box_metric_issues),
            "text_box_metric_issues",
            text_box_metric_issues[:20],
        ),
        (bool(visual_missing), "visual_missing", visual_missing),
        (
            baseline_non_screen_unchanged is False,
            "non_screen_project_fields_changed",
            "projectSettings/lvConf/event_list/variable_setting or metadata changed",
        ),
        (
            baseline_business_unchanged is False,
            "business_fields_changed",
            "event_list or variable_setting changed",
        ),
        (
            minimum_visual < 0.84,
            "minimum_visual_similarity",
            minimum_visual,
        ),
        (
            bool(regional_failures),
            "regional_visual_failures",
            regional_failures[:20],
        ),
    ]
    for failed, category, detail in checks:
        if failed:
            block(category, detail)

    report = {
        "schema_version": "figma-guiguider-validation/v2",
        "screen_count": len(screens),
        "candidate_node_count": len(candidate_rows),
        "source_node_count": len(source_by_figma),
        "source_text_count": sum(
            1
            for node in source_by_figma.values()
            if node.tag == "text" and node.text is not None
        ),
        "candidate_text_count": sum(
            1 for node, _ in candidate_rows if node.get("type") == "label"
        ),
        "text_missing": text_missing,
        "text_value_mismatches": text_value_mismatches,
        "text_size_mismatches": text_size_mismatches,
        "font_mismatches": font_mismatches,
        "parent_mismatches": parent_mismatches,
        "layer_order_mismatches": layer_order_mismatches,
        "visibility_mismatches": visibility_mismatches,
        "scrollbar_mismatches": scrollbar_mismatches,
        "unexpected_source_nodes_missing": unexpected_source_missing,
        "unexpected_candidate_nodes": unexpected_candidate_extras,
        "intentionally_flattened_nodes": sorted(intentionally_flattened),
        "switch_style_nodes": sorted(switch_style_nodes),
        "duplicate_names": duplicate_names,
        "duplicate_object_ids": duplicate_object_ids,
        "duplicate_figma_ids": duplicate_figma_ids,
        "invalid_c_identifiers": invalid_identifiers,
        "invalid_labels": invalid_labels,
        "text_box_metric_issues": text_box_metric_issues,
        "centered_text_issues": centered_text_issues,
        "group_info_icon_border_ok": group_info_icon_border_ok,
        "stale_nav_edges": stale_nav_edges,
        "delay_badge_center_offsets": delay_badge_center_offsets,
        "project_configuration_ok": project_configuration_ok,
        "default_screens": defaults,
        "baseline_non_screen_unchanged": baseline_non_screen_unchanged,
        "baseline_business_unchanged": baseline_business_unchanged,
        "image_widget_count": sum(
            1 for node, _ in candidate_rows if node.get("type") == "image"
        ),
        "unique_image_resources": len(image_resources),
        "image_resource_issues": image_resource_issues,
        "horizontal_scroll_risks": horizontal_scroll_risks,
        "scrollable_screens": [
            node.get("name")
            for node, _ in candidate_rows
            if node.get("type") == "screen"
            and sync.SCROLLABLE not in (node.get("remove_flag") or [])
        ],
        "scrollable_containers": [
            node.get("name")
            for node, _ in candidate_rows
            if node.get("type") == "container"
            and sync.SCROLLABLE not in (node.get("remove_flag") or [])
        ],
        "visual_similarity": similarities,
        "regional_visual_similarity": regional_similarities,
        "regional_visual_failures": regional_failures,
        "minimum_regional_visual_similarity": min(
            (row["score"] for row in all_region_scores),
            default=None,
        ),
        "minimum_visual_similarity": minimum_visual,
        "visual_baseline": args.visual_baseline,
        "minimum_visual_similarity_delta": minimum_visual - args.visual_baseline,
        "blocking_issues": blocking_issues,
        "gui_guider_roundtrip_verified": False,
    }

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    report_md = args.report_md or args.report.with_suffix(".md")
    report_md.write_text(
        render_markdown(report),
        encoding="utf-8",
        newline="\n",
    )
    visual_report = {
        "schema_version": "figma-guiguider-visual-validation/v1",
        "visual_baseline": report["visual_baseline"],
        "minimum_visual_similarity": report["minimum_visual_similarity"],
        "minimum_visual_similarity_delta": report[
            "minimum_visual_similarity_delta"
        ],
        "minimum_regional_visual_similarity": report[
            "minimum_regional_visual_similarity"
        ],
        "visual_similarity": report["visual_similarity"],
        "regional_visual_similarity": report["regional_visual_similarity"],
        "regional_visual_failures": report["regional_visual_failures"],
        "heatmap_directory": str(heatmap_dir.resolve()),
    }
    visual_json_path = args.report.parent / "visual_comparison_report.json"
    visual_json_path.write_text(
        json.dumps(visual_report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    visual_md_lines = [
        "# 视觉对比报告",
        "",
        f"- 既有最低基线：{report['visual_baseline']:.6f}",
        f"- 本次最低整页：{report['minimum_visual_similarity']:.6f}",
        f"- 基线变化：{report['minimum_visual_similarity_delta']:+.6f}",
        f"- 本次最低局部：{report['minimum_regional_visual_similarity']:.6f}",
        f"- 局部失败项：{len(report['regional_visual_failures'])}",
        f"- 热图目录：`{heatmap_dir.resolve()}`",
        "",
        "| 页面 | Figma ID | 相似度 |",
        "|---|---|---:|",
    ]
    visual_md_lines.extend(
        f"| {row['name']} | `{row['figma_id']}` | {row['score']:.6f} |"
        for row in report["visual_similarity"]
    )
    (args.report.parent / "visual_comparison_report.md").write_text(
        "\n".join(visual_md_lines) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if blocking_issues:
        raise AssertionError(
            f"Validation has {len(blocking_issues)} blocking issue categories"
        )


if __name__ == "__main__":
    main()
