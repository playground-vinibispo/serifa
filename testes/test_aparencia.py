"""Tipografia e medida da coluna.

Sem cores: a paleta é escolha de quem escreve, e a tentativa de impor uma foi
revertida a pedido. O que está aqui é o que não é gosto -- isto não é um
editor de código, e os instrumentos de código não servem a um parágrafo de
cem palavras.
"""

import unittest

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from testes.apoio import CasoGrafico, bombear, iniciar


class TestMobiliarioDeCodigo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not iniciar():
            raise unittest.SkipTest("sem servidor gráfico")

    def setUp(self):
        from serifa.editor import Editor
        self.ed = Editor()

    def test_sem_numeros_de_linha(self):
        self.assertFalse(self.ed.get_show_line_numbers())

    def test_sem_regua_de_oitenta_colunas(self):
        self.assertFalse(self.ed.get_show_right_margin())

    def test_sem_realce_da_linha_atual(self):
        self.assertFalse(self.ed.get_highlight_current_line())

    def test_quebra_por_palavra_inteira(self):
        # WORD_CHAR parte palavra no meio quando ela não cabe; em prosa isso
        # é pior que deixar a linha curta.
        self.assertEqual(self.ed.get_wrap_mode(), Gtk.WrapMode.WORD)

    def test_nao_impoe_esquema_de_cores(self):
        from serifa import aparencia
        self.assertFalse(hasattr(aparencia, "instalar_esquema"),
                         "a paleta é escolha do usuário")


class TestMedidaDaColuna(CasoGrafico):
    def caracteres_visiveis(self):
        from serifa.aparencia import largura_do_caractere
        largura = self.editor.get_width() - self.editor.get_left_margin() \
            - self.editor.get_right_margin()
        return largura // max(1, largura_do_caractere(self.editor))

    def test_painel_largo_limita_a_medida(self):
        from serifa.aparencia import MEDIDA
        self.janela.set_default_size(1900, 1000)
        self.janela._divisor.set_position(1300)
        bombear(500)
        self.assertLessEqual(self.caracteres_visiveis(), MEDIDA + 2)
        self.assertGreater(self.editor.get_left_margin(), 24)

    def test_painel_estreito_usa_a_margem_minima(self):
        self.janela.set_default_size(700, 600)
        self.janela._divisor.set_position(360)
        bombear(500)
        self.assertEqual(self.editor.get_left_margin(), 24)

    def test_margens_simetricas(self):
        bombear(300)
        self.assertEqual(self.editor.get_left_margin(), self.editor.get_right_margin())

    def test_fonte_do_editor(self):
        from serifa.aparencia import FONTE
        familia = self.editor.get_pango_context().get_font_description().get_family()
        self.assertIn(FONTE, familia)


if __name__ == "__main__":
    unittest.main()
