"""Vigil widget kit (CustomTkinter). Colours come from app.ui.tokens as
(light, dark) pairs, so every widget here follows the light/dark toggle."""
from __future__ import annotations

import math
import time
import tkinter as tk
from typing import Callable, Iterable, Optional, Sequence

import customtkinter as ctk

from app.ui import theme, tokens as T


# ---------------------------------------------------------------- text
def label(parent, text: str = "", role: str = "body", color=T.TEXT, **kw) -> ctk.CTkLabel:
    kw.setdefault("anchor", "w")
    kw.setdefault("justify", "left")
    return ctk.CTkLabel(parent, text=text, font=theme.font(role), text_color=color, **kw)


def autowrap(lbl: ctk.CTkLabel, container, margin: int = 32) -> ctk.CTkLabel:
    """Keep a label's wraplength equal to its container's width (in CTk units)."""
    def _fit(event):
        if not lbl.winfo_exists():   # label destroyed (e.g. drawer reopened); binding is stale
            return
        scale = ctk.ScalingTracker.get_widget_scaling(lbl)
        lbl.configure(wraplength=max(120, int(event.width / scale) - margin))
    container.bind("<Configure>", _fit, add="+")
    return lbl


def spacer(parent) -> ctk.CTkFrame:
    """An empty frame that takes no space until children are added (CTkFrame defaults to 200 px)."""
    return ctk.CTkFrame(parent, fg_color="transparent", height=1, width=1)


def page_header(parent, title: str, subtitle: str = "") -> ctk.CTkFrame:
    f = ctk.CTkFrame(parent, fg_color="transparent")
    label(f, title, "h1").pack(anchor="w")
    if subtitle:
        label(f, subtitle, "body", T.MUTED, wraplength=1000).pack(anchor="w", pady=(2, 0))
    return f


def section_title(parent, text: str, note: str = "") -> ctk.CTkFrame:
    f = ctk.CTkFrame(parent, fg_color="transparent")
    label(f, text, "h2").pack(side="left")
    if note:
        label(f, note, "small", T.MUTED).pack(side="right")
    return f


# ---------------------------------------------------------------- containers
class Card(ctk.CTkFrame):
    def __init__(self, parent, padding: int = T.SPACE["l"], **kw):
        kw.setdefault("fg_color", T.SURFACE)
        kw.setdefault("border_color", T.BORDER)
        kw.setdefault("border_width", 1)
        kw.setdefault("corner_radius", T.RADIUS_CARD)
        super().__init__(parent, **kw)
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=padding, pady=padding)


class Page(ctk.CTkScrollableFrame):
    """Scrollable screen body. Mouse-wheel scrolling works anywhere over it."""

    def __init__(self, parent, **kw):
        kw.setdefault("fg_color", T.BG)
        super().__init__(parent, corner_radius=0, **kw)
        self.columnconfigure(0, weight=1)

    def to_top(self) -> None:
        self._parent_canvas.yview_moveto(0)


def note_box(parent, text: str, color=T.ACCENT) -> ctk.CTkFrame:
    f = ctk.CTkFrame(parent, fg_color=T.SURFACE, border_color=color, border_width=1, corner_radius=T.RADIUS_CARD)
    lbl = label(f, text, "body", T.TEXT, wraplength=900)
    lbl.pack(anchor="w", fill="x", padx=T.SPACE["l"], pady=T.SPACE["m"])
    autowrap(lbl, f, margin=2 * T.SPACE["l"] + 8)
    return f


# ---------------------------------------------------------------- buttons
def button(parent, text: str, command: Callable, kind: str = "primary", **kw) -> ctk.CTkButton:
    styles = {
        "primary": dict(fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER, text_color=T.ON_ACCENT),
        "secondary": dict(fg_color=T.SURFACE_2, hover_color=T.BORDER, text_color=T.TEXT,
                          border_color=T.BORDER, border_width=1),
        "ghost": dict(fg_color="transparent", hover_color=T.SURFACE_2, text_color=T.MUTED),
        "danger": dict(fg_color="transparent", hover_color=T.SURFACE_2, text_color=T.DANGER,
                       border_color=T.DANGER, border_width=1),
    }
    kw.setdefault("corner_radius", 8)
    kw.setdefault("height", 34)
    return ctk.CTkButton(parent, text=text, command=command, font=theme.font("body_bold"),
                         **{**styles[kind], **kw})


