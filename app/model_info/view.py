from __future__ import annotations

import tkinter as tk

from app.common import theme
from app.common.context import AppContext


class ModelInfoView(tk.Frame):
    def __init__(self, parent, ctx: AppContext):
        super().__init__(parent, bg=theme.BG_PRIMARY)
        self.ctx = ctx
        self._build()

    def _build(self) -> None:
        pad = tk.Frame(self, bg=theme.BG_PRIMARY, padx=24, pady=18)
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

        spotter_metrics = getattr(self.ctx.spotter, "reference_metrics", None)
        risk_metrics = getattr(self.ctx.risk_analyst, "reference_metrics", None)

        self._model_card(
            row,
            col=0,
            name="Spotter",
            subtitle="Attack Detection Model",
            purpose="Classifies each network flow into one of 34 classes (benign traffic plus 33 named "
            "attack categories spanning DDoS, DoS, Mirai botnet, reconnaissance, spoofing, web "
            "exploitation, and brute-force families) trained on CICIoT2023-style flow features.",
            metrics=spotter_metrics,
            tiers_fallback=None,
        )
        self._model_card(
            row,
            col=1,
            name="Risk Analyst",
            subtitle="Severity / Predictive Risk Model",
            purpose="Scores a connection's forward-looking risk on a 5-tier scale, from Normal traffic "
            "through Reconnaissance, Access/Compromise, High-severity DoS/DDoS, up to Critical "
            "(ransomware-pattern) traffic, trained on ToN_IoT-style connection features.",
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
            text="On \u201cpredictive analytics\u201d and schema bridging",
            bg=theme.BG_CARD,
            fg=theme.ACCENT_AMBER,
            font=theme.FONT_HEADER,
        ).pack(anchor="w", padx=16, pady=(12, 4))
        explanation = (
            "\u201cPredictive\u201d here means forward-looking risk scoring -- how dangerous or escalating a "
            "traffic pattern looks -- not literal time-series forecasting. The underlying CICIoT2023 and "
            "ToN_IoT datasets do not carry real timestamps suitable for time-series modeling, so severity "
            "scoring on a single connection's features is the methodologically honest framing.\n\n"
            "Spotter and Risk Analyst come from two different datasets with two different schemas, so there "
            "is no principled per-packet mapping from one model's features to the other's. This build uses "
            "an independent-parallel-slice approach: each replayed row carries its own native feature set "
            "for each model, both assigned to the same point on a shared synthetic timeline. The two "
            "verdicts shown together are two independent models' opinions about the same simulated moment, "
            "not one model's output feeding the other."
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

    def _model_card(
        self, parent, col, name, subtitle, purpose, metrics, tiers_fallback
    ) -> None:
        card = tk.Frame(
            parent,
            bg=theme.BG_CARD,
            highlightbackground=theme.BORDER,
            highlightthickness=1,
        )
        card.grid(row=0, column=col, sticky="nsew", padx=6, pady=2)
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
            self._render_metrics(inner, metrics)
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

    def _render_metrics(self, inner, metrics: dict) -> None:
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
            text="Figures above are the real research model's reported held-out test "
            "metrics; they describe the actual trained model, independent of whichever "
            "artifact file is currently loaded for this demo session.",
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
