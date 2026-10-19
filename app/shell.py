"""Vigil app shell: sidebar navigation, theme switch, and the replay pipeline
(queue drain -> per-host history -> de-duplicated alerts -> listeners)."""
from __future__ import annotations

import importlib

import customtkinter as ctk

from app.auth import db
from app.brand.logo import mark_image
from app.context import AppContext
from app.ui import theme, tokens as T
from app.ui.widgets import Badge, RateLimiter, button, label, show_toast

NAV = [
    ("overview", "Overview", "◫"),
    ("live_replay", "Live Replay", "▶"),
    ("alerts", "Alerts", "⚠"),
    ("risk_timeline", "Risk Timeline", "↗"),
    ("evaluation", "Model Evaluation", "≡"),
    ("about", "About the model", "ⓘ"),
    ("settings", "Settings", "⚙"),
    ("users", "Users", "☺"),          # administrators only
]
SCREENS = {
    "overview": ("app.screens.overview", "OverviewScreen"),
    "live_replay": ("app.screens.live_replay", "LiveReplayScreen"),
    "alerts": ("app.screens.alerts", "AlertsScreen"),
    "risk_timeline": ("app.screens.risk_timeline", "RiskTimelineScreen"),
    "evaluation": ("app.screens.evaluation", "EvaluationScreen"),
    "about": ("app.screens.about", "AboutScreen"),
    "settings": ("app.screens.settings", "SettingsScreen"),
    "users": ("app.screens.users", "UsersScreen"),
}


