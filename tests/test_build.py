# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Vinícius Bispo e colaboradores

"""Reading the LaTeX .log."""

import tempfile
import unittest
from pathlib import Path

from serifa.build import Builder, Diagnostic, read_log


class TestReadLog(unittest.TestCase):
    def log(self, content):
        file = Path(self._tmp.name) / "previa.log"
        file.write_text(content, encoding="utf-8")
        return read_log(file)

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="serifa-log-")

    def tearDown(self):
        self._tmp.cleanup()

    def test_missing_file_does_not_blow_up(self):
        self.assertEqual(read_log(Path(self._tmp.name) / "nao-existe.log"), [])

    def test_simple_error_with_line(self):
        d = self.log("(./texto.tex\n! Undefined control sequence.\nl.23 \\foo\n")
        self.assertEqual([(x.severity, x.message, x.line) for x in d],
                         [("error", "Undefined control sequence.", 23)])

    def test_unwraps_line_broken_at_79_columns(self):
        # TeX breaks long messages at 79 columns; without joining them back,
        # the message reaches the panel in pieces.
        whole = ("! Package babel Error: Unknown option `portuges'. "
                 "Either you misspelled it and the correct spelling is portuguese.")
        pieces = [whole[i:i + 79] for i in range(0, len(whole), 79)]
        self.assertEqual(len(pieces[0]), 79, "o teste precisa quebrar onde o TeX quebra")
        d = self.log("\n".join(pieces) + "\nl.7 \\usepackage\n")
        self.assertEqual(len(d), 1)
        self.assertIn("misspelled it", d[0].message)

    def test_warning_with_line(self):
        d = self.log("LaTeX Warning: Reference `x' on input line 12 undefined.\n")
        self.assertEqual([(x.severity, x.line) for x in d], [("warning", 12)])

    def test_rerun_is_noise_and_goes_away(self):
        # latexmk sorts it out on its own; showing it only clutters the panel.
        self.assertEqual(
            self.log("LaTeX Warning: Label(s) may have changed. Rerun.\n"), [])

    def test_summary_has_file_and_line(self):
        d = Diagnostic("error", "algo", "sub/texto.tex", 9)
        self.assertEqual(d.summary, "texto.tex:9 — algo")

    def test_summary_without_file(self):
        self.assertEqual(Diagnostic("warning", "algo").summary, "algo")


class TestPaths(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="serifa-cam-")
        self.folder = Path(self._tmp.name) / "questionario-02"
        self.folder.mkdir()
        self.tex = self.folder / "texto.tex"
        self.tex.write_text("", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_pdf_named_after_the_tex_when_the_folder_one_is_missing(self):
        self.assertEqual(Builder._pdf_for(self.tex, self.folder).name, "texto.pdf")

    def test_pdf_named_after_the_folder_when_it_exists(self):
        # That is how the project's scripts/compilar.sh names it, so the
        # attachment comes out already identified.
        (self.folder / "questionario-02.pdf").write_bytes(b"%PDF")
        self.assertEqual(Builder._pdf_for(self.tex, self.folder).name,
                         "questionario-02.pdf")

    def test_shadow_is_stable_and_outside_the_project(self):
        a = Builder.shadow_folder(self.folder)
        b = Builder.shadow_folder(self.folder)
        self.assertEqual(a, b)
        self.assertNotIn(str(self.folder), str(a))

    def test_shadows_of_different_folders_do_not_collide(self):
        other = Path(self._tmp.name) / "questionario-03"
        self.assertNotEqual(Builder.shadow_folder(self.folder),
                            Builder.shadow_folder(other))

    def test_project_script_found_by_climbing(self):
        scripts = Path(self._tmp.name) / "scripts"
        scripts.mkdir()
        script = scripts / "compilar.sh"
        script.write_text("#!/bin/sh\n", encoding="utf-8")
        script.chmod(0o755)
        self.assertEqual(Builder._project_script(self.folder), script)

    def test_non_executable_script_is_ignored(self):
        scripts = Path(self._tmp.name) / "scripts"
        scripts.mkdir(exist_ok=True)
        (scripts / "compilar.sh").write_text("", encoding="utf-8")
        (scripts / "compilar.sh").chmod(0o644)
        self.assertIsNone(Builder._project_script(self.folder))


if __name__ == "__main__":
    unittest.main()
