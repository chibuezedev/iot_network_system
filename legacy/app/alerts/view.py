from __future__ import annotations

import csv
import json
import tkinter as tk
from tkinter import ttk, filedialog

from app.auth import db
from app.common import theme
from app.common.context import AppContext
from app.common.widgets import AlertBadge, HybridAlertRow, ScrollFrame, show_toast
from services.hybrid_service import TIER_NAMES

HYBRID_ALERT_LIMIT = 500


class AlertsView(tk.Frame):
    def __init__(self, parent, ctx: AppContext):
        super().__init__(parent, bg=theme.BG_PRIMARY)
        self.ctx = ctx
        self._rows_cache: list = []
        self._build()

    def on_show(self) -> None:
        self._reload()
        self._reload_hybrid()

    # ---------------------------------------------------------------- hybrid
    def _build_hybrid(self, tab) -> None:
        tk.Label(tab, text="Alerts from the RF–LSTM engine (alert_level / alert_reason). One alert per host per "
                           "level until that host's level changes. Times are recorded window starts (UTC).",
                 bg=theme.BG_PRIMARY, fg=theme.TEXT_MUTED, font=theme.FONT_LABEL, justify="left",
                 wraplength=1000).pack(anchor="w")
        legend = tk.Frame(tab, bg=theme.BG_PRIMARY)
        legend.pack(anchor="w", pady=(6, 8))
        for i, (kind, text) in enumerate((
                ("Detected", "filled = Detected: the current window is classified as an attack tier"),
                ("Predicted", "outlined = Predicted: forecast for the horizon ahead, not yet observed"))):
            AlertBadge(legend, "HIGH", kind, bg=theme.BG_PRIMARY).grid(row=i, column=0, sticky="w", pady=2)
            tk.Label(legend, text=text, bg=theme.BG_PRIMARY, fg=theme.TEXT_MUTED,
                     font=(theme.FONT_LABEL[0], 9)).grid(row=i, column=1, sticky="w", padx=(8, 0))

        filters = tk.Frame(tab, bg=theme.BG_CARD, highlightbackground=theme.BORDER, highlightthickness=1)
        filters.pack(fill="x", pady=(0, 8))
        f = tk.Frame(filters, bg=theme.BG_CARD, padx=12, pady=8)
        f.pack(fill="x")
        tk.Label(f, text="Level", bg=theme.BG_CARD, fg=theme.TEXT_MUTED, font=theme.FONT_LABEL).pack(side="left")
        self.h_level_var = tk.StringVar(value="All")
        ttk.Combobox(f, textvariable=self.h_level_var, values=["All"] + theme.ALERT_LEVEL_ORDER[:-1], width=11,
                     state="readonly").pack(side="left", padx=(6, 18))
        tk.Label(f, text="Type", bg=theme.BG_CARD, fg=theme.TEXT_MUTED, font=theme.FONT_LABEL).pack(side="left")
        self.h_kind_var = tk.StringVar(value="All")
        ttk.Combobox(f, textvariable=self.h_kind_var, values=["All", "Detected", "Predicted"], width=11,
                     state="readonly").pack(side="left", padx=(6, 18))
        self.h_all_runs = tk.BooleanVar(value=False)
        tk.Checkbutton(f, text="All replay runs", variable=self.h_all_runs, bg=theme.BG_CARD, fg=theme.TEXT_PRIMARY,
                       selectcolor=theme.BG_SECONDARY, activebackground=theme.BG_CARD,
                       font=theme.FONT_LABEL).pack(side="left")
        tk.Button(f, text="Apply Filters", command=self._reload_hybrid, bg=theme.BG_SECONDARY, fg=theme.ACCENT_CYAN,
                  relief="flat", font=(theme.FONT_LABEL[0], 9, "bold"), cursor="hand2", padx=10).pack(side="left",
                                                                                                    padx=12)
        tk.Button(f, text="Export CSV", command=self._export_hybrid_csv, bg=theme.BG_SECONDARY,
                  fg=theme.ACCENT_GREEN, relief="flat", font=(theme.FONT_LABEL[0], 9, "bold"), cursor="hand2",
                  padx=10).pack(side="right")
        self.h_count = tk.Label(filters, text="", bg=theme.BG_CARD, fg=theme.TEXT_MUTED, font=theme.FONT_MONO_SMALL)
        self.h_count.pack(anchor="w", padx=12, pady=(0, 6))

        self.h_scroll = ScrollFrame(tab, bg=theme.BG_CARD)
        self.h_scroll.pack(fill="both", expand=True)
        self._hybrid_rows: list = []

    def _on_hybrid_step(self, step, new_alerts) -> None:
        if new_alerts and self.winfo_exists() and self.winfo_viewable():
            self._reload_hybrid()

    def _reload_hybrid(self) -> None:
        run_id = None if self.h_all_runs.get() else (self.ctx.hybrid_run_id or db.latest_hybrid_run_id())
        rows = [dict(r) for r in db.fetch_hybrid_alerts(run_id=run_id, limit=HYBRID_ALERT_LIMIT)]
        level, kind = self.h_level_var.get(), self.h_kind_var.get()
        rows = [r for r in rows if (level == "All" or r["level"] == level) and (kind == "All" or r["kind"] == kind)]
        self._hybrid_rows = rows
        n_pred = sum(1 for r in rows if r["kind"] == "Predicted")
        self.h_count.config(text=f"{len(rows)} shown · {len(rows) - n_pred} detected · {n_pred} predicted"
                                 + ("" if run_id is None else f" · run #{run_id}"))
        body = self.h_scroll.body
        for w in body.winfo_children():
            w.destroy()
        if not rows:
            msg = ("No RF–LSTM alerts match. Start the Hybrid Replay to generate alerts."
                   if level == "All" and kind == "All" else f"No {kind if kind != 'All' else ''} "
                   f"{level if level != 'All' else ''} alerts in the selected run(s).".replace("  ", " "))
            tk.Label(body, text=msg, bg=theme.BG_CARD, fg=theme.TEXT_MUTED, font=theme.FONT_LABEL).pack(
                anchor="w", padx=12, pady=12)
            return
        for r in rows:
            HybridAlertRow(body, r, TIER_NAMES).pack(fill="x", padx=12)
            tk.Frame(body, bg=theme.BORDER, height=1).pack(fill="x", padx=12)

    def _export_hybrid_csv(self) -> None:
        if not self._hybrid_rows:
            show_toast(self.winfo_toplevel(), "Nothing to export", "No hybrid alerts match the filters.", "warning")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        cols = ["run_id", *db.HYBRID_ALERT_FIELDS]
        with open(path, "w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(cols)
            for r in self._hybrid_rows:
                writer.writerow([r[c] for c in cols])
        show_toast(self.winfo_toplevel(), "Export complete", f"Hybrid alerts exported to {path}", "success")

    def _build(self) -> None:
        pad = tk.Frame(self, bg=theme.BG_PRIMARY, padx=24, pady=18)
        pad.pack(fill="both", expand=True)

        tk.Label(pad, text="Alerts", bg=theme.BG_PRIMARY, fg=theme.TEXT_PRIMARY,
                 font=(theme.FONT_HEADER[0], 18, "bold")).pack(anchor="w")
        tk.Label(pad, text="Every event that crossed the alert threshold, logged to disk across sessions",
                 bg=theme.BG_PRIMARY, fg=theme.TEXT_MUTED, font=theme.FONT_LABEL).pack(anchor="w", pady=(0, 12))

        notebook = ttk.Notebook(pad)
        notebook.pack(fill="both", expand=True)
        hybrid_tab = tk.Frame(notebook, bg=theme.BG_PRIMARY, padx=4, pady=10)
        legacy_tab = tk.Frame(notebook, bg=theme.BG_PRIMARY, padx=4, pady=10)
        notebook.add(hybrid_tab, text="  RF–LSTM hybrid (recorded ToN_IoT replay)  ")
        notebook.add(legacy_tab, text="  Legacy XGBoost demo (non-chronological sample)  ")
        self._build_hybrid(hybrid_tab)
        self.ctx.hybrid_listeners.append(self._on_hybrid_step)

        # ---- legacy XGBoost alerts (unchanged behaviour) ----
        pad = legacy_tab
        tk.Label(pad, text="Legacy XGBoost demo (non-chronological sample): times, source IPs and device names in "
                           "this table are generated by the demo feed, not recorded.",
                 bg=theme.BG_PRIMARY, fg=theme.ACCENT_AMBER, font=theme.FONT_LABEL).pack(anchor="w", pady=(0, 8))

        filters = tk.Frame(pad, bg=theme.BG_CARD, highlightbackground=theme.BORDER, highlightthickness=1)
        filters.pack(fill="x", pady=(0, 10))
        finner = tk.Frame(filters, bg=theme.BG_CARD, padx=12, pady=8)
        finner.pack(fill="x")

        tk.Label(finner, text="Severity", bg=theme.BG_CARD, fg=theme.TEXT_MUTED,
                 font=theme.FONT_LABEL).pack(side="left")
        self.severity_var = tk.StringVar(value="All")
        severity_options = ["All"] + list(theme.SEVERITY_LABELS.values())
        ttk.Combobox(finner, textvariable=self.severity_var, values=severity_options, width=20,
                     state="readonly").pack(side="left", padx=(6, 18))

        tk.Label(finner, text="Attack type contains", bg=theme.BG_CARD, fg=theme.TEXT_MUTED,
                 font=theme.FONT_LABEL).pack(side="left")
        self.type_var = tk.StringVar()
        tk.Entry(finner, textvariable=self.type_var, bg=theme.BG_SECONDARY, fg=theme.TEXT_PRIMARY,
                 insertbackground=theme.TEXT_PRIMARY, relief="flat", width=18).pack(side="left", padx=(6, 18))

        apply_btn = tk.Button(finner, text="Apply Filters", command=self._reload, bg=theme.BG_SECONDARY,
                               fg=theme.ACCENT_CYAN, relief="flat", font=(theme.FONT_LABEL[0], 9, "bold"),
                               cursor="hand2", padx=10)
        apply_btn.pack(side="left")

        export_btn = tk.Button(finner, text="Export CSV", command=self._export_csv, bg=theme.BG_SECONDARY,
                                fg=theme.ACCENT_GREEN, relief="flat", font=(theme.FONT_LABEL[0], 9, "bold"),
                                cursor="hand2", padx=10)
        export_btn.pack(side="right")

        table_card = tk.Frame(pad, bg=theme.BG_CARD, highlightbackground=theme.BORDER, highlightthickness=1)
        table_card.pack(fill="both", expand=True)

        style = ttk.Style()
        style.configure("Alerts.Treeview", background=theme.BG_CARD, fieldbackground=theme.BG_CARD,
                         foreground=theme.TEXT_PRIMARY, rowheight=24, font=theme.FONT_MONO_SMALL)
        style.configure("Alerts.Treeview.Heading", background=theme.BG_SECONDARY, foreground=theme.TEXT_MUTED,
                         font=(theme.FONT_LABEL[0], 9, "bold"))

        columns = ("time", "device", "label", "conf", "severity", "sev_conf", "ack")
        self.tree = ttk.Treeview(table_card, columns=columns, show="headings", style="Alerts.Treeview", height=16)
        headers = {"time": "Sim Time", "device": "Device", "label": "Predicted", "conf": "Det. Conf.",
                   "severity": "Severity", "sev_conf": "Sev. Conf.", "ack": "Ack'd"}
        for col in columns:
            self.tree.heading(col, text=headers[col], command=lambda c=col: self._sort_by(c))
            self.tree.column(col, width=140, anchor="w")
        self.tree.pack(fill="both", expand=True, side="left", pady=1)
        scroll = ttk.Scrollbar(table_card, orient="vertical", command=self.tree.yview)
        scroll.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<Double-1>", self._show_feature_vector)
        self.tree.bind("<Button-3>", self._acknowledge_selected)

        tk.Label(pad, text="Double-click a row to inspect its full feature vector. Right-click to acknowledge.",
                 bg=theme.BG_PRIMARY, fg=theme.TEXT_MUTED, font=(theme.FONT_LABEL[0], 8)).pack(anchor="w", pady=(6, 0))

        for tier, color in theme.SEVERITY_COLORS.items():
            self.tree.tag_configure(f"tier{tier}", foreground=color)

    def _reload(self) -> None:
        rows = db.fetch_events(only_flagged=True, limit=2000)
        sev_filter = self.severity_var.get()
        type_filter = self.type_var.get().strip().lower()

        self._rows_cache = []
        for row in rows:
            if sev_filter != "All" and theme.SEVERITY_LABELS.get(row["severity_tier"]) != sev_filter:
                continue
            if type_filter and type_filter not in (row["predicted_label"] or "").lower():
                continue
            self._rows_cache.append(row)

        self.tree.delete(*self.tree.get_children())
        for row in self._rows_cache:
            tier = row["severity_tier"]
            self.tree.insert(
                "", "end", iid=str(row["id"]),
                values=(row["sim_time"], row["device_name"], row["predicted_label"],
                        f"{row['detection_confidence']:.0%}", theme.SEVERITY_LABELS.get(tier, tier),
                        f"{row['severity_confidence']:.0%}", "Yes" if row["acknowledged"] else "No"),
                tags=(f"tier{tier}",),
            )

    def _sort_by(self, col: str) -> None:
        key_map = {"time": "sim_time", "device": "device_name", "label": "predicted_label",
                   "conf": "detection_confidence", "severity": "severity_tier",
                   "sev_conf": "severity_confidence", "ack": "acknowledged"}
        key = key_map.get(col, col)
        self._rows_cache.sort(key=lambda r: (r[key] is None, r[key]))
        self.tree.delete(*self.tree.get_children())
        for row in self._rows_cache:
            tier = row["severity_tier"]
            self.tree.insert(
                "", "end", iid=str(row["id"]),
                values=(row["sim_time"], row["device_name"], row["predicted_label"],
                        f"{row['detection_confidence']:.0%}", theme.SEVERITY_LABELS.get(tier, tier),
                        f"{row['severity_confidence']:.0%}", "Yes" if row["acknowledged"] else "No"),
                tags=(f"tier{tier}",),
            )

    def _acknowledge_selected(self, event) -> None:
        item = self.tree.identify_row(event.y)
        if not item:
            return
        db.acknowledge_event(int(item))
        self._reload()
        show_toast(self.winfo_toplevel(), "Alert acknowledged", f"Event #{item} marked as acknowledged.", "success")

    def _show_feature_vector(self, event) -> None:
        item = self.tree.identify_row(event.y)
        if not item:
            return
        match = next((r for r in self._rows_cache if str(r["id"]) == item), None)
        if match is None:
            return
        try:
            snapshot = json.loads(match["feature_snapshot"] or "{}")
        except json.JSONDecodeError:
            snapshot = {}

        win = tk.Toplevel(self)
        win.title(f"Feature vector -- alert #{item}")
        win.configure(bg=theme.BG_CARD)
        win.geometry("480x520")
        tk.Label(win, text=f"{match['predicted_label']} -- {theme.SEVERITY_LABELS.get(match['severity_tier'])}",
                 bg=theme.BG_CARD, fg=theme.ACCENT_CYAN, font=theme.FONT_HEADER).pack(anchor="w", padx=14, pady=(12, 0))
        text = tk.Text(win, bg=theme.BG_SECONDARY, fg=theme.TEXT_PRIMARY, font=theme.FONT_MONO_SMALL, relief="flat")
        text.pack(fill="both", expand=True, padx=14, pady=12)
        for k, v in snapshot.items():
            text.insert("end", f"{k:24s} {v}\n")
        text.config(state="disabled")

    def _export_csv(self) -> None:
        if not self._rows_cache:
            show_toast(self.winfo_toplevel(), "Nothing to export", "No alerts match the current filters.", "warning")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["sim_time", "device_name", "device_ip", "protocol", "predicted_label",
                              "detection_confidence", "severity_tier", "severity_label",
                              "severity_confidence", "acknowledged"])
            for row in self._rows_cache:
                writer.writerow([row["sim_time"], row["device_name"], row["device_ip"], row["protocol"],
                                  row["predicted_label"], row["detection_confidence"], row["severity_tier"],
                                  row["severity_label"], row["severity_confidence"], row["acknowledged"]])
        show_toast(self.winfo_toplevel(), "Export complete", f"Alerts exported to {path}", "success")