class Shell(ctk.CTkFrame):
    def __init__(self, parent, ctx: AppContext, on_logout):
        super().__init__(parent, fg_color=T.BG, corner_radius=0)
        self.ctx = ctx
        self.on_logout = on_logout
        ctx.navigate = self.navigate
        ctx.toast = lambda title, msg, kind="info": show_toast(self, title, msg, kind)
        self._frames: dict[str, ctk.CTkFrame] = {}
        self._buttons: dict[str, ctk.CTkButton] = {}
        self._current: str | None = None
        self._toast_limit = RateLimiter(1.5)
        self.pack(fill="both", expand=True)
        self._build()
        self.navigate("overview")
        self.after(80, self._poll)
        self.after(500, self._refresh_status)

    # ------------------------------------------------------------------
    def _build(self) -> None:
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        side = ctk.CTkFrame(self, fg_color=T.SIDEBAR, corner_radius=0, width=T.SIDEBAR_WIDTH)
        side.grid(row=0, column=0, sticky="ns")
        side.grid_propagate(False)
        side.pack_propagate(False)

        brand = ctk.CTkFrame(side, fg_color="transparent")
        brand.pack(fill="x", padx=18, pady=(20, 22))
        logo = ctk.CTkImage(light_image=mark_image(0), dark_image=mark_image(1), size=(30, 30))
        ctk.CTkLabel(brand, image=logo, text="").pack(side="left")
        label(brand, T.APP_NAME, "h1").pack(side="left", padx=(10, 0))

        for key, text, icon in NAV:
            if key == "users" and not self.ctx.is_admin():
                continue
            b = ctk.CTkButton(side, text=f"  {icon}   {text}", anchor="w", height=38, corner_radius=8,
                              font=theme.font("body"), fg_color="transparent", hover_color=T.SURFACE_2,
                              text_color=T.MUTED, command=lambda k=key: self.navigate(k))
            b.pack(fill="x", padx=10, pady=1)
            self._buttons[key] = b

        bottom = ctk.CTkFrame(side, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=14, pady=16)
        self.model_status = label(bottom, "", "small_bold", T.MUTED, wraplength=190)
        self.model_status.pack(anchor="w")
        self.replay_status = label(bottom, "", "small", T.MUTED, wraplength=190)
        self.replay_status.pack(anchor="w", pady=(2, 12))
        self.theme_switch = ctk.CTkSwitch(bottom, text="Dark mode", command=self._toggle_theme,
                                          font=theme.font("small"), text_color=T.MUTED, progress_color=T.ACCENT)
        self._sync_switch()
        unsub = theme.on_change(self._sync_switch)
        self.bind("<Destroy>", lambda e: unsub() if e.widget is self else None)
        self.theme_switch.pack(anchor="w", pady=(0, 12))
        who = ctk.CTkFrame(bottom, fg_color="transparent")
        who.pack(fill="x")
        label(who, self.ctx.username, "body_bold").pack(side="left")
        label(who, self.ctx.role, "small", T.MUTED).pack(side="left", padx=(8, 0))
        button(bottom, "Log out", self.on_logout, "secondary", height=30).pack(fill="x", pady=(10, 0))

        self.content = ctk.CTkFrame(self, fg_color=T.BG, corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew")
        self._set_model_status()

    def _set_model_status(self) -> None:
        h = self.ctx.hybrid
        if h is None:
            self.model_status.configure(text="✖ Model not loaded", text_color=T.DANGER)
        elif h.lstm_available:
            self.model_status.configure(text="● RF–LSTM hybrid loaded", text_color=T.ALERT["NORMAL"])
        else:
            self.model_status.configure(text="⚠ RF-only fallback (LSTM unavailable)", text_color=T.ALERT["HIGH"])

    def _refresh_status(self) -> None:
        if not self.winfo_exists():
            return
        e = self.ctx.engine
        if e is None:
            text = ""
        elif e.error:
            text = f"Replay error: {e.error}"
        elif e.is_running():
            text = ("Replay paused" if e.is_paused() else f"Replaying ×{e.speed:g}") + \
                   (f" · {self.ctx.last_step.window_start_utc}" if self.ctx.last_step else "")
        elif e.finished:
            text = "Replay complete"
        else:
            text = "Replay idle"
        self.replay_status.configure(text=text)
        self.after(500, self._refresh_status)

    def _toggle_theme(self) -> None:
        theme.set_mode("dark" if self.theme_switch.get() else "light")

    def _sync_switch(self) -> None:
        if self.theme_switch.winfo_exists():
            (self.theme_switch.select if theme.mode() == "dark" else self.theme_switch.deselect)()

    # ------------------------------------------------------------------
    def navigate(self, key: str) -> None:
        if key not in SCREENS or (key == "users" and not self.ctx.is_admin()):
            return
        for k, b in self._buttons.items():
            active = k == key
            b.configure(fg_color=T.SURFACE_2 if active else "transparent",
                        text_color=T.ACCENT if active else T.MUTED,
                        font=theme.font("body_bold" if active else "body"))
        if key not in self._frames:
            module, cls = SCREENS[key]
            self._frames[key] = getattr(importlib.import_module(module), cls)(self.content, self.ctx)
        for k, f in self._frames.items():
            if k != key:
                f.pack_forget()
        frame = self._frames[key]
        frame.pack(fill="both", expand=True)
        self._current = key
        frame.on_show()

    # ------------------------------------------------------------------
    # Replay pipeline. Every time used here is step.window_start (recorded).
    def _poll(self) -> None:
        if not self.winfo_exists():
            return
        e = self.ctx.engine
        if e is not None:
            for _ in range(20):
                try:
                    step = e.result_queue.get_nowait()
                except Exception:
                    break
                self._handle_step(step)
        self.after(80, self._poll)

    def _handle_step(self, step) -> None:
        ctx = self.ctx
        ctx.record_step(step)
        new_alerts = ctx.tracker.update(step)       # partial-lookback windows never alert
        for a in new_alerts:
            if ctx.run_id is not None:
                db.log_hybrid_alert(ctx.run_id, a.__dict__)
        if new_alerts:
            worst = min(new_alerts, key=lambda a: T.ALERT_ORDER.index(a.level))
            if worst.level in ("CRITICAL", "HIGH") and self._toast_limit.ready():
                more = f" (+{len(new_alerts) - 1} more)" if len(new_alerts) > 1 else ""
                show_toast(self, f"{worst.level} · {worst.kind}",
                           f"{worst.host} at {worst.window_start_utc} (recorded){more}\n{worst.reason}",
                           "critical" if worst.level == "CRITICAL" else "warning")
        for cb in list(ctx.step_listeners):
            try:
                cb(step, new_alerts)
            except Exception:
                pass

    def start_run(self) -> None:
        self.ctx.start_run()
