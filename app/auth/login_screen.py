from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from app.auth import db
from app.auth.reset_dialog import ResetPasswordDialog
from app.common import theme
from app.common.widgets import show_toast


class LoginScreen(ttk.Frame):
    """Minimal, single-card login screen with a working forgot-password flow
    and a forced reset for accounts still on a temporary password."""

    def __init__(self, parent, on_success):
        super().__init__(parent, style="Root.TFrame")
        self.on_success = on_success
        self._show_password = False
        self.pack(fill="both", expand=True)
        self._build()


    def _build(self) -> None:
        bg = tk.Frame(self, bg=theme.BG_PRIMARY)
        bg.pack(fill="both", expand=True)

        card = tk.Frame(
            bg, bg=theme.BG_CARD, highlightbackground=theme.BORDER, highlightthickness=1
        )
        card.place(relx=0.5, rely=0.5, anchor="center")

        pad = tk.Frame(card, bg=theme.BG_CARD, padx=44, pady=40)
        pad.pack()

        tk.Label(
            pad,
            text=theme.APP_NAME,
            bg=theme.BG_CARD,
            fg=theme.TEXT_PRIMARY,
            font=theme.FONT_LOGO,
        ).pack(anchor="w")
        tk.Label(
            pad,
            text="IoT Threat Detection & Predictive Risk Analytics",
            bg=theme.BG_CARD,
            fg=theme.TEXT_MUTED,
            font=theme.FONT_LABEL,
        ).pack(anchor="w", pady=(2, 32))

        self.username_var = tk.StringVar()
        self.username_entry = self._field(pad, "Username", self.username_var)

        self.password_var = tk.StringVar()
        self.password_entry = self._field(
            pad, "Password", self.password_var, show="\u2022", toggleable=True
        )
        self.password_entry.bind("<Return>", lambda e: self._attempt_login())

        forgot = tk.Label(
            pad,
            text="Forgot password?",
            bg=theme.BG_CARD,
            fg=theme.TEXT_MUTED,
            font=(theme.FONT_LABEL[0], 9),
            cursor="hand2",
        )
        forgot.pack(anchor="e", pady=(0, 22))
        forgot.bind("<Button-1>", lambda e: self._open_forgot_password())
        forgot.bind("<Enter>", lambda e: forgot.config(fg=theme.ACCENT_CYAN))
        forgot.bind("<Leave>", lambda e: forgot.config(fg=theme.TEXT_MUTED))

        self.login_btn = tk.Button(
            pad,
            text="SIGN IN",
            command=self._attempt_login,
            bg=theme.ACCENT_CYAN,
            fg="#04141a",
            activebackground="#67e8f9",
            relief="flat",
            bd=0,
            font=(theme.FONT_LABEL[0], 10, "bold"),
            cursor="hand2",
            pady=9,
        )
        self.login_btn.pack(fill="x")

        self.error_label = tk.Label(
            pad, text="", bg=theme.BG_CARD, fg="#f87171", font=(theme.FONT_LABEL[0], 8)
        )
        self.error_label.pack(anchor="w", pady=(14, 0))

    def _field(
        self,
        parent,
        label: str,
        var: tk.StringVar,
        show: str = "",
        toggleable: bool = False,
    ) -> tk.Entry:
        tk.Label(
            parent,
            text=label.upper(),
            bg=theme.BG_CARD,
            fg=theme.TEXT_MUTED,
            font=(theme.FONT_LABEL[0], 8),
        ).pack(anchor="w", pady=(0, 4))

        row = tk.Frame(parent, bg=theme.BG_CARD)
        row.pack(fill="x")

        entry = tk.Entry(
            row,
            textvariable=var,
            show=show,
            bg=theme.BG_CARD,
            fg=theme.TEXT_PRIMARY,
            insertbackground=theme.TEXT_PRIMARY,
            relief="flat",
            bd=0,
            font=theme.FONT_LABEL,
            highlightthickness=0,
        )
        entry.pack(side="left", fill="x", expand=True, ipady=6)

        if toggleable:
            toggle = tk.Label(
                row,
                text="show",
                bg=theme.BG_CARD,
                fg=theme.TEXT_MUTED,
                font=(theme.FONT_LABEL[0], 8),
                cursor="hand2",
            )
            toggle.pack(side="right")

            def _toggle(_e=None):
                self._show_password = not self._show_password
                entry.config(show="" if self._show_password else "\u2022")
                toggle.config(text="hide" if self._show_password else "show")

            toggle.bind("<Button-1>", _toggle)

        underline = tk.Frame(parent, bg=theme.BORDER, height=2)
        underline.pack(fill="x", pady=(4, 18))
        entry.bind("<FocusIn>", lambda e: underline.config(bg=theme.ACCENT_CYAN))
        entry.bind("<FocusOut>", lambda e: underline.config(bg=theme.BORDER))
        return entry

    def _attempt_login(self) -> None:
        username = self.username_var.get().strip()
        password = self.password_var.get()
        if not username or not password:
            self._show_error("Enter both username and password.")
            return

        user_row = db.verify_login(username, password)
        if user_row is None:
            self._show_error("Invalid username or password.")
            self.password_var.set("")
            return

        self._show_error("")
        if user_row["must_reset_password"]:
            self._force_password_reset(username)
            return
        self.on_success(user_row)

    def _force_password_reset(self, username: str) -> None:
        def _done(_username: str) -> None:
            refreshed = db.get_user(username)
            self.on_success(refreshed)

        ResetPasswordDialog(
            self.winfo_toplevel(), on_complete=_done, username=username, forced=True
        )

    def _open_forgot_password(self) -> None:
        def _done(_username: str) -> None:
            show_toast(
                self.winfo_toplevel(),
                "Password updated",
                "Sign in with your new password.",
                "warning",
            )

        ResetPasswordDialog(self.winfo_toplevel(), on_complete=_done)

    def _show_error(self, message: str) -> None:
        self.error_label.config(text=message)
