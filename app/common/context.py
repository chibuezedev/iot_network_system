from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from app.live_monitor.engine import SimulationEngine
from models.inference import Spotter, RiskAnalyst


@dataclass
class SessionCounters:
    total_flows: int = 0
    total_attacks: int = 0
    active_alerts: int = 0
    highest_severity_tier: int = 0
    attack_type_counts: dict = field(default_factory=dict)
    severity_tier_counts: dict = field(default_factory=lambda: {i: 0 for i in range(5)})
    flow_rate_history: list = field(default_factory=list)   # (t, flows-per-tick)
    attack_rate_history: list = field(default_factory=list)  # (t, attacks-per-tick)

    def reset(self) -> None:
        self.total_flows = 0
        self.total_attacks = 0
        self.active_alerts = 0
        self.highest_severity_tier = 0
        self.attack_type_counts = {}
        self.severity_tier_counts = {i: 0 for i in range(5)}
        self.flow_rate_history = []
        self.attack_rate_history = []


class AppContext:
    """Everything a screen needs, handed down from main.py. Keeps screens
    decoupled from each other -- they only ever talk to this object."""

    def __init__(self, user_row, spotter: Spotter, risk_analyst: RiskAnalyst, engine: SimulationEngine):
        self.user_row = user_row
        self.username: str = user_row["username"]
        self.role: str = user_row["role"]
        self.spotter = spotter
        self.risk_analyst = risk_analyst
        self.engine = engine
        self.counters = SessionCounters()
        self.session_id: Optional[int] = None
        self.alert_confidence_threshold: float = 0.6
        self.on_logout: Optional[Callable[[], None]] = None
        self.navigate: Optional[Callable[[str], None]] = None
        self.recent_events: list = []  # in-memory ring buffer for the Live Monitor table
        self.result_listeners: list[Callable] = []  # views wanting every new SimResult
        self.max_recent_events = 500

    def is_admin(self) -> bool:
        return self.role == "administrator"
