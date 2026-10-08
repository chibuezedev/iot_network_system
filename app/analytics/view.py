from __future__ import annotations

import datetime
import tkinter as tk
from tkinter import filedialog, ttk

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from app.auth import db
from app.common import theme
from app.common.context import AppContext
from app.common.widgets import StatCard, show_toast

# How often the page refreshes its all-time charts/table while it's the
# visible screen. Cheap enough to poll (a couple of small SQLite reads),
# unlike redrawing on every single simulated row.
ALLTIME_REFRESH_MS = 4000

# How many past sessions/events to pull for all-time aggregation. Plenty
# for a demo app; not meant to scale to a real production event volume.
HISTORY_LIMIT = 500


class AnalyticsView(tk.Frame):
    def __init__(self, parent, ctx: AppContext):
        super().__init__(parent, bg=theme.BG_PRIMARY)
        self.ctx = ctx
        self._refresh_job = None
        self._build()
        self.ctx.result_listeners.append(self._on_live_result)

    def on_show(self) -> None:
        self._refresh_all()
        self._schedule_refresh()

    def _schedule_refresh(self) -> None:
        if self._refresh_job is not None:
            self.after_cancel(self._refresh_job)
        self._refresh_job = self.after(ALLTIME_REFRESH_MS, self._periodic_refresh)

    def _periodic_refresh(self) -> None:
        if not self.winfo_exists():
            return
        self._refresh_all()
        self._schedule_refresh()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        pad = tk.Frame(self, bg=theme.BG_PRIMARY, padx=24, pady=18)
        pad.pack(fill="both", expand=True)

        header = tk.Frame(pad, bg=theme.BG_PRIMARY)
        header.pack(fill="x")
        tk.Label(
            header,
            text="Analytics & Reports",
            bg=theme.BG_PRIMARY,
            fg=theme.TEXT_PRIMARY,
            font=(theme.FONT_HEADER[0], 18, "bold"),
        ).pack(side="left")
        tk.Label(
            header,
            text="Reflects every session ever logged to disk, updates automatically",
            bg=theme.BG_PRIMARY,
            fg=theme.TEXT_MUTED,
            font=theme.FONT_LABEL,
        ).pack(side="left", padx=(12, 0))
        tk.Button(
            header,
            text="Generate Session Report",
            command=self._generate_report,
            bg=theme.BG_SECONDARY,
            fg=theme.ACCENT_CYAN,
            relief="flat",
            font=(theme.FONT_LABEL[0], 9, "bold"),
            cursor="hand2",
            padx=10,
        ).pack(side="right")

        # -- All-time overview strip -----------------------------------
        overview = tk.Frame(pad, bg=theme.BG_PRIMARY)
        overview.pack(fill="x", pady=(14, 0))
        for i in range(4):
            overview.columnconfigure(i, weight=1)

        self.card_sessions = StatCard(
            overview, "Total Sessions", accent=theme.ACCENT_CYAN
        )
        self.card_sessions.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.card_flows = StatCard(
            overview, "Flows Analyzed (All-Time)", accent=theme.ACCENT_CYAN
        )
        self.card_flows.grid(row=0, column=1, sticky="ew", padx=8)
        self.card_attacks = StatCard(
            overview, "Attacks Detected (All-Time)", accent=theme.ACCENT_AMBER
        )
        self.card_attacks.grid(row=0, column=2, sticky="ew", padx=8)
        self.card_max_sev = StatCard(
            overview, "Highest Severity Ever", suffix="", accent=theme.ACCENT_RED
        )
        self.card_max_sev.grid(row=0, column=3, sticky="ew", padx=(8, 0))

        # -- Live current-session strip (only meaningful while running) --
        live_strip = tk.Frame(
            pad,
            bg=theme.BG_CARD,
            highlightbackground=theme.BORDER,
            highlightthickness=1,
        )
        live_strip.pack(fill="x", pady=(12, 0))
        li = tk.Frame(live_strip, bg=theme.BG_CARD, padx=14, pady=8)
        li.pack(fill="x")
        tk.Label(
            li,
            text="CURRENT SESSION",
            bg=theme.BG_CARD,
            fg=theme.TEXT_MUTED,
            font=(theme.FONT_LABEL[0], 8, "bold"),
        ).pack(side="left")
        self.live_label = tk.Label(
            li,
            text="No active session. Start Live Monitor to begin one.",
            bg=theme.BG_CARD,
            fg=theme.TEXT_PRIMARY,
            font=theme.FONT_MONO_SMALL,
        )
        self.live_label.pack(side="left", padx=(14, 0))

        # -- Charts --------------------------------------------------------
        charts_row = tk.Frame(pad, bg=theme.BG_PRIMARY)
        charts_row.pack(fill="both", expand=True, pady=(16, 0))
        charts_row.columnconfigure(0, weight=1)
        charts_row.columnconfigure(1, weight=1)
        charts_row.rowconfigure(0, weight=1)

        left = tk.Frame(
            charts_row,
            bg=theme.BG_CARD,
            highlightbackground=theme.BORDER,
            highlightthickness=1,
        )
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        tk.Label(
            left,
            text="Attack Type Distribution (All-Time)",
            bg=theme.BG_CARD,
            fg=theme.TEXT_PRIMARY,
            font=theme.FONT_HEADER,
        ).pack(anchor="w", padx=14, pady=(12, 0))
        self.attack_fig = plt.Figure(figsize=(4.4, 3), dpi=100, facecolor=theme.BG_CARD)
        self.attack_ax = self.attack_fig.add_subplot(111)
        self.attack_canvas = FigureCanvasTkAgg(self.attack_fig, master=left)
        self.attack_canvas.get_tk_widget().pack(
            fill="both", expand=True, padx=10, pady=10
        )

        right = tk.Frame(
            charts_row,
            bg=theme.BG_CARD,
            highlightbackground=theme.BORDER,
            highlightthickness=1,
        )
        right.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        tk.Label(
            right,
            text="Severity Tier Breakdown (All-Time, Flagged Events)",
            bg=theme.BG_CARD,
            fg=theme.TEXT_PRIMARY,
            font=theme.FONT_HEADER,
        ).pack(anchor="w", padx=14, pady=(12, 0))
        self.sev_fig = plt.Figure(figsize=(4.4, 3), dpi=100, facecolor=theme.BG_CARD)
        self.sev_ax = self.sev_fig.add_subplot(111)
        self.sev_canvas = FigureCanvasTkAgg(self.sev_fig, master=right)
        self.sev_canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=10)

        # -- Extra: average confidence + most active device -------------
        extra_row = tk.Frame(
            pad,
            bg=theme.BG_CARD,
            highlightbackground=theme.BORDER,
            highlightthickness=1,
        )
        extra_row.pack(fill="x", pady=(16, 0))
        ei = tk.Frame(extra_row, bg=theme.BG_CARD, padx=14, pady=10)
        ei.pack(fill="x")
        self.avg_conf_label = tk.Label(
            ei,
            text="Avg. detection confidence on flagged events: --",
            bg=theme.BG_CARD,
            fg=theme.TEXT_PRIMARY,
            font=theme.FONT_LABEL,
        )
        self.avg_conf_label.pack(side="left")
        self.top_device_label = tk.Label(
            ei,
            text="Most flagged device: --",
            bg=theme.BG_CARD,
            fg=theme.TEXT_PRIMARY,
            font=theme.FONT_LABEL,
        )
        self.top_device_label.pack(side="left", padx=(28, 0))

        # -- Session history table ---------------------------------------
        hist_card = tk.Frame(
            pad,
            bg=theme.BG_CARD,
            highlightbackground=theme.BORDER,
            highlightthickness=1,
        )
        hist_card.pack(fill="both", expand=True, pady=(16, 0))
        tk.Label(
            hist_card,
            text="Session History (all demo runs, from disk)",
            bg=theme.BG_CARD,
            fg=theme.TEXT_PRIMARY,
            font=theme.FONT_HEADER,
        ).pack(anchor="w", padx=14, pady=(12, 6))

        style = ttk.Style()
        style.configure(
            "Hist.Treeview",
            background=theme.BG_CARD,
            fieldbackground=theme.BG_CARD,
            foreground=theme.TEXT_PRIMARY,
            rowheight=22,
            font=theme.FONT_MONO_SMALL,
        )
        columns = ("started", "user", "flows", "attacks", "max_sev")
        self.hist_tree = ttk.Treeview(
            hist_card, columns=columns, show="headings", style="Hist.Treeview", height=6
        )
        for col, label in zip(
            columns, ["Started", "User", "Flows", "Attacks", "Max Severity"]
        ):
            self.hist_tree.heading(col, text=label)
            self.hist_tree.column(col, width=150, anchor="w")
        self.hist_tree.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def _on_live_result(self, result) -> None:
        if not self.winfo_exists():
            return
        c = self.ctx.counters
        self.live_label.config(
            text=f"{c.total_flows:,} flows  |  {c.total_attacks:,} attacks  |  "
            f"{c.active_alerts:,} active alerts  |  highest severity: "
            f"{theme.SEVERITY_LABELS.get(c.highest_severity_tier, c.highest_severity_tier)}"
        )

    def _refresh_all(self) -> None:
        sessions = db.fetch_sessions(limit=HISTORY_LIMIT)
        events = db.fetch_events(only_flagged=True, limit=HISTORY_LIMIT)

        total_sessions = len(sessions)
        total_flows_alltime = sum(s["total_flows"] or 0 for s in sessions)
        total_attacks_alltime = sum(s["total_attacks"] or 0 for s in sessions)
        highest_sev_alltime = max(
            (s["highest_severity_tier"] or 0 for s in sessions), default=0
        )

        self.card_sessions.set_value(total_sessions)
        self.card_flows.set_value(total_flows_alltime)
        self.card_attacks.set_value(total_attacks_alltime)
        self.card_max_sev.value_label.config(
            text=theme.SEVERITY_LABELS.get(
                highest_sev_alltime, str(highest_sev_alltime)
            )
        )

        # -- Attack type distribution, from flagged events across all sessions --
        attack_counts: dict[str, int] = {}
        sev_counts = {t: 0 for t in range(5)}
        conf_values = []
        device_counts: dict[str, int] = {}
        for e in events:
            label = e["predicted_label"]
            if label and label != "BenignTraffic":
                attack_counts[label] = attack_counts.get(label, 0) + 1
            tier = e["severity_tier"] or 0
            sev_counts[tier] = sev_counts.get(tier, 0) + 1
            if e["detection_confidence"] is not None:
                conf_values.append(e["detection_confidence"])
            device = e["device_name"]
            if device:
                device_counts[device] = device_counts.get(device, 0) + 1

        self.attack_ax.clear()
        if attack_counts:
            items = sorted(attack_counts.items(), key=lambda kv: kv[1], reverse=True)[
                :8
            ]
            labels = [k for k, _ in items]
            values = [v for _, v in items]
            self.attack_ax.barh(labels, values, color=theme.ACCENT_AMBER)
            self.attack_ax.invert_yaxis()
        else:
            self.attack_ax.text(
                0.5,
                0.5,
                "No flagged attacks logged yet",
                ha="center",
                va="center",
                color=theme.TEXT_MUTED,
                fontsize=9,
                transform=self.attack_ax.transAxes,
            )
        self.attack_ax.set_facecolor(theme.BG_CARD)
        self.attack_ax.tick_params(colors=theme.TEXT_MUTED, labelsize=7)
        for spine in self.attack_ax.spines.values():
            spine.set_color(theme.BORDER)
        self.attack_canvas.draw_idle()

        self.sev_ax.clear()
        tiers = list(range(5))
        counts = [sev_counts.get(t, 0) for t in tiers]
        if any(counts):
            colors = [theme.SEVERITY_COLORS[t] for t in tiers]
            self.sev_ax.bar(
                [theme.SEVERITY_LABELS[t] for t in tiers], counts, color=colors
            )
        else:
            self.sev_ax.text(
                0.5,
                0.5,
                "No flagged events logged yet",
                ha="center",
                va="center",
                color=theme.TEXT_MUTED,
                fontsize=9,
                transform=self.sev_ax.transAxes,
            )
        self.sev_ax.set_facecolor(theme.BG_CARD)
        self.sev_ax.tick_params(colors=theme.TEXT_MUTED, labelsize=6, rotation=20)
        for spine in self.sev_ax.spines.values():
            spine.set_color(theme.BORDER)
        self.sev_canvas.draw_idle()

        if conf_values:
            avg_conf = sum(conf_values) / len(conf_values)
            self.avg_conf_label.config(
                text=f"Avg. detection confidence on flagged events: {avg_conf:.0%}"
            )
        else:
            self.avg_conf_label.config(
                text="Avg. detection confidence on flagged events: --"
            )

        if device_counts:
            top_device = max(device_counts.items(), key=lambda kv: kv[1])
            self.top_device_label.config(
                text=f"Most flagged device: {top_device[0]} ({top_device[1]} events)"
            )
        else:
            self.top_device_label.config(text="Most flagged device: --")

        self.hist_tree.delete(*self.hist_tree.get_children())
        for row in sessions[:50]:
            self.hist_tree.insert(
                "",
                "end",
                values=(
                    row["started_at"],
                    row["username"],
                    row["total_flows"],
                    row["total_attacks"],
                    theme.SEVERITY_LABELS.get(
                        row["highest_severity_tier"], row["highest_severity_tier"]
                    ),
                ),
            )

    # ------------------------------------------------------------------
    def _generate_report(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".html", filetypes=[("HTML report", "*.html")]
        )
        if not path:
            return
        c = self.ctx.counters
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        attack_rows = (
            "".join(
                f"<tr><td>{k}</td><td>{v}</td></tr>"
                for k, v in sorted(
                    c.attack_type_counts.items(), key=lambda kv: kv[1], reverse=True
                )
            )
            or "<tr><td colspan='2'>No attacks observed this session</td></tr>"
        )
        severity_rows = "".join(
            f"<tr><td>{theme.SEVERITY_LABELS[t]}</td><td>{c.severity_tier_counts.get(t, 0)}</td></tr>"
            for t in range(5)
        )
        html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>SentinelIoT Session Report</title>
