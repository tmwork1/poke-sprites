"""PokeAPIのタイプ画像から通常・テラスタル用アイコンを生成する。

入力は各出力先の raw/ に保存した原画、出力は sprites/types/ と
sprites/tera-types/ の PNG・lossless WebP。通常タイプは白色系マークを
背景から分離して縮小し、円形アルファマスクを適用する。テラスタルは
英字部分を除去して左右の縁をつなぎ、正方形に整形する。
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

try:
    from PIL import Image, ImageChops, ImageDraw
except ImportError as exc:  # pragma: no cover
    print(
        "Pillow が見つかりません。`pip install Pillow` を実行してから再実行してください。",
        file=sys.stderr,
    )
    raise SystemExit(1) from exc

import common


REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "sprites" / "types"
TERA_OUT_DIR = REPO_ROOT / "sprites" / "tera-types"

SPRITES_BASE = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/types/generation-ix/scarlet-violet"

# 和名とPokeAPIタイプIDの対応。
TYPE_IDS_JA = {
    1: "ノーマル",
    2: "かくとう",
    3: "ひこう",
    4: "どく",
    5: "じめん",
    6: "いわ",
    7: "むし",
    8: "ゴースト",
    9: "はがね",
    10: "ほのお",
    11: "みず",
    12: "くさ",
    13: "でんき",
    14: "エスパー",
    15: "こおり",
    16: "ドラゴン",
    17: "あく",
    18: "フェアリー",
    19: "ステラ",
}

# 表示品質を保つ最終出力サイズ(px)。
OUTPUT_SIZE = 96

# 背景の明るい色を誤検出しないための前景しきい値。
WHITE_CHANNEL_MIN = 245
ALPHA_MIN = 100

# アイコン内部の隙間だけを連結する上限(px)。英字との間隔より小さく保つ。
GAP_MERGE_THRESHOLD = 6

# 背景の最大値159を上回り、アンチエイリアス縁を含める粗い前景しきい値。
ROUGH_WHITE_MIN = 190
ROUGH_ALPHA_MIN = 60

# 円形内に十分な余白を確保するマーク縮小率。
MARK_SCALE = 0.84

# 残像を防ぐためにマスクへ加える余白(px)。
MARK_MASK_DILATE = 1

# 円周のジャギーを抑えるための描画倍率。
CIRCLE_MASK_SUPERSAMPLE = 4


def load_raw(type_id: int, name: str, *, tera: bool, refetch: bool) -> Image.Image:
    """raw/ の原画を読み込み、必要なら取得して保存する。"""
    out_dir = TERA_OUT_DIR if tera else OUT_DIR
    raw_path = out_dir / "raw" / f"{common.to_filename(name)}.png"
    if refetch or not raw_path.exists():
        url = f"{SPRITES_BASE}/Tera/{type_id}.png" if tera else f"{SPRITES_BASE}/{type_id}.png"
        data = common.fetch(url)
        if data is None:
            raise RuntimeError(f"原画が見つかりません: {url}")
        raw_path = common.save_raw(data, out_dir / "raw", name)
    with Image.open(raw_path) as raw:
        return raw.convert("RGBA")


def _is_white_fg(pixel: tuple[int, int, int, int]) -> bool:
    r, g, b, a = pixel
    return a >= ALPHA_MIN and min(r, g, b) >= WHITE_CHANNEL_MIN


def detect_icon_x_range(im: Image.Image) -> tuple[int, int]:
    """左側マークの水平範囲 [x0, x1) を検出する。"""
    w, h = im.size
    px = im.load()
    fg_cols = [any(_is_white_fg(px[x, y]) for y in range(h)) for x in range(w)]

    i = 0
    while i < w and not fg_cols[i]:
        i += 1
    if i == w:
        raise RuntimeError("前景(白色系)ピクセルが1つも見つかりませんでした。しきい値を見直してください。")

    start = i
    end = i
    while i < w:
        if fg_cols[i]:
            end = i + 1
            i += 1
        else:
            gap_start = i
            while i < w and not fg_cols[i]:
                i += 1
            if (i - gap_start) >= GAP_MERGE_THRESHOLD:
                break
    return start, end


def crop_icon_square(im: Image.Image) -> tuple[Image.Image, tuple[int, int, int, int]]:
    """マーク中心を基準に、画像高と同じ一辺の正方形を切り出す。"""
    w, h = im.size
    x0, x1 = detect_icon_x_range(im)
    cx = (x0 + x1) / 2

    side = h
    crop_x0 = round(cx - side / 2)
    crop_x0 = max(0, min(crop_x0, w - side))
    box = (crop_x0, 0, crop_x0 + side, h)

    cropped = im.crop(box)
    return cropped, box


def _is_rough_fg(pixel: tuple[int, int, int, int]) -> bool:
    r, g, b, a = pixel
    return a >= ROUGH_ALPHA_MIN and min(r, g, b) >= ROUGH_WHITE_MIN


def _dilate_mask(mask: list[list[bool]], radius: int) -> list[list[bool]]:
    """マーク周辺のアンチエイリアス縁を含めるため、マスクを膨張する。"""
    if radius <= 0:
        return mask
    h = len(mask)
    w = len(mask[0])
    offsets = [
        (dx, dy)
        for dy in range(-radius, radius + 1)
        for dx in range(-radius, radius + 1)
        if dx * dx + dy * dy <= radius * radius + radius
    ]
    out = [[False] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            if not mask[y][x]:
                continue
            for dx, dy in offsets:
                yy, xx = y + dy, x + dx
                if 0 <= yy < h and 0 <= xx < w:
                    out[yy][xx] = True
    return out


def _row_fill_background(im: Image.Image, rough_mask: list[list[bool]]) -> Image.Image:
    """マーク位置を同じ行の近傍色で埋め、背景画像を作る。"""
    w, h = im.size
    px = im.load()
    out = Image.new("RGBA", (w, h))
    out_px = out.load()
    for y in range(h):
        row_is_mark = rough_mask[y]
        for x in range(w):
            if not row_is_mark[x]:
                out_px[x, y] = px[x, y]
                continue
            left = next((xx for xx in range(x - 1, -1, -1) if not row_is_mark[xx]), None)
            right = next((xx for xx in range(x + 1, w) if not row_is_mark[xx]), None)
            if left is not None and (right is None or (x - left) <= (right - x)):
                out_px[x, y] = px[left, y]
            elif right is not None:
                out_px[x, y] = px[right, y]
            else:
                out_px[x, y] = px[x, y]  # 行全体がマーク(通常は起こらない)のフォールバック
    return out


def _compute_mark_alpha(im: Image.Image, bg: Image.Image) -> list[list[float]]:
    """背景との差から、白色マークのアルファ値を求める。"""
    w, h = im.size
    px = im.load()
    bg_px = bg.load()
    alpha = [[0.0] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            br, bgc, bb, _ = bg_px[x, y]
            ts = []
            for c, bc in ((r, br), (g, bgc), (b, bb)):
                denom = 255 - bc
                if denom > 0:
                    ts.append((c - bc) / denom)
            t = sum(ts) / len(ts) if ts else 0.0
            alpha[y][x] = max(0.0, min(1.0, t)) * (a / 255.0)
    return alpha


def build_mark_shrunk_icon(cropped: Image.Image, size: int) -> Image.Image:
    """マークだけを縮小して背景へ再合成し、指定サイズに整形する。

    背景を維持してマークの見切れを防ぎ、リサイズは一度だけ行う。"""
    w, h = cropped.size
    px = cropped.load()
    rough_mask = [[_is_rough_fg(px[x, y]) for x in range(w)] for y in range(h)]
    bg = _row_fill_background(cropped, _dilate_mask(rough_mask, MARK_MASK_DILATE))
    mark_alpha = _compute_mark_alpha(cropped, bg)

    mark_layer = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    mark_px = mark_layer.load()
    for y in range(h):
        for x in range(w):
            mark_px[x, y] = (255, 255, 255, round(255 * mark_alpha[y][x]))

    bg_resized = bg.resize((size, size), Image.LANCZOS)
    new_side = round(size * MARK_SCALE)
    mark_resized = mark_layer.resize((new_side, new_side), Image.LANCZOS)
    mark_canvas = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    offset = (size - new_side) // 2
    mark_canvas.paste(mark_resized, (offset, offset))

    result = bg_resized.convert("RGBA")
    result.alpha_composite(mark_canvas)
    return result


def _circular_mask(size: int) -> Image.Image:
    """アンチエイリアス済みの円形アルファマスクを作る。"""
    big = size * CIRCLE_MASK_SUPERSAMPLE
    mask_big = Image.new("L", (big, big), 0)
    draw = ImageDraw.Draw(mask_big)
    draw.ellipse((0, 0, big - 1, big - 1), fill=255)
    return mask_big.resize((size, size), Image.LANCZOS)


def apply_circular_mask(im: Image.Image) -> Image.Image:
    """正方形画像に円形アルファマスクを適用する。"""
    w, h = im.size
    if w != h:
        raise ValueError(f"円形マスクは正方形画像のみ対応: got {w}x{h}")
    mask = _circular_mask(w)
    result = im.convert("RGBA")
    r, g, b, a = result.split()
    masked_alpha = ImageChops.multiply(a, mask)
    result.putalpha(masked_alpha)
    return result


def _column_alpha_span(im: Image.Image, x: int) -> tuple[int, int] | None:
    """列 x の不透明画素の最小・最大 y を返す。なければ None。"""
    h = im.size[1]
    px = im.load()
    ys = [y for y in range(h) if px[x, y][3] > ALPHA_MIN]
    return (ys[0], ys[-1]) if ys else None


def detect_frame_taper(im: Image.Image) -> tuple[tuple[int, int], int]:
    """テラスタイプの胴体位置と両端の尖った縁の幅を検出する。

    胴体の不透明範囲の最頻値を使い、幅が異なるアイコンでも安定して判定する。"""
    w = im.size[0]
    spans = [_column_alpha_span(im, x) for x in range(w)]
    plateau = Counter(s for s in spans if s is not None).most_common(1)[0][0]
    left_width = next(x for x in range(w) if spans[x] == plateau)
    right_width = w - 1 - max(x for x in range(w) if spans[x] == plateau)
    return plateau, max(left_width, right_width)


def stitch_tera_icon(im: Image.Image, icon_x_range: tuple[int, int]) -> Image.Image:
    """英字部分を除去し、アイコンと左右の縁をつなぎ合わせる。

    実ピクセルの右端を使うことで、縁の形状を保つ。"""
    w, h = im.size
    x0, x1 = icon_x_range
    _plateau, taper_width = detect_frame_taper(im)
    cut = x0 + x1 - taper_width

    left_piece = im.crop((0, 0, cut, h))
    right_piece = im.crop((w - taper_width, 0, w, h))

    assembled = Image.new("RGBA", (cut + taper_width, h), (0, 0, 0, 0))
    assembled.paste(left_piece, (0, 0))
    assembled.paste(right_piece, (cut, 0))
    return assembled


def pad_to_square(im: Image.Image) -> Image.Image:
    """横長画像を透明パディングで正方形にする。"""
    w, h = im.size
    side = max(w, h)
    result = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    result.paste(im, ((side - w) // 2, (side - h) // 2))
    return result


def generate_one(im: Image.Image, *, tera: bool) -> tuple[Image.Image, tuple[int, int, int, int]]:
    if tera:
        icon_x_range = detect_icon_x_range(im)
        stitched = stitch_tera_icon(im, icon_x_range)
        box = (0, 0, stitched.width, stitched.height)
        result = pad_to_square(stitched).resize((OUTPUT_SIZE, OUTPUT_SIZE), Image.LANCZOS)
    else:
        cropped, box = crop_icon_square(im)
        result = apply_circular_mask(build_mark_shrunk_icon(cropped, OUTPUT_SIZE))

    return result, box


def main() -> None:
    parser = argparse.ArgumentParser(description="通常・テラスタルのタイプアイコンを生成する")
    common.add_common_args(parser)
    parser.add_argument("--refetch", action="store_true", help="raw/ の原画も再取得する")
    parser.add_argument("--tera-only", action="store_true", help="テラスタルだけ生成する")
    parser.add_argument("--normal-only", action="store_true", help="通常タイプだけ生成する")
    args = parser.parse_args()
    if args.tera_only and args.normal_only:
        parser.error("--tera-only と --normal-only は同時に指定できません")

    names = common.filter_names(parser, args, list(TYPE_IDS_JA.values()))
    selected = [(type_id, name) for type_id, name in TYPE_IDS_JA.items() if name in names]
    kinds = []
    if not args.tera_only:
        kinds.append(False)
    if not args.normal_only:
        kinds.append(True)

    generated = skipped = 0
    failures: list[str] = []
    print(f"出力先: {OUT_DIR} / {TERA_OUT_DIR}")
    print(f"{'type':>4} {'ja':<8} {'kind':<6} {'crop-box':<20} {'file':<40} size")
    for type_id, ja in selected:
        for tera in kinds:
            out_dir = TERA_OUT_DIR if tera else OUT_DIR
            kind = "tera" if tera else "normal"
            if not args.force and common.outputs_exist(out_dir, ja):
                skipped += 1
                print(f"{type_id:>4} {ja:<8} {kind:<6} skip (outputs exist)")
                continue
            try:
                image = load_raw(type_id, ja, tera=tera, refetch=args.refetch)
                result, box = generate_one(image, tera=tera)
                png_path, webp_path = common.save_png_and_webp(result, out_dir, ja, webp_quality=None)
                generated += 1
                rel = png_path.relative_to(REPO_ROOT)
                print(f"{type_id:>4} {ja:<8} {kind:<6} {str(box):<20} {str(rel):<40} {png_path.stat().st_size + webp_path.stat().st_size}B")
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{kind}/{ja}: {exc}")
                print(f"{type_id:>4} {ja:<8} {kind:<6} FAILED: {exc}")

    common.report(OUT_DIR, "通常タイプ出力")
    common.report(TERA_OUT_DIR, "テラスタルタイプ出力")
    total_bytes = sum(p.stat().st_size for directory in (OUT_DIR, TERA_OUT_DIR) for p in directory.glob("*") if p.is_file())
    print(f"完了: 生成 {generated} 件、スキップ {skipped} 件、失敗 {len(failures)} 件。合計サイズ: {total_bytes:,} バイト ({total_bytes / 1024:.1f} KiB)")
    if failures:
        print("失敗一覧:")
        print("\n".join(failures))


if __name__ == "__main__":
    main()
