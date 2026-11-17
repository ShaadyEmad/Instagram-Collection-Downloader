"""Application-wide paths and tuning constants."""

from __future__ import annotations

import sys
from pathlib import Path

APP_NAME = "Instagram Collection Downloader"


def _resolve_base_dir() -> Path:
    """Return the folder the app lives in.

    When frozen with PyInstaller this is the folder containing the executable,
    otherwise it is the project root (the folder containing ``main.py``).
    All user files (cookies, links, downloads) are resolved relative to it so
    the app stays portable.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = _resolve_base_dir()
COOKIES_FILE = BASE_DIR / "cookies.txt"
LINKS_FILE = BASE_DIR / "links.txt"
DEFAULT_DOWNLOAD_DIR = BASE_DIR / "videos"

INSTAGRAM_URL = "https://www.instagram.com/"

# --- Scraping ---
SCROLL_PAUSE_SECONDS = 1.5
# Stop scrolling after this many scrolls in a row that found no new links.
MAX_IDLE_SCROLLS = 5
# "Only new reels": stop the scan after this many already-downloaded reels in a row.
STOP_AFTER_DOWNLOADED_CHOICES = (3, 5, 10, 20)
DEFAULT_STOP_AFTER_DOWNLOADED = 5

# --- Downloading ---
# Includes the post id so posts with the same date + title don't overwrite each other.
OUTPUT_TEMPLATE = "%(upload_date)s_%(title).80B_%(id)s.%(ext)s"
FORMAT_WITH_FFMPEG = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
FORMAT_WITHOUT_FFMPEG = "best[ext=mp4]/best"