<style>
body {{ font-family: -apple-system, Segoe UI, sans-serif; background:#0b0f14; color:#e6edf3; padding:32px; }}
h1 {{ color:#22d3ee; }} table {{ border-collapse: collapse; width:100%; margin-bottom: 24px; }}
td, th {{ border: 1px solid #232c3a; padding: 6px 10px; text-align:left; }}
th {{ background:#121821; }}
</style></head><body>
<h1>SentinelIoT -- Session Report</h1>
<p>Generated {now} by {self.ctx.username} ({self.ctx.role})</p>
<h2>Current Session Summary</h2>
<table>
<tr><th>Total Flows Analyzed</th><td>{c.total_flows}</td></tr>
<tr><th>Total Attacks Detected</th><td>{c.total_attacks}</td></tr>
<tr><th>Active Alerts</th><td>{c.active_alerts}</td></tr>
<tr><th>Highest Severity Tier Seen</th><td>{theme.SEVERITY_LABELS.get(c.highest_severity_tier)}</td></tr>
</table>
<h2>Attack Type Distribution (This Session)</h2>
<table><tr><th>Attack Type</th><th>Count</th></tr>{attack_rows}</table>
<h2>Severity Tier Breakdown (This Session)</h2>
<table><tr><th>Tier</th><th>Count</th></tr>{severity_rows}</table>
<p style="color:#8b98a9;font-size:12px">Note: figures reflect the current in-app simulation session using the
loaded model_artifacts, not a live network capture. See the Analytics screen's All-Time charts for
cumulative history across every session on this machine.</p>
</body></html>"""
        with open(path, "w") as f:
            f.write(html)
        show_toast(
            self.winfo_toplevel(),
            "Report generated",
            f"Session report saved to {path}",
            "success",
        )
