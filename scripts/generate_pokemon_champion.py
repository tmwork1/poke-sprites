"""BulbagardenのChampionsメニュースプライトを生成する。

``data/pokemon.csv`` とカテゴリ情報を図鑑番号・フォルムで照合し、
日本語名のPNGと可逆WebPを ``sprites/pokemon-champion/`` に出力する。
原画は ``raw/`` に保存し、アニメ向けReal-ESRGANで4倍化(512px)したものをそのまま ``png/`` と ``webp/`` に出力する。
"""

from __future__ import annotations

import argparse
import io
import json
import re
import tempfile
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PIL import Image

import common
from realesrgan_tool import upscale_dir

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "sprites" / "pokemon-champion"
RAW_DIR = OUT_DIR / "raw"

# 原画128pxをReal-ESRGANで4倍化した512pxをそのまま出力する。
# Real-ESRGANが使えない場合はLANCZOSで同サイズに拡大して揃える。
OUTPUT_SIZE = 512

API_URL = "https://archives.bulbagarden.net/w/api.php"
CATEGORY_TITLE = "Category:Champions_menu_sprites"
FORME_ALIASES = {
    "f": "female",
    "super": "jumbo",
}
FILENAME_RE = re.compile(r"^Menu[ _]CP[ _](\d{4})(?:[-_](.+))?\.png$", re.IGNORECASE)
MAX_WORKERS = 8


def norm(value: str | None) -> str:
    """接尾辞を正規化し、表記ゆれを統一する。"""
    if not value:
        return ""
    collapsed = " ".join(value.strip().lower().replace("_", " ").replace("-", " ").split())
    return collapsed.replace(" ", "-")


def aliased(value: str | None) -> str:
    return FORME_ALIASES.get(norm(value), norm(value))


def fetch_bulba_manifest() -> list[dict]:
    """カテゴリ内の全ファイルから図鑑番号・接尾辞・URL・題名を取得する。"""
    entries: list[dict] = []
    params = {
        "action": "query",
        "generator": "categorymembers",
        "gcmtitle": CATEGORY_TITLE,
        "gcmlimit": "500",
        "gcmtype": "file",
        "prop": "imageinfo",
        "iiprop": "url",
        "format": "json",
    }
    while True:
        url = API_URL + "?" + urllib.parse.urlencode(params)
        payload = common.fetch(url)
        if payload is None:
            raise RuntimeError(f"MediaWiki API returned 404: {url}")
        data = json.loads(payload)
        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            title = page["title"]
            body = title.removeprefix("File:")
            match = FILENAME_RE.match(body)
            if not match:
                print(f"スキップ: 想定外のカテゴリファイル名: {title}")
                continue
            imageinfo = page.get("imageinfo")
            if not imageinfo:
                print(f"スキップ: URL のないカテゴリファイル: {title}")
                continue
            entries.append({
                "dexNo": int(match.group(1)),
                "suffix": match.group(2),
                "url": imageinfo[0]["url"],
                "title": title,
            })
        continuation = data.get("continue")
        if not continuation:
            return entries
        params.update(continuation)


def build_index(entries: list[dict]) -> dict[tuple[int, str], dict]:
    return {(entry["dexNo"], aliased(entry["suffix"])): entry for entry in entries}


def raw_path(name: str) -> Path:
    return RAW_DIR / f"{common.to_filename(name)}.png"


