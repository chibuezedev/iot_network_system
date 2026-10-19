"""
report_export.py -- write the Model Evaluation tables and figures to one
self-contained HTML file (figures embedded as base64). Light styling for
printing. Every number is read from the report CSVs / JSON via services.reports.
"""
from __future__ import annotations

import base64
import html
import math
import os

import pandas as pd

from app.ui import tokens as T
from services import reports


def _fmt(v) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "&mdash;"
    if isinstance(v, float):
        return f"{v:,.0f}" if v.is_integer() and abs(v) >= 1000 else f"{v:.4f}"
    return html.escape(str(v))


def _table(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return "<p class='muted'>No rows.</p>"
    head = "".join(f"<th>{html.escape(str(c))}</th>" for c in df.columns)
    body = "".join("<tr>" + "".join(f"<td>{_fmt(v)}</td>" for v in row) + "</tr>"
                   for row in df.itertuples(index=False))
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def transpose_by_model(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Metrics as rows, models as columns (readable when there are many metrics)."""
    t = df.set_index("model")[cols].T.reset_index().rename(columns={"index": "metric"})
    t.columns = [str(c) for c in t.columns]
    return t


def build_html() -> str:
    parts = [f"<h1>{T.APP_NAME} &mdash; model evaluation report</h1>",
             "<p class='muted'>RF&ndash;LSTM hybrid and comparison models. All values are read from "
             f"<code>{html.escape(reports.display_path(reports.REPORTS_DIR))}</code> and <code>model_artifacts/spotter_metrics.json</code>."
             "</p>"]
    types = reports.test_split_types()
    if types:
        parts.append(f"<p>Traffic types in the test split: {html.escape(', '.join(types))}.</p>")
    mc = reports.load_report("model_comparison")
    if mc is not None:
        main, xgb = reports.split_xgboost(mc)
        for task in reports.tasks(mc):
            sub = main[main["task"].astype(str) == task]
            parts.append(f"<h2>Window-level: {html.escape(task)}</h2>")
            parts.append(_table(transpose_by_model(sub, reports.quality_columns(sub))))
    for name, title in (("early_warning", "Early warning (onset / escalation events)"),
                        ("flow_level_comparison", "Flow-level classification (per flow)"),
                        ("efficiency", "Efficiency"), ("split_coverage", "Split coverage (flows per type)"),
                        ("attack_type_time_spans", "Attack-type time spans (recorded)")):
        df = reports.load_report(name)
        if df is None:
            continue
        main, _ = reports.split_xgboost(df)
        parts.append(f"<h2>{html.escape(title)}</h2>{_table(reports.drop_empty_columns(main))}")

    parts.append("<h2>XGBoost baseline (same ToN_IoT experiment)</h2>")
    for name in ("model_comparison", "early_warning", "flow_level_comparison", "efficiency"):
        df = reports.load_report(name)
        _, xgb = reports.split_xgboost(df)
        if xgb is not None and not xgb.empty:
            xgb = reports.drop_empty_columns(xgb)
            if name == "model_comparison":
                lab = xgb.assign(model=xgb["model"].astype(str) + " · " + xgb["task"].astype(str))
                xgb = transpose_by_model(lab, reports.quality_columns(xgb))
            parts.append(f"<h3>{html.escape(reports.REPORT_FILES[name])}</h3>{_table(xgb)}")
    prev = reports.previous_system_metrics()
    parts.append("<h2>Previous system: XGBoost on CICIoT2023 (reference only, different dataset, "
                 "not directly comparable)</h2>")
    if prev:
        parts.append(_table(pd.DataFrame(list(prev["metrics"].items()), columns=["metric", "value"])))
        parts.append(f"<p class='muted'>Source: {html.escape(prev['source'] or '')}</p>")

    figs = reports.figure_paths()
    if figs:
        parts.append("<h2>Figures</h2>")
        for p in figs:
            with open(p, "rb") as fh:
                b64 = base64.b64encode(fh.read()).decode()
            parts.append(f"<figure><img src='data:image/png;base64,{b64}'/>"
                         f"<figcaption>{html.escape(os.path.basename(p))}</figcaption></figure>")
    css = ("body{font-family:Segoe UI,Arial,sans-serif;color:#141A22;margin:32px;max-width:1100px}"
           "h1{font-size:24px}h2{font-size:17px;margin-top:28px;border-bottom:1px solid #D3DAE2;padding-bottom:4px}"
           "h3{font-size:13px;color:#55606E}table{border-collapse:collapse;font-size:12px;margin:8px 0}"
           "th,td{border:1px solid #D3DAE2;padding:4px 8px;text-align:right}th{background:#EDF1F5}"
           "td:first-child,th:first-child{text-align:left}.muted{color:#55606E;font-size:12px}"
           "img{max-width:100%;border:1px solid #D3DAE2}figure{margin:16px 0}figcaption{font-size:11px;color:#55606E}")
    return (f"<!doctype html><html><head><meta charset='utf-8'><title>{T.APP_NAME} model evaluation</title>"
            f"<style>{css}</style></head><body>{''.join(parts)}</body></html>")


def export(path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(build_html())
