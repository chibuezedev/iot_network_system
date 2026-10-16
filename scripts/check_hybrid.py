"""
check_hybrid.py -- parity check between the dashboard's hybrid service and the
Kaggle-exported dashboard_feed.csv (the same check the training notebook passes).

For feed rows whose host appears in replay_flows.csv:
  1. direct: run analyse() on that host's flows from the preceding `lookback`
     windows with window_start = the row's win_ts, and compare
     p_attack_next (tol 1e-4), det_tier and fut_tier with the feed row;
  2. replay: run the service's replay iterator and compare the same fields at
     every recorded window boundary (checks the iterator's slicing/timing).

Usage:  python scripts/check_hybrid.py [--sample N] [--seed S] [--skip-replay]
        (default: every eligible feed row)
Exit code 0 = all match, 1 = mismatch, 2 = LSTM layer unavailable.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from services.hybrid_service import HybridService  # noqa: E402

TOL = 1e-4


def compare(feed_row, got, errors, where):
    p_ok = abs(float(got["p_attack_next"]) - float(feed_row["p_attack_next"])) <= TOL
    d_ok = int(got["det_tier"]) == int(feed_row["det_tier"])
    f_ok = int(got["fut_tier"]) == int(feed_row["fut_tier"])
    if not (p_ok and d_ok and f_ok):
        errors.append(f"[{where}] {feed_row['entity']} @ {feed_row['window_start_utc']}: "
                      f"p_attack_next {got['p_attack_next']:.7f} vs {feed_row['p_attack_next']:.7f}, "
                      f"det_tier {got['det_tier']} vs {feed_row['det_tier']}, "
                      f"fut_tier {got['fut_tier']} vs {feed_row['fut_tier']}")
    return abs(float(got["p_attack_next"]) - float(feed_row["p_attack_next"]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=0, help="check N random eligible rows (0 = all)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--skip-replay", action="store_true")
    args = ap.parse_args()

    svc = HybridService()
    print(f"engine: lstm_available={svc.lstm_available}  window_sec={svc.window_sec:g}  "
          f"lookback={svc.lookback}  horizon={svc.horizon}  t0={svc.t0:.0f}")
    for w in svc.load_warnings:
        print("load warning:", w)
    if not svc.lstm_available:
        print("LSTM layer unavailable:", svc.lstm_error)
        return 2

    flows = svc.replay_flows()
    feed = svc.dashboard_feed()
    hosts = set(flows["dst_ip"].astype(str).str.strip().unique())
    eligible = feed[feed["entity"].isin(hosts)].reset_index(drop=True)
    if eligible.empty:
        print("No feed rows for hosts present in replay_flows.csv -- nothing to check.")
        return 1
    if args.sample and args.sample < len(eligible):
        eligible = eligible.sample(args.sample, random_state=args.seed).reset_index(drop=True)
    print(f"feed rows: {len(feed)}  eligible (host in replay): {len(eligible)}  "
          f"hosts: {eligible['entity'].nunique()}  windows: {eligible['win_ts'].nunique()}")

    # ---- 1. direct analyse() per feed row --------------------------------
    k_all = svc.window_index(flows["ts"].values)
    errors: list[str] = []
    max_dp = 0.0
    for _, row in eligible.iterrows():
        k = int(svc.window_index([row["win_ts"]])[0])
        assert abs(svc.window_start(k) - float(row["win_ts"])) < 1e-6, "win_ts not on the t0 + k*W grid"
        m = (k_all > k - svc.lookback) & (k_all <= k) & (flows["dst_ip"].values == row["entity"])
        res = svc.analyse(flows[m], window_start=float(row["win_ts"]))
        res = res[res["entity"] == row["entity"]]
        if res.empty:
            errors.append(f"[direct] {row['entity']} @ {row['window_start_utc']}: no result")
            continue
        got = res.iloc[0]
        if got["window_start_utc"] != row["window_start_utc"]:
            errors.append(f"[direct] window_start_utc {got['window_start_utc']} vs {row['window_start_utc']}")
        max_dp = max(max_dp, compare(row, got, errors, "direct"))
    print(f"direct analyse(): {len(eligible)} rows, max |dp_attack_next| = {max_dp:.2e}, "
          f"mismatches = {len(errors)}")

    # ---- 2. through the replay iterator -----------------------------------
    if not args.skip_replay:
        want = {(r.entity, float(r.win_ts)): r for r in eligible.itertuples(index=False)}
        n_err_before = len(errors)
        checked, max_dp_r, steps = 0, 0.0, 0
        for step in svc.iter_replay():
            steps += 1
            for got in step.hosts.to_dict("records"):
                key = (got["entity"], float(step.window_start))
                if key in want:
                    checked += 1
                    max_dp_r = max(max_dp_r, compare(pd.Series(want[key]._asdict()), got, errors, "replay"))
        missing = len(want) - checked
        if missing:
            errors.append(f"[replay] {missing} eligible feed rows never produced by the iterator")
        print(f"replay iterator: {steps} windows, {checked} feed rows matched, "
              f"max |dp_attack_next| = {max_dp_r:.2e}, mismatches = {len(errors) - n_err_before}")

    for e in errors[:20]:
        print("MISMATCH", e)
    if errors:
        print(f"FAIL: {len(errors)} mismatches")
        return 1
    print("PASS: p_attack_next (tol 1e-4), det_tier and fut_tier match dashboard_feed.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
