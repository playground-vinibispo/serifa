# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Vinícius Bispo e colaboradores

"""Application entry point."""

from __future__ import annotations

import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GtkSource", "5")

from gi.repository import Adw, Gio, GtkSource

from .workspace import Workspace


class Serifa(Adw.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id="br.ufmg.vinibispo.Serifa",
            flags=Gio.ApplicationFlags.HANDLES_OPEN,
        )

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        GtkSource.init()

    def do_activate(self) -> None:
        workspace = self._ensure_window()
        if not workspace.tabs.get_n_pages():
            workspace._new_document()
        workspace.present()

    def do_open(self, files, n, hint) -> None:
        for file in files:
            path = file.get_path()
            if path:
                self.open_document(Path(path))

    def open_document(self, path: Path):
        workspace = self._ensure_window()
        document = workspace.open_document(path)
        workspace.present()
        return document

    def _ensure_window(self) -> Workspace:
        for window in self.get_windows():
            if isinstance(window, Workspace):
                return window
        return Workspace(application=self)


def main() -> int:
    return Serifa().run(sys.argv)
