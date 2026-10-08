from __future__ import annotations

import time
import tkinter as tk
from tkinter import ttk

from app.auth import db
from app.common import theme
from app.common.context import AppContext
from app.common.widgets import LiveIndicator, RoleBadge, show_toast

NAV_ITEMS = [
    ("dashboard", "\u25a6  Dashboard"),
    ("live_monitor", "\u25b6  Live Monitor"),
    ("alerts", "\u26a0  Alerts"),
    ("analytics", "\u25a4  Analytics & Reports"),
    ("model_info", "\u2699  Model Info"),
    ("user_management", "\U0001f465  User Management"),
    ("settings", "\u2699  Settings"),
]


class Shell(ttk.Frame):
    def __init__(self, parent, ctx: AppContext, on_logout):
        super().__init__(parent, style="Root.TFrame")
        self.ctx = ctx
        self.on_logout = on_logout
        self.ctx.navigate = self.navigate
        self._frames: dict[str, tk.Widget] = {}
        self._current_key: str | None = None
        self._session_start = time.time()
        self.pack(fill="both", expand=True)
        self._last_toast_time = 0.0
        self._toast_cooldown_seconds = 1.5
        self._build()
        self._tick_session_timer()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        # Top bar
        topbar = tk.Frame(self, bg=theme.BG_SECONDARY, height=48)
        topbar.grid(row=0, column=0, columnspan=2, sticky="ew")
        topbar.grid_propagate(False)

        tk.Label(
            topbar,
            text=f"\u25c9 {theme.APP_NAME}",
            bg=theme.BG_SECONDARY,
            fg=theme.ACCENT_CYAN,
            font=theme.FONT_LOGO,
        ).pack(side="left", padx=16)

        right = tk.Frame(topbar, bg=theme.BG_SECONDARY)
        right.pack(side="right", padx=16)

        self.logout_btn = tk.Button(
            right,
            text="Log out",
            command=self.on_logout,
            bg=theme.BG_SECONDARY,
            fg=theme.TEXT_MUTED,
            activebackground=theme.BG_CARD,
            relief="flat",
            font=(theme.FONT_LABEL[0], 9),
            cursor="hand2",
        )
        self.logout_btn.pack(side="right", padx=(12, 0))

        self.session_label = tk.Label(
            right,
            text="Session 00:00",
            bg=theme.BG_SECONDARY,
            fg=theme.TEXT_MUTED,
            font=theme.FONT_MONO_SMALL,
        )
        self.session_label.pack(side="right", padx=12)

        status_frame = tk.Frame(right, bg=theme.BG_SECONDARY)
        status_frame.pack(side="right", padx=12)
        self.status_indicator = LiveIndicator(status_frame)
        self.status_indicator.set_color(theme.TEXT_MUTED)
        self.status_indicator.pack(side="left", padx=(0, 6))
        self.status_label = tk.Label(
            status_frame,
            text="Paused",
            bg=theme.BG_SECONDARY,
            fg=theme.TEXT_MUTED,
            font=(theme.FONT_LABEL[0], 9),
        )
        self.status_label.pack(side="left")

        RoleBadge(right, self.ctx.role).pack(side="right", padx=12)
        tk.Label(
            right,
            text=self.ctx.username,
            bg=theme.BG_SECONDARY,
            fg=theme.TEXT_PRIMARY,
            font=(theme.FONT_LABEL[0], 10, "bold"),
        ).pack(side="right")

        # Sidebar
        sidebar = tk.Frame(self, bg=theme.BG_SECONDARY, width=210)
        sidebar.grid(row=1, column=0, sticky="ns")
        sidebar.grid_propagate(False)

        self._nav_buttons: dict[str, tk.Label] = {}
        for key, label in NAV_ITEMS:
            if key == "user_management" and not self.ctx.is_admin():
                continue
            btn = tk.Label(
                sidebar,
                text=label,
                bg=theme.BG_SECONDARY,
                fg=theme.TEXT_MUTED,
                anchor="w",
                font=theme.FONT_LABEL,
                padx=18,
                pady=10,
                cursor="hand2",
            )
            btn.pack(fill="x")
            btn.bind("<Button-1>", lambda e, k=key: self.navigate(k))
            btn.bind("<Enter>", lambda e, b=btn, k=key: self._hover(b, k, True))
            btn.bind("<Leave>", lambda e, b=btn, k=key: self._hover(b, k, False))
            self._nav_buttons[key] = btn

        # Content area
        self.content = tk.Frame(self, bg=theme.BG_PRIMARY)
        self.content.grid(row=1, column=1, sticky="nsew")

        self.navigate("dashboard")
        self.after(80, self._poll_engine_queue)

    # ------------------------------------------------------------------
    # Central queue drain: runs continuously regardless of which screen is
    # visible, so counters/DB logging/toasts stay correct even if the user
    # is looking at, say, Analytics while the simulation keeps running.
    def _poll_engine_queue(self) -> None:
        engine = self.ctx.engine
        drained = 0
        while drained < 200:  # cap per tick so a burst can't stall the UI
            try:
                result = engine.result_queue.get_nowait()
            except Exception:
                break
            drained += 1
            self._handle_result(result)
        self.after(80, self._poll_engine_queue)

    def _handle_result(self, result) -> None:
        ctx = self.ctx
        c = ctx.counters
        c.total_flows += 1
        if result.is_attack:
            c.total_attacks += 1
            c.attack_type_counts[result.predicted_label] = (
                c.attack_type_counts.get(result.predicted_label, 0) + 1
            )
        c.severity_tier_counts[result.severity_tier] = (
            c.severity_tier_counts.get(result.severity_tier, 0) + 1
        )
        c.highest_severity_tier = max(c.highest_severity_tier, result.severity_tier)

        ctx.recent_events.append(result)
        if len(ctx.recent_events) > ctx.max_recent_events:
            ctx.recent_events.pop(0)

        is_flagged = result.severity_tier >= 3 or (
            result.is_attack
            and result.detection_confidence >= ctx.alert_confidence_threshold
        )
        if is_flagged:
            c.active_alerts += 1
            if ctx.session_id is not None:
                db.log_event(
                    ctx.session_id,
                    {
                        "sim_time": result.sim_time,
                        "device_name": result.device_name,
                        "device_ip": result.device_ip,
                        "protocol": result.protocol,
                        "predicted_label": result.predicted_label,
                        "detection_confidence": result.detection_confidence,
                        "severity_tier": result.severity_tier,
                        "severity_label": result.severity_label,
                        "severity_confidence": result.severity_confidence,
                        "feature_snapshot": result.feature_snapshot,
                    },
                )
            if result.severity_tier >= 3:
                now = time.time()
                if (now - self._last_toast_time) >= self._toast_cooldown_seconds:
                    self._last_toast_time = now
                    kind = "critical" if result.severity_tier == 4 else "warning"
                    show_toast(
                        self.winfo_toplevel(),
                        f"{theme.SEVERITY_LABELS[result.severity_tier]} severity",
                        f"{result.predicted_label} from {result.src_ip} ({result.detection_confidence:.0%} conf.)",
                        kind,
                    )

        for listener in list(ctx.result_listeners):
            try:
                listener(result)
            except Exception:
                pass

    def _hover(self, btn: tk.Label, key: str, entering: bool) -> None:
        if key == self._current_key:
            return
        btn.config(bg=theme.BG_CARD if entering else theme.BG_SECONDARY)

    def set_live_status(self, live: bool) -> None:
        if live:
            self.status_indicator.set_color(theme.ACCENT_GREEN)
            self.status_indicator.start()
            self.status_label.config(text="Live", fg=theme.ACCENT_GREEN)
        else:
            self.status_indicator.stop()
            self.status_indicator.set_color(theme.TEXT_MUTED)
            self.status_label.config(text="Paused", fg=theme.TEXT_MUTED)

    def _tick_session_timer(self) -> None:
        elapsed = int(time.time() - self._session_start)
        m, s = divmod(elapsed, 60)
        h, m = divmod(m, 60)
        self.session_label.config(text=f"Session {h:02d}:{m:02d}:{s:02d}")
        self.after(1000, self._tick_session_timer)

    # ------------------------------------------------------------------
    def navigate(self, key: str) -> None:
        for k, btn in self._nav_buttons.items():
            btn.config(
                bg=theme.BG_CARD if k == key else theme.BG_SECONDARY,
                fg=theme.ACCENT_CYAN if k == key else theme.TEXT_MUTED,
            )
        self._current_key = key

        if key not in self._frames:
            self._frames[key] = self._build_frame(key)
        for frame in self._frames.values():
            frame.pack_forget()
        frame = self._frames[key]
        frame.pack(fill="both", expand=True)
        if hasattr(frame, "on_show"):
            frame.on_show()

    def _build_frame(self, key: str) -> tk.Widget:
        if key == "dashboard":
            from app.dashboard.view import DashboardView

            return DashboardView(self.content, self.ctx)
        if key == "live_monitor":
            from app.live_monitor.view import LiveMonitorView

            return LiveMonitorView(self.content, self.ctx, shell=self)
        if key == "alerts":
            from app.alerts.view import AlertsView

            return AlertsView(self.content, self.ctx)
        if key == "analytics":
            from app.analytics.view import AnalyticsView

            return AnalyticsView(self.content, self.ctx)
        if key == "model_info":
            from app.model_info.view import ModelInfoView

            return ModelInfoView(self.content, self.ctx)
        if key == "user_management":
            from app.user_management.view import UserManagementView

            return UserManagementView(self.content, self.ctx)
        if key == "settings":
            from app.settings.view import SettingsView

            return SettingsView(self.content, self.ctx)
        raise ValueError(key)
