# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Vinícius Bispo e colaboradores

"""Key routing through the window, and visual mode's text objects.

These tests exist because of five wrong diagnoses in a row. Each one guards
something I assumed and got wrong.
"""

import unittest

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gtk

from tests.support import GraphicalCase, pump, until


class TestTextObjects(GraphicalCase):
    def setUp(self):
        super().setUp()
        self.window._vim_button.set_active(True)
        self.editor.grab_focus()
        # Wait for the condition, not a fixed time: focus settles at a
        # different pace depending on the compositor.
        self.assertTrue(until(self.editor.is_focus, 3000), "o editor não ganhou o foco")

    def prepare(self, text, mark):
        self.buffer.set_text(text)
        self.buffer.place_cursor(self.buffer.get_iter_at_offset(text.index(mark)))
        self.editor._sequence.clear()

    def test_vi_braces(self):
        self.prepare(r"\textbf{palavra aqui} fim", "palavra")
        self.send_keys("vi{")
        self.assertEqual(self.selection(), "palavra aqui")

    def test_va_braces_includes_the_delimiters(self):
        self.prepare(r"\cabecalho{um}{dois} fim", "dois")
        self.send_keys("va{")
        self.assertEqual(self.selection(), "{dois}")

    def test_vi_parentheses(self):
        self.prepare(r"f(x, g(y)) fim", "y")
        self.send_keys("vi(")
        self.assertEqual(self.selection(), "y")

    def test_vi_quotes(self):
        self.prepare(r'diz "uma coisa" tal', "uma")
        self.send_keys('vi"')
        self.assertEqual(self.selection(), "uma coisa")

    def test_shift_in_the_middle_does_not_reset_the_sequence(self):
        # The bug that took five attempts: "{" needs Shift, Shift arrives as a
        # key of its own between the "i" and the "{", and treating it as noise
        # reset the state machine.
        self.prepare(r"\textbf{palavra} fim", "palavra")
        keyval, state = Gdk.unicode_to_keyval(ord("v")), Gdk.ModifierType(0)
        self.window._on_key_pressed(None, keyval, 0, state)
        self.window._on_key_pressed(None, Gdk.unicode_to_keyval(ord("i")), 0, state)
        self.window._on_key_pressed(None, Gdk.KEY_Shift_L, 0, state)
        self.assertEqual(self.editor._sequence, ["v", "i"],
                         "o Shift zerou a sequência")

    def test_without_a_block_the_key_goes_on_to_vim(self):
        self.prepare("sem chave aqui", "chave")
        consumed = self.send_keys("vi{")
        self.assertFalse(consumed[-1], "o { deveria seguir para o vim")
        self.assertIsNone(self.selection())

    def test_the_bubble_never_turns_vim_off(self):
        # The earlier wrong fix put the controller in NONE while the bubble
        # was open, and normal mode stopped working.
        def phase():
            return self.editor._vim_controller.get_propagation_phase()

        self.assertEqual(phase(), Gtk.PropagationPhase.CAPTURE)
        self.buffer.set_text("")
        self.type_text("\\cite{")
        pump(300)
        self.assertEqual(phase(), Gtk.PropagationPhase.CAPTURE,
                         "o balão desligou o vim")


class TestWindowFocus(GraphicalCase):
    def test_without_focus_on_the_editor_the_window_does_not_handle_it(self):
        self.window._vim_button.set_active(True)
        self.window._search_entry.grab_focus()
        until(lambda: not self.editor.is_focus(), 2000)
        keyval = Gdk.unicode_to_keyval(ord("v"))
        consumed = self.window._on_key_pressed(None, keyval, 0, Gdk.ModifierType(0))
        self.assertFalse(consumed)


if __name__ == "__main__":
    unittest.main()
