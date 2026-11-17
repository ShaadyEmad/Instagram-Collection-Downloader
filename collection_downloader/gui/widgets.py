"""Reusable, self-contained widgets."""

from __future__ import annotations

import logging
import tkinter as tk
import webbrowser
from collections.abc import Sequence

import customtkinter as ctk

from collection_downloader.gui import theme
from collection_downloader.gui.help_content import HelpSection
from collection_downloader.gui.states import AppState


def blend(color_a: str, color_b: str, t: float) -> str:
    """Linear blend of two ``#rrggbb`` colors (t=0 -> a, t=1 -> b)."""
    a = [int(color_a[i : i + 2], 16) for i in (1, 3, 5)]
    b = [int(color_b[i : i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b, strict=True))


class Card(ctk.CTkFrame):
    """Rounded surface used as the base for every panel."""

    def __init__(self, master: tk.Misc, **kwargs) -> None:
        kwargs.setdefault("fg_color", theme.SURFACE)
        kwargs.setdefault("corner_radius", theme.RADIUS)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", theme.BORDER)
        super().__init__(master, **kwargs)


class ActionButton(ctk.CTkButton):
    """Button with color variants and a clearly muted disabled look."""

    VARIANTS: dict[str, tuple[str, str]] = {
        "primary": (theme.ACCENT, theme.ACCENT_HOVER),
        "secondary": (theme.SECONDARY, theme.SECONDARY_HOVER),
        "danger": (theme.RED, theme.RED_HOVER),
    }

    def __init__(self, master: tk.Misc, variant: str = "secondary", **kwargs) -> None:
        kwargs.setdefault("corner_radius", 8)
        kwargs.setdefault("text_color", "#FFFFFF")
        kwargs.setdefault("text_color_disabled", theme.TEXT_FAINT)
        super().__init__(master, **kwargs)
        self._variant = variant
        self._enabled = True
        self._apply_colors()

    def set_variant(self, variant: str) -> None:
        if variant != self._variant:
            self._variant = variant
            self._apply_colors()

    def set_enabled(self, enabled: bool) -> None:
        if enabled != self._enabled:
            self._enabled = enabled
            self.configure(state="normal" if enabled else "disabled")
            self._apply_colors()

    def _apply_colors(self) -> None:
        color, hover = self.VARIANTS[self._variant]
        if not self._enabled:
            color = hover = theme.SURFACE_ALT
        self.configure(fg_color=color, hover_color=hover)


class WrappingLabel(ctk.CTkLabel):
    """A label that re-wraps its text to the available width."""

    def __init__(self, master: tk.Misc, padding: int = 0, **kwargs) -> None:
        kwargs.setdefault("justify", "left")
        kwargs.setdefault("anchor", "w")
        super().__init__(master, **kwargs)
        self._padding = padding
        # CTkLabel.bind() targets the inner text label, whose width depends on the
        # wraplength itself (-> endless shrink loop). Bind the outer frame instead,
        # whose width is dictated by the layout manager.
        tk.Frame.bind(self, "<Configure>", self._rewrap, add="+")

    def _rewrap(self, event: tk.Event) -> None:
        width = max(event.width - self._padding, 50)
        if abs(self.cget("wraplength") - width) > 2:
            self.configure(wraplength=width)


class Dot(ctk.CTkFrame):
    """A small colored circle that can softly pulse to indicate activity."""

    _PULSE_STEPS = 16
    _PULSE_INTERVAL_MS = 60

    def __init__(self, master: tk.Misc, size: int = 12, color: str = theme.GRAY) -> None:
        super().__init__(master, width=size, height=size, corner_radius=size // 2, fg_color=color)
        self._color = color
        self._pulse_job: str | None = None
        self._step = 0

    def set_color(self, color: str, pulse: bool = False) -> None:
        self._color = color
        self.configure(fg_color=color)
        self._stop_pulse()
        if pulse:
            self._pulse()

    def _pulse(self) -> None:
        # Triangle wave between full color and a dimmed variant.
        half = self._PULSE_STEPS // 2
        t = abs(self._step % self._PULSE_STEPS - half) / half
        self.configure(fg_color=blend(self._color, theme.SURFACE, 0.65 * (1 - t)))
        self._step += 1
        self._pulse_job = self.after(self._PULSE_INTERVAL_MS, self._pulse)

    def _stop_pulse(self) -> None:
        if self._pulse_job is not None:
            self.after_cancel(self._pulse_job)
            self._pulse_job = None

    def destroy(self) -> None:
        self._stop_pulse()
        super().destroy()


class StatusPanel(Card):
    """Large status read-out with a colored accent bar, state label and detail text."""

    def __init__(self, master: tk.Misc, fonts: theme.Fonts) -> None:
        super().__init__(master)
        self.grid_columnconfigure(1, weight=1)

        # height=1: let the grid stretch it (CTkFrame defaults to 200px tall).
        self._accent = ctk.CTkFrame(self, width=5, height=1, corner_radius=3, fg_color=theme.GRAY)
        self._accent.grid(row=0, column=0, rowspan=2, sticky="ns", padx=(10, 0), pady=12)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=1, sticky="ew", padx=14, pady=(12, 0))
        ctk.CTkLabel(header, text="STATUS", font=fonts.small, text_color=theme.TEXT_FAINT).pack(
            side="left", padx=(0, 10)
        )
        self._dot = Dot(header)
        self._dot.pack(side="left", padx=(0, 8))
        self._label = ctk.CTkLabel(header, text="", font=fonts.status, text_color=theme.TEXT)
        self._label.pack(side="left")

        self._detail = WrappingLabel(self, padding=4, text="", font=fonts.body, text_color=theme.TEXT_MUTED)
        self._detail.grid(row=1, column=1, sticky="ew", padx=14, pady=(2, 12))

    def set_state(self, state: AppState, detail: str | None = None) -> None:
        self._accent.configure(fg_color=state.color)
        self._dot.set_color(state.color, pulse=state.busy)
        self._label.configure(text=state.label, text_color=state.color)
        self.set_detail(detail or state.default_detail)

    def set_detail(self, detail: str) -> None:
        self._detail.configure(text=detail)


class StatCard(Card):
    """Caption + big number."""

    def __init__(
        self, master: tk.Misc, fonts: theme.Fonts, caption: str, accent: str, hint: str = ""
    ) -> None:
        super().__init__(master)
        self._count = 0
        ctk.CTkFrame(self, height=3, corner_radius=2, fg_color=accent).pack(fill="x", padx=14, pady=(10, 0))
        self._value = ctk.CTkLabel(self, text="0", font=fonts.stat, text_color=theme.TEXT, anchor="w")
        self._value.pack(fill="x", padx=14, pady=(2, 0))
        ctk.CTkLabel(self, text=caption, font=fonts.body_bold, text_color=theme.TEXT_MUTED, anchor="w").pack(
            fill="x", padx=14
        )
        self._hint = ctk.CTkLabel(self, text=hint, font=fonts.small, text_color=theme.TEXT_FAINT, anchor="w")
        self._hint.pack(fill="x", padx=14)
        ctk.CTkFrame(self, height=6, fg_color="transparent").pack()

    @property
    def value(self) -> int:
        return self._count

    def set(self, value: int) -> None:
        self._count = value
        self._value.configure(text=f"{value:,}")

    def increment(self, by: int = 1) -> None:
        self.set(self._count + by)

    def set_hint(self, hint: str) -> None:
        self._hint.configure(text=hint)


class StepCard(Card):
    """A numbered step with title, explanatory text and a ``body`` frame for controls."""

    def __init__(
        self, master: tk.Misc, fonts: theme.Fonts, number: int, title: str, description: str
    ) -> None:
        super().__init__(master)
        self.grid_columnconfigure(1, weight=1)

        badge = ctk.CTkLabel(
            self,
            text=str(number),
            width=30,
            height=30,
            corner_radius=15,
            fg_color=theme.ACCENT,
            text_color="#FFFFFF",
            font=fonts.body_bold,
        )
        badge.grid(row=0, column=0, rowspan=2, sticky="n", padx=(theme.PAD, 12), pady=(14, 0))

        ctk.CTkLabel(self, text=title, font=fonts.heading, text_color=theme.TEXT, anchor="w").grid(
            row=0, column=1, sticky="ew", padx=(0, theme.PAD), pady=(14, 0)
        )
        WrappingLabel(self, padding=4, text=description, font=fonts.body, text_color=theme.TEXT_MUTED).grid(
            row=1, column=1, sticky="ew", padx=(0, theme.PAD), pady=(2, 0)
        )

        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.grid(row=2, column=1, sticky="ew", padx=(0, theme.PAD), pady=(10, 14))


class Tooltip:
    """Shows ``text`` in a small popup when hovering ``widget``."""

    def __init__(self, widget: tk.Misc, text: str, delay_ms: int = 450) -> None:
        self.text = text
        self._widget = widget
        self._delay = delay_ms
        self._job: str | None = None
        self._tip: tk.Toplevel | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event: tk.Event | None = None) -> None:
        self._cancel()
        self._job = self._widget.after(self._delay, self._show)

    def _cancel(self) -> None:
        if self._job is not None:
            self._widget.after_cancel(self._job)
            self._job = None

    def _show(self) -> None:
        if not self.text or self._tip is not None:
            return
        x = self._widget.winfo_pointerx() + 14
        y = self._widget.winfo_pointery() + 18
        self._tip = tip = tk.Toplevel(self._widget)
        tip.wm_overrideredirect(True)
        tip.configure(bg=theme.BORDER)
        tk.Label(
            tip,
            text=self.text,
            justify="left",
            wraplength=300,
            bg=theme.SURFACE_ALT,
            fg=theme.TEXT,
            padx=10,
            pady=6,
        ).pack(padx=1, pady=1)
        tip.wm_geometry(f"+{x}+{y}")

    def _hide(self, _event: tk.Event | None = None) -> None:
        self._cancel()
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None


