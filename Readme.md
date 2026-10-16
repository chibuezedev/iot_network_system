# SentinelIoT

**ML-Based Network Surveillance System for Anomaly Detection and Predictive Analytics of Cyber Threats in the IoT**

SentinelIoT is a desktop application for IoT network surveillance. Its primary model is an **RF–LSTM hybrid** trained on ToN_IoT network flows ordered by their recorded Zeek capture time: a Random Forest labels each flow, and an LSTM over a host's recent time windows **detects** the severity tier of the current window and **forecasts** the highest severity tier within the next horizon (the window, lookback and horizon are read from `preprocessing.json`). The app replays recorded test traffic through the hybrid in recorded order, at an adjustable speed, and always shows the recorded capture time.

The earlier two-model **XGBoost** system (Spotter + Risk Analyst) is kept as a per-flow **baseline**.

This repository is the desktop deployment layer for a PhD research project. The trained models come from separate Kaggle notebooks (not included here; see [Model artifacts](#model-artifacts) below).

---

## What it does

- **RF–LSTM hybrid (primary).** It detects the current window's severity tier and forecasts P(any attack) and P(escalation to compromise/DoS) for the horizon ahead, per destination host IP. Alerts are NORMAL / WARNING / HIGH / CRITICAL with a reason that starts "Detected: …" or "Predicted: …", both from the engine in `sentinel_inference.py`.
- **Replay of recorded traffic.** `replay_flows.csv` is processed in `ts` order and evaluated at each recorded window boundary. The screen is labelled "Replay of recorded ToN_IoT traffic (requested ×N, actual ~×M speed)". The actual speed is measured, because model compute can make the replay slower than requested. Only the speed is controlled by the user; every time shown comes from the data.
- **Model comparison.** It shows the hybrid, standalone LSTM, standalone RF, the XGBoost baseline and persistence, as read from the run's report CSVs, together with the saved figures.
- **Legacy XGBoost baseline.** Per-flow attack detection across 34 CICIoT2023 categories ("Spotter") and per-flow severity tiering on ToN_IoT connection data ("Risk Analyst"). Neither model forecasts. Its Live Monitor demo samples rows at random from a non-chronological feed.
- **Logs everything** to a local SQLite database: legacy sessions and events, plus hybrid alerts (which carry the recorded window time).

---

## Screens

| Screen | Purpose |
|---|---|
| Dashboard | Legacy XGBoost demo session summary (non-chronological sample) |
| Hybrid Replay | RF–LSTM replay of recorded ToN_IoT traffic. Per host: detected tier, forecast tier, both forecast probabilities, RF per-flow verdict counts, alert level and reason. The recorded window time is shown in large type. |
| Risk Timeline | For a chosen host, true tier vs. hybrid detected tier, and P(any attack) / P(escalation) with the dashed alert thresholds, over recorded time (`dashboard_feed.csv`) |
| Alerts | Hybrid tab: one alert per host per level change. Filled badge = Detected, outlined badge = Predicted. Legacy tab: the original XGBoost alert table |
| Model Comparison | Detection and forecast tables, flow-level, early-warning, efficiency and split-coverage tables, plus the figures, all read from `artifacts_rf_lstm/reports` and `figures` |
| Baseline: XGBoost | The original Live Monitor, labelled "Baseline: XGBoost (CICIoT2023, per-flow, no forecasting)" |
| Analytics & Reports | All-time stats for the legacy demo, session history, HTML report export |
| Model Info | Purpose of all three models, the hybrid's test-period metrics (from the CSVs), and how detection, prediction and time differ between the two systems |
| User Management | Add/deactivate users, change roles, force password resets (administrator only) |
| Settings | Theme, alert sound, alert confidence threshold, default simulation speed |

---

## Getting started

### Requirements

- Python 3.10+
- `tkinter` available as a system package (it does **not** install via pip):
  - Ubuntu/Debian: `sudo apt-get install python3-tk`
  - Fedora: `sudo dnf install python3-tkinter`
  - macOS (python.org installer): bundled; Homebrew Python needs `brew install python-tk`
  - Windows: bundled with the python.org installer (check "tcl/tk and IDLE" during install)

### Install

```bash
git clone <this-repo-url>
cd sentineliot_app
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Model artifacts

`model_artifacts/` and `data/simulation_feed.csv` are not tracked in this repository (see `.gitignore`) because they're large, binary, and derived from the training notebook rather than written by hand. Before running the app, place the following files into `model_artifacts/`:

```
model_artifacts/
  detection_model_xgboost.json
  detection_label_encoder.joblib
  detection_feature_columns.json
  detection_class_names.json
  severity_model_xgboost.json
  severity_categorical_encoders.joblib
  severity_feature_columns.json
  severity_class_names.json
  severity_tier_mapping.json
```

And a labeled feed file at `data/simulation_feed.csv` (same column layout the training notebook exports: the 46 Spotter feature columns + the Risk Analyst feature columns + a `true_label` column + `device_name` / `device_ip` display columns).

No application code needs to change to swap these in. `models/inference.py` only depends on the filenames and the column-order files above, not on how the models were produced.

#### RF–LSTM hybrid artifacts

**Where they come from.** The RF–LSTM training notebook on Kaggle writes its outputs to a folder named `artifacts_rf_lstm/`. Download it as the notebook's output zip from the Kaggle notebook's *Output* tab.

**Where to put them.** Unzip at the project root, so that the folder sits next to `main.py` and contains `models/`, `data/`, `reports/` and `figures/` directly (for example `artifacts_rf_lstm/models/preprocessing.json`). If the zip has an extra top-level folder, move its contents up one level.

**Not in git.** `artifacts_rf_lstm/` is listed in `.gitignore`. The current artifacts are a development run (2 dataset files, normal and DoS traffic only) and will be replaced by the full 23-file run. Replace the whole folder; the app needs no code changes as long as the file names and schema stay the same. After replacing it, re-run `python scripts/check_hybrid.py`.

The hybrid reads everything from `artifacts_rf_lstm/` (see `artifacts_rf_lstm/README.txt`):

```
artifacts_rf_lstm/
  models/   sentinel_inference.py, rf_flow.joblib, hybrid_rf_lstm.pt, window_scaler.joblib,
            preprocessing.json (window/lookback/horizon/t0, category maps, alert thresholds), baselines
  data/     replay_flows.csv (raw test flows), dashboard_feed.csv (every test window, per host)
  reports/  model_comparison.csv, flow_level_comparison.csv, early_warning.csv, efficiency.csv, ...
  figures/  *.png
```

The app imports `sentinel_inference.py` and uses its `SentinelEngine`, `alert_level` and `TIER_NAMES` directly, so features and alert levels are computed exactly as they were in training. Thresholds, window settings, hosts, attack types and time ranges all come from these files, so a new run with the same file names and schema can replace the folder without code changes. Afterwards, re-run the parity check:

```bash
python scripts/check_hybrid.py     # analyse() vs dashboard_feed.csv: p_attack_next (tol 1e-4), det_tier, fut_tier
```

The LSTM layer needs `torch` (CPU build is fine). Without it, Hybrid Replay shows the RF per-flow layer and a message that the LSTM layer is unavailable. `scikit-learn` is pinned to the version the pickles were saved with; a mismatch is reported as an `InconsistentVersionWarning`, not hidden.

### Seed the admin account

On first run, the app creates `users.db` (SQLite) with one seeded account:

```
username: admin
password: ChangeMe!2024
```

You'll be forced to set a new password on first login. To start over, delete `users.db` and relaunch.

### Run

```bash
python3 main.py
```

---

## Demo flow

1. Log in as `admin` (or create an `analyst` account under User Management).
2. Open **Hybrid Replay**, choose a speed and press **Start**. The recorded window time advances through the test period, and each host shows its detected tier, forecast tier and both forecast probabilities.
3. Open **Alerts**. In the hybrid tab, filled badges are detections and outlined badges are predictions. Filter by level or type and export to CSV.
4. Open **Risk Timeline**, pick a host and compare the true tier with the hybrid's predicted risk and thresholds (switch on the logit scale to separate values near 1).
5. Open **Model Comparison** for the detection and forecast tables and the saved figures.
6. To show the baseline, open **Baseline: XGBoost**, press **Start** and optionally **Inject Attack Burst**. This is the legacy non-chronological demo.
7. Open **Model Info** to walk through what each system does and does not do.

Runs fully offline, no network connection required.

---

## Architecture notes

**RF–LSTM hybrid: recorded time, real hosts.**
- The hybrid is trained on the ToN_IoT processed network dataset, with flows ordered by their recorded Zeek capture time (`ts`). Flows are aggregated into fixed windows per destination host.
- Layer 1 is a Random Forest that labels each flow. Layer 2 is an LSTM that reads the last `lookback` windows (window statistics plus the RF evidence) and has two heads:
  - **detection**: the severity tier of the current window;
  - **forecast**: the highest severity tier within the next `horizon` windows.
- In the dashboard, `services/hybrid_service.py` loads the engine once. It walks `replay_flows.csv` in `ts` order, and at each window boundary `t0 + k·window_sec` it calls `SentinelEngine.analyse(flows of the last lookback windows, window_start=<recorded start>)`.
- Timestamps are never generated. Wall-clock time is used only to pace an accelerated replay.
- Hosts are the IP addresses recorded in the data, with no device names attached.
- `scripts/check_hybrid.py` checks that the dashboard reproduces the notebook's `dashboard_feed.csv`.

**What the current artifacts can and cannot show.** These artifacts come from a development run. The test period's traffic types are listed in `reports/split_coverage.csv`, and `reports/early_warning.csv` evaluates no onset/escalation events. So the app shows detection and forecast scores for the test period but makes no early-warning claim. The views handle runs that contain "Predicted" alerts and other attack types without code changes.

**Legacy XGBoost baseline: per-flow only.**
- CICIoT2023 and the ToN_IoT train/test file have no usable timestamps, so Spotter (CICIoT2023, 46 numeric features) and Risk Analyst (ToN_IoT connection features) are per-flow classifiers: no sequence model and no forecasting.
- Their Live Monitor demo samples rows at random from `data/simulations_feed.csv`. That feed pairs unrelated rows from the two datasets, each row carrying a native feature set for each model, and assigns generated times, source IPs and device names for display.
- That feed is labelled "Legacy XGBoost demo (non-chronological sample)" and never drives any hybrid timeline or forecast.

**Training.** The XGBoost models were trained on GPU (`device='cuda'`) in a companion Kaggle notebook. The RF–LSTM hybrid and its comparison models were trained in a separate Kaggle notebook that exports `artifacts_rf_lstm/`.

---

## Project structure

```
sentineliot_app/
  main.py                   entry point
  app/
    auth/                   login, session handling, SQLite user DB
    common/                 theme, shared widgets, app context, paths
    dashboard/               Dashboard screen (legacy demo)
    hybrid_replay/           Hybrid Replay screen (RF-LSTM, recorded time)
    risk_timeline/           Risk Timeline screen (RF-LSTM, dashboard_feed.csv)
    model_comparison/        Model Comparison screen (report CSVs + figures)
    live_monitor/            Baseline: XGBoost screen + SimulationEngine (legacy demo)
    alerts/                  Alerts screen (hybrid + legacy tabs)
    analytics/               Analytics & Reports screen
    model_info/              Model Info screen
    user_management/         User Management screen
    settings/                Settings screen
    shell.py                 app shell, navigation, result polling, toasts
  services/
    hybrid_service.py        RF-LSTM service: SentinelEngine, replay iterator, alert de-duplication
    reports.py               reads artifacts_rf_lstm/reports/*.csv and figures
  models/
    inference.py             Spotter / RiskAnalyst model wrappers (legacy baseline)
  model_artifacts/           legacy XGBoost model files
  artifacts_rf_lstm/         RF-LSTM hybrid artifacts (models, data, reports, figures)
  data/
    simulations_feed.csv     legacy non-chronological demo feed
  scripts/
    check_hybrid.py          parity check: dashboard hybrid vs dashboard_feed.csv
    generate_placeholder_artifacts.py   generates dummy artifacts for plumbing tests
  requirements.txt
```

---

## Packaging as a standalone binary

All paths resolve through `app/common/paths.py`, so the project is PyInstaller-ready:

```bash
pip install pyinstaller
pyinstaller --name SentinelIoT --onedir \
  --add-data "model_artifacts:model_artifacts" \
  --add-data "data:data" \
  main.py
```

(Use `;` instead of `:` in `--add-data` on Windows.)

---

## Status

Research prototype built as part of a PhD thesis on ML-based IoT network surveillance. Predictions are only meaningful once real trained artifacts (not the placeholder set) are in place. Not intended for production deployment on live network traffic.