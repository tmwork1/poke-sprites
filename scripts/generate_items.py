"""高解像度アイテム画像を正規化して生成する。

items.csvを入力し、和名のPNG・可逆WebPをsprites/itemsへ、原画をrawへ出力する。
前景のアルファ領域から正方形に切り出し、見かけの面積をそろえて96pxへ縮小する。
細長い画像は長辺を94%以内に収め、切れを防ぐ。
"""
from __future__ import annotations

import argparse
import io
import math
import re
from pathlib import Path

from PIL import Image

import common

OUT_DIR = common.SPRITES_DIR / "items"
RAW_DIR = OUT_DIR / "raw"
SPRITES_BASE = "https://www.serebii.net/itemdex/sprites"
OUTPUT_SIZE = 96
ALPHA_MIN = 8
TARGET_AREA_SIDE_FRACTION = 0.8
MAX_LONG_SIDE_FRACTION = 0.94
OUTPUT_ALPHA_MIN = 16
LIST_PAGES = ["pokeball", "recovery", "holditem", "evolutionary", "berry", "gsberry", "battleeffect", "vitamins", "fossil", "mail", "miscellaneous", "keyitem", "eventitem", "decorations"]
IMAGE_DIRS = ["za", "sv", ""]
# 通常の索引と異なるSerebii上の画像名。
SEREBII_STEM_OVERRIDES: dict[str, str] = {
    "heavy-duty-boots": "heavy-dutyboots",
}

HIGH_RES_SOURCE_URL: dict[str, str] = {
    "\u3068\u3051\u306a\u3044\u3053\u304a\u308a": "https://www.gamerguides.com/assets/media/15/662678/item_0246-3f14402f.png",
    "\u304a\u3046\u3058\u3083\u306e\u3057\u308b\u3057": "https://www.gamerguides.com/assets/media/15/1988/item_0221.png",
}
STEM_IMG_RE = re.compile(r"/itemdex/sprites/([a-zA-Z0-9\\-]+)\\.png")


def detect_alpha_bbox(im: Image.Image) -> tuple[int, int, int, int]:
    """alpha>=ALPHA_MIN の前景 bbox を返す。"""
    bbox = im.getchannel("A").point(lambda a: 255 if a >= ALPHA_MIN else 0).getbbox()
    if bbox is None:
        raise RuntimeError(f"alpha >= {ALPHA_MIN} のピクセルがありません")
    return bbox


def build_normalized_icon(im: Image.Image) -> Image.Image:
    """bbox 中心で正方形クロップし、96px へ一度だけ LANCZOS リサイズする。"""
    x0, y0, x1, y1 = detect_alpha_bbox(im)
    width, height = x1 - x0, y1 - y0
    side = max(math.sqrt(width * height) / TARGET_AREA_SIDE_FRACTION, max(width, height) / MAX_LONG_SIDE_FRACTION)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    result = im.crop((round(cx - side / 2), round(cy - side / 2), round(cx + side / 2), round(cy + side / 2))).resize((OUTPUT_SIZE, OUTPUT_SIZE), Image.LANCZOS)
    alpha = result.getchannel("A")
    result.putalpha(alpha.point(lambda value: 0 if value < OUTPUT_ALPHA_MIN else value))
    return result


def raw_path(name: str) -> Path | None:
    """元の拡張子を問わず、既存の raw 原画を見つける。"""
    matches = sorted(RAW_DIR.glob(f"{common.to_filename(name)}.*"))
    return matches[0] if matches else None


def extension_for(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "webp"
    return "png"


def build_stem_index() -> dict[str, str]:
    """Serebii のカテゴリ一覧からハイフン有無の名称索引を作る。"""
    index: dict[str, str] = {}
    for page in LIST_PAGES:
        url = f"https://www.serebii.net/itemdex/list/{page}.shtml"
        try:
            data = common.fetch(url)
        except RuntimeError as exc:
            print(f"  [警告] 索引を取得できません: {url}: {exc}")
            continue
        if data:
            for stem in STEM_IMG_RE.findall(data.decode("utf-8", errors="ignore")):
                index.setdefault(stem.replace("-", "").lower(), stem)
    return index


def resolve_image(slug: str, index: dict[str, str]) -> tuple[bytes, str] | None:
    base = slug.split("/")[-1]
    stripped = base.replace("-", "").lower()
    candidates = [stripped]
    if (override := SEREBII_STEM_OVERRIDES.get(base)):
        candidates.insert(0, override)
    if (looked_up := index.get(stripped)) and looked_up != stripped:
        candidates.append(looked_up)
    if base != stripped:
        candidates.append(base)
    for candidate in dict.fromkeys(candidates):
        for image_dir in IMAGE_DIRS:
            prefix = f"{image_dir}/" if image_dir else ""
            url = f"{SPRITES_BASE}/{prefix}{candidate}.png"
            try:
                data = common.fetch(url)
            except RuntimeError as exc:
                print(f"  [警告] {url}: {exc}")
                continue
            if data is not None:
                return data, url
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="アイテム画像を正規化して生成する")
    common.add_common_args(parser)
    parser.add_argument("--refetch", action="store_true", help="raw 原画も再取得する")
    args = parser.parse_args()
    entries = common.load_items()
    # 空URLの透明画像を原画として保存しないため、slugなしは除外する。
    targets = [(entry["name"], entry["slug"]) for entry in entries if entry["slug"]]
    names = common.filter_names(parser, args, [name for name, _ in targets])
    targets = [(name, slug) for name, slug in targets if name in set(names)]
    needs_network = any(args.refetch or raw_path(name) is None for name, _ in targets)
    index = build_stem_index() if needs_network else {}
    print(f"対象: {len(targets)} 件")
    failures: list[tuple[str, str]] = []
    generated = skipped = 0
    for number, (name, slug) in enumerate(targets, 1):
        if not args.force and common.outputs_exist(OUT_DIR, name):
            skipped += 1
            continue
        raw = None if args.refetch else raw_path(name)
        source = "raw"
        if raw is None:
            source_url = HIGH_RES_SOURCE_URL.get(name)
            try:
                resolved = (common.fetch(source_url), source_url) if source_url else resolve_image(slug or "", index)
            except RuntimeError as exc:
                resolved = None
                failures.append((name, str(exc)))
            if not resolved or resolved[0] is None:
                if not any(item[0] == name for item in failures):
                    failures.append((name, slug or "slug 不明"))
                print(f"[{number}/{len(targets)}] {name}: FAILED - 原画を取得できません")
                continue
            raw = common.save_raw(resolved[0], RAW_DIR, name, extension_for(resolved[0]))
            source = resolved[1]
        try:
            with Image.open(raw) as image:
                result = build_normalized_icon(image.convert("RGBA"))
            common.save_png_and_webp(result, OUT_DIR, name, webp_quality=None)
            generated += 1
            print(f"[{number}/{len(targets)}] {name}: OK ({source})")
        except Exception as exc:  # noqa: BLE001 - 他の画像の処理を継続する
            failures.append((name, str(exc)))
            print(f"[{number}/{len(targets)}] {name}: FAILED - {exc}")
    print(f"完了: 生成 {generated} 件 / スキップ {skipped} 件 / 失敗 {len(failures)} 件")
    if failures:
        print("失敗一覧:")
        for name, reason in failures:
            print(f"  - {name}: {reason}")
    common.report(OUT_DIR, "items 出力")
    common.report(RAW_DIR, "items raw")


if __name__ == "__main__":
    main()
