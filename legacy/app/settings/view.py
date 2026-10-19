from __future__ import annotations

import tkinter as tk

from app.common import theme
from app.common.context import AppContext
from app.common.widgets import show_toast


class SettingsView(tk.Frame):
    def __init__(self, parent, ctx: AppContext):
        super().__init__(parent, bg=theme.BG_PRIMARY)
        self.ctx = ctx
        self._build()

    def _build(self) -> None:
        pad = tk.Frame(self, bg=theme.BG_PRIMARY, padx=24, pady=18)
        pad.pack(fill="both", expand=True)

        tk.Label(pad, text="Settings", bg=theme.BG_PRIMARY, fg=theme.TEXT_PRIMARY,
                 font=(theme.FONT_HEADER[0], 18, "bold")).pack(anchor="w", pady=(0, 14))

        card = tk.Frame(pad, bg=theme.BG_CARD, highlightbackground=theme.BORDER, highlightthickness=1)
        card.pack(fill="x")
        inner = tk.Frame(card, bg=theme.BG_CARD, padx=20, pady=18)
        inner.pack(fill="x")

        self.sound_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            inner, text="Alert sound on new critical alert", variable=self.sound_var, bg=theme.BG_CARD,
            fg=theme.TEXT_PRIMARY, selectcolor=theme.BG_SECONDARY, activebackground=theme.BG_CARD,
            font=theme.FONT_LABEL, bd=0, highlightthickness=0,
        ).pack(anchor="w", pady=6)

        tk.Label(inner, text="Alert confidence threshold", bg=theme.BG_CARD, fg=theme.TEXT_MUTED,
                 font=theme.FONT_LABEL).pack(anchor="w", pady=(14, 2))
        self.threshold_var = tk.DoubleVar(value=self.ctx.alert_confidence_threshold)
        tk.Scale(
            inner, from_=0.1, to=0.99, resolution=0.01, orient="horizontal", variable=self.threshold_var,
            bg=theme.BG_CARD, fg=theme.TEXT_PRIMARY, highlightthickness=0, troughcolor=theme.BG_SECONDARY,
            length=280, command=self._on_threshold_change,
        ).pack(anchor="w")

        tk.Label(inner, text="Default simulation speed (x)", bg=theme.BG_CARD, fg=theme.TEXT_MUTED,
                 font=theme.FONT_LABEL).pack(anchor="w", pady=(14, 2))
        self.speed_var = tk.DoubleVar(value=5.0)
        tk.Scale(
            inner, from_=1, to=20, orient="horizontal", variable=self.speed_var,
            bg=theme.BG_CARD, fg=theme.TEXT_PRIMARY, highlightthickness=0, troughcolor=theme.BG_SECONDARY,
            length=280,
        ).pack(anchor="w")

        tk.Label(inner, text="Data source", bg=theme.BG_CARD, fg=theme.TEXT_MUTED,
                 font=theme.FONT_LABEL).pack(anchor="w", pady=(14, 2))
        self.source_var = tk.StringVar(value="data/simulations_feed.csv (bundled)")
        tk.Label(inner, textvariable=self.source_var, bg=theme.BG_SECONDARY, fg=theme.TEXT_PRIMARY,
                 font=theme.FONT_MONO_SMALL, padx=8, pady=6, anchor="w").pack(anchor="w", fill="x")

        tk.Button(
            inner, text="Save Settings", command=self._save, bg=theme.BG_SECONDARY, fg=theme.ACCENT_GREEN,
            relief="flat", font=(theme.FONT_LABEL[0], 9, "bold"), cursor="hand2", padx=14,
        ).pack(anchor="w", pady=(20, 0))

    def _on_threshold_change(self, value) -> None:
        self.ctx.alert_confidence_threshold = float(value)

    def _save(self) -> None:
        self.ctx.alert_confidence_threshold = self.threshold_var.get()
        self.ctx.engine.set_speed(self.speed_var.get())
        show_toast(self.winfo_toplevel(), "Settings saved", "Preferences applied for this session.", "success")