# ---------------------------------------------------------------- badges
class Badge(ctk.CTkFrame):
    """Alert badge. Detected = FILLED, Predicted = OUTLINED (plus a filled/hollow
    glyph, so the difference never relies on colour alone)."""

    def __init__(self, parent, level: str, kind: str = "", width: int = 178, bg=T.SURFACE):
        color = T.ALERT.get(level, T.MUTED)
        if kind == "Predicted":
            # explicit bg: a "transparent" CTkFrame draws its border incorrectly
            super().__init__(parent, fg_color=bg, bg_color=bg, border_color=color, border_width=2,
                             corner_radius=T.RADIUS_BADGE, width=width, height=26)
            text, fg = f"○  PREDICTED · {level}", color
        elif kind == "Detected":
            super().__init__(parent, fg_color=color, border_color=color, border_width=2,
                             corner_radius=T.RADIUS_BADGE, width=width, height=26)
            text, fg = f"●  DETECTED · {level}", T.ON_FILL
        else:   # plain level chip (e.g. NORMAL, or n/a)
            super().__init__(parent, fg_color=T.SURFACE_2, border_color=T.BORDER, border_width=1,
                             corner_radius=T.RADIUS_BADGE, width=width, height=26)
            text, fg = level, color
        self.pack_propagate(False)
        # inset so the label's background never covers the (outlined) border
        label(self, text, "small_bold", fg, anchor="center").pack(fill="both", expand=True, padx=6, pady=3)


# ---------------------------------------------------------------- tiles
class StatTile(Card):
    def __init__(self, parent, caption: str, value: str = "—", color=T.TEXT, sub: str = ""):
        super().__init__(parent, padding=T.SPACE["l"])
        self.caption = label(self.body, caption.upper(), "small_bold", T.MUTED)
        self.caption.pack(anchor="w")
        self.value = autowrap(label(self.body, value, "h1", color), self.body, margin=4)
        self.value.pack(anchor="w", fill="x", pady=(4, 0))
        self.sub = autowrap(label(self.body, sub, "small", T.MUTED), self.body, margin=4)
        self.sub.pack(anchor="w", fill="x")

    def set(self, value: str, color=None, sub: Optional[str] = None) -> None:
        self.value.configure(text=value)
        if color is not None:
            self.value.configure(text_color=color)
        if sub is not None:
            self.sub.configure(text=sub)


class ProbBar(ctk.CTkFrame):
    """Label + value + thin bar for a probability in [0, 1]."""

    def __init__(self, parent, caption: str, color=T.ACCENT):
        super().__init__(parent, fg_color="transparent")
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x")
        self.caption = label(top, caption, "small", T.MUTED)
        self.caption.pack(side="left")
        self.value = label(top, "—", "mono_bold", T.TEXT)
        self.value.pack(side="right")
        self.bar = ctk.CTkProgressBar(self, height=6, corner_radius=3, progress_color=color, fg_color=T.SURFACE_2)
        self.bar.pack(fill="x", pady=(3, 0))
        self.bar.set(0)

    def set(self, p: Optional[float], text_color=T.TEXT) -> None:
        if p is None or (isinstance(p, float) and math.isnan(p)):
            self.value.configure(text="n/a", text_color=T.MUTED)
            self.bar.set(0)
            return
        self.value.configure(text=f"{p:.3f}", text_color=text_color)
        self.bar.set(max(0.0, min(1.0, float(p))))


# ---------------------------------------------------------------- tables
def fmt_value(v) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    if isinstance(v, float):
        if v.is_integer() and abs(v) >= 1000:
            return f"{v:,.0f}"
        return f"{v:.4f}"
    if isinstance(v, int) and abs(v) >= 1000:
        return f"{v:,}"
    return str(v)


class Table(ctk.CTkFrame):
    """Small read-only grid table (header + rows). For report-sized data
    (tens of rows); long lists use a paged list instead."""

    def __init__(self, parent, columns: Sequence[str], rows: Iterable[Sequence], headers: Optional[Sequence[str]] = None,
                 numeric: Optional[set] = None, emphasis_row: Optional[int] = None, mono_cols: Optional[set] = None):
        super().__init__(parent, fg_color=T.SURFACE, corner_radius=8, border_color=T.BORDER, border_width=1)
        headers = list(headers or columns)
        numeric = numeric or set()
        mono_cols = mono_cols if mono_cols is not None else numeric
        for j, h in enumerate(headers):
            cell = ctk.CTkFrame(self, fg_color=T.SURFACE_2, corner_radius=0)
            cell.grid(row=0, column=j, sticky="nsew", padx=(1 if j == 0 else 0, 1 if j == len(headers) - 1 else 0),
                      pady=(1, 0))
            label(cell, h, "small_bold", T.MUTED, anchor="e" if columns[j] in numeric else "w").pack(
                fill="x", padx=10, pady=6)
        for i, row in enumerate(rows, start=1):
            bold = emphasis_row is not None and i - 1 == emphasis_row
            for j, v in enumerate(row):
                col = columns[j]
                role = ("mono_bold" if bold else "mono") if col in mono_cols else ("body_bold" if bold else "body")
                label(self, fmt_value(v), role, T.TEXT, anchor="e" if col in numeric else "w").grid(
                    row=i, column=j, sticky="ew", padx=10, pady=4)
        for j in range(len(headers)):
            self.columnconfigure(j, weight=1)


