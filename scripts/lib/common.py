"""各 generate_*.py が共有する処理(データ読み込み・fetch・PNG+WebP 両出力)。

各スクリプトからは次のように import する(sys.path に scripts/ を追加してから):

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lib import common
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
SPRITES_DIR = REPO_ROOT / "sprites"

USER_AGENT = "poke-sprites-fetch/1.0 (local dev tool)"

# Windows のファイル名に使えない文字の置換表。和名に含まれるのは「タイプ:ヌル」のコロンのみ。
_FILENAME_REPLACEMENTS = {":": "："}


def to_filename(name: str) -> str:
    """和名をファイル名(拡張子なし)にする。ファイル名に使えない文字は全角へ置換する。"""
    for src, dst in _FILENAME_REPLACEMENTS.items():
        name = name.replace(src, dst)
    return name


def load_pokemon() -> list[dict]:
    """data/pokemon.json (name/dexNo/imageId/forme/types/regulations) を返す。"""
    return json.loads((DATA_DIR / "pokemon.json").read_text(encoding="utf-8"))


def load_items() -> list[dict]:
    """data/items.json (name/spritePath/regulations) を返す。"""
    return json.loads((DATA_DIR / "items.json").read_text(encoding="utf-8"))


def fetch(url: str, *, retries: int = 3, timeout: int = 30, wait_sec: float = 1.0) -> bytes | None:
    """URL を取得する。404 なら None、それ以外の失敗は retries 回リトライしてから RuntimeError。"""
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as res:
                return res.read()
        except urllib.error.HTTPError as err:
            if err.code == 404:
                return None
            last_err = err
        except Exception as err:  # noqa: BLE001 - ネットワーク由来は全部リトライ対象
            last_err = err
        if attempt < retries - 1:
            time.sleep(wait_sec * (attempt + 1))
    raise RuntimeError(f"{url} の取得に失敗しました: {last_err}")


def save_raw(data: bytes, out_dir: Path, name: str, ext: str = "png") -> Path:
    """原画をそのまま raw/ 等へ保存する(無加工)。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{to_filename(name)}.{ext}"
    path.write_bytes(data)
    return path


def save_png_and_webp(
    im: Image.Image, out_dir: Path, name: str, *, webp_quality: int | None = None
) -> tuple[Path, Path]:
    """加工済み画像を {name}.png と {name}.webp の両方で保存する。

    webp_quality が None なら lossless WebP、整数なら lossy(quality 指定)。
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = to_filename(name)
    im = im.convert("RGBA")
    png_path = out_dir / f"{stem}.png"
    webp_path = out_dir / f"{stem}.webp"
    im.save(png_path, "PNG", optimize=True)
    if webp_quality is None:
        im.save(webp_path, "WEBP", lossless=True, quality=100, method=6)
    else:
        im.save(webp_path, "WEBP", quality=webp_quality, method=6)
    return png_path, webp_path


def add_common_args(parser: argparse.ArgumentParser) -> None:
    """--force / --names を追加する。"""
    parser.add_argument("--force", action="store_true", help="既に存在する画像も処理し直す")
    parser.add_argument(
        "--names",
        help="処理する和名をカンマ区切りで指定する(欠損分だけを追加するとき用)",
    )


def filter_names(parser: argparse.ArgumentParser, args: argparse.Namespace, known: list[str]) -> list[str]:
    """--names が指定されていればその和名だけに絞る(未知の和名は parser.error)。"""
    if not args.names:
        return known
    requested = {v.strip() for v in args.names.split(",") if v.strip()}
    unknown = requested - set(known)
    if unknown:
        parser.error(f"data に存在しない和名が指定されました: {sorted(unknown)}")
    return [n for n in known if n in requested]


def outputs_exist(out_dir: Path, name: str) -> bool:
    """PNG と WebP の両方が既にあれば True。"""
    stem = to_filename(name)
    return (out_dir / f"{stem}.png").exists() and (out_dir / f"{stem}.webp").exists()


def report(out_dir: Path, label: str) -> None:
    files = sorted(p for p in out_dir.glob("*") if p.is_file())
    total = sum(p.stat().st_size for p in files)
    print(f"{label}: {len(files)} ファイル / {total / 1024 / 1024:.2f} MB")
