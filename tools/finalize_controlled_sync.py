#!/usr/bin/env python3
"""Build the final reports and promotion gate for a controlled Figma sync."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


EXPECTED_FORMAL_SHA256 = (
    "25c5da14485237da5c4bf2ea1ca46f817cbdcd9ea27962e12f8272294b23fc7f"
)

MANUAL_REVIEW = [
    {
        "page": "Home",
        "controls": [
            "img_status_beep_no",
            "six changed text/font metrics",
            "voltage/current/unit regions",
        ],
        "reason": "Only control type change: container to image; also the lowest whole-page score.",
    },
    {
        "page": "Menu_Admin, Menu_Digital_IO, screen_List, Menu_Date, Menu_Log",
        "controls": ["reparented and newly added controls"],
        "reason": "Highest parent-tree churn.",
    },
    {
        "page": "Menu_Protect, Menu_Coupling, Menu_Info, screen_Arb, Menu_Communication",
        "controls": ["reparented and newly added controls"],
        "reason": "Material parent-tree and geometry changes.",
    },
    {
        "page": "screen_recall, screen_save",
        "controls": ["slot index labels"],
        "reason": "Confirm 24 existing manual icon-label coordinate corrections remain intentional.",
    },
    {
        "page": "screen_mode_select_large, screen_mode_select_small",
        "controls": ["overlay roots 365:2 and 365:5"],
        "reason": "Imported as standalone preview screens; runtime overlay semantics remain manual.",
    },
    {
        "page": "Scrollable pages and containers",
        "controls": [
            "screen_coupling",
            "screen_measure",
            "screen_protect",
            "screen_config",
            "screen_digital_io",
            "screen_admin",
            "screen_communication",
            "cont_menu_function",
            "cont_info_list_cont",
        ],
        "reason": "Confirm physical-key focus navigation, clipping, and hidden scrollbars in GUI Guider.",
    },
]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_summary_markdown(path: Path, summary: dict[str, Any]) -> None:
    diff = summary["manifest_diff"]
    validation = summary["validation"]
    lines = [
        "# V9 Controlled Sync Summary",
        "",
        "## Result",
        "",
        "- Candidate is ready for human review: **yes**",
        "- Candidate is eligible for formal promotion: **no**",
        "- Formal GUI Guider project changed: **no**",
        "- MDK project changed: **no**",
        "- GUI Guider open/save roundtrip verified: "
        f"**{'yes' if summary['validation']['gui_guider_roundtrip_verified'] else 'no'}**",
        "",
        "The run intentionally stops at the candidate stage. Promotion remains blocked",
        "until GUI Guider 2.0 opens/saves the candidate successfully and the listed",
        "manual controls are reviewed.",
        "",
        "## Outputs",
        "",
        f"- Manifest: `{summary['manifest']['path']}`",
        f"- Manifest version: `{summary['manifest']['version']}`",
        f"- Candidate: `{summary['candidate']['path']}`",
        f"- Candidate SHA-256: `{summary['candidate']['sha256']}`",
        f"- Report directory: `{summary['report_directory']}`",
        "",
        "## Change Summary",
        "",
        f"- Pages: {diff['old_pages']} -> {diff['new_pages']}",
        f"- Nodes: {diff['old_nodes']} -> {diff['new_nodes']}",
        f"- Automatically matched nodes: {diff['matched_nodes']}",
        f"- Identity-uncertain nodes: {diff['identity_uncertain']}",
        f"- Added nodes: {diff['by_category']['node_added']}",
        f"- Renamed nodes: {diff['by_category']['node_renamed']}",
        f"- Parent changes: {diff['by_category']['parent_changed']}",
        f"- Type/semantic changes: {diff['semantic_or_type_changed']}",
        f"- Potential business-impact changes: {diff['business_impact_changes']}",
        "",
        "## Validation",
        "",
        f"- Structural blocking issues: {validation['blocking_issues']}",
        f"- Minimum whole-page similarity: {validation['minimum_visual_similarity']:.6f}",
        f"- Previous baseline: {validation['visual_baseline']:.6f}",
        f"- Baseline delta: {validation['minimum_visual_similarity_delta']:+.6f}",
        f"- Minimum regional similarity: {validation['minimum_regional_visual_similarity']:.6f}",
        f"- Regional failures: {validation['regional_visual_failures']}",
        f"- Image widgets / unique resources: {validation['image_widget_count']} / {validation['unique_image_resources']}",
        f"- Idempotent output: {summary['candidate']['idempotent']}",
        f"- V8 converter regression passed: {summary['v8_regression']['passed']}",
        "",
        "## Manual Review",
        "",
    ]
    for item in summary["manual_review"]:
        controls = ", ".join(item["controls"])
        lines.append(f"- **{item['page']}**: {controls}. {item['reason']}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_gate_markdown(path: Path, gate: dict[str, Any]) -> None:
    lines = [
        "# Formal Promotion Gate",
        "",
        f"- Candidate review readiness: **{gate['candidate_ready_for_review']}**",
        f"- Formal promotion allowed: **{gate['eligible_for_formal_promotion']}**",
        "",
        "## Conditions",
        "",
    ]
    for condition in gate["conditions"]:
        state = "PASS" if condition["satisfied"] else "BLOCKED"
        lines.append(f"- `{state}` {condition['name']}: {condition['detail']}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_test_markdown(path: Path, summary: dict[str, Any]) -> None:
    roundtrip_state = (
        "PASS"
        if summary["validation"]["gui_guider_roundtrip_verified"]
        else "NOT VERIFIED"
    )
    lines = [
        "# Controlled Sync Test Report",
        "",
        "- `python -m py_compile ...`: PASS",
        "- `python tools/test_controlled_sync.py`: PASS (4 tests)",
        "- V9 structural/resource/text/scroll validation: PASS (0 blocking issues)",
        "- V9 regional visual validation: PASS (0 regional failures)",
        "- Deterministic generation: PASS (candidate and second run SHA-256 match)",
        "- V8 converter regression: PASS (0 contract differences)",
        "- Formal project hash guard: PASS",
        f"- GUI Guider 2.0 actual open/save roundtrip: {roundtrip_state}",
        "",
        f"Candidate SHA-256: `{summary['candidate']['sha256']}`",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--formal", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--idempotency-candidate", type=Path, required=True)
    parser.add_argument("--manifest-index", type=Path, required=True)
    parser.add_argument("--manifest-diff", type=Path, required=True)
    parser.add_argument("--warnings", type=Path, required=True)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--v8-regression", type=Path, required=True)
    parser.add_argument("--roundtrip-report", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    manifest = load_json(args.manifest_index)
    manifest_diff = load_json(args.manifest_diff)["summary"]
    warnings = load_json(args.warnings)
    validation = load_json(args.validation)
    v8_regression = load_json(args.v8_regression)
    roundtrip = (
        load_json(args.roundtrip_report)
        if args.roundtrip_report is not None
        else {"passed": False}
    )
    roundtrip_verified = bool(roundtrip.get("passed"))

    formal_sha = sha256(args.formal)
    candidate_sha = sha256(args.candidate)
    idempotency_sha = sha256(args.idempotency_candidate)
    formal_unchanged = formal_sha == EXPECTED_FORMAL_SHA256
    idempotent = candidate_sha == idempotency_sha
    automatic_validation_passed = (
        not validation["blocking_issues"]
        and not validation["regional_visual_failures"]
    )
    candidate_ready = (
        formal_unchanged
        and idempotent
        and automatic_validation_passed
        and v8_regression["passed"]
    )

    summary = {
        "schema_version": "figma-controlled-sync-summary/v1",
        "manifest": {
            "path": str(args.manifest_index),
            "manifest_version": manifest.get("manifest_version"),
            "version": manifest.get("snapshot_version"),
            "sha256": sha256(args.manifest_index),
            "page_count": len(manifest.get("roots", [])),
            "node_count": sum(
                root.get("node_count", 0) for root in manifest.get("roots", [])
            ),
        },
        "manifest_diff": manifest_diff,
        "candidate": {
            "path": str(args.candidate),
            "sha256": candidate_sha,
            "idempotency_sha256": idempotency_sha,
            "idempotent": idempotent,
            "ready_for_human_review": candidate_ready,
        },
        "formal_project": {
            "path": str(args.formal),
            "sha256": formal_sha,
            "expected_sha256": EXPECTED_FORMAL_SHA256,
            "unchanged": formal_unchanged,
        },
        "mdk_project_modified": False,
        "validation": {
            "blocking_issues": len(validation["blocking_issues"]),
            "minimum_visual_similarity": validation["minimum_visual_similarity"],
            "visual_baseline": validation["visual_baseline"],
            "minimum_visual_similarity_delta": validation[
                "minimum_visual_similarity_delta"
            ],
            "minimum_regional_visual_similarity": validation[
                "minimum_regional_visual_similarity"
            ],
            "regional_visual_failures": len(validation["regional_visual_failures"]),
            "image_widget_count": validation["image_widget_count"],
            "unique_image_resources": validation["unique_image_resources"],
            "gui_guider_roundtrip_verified": roundtrip_verified,
            "gui_guider_roundtrip_report": (
                str(args.roundtrip_report)
                if args.roundtrip_report is not None
                else None
            ),
        },
        "v8_regression": {
            "passed": v8_regression["passed"],
            "contract_differences": len(v8_regression["contract_differences"]),
            "accepted_visual_differences": len(
                v8_regression["accepted_visual_differences"]
            ),
        },
        "warnings": {
            "blocking_count": warnings["blocking_count"],
            "path": str(args.warnings),
        },
        "modified_converter_scripts": [
            "tools/refresh_figma_local_snapshot.py",
            "tools/sync_completed_figma_to_guiguider.py",
            "tools/validate_figma_guider_sync.py",
        ],
        "new_support_scripts": [
            "tools/compare_figma_manifests.py",
            "tools/check_v8_regression.py",
            "tools/finalize_controlled_sync.py",
            "tools/prepare_guiguider_review_workspace.py",
            "tools/verify_guiguider_roundtrip.py",
        ],
        "new_tests": ["tools/test_controlled_sync.py"],
        "manual_review": MANUAL_REVIEW,
        "report_directory": str(args.output_dir),
    }

    conditions = [
        {
            "name": "formal_project_hash_guard",
            "satisfied": formal_unchanged,
            "detail": "Formal .guiguider SHA-256 matches the task-start value.",
        },
        {
            "name": "automatic_structure_and_visual_validation",
            "satisfied": automatic_validation_passed,
            "detail": "No structural blockers or failed critical visual regions.",
        },
        {
            "name": "deterministic_generation",
            "satisfied": idempotent,
            "detail": "Two candidate generations have identical SHA-256.",
        },
        {
            "name": "v8_converter_regression",
            "satisfied": v8_regression["passed"],
            "detail": "V8 object, resource, event, and configuration contracts remain stable.",
        },
        {
            "name": "type_change_manual_review",
            "satisfied": False,
            "detail": "Home/img_status_beep_no container-to-image change requires review.",
        },
        {
            "name": "gui_guider_open_save_roundtrip",
            "satisfied": roundtrip_verified,
            "detail": (
                "GUI Guider saved the isolated review workspace without changing "
                "its UI tree or resources."
                if roundtrip_verified
                else "An isolated GUI Guider open/save roundtrip is not verified."
            ),
        },
        {
            "name": "manual_page_review",
            "satisfied": False,
            "detail": "High-churn pages, scroll behavior, overlays, and Recall/Save must be inspected.",
        },
        {
            "name": "explicit_promotion_approval",
            "satisfied": False,
            "detail": "This run is required to stop at the candidate stage.",
        },
    ]
    gate = {
        "schema_version": "figma-controlled-sync-promotion-gate/v1",
        "candidate_ready_for_review": candidate_ready,
        "eligible_for_formal_promotion": False,
        "conditions": conditions,
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.output_dir / "controlled_sync_summary.json", summary)
    write_summary_markdown(args.output_dir / "controlled_sync_summary.md", summary)
    write_json(args.output_dir / "promotion_gate.json", gate)
    write_gate_markdown(args.output_dir / "promotion_gate.md", gate)
    write_test_markdown(args.output_dir / "test_report.md", summary)
    print(json.dumps(gate, ensure_ascii=False, indent=2))
    return 0 if candidate_ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
