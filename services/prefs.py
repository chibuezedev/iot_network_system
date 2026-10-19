"""
prefs.py -- small per-machine preferences (theme, default replay speed,
artifacts folder), stored as JSON next to users.db. Missing or unreadable
file -> defaults; nothing here is research data.
"""
from __future__ import annotations

import json
import os
from typing import Any

from app.common.paths import user_data_path

PREFS_PATH = user_data_path("prefs.json")
DEFAULTS: dict[str, Any] = {
    "theme": "dark",            # "dark" | "light"
    "replay_speed": 60,
    "artifacts_dir": None,      # None -> <project>/artifacts_rf_lstm
}


def load() -> dict:
    out = dict(DEFAULTS)
    try:
        with open(PREFS_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            out.update({k: v for k, v in data.items() if k in DEFAULTS})
    except (OSError, ValueError):
        pass
    return out


def get(key: str) -> Any:
    return load().get(key, DEFAULTS.get(key))


def set(key: str, value: Any) -> None:  # noqa: A001 -- module-level API: prefs.set(...)
    data = load()
    data[key] = value
    tmp = PREFS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    os.replace(tmp, PREFS_PATH)