class HelpView(ctk.CTkFrame):
    """Renders a list of :class:`HelpSection` (headings, text, numbered steps, links)."""

    def __init__(
        self, master: tk.Misc, fonts: theme.Fonts, sections: Sequence[HelpSection], **kwargs
    ) -> None:
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)
        self.grid_columnconfigure(0, weight=1)
        row = 0
        for section in sections:
            ctk.CTkLabel(
                self, text=section.title, font=fonts.heading, text_color=theme.TEXT, anchor="w"
            ).grid(row=row, column=0, sticky="ew", pady=(14 if row else 0, 4))
            row += 1

            if section.text:
                WrappingLabel(self, text=section.text, font=fonts.body, text_color=theme.TEXT_MUTED).grid(
                    row=row, column=0, sticky="ew", pady=2
                )
                row += 1

            for number, step in enumerate(section.steps, start=1):
                self._step_row(fonts, number, step).grid(row=row, column=0, sticky="ew", pady=3)
                row += 1

            for link in section.links:
                ctk.CTkButton(
                    self,
                    text=f"↗  {link.label}",
                    font=fonts.body,
                    anchor="w",
                    fg_color="transparent",
                    hover_color=theme.SURFACE_ALT,
                    text_color=theme.ACCENT,
                    height=26,
                    command=lambda url=link.url: webbrowser.open(url),
                ).grid(row=row, column=0, sticky="w", pady=1)
                row += 1

    def _step_row(self, fonts: theme.Fonts, number: int, text: str) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            frame,
            text=str(number),
            width=22,
            height=22,
            corner_radius=11,
            fg_color=theme.SURFACE_ALT,
            text_color=theme.TEXT,
            font=fonts.small,
        ).grid(row=0, column=0, sticky="n", padx=(0, 10), pady=1)
        WrappingLabel(frame, text=text, font=fonts.body, text_color=theme.TEXT_MUTED).grid(
            row=0, column=1, sticky="ew"
        )
        return frame


