"""
Live Replay -- the RF-LSTM hybrid over recorded ToN_IoT traffic.

Every time shown is the recorded window start from replay_flows.csv (via
services.hybrid_service). Hosts are the recorded IPs. Windows whose lookback
is not fully inside the file are greyed out and never alert.
"""
from __future__ import annotations

import customtkinter as ctk

from app.screens.base import Screen
from app.ui import theme, tokens as T
from app.ui.widgets import Badge, Card, ProbBar, autowrap, button, label, note_box, spacer
from services import prefs
from services.hybrid_service import TIER_NAMES, alert_kind

SPEEDS = ["1", "10", "30", "60", "120", "300", "600"]


def tier_name(t) -> str:
    t = int(t)
    return TIER_NAMES[t] if 0 <= t < len(TIER_NAMES) else f"Tier {t}"


def pretty_utc(s: str) -> str:
    return s.replace("T", " ").replace("Z", " UTC")


def verdict_mix(counts: dict) -> str:
    if not counts:
        return "no flows in this window"
    return " · ".join(f"{t} {n:,}" for t, n in sorted(counts.items(), key=lambda kv: -kv[1]))


class HostCard(Card):
    def __init__(self, parent, host: str, horizon_minutes: float):
        super().__init__(parent, padding=T.SPACE["l"])
        b = self.body
        top = ctk.CTkFrame(b, fg_color="transparent")
        top.pack(fill="x")
        self.ip = label(top, host, "mono_bold", T.TEXT)
        self.ip.pack(side="left")
        self.badge_holder = ctk.CTkFrame(top, fg_color="transparent")
        self.badge_holder.pack(side="right")
        self._badge_key = None

        self.det = label(b, "", "body", T.TEXT)
        self.det.pack(anchor="w", pady=(8, 0))
        self.fut = label(b, "", "body", T.TEXT)
        self.fut.pack(anchor="w", pady=(0, 8))
        hm = self.hm = f"{horizon_minutes:g}"
        bars = ctk.CTkFrame(b, fg_color="transparent")
        bars.pack(fill="x")
        bars.columnconfigure((0, 1), weight=1, uniform="bars")
        self.p_any = ProbBar(bars, f"P(attack ≤{hm} min)", T.SERIES_P_ANY)
        self.p_any.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.p_esc = ProbBar(bars, f"P(escalation ≤{hm} min)", T.SERIES_P_ESC)
        self.p_esc.grid(row=0, column=1, sticky="ew", padx=(10, 0))
        self.mix = autowrap(label(b, "", "small", T.MUTED), b, margin=8)
        self.mix.pack(anchor="w", fill="x", pady=(10, 0))
        self.reason = autowrap(label(b, "", "small", T.MUTED), b, margin=8)
        self.reason.pack(anchor="w", fill="x")

    def _set_badge(self, level: str, kind: str) -> None:
        key = (level, kind)
        if key == self._badge_key:
            return
        for w in self.badge_holder.winfo_children():
            w.destroy()
        Badge(self.badge_holder, level, kind).pack()
        self._badge_key = key

    def update_row(self, r: dict, counts: dict, lstm: bool, complete: bool) -> None:
        greyed = not complete
        fg = T.FAINT if greyed else T.TEXT
        self.configure(border_color=T.BORDER if not greyed else T.SURFACE_2)
        self.ip.configure(text_color=fg)
        self.mix.configure(text=f"{r['n_flows']:,} flows · RF per-flow verdicts: {verdict_mix(counts)}")
        if not lstm:
            self._set_badge("RF only", "")
            self.det.configure(text=f"RF max per-flow tier this window: {tier_name(r['rf_tier'])}",
                               text_color=fg)
            self.fut.configure(text="Forecast: needs the LSTM layer", text_color=T.MUTED)
            self.p_any.set(None)
            self.p_esc.set(None)
            self.reason.configure(text="Detection/forecast heads need the LSTM layer.")
            return
        det, fut = tier_name(r["det_tier"]), tier_name(r["fut_tier"])
        self.det.configure(text=f"Detected now:  {det}", text_color=fg)
        self.fut.configure(text=f"Forecast, next {self.hm} min:  {fut}", text_color=fg)
        self.p_any.set(float(r["p_attack_next"]), fg)
        self.p_esc.set(float(r["p_severe_next"]), fg)
        if greyed:
            self._set_badge("NOT ALERTED", "")
            self.reason.configure(text="Partial lookback: shown for reference only; no alert is raised.")
        else:
            reason = r.get("alert_reason") or ""
            self._set_badge(r["alert"], alert_kind(reason))
            self.reason.configure(text=reason or "No alert condition met.")


