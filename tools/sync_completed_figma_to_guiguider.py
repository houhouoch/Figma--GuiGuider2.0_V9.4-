#!/usr/bin/env python3
"""Safely sync the complete current Figma design into GUI Guider 2.0.

The input is the read-only Figma MCP evidence stored in
tools/manifests/v7_all_20260728.  This script never consumes plugin exports.
It preserves the current non-screen project configuration, rebuilds the
explicitly managed Figma roots, writes a candidate project, and validates the
result before it can be promoted to the formal .guiguider file.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import math
import os
import re
import shutil
import struct
import urllib.request
import xml.etree.ElementTree as ET
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = ROOT / "project" / "guiguider_2.0.guiguider"
DEFAULT_INDEX = (
    ROOT / "manifests" / "v9_all_20260729_context" / "index.json"
)
DEFAULT_OUTPUT = (
    ROOT
    / "artifacts"
    / "candidates"
    / "guiguider_2.0.candidate.guiguider"
)
DEFAULT_REPORT = DEFAULT_OUTPUT.with_name("conversion_report.json")
DEFAULT_SEMANTICS = DEFAULT_OUTPUT.with_name("semantic_overrides.json")
MAIN_STYLE = "LV_PART_MAIN|LV_STATE_DEFAULT"
MANAGED_ROOTS = {
    "130:2",
    "71:3",
    "130:6",
    "243:234",
    "243:280",
    "243:328",
    "243:331",
    "243:361",
    "243:433",
    "243:524",
    "243:609",
    "243:187",
    "243:135",
    "217:2",
    "199:2",
    "365:2",
    "365:5",
    "366:2",
    "366:183",
    "366:218",
    "366:291",
    "366:347",
    "366:404",
    "366:492",
    "366:495",
    "366:557",
    "366:562",
    "366:579",
    "366:683",
    "366:777",
    "366:841",
}
PRESERVE_ROOTS: set[str] = set()
EXPECTED_DESIGN_ROOTS = set(MANAGED_ROOTS)
LOCAL_ASSET_ROOT = Path(
    os.environ.get(
        "FIGMA_GUI_GUIDER_ASSET_ROOT",
        ROOT / "external-assets" / "source",
    )
)
LOCAL_ASSET_BY_NODE_NAME = {
    # Home and shared status images.
    "img_logo": Path("UNIT.png"),
    "img_menu": Path("home") / "Icons_Menu.png",
    "img_status_beep": Path("home") / "beep.png",
    "img_status_beep_no": Path("home") / "beep_no.png",
    "img_status_lock": Path("home") / "suo.png",
    "img_status_usb": Path("home") / "usb3.png",
    "img_status_protect": Path("home") / "img_status_protect.png",
    "img_arb_mode": Path("Arb") / "Sine.png",
    # HOME_MENU navigation images.  The 211 px menu_alone variants are the
    # reviewed transparent production assets; the larger 图片原件 files are
    # retained as source artwork but are unnecessary for a 70 px GUI target.
    "img_menu_back": Path("menu") / "back2.png",
    "img_menu_home": Path("menu") / "home.png",
    "img_menu_config": Path("menu_alone") / "config_alone.png",
    "img_menu_protect": Path("menu_alone") / "protect_alone.png",
    "img_menu_measure": Path("menu_alone") / "measure_alone.png",
    "img_menu_trigger": Path("menu_alone") / "trigger_alone_2.png",
    "img_menu_recall": Path("menu_alone") / "recall_alone.png",
    "img_menu_save": Path("menu_alone") / "save_alone.png",
    "img_menu_meter": Path("menu_alone") / "meter2.png",
    "img_menu_recorder": Path("menu_alone") / "recoder_alone.png",
    "img_menu_function": Path("menu_alone") / "Function_alone.png",
    "img_menu_delays": Path("menu_alone") / "delays_alone.png",
    "img_menu_coupling": Path("menu_alone") / "coupling_alone.png",
    "img_menu_group": Path("menu_alone") / "group_alone.png",
    "img_menu_general": Path("menu_alone") / "general_alone.png",
    "img_menu_digital_io": Path("menu_alone") / "Digital_io_alone.png",
    "img_menu_preference": Path("menu_alone") / "perfect_alone.png",
    "img_menu_log": Path("menu_alone") / "log_alone.png",
    "img_menu_admin": Path("menu_alone") / "admin_alone.png",
    "img_menu_communication": Path("menu_alone")
    / "communication_alone.png",
    "img_menu_info": Path("menu_alone") / "info_alone.png",
    "img_menu_energy": Path("menu_alone") / "energy_alone.png",
    "img_menu_date": Path("menu_alone") / "date_alone.png",
    # Function-page artwork.
    "img_list": Path("高级功能-统一色差") / "List.png",
    "img_fixed": Path("高级功能-统一色差") / "Fixed.png",
    "img_arb": Path("高级功能-统一色差") / "Arb.png",
    "img_sequence": Path("高级功能-统一色差") / "Sequence.png",
    "img_cd_arb": Path("高级功能-统一色差") / "CD_Arb.png",
    "img_sine_sweep": Path("高级功能-统一色差") / "Sine_Aweep.png",
    "img_bemulator": Path("高级功能-统一色差") / "BEmulator.png",
    "img_bdischarge": Path("高级功能-统一色差") / "BDischarge.png",
    "img_bcharge": Path("高级功能-统一色差") / "BCharge.png",
    # File/actions.
    "img_list_file": Path("file.png"),
    "img_arb_file": Path("file.png"),
    "img_clear_icon": Path("trash.png"),
}
FONT_FILES = [
    ROOT / "resources" / "font" / "AlibabaPuHuiTi2.0.ttf",
]
HIDDEN = "LV_OBJ_FLAG_HIDDEN"
SCROLLABLE = "LV_OBJ_FLAG_SCROLLABLE"
SCREEN_HEIGHT = 240
SEMANTIC_VISIBILITY = {
    # Overlapping editor states must not be emitted as simultaneously visible.
    "71:3": {
        "525:2": True,    # cont_list
        "525:35": False,  # cont_Arb
        "72:8": False,    # panel_setpoints
    },
    "366:683": {
        "366:684": False,  # cont_Sine
        "366:739": True,   # cont_user_defined
    },
    "366:777": {
        "366:778": True,   # screen_file content root
        "366:779": False,  # save-name/keyboard state
        "366:792": True,   # browser state
    },
    "366:291": {
        "366:292": True,   # Menu_Admin content root
        "366:304": False,  # Init tab content
        "366:311": False,  # Factory tab content
        "366:320": True,   # Firmware tab content
    },
    "366:562": {
        # The current Figma state is checked for all four reset categories.
        # Keep the unchecked boxes underneath for runtime state changes, while
        # showing the enable glyphs by default to match the design.
        "592:4": True,
        "592:5": True,
        "592:6": True,
        "592:7": True,
    },
}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as stream:
        return json.load(stream)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def digest(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def file_digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def stable_id(figma_id: str) -> str:
    token = base64.b32encode(
        hashlib.sha1(figma_id.encode("utf-8")).digest()[:8]
    ).decode("ascii").rstrip("=")
    return f"figma_{token}"


def round_px(value: str | float | int | None, default: int = 0) -> int:
    if value is None:
        return default
    return int(math.floor(float(value) + 0.5))


def sanitize(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_]+", "_", value.strip())
    value = re.sub(r"_+", "_", value).strip("_")
    if not value:
        return "node"
    if value[0].isdigit():
        value = f"n_{value}"
    return value


def color_rgba(value: str) -> tuple[str, int]:
    value = value.strip()
    if value.startswith("#"):
        raw = value[1:]
        if len(raw) == 3:
            raw = "".join(char * 2 for char in raw)
        if len(raw) == 8:
            return f"#{raw[:6].lower()}", round(int(raw[6:8], 16))
        return f"#{raw[:6].lower()}", 255
    match = re.fullmatch(
        r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*([0-9.]+))?\s*\)",
        value,
    )
    if match:
        red, green, blue = (int(match.group(index)) for index in range(1, 4))
        alpha = float(match.group(4) or 1)
        return f"#{red:02x}{green:02x}{blue:02x}", max(
            0, min(255, round(alpha * 255))
        )
    return "#000000", 0


def class_value(classes: str, prefix: str) -> str | None:
    match = re.search(re.escape(prefix) + r"\[([^\]]+)\]", classes)
    return match.group(1) if match else None


def parse_color_class(classes: str, prefix: str) -> tuple[str, int] | None:
    # A class family can contain both a dimension and a color, e.g.
    # ``border-[1.5px] border-[rgba(217,150,19,0.71)]``.  Selecting the first
    # value turns the border black because ``1.5px`` is not a color.
    for match in re.finditer(re.escape(prefix) + r"\[([^\]]+)\]", classes):
        value = match.group(1)
        if value.startswith("#") or value.startswith("rgb"):
            return color_rgba(value)
    return None


def parse_dimension_class(classes: str, prefix: str) -> float | None:
    # A class family can contain both a color and a dimension, e.g.
    # ``text-[#d6d6cf] text-[16px]``.  Scan all matches rather than stopping
    # at the first (color) class.
    for match in re.finditer(re.escape(prefix) + r"\[([^\]]+)\]", classes):
        value = match.group(1)
        if not value.endswith("px"):
            continue
        try:
            return float(value[:-2])
        except ValueError:
            continue
    return None


def extract_sections(raw: str) -> tuple[dict[str, Any], str, str, dict[str, Any]]:
    source_text = raw.split("=== SOURCE ===\n", 1)[1].split(
        "\n=== METADATA_XML ===", 1
    )[0]
    metadata = raw.split("=== METADATA_XML ===\n", 1)[1].split(
        "\n=== DESIGN_CONTEXT_TSX ===", 1
    )[0]
    tsx = raw.split("=== DESIGN_CONTEXT_TSX ===\n", 1)[1].split(
        "\n=== SCREENSHOT_JSON ===", 1
    )[0]
    screenshot_text = raw.split("=== SCREENSHOT_JSON ===\n", 1)[1]
    return (
        json.loads(source_text),
        metadata,
        tsx,
        json.loads(screenshot_text),
    )


def opening_tags(tsx: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for match in re.finditer(r"<(?:div|p|span|button|img|svg)\b[^>]*>", tsx):
        tag = match.group(0)
        node_id = re.search(r'data-node-id="([^"]+)"', tag)
        if node_id:
            result[node_id.group(1)] = tag
    return result


def tag_classes(tag: str) -> str:
    match = re.search(r'className="([^"]*)"', tag)
    return match.group(1) if match else ""


def text_contents(tsx: str) -> dict[str, str]:
    result: dict[str, str] = {}
    patterns = [
        # Older context format: the Figma ID is attached to the <p>.
        re.compile(
            r"<p\b(?=[^>]*\bdata-node-id=\"([^\"]+)\")[^>]*>(.*?)</p>",
            re.DOTALL,
        ),
        # Current context format: the ID is attached to the text wrapper and
        # the immediate child <p> contains the actual characters.
        re.compile(
            r"<(?:div|span)\b(?=[^>]*\bdata-node-id=\"([^\"]+)\")[^>]*>"
            r"\s*<p\b[^>]*>(.*?)</p>",
            re.DOTALL,
        ),
    ]
    for pattern in patterns:
        for match in pattern.finditer(tsx):
            inner = match.group(2)
            inner = re.sub(r"\{`(.*?)`\}", lambda item: item.group(1), inner, flags=re.S)
            inner = re.sub(r"\{\"(.*?)\"\}", lambda item: item.group(1), inner, flags=re.S)
            inner = re.sub(r"<[^>]+>", "", inner)
            inner = html.unescape(inner)
            inner = re.sub(r"\s+", " ", inner).strip()
            result[match.group(1)] = inner
    return result


def asset_constants(tsx: str) -> dict[str, str]:
    return {
        match.group(1): match.group(2)
        for match in re.finditer(r'const\s+(\w+)\s*=\s*"([^"]+)";', tsx)
    }


def direct_assets(tsx: str, tags: dict[str, str]) -> dict[str, str]:
    constants = asset_constants(tsx)
    positions: list[tuple[int, str, int]] = []
    for node_id, tag in tags.items():
        position = tsx.find(tag)
        if position >= 0:
            positions.append((position, node_id, position + len(tag)))
    positions.sort()
    result: dict[str, str] = {}
    for index, (position, node_id, content_start) in enumerate(positions):
        next_position = (
            positions[index + 1][0] if index + 1 < len(positions) else len(tsx)
        )
        close_position = tsx.find("</", content_start, next_position)
        segment_end = close_position if close_position >= 0 else next_position
        segment = tsx[content_start:segment_end]
        reference = re.search(r"src=\{(\w+)\}", segment)
        if reference and reference.group(1) in constants:
            result[node_id] = constants[reference.group(1)]
    return result


@dataclass
class SourceNode:
    id: str
    name: str
    tag: str
    x: float
    y: float
    width: float
    height: float
    hidden: bool = False
    opacity: int = 255
    clips_content: bool = False
    classes: str = ""
    text: str | None = None
    font_size: float | None = None
    font_family: str | None = None
    font_style: str | None = None
    text_align: str | None = None
    line_height: float | None = None
    fill: tuple[str, int] | None = None
    stroke: tuple[str, int] | None = None
    stroke_width: float = 0
    corner_radius: float = 0
    image_hash: str | None = None
    asset_url: str | None = None
    parent: "SourceNode | None" = None
    children: list["SourceNode"] = field(default_factory=list)


def parse_source_tree(metadata: str, tsx: str) -> SourceNode:
    element = ET.fromstring(metadata)
    tags = opening_tags(tsx)
    texts = text_contents(tsx)
    assets = direct_assets(tsx, tags)

    def convert(xml_node: ET.Element, parent: SourceNode | None) -> SourceNode:
        node_id = xml_node.attrib["id"]
        classes = tag_classes(tags.get(node_id, ""))
        node = SourceNode(
            id=node_id,
            name=xml_node.attrib.get("name", ""),
            tag=xml_node.tag.lower(),
            x=float(xml_node.attrib.get("x", 0)),
            y=float(xml_node.attrib.get("y", 0)),
            width=float(xml_node.attrib.get("width", 1)),
            height=float(xml_node.attrib.get("height", 1)),
            hidden=xml_node.attrib.get("hidden", "false").lower() == "true",
            opacity=0
            if xml_node.attrib.get("hidden", "false").lower() == "true"
            else 255,
            classes=classes,
            text=texts.get(node_id),
            asset_url=assets.get(node_id),
            parent=parent,
        )
        node.children = [convert(child, node) for child in list(xml_node)]
        return node

    return convert(element, None)


def parse_compact_tree(
    directory: Path,
    legacy_asset_urls: dict[str, str],
) -> SourceNode:
    exact = directory / "manifest.json"
    paths = [exact] if exact.exists() else sorted(directory.glob("manifest_[0-9]*_[0-9]*.json"))
    if not paths:
        raise AssertionError(f"No compact manifest found in {directory}")
    payloads = [load_json(path) for path in paths]
    root_id = payloads[0]["rootId"]
    total = payloads[0]["total"]
    rows: list[dict[str, Any]] = []
    for payload in payloads:
        assert payload["schema"] == "figma-compact-manifest/v1"
        assert payload["rootId"] == root_id
        assert payload["total"] == total
        rows.extend(payload["nodes"])
    assert len(rows) == total, f"Compact manifest is incomplete for {root_id}"
    assert len({row["id"] for row in rows}) == total

    nodes: dict[str, SourceNode] = {}
    orders: dict[str, int] = {}
    parent_ids: dict[str, str | None] = {}
    for row in rows:
        text = row.get("t") or {}
        fill = tuple(row["f"]) if row.get("f") else None
        stroke = tuple(row["s"]) if row.get("s") else None
        node = SourceNode(
            id=row["id"],
            name=row.get("n", ""),
            tag=row.get("ty", "FRAME").lower(),
            x=float(row.get("x", 0)),
            y=float(row.get("y", 0)),
            width=float(row.get("w", 1)),
            height=float(row.get("h", 1)),
            hidden=not bool(row.get("v", True)),
            opacity=int(row.get("op", 255)),
            clips_content=bool(row.get("clip", False)),
            text=text.get("c"),
            font_size=text.get("fs"),
            font_family=text.get("ff"),
            font_style=text.get("fy"),
            text_align=text.get("a"),
            line_height=text.get("lh"),
            fill=fill,  # type: ignore[arg-type]
            stroke=stroke,  # type: ignore[arg-type]
            stroke_width=float(row.get("sw", 0) or 0),
            corner_radius=float(row.get("r", 0) or 0),
            image_hash=row.get("img"),
            asset_url=legacy_asset_urls.get(row["id"]),
        )
        nodes[node.id] = node
        orders[node.id] = int(row.get("o", 0))
        parent_ids[node.id] = row.get("p")
    roots = [node for node in nodes.values() if parent_ids[node.id] is None]
    assert len(roots) == 1 and roots[0].id == root_id
    for node in nodes.values():
        parent_id = parent_ids[node.id]
        if parent_id is None:
            continue
        parent = nodes[parent_id]
        node.parent = parent
        parent.children.append(node)
    for node in nodes.values():
        node.children.sort(key=lambda child: orders[child.id])
    return roots[0]


def iter_source(node: SourceNode) -> Iterator[SourceNode]:
    yield node
    for child in node.children:
        yield from iter_source(child)


def legacy_asset_urls(spec: dict[str, Any]) -> dict[str, str]:
    legacy = (
        ROOT
        / "tools"
        / "manifests"
        / "v4_local_raw_20260727"
        / spec["directory"]
        / "raw_context.txt"
    )
    if not legacy.exists():
        return {}
    _, _, tsx, _ = extract_sections(legacy.read_text(encoding="utf-8"))
    return direct_assets(tsx, opening_tags(tsx))


def iter_objects(nodes: Iterable[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    for node in nodes:
        yield node
        yield from iter_objects(node.get("children", []))


class NameAllocator:
    def __init__(
        self,
        reserved: set[str],
        preferred_owners: dict[str, str] | None = None,
    ) -> None:
        self.used = set(reserved)
        self.preferred_owners = preferred_owners or {}

    def allocate(self, candidate: str, figma_id: str) -> str:
        candidate = sanitize(candidate)
        preferred_owner = self.preferred_owners.get(candidate)
        if candidate not in self.used and preferred_owner in {None, figma_id}:
            self.used.add(candidate)
            return candidate
        suffix = figma_id.replace(":", "_")
        candidate = f"{candidate}_{suffix}"
        counter = 2
        while candidate in self.used:
            candidate = f"{candidate}_{counter}"
            counter += 1
        self.used.add(candidate)
        return candidate


def base_visual_style(node: SourceNode) -> dict[str, Any]:
    classes = node.classes
    background = node.fill or parse_color_class(classes, "bg-")
    border = node.stroke or parse_color_class(classes, "border-")
    # Figma exposes a default strokeWeight (normally 1) even when a node has no
    # visible strokes.  Treating that default as an actual border creates a
    # spurious outline around every transparent text wrapper in GUI Guider.
    # A Figma stroke width is meaningful only when a stroke paint is present.
    border_width = node.stroke_width if border is not None else 0
    if border_width == 0:
        if re.search(r"(?:^|\s)border(?:\s|$)", classes):
            border_width = 1
        explicit_border = parse_dimension_class(classes, "border-")
        if explicit_border is not None:
            border_width = explicit_border
        if "border-0" in classes:
            border_width = 0
    radius = node.corner_radius or parse_dimension_class(classes, "rounded-") or 0
    if "rounded-full" in classes and node.corner_radius == 0:
        radius = min(node.width, node.height) / 2
    opacity = 0 if node.hidden else node.opacity
    if "opacity-0" in classes:
        opacity = 0
    style: dict[str, Any] = {
        "part": "LV_PART_MAIN",
        "state": "LV_STATE_DEFAULT",
        "opa": opacity,
        "radius": max(0, round_px(radius)),
        "clip_corner": 1,
        "outline_width": 0,
        "outline_opa": 0,
        "pad_left": 0,
        "pad_right": 0,
        "pad_top": 0,
        "pad_bottom": 0,
        "bg_color": (background or ("#000000", 0))[0],
        "bg_opa": (background or ("#000000", 0))[1],
        "border_width": max(0, round_px(border_width)),
        "border_opa": (border or ("#000000", 0))[1] if border_width else 0,
    }
    if border_width:
        style["border_color"] = (border or ("#786e57", 255))[0]
        if style["border_opa"] == 0:
            style["border_opa"] = 255
    return {MAIN_STYLE: style}


def text_family(node: SourceNode) -> str:
    # The current Figma file intentionally uses Alibaba PuHuiTi 2.0
    # (55 Regular) for every text node.  GUI Guider stores the selected custom
    # font using its resource filename, so use the exact available resource
    # key instead of falling back to Inter or the removed 1.0 filename.
    return "AlibabaPuHuiTi2.0.ttf"


def label_style(node: SourceNode) -> dict[str, Any]:
    classes = node.classes
    color = node.fill or parse_color_class(classes, "text-") or ("#d6d6cf", 255)
    font_size = node.font_size or parse_dimension_class(classes, "text-") or 18
    align = "LV_TEXT_ALIGN_LEFT"
    source_align = (node.text_align or "").upper()
    if source_align == "CENTER" or "text-center" in classes:
        align = "LV_TEXT_ALIGN_CENTER"
    elif source_align == "RIGHT" or "text-right" in classes:
        align = "LV_TEXT_ALIGN_RIGHT"
    return {
        MAIN_STYLE: {
            "part": "LV_PART_MAIN",
            "state": "LV_STATE_DEFAULT",
            "opa": 0 if node.hidden else 255,
            "border_width": 0,
            "border_opa": 0,
            "outline_width": 0,
            "outline_opa": 0,
            "text_color": color[0],
            "text_opa": color[1],
            "text_size": max(1, round_px(font_size)),
            "text_family": text_family(node),
            "text_align": align,
            # Large Home readouts need LVGL baseline compensation even when
            # the same TTF and point size are used.  Keep ordinary labels at
            # zero so their Figma boxes remain authoritative.
            "pad_top": -round_px(font_size / 4) if font_size >= 80 else 0,
        }
    }


def rendered_text_metrics(text: str, size: int) -> tuple[int | None, int]:
    try:
        from PIL import ImageFont

        font = ImageFont.truetype(
            str(ROOT / "resources" / "font" / "AlibabaPuHuiTi2.0.ttf"),
            size,
        )
        ascent, descent = font.getmetrics()
        return math.ceil(font.getlength(text)), math.ceil(ascent + descent)
    except (ImportError, OSError):
        return None, max(1, math.ceil(size * 1.45))


def switch_style(node: SourceNode, knob: SourceNode | None) -> dict[str, Any]:
    track = base_visual_style(node)[MAIN_STYLE]
    height = max(1, round_px(node.height))
    radius = height // 2
    track.update({"radius": radius, "anim_duration": 0})
    if track["bg_opa"] == 0:
        track.update({"bg_color": "#0a0a0a", "bg_opa": 255})
    if track["border_width"] == 0:
        track.update(
            {
                "border_color": "#4d422e",
                "border_opa": 255,
                "border_width": 1,
            }
        )
    indicator_default = {
        "part": "LV_PART_INDICATOR",
        "state": "LV_STATE_DEFAULT",
        "opa": 255,
        "radius": radius,
        "bg_color": "#0a0a0a",
        "bg_opa": 0,
        "border_width": 0,
        "border_opa": 0,
        "outline_width": 0,
        "outline_opa": 0,
    }
    indicator_checked = deepcopy(indicator_default)
    indicator_checked.update(
        {
            "state": "LV_STATE_CHECKED",
            "bg_color": "#d6a340",
            "bg_opa": 255,
        }
    )
    knob_size = round_px(knob.width if knob else 18)
    knob_x = max(0, round_px(knob.x if knob else 5))
    knob_y = max(0, round_px(knob.y if knob else (node.height - knob_size) / 2))
    knob_style = (
        base_visual_style(knob)[MAIN_STYLE]
        if knob
        else {
            "part": "LV_PART_MAIN",
            "state": "LV_STATE_DEFAULT",
            "opa": 255,
            "radius": knob_size // 2,
            "clip_corner": 1,
            "bg_color": "#bab096",
            "bg_opa": 255,
            "border_width": 0,
            "border_opa": 0,
            "outline_width": 0,
            "outline_opa": 0,
        }
    )
    knob_style.update(
        {
            "part": "LV_PART_KNOB",
            "state": "LV_STATE_DEFAULT",
            "radius": knob_size // 2,
            "pad_left": -knob_x,
            "pad_right": -max(0, height - knob_x - knob_size),
            "pad_top": -knob_y,
            "pad_bottom": -max(0, height - knob_y - knob_size),
            "bg_color": knob_style.get("bg_color", "#bab096"),
            "bg_opa": 255,
            "shadow_color": "#000000",
            "shadow_opa": 0,
            "shadow_offset_x": 0,
            "shadow_offset_y": 0,
            "shadow_width": 0,
            "shadow_spread": 0,
        }
    )
    return {
        MAIN_STYLE: track,
        "LV_PART_INDICATOR|LV_STATE_DEFAULT": indicator_default,
        "LV_PART_INDICATOR|LV_STATE_CHECKED": indicator_checked,
        "LV_PART_KNOB|LV_STATE_DEFAULT": knob_style,
    }


def object_node(
    node: SourceNode,
    name: str,
    obj_type: str,
    x: int,
    y: int,
    style: dict[str, Any],
    children: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": stable_id(node.id),
        "figma_id": node.id,
        "name": name,
        "type": obj_type,
        "width": max(1, round_px(node.width)),
        "width_unit": "px",
        "height": max(1, round_px(node.height)),
        "height_unit": "px",
        "x": x,
        "x_unit": "px",
        "y": y,
        "y_unit": "px",
        "align": "LV_ALIGN_TOP_LEFT",
        "style": style,
        "children": children or [],
    }
    if obj_type == "container":
        result["scrollbar_mode"] = "LV_SCROLLBAR_MODE_OFF"
        result["remove_flag"] = [SCROLLABLE]
    if node.hidden:
        flags = list(result.get("add_flag", []) or [])
        if HIDDEN not in flags:
            flags.append(HIDDEN)
        result["add_flag"] = flags
    if obj_type == "button":
        result["style"][MAIN_STYLE].update(
            {
                "shadow_color": "#000000",
                "shadow_opa": 0,
                "shadow_offset_x": 0,
                "shadow_offset_y": 0,
                "shadow_width": 0,
                "shadow_spread": 0,
            }
        )
    return result


def apply_semantic_visibility(
    screen: dict[str, Any],
    visibility: dict[str, bool],
    report: dict[str, Any],
) -> None:
    by_figma_id = {
        node.get("figma_id"): node
        for node in iter_objects([screen])
        if node.get("figma_id")
    }
    for figma_id, visible in visibility.items():
        node = by_figma_id.get(figma_id)
        assert node is not None, f"Missing semantic visibility node: {figma_id}"
        add_flags = list(node.get("add_flag", []) or [])
        # State containers are switched at runtime with LV_OBJ_FLAG_HIDDEN.
        # Their overall opacity must remain opaque even while initially hidden,
        # otherwise removing HIDDEN later still leaves every child invisible.
        style = node.get("style", {}).get(MAIN_STYLE, {})
        if style.get("opa") == 0:
            style["opa"] = 255
        if visible:
            add_flags = [flag for flag in add_flags if flag != HIDDEN]
        elif HIDDEN not in add_flags:
            add_flags.append(HIDDEN)
        if add_flags:
            node["add_flag"] = add_flags
        else:
            node.pop("add_flag", None)
        report["visibility_overrides"].append(
            {
                "screen": screen.get("name"),
                "figma_id": figma_id,
                "name": node.get("name"),
                "visible": visible,
            }
        )


def normalize_scroll_flags(
    project: dict[str, Any],
    managed_roots: set[str],
    report: dict[str, Any],
) -> None:
    """Hide every scrollbar while preserving required vertical scrolling."""

    def content_extent(node: dict[str, Any], base_y: int = 0) -> int:
        maximum = base_y + int(node.get("height") or 0)
        for child in node.get("children", []) or []:
            child_y = base_y + int(child.get("y") or 0)
            maximum = max(maximum, content_extent(child, child_y))
        return maximum

    def set_scrollable(node: dict[str, Any], enabled: bool) -> None:
        flags = list(node.get("remove_flag", []) or [])
        if enabled:
            flags = [flag for flag in flags if flag != SCROLLABLE]
        elif SCROLLABLE not in flags:
            flags.append(SCROLLABLE)
        if flags:
            node["remove_flag"] = flags
        else:
            node.pop("remove_flag", None)
        node["scrollbar_mode"] = "LV_SCROLLBAR_MODE_OFF"

    report["scrollable_screens"] = []
    report["scrollable_containers"] = []
    for screen in project["UI"]["screen_list"]:
        if screen.get("figma_id") not in managed_roots:
            continue
        children = screen.get("children", []) or []
        containers = [
            node
            for node in iter_objects(children)
            if node.get("type") == "container"
        ]
        overflow_candidates: dict[int, tuple[dict[str, Any], int]] = {}
        for node in containers:
            node_height = int(node.get("height") or 0)
            node_content = max(
                (
                    content_extent(child, int(child.get("y") or 0))
                    for child in node.get("children", []) or []
                ),
                default=node_height,
            )
            if node_height <= SCREEN_HEIGHT and node_content > node_height + 8:
                overflow_candidates[id(node)] = (node, node_content)

        def contains_candidate(node: dict[str, Any]) -> bool:
            return any(
                id(descendant) in overflow_candidates
                for descendant in iter_objects(node.get("children", []) or [])
            )

        embedded_viewports = {
            node_id: row
            for node_id, row in overflow_candidates.items()
            if not contains_candidate(row[0])
        }
        direct_extent = max(
            (
                int(child.get("y") or 0) + int(child.get("height") or 0)
                for child in children
            ),
            default=SCREEN_HEIGHT,
        )
        screen_scrollable = direct_extent > SCREEN_HEIGHT and not embedded_viewports
        set_scrollable(screen, screen_scrollable)
        if screen_scrollable:
            report["scrollable_screens"].append(
                {"name": screen.get("name"), "content_height": direct_extent}
            )

        for node in containers:
            embedded = id(node) in embedded_viewports
            set_scrollable(node, embedded)
            if embedded:
                report["scrollable_containers"].append(
                    {
                        "screen": screen.get("name"),
                        "name": node.get("name"),
                        "viewport_height": int(node.get("height") or 0),
                        "content_height": embedded_viewports[id(node)][1],
                    }
                )


def png_has_alpha(path: Path) -> tuple[int, int, bool]:
    with path.open("rb") as stream:
        signature = stream.read(8)
        if signature != b"\x89PNG\r\n\x1a\n":
            raise AssertionError(f"Not a PNG: {path}")
        length = struct.unpack(">I", stream.read(4))[0]
        kind = stream.read(4)
        if kind != b"IHDR" or length != 13:
            raise AssertionError(f"Invalid PNG header: {path}")
        data = stream.read(13)
        width, height, _, color_type, _, _, _ = struct.unpack(">IIBBBBB", data)
        alpha = color_type in {4, 6}
        while not alpha:
            length_bytes = stream.read(4)
            if not length_bytes:
                break
            length = struct.unpack(">I", length_bytes)[0]
            kind = stream.read(4)
            if kind == b"tRNS":
                alpha = True
            stream.seek(length + 4, 1)
            if kind == b"IEND":
                break
        return width, height, alpha


def semantic_local_asset(node: SourceNode) -> Path | None:
    name = node.name.lower()
    mapped = LOCAL_ASSET_BY_NODE_NAME.get(name)
    if mapped is not None:
        candidate = LOCAL_ASSET_ROOT / mapped
        if not candidate.exists():
            raise AssertionError(
                f"Mapped local asset is missing for {node.id} {node.name}: "
                f"{candidate}"
            )
        return candidate
    ancestor = node
    ancestor_ids: set[str] = set()
    while ancestor is not None:
        ancestor_ids.add(ancestor.id)
        ancestor = ancestor.parent
    mapping = [
        ("warning", "warning.png"),
        ("reset", "RESET.png"),
        ("present_file", "present_file.png"),
        ("file", "file.png"),
        ("in_use", "checked.png"),
        ("source_usb", "usb.png"),
        ("source_local", "file.png"),
        ("io_", "checked.png"),
    ]
    if name.endswith("_enable"):
        candidate = LOCAL_ASSET_ROOT / "checked.png"
        if candidate.exists():
            return candidate
    if name.endswith("_disable"):
        candidate = LOCAL_ASSET_ROOT / "dischecked.png"
        if candidate.exists():
            return candidate
    if node.name == "img_1" and node.parent and node.parent.id == "366:3":
        return LOCAL_ASSET_ROOT / "notify.png"
    if node.name == "img_1" and "366:777" in ancestor_ids:
        return LOCAL_ASSET_ROOT / "usb.png"
    for token, filename in mapping:
        if token in name:
            candidate = LOCAL_ASSET_ROOT / filename
            if candidate.exists():
                return candidate
    return None


def prepare_image_asset(node: SourceNode, report: dict[str, Any]) -> str:
    legacy_filename = f"_figma_{node.id.replace(':', '_')}.png"
    legacy_destination = ROOT / "resources" / "image" / legacy_filename
    image_directory = legacy_destination.parent
    staging = image_directory / f".{legacy_destination.stem}.asset-stage.png"
    source = semantic_local_asset(node)
    image_directory.mkdir(parents=True, exist_ok=True)
    fallback = report["_existing_asset_by_figma_id"].get(node.id)
    try:
        if source and source.exists():
            # Do not preserve Windows read-only attributes from reviewed source
            # artwork; the staging file must remain removable after validation.
            shutil.copyfile(source, staging)
            origin = str(source)
        elif node.asset_url and node.asset_url.lower().endswith(".png"):
            try:
                with urllib.request.urlopen(node.asset_url, timeout=15) as response:
                    staging.write_bytes(response.read())
            except Exception as error:
                fallback_candidates = [
                    ROOT / fallback if fallback else None,
                    legacy_destination,
                ]
                cached = next(
                    (
                        candidate
                        for candidate in fallback_candidates
                        if candidate is not None and candidate.exists()
                    ),
                    None,
                )
                if cached is None:
                    raise AssertionError(
                        f"Failed to fetch PNG for {node.id} {node.name} "
                        f"from {node.asset_url}: {error}"
                    ) from error
                shutil.copyfile(cached, staging)
                report.setdefault("asset_refresh_warnings", []).append(
                    {
                        "figma_id": node.id,
                        "name": node.name,
                        "url": node.asset_url,
                        "error": str(error),
                        "fallback": str(cached.relative_to(ROOT)),
                    }
                )
                origin = f"existing cache: {cached.relative_to(ROOT)}"
            else:
                origin = node.asset_url
        else:
            raise AssertionError(
                f"No reviewed PNG source for image node {node.id} {node.name}"
            )

        width, height, alpha = png_has_alpha(staging)
        if not alpha:
            try:
                from PIL import Image

                with Image.open(staging) as image:
                    converted = image.convert("RGBA")
                    converted.save(staging)
                width, height, alpha = png_has_alpha(staging)
            except ImportError as error:
                raise AssertionError(
                    f"PNG lacks alpha and Pillow is unavailable: {staging}"
                ) from error
        assert alpha, f"Image asset must preserve alpha: {staging}"

        content_sha256 = file_digest(staging)
        registry = report["_asset_sha256_to_filename"]
        filename = registry.get(content_sha256)
        reused_resource = filename is not None
        if filename is None:
            if source is not None:
                source_token = sanitize(source.stem).lower()
                filename = f"_asset_{source_token}_{content_sha256[:12]}.png"
            else:
                filename = f"_figma_asset_{content_sha256[:16]}.png"
            registry[content_sha256] = filename

        destination = image_directory / filename
        if not destination.exists() or file_digest(destination) != content_sha256:
            shutil.copyfile(staging, destination)
    finally:
        if staging.exists():
            staging.unlink()

    width, height, alpha = png_has_alpha(destination)
    assert alpha, f"Image asset must preserve alpha: {destination}"
    report["assets"].append(
        {
            "figma_id": node.id,
            "source_name": node.name,
            "file": str(destination.relative_to(ROOT)),
            "origin": origin,
            "width": width,
            "height": height,
            "alpha": alpha,
            "content_sha256": content_sha256,
            "reused_resource": reused_resource,
        }
    )
    return filename


def is_transparent_text_wrapper(node: SourceNode) -> bool:
    if len(node.children) != 1 or node.children[0].tag != "text":
        return False
    style = base_visual_style(node)[MAIN_STYLE]
    return style["bg_opa"] == 0 and style["border_width"] == 0


def classify(node: SourceNode, root: SourceNode) -> str:
    if node is root:
        return "screen"
    name = node.name.lower()
    if node.tag == "text":
        return "label"
    if node.image_hash or (node.asset_url and node.asset_url.lower().endswith(".png")):
        return "image"
    if name.startswith("sw_"):
        return "switch"
    if name.startswith(("btn_", "button_")):
        return "button"
    if name.startswith(("indicator_", "led_")):
        return "led"
    return "container"


def meaningful_name(
    node: SourceNode,
    obj_type: str,
    slug: str,
    allocator: NameAllocator,
    existing_names: dict[str, str],
) -> str:
    if node.id in existing_names:
        return allocator.allocate(existing_names[node.id], node.id)
    source = sanitize(node.name)
    lower = source.lower()
    if obj_type == "screen":
        return allocator.allocate(f"screen_{slug}", node.id)
    generic = lower in {"", "node", "text", "vector", "frame", "group", "cont"}
    if obj_type == "label":
        if lower.startswith("label_"):
            candidate = source
        elif node.parent and sanitize(node.parent.name).lower().startswith(
            ("btn_", "button_", "ddlist_", "label_", "cont_")
        ):
            candidate = f"label_{sanitize(node.parent.name)}_text"
        else:
            candidate = f"label_{slug}_{node.id.replace(':', '_')}"
    elif obj_type == "switch":
        candidate = source if lower.startswith("sw_") else f"sw_{slug}_{source}"
    elif obj_type == "button":
        candidate = source if lower.startswith(("btn_", "button_")) else f"btn_{slug}_{source}"
    elif obj_type == "image":
        candidate = source if lower.startswith(("img_", "image_")) else f"img_{slug}_{source}"
    elif obj_type == "led":
        candidate = source if lower.startswith(("led_", "indicator_")) else f"led_{slug}_{source}"
    else:
        if generic:
            candidate = f"cont_{slug}_{node.id.replace(':', '_')}"
        elif lower.startswith(
            ("cont_", "container_", "panel_", "label_", "ddlist_", "decor_", "img_")
        ):
            candidate = source
        elif node.width <= 3 or node.height <= 3 or "line" in lower:
            candidate = f"decor_{slug}_{source}"
        else:
            candidate = f"cont_{slug}_{source}"
    return allocator.allocate(candidate, node.id)


def build_screen(
    spec: dict[str, Any],
    root: SourceNode,
    allocator: NameAllocator,
    existing_names: dict[str, str],
    report: dict[str, Any],
) -> dict[str, Any]:
    target_name = spec["target_name"]
    slug = re.sub(r"^screen_", "", target_name)
    kind = spec.get("kind", "screen")
    overlay = kind == "overlay"
    home_container = kind == "home_container"
    if not overlay and not home_container:
        assert (round_px(root.width), round_px(root.height)) == (960, 240), (
            f"Screen {root.id} must be 960x240, got "
            f"{root.width}x{root.height}"
        )

    def build(
        source: SourceNode,
        offset_x: float = 0,
        offset_y: float = 0,
        preferred_name: str | None = None,
    ) -> dict[str, Any] | None:
        if is_transparent_text_wrapper(source):
            report["flattened_nodes"].append(
                {
                    "figma_id": source.id,
                    "name": source.name,
                    "reason": "transparent single-text wrapper",
                }
            )
            child = source.children[0]
            wrapper_name = sanitize(source.name)
            return build(
                child,
                offset_x + source.x,
                offset_y + source.y,
                wrapper_name if wrapper_name.lower().startswith("label_") else None,
            )

        obj_type = classify(source, root)
        if obj_type == "screen" and (overlay or home_container):
            obj_type = "container"
        knob = next(
            (
                child
                for child in source.children
                if "knob" in child.name.lower()
            ),
            None,
        )
        source_children = [
            child for child in source.children if not (obj_type == "switch" and child is knob)
        ]
        converted_back_to_front = [
            child
            for source_child in source_children
            if (child := build(source_child)) is not None
        ]
        # Figma stores siblings back-to-front.  GUI Guider's tree stores them
        # front-to-back, so keeping the source order places background frames
        # above labels and controls.
        converted = list(reversed(converted_back_to_front))
        name = (
            allocator.allocate(preferred_name, source.id)
            if preferred_name and obj_type == "label"
            else meaningful_name(source, obj_type, slug, allocator, existing_names)
        )
        x = round_px(source.x + offset_x)
        y = round_px(source.y + offset_y)

        if obj_type == "screen":
            screen_style = base_visual_style(source)
            screen_style[MAIN_STYLE].update(
                {
                    "bg_color": "#000000",
                    "bg_opa": 255,
                    "border_width": 0,
                    "border_opa": 0,
                    "radius": 0,
                }
            )
            return {
                "id": stable_id(source.id),
                "figma_id": source.id,
                "name": target_name,
                "type": "screen",
                "style": screen_style,
                "children": converted,
                "default_screen": source.id == "71:3",
            }
        if obj_type == "label":
            result = object_node(
                source,
                name,
                "label",
                x,
                y,
                label_style(source),
            )
            result["static_text"] = False
            result["text"] = source.text or source.name
            text_size = result["style"][MAIN_STYLE]["text_size"]
            measured_width, line_height = rendered_text_metrics(
                result["text"],
                text_size,
            )
            parent = source.parent
            layout_parent = parent
            while (
                layout_parent is not None
                and is_transparent_text_wrapper(layout_parent)
            ):
                layout_parent = layout_parent.parent

            # Figma text boxes describe the visual glyph bounds, while LVGL
            # clips labels using the complete custom-font line height.  The
            # Alibaba PuHuiTi 2.0 23 px font, for example, needs a 33 px LVGL
            # line box even when Figma reports only 27-29 px.  Preserve the
            # source centre while expanding the GUI Guider label.
            if text_size < 80 and line_height > result["height"]:
                original_height = result["height"]
                original_center = result["y"] + original_height / 2
                available_height = (
                    max(1, round_px(layout_parent.height))
                    if layout_parent is not None
                    else line_height
                )
                corrected_height = min(line_height, available_height)
                result["height"] = corrected_height
                result["y"] = max(
                    0,
                    min(
                        round_px(original_center - corrected_height / 2),
                        max(0, available_height - corrected_height),
                    ),
                )
                if line_height > available_height:
                    result["style"][MAIN_STYLE]["pad_top"] = -math.ceil(
                        (line_height - available_height) / 2
                    )
                report["text_box_corrections"].append(
                    {
                        "figma_id": source.id,
                        "axis": "height",
                        "from": original_height,
                        "to": corrected_height,
                    }
                )

            # Small badges and circular text icons must use the parent's full
            # width; otherwise LV_TEXT_ALIGN_CENTER only centres within the
            # narrow original glyph box rather than within the badge/icon.
            parent_name = parent.name.lower() if parent is not None else ""
            small_centered_parent = (
                parent is not None
                and parent.width <= 40
                and parent.height <= 40
                and ("badge" in parent_name or "icon" in parent_name)
            )
            if small_centered_parent:
                corrected_height = min(line_height, max(1, round_px(parent.height)))
                result["x"] = 0
                result["width"] = max(1, round_px(parent.width))
                result["height"] = corrected_height
                result["y"] = max(
                    0,
                    round_px((parent.height - corrected_height) / 2),
                )
                result["style"][MAIN_STYLE]["text_align"] = "LV_TEXT_ALIGN_CENTER"

            # Add a small width reserve because GUI Guider/LVGL and Pillow can
            # round individual glyph advances differently.  Expand every
            # single-line label, not only nodes carrying Tailwind's nowrap
            # class; Figma sometimes omits that class for fixed text nodes.
            if measured_width and "\n" not in result["text"]:
                desired_width = measured_width + 8
                if desired_width > result["width"]:
                    old_x = result["x"]
                    old_width = result["width"]
                    parent_width = (
                        round_px(parent.width)
                        if parent is not None
                        else old_x + desired_width
                    )
                    align = result["style"][MAIN_STYLE]["text_align"]
                    if align == "LV_TEXT_ALIGN_RIGHT":
                        right = old_x + old_width
                        corrected = min(desired_width, right)
                        result["x"] = max(0, right - corrected)
                    elif align == "LV_TEXT_ALIGN_CENTER":
                        center = old_x + old_width / 2
                        corrected = min(desired_width, parent_width)
                        result["x"] = max(
                            0,
                            min(
                                round_px(center - corrected / 2),
                                max(0, parent_width - corrected),
                            ),
                        )
                    else:
                        corrected = min(
                            desired_width,
                            max(old_width, parent_width - old_x),
                        )
                    result["width"] = max(old_width, corrected)
                    report["text_box_corrections"].append(
                        {
                            "figma_id": source.id,
                            "axis": "width",
                            "from": old_width,
                            "to": result["width"],
                        }
                    )
            return result
        if obj_type == "image":
            filename = prepare_image_asset(source, report)
            style = base_visual_style(source)
            style[MAIN_STYLE].update(
                {
                    "bg_opa": 0,
                    "border_width": 0,
                    "border_opa": 0,
                    "radius": 0,
                }
            )
            result = object_node(source, name, "image", x, y, style)
            result["src"] = f"resources\\image\\{filename}"
            return result
        if obj_type == "switch":
            return object_node(
                source,
                name,
                "switch",
                x,
                y,
                switch_style(source, knob),
            )

        style = base_visual_style(source)
        if (
            (source.width <= 3 or source.height <= 3 or "line" in source.name.lower())
            and style[MAIN_STYLE]["bg_opa"] == 0
        ):
            style[MAIN_STYLE].update({"bg_color": "#786e57", "bg_opa": 255})
        return object_node(source, name, obj_type, x, y, style, converted)

    if home_container:
        built = build(root)
        assert built and built["type"] == "container"
        return built

    if not overlay:
        built = build(root)
        assert built and built["type"] == "screen"
        return built

    inner = build(root)
    assert inner and inner["type"] == "container"
    inner["figma_id"] = f"{root.id}:overlay_content"
    inner["id"] = stable_id(inner["figma_id"])
    inner_name = existing_names.get(
        inner["figma_id"], f"{root.name}_overlay"
    )
    inner["name"] = allocator.allocate(inner_name, inner["figma_id"])
    inner["x"] = round_px((960 - root.width) / 2)
    inner["y"] = round_px((240 - root.height) / 2)
    screen_id = root.id
    screen_style = {
        MAIN_STYLE: {
            "part": "LV_PART_MAIN",
            "state": "LV_STATE_DEFAULT",
            "opa": 255,
            "radius": 0,
            "clip_corner": 1,
            "bg_color": "#000000",
            "bg_opa": 255,
            "border_width": 0,
            "border_opa": 0,
            "outline_width": 0,
            "outline_opa": 0,
            "pad_left": 0,
            "pad_right": 0,
            "pad_top": 0,
            "pad_bottom": 0,
        }
    }
    report["semantic_pending"].append(
        {
            "figma_id": root.id,
            "target_name": target_name,
            "imported_as": "standalone preview screen",
            "pending_semantic": "overlay show/hide integration with Home is intentionally deferred",
        }
    )
    return {
        "id": stable_id(screen_id),
        "figma_id": screen_id,
        "name": target_name,
        "type": "screen",
        "style": screen_style,
        "children": [inner],
        "default_screen": False,
    }


SYNC_OWNED_OBJECT_FIELDS = {
    "figma_id",
    "type",
    "width",
    "width_unit",
    "height",
    "height_unit",
    "x",
    "x_unit",
    "y",
    "y_unit",
    "align",
    "style",
    "children",
    "scrollbar_mode",
    "remove_flag",
    "add_flag",
    "static_text",
    "text",
    "src",
    "default_screen",
    "checked",
    "range_min",
    "range_max",
    "range_value",
}


def preserve_existing_object_contract(
    screen: dict[str, Any],
    existing_objects: dict[str, dict[str, Any]],
    report: dict[str, Any],
) -> None:
    """Keep stable identity and non-visual business fields on rebuilt objects."""

    for node in iter_objects([screen]):
        figma_id = node.get("figma_id")
        old = existing_objects.get(figma_id)
        if old is None:
            continue
        preserved_fields: list[str] = []
        for key in ("id", "name"):
            if old.get(key) is not None and node.get(key) != old.get(key):
                node[key] = deepcopy(old[key])
                preserved_fields.append(key)
        for key, value in old.items():
            if key in SYNC_OWNED_OBJECT_FIELDS or key in {"id", "name"}:
                continue
            if node.get(key) != value:
                node[key] = deepcopy(value)
                preserved_fields.append(key)
        if preserved_fields:
            report["preserved_object_contracts"].append(
                {
                    "figma_id": figma_id,
                    "name": node.get("name"),
                    "fields": sorted(preserved_fields),
                }
            )


def validate(
    before: dict[str, Any],
    project: dict[str, Any],
    preserved_hashes: dict[str, str],
    report: dict[str, Any],
    managed_roots: set[str],
    expected_design_roots: set[str],
) -> dict[str, Any]:
    screens = project["UI"]["screen_list"]
    design_screens = [screen for screen in screens if screen.get("figma_id")]
    roots = [screen["figma_id"] for screen in design_screens]
    assert set(roots) == expected_design_roots, (
        f"Unexpected design screen roots: missing={expected_design_roots - set(roots)}, "
        f"extra={set(roots) - expected_design_roots}"
    )
    assert len(roots) == len(set(roots)) == len(expected_design_roots)
    defaults = [
        screen["name"] for screen in design_screens if screen.get("default_screen")
    ]
    assert defaults == ["Home"], f"Unexpected default screens: {defaults}"
    for figma_id, expected_hash in preserved_hashes.items():
        screen = next(item for item in screens if item.get("figma_id") == figma_id)
        assert digest(screen) == expected_hash, f"Preserved screen changed: {figma_id}"

    before_non_ui = deepcopy(before)
    after_non_ui = deepcopy(project)
    before_non_ui["UI"]["screen_list"] = []
    after_non_ui["UI"]["screen_list"] = []
    assert before_non_ui == after_non_ui, "Non-screen project configuration changed"

    all_nodes = list(iter_objects(screens))
    managed_nodes = list(
        iter_objects(
            [
                screen
                for screen in screens
                if screen.get("figma_id") in managed_roots
            ]
        )
    )
    managed_object_ids = {node.get("id") for node in managed_nodes}
    names = [node.get("name") for node in all_nodes if node.get("name")]
    ids = [node.get("id") for node in all_nodes if node.get("id")]
    figma_ids = [
        node.get("figma_id") for node in all_nodes if node.get("figma_id")
    ]
    assert len(names) == len(set(names)), "Duplicate GUI Guider names"
    assert len(ids) == len(set(ids)), "Duplicate GUI Guider object IDs"
    assert len(figma_ids) == len(set(figma_ids)), "Duplicate Figma IDs"
    invalid = [name for name in names if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name)]
    assert not invalid, f"Invalid C identifiers: {invalid[:10]}"
    for node in all_nodes:
        if node.get("type") == "label":
            assert node.get("width", 0) > 0 and node.get("height", 0) > 0
            assert node.get("width_unit") == "px" and node.get("height_unit") == "px"
            if node.get("id") in managed_object_ids:
                assert (
                    node["style"][MAIN_STYLE].get("text_family")
                    == "AlibabaPuHuiTi2.0.ttf"
                )
        if node.get("type") == "image":
            path = ROOT / node["src"].replace("\\", "/")
            assert path.exists(), f"Missing image resource: {path}"
            _, _, alpha = png_has_alpha(path)
            assert alpha, f"Image without alpha: {path}"
        if node.get("type") == "button" and node.get("id") in managed_object_ids:
            style = node["style"][MAIN_STYLE]
            assert style.get("shadow_opa") == 0
        if node.get("type") == "switch" and node.get("id") in managed_object_ids:
            checked = node["style"]["LV_PART_INDICATOR|LV_STATE_CHECKED"]
            knob = node["style"]["LV_PART_KNOB|LV_STATE_DEFAULT"]
            assert checked["bg_opa"] == 255
            assert checked["bg_color"] == "#d6a340"
            assert knob["radius"] >= 8
        if node.get("id") in managed_object_ids and node.get("type") in {
            "screen",
            "container",
        }:
            assert node.get("scrollbar_mode") == "LV_SCROLLBAR_MODE_OFF"
        assert node.get("name") != "decor_nav_right_edge"
        if node.get("figma_id") in {
            "243:401",
            "243:399",
            "243:397",
            "243:395",
            "243:393",
            "243:391",
        }:
            assert (node.get("width"), node.get("height")) == (34, 34)
    for font_file in FONT_FILES:
        assert font_file.exists(), f"Missing font: {font_file}"
    validation = {
        "design_screen_count": len(design_screens),
        "project_screen_entry_count": len(screens),
        "default_screen": defaults[0],
        "unique_names": len(names),
        "unique_object_ids": len(ids),
        "unique_figma_ids": len(figma_ids),
        "preserved_screen_hashes": preserved_hashes,
        "fonts": [str(path.relative_to(ROOT)) for path in FONT_FILES],
        "managed_roots": sorted(managed_roots),
    }
    report["validation"] = validation
    return validation


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-project", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--manifest-index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--output-project", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--semantic-overrides", type=Path, default=DEFAULT_SEMANTICS)
    parser.add_argument(
        "--managed-root",
        dest="managed_roots",
        action="append",
        help="Rebuild only this Figma root; may be supplied multiple times.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    before = load_json(args.input_project)
    project = deepcopy(before)
    index = load_json(args.manifest_index)
    roots_by_id = {item["id"]: item for item in index["roots"]}
    expected_design_roots = set(roots_by_id)
    managed_roots = set(args.managed_roots or expected_design_roots)
    assert managed_roots <= set(roots_by_id)

    preserved_hashes = {
        screen["figma_id"]: digest(screen)
        for screen in before["UI"]["screen_list"]
        if screen.get("figma_id")
        and screen.get("figma_id") not in managed_roots
    }
    explicitly_preserved = {
        figma_id: preserved_hashes[figma_id] for figma_id in PRESERVE_ROOTS
    }

    existing_objects = {
        node["figma_id"]: node
        for node in iter_objects(project["UI"]["screen_list"])
        if node.get("figma_id")
    }
    unmanaged_entries = [
        screen
        for screen in project["UI"]["screen_list"]
        if screen.get("figma_id") not in managed_roots
    ]
    existing_names = {
        node["figma_id"]: node["name"]
        for node in iter_objects(project["UI"]["screen_list"])
        if node.get("figma_id") and node.get("name")
    }
    reserved_names = {
        node["name"]
        for node in iter_objects(unmanaged_entries)
        if node.get("name")
    }
    managed_preferred_owners = {
        node["name"]: node["figma_id"]
        for screen in project["UI"]["screen_list"]
        if screen.get("figma_id") in managed_roots
        for node in iter_objects([screen])
        if node.get("figma_id") and node.get("name")
    }
    allocator = NameAllocator(reserved_names, managed_preferred_owners)
    report: dict[str, Any] = {
        "schema_version": "figma-local-mcp-to-guiguider-report/v1",
        "input_project": str(args.input_project.resolve()),
        "input_sha256": file_digest(args.input_project),
        "manifest_index": str(args.manifest_index.resolve()),
        "managed_roots": sorted(managed_roots),
        "preserved_roots": sorted(set(preserved_hashes)),
        "explicitly_preserved_roots": explicitly_preserved,
        "added_or_rebuilt_screens": [],
        "flattened_nodes": [],
        "text_box_corrections": [],
        "assets": [],
        "semantic_pending": [],
        "visibility_overrides": [],
        "preserved_object_contracts": [],
        "removed_figma_nodes": [],
        "blocking_business_references": [],
        "_asset_sha256_to_filename": {},
        "_existing_asset_by_figma_id": {
            node["figma_id"]: node["src"]
            for node in iter_objects(before["UI"]["screen_list"])
            if node.get("figma_id") and node.get("src")
        },
    }
    built_by_id: dict[str, dict[str, Any]] = {}
    for spec in index["roots"]:
        if spec["id"] not in managed_roots:
            continue
        source_dir = args.manifest_index.parent / spec["directory"]
        raw_path = source_dir / "raw_context.txt"
        if raw_path.exists():
            source, metadata, tsx, _ = extract_sections(
                raw_path.read_text(encoding="utf-8")
            )
            assert source["root_id"] == spec["id"]
            supplements = sorted(source_dir.glob("*_supplement.tsx"))
            if supplements:
                tsx = "\n".join(
                    [
                        tsx,
                        *[
                            path.read_text(encoding="utf-8")
                            for path in supplements
                        ],
                    ]
                )
            root = parse_source_tree(metadata, tsx)
            source_format = (
                "figma.get_design_context+get_metadata"
                + ("+supplements" if supplements else "")
            )
        else:
            root = parse_compact_tree(source_dir, legacy_asset_urls(spec))
            source_format = "figma.use_figma compact manifest"
        assert root.id == spec["id"]
        screen = build_screen(
            spec,
            root,
            allocator,
            existing_names,
            report,
        )
        preserve_existing_object_contract(screen, existing_objects, report)
        if spec["id"] in SEMANTIC_VISIBILITY:
            apply_semantic_visibility(
                screen,
                SEMANTIC_VISIBILITY[spec["id"]],
                report,
            )
        built_by_id[spec["id"]] = screen
        report["added_or_rebuilt_screens"].append(
            {
                "figma_id": spec["id"],
                "source_name": spec["name"],
                "target_name": screen["name"],
                "kind": spec["kind"],
                "source_format": source_format,
                "source_node_count": len(list(iter_source(root))),
                "screenshot": spec["screenshot"],
            }
        )

    rebuilt_list: list[dict[str, Any]] = []
    seen_managed: set[str] = set()
    for screen in before["UI"]["screen_list"]:
        figma_id = screen.get("figma_id")
        if figma_id in built_by_id:
            rebuilt_list.append(built_by_id[figma_id])
            seen_managed.add(figma_id)
        elif figma_id not in managed_roots:
            rebuilt_list.append(screen)
    for spec in index["roots"]:
        figma_id = spec["id"]
        if figma_id in built_by_id and figma_id not in seen_managed:
            rebuilt_list.append(built_by_id[figma_id])
            seen_managed.add(figma_id)
    assert seen_managed == managed_roots
    project["UI"]["screen_list"] = rebuilt_list

    rebuilt_figma_ids = {
        node.get("figma_id")
        for node in iter_objects(project["UI"]["screen_list"])
        if node.get("figma_id")
    }
    business_payload = json.dumps(
        {
            "event_list": before["UI"].get("event_list"),
            "variable_setting": before["UI"].get("variable_setting"),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    for figma_id in sorted(set(existing_objects) - rebuilt_figma_ids):
        old = existing_objects[figma_id]
        references = [
            token
            for token in (old.get("id"), old.get("name"))
            if token and str(token) in business_payload
        ]
        item = {
            "figma_id": figma_id,
            "name": old.get("name"),
            "object_id": old.get("id"),
            "business_references": references,
        }
        report["removed_figma_nodes"].append(item)
        if references:
            report["blocking_business_references"].append(item)
    assert not report["blocking_business_references"], (
        "Figma deleted objects are still referenced by GUI Guider business data: "
        f"{report['blocking_business_references']}"
    )

    normalize_scroll_flags(project, managed_roots, report)
    validate(
        before,
        project,
        preserved_hashes,
        report,
        managed_roots,
        expected_design_roots,
    )
    asset_registry = report.pop("_asset_sha256_to_filename")
    report.pop("_existing_asset_by_figma_id")
    report["asset_deduplication"] = {
        "image_widgets": len(report["assets"]),
        "unique_resources": len(asset_registry),
        "reused_references": sum(
            1 for asset in report["assets"] if asset["reused_resource"]
        ),
        "resources_by_sha256": asset_registry,
    }
    args.output_project.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.output_project, project)
    report["output_project"] = str(args.output_project.resolve())
    report["output_sha256"] = file_digest(args.output_project)
    write_json(args.report, report)
    write_json(
        args.semantic_overrides,
        {
            "schema_version": "figma-semantic-overrides/v1",
            "pending": report["semantic_pending"],
            "policy": (
                "Ambiguous controls remain visual containers. Overlay templates are "
                "standalone preview screens until runtime show/hide behavior is confirmed."
            ),
        },
    )
    print(json.dumps(report["validation"], ensure_ascii=False, indent=2))
    print(f"candidate={args.output_project}")
    print(f"sha256={report['output_sha256']}")


if __name__ == "__main__":
    main()
