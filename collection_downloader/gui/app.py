"""Main application window and controller."""

from __future__ import annotations

import logging
import queue
import sys
import threading
import time
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any, TypeVar

import customtkinter as ctk

from collection_downloader import __version__, config
from collection_downloader.core import downloader
from collection_downloader.core.browser import BrowserError, BrowserSession, ScanEnd, ScanProgress, ScanResult
from collection_downloader.core.cookies import CookieCheck, CookieStatus, check_cookies
from collection_downloader.core.downloader import DownloadCallbacks, DownloadSummary, FileProgress
from collection_downloader.core.links import LinkHistory, LinkStatus
from collection_downloader.core.utils import (
    format_bytes_per_second,
    format_duration,
    open_in_file_manager,
    plural,
)
from collection_downloader.gui import help_content, theme
from collection_downloader.gui.dialogs import HelpDialog
from collection_downloader.gui.states import AppState
from collection_downloader.gui.widgets import (
    ActionButton,
    Card,
    Dot,
    HelpView,
    LogPanel,
    StatCard,
    StatusPanel,
    StepCard,
    Tooltip,
    WrappingLabel,
)

log = logging.getLogger(__name__)
T = TypeVar("T")

COOKIE_CHECK_INTERVAL_MS = 2000
PROGRESS_THROTTLE_SECONDS = 0.1
HISTORY_SAVE_INTERVAL_SECONDS = 2.0

_COOKIE_DISPLAY: dict[CookieStatus, tuple[str, str]] = {
    CookieStatus.OK: ("Cookies ready", theme.GREEN),
    CookieStatus.EXPIRED: ("Cookies expired", theme.AMBER),
    CookieStatus.NO_SESSION: ("Not logged in", theme.AMBER),
    CookieStatus.INVALID: ("Cookies invalid", theme.RED),
    CookieStatus.MISSING: ("Cookies missing", theme.RED),
}


class UiDispatcher:
    """Runs callables posted from worker threads on the Tk main thread."""

    def __init__(self, root: tk.Misc, interval_ms: int = 50, max_per_tick: int = 500) -> None:
        self._root = root
        self._interval = interval_ms
        self._max_per_tick = max_per_tick
        self._queue: queue.SimpleQueue[tuple[Callable[..., Any], tuple[Any, ...]]] = queue.SimpleQueue()
        self._job: str | None = root.after(interval_ms, self._drain)

    def post(self, fn: Callable[..., Any], *args: Any) -> None:
        self._queue.put((fn, args))

    def stop(self) -> None:
        if self._job is not None:
            self._root.after_cancel(self._job)
            self._job = None

    def _drain(self) -> None:
        for _ in range(self._max_per_tick):
            try:
                fn, args = self._queue.get_nowait()
            except queue.Empty:
                break
            try:
                fn(*args)
            except Exception:  # noqa: BLE001 - never let one callback kill the loop
                log.exception("Error in UI callback")
        self._job = self._root.after(self._interval, self._drain)


class _UiLogHandler(logging.Handler):
    """Forwards log records to the log panel through the dispatcher."""

    def __init__(self, dispatcher: UiDispatcher, sink: Callable[[int, str], None]) -> None:
        super().__init__()
        self._dispatcher = dispatcher
        self._sink = sink

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._dispatcher.post(self._sink, record.levelno, self.format(record))
        except Exception:  # noqa: BLE001
            self.handleError(record)


