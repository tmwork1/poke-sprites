# poke-sprites

自作アプリで使われているポケモンやタイプ、アイテムなどの画像の管理をこのレポジトリに集約する。

## 目的

- 自作アプリの画像ソースを集約する
- 画像の入手経路を明確化し、入手・更新スクリプトを整備する

## ルール

- スクリプトはすべて Python で作る(依存は `requirements.txt`、実行は `python scripts/<カテゴリ>/generate_*.py`)
- 画像ファイル名は和名に統一する(例: `sprites/items/たべのこし.png`)
- 加工済み画像は **PNG と WebP の両方**を同じディレクトリに並べて持つ(`{和名}.png` / `{和名}.webp`)
- 入手した**原画は加工せず `raw/` に保持する**(入手経路を明確化し、加工方針を変えたときにネットワークなしで再生成できるようにする)
- 画像は事前生成してリポジトリにコミットする(利用側アプリは実行時に外部サイトへアクセスしない)

## ディレクトリ構成

```
data/
  pokemon.json              # poke-guide の master-data をコピー (name/dexNo/imageId/forme/types)
  items.json                # poke-guide の master-data をコピー (name/spritePath)
scripts/
  lib/common.py             # 共通処理 (data 読み込み、リトライ付き fetch、PNG+WebP 両出力)
  pokemon-artwork/generate_pokemon_artwork.py
  pokemon-champion/generate_pokemon_champion.py
  pokemon-champion/generate_pokemon_champion_variants.py
  pokemon-champion/realesrgan_tool.py
  pokemon-champion/.cache/  # Real-ESRGAN 実行ファイル (gitignore)
  items/generate_items.py
  types/generate_types.py   # 通常タイプ・テラスタルタイプの両方を生成
  ui/generate_ui.py
sprites/
  pokemon-artwork/
    raw/{和名}.png            # PokeAPI official-artwork 原画 (475px)
    {和名}.png / .webp        # 320px
  pokemon-champion/
    raw/{和名}.png            # bulbagarden Champions menu sprite 原画 (128px)
    upscaled/{和名}.png       # Real-ESRGAN x4plus-anime 出力 (512px、縮小前)
    {和名}.png / .webp        # 320px
    icon/{和名}.png / .webp   # 96px
    medium/{和名}.png / .webp # 192px
  items/
    raw/{和名}.png            # serebii.net 原画 (160px、旧世代アイテムは 40px)
    {和名}.png / .webp        # 96px 正規化済み
  types/
    raw/{和名}.png            # PokeAPI 横長リボン原画
    {和名}.png / .webp        # 96px 円形
  tera-types/
    raw/{和名}.png
    {和名}.png / .webp        # 96px 正方形
  ui/
    raw/テラスタル.png         # GameWith 原画
    テラスタル.png / .webp
```

## 画像仕様

| カテゴリ | 入手元 | 対象 | 加工 | 出力サイズ | WebP 品質 |
|---|---|---|---|---|---|
| ポケモン公式絵 | PokeAPI/sprites `pokemon/other/official-artwork/{imageId}.png` | `data/pokemon.json` 全件(上流に存在するもの) | LANCZOS で 1 回縮小 | 320px | q82 |
| ポケモン立ち絵 | bulbagarden `Category:Champions_menu_sprites`(MediaWiki API で列挙) | `data/pokemon.json` のうち dexNo+forme が一致するもの(Champions 実装済みのみ) | Real-ESRGAN x4plus-anime で 4 倍 → LANCZOS で縮小 | 320 / 192 / 96px | 320: lossless、icon/medium: q90 |
| アイテム | serebii.net `itemdex/sprites/{za,sv,}/` | `data/items.json` 273 件(spritePath 欠損は手動対応表で補完) | alpha bbox 検出 → 面積基準の正方形クロップ → LANCZOS 1 回 | 96px | lossless |
| タイプ | PokeAPI/sprites `types/generation-ix/scarlet-violet/{id}.png` | 19 種(ステラ含む) | マーク検出・縮小・円形マスク | 96px | lossless |
| テラスタルタイプ | 同上 `Tera/{id}.png` | 19 種 | リボン繋ぎ合わせで正方形化 | 96px | lossless |
| テラスタル発動ボタン | GameWith `img.gamewith.jp/article_tools/pokemon-sv/gacha/map_icon_terra2.png` | 1 枚 | 無加工(両形式変換のみ) | 原寸 | lossless |

- 加工ロジック・定数(ALPHA_MIN、TARGET_AREA_SIDE_FRACTION、MARK_SCALE 等)は poke-guide のスクリプトをそのまま踏襲する。実測に基づく設計理由は各スクリプトの docstring に残す。
- `raw/` と `upscaled/` は入手元・ツールの出力形式のまま(PNG のみ)保持する。両形式出力は加工済み画像に対してのみ行う。
- ファイル名の和名は `data/*.json` の `name` をそのまま使う。フォルム違いは `メガフシギバナ`、`フシギバナ(キョダイ)`、`ロトム(ヒート)` のように name に含まれる表記のまま。タイプは `ほのお` などタイプ名そのもの。Windows のファイル名に使えない文字は全角に置換する(`タイプ:ヌル` → `タイプ：ヌル`、`scripts/lib/common.py` の `to_filename()` に集約)。

## 開発手順(初期整備)

1. `../poke-guide/public/master-data/autocomplete/{pokemon,items}.json` を `data/` にコピーする
2. `../poke-guide/scripts/` の各 generate スクリプトを移植する。変更点:
   - 入力を `data/*.json`、出力を `sprites/<カテゴリ>/` にする
   - ファイル名を imageId / typeId から和名に変える
   - 原画を `raw/`(立ち絵はさらに `upscaled/`)に保存する
   - 出力を PNG + WebP の両方にする(`scripts/lib/common.py` に共通化)
   - 既存ファイルはスキップし `--force` で上書き、`--names`(和名カンマ区切り)で対象を絞れるようにする
3. 各スクリプトを実行して画像を生成し、コミットする

## 補足

- poke-guide のアイテム画像はすでに serebii.net から取得済み。GameWith 依存として残っているのはテラスタル発動ボタン画像 1 枚のみで、これは GameWith から取得してリポジトリに固定する。
- Real-ESRGAN は ncnn-vulkan 版の実行ファイルを初回に GitHub Releases から取得する(Vulkan 対応 GPU が必要。動作確認は Windows のみ)。
