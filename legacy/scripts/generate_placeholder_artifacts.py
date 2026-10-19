"""
generate_placeholder_artifacts.py

PLACEHOLDER ARTIFACT GENERATOR
==============================
This script is NOT part of the shipped application. It exists solely because
the real trained models (from the CICIoT2023 / ToN_IoT-based PhD research)
were not provided alongside this build. It fabricates small, honestly-labeled
STAND-IN models with the exact file names, schemas, and class sets described
in the build spec, so the rest of the application (auth, dashboards, live
monitor, alerts, analytics, threading) is fully buildable and demoable today.

When the real artifacts are available, drop them into model_artifacts/ with
the SAME filenames and this script/its output become irrelevant -- no
application code changes are required, because app/models/inference.py only
depends on the file contracts below, not on how the files were produced.

Do NOT present these placeholder models' predictions as reflecting the
thesis's actual reported metrics. The real metrics (Section 1 of the spec)
are hardcoded into the Model Info screen as reference text, independent of
whatever model happens to be loaded -- clearly labeled as reference metrics
for the real model, not a live evaluation of the currently loaded artifact.
"""
import json
import os
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.preprocessing import LabelEncoder
import joblib

OUT = os.path.join(os.path.dirname(__file__), "..", "model_artifacts")
DATA_OUT = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(OUT, exist_ok=True)
os.makedirs(DATA_OUT, exist_ok=True)

rng = np.random.default_rng(42)

# ---------------------------------------------------------------------------
# 1. Spotter (attack detection) -- 46 features, 34 classes
# ---------------------------------------------------------------------------
DETECTION_CLASSES = [
    "BenignTraffic",
    "DDoS-ICMP_Flood", "DDoS-UDP_Flood", "DDoS-TCP_Flood", "DDoS-PSHACK_Flood",
    "DDoS-SYN_Flood", "DDoS-RSTFINFlood", "DDoS-SynonymousIP_Flood",
    "DDoS-ICMP_Fragmentation", "DDoS-ACK_Fragmentation", "DDoS-UDP_Fragmentation",
    "DDoS-HTTP_Flood", "DDoS-SlowLoris",
    "DoS-UDP_Flood", "DoS-TCP_Flood", "DoS-SYN_Flood", "DoS-HTTP_Flood",
    "Mirai-greeth_flood", "Mirai-greip_flood", "Mirai-udpplain",
    "Recon-PortScan", "Recon-OSScan", "Recon-PingSweep", "Recon-HostDiscovery",
    "VulnerabilityScan",
    "MITM-ArpSpoofing", "DNS_Spoofing",
    "BrowserHijacking", "CommandInjection", "SqlInjection", "XSS",
    "Backdoor_Malware", "Uploading_Attack", "DictionaryBruteForce",
]
assert len(DETECTION_CLASSES) == 34, len(DETECTION_CLASSES)

DETECTION_FEATURES = [f"flow_feat_{i:02d}" for i in range(1, 47)]
# Give a handful of features human-recognizable names (cosmetic realism only)
_named = {
    0: "flow_duration", 1: "header_length", 2: "protocol_type", 3: "duration",
    4: "rate", 5: "srate", 6: "drate", 7: "fin_flag_count", 8: "syn_flag_count",
    9: "rst_flag_count", 10: "psh_flag_count", 11: "ack_flag_count",
    12: "ece_flag_count", 13: "cwr_flag_count", 14: "ack_count", 15: "syn_count",
    16: "fin_count", 17: "urg_count", 18: "rst_count", 19: "http", 20: "https",
    21: "dns", 22: "telnet", 23: "smtp", 24: "ssh", 25: "irc", 26: "tcp",
    27: "udp", 28: "dhcp", 29: "arp", 30: "icmp", 31: "ipv", 32: "llc",
    33: "tot_sum", 34: "min", 35: "max", 36: "avg", 37: "std", 38: "tot_size",
    39: "iat", 40: "number", 41: "magnitude", 42: "radius", 43: "covariance",
    44: "variance", 45: "weight",
}
for i, name in _named.items():
    DETECTION_FEATURES[i] = name

