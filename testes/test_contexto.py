"""Detecção de contexto e acervo da completação."""

import tempfile
import unittest
from pathlib import Path

from serifa.contexto import Acervo, Contexto, detectar, _subsequencia


class TestDetectar(unittest.TestCase):
    def conferir(self, esquerda, tipo, prefixo):
        contexto = detectar(esquerda, len(esquerda))
        self.assertEqual((contexto.tipo, contexto.prefixo), (tipo, prefixo), repr(esquerda))

    def test_citacao_vazia(self):        self.conferir(r"veja \cite{", "citacao", "")
    def test_citacao_com_prefixo(self):  self.conferir(r"veja \cite{eins", "citacao", "eins")
    def test_citacao_com_opcional(self): self.conferir(r"\citep[p.~64]{ei", "citacao", "ei")
    def test_citacao_multipla(self):
        # Só o trecho depois da última vírgula conta como prefixo.
        self.conferir(r"\cite{pires, eins", "citacao", "eins")
    def test_referencia(self):     self.conferir(r"na \ref{sec:", "referencia", "sec:")
    def test_eqref(self):          self.conferir(r"\eqref{eq1", "referencia", "eq1")
    def test_ambiente_begin(self): self.conferir(r"\begin{item", "ambiente", "item")
    def test_ambiente_end(self):   self.conferir(r"\end{", "ambiente", "")
    def test_grafico(self):        self.conferir(r"\includegraphics[width=2cm]{fig", "grafico", "fig")
    def test_entrada(self):        self.conferir(r"\input{../../pre", "entrada", "../../pre")
    def test_bibliography_e_entrada(self): self.conferir(r"\bibliography{../../ref", "entrada", "../../ref")
    def test_prosa_nao_e_contexto(self):   self.conferir(r"texto normal ", "", "")
    def test_section_nao_e_contexto(self):
        # \section{ tem chaves mas não é lugar de completar nada.
        self.conferir(r"\section{Um titulo", "", "")


class TestSubsequencia(unittest.TestCase):
    def test_casa(self):
        self.assertTrue(_subsequencia("eif", "einstein_infeld"))

    def test_nao_casa(self):
        self.assertFalse(_subsequencia("xyz", "einstein_infeld"))

    def test_ordem_importa(self):
        self.assertFalse(_subsequencia("fie", "einstein_infeld"))


class TestAcervo(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="serifa-acervo-")
        self.raiz = Path(self._tmp.name)
        (self.raiz / "trabalho").mkdir()
        (self.raiz / "referencias.bib").write_text(
            '@book{einstein_infeld,\n  title = {A Evolução da Física},\n'
            '  author = {Einstein, A.},\n}\n'
            '@book{pires,\n  title = {Evolução das Ideias},\n}\n',
            encoding="utf-8")
        (self.raiz / "preambulo.tex").write_text("% preambulo\n", encoding="utf-8")
        (self.raiz / "trabalho" / "texto.tex").write_text("% texto\n", encoding="utf-8")
        (self.raiz / "trabalho" / "figura.png").write_bytes(b"\x89PNG")
        self.acervo = Acervo()
        self.acervo.definir_pasta(self.raiz / "trabalho")

    def tearDown(self):
        self._tmp.cleanup()

    def test_le_bib_de_pasta_acima(self):
        chaves = [i.texto for i in self.acervo.itens(Contexto("citacao", "", 0), "")]
        self.assertEqual(sorted(chaves), ["einstein_infeld", "pires"])

    def test_traz_o_titulo_ao_lado(self):
        itens = self.acervo.itens(Contexto("citacao", "", 0), "")
        detalhe = next(i.detalhe for i in itens if i.texto == "einstein_infeld")
        self.assertIn("Evolução da Física", detalhe)

    def test_filtra_por_subsequencia(self):
        itens = self.acervo.itens(Contexto("citacao", "eif", 0), "")
        self.assertEqual([i.texto for i in itens], ["einstein_infeld"])

    def test_rotulos_vem_do_documento(self):
        itens = self.acervo.itens(
            Contexto("referencia", "", 0), r"\label{sec:um} x \label{fig:dois}")
        self.assertEqual([i.texto for i in itens], ["fig:dois", "sec:um"])

    def test_entrada_traz_tex_e_bib_sem_imagem(self):
        nomes = [i.texto for i in self.acervo.itens(Contexto("entrada", "", 0), "")]
        self.assertIn("texto", nomes)
        self.assertIn("../preambulo", nomes)
        self.assertNotIn("figura.png", nomes)

    def test_grafico_traz_imagem_sem_tex(self):
        nomes = [i.texto for i in self.acervo.itens(Contexto("grafico", "", 0), "")]
        self.assertIn("figura.png", nomes)
        self.assertNotIn("texto", nomes)

    def test_input_dispensa_a_extensao_tex(self):
        nomes = [i.texto for i in self.acervo.itens(Contexto("entrada", "", 0), "")]
        self.assertNotIn("texto.tex", nomes)


if __name__ == "__main__":
    unittest.main()
