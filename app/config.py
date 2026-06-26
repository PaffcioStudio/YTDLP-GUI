# -*- coding: utf-8 -*-
"""
Konfiguracja globalna: ścieżki, stałe, wyrażenia regularne, logowanie.
"""

import os
import re
import logging
from pathlib import Path

# ---------------------------------------------------------------------------
# Katalogi aplikacji
# ---------------------------------------------------------------------------

app_data_base_dir = Path(os.getenv("APPDATA") or Path.home()) / "VideoDownloader"
log_dir = app_data_base_dir / "logs"
log_dir.mkdir(parents=True, exist_ok=True)

THUMBS_CACHE_DIR = app_data_base_dir / "thumbs"
THUMBS_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Ścieżki narzędzi
# ---------------------------------------------------------------------------

LIBS_DIR = app_data_base_dir / "libs"
TOOLS_DIR = app_data_base_dir / "tools"

YTDLP_PATH_WINDOWS = LIBS_DIR / "yt-dlp.exe"
YTDLP_PATH_LINUX   = TOOLS_DIR / "yt-dlp"

FFMPEG_DIR         = LIBS_DIR / "ffmpeg"
FFMPEG_BIN_DIR     = FFMPEG_DIR / "bin"
FFMPEG_PATH_WINDOWS = FFMPEG_BIN_DIR / "ffmpeg.exe"
FFMPEG_PATH_LINUX   = TOOLS_DIR / "ffmpeg"

# ---------------------------------------------------------------------------
# URL-e pobierania
# ---------------------------------------------------------------------------

FFMPEG_DOWNLOAD_URL_WINDOWS = (
    "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
)
FFMPEG_DOWNLOAD_URL_LINUX = (
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
    "ffmpeg-master-latest-linux64-gpl.tar.xz"
)

# ---------------------------------------------------------------------------
# Regex
# ---------------------------------------------------------------------------

DETAILED_PROGRESS_REGEX = re.compile(
    r"\[download\]\s+([\d.]+)\%(?:.*?(?:of|\s+)\s*([\\d.]+\S+))?(?:.*?at\s+([\d.]+\S+)\/s)?.*"
)
URL_SIMPLE_REGEX = re.compile(
    r"(?:(?:https?://)?(?:[\w.-]+\.[a-z]{2,})(?:/\S*)?)", re.IGNORECASE
)
STRICT_URL_REGEX = re.compile(
    r"^(https?://)?([\w.-]+)\.[a-z]{2,}(/\S*)?$", re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Inne stałe
# ---------------------------------------------------------------------------

DEFAULT_SOCKET_TIMEOUT = 15   # sekundy dla --socket-timeout yt-dlp

# ---------------------------------------------------------------------------
# Logowanie
# ---------------------------------------------------------------------------

logging.basicConfig(
    filename=log_dir / "app.log",
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sciezki do zasobow (ikony) - dziala w dev, PyInstaller, DEB, AppImage
# ---------------------------------------------------------------------------

def get_icons_dir() -> Path:
    import sys, os
    # PyInstaller onefile/onedir
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "icons"
    # AppImage
    if os.environ.get("APPDIR"):
        return Path(os.environ["APPDIR"]) / "usr" / "share" / "ytdlp-gui" / "icons"
    # DEB systemowy
    system_icons = Path("/usr/share/ytdlp-gui/icons")
    if system_icons.exists():
        return system_icons
    # Dev - wzgledem tego pliku (app/config.py -> ../icons)
    return Path(__file__).parent.parent / "icons"


def get_icon_path(name: str) -> str:
    return str(get_icons_dir() / name)
