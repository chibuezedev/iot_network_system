# SentinelIoT

**ML-Based Network Surveillance System for Anomaly Detection and Predictive Analytics of Cyber Threats in the IoT**

SentinelIoT is a desktop application that demonstrates a two-model machine learning pipeline for IoT network security: one model detects and classifies attack traffic in real time, a second model scores the severity and likely risk tier of whatever is detected. The app replays labeled network flow data through both models at adjustable speed, so the full detection-to-risk-scoring pipeline can be watched live rather than read off a static report.

This repository is the desktop deployment layer for a PhD research project. The trained models themselves come from a separate Kaggle notebook (not included here, see [Model Artifacts](#model-artifacts) below).

---

## What it does

- **Detects attacks** in IoT network flow data across 34 CICIoT2023 attack categories plus benign traffic, using a GPU-trained XGBoost classifier ("Spotter").
- **Scores severity** of detected traffic into 5 risk tiers (Normal, Reconnaissance, Access/Compromise, High DoS/DDoS, Critical Ransomware), using a second XGBoost classifier ("Risk Analyst") trained on ToN_IoT connection data.
- **Simulates a live network feed** by replaying held-out test rows through both models on a background thread, at a speed you control (1x to 20x), with an "Inject Attack Burst" control to force a wave of high-severity detections on demand.
- **Logs everything** to a local SQLite database, so sessions, flows, and flagged events persist across restarts and roll up into all-time analytics.
- **Explains itself**: the Model Info screen shows each model's real held-out test metrics and documents exactly how the two models' different schemas are bridged in the live demo (see [Architecture notes](#architecture-notes)).

---

## Screens

| Screen | Purpose |
|---|---|
| Dashboard | Session summary cards, benign-vs-attack breakdown, top attack types, live flow sparkline, all-time footer |
| Live Monitor | Start/pause/stop the simulation, adjust speed, inject an attack burst, watch verdicts stream in |
| Alerts | Filter flagged events by severity or attack type, inspect a row's full feature vector, export to CSV |
| Analytics & Reports | All-time stats, attack/severity distribution charts, session history, one-click HTML report export |
| Model Info | Both models' purpose and real test-set metrics, plus the schema-bridging disclosure |
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
2. Land on Dashboard in its zeroed-out state.
3. Go to Live Monitor, hit **Start** at 5x. Rows start streaming within a second.
4. Let it run for a bit to show a natural mix of benign and low-severity traffic.
5. Hit **Inject Attack Burst** to reliably trigger high-severity detections.
6. Switch to Alerts, filter by severity, double-click a row to inspect its full feature vector, export to CSV.
7. Switch to Analytics & Reports, generate a downloadable HTML session report.
8. Open Model Info to walk through the real training metrics and the note on how the two models' schemas are bridged for the live demo.

Runs fully offline, no network connection required.

---

## Architecture notes

**Two models, two datasets, no shared schema.** Spotter is trained on CICIoT2023-style flow features (46 numeric columns). Risk Analyst is trained on ToN_IoT-style connection features (8 numeric + 3 categorical columns). There is no principled row-for-row mapping between the two.

The approach used here, chosen for methodological transparency over a fabricated cross-dataset mapping, is **independent parallel slice, shared synthetic timeline**: each row of the simulation feed carries a full, valid feature vector for Spotter and a full, valid feature vector for Risk Analyst, sampled independently of one another but assigned the same position in the simulated replay. The two verdicts shown side by side in Live Monitor are two independent models' opinions about traffic at the same simulated moment, not one model's output feeding the other, and not one model's features reused for the other. This is stated explicitly on the Model Info screen.

**"Predictive analytics" is risk/severity scoring, not literal time-series forecasting.** Neither public CICIoT2023 nor ToN_IoT Kaggle derivative preserves real packet or flow timestamps, which ruled out literal sequence-based forecasting (e.g. an LSTM predicting the next event in a time series). The predictive component was reframed as severity and risk-tier scoring on each detected flow, a disclosed methodological decision rather than a hidden workaround.

**Training.** Both models are XGBoost classifiers trained on GPU (`device='cuda'`), with per-class row capping applied to the larger dataset to control training time and class imbalance. Full training details, metrics, and charts live in the companion Kaggle notebook (not part of this repository).

---

## Project structure

```
sentineliot_app/
  main.py                   entry point
  app/
    auth/                   login, session handling, SQLite user DB
    common/                 theme, shared widgets, app context, paths
    dashboard/               Dashboard screen
    live_monitor/            Live Monitor screen + SimulationEngine
    alerts/                  Alerts screen
    analytics/               Analytics & Reports screen
    model_info/              Model Info screen
    user_management/         User Management screen
    settings/                Settings screen
    shell.py                 app shell, navigation, result polling, toasts
  models/
    inference.py             Spotter / RiskAnalyst model wrappers
  model_artifacts/           trained model files (not tracked, see above)
  data/
    simulation_feed.csv      labeled replay feed (not tracked, see above)
  scripts/
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