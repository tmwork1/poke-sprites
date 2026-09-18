"""画像生成スクリプトの共通処理。

CSVデータの読み込み、URL取得、原画保存、PNG・WebP出力を提供する。
和名をWindowsで使えるファイル名に変換し、既存出力の確認や引数処理も共通化する。
"""

from __future__ import annotations

import argparse
import csv
import time
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
SPRITES_DIR = REPO_ROOT / "sprites"

USER_AGENT = "poke-sprites-fetch/1.0 (local dev tool)"

# Windowsで使えない文字を全角へ置換する。
_FILENAME_REPLACEMENTS = {":": "："}


def to_filename(name: str) -> str:
    """和名を拡張子なしの安全なファイル名へ変換する。"""
    for src, dst in _FILENAME_REPLACEMENTS.items():
        name = name.replace(src, dst)
    return name


def _load_csv(filename: str) -> list[dict[str, str]]:
    """data内のヘッダ付きCSVを読み、名前がない行を除く。"""
    with (DATA_DIR / filename).open(encoding="utf-8", newline="") as f:
        return [row for row in csv.DictReader(f) if row.get("name")]


def load_pokemon() -> list[dict]:
    """pokemon.csvを読み、番号はint、空のフォームはNoneで返す。"""
    return [
        {
            "name": row["name"],
            "dexNo": int(row["dexNo"]),
            "imageId": int(row["imageId"]) if row["imageId"] else None,
            "forme": row["forme"] or None,
        }
        for row in _load_csv("pokemon.csv")
    ]


def load_items() -> list[dict]:
    """items.csvを読み、空のslugはNoneで返す。"""
    return [{"name": row["name"], "slug": row["slug"] or None} for row in _load_csv("items.csv")]


def fetch(url: str, *, retries: int = 3, timeout: int = 30, wait_sec: float = 1.0) -> bytes | None:
    """URLを取得し、404はNone、それ以外は再試行後に例外とする。"""
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
        except Exception as err:  # noqa: BLE001 - 通信エラーはすべて再試行する
            last_err = err
        if attempt < retries - 1:
            time.sleep(wait_sec * (attempt + 1))
    raise RuntimeError(f"{url} の取得に失敗しました: {last_err}")


def save_raw(data: bytes, out_dir: Path, name: str, ext: str = "png") -> Path:
    """原画を無加工で指定先へ保存する。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{to_filename(name)}.{ext}"
    path.write_bytes(data)
    return path


def save_png_and_webp(
    im: Image.Image, out_dir: Path, name: str, *, webp_quality: int | None = None
) -> tuple[Path, Path]:
    """加工済み画像をPNGとWebPで保存する。Noneなら可逆WebPを使う。"""
    stem = to_filename(name)
    im = im.convert("RGBA")
    png_path = out_dir / "png" / f"{stem}.png"
    webp_path = out_dir / "webp" / f"{stem}.webp"
    png_path.parent.mkdir(parents=True, exist_ok=True)
    webp_path.parent.mkdir(parents=True, exist_ok=True)
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
    """--names指定時は対象を絞り、未知の名前はエラーにする。"""
    if not args.names:
        return known
    requested = {v.strip() for v in args.names.split(",") if v.strip()}
    unknown = requested - set(known)
    if unknown:
        parser.error(f"data に存在しない和名が指定されました: {sorted(unknown)}")
    return [n for n in known if n in requested]


def outputs_exist(out_dir: Path, name: str) -> bool:
    """out_dir/png/ と out_dir/webp/ の両方に既にあれば True。"""
    stem = to_filename(name)
    return (out_dir / "png" / f"{stem}.png").exists() and (out_dir / "webp" / f"{stem}.webp").exists()


def report(out_dir: Path, label: str) -> None:
    files = sorted(p for p in out_dir.rglob("*") if p.is_file())
    total = sum(p.stat().st_size for p in files)
    print(f"{label}: {len(files)} ファイル / {total / 1024 / 1024:.2f} MB")
