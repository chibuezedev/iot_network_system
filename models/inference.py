"""
inference.py -- loads Spotter (detection) and Risk Analyst (severity) once,
keeps them resident in memory, and exposes simple predict functions.

SCHEMA-BRIDGING DECISION (read this before changing anything)
===============================================================
Spotter is trained on CICIoT2023-style flow features (46 numeric columns).
Risk Analyst is trained on ToN_IoT-style connection features (8 numeric +
3 categorical columns). These are two different datasets with two different
schemas -- there is no principled per-packet mapping from one to the other.

The approach used here, chosen for methodological transparency (per the
build spec, Section 4.2 step 3) is:

    APPROACH: INDEPENDENT PARALLEL SLICE, SHARED SYNTHETIC TIMELINE.
    Each row of simulation_feed.csv carries BOTH a full Spotter feature
    vector AND a full Risk Analyst feature vector, generated independently
    of one another but assigned the same row_id / sim_time position in the
    replay. Spotter and Risk Analyst are each run on their own native
    columns from that row. The two verdicts shown side by side in the Live
    Monitor are therefore two independent models' opinions about traffic
    occurring at the same simulated moment, NOT a single model's features
    reused for a second model, and NOT one model's output feeding the
    other. This is stated explicitly in the Model Info screen.

This is a deliberate, disclosed simplification: it lets the demo show both
models operating "live" over a shared timeline without fabricating a
cross-dataset feature translation that would misrepresent what either model
actually learned.
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from typing import Optional

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb

from app.common.paths import resource_path

_lock = threading.Lock()


@dataclass
class PredictionResult:
    label: str
    confidence: float
    class_probabilities: dict


class Spotter:
    """Attack detection model (Model 1)."""

    def __init__(self):
        artifacts = resource_path("model_artifacts")
        self.booster = xgb.Booster()
        self.booster.load_model(f"{artifacts}/detection_model_xgboost.json")
        with open(f"{artifacts}/detection_feature_columns.json") as f:
            self.feature_columns: list[str] = json.load(f)
        self.label_encoder = joblib.load(f"{artifacts}/detection_label_encoder.joblib")
        with open(f"{artifacts}/detection_class_names.json") as f:
            self.class_names: list[str] = json.load(f)

        # Reference metrics from the real trained model (Section 1 of the
        # build spec). These describe the ACTUAL research model's held-out
        # test performance and are shown as-is in Model Info regardless of
        # which artifact file happens to be loaded at runtime (placeholder
        # or real) -- clearly labeled as reference metrics, never presented
        # as a live evaluation of the current session.
        self.reference_metrics = {
            "Accuracy": 0.9946,
            "Balanced Accuracy": 0.8661,
            "Precision (macro)": 0.9082,
            "Recall (macro)": 0.8661,
            "F1 (macro)": 0.8799,
            "F1 (weighted)": 0.9947,
            "Matthews Correlation Coefficient": 0.9941,
            "Cohen's Kappa": 0.9941,
        }

    def predict_row(self, row: pd.Series) -> PredictionResult:
        x = row[self.feature_columns].to_frame().T.astype("float32")
        with _lock:
            probs = self.booster.predict(xgb.DMatrix(x))[0]
        idx = int(np.argmax(probs))
        label = self.label_encoder.inverse_transform([idx])[0]
        class_probs = {
            self.label_encoder.inverse_transform([i])[0]: float(p)
            for i, p in enumerate(probs)
        }
        return PredictionResult(label=label, confidence=float(probs[idx]), class_probabilities=class_probs)


class RiskAnalyst:
    """Severity / predictive risk model (Model 2)."""

    def __init__(self):
        artifacts = resource_path("model_artifacts")
        self.booster = xgb.Booster()
        self.booster.load_model(f"{artifacts}/severity_model_xgboost.json")
        with open(f"{artifacts}/severity_feature_columns.json") as f:
            self.feature_columns: list[str] = json.load(f)
        self.categorical_encoders = joblib.load(f"{artifacts}/severity_categorical_encoders.joblib")
        with open(f"{artifacts}/severity_class_names.json") as f:
            raw = json.load(f)
        self.tier_names: dict[int, str] = {int(k): v for k, v in raw.items()}

    def predict_row(self, row: pd.Series) -> PredictionResult:
        x = row[self.feature_columns].to_frame().T.copy()
        for col, encoder in self.categorical_encoders.items():
            # Unseen categories fall back to the first known class rather
            # than raising, so a noisy demo row never crashes the pipeline.
            val = x.at[x.index[0], col]
            if val not in set(encoder.classes_):
                val = encoder.classes_[0]
            x.at[x.index[0], col] = encoder.transform([val])[0]
        x = x.astype("float32")
        with _lock:
            probs = self.booster.predict(xgb.DMatrix(x))[0]
        idx = int(np.argmax(probs))
        label = self.tier_names.get(idx, f"Tier {idx}")
        class_probs = {self.tier_names.get(i, f"Tier {i}"): float(p) for i, p in enumerate(probs)}
        return PredictionResult(label=label, confidence=float(probs[idx]), class_probabilities=class_probs)


_spotter: Optional[Spotter] = None
_risk_analyst: Optional[RiskAnalyst] = None
_init_lock = threading.Lock()


def load_models() -> tuple[Spotter, RiskAnalyst]:
    """Load both models once and cache them at module level. Thread-safe."""
    global _spotter, _risk_analyst
    with _init_lock:
        if _spotter is None:
            _spotter = Spotter()
        if _risk_analyst is None:
            _risk_analyst = RiskAnalyst()
    return _spotter, _risk_analyst


def severity_tier_index(label: str, risk_analyst: RiskAnalyst) -> int:
    for idx, name in risk_analyst.tier_names.items():
        if name == label:
            return idx
    return 0
