"""
reports.py -- read the RF-LSTM run's report CSVs and figures.

No metric is ever typed into the app: every number shown in Model Comparison
and Model Info is read from artifacts_rf_lstm/reports/*.csv by this module.
Missing files return None so the views can say so instead of crashing.
"""
from __future__ import annotations

import glob
import os
from typing import Optional

import pandas as pd

from services.hybrid_service import FIGURES_DIR, REPORTS_DIR

REPORT_FILES = {
    "model_comparison": "model_comparison.csv",
    "flow_level_comparison": "flow_level_comparison.csv",
    "early_warning": "early_warning.csv",
    "efficiency": "efficiency.csv",
    "split_coverage": "split_coverage.csv",
    "attack_type_time_spans": "attack_type_time_spans.csv",
}


def report_path(name: str) -> str:
    return os.path.join(REPORTS_DIR, REPORT_FILES[name])


def load_report(name: str) -> Optional[pd.DataFrame]:
    path = report_path(name)
    if not os.path.exists(path):
        return None
    return pd.read_csv(path)


def tasks(df: pd.DataFrame) -> list[str]:
    """Task values in file order (e.g. detection / forecast), as written by the notebook."""
    return list(dict.fromkeys(df["task"].astype(str))) if df is not None and "task" in df else []


def drop_empty_columns(df: pd.DataFrame) -> pd.DataFrame:
    return df.dropna(axis=1, how="all")


def primary_model_name(df: Optional[pd.DataFrame]) -> Optional[str]:
    """The hybrid's row label in model_comparison.csv (the row naming the hybrid, else the first)."""
    if df is None or df.empty:
        return None
    names = list(dict.fromkeys(df["model"].astype(str)))
    return next((n for n in names if "hybrid" in n.lower()), names[0])


def test_split_types() -> Optional[list[str]]:
    """Traffic types with at least one flow in the test split (split_coverage.csv)."""
    df = load_report("split_coverage")
    if df is None or "test" not in df:
        return None
    return sorted(df.loc[pd.to_numeric(df["test"], errors="coerce").fillna(0) > 0, "type"].astype(str))


def early_warning_events_evaluated() -> Optional[int]:
    df = load_report("early_warning")
    if df is None or "events_evaluated" not in df:
        return None
    return int(pd.to_numeric(df["events_evaluated"], errors="coerce").fillna(0).sum())


def figure_paths() -> list[str]:
    return sorted(glob.glob(os.path.join(FIGURES_DIR, "*.png")))


# ---------------------------------------------------------------- XGBoost separation
# Model Evaluation shows XGBoost only in its own section, so rows are split by name.
def is_xgboost(model: str) -> bool:
    return "xgboost" in str(model).lower()


def split_xgboost(df: Optional[pd.DataFrame]) -> tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """(rows without XGBoost, XGBoost rows) of a report with a 'model' column."""
    if df is None or "model" not in df:
        return df, None
    mask = df["model"].map(is_xgboost)
    return df[~mask].reset_index(drop=True), df[mask].reset_index(drop=True)


# Columns of model_comparison.csv that duplicate efficiency.csv / early_warning.csv; they are shown
# in those tables instead of being repeated in the detection/forecast tables.
OPERATIONAL_COLUMNS = ["train_s", "infer_ms_per_1k_seq", "size_mb"]
EARLY_WARNING_PREFIXES = ("escalation_", "onset_")


def quality_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c not in ("model", "task", *OPERATIONAL_COLUMNS)
            and not c.startswith(EARLY_WARNING_PREFIXES) and df[c].notna().any()]


def previous_system_metrics() -> Optional[dict]:
    """Reference metrics of the previous CICIoT2023 XGBoost system (model_artifacts/spotter_metrics.json)."""
    import json
    from app.common.paths import resource_path
    path = resource_path("model_artifacts", "spotter_metrics.json")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return {"source": data.get("source"), "metrics": data.get("metrics") or {}, "path": path}


def display_path(path: str) -> str:
    """Path relative to the project folder when inside it (keeps local user paths out of screenshots)."""
    from app.common.paths import resource_path
    root = resource_path()
    try:
        rel = os.path.relpath(path, root)
    except ValueError:      # different drive
        return path
    return path if rel.startswith("..") else rel.replace(os.sep, "/")
