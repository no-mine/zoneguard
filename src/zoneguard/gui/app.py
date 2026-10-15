"""Entry point for ZoneGuard's settings front-end."""
from __future__ import annotations

import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw

from .config_window import ConfigWindow


def main_config() -> None:
    app = Adw.Application(application_id="io.github.zoneguard.Settings")

    def on_activate(app: Adw.Application) -> None:
        win = ConfigWindow(app)
        win.present()

    app.connect("activate", on_activate)
    sys.exit(app.run(sys.argv))


if __name__ == "__main__":
    main_config()