def read_rgba(path: Path) -> Image.Image:
    """書き出し前にファイルを閉じられるよう、RGBA画像を即時読み込みする。"""
    with Image.open(path) as source:
        return source.convert("RGBA")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bulbagarden Champions menu sprite を生成する")
    common.add_common_args(parser)
    parser.add_argument("--refetch", action="store_true", help="raw/ も再取得して以後の段階を再生成する")
    args = parser.parse_args()

    pokemon = common.load_pokemon()
    selected_names = set(common.filter_names(parser, args, [entry["name"] for entry in pokemon]))
    selected_pokemon = [entry for entry in pokemon if entry["name"] in selected_names]

    print("Bulbagarden Champions_menu_sprites を列挙中...")
    manifest = fetch_bulba_manifest()
    print(f"Bulbagarden カテゴリファイル: {len(manifest)}")
    index = build_index(manifest)

    matched: list[tuple[dict, dict]] = []
    unmatched: list[dict] = []
    for entry in selected_pokemon:
        hit = index.get((entry["dexNo"], aliased(entry.get("forme"))))
        if hit:
            matched.append((entry, hit))
        else:
            unmatched.append(entry)

    print(f"対象: {len(selected_pokemon)} 件 / 一致: {len(matched)} 件 / 未マッチ: {len(unmatched)} 件（情報のみ）")

    fetched: list[str] = []
    failed: list[str] = []
    upscale_fallbacks: list[str] = []
    raw_targets = [(entry, hit) for entry, hit in matched if args.refetch or not raw_path(entry["name"]).exists()]
    if raw_targets:
        print(f"原画を取得中: {len(raw_targets)} 件")

        def download(item: tuple[dict, dict]) -> tuple[str, str | None]:
            entry, hit = item
            name = entry["name"]
            try:
                payload = common.fetch(hit["url"])
                if payload is None:
                    raise RuntimeError("404")
                # エラーページで既存の原画を上書きしないよう、保存前に検証する。
                read_rgba_from_bytes = Image.open(io.BytesIO(payload))
                read_rgba_from_bytes.verify()
                common.save_raw(payload, RAW_DIR, name)
                return name, None
            except Exception as err:  # ネットワーク・画像エラーは個別に記録する。
                return name, str(err)

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = [pool.submit(download, item) for item in raw_targets]
            for done, future in enumerate(as_completed(futures), start=1):
                name, error = future.result()
                if error:
                    failed.append(name)
                    print(f"失敗: {name} の原画取得: {error}")
                else:
                    fetched.append(name)
                if done % 50 == 0 or done == len(raw_targets):
                    print(f"  原画 {done}/{len(raw_targets)}")
    else:
        print("原画取得: すべて raw/ に存在するためスキップ")

    # ``--refetch`` で再取得した原画は加工済み画像を作り直す。
    targets: list[str] = []
    skipped = 0
    for entry, _ in matched:
        name = entry["name"]
        if name in failed or not raw_path(name).exists():
            continue
        if args.force or name in fetched or not common.outputs_exist(OUT_DIR, name):
            targets.append(name)
        else:
            skipped += 1

    generated = 0
    if targets:
        print(f"Real-ESRGAN x4plus-anime でアップスケール中: {len(targets)} 件")
        # ディレクトリ入力のため対象だけを一時領域に置き、既存結果の再処理を避ける。
        with tempfile.TemporaryDirectory(prefix="champion-upscale-") as stage_s:
            stage = Path(stage_s)
            in_dir, out_dir = stage / "in", stage / "out"
            in_dir.mkdir()
            for name in targets:
                (in_dir / raw_path(name).name).write_bytes(raw_path(name).read_bytes())
            try:
                upscale_dir(in_dir, out_dir)
            except Exception as err:  # 出力がない画像は後で個別に報告する。
                print(f"失敗: Real-ESRGAN 実行: {err}")
            for name in targets:
                source = out_dir / raw_path(name).name
                if not source.exists():
                    # 有効な原画を活かすため、出力がない画像は原画を拡大する。
                    upscale_fallbacks.append(name)
                    print(f"警告: {name} のアップスケール出力がないため原画を拡大します")
                    source = raw_path(name)
                image = read_rgba(source)
                if image.size != (OUTPUT_SIZE, OUTPUT_SIZE):
                    image = image.resize((OUTPUT_SIZE, OUTPUT_SIZE), Image.LANCZOS)
                common.save_png_and_webp(image, OUT_DIR, name, webp_quality=None)
                generated += 1
    else:
        print("アップスケール: すべて png/ と webp/ に存在するためスキップ")

    print(f"最終出力: 生成 {generated} 件 / 既存スキップ {skipped} 件")
    common.report(RAW_DIR, "raw/")
    common.report(OUT_DIR, "pokemon-champion/")
    if failed:
        print(f"失敗一覧 ({len(set(failed))} 件): {', '.join(sorted(set(failed)))}")
    else:
        print("失敗: 0 件")
    if upscale_fallbacks:
        print(f"Real-ESRGAN 原画フォールバック ({len(upscale_fallbacks)} 件): {', '.join(sorted(upscale_fallbacks))}")
    if unmatched:
        print(f"未マッチ: {len(unmatched)} 件（Champions menu sprite がないため欠損ではない）")


if __name__ == "__main__":
    main()
