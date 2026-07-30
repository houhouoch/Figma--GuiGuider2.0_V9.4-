#!/usr/bin/env python3
"""Relocate a validated manifest snapshot into a self-contained public layout."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST_DIR = ROOT / "manifests" / "v9_all_20260729_context"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, payload: dict) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest-dir", type=Path, default=DEFAULT_MANIFEST_DIR)
    parser.add_argument(
        "--source-screenshots",
        type=Path,
        required=True,
        help="Directory containing the validated root screenshots.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest_dir = args.manifest_dir.resolve()
    source_screenshots = args.source_screenshots.resolve()
    index_path = manifest_dir / "index.json"
    checksums_path = manifest_dir / "checksums.json"
    screenshots_dir = manifest_dir / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["base_manifest"] = "v8_all_20260729_context/index.json"

    for root in index["roots"]:
        filename = f"{root['id'].replace(':', '_')}.png"
        source = source_screenshots / filename
        target = screenshots_dir / filename
        if not source.is_file():
            raise FileNotFoundError(source)
        shutil.copy2(source, target)
        root["screenshot"] = str(target.relative_to(ROOT)).replace("\\", "/")

    write_json(index_path, index)

    checksums = json.loads(checksums_path.read_text(encoding="utf-8"))
    relocated: dict[str, str] = {}
    old_manifest_prefix = "tools/manifests/v9_all_20260729_context/"
    old_screenshot_prefix = "artifacts/figma_reference_v9_all_20260729_context/"
    new_manifest_prefix = "manifests/v9_all_20260729_context/"
    new_screenshot_prefix = f"{new_manifest_prefix}screenshots/"

    for key, value in checksums["files"].items():
        if key.startswith(old_manifest_prefix):
            key = new_manifest_prefix + key[len(old_manifest_prefix) :]
        elif key.startswith(old_screenshot_prefix):
            key = new_screenshot_prefix + key[len(old_screenshot_prefix) :]
        relocated[key] = value

    relocated[f"{new_manifest_prefix}index.json"] = sha256(index_path)
    checksums["files"] = dict(sorted(relocated.items()))
    write_json(checksums_path, checksums)

    for relative_path, expected in checksums["files"].items():
        path = ROOT / relative_path
        if not path.is_file():
            raise FileNotFoundError(path)
        actual = sha256(path)
        if actual != expected:
            raise ValueError(f"Checksum mismatch: {relative_path}")

    print(f"Relocated {len(index['roots'])} screenshots")
    print(f"Verified {len(checksums['files'])} checksums")


if __name__ == "__main__":
    main()
