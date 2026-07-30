#!/usr/bin/env python3
"""Validate the distributable repository without third-party local assets."""

from __future__ import annotations

import json
import hashlib
import py_compile
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "project" / "guiguider_2.0.template.guiguider"
MANIFEST_INDEX = ROOT / "manifests" / "v9_all_20260729_context" / "index.json"
EXPECTED_IMAGES = 50
EXPECTED_FIGMA_ROOTS = 31
EXPECTED_GUI_ENTRIES = 34
EXPECTED_CHECKSUMS = 94


def fail(message: str, failures: list[str]) -> None:
    failures.append(message)
    print(f"ERROR: {message}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    failures: list[str] = []

    try:
        project = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"Cannot parse GUI Guider template: {exc}", failures)
        project = {}

    if project:
        if project.get("projectPath") != "__PROJECT_ROOT__":
            fail("Template projectPath must remain portable", failures)
        entries = len(project.get("UI", {}).get("screen_list", []))
        if entries != EXPECTED_GUI_ENTRIES:
            fail(
                f"Expected {EXPECTED_GUI_ENTRIES} GUI entries, found {entries}",
                failures,
            )

    images = list((ROOT / "project" / "resources" / "image").glob("*.png"))
    if len(images) != EXPECTED_IMAGES:
        fail(f"Expected {EXPECTED_IMAGES} images, found {len(images)}", failures)

    tracked_fonts = subprocess.run(
        ["git", "ls-files", "project/resources/font"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    forbidden_fonts = [
        path
        for path in tracked_fonts
        if Path(path).suffix.lower() in {".ttf", ".otf", ".woff", ".woff2", ".eot"}
    ]
    if forbidden_fonts:
        fail("Third-party font binaries must not be committed", failures)

    try:
        manifest = json.loads(MANIFEST_INDEX.read_text(encoding="utf-8"))
        roots = manifest.get("roots", [])
        if len(roots) != EXPECTED_FIGMA_ROOTS:
            fail(
                f"Expected {EXPECTED_FIGMA_ROOTS} Figma roots, found {len(roots)}",
                failures,
            )
        missing_screenshots = [
            root["screenshot"]
            for root in roots
            if not (ROOT / root["screenshot"]).is_file()
        ]
        if missing_screenshots:
            fail(
                f"Missing manifest screenshots: {len(missing_screenshots)}",
                failures,
            )
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"Cannot parse V9 manifest index: {exc}", failures)

    checksums_path = MANIFEST_INDEX.with_name("checksums.json")
    try:
        checksums = json.loads(checksums_path.read_text(encoding="utf-8"))
        files = checksums.get("files", {})
        if len(files) != EXPECTED_CHECKSUMS:
            fail(
                f"Expected {EXPECTED_CHECKSUMS} checksums, found {len(files)}",
                failures,
            )
        for relative_path, expected in files.items():
            path = ROOT / relative_path
            if not path.is_file():
                fail(f"Missing checksummed file: {relative_path}", failures)
            elif sha256(path) != expected:
                fail(f"Checksum mismatch: {relative_path}", failures)
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"Cannot validate manifest checksums: {exc}", failures)

    for forbidden in ("platform", "generated", "artifacts"):
        if (ROOT / forbidden).exists():
            fail(f"Forbidden distributable directory exists: {forbidden}", failures)

    required_skill_files = (
        ROOT / "skills" / "figma-to-guiguider-controlled-sync" / "SKILL.md",
        ROOT
        / "skills"
        / "figma-to-guiguider-controlled-sync"
        / "agents"
        / "openai.yaml",
        ROOT
        / "skills"
        / "figma-to-guiguider-controlled-sync"
        / "scripts"
        / "audit_guiguider_project.py",
    )
    for path in required_skill_files:
        if not path.is_file():
            fail(f"Missing Skill file: {path.relative_to(ROOT)}", failures)

    for path in list((ROOT / "tools").glob("*.py")) + list(
        (ROOT / "skills").rglob("*.py")
    ):
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            fail(f"Python syntax error in {path.relative_to(ROOT)}: {exc}", failures)

    oversized = [
        path
        for path in ROOT.rglob("*")
        if path.is_file()
        and ".git" not in path.parts
        and path.stat().st_size > 50 * 1024 * 1024
    ]
    if oversized:
        fail(
            "Files larger than 50 MiB: "
            + ", ".join(str(path.relative_to(ROOT)) for path in oversized),
            failures,
        )

    if failures:
        print(f"Repository validation failed: {len(failures)} issue(s)")
        return 1

    print("Repository validation passed")
    print(f"GUI Guider entries: {EXPECTED_GUI_ENTRIES}")
    print(f"Figma roots: {EXPECTED_FIGMA_ROOTS}")
    print(f"Project images: {EXPECTED_IMAGES}")
    print("External font binaries: excluded as intended")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