class App(ctk.CTk):
    def __init__(self) -> None:
        theme.apply_global_theme()
        super().__init__(fg_color=theme.BG)
        self.title(config.APP_NAME)
        self._fit_window(width=820, height=980)
        self.minsize(680, 620)

        self.fonts = theme.Fonts.create()
        self._dispatcher = UiDispatcher(self)
        self._browser = BrowserSession()
        self._stop_event = threading.Event()

        self._state = AppState.IDLE
        self._browser_open = False
        # The history is only ever touched on the main thread; workers get snapshots.
        self._history = LinkHistory.load(config.LINKS_FILE)
        self._cookies_path = config.COOKIES_FILE
        self._cookie_check: CookieCheck = check_cookies(self._cookies_path)
        self._download_dir = tk.StringVar(value=str(config.DEFAULT_DOWNLOAD_DIR))
        self._only_new = tk.BooleanVar(value=True)
        self._stop_after = tk.StringVar(value=str(config.DEFAULT_STOP_AFTER_DOWNLOADED))
        self._last_progress_post = 0.0
        self._last_history_save = 0.0
        self._download_total = 0

        self._build_layout()
        self._install_log_handler()

        self._set_state(AppState.IDLE, self._idle_detail())
        self._apply_cookie_check(self._cookie_check)
        self._refresh_stats()
        self.after(COOKIE_CHECK_INTERVAL_MS, self._poll_cookies)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        log.info("%s %s started", config.APP_NAME, __version__)
        log.info("App folder: %s", config.BASE_DIR)
        if len(self._history):
            log.info(
                "Loaded %d links (%d still to download) from %s",
                len(self._history),
                len(self._history.to_download()),
                config.LINKS_FILE.name,
            )

    # =====================================================================
    # Layout
    # =====================================================================

    def _fit_window(self, width: int, height: int) -> None:
        """Use the preferred size, but never exceed the screen (taking DPI scaling into account)."""
        scaling = ctk.ScalingTracker.get_window_scaling(self)
        max_height = int((self.winfo_screenheight() - 100) / scaling)
        self.geometry(f"{width}x{min(height, max_height)}")

    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self._build_header().grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 10))

        self._status = StatusPanel(self, self.fonts)
        self._status.grid(row=1, column=0, sticky="ew", padx=20)

        self._build_stats().grid(row=2, column=0, sticky="ew", padx=20, pady=(theme.GAP, theme.GAP))

        tabs = ctk.CTkTabview(
            self,
            fg_color=theme.BG,
            segmented_button_fg_color=theme.SURFACE,
            segmented_button_selected_color=theme.ACCENT,
            segmented_button_selected_hover_color=theme.ACCENT_HOVER,
            segmented_button_unselected_color=theme.SURFACE,
            segmented_button_unselected_hover_color=theme.SURFACE_ALT,
            anchor="w",
        )
        tabs.grid(row=3, column=0, sticky="nsew", padx=12)
        self._build_downloader_tab(tabs.add("  Downloader  "))
        self._build_guide_tab(tabs.add("  How it works  "))

        self._log_panel = LogPanel(self, self.fonts)
        self._log_panel.grid(row=4, column=0, sticky="nsew", padx=20, pady=(4, 0))
        self._log_panel.grid_remove()  # hidden by default

        self._build_footer().grid(row=5, column=0, sticky="ew", padx=20, pady=(6, 12))

    def _build_header(self) -> ctk.CTkFrame:
        header = ctk.CTkFrame(self, fg_color="transparent")
        ctk.CTkLabel(
            header,
            text="↓",
            width=40,
            height=40,
            corner_radius=12,
            fg_color=theme.ACCENT,
            text_color="#FFFFFF",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).pack(side="left", padx=(0, 12))
        titles = ctk.CTkFrame(header, fg_color="transparent")
        titles.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(
            titles, text=config.APP_NAME, font=self.fonts.title, text_color=theme.TEXT, anchor="w"
        ).pack(fill="x")
        ctk.CTkLabel(
            titles,
            text="Save every reel from your private Instagram collections to your computer.",
            font=self.fonts.subtitle,
            text_color=theme.TEXT_MUTED,
            anchor="w",
        ).pack(fill="x")
        ctk.CTkLabel(header, text=f"v{__version__}", font=self.fonts.small, text_color=theme.TEXT_FAINT).pack(
            side="right", anchor="n"
        )
        return header

    def _build_stats(self) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self, fg_color="transparent")
        specs = (
            ("found", "Reels found", theme.ACCENT, ""),
            (LinkStatus.DOWNLOADED.value, "Downloaded", theme.GREEN, "kept in your history"),
            (LinkStatus.SKIPPED.value, "Skipped", theme.AMBER, "no video in post"),
            (LinkStatus.FAILED.value, "Failed", theme.RED, "retried on next download"),
        )
        self._stats: dict[str, StatCard] = {}
        for column, (key, caption, color, hint) in enumerate(specs):
            frame.grid_columnconfigure(column, weight=1, uniform="stats")
            card = StatCard(frame, self.fonts, caption, color, hint)
            card.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else theme.GAP // 2, 0))
            self._stats[key] = card
        return frame

    def _build_downloader_tab(self, tab: ctk.CTkFrame) -> None:
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)
        scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)

        self._build_prepare_step(scroll).grid(row=0, column=0, sticky="ew", pady=(0, theme.GAP))
        self._build_find_step(scroll).grid(row=1, column=0, sticky="ew", pady=(0, theme.GAP))
        self._build_download_step(scroll).grid(row=2, column=0, sticky="ew")

    def _build_prepare_step(self, master: tk.Misc) -> StepCard:
        step = StepCard(
            master,
            self.fonts,
            1,
            "Prepare",
            "Choose where your videos will be saved. Downloads also need your Instagram login "
            "cookies (cookies.txt) - click the ? if you don't have them yet.",
        )
        body = step.body
        body.grid_columnconfigure(0, weight=1)

        # --- download folder ---
        self._field_label(body, "Download folder").grid(row=0, column=0, columnspan=3, sticky="w")
        self._folder_entry = ctk.CTkEntry(
            body,
            textvariable=self._download_dir,
            font=self.fonts.body,
            fg_color=theme.SURFACE_ALT,
            border_color=theme.BORDER,
            height=34,
        )
        self._folder_entry.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self._browse_btn = self._button(body, "Browse...", self._choose_download_dir, width=96)
        self._browse_btn.grid(row=1, column=1, padx=(8, 0), pady=(4, 0))
        Tooltip(self._browse_btn, "Pick the folder your videos are saved to.")
        open_btn = self._button(body, "Open", self._open_download_dir, width=64)
        open_btn.grid(row=1, column=2, padx=(8, 0), pady=(4, 0))
        Tooltip(open_btn, "Open the download folder in your file explorer.")

        # --- cookies ---
        self._field_label(body, "Login cookies").grid(row=2, column=0, columnspan=3, sticky="w", pady=(14, 0))
        cookie_box = Card(body, fg_color=theme.BG)
        cookie_box.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(4, 0))
        cookie_box.grid_columnconfigure(1, weight=1)

        self._cookie_dot = Dot(cookie_box, size=12)
        self._cookie_dot.grid(row=0, column=0, rowspan=2, padx=(12, 10), pady=12)
        title_row = ctk.CTkFrame(cookie_box, fg_color="transparent")
        title_row.grid(row=0, column=1, sticky="ew", pady=(10, 0))
        self._cookie_title = ctk.CTkLabel(title_row, text="", font=self.fonts.body_bold)
        self._cookie_title.pack(side="left")
        help_btn = ctk.CTkButton(
            title_row,
            text="?",
            width=22,
            height=22,
            corner_radius=11,
            font=self.fonts.body_bold,
            fg_color=theme.SECONDARY,
            hover_color=theme.ACCENT,
            command=self._show_cookie_help,
        )
        help_btn.pack(side="left", padx=(8, 0))
        Tooltip(help_btn, "How do I get cookies.txt?")
        self._cookie_message = WrappingLabel(
            cookie_box, padding=4, text="", font=self.fonts.small, text_color=theme.TEXT_MUTED
        )
        self._cookie_message.grid(row=1, column=1, sticky="ew", pady=(0, 10))

        buttons = ctk.CTkFrame(cookie_box, fg_color="transparent")
        buttons.grid(row=0, column=2, rowspan=2, padx=12, pady=10)
        self._choose_cookies_btn = self._button(
            buttons, "Choose file...", self._choose_cookies_file, width=110
        )
        self._choose_cookies_btn.pack(side="top", fill="x")
        Tooltip(self._choose_cookies_btn, "Use a cookies.txt file from another location.")
        self._export_cookies_btn = self._button(buttons, "Get from browser", self._export_cookies, width=110)
        self._export_cookies_btn.pack(side="top", fill="x", pady=(6, 0))
        Tooltip(
            self._export_cookies_btn,
            "Saves the login cookies of the app's browser to cookies.txt. "
            "Open the browser in step 2 and log in first.",
        )
        return step

    def _build_find_step(self, master: tk.Misc) -> StepCard:
        step = StepCard(
            master,
            self.fonts,
            2,
            "Find reels",
            "Open the browser and log in to Instagram. Then go to your profile > Saved and open "
            "the collection you want. Come back here and start the scan - the app scrolls through "
            "the collection and remembers every reel it finds.",
        )
        body = step.body
        body.grid_columnconfigure((0, 1), weight=1, uniform="find")

        # --- "only new reels" option ---
        options = ctk.CTkFrame(body, fg_color="transparent")
        options.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self._only_new_switch = ctk.CTkSwitch(
            options,
            text="Only new reels - stop after",
            variable=self._only_new,
            font=self.fonts.body,
            text_color=theme.TEXT,
            progress_color=theme.ACCENT,
            command=self._refresh_controls,
        )
        self._only_new_switch.pack(side="left")
        self._stop_after_menu = ctk.CTkOptionMenu(
            options,
            values=[str(n) for n in config.STOP_AFTER_DOWNLOADED_CHOICES],
            variable=self._stop_after,
            width=64,
            height=28,
            font=self.fonts.body,
            fg_color=theme.SECONDARY,
            button_color=theme.SECONDARY,
            button_hover_color=theme.SECONDARY_HOVER,
        )
        self._stop_after_menu.pack(side="left", padx=8)
        ctk.CTkLabel(
            options, text="already downloaded reels in a row", font=self.fonts.body, text_color=theme.TEXT
        ).pack(side="left")
        tip = (
            "Saved collections show your newest saves first. With this on, the scan stops as soon as it "
            "reaches reels you already downloaded - so only recently saved reels are fetched. "
            "Turn it off to scan the whole collection."
        )
        Tooltip(self._only_new_switch, tip)
        Tooltip(self._stop_after_menu, tip)

        self._browser_btn = self._button(body, "Open browser", self._open_browser, height=40)
        self._browser_btn.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        Tooltip(self._browser_btn, "Starts a Google Chrome window controlled by this app.")

        self._scan_btn = self._button(body, "Scan collection", self._toggle_scan, primary=True, height=40)
        self._scan_btn.grid(row=0, column=1, sticky="ew", padx=(5, 0))
        Tooltip(
            self._scan_btn,
            "Scrolls through the page that is open in the browser and collects all reel links. "
            "You can stop at any time - links found so far are kept.",
        )

        self._scan_hint = WrappingLabel(body, text="", font=self.fonts.small, text_color=theme.TEXT_FAINT)
        self._scan_hint.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        return step

    def _build_download_step(self, master: tk.Misc) -> StepCard:
        step = StepCard(
            master,
            self.fonts,
            3,
            "Download",
            "Downloads every reel that hasn't been downloaded yet. The app remembers what you "
            f"downloaded (in {config.LINKS_FILE.name}), so you can stop at any time and continue later.",
        )
        body = step.body
        body.grid_columnconfigure(0, weight=1)

        self._download_btn = self._button(
            body, "Download all", self._toggle_download, primary=True, height=42
        )
        self._download_btn.grid(row=0, column=0, columnspan=2, sticky="ew")
        self._download_hint = WrappingLabel(body, text="", font=self.fonts.small, text_color=theme.TEXT_FAINT)
        self._download_hint.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))

        # --- overall progress ---
        self._field_label(body, "Overall progress").grid(row=2, column=0, sticky="w", pady=(14, 0))
        self._overall_text = ctk.CTkLabel(body, text="-", font=self.fonts.small, text_color=theme.TEXT_MUTED)
        self._overall_text.grid(row=2, column=1, sticky="e", pady=(14, 0))
        self._overall_bar = ctk.CTkProgressBar(
            body, height=12, corner_radius=6, fg_color=theme.SURFACE_ALT, progress_color=theme.ACCENT
        )
        self._overall_bar.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self._overall_bar.set(0)

        # --- current file ---
        self._file_text = ctk.CTkLabel(
            body, text="Current file", font=self.fonts.small, text_color=theme.TEXT_MUTED, anchor="w"
        )
        self._file_text.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        self._file_speed = ctk.CTkLabel(body, text="", font=self.fonts.small, text_color=theme.TEXT_MUTED)
        self._file_speed.grid(row=4, column=1, sticky="e", pady=(12, 0))
        self._file_bar = ctk.CTkProgressBar(
            body, height=6, corner_radius=3, fg_color=theme.SURFACE_ALT, progress_color=theme.BLUE
        )
        self._file_bar.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self._file_bar.set(0)

        # --- download history ---
        history_box = Card(body, fg_color=theme.BG)
        history_box.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(16, 0))
        history_box.grid_columnconfigure(0, weight=1)
        self._field_label(history_box, "Download history").grid(
            row=0, column=0, sticky="w", padx=12, pady=(10, 0)
        )
        self._history_text = WrappingLabel(
            history_box, padding=4, text="", font=self.fonts.small, text_color=theme.TEXT_MUTED
        )
        self._history_text.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 10))
        self._clear_history_btn = self._button(history_box, "Clear history", self._clear_history, width=110)
        self._clear_history_btn.grid(row=0, column=1, rowspan=2, padx=12, pady=10)
        Tooltip(
            self._clear_history_btn,
            "Forget all found reels and which ones were downloaded. Your downloaded files are NOT deleted.",
        )
        return step

    def _build_guide_tab(self, tab: ctk.CTkFrame) -> None:
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)
        scroll = ctk.CTkScrollableFrame(tab, fg_color=theme.SURFACE, corner_radius=theme.RADIUS)
        scroll.grid(row=0, column=0, sticky="nsew", padx=8, pady=(0, 4))
        scroll.grid_columnconfigure(0, weight=1)
        HelpView(scroll, self.fonts, help_content.GUIDE).grid(
            row=0, column=0, sticky="nsew", padx=14, pady=14
        )

    def _build_footer(self) -> ctk.CTkFrame:
        footer = ctk.CTkFrame(self, fg_color="transparent")
        self._log_switch = ctk.CTkSwitch(
            footer,
            text="Show log",
            font=self.fonts.small,
            text_color=theme.TEXT_MUTED,
            progress_color=theme.ACCENT,
            command=self._toggle_log,
        )
        self._log_switch.pack(side="left")
        Tooltip(self._log_switch, "Show detailed technical output - useful when something goes wrong.")
        ctk.CTkLabel(
            footer,
            text=f"App folder: {config.BASE_DIR}",
            font=self.fonts.small,
            text_color=theme.TEXT_FAINT,
        ).pack(side="right")
        return footer

    def _field_label(self, master: tk.Misc, text: str) -> ctk.CTkLabel:
        return ctk.CTkLabel(master, text=text, font=self.fonts.body_bold, text_color=theme.TEXT)

    def _button(
        self,
        master: tk.Misc,
        text: str,
        command: Callable[[], None],
        *,
        primary: bool = False,
        width: int = 140,
        height: int = 34,
    ) -> ActionButton:
        return ActionButton(
            master,
            variant="primary" if primary else "secondary",
            text=text,
            command=command,
            width=width,
            height=height,
            font=self.fonts.body_bold,
        )

    # =====================================================================
    # State & read-outs
    # =====================================================================

    def _set_state(self, state: AppState, detail: str | None = None) -> None:
        self._state = state
        self._status.set_state(state, detail)
        self._refresh_controls()

    def _refresh_controls(self) -> None:
        busy = self._state.busy
        state = self._state

        # Step 1
        self._folder_entry.configure(state="disabled" if busy else "normal")
        self._browse_btn.set_enabled(not busy)
        self._choose_cookies_btn.set_enabled(not busy)
        self._export_cookies_btn.set_enabled(self._browser_open and not busy)

        # Step 2
        self._browser_btn.configure(text="✓  Browser open" if self._browser_open else "Open browser")
        self._browser_btn.set_enabled(not self._browser_open and not busy)
        scanning = state is AppState.SEARCHING
        self._scan_btn.configure(text="■  Stop scanning" if scanning else "Scan collection")
        self._scan_btn.set_variant("danger" if scanning else "primary")
        self._scan_btn.set_enabled(scanning or (self._browser_open and not busy))
        self._scan_hint.configure(text=self._scan_hint_text())
        self._only_new_switch.configure(state="disabled" if busy else "normal")
        self._stop_after_menu.configure(state="normal" if self._only_new.get() and not busy else "disabled")

        # Step 3
        downloading = state is AppState.DOWNLOADING
        to_download = len(self._history.to_download())
        if downloading:
            label = "■  Stop download"
        elif to_download:
            label = f"Download {plural(to_download, 'reel')}"
        else:
            label = "Nothing to download"
        self._download_btn.configure(text=label)
        self._download_btn.set_variant("danger" if downloading else "primary")
        self._download_btn.set_enabled(
            downloading or (not busy and self._cookie_check.usable and to_download > 0)
        )
        hint, color = self._download_hint_text(to_download)
        self._download_hint.configure(text=hint, text_color=color)
        self._clear_history_btn.set_enabled(not busy and len(self._history) > 0)

    def _scan_hint_text(self) -> str:
        if self._state is AppState.SEARCHING:
            return "Keep the browser window open while scanning. Stopping keeps the links found so far."
        if not self._browser_open:
            return "Start by opening the browser."
        return "Make sure your saved collection is open in the browser, then click Scan collection."

    def _download_hint_text(self, to_download: int) -> tuple[str, str]:
        if self._state is AppState.DOWNLOADING:
            return "You can stop at any time - progress is saved.", theme.TEXT_FAINT
        if not self._cookie_check.usable:
            return "⚠  Downloading is blocked until a valid cookies.txt is found (step 1).", theme.RED
        if not len(self._history):
            return "Scan a collection in step 2 first.", theme.TEXT_FAINT
        if not to_download:
            return "Everything found so far is downloaded. Scan again to find new reels.", theme.GREEN
        if self._cookie_check.status is not CookieStatus.OK:
            return f"⚠  {self._cookie_check.message}. Downloads will probably fail.", theme.AMBER
        return f"Ready - {plural(to_download, 'reel')} not downloaded yet.", theme.GREEN

    def _idle_detail(self) -> str:
        to_download = len(self._history.to_download())
        if to_download:
            return (
                f"{plural(to_download, 'reel')} from earlier scans waiting. "
                "Download them in step 3 or scan again."
            )
        if len(self._history):
            return "Everything is downloaded. Scan your collection to find newly saved reels."
        return AppState.IDLE.default_detail

    def _refresh_stats(self) -> None:
        """Update the counters and history read-out from the link history."""
        counts = self._history.counts()
        waiting = counts[LinkStatus.PENDING] + counts[LinkStatus.FAILED]
        self._stats["found"].set(len(self._history))
        self._stats["found"].set_hint(f"{waiting:,} waiting for download")
        for status in (LinkStatus.DOWNLOADED, LinkStatus.SKIPPED, LinkStatus.FAILED):
            self._stats[status.value].set(counts[status])
        if len(self._history):
            downloaded = counts[LinkStatus.DOWNLOADED]
            self._history_text.configure(
                text=f"{len(self._history):,} reels known  ·  {downloaded:,} downloaded  ·  "
                f"{waiting:,} waiting.  Stored in {config.LINKS_FILE.name}."
            )
        else:
            self._history_text.configure(text="Empty - nothing has been scanned or downloaded yet.")

    def _apply_cookie_check(self, check: CookieCheck) -> None:
        self._cookie_check = check
        title, color = _COOKIE_DISPLAY[check.status]
        self._cookie_dot.set_color(color)
        self._cookie_title.configure(text=title, text_color=color)
        location = "" if check.path == config.COOKIES_FILE else f"\n{check.path}"
        self._cookie_message.configure(text=f"{check.message}{location}")
        self._refresh_controls()

    def _poll_cookies(self) -> None:
        check = check_cookies(self._cookies_path)
        if (check.status, check.message) != (self._cookie_check.status, self._cookie_check.message):
            log.info("cookies.txt status: %s", check.message)
            self._apply_cookie_check(check)
        self.after(COOKIE_CHECK_INTERVAL_MS, self._poll_cookies)

    def _reset_download_readouts(self) -> None:
        self._overall_bar.set(0)
        self._overall_text.configure(text="-")
        self._file_bar.set(0)
        self._file_text.configure(text="Current file")
        self._file_speed.configure(text="")

    # =====================================================================
    # Background work
    # =====================================================================

    def _run_in_background(
        self,
        task: Callable[[], T],
        on_success: Callable[[T], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        def worker() -> None:
            try:
                result = task()
            except Exception as exc:  # noqa: BLE001 - reported to the UI
                log.debug("Background task failed", exc_info=True)
                self._dispatcher.post(on_error, exc)
            else:
                self._dispatcher.post(on_success, result)

        threading.Thread(target=worker, daemon=True).start()

    def _fail(self, title: str, exc: Exception) -> None:
        if isinstance(exc, BrowserError):
            self._browser_open = False
        log.error("%s: %s", title, exc)
        self._set_state(AppState.ERROR, f"{title}: {exc}")

    # --- Browser ---------------------------------------------------------

    def _open_browser(self) -> None:
        self._set_state(AppState.OPENING_BROWSER)

        def done(_: None) -> None:
            self._browser_open = True
            self._set_state(AppState.WAITING_FOR_LOGIN)

        def failed(exc: Exception) -> None:
            self._fail("Could not open the browser", exc)
            messagebox.showerror(
                "Browser error", f"{exc}\n\nOpen the log for technical details.", parent=self
            )

        self._run_in_background(self._browser.open, done, failed)

    def _export_cookies(self) -> None:
        if config.COOKIES_FILE.exists() and not messagebox.askyesno(
            "Replace cookies.txt?",
            f"{config.COOKIES_FILE} already exists.\n\nReplace it with the cookies from the app's browser?",
            parent=self,
        ):
            return
        self._set_state(AppState.OPENING_BROWSER, "Reading cookies from the browser...")

        def done(count: int) -> None:
            self._cookies_path = config.COOKIES_FILE
            self._apply_cookie_check(check_cookies(self._cookies_path))
            if self._cookie_check.status is CookieStatus.OK:
                self._set_state(AppState.WAITING_FOR_LOGIN, f"Saved {count} cookies - you're logged in.")
            else:
                self._set_state(
                    AppState.WAITING_FOR_LOGIN,
                    "Cookies saved, but you don't seem to be logged in yet. Log in and try again.",
                )

        self._run_in_background(
            lambda: self._browser.export_cookies(config.COOKIES_FILE),
            done,
            lambda exc: self._fail("Could not export cookies", exc),
        )

    # --- Scanning --------------------------------------------------------

    def _toggle_scan(self) -> None:
        if self._state is AppState.SEARCHING:
            self._request_stop()
        else:
            self._start_scan()

    def _start_scan(self) -> None:
        try:
            url = self._browser.current_url
        except BrowserError as exc:
            self._fail("Browser not available", exc)
            return
        if "/saved" not in url and not messagebox.askyesno(
            "Not on a saved collection",
            f"The browser is currently on:\n{url}\n\n"
            "This doesn't look like a saved collection. Scan this page anyway?",
            parent=self,
        ):
            return

        self._stop_event.clear()
        self._set_state(AppState.SEARCHING, "Scrolling through your collection... 0 found so far.")

        # Snapshots for the worker thread - the history itself stays on the main thread.
        already_downloaded = self._history.done_links()
        stop_after = int(self._stop_after.get()) if self._only_new.get() else None

        def progress(p: ScanProgress) -> None:
            self._dispatcher.post(self._on_scan_progress, p)

        self._run_in_background(
            lambda: self._browser.collect_links(
                self._stop_event,
                progress,
                already_downloaded=already_downloaded,
                stop_after_downloaded=stop_after,
            ),
            self._on_scan_finished,
            lambda exc: self._fail("Scan failed", exc),
        )

    def _on_scan_progress(self, p: ScanProgress) -> None:
        self._stats["found"].set(p.found)
        self._stats["found"].set_hint(f"{p.new:,} new in this scan")
        if self._state is not AppState.SEARCHING:
            return
        detail = f"Scrolling through your collection... {p.found:,} found, {p.new:,} new."
        if p.known_streak:
            detail += f" {p.known_streak} already downloaded in a row."
        if p.idle_scrolls:
            detail += f" Checking for more ({p.idle_scrolls}/{config.MAX_IDLE_SCROLLS})."
        self._status.set_detail(detail)

    def _on_scan_finished(self, result: ScanResult) -> None:
        new = self._history.merge_scan(result.links)
        try:
            self._history.save()
        except OSError as exc:
            log.error("Could not save %s: %s", self._history.path, exc)
        self._refresh_stats()

        if not result.links:
            self._set_state(
                AppState.WAITING_FOR_LOGIN,
                "No reels found. Make sure you're logged in and the collection is open, then scan again.",
            )
            return
        reason = {
            ScanEnd.COMPLETE: "Scan complete",
            ScanEnd.STOPPED: "Scan stopped",
            ScanEnd.REACHED_DOWNLOADED: "Reached reels you already downloaded",
        }[result.end]
        next_step = "Continue with step 3." if self._history.to_download() else "Nothing new to download."
        self._set_state(
            AppState.DONE,
            f"{reason} - {len(result.links):,} reels checked, {new:,} new. {next_step}",
        )

    # --- Downloading -----------------------------------------------------

    def _toggle_download(self) -> None:
        if self._state is AppState.DOWNLOADING:
            self._request_stop()
        else:
            self._start_download()

    def _start_download(self) -> None:
        raw_dir = self._download_dir.get().strip()
        if not raw_dir:
            messagebox.showwarning("No folder", "Please choose a download folder first.", parent=self)
            return
        download_dir = Path(raw_dir).expanduser()
        if not download_dir.is_absolute():
            download_dir = config.BASE_DIR / download_dir

        self._stop_event.clear()
        self._reset_download_readouts()
        self._set_state(AppState.DOWNLOADING, f"Saving to {download_dir}")

        urls = self._history.to_download()
        self._download_total = len(urls)
        cookies = self._cookies_path
        callbacks = DownloadCallbacks(
            on_item_start=lambda i, total, url: self._dispatcher.post(self._on_item_start, i, total, url),
            on_file_progress=self._post_file_progress,
            on_item_done=lambda i, url, res: self._dispatcher.post(self._on_item_done, i, url, res),
        )
        self._run_in_background(
            lambda: downloader.download_all(urls, download_dir, cookies, self._stop_event, callbacks),
            self._on_download_finished,
            lambda exc: self._fail("Download failed", exc),
        )

    def _post_file_progress(self, progress: FileProgress) -> None:
        """Called from the worker thread; throttles UI updates."""
        now = time.monotonic()
        if now - self._last_progress_post < PROGRESS_THROTTLE_SECONDS and progress.fraction != 1.0:
            return
        self._last_progress_post = now
        self._dispatcher.post(self._on_file_progress, progress)

    def _on_item_start(self, index: int, total: int, url: str) -> None:
        self._overall_bar.set(index / total)
        self._overall_text.configure(text=f"{index:,} / {total:,}  ·  {index / total:.0%}")
        self._file_bar.set(0)
        self._file_text.configure(text=f"Fetching {url}")
        self._file_speed.configure(text="")
        if self._state is AppState.DOWNLOADING:
            self._status.set_detail(f"Downloading reel {index + 1:,} of {total:,}...")

    def _on_file_progress(self, progress: FileProgress) -> None:
        name = progress.filename
        if len(name) > 60:
            name = name[:57] + "..."
        self._file_text.configure(text=name or "Current file")
        if progress.fraction is not None:
            self._file_bar.set(progress.fraction)
        parts = []
        if progress.fraction is not None:
            parts.append(f"{progress.fraction:.0%}")
        parts.append(format_bytes_per_second(progress.speed_bps))
        if progress.eta_seconds is not None:
            parts.append(f"ETA {format_duration(progress.eta_seconds)}")
        self._file_speed.configure(text="  ·  ".join(parts))

    def _on_item_done(self, index: int, url: str, result: LinkStatus) -> None:
        self._history.set_status(url, result)
        self._save_history(force=False)
        self._refresh_stats()
        total = self._download_total
        done = index + 1
        self._overall_bar.set(done / total)
        self._overall_text.configure(text=f"{done:,} / {total:,}  ·  {done / total:.0%}")
        if result is LinkStatus.DOWNLOADED:
            self._file_bar.set(1)

    def _save_history(self, force: bool = True) -> None:
        """Persist the history; when not forced, at most every few seconds."""
        now = time.monotonic()
        if not force and now - self._last_history_save < HISTORY_SAVE_INTERVAL_SECONDS:
            return
        self._last_history_save = now
        try:
            self._history.save()
        except OSError as exc:
            log.error("Could not save %s: %s", self._history.path, exc)

    def _on_download_finished(self, summary: DownloadSummary) -> None:
        self._save_history()
        self._refresh_stats()
        counts = f"{summary.downloaded:,} downloaded, {summary.skipped:,} skipped, {summary.failed:,} failed"
        self._file_speed.configure(text="")
        if summary.cancelled:
            self._set_state(AppState.IDLE, f"Download stopped - {counts}. Click Download to continue.")
        elif summary.failed and not summary.downloaded:
            self._set_state(
                AppState.ERROR,
                f"All downloads failed. Your cookies may be expired - export them again. ({counts})",
            )
        else:
            self._file_text.configure(text="Finished")
            self._set_state(AppState.DONE, f"Download complete - {counts}.")

    def _request_stop(self) -> None:
        self._stop_event.set()
        self._set_state(AppState.STOPPING)

    # =====================================================================
    # Simple actions
    # =====================================================================

    def _choose_download_dir(self) -> None:
        current = Path(self._download_dir.get()).expanduser()
        initial = current if current.is_dir() else config.BASE_DIR
        chosen = filedialog.askdirectory(parent=self, title="Choose download folder", initialdir=initial)
        if chosen:
            self._download_dir.set(str(Path(chosen)))
            log.info("Download folder set to %s", chosen)

    def _open_download_dir(self) -> None:
        path = Path(self._download_dir.get()).expanduser()
        try:
            path.mkdir(parents=True, exist_ok=True)
            open_in_file_manager(path)
        except OSError as exc:
            messagebox.showerror("Can't open folder", str(exc), parent=self)

    def _choose_cookies_file(self) -> None:
        chosen = filedialog.askopenfilename(
            parent=self,
            title="Choose cookies.txt",
            initialdir=self._cookies_path.parent,
            filetypes=[("Cookie files", "*.txt"), ("All files", "*.*")],
        )
        if chosen:
            self._cookies_path = Path(chosen)
            log.info("Using cookies from %s", chosen)
            self._apply_cookie_check(check_cookies(self._cookies_path))

    def _clear_history(self) -> None:
        if not messagebox.askyesno(
            "Clear download history?",
            f"This forgets all {len(self._history):,} found reels and which of them were downloaded "
            f"({config.LINKS_FILE.name} is deleted).\n\n"
            "Your downloaded video files are NOT deleted.\n\n"
            "The next scan will go through the whole collection again. Continue?",
            icon="warning",
            parent=self,
        ):
            return
        try:
            self._history.clear()
        except OSError as exc:
            messagebox.showerror("Could not clear history", str(exc), parent=self)
            return
        self._refresh_stats()
        self._reset_download_readouts()
        self._set_state(AppState.IDLE, "History cleared. Scan a collection to start over.")

    def _show_cookie_help(self) -> None:
        HelpDialog(self, self.fonts, "Getting your cookies.txt", help_content.COOKIES_HELP)

    def _toggle_log(self) -> None:
        if self._log_switch.get():
            self._log_panel.grid()
        else:
            self._log_panel.grid_remove()

    # =====================================================================
    # Logging & shutdown
    # =====================================================================

    def _install_log_handler(self) -> None:
        self._log_handler = _UiLogHandler(self._dispatcher, self._log_panel.append)
        self._log_handler.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%H:%M:%S"))
        logging.getLogger().addHandler(self._log_handler)

    def _on_close(self) -> None:
        if self._state.busy and not messagebox.askyesno(
            "Quit?", "A task is still running. Stop it and quit?", parent=self
        ):
            return
        self._stop_event.set()
        if len(self._history):
            self._save_history()  # keep statuses of items finished since the last periodic save
        self._browser.close()
        logging.getLogger().removeHandler(self._log_handler)
        self._dispatcher.stop()
        self.destroy()


def configure_logging() -> None:
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    logging.getLogger("collection_downloader").setLevel(logging.DEBUG)
    for noisy in ("urllib3", "selenium", "WDM"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    # Mirror the log to the terminal when there is one (not in windowed executables).
    if sys.stderr is not None:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
        root.addHandler(handler)


def run() -> None:
    configure_logging()
    App().mainloop()
