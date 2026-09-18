"""Generate Pokémon Champions menu sprites from Bulbagarden.

This ports poke-guide's measured design: Bulbagarden's 128px Champions menu
sprites are first enlarged four times with Real-ESRGAN ``x4plus-anime`` and
then reduced once with LANCZOS to the display size.  This preserves sharper
pixel edges than scaling the original sprite directly.  Bulbagarden category
file names encode only a dex number and optional form suffix, so they are
matched against the complete Pokémon master data by ``(dexNo, forme)``;
``F → Female`` and ``Super → Jumbo`` are the two observed naming aliases.

Changes for poke-sprites: inputs are ``data/pokemon.json`` and outputs are
Japanese-name files under ``sprites/pokemon-champion/``.  Original downloads
are retained in ``raw/`` and Real-ESRGAN results in ``upscaled/``.  Final
320px assets are emitted as both PNG and lossless WebP.  ``--force`` replaces
only final assets, ``--names`` filters Japanese names, and ``--refetch`` also
refreshes raw downloads (and their derived upscale).
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import tempfile
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import common
from realesrgan_tool import upscale_dir

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "sprites" / "pokemon-champion"
RAW_DIR = OUT_DIR / "raw"
UPSCALED_DIR = OUT_DIR / "upscaled"

# The largest displayed menu sprite is 160px at retina 2x, hence a 320px
# final asset.  This is deliberately the same one-pass LANCZOS reduction used
# by poke-guide after the four-times Real-ESRGAN result.
OUTPUT_SIZE = 320

API_URL = "https://archives.bulbagarden.net/w/api.php"
CATEGORY_TITLE = "Category:Champions_menu_sprites"
FORME_ALIASES = {
    "f": "female",
    "super": "jumbo",
}
FILENAME_RE = re.compile(r"^Menu[ _]CP[ _](\d{4})(?:[-_](.+))?\.png$", re.IGNORECASE)
MAX_WORKERS = 8


def norm(value: str | None) -> str:
    """Normalize suffixes so spacing, case, underscores, and hyphens match alike."""
    if not value:
        return ""
    collapsed = " ".join(value.strip().lower().replace("_", " ").replace("-", " ").split())
    return collapsed.replace(" ", "-")


def aliased(value: str | None) -> str:
    return FORME_ALIASES.get(norm(value), norm(value))


def fetch_bulba_manifest() -> list[dict]:
    """Fetch every category file as ``dexNo``, form suffix, URL, and title."""
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


def upscaled_path(name: str) -> Path:
    return UPSCALED_DIR / f"{common.to_filename(name)}.png"


def read_rgba(path: Path) -> Image.Image:
    """Load eagerly so the source handle can be closed before writing output."""
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
                # Validate before replacing a retained raw image with an error page.
                read_rgba_from_bytes = Image.open(io.BytesIO(payload))
                read_rgba_from_bytes.verify()
                common.save_raw(payload, RAW_DIR, name)
                return name, None
            except Exception as err:  # network and image errors are per asset
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

    # ``--refetch`` means a newly downloaded raw invalidates its derived image.
    upscale_targets = [
        entry["name"] for entry, _ in matched
        if entry["name"] not in failed
        and raw_path(entry["name"]).exists()
        and (args.refetch and entry["name"] in fetched or not upscaled_path(entry["name"]).exists())
    ]
    if upscale_targets:
        print(f"Real-ESRGAN x4plus-anime でアップスケール中: {len(upscale_targets)} 件")
        # The upstream command accepts directories, so stage only missing items
        # as inputs.  Its output is nevertheless written directly and durably
        # to ``upscaled/``; existing upscaled files are never reprocessed.
        with tempfile.TemporaryDirectory(prefix="champion-upscale-input-") as stage_s:
            stage = Path(stage_s)
            for name in upscale_targets:
                (stage / raw_path(name).name).write_bytes(raw_path(name).read_bytes())
            try:
                upscale_dir(stage, UPSCALED_DIR)
            except Exception as err:  # report individual missing output below
                print(f"失敗: Real-ESRGAN 実行: {err}")
            for name in upscale_targets:
                if not upscaled_path(name).exists():
                    # Keep poke-guide's per-file fallback: a missing result
                    # does not discard an otherwise valid raw download.
                    upscale_fallbacks.append(name)
                    print(f"警告: {name} のアップスケール出力がないため原画で縮小します")
    else:
        print("アップスケール: すべて upscaled/ に存在するためスキップ")

    generated = 0
    skipped = 0
    for entry, _ in matched:
        name = entry["name"]
        if name in failed:
            continue
        if not args.force and common.outputs_exist(OUT_DIR, name):
            skipped += 1
            continue
        source = upscaled_path(name)
        if not source.exists():
            # Preserve poke-guide's fallback behavior for a missing individual
            # Real-ESRGAN result.
            source = raw_path(name)
        if not source.exists():
            failed.append(name)
            print(f"失敗: {name} の加工元がありません")
            continue
        image = read_rgba(source).resize((OUTPUT_SIZE, OUTPUT_SIZE), Image.LANCZOS)
        common.save_png_and_webp(image, OUT_DIR, name, webp_quality=None)
        generated += 1

    print(f"最終出力: 生成 {generated} 件 / 既存スキップ {skipped} 件")
    common.report(RAW_DIR, "raw/")
    common.report(UPSCALED_DIR, "upscaled/")
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
