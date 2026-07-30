#!/usr/bin/env python3
"""Fix screen_config switch knob geometry and checked-state feedback.

Only four switch styles are changed:
* make each LV_PART_KNOB circle using its effective knob diameter;
* make LV_PART_INDICATOR bright gold while LV_STATE_CHECKED.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterator


ROOT = Path(__file__).resolve().parents[1]
KNOB = "LV_PART_KNOB|LV_STATE_DEFAULT"
CHECKED_INDICATOR = "LV_PART_INDICATOR|LV_STATE_CHECKED"
ON_COLOR = "#d6a340"
TARGETS = {
    "sw_config_rise_tracking_slew": 9,
    "sw_config_label_res": 9,
    "sw_config_tracking_limits": 8,
    "sw_config_type_tracking_limits": 8,
}
DEFAULT_INPUT = ROOT / "guiguider_2.0.guiguider"
DEFAULT_OUTPUT = (
    ROOT
    / "tools"
    / "artifacts"
    / "config_switch_style_fix_20260727"
    / "guiguider_2.0.config_switch_candidate.guiguider"
)
DEFAULT_REPORT = (
    ROOT
    / "tools"
    / "artifacts"
    / "config_switch_style_fix_20260727"
    / "config_switch_style_report.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-project", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-project", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as stream:
        return json.load(stream)


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def walk(nodes: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    for node in nodes:
        yield node
        children = node.get("children")
        if isinstance(children, list):
            yield from walk(children)


def find_targets(project: dict[str, Any]) -> dict[str, dict[str, Any]]:
    matches = {
        node["name"]: node
        for node in walk(project["UI"]["screen_list"])
        if node.get("name") in TARGETS
    }
    assert set(matches) == set(TARGETS)
    for name, node in matches.items():
        assert node.get("type") == "switch", f"{name} is not a switch"
        assert KNOB in node["style"]
        assert CHECKED_INDICATOR in node["style"]
        assert not node.get("children"), f"{name} unexpectedly has children"
    return matches


def masked_project(project: dict[str, Any]) -> dict[str, Any]:
    masked = deepcopy(project)
    for node in find_targets(masked).values():
        node["style"][KNOB]["radius"] = "<MASKED>"
        node["style"][CHECKED_INDICATOR]["bg_color"] = "<MASKED>"
        node["style"][CHECKED_INDICATOR]["bg_opa"] = "<MASKED>"
    return masked


def main() -> None:
    args = parse_args()
    before = load_json(args.input_project)
    before_targets = find_targets(before)
    before_masked_hash = canonical_hash(masked_project(before))
    before_styles = {
        name: {
            "knob_radius": node["style"][KNOB].get("radius"),
            "checked_bg_color": node["style"][CHECKED_INDICATOR].get(
                "bg_color"
            ),
            "checked_bg_opa": node["style"][CHECKED_INDICATOR].get("bg_opa"),
        }
        for name, node in before_targets.items()
    }

    after = deepcopy(before)
    after_targets = find_targets(after)
    for name, radius in TARGETS.items():
        node = after_targets[name]
        node["style"][KNOB]["radius"] = radius
        node["style"][CHECKED_INDICATOR]["bg_color"] = ON_COLOR
        node["style"][CHECKED_INDICATOR]["bg_opa"] = 255

    assert canonical_hash(masked_project(after)) == before_masked_hash, (
        "Unexpected project mutation outside the four config switch styles"
    )
    screens = [
        node
        for node in after["UI"]["screen_list"]
        if node.get("type") == "screen"
    ]
    assert len(screens) == 15
    assert sum(bool(screen.get("default_screen")) for screen in screens) == 1
    assert next(
        screen for screen in screens if screen.get("default_screen")
    ).get("figma_id") == "71:3"

    # Second pass is identical.
    repeat = deepcopy(after)
    for name, radius in TARGETS.items():
        node = find_targets(repeat)[name]
        node["style"][KNOB]["radius"] = radius
        node["style"][CHECKED_INDICATOR]["bg_color"] = ON_COLOR
        node["style"][CHECKED_INDICATOR]["bg_opa"] = 255
    assert repeat == after

    write_json(args.output_project, after)
    after_styles = {
        name: {
            "knob_radius": node["style"][KNOB].get("radius"),
            "checked_bg_color": node["style"][CHECKED_INDICATOR].get(
                "bg_color"
            ),
            "checked_bg_opa": node["style"][CHECKED_INDICATOR].get("bg_opa"),
        }
        for name, node in after_targets.items()
    }
    report = {
        "input_project": str(args.input_project),
        "output_project": str(args.output_project),
        "input_sha256": file_hash(args.input_project),
        "output_sha256": file_hash(args.output_project),
        "on_color": ON_COLOR,
        "switches": {
            name: {
                "before": before_styles[name],
                "after": after_styles[name],
            }
            for name in TARGETS
        },
        "validation": {
            "only_four_config_switch_styles_changed": True,
            "manual_project_edits_preserved": True,
            "circular_knobs": True,
            "bright_checked_indicator": True,
            "screen_count": 15,
            "default_screen": "Home",
            "second_pass_identical": True,
        },
    }
    write_json(args.report, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
