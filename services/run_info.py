"""
run_info.py -- facts about the loaded artifacts run, read from the files the
Kaggle notebook exported (README.txt, preprocessing.json, replay_flows.csv).
Nothing is typed in; anything the files do not state is returned as None.
"""
from __future__ import annotations

import os
import re
from typing import Optional

from services.hybrid_service import ARTIFACT_DIR, HybridService

README_PATH = os.path.join(ARTIFACT_DIR, "README.txt")
_DATA_RE = re.compile(r"Data:\s*(?P<name>.+?)\s*\((?P<files>[\d,]+)\s+files?,\s*(?P<flows>[\d,]+)\s+flows\)",
                      re.S)


def readme_facts() -> dict:
    """Dataset name, file and flow counts from the 'Data:' line of README.txt."""
    out = {"dataset": None, "files": None, "flows": None, "timestamp_note": None}
    try:
        text = open(README_PATH, encoding="utf-8").read()
    except OSError:
        return out
    m = _DATA_RE.search(text)
    if m:
        out["dataset"] = " ".join(m.group("name").split())
        out["files"] = int(m.group("files").replace(",", ""))
        out["flows"] = int(m.group("flows").replace(",", ""))
    m2 = re.search(r"ordered by the recorded\s+(.+?\(ts\))", text, re.S)
    if m2:
        out["timestamp_note"] = "ordered by the recorded " + " ".join(m2.group(1).split())
    return out


def split_description(svc: HybridService) -> Optional[str]:
    cfg = svc.cfg
    mode = cfg.get("split_mode")
    if not mode:
        return None
    c = cfg.get("config", {})
    if mode == "blocked" and c.get("BLOCK_HOURS") and c.get("BLOCK_PATTERN"):
        minutes = float(c["BLOCK_HOURS"]) * 60
        return f"blocked: {minutes:g}-minute blocks repeating {' / '.join(c['BLOCK_PATTERN'])}"
    if mode == "chrono" and c.get("CHRONO_FRACS"):
        fr = c["CHRONO_FRACS"]
        return f"chronological: first {fr[0]:.0%} train, next {fr[1]:.0%} validation, rest test"
    return str(mode)


def replay_summary(svc: HybridService) -> dict:
    flows = svc.replay_flows()
    first, last = svc.replay_windows()
    return dict(n_flows=len(flows), n_hosts=int(flows["dst_ip"].nunique()), first_k=first, last_k=last,
                n_windows=last - first + 1, start_utc=svc.to_utc(svc.window_start(first)),
                end_utc=svc.to_utc(svc.window_start(last)),
                first_complete_utc=svc.to_utc(svc.window_start(first + svc.lookback - 1))
                if last - first + 1 >= svc.lookback else None)
