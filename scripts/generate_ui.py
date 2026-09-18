"""GameWith の UI 原画を sprites/ui/ に PNG と lossless WebP で生成する。

この移植版は UI ごとの (和名, URL) を定数で管理し、原画を sprites/ui/raw/ に
無加工で保存する。raw があればネットワークへ接続せず再生成できる。--force は
加工済み出力だけを上書きし、--refetch は raw も取り直す。UI 原画はサイズ・形状を
加工せずそのまま変換する。
"""
from __future__ import annotations

import argparse
import io
from pathlib import Path

from PIL import Image

import common

OUT_DIR = common.SPRITES_DIR / "ui"
RAW_DIR = OUT_DIR / "raw"
UI_IMAGES = [("\u30c6\u30e9\u30b9\u30bf\u30eb", "https://img.gamewith.jp/article_tools/pokemon-sv/gacha/map_icon_terra2.png")]


def raw_path(name: str) -> Path | None:
    matches = sorted(RAW_DIR.glob(f"{common.to_filename(name)}.*"))
    return matches[0] if matches else None


def extension_for(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "webp"
    return "png"


def main() -> None:
    parser = argparse.ArgumentParser(description="UI 画像を無加工で生成する")
    common.add_common_args(parser)
    parser.add_argument("--refetch", action="store_true", help="raw 原画も再取得する")
    args = parser.parse_args()
    names = common.filter_names(parser, args, [name for name, _ in UI_IMAGES])
    targets = [(name, url) for name, url in UI_IMAGES if name in set(names)]
    print(f"対象: {len(targets)} 件")
    failures: list[tuple[str, str]] = []
    generated = skipped = 0
    for number, (name, url) in enumerate(targets, 1):
        if not args.force and common.outputs_exist(OUT_DIR, name):
            skipped += 1
            continue
        raw = None if args.refetch else raw_path(name)
        if raw is None:
            try:
                data = common.fetch(url)
            except RuntimeError as exc:
                data = None
                failures.append((name, str(exc)))
            if data is None:
                if not any(item[0] == name for item in failures):
                    failures.append((name, "原画を取得できません"))
                print(f"[{number}/{len(targets)}] {name}: FAILED - 原画を取得できません")
                continue
            raw = common.save_raw(data, RAW_DIR, name, extension_for(data))
        try:
            with Image.open(raw) as image:
                common.save_png_and_webp(image.convert("RGBA"), OUT_DIR, name, webp_quality=None)
            generated += 1
            print(f"[{number}/{len(targets)}] {name}: OK")
        except Exception as exc:  # noqa: BLE001
            failures.append((name, str(exc)))
            print(f"[{number}/{len(targets)}] {name}: FAILED - {exc}")
    print(f"完了: 生成 {generated} 件 / スキップ {skipped} 件 / 失敗 {len(failures)} 件")
    if failures:
        print("失敗一覧:")
        for name, reason in failures:
            print(f"  - {name}: {reason}")
    common.report(OUT_DIR, "ui 出力")
    common.report(RAW_DIR, "ui raw")


if __name__ == "__main__":
    main()
