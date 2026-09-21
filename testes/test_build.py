"""Leitura do .log do LaTeX."""

import tempfile
import unittest
from pathlib import Path

from serifa.build import Compilador, Diagnostico, ler_log


class TestLerLog(unittest.TestCase):
    def log(self, conteudo):
        arquivo = Path(self._tmp.name) / "previa.log"
        arquivo.write_text(conteudo, encoding="utf-8")
        return ler_log(arquivo)

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="serifa-log-")

    def tearDown(self):
        self._tmp.cleanup()

    def test_arquivo_ausente_nao_estoura(self):
        self.assertEqual(ler_log(Path(self._tmp.name) / "nao-existe.log"), [])

    def test_erro_simples_com_linha(self):
        d = self.log("(./texto.tex\n! Undefined control sequence.\nl.23 \\foo\n")
        self.assertEqual([(x.severidade, x.mensagem, x.linha) for x in d],
                         [("erro", "Undefined control sequence.", 23)])

    def test_desdobra_linha_quebrada_em_79_colunas(self):
        # O TeX quebra mensagens longas em 79 colunas; sem juntar de volta, a
        # mensagem chega picada ao painel.
        inteira = ("! Package babel Error: Unknown option `portuges'. "
                   "Either you misspelled it and the correct spelling is portuguese.")
        pedacos = [inteira[i:i + 79] for i in range(0, len(inteira), 79)]
        self.assertEqual(len(pedacos[0]), 79, "o teste precisa quebrar onde o TeX quebra")
        d = self.log("\n".join(pedacos) + "\nl.7 \\usepackage\n")
        self.assertEqual(len(d), 1)
        self.assertIn("misspelled it", d[0].mensagem)

    def test_aviso_com_linha(self):
        d = self.log("LaTeX Warning: Reference `x' on input line 12 undefined.\n")
        self.assertEqual([(x.severidade, x.linha) for x in d], [("aviso", 12)])

    def test_rerun_e_ruido_e_some(self):
        # O latexmk resolve sozinho; mostrar isso só polui o painel.
        self.assertEqual(
            self.log("LaTeX Warning: Label(s) may have changed. Rerun.\n"), [])

    def test_resumo_traz_arquivo_e_linha(self):
        d = Diagnostico("erro", "algo", "sub/texto.tex", 9)
        self.assertEqual(d.resumo, "texto.tex:9 — algo")

    def test_resumo_sem_arquivo(self):
        self.assertEqual(Diagnostico("aviso", "algo").resumo, "algo")


class TestCaminhos(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="serifa-cam-")
        self.pasta = Path(self._tmp.name) / "questionario-02"
        self.pasta.mkdir()
        self.tex = self.pasta / "texto.tex"
        self.tex.write_text("", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_pdf_pelo_nome_do_tex_quando_nao_ha_o_da_pasta(self):
        self.assertEqual(Compilador._pdf_de(self.tex, self.pasta).name, "texto.pdf")

    def test_pdf_pelo_nome_da_pasta_quando_existe(self):
        # É como o scripts/compilar.sh do projeto nomeia, para o anexo já sair
        # identificado.
        (self.pasta / "questionario-02.pdf").write_bytes(b"%PDF")
        self.assertEqual(Compilador._pdf_de(self.tex, self.pasta).name,
                         "questionario-02.pdf")

    def test_sombra_e_estavel_e_fora_do_projeto(self):
        a = Compilador.pasta_da_sombra(self.pasta)
        b = Compilador.pasta_da_sombra(self.pasta)
        self.assertEqual(a, b)
        self.assertNotIn(str(self.pasta), str(a))

    def test_sombras_de_pastas_diferentes_nao_colidem(self):
        outra = Path(self._tmp.name) / "questionario-03"
        self.assertNotEqual(Compilador.pasta_da_sombra(self.pasta),
                            Compilador.pasta_da_sombra(outra))

    def test_script_do_projeto_encontrado_subindo(self):
        scripts = Path(self._tmp.name) / "scripts"
        scripts.mkdir()
        script = scripts / "compilar.sh"
        script.write_text("#!/bin/sh\n", encoding="utf-8")
        script.chmod(0o755)
        self.assertEqual(Compilador._script_do_projeto(self.pasta), script)

    def test_script_nao_executavel_e_ignorado(self):
        scripts = Path(self._tmp.name) / "scripts"
        scripts.mkdir(exist_ok=True)
        (scripts / "compilar.sh").write_text("", encoding="utf-8")
        (scripts / "compilar.sh").chmod(0o644)
        self.assertIsNone(Compilador._script_do_projeto(self.pasta))


if __name__ == "__main__":
    unittest.main()
