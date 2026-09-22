"""Generating the snippets file.

It exists because of a trap: GtkSourceView's parser contradicts its own
snippets.rng on three attributes, and getting any of them wrong yields zero
snippets with a WARNING on the console and nothing else. Without this test,
the breakage is silent.
"""

import unittest
import xml.etree.ElementTree as ET

from serifa.complete import COMMANDS, ENVIRONMENTS, GREEK_LETTERS, prepare_snippets


class TestSnippets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = prepare_snippets()
        cls.file = cls.folder / "latex.snippets"
        cls.root = ET.parse(cls.file).getroot()

    def test_file_generated(self):
        self.assertTrue(self.file.exists())

    def test_count_matches_the_lists(self):
        expected = len(COMMANDS) + len(GREEK_LETTERS) + 2 * len(ENVIRONMENTS)
        self.assertEqual(len(self.root.findall("snippet")), expected)

    def test_no_version_attribute(self):
        # The RNG declares version required; the real parser rejects the file
        # if it is present.
        self.assertNotIn("version", self.root.attrib)

    def test_uses_the_underscore_forms(self):
        # The RNG accepts group/name/description; the real parser only accepts
        # the underscore forms.
        self.assertIn("_group", self.root.attrib)
        first = self.root.find("snippet")
        self.assertIn("_name", first.attrib)
        self.assertIn("_description", first.attrib)

    def test_text_declares_languages(self):
        # The RNG says optional; the parser demands it.
        for snippet in self.root.findall("snippet"):
            self.assertIn("languages", snippet.find("text").attrib)

    def test_trigger_never_has_an_asterisk(self):
        # equation* is no good as a trigger; it becomes equationx.
        for snippet in self.root.findall("snippet"):
            self.assertNotIn("*", snippet.get("trigger"))

    def test_starred_environment_comes_out_right_in_the_body(self):
        bodies = [s.find("text").text for s in self.root.findall("snippet")
                  if s.get("trigger") == "equationx"]
        self.assertTrue(bodies and "\\begin{equation*}" in bodies[0])

    def test_gtksourceview_really_loads_it(self):
        from tests.support import start
        if not start():
            self.skipTest("sem servidor gráfico")
        import gi
        gi.require_version("GtkSource", "5")
        from gi.repository import GtkSource

        manager = GtkSource.SnippetManager()
        manager.set_search_path([str(self.folder)])
        model = manager.list_matching(None, "latex", None)
        self.assertIsNotNone(model, "o parser rejeitou o arquivo inteiro")
        self.assertGreater(model.get_n_items(), 100)


if __name__ == "__main__":
    unittest.main()
