from __future__ import annotations

import customtkinter as ctk

from app.auth import db
from app.auth.reset_dialog import ResetPasswordDialog
from app.brand.logo import mark_image
from app.ui import theme, tokens as T
from app.ui.widgets import button, label, show_toast


class LoginScreen(ctk.CTkFrame):
    """Single-card sign-in with a working forgot-password flow and a forced
    reset for accounts still on a temporary password (same auth as before)."""

    def __init__(self, parent, on_success):
        super().__init__(parent, fg_color=T.BG, corner_radius=0)
        self.on_success = on_success
        self._show_password = False
        self.pack(fill="both", expand=True)
        self._build()

    def _build(self) -> None:
        corner = ctk.CTkFrame(self, fg_color="transparent")
        corner.place(relx=1.0, rely=0.0, anchor="ne", x=-20, y=16)
        self.theme_switch = ctk.CTkSwitch(corner, text="Dark mode", command=self._toggle_theme,
                                          font=theme.font("small"), text_color=T.MUTED,
                                          progress_color=T.ACCENT)
        self._sync_switch()
        unsub = theme.on_change(self._sync_switch)
        self.bind("<Destroy>", lambda e: unsub() if e.widget is self else None)
        self.theme_switch.pack()

        card = ctk.CTkFrame(self, fg_color=T.SURFACE, border_color=T.BORDER, border_width=1,
                            corner_radius=16, width=420)
        card.place(relx=0.5, rely=0.5, anchor="center")
        pad = ctk.CTkFrame(card, fg_color="transparent")
        pad.pack(padx=40, pady=36)

        brand = ctk.CTkFrame(pad, fg_color="transparent")
        brand.pack(anchor="w")
        logo = ctk.CTkImage(light_image=mark_image(0), dark_image=mark_image(1), size=(44, 44))
        ctk.CTkLabel(brand, image=logo, text="").pack(side="left")
        label(brand, T.APP_NAME, "display").pack(side="left", padx=(12, 0))
        label(pad, T.TAGLINE, "small", T.MUTED, wraplength=330).pack(anchor="w", pady=(8, 26))

        label(pad, "USERNAME", "small_bold", T.MUTED).pack(anchor="w")
        self.username_entry = ctk.CTkEntry(pad, width=330, height=38, font=theme.font("body"),
                                           fg_color=T.SURFACE_2, border_color=T.BORDER, text_color=T.TEXT)
        self.username_entry.pack(anchor="w", pady=(4, 14))

        label(pad, "PASSWORD", "small_bold", T.MUTED).pack(anchor="w")
        row = ctk.CTkFrame(pad, fg_color="transparent")
        row.pack(anchor="w", fill="x", pady=(4, 6))
        self.password_entry = ctk.CTkEntry(row, width=260, height=38, show="•", font=theme.font("body"),
                                           fg_color=T.SURFACE_2, border_color=T.BORDER, text_color=T.TEXT)
        self.password_entry.pack(side="left", fill="x", expand=True)
        self.toggle_btn = button(row, "Show", self._toggle_password, "ghost", width=62)
        self.toggle_btn.pack(side="left", padx=(8, 0))
        self.password_entry.bind("<Return>", lambda e: self._attempt_login())
        self.username_entry.bind("<Return>", lambda e: self.password_entry.focus_set())

        forgot = button(pad, "Forgot password?", self._open_forgot_password, "ghost", height=26)
        forgot.pack(anchor="e", pady=(0, 18))

        self.login_btn = button(pad, "Sign in", self._attempt_login, "primary", height=40)
        self.login_btn.pack(fill="x")
        self.error_label = label(pad, "", "small", T.DANGER, wraplength=330)
        self.error_label.pack(anchor="w", pady=(12, 0))
        self.after(50, self.username_entry.focus_set)

    # Kept as attributes for scripts that drive the login programmatically.
    @property
    def username_var(self):
        return _EntryVar(self.username_entry)

    @property
    def password_var(self):
        return _EntryVar(self.password_entry)

    def _toggle_theme(self) -> None:
        theme.set_mode("dark" if self.theme_switch.get() else "light")

    def _sync_switch(self) -> None:
        if self.theme_switch.winfo_exists():
            (self.theme_switch.select if theme.mode() == "dark" else self.theme_switch.deselect)()

    def _toggle_password(self) -> None:
        self._show_password = not self._show_password
        self.password_entry.configure(show="" if self._show_password else "•")
        self.toggle_btn.configure(text="Hide" if self._show_password else "Show")

    def _attempt_login(self) -> None:
        username = self.username_entry.get().strip()
        password = self.password_entry.get()
        if not username or not password:
            self._show_error("Enter both username and password.")
            return
        user_row = db.verify_login(username, password)
        if user_row is None:
            self._show_error("Invalid username or password.")
            self.password_entry.delete(0, "end")
            return
        self._show_error("")
        if user_row["must_reset_password"]:
            self._force_password_reset(username)
            return
        self.on_success(user_row)

    def _force_password_reset(self, username: str) -> None:
        def _done(_username: str) -> None:
            self.on_success(db.get_user(username))

        ResetPasswordDialog(self.winfo_toplevel(), on_complete=_done, username=username, forced=True)

    def _open_forgot_password(self) -> None:
        def _done(_username: str) -> None:
            show_toast(self, "Password updated", "Sign in with your new password.", "success")

        ResetPasswordDialog(self.winfo_toplevel(), on_complete=_done)

    def _show_error(self, message: str) -> None:
        self.error_label.configure(text=message)


class _EntryVar:
    """Minimal StringVar-like adapter over a CTkEntry (get/set)."""

    def __init__(self, entry):
        self.entry = entry

    def get(self) -> str:
        return self.entry.get()

    def set(self, value: str) -> None:
        self.entry.delete(0, "end")
        self.entry.insert(0, value)
