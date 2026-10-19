"""Overview -- status at a glance. Every figure comes from the loaded artifacts,
the replay state, or the hybrid_alerts table; times are recorded times."""
from __future__ import annotations

import time

import customtkinter as ctk
import numpy as np

from app.auth import db
from app.screens.base import Screen
from app.screens.live_replay import pretty_utc
from app.ui import tokens as T
from app.ui.charts import ThemedChart, style_axes
from app.ui.widgets import Badge, Card, StatTile, button, label, section_title
from services import run_info

MAX_SPARK_HOSTS = 12


class OverviewScreen(Screen):
    title = "Overview"
    subtitle = "Status of the RF–LSTM hybrid, the loaded run and the current replay."

    def build(self) -> None:
        self.header()
        svc = self.ctx.hybrid
        self._last_refresh = 0.0

        g1 = ctk.CTkFrame(self.page, fg_color="transparent")
        self.section(g1)
        g1.columnconfigure((0, 1, 2, 3), weight=1, uniform="tiles")
        self.t_model = StatTile(g1, "Model")
        self.t_run = StatTile(g1, "Training data")
        self.t_replay = StatTile(g1, "Replay file")
        self.t_window = StatTile(g1, "Latest recorded window")
        for i, t in enumerate((self.t_model, self.t_run, self.t_replay, self.t_window)):
            t.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 6, 0 if i == 3 else 6))

        section_title(self.page, "Alerts in the current replay run",
                      "complete-lookback windows only · one per host per level change").pack(
            fill="x", padx=32, pady=(4, 8))
        g2 = ctk.CTkFrame(self.page, fg_color="transparent")
        self.section(g2)
        g2.columnconfigure((0, 1, 2, 3), weight=1, uniform="tiles")
        self.t_levels = {}
        for i, lvl in enumerate(("CRITICAL", "HIGH", "WARNING")):
            t = StatTile(g2, f"{lvl} alerts", "0", T.ALERT[lvl])
            t.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 6, 6))
            self.t_levels[lvl] = t
        self.t_pred = StatTile(g2, "Predicted (of all alerts)", "0", T.ACCENT)
        self.t_pred.grid(row=0, column=3, sticky="nsew", padx=(6, 0))

        row = ctk.CTkFrame(self.page, fg_color="transparent")
        self.section(row)
        row.columnconfigure(0, weight=5, uniform="row")
        row.columnconfigure(1, weight=6, uniform="row")
        self.recent = Card(row)
        self.recent.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self.spark = Card(row)
        self.spark.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        section_title(self.recent.body, "Most recent alerts").pack(fill="x")
        self.recent_list = ctk.CTkFrame(self.recent.body, fg_color="transparent")
        self.recent_list.pack(fill="both", expand=True, pady=(8, 8))
        button(self.recent.body, "Open Alerts →", lambda: self.ctx.navigate("alerts"), "secondary",
               width=140).pack(anchor="w")
        section_title(self.spark.body, "Risk per host", "P(any attack ahead), recorded time").pack(fill="x")
        self.spark_note = label(self.spark.body, "", "small", T.MUTED, wraplength=520)
        self.spark_note.pack(anchor="w", pady=(4, 0))
        self.chart = ThemedChart(self.spark.body, self._draw_sparks, height=300)
        self.chart.pack(fill="both", expand=True, pady=(6, 0))

        self._fill_static(svc)
        self.ctx.step_listeners.append(self._on_step)

    # ------------------------------------------------------------------
    def _fill_static(self, svc) -> None:
        if svc is None:
            self.t_model.set("Not loaded", T.DANGER, self.ctx.hybrid_error or "")
            return
        if svc.lstm_available:
            self.t_model.set("RF–LSTM hybrid", T.ALERT["NORMAL"], "RF flow layer + LSTM detection/forecast heads")
        else:
            self.t_model.set("RF-only fallback", T.ALERT["HIGH"], svc.lstm_error or "LSTM layer unavailable")
        facts = run_info.readme_facts()
        split = run_info.split_description(svc)
        if facts["flows"] is not None:
            self.t_run.set(f"{facts['flows']:,} flows", T.TEXT,
                           f"{facts['dataset']} · {facts['files']} files" + (f"\n{split}" if split else ""))
        else:
            self.t_run.set("—", T.MUTED, "README.txt does not state the dataset size" +
                           (f"\n{split}" if split else ""))
        rs = run_info.replay_summary(svc)
        self.t_replay.set(f"{rs['n_hosts']} hosts", T.TEXT,
                          f"{rs['n_windows']} windows · {rs['n_flows']:,} flows\n"
                          f"{pretty_utc(rs['start_utc'])} → {pretty_utc(rs['end_utc'])[11:]}")

    def on_show(self) -> None:
        self._refresh(force=True)

    def _on_step(self, step, new_alerts) -> None:
        if self.winfo_exists() and self.winfo_ismapped():
            self._refresh()

    def _refresh(self, force: bool = False) -> None:
        now = time.monotonic()      # UI throttle only
        if not force and now - self._last_refresh < 1.0:
            return
        self._last_refresh = now
        st = self.ctx.last_step
        if st is None:
            self.t_window.set("—", T.MUTED, "Replay not started (Live Replay → Play)")
        else:
            self.t_window.set(pretty_utc(st.window_start_utc)[11:], T.TEXT if st.lookback_complete else T.FAINT,
                              f"{st.window_start_utc[:10]} UTC · window {st.step} of {st.total_steps}" +
                              ("" if st.lookback_complete else " · partial lookback"))
        rows = [dict(r) for r in db.fetch_hybrid_alerts(run_id=self.ctx.run_id, limit=100000)] \
            if self.ctx.run_id is not None else []
        for lvl, tile in self.t_levels.items():
            tile.set(str(sum(1 for r in rows if r["level"] == lvl)))
        n_pred = sum(1 for r in rows if r["kind"] == "Predicted")
        self.t_pred.set(f"{n_pred} of {len(rows)}")
        for w in self.recent_list.winfo_children():
            w.destroy()
        if not rows:
            label(self.recent_list, "No alerts in this run yet.", "body", T.MUTED).pack(anchor="w")
        for r in rows[:5]:
            line = ctk.CTkFrame(self.recent_list, fg_color="transparent")
            line.pack(fill="x", pady=3)
            Badge(line, r["level"], r["kind"], width=168).pack(side="left")
            label(line, r["host"], "mono_bold").pack(side="left", padx=(10, 8))
            label(line, pretty_utc(r["window_start_utc"])[11:16], "mono", T.MUTED).pack(side="left")
        self.chart.redraw()

    def _draw_sparks(self, fig, c) -> None:
        hist = {h: list(d) for h, d in self.ctx.host_history.items()
                if any(p["p_attack_next"] is not None for p in d)}
        if not hist:
            self.spark_note.configure(text="Play the Live Replay to fill this in. Greyed points are "
                                           "partial-lookback windows.")
            ax = fig.add_subplot(111)
            style_axes(ax, c)
            ax.set_axis_off()
            return
        latest = {h: d[-1]["p_attack_next"] for h, d in hist.items()}
        hosts = sorted(hist, key=lambda h: (-(latest[h] or 0), h))[:MAX_SPARK_HOSTS]
        extra = len(hist) - len(hosts)
        self.spark_note.configure(text=(f"{len(hosts)} hosts, highest current risk first" +
                                        (f" ({extra} more not shown)" if extra else "") +
                                        ". Greyed points: partial-lookback windows (no alerts)."))
        axes = fig.subplots(len(hosts), 1, sharex=True, squeeze=False)[:, 0]
        fig.subplots_adjust(left=0.30, right=0.86, top=0.97, bottom=0.04, hspace=0.35)
        t_all = sorted({p["window_start"] for d in hist.values() for p in d})
        for ax, h in zip(axes, hosts):
            d = hist[h]
            x = np.array([p["window_start"] for p in d], dtype=float)
            y = np.array([np.nan if p["p_attack_next"] is None else p["p_attack_next"] for p in d], dtype=float)
            ok = np.array([p["complete"] for p in d])
            ax.set_facecolor(c["bg"])
            ax.plot(x, np.where(ok, y, np.nan), color=c["p_any"], linewidth=1.8)
            ax.plot(x, np.where(ok, np.nan, y), color=c["muted"], linewidth=1.2, alpha=0.6, linestyle=(0, (2, 2)))
            ax.set_ylim(-0.05, 1.05)
            ax.set_xlim(t_all[0], t_all[-1] if len(t_all) > 1 else t_all[0] + 60)
            ax.set_yticks([])
            ax.set_xticks([])
            for s in ax.spines.values():
                s.set_visible(False)
            ax.axhline(0, color=c["grid"], linewidth=0.8)
            ax.text(-0.02, 0.5, h, transform=ax.transAxes, ha="right", va="center", fontsize=8,
                    family="monospace", color=c["text"])
            last = y[-1]
            ax.text(1.02, 0.5, "n/a" if np.isnan(last) else f"{last:.2f}", transform=ax.transAxes, ha="left",
                    va="center", fontsize=8, family="monospace",
                    color=c["text"] if ok[-1] else c["muted"])
