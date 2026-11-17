"""User-facing help texts, kept separate from layout code so they are easy to edit."""

from __future__ import annotations

from dataclasses import dataclass, field

from collection_downloader import config


@dataclass(frozen=True)
class Link:
    label: str
    url: str


@dataclass(frozen=True)
class HelpSection:
    title: str
    text: str = ""
    steps: tuple[str, ...] = ()
    links: tuple[Link, ...] = field(default_factory=tuple)


COOKIE_EXTENSION_LINKS = (
    Link(
        "Get cookies.txt LOCALLY (Chrome / Edge)",
        "https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc",
    ),
    Link("cookies.txt (Firefox)", "https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/"),
)

COOKIES_HELP: tuple[HelpSection, ...] = (
    HelpSection(
        "Why is this needed?",
        text=(
            "Your saved collections are private. The downloader sends your Instagram login "
            "cookies along with each request so Instagram knows it's you. The file never "
            "leaves your computer - but treat it like a password and never share it."
        ),
    ),
    HelpSection(
        "Option A - Easiest: use the app's browser",
        steps=(
            'Click "Open browser" in step 2 and log in to Instagram.',
            'Click "Get from browser" next to the cookie status in step 1.',
            "The status turns green - you're done.",
        ),
    ),
    HelpSection(
        "Option B - Browser extension",
        steps=(
            "Log in to instagram.com in your normal browser.",
            "Install one of the extensions below.",
            "While on instagram.com, click the extension and export in Netscape format.",
            f'Save the file as "cookies.txt" in:\n{config.BASE_DIR}\n'
            '...or pick it anywhere with "Choose file".',
        ),
        links=COOKIE_EXTENSION_LINKS,
    ),
    HelpSection(
        "Good to know",
        text=(
            "Cookies expire, and logging out of Instagram invalidates them. If downloads "
            "suddenly fail with login errors, simply export the cookies again."
        ),
    ),
)

GUIDE: tuple[HelpSection, ...] = (
    HelpSection(
        "Quick start",
        steps=(
            "Step 1 - Prepare: choose where videos are saved and make sure cookies.txt "
            "is found (green). Click the ? next to it if you don't have one yet.",
            'Step 2 - Find reels: click "Open browser", log in to Instagram and open the '
            'saved collection you want (Profile > Saved > a collection). Then click "Scan collection". '
            "The app scrolls through it and remembers every reel and post.",
            'Step 3 - Download: click "Download". Only reels that weren\'t downloaded before are '
            "fetched. Progress is shown for the whole batch and for the current file.",
        ),
    ),
    HelpSection(
        "Downloading only newly saved reels",
        text=(
            f"The app keeps a history of every reel it found and whether it was downloaded "
            f"({config.LINKS_FILE.name}). Saved collections show your newest saves first, so with "
            '"Only new reels" turned on (step 2) the scan stops as soon as it finds a few '
            "already-downloaded reels in a row. A regular scan + download then only fetches what you "
            "saved since last time. Turn the option off to go through the whole collection - for "
            'example to catch up on older reels. "Clear history" in step 3 forgets everything and '
            "starts over (your video files are kept)."
        ),
    ),
    HelpSection(
        "Getting cookies.txt",
        text=(
            "Downloads need your Instagram login cookies. The easiest way: open the browser "
            'in step 2, log in, then click "Get from browser" in step 1. '
            "Alternatively, export them with a browser extension:"
        ),
        links=COOKIE_EXTENSION_LINKS,
    ),
    HelpSection(
        "Where do my files go?",
        text=(
            f"Videos are saved to the folder chosen in step 1 (default: {config.DEFAULT_DOWNLOAD_DIR}). "
            f"Found links and their download status are stored in {config.LINKS_FILE.name}, so you can "
            "close the app and continue later without scanning again."
        ),
    ),
    HelpSection(
        "Reading the counters",
        steps=(
            "Reels found - all reels and posts in your history (during a scan: found in this scan).",
            "Downloaded - reels downloaded successfully (or already on disk).",
            "Skipped - posts without a video, e.g. photo-only posts. They are not tried again.",
            "Failed - reels that could not be downloaded. They are retried on the next download; "
            "open the log to see why they failed.",
        ),
    ),
    HelpSection(
        "Troubleshooting",
        steps=(
            "Browser doesn't open: install or update Google Chrome.",
            "Scan finds 0 reels: make sure you are logged in and the collection page is open.",
            'Scan stops too early: turn off "Only new reels" in step 2 to scan the whole collection.',
            "Many downloads fail: your cookies are probably expired - export them again.",
            "Lower video quality: install FFmpeg so video and audio can be merged.",
            'Need details? Turn on "Show log" at the bottom of the window.',
        ),
        links=(Link("Download FFmpeg", "https://ffmpeg.org/download.html"),),
    ),
    HelpSection(
        "Disclaimer",
        text=(
            "For personal use only. Downloading content may violate Instagram's Terms of "
            "Service - only download content you have the right to."
        ),
    ),
)
