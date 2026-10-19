"""
Risk Timeline -- per host, true severity vs the hybrid's predicted risk over
RECORDED time (dashboard_feed.csv, x = window_start_utc). Two stacked panels
share the time axis (no dual y-axis). Test blocks are runs of consecutive
feed windows; gaps between blocks (and missing windows) are drawn as gaps.
"""
from __future__ import annotations

import customtkinter as ctk
import matplotlib.dates as mdates
import numpy as np
import pandas as pd

from app.screens.base import Screen
from app.screens.live_replay import pretty_utc, tier_name
from app.ui import theme, tokens as T
from app.ui.charts import ThemedChart, style_axes
from app.ui.widgets import Card, Table, label
from services.hybrid_service import TIER_NAMES

ALL_BLOCKS = "All blocks"
LOGIT_CLIP = 1e-7
TABLE_COLUMNS = ["window_start_utc", "n_flows", "y_now", "true_tier_next", "det_tier", "fut_tier",
                 "p_attack_next", "p_severe_next", "alert", "alert_reason"]
TABLE_MAX_ROWS = 60


class RiskTimelineScreen(Screen):
    title = "Risk Timeline"
    subtitle = ("Per host: true severity tier vs the hybrid's predicted risk over recorded time "
                "(artifacts_rf_lstm/data/dashboard_feed.csv).")

    def build(self) -> None:
        self.header()
        self.svc = self.ctx.hybrid
        if self.svc is None:
            self.unavailable(self.ctx.hybrid_error or "The RF–LSTM hybrid is not loaded.")
            return
        try:
            self.feed = self.svc.dashboard_feed().sort_values(["entity", "win_ts"], kind="mergesort")
        except Exception as exc:
            self.unavailable(f"Could not read dashboard_feed.csv: {exc}")
            return
        self._blocks = self._find_blocks()
        self._df = pd.DataFrame()

        ctl = Card(self.page, padding=T.SPACE["m"])
        self.section(ctl)
        b = ctl.body
        label(b, "HOST (IP)", "small_bold", T.MUTED).grid(row=0, column=0, sticky="w")
        label(b, "TEST BLOCK", "small_bold", T.MUTED).grid(row=0, column=1, sticky="w", padx=(16, 0))
        hosts = self._hosts_by_attack_windows()
        self.host = self._menu(b, hosts, 0, 190)
        self.block = self._menu(b, [ALL_BLOCKS], 1, 460)
        self.block.grid_configure(padx=(16, 0))
        self.logit = ctk.CTkSwitch(b, text="Logit probability scale", command=self._redraw,
                                   font=theme.font("small"), text_color=T.TEXT, progress_color=T.ACCENT)
        self.logit.grid(row=1, column=2, sticky="w", padx=(20, 0))
        b.columnconfigure(3, weight=1)
        self.summary = label(b, "", "small", T.MUTED)
        self.summary.grid(row=2, column=0, columnspan=4, sticky="w", pady=(10, 0))

        chart_card = Card(self.page, padding=T.SPACE["s"])
        self.section(chart_card)
        self.chart = ThemedChart(chart_card.body, self._draw_chart, height=470)
        self.chart.pack(fill="both", expand=True)
        self.readout = label(chart_card.body, "Hover the chart to read a recorded window.", "mono_small", T.MUTED)
        self.readout.pack(anchor="w", padx=8, pady=(4, 4))
        self.chart.canvas.mpl_connect("motion_notify_event", self._hover)

        self.table_holder = ctk.CTkFrame(self.page, fg_color="transparent")
        self.section(self.table_holder)
        self._on_host(hosts[0] if hosts else None)

    def _menu(self, parent, values, col, width):
        m = ctk.CTkOptionMenu(parent, values=values or ["—"], width=width, font=theme.font("small"),
                              dropdown_font=theme.font("small"), fg_color=T.SURFACE_2, button_color=T.SURFACE_2,
                              button_hover_color=T.BORDER, text_color=T.TEXT, dropdown_fg_color=T.SURFACE,
                              dropdown_text_color=T.TEXT, dropdown_hover_color=T.SURFACE_2,
                              command=(self._on_host if col == 0 else lambda _v: self._redraw()))
        m.grid(row=1, column=col, sticky="w")
        return m

    # ------------------------------------------------------------------ data
    def _attack(self, df: pd.DataFrame) -> pd.Series:
        """Attack windows: true current tier > 0 when the feed has it, else the hybrid's detected tier."""
        col = "y_now" if "y_now" in df and df["y_now"].notna().any() else "det_tier"
        return df[col].fillna(0) > 0

    def _find_blocks(self) -> list[tuple[float, float]]:
        """Consecutive runs of feed windows (any host); a gap > window_sec starts a new block."""
        w = np.sort(self.feed["win_ts"].unique().astype(float))
        if len(w) == 0:
            return []
        cuts = np.where(np.diff(w) > self.svc.window_sec + 1e-6)[0] + 1
        return [(float(seg[0]), float(seg[-1])) for seg in np.split(w, cuts)]

    def _hosts_by_attack_windows(self) -> list[str]:
        f = self.feed
        n = self._attack(f).groupby(f["entity"]).sum()
        return sorted(n.index, key=lambda h: (-int(n[h]), h))

    def _block_label(self, i: int, lo: float, hi: float, n_attack: int) -> str:
        a, b = pretty_utc(self.svc.to_utc(lo)), pretty_utc(self.svc.to_utc(hi))
        return f"Block {i + 1} · {a[:16]} – {b[11:16]} UTC · {n_attack} attack windows"

    def _on_host(self, host) -> None:
        if host is None:
            return
        d = self.feed[self.feed["entity"] == host]
        att = self._attack(d)
        options, best, best_n = [], None, -1
        self._block_by_label = {}
        for i, (lo, hi) in enumerate(self._blocks):
            m = (d["win_ts"] >= lo) & (d["win_ts"] <= hi)
            if not m.any():
                continue
            n = int(att[m].sum())
            lab = self._block_label(i, lo, hi, n)
            options.append(lab)
            self._block_by_label[lab] = (lo, hi)
            if n > best_n:
                best, best_n = lab, n
        self.block.configure(values=options + [ALL_BLOCKS])
        self.block.set(best or ALL_BLOCKS)
        self._redraw()

    def _selected(self) -> pd.DataFrame:
        host = self.host.get()
        d = self.feed[self.feed["entity"] == host]
        sel = self.block.get()
        if sel != ALL_BLOCKS and sel in self._block_by_label:
            lo, hi = self._block_by_label[sel]
            d = d[(d["win_ts"] >= lo) & (d["win_ts"] <= hi)]
        d = d.assign(t=pd.to_datetime(d["window_start_utc"], utc=True).dt.tz_localize(None)).reset_index(drop=True)
        return d

    # ------------------------------------------------------------------ chart
    def _redraw(self) -> None:
        self._df = self._selected()
        df = self._df
        if df.empty:
            self.summary.configure(text="No feed rows for this selection.")
        else:
            counts = df["alert"].value_counts() if "alert" in df else {}
            n_blocks = len({b for b in self._block_by_label.values()
                            if ((df["win_ts"] >= b[0]) & (df["win_ts"] <= b[1])).any()})
            self.summary.configure(text=(
                f"{self.host.get()} · {len(df)} windows in {n_blocks} block(s) · "
                f"{pretty_utc(df['window_start_utc'].iloc[0])} → {pretty_utc(df['window_start_utc'].iloc[-1])} "
                "· " + "  ".join(f"{lvl} {int(counts.get(lvl, 0))}" for lvl in T.ALERT_ORDER)))
        self.chart.redraw()
        self._render_table(df)

    def _segments(self, df):
        ts = df["win_ts"].to_numpy(dtype=float)
        cuts = np.where(np.diff(ts) > self.svc.window_sec + 1e-6)[0] + 1
        return np.split(np.arange(len(df)), cuts)

    def _draw_chart(self, fig, c) -> None:
        df = getattr(self, "_df", pd.DataFrame())
        if df is None or df.empty:
            return
        svc = self.svc
        hm = f"{svc.horizon_minutes:g}"
        ax_t, ax_r = fig.subplots(2, 1, sharex=True, gridspec_kw={"height_ratios": [1, 1.25]})
        fig.subplots_adjust(left=0.14, right=0.98, top=0.92, bottom=0.11, hspace=0.42)
        for ax in (ax_t, ax_r):
            style_axes(ax, c)
        has_now = "y_now" in df and df["y_now"].notna().any()
        has_next = "true_tier_next" in df and df["true_tier_next"].notna().any()
        first = True
        for seg in self._segments(df):
            s = df.iloc[seg]
            lone = len(s) == 1
            if has_now:
                ax_t.step(s["t"], s["y_now"], where="post", color=c["truth"], linewidth=7, alpha=0.3,
                          marker="s" if lone else None, markersize=7, solid_capstyle="butt",
                          label="True tier (now)" if first else None)
            if has_next:
                ax_t.step(s["t"], s["true_tier_next"], where="post", color=c["truth"], linewidth=1.5,
                          linestyle=(0, (1, 2)), label=f"True highest tier (next {hm} min)" if first else None)
            ax_t.step(s["t"], s["det_tier"], where="post", color=c["p_any"], linewidth=2,
                      marker="o" if lone else None, markersize=4, label="Hybrid detected tier (now)" if first else None)
            first = False
        if not (has_now or has_next):
            ax_t.text(0.01, 0.95, "no true-tier columns in this feed", transform=ax_t.transAxes, va="top",
                      fontsize=7, color=c["muted"])
        ax_t.set_ylim(-0.4, len(TIER_NAMES) - 0.6)
        ax_t.set_yticks(range(len(TIER_NAMES)))
        ax_t.set_yticklabels(TIER_NAMES, fontsize=7)
        ax_t.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=3, fontsize=7, frameon=False,
                    labelcolor=c["text"], borderaxespad=0.2)

        logit = bool(self.logit.get())
        clip = (lambda v: np.clip(v, LOGIT_CLIP, 1 - LOGIT_CLIP)) if logit else (lambda v: v)
        first = True
        for seg in self._segments(df):
            s = df.iloc[seg]
            mk = "o" if len(s) < 40 else None
            ax_r.plot(s["t"], clip(s["p_attack_next"]), color=c["p_any"], linewidth=1.8, marker=mk, markersize=3,
                      label=f"P(any attack ≤{hm} min)" if first else None)
            ax_r.plot(s["t"], clip(s["p_severe_next"]), color=c["p_esc"], linewidth=1.8,
                      marker="s" if mk else None, markersize=3,
                      label=f"P(escalation ≤{hm} min)" if first else None)
            first = False
        for thr, name, x, ha in ((svc.threshold_attack, "WARNING if P(any) ≥", 0.995, "right"),
                                 (svc.threshold_severe, "HIGH if P(escalation) ≥", 0.005, "left")):
            ax_r.axhline(clip(thr), color=c["muted"], linestyle="--", linewidth=1)
            ax_r.annotate(f"{name} {thr:.4f}", xy=(x, clip(thr)), xycoords=("axes fraction", "data"),
                          xytext=(0, 2), textcoords="offset points", ha=ha, va="bottom", fontsize=7, color=c["muted"])
        if logit:
            ax_r.set_yscale("logit")
        else:
            ax_r.set_ylim(-0.03, 1.1)
        ax_r.set_ylabel(f"predicted risk (next {hm} min)", fontsize=8)
        ax_r.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, fontsize=7, frameon=False,
                    labelcolor=c["text"], borderaxespad=0.2)
        loc = mdates.AutoDateLocator(maxticks=8)
        ax_r.xaxis.set_major_locator(loc)
        ax_r.xaxis.set_major_formatter(mdates.ConciseDateFormatter(loc))
        ax_r.xaxis.get_offset_text().set_color(c["muted"])
        ax_r.set_xlabel("recorded window start (UTC)", fontsize=8)

    def _hover(self, event) -> None:
        df = self._df
        if event.inaxes is None or event.xdata is None or df is None or df.empty:
            return
        t = pd.Timestamp(mdates.num2date(event.xdata).replace(tzinfo=None))
        i = int(np.argmin(np.abs((df["t"] - t).dt.total_seconds().to_numpy())))
        r = df.iloc[i]
        hm = f"{self.svc.horizon_minutes:g}"
        true_now = tier_name(r["y_now"]) if "y_now" in r and pd.notna(r["y_now"]) else "n/a"
        reason = r["alert_reason"] if isinstance(r.get("alert_reason"), str) else ""
        self.readout.configure(text_color=T.TEXT, text=(
            f"{pretty_utc(r['window_start_utc'])}   true {true_now} · detected {tier_name(r['det_tier'])} · "
            f"forecast {tier_name(r['fut_tier'])} · P(any ≤{hm} min) {r['p_attack_next']:.4f} · "
            f"P(escalation ≤{hm} min) {r['p_severe_next']:.4f} · {r['alert']} {reason}"))

    # ------------------------------------------------------------------ table
    def _render_table(self, df: pd.DataFrame) -> None:
        for w in self.table_holder.winfo_children():
            w.destroy()
        if df.empty:
            return
        cols = [c for c in TABLE_COLUMNS if c in df.columns]
        shown = df.head(TABLE_MAX_ROWS)
        note = f"Feed rows for this selection ({len(df)} windows" + \
               (f"; first {TABLE_MAX_ROWS} shown)" if len(df) > TABLE_MAX_ROWS else ")")
        label(self.table_holder, note, "small_bold", T.MUTED).pack(anchor="w", pady=(0, 6))
        rows = [[(pretty_utc(v) if c == "window_start_utc" else
                  (v if not isinstance(v, float) or not np.isnan(v) else None)) for c, v in zip(cols, rec)]
                for rec in shown[cols].itertuples(index=False)]
        Table(self.table_holder, cols, rows,
              numeric={"n_flows", "y_now", "true_tier_next", "det_tier", "fut_tier", "p_attack_next",
                       "p_severe_next"}).pack(fill="x")
