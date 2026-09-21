"""Roteamento de teclas pela janela, e os text objects do modo visual.

Estes testes existem por causa de cinco diagnósticos errados seguidos. Cada um
guarda uma coisa que eu supus e estava errada.
"""

import unittest

import gi
gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gtk

from testes.apoio import CasoGrafico, bombear


class TestTextObjects(CasoGrafico):
    def setUp(self):
        super().setUp()
        self.janela._botao_vim.set_active(True)
        self.editor.grab_focus()
        bombear(300)

    def preparar(self, texto, marca):
        self.buffer.set_text(texto)
        self.buffer.place_cursor(self.buffer.get_iter_at_offset(texto.index(marca)))
        self.editor._sequencia.clear()

    def test_vi_chaves(self):
        self.preparar(r"\textbf{palavra aqui} fim", "palavra")
        self.teclar("vi{")
        self.assertEqual(self.selecao(), "palavra aqui")

    def test_va_chaves_inclui_os_delimitadores(self):
        self.preparar(r"\cabecalho{um}{dois} fim", "dois")
        self.teclar("va{")
        self.assertEqual(self.selecao(), "{dois}")

    def test_vi_parenteses(self):
        self.preparar(r"f(x, g(y)) fim", "y")
        self.teclar("vi(")
        self.assertEqual(self.selecao(), "y")

    def test_vi_aspas(self):
        self.preparar(r'diz "uma coisa" tal', "uma")
        self.teclar('vi"')
        self.assertEqual(self.selecao(), "uma coisa")

    def test_o_shift_no_meio_nao_zera_a_sequencia(self):
        # O bug que custou cinco tentativas: "{" exige Shift, o Shift chega
        # como tecla própria entre o "i" e o "{", e tratá-lo como ruído
        # zerava a máquina de estados.
        self.preparar(r"\textbf{palavra} fim", "palavra")
        keyval, estado = Gdk.unicode_to_keyval(ord("v")), Gdk.ModifierType(0)
        self.janela._ao_teclar(None, keyval, 0, estado)
        self.janela._ao_teclar(None, Gdk.unicode_to_keyval(ord("i")), 0, estado)
        self.janela._ao_teclar(None, Gdk.KEY_Shift_L, 0, estado)
        self.assertEqual(self.editor._sequencia, ["v", "i"],
                         "o Shift zerou a sequência")

    def test_sem_bloco_a_tecla_segue_para_o_vim(self):
        self.preparar("sem chave aqui", "chave")
        consumidas = self.teclar("vi{")
        self.assertFalse(consumidas[-1], "o { deveria seguir para o vim")
        self.assertIsNone(self.selecao())

    def test_o_vim_nunca_e_desligado_pelo_balao(self):
        # A correção errada anterior punha o controlador em NONE enquanto o
        # balão estivesse aberto, e o modo normal parava de funcionar.
        fase = lambda: self.editor._controlador_vim.get_propagation_phase()
        self.assertEqual(fase(), Gtk.PropagationPhase.CAPTURE)
        self.buffer.set_text("")
        self.digitar("\\cite{")
        bombear(300)
        self.assertEqual(fase(), Gtk.PropagationPhase.CAPTURE,
                         "o balão desligou o vim")


class TestFocoDaJanela(CasoGrafico):
    def test_sem_foco_no_editor_a_janela_nao_trata(self):
        self.janela._botao_vim.set_active(True)
        self.janela._campo_busca.grab_focus()
        bombear(200)
        keyval = Gdk.unicode_to_keyval(ord("v"))
        self.assertFalse(self.janela._ao_teclar(None, keyval, 0, Gdk.ModifierType(0)))


if __name__ == "__main__":
    unittest.main()
