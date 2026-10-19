"""Settings -- theme, default replay speed, artifacts folder, and a button that
re-runs scripts/check_hybrid.py (the parity check) and shows its output."""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from tkinter import filedialog

import customtkinter as ctk

from app.common.paths import resource_path
from app.screens.base import Screen
from app.screens.live_replay import SPEEDS
from app.ui import theme, tokens as T
from app.ui.widgets import Card, autowrap, button, label, section_title, show_toast
from services import prefs, reports
from services.hybrid_service import ARTIFACT_DIR

CHECK_SCRIPT = resource_path("scripts", "check_hybrid.py")
RESULT_TEXT = {0: ("PASS", T.ALERT["NORMAL"]), 1: ("FAIL", T.DANGER), 2: ("LSTM layer unavailable", T.ALERT["HIGH"])}


def _seg(parent, values, command):
    return ctk.CTkSegmentedButton(parent, values=values, command=command, font=theme.font("small"),
                                  selected_color=T.ACCENT, selected_hover_color=T.ACCENT_HOVER,
                                  unselected_color=T.SURFACE_2, unselected_hover_color=T.BORDER,
                                  text_color=T.TEXT, fg_color=T.SURFACE_2)


class SettingsScreen(Screen):
    title = "Settings"
    subtitle = "Preferences are saved on this machine (prefs.json next to users.db)."

    def build(self) -> None:
        self.header()

        ap = Card(self.page)
        self.section(ap)
        section_title(ap.body, "Appearance").pack(fill="x")
        self.theme_seg = _seg(ap.body, ["Dark", "Light"], lambda v: theme.set_mode(v.lower()))
        self.theme_seg.set("Dark" if theme.mode() == "dark" else "Light")
        self.theme_seg.pack(anchor="w", pady=(10, 0))
        unsub = theme.on_change(lambda: self.theme_seg.set("Dark" if theme.mode() == "dark" else "Light"))
        self.bind("<Destroy>", lambda e: unsub() if e.widget is self else None)

        rp = Card(self.page)
        self.section(rp)
        section_title(rp.body, "Live Replay").pack(fill="x")
        label(rp.body, "Default requested speed (×). The replay may run slower when model compute takes "
                       "longer; Live Replay always shows the actual speed.", "small", T.MUTED).pack(anchor="w",
                                                                                                    pady=(4, 8))
        self.speed_seg = _seg(rp.body, SPEEDS, lambda v: prefs.set("replay_speed", int(v)))
        cur = str(prefs.get("replay_speed") or 60)
        self.speed_seg.set(cur if cur in SPEEDS else "60")
        self.speed_seg.pack(anchor="w")

        af = Card(self.page)
        self.section(af)
        section_title(af.body, "Artifacts folder", "unzipped Kaggle notebook output").pack(fill="x")
        self.path_label = label(af.body, "", "mono", T.TEXT)
        self.path_label.pack(anchor="w", pady=(8, 2))
        self.path_note = autowrap(label(af.body, "", "small", T.MUTED), af.body, margin=8)
        self.path_note.pack(anchor="w", fill="x")
        row = ctk.CTkFrame(af.body, fg_color="transparent")
        row.pack(anchor="w", pady=(10, 0))
        button(row, "Choose folder…", self._choose, "secondary", width=150).pack(side="left")
        button(row, "Use default", self._reset_dir, "ghost", width=110).pack(side="left", padx=8)
        self._show_dir()

        pc = Card(self.page)
        self.section(pc)
        section_title(pc.body, "Parity check", "scripts/check_hybrid.py").pack(fill="x")
        autowrap(label(pc.body, "Re-computes the hybrid's outputs for every dashboard_feed.csv row inside the "
                                "replay's recorded time range and compares them with the notebook's values "
                                "(p_attack_next within 1e-4, det_tier and fut_tier exact).", "small", T.MUTED),
                 pc.body, margin=8).pack(anchor="w", fill="x", pady=(4, 8))
        row2 = ctk.CTkFrame(pc.body, fg_color="transparent")
        row2.pack(fill="x")
        self.check_btn = button(row2, "Re-run parity check", self._run_check, "primary", width=180)
        self.check_btn.pack(side="left")
        self.check_result = label(row2, "", "body_bold", T.MUTED)
        self.check_result.pack(side="left", padx=14)
        self.output = ctk.CTkTextbox(pc.body, height=190, font=theme.font("mono_small"), fg_color=T.SURFACE_2,
                                     text_color=T.TEXT, border_color=T.BORDER, border_width=1, wrap="word")
        self.output.pack(fill="x", pady=(10, 0))
        self.output.insert("end", "Not run in this session.")
        self.output.configure(state="disabled")

        info = Card(self.page)
        self.section(info)
        section_title(info.body, "Environment").pack(fill="x")
        svc = self.ctx.hybrid
        lines = [f"Python {sys.version.split()[0]}", self._versions()]
        if svc is not None:
            lines.append("LSTM layer: " + ("loaded" if svc.lstm_available else f"unavailable — {svc.lstm_error}"))
            lines += [f"Load warning: {w}" for w in svc.load_warnings] or ["No model load warnings."]
        for ln in lines:
            autowrap(label(info.body, ln, "mono_small", T.MUTED), info.body, margin=8).pack(anchor="w", fill="x")

    @staticmethod
    def _versions() -> str:
        out = []
        for mod in ("torch", "sklearn", "pandas", "numpy", "customtkinter"):
            try:
                m = __import__(mod)
                out.append(f"{mod} {getattr(m, '__version__', '?')}")
            except Exception:
                out.append(f"{mod} not installed")
        return " · ".join(out)

    # ------------------------------------------------------------------ artifacts folder
    def _show_dir(self) -> None:
        chosen = prefs.get("artifacts_dir")
        self.path_label.configure(text=reports.display_path(ARTIFACT_DIR))
        if chosen and os.path.normcase(os.path.abspath(chosen)) != os.path.normcase(os.path.abspath(ARTIFACT_DIR)):
            self.path_note.configure(text=f"Chosen: {chosen}. Restart Vigil to load it.", text_color=T.ALERT["HIGH"])
        else:
            self.path_note.configure(text="In use now." + ("" if chosen else " (default: artifacts_rf_lstm/ next to "
                                                                             "main.py)"), text_color=T.MUTED)

    def _choose(self) -> None:
        path = filedialog.askdirectory(title="Choose the unzipped artifacts_rf_lstm folder")
        if not path:
            return
        need = [os.path.join("models", "preprocessing.json"), os.path.join("models", "sentinel_inference.py"),
                os.path.join("data", "replay_flows.csv")]
        missing = [n for n in need if not os.path.exists(os.path.join(path, n))]
        if missing:
            show_toast(self, "Not an artifacts folder", "Missing: " + ", ".join(missing), "warning")
            return
        prefs.set("artifacts_dir", path)
        self._show_dir()
        show_toast(self, "Artifacts folder saved", "Restart Vigil to load it.", "info")

    def _reset_dir(self) -> None:
        prefs.set("artifacts_dir", None)
        self._show_dir()

    # ------------------------------------------------------------------ parity check
    def _run_check(self) -> None:
        self.check_btn.configure(state="disabled", text="Running…")
        self.check_result.configure(text="running (about a minute)", text_color=T.MUTED)
        self._set_output("")
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self) -> None:
        try:
            proc = subprocess.run([sys.executable, CHECK_SCRIPT], cwd=resource_path(), capture_output=True,
                                  text=True, timeout=1800,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            out, code = (proc.stdout or "") + (proc.stderr or ""), proc.returncode
        except Exception as exc:
            out, code = f"{type(exc).__name__}: {exc}", -1
        self.after(0, lambda: self._done(out, code))

    def _done(self, out: str, code: int) -> None:
        if not self.winfo_exists():
            return
        text, color = RESULT_TEXT.get(code, (f"error (exit {code})", T.DANGER))
        self.check_result.configure(text=text, text_color=color)
        self.check_btn.configure(state="normal", text="Re-run parity check")
        self._set_output(out.strip() or "(no output)")

    def _set_output(self, text: str) -> None:
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.insert("end", text)
        self.output.configure(state="disabled")
