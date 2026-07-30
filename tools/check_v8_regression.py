#!/usr/bin/env python3
"""Check that the controlled-sync converter still reproduces the V8 baseline."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any


IDENTITY_FIELDS = ("id", "name", "type", "src")
ALLOWED_VISUAL_FIELDS = {"x", "y"}
ALLOWED_VISUAL_SCREENS = {"screen_recall", "screen_save"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def flatten_figma_objects(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    objects: dict[str, dict[str, Any]] = {}

    def visit(node: dict[str, Any], screen_name: str) -> None:
        figma_id = node.get("figma_id")
        if figma_id:
            objects[figma_id] = {
                "screen": screen_name,
                "node": node,
            }
        for child in node.get("children", []):
            if isinstance(child, dict):
                visit(child, screen_name)

    for screen in document["UI"]["screen_list"]:
        if screen.get("type") != "screen":
            continue
        visit(screen, screen.get("name", ""))
    return objects


def non_screen_contract(document: dict[str, Any]) -> dict[str, Any]:
    contract = copy.deepcopy(document)
    contract.pop("lastModified", None)
    ui = contract.get("UI", {})
    ui.pop("screen_list", None)
    return contract


def compare_objects(
    formal_objects: dict[str, dict[str, Any]],
    regenerated_objects: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    contract_differences: list[dict[str, Any]] = []
    visual_differences: list[dict[str, Any]] = []

    for figma_id in sorted(formal_objects.keys() & regenerated_objects.keys()):
        formal_entry = formal_objects[figma_id]
        regenerated_entry = regenerated_objects[figma_id]
        formal_node = formal_entry["node"]
        regenerated_node = regenerated_entry["node"]

        for field in IDENTITY_FIELDS:
            if formal_node.get(field) != regenerated_node.get(field):
                contract_differences.append(
                    {
                        "figma_id": figma_id,
                        "screen": formal_entry["screen"],
                        "name": formal_node.get("name"),
                        "field": field,
                        "formal": formal_node.get(field),
                        "regenerated": regenerated_node.get(field),
                    }
                )

        fields = (formal_node.keys() | regenerated_node.keys()) - {
            "children",
            *IDENTITY_FIELDS,
        }
        for field in sorted(fields):
            if formal_node.get(field) == regenerated_node.get(field):
                continue
            difference = {
                "figma_id": figma_id,
                "screen": formal_entry["screen"],
                "name": formal_node.get("name"),
                "field": field,
                "formal": formal_node.get(field),
                "regenerated": regenerated_node.get(field),
            }
            if (
                field in ALLOWED_VISUAL_FIELDS
                and formal_entry["screen"].lower() in ALLOWED_VISUAL_SCREENS
            ):
                visual_differences.append(difference)
            else:
                contract_differences.append(difference)

    return contract_differences, visual_differences


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    status = "PASS" if report["passed"] else "FAIL"
    lines = [
        "# V8 Converter Regression",
        "",
        f"- Status: **{status}**",
        f"- Formal SHA-256: `{report['formal_sha256']}`",
        f"- Regenerated SHA-256: `{report['regenerated_sha256']}`",
        f"- Formal Figma IDs: {report['formal_figma_ids']}",
        f"- Regenerated Figma IDs: {report['regenerated_figma_ids']}",
        f"- Missing IDs: {len(report['missing_ids'])}",
        f"- New IDs: {len(report['new_ids'])}",
        f"- Non-screen configuration unchanged: {report['non_screen_configuration_unchanged']}",
        f"- Contract differences: {len(report['contract_differences'])}",
        f"- Accepted Recall/Save coordinate differences: {len(report['accepted_visual_differences'])}",
        "",
        "The accepted coordinate differences are existing manual Recall/Save icon-label",
        "corrections in the formal project. They are not generalized into the converter.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--formal", type=Path, required=True)
    parser.add_argument("--regenerated", type=Path, required=True)
    parser.add_argument("--json-report", type=Path, required=True)
    parser.add_argument("--markdown-report", type=Path, required=True)
    args = parser.parse_args()

    formal = load_json(args.formal)
    regenerated = load_json(args.regenerated)
    formal_objects = flatten_figma_objects(formal)
    regenerated_objects = flatten_figma_objects(regenerated)

    missing_ids = sorted(formal_objects.keys() - regenerated_objects.keys())
    new_ids = sorted(regenerated_objects.keys() - formal_objects.keys())
    contract_differences, visual_differences = compare_objects(
        formal_objects,
        regenerated_objects,
    )
    non_screen_unchanged = non_screen_contract(formal) == non_screen_contract(regenerated)
    passed = (
        not missing_ids
        and not new_ids
        and non_screen_unchanged
        and not contract_differences
    )

    report = {
        "schema_version": "1.0",
        "passed": passed,
        "formal_sha256": sha256(args.formal),
        "regenerated_sha256": sha256(args.regenerated),
        "formal_figma_ids": len(formal_objects),
        "regenerated_figma_ids": len(regenerated_objects),
        "missing_ids": missing_ids,
        "new_ids": new_ids,
        "non_screen_configuration_unchanged": non_screen_unchanged,
        "contract_differences": contract_differences,
        "accepted_visual_differences": visual_differences,
        "assessment": (
            "pass: no identity, schema, resource, event, or configuration regression"
            if passed
            else "fail: inspect missing IDs, contract differences, or non-screen configuration"
        ),
    }
    args.json_report.parent.mkdir(parents=True, exist_ok=True)
    args.json_report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_markdown(args.markdown_report, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
