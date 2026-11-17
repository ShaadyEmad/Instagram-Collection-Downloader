"""Downloads a list of Instagram URLs with yt-dlp, reporting progress via callbacks."""

from __future__ import annotations

import logging
import shutil
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yt_dlp
from yt_dlp.utils import DownloadCancelled, DownloadError

from collection_downloader import config
from collection_downloader.core.links import LinkStatus

log = logging.getLogger(__name__)
_ytdlp_log = logging.getLogger("yt_dlp")


@dataclass(frozen=True)
class FileProgress:
    """Progress of the file that is currently being downloaded."""

    filename: str
    fraction: float | None  # 0.0 - 1.0, None if the size is unknown
    speed_bps: float | None
    eta_seconds: int | None


@dataclass(frozen=True)
class DownloadSummary:
    total: int
    downloaded: int
    skipped: int
    failed: int
    cancelled: bool


@dataclass
class DownloadCallbacks:
    """Hooks invoked from the worker thread. All are optional."""

    on_item_start: Callable[[int, int, str], None] | None = None  # (index, total, url)
    on_file_progress: Callable[[FileProgress], None] | None = None
    on_item_done: Callable[[int, str, LinkStatus], None] | None = None  # (index, url, result)


def has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def download_all(
    urls: Sequence[str],
    download_dir: Path,
    cookies_file: Path,
    stop_event: threading.Event,
    callbacks: DownloadCallbacks | None = None,
) -> DownloadSummary:
    """Download every URL into ``download_dir``. Blocking - run it in a worker thread."""
    cb = callbacks or DownloadCallbacks()
    download_dir.mkdir(parents=True, exist_ok=True)

    def progress_hook(d: dict[str, Any]) -> None:
        if stop_event.is_set():
            raise DownloadCancelled("Stopped by user")
        if d.get("status") != "downloading" or cb.on_file_progress is None:
            return
        total = d.get("total_bytes") or d.get("total_bytes_estimate")
        done = d.get("downloaded_bytes") or 0
        cb.on_file_progress(
            FileProgress(
                filename=Path(d.get("filename") or "").name,
                fraction=min(done / total, 1.0) if total else None,
                speed_bps=d.get("speed"),
                eta_seconds=d.get("eta"),
            )
        )

    ffmpeg = has_ffmpeg()
    if not ffmpeg:
        log.warning("FFmpeg not found - downloading single-file formats only (may be lower quality).")

    ydl_opts = {
        "outtmpl": str(download_dir / config.OUTPUT_TEMPLATE),
        "cookiefile": str(cookies_file),
        "format": config.FORMAT_WITH_FFMPEG if ffmpeg else config.FORMAT_WITHOUT_FFMPEG,
        "merge_output_format": "mp4",
        "continuedl": True,
        "ignoreerrors": False,  # we handle errors per URL so we can count them
        "noprogress": True,
        "logger": _YtDlpLogAdapter(),
        "progress_hooks": [progress_hook],
    }

    total = len(urls)
    counts = {status: 0 for status in LinkStatus}
    cancelled = False

    log.info("Downloading %d links to %s", total, download_dir)
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        for index, url in enumerate(urls):
            if stop_event.is_set():
                cancelled = True
                break
            if cb.on_item_start:
                cb.on_item_start(index, total, url)

            try:
                result = _download_one(ydl, url)
            except DownloadCancelled:
                cancelled = True
                break

            counts[result] += 1
            if cb.on_item_done:
                cb.on_item_done(index, url, result)

    summary = DownloadSummary(
        total=total,
        downloaded=counts[LinkStatus.DOWNLOADED],
        skipped=counts[LinkStatus.SKIPPED],
        failed=counts[LinkStatus.FAILED],
        cancelled=cancelled,
    )
    log.info(
        "Download %s: %d downloaded, %d skipped, %d failed",
        "stopped" if cancelled else "finished",
        summary.downloaded,
        summary.skipped,
        summary.failed,
    )
    return summary


def _download_one(ydl: yt_dlp.YoutubeDL, url: str) -> LinkStatus:
    try:
        retcode = ydl.download([url])
    except DownloadCancelled:
        raise
    except DownloadError as exc:
        if "no video" in str(exc).lower():
            log.info("Skipped (no video in post): %s", url)
            return LinkStatus.SKIPPED
        log.error("Failed: %s", url)
        return LinkStatus.FAILED
    return LinkStatus.DOWNLOADED if retcode == 0 else LinkStatus.FAILED


class _YtDlpLogAdapter:
    """Routes yt-dlp's output into the standard ``logging`` module."""

    def debug(self, msg: str) -> None:
        # yt-dlp sends both debug and regular info lines through ``debug``.
        if msg.startswith("[debug] "):
            _ytdlp_log.debug(msg[8:])
        else:
            _ytdlp_log.info(msg)

    def info(self, msg: str) -> None:
        _ytdlp_log.info(msg)

    def warning(self, msg: str) -> None:
        _ytdlp_log.warning(msg)

    def error(self, msg: str) -> None:
        _ytdlp_log.error(msg)
