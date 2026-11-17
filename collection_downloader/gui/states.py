"""The states the application can be in, with the label/color shown in the status panel."""

from __future__ import annotations

from enum import Enum

from collection_downloader.gui import theme


class AppState(Enum):
    #             label                 accent color   busy   default detail text
    IDLE = ("Ready", theme.GRAY, False, "Follow the three steps below to get started.")
    OPENING_BROWSER = ("Opening browser", theme.BLUE, True, "Starting Google Chrome...")
    WAITING_FOR_LOGIN = (
        "Waiting for login",
        theme.CYAN,
        False,
        "Log in to Instagram in the browser window and open your saved collection.",
    )
    SEARCHING = ("Searching", theme.AMBER, True, "Scrolling through your collection...")
    DOWNLOADING = ("Downloading", theme.PINK, True, "Downloading media...")
    STOPPING = ("Stopping", theme.ORANGE, True, "Finishing the current step...")
    DONE = ("Done", theme.GREEN, False, "All done!")
    ERROR = ("Error", theme.RED, False, "Something went wrong. Open the log for details.")

    def __init__(self, label: str, color: str, busy: bool, detail: str) -> None:
        self.label = label
        self.color = color
        self.busy = busy
        self.default_detail = detail
