"""
Simulation engine. Runs the replay + inference loop on a background thread
and pushes results onto a thread-safe queue.Queue. The Tk main thread drains
the queue via root.after() polling -- Tkinter widgets are NEVER touched from
this thread directly, per the standard safe pattern for Tk + background
workers.
"""
from __future__ import annotations

import queue
import random
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import pandas as pd

from models.inference import Spotter, RiskAnalyst, severity_tier_index

ATTACKER_IPS = [f"203.0.113.{n}" for n in (5, 12, 19, 33, 47, 58, 71, 88)]


@dataclass
class SimResult:
    sim_time: str
    device_name: str
    device_ip: str
    src_ip: str
    protocol: str
    predicted_label: str
    detection_confidence: float
    severity_tier: int
    severity_label: str
    severity_confidence: float
    is_attack: bool
    feature_snapshot: str


class SimulationEngine:
    def __init__(self, feed_path: str, spotter: Spotter, risk_analyst: RiskAnalyst):
        self.feed = pd.read_csv(feed_path)
        self.spotter = spotter
        self.risk_analyst = risk_analyst
        self.result_queue: "queue.Queue[SimResult]" = queue.Queue()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self.speed_multiplier = 5.0
        self._burst_rows_remaining = 0
        self._sim_clock = datetime.now()

    # -- controls, all safe to call from the main thread ------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            self._pause_event.clear()
            return
        self._stop_event.clear()
        self._pause_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def pause(self) -> None:
        self._pause_event.set()

    def resume(self) -> None:
        self._pause_event.clear()

    def stop(self) -> None:
        self._stop_event.set()

    def set_speed(self, multiplier: float) -> None:
        self.speed_multiplier = max(0.1, multiplier)

    def inject_attack_burst(self, n_rows: int = 25) -> None:
        self._burst_rows_remaining = n_rows

    # -- worker thread body -------------------------------------------------
    def _run(self) -> None:
        attack_rows = self.feed[self.feed["true_label"] != "BenignTraffic"].reset_index(drop=True)
        benign_rows = self.feed[self.feed["true_label"] == "BenignTraffic"].reset_index(drop=True)
        rng = random.Random(1234)

        while not self._stop_event.is_set():
            if self._pause_event.is_set():
                time.sleep(0.1)
                continue

            if self._burst_rows_remaining > 0 and len(attack_rows) > 0:
                row = attack_rows.iloc[rng.randrange(len(attack_rows))]
                self._burst_rows_remaining -= 1
            else:
                pool = self.feed
                row = pool.iloc[rng.randrange(len(pool))]

            try:
                det = self.spotter.predict_row(row)
                sev = self.risk_analyst.predict_row(row)
            except Exception as exc:  # keep the worker alive even on a bad row
                time.sleep(0.05)
                continue

            self._sim_clock += timedelta(milliseconds=rng.randint(150, 900))
            tier_idx = severity_tier_index(sev.label, self.risk_analyst)
            is_attack = det.label != "BenignTraffic"
            src_ip = rng.choice(ATTACKER_IPS) if is_attack else row.get("device_ip", "192.168.1.10")
            snapshot = row.drop(labels=["true_label"], errors="ignore").to_json()

            result = SimResult(
                sim_time=self._sim_clock.strftime("%H:%M:%S.%f")[:-3],
                device_name=str(row.get("device_name", "Unknown Device")),
                device_ip=str(row.get("device_ip", "192.168.1.10")),
                src_ip=src_ip,
                protocol=rng.choice(["TCP", "UDP", "ICMP", "HTTP", "DNS"]),
                predicted_label=det.label,
                detection_confidence=det.confidence,
                severity_tier=tier_idx,
                severity_label=sev.label,
                severity_confidence=sev.confidence,
                is_attack=is_attack,
                feature_snapshot=snapshot,
            )
            self.result_queue.put(result)

            base_interval = 0.2  # 1x = one row / 200ms, per spec
            jitter = rng.uniform(0.85, 1.15)
            interval = (base_interval / self.speed_multiplier) * jitter
            time.sleep(max(0.002, interval))
