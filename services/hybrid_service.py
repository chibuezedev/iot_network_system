"""
hybrid_service.py -- the RF-LSTM hybrid as a service for the dashboard.

Everything model-related is delegated to artifacts_rf_lstm/models/
sentinel_inference.py (SentinelEngine, alert_level, TIER_NAMES), the same
file the training notebook imports. Nothing here computes features, tiers or
alert levels itself; this module only:

  * loads the engine once (RF-only fallback when torch is unavailable),
  * reads config/thresholds from preprocessing.json,
  * walks replay_flows.csv in recorded ts order, calling analyse() at each
    window boundary t0 + k * window_sec with window_start = that window's
    recorded start,
  * de-duplicates the engine's alert levels into alert events.

RESEARCH-INTEGRITY RULES (do not relax)
  - Every time attached to a result is a recorded capture time (ts / the
    window start derived from it). No wall-clock time is ever used as an
    event time; wall-clock is only used to pace the replay.
  - Hosts are the real IPs in the data. No device-name mapping here.
  - The legacy simulation feed is never read by this module.
"""
from __future__ import annotations

import importlib.util
import json
import math
import os
import queue
import sys
import threading
import time
import warnings
from collections import deque
from dataclasses import dataclass, field
from typing import Iterator, Optional

import numpy as np
import pandas as pd

from app.common.paths import resource_path

ARTIFACT_DIR = resource_path("artifacts_rf_lstm")
MODEL_DIR = os.path.join(ARTIFACT_DIR, "models")
DATA_DIR = os.path.join(ARTIFACT_DIR, "data")
REPORTS_DIR = os.path.join(ARTIFACT_DIR, "reports")
FIGURES_DIR = os.path.join(ARTIFACT_DIR, "figures")

REPLAY_FLOWS_PATH = os.path.join(DATA_DIR, "replay_flows.csv")
DASHBOARD_FEED_PATH = os.path.join(DATA_DIR, "dashboard_feed.csv")

# Requested AND achieved speed, so the banner never overstates how fast the replay runs.
REPLAY_MODE_LABEL = "Replay of recorded ToN_IoT traffic (requested {requested}, actual {actual} speed)"


