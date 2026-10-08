from __future__ import annotations

import tkinter as tk
from collections import deque

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from app.auth import db
from app.common import theme
from app.common.context import AppContext
from app.common.widgets import StatCard

SPARK_WINDOW_TICKS = 40
ALLTIME_FOOTER_REFRESH_MS = 5000


class DashboardView(tk.Frame):
    def __init__(self, parent, ctx: AppContext):
        super().__init__(parent, bg=theme.BG_PRIMARY)
        self.ctx = ctx
        self._flow_ticks: deque = deque(maxlen=SPARK_WINDOW_TICKS)
        self._tick_flow_count = 0
        self._build()
        self.ctx.result_listeners.append(self._on_result)
        self._refresh_charts()
        self._refresh_alltime_footer()

    def on_show(self) -> None:
        self._refresh_all()
        self._refresh_alltime_footer()

    def _build(self) -> None:
        pad = tk.Frame(self, bg=theme.BG_PRIMARY, padx=24, pady=20)
        pad.pack(fill="both", expand=True)

        tk.Label(
            pad,
            text="Dashboard",
            bg=theme.BG_PRIMARY,
            fg=theme.TEXT_PRIMARY,
            font=(theme.FONT_HEADER[0], 18, "bold"),
        ).pack(anchor="w")
        tk.Label(
            pad,
            text="Session overview -- resets when a new monitoring session starts",
            bg=theme.BG_PRIMARY,
            fg=theme.TEXT_MUTED,
            font=theme.FONT_LABEL,
        ).pack(anchor="w", pady=(0, 16))

        cards_row = tk.Frame(pad, bg=theme.BG_PRIMARY)
        cards_row.pack(fill="x")
        for i in range(4):
            cards_row.columnconfigure(i, weight=1, uniform="cards")

        self.card_flows = StatCard(
            cards_row, "Total Flows Analyzed", 0, accent=theme.ACCENT_CYAN
        )
        self.card_flows.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.card_attacks = StatCard(
            cards_row, "Attacks Detected", 0, accent=theme.ACCENT_AMBER
        )
        self.card_attacks.grid(row=0, column=1, sticky="ew", padx=10)
        self.card_alerts = StatCard(
            cards_row, "Active Alerts", 0, accent=theme.ACCENT_RED
        )
        self.card_alerts.grid(row=0, column=2, sticky="ew", padx=10)
        self.card_severity = StatCard(
            cards_row, "Highest Severity Seen", accent=theme.ACCENT_DARKRED
        )
        self.card_severity.grid(row=0, column=3, sticky="ew", padx=(10, 0))
        self.card_severity.value_label.config(text=theme.SEVERITY_LABELS[0])

        mid = tk.Frame(pad, bg=theme.BG_PRIMARY)
        mid.pack(fill="both", expand=True, pady=(20, 0))
        mid.columnconfigure(0, weight=1)
        mid.columnconfigure(1, weight=1)
        mid.rowconfigure(0, weight=1)

        donut_card = tk.Frame(
            mid,
            bg=theme.BG_CARD,
            highlightbackground=theme.BORDER,
            highlightthickness=1,
        )
        donut_card.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        tk.Label(
            donut_card,
            text="Benign vs Attack",
            bg=theme.BG_CARD,
            fg=theme.TEXT_PRIMARY,
            font=theme.FONT_HEADER,
        ).pack(anchor="w", padx=16, pady=(14, 0))
        self.donut_fig = plt.Figure(
            figsize=(3.4, 2.8), dpi=100, facecolor=theme.BG_CARD
        )
        self.donut_ax = self.donut_fig.add_subplot(111)
        self.donut_canvas = FigureCanvasTkAgg(self.donut_fig, master=donut_card)
        self.donut_canvas.get_tk_widget().pack(
            fill="both", expand=True, padx=10, pady=10
        )

        right_col = tk.Frame(mid, bg=theme.BG_PRIMARY)
        right_col.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        right_col.rowconfigure(0, weight=1)
        right_col.rowconfigure(1, weight=1)
        right_col.columnconfigure(0, weight=1)

        top5_card = tk.Frame(
            right_col,
            bg=theme.BG_CARD,
            highlightbackground=theme.BORDER,
            highlightthickness=1,
        )
        top5_card.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        tk.Label(
            top5_card,
            text="Top 5 Attack Types This Session",
            bg=theme.BG_CARD,
            fg=theme.TEXT_PRIMARY,
            font=theme.FONT_HEADER,
        ).pack(anchor="w", padx=16, pady=(14, 6))
        self.top5_frame = tk.Frame(top5_card, bg=theme.BG_CARD)
        self.top5_frame.pack(fill="both", expand=True, padx=16, pady=(0, 14))

        spark_card = tk.Frame(
            right_col,
            bg=theme.BG_CARD,
            highlightbackground=theme.BORDER,
            highlightthickness=1,
        )
        spark_card.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        tk.Label(
            spark_card,
            text="Flow Volume (last ~20s, live)",
            bg=theme.BG_CARD,
            fg=theme.TEXT_PRIMARY,
            font=theme.FONT_HEADER,
        ).pack(anchor="w", padx=16, pady=(14, 0))
        self.spark_fig = plt.Figure(
            figsize=(3.4, 1.6), dpi=100, facecolor=theme.BG_CARD
        )
        self.spark_ax = self.spark_fig.add_subplot(111)
        self.spark_canvas = FigureCanvasTkAgg(self.spark_fig, master=spark_card)
        self.spark_canvas.get_tk_widget().pack(
            fill="both", expand=True, padx=10, pady=10
        )

        # -- All-time footer, so a fresh login doesn't look like a broken page --
        footer = tk.Frame(pad, bg=theme.BG_PRIMARY)
        footer.pack(fill="x", pady=(14, 0))
        self.footer_label = tk.Label(
            footer,
            text="Loading all-time totals...",
            bg=theme.BG_PRIMARY,
            fg=theme.TEXT_MUTED,
            font=(theme.FONT_LABEL[0], 8),
        )
        self.footer_label.pack(anchor="w")

    def _on_result(self, result) -> None:
        self._tick_flow_count += 1

    def _refresh_all(self) -> None:
        c = self.ctx.counters
        self.card_flows.set_value(c.total_flows)
        self.card_attacks.set_value(c.total_attacks)
        self.card_alerts.set_value(c.active_alerts)
        self.card_severity.value_label.config(
            text=theme.SEVERITY_LABELS.get(
                c.highest_severity_tier, str(c.highest_severity_tier)
            )
        )

        for w in self.top5_frame.winfo_children():
            w.destroy()
        top5 = sorted(c.attack_type_counts.items(), key=lambda kv: kv[1], reverse=True)[
            :5
        ]
        if not top5:
            tk.Label(
                self.top5_frame,
                text="No attacks observed yet this session.",
                bg=theme.BG_CARD,
                fg=theme.TEXT_MUTED,
                font=theme.FONT_LABEL,
            ).pack(anchor="w")
        for label, count in top5:
            row = tk.Frame(self.top5_frame, bg=theme.BG_CARD)
            row.pack(fill="x", pady=3)
            tk.Label(
                row,
                text=label,
                bg=theme.BG_CARD,
                fg=theme.TEXT_PRIMARY,
                font=theme.FONT_MONO_SMALL,
                anchor="w",
            ).pack(side="left", fill="x", expand=True)
            tk.Label(
                row,
                text=str(count),
                bg=theme.BG_CARD,
                fg=theme.ACCENT_AMBER,
                font=(theme.FONT_MONO_SMALL[0], 9, "bold"),
            ).pack(side="right")

    def _refresh_charts(self) -> None:
        if not self.winfo_exists():
            return
        self._refresh_all()
        c = self.ctx.counters

        self.donut_ax.clear()
        benign = max(c.total_flows - c.total_attacks, 0)
        attack = c.total_attacks
        values = [benign, attack] if (benign + attack) > 0 else [1, 0]
        colors = [theme.ACCENT_GREEN, theme.ACCENT_RED]
        self.donut_ax.pie(
            values,
            colors=colors,
            startangle=90,
            wedgeprops=dict(width=0.42, edgecolor=theme.BG_CARD),
        )
        self.donut_ax.set_facecolor(theme.BG_CARD)
        self.donut_ax.text(
            0,
            0,
            f"{c.total_flows}\nflows",
            ha="center",
            va="center",
            color=theme.TEXT_PRIMARY,
            fontsize=10,
        )
        self.donut_canvas.draw_idle()

        self._flow_ticks.append(self._tick_flow_count)
        self._tick_flow_count = 0

        self.spark_ax.clear()
        if any(self._flow_ticks):
            self.spark_ax.plot(
                list(self._flow_ticks), color=theme.ACCENT_CYAN, linewidth=2
            )
            self.spark_ax.fill_between(
                range(len(self._flow_ticks)),
                list(self._flow_ticks),
                color=theme.ACCENT_CYAN,
                alpha=0.15,
            )
        self.spark_ax.set_facecolor(theme.BG_CARD)
        self.spark_ax.axis("off")
        self.spark_canvas.draw_idle()

        self.after(500, self._refresh_charts)

    def _refresh_alltime_footer(self) -> None:
        if not self.winfo_exists():
            return
        sessions = db.fetch_sessions(limit=500)
        total_sessions = len(sessions)
        total_flows = sum(s["total_flows"] or 0 for s in sessions)
        self.footer_label.config(
            text=f"All-time on this machine: {total_sessions} session(s) run, "
            f"{total_flows:,} flows analyzed in total. See Analytics & Reports for the full breakdown."
        )
        self.after(ALLTIME_FOOTER_REFRESH_MS, self._refresh_alltime_footer)
