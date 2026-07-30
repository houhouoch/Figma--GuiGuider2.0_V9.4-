#!/usr/bin/env python3
"""Read-only integrity audit for a GUI Guider project and generated fonts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


FONT_SYMBOL = re.compile(r"\blv_font_[A-Za-z0-9_]+\b")
FONT_SUFFIX = re.compile(r"^(.*?)(?:_\d+)+$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--generated-dir", type=Path)
    parser.add_argument("--json-report", type=Path)
    return parser.parse_args()


def walk(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def iter_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from iter_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_strings(child)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve_explicit_resource(project_dir: Path, raw: str) -> Path | None:
    normalized = raw.replace("\\", "/")
    marker = "resources/"
    pos = normalized.lower().find(marker)
    if pos >= 0:
        return project_dir / Path(normalized[pos:])
    return None


def symbols_from_files(files: Iterable[Path]) -> set[str]:
    result: set[str] = set()
    for path in files:
        if path.is_file():
            result.update(FONT_SYMBOL.findall(path.read_text(encoding="utf-8", errors="ignore")))
    return result


def audit_generated_fonts(generated_dir: Path) -> dict[str, Any]:
    screens = generated_dir / "screens"
    fonts = generated_dir / "assets" / "fonts"
    header = fonts / "gg_font.h"
    refs = symbols_from_files(screens.glob("*.c")) if screens.is_dir() else set()
    declarations = symbols_from_files([header]) if header.is_file() else set()
    all_definitions = symbols_from_files(fonts.glob("lv_font_*.c")) if fonts.is_dir() else set()

    family_prefixes: set[str] = set()
    for symbol in declarations:
        match = FONT_SUFFIX.match(symbol)
        if match:
            family_prefixes.add(match.group(1))

    custom_refs = {
        symbol
        for symbol in refs
        if any(symbol.startswith(prefix + "_") for prefix in family_prefixes)
    }
    definitions = {
        symbol
        for symbol in all_definitions
        if any(symbol.startswith(prefix + "_") for prefix in family_prefixes)
    }
    missing_declarations = sorted(custom_refs - declarations)
    missing_definitions = sorted(custom_refs - definitions)
    declaration_without_definition = sorted(declarations - definitions)
    definition_without_declaration = sorted(definitions - declarations)

    return {
        "reference_count": len(custom_refs),
        "declaration_count": len(declarations),
        "definition_count": len(definitions),
        "missing_declarations": missing_declarations,
        "missing_definitions": missing_definitions,
        "declaration_without_definition": declaration_without_definition,
        "definition_without_declaration": definition_without_declaration,
    }


def main() -> int:
    args = parse_args()
    project_path = args.project.resolve()
    project_dir = project_path.parent

    if not project_path.is_file():
        print(f"ERROR: project not found: {project_path}", file=sys.stderr)
        return 2

    try:
        project = json.loads(project_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: invalid GUI Guider JSON: {exc}", file=sys.stderr)
        return 2

    nodes = list(walk(project.get("UI", {})))
    object_ids = [str(node["id"]) for node in nodes if node.get("id")]
    figma_ids = [str(node["figma_id"]) for node in nodes if node.get("figma_id")]
    duplicate_object_ids = sorted(key for key, count in Counter(object_ids).items() if count > 1)
    duplicate_figma_ids = sorted(key for key, count in Counter(figma_ids).items() if count > 1)

    resource_paths: dict[str, Path] = {}
    for value in iter_strings(project):
        path = resolve_explicit_resource(project_dir, value)
        if path is not None:
            resource_paths[str(path)] = path
    for node in nodes:
        for key, value in node.items():
            if key == "text_family" and isinstance(value, str) and value:
                path = project_dir / "resources" / "font" / Path(value).name
                resource_paths[str(path)] = path
    missing_resources = sorted(path for path, value in resource_paths.items() if not value.is_file())

    generated_report: dict[str, Any] | None = None
    if args.generated_dir:
        generated_report = audit_generated_fonts(args.generated_dir.resolve())

    blockers: list[str] = []
    if duplicate_object_ids:
        blockers.append("duplicate_object_ids")
    if duplicate_figma_ids:
        blockers.append("duplicate_figma_ids")
    if missing_resources:
        blockers.append("missing_resources")
    if generated_report and any(
        generated_report[key]
        for key in (
            "missing_declarations",
            "missing_definitions",
            "declaration_without_definition",
            "definition_without_declaration",
        )
    ):
        blockers.append("generated_font_contract")

    report = {
        "schema": "guiguider-readonly-audit/v1",
        "project": str(project_path),
        "sha256": sha256(project_path),
        "project_name": project.get("projectName"),
        "screen_count": len(project.get("UI", {}).get("screen_list", [])),
        "object_count": len(object_ids),
        "figma_id_count": len(figma_ids),
        "duplicate_object_ids": duplicate_object_ids,
        "duplicate_figma_ids": duplicate_figma_ids,
        "resource_count": len(resource_paths),
        "missing_resources": missing_resources,
        "generated_fonts": generated_report,
        "blockers": blockers,
        "passed": not blockers,
    }

    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.json_report:
        args.json_report.parent.mkdir(parents=True, exist_ok=True)
        args.json_report.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