class LogPanel(Card):
    """Read-only, color-coded log output."""

    MAX_LINES = 5000
    _LEVEL_COLORS = {
        logging.DEBUG: theme.TEXT_FAINT,
        logging.INFO: theme.TEXT,
        logging.WARNING: theme.AMBER,
        logging.ERROR: theme.RED,
    }

    def __init__(self, master: tk.Misc, fonts: theme.Fonts) -> None:
        super().__init__(master)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(8, 0))
        ctk.CTkLabel(header, text="Detailed log", font=fonts.body_bold, text_color=theme.TEXT).pack(
            side="left"
        )
        ctk.CTkButton(
            header,
            text="Clear",
            width=60,
            height=24,
            font=fonts.small,
            fg_color=theme.SECONDARY,
            hover_color=theme.SECONDARY_HOVER,
            command=self.clear,
        ).pack(side="right")

        self._text = ctk.CTkTextbox(
            self,
            font=fonts.mono,
            fg_color=theme.BG,
            text_color=theme.TEXT,
            wrap="word",
            height=150,
        )
        self._text.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        for level, color in self._LEVEL_COLORS.items():
            self._text.tag_config(logging.getLevelName(level), foreground=color)
        self._text.configure(state="disabled")

    def append(self, levelno: int, message: str) -> None:
        tag = logging.getLevelName(min(self._LEVEL_COLORS, key=lambda lvl: abs(lvl - levelno)))
        at_bottom = self._text.yview()[1] >= 0.999
        self._text.configure(state="normal")
        self._text.insert("end", message + "\n", tag)
        line_count = int(self._text.index("end-1c").split(".")[0])
        if line_count > self.MAX_LINES:
            self._text.delete("1.0", f"{line_count - self.MAX_LINES}.0")
        self._text.configure(state="disabled")
        if at_bottom:
            self._text.see("end")

    def clear(self) -> None:
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._text.configure(state="disabled")
