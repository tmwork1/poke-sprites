"""PokeAPI の公式アートワークを 320px WebP に加工して public/pokemon-artwork/ に配置する。

このリポジトリ向けの変更: 入力は data/pokemon.json、出力は
sprites/pokemon-artwork/、ファイル名は和名にする。原画は raw/ に保存し、PNG と
WebP の両方を出力する。--force/--names に対応し、raw/ があれば再取得せず再生成する。

元の設計理由: ダウンロード直後のファイルをそのまま置かない。
ダウンロード後は 1KB 未満なので別ファイルでコンパクト化したが、公式アートワークは
475x475 / 平均 45.8KB（執筆時点）である。1284 件すべてを置くと 178.6MB となり、
Git にもデプロイにも重い。最大表示は 160px の Retina (2 倍) で十分なので 320px に
LANCZOS で一回だけ縮小し、WebP quality 82 で保存する。quality 75 まで下げても
節約できるサイズは小さく、公式アートワークは色数が多いため画質を優先する。

raw.githubusercontent.com の Cache-Control は max-age=300 であり、全件を逐次取得
すると DNS/TCP/TLS の待ち時間が支配的になる。そのため取得は 8 並列にする。
"""

from __future__ import annotations

import argparse
import io
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import common  # noqa: E402


OUT_DIR = Path(__file__).resolve().parents[2] / "sprites" / "pokemon-artwork"
RAW_DIR = OUT_DIR / "raw"
ARTWORK_URL = (
    "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/"
    "other/official-artwork/{image_id}.png"
)

# /pokemon/[name] と /share/[slug] の 160px を Retina (2 倍) で表示するため 320px。
OUTPUT_SIZE = 320
# q82 は 320px で平均 18.0KB/枚。q75 との差が小さいため公式絵の画質を優先する。
WEBP_QUALITY = 82
MAX_WORKERS = 8


def raw_path(name: str) -> Path:
    """共通の Windows 安全なファイル名規則で raw の保存先を返す。"""
    return RAW_DIR / f"{common.to_filename(name)}.png"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PokeAPI 公式アートワークを PNG + WebP に加工して sprites/pokemon-artwork/ に保存する"
    )
    common.add_common_args(parser)
    parser.add_argument(
        "--refetch",
        action="store_true",
        help="raw/ にある原画も再取得する（--force と組み合わせなくても raw を更新する）",
    )
    args = parser.parse_args()

    entries = common.load_pokemon()
    known_names = [entry["name"] for entry in entries]
    names = common.filter_names(parser, args, known_names)
    selected = [entry for entry in entries if entry["name"] in set(names)]

    missing_data_ids = [entry["name"] for entry in selected if entry.get("imageId") is None]
    eligible = [entry for entry in selected if entry.get("imageId") is not None]
    targets = [
        entry
        for entry in eligible
        if args.force or args.refetch or not common.outputs_exist(OUT_DIR, entry["name"])
    ]
    skipped = len(selected) - len(targets) - len(missing_data_ids)
    print(f"対象: {len(selected)} 件（出力済みスキップ: {skipped} 件、処理: {len(targets)} 件）")
    print(f"出力: {OUTPUT_SIZE}px PNG + WebP (quality={WEBP_QUALITY}) / 取得並列数: {MAX_WORKERS}")

    missing_upstream: list[int] = []
    failures: list[str] = []
    generated = 0

    def work(entry: dict) -> tuple[str, int | None, str | None]:
        name = entry["name"]
        image_id = int(entry["imageId"])
        source = raw_path(name)
        try:
            if source.exists() and not args.refetch:
                data = source.read_bytes()
            else:
                data = common.fetch(ARTWORK_URL.format(image_id=image_id), timeout=60)
                if data is None:
                    return name, image_id, "missing"
                source = common.save_raw(data, RAW_DIR, name)
            with Image.open(io.BytesIO(data)) as image:
                resized = image.convert("RGBA").resize((OUTPUT_SIZE, OUTPUT_SIZE), Image.LANCZOS)
            common.save_png_and_webp(resized, OUT_DIR, name, webp_quality=WEBP_QUALITY)
            return name, None, None
        except Exception as err:  # noqa: BLE001 - 全件処理を継続して失敗一覧を出す
            return name, None, str(err)

    if targets:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(work, entry) for entry in targets]
            for done, future in enumerate(as_completed(futures), start=1):
                name, missing_id, error = future.result()
                if missing_id is not None:
                    missing_upstream.append(missing_id)
                elif error is not None:
                    failures.append(f"{name}: {error}")
                else:
                    generated += 1
                if done % 100 == 0 or done == len(targets):
                    print(f"  進捗: {done}/{len(targets)}")

    covered = sum(1 for entry in eligible if common.outputs_exist(OUT_DIR, entry["name"]))
    print()
    print(f"今回生成: {generated} 件 / 出力済み: {covered}/{len(eligible)} 件")
    common.report(OUT_DIR, "pokemon-artwork（加工済み）")
    common.report(RAW_DIR, "pokemon-artwork/raw（原画）")
    if missing_data_ids:
        print(f"data に imageId がない名前 ({len(missing_data_ids)} 件): {missing_data_ids}")
    if missing_upstream:
        print(f"上流にない imageId ({len(set(missing_upstream))} 件): {sorted(set(missing_upstream))}")
    else:
        print("上流にない imageId: なし")
    if failures:
        print(f"失敗 ({len(failures)} 件):")
        for failure in failures:
            print(f"  - {failure}")
    else:
        print("失敗: なし")


if __name__ == "__main__":
    main()
