"""
Model Evaluation -- every number is read from artifacts_rf_lstm/reports/*.csv
(and model_artifacts/spotter_metrics.json for the previous system). XGBoost
appears only in the XGBoost tab, in two separated sections.
"""
from __future__ import annotations

import os
from tkinter import filedialog

import customtkinter as ctk
import pandas as pd
from PIL import Image

from app.screens.base import Screen
from app.ui import theme, tokens as T
from app.ui.widgets import Card, Table, autowrap, button, label, note_box, section_title, show_toast
from services import report_export, reports

THUMB = 300
TABS = ["Detection", "Forecast", "Early warning", "Flow-level", "Efficiency", "Coverage", "Figures", "XGBoost"]


def _numeric(df: pd.DataFrame) -> set:
    return {c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])}


class EvaluationScreen(Screen):
    title = "Model Evaluation"
    subtitle = ("Test-period results of the RF–LSTM hybrid and the comparison models, read from "
                "artifacts_rf_lstm/reports/*.csv.")

    def build(self) -> None:
        self.header()
        self._thumbs = []
        bar = ctk.CTkFrame(self.page, fg_color="transparent")
        self.section(bar, pady=(0, T.SPACE["m"]))
        types = reports.test_split_types()
        if types is not None:
            label(bar, "Traffic types in the test split (split_coverage.csv): " + ", ".join(types), "small",
                  T.MUTED).pack(side="left")
        button(bar, "Export report (HTML)", self._export, "secondary", width=170).pack(side="right")

        self.tabs = ctk.CTkTabview(self.page, fg_color=T.SURFACE, border_color=T.BORDER, border_width=1,
                                   segmented_button_fg_color=T.SURFACE_2,
                                   segmented_button_selected_color=T.ACCENT,
                                   segmented_button_selected_hover_color=T.ACCENT_HOVER,
                                   segmented_button_unselected_color=T.SURFACE_2,
                                   segmented_button_unselected_hover_color=T.BORDER, text_color=T.TEXT,
                                   corner_radius=T.RADIUS_CARD, anchor="w", height=200)
        self.section(self.tabs, fill="both")
        self.tabs._segmented_button.configure(font=theme.font("small_bold"))
        for t in TABS:
            self.tabs.add(t)
        self._task_tabs()
        self._early_warning(self.tabs.tab("Early warning"))
        self._simple(self.tabs.tab("Flow-level"), "flow_level_comparison", "Flow-level classification (per flow)",
                     transpose=True)
        self._simple(self.tabs.tab("Efficiency"), "efficiency", "Training time, inference cost and model size")
        self._simple(self.tabs.tab("Coverage"), "split_coverage", "Flows per traffic type in each split")
        self._simple(self.tabs.tab("Coverage"), "attack_type_time_spans", "Attack-type time spans (recorded ts)")
        self._figures(self.tabs.tab("Figures"))
        self._xgboost(self.tabs.tab("XGBoost"))

    # ------------------------------------------------------------------ tabs
    def _missing(self, parent, name) -> None:
        label(parent, f"{reports.REPORT_FILES[name]} not found in {reports.display_path(reports.REPORTS_DIR)}", "body", T.DANGER).pack(
            anchor="w", padx=12, pady=12)

    def _head(self, parent, title: str, source: str) -> None:
        section_title(parent, title, source).pack(fill="x", padx=12, pady=(12, 6))

    def _table(self, parent, df: pd.DataFrame, emphasis: int | None = None) -> None:
        Table(parent, list(df.columns), df.itertuples(index=False), numeric=_numeric(df),
              emphasis_row=emphasis).pack(fill="x", padx=12, pady=(0, 12))

    def _task_tabs(self) -> None:
        mc = reports.load_report("model_comparison")
        for tab_name in ("Detection", "Forecast"):
            tab = self.tabs.tab(tab_name)
            if mc is None:
                self._missing(tab, "model_comparison")
                continue
            main, _ = reports.split_xgboost(mc)
            tasks = [t for t in reports.tasks(main) if t.lower().startswith(tab_name.lower())]
            if not tasks:
                label(tab, f"No '{tab_name.lower()}' task in model_comparison.csv.", "body", T.MUTED).pack(
                    anchor="w", padx=12, pady=12)
            for task in tasks:
                sub = main[main["task"].astype(str) == task]
                df = report_export.transpose_by_model(sub, reports.quality_columns(sub))
                self._head(tab, f"Window-level {task}", "model_comparison.csv · metrics as rows, models as columns")
                Table(tab, list(df.columns), df.itertuples(index=False), numeric=set(df.columns) - {"metric"}).pack(
                    fill="x", padx=12, pady=(0, 8))
            label(tab, "XGBoost baseline rows are in the XGBoost tab. Training/inference cost: Efficiency tab; "
                       "early-warning columns: Early warning tab.", "small", T.MUTED).pack(anchor="w", padx=12,
                                                                                        pady=(0, 12))

    def _early_warning(self, tab) -> None:
        df = reports.load_report("early_warning")
        if df is None:
            self._missing(tab, "early_warning")
            return
        main, xgb = reports.split_xgboost(df)
        lines = []
        hybrid = reports.primary_model_name(main)
        for ev in main["event"].astype(str).unique():
            d = main[main["event"].astype(str) == ev]
            n = int(d["events_evaluated"].max()) if len(d) else 0
            h = d[d["model"] == hybrid]
            best = d.sort_values("early_warning_recall", ascending=False).iloc[0] if len(d) else None
            if n == 0:
                lines.append(f"{ev}: no events in the test period, so early warning is not measured.")
                continue
            hs = (f"{hybrid} anticipated {int(h['anticipated'].iloc[0])} of {n} "
                  f"(recall {h['early_warning_recall'].iloc[0]:.3f})") if len(h) else f"{hybrid}: no row"
            bs = (f"; highest recall among these models: {best['model']} {int(best['anticipated'])} of {n} "
                  f"({best['early_warning_recall']:.3f})") if best is not None and best["model"] != hybrid else ""
            lines.append(f"{ev}: {n} events evaluated — {hs}{bs}.")
        if xgb is not None and not xgb.empty:
            lines.append("XGBoost baseline early-warning rows are shown in the XGBoost tab.")
        box = note_box(tab, "\n".join(lines), T.ALERT["HIGH"])
        box.pack(fill="x", padx=12, pady=(12, 6))
        self._head(tab, "Early warning (onset / escalation events)", "early_warning.csv")
        self._table(tab, reports.drop_empty_columns(main))

    def _simple(self, tab, name: str, title: str, transpose: bool = False) -> None:
        df = reports.load_report(name)
        if df is None:
            self._missing(tab, name)
            return
        main, xgb = reports.split_xgboost(df)
        main = reports.drop_empty_columns(main)
        self._head(tab, title, reports.REPORT_FILES[name])
        if transpose and "model" in main:
            t = report_export.transpose_by_model(main, [c for c in main.columns if c != "model"])
            Table(tab, list(t.columns), t.itertuples(index=False), numeric=set(t.columns) - {"metric"}).pack(
                fill="x", padx=12, pady=(0, 12))
        else:
            self._table(tab, main)
        if xgb is not None and not xgb.empty:
            label(tab, "XGBoost baseline rows: XGBoost tab.", "small", T.MUTED).pack(anchor="w", padx=12,
                                                                                       pady=(0, 12))

    def _figures(self, tab) -> None:
        paths = reports.figure_paths()
        label(tab, f"{len(paths)} figures from {reports.display_path(reports.FIGURES_DIR)} — click to enlarge. They are the "
                   "notebook's own images and may include the comparison models.", "small", T.MUTED).pack(
            anchor="w", padx=12, pady=(12, 6))
        grid = ctk.CTkFrame(tab, fg_color="transparent")
        grid.pack(fill="x", padx=6)
        for i, p in enumerate(paths):
            cell = ctk.CTkFrame(grid, fg_color=T.SURFACE_2, corner_radius=8)
            cell.grid(row=i // 3, column=i % 3, sticky="nsew", padx=6, pady=6)
            try:
                img = Image.open(p)
                img.thumbnail((THUMB, THUMB))
                cimg = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
                self._thumbs.append(cimg)
                pic = ctk.CTkLabel(cell, image=cimg, text="", cursor="hand2")
                pic.pack(padx=8, pady=(8, 4))
                pic.bind("<Button-1>", lambda e, path=p: self._open_figure(path))
            except Exception as exc:
                label(cell, f"Could not open: {exc}", "small", T.DANGER).pack(padx=8, pady=8)
            label(cell, os.path.basename(p), "mono_small", T.MUTED).pack(anchor="w", padx=10, pady=(0, 8))
        for c in range(3):
            grid.columnconfigure(c, weight=1, uniform="figs")

    def _open_figure(self, path: str) -> None:
        win = ctk.CTkToplevel(self)
        win.title(os.path.basename(path))
        win.configure(fg_color=T.SURFACE)
        img = Image.open(path)
        scale = ctk.ScalingTracker.get_widget_scaling(self)
        max_w = int(self.winfo_screenwidth() * 0.85 / scale)
        max_h = int(self.winfo_screenheight() * 0.85 / scale)
        img.thumbnail((max_w, max_h))
        cimg = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
        lbl = ctk.CTkLabel(win, image=cimg, text="")
        lbl.image = cimg
        lbl.pack(padx=10, pady=10)
        win.after(50, win.lift)

    def _xgboost(self, tab) -> None:
        a = Card(tab, fg_color=T.SURFACE_2)
        a.pack(fill="x", padx=12, pady=(12, 8))
        section_title(a.body, "XGBoost baseline (same ToN_IoT experiment)",
                      "XGBoost rows of the report CSVs").pack(fill="x")
        found = False
        for name in ("model_comparison", "early_warning", "flow_level_comparison", "efficiency"):
            df = reports.load_report(name)
            _, xgb = reports.split_xgboost(df)
            if xgb is None or xgb.empty:
                continue
            found = True
            xgb = reports.drop_empty_columns(xgb)
            label(a.body, reports.REPORT_FILES[name], "small_bold", T.MUTED).pack(anchor="w", pady=(10, 4))
            if name == "model_comparison":       # metrics as rows, one column per model/task
                lab = xgb.assign(model=xgb["model"].astype(str) + " · " + xgb["task"].astype(str))
                xgb = report_export.transpose_by_model(lab, reports.quality_columns(xgb))
            elif name == "flow_level_comparison":
                xgb = report_export.transpose_by_model(xgb, [c for c in xgb.columns if c != "model"])
            numeric = set(xgb.columns) - {"metric"} if "metric" in xgb else _numeric(xgb)
            Table(a.body, list(xgb.columns), xgb.itertuples(index=False), numeric=numeric).pack(fill="x")
        if not found:
            label(a.body, "No XGBoost rows in the report CSVs.", "body", T.MUTED).pack(anchor="w", pady=8)

        b = Card(tab, fg_color=T.SURFACE_2, border_color=T.ALERT["WARNING"])
        b.pack(fill="x", padx=12, pady=(8, 12))
        section_title(b.body, "Previous system: XGBoost on CICIoT2023").pack(fill="x")
        label(b.body, "Reference only — different dataset, not directly comparable with the results above.",
              "body_bold", T.ALERT["WARNING"]).pack(anchor="w", pady=(4, 8))
        prev = reports.previous_system_metrics()
        if prev is None:
            label(b.body, "model_artifacts/spotter_metrics.json not found.", "body", T.DANGER).pack(anchor="w")
            return
        rows = list(prev["metrics"].items())
        Table(b.body, ["metric", "value"], rows, numeric={"value"}).pack(fill="x")
        src = autowrap(label(b.body, f"Source: {prev['source']}", "small", T.MUTED), b.body, margin=8)
        src.pack(anchor="w", fill="x", pady=(8, 0))

    # ------------------------------------------------------------------ export
    def _export(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".html", initialfile="vigil_model_evaluation.html",
                                            filetypes=[("HTML", "*.html")])
        if not path:
            return
        try:
            report_export.export(path)
        except Exception as exc:
            show_toast(self, "Export failed", f"{type(exc).__name__}: {exc}", "critical")
            return
        show_toast(self, "Report exported", path, "success")
