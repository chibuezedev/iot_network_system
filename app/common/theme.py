"""Central theme constants -- change once here, applies everywhere."""

APP_NAME = "SentinelIoT"
TTKBOOTSTRAP_THEME = "cyborg"

# Palette
BG_PRIMARY = "#0b0f14"
BG_SECONDARY = "#121821"
BG_CARD = "#161d28"
BORDER = "#232c3a"

ACCENT_CYAN = "#22d3ee"
ACCENT_AMBER = "#f59e0b"
ACCENT_GREEN = "#34d399"
ACCENT_RED = "#ef4444"
ACCENT_DARKRED = "#7f1d1d"

TEXT_PRIMARY = "#e6edf3"
TEXT_MUTED = "#8b98a9"

SEVERITY_COLORS = {
    0: ACCENT_GREEN,    # Normal
    1: "#eab308",       # Reconnaissance -- yellow
    2: ACCENT_AMBER,    # Access/Compromise -- orange
    3: ACCENT_RED,      # High
    4: ACCENT_DARKRED,  # Critical -- pulsing dark red
}
SEVERITY_LABELS = {
    0: "Normal", 1: "Reconnaissance", 2: "Access/Compromise",
    3: "High (DoS/DDoS)", 4: "Critical (Ransomware)",
}

FONT_HEADER = ("Segoe UI Semibold", 14)
FONT_LABEL = ("Segoe UI", 10)
FONT_MONO = ("Consolas", 10)
FONT_MONO_SMALL = ("Consolas", 9)
FONT_LOGO = ("Segoe UI Semibold", 16)


def resolve_fonts() -> None:
    """
    Swap in whichever fonts actually exist on this OS. Must be called AFTER
    a Tk root exists (font family enumeration needs a live Tk interpreter).
    Segoe UI / Consolas are Windows fonts; on Linux/macOS we fall back to
    widely-available equivalents so the app still looks intentional rather
    than silently degrading to Tk's default serif.
    """
    global FONT_HEADER, FONT_LABEL, FONT_MONO, FONT_MONO_SMALL, FONT_LOGO
    import tkinter.font as tkfont

    available = set(tkfont.families())

    def pick(preferred: list[str]) -> str:
        for name in preferred:
            if name in available:
                return name
        return "TkDefaultFont"

    sans = pick(["Segoe UI", "Helvetica Neue", "DejaVu Sans", "Arial"])
    sans_bold = pick(["Segoe UI Semibold", "Segoe UI", "Helvetica Neue", "DejaVu Sans"])
    mono = pick(["Consolas", "JetBrains Mono", "Cascadia Mono", "DejaVu Sans Mono", "Courier New", "Courier"])

    FONT_HEADER = (sans_bold, 14)
    FONT_LABEL = (sans, 10)
    FONT_MONO = (mono, 10)
    FONT_MONO_SMALL = (mono, 9)
    FONT_LOGO = (sans_bold, 16)
