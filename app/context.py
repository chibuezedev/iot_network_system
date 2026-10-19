"""Everything a Vigil screen needs, handed down from main.py. Screens only
talk to this object, never to each other."""
from __future__ import annotations

from collections import deque
from typing import Callable, Optional

from services.hybrid_service import AlertTracker, HybridReplayEngine, HybridService

HISTORY_WINDOWS = 120   # per-host replay history kept for sparklines


class AppContext:
    def __init__(self, user_row, hybrid: Optional[HybridService], hybrid_error: Optional[str] = None):
        self.user_row = user_row
        self.username: str = user_row["username"]
        self.role: str = user_row["role"]
        self.hybrid = hybrid
        self.hybrid_error = hybrid_error
        self.engine: Optional[HybridReplayEngine] = HybridReplayEngine(hybrid) if hybrid else None
        self.tracker = AlertTracker()
        self.run_id: Optional[int] = None
        self.last_step = None                       # latest ReplayStep
        # host -> deque of dicts (window_start, window_start_utc, p_attack_next, p_severe_next, alert, complete)
        self.host_history: dict[str, deque] = {}
        self.step_listeners: list[Callable] = []    # called with (step, new_alerts)
        self.navigate: Optional[Callable[[str], None]] = None
        self.on_logout: Optional[Callable[[], None]] = None
        self.toast: Callable[[str, str, str], None] = lambda title, msg, kind="info": None

    def is_admin(self) -> bool:
        return self.role == "administrator"

    def reset_run(self) -> None:
        self.tracker.reset()
        self.last_step = None
        self.host_history.clear()

    def start_run(self) -> None:
        """Begin a new replay run: fresh alert de-duplication, history and run id."""
        from app.auth import db
        self.reset_run()
        self.run_id = db.next_hybrid_run_id()

    def record_step(self, step) -> None:
        self.last_step = step
        if step.hosts.empty:
            return
        lstm = step.lstm_available and "p_attack_next" in step.hosts
        for r in step.hosts.to_dict("records"):
            h = self.host_history.setdefault(r["entity"], deque(maxlen=HISTORY_WINDOWS))
            h.append(dict(window_start=step.window_start, window_start_utc=step.window_start_utc,
                          p_attack_next=r.get("p_attack_next") if lstm else None,
                          p_severe_next=r.get("p_severe_next") if lstm else None,
                          alert=r.get("alert") if lstm else None, complete=step.lookback_complete))
