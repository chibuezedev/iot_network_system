"""
Resource path resolution.

Never hardcode absolute paths elsewhere in the app -- always resolve through
resource_path() so the project still works both when run from source and
when frozen into a PyInstaller onefile/onedir binary (sys._MEIPASS is the
temp extraction dir PyInstaller sets at runtime).
"""
import os
import sys


def _base_dir() -> str:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS  # type: ignore[attr-defined]
    # app/common/paths.py -> project root is two levels up
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def resource_path(*parts: str) -> str:
    return os.path.join(_base_dir(), *parts)


def user_data_path(*parts: str) -> str:
    """
    Writable location for users.db / logs, distinct from resource_path()
    since a frozen app's install directory may not be writable.
    Falls back to project root when running from source.
    """
    if getattr(sys, "frozen", False):
        base = os.path.join(os.path.expanduser("~"), ".sentineliot")
        os.makedirs(base, exist_ok=True)
        return os.path.join(base, *parts)
    return resource_path(*parts)
