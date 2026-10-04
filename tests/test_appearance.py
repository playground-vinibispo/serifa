# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Vinícius Bispo e colaboradores

"""Typography and the column measure.

No colours: the palette is the writer's choice, and the attempt to impose one
was reverted on request. What is here is what is not taste -- this is not a
code editor, and code tools are of no use to a hundred-word paragraph.
"""

import unittest

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from tests.support import GraphicalCase, pump, start


class TestCodeFurniture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not start():
            raise unittest.SkipTest("sem servidor gráfico")

    def setUp(self):
        from serifa.editor import Editor
        self.ed = Editor()

    def test_no_line_numbers(self):
        self.assertFalse(self.ed.get_show_line_numbers())

    def test_no_eighty_column_ruler(self):
        self.assertFalse(self.ed.get_show_right_margin())

    def test_no_current_line_highlight(self):
        self.assertFalse(self.ed.get_highlight_current_line())

    def test_wraps_on_whole_words(self):
        # WORD_CHAR splits a word in the middle when it does not fit; in prose
        # that is worse than leaving the line short.
        self.assertEqual(self.ed.get_wrap_mode(), Gtk.WrapMode.WORD)

    def test_imposes_no_colour_scheme(self):
        from serifa import appearance
        self.assertFalse(hasattr(appearance, "install_scheme"),
                         "a paleta é escolha do usuário")


class TestColumnMeasure(GraphicalCase):
    def visible_characters(self):
        from serifa.appearance import character_width
        width = self.editor.get_width() - self.editor.get_left_margin() \
            - self.editor.get_right_margin()
        return width // max(1, character_width(self.editor))

    def test_wide_pane_caps_the_measure(self):
        from serifa.appearance import MEASURE
        self.window.set_default_size(1900, 1000)
        self.window._split.set_position(1300)
        pump(500)
        self.assertLessEqual(self.visible_characters(), MEASURE + 2)
        self.assertGreater(self.editor.get_left_margin(), 24)

    def test_narrow_pane_uses_the_minimum_margin(self):
        self.window.set_default_size(700, 600)
        self.window._split.set_position(360)
        pump(500)
        self.assertEqual(self.editor.get_left_margin(), 24)

    def test_margins_are_symmetric(self):
        pump(300)
        self.assertEqual(self.editor.get_left_margin(), self.editor.get_right_margin())

    def test_editor_font(self):
        from serifa.appearance import FONT
        family = self.editor.get_pango_context().get_font_description().get_family()
        self.assertIn(FONT, family)


if __name__ == "__main__":
    unittest.main()
