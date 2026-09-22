"""Geração do arquivo de snippets.

Existe por causa de uma armadilha: o parser do GtkSourceView contraria o
próprio snippets.rng em três atributos, e errar qualquer um deles produz zero
snippets com um WARNING no console e mais nada. Sem este teste, a quebra é
silenciosa.
"""

import unittest
import xml.etree.ElementTree as ET

from serifa.complete import COMMANDS, ENVIRONMENTS, GREEK_LETTERS, prepare_snippets


class TestSnippets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pasta = prepare_snippets()
        cls.arquivo = cls.pasta / "latex.snippets"
        cls.raiz = ET.parse(cls.arquivo).getroot()

    def test_arquivo_gerado(self):
        self.assertTrue(self.arquivo.exists())

    def test_quantidade_bate_com_as_listas(self):
        esperado = len(COMMANDS) + len(GREEK_LETTERS) + 2 * len(ENVIRONMENTS)
        self.assertEqual(len(self.raiz.findall("snippet")), esperado)

    def test_sem_atributo_version(self):
        # O RNG declara version obrigatório; o parser real rejeita o arquivo
        # se ele estiver presente.
        self.assertNotIn("version", self.raiz.attrib)

    def test_usa_as_formas_com_underscore(self):
        # O RNG aceita group/name/description; o parser real só aceita as
        # formas com underscore.
        self.assertIn("_group", self.raiz.attrib)
        primeiro = self.raiz.find("snippet")
        self.assertIn("_name", primeiro.attrib)
        self.assertIn("_description", primeiro.attrib)

    def test_texto_declara_languages(self):
        # O RNG diz opcional; o parser exige.
        for snippet in self.raiz.findall("snippet"):
            self.assertIn("languages", snippet.find("text").attrib)

    def test_gatilho_nunca_tem_asterisco(self):
        # equation* não serve de gatilho; vira equationx.
        for snippet in self.raiz.findall("snippet"):
            self.assertNotIn("*", snippet.get("trigger"))

    def test_ambiente_com_asterisco_sai_certo_no_corpo(self):
        corpos = [s.find("text").text for s in self.raiz.findall("snippet")
                  if s.get("trigger") == "equationx"]
        self.assertTrue(corpos and "\\begin{equation*}" in corpos[0])

    def test_gtksourceview_carrega_de_verdade(self):
        from testes.apoio import iniciar
        if not iniciar():
            self.skipTest("sem servidor gráfico")
        import gi
        gi.require_version("GtkSource", "5")
        from gi.repository import GtkSource

        gerente = GtkSource.SnippetManager()
        gerente.set_search_path([str(self.pasta)])
        modelo = gerente.list_matching(None, "latex", None)
        self.assertIsNotNone(modelo, "o parser rejeitou o arquivo inteiro")
        self.assertGreater(modelo.get_n_items(), 100)


if __name__ == "__main__":
    unittest.main()
