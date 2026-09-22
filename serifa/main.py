"""Application entry point."""

from __future__ import annotations

import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GtkSource", "5")

from gi.repository import Adw, Gio, GtkSource

from .window import Window


class Serifa(Adw.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id="br.ufmg.vinibispo.Serifa",
            flags=Gio.ApplicationFlags.HANDLES_OPEN,
        )
        self._window: Window | None = None

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        GtkSource.init()

    def do_activate(self) -> None:
        self._ensure_window().present()

    def do_open(self, files, n, hint) -> None:
        window = self._ensure_window()
        window.present()
        for file in files:
            path = file.get_path()
            if path:
                window.open_file(Path(path))
                break

    def _ensure_window(self) -> Window:
        if self._window is None:
            self._window = Window(application=self)
        return self._window


def main() -> int:
    return Serifa().run(sys.argv)
