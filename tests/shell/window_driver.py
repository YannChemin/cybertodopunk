"""Open the window with every report unrolled, or on a given page (shell test).

Usage: window_driver.py [tasks|settings]

SPDX-License-Identifier: Unlicense
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from gi.repository import GLib  # noqa: E402

from cybertodopunk import app, brand  # noqa: E402

PAGE = sys.argv[1] if len(sys.argv) > 1 else "tasks"


def arrange(a):
    win = a.window
    if win is None:
        return True
    for card in win.cards:
        card.set_expanded(True)
    win.stack.set_visible_child_name(PAGE)
    return False


brand.load_fonts()
application = app.CyberTodoPunk()
application.connect("activate", lambda a: GLib.timeout_add(500, arrange, a))
sys.exit(application.run([sys.argv[0]]))
