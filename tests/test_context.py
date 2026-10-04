# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Vinícius Bispo e colaboradores

"""Context detection and the completion library."""

import tempfile
import unittest
from pathlib import Path

from serifa.context import Context, Library, _is_subsequence, detect


class TestDetect(unittest.TestCase):
    def check(self, left, kind, prefix):
        context = detect(left, len(left))
        self.assertEqual((context.kind, context.prefix), (kind, prefix),
                         repr(left))

    def test_empty_citation(self):
        self.check(r"veja \cite{", "citation", "")

    def test_citation_with_prefix(self):
        self.check(r"veja \cite{eins", "citation", "eins")

    def test_citation_with_optional_argument(self):
        self.check(r"\citep[p.~64]{ei", "citation", "ei")

    def test_multiple_citation(self):
        # Only the part after the last comma counts as the prefix.
        self.check(r"\cite{pires, eins", "citation", "eins")

    def test_reference(self):
        self.check(r"na \ref{sec:", "reference", "sec:")

    def test_eqref(self):
        self.check(r"\eqref{eq1", "reference", "eq1")

    def test_environment_begin(self):
        self.check(r"\begin{item", "environment", "item")

    def test_environment_end(self):
        self.check(r"\end{", "environment", "")

    def test_graphic(self):
        self.check(r"\includegraphics[width=2cm]{fig", "graphic", "fig")

    def test_input(self):
        self.check(r"\input{../../pre", "input", "../../pre")

    def test_bibliography_is_input(self):
        self.check(r"\bibliography{../../ref", "input", "../../ref")

    def test_prose_is_no_context(self):
        self.check(r"texto normal ", "", "")

    def test_section_is_no_context(self):
        # \section{ has braces but is no place to complete anything.
        self.check(r"\section{Um titulo", "", "")


class TestSubsequence(unittest.TestCase):
    def test_matches(self):
        self.assertTrue(_is_subsequence("eif", "einstein_infeld"))

    def test_does_not_match(self):
        self.assertFalse(_is_subsequence("xyz", "einstein_infeld"))

    def test_order_matters(self):
        self.assertFalse(_is_subsequence("fie", "einstein_infeld"))


class TestLibrary(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="serifa-acervo-")
        self.root = Path(self._tmp.name)
        (self.root / "trabalho").mkdir()
        (self.root / "referencias.bib").write_text(
            '@book{einstein_infeld,\n  title = {A Evolução da Física},\n'
            '  author = {Einstein, A.},\n}\n'
            '@book{pires,\n  title = {Evolução das Ideias},\n}\n',
            encoding="utf-8")
        (self.root / "preambulo.tex").write_text("% preambulo\n", encoding="utf-8")
        (self.root / "trabalho" / "texto.tex").write_text("% texto\n", encoding="utf-8")
        (self.root / "trabalho" / "figura.png").write_bytes(b"\x89PNG")
        self.library = Library()
        self.library.set_folder(self.root / "trabalho")

    def tearDown(self):
        self._tmp.cleanup()

    def test_reads_bib_from_a_folder_above(self):
        keys = [i.text for i in self.library.items(Context("citation", "", 0), "")]
        self.assertEqual(sorted(keys), ["einstein_infeld", "pires"])

    def test_brings_the_title_alongside(self):
        items = self.library.items(Context("citation", "", 0), "")
        detail = next(i.detail for i in items if i.text == "einstein_infeld")
        self.assertIn("Evolução da Física", detail)

    def test_filters_by_subsequence(self):
        items = self.library.items(Context("citation", "eif", 0), "")
        self.assertEqual([i.text for i in items], ["einstein_infeld"])

    def test_labels_come_from_the_document(self):
        items = self.library.items(
            Context("reference", "", 0), r"\label{sec:um} x \label{fig:dois}")
        self.assertEqual([i.text for i in items], ["fig:dois", "sec:um"])

    def test_input_brings_tex_and_bib_but_no_image(self):
        names = [i.text for i in self.library.items(Context("input", "", 0), "")]
        self.assertIn("texto", names)
        self.assertIn("../preambulo", names)
        self.assertNotIn("figura.png", names)

    def test_graphic_brings_image_but_no_tex(self):
        names = [i.text for i in self.library.items(Context("graphic", "", 0), "")]
        self.assertIn("figura.png", names)
        self.assertNotIn("texto", names)

    def test_input_drops_the_tex_extension(self):
        names = [i.text for i in self.library.items(Context("input", "", 0), "")]
        self.assertNotIn("texto.tex", names)


if __name__ == "__main__":
    unittest.main()
