"""Matplotlib inside CustomTkinter, following the active theme.

ThemedChart owns a Figure and a draw function; it redraws on theme changes
and on resize, so charts always match light/dark mode (light mode uses a
white figure background suitable for printing)."""
from __future__ import annotations

from typing import Callable

import customtkinter as ctk
import matplotlib

matplotlib.use("Agg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from app.ui import theme, tokens as T  # noqa: E402


def colors() -> dict:
    p = theme.pick
    return dict(bg=p(T.SURFACE), text=p(T.TEXT), muted=p(T.MUTED), grid=p(T.CHART_GRID), border=p(T.BORDER),
                p_any=p(T.SERIES_P_ANY), p_esc=p(T.SERIES_P_ESC), truth=p(T.SERIES_TRUTH), accent=p(T.ACCENT),
                alert={k: p(v) for k, v in T.ALERT.items()})


def style_axes(ax, c: dict | None = None) -> None:
    c = c or colors()
    ax.set_facecolor(c["bg"])
    ax.tick_params(colors=c["muted"], labelsize=8)
    for side, spine in ax.spines.items():
        spine.set_color(c["border"])
        spine.set_visible(side in ("left", "bottom"))
    ax.grid(axis="y", color=c["grid"], linewidth=0.7)
    ax.set_axisbelow(True)
    ax.xaxis.label.set_color(c["muted"])
    ax.yaxis.label.set_color(c["muted"])


class ThemedChart(ctk.CTkFrame):
    """draw(fig, colors) is called on first show, theme change and resize."""

    def __init__(self, parent, draw: Callable[[Figure, dict], None], height: int = 320, **kw):
        kw.setdefault("fg_color", "transparent")
        super().__init__(parent, height=height, **kw)
        self._draw_fn = draw
        self._height = height
        self.fig = Figure(figsize=(8, height / 100), dpi=100)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.widget = self.canvas.get_tk_widget()
        self.widget.configure(highlightthickness=0, borderwidth=0)
        self.widget.pack(fill="both", expand=True)
        self._unsub = theme.on_change(self.redraw)
        self._pending = None
        # add="+": keep matplotlib's own resize handler (it also applies the HiDPI device pixel ratio)
        self.widget.bind("<Configure>", self._on_resize, add="+")
        self.bind("<Destroy>", lambda e: self._unsub() if e.widget is self else None)
        self.redraw()

    def set_draw(self, draw: Callable[[Figure, dict], None]) -> None:
        self._draw_fn = draw
        self.redraw()

    def _on_resize(self, event) -> None:
        if self._pending:
            self.after_cancel(self._pending)
        self._pending = self.after(120, self.redraw)

    def redraw(self) -> None:
        self._pending = None
        if not self.winfo_exists():
            return
        c = colors()
        # Size and DPI are managed by matplotlib's Tk backend (resize events + device pixel ratio).
        self.fig.clear()
        self.fig.set_facecolor(c["bg"])
        try:
            self._draw_fn(self.fig, c)
        except Exception as exc:  # show the error in the chart instead of a blank box
            self.fig.clear()
            self.fig.text(0.02, 0.5, f"Chart error: {type(exc).__name__}: {exc}", color=c["alert"]["CRITICAL"],
                          fontsize=9)
        self.canvas.draw_idle()
