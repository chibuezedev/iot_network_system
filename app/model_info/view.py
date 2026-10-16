from __future__ import annotations

import tkinter as tk

from app.common import theme
from app.common.context import AppContext
from app.common.widgets import ScrollFrame, dataframe_table
from services import reports
from services.hybrid_service import TIER_NAMES

# Columns of model_comparison.csv summarised on the hybrid card (whichever exist).
HYBRID_SUMMARY_METRICS = ["detection_rate", "false_positive_rate", "f1_macro", "f1_binary", "pr_auc", "roc_auc"]


class ModelInfoView(tk.Frame):
    def __init__(self, parent, ctx: AppContext):
        super().__init__(parent, bg=theme.BG_PRIMARY)
        self.ctx = ctx
        self._build()

    def _build(self) -> None:
        scroll = ScrollFrame(self)
        scroll.pack(fill="both", expand=True)
        pad = tk.Frame(scroll.body, bg=theme.BG_PRIMARY, padx=24, pady=18)
        pad.pack(fill="both", expand=True)

        tk.Label(
            pad,
            text="Model Info",
            bg=theme.BG_PRIMARY,
            fg=theme.TEXT_PRIMARY,
            font=(theme.FONT_HEADER[0], 18, "bold"),
        ).pack(anchor="w", pady=(0, 14))

        row = tk.Frame(pad, bg=theme.BG_PRIMARY)
        row.pack(fill="x")
        row.columnconfigure(0, weight=1)
        row.columnconfigure(1, weight=1)

        self._hybrid_card(row)

        spotter_metrics = getattr(self.ctx.spotter, "reference_metrics", None)
        risk_metrics = getattr(self.ctx.risk_analyst, "reference_metrics", None)

        self._model_card(
            row,
            col=0,
            row=1,
            name="Spotter (legacy baseline)",
            subtitle="Per-flow attack detection · CICIoT2023 · no forecasting",
            purpose="Classifies each network flow into one of 34 classes (benign traffic plus 33 named "
            "attack categories spanning DDoS, DoS, Mirai botnet, reconnaissance, spoofing, web "
            "exploitation, and brute-force families) trained on CICIoT2023-style flow features. "
            "Each flow is classified on its own; time plays no part.",
            metrics=spotter_metrics,
            metrics_source=getattr(self.ctx.spotter, "reference_metrics_source", None),
            tiers_fallback=None,
        )
        self._model_card(
            row,
            col=1,
            row=1,
            name="Risk Analyst (legacy baseline)",
            subtitle="Per-flow severity tier · ToN_IoT train/test file · no forecasting",
            purpose="Assigns a single connection to one of 5 severity tiers, from Normal traffic "
            "through Reconnaissance, Access/Compromise, High-severity DoS/DDoS, up to Critical "
            "(ransomware-pattern) traffic, using only that connection's own ToN_IoT-style features. "
            "It does not use time and does not forecast.",
            metrics=risk_metrics,
            tiers_fallback="Normal \u2192 Reconnaissance \u2192 Access/Compromise \u2192 "
            "High (DoS/DDoS) \u2192 Critical (Ransomware)",
        )

        note = tk.Frame(
            pad,
            bg=theme.BG_CARD,
            highlightbackground=theme.ACCENT_AMBER,
            highlightthickness=1,
        )
        note.pack(fill="x", pady=(16, 0))
        tk.Label(
            note,
            text="Detection, prediction and time in the two systems",
            bg=theme.BG_CARD,
            fg=theme.ACCENT_AMBER,
            font=theme.FONT_HEADER,
        ).pack(anchor="w", padx=16, pady=(12, 4))
        hm = f"{self.ctx.hybrid.horizon_minutes:g}" if self.ctx.hybrid else "the horizon"
        explanation = (
            "RF\u2013LSTM hybrid (primary). Trained on the ToN_IoT processed network data, with flows ordered by "
            "their recorded Zeek capture time (ts). Flows are grouped into fixed windows per destination host; the "
            "model detects the severity tier of the current window and forecasts the highest severity tier within "
            f"the next {hm} minutes. Hybrid Replay and Risk Timeline show recorded capture times only, and the "
            "replay processes flows in recorded order.\n\n"
            "Legacy XGBoost (baseline). CICIoT2023 and the ToN_IoT train/test file have no usable timestamps, "
            "so Spotter and Risk Analyst are per-flow classifiers only: no sequence model and no forecasting. "
            "Their Live Monitor demo draws rows at random from data/simulations_feed.csv, which pairs unrelated "
            "rows from the two datasets (each row carries a native feature set for each model) and assigns "
            "generated times, source IPs and device names for display. That feed is a non-chronological sample "
            "and never drives a hybrid timeline or forecast."
        )
        tk.Label(
            note,
            text=explanation,
            bg=theme.BG_CARD,
            fg=theme.TEXT_PRIMARY,
            font=theme.FONT_LABEL,
            justify="left",
            wraplength=920,
        ).pack(anchor="w", padx=16, pady=(0, 14))

    def _hybrid_card(self, parent) -> None:
        card = tk.Frame(parent, bg=theme.BG_CARD, highlightbackground=theme.ACCENT_CYAN, highlightthickness=1)
        card.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=6, pady=(2, 12))
        inner = tk.Frame(card, bg=theme.BG_CARD, padx=18, pady=16)
        inner.pack(fill="both", expand=True)
        tk.Label(inner, text="RF–LSTM hybrid", bg=theme.BG_CARD, fg=theme.ACCENT_CYAN,
                 font=(theme.FONT_LOGO[0], 16, "bold")).pack(anchor="w")
        tk.Label(inner, text="Primary model · detection of the current window + forecast of the horizon ahead",
                 bg=theme.BG_CARD, fg=theme.TEXT_MUTED, font=theme.FONT_LABEL).pack(anchor="w", pady=(0, 10))
        svc = self.ctx.hybrid
        if svc is None:
            tk.Label(inner, text=self.ctx.hybrid_error or "RF-LSTM hybrid is not loaded.", bg=theme.BG_CARD,
                     fg=theme.ACCENT_RED, font=theme.FONT_LABEL).pack(anchor="w")
            return
        tiers = " → ".join(TIER_NAMES)
        purpose = (
            "Trained on ToN_IoT processed network data ordered by recorded Zeek capture time (ts). "
            f"Layer 1: a Random Forest labels each flow as one of {len(svc.type_order)} traffic types "
            f"({', '.join(svc.type_order)}). Layer 2: an LSTM reads the last {svc.lookback} windows of "
            f"{svc.window_sec:g} s for each destination host (window statistics plus the RF evidence) and has two "
            "heads: detection (severity tier of the current window) and forecast (highest severity tier within the "
            f"next {svc.horizon_minutes:g} min). Tiers: {tiers}."
        )
        tk.Label(inner, text=purpose, bg=theme.BG_CARD, fg=theme.TEXT_PRIMARY, font=theme.FONT_LABEL,
                 justify="left", wraplength=880).pack(anchor="w", pady=(0, 6))
        if not svc.lstm_available:
            tk.Label(inner, text=f"LSTM layer unavailable on this machine: {svc.lstm_error}", bg=theme.BG_CARD,
                     fg=theme.ACCENT_RED, font=theme.FONT_LABEL, justify="left", wraplength=880).pack(anchor="w")

        mc = reports.load_report("model_comparison")
        name = reports.primary_model_name(mc)
        tk.Label(inner, text=f"TEST-PERIOD PERFORMANCE — “{name}” rows of reports/model_comparison.csv",
                 bg=theme.BG_CARD, fg=theme.TEXT_MUTED,
                 font=(theme.FONT_LABEL[0], 8, "bold")).pack(anchor="w", pady=(8, 4))
        if mc is None:
            tk.Label(inner, text="reports/model_comparison.csv not found.", bg=theme.BG_CARD, fg=theme.ACCENT_RED,
                     font=theme.FONT_LABEL).pack(anchor="w")
        else:
            rows = mc[mc["model"].astype(str) == name]
            cols = [c for c in HYBRID_SUMMARY_METRICS if c in rows.columns]
            table = rows[["task", *cols]].dropna(axis=1, how="all")
            dataframe_table(inner, table, height=max(1, len(table))).pack(fill="x")
        facts = []
        types = reports.test_split_types()
        if types is not None:
            facts.append("Traffic types in the test split: " + ", ".join(types) + " (reports/split_coverage.csv).")
        if reports.early_warning_events_evaluated() == 0:
            facts.append("No onset/escalation events occur in the test period (reports/early_warning.csv), so "
                         "early warning is not evaluated by these artifacts.")
        facts.append("Full tables for all compared models: Model Comparison screen.")
        tk.Label(inner, text="\n".join(facts), bg=theme.BG_CARD, fg=theme.TEXT_MUTED, font=(theme.FONT_LABEL[0], 8),
                 justify="left", wraplength=880).pack(anchor="w", pady=(8, 0))

    def _model_card(
        self, parent, col, name, subtitle, purpose, metrics, tiers_fallback, row=0, metrics_source=None
    ) -> None:
        card = tk.Frame(
            parent,
            bg=theme.BG_CARD,
            highlightbackground=theme.BORDER,
            highlightthickness=1,
        )
        card.grid(row=row, column=col, sticky="nsew", padx=6, pady=2)
        inner = tk.Frame(card, bg=theme.BG_CARD, padx=18, pady=16)
        inner.pack(fill="both", expand=True)

        tk.Label(
            inner,
            text=name,
            bg=theme.BG_CARD,
            fg=theme.ACCENT_CYAN,
            font=(theme.FONT_LOGO[0], 16, "bold"),
        ).pack(anchor="w")
        tk.Label(
            inner,
            text=subtitle,
            bg=theme.BG_CARD,
            fg=theme.TEXT_MUTED,
            font=theme.FONT_LABEL,
        ).pack(anchor="w", pady=(0, 10))
        tk.Label(
            inner,
            text=purpose,
            bg=theme.BG_CARD,
            fg=theme.TEXT_PRIMARY,
            font=theme.FONT_LABEL,
            justify="left",
            wraplength=380,
        ).pack(anchor="w", pady=(0, 12))

        if metrics:
            self._render_metrics(inner, metrics, metrics_source)
        elif tiers_fallback:
            self._render_pending_metrics(inner, tiers_fallback)
        else:
            tk.Label(
                inner,
                text="No reference metrics attached to this model yet.",
                bg=theme.BG_CARD,
                fg=theme.TEXT_MUTED,
                font=theme.FONT_LABEL,
                justify="left",
                wraplength=380,
            ).pack(anchor="w")

    def _render_metrics(self, inner, metrics: dict, source: str | None = None) -> None:
        tk.Label(
            inner,
            text="TEST-SET PERFORMANCE (reference)",
            bg=theme.BG_CARD,
            fg=theme.TEXT_MUTED,
            font=(theme.FONT_LABEL[0], 8, "bold"),
        ).pack(anchor="w", pady=(4, 4))
        for k, v in metrics.items():
            mrow = tk.Frame(inner, bg=theme.BG_CARD)
            mrow.pack(fill="x", pady=1)
            tk.Label(
                mrow,
                text=k,
                bg=theme.BG_CARD,
                fg=theme.TEXT_PRIMARY,
                font=theme.FONT_MONO_SMALL,
                anchor="w",
            ).pack(side="left")
            tk.Label(
                mrow,
                text=f"{v:.4f}",
                bg=theme.BG_CARD,
                fg=theme.ACCENT_GREEN,
                font=(theme.FONT_MONO_SMALL[0], 9, "bold"),
            ).pack(side="right")
        tk.Label(
            inner,
            text=(f"Source: {source} (model_artifacts/spotter_metrics.json)" if source else
                  "Figures above are the real research model's reported held-out test "
                  "metrics; they describe the actual trained model, independent of whichever "
                  "artifact file is currently loaded for this demo session."),
            bg=theme.BG_CARD,
            fg=theme.TEXT_MUTED,
            font=(theme.FONT_LABEL[0], 8),
            justify="left",
            wraplength=380,
        ).pack(anchor="w", pady=(10, 0))

    def _render_pending_metrics(self, inner, tiers_text: str) -> None:
        """Shown when a model has no reference_metrics attached. Looks like a
        deliberate state, not a missing feature, so the two cards never feel
        mismatched next to each other."""
        tk.Label(
            inner,
            text="RISK TIERS",
            bg=theme.BG_CARD,
            fg=theme.TEXT_MUTED,
            font=(theme.FONT_LABEL[0], 8, "bold"),
        ).pack(anchor="w", pady=(4, 4))
        tk.Label(
            inner,
            text=tiers_text,
            bg=theme.BG_CARD,
            fg=theme.TEXT_PRIMARY,
            font=theme.FONT_LABEL,
            justify="left",
            wraplength=380,
        ).pack(anchor="w")

        divider = tk.Frame(inner, bg=theme.BORDER, height=1)
        divider.pack(fill="x", pady=(12, 10))

        tk.Label(
            inner,
            text="TEST-SET PERFORMANCE (reference)",
            bg=theme.BG_CARD,
            fg=theme.TEXT_MUTED,
            font=(theme.FONT_LABEL[0], 8, "bold"),
        ).pack(anchor="w", pady=(0, 4))
        tk.Label(
            inner,
            text="Not attached to this model yet. Add a reference_metrics dict to "
            "RiskAnalyst in models/inference.py (same pattern used for Spotter) "
            "once held-out test numbers are available, and they will appear here "
            "automatically.",
            bg=theme.BG_CARD,
            fg=theme.TEXT_MUTED,
            font=(theme.FONT_LABEL[0], 8),
            justify="left",
            wraplength=380,
        ).pack(anchor="w")
