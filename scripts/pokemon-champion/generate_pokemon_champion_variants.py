"""Create compact Champions sprite variants from the 320px final PNGs.

This preserves poke-guide's measured variant sizes: 96px icons serve the
roughly 48px display, while 192px medium sprites serve 64--128px views.
Source PNGs are already post-Real-ESRGAN, so variants only make one LANCZOS
reduction.  For poke-sprites the input and output names are Japanese data
names under ``sprites/pokemon-champion/``; both PNG and q90 WebP are emitted,
and ``--force``/``--names`` use the shared common arguments.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import common

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIR = REPO_ROOT / "sprites" / "pokemon-champion"
# The output directory names and dimensions are consumed by the site.
VARIANTS = (("icon", 96), ("medium", 192))
WEBP_QUALITY = 90


def main() -> None:
    parser = argparse.ArgumentParser(description="Champions sprite の icon/ と medium/ を生成する")
    common.add_common_args(parser)
    args = parser.parse_args()

    known_names = [entry["name"] for entry in common.load_pokemon()]
    names = common.filter_names(parser, args, known_names)
    sources = {path.stem: path for path in SOURCE_DIR.glob("*.png")}
    requested = [name for name in names if common.to_filename(name) in sources]
    missing = [name for name in names if common.to_filename(name) not in sources]
    print(f"入力 PNG: {len(requested)} 件 / 未生成の入力: {len(missing)} 件")

    for directory_name, size in VARIANTS:
        out_dir = SOURCE_DIR / directory_name
        generated = 0
        skipped = 0
        for name in requested:
            if not args.force and common.outputs_exist(out_dir, name):
                skipped += 1
                continue
            with Image.open(sources[common.to_filename(name)]) as source:
                image = source.convert("RGBA").resize((size, size), Image.LANCZOS)
            common.save_png_and_webp(image, out_dir, name, webp_quality=WEBP_QUALITY)
            generated += 1
        print(f"{directory_name}/ ({size}px): 生成 {generated} 件 / 既存スキップ {skipped} 件")
        common.report(out_dir, f"{directory_name}/")

    if missing:
        print(f"入力 PNG がない名前: {len(missing)} 件（Champions menu sprite 未マッチ）")
    print("失敗: 0 件")


if __name__ == "__main__":
    main()
