"""
Hybrid Replay -- live view of the RF-LSTM hybrid over recorded ToN_IoT traffic.

Every time on this screen is the recorded window start (from replay_flows.csv
ts via services.hybrid_service). Hosts are the real IPs in the data.
"""
from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from app.auth import db
from app.common import theme
from app.common.context import AppContext
from app.common.widgets import HybridAlertRow
from services.hybrid_service import TIER_NAMES

SPEED_CHOICES = (1, 10, 30, 60, 120, 300, 600)
MAX_RECENT_ALERTS = 4


def _tier(t) -> str:
    t = int(t)
    return TIER_NAMES[t] if 0 <= t < len(TIER_NAMES) else f"Tier {t}"


def _pretty_utc(s: str) -> str:
    return s.replace("T", " ").replace("Z", " UTC")


class HybridReplayView(tk.Frame):
    def __init__(self, parent, ctx: AppContext, shell):
        super().__init__(parent, bg=theme.BG_PRIMARY)
        self.ctx = ctx
        self.shell = shell
        self.svc = ctx.hybrid
        self.engine = ctx.hybrid_engine
        self._recent_alerts: list = []
        self._build()
        if self.svc is not None:
            self.ctx.hybrid_listeners.append(self._on_step)
            if self.ctx.hybrid_last_step is not None:
                self._render_step(self.ctx.hybrid_last_step)
            self._watch_engine()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        pad = tk.Frame(self, bg=theme.BG_PRIMARY, padx=24, pady=18)
        pad.pack(fill="both", expand=True)

        tk.Label(pad, text="Hybrid Replay — RF–LSTM", bg=theme.BG_PRIMARY, fg=theme.TEXT_PRIMARY,
                 font=(theme.FONT_HEADER[0], 18, "bold")).pack(anchor="w")

        if self.svc is None:
            self._message(pad, self.ctx.hybrid_error or "RF-LSTM hybrid is not loaded.", theme.ACCENT_RED)
            return
        svc = self.svc

        # Mode banner -- the speed is the only thing that is not recorded data.
        banner = tk.Frame(pad, bg=theme.BG_CARD, highlightbackground=theme.ACCENT_AMBER, highlightthickness=1)
        banner.pack(fill="x", pady=(8, 8))
        self.mode_label = tk.Label(banner, text=self.engine.mode_label, bg=theme.BG_CARD, fg=theme.ACCENT_AMBER,
                                   font=theme.FONT_HEADER)
        self.mode_label.pack(anchor="w", padx=14, pady=(8, 0))
        tk.Label(banner, text="All times are recorded Zeek capture times (window start, UTC) from "
                              "artifacts_rf_lstm/data/replay_flows.csv, processed in recorded ts order. "
                              "Hosts are the destination IPs recorded in the data.",
                 bg=theme.BG_CARD, fg=theme.TEXT_MUTED, font=(theme.FONT_LABEL[0], 9), justify="left",
                 wraplength=1000).pack(anchor="w", padx=14, pady=(0, 8))

        if not svc.lstm_available:
            self._message(pad, f"LSTM layer unavailable. {svc.lstm_error} Detection/forecast tiers, "
                               "forecast probabilities and alert levels require the LSTM layer.", theme.ACCENT_RED)
        for w in svc.load_warnings:
            self._message(pad, f"Model load warning: {w}", theme.ACCENT_AMBER)

        # Controls
        controls = tk.Frame(pad, bg=theme.BG_CARD, highlightbackground=theme.BORDER, highlightthickness=1)
        controls.pack(fill="x", pady=(0, 10))
        inner = tk.Frame(controls, bg=theme.BG_CARD, padx=14, pady=8)
        inner.pack(fill="x")
        self._button(inner, "▶ Start", self._start, theme.ACCENT_GREEN).pack(side="left")
        self._button(inner, "⏸ Pause", self._pause, theme.ACCENT_AMBER).pack(side="left", padx=8)
        self._button(inner, "⏹ Stop", self._stop, theme.TEXT_MUTED).pack(side="left")
        tk.Label(inner, text="Replay speed  ×", bg=theme.BG_CARD, fg=theme.TEXT_MUTED,
                 font=theme.FONT_LABEL).pack(side="left", padx=(24, 4))
        self.speed_var = tk.StringVar(value=f"{self.engine.speed:g}")
        speed = ttk.Combobox(inner, textvariable=self.speed_var, values=[str(s) for s in SPEED_CHOICES],
                             width=6, state="readonly")
        speed.pack(side="left")
        speed.bind("<<ComboboxSelected>>", self._on_speed)
        self.state_label = tk.Label(inner, text="Stopped", bg=theme.BG_CARD, fg=theme.TEXT_MUTED,
                                    font=theme.FONT_LABEL)
        self.state_label.pack(side="right")

        # Recorded time, prominently
        clock = tk.Frame(pad, bg=theme.BG_CARD, highlightbackground=theme.BORDER, highlightthickness=1)
        clock.pack(fill="x", pady=(0, 10))
        cinner = tk.Frame(clock, bg=theme.BG_CARD, padx=16, pady=10)
        cinner.pack(fill="x")
        tk.Label(cinner, text="RECORDED WINDOW START", bg=theme.BG_CARD, fg=theme.TEXT_MUTED,
                 font=(theme.FONT_LABEL[0], 8, "bold")).grid(row=0, column=0, sticky="w")
        self.time_label = tk.Label(cinner, text="—", bg=theme.BG_CARD, fg=theme.ACCENT_CYAN,
                                   font=(theme.FONT_MONO[0], 26, "bold"))
        self.time_label.grid(row=1, column=0, sticky="w")
        self.window_label = tk.Label(cinner, text="", bg=theme.BG_CARD, fg=theme.TEXT_MUTED,
                                     font=theme.FONT_MONO_SMALL, justify="left")
        self.window_label.grid(row=2, column=0, sticky="w")
        self.level_summary = tk.Frame(cinner, bg=theme.BG_CARD)
        self.level_summary.grid(row=3, column=0, sticky="w", pady=(6, 0))
        self.window_label.config(text=self._config_text())

        # Host table
        table_card = tk.Frame(pad, bg=theme.BG_CARD, highlightbackground=theme.BORDER, highlightthickness=1)
        table_card.pack(fill="x")
        style = ttk.Style()
        style.configure("Hybrid.Treeview", background=theme.BG_CARD, fieldbackground=theme.BG_CARD,
                        foreground=theme.TEXT_PRIMARY, rowheight=24, font=theme.FONT_MONO_SMALL)
        style.configure("Hybrid.Treeview.Heading", background=theme.BG_SECONDARY, foreground=theme.TEXT_MUTED,
                        font=(theme.FONT_LABEL[0], 8, "bold"))
        hm = f"{svc.horizon_minutes:g}"
        self.columns = ("host", "flows", "rf", "det", "fut", "p_any", "p_esc", "alert", "reason")
        headers = {"host": "Host (IP)", "flows": "Flows", "rf": "RF per-flow verdicts (this window)",
                   "det": "Detected tier (now)", "fut": f"Forecast tier (≤{hm} min)",
                   "p_any": f"P(any attack ≤{hm} min)", "p_esc": f"P(escalation ≤{hm} min)",
                   "alert": "Alert", "reason": "Alert reason"}
        # Column widths from measured text, so they hold at any display scaling.
        body_font = tkfont.Font(font=theme.FONT_MONO_SMALL)
        head_font = tkfont.Font(font=(theme.FONT_LABEL[0], 8, "bold"))
        samples = {"host": "0000:0000:0000:0000", "flows": "000000", "rf": "scanning 0000 · normal 0000 · dos 0000",
                   "det": max(TIER_NAMES, key=len), "fut": max(TIER_NAMES, key=len), "p_any": "0.0000",
                   "p_esc": "0.0000", "alert": "CRITICAL",
                   "reason": "Predicted: escalation to compromise/DoS within horizon"}
        self.tree = ttk.Treeview(table_card, columns=self.columns, show="headings", style="Hybrid.Treeview",
                                 height=6)
        for c in self.columns:
            self.tree.heading(c, text=headers[c])
            w = max(head_font.measure(headers[c]), body_font.measure(samples[c])) + 18
            self.tree.column(c, width=w, minwidth=w, anchor="w", stretch=c == "reason")
        xs = ttk.Scrollbar(table_card, orient="horizontal", command=self.tree.xview)
        xs.pack(side="bottom", fill="x")
        self.tree.pack(fill="both", expand=True, side="left", pady=1)
        sb = ttk.Scrollbar(table_card, orient="vertical", command=self.tree.yview)
        sb.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=sb.set, xscrollcommand=xs.set)
        for level, color in theme.ALERT_LEVEL_COLORS.items():
            self.tree.tag_configure(level, foreground=color)

        tk.Label(pad, text=(f"Alert thresholds (preprocessing.json): WARNING if P(any attack) ≥ "
                            f"{svc.threshold_attack:.4f}; HIGH if P(escalation to compromise/DoS) ≥ "
                            f"{svc.threshold_severe:.4f}; detection-based levels from the detected tier. "
                            "Level and reason come from sentinel_inference.alert_level()."),
                 bg=theme.BG_PRIMARY, fg=theme.TEXT_MUTED, font=(theme.FONT_LABEL[0], 8), justify="left",
                 wraplength=1000).pack(anchor="w", pady=(4, 6))

        # Latest alerts (same row component as the Alerts screen)
        alerts_card = tk.Frame(pad, bg=theme.BG_CARD, highlightbackground=theme.BORDER, highlightthickness=1)
        alerts_card.pack(fill="x")
        head = tk.Frame(alerts_card, bg=theme.BG_CARD)
        head.pack(fill="x", padx=12, pady=(8, 2))
        tk.Label(head, text="Latest alerts (one per host per level change)", bg=theme.BG_CARD,
                 fg=theme.TEXT_PRIMARY, font=theme.FONT_HEADER).pack(side="left")
        tk.Label(head, text="filled badge = Detected now   ·   outlined badge = Predicted within horizon",
                 bg=theme.BG_CARD, fg=theme.TEXT_MUTED, font=(theme.FONT_LABEL[0], 8)).pack(side="right")
        self.alerts_box = tk.Frame(alerts_card, bg=theme.BG_CARD)
        self.alerts_box.pack(fill="x", padx=12, pady=(0, 8))
        self._render_recent_alerts()

    def _config_text(self) -> str:
        s = self.svc
        return (f"window {s.window_sec:g} s · lookback {s.lookback} windows · forecast horizon "
                f"{s.horizon} windows ({s.horizon_minutes:g} min) · t0 = {s.to_utc(s.t0)}")

    def _message(self, parent, text: str, color: str) -> None:
        box = tk.Frame(parent, bg=theme.BG_CARD, highlightbackground=color, highlightthickness=1)
        box.pack(fill="x", pady=(0, 8))
        tk.Label(box, text=text, bg=theme.BG_CARD, fg=color, font=theme.FONT_LABEL, justify="left",
                 wraplength=1000).pack(anchor="w", padx=14, pady=8)

    def _button(self, parent, text, command, accent) -> tk.Button:
        return tk.Button(parent, text=text, command=command, bg=theme.BG_SECONDARY, fg=accent,
                         activebackground=theme.BORDER, relief="flat", font=(theme.FONT_LABEL[0], 9, "bold"),
                         cursor="hand2", padx=10, pady=4)

    # ------------------------------------------------------------------
    def _start(self) -> None:
        if not self.engine.is_running():
            self.ctx.hybrid_tracker.reset()
            self.ctx.hybrid_run_id = db.next_hybrid_run_id()
            self._recent_alerts = []
            self._render_recent_alerts()
        self.engine.set_speed(float(self.speed_var.get()))
        self.engine.start()
        self.shell.set_live_status(True, text="Replay (recorded)")

    def _pause(self) -> None:
        self.engine.pause()
        self.shell.set_live_status(False)

    def _stop(self) -> None:
        self.engine.stop()
        self.shell.set_live_status(False)

    def _on_speed(self, _event=None) -> None:
        self.engine.set_speed(float(self.speed_var.get()))
        self.mode_label.config(text=self.engine.mode_label)

    def _watch_engine(self) -> None:
        if not self.winfo_exists():
            return
        e = self.engine
        if e.error:
            self.state_label.config(text=f"Replay error: {e.error}", fg=theme.ACCENT_RED)
        elif e.finished:
            self.state_label.config(text="Replay complete — end of recorded data", fg=theme.ACCENT_CYAN)
        elif e.is_running():
            paused = e.is_paused()
            self.state_label.config(text="Paused" if paused else "Replaying", fg=theme.ACCENT_AMBER if paused
                                    else theme.ACCENT_GREEN)
        else:
            self.state_label.config(text="Stopped", fg=theme.TEXT_MUTED)
        self.after(500, self._watch_engine)

    # ------------------------------------------------------------------
    def _on_step(self, step, new_alerts) -> None:
        if not self.winfo_exists():
            return
        self._recent_alerts = (list(reversed([a.__dict__ for a in new_alerts])) + self._recent_alerts)[
            :MAX_RECENT_ALERTS]
        self._render_step(step)
        if new_alerts:
            self._render_recent_alerts()

    def _render_step(self, step) -> None:
        self.mode_label.config(text=self.engine.mode_label)
        self.time_label.config(text=_pretty_utc(step.window_start_utc))
        self.window_label.config(text=f"window {step.step} of {step.total_steps} · "
                                      f"{step.n_flows_window:,} flows recorded in this window · "
                                      f"{len(step.hosts)} hosts in lookback\n{self._config_text()}")

        hosts = step.hosts
        for w in self.level_summary.winfo_children():
            w.destroy()
        if step.lstm_available and not hosts.empty:
            counts = hosts["alert"].value_counts()
            tk.Label(self.level_summary, text="HOSTS BY ALERT LEVEL", bg=theme.BG_CARD, fg=theme.TEXT_MUTED,
                     font=(theme.FONT_LABEL[0], 8, "bold")).pack(side="left", padx=(0, 10))
            for lvl in theme.ALERT_LEVEL_ORDER:
                tk.Label(self.level_summary, text=f"■ {lvl} {int(counts.get(lvl, 0))}", bg=theme.BG_CARD,
                         fg=theme.ALERT_LEVEL_COLORS[lvl], font=(theme.FONT_MONO[0], 10, "bold")).pack(
                    side="left", padx=(0, 14))

        self.tree.delete(*self.tree.get_children())
        if hosts.empty:
            return
        rows = hosts.to_dict("records")
        if step.lstm_available:
            rows.sort(key=lambda r: (theme.ALERT_LEVEL_ORDER.index(r["alert"]), r["entity"]))
        for r in rows:
            counts = step.rf_counts.get(r["entity"], {})
            rf_text = " · ".join(f"{t} {n}" for t, n in sorted(counts.items(), key=lambda kv: -kv[1])) \
                or "no flows this window"
            if step.lstm_available:
                vals = (r["entity"], r["n_flows"], rf_text, _tier(r["det_tier"]), _tier(r["fut_tier"]),
                        f"{r['p_attack_next']:.4f}", f"{r['p_severe_next']:.4f}", r["alert"],
                        r["alert_reason"] or "—")
                tag = r["alert"]
            else:
                vals = (r["entity"], r["n_flows"], rf_text, f"RF max: {_tier(r['rf_tier'])}",
                        "n/a", "n/a", "n/a", "n/a", "LSTM layer unavailable")
                tag = ""
            self.tree.insert("", "end", values=vals, tags=(tag,))

    def _render_recent_alerts(self) -> None:
        for w in self.alerts_box.winfo_children():
            w.destroy()
        if not self._recent_alerts:
            msg = ("No alerts yet in this replay run." if self.svc.lstm_available
                   else "Alerts require the LSTM layer (unavailable).")
            tk.Label(self.alerts_box, text=msg, bg=theme.BG_CARD, fg=theme.TEXT_MUTED,
                     font=theme.FONT_LABEL).pack(anchor="w", pady=4)
            return
        for a in self._recent_alerts:
            HybridAlertRow(self.alerts_box, a, TIER_NAMES).pack(fill="x")