class LiveReplayScreen(Screen):
    title = "Live Replay"
    subtitle = "RF–LSTM hybrid over recorded ToN_IoT traffic, window by window, in recorded order."

    def build(self) -> None:
        self.svc = self.ctx.hybrid
        self.engine = self.ctx.engine
        self.cards: dict[str, HostCard] = {}
        self.header()
        if self.svc is None:
            self.unavailable(self.ctx.hybrid_error or "The RF–LSTM hybrid is not loaded.")
            return
        pad = dict(padx=T.SPACE["xxl"])
        P = self.page

        if not self.svc.lstm_available:
            note_box(P, f"LSTM layer unavailable — {self.svc.lstm_error} Detection and forecast tiers, "
                           "forecast probabilities and alerts need the LSTM layer.", T.DANGER).pack(
                fill="x", pady=(0, T.SPACE["m"]), **pad)
        for w in self.svc.load_warnings:
            note_box(P, f"Model load warning: {w}", T.ALERT["HIGH"]).pack(fill="x", pady=(0, T.SPACE["m"]), **pad)

        # --- clock + controls
        top = Card(P)
        top.pack(fill="x", **pad)
        tb = top.body
        tb.columnconfigure(0, weight=1)
        self.mode_label = label(tb, self.engine.mode_label, "body_bold", T.ACCENT)
        self.mode_label.grid(row=0, column=0, sticky="w")
        label(tb, "RECORDED WINDOW START (UTC, from replay_flows.csv ts)", "small_bold", T.MUTED).grid(
            row=1, column=0, sticky="w", pady=(10, 0))
        self.clock = label(tb, "—", "clock", T.TEXT)
        self.clock.grid(row=2, column=0, sticky="w")
        self.meta = autowrap(label(tb, self._config_text(), "small", T.MUTED), tb, margin=8)
        self.meta.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self.progress = ctk.CTkProgressBar(tb, height=6, progress_color=T.ACCENT, fg_color=T.SURFACE_2)
        self.progress.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self.progress.set(0)

        ctl = ctk.CTkFrame(tb, fg_color="transparent")
        ctl.grid(row=0, column=1, rowspan=4, sticky="ne")
        row = ctk.CTkFrame(ctl, fg_color="transparent")
        row.pack(anchor="e")
        button(row, "▶  Play", self._play, "primary", width=96).pack(side="left")
        button(row, "⏸  Pause", self._pause, "secondary", width=96).pack(side="left", padx=8)
        button(row, "⏹  Stop", self._stop, "secondary", width=90).pack(side="left")
        srow = ctk.CTkFrame(ctl, fg_color="transparent")
        srow.pack(anchor="e", pady=(12, 0))
        label(srow, "Requested speed  ×", "small", T.MUTED).pack(side="left", padx=(0, 6))
        default = str(prefs.get("replay_speed") or 60)
        self.speed = ctk.CTkSegmentedButton(srow, values=SPEEDS, command=self._on_speed, font=theme.font("small"),
                                            selected_color=T.ACCENT, selected_hover_color=T.ACCENT_HOVER,
                                            unselected_color=T.SURFACE_2, unselected_hover_color=T.BORDER,
                                            text_color=T.TEXT, fg_color=T.SURFACE_2)
        self.speed.pack(side="left")
        if self.engine.is_running() or self.ctx.last_step is not None:
            cur = f"{self.engine.speed:g}"      # a run exists: show its speed, keep its measured actual speed
            self.speed.set(cur if cur in SPEEDS else default)
        else:
            self.speed.set(default if default in SPEEDS else "60")
            self.engine.set_speed(float(self.speed.get()))
        self.state = label(ctl, "Stopped", "small_bold", T.MUTED)
        self.state.pack(anchor="e", pady=(10, 0))

        self.partial = spacer(P)        # packed only while a partial-lookback note is shown

        # --- host cards
        self.levels = spacer(P)
        self._pad = pad
        self.levels.pack(fill="x", pady=(T.SPACE["m"], T.SPACE["s"]), **pad)
        self.grid_area = ctk.CTkFrame(P, fg_color="transparent")
        self.grid_area.pack(fill="x", padx=T.SPACE["xxl"] - 8, pady=(0, T.SPACE["s"]))
        self.grid_area.columnconfigure((0, 1), weight=1, uniform="hosts")
        self.empty = label(self.grid_area, "Press Play to replay the recorded traffic.", "body", T.MUTED)
        self.empty.grid(row=0, column=0, columnspan=2, sticky="w", padx=8, pady=8)
        foot = label(P, (f"Alert thresholds from preprocessing.json: WARNING if P(any attack) ≥ "
                     f"{self.svc.threshold_attack:.4f}; HIGH if P(escalation) ≥ {self.svc.threshold_severe:.4f}; "
                     "detection-based levels from the detected tier. Escalation = compromise or DoS-level tier (≥ 2). "
                     "Levels and reasons come from sentinel_inference.alert_level(). Filled badge = Detected now; "
                     "outlined = Predicted ahead."), "small", T.MUTED)
        foot.pack(anchor="w", fill="x", pady=(0, T.SPACE["l"]), **pad)
        autowrap(foot, P, margin=2 * T.SPACE["xxl"] + 16)

        self.ctx.step_listeners.append(self._on_step)
        self._watch()

    def _config_text(self) -> str:
        s = self.svc
        first, last = s.replay_windows()
        return (f"window {s.window_sec:g} s · lookback {s.lookback} windows · horizon {s.horizon} windows "
                f"({s.horizon_minutes:g} min) · file covers {pretty_utc(s.to_utc(s.window_start(first)))} → "
                f"{pretty_utc(s.to_utc(s.window_start(last)))} ({last - first + 1} windows)")

    # ------------------------------------------------------------------ controls
    def on_show(self) -> None:
        if self.svc is not None and self.ctx.last_step is not None:
            self._render(self.ctx.last_step)

    def _play(self) -> None:
        if not self.engine.is_running():
            self.ctx.start_run()
            for c in self.cards.values():
                c.destroy()
            self.cards.clear()
        self.engine.set_speed(float(self.speed.get()))
        self.engine.start()

    def _pause(self) -> None:
        self.engine.pause()

    def _stop(self) -> None:
        self.engine.stop()

    def _on_speed(self, value: str) -> None:
        self.engine.set_speed(float(value))
        prefs.set("replay_speed", int(value))
        self.mode_label.configure(text=self.engine.mode_label)

    def _watch(self) -> None:
        if not self.winfo_exists():
            return
        e = self.engine
        if e.error:
            self.state.configure(text=f"Replay error: {e.error}", text_color=T.DANGER)
        elif e.finished:
            self.state.configure(text="Replay complete — end of recorded data", text_color=T.ACCENT)
        elif e.is_running():
            self.state.configure(text="Paused" if e.is_paused() else "Replaying",
                                 text_color=T.ALERT["WARNING"] if e.is_paused() else T.ALERT["NORMAL"])
        else:
            self.state.configure(text="Stopped", text_color=T.MUTED)
        self.mode_label.configure(text=e.mode_label)
        self.after(500, self._watch)

    # ------------------------------------------------------------------ rendering
    def _on_step(self, step, new_alerts) -> None:
        if self.winfo_exists() and self.winfo_ismapped():
            self._render(step)

    def _render(self, step) -> None:
        self.clock.configure(text=pretty_utc(step.window_start_utc),
                             text_color=T.TEXT if step.lookback_complete else T.FAINT)
        self.meta.configure(text=f"window {step.step} of {step.total_steps} · {step.n_flows_window:,} flows "
                                 f"recorded in this window · {len(step.hosts)} hosts in lookback\n"
                                 + self._config_text())
        self.progress.set(step.step / max(1, step.total_steps))

        for w in self.partial.winfo_children():
            w.destroy()
        self.partial.pack_forget()      # an emptied Tk frame keeps its old height, so unpack it
        if not step.lookback_complete:
            self.partial.pack(fill="x", pady=(T.SPACE["m"], 0), before=self.levels, **self._pad)
            first, _ = self.svc.replay_windows()
            note_box(self.partial, (f"Partial lookback — window greyed out, no alerts. Only "
                                    f"{step.lookback_available} of {step.lookback} lookback windows lie inside "
                                    f"replay_flows.csv, which starts at "
                                    f"{pretty_utc(self.svc.to_utc(self.svc.window_start(first)))}. Any traffic "
                                    "before that is not in the file."), T.ALERT["WARNING"]).pack(fill="x")

        for w in self.levels.winfo_children():
            w.destroy()
        hosts = step.hosts
        lstm = step.lstm_available and not hosts.empty and "alert" in hosts
        if lstm and step.lookback_complete:
            counts = hosts["alert"].value_counts()
            label(self.levels, "HOSTS BY ALERT LEVEL", "small_bold", T.MUTED).pack(side="left", padx=(0, 14))
            for lvl in T.ALERT_ORDER:
                label(self.levels, f"■ {lvl} {int(counts.get(lvl, 0))}", "mono_bold", T.ALERT[lvl]).pack(
                    side="left", padx=(0, 16))

        if hosts.empty:
            self.empty.configure(text="No flows recorded in this window's lookback.")
            self.empty.grid()
            return
        self.empty.grid_remove()
        rows = hosts.to_dict("records")
        if lstm:
            rows.sort(key=lambda r: (T.ALERT_ORDER.index(r["alert"]), r["entity"]))
        seen = set()
        for i, r in enumerate(rows):
            host = r["entity"]
            seen.add(host)
            card = self.cards.get(host)
            if card is None:
                card = HostCard(self.grid_area, host, self.svc.horizon_minutes)
                self.cards[host] = card
            card.update_row(r, step.rf_counts.get(host, {}), lstm, step.lookback_complete)
            card.grid(row=1 + i // 2, column=i % 2, sticky="nsew", padx=8, pady=8)
        for host, card in self.cards.items():
            if host not in seen:
                card.grid_remove()
