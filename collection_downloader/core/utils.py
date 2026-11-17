"""Small, dependency-free helpers."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def plural(count: int, word: str) -> str:
    """``plural(1, "reel") -> "1 reel"``, ``plural(3, "reel") -> "3 reels"``."""
    return f"{count:,} {word}{'' if count == 1 else 's'}"


def format_bytes_per_second(value: float | None) -> str:
    if not value:
        return "-"
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024:
            return f"{value:.1f} {unit}/s"
        value /= 1024
    return f"{value:.1f} TB/s"


def format_duration(seconds: int | float | None) -> str:
    if seconds is None:
        return "-"
    seconds = int(seconds)
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def open_in_file_manager(path: Path) -> None:
    """Open ``path`` in the OS file explorer."""
    if sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])  # noqa: S603, S607
    else:
        subprocess.Popen(["xdg-open", str(path)])  # noqa: S603, S607
