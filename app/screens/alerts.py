"""
Alerts -- RF-LSTM hybrid alerts only (hybrid_alerts table). Times are the
recorded window starts. Detected = filled badge, Predicted = outlined badge.
"""
from __future__ import annotations

import csv
from tkinter import filedialog

import customtkinter as ctk

from app.auth import db
from app.screens.base import Screen
from app.screens.live_replay import pretty_utc, tier_name
from app.ui import theme, tokens as T
from app.ui.widgets import Badge, Card, Drawer, button, label, show_toast

PAGE_SIZE = 60
ALL = "All"


class AlertsScreen(Screen):
    title = "Alerts"
    subtitle = ("RF–LSTM hybrid alerts: one per host per level change, from complete-lookback windows only. "
                "Times are recorded window starts (UTC).")

    def build(self) -> None:
        self.header()
        self._rows: list[dict] = []
        self._shown: list[dict] = []
        self._page = 0

        legend = ctk.CTkFrame(self.page, fg_color="transparent")
        self.section(legend, pady=(0, T.SPACE["m"]))
        for i, (kind, text) in enumerate((
                ("Detected", "filled — the current window is classified as an attack tier"),
                ("Predicted", "outlined — forecast for the horizon ahead, not yet observed"))):
            Badge(legend, "HIGH", kind, bg=T.BG).grid(row=i, column=0, sticky="w", pady=2)
            label(legend, text, "small", T.MUTED).grid(row=i, column=1, sticky="w", padx=(10, 0))

        f = Card(self.page, padding=T.SPACE["m"])
        self.section(f)
        b = f.body
        self.scope = self._combo(b, "Run", ["Latest run", "All runs"], 0, 0, 130)
        self.level = self._combo(b, "Level", [ALL, "CRITICAL", "HIGH", "WARNING"], 0, 1, 130)
        self.kind = self._combo(b, "Type", [ALL, "Detected", "Predicted"], 0, 2, 130)
        self.host = self._combo(b, "Host", [ALL], 0, 3, 170)
        self.t_from = self._combo(b, "From (recorded)", [ALL], 2, 0, 200, span=2)
        self.t_to = self._combo(b, "To (recorded)", [ALL], 2, 2, 200, span=2)
        button(b, "Export CSV", self._export, "secondary", width=110).grid(row=3, column=4, sticky="e")
        b.columnconfigure(4, weight=1)
        self.count = label(b, "", "small", T.MUTED)
        self.count.grid(row=4, column=0, columnspan=5, sticky="w", pady=(10, 0))

        self.list_card = Card(self.page, padding=T.SPACE["s"])
        self.section(self.list_card)
        nav = ctk.CTkFrame(self.page, fg_color="transparent")
        self.section(nav)
        self.prev_btn = button(nav, "← Newer", lambda: self._go(-1), "secondary", width=100)
        self.prev_btn.pack(side="left")
        self.page_label = label(nav, "", "small", T.MUTED)
        self.page_label.pack(side="left", padx=12)
        self.next_btn = button(nav, "Older →", lambda: self._go(1), "secondary", width=100)
        self.next_btn.pack(side="left")

        self.drawer = Drawer(self, width=420)
        self.ctx.step_listeners.append(self._on_step)

    def _combo(self, parent, caption: str, values, row: int, col: int, width: int, span: int = 1) -> ctk.CTkOptionMenu:
        label(parent, caption.upper(), "small_bold", T.MUTED).grid(row=row, column=col, columnspan=span, sticky="w",
                                                                   padx=(0, 12), pady=(8 if row else 0, 0))
        m = ctk.CTkOptionMenu(parent, values=values, width=width, command=lambda _v: self._apply(reset=True),
                              font=theme.font("small"), dropdown_font=theme.font("small"), fg_color=T.SURFACE_2,
                              button_color=T.SURFACE_2, button_hover_color=T.BORDER, text_color=T.TEXT,
                              dropdown_fg_color=T.SURFACE, dropdown_text_color=T.TEXT,
                              dropdown_hover_color=T.SURFACE_2)
        m.grid(row=row + 1, column=col, columnspan=span, sticky="w", padx=(0, 12))
        m.set(values[0])
        return m

    # ------------------------------------------------------------------ data
    def on_show(self) -> None:
        self._reload()

    def _on_step(self, step, new_alerts) -> None:
        if new_alerts and self.winfo_exists() and self.winfo_ismapped():
            self._reload()

    def _reload(self) -> None:
        run_id = None if self.scope.get() == "All runs" else (self.ctx.run_id or db.latest_hybrid_run_id())
        self._rows = [dict(r) for r in db.fetch_hybrid_alerts(run_id=run_id, limit=100000)] \
            if (run_id is not None or self.scope.get() == "All runs") else []
        hosts = sorted({r["host"] for r in self._rows})
        times = sorted({r["window_start_utc"] for r in self._rows})
        self._set_values(self.host, [ALL] + hosts)
        self._set_values(self.t_from, [ALL] + [pretty_utc(t) for t in times])
        self._set_values(self.t_to, [ALL] + [pretty_utc(t) for t in reversed(times)])
        self._run_id = run_id
        self._apply(reset=True)

    @staticmethod
    def _set_values(menu, values) -> None:
        cur = menu.get()
        menu.configure(values=values)
        if cur not in values:
            menu.set(values[0])

    def _apply(self, reset: bool = False) -> None:
        if reset:
            self._page = 0
        lvl, kind, host = self.level.get(), self.kind.get(), self.host.get()
        lo = None if self.t_from.get() == ALL else self.t_from.get()
        hi = None if self.t_to.get() == ALL else self.t_to.get()
        rows = []
        for r in self._rows:
            t = pretty_utc(r["window_start_utc"])
            if lvl != ALL and r["level"] != lvl:
                continue
            if kind != ALL and r["kind"] != kind:
                continue
            if host != ALL and r["host"] != host:
                continue
            if (lo and t < lo) or (hi and t > hi):
                continue
            rows.append(r)
        self._shown = rows
        n_pred = sum(1 for r in rows if r["kind"] == "Predicted")
        scope = "all replay runs" if self._run_id is None else f"replay run #{self._run_id}"
        self.count.configure(text=f"{len(rows)} of {len(self._rows)} alerts in {scope} · "
                                  f"{len(rows) - n_pred} detected · {n_pred} predicted")
        self._render()

    def _go(self, delta: int) -> None:
        pages = max(1, -(-len(self._shown) // PAGE_SIZE))
        self._page = max(0, min(pages - 1, self._page + delta))
        self._render()

    # ------------------------------------------------------------------ list
    def _render(self) -> None:
        body = self.list_card.body
        for w in body.winfo_children():
            w.destroy()
        pages = max(1, -(-len(self._shown) // PAGE_SIZE))
        self.page_label.configure(text=f"page {self._page + 1} of {pages}")
        self.prev_btn.configure(state="normal" if self._page > 0 else "disabled")
        self.next_btn.configure(state="normal" if self._page < pages - 1 else "disabled")
        if not self._shown:
            msg = ("No alerts yet. Run the Live Replay to generate alerts." if not self._rows
                   else "No alerts match these filters.")
            label(body, msg, "body", T.MUTED).pack(anchor="w", padx=T.SPACE["m"], pady=T.SPACE["l"])
            return
        chunk = self._shown[self._page * PAGE_SIZE:(self._page + 1) * PAGE_SIZE]
        for i, r in enumerate(chunk):
            bg = T.SURFACE if i % 2 else T.SURFACE_2
            row = ctk.CTkFrame(body, fg_color=bg, corner_radius=8, cursor="hand2")
            row.pack(fill="x", pady=2)
            Badge(row, r["level"], r["kind"], bg=bg).grid(row=0, column=0, rowspan=3, padx=10, pady=8, sticky="w")
            line1 = ctk.CTkFrame(row, fg_color="transparent")
            line1.grid(row=0, column=1, sticky="w", padx=(4, 8), pady=(8, 0))
            label(line1, r["host"], "mono_bold").pack(side="left")
            label(line1, pretty_utc(r["window_start_utc"]), "mono", T.MUTED).pack(side="left", padx=(16, 0))
            label(row, r["reason"] or "", "body", T.ALERT.get(r["level"], T.TEXT)).grid(row=1, column=1, sticky="w",
                                                                                         padx=(4, 8))
            hm = f"{r['horizon_minutes']:g}"
            label(row, (f"detected {tier_name(r['det_tier'])} · forecast {tier_name(r['fut_tier'])} · "
                        f"P(attack ≤{hm} min) {r['p_attack_next']:.3f} · "
                        f"P(escalation ≤{hm} min) {r['p_severe_next']:.3f}"), "small", T.MUTED).grid(
                row=2, column=1, sticky="w", padx=(4, 8), pady=(0, 8))
            row.columnconfigure(1, weight=1)
            for w in [row, *row.winfo_children(), *line1.winfo_children()]:
                w.bind("<Button-1>", lambda e, r=r: self._open(r))

    def _open(self, r: dict) -> None:
        hm = f"{r['horizon_minutes']:g}"
        self.drawer.open(
            f"Alert #{r['id']}",
            [("Host (IP)", r["host"]),
             ("Recorded window start", pretty_utc(r["window_start_utc"])),
             ("Epoch seconds (ts)", f"{r['window_start']:.0f}"),
             ("Level", r["level"]), ("Type", r["kind"]), ("Reason", r["reason"] or ""),
             ("Detected tier (now)", tier_name(r["det_tier"])),
             (f"Forecast tier (next {hm} min)", tier_name(r["fut_tier"])),
             (f"P(any attack within {hm} min)", f"{r['p_attack_next']:.6f}"),
             (f"P(escalation to compromise/DoS within {hm} min)", f"{r['p_severe_next']:.6f}"),
             ("Forecast horizon", f"{hm} minutes"),
             ("Replay run", f"#{r['run_id']}")],
            header_widget=lambda parent: Badge(parent, r["level"], r["kind"]))

    def _export(self) -> None:
        if not self._shown:
            show_toast(self, "Nothing to export", "No alerts match the current filters.", "warning")
            return
        run = "all" if self._run_id is None else f"run{self._run_id}"
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile=f"vigil_alerts_{run}.csv",
                                            filetypes=[("CSV", "*.csv")])
        if not path:
            return
        cols = ["run_id", *db.HYBRID_ALERT_FIELDS]
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(cols)
            for r in self._shown:
                w.writerow([r[c] for c in cols])
        show_toast(self, "Export complete", f"{len(self._shown)} alerts written to {path}", "success")
