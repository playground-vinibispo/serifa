"""Gravação, prévia e vigia de disco.

O invariante mais importante do editor está aqui: **digitar não escreve no
arquivo do usuário.** Até pouco tempo escrevia, como efeito colateral da
compilação contínua.
"""

import unittest

from serifa.build import Compilador
from testes.apoio import CasoGrafico, ate, bombear

DOCUMENTO = (
    "\\documentclass[12pt]{article}\n"
    "\\begin{document}\n"
    "Uma frase qualquer.\n"
    "\\end{document}\n"
)


class TestGravacao(CasoGrafico):
    def setUp(self):
        super().setUp()
        self.alvo = self.arquivo("texto.tex", DOCUMENTO)
        self.original = self.alvo.read_text(encoding="utf-8")
        self.janela.abrir(self.alvo)
        bombear(200)

    def test_abrir_carrega_o_texto(self):
        self.assertIn("Uma frase qualquer", self.texto)

    def test_digitar_nao_grava(self):
        self.digitar("mexido ")
        bombear(200)
        self.assertEqual(self.alvo.read_text(encoding="utf-8"), self.original)
        self.assertTrue(self.janela._sujo)

    def test_previa_nao_grava(self):
        self.digitar("mexido ")
        self.janela.previsualizar()
        bombear(400)
        self.assertEqual(self.alvo.read_text(encoding="utf-8"), self.original)

    def test_previa_compila_na_sombra_fora_do_projeto(self):
        sombra = Compilador.pasta_da_sombra(self.alvo.parent)
        self.assertNotIn(str(self.caixa), str(sombra))
        self.janela.previsualizar()
        self.assertTrue(ate(lambda: (sombra / "previa.tex").exists(), 4000))
        # nenhum resíduo de compilação na pasta do usuário
        self.assertEqual(sorted(p.name for p in self.caixa.iterdir()),
                         ["estado.json", "texto.tex"])

    def test_salvar_grava_e_limpa_o_sujo(self):
        self.digitar("mexido ")
        self.janela._gravar()
        self.assertIn("mexido", self.alvo.read_text(encoding="utf-8"))
        self.assertFalse(self.janela._sujo)

    def test_fechar_sujo_e_bloqueado(self):
        self.digitar("mexido ")
        self.assertTrue(self.janela._ao_pedir_fechamento())

    def test_fechar_limpo_passa_direto(self):
        self.assertFalse(self.janela._ao_pedir_fechamento())

    def test_botao_salvar_reflete_o_estado(self):
        self.assertFalse(self.janela._botao_salvar.get_sensitive())
        self.digitar("x")
        bombear(100)
        self.assertTrue(self.janela._botao_salvar.get_sensitive())


class TestVigia(CasoGrafico):
    def setUp(self):
        super().setUp()
        self.alvo = self.arquivo("texto.tex", "linha um\nlinha dois\n")
        self.janela.abrir(self.alvo)
        bombear(300)

    def test_buffer_limpo_recarrega_sozinho(self):
        self.alvo.write_text("MUDOU FORA\nlinha dois\n", encoding="utf-8")
        self.assertTrue(ate(lambda: self.texto.startswith("MUDOU FORA"), 4000))
        self.assertFalse(self._banner_visivel())

    def test_buffer_sujo_preserva_e_avisa(self):
        self.digitar("EDICAO LOCAL ")
        bombear(100)
        self.alvo.write_text("MUDOU FORA\n", encoding="utf-8")
        self.assertTrue(ate(self._banner_visivel, 4000))
        self.assertIn("EDICAO LOCAL", self.texto)

    def test_recarregar_descarta_e_traz_o_disco(self):
        self.digitar("EDICAO LOCAL ")
        bombear(100)
        self.alvo.write_text("DO DISCO\n", encoding="utf-8")
        self.assertTrue(ate(self._banner_visivel, 4000))
        self.janela._recarregar()
        self.assertTrue(self.texto.startswith("DO DISCO"))
        self.assertFalse(self.janela._sujo)

    def test_gravar_pelo_editor_nao_acende_aviso(self):
        # A própria gravação dispara o vigia; o conteúdo é comparado antes de
        # alarmar, o que é mais robusto que um sinalizador de "ignore o
        # próximo evento" -- o monitor emite mais de um.
        self.digitar("meu texto ")
        self.janela._gravar()
        bombear(1200)
        self.assertFalse(self._banner_visivel())

    def _banner_visivel(self):
        return self.janela._aviso.get_revealed()


if __name__ == "__main__":
    unittest.main()
