from __future__ import annotations

import tkinter as tk
from typing import Callable, Optional

from app.auth import db
from app.common import theme


class ResetPasswordDialog(tk.Toplevel):
    """
    Simple, local password reset -- no email, no reset codes, nothing sent
    anywhere. Two modes:

    - forced (username given, forced=True): shown right after a successful
      login when the account's must_reset_password flag is set (e.g. the
      seed admin account). Username is locked and the dialog can't be
      closed until a new password is saved.

    - self-service (forced=False, the default "Forgot password?" path):
      the user types their own username, then sets a new password
      directly.

    Security note: self-service mode does not verify the caller's identity
    beyond knowing a valid, active username -- there is no "old password"
    or code check. That's a deliberate simplification for a local,
    single-machine tool. If this app is ever exposed to more than one
    trusted operator, harden this (require the current password, or make
    resets admin-only) before relying on it.
    """

    def __init__(
        self,
        parent,
        on_complete: Callable[[str], None],
        username: Optional[str] = None,
        forced: bool = False,
    ):
        super().__init__(parent)
        self.on_complete = on_complete
        self.forced = forced
        self.username = username

        self.title("Set a new password" if forced else "Reset password")
        self.configure(bg=theme.BG_CARD)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        if forced:
            # Can't be dismissed with a temporary/default password still active.
            self.protocol("WM_DELETE_WINDOW", lambda: None)

        self._build()
        self.update_idletasks()
        self._center(parent)

    def _center(self, parent) -> None:
        self.update_idletasks()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 2}")

    def _build(self) -> None:
        pad = tk.Frame(self, bg=theme.BG_CARD, padx=32, pady=28)
        pad.pack()

        heading = "Set a new password" if self.forced else "Reset your password"
        tk.Label(
            pad,
            text=heading,
            bg=theme.BG_CARD,
            fg=theme.TEXT_PRIMARY,
            font=(theme.FONT_LABEL[0], 13, "bold"),
        ).pack(anchor="w")

        if self.forced:
            sub = "You're signed in with a temporary password. Choose a new one to continue."
        else:
            sub = "Enter your username and choose a new password. Nothing is emailed or texted."
        tk.Label(
            pad,
            text=sub,
            bg=theme.BG_CARD,
            fg=theme.TEXT_MUTED,
            wraplength=280,
            justify="left",
            font=(theme.FONT_LABEL[0], 9),
        ).pack(anchor="w", pady=(4, 20))

        self.username_var = tk.StringVar(value=self.username or "")
        if not self.forced:
            self._field(pad, "Username", self.username_var)

        self.pw_var = tk.StringVar()
        self.confirm_var = tk.StringVar()
        self._field(pad, "New password", self.pw_var, show="\u2022")
        self._field(pad, "Confirm password", self.confirm_var, show="\u2022")

        self.error_label = tk.Label(
            pad,
            text="",
            bg=theme.BG_CARD,
            fg="#f87171",
            font=(theme.FONT_LABEL[0], 8),
            wraplength=280,
            justify="left",
        )
        self.error_label.pack(anchor="w", pady=(0, 14))

        btn_row = tk.Frame(pad, bg=theme.BG_CARD)
        btn_row.pack(fill="x")
        if not self.forced:
            tk.Button(
                btn_row,
                text="Cancel",
                command=self.destroy,
                bg=theme.BG_SECONDARY,
                fg=theme.TEXT_MUTED,
                relief="flat",
                bd=0,
                font=(theme.FONT_LABEL[0], 9),
                cursor="hand2",
                pady=8,
            ).pack(side="left", fill="x", expand=True, padx=(0, 8))
        tk.Button(
            btn_row,
            text="SAVE",
            command=self._submit,
            bg=theme.ACCENT_CYAN,
            fg="#04141a",
            activebackground="#67e8f9",
            relief="flat",
            bd=0,
            font=(theme.FONT_LABEL[0], 9, "bold"),
            cursor="hand2",
            pady=8,
        ).pack(side="left", fill="x", expand=True)

    def _field(self, parent, label: str, var: tk.StringVar, show: str = "") -> tk.Entry:
        tk.Label(
            parent,
            text=label.upper(),
            bg=theme.BG_CARD,
            fg=theme.TEXT_MUTED,
            font=(theme.FONT_LABEL[0], 8),
        ).pack(anchor="w")
        entry = tk.Entry(
            parent,
            textvariable=var,
            show=show,
            bg=theme.BG_SECONDARY,
            fg=theme.TEXT_PRIMARY,
            insertbackground=theme.TEXT_PRIMARY,
            relief="flat",
            bd=0,
            font=theme.FONT_LABEL,
            width=28,
        )
        entry.pack(fill="x", ipady=7, pady=(3, 14))
        entry.bind("<Return>", lambda e: self._submit())
        return entry

    def _submit(self) -> None:
        username = (self.username or self.username_var.get()).strip()
        new_pw = self.pw_var.get()
        confirm = self.confirm_var.get()

        if not username:
            self._error("Enter your username.")
            return
        if len(new_pw) < 8:
            self._error("Password must be at least 8 characters.")
            return
        if new_pw != confirm:
            self._error("Passwords don't match.")
            return

        user_row = db.get_user(username)
        if user_row is None:
            self._error("No account with that username.")
            return
        if not user_row["active"]:
            self._error("This account is disabled. Contact an administrator.")
            return

        db.set_password(username, new_pw, clear_reset_flag=True)
        self.destroy()
        self.on_complete(username)

    def _error(self, message: str) -> None:
        self.error_label.config(text=message)
