# legacy/

Code and assets from before the Vigil redesign. **The application does not import anything in this
folder**; it is kept for reference and for the thesis record. Moved with `git mv`, so history is intact.

| Path | What it was |
|---|---|
| `app/live_monitor/` | XGBoost "Spotter" / "Risk Analyst" live screen and the simulation engine (random rows from the simulation feed) |
| `app/dashboard/`, `app/analytics/` | Session dashboard and Analytics & Reports, both driven by the legacy simulation stream |
| `app/alerts/` | Alerts screen with the legacy XGBoost tab |
| `app/hybrid_replay/`, `app/risk_timeline/`, `app/model_comparison/`, `app/model_info/`, `app/settings/`, `app/user_management/`, `app/shell.py` | Pre-redesign Tk/ttkbootstrap screens, replaced by `app/screens/` |
| `app/common/theme.py`, `widgets.py`, `context.py` | Pre-redesign theme, widgets and app context |
| `models/inference.py` | Spotter (CICIoT2023) and Risk Analyst (ToN_IoT train/test) XGBoost wrappers |
| `model_artifacts/` | The two XGBoost models and their encoders/column files |
| `data/simulation_feed*.csv`, `data/simulations_feed.csv` | The non-chronological demo feed (pairs unrelated rows from two datasets) |
| `scripts/generate_placeholder_artifacts.py`, `scripts/ui_smoketest.py` | Placeholder XGBoost artifacts generator; smoke test for the old UI |
| `notebooks/sentineliot.ipynb` | The earlier CICIoT2023 / ToN_IoT XGBoost training notebook |

The only legacy *values* still shown by Vigil are the previous system's reference metrics in
`model_artifacts/spotter_metrics.json`, on the Model Evaluation screen, labelled as a different dataset
and not directly comparable.
