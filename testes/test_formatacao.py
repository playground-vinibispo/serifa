"""Envoltórios de LaTeX, completação por contexto e aceleradores."""

import unittest

from testes.apoio import CasoGrafico, bombear


class TestFormatacao(CasoGrafico):
    def test_envolve_a_selecao(self):
        self.buffer.set_text("palavra solta")
        self.buffer.select_range(self.buffer.get_iter_at_offset(0),
                                 self.buffer.get_iter_at_offset(7))
        self.janela.formatar("textbf")
        self.assertEqual(self.texto, "\\textbf{palavra} solta")

    def test_sem_selecao_abre_as_chaves_com_o_cursor_dentro(self):
        self.buffer.set_text("abc")
        self.buffer.place_cursor(self.buffer.get_end_iter())
        self.janela.formatar("textit")
        self.assertEqual(self.texto, "abc\\textit{}")
        self.assertEqual(self.buffer.get_property("cursor-position"), 11)

    def test_nao_duplica_o_fechamento(self):
        # Inserido de uma vez, os pares automáticos não reagem -- eles só
        # olham caractere solto.
        self.buffer.set_text("")
        self.janela.formatar("enquote")
        self.assertEqual(self.texto, "\\enquote{}")

    def test_todos_os_formatos_produzem_o_comando(self):
        for nome, comando, _icone, _rotulo in self.janela.FORMATOS:
            self.buffer.set_text("")
            self.janela.formatar(comando)
            self.assertEqual(self.texto, f"\\{comando}{{}}", nome)


class TestAceleradores(CasoGrafico):
    def acel(self, nome):
        return self.janela.get_application().get_accels_for_action(f"win.{nome}")

    def test_ctrl_b_e_negrito_com_vim_desligado(self):
        self.assertEqual(self.acel("negrito"), ["<Control>b"])

    def test_compilar_nao_usa_mais_ctrl_b(self):
        self.assertNotIn("<Control>b", self.acel("compilar"))
        self.assertIn("F5", self.acel("compilar"))

    def test_vim_ligado_devolve_ctrl_b_e_ctrl_i(self):
        # Acelerador de janela é resolvido antes dos controladores do widget
        # e venceria o vim sem avisar; quem usa vim espera Ctrl+B como
        # página acima.
        self.janela._botao_vim.set_active(True)
        self.assertEqual(self.acel("negrito"), [])
        self.assertEqual(self.acel("italico"), [])

    def test_desligar_o_vim_devolve_os_atalhos(self):
        self.janela._botao_vim.set_active(True)
        self.janela._botao_vim.set_active(False)
        self.assertEqual(self.acel("negrito"), ["<Control>b"])


class TestCompletacaoPorContexto(CasoGrafico):
    def setUp(self):
        super().setUp()
        (self.caixa / "referencias.bib").write_text(
            "@book{einstein_infeld,\n  title = {A Evolução da Física},\n}\n",
            encoding="utf-8")
        self.alvo = self.arquivo("texto.tex", "\\label{sec:um}\nTexto.\n")
        self.janela.abrir(self.alvo)
        bombear(200)

    def digitar_no_fim(self, sufixo):
        self.buffer.set_text("\\label{sec:um}\nTexto.\n")
        self.buffer.place_cursor(self.buffer.get_end_iter())
        self.digitar(sufixo)
        bombear(250)

    def test_cite_oferece_as_chaves_do_bib(self):
        self.digitar_no_fim("\\cite{")
        self.assertTrue(self.janela._popup.visivel)
        self.assertIn("einstein_infeld", [i.texto for i in self.janela._popup._itens])

    def test_ref_oferece_os_rotulos_do_documento(self):
        self.digitar_no_fim("\\ref{")
        self.assertEqual([i.texto for i in self.janela._popup._itens], ["sec:um"])

    def test_prosa_nao_abre_o_balao(self):
        self.digitar_no_fim("texto comum ")
        self.assertFalse(self.janela._popup.visivel)

    def test_andar_com_o_cursor_nao_abre_o_balao(self):
        # O bug do preambulo.tex: passar por cima de um \begin{...} já
        # escrito abria o balão, que silenciava o vim, e a tecla seguinte
        # sobrescrevia uma letra.
        self.buffer.set_text("\\begin{center}\ntexto\n\\end{center}\n")
        bombear(200)
        self.buffer.place_cursor(self.buffer.get_iter_at_offset(9))
        bombear(250)
        self.assertFalse(self.janela._popup.visivel)

    def test_aceitar_insere_e_pula_o_fechamento(self):
        self.digitar_no_fim("\\cite{eif")
        self.assertTrue(self.janela._popup.visivel)
        self.janela._popup._aceitar(0)
        bombear(150)
        self.assertIn("\\cite{einstein_infeld}", self.texto)
        self.assertFalse(self.janela._popup.visivel)


if __name__ == "__main__":
    unittest.main()