n_det = 6000
X_det = pd.DataFrame(rng.normal(0, 1, size=(n_det, 46)).astype("float32"), columns=DETECTION_FEATURES)
# Make benign vs attack loosely separable, and skew realistically toward
# benign traffic (~78%) so the placeholder demo isn't attack-saturated.
weights = rng.normal(0, 1, size=46)
score = X_det.values @ weights
y_idx = rng.integers(0, 34, size=n_det)
benign_cutoff = np.quantile(score, 0.22)  # bottom 22% of score stays attack-labeled
y_idx[score > benign_cutoff] = 0
det_label_encoder = LabelEncoder().fit(DETECTION_CLASSES)
y_det = det_label_encoder.transform([DETECTION_CLASSES[i] for i in y_idx])

dtrain = xgb.DMatrix(X_det, label=y_det)
det_booster = xgb.train(
    {"objective": "multi:softprob", "num_class": 34, "max_depth": 4, "eta": 0.3},
    dtrain, num_boost_round=15,
)
det_booster.save_model(os.path.join(OUT, "detection_model_xgboost.json"))
joblib.dump(det_label_encoder, os.path.join(OUT, "detection_label_encoder.joblib"))
with open(os.path.join(OUT, "detection_feature_columns.json"), "w") as f:
    json.dump(DETECTION_FEATURES, f, indent=2)
with open(os.path.join(OUT, "detection_class_names.json"), "w") as f:
    json.dump(DETECTION_CLASSES, f, indent=2)

# ---------------------------------------------------------------------------
# 2. Risk Analyst (severity) -- ToN_IoT-style features, 5 tiers
# ---------------------------------------------------------------------------
SEVERITY_TIERS = {
    "0": "Normal",
    "1": "Reconnaissance",
    "2": "Access/Compromise",
    "3": "High (DoS/DDoS)",
    "4": "Critical (Ransomware)",
}
SEVERITY_NUMERIC_FEATURES = [
    "src_bytes", "dst_bytes", "duration", "missed_bytes",
    "src_pkts", "dst_pkts", "src_ip_bytes", "dst_ip_bytes",
]
SEVERITY_CATEGORICAL_FEATURES = ["proto", "service", "conn_state"]
SEVERITY_FEATURES = SEVERITY_NUMERIC_FEATURES + SEVERITY_CATEGORICAL_FEATURES

CAT_VALUES = {
    "proto": ["tcp", "udp", "icmp"],
    "service": ["-", "http", "dns", "ssl", "ftp", "ssh", "dhcp"],
    "conn_state": ["S0", "S1", "SF", "REJ", "RSTO", "RSTR", "OTH"],
}
severity_encoders = {col: LabelEncoder().fit(vals) for col, vals in CAT_VALUES.items()}

n_sev = 6000
sev_df = pd.DataFrame({
    "src_bytes": rng.exponential(500, n_sev),
    "dst_bytes": rng.exponential(500, n_sev),
    "duration": rng.exponential(2, n_sev),
    "missed_bytes": rng.integers(0, 50, n_sev),
    "src_pkts": rng.integers(1, 200, n_sev),
    "dst_pkts": rng.integers(0, 200, n_sev),
    "src_ip_bytes": rng.exponential(1000, n_sev),
    "dst_ip_bytes": rng.exponential(1000, n_sev),
    "proto": rng.choice(CAT_VALUES["proto"], n_sev),
    "service": rng.choice(CAT_VALUES["service"], n_sev),
    "conn_state": rng.choice(CAT_VALUES["conn_state"], n_sev),
})
sev_encoded = sev_df.copy()
for col in SEVERITY_CATEGORICAL_FEATURES:
    sev_encoded[col] = severity_encoders[col].transform(sev_df[col])
