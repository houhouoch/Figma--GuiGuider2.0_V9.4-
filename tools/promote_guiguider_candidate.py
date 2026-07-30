#!/usr/bin/env python3
"""Promote a validated GUI Guider candidate by replacing only the UI tree."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def iter_nodes(value: Any):
    if isinstance(value, dict):
        if value.get("type") and value.get("name"):
            yield value
        for child in value.values():
            yield from iter_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_nodes(child)


def referenced_resources(project: dict[str, Any]) -> list[Path]:
    resources: set[Path] = set()
    for node in iter_nodes(project.get("UI", {})):
        source = node.get("src")
        if isinstance(source, str) and source:
            resources.add(Path(source.replace("\\", "/")))
        for style in node.get("style", {}).values():
            if not isinstance(style, dict):
                continue
            family = style.get("text_family")
            if isinstance(family, str) and family:
                resources.add(Path("resources") / "font" / family)
    return sorted(resources, key=lambda path: path.as_posix().lower())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--formal", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--backup-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--approval-note", required=True)
    args = parser.parse_args()

    formal_path = args.formal.resolve()
    candidate_path = args.candidate.resolve()
    project_root = formal_path.parent
    formal = json.loads(formal_path.read_text(encoding="utf-8"))
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))

    identity_fields = ("projectId", "projectName", "projectPath")
    identity_mismatches = {
        field: [formal.get(field), candidate.get(field)]
        for field in identity_fields
        if formal.get(field) != candidate.get(field)
    }
    if identity_mismatches:
        raise ValueError(f"Candidate identity mismatch: {identity_mismatches}")

    missing_resources = [
        str(path)
        for path in referenced_resources(candidate)
        if not (project_root / path).is_file()
    ]
    if missing_resources:
        raise FileNotFoundError(
            "Missing formal project resources:\n" + "\n".join(missing_resources)
        )

    before_non_ui = dict(formal)
    before_non_ui["UI"] = None
    before_sha = sha256(formal_path)
    candidate_sha = sha256(candidate_path)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    args.backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = args.backup_dir / (
        f"{formal_path.stem}.before_v9_promotion_{timestamp}{formal_path.suffix}"
    )
    shutil.copy2(formal_path, backup_path)

    formal["UI"] = candidate["UI"]
    after_non_ui = dict(formal)
    after_non_ui["UI"] = None
    if canonical_sha256(before_non_ui) != canonical_sha256(after_non_ui):
        raise AssertionError("Non-UI formal project configuration changed")

    temporary_path = formal_path.with_suffix(formal_path.suffix + ".promoting")
    temporary_path.write_text(
        json.dumps(formal, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary_path, formal_path)

    report = {
        "schema_version": "guiguider-formal-promotion/v1",
        "approved": True,
        "approval_note": args.approval_note,
        "formal_project": str(formal_path),
        "candidate": str(candidate_path),
        "backup": str(backup_path.resolve()),
        "before_sha256": before_sha,
        "candidate_sha256": candidate_sha,
        "promoted_sha256": sha256(formal_path),
        "backup_sha256": sha256(backup_path),
        "non_ui_configuration_preserved": True,
        "formal_ui_matches_candidate": formal["UI"] == candidate["UI"],
        "resource_count": len(referenced_resources(candidate)),
        "missing_resources": missing_resources,
        "gui_guider_open_save_verified": False,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
