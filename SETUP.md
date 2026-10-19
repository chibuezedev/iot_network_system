# SETUP.md -- Vigil

Step-by-step setup for the Vigil desktop dashboard (RF–LSTM hybrid, PhD research project). Readme.md explains
what each screen does and how the pipeline works.

## 1. System requirements

- Python 3.10 (developed on 3.10.11)
- `tkinter` from the system Python. On Windows it comes with the python.org installer; tick "tcl/tk and IDLE".

## 2. Install dependencies

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

If the `torch` line fails, install the CPU build directly:
`pip install torch --index-url https://download.pytorch.org/whl/cpu`.

With pip 23.x, first run `pip install typing-extensions sympy networkx fsspec jinja2 filelock`. Without torch,
Vigil runs in RF-only mode and says so on every screen that needs the LSTM layer.

## 3. Place the RF–LSTM artifacts

1. Download the RF–LSTM Kaggle notebook's output zip (*Output* tab).
2. Unzip it at the project root as `artifacts_rf_lstm/`, so it contains `models/`, `data/`, `reports/`,
   `figures/` and `README.txt`.

The folder is git-ignored. To use a folder elsewhere, choose it under *Settings → Artifacts folder* and restart.

## 4. Check the artifacts

```bash
python scripts/check_hybrid.py
```

This must print `PASS`. It confirms the dashboard computes exactly what the notebook exported. The same check is
available in the app under *Settings → Re-run parity check*.

## 5. Run

```bash
python main.py
```

On first run `users.db` is created with `admin` / `ChangeMe!2024`, and you must set a new password at first
sign-in. To start over, delete `users.db`.

## 6. (Optional) Regenerate the brand assets

```bash
python scripts/make_brand_assets.py
```

## Demo flow (thesis defence walkthrough)

1. Sign in. **Overview** shows the model status, the training run and the replay file.
2. **Live Replay** → choose a speed → **Play**:
   - The first windows are greyed out: their lookback starts before the replay file, so they raise no alerts.
   - From the first complete window on, each host card shows the detected tier, forecast tier and both forecast
     probabilities.
3. **Alerts**: filled badges are detections, outlined badges are predictions. Click a row for the full record, or
   export to CSV.
4. **Risk Timeline**: pick a host and a test block; compare the true tier with the predicted risk and thresholds.
5. **Model Evaluation**:
   - detection and forecast tables, and the early-warning table with its event counts;
   - the XGBoost tab, which holds the same-experiment baseline and the previous CICIoT2023 system (reference
     only);
   - *Export report* writes the tables and figures to one HTML file.
6. **About the model**: architecture, task definition, alert rules and limitations.
7. Switch to **Light** mode (sidebar or Settings) for print-friendly screenshots.

Everything runs offline.
