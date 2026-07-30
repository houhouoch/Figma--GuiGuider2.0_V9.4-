#!/usr/bin/env python3
"""Render a lightweight GUI Guider JSON contact sheet for visual regression.

This is not a replacement for the GUI Guider simulator.  It reproduces the
parts needed for conversion review: sibling order, fills, borders, text boxes,
font files, hidden flags, and PNG placement.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


MAIN_STYLE = "LV_PART_MAIN|LV_STATE_DEFAULT"
HIDDEN = "LV_OBJ_FLAG_HIDDEN"
FONT_FILES = {
    "Inter-Regular": "Inter-Regular.ttf",
    "Inter-Medium": "Inter-Medium.ttf",
    "AlibabaPuHuiTi1": "AlibabaPuHuiTi1.ttf",
    "AlibabaPuHuiTi2.0.ttf": "AlibabaPuHuiTi2.0.ttf",
    "IBMPlexMono-Medium": "IBMPlexMono-Medium.ttf",
    "IBMPlexMono-Regular": "IBMPlexMono-Regular.ttf",
    "IBMPlexSans-Light": "IBMPlexSans-Light.ttf",
    "IBMPlexSans-Regular": "IBMPlexSans-Regular.ttf",
}


def rgba(value: str | None, opacity: int | None = 255) -> tuple[int, int, int, int]:
    value = (value or "#000000").lstrip("#")
    if len(value) != 6:
        value = "000000"
    return (
        int(value[0:2], 16),
        int(value[2:4], 16),
        int(value[4:6], 16),
        int(opacity or 0),
    )


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    if not text or width <= 0:
        return [text]
    words = text.split(" ")
    rows: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if draw.textlength(candidate, font=font) <= width:
            current = candidate
        else:
            if current:
                rows.append(current)
            current = word
    if current:
        rows.append(current)
    return rows or [text]


class Renderer:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.font_root = root / "resources" / "font"

    def font(self, family: str | None, size: int) -> ImageFont.FreeTypeFont:
        filename = FONT_FILES.get(family or "", "Inter-Regular.ttf")
        return ImageFont.truetype(str(self.font_root / filename), size)

    def node(self, canvas: Image.Image, node: dict[str, Any], offset_x: int = 0, offset_y: int = 0) -> None:
        if HIDDEN in (node.get("add_flag") or []):
            return
        x = offset_x + int(node.get("x") or 0)
        y = offset_y + int(node.get("y") or 0)
        width = int(node.get("width") or 0)
        height = int(node.get("height") or 0)
        visual = (node.get("style") or {}).get(MAIN_STYLE, {})
        draw = ImageDraw.Draw(canvas, "RGBA")

        if width > 0 and height > 0:
            radius = int(visual.get("radius") or 0)
            background_opacity = int(visual.get("bg_opa") or 0)
            if background_opacity:
                draw.rounded_rectangle(
                    (x, y, x + width - 1, y + height - 1),
                    radius=radius,
                    fill=rgba(visual.get("bg_color"), background_opacity),
                )

            border_width = int(visual.get("border_width") or 0)
            border_opacity = int(visual.get("border_opa") or 0)
            for inset in range(border_width if border_opacity else 0):
                if x + width - 1 - inset < x + inset or y + height - 1 - inset < y + inset:
                    break
                draw.rounded_rectangle(
                    (x + inset, y + inset, x + width - 1 - inset, y + height - 1 - inset),
                    radius=max(0, radius - inset),
                    outline=rgba(visual.get("border_color"), border_opacity),
                    width=1,
                )

            if node.get("type") == "image" and node.get("src"):
                path = self.root / str(node["src"]).replace("\\", "/")
                if path.is_file():
                    image = Image.open(path).convert("RGBA").resize((width, height))
                    canvas.alpha_composite(image, (x, y))

            if node.get("type") == "label":
                text = str(node.get("text") or "")
                size = int(visual.get("text_size") or 14)
                font = self.font(visual.get("text_family"), size)
                rows = wrap_text(draw, text, font, width)
                line_height = max(size, int(size * 1.2 + 0.5))
                block_height = line_height * len(rows)
                top = y + int(visual.get("pad_top") or 0) + max(0, (height - block_height) // 2)
                align = visual.get("text_align", "LV_TEXT_ALIGN_LEFT")
                for index, row in enumerate(rows):
                    text_width = int(draw.textlength(row, font=font) + 0.5)
                    if align.endswith("RIGHT"):
                        left = x + width - text_width
                    elif align.endswith("CENTER"):
                        left = x + (width - text_width) // 2
                    else:
                        left = x
                    draw.text(
                        (left, top + index * line_height),
                        row,
                        font=font,
                        fill=rgba(visual.get("text_color", "#d6d6cf"), visual.get("text_opa", 255)),
                    )

        # GUI Guider stores siblings front-to-back, so paint in reverse.
        for child in reversed(node.get("children") or []):
            self.node(canvas, child, x, y)

    def screen(self, node: dict[str, Any]) -> Image.Image:
        visual = (node.get("style") or {}).get(MAIN_STYLE, {})
        image = Image.new(
            "RGBA",
            (960, 240),
            rgba(
                visual.get("bg_color", "#000000"),
                visual.get("bg_opa", 255),
            ),
        )
        self.node(image, node)
        return image.convert("RGB")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--figma-id", action="append", dest="figma_ids", required=True)
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    project = json.loads(args.project.read_text(encoding="utf-8"))
    renderer = Renderer(root)
    cards: list[Image.Image] = []
    preview_dir = args.output.with_suffix("")
    preview_dir.mkdir(parents=True, exist_ok=True)
    for figma_id in args.figma_ids:
        screen = next(
            item for item in project["UI"]["screen_list"] if item.get("figma_id") == figma_id
        )
        preview = renderer.screen(screen)
        preview.save(preview_dir / f"{figma_id.replace(':', '_')}.png")
        card = Image.new("RGB", (500, 150), "#202020")
        card.paste(preview.resize((480, 120)), (10, 24))
        ImageDraw.Draw(card).text((10, 4), f"{figma_id} {screen['name']}", fill="white")
        cards.append(card)

    columns = 2
    rows = (len(cards) + columns - 1) // columns
    sheet = Image.new("RGB", (500 * columns, 150 * rows), "#181818")
    for index, card in enumerate(cards):
        sheet.paste(card, ((index % columns) * 500, (index // columns) * 150))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.output)
    print(args.output)


if __name__ == "__main__":
    main()
