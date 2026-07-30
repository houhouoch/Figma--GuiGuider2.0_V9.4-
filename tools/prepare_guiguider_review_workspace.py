#!/usr/bin/env python3
"""Create an isolated GUI Guider workspace from a generated candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path, PureWindowsPath
from typing import Any


def iter_strings(value: Any):
    if isinstance(value, dict):
        for child in value.values():
            yield from iter_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_strings(child)
    elif isinstance(value, str):
        yield value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resource_paths(project: dict[str, Any]) -> list[Path]:
    paths: set[Path] = set()
    for value in iter_strings(project):
        normalized = value.replace("\\", "/")
        if normalized.startswith("resources/"):
            paths.add(Path(*PureWindowsPath(value).parts))
    for node in project.get("UI", {}).get("screen_list", []):
        for family in iter_text_families(node):
            paths.add(Path("resources") / "font" / family)
    return sorted(paths, key=lambda path: path.as_posix().lower())


def iter_text_families(value: Any):
    if isinstance(value, dict):
        family = value.get("text_family")
        if isinstance(family, str) and family:
            yield family
        for child in value.values():
            yield from iter_text_families(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_text_families(child)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--project-name", default="V9_CONTROLLED_REVIEW")
    args = parser.parse_args()

    candidate = args.candidate.resolve()
    source_root = args.source_root.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    project = json.loads(candidate.read_text(encoding="utf-8"))
    project_name = args.project_name
    project["projectId"] = "project-" + hashlib.sha256(
        f"{project_name}|{candidate}".encode("utf-8")
    ).hexdigest()[:16].upper()
    project["projectName"] = project_name
    project["projectPath"] = str(output_dir)
    project["description"] = (
        "Isolated review workspace generated from the controlled Figma V9 candidate."
    )

    referenced_resources = resource_paths(project)
    missing: list[str] = []
    copied: list[dict[str, str]] = []
    for relative_path in referenced_resources:
        source = source_root / relative_path
        destination = output_dir / relative_path
        if not source.is_file():
            missing.append(str(relative_path))
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied.append(
            {
                "path": str(relative_path),
                "sha256": sha256(destination),
            }
        )

    if missing:
        raise FileNotFoundError(
            "Missing candidate resources:\n" + "\n".join(missing)
        )

    project_file = output_dir / f"{project_name}.guiguider"
    project_file.write_text(
        json.dumps(project, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    report = {
        "schema_version": "guiguider-review-workspace/v1",
        "source_candidate": str(candidate),
        "source_candidate_sha256": sha256(candidate),
        "review_project": str(project_file),
        "review_project_sha256": sha256(project_file),
        "project_id": project["projectId"],
        "project_name": project["projectName"],
        "project_path": project["projectPath"],
        "resource_count": len(copied),
        "resources": copied,
    }
    report_path = output_dir / "review_workspace_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
