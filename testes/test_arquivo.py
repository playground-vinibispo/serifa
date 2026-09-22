"""Gravação, prévia e vigia de disco.

O invariante mais importante do editor está aqui: **digitar não escreve no
arquivo do usuário.** Até pouco tempo escrevia, como efeito colateral da
compilação contínua.
"""

import shutil
import unittest

from serifa.build import Builder
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
        self.janela.open_file(self.alvo)
        bombear(200)

    def test_abrir_carrega_o_texto(self):
        self.assertIn("Uma frase qualquer", self.texto)

    def test_digitar_nao_grava(self):
        self.digitar("mexido ")
        bombear(200)
        self.assertEqual(self.alvo.read_text(encoding="utf-8"), self.original)
        self.assertTrue(self.janela._dirty)

    def test_previa_nao_grava(self):
        self.digitar("mexido ")
        self.janela.preview_build()
        bombear(400)
        self.assertEqual(self.alvo.read_text(encoding="utf-8"), self.original)

    @unittest.skipUnless(shutil.which("latexmk"), "latexmk não instalado")
    def test_previa_compila_na_sombra_fora_do_projeto(self):
        sombra = Builder.shadow_folder(self.alvo.parent)
        self.assertNotIn(str(self.caixa), str(sombra))
        self.janela.preview_build()
        self.assertTrue(ate(lambda: (sombra / "previa.tex").exists(), 4000))
        # nenhum resíduo de compilação na pasta do usuário
        self.assertEqual(sorted(p.name for p in self.caixa.iterdir()),
                         ["estado.json", "texto.tex"])

    def test_salvar_grava_e_limpa_o_sujo(self):
        self.digitar("mexido ")
        self.janela._write()
        self.assertIn("mexido", self.alvo.read_text(encoding="utf-8"))
        self.assertFalse(self.janela._dirty)

    def test_fechar_sujo_e_bloqueado(self):
        self.digitar("mexido ")
        self.assertTrue(self.janela._on_close_request())

    def test_fechar_limpo_passa_direto(self):
        self.assertFalse(self.janela._on_close_request())

    def test_botao_salvar_reflete_o_estado(self):
        self.assertFalse(self.janela._save_button.get_sensitive())
        self.digitar("x")
        bombear(100)
        self.assertTrue(self.janela._save_button.get_sensitive())


class TestVigia(CasoGrafico):
    def setUp(self):
        super().setUp()
        self.alvo = self.arquivo("texto.tex", "linha um\nlinha dois\n")
        self.janela.open_file(self.alvo)
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
        self.janela._reload()
        self.assertTrue(self.texto.startswith("DO DISCO"))
        self.assertFalse(self.janela._dirty)

    def test_gravar_pelo_editor_nao_acende_aviso(self):
        # A própria gravação dispara o vigia; o conteúdo é comparado antes de
        # alarmar, o que é mais robusto que um sinalizador de "ignore o
        # próximo evento" -- o monitor emite mais de um.
        self.digitar("meu texto ")
        self.janela._write()
        bombear(1200)
        self.assertFalse(self._banner_visivel())

    def _banner_visivel(self):
        return self.janela._banner.get_revealed()


if __name__ == "__main__":
    unittest.main()


class TestGuardaAoTrocarDeArquivo(CasoGrafico):
    """Trocar de arquivo com alteração pendente não pode engolir o texto.

    Fechar a janela já perguntava; abrir outro arquivo não, e substituía o
    buffer em silêncio. Era perda de dados, não incômodo.
    """

    def setUp(self):
        super().setUp()
        self.um = self.arquivo("um.tex", "conteudo do um\n")
        self.dois = self.arquivo("dois.tex", "conteudo do dois\n")
        self.janela.open_file(self.um)
        bombear(200)

    def test_limpo_troca_direto(self):
        self.assertFalse(self.janela._settle_pending(lambda: None))

    def test_sujo_adia_a_troca(self):
        self.digitar("mexido ")
        seguiu = []
        self.assertTrue(self.janela._settle_pending(lambda: seguiu.append(1)))
        self.assertEqual(seguiu, [], "trocou antes de perguntar")

    def test_cancelar_nao_segue_e_preserva(self):
        self.digitar("mexido ")
        seguiu = []
        self.janela._apply_response("cancel", lambda: seguiu.append(1))
        self.assertEqual(seguiu, [])
        self.assertIn("mexido", self.texto)
        self.assertTrue(self.janela._dirty)

    def test_descartar_segue_sem_gravar(self):
        self.digitar("mexido ")
        seguiu = []
        self.janela._apply_response("discard", lambda: seguiu.append(1))
        self.assertEqual(seguiu, [1])
        self.assertNotIn("mexido", self.um.read_text(encoding="utf-8"))
        self.assertFalse(self.janela._dirty)

    def test_salvar_grava_e_segue(self):
        self.digitar("mexido ")
        seguiu = []
        self.janela._apply_response("save", lambda: seguiu.append(1))
        self.assertEqual(seguiu, [1])
        self.assertIn("mexido", self.um.read_text(encoding="utf-8"))
        self.assertFalse(self.janela._dirty)

    def test_abrir_outro_depois_de_descartar(self):
        self.digitar("mexido ")
        self.janela._apply_response("discard", lambda: self.janela.open_file(self.dois))
        bombear(150)
        self.assertIn("conteudo do dois", self.texto)
        self.assertEqual(self.janela._file, self.dois)

    def test_fechar_usa_a_mesma_guarda(self):
        self.digitar("mexido ")
        self.assertTrue(self.janela._on_close_request())
