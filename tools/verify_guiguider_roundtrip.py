#!/usr/bin/env python3
"""Verify that GUI Guider opened and saved an isolated review workspace safely."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


IDENTITY_FIELDS = {
    "projectId",
    "projectName",
    "projectPath",
    "description",
    "lastModified",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized_project(project: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in project.items()
        if key not in IDENTITY_FIELDS
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--review-project", type=Path, required=True)
    parser.add_argument("--workspace-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
    review = json.loads(args.review_project.read_text(encoding="utf-8"))
    workspace = json.loads(args.workspace_report.read_text(encoding="utf-8"))

    resources_missing: list[str] = []
    resources_changed: list[str] = []
    review_root = args.review_project.parent
    for resource in workspace["resources"]:
        path = review_root / resource["path"]
        if not path.is_file():
            resources_missing.append(resource["path"])
        elif sha256(path) != resource["sha256"]:
            resources_changed.append(resource["path"])

    before_sha = workspace["review_project_sha256"]
    after_sha = sha256(args.review_project)
    checks = {
        "project_identity_isolated": (
            review.get("projectId") == workspace["project_id"]
            and review.get("projectName") == workspace["project_name"]
            and review.get("projectPath") == workspace["project_path"]
        ),
        "gui_guider_saved_project": (
            before_sha != after_sha
            and review.get("lastModified") != candidate.get("lastModified")
        ),
        "project_configuration_preserved": (
            normalized_project(candidate) == normalized_project(review)
        ),
        "ui_tree_preserved": candidate.get("UI") == review.get("UI"),
        "resources_complete": not resources_missing,
        "resources_unchanged": not resources_changed,
    }
    passed = all(checks.values())
    report = {
        "schema_version": "guiguider-roundtrip-verification/v1",
        "passed": passed,
        "candidate": str(args.candidate.resolve()),
        "review_project": str(args.review_project.resolve()),
        "before_sha256": before_sha,
        "after_sha256": after_sha,
        "candidate_last_modified": candidate.get("lastModified"),
        "review_last_modified": review.get("lastModified"),
        "checks": checks,
        "resources_missing": resources_missing,
        "resources_changed": resources_changed,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
