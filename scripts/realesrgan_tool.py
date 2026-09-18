"""Real-ESRGAN ncnn-vulkan executable helper.

This is the poke-guide implementation used for Champions menu sprites.  The
original 128px sprites need an anime-oriented four-times enlargement before
they are reduced for display; generic image scaling left the small sprites
visibly soft.  The Python Real-ESRGAN packages are not usable on the target
Python 3.13 environment, so this helper downloads the upstream ncnn-vulkan
release on first use and invokes it directly.

The downloaded executable and its model files are cached in ``.cache/`` next
to this file (and are gitignored).  Windows uses the Vulkan build, including
on supported Intel integrated GPUs.
"""

from __future__ import annotations

import platform
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent / ".cache"

RELEASE_TAG = "v0.2.5.0"
RELEASE_DATE = "20220424"

# xinntao/Real-ESRGAN の GitHub Releases が配布する OS ごとのアセット名。
# 動作確認は Windows (Intel iGPU) のみ。macOS/Linux はアセット名が分かっている場合に限る。
_PLATFORM_ASSETS = {
    "Windows": f"realesrgan-ncnn-vulkan-{RELEASE_DATE}-windows.zip",
    "Darwin": f"realesrgan-ncnn-vulkan-{RELEASE_DATE}-macos.zip",
    "Linux": f"realesrgan-ncnn-vulkan-{RELEASE_DATE}-ubuntu.zip",
}
_PLATFORM_EXE = {
    "Windows": "realesrgan-ncnn-vulkan.exe",
    "Darwin": "realesrgan-ncnn-vulkan",
    "Linux": "realesrgan-ncnn-vulkan",
}

# アニメ塗り画像（セルシェーディングを含む）のため、汎用モデルではなくアニメ向けモデルを用いる。
# 確認時点では -n の省略値が将来変更される可能性があるため明示する。
MODEL = "realesrgan-x4plus-anime"
SCALE = 4


def _current_platform() -> str:
    system = platform.system()
    if system not in _PLATFORM_ASSETS:
        sys.exit(f"未対応 OS: {system} (Windows/macOS/Linux のみ対応)")
    return system


def ensure_tool() -> Path:
    """realesrgan-ncnn-vulkan の実行ファイルを返す。なければダウンロードして展開する。"""
    system = _current_platform()
    tool_dir = CACHE_DIR / system
    exe_path = tool_dir / _PLATFORM_EXE[system]
    if exe_path.exists():
        return exe_path

    asset = _PLATFORM_ASSETS[system]
    print(f"Real-ESRGAN 実行ファイルを取得中: {asset}")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = CACHE_DIR / asset
    url = f"https://github.com/xinntao/Real-ESRGAN/releases/download/{RELEASE_TAG}/{asset}"
    req = urllib.request.Request(url, headers={"User-Agent": "poke-guide-realesrgan-fetch/1.0"})
    with urllib.request.urlopen(req, timeout=120) as res:
        zip_path.write_bytes(res.read())

    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(tool_dir)
    zip_path.unlink()

    if system != "Windows":
        exe_path.chmod(0o755)
    if not exe_path.exists():
        sys.exit(f"展開後も実行ファイルが見つかりません: {exe_path}")
    return exe_path


def upscale_dir(in_dir: Path, out_dir: Path) -> None:
    """in_dir 内の全画像を MODEL/SCALE でアップスケールし、out_dir に同名で書き出す。"""
    exe_path = ensure_tool()
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [str(exe_path), "-i", str(in_dir), "-o", str(out_dir), "-n", MODEL, "-s", str(SCALE)],
        cwd=exe_path.parent,
        check=True,
    )
