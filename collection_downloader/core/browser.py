"""Selenium-controlled Chrome session used to log in and collect links."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Collection
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import StaleElementReferenceException, WebDriverException
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By

from collection_downloader import config
from collection_downloader.core.cookies import INSTAGRAM_DOMAIN, write_netscape_cookies

log = logging.getLogger(__name__)

_POST_LINK_XPATH = '//a[starts-with(@href, "/p/") or starts-with(@href, "/reel/")]'


@dataclass(frozen=True)
class ScanProgress:
    found: int  # unique links found so far
    new: int  # of which not yet downloaded
    known_streak: int  # already-downloaded links seen in a row (latest)
    idle_scrolls: int  # scrolls in a row without new links


class ScanEnd(Enum):
    COMPLETE = "complete"  # reached the end of the page
    STOPPED = "stopped"  # stopped by the user
    REACHED_DOWNLOADED = "reached_downloaded"  # hit N already-downloaded links in a row


@dataclass(frozen=True)
class ScanResult:
    links: list[str]  # in page order, i.e. newest saves first
    end: ScanEnd


ScanProgressCallback = Callable[[ScanProgress], None]


class BrowserError(RuntimeError):
    """Raised when the browser can't be started or was closed by the user."""


class BrowserSession:
    """Owns a single Chrome WebDriver instance.

    Methods are blocking and meant to be called from a worker thread, one at a time.
    """

    def __init__(self) -> None:
        self._driver: webdriver.Chrome | None = None

    # --- lifecycle ---------------------------------------------------------

    @property
    def is_open(self) -> bool:
        if self._driver is None:
            return False
        try:
            _ = self._driver.window_handles
        except WebDriverException:
            self._driver = None
            return False
        return True

    def open(self) -> None:
        """Launch Chrome and navigate to Instagram."""
        if self.is_open:
            return
        log.info("Launching Chrome...")
        self._driver = _create_driver()
        self._driver.maximize_window()
        self._driver.get(config.INSTAGRAM_URL)
        log.info("Browser opened. Log in and open your saved collection.")

    def close(self) -> None:
        if self._driver is None:
            return
        try:
            self._driver.quit()
        except WebDriverException as exc:
            log.debug("Error while closing the browser: %s", exc)
        finally:
            self._driver = None

    # --- actions -----------------------------------------------------------

    @property
    def current_url(self) -> str:
        return self._require_driver().current_url

    def collect_links(
        self,
        stop_event: threading.Event,
        on_progress: ScanProgressCallback | None = None,
        *,
        already_downloaded: Collection[str] = (),
        stop_after_downloaded: int | None = None,
    ) -> ScanResult:
        """Scroll the current page and collect post/reel links in page order.

        Ends when no new links appear anymore, when ``stop_event`` is set, or -
        if ``stop_after_downloaded`` is given - after that many links in a row
        that are in ``already_downloaded``. Saved collections list the newest
        saves first, so this finds just the recently added reels.
        """
        driver = self._require_driver()
        found: dict[str, None] = {}  # ordered set
        new = 0
        known_streak = 0
        idle_scrolls = 0
        end = ScanEnd.COMPLETE

        log.info("Scanning %s", driver.current_url)
        try:
            while not stop_event.is_set():
                before = len(found)
                for anchor in driver.find_elements(By.XPATH, _POST_LINK_XPATH):
                    try:
                        href = anchor.get_attribute("href")
                    except StaleElementReferenceException:
                        continue
                    if not href:
                        continue
                    url = href.split("?")[0].rstrip("/")
                    if url in found:
                        continue
                    found[url] = None
                    if url in already_downloaded:
                        known_streak += 1
                    else:
                        known_streak = 0
                        new += 1
                    if stop_after_downloaded and known_streak >= stop_after_downloaded:
                        end = ScanEnd.REACHED_DOWNLOADED
                        break

                if len(found) == before:
                    idle_scrolls += 1
                    log.debug("No new links (%d/%d)", idle_scrolls, config.MAX_IDLE_SCROLLS)
                else:
                    idle_scrolls = 0
                    log.info("Found %d links so far (%d new)", len(found), new)

                if on_progress:
                    on_progress(ScanProgress(len(found), new, known_streak, idle_scrolls))

                if end is ScanEnd.REACHED_DOWNLOADED or idle_scrolls >= config.MAX_IDLE_SCROLLS:
                    break
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                stop_event.wait(config.SCROLL_PAUSE_SECONDS)
        except WebDriverException as exc:
            self._driver = None
            raise BrowserError("The browser was closed or stopped responding.") from exc

        if stop_event.is_set():
            end = ScanEnd.STOPPED
        log.info("Scan ended (%s): %d links, %d new", end.value, len(found), new)
        return ScanResult(list(found), end)

    def export_cookies(self, path: Path) -> int:
        """Save the browser's Instagram cookies to ``path`` (Netscape format)."""
        driver = self._require_driver()
        try:
            if INSTAGRAM_DOMAIN not in driver.current_url:
                driver.get(config.INSTAGRAM_URL)
            cookies = [c for c in driver.get_cookies() if INSTAGRAM_DOMAIN in c.get("domain", "")]
        except WebDriverException as exc:
            self._driver = None
            raise BrowserError("The browser was closed or stopped responding.") from exc
        count = write_netscape_cookies(cookies, path)
        log.info("Exported %d Instagram cookies to %s", count, path)
        return count

    def _require_driver(self) -> webdriver.Chrome:
        if not self.is_open or self._driver is None:
            raise BrowserError("The browser is not open.")
        return self._driver


def _create_driver() -> webdriver.Chrome:
    """Start Chrome, preferring Selenium's built-in driver manager."""
    options = webdriver.ChromeOptions()
    try:
        return webdriver.Chrome(options=options)
    except WebDriverException as exc:
        log.warning("Selenium Manager could not start Chrome (%s). Trying webdriver-manager...", exc.msg)

    try:
        from webdriver_manager.chrome import ChromeDriverManager

        service = ChromeService(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=options)
    except Exception as exc:  # noqa: BLE001 - surface any failure to the user
        raise BrowserError(
            "Could not start Google Chrome. Make sure Chrome is installed and up to date."
        ) from exc
