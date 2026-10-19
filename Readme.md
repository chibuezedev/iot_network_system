# Vigil

**Intelligent IoT network surveillance: anomaly detection and predictive threat analytics with an RF–LSTM hybrid**

Vigil is the desktop dashboard for a PhD research project on ML-based IoT network surveillance. It runs an
**RF–LSTM hybrid** over recorded ToN_IoT network traffic:

- a **Random Forest** labels every flow, one at a time;
- an **LSTM** reads each host's recent time windows and
  - **detects** the severity tier of the current window, and
  - **forecasts** the highest severity tier within the next horizon.

Traffic is replayed in recorded capture-time order, and every time Vigil shows is the recorded time. The models
were trained in a separate Kaggle notebook; see [Model artifacts](#model-artifacts).

---

## Screens

| Screen | Purpose |
|---|---|
| Overview | Model status (hybrid or RF-only fallback), training-run facts, the replay file, the latest recorded window, alert counts for the current run, recent alerts and a risk sparkline per host |
| Live Replay | Window-by-window replay of `replay_flows.csv`: a recorded-time clock, play/pause/stop, requested vs actual speed, and one card per host (detected tier, forecast tier, P(attack ahead), P(escalation ahead), RF verdict mix, alert badge) |
| Alerts | RF–LSTM alerts only. Filter by run, level, type (Detected / Predicted), host and recorded time; open a detail drawer; export to CSV |
| Risk Timeline | Per host: true tier and the hybrid's predicted risk over recorded time, with the dashed alert thresholds and a test-block selector |
| Model Evaluation | Detection, forecast, early-warning, flow-level, efficiency and coverage tables, the figure gallery, an XGBoost tab, and HTML report export |
| About the model | Architecture diagram, dataset, task definition, alert rules and limitations |
| Settings | Light/dark theme, default replay speed, artifacts folder, and a button that re-runs the parity check |
| Users | Administrators only: add, edit or deactivate users, change roles, force password resets |

Badges: a **filled** badge means *Detected* (the current window is an attack tier). An **outlined** badge means
*Predicted* (a forecast for the horizon ahead, not yet observed).

---

## Getting started

### Requirements

- Python 3.10 (developed on 3.10.11)
- `tkinter` from the system Python (on Windows, the python.org installer with "tcl/tk and IDLE")

### Install

```bash
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

The LSTM layer needs `torch`; the CPU build is enough:
`pip install torch --index-url https://download.pytorch.org/whl/cpu`.

If you have pip 23.x, install `typing-extensions sympy networkx fsspec jinja2 filelock` from PyPI first. Without
torch, Vigil still runs and shows the RF per-flow layer, with a notice that the LSTM layer is unavailable.

`scikit-learn` is pinned to the version the pickles were saved with. A mismatch is reported as an
`InconsistentVersionWarning` and is not hidden.

### Model artifacts

**Where they come from.** The RF–LSTM training notebook on Kaggle writes its outputs to a folder named
`artifacts_rf_lstm/`. Download it as the notebook's output zip from the *Output* tab.

**Where to put them.** Unzip at the project root, so the folder sits next to `main.py` and contains `models/`,
`data/`, `reports/` and `figures/` directly. If the zip has an extra top-level folder, move its contents up one
level. You can also choose another folder under *Settings → Artifacts folder*; it is loaded at the next start.

```
artifacts_rf_lstm/
  models/   sentinel_inference.py, rf_flow.joblib, hybrid_rf_lstm.pt, window_scaler.joblib,
            preprocessing.json (window/lookback/horizon/t0, category maps, thresholds, hosts), baselines
  data/     replay_flows.csv (recorded test flows), dashboard_feed.csv (every test window, per host)
  reports/  model_comparison.csv, early_warning.csv, flow_level_comparison.csv, efficiency.csv, ...
  figures/  *.png
README.txt  dataset description (Vigil reads the dataset size from its "Data:" line)
```

`artifacts_rf_lstm/` is git-ignored. Vigil reads every threshold, window setting, host, attack type, time range
and metric from these files, so a new run with the same file names and schema drops in without code changes.

After replacing the folder, re-run the parity check, either from *Settings* or with:

```bash
python scripts/check_hybrid.py
```

It recomputes the hybrid's outputs for every `dashboard_feed.csv` row inside the replay's recorded time range and
compares them with the notebook's values: `p_attack_next` within 1e-4, and `det_tier` and `fut_tier` exactly.

### First sign-in

On first run Vigil creates `users.db` (SQLite) with one account, `admin` / `ChangeMe!2024`. You must set a new
password at first sign-in. Existing `users.db` files keep working.

### Run

```bash
python main.py
```

Vigil runs fully offline.

---

## How it works

**Pipeline.** `services/hybrid_service.py` loads `SentinelEngine` from `sentinel_inference.py` once; the training
notebook imports the same file. The service then:

1. walks `replay_flows.csv` in `ts` order;
2. at each window boundary `t0 + k·window_sec`, calls `analyse(flows of the last lookback windows,
   window_start=<recorded start>)`;
3. de-duplicates the engine's alert levels, so each host raises one alert per level until its level changes.

**Partial lookback.** A window is *complete* when all `lookback` windows before it lie inside the replay file's
recorded range. Earlier windows are shown greyed out, with a note, and never raise alerts.

**Alert rules** (`sentinel_inference.alert_level`, thresholds from `preprocessing.json`):

| Level | Raised when |
|---|---|
| CRITICAL | DoS/DDoS/ransomware detected now, or ransomware-level activity forecast |
| HIGH | compromise detected now, or P(escalation ahead) at or above the HIGH threshold |
| WARNING | reconnaissance detected now, or P(any attack ahead) at or above the WARNING threshold |

**Research-integrity rules.**
- Event times come only from the data (`ts`, `win_ts`, `window_start_utc`). Wall-clock time only paces the replay
  and rate-limits notifications.
- Hosts are the recorded IP addresses; no device names are attached.
- Every metric shown is read from the report CSVs.

**Previous system.** The earlier XGBoost system (CICIoT2023 "Spotter" and ToN_IoT "Risk Analyst", per-flow only)
has been retired from the product and moved to `legacy/` (see `legacy/README.md`). XGBoost now appears only on the
Model Evaluation screen, in two places:
- the XGBoost baseline rows from the same ToN_IoT experiment;
- the previous CICIoT2023 system's reference metrics (`model_artifacts/spotter_metrics.json`), labelled as a
  different dataset and not directly comparable.

---

## Project structure

```
main.py                     entry point (CustomTkinter window, login -> shell)
app/
  auth/                     login screen, password reset dialog, SQLite user/alert store (db.py)
  brand/                    logo drawing code (logo.py) and generated assets (PNG, .ico)
  screens/                  overview, live_replay, alerts, risk_timeline, evaluation, about, settings, users
  ui/                       design tokens, theme switching, widget kit, matplotlib theming
  shell.py                  sidebar navigation, replay queue -> alerts pipeline
  context.py                state shared by the screens
  common/paths.py           resource / user-data path resolution (PyInstaller-ready)
services/
  hybrid_service.py         SentinelEngine wrapper, replay iterator, alert de-duplication, replay worker
  reports.py                report CSVs, figures, previous-system metrics
  report_export.py          Model Evaluation -> self-contained HTML report
  run_info.py               training-run facts from README.txt / preprocessing.json
  prefs.py                  theme, default speed, artifacts folder (prefs.json)
scripts/
  check_hybrid.py           parity check against dashboard_feed.csv
  make_brand_assets.py      regenerates app/brand/assets/
model_artifacts/
  spotter_metrics.json      previous system's reference metrics (shown as-is)
legacy/                     pre-Vigil XGBoost system and old UI (not imported by the app)
```

---

## Packaging as a standalone binary

```bash
pip install pyinstaller
pyinstaller --name Vigil --onedir --icon app/brand/assets/vigil.ico ^
  --add-data "artifacts_rf_lstm;artifacts_rf_lstm" --add-data "model_artifacts;model_artifacts" ^
  --add-data "app/brand/assets;app/brand/assets" --add-data "scripts;scripts" main.py
```

(On macOS/Linux use `:` instead of `;` in `--add-data`, and `\` for line continuation.) A frozen build stores
`users.db` and `prefs.json` in `~/.vigil`.

---

## Status

Research prototype for a PhD thesis. It replays recorded testbed traffic and is not a live network sensor. See
*About the model → Limitations* in the app for what the current results can and cannot show.
