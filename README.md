# poke-sprites

自作ポケモンアプリで使う画像(ポケモン・アイテム・タイプなど)を一か所に集めたリポジトリです。画像はすべて生成済みでコミットされているので、利用側は `sprites/` 配下のファイルをそのまま参照できます(実行時に外部サイトへアクセスする必要はありません)。

## 画像一覧

ファイル名はすべて**和名**です(例: `sprites/items/たべのこし.png`)。加工済み画像は同じ場所に **PNG と WebP の両方**があります。

| 種類 | パス | サイズ | 内容 | 入手元 |
|---|---|---|---|---|
| ポケモン公式絵 | `sprites/pokemon-artwork/{和名}.png/.webp` | 320px | 1292 種(全フォルム) | [PokeAPI/sprites](https://github.com/PokeAPI/sprites) official-artwork |
| ポケモン立ち絵 | `sprites/pokemon-champion/{和名}.png/.webp` | 320px | Pokémon Champions 実装済みの約 350 種 | [Bulbagarden Archives](https://archives.bulbagarden.net/wiki/Category:Champions_menu_sprites) を Real-ESRGAN で 4 倍拡大 |
| 〃 中サイズ | `sprites/pokemon-champion/medium/{和名}.png/.webp` | 192px | 上記の縮小版 | 〃 |
| 〃 アイコン | `sprites/pokemon-champion/icon/{和名}.png/.webp` | 96px | 上記の縮小版 | 〃 |
| アイテム | `sprites/items/{和名}.png/.webp` | 96px | 対戦で使う 272 種(絵柄の大きさを揃えて正規化済み) | [serebii.net](https://www.serebii.net/itemdex/) |
| タイプ | `sprites/types/{和名}.png/.webp` | 96px | 19 種(ステラ含む)、円形 | PokeAPI/sprites (SV タイプバッジ) |
| テラスタルタイプ | `sprites/tera-types/{和名}.png/.webp` | 96px | 19 種、正方形 | PokeAPI/sprites (SV テラスタルアイコン) |
| テラスタル発動ボタン | `sprites/ui/テラスタル.png/.webp` | 原寸 | 1 枚 | GameWith |
| 原画 | 各カテゴリの `raw/{和名}.png` | 原寸 | 入手元から取得したままの無加工画像 | 〃 |
| 立ち絵の拡大原寸 | `sprites/pokemon-champion/upscaled/{和名}.png` | 512px | Real-ESRGAN 出力(縮小前) | 〃 |

### ファイル名の規則

- 和名は `data/pokemon.json` / `data/items.json` の `name` と同じです。フォルム違いは `メガフシギバナ`、`フシギバナ(キョダイ)`、`ロトム(ヒート)` のように名前に含まれます。
- ファイル名に使えない文字は全角に置き換えています(`タイプ:ヌル` → `タイプ：ヌル`)。
- WebP は公式絵(q82)と立ち絵の medium/icon(q90)のみ非可逆、それ以外はロスレスです。

## 画像を更新する

Python 3.13 と Pillow が必要です(`pip install -r requirements.txt`)。各スクリプトはネットワークから画像を取得し、`raw/` に原画を保存してから加工します。既に生成済みの画像はスキップします。

| コマンド | 生成するもの |
|---|---|
| `python scripts/pokemon-artwork/generate_pokemon_artwork.py` | ポケモン公式絵 |
| `python scripts/pokemon-champion/generate_pokemon_champion.py` | ポケモン立ち絵 320px(要 Vulkan 対応 GPU、初回に Real-ESRGAN を自動ダウンロード) |
| `python scripts/pokemon-champion/generate_pokemon_champion_variants.py` | 立ち絵の medium / icon |
| `python scripts/items/generate_items.py` | アイテム |
| `python scripts/types/generate_types.py` | タイプ・テラスタルタイプ |
| `python scripts/ui/generate_ui.py` | テラスタル発動ボタン |

共通オプション:

- `--names 和名1,和名2` … 指定した画像だけ処理する
- `--force` … 生成済みの画像も作り直す(`raw/` があれば再取得しない)
- `--refetch` … `raw/` も取り直す

ポケモン・アイテムを追加するときは `data/pokemon.json` / `data/items.json` に行を足してから対象スクリプトを実行してください。

## 開発者向けメモ

- 加工ロジックと定数は [poke-guide](../poke-guide) のスクリプトを移植したもので、実測に基づく設計理由は各スクリプトの docstring に残しています。
- 共通処理(データ読み込み、リトライ付き取得、PNG+WebP 両出力、`--force`/`--names`)は `scripts/lib/common.py` にあります。
- `data/*.json` は poke-guide の master-data をコピーしたものです。
