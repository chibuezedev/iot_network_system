"""
About the model -- architecture diagram, dataset, task definition, alert
rules and limitations. Plain description; every number is filled in from the
artifacts (preprocessing.json, README.txt, report CSVs).
"""
from __future__ import annotations

import tkinter as tk

import customtkinter as ctk
import pandas as pd

from app.screens.base import Screen
from app.ui import theme, tokens as T
from app.ui.widgets import Card, Table, autowrap, label, section_title
from services import reports, run_info


def paragraph(parent, text: str, role: str = "body", color=T.TEXT, pady=(0, 8)):
    lbl = autowrap(label(parent, text, role, color), parent, margin=8)
    lbl.pack(anchor="w", fill="x", pady=pady)
    return lbl


class ArchitectureDiagram(tk.Canvas):
    """Flow of data through the hybrid, drawn on a canvas that follows the theme."""

    def __init__(self, parent, svc, height: int = 300):
        super().__init__(parent, height=height, highlightthickness=0, bd=0)
        self.svc = svc
        self._unsub = theme.on_change(self.redraw)
        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<Destroy>", lambda e: self._unsub() if e.widget is self else None)

    def _box(self, x0, y0, x1, y1, title, body, fill, border, text, muted, accent=False):
        r = 10
        pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1, x0, y1,
               x0, y1 - r, x0, y0 + r, x0, y0]
        self.create_polygon(pts, smooth=True, fill=fill, outline=border, width=2 if accent else 1)
        fam = theme.family("sans")
        s = ctk.ScalingTracker.get_widget_scaling(self)
        t = self.create_text(x0 + 12 * s, y0 + 10 * s, text=title, anchor="nw", fill=text,
                             font=(fam, -int(13 * s), "bold"), width=x1 - x0 - 24 * s)
        title_bottom = self.bbox(t)[3]      # body starts under the (possibly wrapped) title
        self.create_text(x0 + 12 * s, title_bottom + 6 * s, text=body, anchor="nw", fill=muted,
                         font=(fam, -int(11 * s)), width=x1 - x0 - 24 * s)

    def _arrow(self, x0, y0, x1, y1, color):
        self.create_line(x0, y0, x1, y1, fill=color, width=2, arrow="last", arrowshape=(10, 12, 5))

    def redraw(self) -> None:
        if not self.winfo_exists():
            return
        p = theme.pick
        bg, card, card2, border = p(T.SURFACE), p(T.SURFACE_2), p(T.SURFACE), p(T.BORDER)
        text, muted, accent = p(T.TEXT), p(T.MUTED), p(T.ACCENT)
        self.configure(bg=bg)
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 50:
            return
        svc = self.svc
        cfg = svc.cfg
        n_types = len(svc.type_order)
        n_stat = len(cfg.get("stat_features", []))
        n_feat = len(cfg.get("hybrid_features", []))
        gap = w * 0.025
        cols = [0.0, 0.205, 0.41, 0.615, 0.82, 1.0]
        boxes = [
            ("Recorded Zeek flows", "ToN_IoT network records, kept in capture-time (ts) order"),
            ("Layer 1 · Random Forest", f"one flow at a time → probability of each of {n_types} traffic "
                                            "types"),
            (f"Per-host {svc.window_sec:g} s windows", f"per destination IP: {n_stat} traffic statistics + "
                                                       f"RF evidence ({n_feat} features)"),
            ("Layer 2 · LSTM", f"reads the last {svc.lookback} windows of a host "
                                   f"({svc.lookback * svc.window_sec / 60:g} min of history)"),
        ]
        top, bot = h * 0.10, h * 0.55
        for i, (title, body) in enumerate(boxes):
            x0, x1 = cols[i] * w + (gap if i else 0), cols[i + 1] * w - gap / 2
            self._box(x0, top, x1, bot, title, body, card, border, text, muted, accent=(i in (1, 3)))
            if i:
                self._arrow(cols[i] * w - gap / 2 + 1, (top + bot) / 2, cols[i] * w + gap - 1, (top + bot) / 2, muted)
        hx0, hx1 = cols[4] * w + gap, w - 2
        mid = (top + bot) / 2
        heads = [("Detection head", "severity tier of the current window"),
                 ("Forecast head", f"highest tier within the next {svc.horizon} windows "
                                   f"({svc.horizon_minutes:g} min)")]
        hh = (h * 0.86 - h * 0.04) / 2 - 6
        for j, (title, body) in enumerate(heads):
            y0 = h * 0.04 + j * (hh + 12)
            self._box(hx0, y0, hx1, y0 + hh, title, body, card2, accent, text, muted, accent=True)
            self._arrow(cols[4] * w - gap / 2 + 1, mid, hx0 - 1, y0 + hh / 2, muted)
        # alert rules strip under the pipeline
        ay0, ay1 = h * 0.63, h * 0.97
        self._box(cols[1] * w + gap, ay0, cols[4] * w - gap / 2, ay1, "Alert rules — alert_level()",
                  "detected tier + forecast tier + P(any attack ahead) + P(escalation ahead) → "
                  "NORMAL / WARNING / HIGH / CRITICAL, reason 'Detected: …' or 'Predicted: …'",
                  card, border, text, muted)
        y_link = min((ay0 + ay1) / 2, h * 0.86 - 12)     # horizontal link from the heads to the rules
        self._arrow(hx0 - 1, y_link, cols[4] * w - gap / 2 + 2, y_link, muted)


