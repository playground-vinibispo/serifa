"""LaTeX wrappers, context-aware completion and accelerators."""

import unittest

from tests.support import GraphicalCase, pump


class TestFormatting(GraphicalCase):
    def test_wraps_the_selection(self):
        self.buffer.set_text("palavra solta")
        self.buffer.select_range(self.buffer.get_iter_at_offset(0),
                                 self.buffer.get_iter_at_offset(7))
        self.window.format_text("textbf")
        self.assertEqual(self.text, "\\textbf{palavra} solta")

    def test_without_selection_opens_the_braces_with_the_cursor_inside(self):
        self.buffer.set_text("abc")
        self.buffer.place_cursor(self.buffer.get_end_iter())
        self.window.format_text("textit")
        self.assertEqual(self.text, "abc\\textit{}")
        self.assertEqual(self.buffer.get_property("cursor-position"), 11)

    def test_does_not_double_the_closer(self):
        # Inserted all at once, auto-pairing does not react -- it only looks
        # at a lone character.
        self.buffer.set_text("")
        self.window.format_text("enquote")
        self.assertEqual(self.text, "\\enquote{}")

    def test_every_format_produces_its_command(self):
        for name, command, _icon, _label in self.window.FORMATS:
            self.buffer.set_text("")
            self.window.format_text(command)
            self.assertEqual(self.text, f"\\{command}{{}}", name)


class TestAccelerators(GraphicalCase):
    def accels(self, name):
        return self.window.get_application().get_accels_for_action(f"win.{name}")

    def test_ctrl_b_is_bold_with_vim_off(self):
        self.assertEqual(self.accels("bold"), ["<Control>b"])

    def test_build_no_longer_uses_ctrl_b(self):
        self.assertNotIn("<Control>b", self.accels("build"))
        self.assertIn("F5", self.accels("build"))

    def test_vim_on_gives_ctrl_b_and_ctrl_i_back(self):
        # A window accelerator is resolved before the widget's controllers
        # and would beat vim without warning; vim users expect Ctrl+B to mean
        # page up.
        self.window._vim_button.set_active(True)
        self.assertEqual(self.accels("bold"), [])
        self.assertEqual(self.accels("italic"), [])

    def test_turning_vim_off_restores_the_shortcuts(self):
        self.window._vim_button.set_active(True)
        self.window._vim_button.set_active(False)
        self.assertEqual(self.accels("bold"), ["<Control>b"])


class TestContextCompletion(GraphicalCase):
    def setUp(self):
        super().setUp()
        (self.folder / "referencias.bib").write_text(
            "@book{einstein_infeld,\n  title = {A Evolução da Física},\n}\n",
            encoding="utf-8")
        self.path = self.file_at("texto.tex", "\\label{sec:um}\nTexto.\n")
        self.window.open_file(self.path)
        pump(200)

    def type_at_the_end(self, suffix):
        self.buffer.set_text("\\label{sec:um}\nTexto.\n")
        self.buffer.place_cursor(self.buffer.get_end_iter())
        self.type_text(suffix)
        pump(250)

    def test_cite_offers_the_bib_keys(self):
        self.type_at_the_end("\\cite{")
        self.assertTrue(self.window._popup.visible)
        self.assertIn("einstein_infeld", [i.text for i in self.window._popup._items])

    def test_ref_offers_the_document_labels(self):
        self.type_at_the_end("\\ref{")
        self.assertEqual([i.text for i in self.window._popup._items], ["sec:um"])

    def test_prose_does_not_open_the_bubble(self):
        self.type_at_the_end("texto comum ")
        self.assertFalse(self.window._popup.visible)

    def test_moving_the_cursor_does_not_open_the_bubble(self):
        # The preambulo.tex bug: passing over an already written \begin{...}
        # opened the bubble, which silenced vim, and the next key overwrote a
        # letter.
        self.buffer.set_text("\\begin{center}\ntexto\n\\end{center}\n")
        pump(200)
        self.buffer.place_cursor(self.buffer.get_iter_at_offset(9))
        pump(250)
        self.assertFalse(self.window._popup.visible)

    def test_accepting_inserts_and_steps_over_the_closer(self):
        self.type_at_the_end("\\cite{eif")
        self.assertTrue(self.window._popup.visible)
        self.window._popup._accept(0)
        pump(150)
        self.assertIn("\\cite{einstein_infeld}", self.text)
        self.assertFalse(self.window._popup.visible)


if __name__ == "__main__":
    unittest.main()
