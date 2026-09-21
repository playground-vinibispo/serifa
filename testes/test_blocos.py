"""Delimitação de blocos -- a parte pura do `vi{`.

Função pura, testável sem janela, e não por acaso foi o único pedaço do modo
visual que funcionou de primeira.
"""

import unittest

from serifa.blocos import alvo, limites_do_bloco, limites_das_aspas


class TestAlvo(unittest.TestCase):
    def conferir(self, texto, marca, sinal, por_dentro, esperado):
        posicao = texto.index(marca) if isinstance(marca, str) else marca
        faixa = alvo(texto, posicao, sinal, por_dentro)
        obtido = texto[faixa[0]:faixa[1]] if faixa else None
        self.assertEqual(obtido, esperado, f"{'i' if por_dentro else 'a'}{sinal} em {texto!r}")

    def test_chaves_por_dentro(self):
        self.conferir(r"\textbf{palavra aqui} depois", "palavra", "{", True, "palavra aqui")

    def test_chaves_em_volta(self):
        self.conferir(r"\textbf{palavra aqui} depois", "palavra", "{", False, "{palavra aqui}")

    def test_aninhamento_pega_o_interno(self):
        self.conferir(r"{a {b} c}", "b", "{", True, "b")

    def test_aninhamento_pega_o_externo(self):
        self.conferir(r"{a {b} c}", "a", "{", True, "a {b} c")

    def test_cursor_sobre_a_abertura(self):
        self.conferir(r"{a {b} c}", 0, "{", True, "a {b} c")

    def test_chave_escapada_do_latex_e_ignorada(self):
        # \{ é chave literal; casar com ela daria o bloco errado em qualquer
        # \newcommand -- foi o caso que motivou a checagem de escape.
        self.conferir(r"\newcommand{\x}[2]{\{literal\} real}", "real", "{", True,
                      r"\{literal\} real")

    def test_so_escapadas_nao_formam_bloco(self):
        self.conferir(r"\{so escapadas\}", "so", "{", True, None)

    def test_parenteses(self):
        self.conferir(r"f(x, g(y)) fim", "y", "(", True, "y")

    def test_b_minusculo_e_parentese(self):
        self.conferir(r"f(x, g(y)) fim", "x", "b", True, "x, g(y)")

    def test_colchetes(self):
        self.conferir(r"arr[i+1] fim", "i+1", "[", True, "i+1")

    def test_aspas_por_dentro(self):
        self.conferir(r'diz "uma coisa" e para', "uma", '"', True, "uma coisa")

    def test_aspas_em_volta(self):
        self.conferir(r'diz "uma coisa" e para', "uma", '"', False, '"uma coisa"')

    def test_sem_bloco_devolve_nada(self):
        self.conferir(r"sem nada aqui", "nada", "{", True, None)

    def test_sinal_desconhecido(self):
        self.assertIsNone(alvo("texto qualquer", 3, "@", True))

    def test_texto_vazio(self):
        self.assertIsNone(limites_do_bloco("", 0, "{", "}"))

    def test_aspas_nao_atravessam_linha(self):
        # Aspas não aninham: a paridade é contada por linha, senão uma aspa
        # solta numa linha casaria com outra três parágrafos abaixo.
        self.assertIsNone(limites_das_aspas('diz "aberta\noutra linha"', 5, '"'))


if __name__ == "__main__":
    unittest.main()
