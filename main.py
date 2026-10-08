"""
SentinelIoT -- IoT Threat Detection & Predictive Risk Analytics
Entry point. Run with: python main.py
"""
from __future__ import annotations

import tkinter as tk

import ttkbootstrap as tb
from ttkbootstrap.constants import *  # noqa: F401,F403 -- required by ttkbootstrap style API

from app.auth import db
from app.auth.login_screen import LoginScreen
from app.common import theme
from app.common.context import AppContext
from app.common.paths import resource_path
from app.common.widgets import show_toast
from app.live_monitor.engine import SimulationEngine
from app.shell import Shell
from models.inference import load_models


class SentinelApp:
    def __init__(self):
        db.init_db()

        self.root = tb.Window(themename=theme.TTKBOOTSTRAP_THEME)
        self.root.title(f"{theme.APP_NAME} -- IoT Threat Detection & Predictive Risk Analytics")
        self.root.geometry("1280x820")
        self.root.minsize(1040, 680)
        self.root.configure(bg=theme.BG_PRIMARY)

        theme.resolve_fonts()
        self._configure_styles()

        self.spotter, self.risk_analyst = load_models()

        self._current_frame: tk.Widget | None = None
        self._show_login()
        self.root.mainloop()

    def _configure_styles(self) -> None:
        style = tb.Style()
        style.configure("Root.TFrame", background=theme.BG_PRIMARY)
        style.configure("Card.TFrame", background=theme.BG_CARD)

    def _clear(self) -> None:
        if self._current_frame is not None:
            self._current_frame.destroy()
            self._current_frame = None

    def _show_login(self) -> None:
        self._clear()
        self._current_frame = LoginScreen(self.root, on_success=self._on_login_success)

    def _on_login_success(self, user_row) -> None:
        if user_row["must_reset_password"]:
            self._show_forced_reset(user_row)
        else:
            self._enter_shell(user_row)

    def _show_forced_reset(self, user_row) -> None:
        self._clear()
        frame = tk.Frame(self.root, bg=theme.BG_PRIMARY)
        frame.pack(fill="both", expand=True)
        self._current_frame = frame

        card = tk.Frame(frame, bg=theme.BG_CARD, highlightbackground=theme.BORDER, highlightthickness=1)
        card.place(relx=0.5, rely=0.5, anchor="center")
        inner = tk.Frame(card, bg=theme.BG_CARD, padx=36, pady=30)
        inner.pack()

        tk.Label(inner, text="Set a new password", bg=theme.BG_CARD, fg=theme.ACCENT_CYAN,
                 font=theme.FONT_HEADER).pack(anchor="w")
        tk.Label(inner, text=f"This is {user_row['username']}'s first login -- a password change is required.",
                 bg=theme.BG_CARD, fg=theme.TEXT_MUTED, font=theme.FONT_LABEL).pack(anchor="w", pady=(0, 16))

        pw_var = tk.StringVar()
        confirm_var = tk.StringVar()
        for label, var in (("New password", pw_var), ("Confirm password", confirm_var)):
            tk.Label(inner, text=label.upper(), bg=theme.BG_CARD, fg=theme.TEXT_MUTED,
                     font=(theme.FONT_LABEL[0], 8)).pack(anchor="w")
            tk.Entry(inner, textvariable=var, show="\u2022", bg=theme.BG_SECONDARY, fg=theme.TEXT_PRIMARY,
                     insertbackground=theme.TEXT_PRIMARY, relief="flat", width=30).pack(fill="x", ipady=6,
                                                                                         pady=(2, 12))

        def submit():
            if len(pw_var.get()) < 8:
                show_toast(self.root, "Password too short", "Use at least 8 characters.", "warning")
                return
            if pw_var.get() != confirm_var.get():
                show_toast(self.root, "Passwords don't match", "Re-enter the same password twice.", "warning")
                return
            db.set_password(user_row["username"], pw_var.get())
            show_toast(self.root, "Password updated", "You're all set.", "success")
            fresh = db.verify_login(user_row["username"], pw_var.get())
            self._enter_shell(fresh)

        tk.Button(inner, text="SET PASSWORD & CONTINUE", command=submit, bg=theme.ACCENT_CYAN, fg="#04141a",
                  relief="flat", font=(theme.FONT_LABEL[0], 10, "bold"), cursor="hand2", pady=8).pack(fill="x")

    def _enter_shell(self, user_row) -> None:
        self._clear()
        engine = SimulationEngine(
            feed_path=resource_path("data", "simulations_feed.csv"),
            spotter=self.spotter,
            risk_analyst=self.risk_analyst,
        )
        ctx = AppContext(user_row=user_row, spotter=self.spotter, risk_analyst=self.risk_analyst, engine=engine)
        ctx.on_logout = self._logout
        self._current_frame = Shell(self.root, ctx, on_logout=self._logout)
        self._active_ctx = ctx

    def _logout(self) -> None:
        ctx = getattr(self, "_active_ctx", None)
        if ctx is not None:
            ctx.engine.stop()
        self._show_login()


if __name__ == "__main__":
    SentinelApp()
