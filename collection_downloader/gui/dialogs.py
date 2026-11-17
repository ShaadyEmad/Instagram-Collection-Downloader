"""Popup windows."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Sequence

import customtkinter as ctk

from collection_downloader.gui import theme
from collection_downloader.gui.help_content import HelpSection
from collection_downloader.gui.widgets import HelpView


class HelpDialog(ctk.CTkToplevel):
    """A modal window that shows help sections."""

    def __init__(
        self,
        master: tk.Misc,
        fonts: theme.Fonts,
        title: str,
        sections: Sequence[HelpSection],
        width: int = 560,
        height: int = 600,
    ) -> None:
        super().__init__(master, fg_color=theme.BG)
        self.title(title)
        self.minsize(420, 360)
        self._center_on(master, width, height)
        self.transient(master.winfo_toplevel())

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(self, text=title, font=fonts.title, text_color=theme.TEXT, anchor="w").grid(
            row=0, column=0, sticky="ew", padx=20, pady=(18, 8)
        )

        scroll = ctk.CTkScrollableFrame(
            self,
            fg_color=theme.SURFACE,
            corner_radius=theme.RADIUS,
            border_width=1,
            border_color=theme.BORDER,
        )
        scroll.grid(row=1, column=0, sticky="nsew", padx=20)
        scroll.grid_columnconfigure(0, weight=1)
        HelpView(scroll, fonts, sections).grid(row=0, column=0, sticky="nsew", padx=12, pady=12)

        ctk.CTkButton(
            self,
            text="Got it",
            width=120,
            font=fonts.body_bold,
            fg_color=theme.ACCENT,
            hover_color=theme.ACCENT_HOVER,
            command=self.destroy,
        ).grid(row=2, column=0, sticky="e", padx=20, pady=16)

        self.bind("<Escape>", lambda _e: self.destroy())
        # Grabbing must wait until the window is actually mapped (required on Linux).
        self.after(150, self._make_modal)

    def _center_on(self, master: tk.Misc, width: int, height: int) -> None:
        root = master.winfo_toplevel()
        x = root.winfo_rootx() + (root.winfo_width() - width) // 2
        y = root.winfo_rooty() + (root.winfo_height() - height) // 2
        self.geometry(f"{width}x{height}+{max(x, 0)}+{max(y, 0)}")

    def _make_modal(self) -> None:
        try:
            self.lift()
            self.focus_force()
            self.grab_set()
        except tk.TclError:
            pass  # window was closed before it became visible
