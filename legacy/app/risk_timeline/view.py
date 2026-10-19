"""
Risk Timeline -- per-host true severity vs the hybrid's predicted risk over
RECORDED time. Data source: artifacts_rf_lstm/data/dashboard_feed.csv only
(never the legacy simulation feed). x = window_start_utc from the feed.

Two stacked panels sharing the time axis (no dual y-axis):
  top    severity tier: true tier now (y_now), true highest tier in the next
         horizon (true_tier_next) and the hybrid's detected tier (det_tier)
  bottom predicted risk: P(any attack within horizon), P(escalation within
         horizon), with the alert thresholds from preprocessing.json dashed.
Windows missing from the feed are left as gaps (lines are not drawn across them).
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg  # noqa: E402

from app.common import theme  # noqa: E402
from app.common.context import AppContext  # noqa: E402
from app.common.widgets import dataframe_table  # noqa: E402
from services.hybrid_service import TIER_NAMES  # noqa: E402

# Series colours validated (dataviz validate_palette.js, dark mode, surface BG_CARD): all checks pass.
COLOR_P_ANY = "#0891b2"
COLOR_P_ESC = "#9a7cf0"
COLOR_TRUTH = "#c9d1d9"
COLOR_GRID = theme.BORDER
LOGIT_CLIP = 1e-7

TABLE_COLUMNS = ["window_start_utc", "n_flows", "y_now", "true_tier_next", "det_tier", "fut_tier",
                 "p_attack_next", "p_severe_next", "alert", "alert_reason"]


class RiskTimelineView(tk.Frame):
    def __init__(self, parent, ctx: AppContext):
        super().__init__(parent, bg=theme.BG_PRIMARY)
        self.ctx = ctx
        self.svc = ctx.hybrid
        self.feed: pd.DataFrame | None = None
        self.host_df: pd.DataFrame | None = None
        self._table = None
        self._build()

    def _build(self) -> None:
        pad = tk.Frame(self, bg=theme.BG_PRIMARY, padx=24, pady=18)
        pad.pack(fill="both", expand=True)
        tk.Label(pad, text="Risk Timeline — RF–LSTM hybrid", bg=theme.BG_PRIMARY, fg=theme.TEXT_PRIMARY,
                 font=(theme.FONT_HEADER[0], 18, "bold")).pack(anchor="w")
        tk.Label(pad, text="Recorded time (window start, UTC) from artifacts_rf_lstm/data/dashboard_feed.csv. "
                           "Windows absent from the feed are shown as gaps.",
                 bg=theme.BG_PRIMARY, fg=theme.TEXT_MUTED, font=theme.FONT_LABEL).pack(anchor="w", pady=(0, 10))

        if self.svc is None:
            tk.Label(pad, text=self.ctx.hybrid_error or "RF-LSTM hybrid is not loaded.", bg=theme.BG_PRIMARY,
                     fg=theme.ACCENT_RED, font=theme.FONT_LABEL).pack(anchor="w")
            return
        try:
            self.feed = self.svc.dashboard_feed()
        except Exception as exc:
            tk.Label(pad, text=f"Could not read dashboard_feed.csv: {exc}", bg=theme.BG_PRIMARY,
                     fg=theme.ACCENT_RED, font=theme.FONT_LABEL).pack(anchor="w")
            return

        controls = tk.Frame(pad, bg=theme.BG_CARD, highlightbackground=theme.BORDER, highlightthickness=1)
        controls.pack(fill="x", pady=(0, 10))
        inner = tk.Frame(controls, bg=theme.BG_CARD, padx=14, pady=8)
        inner.pack(fill="x")
        tk.Label(inner, text="Host (IP)", bg=theme.BG_CARD, fg=theme.TEXT_MUTED,
                 font=theme.FONT_LABEL).pack(side="left")
        hosts = self._hosts_by_alert_count()
        self.host_var = tk.StringVar(value=hosts[0] if hosts else "")
        combo = ttk.Combobox(inner, textvariable=self.host_var, values=hosts, width=28, state="readonly")
        combo.pack(side="left", padx=(6, 18))
        combo.bind("<<ComboboxSelected>>", lambda e: self._redraw())
        self.logit_var = tk.BooleanVar(value=False)
        tk.Checkbutton(inner, text="Logit probability scale (separates values near 0 and 1)",
                       variable=self.logit_var, command=self._redraw, bg=theme.BG_CARD, fg=theme.TEXT_PRIMARY,
                       selectcolor=theme.BG_SECONDARY, activebackground=theme.BG_CARD,
                       font=theme.FONT_LABEL).pack(side="left")
        self.summary = tk.Label(controls, text="", bg=theme.BG_CARD, fg=theme.TEXT_MUTED, font=theme.FONT_MONO_SMALL,
                                justify="left", wraplength=1000)
        self.summary.pack(anchor="w", padx=14, pady=(0, 8))

        chart_card = tk.Frame(pad, bg=theme.BG_CARD, highlightbackground=theme.BORDER, highlightthickness=1)
        chart_card.pack(fill="both", expand=True)
        self.fig = plt.Figure(figsize=(10, 5.6), dpi=100, facecolor=theme.BG_CARD)
        self.ax_tier, self.ax_risk = self.fig.subplots(2, 1, sharex=True, gridspec_kw={"height_ratios": [1, 1.25]})
        self.fig.subplots_adjust(left=0.16, right=0.98, top=0.91, bottom=0.12, hspace=0.38)
        self.canvas = FigureCanvasTkAgg(self.fig, master=chart_card)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=(8, 0))
        self.readout = tk.Label(chart_card, text="Hover the chart to read a recorded window.", bg=theme.BG_CARD,
                                fg=theme.TEXT_MUTED, font=theme.FONT_MONO_SMALL, anchor="w", justify="left")
        self.readout.pack(fill="x", padx=16, pady=(0, 8))
        self.canvas.mpl_connect("motion_notify_event", self._on_hover)

        self.table_card = tk.Frame(pad, bg=theme.BG_CARD, highlightbackground=theme.BORDER, highlightthickness=1)
        self.table_card.pack(fill="x", pady=(10, 0))
        self._redraw()

    def _hosts_by_alert_count(self) -> list[str]:
        f = self.feed
        if f is None or f.empty:
            return []
        n_alert = (f["alert"] != "NORMAL").groupby(f["entity"]).sum() if "alert" in f else \
            f.groupby("entity").size() * 0
        return sorted(n_alert.index, key=lambda h: (-int(n_alert[h]), h))

    # ------------------------------------------------------------------
    def _segments(self, df: pd.DataFrame):
        """Split into runs of consecutive recorded windows (diff == window_sec)."""
        ts = df["win_ts"].to_numpy(dtype=float)
        breaks = np.where(np.diff(ts) > self.svc.window_sec + 1e-6)[0] + 1
        return np.split(np.arange(len(df)), breaks)

    def _style_axis(self, ax) -> None:
        ax.set_facecolor(theme.BG_CARD)
        ax.tick_params(colors=theme.TEXT_MUTED, labelsize=8)
        for side, spine in ax.spines.items():
            spine.set_color(COLOR_GRID)
            spine.set_visible(side in ("left", "bottom"))
        ax.grid(axis="y", color=COLOR_GRID, linewidth=0.6)

    def _redraw(self) -> None:
        host = self.host_var.get()
        df = self.feed[self.feed["entity"] == host].sort_values("win_ts", kind="mergesort").reset_index(drop=True)
        self.host_df = df
        df = df.assign(t=pd.to_datetime(df["window_start_utc"], utc=True).dt.tz_localize(None))
        svc = self.svc
        hm = f"{svc.horizon_minutes:g}"
        for ax in (self.ax_tier, self.ax_risk):
            ax.clear()
            self._style_axis(ax)
        if df.empty:
            self.canvas.draw_idle()
            return

        # --- tiers (top) ---
        a = self.ax_tier
        has_now = "y_now" in df and df["y_now"].notna().any()
        has_next = "true_tier_next" in df and df["true_tier_next"].notna().any()
        first = True
        for seg in self._segments(df):
            s = df.iloc[seg]
            lone = len(s) == 1  # a one-window segment has no step length; mark it instead
            # Truth is a wide translucent underlay so it stays visible where the
            # hybrid's (thinner) detected-tier line coincides with it. Markers keep
            # isolated windows (gaps on both sides) visible.
            if has_now:
                a.step(s["t"], s["y_now"], where="post", color=COLOR_TRUTH, linewidth=7, alpha=0.3,
                       marker="s" if lone else None, markersize=7, solid_capstyle="butt", label="True tier (now)" if first else None)
            if has_next:
                a.step(s["t"], s["true_tier_next"], where="post", color=COLOR_TRUTH, linewidth=1.6,
                       linestyle=(0, (1, 2)), label=f"True highest tier (next {hm} min)" if first else None)
            a.step(s["t"], s["det_tier"], where="post", color=COLOR_P_ANY, linewidth=2, marker="o" if lone else None,
                   markersize=4, label="Hybrid detected tier (now)" if first else None)
            first = False
        if not (has_now or has_next):
            a.text(0.01, 0.97, "no true-tier columns in this feed", transform=a.transAxes, va="top", fontsize=7,
                   color=theme.TEXT_MUTED)
        a.set_ylim(-0.4, len(TIER_NAMES) - 0.6)
        a.set_yticks(range(len(TIER_NAMES)))
        a.set_yticklabels(TIER_NAMES, fontsize=7, color=theme.TEXT_MUTED)
        a.set_ylabel("severity tier", color=theme.TEXT_MUTED, fontsize=8)
        a.legend(loc="lower left", bbox_to_anchor=(0.0, 1.0), ncol=3, fontsize=7, frameon=False,
                 labelcolor=theme.TEXT_PRIMARY, borderaxespad=0.2)

        # --- risk (bottom) ---
        r = self.ax_risk
        logit = self.logit_var.get()
        clip = (lambda v: np.clip(v, LOGIT_CLIP, 1 - LOGIT_CLIP)) if logit else (lambda v: v)
        first = True
        for seg in self._segments(df):
            s = df.iloc[seg]
            r.plot(s["t"], clip(s["p_attack_next"]), color=COLOR_P_ANY, linewidth=2, marker="o", markersize=3,
                   label=f"P(any attack ≤{hm} min)" if first else None)
            r.plot(s["t"], clip(s["p_severe_next"]), color=COLOR_P_ESC, linewidth=2, marker="s", markersize=3,
                   label=f"P(escalation ≤{hm} min)" if first else None)
            first = False
        # Dashed alert thresholds (preprocessing.json). Labels sit inside the plot just
        # above their line, at opposite ends, so they never collide even when both
        # thresholds are close to 1.
        for thr, name, x, ha in ((svc.threshold_attack, "WARNING if P(any) ≥", 0.995, "right"),
                                 (svc.threshold_severe, "HIGH if P(escalation) ≥", 0.005, "left")):
            r.axhline(clip(thr), color=theme.TEXT_MUTED, linestyle="--", linewidth=1)
            r.annotate(f"{name} {thr:.4f}", xy=(x, clip(thr)), xycoords=("axes fraction", "data"),
                       xytext=(0, 2), textcoords="offset points", ha=ha, va="bottom", fontsize=7,
                       color=theme.TEXT_MUTED)
        if logit:
            r.set_yscale("logit")
        else:
            r.set_ylim(-0.03, 1.1)
        r.set_ylabel(f"predicted risk (next {hm} min)", color=theme.TEXT_MUTED, fontsize=8)
        r.legend(loc="lower left", bbox_to_anchor=(0.0, 1.0), ncol=2, fontsize=7, frameon=False,
                 labelcolor=theme.TEXT_PRIMARY, borderaxespad=0.2)
        locator = mdates.AutoDateLocator(maxticks=8)
        r.xaxis.set_major_locator(locator)
        r.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
        r.xaxis.get_offset_text().set_color(theme.TEXT_MUTED)
        r.set_xlabel("recorded window start (UTC)", color=theme.TEXT_MUTED, fontsize=8)
        self.canvas.draw_idle()

        counts = df["alert"].value_counts()
        self.summary.config(text=(f"{host} · {len(df)} windows · {df['window_start_utc'].iloc[0]} → "
                                  f"{df['window_start_utc'].iloc[-1]} · " +
                                  "  ".join(f"{lvl} {int(counts.get(lvl, 0))}" for lvl in theme.ALERT_LEVEL_ORDER)))
        self._render_table(df)

    def _render_table(self, df: pd.DataFrame) -> None:
        if self._table is not None:
            self._table.master.destroy()
        holder = tk.Frame(self.table_card, bg=theme.BG_CARD)
        holder.pack(fill="x", padx=8, pady=8)
        cols = [c for c in TABLE_COLUMNS if c in df.columns]
        self._table = dataframe_table(holder, df[cols], height=6)
        self._table.pack(side="left", fill="x", expand=True)
        sb = ttk.Scrollbar(holder, orient="vertical", command=self._table.yview)
        sb.pack(side="right", fill="y")
        self._table.configure(yscrollcommand=sb.set)

    def _on_hover(self, event) -> None:
        df = self.host_df
        if event.inaxes is None or event.xdata is None or df is None or df.empty:
            return
        t = mdates.num2date(event.xdata).replace(tzinfo=None)
        times = pd.to_datetime(df["window_start_utc"], utc=True).dt.tz_localize(None)
        i = int(np.argmin(np.abs((times - pd.Timestamp(t)).dt.total_seconds().to_numpy())))
        row = df.iloc[i]
        hm = f"{self.svc.horizon_minutes:g}"
        true_now = TIER_NAMES[int(row["y_now"])] if "y_now" in row else "n/a"
        reason = row["alert_reason"] if isinstance(row.get("alert_reason"), str) else ""
        self.readout.config(
            fg=theme.TEXT_PRIMARY,
            text=(f"{row['window_start_utc']}  true: {true_now}   detected: {TIER_NAMES[int(row['det_tier'])]}   "
                  f"forecast: {TIER_NAMES[int(row['fut_tier'])]}   P(any ≤{hm} min) {row['p_attack_next']:.6f}   "
                  f"P(escalation ≤{hm} min) {row['p_severe_next']:.6f}   {row['alert']} {reason}"))
