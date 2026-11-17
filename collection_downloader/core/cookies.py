"""Validation and export of Netscape-format ``cookies.txt`` files.

yt-dlp needs your Instagram login cookies to see private saved posts. The
important one is ``sessionid`` - without it Instagram treats you as logged out.
"""

from __future__ import annotations

import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

SESSION_COOKIE = "sessionid"
INSTAGRAM_DOMAIN = "instagram.com"
_HTTP_ONLY_PREFIX = "#HttpOnly_"


class CookieStatus(Enum):
    """Result of checking a cookies file. ``usable`` decides if downloads may start."""

    OK = ("ok", True)
    EXPIRED = ("expired", True)  # usable, but will most likely fail
    NO_SESSION = ("no_session", True)  # usable, but will most likely fail
    INVALID = ("invalid", False)
    MISSING = ("missing", False)

    def __init__(self, key: str, usable: bool) -> None:
        self.key = key
        self.usable = usable


@dataclass(frozen=True)
class CookieCheck:
    status: CookieStatus
    message: str
    path: Path

    @property
    def usable(self) -> bool:
        return self.status.usable


def check_cookies(path: Path) -> CookieCheck:
    """Inspect ``path`` and report whether it looks like a usable Instagram cookie file."""
    if not path.is_file():
        return CookieCheck(CookieStatus.MISSING, "cookies.txt not found", path)

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return CookieCheck(CookieStatus.INVALID, f"Can't read file: {exc}", path)

    instagram_cookies = [c for c in _parse_netscape(text) if INSTAGRAM_DOMAIN in c["domain"]]
    if not instagram_cookies:
        return CookieCheck(
            CookieStatus.INVALID,
            "No Instagram cookies inside - is it in Netscape format?",
            path,
        )

    session = next((c for c in instagram_cookies if c["name"] == SESSION_COOKIE), None)
    if session is None:
        return CookieCheck(
            CookieStatus.NO_SESSION,
            "Found, but no login session - were you logged in when exporting?",
            path,
        )

    if 0 < session["expires"] < time.time():
        return CookieCheck(CookieStatus.EXPIRED, "Found, but the login session has expired", path)

    return CookieCheck(CookieStatus.OK, "Found and contains a login session", path)


def _parse_netscape(text: str) -> list[dict[str, Any]]:
    cookies = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith(_HTTP_ONLY_PREFIX):
            line = line[len(_HTTP_ONLY_PREFIX) :]
        elif not line or line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) != 7:
            continue
        domain, _, _, _, expires, name, _ = fields
        try:
            expires_ts = int(float(expires))
        except ValueError:
            expires_ts = 0
        cookies.append({"domain": domain, "name": name, "expires": expires_ts})
    return cookies


def write_netscape_cookies(cookies: Iterable[Mapping[str, Any]], path: Path) -> int:
    """Write Selenium-style cookie dicts to ``path`` in Netscape format.

    Returns the number of cookies written.
    """
    lines = [
        "# Netscape HTTP Cookie File",
        "# Exported by Instagram Collection Downloader. Keep this file private!",
        "",
    ]
    count = 0
    for cookie in cookies:
        domain = cookie["domain"]
        prefix = _HTTP_ONLY_PREFIX if cookie.get("httpOnly") else ""
        lines.append(
            "\t".join(
                (
                    f"{prefix}{domain}",
                    "TRUE" if domain.startswith(".") else "FALSE",
                    cookie.get("path", "/"),
                    "TRUE" if cookie.get("secure") else "FALSE",
                    str(int(cookie.get("expiry", 0))),
                    cookie["name"],
                    cookie["value"],
                )
            )
        )
        count += 1
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return count
