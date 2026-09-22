"""Editing behaviours: auto-pairing, word count, the vim cycle."""

import unittest

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk

from tests.support import start


class TestEditor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not start():
            raise unittest.SkipTest("sem servidor gráfico")

    def setUp(self):
        from serifa.editor import Editor
        self.ed = Editor()
        self.buffer = self.ed.buffer

    def type_text(self, text):
        # Character by character: the pairs only react to a single insertion,
        # and inserting the whole string gives a false negative.
        for c in text:
            self.buffer.insert_at_cursor(c)

    @property
    def text(self):
        return self.buffer.get_text(*self.buffer.get_bounds(), True)

    # ---------------------------------------------------------- auto-pairing

    def test_brace_closes_itself(self):
        self.type_text("a{")
        self.assertEqual(self.text, "a{}")
        self.assertEqual(self.buffer.get_property("cursor-position"), 2)

    def test_parenthesis_and_bracket(self):
        self.type_text("f(")
        self.assertEqual(self.text, "f()")
        self.buffer.set_text("")
        self.type_text("v[")
        self.assertEqual(self.text, "v[]")

    def test_dollar_closes(self):
        self.type_text("x$")
        self.assertEqual(self.text, "x$$")

    def test_typing_the_closer_steps_over_it(self):
        self.type_text("a{")
        self.assertEqual(self.text, "a{}")
        self.buffer.insert_at_cursor("}")
        self.assertEqual(self.text, "a{}", "digitar } duplicou o fechamento")
        self.assertEqual(self.buffer.get_property("cursor-position"), 3)

    def test_dollar_closes_math_by_stepping_over_the_existing_one(self):
        # Typing $ with a $ ahead closes inline math: the cursor steps over
        # it. This used to produce a third $.
        self.buffer.set_text("$x$")
        self.buffer.place_cursor(self.buffer.get_iter_at_offset(2))
        self.buffer.insert_at_cursor("$")
        self.assertEqual(self.text, "$x$")
        self.assertEqual(self.buffer.get_property("cursor-position"), 3)

    def test_begin_closes_the_environment(self):
        self.type_text("\\begin{align}")
        self.buffer.insert_at_cursor("\n")
        self.assertEqual(self.text, "\\begin{align}\n  \n\\end{align}")

    def test_begin_keeps_the_indent(self):
        self.type_text("  \\begin{itemize}")
        self.buffer.insert_at_cursor("\n")
        self.assertIn("\n  \\end{itemize}", self.text)

    # ------------------------------------------------------------ counting

    def test_count_ignores_command_and_braces(self):
        # "duas palavras" is what one reads; \textbf and the braces do not count.
        self.buffer.set_text("\\textbf{duas} palavras")
        self.assertEqual(self.ed.count_words(), 2)

    def test_count_ignores_comments(self):
        self.buffer.set_text("prosa de verdade\n% comentario que nao conta\n")
        self.assertEqual(self.ed.count_words(), 3)

    def test_count_ignores_inline_math(self):
        self.buffer.set_text("antes $x^2 + y^2$ depois")
        self.assertEqual(self.ed.count_words(), 2)

    # ---------------------------------------------------------------- vim

    def test_vim_turns_on_and_off(self):
        self.assertFalse(self.ed.vim_active)
        self.ed.toggle_vim(True)
        self.assertTrue(self.ed.vim_active)
        self.ed.toggle_vim(False)
        self.assertFalse(self.ed.vim_active)

    def test_vim_uses_overwrite_for_the_block_cursor(self):
        # That is what makes a leaked key overwrite instead of insert. If this
        # changes, the diagnosis of that bug changes with it.
        self.ed.toggle_vim(True)
        self.assertTrue(self.ed.get_overwrite())
        self.ed.toggle_vim(False)
        self.assertFalse(self.ed.get_overwrite())

    def test_handle_key_is_inert_with_vim_off(self):
        keyval = Gdk.unicode_to_keyval(ord("v"))
        self.assertFalse(self.ed.handle_key(keyval, Gdk.ModifierType(0)))

    def test_v_in_insert_mode_does_not_arm_the_sequence(self):
        # The guard is comparing the character count before and after: if the
        # text changed, that "v" was the letter v.
        self.ed.toggle_vim(True)
        self.buffer.set_text("abc")
        self.buffer.place_cursor(self.buffer.get_end_iter())
        self.ed.handle_key(Gdk.unicode_to_keyval(ord("v")), Gdk.ModifierType(0))
        self.buffer.insert_at_cursor("v")
        consumed = self.ed.handle_key(Gdk.unicode_to_keyval(ord("i")),
                                      Gdk.ModifierType(0))
        self.assertFalse(consumed)


if __name__ == "__main__":
    unittest.main()
