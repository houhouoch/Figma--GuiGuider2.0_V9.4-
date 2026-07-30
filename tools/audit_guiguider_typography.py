#!/usr/bin/env python3
"""Audit Figma, baseline GUI Guider, and candidate text geometry."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_STYLE = "LV_PART_MAIN|LV_STATE_DEFAULT"
FIGMA_FONT_MAP = {
    "Alibaba PuHuiTi 2.0": "AlibabaPuHuiTi2.0.ttf",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def style_of(node: dict[str, Any]) -> dict[str, Any]:
    return node.get("style", {}).get(DEFAULT_STYLE, {})


def flatten_guider(project: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}

    def walk(
        node: dict[str, Any],
        parent_name: str | None,
        abs_x: float,
        abs_y: float,
        screen: str | None,
    ) -> None:
        node_x = float(node.get("x", 0) or 0)
        node_y = float(node.get("y", 0) or 0)
        current_x = abs_x + node_x
        current_y = abs_y + node_y
        current_screen = node.get("name") if node.get("type") == "screen" else screen
        figma_id = node.get("figma_id")
        if figma_id and node.get("type") == "label":
            style = style_of(node)
            result[figma_id] = {
                "figma_id": figma_id,
                "screen": current_screen,
                "name": node.get("name"),
                "parent": parent_name,
                "text": node.get("text"),
                "x": node.get("x"),
                "y": node.get("y"),
                "absolute_x": current_x,
                "absolute_y": current_y,
                "width": node.get("width"),
                "height": node.get("height"),
                "font_family": style.get("text_family"),
                "font_size": style.get("text_size"),
                "text_align": style.get("text_align"),
                "pad_top": style.get("pad_top", 0),
                "pad_bottom": style.get("pad_bottom", 0),
            }
        for child in node.get("children", []):
            walk(child, node.get("name"), current_x, current_y, current_screen)

    for root in project.get("UI", {}).get("screen_list", []):
        walk(root, None, 0.0, 0.0, None)
    return result


def flatten_figma(manifest_index: Path) -> dict[str, dict[str, Any]]:
    index = load_json(manifest_index)
    result: dict[str, dict[str, Any]] = {}
    for root in index.get("roots", []):
        source_path = manifest_index.parent / root["source_tree"]
        source = load_json(source_path)
        nodes = {node["id"]: node for node in source["nodes"]}
        root_node = nodes[source["root_id"]]
        root_x = float(root_node.get("x", 0) or 0)
        root_y = float(root_node.get("y", 0) or 0)

        for node in source["nodes"]:
            if node.get("node_type") != "text":
                continue
            # Compact Figma captures store canvas-absolute geometry. Normalize
            # every text node to its screen root before comparing it with the
            # GUI Guider screen-local coordinates.
            abs_x = float(node.get("x", 0) or 0) - root_x
            abs_y = float(node.get("y", 0) or 0) - root_y
            result[node["id"]] = {
                "figma_id": node["id"],
                "screen": source["nodes"][0]["name"],
                "name": node.get("name"),
                "parent": nodes.get(node.get("parent_id"), {}).get("name"),
                "text": node.get("text"),
                "x": node.get("x"),
                "y": node.get("y"),
                "absolute_x": abs_x,
                "absolute_y": abs_y,
                "width": node.get("width"),
                "height": node.get("height"),
                "font_family": node.get("font_family"),
                "expected_guider_family": FIGMA_FONT_MAP.get(node.get("font_family")),
                "font_style": node.get("font_style"),
                "font_size": node.get("font_size"),
                "text_align": node.get("text_align"),
                "line_height": node.get("line_height"),
            }
    return result


def changed_fields(
    left: dict[str, Any],
    right: dict[str, Any],
    fields: list[str],
) -> dict[str, list[Any]]:
    return {
        field: [left.get(field), right.get(field)]
        for field in fields
        if left.get(field) != right.get(field)
    }


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    summary = report["summary"]
    lines = [
        "# GUI Guider Typography Audit",
        "",
        "## Summary",
        "",
        f"- Figma text nodes: {summary['figma_text_nodes']}",
        f"- Baseline GUI labels: {summary['baseline_labels']}",
        f"- Candidate GUI labels: {summary['candidate_labels']}",
        f"- Matched baseline/candidate labels: {summary['matched_labels']}",
        f"- New candidate labels: {summary['new_candidate_labels']}",
        f"- Font family changes on matched labels: {summary['font_family_changes']}",
        f"- Font size changes on matched labels: {summary['font_size_changes']}",
        f"- Padding-top changes on matched labels: {summary['pad_top_changes']}",
        f"- Alignment changes on matched labels: {summary['alignment_changes']}",
        f"- Width changes on matched labels: {summary['width_changes']}",
        f"- Height changes on matched labels: {summary['height_changes']}",
        f"- Position changes on matched labels: {summary['position_changes']}",
        f"- Candidate/Figma family mapping mismatches: {summary['figma_family_mismatches']}",
        f"- Candidate/Figma size mismatches: {summary['figma_size_mismatches']}",
        f"- Figma labels with explicit line height: {summary['figma_explicit_line_height']}",
        f"- Missing candidate font files: {summary['missing_font_files']}",
        "",
        "## Interpretation",
        "",
        "Matched labels preserve the baseline GUI Guider font family and size.",
        "Any review workspace must include every referenced file under",
        "`resources/font`; otherwise GUI Guider falls back to a different font and",
        "all width, height, baseline, and clipping comparisons become invalid.",
        "",
        "## Per-label Details",
        "",
        "See `typography_audit.json` for the complete Figma/baseline/candidate record.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--manifest-index", type=Path, required=True)
    parser.add_argument("--candidate-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    args = parser.parse_args()

    baseline = flatten_guider(load_json(args.baseline))
    candidate = flatten_guider(load_json(args.candidate))
    figma = flatten_figma(args.manifest_index)
    matched_ids = sorted(set(baseline) & set(candidate))
    candidate_ids = sorted(candidate)
    font_files = sorted(
        {
            item["font_family"]
            for item in candidate.values()
            if item.get("font_family")
        }
    )
    missing_font_files = [
        family
        for family in font_files
        if not (args.candidate_root / "resources" / "font" / family).is_file()
    ]

    details: list[dict[str, Any]] = []
    baseline_fields = [
        "font_family",
        "font_size",
        "text_align",
        "pad_top",
        "pad_bottom",
        "width",
        "height",
        "absolute_x",
        "absolute_y",
        "parent",
    ]
    for figma_id in candidate_ids:
        baseline_item = baseline.get(figma_id)
        candidate_item = candidate[figma_id]
        figma_item = figma.get(figma_id)
        details.append(
            {
                "figma_id": figma_id,
                "baseline": baseline_item,
                "candidate": candidate_item,
                "figma": figma_item,
                "baseline_to_candidate": (
                    changed_fields(
                        baseline_item,
                        candidate_item,
                        baseline_fields,
                    )
                    if baseline_item
                    else {"status": ["missing", "new"]}
                ),
                "figma_to_candidate": (
                    {
                        "font_family": [
                            figma_item.get("expected_guider_family"),
                            candidate_item.get("font_family"),
                        ],
                        "font_size": [
                            figma_item.get("font_size"),
                            candidate_item.get("font_size"),
                        ],
                        "line_height_to_gui_padding": [
                            figma_item.get("line_height"),
                            {
                                "pad_top": candidate_item.get("pad_top"),
                                "pad_bottom": candidate_item.get("pad_bottom"),
                                "height": candidate_item.get("height"),
                            },
                        ],
                    }
                    if figma_item
                    else {"status": ["missing", "candidate_only"]}
                ),
            }
        )

    summary = {
        "figma_text_nodes": len(figma),
        "baseline_labels": len(baseline),
        "candidate_labels": len(candidate),
        "matched_labels": len(matched_ids),
        "new_candidate_labels": len(set(candidate) - set(baseline)),
        "font_family_changes": sum(
            baseline[item]["font_family"] != candidate[item]["font_family"]
            for item in matched_ids
        ),
        "font_size_changes": sum(
            baseline[item]["font_size"] != candidate[item]["font_size"]
            for item in matched_ids
        ),
        "pad_top_changes": sum(
            baseline[item]["pad_top"] != candidate[item]["pad_top"]
            for item in matched_ids
        ),
        "alignment_changes": sum(
            baseline[item]["text_align"] != candidate[item]["text_align"]
            for item in matched_ids
        ),
        "width_changes": sum(
            baseline[item]["width"] != candidate[item]["width"]
            for item in matched_ids
        ),
        "height_changes": sum(
            baseline[item]["height"] != candidate[item]["height"]
            for item in matched_ids
        ),
        "position_changes": sum(
            (
                baseline[item]["absolute_x"],
                baseline[item]["absolute_y"],
            )
            != (
                candidate[item]["absolute_x"],
                candidate[item]["absolute_y"],
            )
            for item in matched_ids
        ),
        "figma_family_mismatches": sum(
            bool(figma.get(item, {}).get("expected_guider_family"))
            and figma[item]["expected_guider_family"]
            != candidate[item]["font_family"]
            for item in candidate_ids
        ),
        "figma_size_mismatches": sum(
            figma.get(item, {}).get("font_size") is not None
            and figma[item]["font_size"] != candidate[item]["font_size"]
            for item in candidate_ids
        ),
        "figma_explicit_line_height": sum(
            figma.get(item, {}).get("line_height") is not None
            for item in candidate_ids
        ),
        "missing_font_files": len(missing_font_files),
    }
    report = {
        "schema_version": "figma-guiguider-typography-audit/v1",
        "summary": summary,
        "font_files": font_files,
        "missing_font_files": missing_font_files,
        "details": details,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_markdown(args.output_md, report)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not missing_font_files else 1


if __name__ == "__main__":
    raise SystemExit(main())
