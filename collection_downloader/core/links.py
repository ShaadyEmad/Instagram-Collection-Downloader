"""The link history stored in ``links.txt``.

Every link ever found is kept together with its download status, so a later
scan + download only fetches what is new. File format (one link per line)::

    https://www.instagram.com/reel/ABC<TAB>downloaded

Lines without a status (the old format) are read as ``pending``.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Iterable
from enum import StrEnum
from pathlib import Path

log = logging.getLogger(__name__)

_HEADER = (
    "# Instagram Collection Downloader - link history\n"
    "# Format: <url><TAB><status>   status: pending | downloaded | skipped | failed\n"
)


class LinkStatus(StrEnum):
    PENDING = "pending"
    DOWNLOADED = "downloaded"
    SKIPPED = "skipped"  # e.g. a photo-only post without a video
    FAILED = "failed"  # retried on the next download

    @property
    def done(self) -> bool:
        """Whether the link needs no further download attempts."""
        return self in (LinkStatus.DOWNLOADED, LinkStatus.SKIPPED)


class LinkHistory:
    """Ordered mapping of link -> :class:`LinkStatus`, persisted to a text file.

    Not thread-safe: the GUI only touches it from the main thread and hands
    worker threads plain snapshots (see :meth:`done_links`, :meth:`to_download`).
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._entries: dict[str, LinkStatus] = {}

    # --- persistence -------------------------------------------------------

    @classmethod
    def load(cls, path: Path) -> LinkHistory:
        history = cls(path)
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return history
        except OSError as exc:
            log.warning("Could not read %s: %s", path, exc)
            return history

        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            url, _, raw_status = line.partition("\t")
            try:
                status = LinkStatus(raw_status.strip() or LinkStatus.PENDING.value)
            except ValueError:
                status = LinkStatus.PENDING
            history._entries[url.strip()] = status
        return history

    def save(self) -> None:
        body = "".join(f"{url}\t{status.value}\n" for url, status in self._entries.items())
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(_HEADER + body, encoding="utf-8")
        tmp.replace(self.path)  # atomic: never leaves a half-written history behind

    def clear(self) -> None:
        """Forget every link and status, and delete the file."""
        self._entries.clear()
        self.path.unlink(missing_ok=True)
        log.info("Link history cleared")

    # --- queries -----------------------------------------------------------

    def __len__(self) -> int:
        return len(self._entries)

    def status(self, url: str) -> LinkStatus | None:
        return self._entries.get(url)

    def counts(self) -> Counter[LinkStatus]:
        return Counter(self._entries.values())

    def done_links(self) -> frozenset[str]:
        return frozenset(url for url, status in self._entries.items() if status.done)

    def to_download(self) -> list[str]:
        """Links that are pending or failed, in history order (newest saves first)."""
        return [url for url, status in self._entries.items() if not status.done]

    # --- updates -----------------------------------------------------------

    def merge_scan(self, links: Iterable[str]) -> int:
        """Add scanned links, keeping known statuses. Returns how many were new.

        Scanned links come first (in page order, i.e. newest saves first),
        followed by older links that weren't part of this scan.
        """
        merged: dict[str, LinkStatus] = {}
        new = 0
        for url in links:
            if url in merged:
                continue
            if url not in self._entries:
                new += 1
            merged[url] = self._entries.get(url, LinkStatus.PENDING)
        for url, status in self._entries.items():
            merged.setdefault(url, status)
        self._entries = merged
        return new

    def set_status(self, url: str, status: LinkStatus) -> None:
        self._entries[url] = status