def _load_inference_module():
    """Import sentinel_inference.py from the artifact folder under its own name."""
    if "sentinel_inference" in sys.modules:
        return sys.modules["sentinel_inference"]
    path = os.path.join(MODEL_DIR, "sentinel_inference.py")
    spec = importlib.util.spec_from_file_location("sentinel_inference", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sentinel_inference"] = mod
    spec.loader.exec_module(mod)
    return mod


si = _load_inference_module()
SentinelEngine = si.SentinelEngine
alert_level = si.alert_level
TIER_NAMES = si.TIER_NAMES


class LSTMUnavailable(RuntimeError):
    """Raised when a hybrid (LSTM) result is requested but the LSTM layer did not load."""


class _RFOnlyEngine(SentinelEngine):
    """SentinelEngine without the LSTM layer, for machines without torch.

    Only __init__ is replaced (SentinelEngine.__init__ loads the .pt checkpoint
    unconditionally). score_flows / _flow_proba are inherited unchanged, so the
    RF per-flow verdicts are byte-for-byte the engine's own."""

    def __init__(self, model_dir):  # noqa: D401 -- deliberately does not call super()
        import joblib
        with open(os.path.join(model_dir, "preprocessing.json")) as fh:
            self.cfg = json.load(fh)
        self.rf = joblib.load(os.path.join(model_dir, "rf_flow.joblib"))
        self.cat_maps = self.cfg["cat_maps"]
        self.W = self.cfg["window_sec"]
        self.L = self.cfg["lookback"]
        self.H = self.cfg["horizon"]
        self.t0 = self.cfg["t0"]
        self.threshold = self.cfg["thresholds"]["hybrid"]
        self.threshold_severe = self.cfg["thresholds"]["hybrid_severe"]

    def analyse(self, *args, **kwargs):
        raise LSTMUnavailable("LSTM layer unavailable")


# ---------------------------------------------------------------- results
@dataclass
class ReplayStep:
    """One recorded window of the replay."""
    k: int                      # window index: window_start = t0 + k * window_sec
    window_start: float         # recorded epoch seconds
    window_start_utc: str
    step: int                   # 1-based position in the replay
    total_steps: int
    n_flows_window: int         # flows recorded in this window (all hosts)
    hosts: pd.DataFrame         # engine.analyse() output (or RF-only summary), one row per host
    rf_counts: dict             # host -> {pred_type: n flows in this window}
    lstm_available: bool
    speed: float = 1.0                      # requested replay multiplier
    actual_speed: Optional[float] = None    # achieved multiplier (None until measured)
    # How many of the `lookback` windows behind this one lie inside replay_flows.csv.
    # Fewer than `lookback` means the file starts too late to supply the full history
    # the model saw in training (e.g. the replay is a slice of a longer test block).
    lookback_available: int = 0
    lookback: int = 0

    @property
    def lookback_complete(self) -> bool:
        return self.lookback_available >= self.lookback


@dataclass
class HybridAlert:
    host: str
    window_start: float
    window_start_utc: str
    level: str
    reason: str
    kind: str                   # "Detected" / "Predicted" (prefix of the engine's alert_reason)
    det_tier: int
    fut_tier: int
    p_attack_next: float
    p_severe_next: float
    horizon_minutes: float


def alert_kind(reason: str) -> str:
    """The engine's alert_reason always starts with 'Detected' or 'Predicted'."""
    return reason.split(":", 1)[0].strip() if reason else ""


class AlertTracker:
    """One alert per host per level until that host's level changes."""

    def __init__(self):
        self._last: dict[str, str] = {}

    def reset(self) -> None:
        self._last.clear()

    def update(self, step: ReplayStep) -> list[HybridAlert]:
        out: list[HybridAlert] = []
        if not step.lstm_available or step.hosts.empty or "alert" not in step.hosts:
            return out
        for r in step.hosts.itertuples(index=False):
            prev = self._last.get(r.entity)
            self._last[r.entity] = r.alert
            if r.alert == "NORMAL" or r.alert == prev:
                continue
            out.append(HybridAlert(
                host=r.entity, window_start=float(r.window_start), window_start_utc=r.window_start_utc,
                level=r.alert, reason=r.alert_reason, kind=alert_kind(r.alert_reason),
                det_tier=int(r.det_tier), fut_tier=int(r.fut_tier),
                p_attack_next=float(r.p_attack_next), p_severe_next=float(r.p_severe_next),
                horizon_minutes=float(r.horizon_minutes),
            ))
        return out


# ---------------------------------------------------------------- service
class HybridService:
    """Loads SentinelEngine once and exposes score_flows / analyse / iter_replay."""

    def __init__(self, model_dir: str = MODEL_DIR):
        self.model_dir = model_dir
        with open(os.path.join(model_dir, "preprocessing.json")) as fh:
            self.cfg = json.load(fh)
        self.window_sec = float(self.cfg["window_sec"])
        self.lookback = int(self.cfg["lookback"])
        self.horizon = int(self.cfg["horizon"])
        self.t0 = float(self.cfg["t0"])
        self.thresholds: dict = dict(self.cfg["thresholds"])
        self.threshold_attack = float(self.thresholds["hybrid"])
        self.threshold_severe = float(self.thresholds["hybrid_severe"])
        self.horizon_minutes = self.horizon * self.window_sec / 60.0
        self.type_order: list[str] = list(self.cfg.get("type_order", si.TYPE_ORDER))

        self.lstm_available = False
        self.lstm_error: Optional[str] = None
        self.load_warnings: list[str] = []
        self.engine = self._load_engine()

        self._replay_flows: Optional[pd.DataFrame] = None
        self._feed: Optional[pd.DataFrame] = None
        self._data_lock = threading.Lock()

    def _load_engine(self):
        # Record (not suppress) load-time warnings such as sklearn's
        # InconsistentVersionWarning, re-print them, and keep them for the UI.
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            if si.torch is None:
                self.lstm_error = ("PyTorch is not installed, so the LSTM layer (detection + forecast "
                                   "heads) is unavailable. Showing the RF per-flow layer only.")
                engine = _RFOnlyEngine(self.model_dir)
            else:
                try:
                    engine = SentinelEngine(self.model_dir)
                    self.lstm_available = True
                except Exception as exc:  # corrupt/incompatible checkpoint: still offer the RF layer
                    self.lstm_error = f"LSTM layer failed to load ({type(exc).__name__}: {exc}). " \
                                      "Showing the RF per-flow layer only."
                    engine = _RFOnlyEngine(self.model_dir)
        seen = set()
        for w in caught:
            if issubclass(w.category, ResourceWarning):
                continue
            msg = f"{w.category.__name__}: {w.message}"
            if msg not in seen:
                seen.add(msg)
                self.load_warnings.append(msg)
                print(f"[hybrid_service] {msg}", file=sys.stderr)
        return engine

    # ---- model calls (straight through to the engine) -------------------
    def score_flows(self, df: pd.DataFrame) -> pd.DataFrame:
        """Per-flow RF verdicts (engine.score_flows)."""
        return self.engine.score_flows(df)

    def analyse(self, df: pd.DataFrame, window_start: Optional[float] = None, entities=None) -> pd.DataFrame:
        """Per-host detection + forecast (engine.analyse). Raises LSTMUnavailable in RF-only mode."""
        if not self.lstm_available:
            raise LSTMUnavailable(self.lstm_error or "LSTM layer unavailable")
        return self.engine.analyse(df, entities=entities, window_start=window_start)

    # ---- window arithmetic (t0 / window_sec from preprocessing.json) ----
    def window_index(self, ts) -> np.ndarray:
        return np.floor((np.asarray(ts, dtype=np.float64) - self.t0) / self.window_sec).astype(np.int64)

    def window_start(self, k: int) -> float:
        return self.t0 + int(k) * self.window_sec

    @staticmethod
    def to_utc(epoch: float) -> str:
        return pd.to_datetime(epoch, unit="s").strftime("%Y-%m-%dT%H:%M:%SZ")

    # ---- data ------------------------------------------------------------
    def replay_flows(self) -> pd.DataFrame:
        """replay_flows.csv in recorded ts order (stable sort: ties keep file order)."""
        with self._data_lock:
            if self._replay_flows is None:
                df = pd.read_csv(REPLAY_FLOWS_PATH, low_memory=False)
                df["ts"] = pd.to_numeric(df["ts"], errors="coerce")
                df = df[df["ts"].notna()]
                if not df["ts"].is_monotonic_increasing:
                    df = df.sort_values("ts", kind="mergesort")
                self._replay_flows = df.reset_index(drop=True)
            return self._replay_flows

    def dashboard_feed(self) -> pd.DataFrame:
        with self._data_lock:
            if self._feed is None:
                self._feed = pd.read_csv(DASHBOARD_FEED_PATH)
            return self._feed

    # ---- replay ----------------------------------------------------------
    def replay_windows(self) -> tuple[int, int]:
        """(first, last) window index covered by replay_flows.csv.

        The replay evaluates every one of these windows. Windows near the start
        may have fewer than `lookback` windows of recorded history inside the
        file; each ReplayStep reports this (lookback_available), so the UI can
        say so instead of the replay silently skipping them. A replay shorter
        than `lookback` windows (e.g. a slice of a test block) still plays."""
        k = self.window_index(self.replay_flows()["ts"].values)
        return int(k.min()), int(k.max())

    def lookback_available(self, k: int) -> int:
        """Number of the `lookback` windows ending at k that lie inside replay_flows.csv."""
        first, _ = self.replay_windows()
        return int(max(0, min(self.lookback, k - first + 1)))

    def iter_replay(self, start_k: Optional[int] = None) -> Iterator[ReplayStep]:
        """Walk replay_flows.csv in ts order; at each window boundary run the engine
        on the flows of the last `lookback` windows with window_start = recorded start."""
        flows = self.replay_flows()
        k_all = self.window_index(flows["ts"].values)     # non-decreasing, since flows are ts-sorted
        first, last = self.replay_windows()
        data_first = first
        if start_k is not None:
            first = max(first, int(start_k))
        total = last - first + 1
        for step, k in enumerate(range(first, last + 1), start=1):
            lo = np.searchsorted(k_all, k - self.lookback + 1, side="left")
            cur = np.searchsorted(k_all, k, side="left")
            hi = np.searchsorted(k_all, k, side="right")
            ws = self.window_start(k)
            window_flows = flows.iloc[cur:hi]
            rf_counts, rf_tiers = self._rf_summary(window_flows)

            if self.lstm_available and hi > lo:
                hosts = self.analyse(flows.iloc[lo:hi], window_start=ws)
            else:
                hosts = self._rf_only_hosts(rf_counts, rf_tiers, ws)
            if not hosts.empty:
                hosts = hosts.sort_values("entity", kind="mergesort").reset_index(drop=True)
            yield ReplayStep(k=k, window_start=ws, window_start_utc=self.to_utc(ws), step=step,
                             total_steps=total, n_flows_window=int(hi - cur), hosts=hosts,
                             rf_counts=rf_counts, lstm_available=self.lstm_available,
                             lookback_available=int(min(self.lookback, k - data_first + 1)),
                             lookback=self.lookback)

    def _rf_summary(self, window_flows: pd.DataFrame) -> tuple[dict, dict]:
        """Per-host counts of the RF's per-flow verdicts in the current window,
        plus the highest per-flow tier the RF assigned (both from score_flows)."""
        if window_flows.empty:
            return {}, {}
        v = self.score_flows(window_flows)
        counts: dict = {}
        for (host, ptype), n in v.groupby(["dst_ip", "pred_type"]).size().items():
            counts.setdefault(host, {})[ptype] = int(n)
        tiers = {h: int(t) for h, t in v.groupby("dst_ip")["pred_tier"].max().items()}
        return counts, tiers

    def _rf_only_hosts(self, rf_counts: dict, rf_tiers: dict, ws: float) -> pd.DataFrame:
        """Host table in RF-only mode: just what the RF layer says about this window."""
        rows = [dict(entity=host, window_start=ws, window_start_utc=self.to_utc(ws),
                     n_flows=int(sum(counts.values())), rf_tier=rf_tiers.get(host, 0))
                for host, counts in rf_counts.items()]
        return pd.DataFrame(rows)


# ---------------------------------------------------------------- worker
class HybridReplayEngine:
    """Runs iter_replay() on a background thread and posts ReplayStep objects to
    result_queue (drained on the Tk thread, same pattern as SimulationEngine).

    Pacing: windows are emitted window_sec / speed seconds of wall time apart
    (the next window is computed while waiting). When model compute takes longer
    than that, the replay runs slower than requested; actual_speed reports what
    was achieved (window_sec / mean wall time per window over the last few
    windows, paused time excluded) so the UI never overstates the speed.
    Wall-clock is used ONLY to pace and measure; every displayed time is
    step.window_start."""

    SPEED_SAMPLES = 8

    def __init__(self, service: HybridService):
        self.service = service
        self.result_queue: "queue.Queue[ReplayStep]" = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self.speed = 60.0
        self.actual_speed: Optional[float] = None
        self._step_secs: deque = deque(maxlen=self.SPEED_SAMPLES)
        self.error: Optional[str] = None
        self.finished = False

    @property
    def mode_label(self) -> str:
        actual = f"~×{_round_sig(self.actual_speed)}" if self.actual_speed else "measuring…"
        return REPLAY_MODE_LABEL.format(requested=f"×{self.speed:g}", actual=actual)

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def is_paused(self) -> bool:
        return self._pause_event.is_set()

    def start(self) -> None:
        if self.is_running():
            self._pause_event.clear()
            return
        self._stop_event.clear()
        self._pause_event.clear()
        self.error = None
        self.finished = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def pause(self) -> None:
        self._pause_event.set()

    def stop(self) -> None:
        self._stop_event.set()

    def set_speed(self, multiplier: float) -> None:
        self.speed = max(1.0, float(multiplier))
        self._step_secs.clear()      # re-measure at the new speed
        self.actual_speed = None

    def _wait_until(self, due: Optional[float]) -> Optional[float]:
        """Sleep until `due` (monotonic), extended by any time spent paused.
        Returns the seconds spent paused, or None if stopped."""
        paused = 0.0
        while True:
            if self._stop_event.is_set():
                return None
            if self._pause_event.is_set():
                t = time.monotonic()
                time.sleep(0.05)
                paused += time.monotonic() - t
                continue
            if due is None or time.monotonic() >= due + paused:
                return paused
            time.sleep(0.01)

    def _run(self) -> None:
        self._step_secs.clear()
        self.actual_speed = None
        last_emit: Optional[float] = None
        due: Optional[float] = None
        try:
            for step in self.service.iter_replay():      # model compute happens here
                paused = self._wait_until(due)
                if paused is None:
                    return
                now = time.monotonic()
                if last_emit is not None:
                    self._step_secs.append(max(1e-6, now - last_emit - paused))
                    self.actual_speed = self.service.window_sec / (sum(self._step_secs) / len(self._step_secs))
                step.speed = self.speed
                step.actual_speed = self.actual_speed
                self.result_queue.put(step)
                last_emit = now
                due = now + self.service.window_sec / self.speed
            self.finished = True
        except Exception as exc:  # surface to the UI instead of dying silently
            self.error = f"{type(exc).__name__}: {exc}"


def _round_sig(x: float, digits: int = 2) -> str:
    """Round to `digits` significant figures for display (e.g. 147.3 -> '150')."""
    if not x or x <= 0:
        return "0"
    return f"{round(x, digits - 1 - int(math.floor(math.log10(x)))):g}"
