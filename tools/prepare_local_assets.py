#!/usr/bin/env python3
"""Prepare transparent GUI Guider assets from the reviewed local originals.

Do not export Figma image-fill rectangles for icons: that can rasterize the
rectangle background into the PNG. This script keeps the original alpha
channel and only resizes the artwork onto a transparent target canvas.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageColor, ImageOps


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_ROOT = ROOT / "external-assets" / "source"
DEFAULT_OUTPUT_ROOT = ROOT / "project" / "resources" / "image"


@dataclass(frozen=True)
class Asset:
    output_name: str
    source_path: str
    size: tuple[int, int]
    monochrome: str | None = None


ASSETS = (
    Asset("_img_logo_130_4.png", "UNIT.png", (569, 159)),
    Asset("_img_menu_back_176_5.png", r"imag副本\back3.png", (60, 60)),
    Asset(
        "_img_menu_home_176_9.png",
        r"menu\home.png",
        (60, 60),
        monochrome="#e5eff1",
    ),
    Asset(
        "_img_menu_config_176_14.png",
        r"menu_alone\图片原件\config_alone.png",
        (73, 73),
    ),
    Asset(
        "_img_menu_protect_176_25.png",
        r"menu_alone\图片原件\protect_alone.png",
        (73, 73),
    ),
    Asset(
        "_img_menu_measure_176_36.png",
        r"menu_alone\图片原件\measure_alone.png",
        (73, 73),
    ),
    Asset(
        "_img_menu_trigger_176_47.png",
        r"menu_alone\trigger_alone_2.png",
        (73, 73),
    ),
    Asset(
        "_img_menu_recall_176_58.png",
        r"menu_alone\图片原件\recall_alone.png",
        (73, 73),
    ),
    Asset(
        "_img_menu_save_176_69.png",
        r"menu_alone\图片原件\save_alone.png",
        (73, 73),
    ),
    Asset(
        "_img_menu_meter_176_80.png",
        r"menu_alone\meter2.png",
        (73, 73),
    ),
    Asset(
        "_img_menu_recorder_176_91.png",
        r"menu_alone\图片原件\recoder_alone.png",
        (73, 73),
    ),
    Asset(
        "_img_menu_function_176_102.png",
        r"menu_alone\图片原件\Function_alone.png",
        (73, 73),
    ),
    Asset(
        "_img_menu_delays_176_113.png",
        r"menu_alone\图片原件\delays_alone.png",
        (73, 73),
    ),
    Asset(
        "_img_menu_coupling_176_124.png",
        r"menu_alone\图片原件\coupling_alone.png",
        (73, 73),
    ),
    Asset(
        "_img_menu_group_176_135.png",
        r"menu_alone\图片原件\group_alone.png",
        (73, 73),
    ),
    Asset(
        "_img_menu_general_176_146.png",
        r"menu_alone\图片原件\general_alone.png",
        (73, 73),
    ),
    Asset(
        "_img_menu_digital_io_176_157.png",
        r"menu_alone\图片原件\Digital_io_alone.png",
        (73, 73),
    ),
    Asset(
        "_img_menu_preference_176_168.png",
        r"menu_alone\图片原件\perfect_alone.png",
        (73, 73),
    ),
    Asset(
        "_img_menu_log_176_179.png",
        r"menu_alone\图片原件\log_alone.png",
        (73, 73),
    ),
    Asset(
        "_img_menu_admin_176_190.png",
        r"menu_alone\图片原件\admin_alone.png",
        (73, 73),
    ),
    Asset(
        "_img_menu_communication_176_201.png",
        r"menu_alone\图片原件\communication_alone.png",
        (73, 73),
    ),
    Asset(
        "_img_menu_info_176_212.png",
        r"menu_alone\图片原件\info_alone.png",
        (73, 73),
    ),
    Asset(
        "_img_menu_energy_176_223.png",
        r"menu_alone\图片原件\energy_alone.png",
        (73, 73),
    ),
    Asset(
        "_img_menu_date_176_234.png",
        r"menu_alone\图片原件\date_alone.png",
        (73, 73),
    ),
    Asset(
        "_img_function_cd_arb_243_342.png",
        r"高级功能\CD_Arb.png",
        (98, 95),
    ),
    Asset(
        "_img_function_sine_sweep_243_343.png",
        r"高级功能\Sine_Aweep.png",
        (95, 95),
    ),
    Asset(
        "_img_function_bemulator_243_344.png",
        r"高级功能-统一色差\BEmulator.png",
        (95, 95),
    ),
    Asset(
        "_img_function_bdischarge_243_345.png",
        r"高级功能\BDischarge.png",
        (95, 95),
    ),
    Asset(
        "_img_function_bcharge_243_346.png",
        r"高级功能\BCharge.png",
        (95, 95),
    ),
    Asset(
        "_img_function_list_243_347.png",
        r"高级功能\List.png",
        (95, 95),
    ),
    Asset(
        "_img_function_fixed_243_348.png",
        r"高级功能\Fixed.png",
        (95, 95),
    ),
    Asset(
        "_img_function_arb_243_349.png",
        r"高级功能\Arb.png",
        (95, 95),
    ),
    Asset(
        "_img_function_sequence_243_350.png",
        r"高级功能\Sequence.png",
        (95, 95),
    ),
    Asset(
        "_img_checkbox_disable_20.png",
        "dischecked.png",
        (20, 20),
        monochrome="#b7aa86",
    ),
    Asset(
        "_img_checkbox_disable_30.png",
        "dischecked.png",
        (30, 30),
        monochrome="#b7aa86",
    ),
    Asset(
        "_img_checkbox_enable_15.png",
        "checked.png",
        (15, 15),
    ),
    Asset(
        "_img_clear_30.png",
        "trash.png",
        (30, 30),
        monochrome="#f1eee6",
    ),
)

NEW_SCREEN_OUTPUTS = {
    "_img_function_cd_arb_243_342.png",
    "_img_function_sine_sweep_243_343.png",
    "_img_function_bemulator_243_344.png",
    "_img_function_bdischarge_243_345.png",
    "_img_function_bcharge_243_346.png",
    "_img_function_list_243_347.png",
    "_img_function_fixed_243_348.png",
    "_img_function_arb_243_349.png",
    "_img_function_sequence_243_350.png",
    "_img_checkbox_disable_20.png",
    "_img_checkbox_disable_30.png",
    "_img_checkbox_enable_15.png",
    "_img_clear_30.png",
}


def render_asset(source: Path, target: Path, asset: Asset) -> None:
    image = Image.open(source).convert("RGBA")
    if asset.monochrome is not None:
        rgb = ImageColor.getrgb(asset.monochrome)
        alpha = image.getchannel("A")
        image = Image.new("RGBA", image.size, (*rgb, 255))
        image.putalpha(alpha)

    resized = ImageOps.contain(image, asset.size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", asset.size, (0, 0, 0, 0))
    offset = (
        (asset.size[0] - resized.width) // 2,
        (asset.size[1] - resized.height) // 2,
    )
    canvas.alpha_composite(resized, offset)
    target.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(target, format="PNG", optimize=True)

    with Image.open(target) as output:
        assert output.mode == "RGBA", f"Alpha channel missing: {target.name}"
        assert output.size == asset.size, (
            f"Unexpected output size for {target.name}: {output.size}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-root",
        type=Path,
        default=DEFAULT_SOURCE_ROOT,
        help="Directory containing the reviewed original PNG assets.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="GUI Guider resources/image output directory.",
    )
    parser.add_argument(
        "--only-new",
        action="store_true",
        help="Prepare only assets used by the 12 Figma MCP screens.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    assets = (
        tuple(asset for asset in ASSETS if asset.output_name in NEW_SCREEN_OUTPUTS)
        if args.only_new
        else ASSETS
    )
    missing = [
        args.source_root / asset.source_path
        for asset in assets
        if not (args.source_root / asset.source_path).is_file()
    ]
    if missing:
        formatted = "\n".join(str(path) for path in missing)
        raise FileNotFoundError(f"Missing source assets:\n{formatted}")

    for asset in assets:
        source = args.source_root / asset.source_path
        target = args.output_root / asset.output_name
        render_asset(source, target, asset)
        print(f"{source.name} -> {target.name} ({asset.size[0]}x{asset.size[1]})")

    print(f"Prepared {len(assets)} transparent assets in {args.output_root}")


if __name__ == "__main__":
    main()