# ---------------------------------------------------------------- toast
class Toast(ctk.CTkToplevel):
    _active: list["Toast"] = []

    def __init__(self, root, title: str, message: str, kind: str = "info", duration_ms: int = 4200):
        super().__init__(root)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        accent = {"info": T.ACCENT, "success": T.ALERT["NORMAL"], "warning": T.ALERT["HIGH"],
                  "critical": T.ALERT["CRITICAL"]}.get(kind, T.ACCENT)
        self.configure(fg_color=T.SURFACE)
        frame = ctk.CTkFrame(self, fg_color=T.SURFACE, border_color=accent, border_width=2, corner_radius=10)
        frame.pack(fill="both", expand=True)
        label(frame, title, "body_bold", accent).pack(anchor="w", padx=14, pady=(10, 0))
        label(frame, message, "small", T.TEXT, wraplength=300).pack(anchor="w", padx=14, pady=(2, 10))
        self.root = root
        self.update_idletasks()
        w, h = 340, max(64, self.winfo_reqheight())
        stack = sum(t.winfo_height() + 10 for t in Toast._active if t.winfo_exists())
        x = root.winfo_rootx() + root.winfo_width() - w - 24
        y = root.winfo_rooty() + root.winfo_height() - h - 24 - stack
        self.geometry(f"{w}x{h}+{x}+{y}")
        Toast._active.append(self)
        self.after(duration_ms, self._close)

    def _close(self) -> None:
        if self in Toast._active:
            Toast._active.remove(self)
        if self.winfo_exists():
            self.destroy()


def show_toast(root, title: str, message: str, kind: str = "info") -> None:
    try:
        Toast(root.winfo_toplevel(), title, message, kind)
    except tk.TclError:
        pass


class RateLimiter:
    """Wall-clock rate limit for UI notifications only (never an event time)."""

    def __init__(self, seconds: float):
        self.seconds, self._last = seconds, 0.0

    def ready(self) -> bool:
        now = time.monotonic()
        if now - self._last >= self.seconds:
            self._last = now
            return True
        return False


# ---------------------------------------------------------------- drawer
class Drawer(ctk.CTkFrame):
    """Right-hand detail panel overlaid on a screen; .open(title, rows) / .close()."""

    def __init__(self, parent, width: int = 380):
        super().__init__(parent, fg_color=T.SURFACE, border_color=T.BORDER, border_width=1, corner_radius=0,
                         width=width)
        self._drawer_width = width
        self.pack_propagate(False)   # keep the constructor width regardless of content
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=T.SPACE["l"], pady=(T.SPACE["l"], T.SPACE["s"]))
        self.title = label(head, "", "h2")
        self.title.pack(side="left")
        button(head, "Close", self.close, "ghost", width=60).pack(side="right")
        self.content = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.content.pack(fill="both", expand=True, padx=T.SPACE["s"], pady=(0, T.SPACE["l"]))

    def open(self, title: str, rows: Sequence[tuple[str, str]], header_widget: Optional[Callable] = None) -> None:
        self.title.configure(text=title)
        for w in self.content.winfo_children():
            w.destroy()
        if header_widget:
            header_widget(self.content).pack(anchor="w", padx=T.SPACE["s"], pady=(0, T.SPACE["m"]))
        for k, v in rows:
            label(self.content, k.upper(), "small_bold", T.MUTED).pack(anchor="w", padx=T.SPACE["s"], pady=(6, 0))
            lbl = label(self.content, v, "mono", T.TEXT, wraplength=self._drawer_width - 100)
            lbl.pack(anchor="w", fill="x", padx=T.SPACE["s"])
            autowrap(lbl, self.content, margin=24)
        self.place(relx=1.0, rely=0, relheight=1.0, anchor="ne")
        self.lift()

    def close(self) -> None:
        self.place_forget()
