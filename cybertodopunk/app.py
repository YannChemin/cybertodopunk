"""Application entry point (the window; the CLI is in cli.py).

SPDX-License-Identifier: Unlicense
"""

import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, Gtk  # noqa: E402

from . import __version__, brand  # noqa: E402
from .brand import APP_ID  # noqa: E402


class CyberTodoPunk(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.window = None

    def do_startup(self):
        Adw.Application.do_startup(self)
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        brand.add_icon_paths(Gdk.Display.get_default())
        Gtk.Window.set_default_icon_name(APP_ID)
        css = Gtk.CssProvider()
        css.load_from_path(str(Path(__file__).parent / "ui" / "style.css"))
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        for name, cb, accel in (
            ("quit", lambda *_: self.quit(), "<primary>q"),
            ("about", self._about, None),
        ):
            act = Gio.SimpleAction.new(name, None)
            act.connect("activate", cb)
            self.add_action(act)
            if accel:
                self.set_accels_for_action(f"app.{name}", [accel])
        self.set_accels_for_action("win.refresh", ["<primary>r", "F5"])

    def do_activate(self):
        from .ui.window import MainWindow

        if self.window is None:
            self.window = MainWindow(self)
        self.window.present()

    def _about(self, *_):
        about = Adw.AboutDialog(
            application_name="CyberTodoPunk",
            application_icon=APP_ID,
            version=__version__,
            developer_name="Yann Chemin",
            license_type=Gtk.License.UNKNOWN,
            license="Unlicense: free and unencumbered software released into the public domain.",
            website="https://github.com/YannChemin/cybertodopunk",
            comments="Meeting actions from the ACTIONS.tex files of LaTeX reports.",
        )
        about.present(self.window)


def main(argv=None):
    brand.load_fonts()
    return CyberTodoPunk().run([sys.argv[0], *(argv or [])])
