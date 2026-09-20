"""Ponto de entrada da aplicação."""

from __future__ import annotations

import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GtkSource", "5")

from gi.repository import Adw, Gio, GtkSource

from .window import Janela


class Serifa(Adw.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id="br.ufmg.vinibispo.Serifa",
            flags=Gio.ApplicationFlags.HANDLES_OPEN,
        )
        self._janela: Janela | None = None

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        GtkSource.init()

    def do_activate(self) -> None:
        self._garantir_janela().present()

    def do_open(self, arquivos, n, hint) -> None:
        janela = self._garantir_janela()
        janela.present()
        for arquivo in arquivos:
            caminho = arquivo.get_path()
            if caminho:
                janela.abrir(Path(caminho))
                break

    def _garantir_janela(self) -> Janela:
        if self._janela is None:
            self._janela = Janela(application=self)
        return self._janela


def main() -> int:
    return Serifa().run(sys.argv)
