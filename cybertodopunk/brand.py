"""Brand assets: palette, bundled fonts and icons (shared with MetaMonitor).

SPDX-License-Identifier: Unlicense
"""

import ctypes
import ctypes.util
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"
APP_ID = "io.github.yannchemin.CyberTodoPunk"

YELLOW = "#fcee0a"
CYAN = "#00f0ff"
MAGENTA = "#ff2a6d"
RED = "#ff003c"
GREEN = "#39ff88"
TEXT = "#e6f1ff"
DIM = "#7a86a8"


def load_fonts():
    """Make the bundled Orbitron and Rajdhani visible to this process only."""
    fonts = DATA / "fonts"
    lib = ctypes.util.find_library("fontconfig")
    if not lib or not fonts.is_dir():
        return False
    try:
        fc = ctypes.CDLL(lib)
        fc.FcConfigAppFontAddDir.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        return bool(fc.FcConfigAppFontAddDir(None, str(fonts).encode()))
    except (OSError, AttributeError):
        return False


def add_icon_paths(display):
    from gi.repository import Gtk

    theme = Gtk.IconTheme.get_for_display(display)
    for sub in ("icons", "icons/hicolor/scalable/apps", "icons/hicolor/symbolic/apps"):
        path = DATA / sub
        if path.is_dir():
            theme.add_search_path(str(path))
