"""
Vigil design tokens. Every colour is a (light, dark) pair in CustomTkinter's
order, so CTk widgets switch automatically with the appearance mode; non-CTk
code (matplotlib, tk.Canvas) resolves a pair with app.ui.theme.pick().

Contrast (WCAG 2.x, computed): text 17.5:1 light / 14.6:1 dark on cards; muted
text 6.4 / 6.8; every alert-level colour >= 4.4:1 as text/outline on cards and
rows in both themes, and filled-badge text (ON_FILL) >= 5.0:1 on every level fill.
Chart series pairs pass dataviz validate_palette.js in each theme.
"""

APP_NAME = "Vigil"
TAGLINE = "Intelligent IoT network surveillance · anomaly detection and predictive threat analytics"

# ---------------------------------------------------------------- surfaces & text
BG = ("#F5F7FA", "#0D1117")
SIDEBAR = ("#EBEFF4", "#10161D")
SURFACE = ("#FFFFFF", "#151B23")          # cards
SURFACE_2 = ("#EDF1F5", "#1D2531")        # rows, inputs, hover
BORDER = ("#D3DAE2", "#2B3441")
TEXT = ("#141A22", "#E7ECF2")
MUTED = ("#55606E", "#98A4B3")
FAINT = ("#8A95A3", "#5F6B7A")            # greyed-out (partial lookback) -- decorative only, always with a text note
ACCENT = ("#0B7A6E", "#3CC6B4")
ACCENT_HOVER = ("#09665C", "#5ED6C6")
ON_ACCENT = ("#FFFFFF", "#0D1117")
DANGER = ("#C4202F", "#F2616B")

# ---------------------------------------------------------------- alert levels (engine's alert_level names)
ALERT = {
    "NORMAL": ("#1B7F4B", "#4CC38A"),
    "WARNING": ("#8A6100", "#E3B341"),
    "HIGH": ("#B54708", "#F2924A"),
    "CRITICAL": ("#C4202F", "#F2616B"),
}
ALERT_ORDER = ["CRITICAL", "HIGH", "WARNING", "NORMAL"]
ON_FILL = ("#FFFFFF", "#0D1117")          # text on a filled alert badge

# Severity tiers 0..4 reuse the alert scale (Normal, Recon, Access, High, Critical).
TIER_COLOR = [ALERT["NORMAL"], ALERT["WARNING"], ALERT["HIGH"], ALERT["CRITICAL"], ALERT["CRITICAL"]]

# ---------------------------------------------------------------- chart series (validated per theme)
SERIES_P_ANY = ("#0891b2", "#0891b2")
SERIES_P_ESC = ("#7c5cd6", "#9a7cf0")
SERIES_TRUTH = ("#55606E", "#C9D1D9")
CHART_GRID = ("#E3E8EE", "#232C38")

# ---------------------------------------------------------------- type & space
FONT_FAMILIES = ["Segoe UI", "Helvetica Neue", "Inter", "Arial"]
MONO_FAMILIES = ["Cascadia Mono", "Consolas", "DejaVu Sans Mono", "Courier New"]
FONT_ROLES = {
    "display": ("sans", 30, "bold"),
    "clock": ("mono", 30, "bold"),
    "h1": ("sans", 22, "bold"),
    "h2": ("sans", 16, "bold"),
    "body": ("sans", 13, "normal"),
    "body_bold": ("sans", 13, "bold"),
    "small": ("sans", 11, "normal"),
    "small_bold": ("sans", 11, "bold"),
    "mono": ("mono", 12, "normal"),
    "mono_bold": ("mono", 12, "bold"),
    "mono_small": ("mono", 11, "normal"),
}

SPACE = {"xs": 4, "s": 8, "m": 12, "l": 16, "xl": 24, "xxl": 32}
RADIUS_CARD = 12
RADIUS_BADGE = 6
SIDEBAR_WIDTH = 228
