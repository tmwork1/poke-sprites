# poke-sprites

自作ポケモンアプリで使う画像(ポケモン・アイテム・タイプなど)を一か所に集めたリポジトリです。画像はすべて生成済みでコミットされているので、利用側は `sprites/` 配下のファイルをそのまま参照できます(実行時に外部サイトへアクセスする必要はありません)。

## 画像一覧

ファイル名はすべて**和名**です(例: `sprites/items/png/たべのこし.png`)。各カテゴリは形式ごとのサブフォルダに分かれています。

- `png/` … 加工済み PNG
- `webp/` … 加工済み WebP(`png/` と同じ内容)
- `raw/` … 入手元から取得したままの原画
- `upscaled/` … 立ち絵のみ。Real-ESRGAN で拡大した縮小前の画像

| 種類 | パス | サイズ | 内容 | 入手元 |
|---|---|---|---|---|
| ポケモン公式絵 | `sprites/pokemon-artwork/png/{和名}.png` | 320px | 1292 種(全フォルム) | [PokeAPI/sprites](https://github.com/PokeAPI/sprites) official-artwork |
| ポケモン立ち絵 | `sprites/pokemon-champion/png/{和名}.png` | 320px | Pokémon Champions 実装済みの 350 種(`upscaled/` は 512px) | [Bulbagarden Archives](https://archives.bulbagarden.net/wiki/Category:Champions_menu_sprites) を Real-ESRGAN で 4 倍拡大 |
| アイテム | `sprites/items/png/{和名}.png` | 96px | 対戦で使う 272 種(絵柄の大きさを揃えて正規化済み) | [serebii.net](https://www.serebii.net/itemdex/) |
| タイプ | `sprites/types/png/{和名}.png` | 96px | 19 種(ステラ含む)、円形 | PokeAPI/sprites (SV タイプバッジ) |
| テラスタルタイプ | `sprites/tera-types/png/{和名}.png` | 96px | 19 種、正方形 | PokeAPI/sprites (SV テラスタルアイコン) |
| テラスタル発動ボタン | `sprites/ui/png/テラスタル.png` | 原寸 | 1 枚 | GameWith |

### ファイル名の規則

- 和名は `data/pokemon.csv` / `data/items.csv` の `name` と同じです。フォルム違いは `メガフシギバナ`、`フシギバナ(キョダイ)`、`ロトム(ヒート)` のように名前に含まれます。
- ファイル名に使えない文字は全角に置き換えています(`タイプ:ヌル` → `タイプ：ヌル`)。
- WebP は公式絵(q82)のみ非可逆、それ以外はロスレスです。
- 小さい表示用の縮小版は持ちません。必要なら利用側で `png/` から生成してください。

## 画像を更新する

Python 3.13 と Pillow が必要です(`pip install -r requirements.txt`)。各スクリプトはネットワークから画像を取得し、`raw/` に原画を保存してから加工します。既に生成済みの画像はスキップします。

| コマンド | 生成するもの |
|---|---|
| `python scripts/generate_pokemon_artwork.py` | ポケモン公式絵 |
| `python scripts/generate_pokemon_champion.py` | ポケモン立ち絵(要 Vulkan 対応 GPU、初回に Real-ESRGAN を自動ダウンロード) |
| `python scripts/generate_items.py` | アイテム |
| `python scripts/generate_types.py` | タイプ・テラスタルタイプ |

共通オプション:

- `--names 和名1,和名2` … 指定した画像だけ処理する
- `--force` … 生成済みの画像も作り直す(`raw/` があれば再取得しない)
- `--refetch` … `raw/` も取り直す

ポケモン・アイテムを追加するときは `data/` の CSV に行を足してから対象スクリプトを実行してください。CSV には画像取得に必要な列だけがあります。

- `data/pokemon.csv` … `dexNo,name,forme,imageId`。`imageId` は PokeAPI の ID(公式絵の URL に使用)、`forme` は Bulbagarden の Champions ファイル名サフィックス(`Mega`、`Alola`、`Galar-Zen` など。通常フォルムは空)
- `data/items.csv` … `name,slug`。`slug` は serebii.net itemdex の英語スラッグ(`heavy-duty-boots` など)。空にすると対象外になる

## 開発者向けメモ

- 加工ロジックと定数は [poke-guide](../poke-guide) のスクリプトを移植したもので、実測に基づく設計理由は各スクリプトの docstring に残しています。
- 共通処理(データ読み込み、リトライ付き取得、PNG+WebP 両出力、`--force`/`--names`)は `scripts/common.py` にあります。
- `data/*.csv` は poke-guide の master-data から画像取得に必要な列だけを抜き出したものです。

## ライセンス

スクリプト・`data/`・ドキュメントは [MIT License](LICENSE) です。`sprites/` 配下の画像はライセンスの対象外で、著作権は任天堂・クリーチャーズ・ゲームフリーク・株式会社ポケモン等の権利者に帰属します(個人利用・非商用の範囲でお使いください)。
