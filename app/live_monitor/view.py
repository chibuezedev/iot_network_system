from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from collections import deque

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from app.auth import db
from app.common import theme
from app.common.context import AppContext

MAX_TABLE_ROWS = 300


class LiveMonitorView(tk.Frame):
    def __init__(self, parent, ctx: AppContext, shell):
        super().__init__(parent, bg=theme.BG_PRIMARY)
        self.ctx = ctx
        self.shell = shell
        self._flow_window: deque = deque(maxlen=60)   # per-tick flow counts, ~30s at 500ms/tick
        self._attack_window: deque = deque(maxlen=60)
        self._tick_flow_count = 0
        self._tick_attack_count = 0
        self._build()
        self.ctx.result_listeners.append(self._on_result)
        self._refresh_chart()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        pad = tk.Frame(self, bg=theme.BG_PRIMARY, padx=24, pady=18)
        pad.pack(fill="both", expand=True)

        header = tk.Frame(pad, bg=theme.BG_PRIMARY)
        header.pack(fill="x")
        tk.Label(header, text="Live Monitor", bg=theme.BG_PRIMARY, fg=theme.TEXT_PRIMARY,
                 font=(theme.FONT_HEADER[0], 18, "bold")).pack(side="left")

        controls = tk.Frame(pad, bg=theme.BG_CARD, highlightbackground=theme.BORDER, highlightthickness=1)
        controls.pack(fill="x", pady=(12, 12))
        inner = tk.Frame(controls, bg=theme.BG_CARD, padx=14, pady=10)
        inner.pack(fill="x")

        self.start_btn = self._make_button(inner, "\u25b6 Start", self._start, theme.ACCENT_GREEN)
        self.start_btn.pack(side="left")
        self.pause_btn = self._make_button(inner, "\u23f8 Pause", self._pause, theme.ACCENT_AMBER)
        self.pause_btn.pack(side="left", padx=8)
        self.stop_btn = self._make_button(inner, "\u23f9 Stop", self._stop, theme.TEXT_MUTED)
        self.stop_btn.pack(side="left")

        tk.Label(inner, text="Speed", bg=theme.BG_CARD, fg=theme.TEXT_MUTED,
                 font=theme.FONT_LABEL).pack(side="left", padx=(24, 8))
        self.speed_var = tk.DoubleVar(value=5.0)
        speed_scale = tk.Scale(
            inner, from_=1, to=20, orient="horizontal", variable=self.speed_var, showvalue=True,
            bg=theme.BG_CARD, fg=theme.TEXT_PRIMARY, highlightthickness=0, troughcolor=theme.BG_SECONDARY,
            command=self._on_speed_change, length=140,
        )
        speed_scale.pack(side="left")
        tk.Label(inner, text="x", bg=theme.BG_CARD, fg=theme.TEXT_MUTED, font=theme.FONT_LABEL).pack(side="left")

        burst_btn = self._make_button(inner, "\u26a1 Inject Attack Burst", self._inject_burst, theme.ACCENT_RED)
        burst_btn.pack(side="right")

        # Table
        table_card = tk.Frame(pad, bg=theme.BG_CARD, highlightbackground=theme.BORDER, highlightthickness=1)
        table_card.pack(fill="both", expand=True)

        style = ttk.Style()
        style.configure("Live.Treeview", background=theme.BG_CARD, fieldbackground=theme.BG_CARD,
                         foreground=theme.TEXT_PRIMARY, rowheight=24, font=theme.FONT_MONO_SMALL)
        style.configure("Live.Treeview.Heading", background=theme.BG_SECONDARY, foreground=theme.TEXT_MUTED,
                         font=(theme.FONT_LABEL[0], 9, "bold"))
        style.map("Live.Treeview", background=[("selected", theme.BORDER)])

        columns = ("time", "src", "dst_device", "protocol", "label", "det_conf", "severity", "sev_conf")
        self.tree = ttk.Treeview(table_card, columns=columns, show="headings", style="Live.Treeview", height=14)
        headers = {"time": "Sim Time", "src": "Source", "dst_device": "Device", "protocol": "Proto",
                   "label": "Spotter Verdict", "det_conf": "Conf.", "severity": "Risk Tier", "sev_conf": "Conf."}
        widths = {"time": 100, "src": 130, "dst_device": 170, "protocol": 60, "label": 180,
                  "det_conf": 60, "severity": 160, "sev_conf": 60}
        for col in columns:
            self.tree.heading(col, text=headers[col])
            self.tree.column(col, width=widths[col], anchor="w")
        self.tree.pack(fill="both", expand=True, side="left", padx=(1, 0), pady=1)
        scroll = ttk.Scrollbar(table_card, orient="vertical", command=self.tree.yview)
        scroll.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scroll.set)

        for tier, color in theme.SEVERITY_COLORS.items():
            self.tree.tag_configure(f"tier{tier}", foreground=color)

        # Chart
        chart_card = tk.Frame(pad, bg=theme.BG_CARD, highlightbackground=theme.BORDER, highlightthickness=1)
        chart_card.pack(fill="x", pady=(12, 0))
        tk.Label(chart_card, text="Flow Rate vs Attack Rate", bg=theme.BG_CARD, fg=theme.TEXT_PRIMARY,
                 font=theme.FONT_HEADER).pack(anchor="w", padx=16, pady=(10, 0))
        self.fig = plt.Figure(figsize=(9, 1.8), dpi=100, facecolor=theme.BG_CARD)
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, master=chart_card)
        self.canvas.get_tk_widget().pack(fill="x", padx=10, pady=10)

    def _make_button(self, parent, text, command, accent) -> tk.Button:
        return tk.Button(
            parent, text=text, command=command, bg=theme.BG_SECONDARY, fg=accent,
            activebackground=theme.BORDER, relief="flat", font=(theme.FONT_LABEL[0], 9, "bold"),
            cursor="hand2", padx=10, pady=4,
        )

    # ------------------------------------------------------------------
    def _start(self) -> None:
        if self.ctx.session_id is None:
            self.ctx.session_id = db.start_session(self.ctx.username)
        self.ctx.engine.set_speed(self.speed_var.get())
        self.ctx.engine.start()
        self.shell.set_live_status(True)

    def _pause(self) -> None:
        self.ctx.engine.pause()
        self.shell.set_live_status(False)

    def _stop(self) -> None:
        self.ctx.engine.stop()
        self.shell.set_live_status(False)
        if self.ctx.session_id is not None:
            c = self.ctx.counters
            db.end_session(self.ctx.session_id, c.total_flows, c.total_attacks, c.highest_severity_tier)
            self.ctx.session_id = None

    def _inject_burst(self) -> None:
        self.ctx.engine.inject_attack_burst(30)

    def _on_speed_change(self, value) -> None:
        self.ctx.engine.set_speed(float(value))

    # ------------------------------------------------------------------
    def _on_result(self, result) -> None:
        if not self.winfo_exists():
            return
        tier = result.severity_tier
        self.tree.insert(
            "", 0,
            values=(result.sim_time, result.src_ip, f"{result.device_name} ({result.device_ip})",
                    result.protocol, result.predicted_label, f"{result.detection_confidence:.0%}",
                    # theme.SEVERITY_LABELS[tier], f"{result.severity_confidence:.0%}"
                ),
            tags=(f"tier{tier}",),
        )
        children = self.tree.get_children()
        if len(children) > MAX_TABLE_ROWS:
            for extra in children[MAX_TABLE_ROWS:]:
                self.tree.delete(extra)

        self._tick_flow_count += 1
        if result.is_attack:
            self._tick_attack_count += 1

    def _refresh_chart(self) -> None:
        if not self.winfo_exists():
            return
        self._flow_window.append(self._tick_flow_count)
        self._attack_window.append(self._tick_attack_count)
        self._tick_flow_count = 0
        self._tick_attack_count = 0

        self.ax.clear()
        self.ax.plot(list(self._flow_window), color=theme.ACCENT_CYAN, linewidth=1.6, label="Flow rate")
        self.ax.plot(list(self._attack_window), color=theme.ACCENT_RED, linewidth=1.6, label="Attack rate")
        self.ax.set_facecolor(theme.BG_CARD)
        self.ax.tick_params(colors=theme.TEXT_MUTED, labelsize=7)
        for spine in self.ax.spines.values():
            spine.set_color(theme.BORDER)
        self.ax.legend(loc="upper left", fontsize=7, facecolor=theme.BG_CARD, edgecolor=theme.BORDER,
                        labelcolor=theme.TEXT_PRIMARY)
        self.canvas.draw_idle()
        self.after(500, self._refresh_chart)
