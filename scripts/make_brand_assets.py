"""
Generate Vigil brand assets into app/brand/assets/:
  mark_light.png / mark_dark.png   logo mark in the light/dark accent (256 px)
  icon_<n>.png                     app icon tile at 16..256 px
  vigil.ico                        Windows icon (all sizes)
Run from the project root:  python scripts/make_brand_assets.py
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.brand.logo import ASSET_DIR, render_icon, render_mark  # noqa: E402
from app.ui import tokens  # noqa: E402

SIZES = [16, 24, 32, 48, 64, 128, 256]


def main() -> None:
    os.makedirs(ASSET_DIR, exist_ok=True)
    render_mark(256, tokens.ACCENT[0]).save(os.path.join(ASSET_DIR, "mark_light.png"))
    render_mark(256, tokens.ACCENT[1]).save(os.path.join(ASSET_DIR, "mark_dark.png"))
    icons = {n: render_icon(n) for n in SIZES}
    for n, im in icons.items():
        im.save(os.path.join(ASSET_DIR, f"icon_{n}.png"))
    icons[256].save(os.path.join(ASSET_DIR, "vigil.ico"), sizes=[(n, n) for n in SIZES])
    print("wrote", sorted(os.listdir(ASSET_DIR)))


if __name__ == "__main__":
    main()
