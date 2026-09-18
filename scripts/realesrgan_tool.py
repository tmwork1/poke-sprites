"""Real-ESRGAN ncnn-vulkan実行ファイルを取得・実行する補助モジュール。

初回実行時にOS別アーカイブを ``.cache/`` へダウンロードして展開する。
指定ディレクトリ内の画像をアニメ向けモデルで4倍に拡大し、出力先へ保存する。
Pythonパッケージに依存せず、配布済みの実行ファイルを直接利用する。
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

# OS別の配布アーカイブ名。
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

# セル画調の画像の輪郭を保つため、アニメ向けモデルを明示する。
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
