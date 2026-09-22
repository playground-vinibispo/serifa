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

from serifa.document import Document
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
        self.doc = Document(self.buffer)
        self.avisos = []
        for sinal in ("dirty-changed", "reloaded", "conflict", "failed"):
            self.doc.connect(sinal, lambda *a, s=sinal: self.avisos.append(s))

    def tearDown(self):
        self._tmp.cleanup()

    def arquivo(self, nome="texto.tex", conteudo="original\n"):
        caminho = self.pasta / nome
        caminho.write_text(conteudo, encoding="utf-8")
        return caminho

    # ------------------------------------------------------------- abrir

    def test_abrir_carrega_e_limpa(self):
        self.doc.open_file(self.arquivo())
        self.assertEqual(self.doc.text, "original\n")
        self.assertFalse(self.doc.dirty)

    def test_abrir_poe_o_cursor_no_comeco(self):
        self.doc.open_file(self.arquivo(conteudo="a\nb\nc\n"))
        self.assertEqual(self.buffer.get_property("cursor-position"), 0)

    def test_abrir_inexistente_avisa_e_nao_estoura(self):
        self.assertFalse(self.doc.open_file(self.pasta / "nao-existe.tex"))
        self.assertIn("failed", self.avisos)

    # ------------------------------------------------------------ gravar

    def test_gravar_escreve_e_limpa(self):
        alvo = self.arquivo()
        self.doc.open_file(alvo)
        self.buffer.set_text("novo conteudo\n")
        self.doc.mark_dirty()
        self.assertTrue(self.doc.save())
        self.assertEqual(alvo.read_text(encoding="utf-8"), "novo conteudo\n")
        self.assertFalse(self.doc.dirty)

    def test_gravar_sem_caminho_falha(self):
        self.assertFalse(self.doc.save())

    def test_sujar_e_idempotente(self):
        self.doc.open_file(self.arquivo())
        self.avisos.clear()
        self.doc.mark_dirty()
        self.doc.mark_dirty()
        self.assertEqual(self.avisos.count("dirty-changed"), 1)

    # ------------------------------------------------------------- disco

    def test_mudanca_externa_com_buffer_limpo_recarrega(self):
        alvo = self.arquivo()
        self.doc.open_file(alvo)
        alvo.write_text("de fora\n", encoding="utf-8")
        self.assertTrue(ate(lambda: self.doc.text == "de fora\n", 4000))
        self.assertIn("reloaded", self.avisos)

    def test_mudanca_externa_com_buffer_sujo_avisa_e_preserva(self):
        alvo = self.arquivo()
        self.doc.open_file(alvo)
        self.buffer.set_text("meu trabalho\n")
        self.doc.mark_dirty()
        alvo.write_text("de fora\n", encoding="utf-8")
        self.assertTrue(ate(lambda: "conflict" in self.avisos, 4000))
        self.assertEqual(self.doc.text, "meu trabalho\n")

    def test_gravar_nao_dispara_conflito(self):
        # A própria gravação move o arquivo; comparar o conteúdo evita o
        # falso alarme, e é mais robusto que ignorar o próximo evento --
        # o monitor emite mais de um por gravação.
        alvo = self.arquivo()
        self.doc.open_file(alvo)
        self.buffer.set_text("meu texto\n")
        self.doc.mark_dirty()
        self.doc.save()
        bombear(1200)
        self.assertNotIn("conflict", self.avisos)

    def test_recarregar_preserva_a_posicao_do_cursor(self):
        alvo = self.arquivo(conteudo="linha um\nlinha dois\nlinha tres\n")
        self.doc.open_file(alvo)
        self.buffer.place_cursor(self.buffer.get_iter_at_offset(12))
        alvo.write_text("linha um\nlinha DOIS\nlinha tres\n", encoding="utf-8")
        self.assertTrue(ate(lambda: "DOIS" in self.doc.text, 4000))
        self.assertEqual(self.buffer.get_property("cursor-position"), 12)

    def test_recarregar_com_texto_menor_nao_estoura(self):
        alvo = self.arquivo(conteudo="um texto bem longo aqui\n")
        self.doc.open_file(alvo)
        self.buffer.place_cursor(self.buffer.get_end_iter())
        alvo.write_text("x\n", encoding="utf-8")
        self.assertTrue(ate(lambda: self.doc.text == "x\n", 4000))
        self.assertLessEqual(self.buffer.get_property("cursor-position"),
                             self.buffer.get_char_count())

    def test_definir_caminho_passa_a_vigiar_o_novo(self):
        novo = self.pasta / "outro.tex"
        novo.write_text("inicial\n", encoding="utf-8")
        self.doc.set_path(novo)
        self.assertEqual(self.doc.path, novo)
        self.assertEqual(self.doc.name, "outro.tex")


if __name__ == "__main__":
    unittest.main()
