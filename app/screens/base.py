from __future__ import annotations

import customtkinter as ctk

from app.context import AppContext
from app.ui import tokens as T
from app.ui.widgets import Page, label, page_header

PAD_X = T.SPACE["xxl"]


class Screen(ctk.CTkFrame):
    """Base class for a Vigil screen. Content goes into self.page (one
    scrollable column); build() fills it, on_show() runs on every visit."""

    title = ""
    subtitle = ""

    def __init__(self, parent, ctx: AppContext):
        super().__init__(parent, fg_color=T.BG, corner_radius=0)
        self.ctx = ctx
        self.page = Page(self)
        self.page.pack(fill="both", expand=True)
        self.build()

    def build(self) -> None:  # pragma: no cover -- overridden
        self.header()

    def on_show(self) -> None:
        pass

    def header(self, title: str | None = None, subtitle: str | None = None):
        h = page_header(self.page, title or self.title, self.subtitle if subtitle is None else subtitle)
        h.pack(anchor="w", fill="x", padx=PAD_X, pady=(T.SPACE["xl"], T.SPACE["l"]))
        return h

    def section(self, widget, pady=(0, T.SPACE["l"]), **kw):
        """Pack a full-width block into the page with the standard side padding."""
        widget.pack(fill=kw.pop("fill", "x"), padx=PAD_X, pady=pady, **kw)
        return widget

    def unavailable(self, text: str) -> None:
        label(self.page, text, "body", T.DANGER, wraplength=900).pack(anchor="w", padx=PAD_X)