sev_score = (sev_df["src_pkts"] + sev_df["dst_bytes"] / 100 - sev_df["duration"] * 5)
# Skew toward realistic traffic: mostly Normal, tapering off toward Critical,
# so the placeholder demo doesn't look like every flow is high-severity.
severity_quantile_edges = [0.0, 0.70, 0.85, 0.93, 0.98, 1.0]
y_sev = pd.cut(
    sev_score.rank(pct=True), bins=severity_quantile_edges, labels=[0, 1, 2, 3, 4], include_lowest=True,
).astype(int)

dtrain_sev = xgb.DMatrix(sev_encoded[SEVERITY_FEATURES], label=y_sev)
sev_booster = xgb.train(
    {"objective": "multi:softprob", "num_class": 5, "max_depth": 4, "eta": 0.3},
    dtrain_sev, num_boost_round=15,
)
sev_booster.save_model(os.path.join(OUT, "severity_model_xgboost.json"))
joblib.dump(severity_encoders, os.path.join(OUT, "severity_categorical_encoders.joblib"))
with open(os.path.join(OUT, "severity_feature_columns.json"), "w") as f:
    json.dump(SEVERITY_FEATURES, f, indent=2)
with open(os.path.join(OUT, "severity_class_names.json"), "w") as f:
    json.dump(SEVERITY_TIERS, f, indent=2)
with open(os.path.join(OUT, "severity_tier_mapping.json"), "w") as f:
    json.dump(SEVERITY_TIERS, f, indent=2)

# ---------------------------------------------------------------------------
# 3. Simulation feed -- combined rows carrying BOTH schemas + ground truth,
#    keyed to a shared synthetic timeline (see inference.py for the explicit
#    "bridging" documentation this implies).
# ---------------------------------------------------------------------------
n_feed = 4000
feed_det = pd.DataFrame(rng.normal(0, 1, size=(n_feed, 46)).astype("float32"), columns=DETECTION_FEATURES)
feed_y_idx = rng.integers(0, 34, size=n_feed)
feed_score = feed_det.values @ weights
feed_y_idx[feed_score > np.quantile(feed_score, 0.22)] = 0
feed_det["true_label"] = [DETECTION_CLASSES[i] for i in feed_y_idx]

feed_sev = pd.DataFrame({
    "src_bytes": rng.exponential(500, n_feed),
    "dst_bytes": rng.exponential(500, n_feed),
    "duration": rng.exponential(2, n_feed),
    "missed_bytes": rng.integers(0, 50, n_feed),
    "src_pkts": rng.integers(1, 200, n_feed),
    "dst_pkts": rng.integers(0, 200, n_feed),
    "src_ip_bytes": rng.exponential(1000, n_feed),
    "dst_ip_bytes": rng.exponential(1000, n_feed),
    "proto": rng.choice(CAT_VALUES["proto"], n_feed),
    "service": rng.choice(CAT_VALUES["service"], n_feed),
    "conn_state": rng.choice(CAT_VALUES["conn_state"], n_feed),
})
device_pool = [
    "Smart Thermostat", "Smart Bulb", "Webcam", "Smart Lock", "IP Camera",
    "Smart Plug", "Baby Monitor", "Smart Speaker", "Door Sensor", "Smart TV",
]
feed_det["device_name"] = rng.choice(device_pool, n_feed)
feed_det["device_ip"] = [f"192.168.1.{10 + (i % 50)}" for i in rng.integers(0, 50, n_feed)]

full_feed = pd.concat([feed_det.reset_index(drop=True), feed_sev.reset_index(drop=True)], axis=1)
full_feed.insert(0, "row_id", range(n_feed))
full_feed.to_csv(os.path.join(DATA_OUT, "simulation_feed.csv"), index=False)

print("Placeholder artifacts written to", os.path.abspath(OUT))
print("Simulation feed written to", os.path.abspath(DATA_OUT))
print("Detection classes:", len(DETECTION_CLASSES), "Severity tiers:", len(SEVERITY_TIERS))
