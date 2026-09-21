"""Comportamentos de edição: pares automáticos, contagem, ciclo do vim."""

import unittest

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk

from testes.apoio import iniciar


class TestEditor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not iniciar():
            raise unittest.SkipTest("sem servidor gráfico")

    def setUp(self):
        from serifa.editor import Editor
        self.ed = Editor()
        self.buffer = self.ed.buffer

    def digitar(self, texto):
        # Caractere a caractere: os pares só reagem a inserção de um, e
        # inserir a cadeia inteira dá falso negativo.
        for c in texto:
            self.buffer.insert_at_cursor(c)

    @property
    def texto(self):
        return self.buffer.get_text(*self.buffer.get_bounds(), True)

    # ------------------------------------------------------ pares automáticos

    def test_chave_fecha_sozinha(self):
        self.digitar("a{")
        self.assertEqual(self.texto, "a{}")
        self.assertEqual(self.buffer.get_property("cursor-position"), 2)

    def test_parentese_e_colchete(self):
        self.digitar("f(")
        self.assertEqual(self.texto, "f()")
        self.buffer.set_text("")
        self.digitar("v[")
        self.assertEqual(self.texto, "v[]")

    def test_cifrao_fecha(self):
        self.digitar("x$")
        self.assertEqual(self.texto, "x$$")

    def test_digitar_o_fechamento_passa_por_cima(self):
        self.digitar("a{")
        self.assertEqual(self.texto, "a{}")
        self.buffer.insert_at_cursor("}")
        self.assertEqual(self.texto, "a{}", "digitar } duplicou o fechamento")
        self.assertEqual(self.buffer.get_property("cursor-position"), 3)

    def test_cifrao_fecha_matematica_pulando_o_existente(self):
        # Digitar $ com um $ à frente fecha a matemática inline: o cursor
        # pula por cima. Antes isto produzia um terceiro $.
        self.buffer.set_text("$x$")
        self.buffer.place_cursor(self.buffer.get_iter_at_offset(2))
        self.buffer.insert_at_cursor("$")
        self.assertEqual(self.texto, "$x$")
        self.assertEqual(self.buffer.get_property("cursor-position"), 3)

    def test_begin_fecha_o_ambiente(self):
        self.digitar("\\begin{align}")
        self.buffer.insert_at_cursor("\n")
        self.assertEqual(self.texto, "\\begin{align}\n  \n\\end{align}")

    def test_begin_preserva_o_recuo(self):
        self.digitar("  \\begin{itemize}")
        self.buffer.insert_at_cursor("\n")
        self.assertIn("\n  \\end{itemize}", self.texto)

    # ----------------------------------------------------------- contagem

    def test_contagem_ignora_comando_e_chave(self):
        # "duas palavras" é o que se lê; \textbf e as chaves não contam.
        self.buffer.set_text("\\textbf{duas} palavras")
        self.assertEqual(self.ed.contar_palavras(), 2)

    def test_contagem_ignora_comentario(self):
        self.buffer.set_text("prosa de verdade\n% comentario que nao conta\n")
        self.assertEqual(self.ed.contar_palavras(), 3)

    def test_contagem_ignora_matematica_inline(self):
        self.buffer.set_text("antes $x^2 + y^2$ depois")
        self.assertEqual(self.ed.contar_palavras(), 2)

    # ---------------------------------------------------------------- vim

    def test_vim_liga_e_desliga(self):
        self.assertFalse(self.ed.vim_ativo)
        self.ed.alternar_vim(True)
        self.assertTrue(self.ed.vim_ativo)
        self.ed.alternar_vim(False)
        self.assertFalse(self.ed.vim_ativo)

    def test_vim_usa_overwrite_para_o_cursor_em_bloco(self):
        # É o que faz uma tecla vazada sobrescrever em vez de inserir. Se
        # isto mudar, o diagnóstico daquele bug muda junto.
        self.ed.alternar_vim(True)
        self.assertTrue(self.ed.get_overwrite())
        self.ed.alternar_vim(False)
        self.assertFalse(self.ed.get_overwrite())

    def test_tratar_tecla_e_inerte_com_vim_desligado(self):
        keyval = Gdk.unicode_to_keyval(ord("v"))
        self.assertFalse(self.ed.tratar_tecla(keyval, Gdk.ModifierType(0)))

    def test_v_em_modo_de_insercao_nao_arma_a_sequencia(self):
        # A guarda é comparar a contagem de caracteres antes e depois: se o
        # texto mudou, aquele "v" era a letra v.
        self.ed.alternar_vim(True)
        self.buffer.set_text("abc")
        self.buffer.place_cursor(self.buffer.get_end_iter())
        self.ed.tratar_tecla(Gdk.unicode_to_keyval(ord("v")), Gdk.ModifierType(0))
        self.buffer.insert_at_cursor("v")
        consumiu = self.ed.tratar_tecla(Gdk.unicode_to_keyval(ord("i")),
                                        Gdk.ModifierType(0))
        self.assertFalse(consumiu)


if __name__ == "__main__":
    unittest.main()