class AboutScreen(Screen):
    title = "About the model"
    subtitle = "What the RF–LSTM hybrid does, what it was trained on, and what it cannot show."

    def build(self) -> None:
        self.header()
        svc = self.ctx.hybrid
        if svc is None:
            self.unavailable(self.ctx.hybrid_error or "The RF–LSTM hybrid is not loaded.")
            return
        cfg = svc.cfg

        arch = Card(self.page)
        self.section(arch)
        section_title(arch.body, "Architecture").pack(fill="x", pady=(0, 8))
        ArchitectureDiagram(arch.body, svc, height=330).pack(fill="x")

        facts = run_info.readme_facts()
        split = run_info.split_description(svc)
        ds = Card(self.page)
        self.section(ds)
        section_title(ds.body, "Dataset").pack(fill="x", pady=(0, 8))
        if facts["flows"] is not None:
            paragraph(ds.body, f"{facts['dataset']}: {facts['files']} files, {facts['flows']:,} flows, "
                               f"{facts['timestamp_note'] or 'with recorded timestamps'}. Each record is a Zeek "
                               "connection log entry with its real capture time (ts) and a traffic-type label.")
        else:
            paragraph(ds.body, "README.txt in the artifacts folder does not state the dataset size.", color=T.MUTED)
        n_ent = len(cfg.get("entities", []))
        paragraph(ds.body, f"Hosts are destination IP addresses; the model tracks {n_ent} hosts listed in "
                           "preprocessing.json. Windows are aligned to t0 = "
                           f"{svc.to_utc(svc.t0)} and are {svc.window_sec:g} s long.")
        if split:
            paragraph(ds.body, f"Train/validation/test split — {split}. Alert thresholds were chosen on the "
                               "validation period.")
        sc = reports.load_report("split_coverage")
        if sc is not None:
            label(ds.body, "Flows per traffic type in each split (reports/split_coverage.csv)", "small_bold",
                  T.MUTED).pack(anchor="w", pady=(6, 4))
            Table(ds.body, list(sc.columns), sc.itertuples(index=False),
                  numeric=set(sc.columns) - {"type"}).pack(fill="x")

        task = Card(self.page)
        self.section(task)
        section_title(task.body, "Prediction task").pack(fill="x", pady=(0, 8))
        paragraph(task.body, ("Every flow is mapped to a severity tier through its traffic type. For each host and "
                              f"window the model outputs (1) detection: the tier of the current window, and (2) "
                              f"forecast: the highest tier in the next {svc.horizon} windows ({svc.horizon_minutes:g} "
                              "min). P(any attack ahead) is the forecast probability of a tier above Normal; "
                              "P(escalation ahead) is the probability of Access/Compromise or higher."))
        sev = cfg.get("severity_map", {})
        tiers = cfg.get("tier_names", [])
        rows = [(i, name, ", ".join(sorted(t for t, k in sev.items() if k == i)) or "—")
                for i, name in enumerate(tiers)]
        Table(task.body, ["tier", "name", "traffic types (preprocessing.json severity_map)"], rows,
              numeric={"tier"}).pack(fill="x")

        rules = Card(self.page)
        self.section(rules)
        section_title(rules.body, "Alert levels").pack(fill="x", pady=(0, 8))
        thr_a, thr_s = svc.threshold_attack, svc.threshold_severe
        rule_rows = [
            ("CRITICAL", "detected tier is High (DoS/DDoS) or Critical", "forecast tier is Critical (ransomware)"),
            ("HIGH", "detected tier is Access/Compromise", f"P(escalation ahead) ≥ {thr_s:.4f}"),
            ("WARNING", "detected tier is Reconnaissance", f"P(any attack ahead) ≥ {thr_a:.4f}"),
            ("NORMAL", "none of the above", ""),
        ]
        Table(rules.body, ["level", "Detected (now)", "Predicted (within horizon)"], rule_rows).pack(fill="x")
        paragraph(rules.body, ("Rules are checked from the top; detection takes precedence over prediction at the "
                               "same level. They are implemented in sentinel_inference.alert_level() and the "
                               "thresholds come from preprocessing.json. In Vigil an alert is raised once per host "
                               "per level until the level changes, and windows whose lookback is not fully inside "
                               "the replay file never raise alerts."), "small", T.MUTED, pady=(8, 0))

        lim = Card(self.page)
        self.section(lim)
        section_title(lim.body, "Limitations").pack(fill="x", pady=(0, 8))
        for text in self._limitations(svc):
            paragraph(lim.body, "• " + text)

    def _limitations(self, svc) -> list[str]:
        out = []
        ew = reports.load_report("early_warning")
        if ew is not None and not ew.empty:
            main, _ = reports.split_xgboost(ew)
            hybrid = reports.primary_model_name(main)
            for ev in main["event"].astype(str).unique():
                d = main[main["event"].astype(str) == ev]
                h = d[d["model"] == hybrid]
                best = d.sort_values("early_warning_recall", ascending=False).iloc[0]
                n = int(d["events_evaluated"].max())
                if n and len(h):
                    out.append(f"Early warning is weak. Of {n} {ev} events in the test period the hybrid "
                               f"anticipated {int(h['anticipated'].iloc[0])} (recall "
                               f"{h['early_warning_recall'].iloc[0]:.3f}); {best['model']} anticipated "
                               f"{int(best['anticipated'])} (recall {best['early_warning_recall']:.3f}) "
                               "(reports/early_warning.csv).")
        spans = reports.load_report("attack_type_time_spans")
        cfg = svc.cfg.get("config", {})
        if spans is not None and cfg.get("BLOCK_HOURS") and svc.cfg.get("split_mode") == "blocked":
            att = spans[spans["type"].astype(str) != "normal"]
            if len(att):
                shortest = float(((att["max"] - att["min"]) / 3600).min())
                out.append(f"The split interleaves {float(cfg['BLOCK_HOURS']) * 60:g}-minute blocks, while every "
                           f"attack type spans at least {shortest:.1f} hours of recorded time, so each attack "
                           "campaign appears in training, validation and test blocks. Test scores therefore "
                           "measure recognition of campaigns seen in training, and may be optimistic for "
                           "attacks or periods not seen in training.")
        sc = reports.load_report("split_coverage")
        if sc is not None and "test" in sc:
            small = sc.sort_values("test").iloc[0]
            out.append(f"Some classes are rare: the smallest in the test split is {small['type']} with "
                       f"{int(small['test']):,} flows (reports/split_coverage.csv).")
        out.append("All results come from one testbed dataset (ToN_IoT). The model has not been evaluated on live "
                   "traffic or on other networks.")
        out.append("A forecast is scored only where the next horizon of labels exists; windows at the end of a "
                   "test block have no future labels and cannot be checked.")
        out.append("Live Replay replays recorded traffic from replay_flows.csv; it is not a live network capture.")
        return out
