"""
Vigil -- intelligent IoT network surveillance (RF-LSTM hybrid: anomaly
detection and predictive threat analytics on recorded ToN_IoT traffic).
Entry point. Run with: python main.py
"""
from __future__ import annotations

import customtkinter as ctk
from PIL import ImageTk

from app.auth import db
from app.auth.login_screen import LoginScreen
from app.brand.logo import icon_path, render_icon
from app.context import AppContext
from app.ui import theme, tokens as T
from services.hybrid_service import HybridService


class VigilApp:
    def __init__(self, run: bool = True):
        db.init_db()
        theme.init()
        self.root = ctk.CTk(fg_color=T.BG)
        self.root.title(f"{T.APP_NAME} — Intelligent IoT network surveillance")
        self.root.geometry(self.fit_geometry())
        self.root.minsize(1040, 640)
        self._set_icon()

        self.hybrid, self.hybrid_error = None, None
        try:
            self.hybrid = HybridService()
        except Exception as exc:  # missing/broken artifacts: still let the user sign in and see why
            self.hybrid_error = f"RF-LSTM hybrid failed to load: {type(exc).__name__}: {exc}"

        self._current = None
        self._ctx: AppContext | None = None
        self.show_login()
        if run:
            self.root.mainloop()

    def fit_geometry(self) -> str:
        """Up to 1400x880 logical px, never larger than ~92% of the screen at the current DPI scaling."""
        scale = ctk.ScalingTracker.get_window_scaling(self.root) or 1.0
        sw, sh = self.root.winfo_screenwidth() / scale, self.root.winfo_screenheight() / scale
        return f"{min(1400, int(sw * 0.94))}x{min(880, int(sh * 0.88))}"

    def _set_icon(self) -> None:
        ico = icon_path()
        try:
            if ico:
                self.root.iconbitmap(ico)
            self._icon_photo = ImageTk.PhotoImage(render_icon(64))
            self.root.iconphoto(True, self._icon_photo)
        except Exception:
            pass

    def _clear(self) -> None:
        if self._current is not None:
            self._current.destroy()
            self._current = None

    def show_login(self) -> None:
        self._clear()
        self._current = LoginScreen(self.root, on_success=self.enter_shell)

    def enter_shell(self, user_row) -> None:
        from app.shell import Shell

        self._clear()
        self._ctx = AppContext(user_row, self.hybrid, self.hybrid_error)
        self._ctx.on_logout = self.logout
        self._current = Shell(self.root, self._ctx, on_logout=self.logout)

    def logout(self) -> None:
        if self._ctx is not None and self._ctx.engine is not None:
            self._ctx.engine.stop()
        self.show_login()


if __name__ == "__main__":
    VigilApp()
