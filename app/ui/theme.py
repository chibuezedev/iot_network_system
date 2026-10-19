"""
Theme runtime: light/dark switching (persisted in prefs.json), font creation,
and listener callbacks for anything CustomTkinter does not recolour itself
(matplotlib figures, tk.Canvas drawings).
"""
from __future__ import annotations

from typing import Callable

import customtkinter as ctk

from app.ui import tokens
from services import prefs

_listeners: list[Callable[[], None]] = []
_fonts: dict[str, ctk.CTkFont] = {}
_families: dict[str, str] = {}


def init() -> None:
    """Call once before creating the root window."""
    ctk.set_appearance_mode(prefs.get("theme") or "dark")
    ctk.set_default_color_theme("blue")   # base widget geometry; colours come from tokens


def mode() -> str:
    return "dark" if ctk.get_appearance_mode().lower() == "dark" else "light"


def pick(pair) -> str:
    """Resolve a (light, dark) token for code that needs a single hex colour."""
    if isinstance(pair, str):
        return pair
    return pair[1] if mode() == "dark" else pair[0]


def set_mode(new_mode: str) -> None:
    new_mode = "dark" if new_mode == "dark" else "light"
    ctk.set_appearance_mode(new_mode)
    prefs.set("theme", new_mode)
    for cb in list(_listeners):
        try:
            cb()
        except Exception:
            pass


def toggle() -> None:
    set_mode("light" if mode() == "dark" else "dark")


def on_change(cb: Callable[[], None]) -> Callable[[], None]:
    """Register a callback run after every theme change; returns an unsubscribe function."""
    _listeners.append(cb)
    return lambda: _listeners.remove(cb) if cb in _listeners else None


def _family(kind: str) -> str:
    if kind not in _families:
        import tkinter.font as tkfont
        available = set(tkfont.families())
        options = tokens.MONO_FAMILIES if kind == "mono" else tokens.FONT_FAMILIES
        _families[kind] = next((f for f in options if f in available), "TkDefaultFont")
    return _families[kind]


def font(role: str) -> ctk.CTkFont:
    """Shared CTkFont for a role in tokens.FONT_ROLES (create after the root exists)."""
    if role not in _fonts:
        kind, size, weight = tokens.FONT_ROLES[role]
        _fonts[role] = ctk.CTkFont(family=_family(kind), size=size, weight=weight)
    return _fonts[role]


def family(kind: str = "sans") -> str:
    return _family(kind)
