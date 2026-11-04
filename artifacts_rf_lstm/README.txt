SENTINELIOT RF-LSTM HYBRID: ARTIFACTS
=====================================
Data: ToN_IoT processed network dataset (23 files, 22,339,021 flows), ordered by the recorded
Zeek capture time (ts). No synthetic timestamps. Split mode: blocked.
Window 60 s, lookback 10 windows, forecast horizon 5 windows (5 min).

models/
  sentinel_inference.py        shared preprocessing + SentinelEngine (import this in the dashboard)
  rf_flow.joblib               Layer 1 Random Forest (flow -> 10 attack types)
  hybrid_rf_lstm.pt            Layer 2 LSTM (detection head + forecast head), RF evidence as input
  window_scaler.joblib         feature scaler for the LSTM input
  preprocessing.json           window config, category maps, thresholds, host list
  lstm_only.pt / rf_forecaster.joblib / xgb_*_baseline.json   comparison models
data/
  dashboard_feed.csv           every test window: real time, host, detections, forecast, alert level
  replay_flows.csv             raw test flows for live replay through SentinelEngine
reports/
  model_comparison.csv  flow_level_comparison.csv  early_warning.csv  efficiency.csv
  split_coverage.csv  attack_type_time_spans.csv
figures/  timeline, comparisons, PR curves, confusion matrices, lead time, training, case study

Alert levels (si.alert_level, each with an alert_reason saying "Detected" or "Predicted"):
  CRITICAL  DoS/DDoS/ransomware detected now, or ransomware-level activity forecast
  HIGH      compromise detected now, or escalation forecast: P(tier>=2 ahead) >= 0.639
  WARNING   reconnaissance detected now, or P(any attack ahead) >= 0.724
  NORMAL    otherwise. Thresholds were chosen on the validation period.
