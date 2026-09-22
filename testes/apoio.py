"""Andaime dos testes.

O achado que torna a suíte viável: **não é preciso rodar `app.run()`**. Basta
registrar a aplicação, montar a janela, chamar `present()` e bombear o laço
principal à mão. A janela mapeia, o editor recebe foco, e os testes rodam em
segundos em vez de depender de temporizadores dentro de um laço que nunca
devolve o controle.

Nada aqui toca em arquivo do usuário: cada teste recebe uma pasta temporária.
"""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GtkSource", "5")
gi.require_version("Gdk", "4.0")

from gi.repository import Adw, Gdk, GLib, Gtk, GtkSource

RAIZ = Path(__file__).resolve().parent.parent

_iniciado = False


def iniciar() -> bool:
    """Liga GTK uma vez. Devolve False quando não há como abrir janela."""
    global _iniciado
    if not _iniciado:
        if not Gtk.init_check():
            return False
        Adw.init()
        GtkSource.init()
        _iniciado = True
    return True


def bombear(milissegundos: int = 200) -> None:
    """Deixa o laço principal andar sem tomar conta da execução."""
    contexto = GLib.MainContext.default()
    fim = time.monotonic() + milissegundos / 1000
    while time.monotonic() < fim:
        while contexto.pending():
            contexto.iteration(False)
        time.sleep(0.003)


def ate(condicao, limite_ms: int = 4000, passo_ms: int = 50) -> bool:
    """Bombeia até a condição valer ou o tempo acabar. Devolve se valeu."""
    gasto = 0
    while gasto < limite_ms:
        if condicao():
            return True
        bombear(passo_ms)
        gasto += passo_ms
    return condicao()


def tecla(caractere: str) -> tuple[int, Gdk.ModifierType]:
    """Traduz um caractere para (keyval, estado), como o teclado entrega."""
    precisa_shift = caractere in '{}()<>"?:_|~^ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    estado = Gdk.ModifierType.SHIFT_MASK if precisa_shift else Gdk.ModifierType(0)
    return Gdk.unicode_to_keyval(ord(caractere)), estado


class CasoGrafico(unittest.TestCase):
    """Base dos testes que precisam de janela.

    Cada caso ganha a sua pasta temporária e a sua janela, e as duas somem no
    fim. O estado de sessão é redirecionado para a pasta do teste, senão os
    testes leriam e escreveriam a sessão real do usuário.
    """

    continua = False   # compilação contínua desligada salvo quando é o alvo

    @classmethod
    def setUpClass(cls) -> None:
        if not iniciar():
            raise unittest.SkipTest("sem servidor gráfico")
        cls._app = Adw.Application(
            application_id=f"br.ufmg.vinibispo.SerifaTeste.{cls.__name__}"
        )
        cls._app.register(None)

    def setUp(self) -> None:
        self._temporaria = tempfile.TemporaryDirectory(prefix="serifa-teste-")
        self.caixa = Path(self._temporaria.name)

        import serifa.window as modulo_janela

        self._estado_original = modulo_janela.STATE
        modulo_janela.STATE = self.caixa / "estado.json"

        from serifa.window import Window

        self.janela = Window(application=self._app)
        self.janela._continuous_build = self.continua
        self.janela.present()
        self.editor = self.janela._editor
        self.buffer = self.editor.buffer
        bombear(250)

    def tearDown(self) -> None:
        import serifa.window as modulo_janela

        modulo_janela.STATE = self._estado_original
        self.janela.destroy()
        bombear(60)
        self._temporaria.cleanup()

    # ------------------------------------------------------------ utilidades

    def arquivo(self, nome: str, conteudo: str) -> Path:
        caminho = self.caixa / nome
        caminho.write_text(conteudo, encoding="utf-8")
        return caminho

    def digitar(self, texto: str) -> None:
        """Insere caractere a caractere, como o teclado faz.

        Inserir a cadeia inteira de uma vez não é a mesma coisa: os pares
        automáticos só reagem a caractere solto, e foi assim que um teste
        cedo deu falso negativo.
        """
        for caractere in texto:
            self.buffer.insert_at_cursor(caractere)

    def teclar(self, sequencia: str) -> list[bool]:
        """Manda a sequência pelo caminho real: o controlador da janela.

        Emite o Shift antes das teclas que o exigem, porque o teclado emite --
        e foi exatamente esse Shift no meio que quebrava o vi{.
        """
        consumidas = []
        for caractere in sequencia:
            keyval, estado = tecla(caractere)
            if estado & Gdk.ModifierType.SHIFT_MASK:
                self.janela._on_key_pressed(None, Gdk.KEY_Shift_L, 0, Gdk.ModifierType(0))
            consumidas.append(self.janela._on_key_pressed(None, keyval, 0, estado))
        return consumidas

    def selecao(self) -> str | None:
        limites = self.buffer.get_selection_bounds()
        if not limites:
            return None
        return self.buffer.get_text(limites[0], limites[1], True)

    @property
    def texto(self) -> str:
        return self.buffer.get_text(*self.buffer.get_bounds(), True)
