"""
Shared preprocessing + inference for the SentinelIoT RF-LSTM hybrid.

The training notebook imports this file, and the dashboard imports the same
file, so features are computed identically at training time and at run time.
"""
import json
import os

import numpy as np
import pandas as pd

TYPE_ORDER = ['normal', 'scanning', 'dos', 'ddos', 'injection', 'xss',
              'password', 'backdoor', 'ransomware', 'mitm']
SEVERITY_MAP = {
    'normal': 0,
    'scanning': 1,
    'password': 2, 'backdoor': 2, 'mitm': 2, 'injection': 2, 'xss': 2,
    'dos': 3, 'ddos': 3,
    'ransomware': 4,
}
TIER_NAMES = ['Normal', 'Reconnaissance', 'Access/Compromise',
              'High (DoS/DDoS)', 'Critical (Ransomware)']
TYPE_TIER = np.array([SEVERITY_MAP[t] for t in TYPE_ORDER])

NUM_COLS = ['duration', 'src_bytes', 'dst_bytes', 'missed_bytes', 'src_pkts',
            'src_ip_bytes', 'dst_pkts', 'dst_ip_bytes', 'dst_port',
            'dns_qclass', 'dns_qtype', 'dns_rcode', 'http_trans_depth',
            'http_request_body_len', 'http_response_body_len', 'http_status_code']
CAT_COLS = ['proto', 'service', 'conn_state', 'dns_AA', 'dns_RD', 'dns_RA',
            'dns_rejected', 'ssl_version', 'ssl_cipher', 'ssl_resumed',
            'ssl_established', 'http_method', 'http_version', 'weird_name',
            'weird_notice']
FLOW_FEATURES = NUM_COLS + [c + '_code' for c in CAT_COLS]

CONN_STATES = ['S0', 'SF', 'REJ', 'OTH', 'RSTO', 'RSTR', 'SH', 'S1']
PROTOS = ['tcp', 'udp', 'icmp']
SERVICES = ['-', 'dns', 'http', 'ssl']

LOG_STATS = ['n_flows', 'src_bytes', 'dst_bytes', 'src_pkts', 'dst_pkts',
             'dur_mean', 'dur_max', 'n_src', 'n_dport']
STAT_FEATURES = ([c + '_log' for c in LOG_STATS] + ['bytes_ratio']
                 + ['cs_' + s for s in CONN_STATES] + ['cs_other']
                 + ['proto_' + p for p in PROTOS]
                 + ['svc_' + ('none' if s == '-' else s) for s in SERVICES] + ['svc_other'])
RF_FEATURES = ['p_' + t for t in TYPE_ORDER] + ['rf_attack_max', 'rf_attack_frac', 'rf_tier_max']
HYBRID_FEATURES = STAT_FEATURES + RF_FEATURES


def coerce_flows(df):
    """Clean a raw Zeek-style flow table (TON_IoT network schema)."""
    df = df.copy()
    df['ts'] = pd.to_numeric(df['ts'], errors='coerce')
    df = df[df['ts'].notna()]
    for c in NUM_COLS:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0).astype('float32')
        else:
            df[c] = np.float32(0)
    for c in CAT_COLS + ['src_ip', 'dst_ip']:
        if c in df.columns:
            df[c] = df[c].astype(str).str.strip()
        else:
            df[c] = '-'
    return df


def fit_cat_maps(df):
    return {c: {v: i for i, v in enumerate(sorted(df[c].astype(str).unique()))} for c in CAT_COLS}


def flow_matrix(df, cat_maps):
    X = pd.DataFrame(index=df.index)
    for c in NUM_COLS:
        X[c] = df[c].astype('float32')
    for c in CAT_COLS:
        X[c + '_code'] = df[c].map(cat_maps[c]).fillna(-1).astype('float32')
    return X[FLOW_FEATURES]


def align_type_proba(proba, classes):
    """Map a classifier's predict_proba columns onto the fixed TYPE_ORDER."""
    out = np.zeros((proba.shape[0], len(TYPE_ORDER)), dtype=np.float32)
    for j, c in enumerate(classes):
        out[:, TYPE_ORDER.index(c)] = proba[:, j]
    return out


def tier_from_type_proba(P):
    return TYPE_TIER[P.argmax(axis=1)]


