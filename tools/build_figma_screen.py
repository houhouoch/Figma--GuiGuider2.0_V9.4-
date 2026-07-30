#!/usr/bin/env python3
"""Synchronize reviewed Figma screens into the GUI Guider 2.0 project.

The Figma plugins are useful for extracting geometry and assets, but their
automatic widget mapping is not authoritative. This script keeps the local
GUI Guider project settings, preserves the reviewed Home screen, and
deterministically upserts Back and HOME_MENU for LVGL 9.4.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import struct
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


ROOT = Path(__file__).resolve().parents[1]
BASE_PROJECT = ROOT / "tools" / "reference" / "blank_project.guiguider"
HOME_EXPORT = ROOT / "tools" / "reference" / "figma_plugin_export_71_3.json"
OUTPUT_PROJECT = ROOT / "guiguider_2.0.guiguider"

MAIN_STYLE = "LV_PART_MAIN|LV_STATE_DEFAULT"
MANAGED_SCREENS = ("Home", "Back", "HOME_MENU")
MANAGED_FIGMA_IDS = {
    "Home": "71:3",
    "Back": "130:2",
    "HOME_MENU": "130:6",
}

# Figma text layers have explicit boxes. The plugin exported some of them as
# content-sized labels, which changes alignment and clips large LVGL fonts.
LABEL_BOXES: dict[str, tuple[int, int]] = {
    "label_vout": (414, 114),
    "unit_vout": (62, 88),
    "label_iout": (428, 114),
    "unit_iout": (62, 88),
    "label_vset_value": (186, 40),
    "label_iset_pos_value": (186, 40),
    "label_iset_neg_value": (186, 40),
    "label_vset": (86, 40),
    "label_iset_pos": (86, 40),
    "label_iset_neg": (86, 40),
    "label_set_heading": (58, 17),
    "label_mode": (82, 40),
    "label_mode_value": (180, 36),
    "label_output_state": (56, 36),
    "label_output": (64, 14),
    "label_menu": (65, 28),
}

# LVGL includes ascent/descent space in the font line box. A negative top
# padding compensates that line box without changing the Figma font size.
AUTO_BASELINE_LABELS = {"label_vout", "label_iout", "label_menu"}


def lvgl_baseline_padding(font_size: int) -> int:
    """Compensate the LVGL line box while preserving the Figma font size."""
    return -round(font_size / 6)


# These objects are updated by the application at runtime.
DYNAMIC_LABELS = {
    "label_vout",
    "label_iout",
    "label_vset_value",
    "label_iset_pos_value",
    "label_iset_neg_value",
    "label_output_state",
    "label_mode_value",
}

# Correct plugin guesses using the intended interaction semantics.
WIDGET_TYPES = {
    "button_menu": "button",
    "button_mode_select": "button",
    "input_vset": "button",
    "input_iset_pos": "button",
    "input_iset_neg": "button",
    "indicator_system_ready": "led",
}

FONT_FAMILIES = {
    "AlibabaPuHuiTi2.0-55Regular": "AlibabaPuHuiTi1",
}

FONT_FILES = {
    "AlibabaPuHuiTi1": "AlibabaPuHuiTi1.ttf",
    "IBMPlexMono-Medium": "IBMPlexMono-Medium.ttf",
    "IBMPlexMono-Regular": "IBMPlexMono-Regular.ttf",
    "IBMPlexSans-Light": "IBMPlexSans-Light.ttf",
    "IBMPlexSans-Regular": "IBMPlexSans-Regular.ttf",
}

# The tuple fields are:
# slug, display text, button/label/image Figma IDs, x/y, image x/y, font size.
MENU_ITEMS = (
    ("config", "Config", "176:12", "176:13", "176:14", 10, 8, 29, 11, 23),
    ("protect", "Protect", "176:23", "176:24", "176:25", 150, 8, 29, 11, 23),
    ("measure", "Measure", "176:34", "176:35", "176:36", 290, 8, 29, 11, 23),
    ("trigger", "Trigger", "176:45", "176:46", "176:47", 430, 8, 29, 9, 23),
    ("recall", "Recall", "176:56", "176:57", "176:58", 570, 8, 29, 9, 23),
    ("save", "Save", "176:67", "176:68", "176:69", 710, 8, 29, 9, 23),
    ("meter", "Meter", "176:78", "176:79", "176:80", 10, 124, 29, 9, 23),
    ("recorder", "Recorder", "176:89", "176:90", "176:91", 150, 124, 30, 3, 23),
    ("function", "Function", "176:100", "176:101", "176:102", 290, 124, 29, 9, 23),
    ("delays", "Delays", "176:111", "176:112", "176:113", 430, 124, 29, 10, 23),
    ("coupling", "Coupling", "176:122", "176:123", "176:124", 570, 124, 29, 9, 23),
    ("group", "Group", "176:133", "176:134", "176:135", 710, 124, 34, 9, 23),
    ("general", "General", "176:144", "176:145", "176:146", 10, 245, 29, 10, 23),
    (
        "digital_io",
        "Digital IO",
        "176:155",
        "176:156",
        "176:157",
        150,
        245,
        29,
        10,
        23,
    ),
    (
        "preference",
        "Preference",
        "176:166",
        "176:167",
        "176:168",
        290,
        245,
        29,
        9,
        18,
    ),
    ("log", "Log", "176:177", "176:178", "176:179", 430, 245, 29, 9, 23),
    ("admin", "Admin", "176:188", "176:189", "176:190", 570, 245, 29, 9, 23),
    (
        "communication",
        "Communication",
        "176:199",
        "176:200",
        "176:201",
        710,
        245,
        30,
        3,
        16,
    ),
    ("info", "Info", "176:210", "176:211", "176:212", 10, 365, 29, 9, 23),
    ("energy", "Energy", "176:221", "176:222", "176:223", 150, 365, 29, 9, 23),
    ("date", "Date", "176:232", "176:233", "176:234", 290, 365, 29, 9, 23),
)


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as stream:
        return json.load(stream)


def walk(nodes: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    for node in nodes:
        yield node
        children = node.get("children", [])
        if isinstance(children, list):
            yield from walk(children)


def main_style(node: dict[str, Any]) -> dict[str, Any]:
    styles = node.get("style", {})
    return styles.get(MAIN_STYLE, {})


def stable_id(figma_id: str) -> str:
    """Generate a stable GUI Guider object ID from a Figma node ID."""
    digest = hashlib.sha1(figma_id.encode("ascii")).digest()[:8]
    token = base64.b32encode(digest).decode("ascii").rstrip("=")
    return f"figma_{token}"


def panel_style(
    bg_color: str,
    *,
    radius: int = 0,
    border_color: str | None = None,
    border_width: int = 0,
    grad_color: str | None = None,
    grad_dir: str = "LV_GRAD_DIR_VER",
    shadow_color: str | None = None,
    shadow_opa: int = 0,
    shadow_width: int = 0,
    shadow_offset_y: int = 0,
) -> dict[str, Any]:
    style: dict[str, Any] = {
        "part": "LV_PART_MAIN",
        "state": "LV_STATE_DEFAULT",
        "opa": 255,
        "radius": radius,
        "clip_corner": 1,
        "bg_color": bg_color,
    }
    if grad_color is None:
        style["bg_opa"] = 255
    else:
        style.update(
            {
                "bg_main_opa": 255,
                "bg_main_stop": 0,
                "bg_grad_color": grad_color,
                "bg_grad_opa": 255,
                "bg_grad_stop": 255,
                "bg_grad_dir": grad_dir,
            }
        )

    if border_color is None or border_width == 0:
        style.update({"border_width": 0, "border_opa": 0})
    else:
        style.update(
            {
                "border_color": border_color,
                "border_opa": 255,
                "border_width": border_width,
            }
        )

    style.update(
        {
            "outline_width": 0,
            "outline_opa": 0,
            "pad_left": 0,
            "pad_right": 0,
            "pad_top": 0,
            "pad_bottom": 0,
        }
    )
    if shadow_color is not None and shadow_opa > 0:
        style.update(
            {
                "shadow_color": shadow_color,
                "shadow_opa": shadow_opa,
                "shadow_offset_x": 0,
                "shadow_offset_y": shadow_offset_y,
                "shadow_width": shadow_width,
                "shadow_spread": 0,
            }
        )
    return {MAIN_STYLE: style}


def object_node(
    figma_id: str,
    name: str,
    obj_type: str,
    x: int,
    y: int,
    width: int,
    height: int,
    style: dict[str, Any],
    *,
    children: list[dict[str, Any]] | None = None,
    scrollbar_mode: str | None = None,
) -> dict[str, Any]:
    node: dict[str, Any] = {
        "id": stable_id(figma_id),
        "figma_id": figma_id,
        "name": name,
        "type": obj_type,
        "width": width,
        "width_unit": "px",
        "height": height,
        "height_unit": "px",
        "x": x,
        "x_unit": "px",
        "y": y,
        "y_unit": "px",
        "align": "LV_ALIGN_TOP_LEFT",
        "style": style,
        "children": children or [],
    }
    if scrollbar_mode is not None:
        node["scrollbar_mode"] = scrollbar_mode
    return node


def container_node(
    figma_id: str,
    name: str,
    x: int,
    y: int,
    width: int,
    height: int,
    style: dict[str, Any],
    *,
    children: list[dict[str, Any]] | None = None,
    scrollbar_mode: str = "LV_SCROLLBAR_MODE_OFF",
) -> dict[str, Any]:
    return object_node(
        figma_id,
        name,
        "container",
        x,
        y,
        width,
        height,
        style,
        children=children,
        scrollbar_mode=scrollbar_mode,
    )


def button_node(
    figma_id: str,
    name: str,
    x: int,
    y: int,
    width: int,
    height: int,
    style: dict[str, Any],
    children: list[dict[str, Any]],
) -> dict[str, Any]:
    return object_node(
        figma_id,
        name,
        "button",
        x,
        y,
        width,
        height,
        style,
        children=children,
    )


def image_node(
    figma_id: str,
    name: str,
    x: int,
    y: int,
    width: int,
    height: int,
    filename: str,
) -> dict[str, Any]:
    style = {
        MAIN_STYLE: {
            "part": "LV_PART_MAIN",
            "state": "LV_STATE_DEFAULT",
            "opa": 255,
            "radius": 0,
            "border_width": 0,
            "border_opa": 0,
            "outline_width": 0,
            "outline_opa": 0,
        }
    }
    node = object_node(figma_id, name, "image", x, y, width, height, style)
    node["src"] = f"resources\\image\\{filename}"
    return node


def label_node(
    figma_id: str,
    name: str,
    text: str,
    x: int,
    y: int,
    width: int,
    height: int,
    *,
    color: str,
    size: int,
    family: str,
    text_align: str = "LV_TEXT_ALIGN_CENTER",
    static_text: bool = True,
) -> dict[str, Any]:
    style: dict[str, Any] = {
        "part": "LV_PART_MAIN",
        "state": "LV_STATE_DEFAULT",
        "opa": 255,
        "border_width": 0,
        "border_opa": 0,
        "outline_width": 0,
        "outline_opa": 0,
        "text_color": color,
        "text_opa": 255,
        "text_size": size,
        "text_family": family,
        "text_align": text_align,
        "pad_top": lvgl_baseline_padding(size),
    }
    node = object_node(
        figma_id,
        name,
        "label",
        x,
        y,
        width,
        height,
        {MAIN_STYLE: style},
    )
    node["static_text"] = static_text
    node["text"] = text
    return node


def decor_node(
    figma_id: str,
    name: str,
    x: int,
    y: int,
    width: int,
    height: int,
    color: str,
    *,
    radius: int = 0,
) -> dict[str, Any]:
    return container_node(
        figma_id,
        name,
        x,
        y,
        width,
        height,
        panel_style(color, radius=radius),
    )


def screen_node(
    figma_id: str,
    name: str,
    style: dict[str, Any],
    children: list[dict[str, Any]],
    *,
    default_screen: bool = False,
) -> dict[str, Any]:
    return {
        "id": stable_id(figma_id),
        "figma_id": figma_id,
        "name": name,
        "type": "screen",
        "style": style,
        "children": children,
        "default_screen": default_screen,
    }


def fix_home_node(node: dict[str, Any]) -> None:
    name = node.get("name", "")

    if name in WIDGET_TYPES:
        node["type"] = WIDGET_TYPES[name]
        node.pop("scrollbar_mode", None)

    if name in LABEL_BOXES:
        width, height = LABEL_BOXES[name]
        node["width"] = width
        node["width_unit"] = "px"
        node["height"] = height
        node["height_unit"] = "px"

    if name in DYNAMIC_LABELS:
        node["static_text"] = False

    style = main_style(node)
    family = style.get("text_family")
    if family in FONT_FAMILIES:
        style["text_family"] = FONT_FAMILIES[family]

    if name in AUTO_BASELINE_LABELS:
        style["pad_top"] = lvgl_baseline_padding(int(style["text_size"]))

    # LVGL shadows surround the label rectangle, not only its glyphs.
    if name in {"label_vout", "label_iout"}:
        for key in (
            "shadow_color",
            "shadow_opa",
            "shadow_offset_x",
            "shadow_offset_y",
            "shadow_width",
            "shadow_spread",
        ):
            style.pop(key, None)


def imported_home_screen() -> dict[str, Any]:
    figma = load_json(HOME_EXPORT)
    for node in figma["UI"]["screen_list"]:
        if node.get("figma_id") == MANAGED_FIGMA_IDS["Home"] or node.get("name") in {
            "Home",
            "screen_power_console_960x240",
        }:
            home = deepcopy(node)
            home["name"] = "Home"
            home["default_screen"] = True
            for child in walk([home]):
                fix_home_node(child)
            return home
    raise AssertionError("Home screen is missing from the reviewed Figma export")


def build_back_screen() -> dict[str, Any]:
    logo = image_node(
        "130:4",
        "img_logo",
        199,
        43,
        569,
        159,
        "_img_logo_130_4.png",
    )
    background = container_node(
        "130:3",
        "cont_back",
        0,
        0,
        960,
        240,
        panel_style("#000000"),
        children=[logo],
    )
    return screen_node(
        MANAGED_FIGMA_IDS["Back"],
        "Back",
        panel_style("#000000"),
        [background],
    )


def menu_card(
    slug: str,
    text: str,
    button_figma_id: str,
    label_figma_id: str,
    image_figma_id: str,
    x: int,
    y: int,
    image_x: int,
    image_y: int,
    font_size: int,
) -> dict[str, Any]:
    label_width = 128 if slug in {"preference", "communication"} else 126
    label_x = 2 if label_width == 128 else 3
    label = label_node(
        label_figma_id,
        f"label_menu_{slug}",
        text,
        label_x,
        76,
        label_width,
        28,
        color="#e3ecee",
        size=font_size,
        family="IBMPlexSans-Regular",
    )
    image = image_node(
        image_figma_id,
        f"img_menu_{slug}",
        image_x,
        image_y,
        73,
        73,
        f"_img_menu_{slug}_{image_figma_id.replace(':', '_')}.png",
    )

    first_corner_id = int(image_figma_id.split(":")[1]) + 1
    corner_specs = (
        (9, 9, 12, 2),
        (9, 9, 2, 12),
        (111, 9, 12, 2),
        (121, 9, 2, 12),
        (9, 93, 12, 2),
        (9, 83, 2, 12),
        (111, 93, 12, 2),
        (121, 83, 2, 12),
    )
    corners = [
        decor_node(
            f"176:{first_corner_id + index}",
            f"decor_{slug}_corner_{index + 1}",
            corner_x,
            corner_y,
            corner_width,
            corner_height,
            "#8cf5f1",
            radius=1,
        )
        for index, (corner_x, corner_y, corner_width, corner_height) in enumerate(
            corner_specs
        )
    ]

    style = panel_style(
        "#102a34",
        radius=7,
        border_color="#92fff8",
        border_width=2,
        grad_color="#07171e",
        shadow_color="#002e38",
        shadow_opa=107,
        shadow_width=8,
        shadow_offset_y=2,
    )
    return button_node(
        button_figma_id,
        f"btn_menu_{slug}",
        x,
        y,
        132,
        104,
        style,
        [label, image, *corners],
    )


def build_menu_screen() -> dict[str, Any]:
    nav_button_style = panel_style(
        "#14323c",
        radius=7,
        border_color="#67aab5",
        border_width=2,
        grad_color="#0a1d25",
    )
    back_button = button_node(
        "176:4",
        "btn_menu_back",
        17,
        8,
        72,
        72,
        deepcopy(nav_button_style),
        [
            image_node(
                "176:5",
                "img_menu_back",
                6,
                6,
                60,
                60,
                "_img_menu_back_176_5.png",
            )
        ],
    )
    home_button = button_node(
        "176:7",
        "btn_menu_home",
        17,
        160,
        72,
        72,
        deepcopy(nav_button_style),
        [
            image_node(
                "176:9",
                "img_menu_home",
                6,
                6,
                60,
                60,
                "_img_menu_home_176_9.png",
            ),
            decor_node(
                "176:8",
                "decor_home_active",
                24,
                68,
                24,
                2,
                "#4ed6d1",
                radius=1,
            ),
        ],
    )
    nav = container_node(
        "176:2",
        "cont_menu_set",
        0,
        0,
        105,
        240,
        panel_style("#070f12", grad_color="#020303"),
        children=[
            decor_node(
                "176:3",
                "decor_nav_right_edge",
                103,
                0,
                2,
                240,
                "#2a4b54",
            ),
            back_button,
            label_node(
                "176:6",
                "label_menu_title",
                "MENU",
                12,
                103,
                81,
                26,
                color="#e5eff1",
                size=23,
                family="IBMPlexSans-Regular",
            ),
            home_button,
        ],
    )

    cards = [menu_card(*item) for item in MENU_ITEMS]
    content = container_node(
        "176:11",
        "cont_menu_content",
        0,
        0,
        855,
        480,
        panel_style("#020303"),
        children=cards,
    )
    function_panel = container_node(
        "176:10",
        "cont_menu_function",
        105,
        0,
        855,
        240,
        panel_style("#020303"),
        children=[content],
        scrollbar_mode="LV_SCROLLBAR_MODE_OFF",
    )

    # Keep the visual scroll rail fixed while cont_menu_content moves.
    scroll_track = decor_node(
        "176:243",
        "decor_scroll_track",
        953,
        10,
        2,
        220,
        "#24414a",
        radius=1,
    )
    scroll_thumb = decor_node(
        "176:244",
        "decor_scroll_thumb",
        952,
        12,
        4,
        106,
        "#67c4c7",
        radius=2,
    )

    return screen_node(
        MANAGED_FIGMA_IDS["HOME_MENU"],
        "HOME_MENU",
        panel_style("#020303", radius=4, border_color="#426b75", border_width=1),
        [nav, function_panel, scroll_track, scroll_thumb],
    )


def find_screen(project: dict[str, Any], name: str) -> dict[str, Any] | None:
    figma_id = MANAGED_FIGMA_IDS[name]
    for node in project["UI"]["screen_list"]:
        if node.get("type") != "screen":
            continue
        if node.get("name") == name or node.get("figma_id") == figma_id:
            return node
        if name == "Home" and node.get("name") == "screen_power_console_960x240":
            return node
    return None


def upsert_screen(project: dict[str, Any], screen: dict[str, Any]) -> None:
    name = screen["name"]
    figma_id = screen["figma_id"]
    output: list[dict[str, Any]] = []
    replaced = False
    for node in project["UI"]["screen_list"]:
        is_match = (
            node.get("type") == "screen"
            and (
                node.get("name") == name
                or node.get("figma_id") == figma_id
                or (
                    name == "Home"
                    and node.get("name") == "screen_power_console_960x240"
                )
            )
        )
        if is_match:
            if not replaced:
                output.append(screen)
                replaced = True
            continue
        output.append(node)
    if not replaced:
        output.append(screen)
    project["UI"]["screen_list"] = output


def build_project() -> dict[str, Any]:
    if OUTPUT_PROJECT.is_file():
        project = load_json(OUTPUT_PROJECT)
    else:
        project = load_json(BASE_PROJECT)
        project["UI"]["screen_list"] = [
            node
            for node in project["UI"]["screen_list"]
            if node.get("type", "").startswith("layer_")
        ]

    project["projectPath"] = str(ROOT)
    project["lastModified"] = (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )
    project["description"] = (
        "Three reviewed 960x240 Figma screens synchronized for GUI Guider 2.0 "
        "and LVGL 9.4."
    )
    project["UI"].setdefault("event_list", {})
    project["UI"].setdefault("variable_setting", {})

    home = find_screen(project, "Home")
    if home is None:
        home = imported_home_screen()
        upsert_screen(project, home)
    else:
        home["name"] = "Home"
        home["default_screen"] = True
        for node in walk([home]):
            fix_home_node(node)

    upsert_screen(project, build_back_screen())
    upsert_screen(project, build_menu_screen())

    for node in project["UI"]["screen_list"]:
        if node.get("type") == "screen":
            node["default_screen"] = node.get("name") == "Home"

    return project


def png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as stream:
        header = stream.read(24)
    assert header[:8] == b"\x89PNG\r\n\x1a\n", f"Not a PNG file: {path.name}"
    return struct.unpack(">II", header[16:24])


def validate(project: dict[str, Any]) -> None:
    settings = project["projectSettings"]
    assert settings["lvglVersion"] == "9.4.0", "Project must target LVGL 9.4.0"
    assert (settings["width"], settings["height"]) == (960, 240)
    assert settings["targetConfig"]["colorDepth"] == 16

    nodes = list(walk(project["UI"]["screen_list"]))
    names = [node.get("name", "") for node in nodes]
    ids = [node.get("id", "") for node in nodes]

    assert len(names) == len(set(names)), "Widget names must be unique"
    assert len(ids) == len(set(ids)), "Widget IDs must be unique"

    screens = [node for node in nodes if node.get("type") == "screen"]
    screen_names = [node["name"] for node in screens]
    for name in MANAGED_SCREENS:
        assert screen_names.count(name) == 1, f"Expected one {name} screen"
    assert sum(bool(node.get("default_screen")) for node in screens) == 1
    assert next(node for node in screens if node["name"] == "Home")["default_screen"]

    identifier = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
    invalid_names = [name for name in names if not identifier.fullmatch(name)]
    assert not invalid_names, f"Invalid C identifiers: {invalid_names}"

    by_name = {node["name"]: node for node in nodes}
    for name, expected_type in WIDGET_TYPES.items():
        assert by_name[name]["type"] == expected_type, f"{name} must be {expected_type}"

    for node in nodes:
        name = node.get("name", "")
        if name.startswith(("btn_", "button_")):
            assert node["type"] == "button", f"{name} must be a button"
        elif name.startswith("img_"):
            assert node["type"] == "image", f"{name} must be an image"
        elif name.startswith(("label_", "unit_")):
            assert node["type"] == "label", f"{name} must be a label"
        elif name.startswith(("cont_", "panel_", "decor_")):
            assert node["type"] == "container", f"{name} must be a container"

    for name, (width, height) in LABEL_BOXES.items():
        node = by_name[name]
        actual = (node["width"], node["height"], node["width_unit"], node["height_unit"])
        assert actual == (width, height, "px", "px"), (
            f"Unexpected label box for {name}: {actual}"
        )

    assert by_name["cont_menu_content"]["height"] == 480
    assert by_name["cont_menu_function"]["height"] == 240
    assert by_name["img_menu_back"]["width"] == 60
    assert by_name["img_menu_home"]["width"] == 60
    assert by_name["img_logo"]["width"] == 569

    menu_buttons = [
        node
        for node in nodes
        if node.get("type") == "button"
        and node.get("name", "").startswith("btn_menu_")
        and node["name"] not in {"btn_menu_back", "btn_menu_home"}
    ]
    assert len(menu_buttons) == 21, "HOME_MENU must contain 21 function buttons"

    used_families: set[str] = set()
    for node in nodes:
        style = main_style(node)
        if style.get("text_family"):
            used_families.add(style["text_family"])

        if node.get("type") == "image":
            source = node.get("src", "").replace("\\", "/")
            assert source, f"Image source missing for {node['name']}"
            asset_path = ROOT / source
            assert asset_path.is_file(), f"Image resource missing: {source}"
            # The original Home export contains a few source bitmaps that GUI
            # Guider scales into smaller image boxes. Newly exported Back/Menu
            # assets are intentionally 1:1 and must remain so.
            if node.get("figma_id", "").startswith(("130:", "176:")):
                assert png_size(asset_path) == (node["width"], node["height"]), (
                    f"Image dimensions do not match {node['name']}: "
                    f"{png_size(asset_path)} != {(node['width'], node['height'])}"
                )

    unknown_families = used_families - FONT_FILES.keys()
    assert not unknown_families, f"Unmapped fonts: {sorted(unknown_families)}"
    for family in used_families:
        font_path = ROOT / "resources" / "font" / FONT_FILES[family]
        assert font_path.is_file(), f"Font resource missing: {font_path.name}"


def write_project(project: dict[str, Any]) -> None:
    with OUTPUT_PROJECT.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(project, stream, ensure_ascii=True, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    result = build_project()
    validate(result)
    write_project(result)
    print(f"Wrote {OUTPUT_PROJECT}")
    print(
        "Validated: Home, Back, HOME_MENU; LVGL 9.4; 960x240; "
        "RGB565; resources; names; widget mappings"
    )
