from __future__ import annotations

from typing import Callable, Optional

import customtkinter as ctk

from app.auth import db
from app.ui import theme, tokens as T
from app.ui.widgets import button, label


class ResetPasswordDialog(ctk.CTkToplevel):
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

    def __init__(self, parent, on_complete: Callable[[str], None], username: Optional[str] = None,
                 forced: bool = False):
        super().__init__(parent)
        self.on_complete = on_complete
        self.forced = forced
        self.username = username
        self.title("Set a new password" if forced else "Reset password")
        self.configure(fg_color=T.SURFACE)
        self.resizable(False, False)
        self.transient(parent)
        if forced:
            # Can't be dismissed with a temporary/default password still active.
            self.protocol("WM_DELETE_WINDOW", lambda: None)
        self._build()
        self.after(10, lambda: self._center(parent))
        self.after(60, self._grab)

    def _grab(self) -> None:
        try:
            self.grab_set()
        except Exception:
            pass

    def _center(self, parent) -> None:
        self.update_idletasks()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 2}")

    def _build(self) -> None:
        pad = ctk.CTkFrame(self, fg_color="transparent")
        pad.pack(padx=32, pady=28)
        label(pad, "Set a new password" if self.forced else "Reset your password", "h2").pack(anchor="w")
        sub = ("You're signed in with a temporary password. Choose a new one to continue." if self.forced
               else "Enter your username and choose a new password. Nothing is emailed or texted.")
        label(pad, sub, "small", T.MUTED, wraplength=300).pack(anchor="w", pady=(4, 18))

        self.username_entry = None
        if not self.forced:
            self.username_entry = self._field(pad, "Username")
        self.pw_entry = self._field(pad, "New password", show="•")
        self.confirm_entry = self._field(pad, "Confirm password", show="•")

        self.error_label = label(pad, "", "small", T.DANGER, wraplength=300)
        self.error_label.pack(anchor="w", pady=(0, 12))
        row = ctk.CTkFrame(pad, fg_color="transparent")
        row.pack(fill="x")
        if not self.forced:
            button(row, "Cancel", self.destroy, "secondary").pack(side="left", fill="x", expand=True, padx=(0, 8))
        button(row, "Save", self._submit, "primary").pack(side="left", fill="x", expand=True)

    def _field(self, parent, caption: str, show: str = "") -> ctk.CTkEntry:
        label(parent, caption.upper(), "small_bold", T.MUTED).pack(anchor="w")
        entry = ctk.CTkEntry(parent, width=300, height=36, show=show, font=theme.font("body"),
                             fg_color=T.SURFACE_2, border_color=T.BORDER, text_color=T.TEXT)
        entry.pack(fill="x", pady=(3, 12))
        entry.bind("<Return>", lambda e: self._submit())
        return entry

    def _submit(self) -> None:
        username = (self.username or (self.username_entry.get() if self.username_entry else "")).strip()
        new_pw = self.pw_entry.get()
        confirm = self.confirm_entry.get()
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
        self.grab_release()
        self.destroy()
        self.on_complete(username)

    def _error(self, message: str) -> None:
        self.error_label.configure(text=message)