def window_table(flows, type_proba, window_sec, t0, extra=None, entity_col='dst_ip'):
    """Aggregate flows into fixed windows per entity (destination host).

    flows       cleaned flow DataFrame (needs ts, src_ip, dst_ip, conn_state, proto, service, numeric cols)
    type_proba  (n_flows, len(TYPE_ORDER)) RF probabilities for each flow
    extra       optional {name: (values, aggfunc)} aggregated alongside (e.g. true tier)
    """
    n = len(flows)
    f = pd.DataFrame({
        'entity': flows[entity_col].values,
        'win': np.floor((flows['ts'].values - t0) / window_sec).astype(np.int64),
        'n_flows': np.ones(n, dtype=np.float32),
        'src_bytes': flows['src_bytes'].values, 'dst_bytes': flows['dst_bytes'].values,
        'src_pkts': flows['src_pkts'].values, 'dst_pkts': flows['dst_pkts'].values,
        'duration': flows['duration'].values,
        'src_ip': flows['src_ip'].values, 'dst_port': flows['dst_port'].values,
    })
    cs = flows['conn_state'].values
    for s in CONN_STATES:
        f['cs_' + s] = (cs == s).astype(np.float32)
    f['cs_other'] = (~np.isin(cs, CONN_STATES)).astype(np.float32)
    pr = flows['proto'].str.lower().values
    for p in PROTOS:
        f['proto_' + p] = (pr == p).astype(np.float32)
    sv = flows['service'].str.lower().values
    for s in SERVICES:
        f['svc_' + ('none' if s == '-' else s)] = (sv == s).astype(np.float32)
    f['svc_other'] = (~np.isin(sv, SERVICES)).astype(np.float32)

    for i, t in enumerate(TYPE_ORDER):
        f['p_' + t] = type_proba[:, i]
    attack = 1.0 - type_proba[:, 0]
    tier_pred = tier_from_type_proba(type_proba)
    f['rf_attack'] = attack
    f['rf_pred_attack'] = (tier_pred > 0).astype(np.float32)
    f['rf_tier'] = tier_pred.astype(np.float32)

    spec = dict(
        n_flows=('n_flows', 'sum'), src_bytes=('src_bytes', 'sum'), dst_bytes=('dst_bytes', 'sum'),
        src_pkts=('src_pkts', 'sum'), dst_pkts=('dst_pkts', 'sum'),
        dur_mean=('duration', 'mean'), dur_max=('duration', 'max'),
        n_src=('src_ip', 'nunique'), n_dport=('dst_port', 'nunique'),
        rf_attack_max=('rf_attack', 'max'), rf_attack_frac=('rf_pred_attack', 'mean'),
        rf_tier_max=('rf_tier', 'max'),
    )
    mean_cols = ([c for c in f.columns if c.startswith(('cs_', 'proto_', 'svc_'))]
                 + ['p_' + t for t in TYPE_ORDER])
    for c in mean_cols:
        spec[c] = (c, 'mean')
    if extra:
        for name, (vals, how) in extra.items():
            f[name] = vals
            spec[name] = (name, how)

    w = f.groupby(['entity', 'win'], sort=True).agg(**spec).reset_index()
    w['rf_tier_pred'] = w['rf_tier_max'].astype(np.int64)
    return finalize_window_features(w)


def finalize_window_features(w):
    for c in LOG_STATS:
        w[c + '_log'] = np.log1p(np.clip(w[c].astype(np.float64), 0, None)).astype(np.float32)
    w['bytes_ratio'] = (w['src_bytes_log'] - w['dst_bytes_log']).astype(np.float32)
    w['rf_tier_max'] = w['rf_tier_max'] / 4.0
    return w


def grid_fill(w, fill_extra=None, min_win=None, max_win=None):
    """Make every entity's window sequence contiguous (empty windows = no traffic)."""
    out = []
    for ent, g in w.groupby('entity', sort=False):
        lo = g['win'].min() if min_win is None else min(min_win, g['win'].min())
        hi = g['win'].max() if max_win is None else max(max_win, g['win'].max())
        g = g.set_index('win').reindex(np.arange(lo, hi + 1))
        g['entity'] = ent
        empty = g['n_flows'].isna()
        num = g.columns.drop('entity')
        g[num] = g[num].fillna(0)
        g.loc[empty, 'p_normal'] = 1.0
        if fill_extra:
            for c, v in fill_extra.items():
                g.loc[empty, c] = v
        out.append(g.reset_index().rename(columns={'index': 'win'}))
    return pd.concat(out, ignore_index=True)


try:
    import torch
    import torch.nn as nn

    class SeqNet(nn.Module):
        """LSTM over a window sequence with two heads:
           head_now -> severity tier of the current window (detection)
           head_fut -> highest severity tier in the next H windows (forecast)"""

        def __init__(self, n_in, hidden=64, layers=2, n_cls=5, drop=0.2):
            super().__init__()
            self.inp = nn.Linear(n_in, hidden)
            self.lstm = nn.LSTM(hidden, hidden, layers, batch_first=True,
                                dropout=drop if layers > 1 else 0.0)
            def head():
                return nn.Sequential(nn.Linear(hidden + n_in, hidden), nn.ReLU(),
                                     nn.Dropout(drop), nn.Linear(hidden, n_cls))
            self.head_now = head()
            self.head_fut = head()

        def forward(self, x):
            h = torch.relu(self.inp(x))
            o, _ = self.lstm(h)
            z = torch.cat([o[:, -1], x[:, -1]], dim=1)
            return self.head_now(z), self.head_fut(z)
except ImportError:  # dashboard machines without torch can still use the RF layer
    torch = None


