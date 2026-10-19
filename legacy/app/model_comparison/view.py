"""
Model Comparison -- hybrid vs LSTM / RF / XGBoost baseline / persistence.

Every number on this screen is read from artifacts_rf_lstm/reports/*.csv via
services.reports; tables are split by the CSV's own `task` values
(detection vs forecast), so a later run with the same schema drops straight in.
"""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageTk

from app.common import theme
from app.common.context import AppContext
from app.common.widgets import ScrollFrame, dataframe_table
from services import reports

THUMB_W = 330


class ModelComparisonView(tk.Frame):
    def __init__(self, parent, ctx: AppContext):
        super().__init__(parent, bg=theme.BG_PRIMARY)
        self.ctx = ctx
        self._thumbs: list = []   # keep PhotoImage refs alive
        self._build()

    def _build(self) -> None:
        scroll = ScrollFrame(self)
        scroll.pack(fill="both", expand=True)
        pad = tk.Frame(scroll.body, bg=theme.BG_PRIMARY, padx=24, pady=18)
        pad.pack(fill="both", expand=True)

        tk.Label(pad, text="Model Comparison", bg=theme.BG_PRIMARY, fg=theme.TEXT_PRIMARY,
                 font=(theme.FONT_HEADER[0], 18, "bold")).pack(anchor="w")
        tk.Label(pad, text="All values read from artifacts_rf_lstm/reports/*.csv (test period of the RF–LSTM run).",
                 bg=theme.BG_PRIMARY, fg=theme.TEXT_MUTED, font=theme.FONT_LABEL).pack(anchor="w", pady=(0, 8))

        self._caveats(pad)

        mc = reports.load_report("model_comparison")
        if mc is None:
            self._missing(pad, "model_comparison")
        else:
            for task in reports.tasks(mc):
                sub = reports.drop_empty_columns(mc[mc["task"].astype(str) == task].drop(columns=["task"]))
                self._table_section(pad, f"Window-level: {task}", sub,
                                    "Source: reports/model_comparison.csv")
        self._report_section(pad, "flow_level_comparison", "Flow-level classification (per flow)")
        self._report_section(pad, "early_warning", "Early warning (onset / escalation events)")
        self._report_section(pad, "efficiency", "Efficiency (training time, inference cost, size)")
        self._report_section(pad, "split_coverage", "Split coverage (flows per traffic type)")
        self._report_section(pad, "attack_type_time_spans", "Attack-type time spans (recorded)")
        self._figures(pad)

    # ------------------------------------------------------------------
    def _caveats(self, pad) -> None:
        notes = []
        types = reports.test_split_types()
        if types is not None:
            notes.append("Traffic types present in the test split (split_coverage.csv): " + ", ".join(types) + ".")
        n_ev = reports.early_warning_events_evaluated()
        if n_ev == 0:
            notes.append("early_warning.csv evaluates 0 onset/escalation events in the test period, so "
                         "early-warning recall and lead time are not measured by this run.")
        notes.append("“XGBoost (baseline)” rows are the XGBoost models trained alongside the hybrid on the "
                     "same ToN_IoT windows (xgb_*_baseline.json), not the legacy CICIoT2023 Spotter panel.")
        box = tk.Frame(pad, bg=theme.BG_CARD, highlightbackground=theme.ACCENT_AMBER, highlightthickness=1)
        box.pack(fill="x", pady=(0, 12))
        for n in notes:
            tk.Label(box, text="• " + n, bg=theme.BG_CARD, fg=theme.TEXT_PRIMARY, font=theme.FONT_LABEL,
                     justify="left", wraplength=1000).pack(anchor="w", padx=14, pady=(6, 0))
        tk.Frame(box, bg=theme.BG_CARD, height=6).pack()

    def _missing(self, pad, name) -> None:
        tk.Label(pad, text=f"{reports.REPORT_FILES[name]} not found in {os.path.dirname(reports.report_path(name))}",
                 bg=theme.BG_PRIMARY, fg=theme.ACCENT_RED, font=theme.FONT_LABEL).pack(anchor="w", pady=4)

    def _report_section(self, pad, name, title) -> None:
        df = reports.load_report(name)
        if df is None:
            self._missing(pad, name)
            return
        self._table_section(pad, title, reports.drop_empty_columns(df), f"Source: reports/{reports.REPORT_FILES[name]}")

    def _table_section(self, pad, title, df, source) -> None:
        card = tk.Frame(pad, bg=theme.BG_CARD, highlightbackground=theme.BORDER, highlightthickness=1)
        card.pack(fill="x", pady=(0, 12))
        head = tk.Frame(card, bg=theme.BG_CARD)
        head.pack(fill="x", padx=12, pady=(8, 4))
        tk.Label(head, text=title, bg=theme.BG_CARD, fg=theme.TEXT_PRIMARY, font=theme.FONT_HEADER).pack(side="left")
        tk.Label(head, text=source, bg=theme.BG_CARD, fg=theme.TEXT_MUTED,
                 font=(theme.FONT_LABEL[0], 8)).pack(side="right")
        holder = tk.Frame(card, bg=theme.BG_CARD)
        holder.pack(fill="x", padx=12, pady=(0, 10))
        tree = dataframe_table(holder, df, height=max(1, len(df)))
        xs = ttk.Scrollbar(holder, orient="horizontal", command=tree.xview)
        tree.configure(xscrollcommand=xs.set)
        tree.pack(fill="x")
        xs.pack(fill="x")

    def _figures(self, pad) -> None:
        paths = reports.figure_paths()
        card = tk.Frame(pad, bg=theme.BG_CARD, highlightbackground=theme.BORDER, highlightthickness=1)
        card.pack(fill="x", pady=(0, 12))
        tk.Label(card, text="Saved figures (artifacts_rf_lstm/figures/) — click to enlarge", bg=theme.BG_CARD,
                 fg=theme.TEXT_PRIMARY, font=theme.FONT_HEADER).pack(anchor="w", padx=12, pady=(8, 4))
        grid = tk.Frame(card, bg=theme.BG_CARD)
        grid.pack(fill="x", padx=12, pady=(0, 10))
        if not paths:
            tk.Label(grid, text="No figures found.", bg=theme.BG_CARD, fg=theme.TEXT_MUTED,
                     font=theme.FONT_LABEL).pack(anchor="w")
            return
        for i, p in enumerate(paths):
            try:
                img = Image.open(p)
                img.thumbnail((THUMB_W, THUMB_W))
                photo = ImageTk.PhotoImage(img)
            except Exception as exc:
                photo = None
                err = str(exc)
            cell = tk.Frame(grid, bg=theme.BG_CARD, padx=6, pady=6)
            cell.grid(row=i // 3, column=i % 3, sticky="nw")
            if photo is not None:
                self._thumbs.append(photo)
                lbl = tk.Label(cell, image=photo, bg=theme.BG_CARD, cursor="hand2")
                lbl.pack()
                lbl.bind("<Button-1>", lambda e, path=p: self._open_figure(path))
            else:
                tk.Label(cell, text=f"Could not open: {err}", bg=theme.BG_CARD, fg=theme.ACCENT_RED).pack()
            tk.Label(cell, text=os.path.basename(p), bg=theme.BG_CARD, fg=theme.TEXT_MUTED,
                     font=theme.FONT_MONO_SMALL).pack(anchor="w")

    def _open_figure(self, path: str) -> None:
        win = tk.Toplevel(self)
        win.title(os.path.basename(path))
        win.configure(bg=theme.BG_CARD)
        img = Image.open(path)
        max_w, max_h = int(self.winfo_screenwidth() * 0.85), int(self.winfo_screenheight() * 0.85)
        img.thumbnail((max_w, max_h))
        photo = ImageTk.PhotoImage(img)
        lbl = tk.Label(win, image=photo, bg=theme.BG_CARD)
        lbl.image = photo
        lbl.pack(padx=8, pady=8)
