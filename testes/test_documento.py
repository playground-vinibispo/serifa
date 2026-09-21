"""O arquivo aberto, sem janela nenhuma.

O documento só precisa de um buffer. Estes testes rodam em milissegundos, ao
contrário dos que montam interface -- e é justamente aqui que moram os
defeitos que custam texto do usuário.
"""

import tempfile
import unittest
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from serifa.documento import Documento
from testes.apoio import ate, bombear, iniciar


class TestDocumento(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not iniciar():
            raise unittest.SkipTest("sem servidor gráfico")

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="serifa-doc-")
        self.pasta = Path(self._tmp.name)
        self.buffer = Gtk.TextBuffer()
        self.doc = Documento(self.buffer)
        self.avisos = []
        for sinal in ("sujeira-mudou", "recarregado", "conflito", "falhou"):
            self.doc.connect(sinal, lambda *a, s=sinal: self.avisos.append(s))

    def tearDown(self):
        self._tmp.cleanup()

    def arquivo(self, nome="texto.tex", conteudo="original\n"):
        caminho = self.pasta / nome
        caminho.write_text(conteudo, encoding="utf-8")
        return caminho

    # ------------------------------------------------------------- abrir

    def test_abrir_carrega_e_limpa(self):
        self.doc.abrir(self.arquivo())
        self.assertEqual(self.doc.texto, "original\n")
        self.assertFalse(self.doc.sujo)

    def test_abrir_poe_o_cursor_no_comeco(self):
        self.doc.abrir(self.arquivo(conteudo="a\nb\nc\n"))
        self.assertEqual(self.buffer.get_property("cursor-position"), 0)

    def test_abrir_inexistente_avisa_e_nao_estoura(self):
        self.assertFalse(self.doc.abrir(self.pasta / "nao-existe.tex"))
        self.assertIn("falhou", self.avisos)

    # ------------------------------------------------------------ gravar

    def test_gravar_escreve_e_limpa(self):
        alvo = self.arquivo()
        self.doc.abrir(alvo)
        self.buffer.set_text("novo conteudo\n")
        self.doc.sujar()
        self.assertTrue(self.doc.gravar())
        self.assertEqual(alvo.read_text(encoding="utf-8"), "novo conteudo\n")
        self.assertFalse(self.doc.sujo)

    def test_gravar_sem_caminho_falha(self):
        self.assertFalse(self.doc.gravar())

    def test_sujar_e_idempotente(self):
        self.doc.abrir(self.arquivo())
        self.avisos.clear()
        self.doc.sujar()
        self.doc.sujar()
        self.assertEqual(self.avisos.count("sujeira-mudou"), 1)

    # ------------------------------------------------------------- disco

    def test_mudanca_externa_com_buffer_limpo_recarrega(self):
        alvo = self.arquivo()
        self.doc.abrir(alvo)
        alvo.write_text("de fora\n", encoding="utf-8")
        self.assertTrue(ate(lambda: self.doc.texto == "de fora\n", 4000))
        self.assertIn("recarregado", self.avisos)

    def test_mudanca_externa_com_buffer_sujo_avisa_e_preserva(self):
        alvo = self.arquivo()
        self.doc.abrir(alvo)
        self.buffer.set_text("meu trabalho\n")
        self.doc.sujar()
        alvo.write_text("de fora\n", encoding="utf-8")
        self.assertTrue(ate(lambda: "conflito" in self.avisos, 4000))
        self.assertEqual(self.doc.texto, "meu trabalho\n")

    def test_gravar_nao_dispara_conflito(self):
        # A própria gravação move o arquivo; comparar o conteúdo evita o
        # falso alarme, e é mais robusto que ignorar o próximo evento --
        # o monitor emite mais de um por gravação.
        alvo = self.arquivo()
        self.doc.abrir(alvo)
        self.buffer.set_text("meu texto\n")
        self.doc.sujar()
        self.doc.gravar()
        bombear(1200)
        self.assertNotIn("conflito", self.avisos)

    def test_recarregar_preserva_a_posicao_do_cursor(self):
        alvo = self.arquivo(conteudo="linha um\nlinha dois\nlinha tres\n")
        self.doc.abrir(alvo)
        self.buffer.place_cursor(self.buffer.get_iter_at_offset(12))
        alvo.write_text("linha um\nlinha DOIS\nlinha tres\n", encoding="utf-8")
        self.assertTrue(ate(lambda: "DOIS" in self.doc.texto, 4000))
        self.assertEqual(self.buffer.get_property("cursor-position"), 12)

    def test_recarregar_com_texto_menor_nao_estoura(self):
        alvo = self.arquivo(conteudo="um texto bem longo aqui\n")
        self.doc.abrir(alvo)
        self.buffer.place_cursor(self.buffer.get_end_iter())
        alvo.write_text("x\n", encoding="utf-8")
        self.assertTrue(ate(lambda: self.doc.texto == "x\n", 4000))
        self.assertLessEqual(self.buffer.get_property("cursor-position"),
                             self.buffer.get_char_count())

    def test_definir_caminho_passa_a_vigiar_o_novo(self):
        novo = self.pasta / "outro.tex"
        novo.write_text("inicial\n", encoding="utf-8")
        self.doc.definir_caminho(novo)
        self.assertEqual(self.doc.caminho, novo)
        self.assertEqual(self.doc.nome, "outro.tex")


if __name__ == "__main__":
    unittest.main()