def alert_level(det_tier, fut_tier, p_attack_next, p_severe_next, thr_attack, thr_severe):
    """Return (level, reason). Detection reasons describe now; prediction reasons describe the horizon."""
    if det_tier >= 3:
        return 'CRITICAL', 'Detected: ' + TIER_NAMES[det_tier]
    if fut_tier == 4:
        return 'CRITICAL', 'Predicted: ransomware-level activity within horizon'
    if det_tier == 2:
        return 'HIGH', 'Detected: ' + TIER_NAMES[2]
    if p_severe_next >= thr_severe:
        return 'HIGH', 'Predicted: escalation to compromise/DoS within horizon'
    if det_tier == 1:
        return 'WARNING', 'Detected: reconnaissance'
    if p_attack_next >= thr_attack:
        return 'WARNING', 'Predicted: attack likely within horizon'
    return 'NORMAL', ''


class SentinelEngine:
    """Load the exported artifacts and score raw flows.

        eng = SentinelEngine('models')
        flow_view = eng.score_flows(df)      # per-flow RF verdicts
        host_view = eng.analyse(df)          # per-host detection + forecast for the latest window
    """

    def __init__(self, model_dir, device='cpu'):
        import joblib
        with open(os.path.join(model_dir, 'preprocessing.json')) as fh:
            self.cfg = json.load(fh)
        self.rf = joblib.load(os.path.join(model_dir, 'rf_flow.joblib'))
        self.scaler = joblib.load(os.path.join(model_dir, 'window_scaler.joblib'))
        self.cat_maps = self.cfg['cat_maps']
        self.W = self.cfg['window_sec']
        self.L = self.cfg['lookback']
        self.H = self.cfg['horizon']
        self.t0 = self.cfg['t0']
        self.threshold = self.cfg['thresholds']['hybrid']
        self.threshold_severe = self.cfg['thresholds']['hybrid_severe']
        self.device = device
        ck = torch.load(os.path.join(model_dir, 'hybrid_rf_lstm.pt'), map_location=device)
        self.net = SeqNet(len(HYBRID_FEATURES), ck['hidden'], ck['layers'], 5, ck['dropout'])
        self.net.load_state_dict(ck['state_dict'])
        self.net.eval().to(device)

    def _flow_proba(self, df):
        X = flow_matrix(df, self.cat_maps)
        return align_type_proba(self.rf.predict_proba(X), list(self.rf.classes_))

    def score_flows(self, df):
        df = coerce_flows(df)
        P = self._flow_proba(df)
        out = df[['ts', 'src_ip', 'dst_ip', 'dst_port', 'proto', 'service']].copy()
        out['pred_type'] = [TYPE_ORDER[i] for i in P.argmax(1)]
        out['pred_tier'] = TYPE_TIER[P.argmax(1)]
        out['attack_prob'] = 1.0 - P[:, 0]
        return out

    def analyse(self, df, entities=None, window_start=None):
        """Detection + forecast for one window per host.

        window_start: epoch seconds of the window to evaluate (use the recorded ts timeline);
                      default = the latest window present in df. Pass flows covering at least
                      the previous `lookback` windows."""
        import torch as _t
        df = coerce_flows(df)
        if entities is not None:
            df = df[df['dst_ip'].isin(entities)]
        if df.empty:
            return pd.DataFrame()
        P = self._flow_proba(df)
        w = window_table(df, P, self.W, self.t0)
        last = int(w['win'].max()) if window_start is None else int(np.floor((window_start - self.t0) / self.W))
        w = w[w['win'] <= last]
        if w.empty:
            return pd.DataFrame()
        g = grid_fill(w, min_win=last - self.L + 1, max_win=last)
        g = g[g['win'] > last - self.L]
        rows, seqs = [], []
        for ent, e in g.groupby('entity'):
            e = e.sort_values('win')
            seqs.append(self.scaler.transform(e[HYBRID_FEATURES].values.astype(np.float32)))
            cur = e.iloc[-1]
            ws = self.t0 + last * self.W
            rows.append(dict(entity=ent, window_start=ws,
                             window_start_utc=pd.to_datetime(ws, unit='s').strftime('%Y-%m-%dT%H:%M:%SZ'),
                             n_flows=int(cur['n_flows']), rf_tier=int(cur['rf_tier_pred'])))
        x = _t.tensor(np.stack(seqs), dtype=_t.float32, device=self.device)
        with _t.no_grad():
            ln, lf = self.net(x)
        pn = _t.softmax(ln, 1).cpu().numpy()
        pf = _t.softmax(lf, 1).cpu().numpy()
        res = pd.DataFrame(rows)
        res['det_tier'] = pn.argmax(1)
        res['fut_tier'] = pf.argmax(1)
        res['p_attack_next'] = 1.0 - pf[:, 0]
        res['p_severe_next'] = pf[:, 2:].sum(1)
        for k, name in enumerate(TIER_NAMES):
            res['p_fut_' + str(k)] = pf[:, k]
        al = [alert_level(a, b, c, d, self.threshold, self.threshold_severe)
              for a, b, c, d in zip(res['det_tier'], res['fut_tier'], res['p_attack_next'], res['p_severe_next'])]
        res['alert'] = [x[0] for x in al]
        res['alert_reason'] = [x[1] for x in al]
        res['horizon_minutes'] = self.H * self.W / 60.0
        return res
