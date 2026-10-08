"""Shared custom widgets used across screens: toasts, cards, animated counters.

No stock `messagebox` popups are used anywhere in the user-facing app --
this module is why.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from app.common import theme


class Toast(tk.Toplevel):
    """
    A custom animated toast notification anchored to the bottom-right of a
    parent window. Replaces messagebox popups entirely. Stacks multiple
    toasts vertically if several fire in quick succession.
    """

    _active: list["Toast"] = []

    def __init__(self, parent: tk.Misc, title: str, message: str, kind: str = "info", duration_ms: int = 4200):
        super().__init__(parent)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.parent = parent

        colors = {
            "info": theme.ACCENT_CYAN,
            "success": theme.ACCENT_GREEN,
            "warning": theme.ACCENT_AMBER,
            "critical": theme.ACCENT_RED,
        }
        accent = colors.get(kind, theme.ACCENT_CYAN)

        frame = tk.Frame(self, bg=theme.BG_CARD, highlightbackground=accent, highlightthickness=2)
        frame.pack(fill="both", expand=True)
        stripe = tk.Frame(frame, bg=accent, width=4)
        stripe.pack(side="left", fill="y")
        body = tk.Frame(frame, bg=theme.BG_CARD)
        body.pack(side="left", fill="both", expand=True, padx=(10, 14), pady=8)
        tk.Label(body, text=title, bg=theme.BG_CARD, fg=accent, font=theme.FONT_HEADER, anchor="w").pack(fill="x")
        tk.Label(
            body, text=message, bg=theme.BG_CARD, fg=theme.TEXT_PRIMARY, font=theme.FONT_LABEL,
            anchor="w", justify="left", wraplength=280,
        ).pack(fill="x", pady=(2, 0))

        self.update_idletasks()
        self._position()
        self.attributes("-alpha", 0.0)
        Toast._active.append(self)
        self._fade_in()
        self.after(duration_ms, self._fade_out)

    def _position(self) -> None:
        px, py = self.parent.winfo_rootx(), self.parent.winfo_rooty()
        pw, ph = self.parent.winfo_width(), self.parent.winfo_height()
        w, h = 320, self.winfo_reqheight() or 70
        stack_offset = sum(t.winfo_reqheight() + 10 for t in Toast._active if t is not self and t.winfo_exists())
        x = px + pw - w - 24
        y = py + ph - h - 24 - stack_offset
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _fade_in(self, alpha: float = 0.0) -> None:
        if alpha < 0.95 and self.winfo_exists():
            alpha += 0.12
            self.attributes("-alpha", min(alpha, 0.95))
            self.after(15, lambda: self._fade_in(alpha))

    def _fade_out(self, alpha: float = 0.95) -> None:
        if not self.winfo_exists():
            return
        if alpha > 0:
            alpha -= 0.10
            self.attributes("-alpha", max(alpha, 0.0))
            self.after(15, lambda: self._fade_out(alpha))
        else:
            if self in Toast._active:
                Toast._active.remove(self)
            self.destroy()


def show_toast(parent: tk.Misc, title: str, message: str, kind: str = "info") -> None:
    Toast(parent, title, message, kind)


class StatCard(ttk.Frame):
    """A dashboard summary card with a big animated count-up number."""

    def __init__(self, parent, label: str, initial: int = 0, suffix: str = "", accent: str = theme.ACCENT_CYAN):
        super().__init__(parent, style="Card.TFrame", padding=16)
        self.suffix = suffix
        self._value = initial
        self._display_value = initial

        tk.Label(self, text=label.upper(), bg=theme.BG_CARD, fg=theme.TEXT_MUTED,
                 font=(theme.FONT_LABEL[0], 9)).pack(anchor="w")
        self.value_label = tk.Label(
            self, text=f"{initial}{suffix}", bg=theme.BG_CARD, fg=accent,
            font=(theme.FONT_LOGO[0], 26, "bold"),
        )
        self.value_label.pack(anchor="w", pady=(4, 0))

    def set_value(self, new_value: int, animate: bool = True) -> None:
        self._value = new_value
        if not animate:
            self._display_value = new_value
            self.value_label.config(text=f"{new_value}{self.suffix}")
            return
        self._animate_step()

    def _animate_step(self) -> None:
        if self._display_value == self._value:
            return
        diff = self._value - self._display_value
        step = max(1, abs(diff) // 6) * (1 if diff > 0 else -1)
        self._display_value += step
        if (step > 0 and self._display_value > self._value) or (step < 0 and self._display_value < self._value):
            self._display_value = self._value
        self.value_label.config(text=f"{self._display_value}{self.suffix}")
        if self._display_value != self._value:
            self.after(30, self._animate_step)


class LiveIndicator(tk.Canvas):
    """A small pulsing dot indicating the system is live, per the spec's
    'subtle motion/feedback' requirement."""

    def __init__(self, parent, size: int = 12):
        super().__init__(parent, width=size, height=size, bg=theme.BG_SECONDARY, highlightthickness=0)
        self.size = size
        self._radius = size / 2 - 1
        self._growing = True
        self._pulse = 0.0
        self._running = False
        self._color = theme.ACCENT_GREEN
        self._dot = self.create_oval(1, 1, size - 1, size - 1, fill=self._color, outline="")

    def set_color(self, color: str) -> None:
        self._color = color
        self.itemconfig(self._dot, fill=color)

    def start(self) -> None:
        if not self._running:
            self._running = True
            self._animate()

    def stop(self) -> None:
        self._running = False

    def _animate(self) -> None:
        if not self._running or not self.winfo_exists():
            return
        self._pulse += 0.08 if self._growing else -0.08
        if self._pulse >= 1.0:
            self._growing = False
        elif self._pulse <= 0.0:
            self._growing = True
        scale = 0.7 + 0.3 * self._pulse
        r = self._radius * scale
        cx = cy = self.size / 2
        self.coords(self._dot, cx - r, cy - r, cx + r, cy + r)
        self.after(60, self._animate)


class RoleBadge(tk.Label):
    def __init__(self, parent, role: str):
        color = theme.ACCENT_AMBER if role == "administrator" else theme.ACCENT_CYAN
        super().__init__(
            parent, text=role.upper(), bg=color, fg="#0b0f14",
            font=(theme.FONT_LABEL[0], 8, "bold"), padx=8, pady=2,
        )
