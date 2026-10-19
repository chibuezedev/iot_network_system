"""
Vigil logo mark, drawn in code (Pillow): a pointy-top hexagon outline -- a
network node -- holding a forward chevron, the "look ahead" of forecasting.
Original geometry; no external artwork.

render_mark()  transparent mark in one colour
render_icon()  app icon: mark on a rounded dark tile
"""
from __future__ import annotations

import math
import os

from PIL import Image, ImageDraw

from app.ui import tokens

ASSET_DIR = os.path.join(os.path.dirname(__file__), "assets")
SS = 4  # supersampling factor for smooth edges


def _hex_points(cx, cy, r):
    return [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a)))
            for a in (-90, -30, 30, 90, 150, 210)]


def render_mark(size: int, color: str) -> Image.Image:
    s = size * SS
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    stroke = max(SS, round(s * 0.085))
    r = s * 0.46 - stroke / 2
    pts = _hex_points(s / 2, s / 2, r)
    d.line(pts + [pts[0], pts[1]], fill=color, width=stroke, joint="curve")
    # forward chevron, slightly right of centre
    cw, ch = s * 0.20, s * 0.36
    x0, y0 = s / 2 - cw * 0.45, s / 2 - ch / 2
    chevron = [(x0, y0), (x0 + cw, s / 2), (x0, y0 + ch)]
    d.line(chevron, fill=color, width=stroke, joint="curve")
    for x, y in (chevron[0], chevron[2]):   # rounded caps
        d.ellipse([x - stroke / 2, y - stroke / 2, x + stroke / 2, y + stroke / 2], fill=color)
    # small node dot at the left of the chevron's path
    dot = stroke * 0.95
    dx, dy = s / 2 - cw * 1.05, s / 2
    d.ellipse([dx - dot / 2, dy - dot / 2, dx + dot / 2, dy + dot / 2], fill=color)
    return img.resize((size, size), Image.LANCZOS)


def render_icon(size: int) -> Image.Image:
    s = size * SS
    tile = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(tile).rounded_rectangle([0, 0, s - 1, s - 1], radius=s * 0.22, fill=tokens.BG[1])
    tile = tile.resize((size, size), Image.LANCZOS)
    mark = render_mark(int(size * 0.78), tokens.ACCENT[1])
    off = (size - mark.width) // 2
    tile.alpha_composite(mark, (off, off))
    return tile


def mark_image(theme_index: int, size: int = 256) -> Image.Image:
    """Load the generated asset (0 = light theme, 1 = dark theme), or render it."""
    name = "mark_light.png" if theme_index == 0 else "mark_dark.png"
    path = os.path.join(ASSET_DIR, name)
    if os.path.exists(path):
        return Image.open(path).convert("RGBA")
    return render_mark(size, tokens.ACCENT[theme_index])


def icon_path() -> str | None:
    path = os.path.join(ASSET_DIR, "vigil.ico")
    return path if os.path.exists(path) else None
