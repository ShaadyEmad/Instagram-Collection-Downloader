"""Colors, spacing and fonts used throughout the interface."""

from __future__ import annotations

import sys
from dataclasses import dataclass

import customtkinter as ctk

# --- Surfaces ---
BG = "#0E1014"
SURFACE = "#171A21"
SURFACE_ALT = "#1F232C"
BORDER = "#2A2F3A"

# --- Text ---
TEXT = "#E8EAF0"
TEXT_MUTED = "#8C94A6"
TEXT_FAINT = "#5D6577"

# --- Accents ---
ACCENT = "#E1306C"  # Instagram pink
ACCENT_HOVER = "#C2255B"
SECONDARY = "#2A2F3A"
SECONDARY_HOVER = "#363C4A"

# --- Semantic ---
GRAY = "#8C94A6"
BLUE = "#3B82F6"
CYAN = "#22B8CF"
AMBER = "#F59E0B"
PINK = "#E1306C"
ORANGE = "#F97316"
GREEN = "#22C55E"
RED = "#EF4444"
RED_HOVER = "#DC2626"

# --- Geometry ---
RADIUS = 12
PAD = 16
GAP = 10


@dataclass(frozen=True)
class Fonts:
    """Fonts can only be created once a Tk root exists, hence the factory."""

    title: ctk.CTkFont
    subtitle: ctk.CTkFont
    heading: ctk.CTkFont
    body: ctk.CTkFont
    body_bold: ctk.CTkFont
    small: ctk.CTkFont
    stat: ctk.CTkFont
    status: ctk.CTkFont
    mono: ctk.CTkFont

    @classmethod
    def create(cls) -> Fonts:
        if sys.platform.startswith("win"):
            mono_family = "Consolas"
        elif sys.platform == "darwin":
            mono_family = "Menlo"
        else:
            mono_family = "DejaVu Sans Mono"
        return cls(
            title=ctk.CTkFont(size=20, weight="bold"),
            subtitle=ctk.CTkFont(size=12),
            heading=ctk.CTkFont(size=15, weight="bold"),
            body=ctk.CTkFont(size=13),
            body_bold=ctk.CTkFont(size=13, weight="bold"),
            small=ctk.CTkFont(size=11),
            stat=ctk.CTkFont(size=26, weight="bold"),
            status=ctk.CTkFont(size=16, weight="bold"),
            mono=ctk.CTkFont(family=mono_family, size=11),
        )


def apply_global_theme() -> None:
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
