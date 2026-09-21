r"""O arquivo aberto: ler, gravar, saber se está sujo, e vigiar o disco.

Estava tudo espalhado pela janela, misturado com montagem de widget e barra
de estado. É um conceito só, e é onde moram os defeitos que custam texto do
usuário -- gravar sem pedir, recarregar por cima de trabalho não salvo --, o
que é razão de sobra para viver em separado e ter nome próprio.

O documento não decide nada sobre interface. Quando o disco diverge do que
está na tela, ele **avisa** e deixa a janela resolver: recarregar sozinho
apagaria o trabalho de alguém, e essa escolha é de quem escreve.
"""

from __future__ import annotations

from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gio, GObject, Gtk


class Documento(GObject.Object):
    """Liga um buffer a um arquivo em disco."""

    __gsignals__ = {
        # O estado de sujeira mudou; a janela atualiza título e botão.
        "sujeira-mudou": (GObject.SignalFlags.RUN_FIRST, None, (bool,)),
        # Recarregado do disco, por conta própria ou a pedido.
        "recarregado": (GObject.SignalFlags.RUN_FIRST, None, ()),
        # O disco divergiu e há alteração não gravada: quem decide é a janela.
        "conflito": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "falhou": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self, buffer: Gtk.TextBuffer) -> None:
        super().__init__()
        self._buffer = buffer
        self._caminho: Path | None = None
        self._sujo = False
        self._vigia: Gio.FileMonitor | None = None

    # ----------------------------------------------------------- estado

    @property
    def caminho(self) -> Path | None:
        return self._caminho

    @property
    def nome(self) -> str:
        return self._caminho.name if self._caminho else ""

    @property
    def sujo(self) -> bool:
        return self._sujo

    def sujar(self) -> None:
        if not self._sujo:
            self._sujo = True
            self.emit("sujeira-mudou", True)

    def _limpar(self) -> None:
        self._buffer.set_modified(False)
        if self._sujo:
            self._sujo = False
        self.emit("sujeira-mudou", False)

    @property
    def texto(self) -> str:
        return self._buffer.get_text(*self._buffer.get_bounds(), True)

    # -------------------------------------------------------- disco

    def abrir(self, caminho: Path) -> bool:
        try:
            texto = caminho.read_text(encoding="utf-8")
        except OSError as erro:
            self.emit("falhou", f"Não deu para abrir: {erro}")
            return False

        self._buffer.begin_irreversible_action()
        self._buffer.set_text(texto)
        self._buffer.end_irreversible_action()
        self._buffer.place_cursor(self._buffer.get_start_iter())

        self._caminho = caminho
        self._limpar()
        self._vigiar(caminho)
        return True

    def gravar(self) -> bool:
        if self._caminho is None:
            return False
        try:
            self._caminho.write_text(self.texto, encoding="utf-8")
        except OSError as erro:
            self.emit("falhou", f"Não deu para salvar: {erro}")
            return False
        self._limpar()
        return True

    def definir_caminho(self, caminho: Path) -> None:
        """Usado pelo salvar-como, antes da primeira gravação."""
        self._caminho = caminho
        self._vigiar(caminho)

    def recarregar(self) -> bool:
        """Relê o arquivo preservando onde o cursor estava."""
        if self._caminho is None:
            return False
        try:
            texto = self._caminho.read_text(encoding="utf-8")
        except OSError as erro:
            self.emit("falhou", f"Não deu para recarregar: {erro}")
            return False

        onde = self._buffer.get_iter_at_mark(self._buffer.get_insert()).get_offset()
        self._buffer.begin_irreversible_action()
        self._buffer.set_text(texto)
        self._buffer.end_irreversible_action()
        self._buffer.place_cursor(
            self._buffer.get_iter_at_offset(min(onde, self._buffer.get_char_count()))
        )
        self._limpar()
        self.emit("recarregado")
        return True

    # -------------------------------------------------------- vigia

    def _vigiar(self, caminho: Path) -> None:
        """Observa o arquivo, para o editor não competir com o disco."""
        if self._vigia is not None:
            self._vigia.cancel()
        self._vigia = Gio.File.new_for_path(str(caminho)).monitor_file(
            Gio.FileMonitorFlags.NONE, None
        )
        self._vigia.connect("changed", self._ao_mudar_no_disco)

    def _ao_mudar_no_disco(self, _monitor, _arquivo, _outro, evento) -> None:
        if evento not in (
            Gio.FileMonitorEvent.CHANGES_DONE_HINT,
            Gio.FileMonitorEvent.CREATED,
        ):
            return
        if self._caminho is None:
            return
        try:
            em_disco = self._caminho.read_text(encoding="utf-8")
        except OSError:
            return

        # A nossa própria gravação dispara o vigia. Comparar o conteúdo é mais
        # robusto que um sinalizador de "ignore o próximo evento", porque o
        # monitor emite mais de um por gravação.
        if em_disco == self.texto:
            self.emit("sujeira-mudou", self._sujo)
            return

        if self._sujo:
            self.emit("conflito", self.nome)
        else:
            self.recarregar()
