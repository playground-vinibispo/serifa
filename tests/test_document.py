"""The open file, with no window at all.

The document only needs a buffer. These tests run in milliseconds, unlike the
ones that build an interface -- and this is exactly where the defects that
cost the user text live.
"""

import tempfile
import unittest
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from serifa.document import Document
from tests.support import pump, start, until


class TestDocument(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not start():
            raise unittest.SkipTest("sem servidor gráfico")

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="serifa-doc-")
        self.folder = Path(self._tmp.name)
        self.buffer = Gtk.TextBuffer()
        self.doc = Document(self.buffer)
        self.signals = []
        for signal in ("dirty-changed", "reloaded", "conflict", "failed"):
            self.doc.connect(signal, lambda *a, s=signal: self.signals.append(s))

    def tearDown(self):
        self._tmp.cleanup()

    def file_at(self, name="texto.tex", content="original\n"):
        path = self.folder / name
        path.write_text(content, encoding="utf-8")
        return path

    # ------------------------------------------------------------- opening

    def test_open_loads_and_is_clean(self):
        self.doc.open_file(self.file_at())
        self.assertEqual(self.doc.text, "original\n")
        self.assertFalse(self.doc.dirty)

    def test_open_puts_the_cursor_at_the_start(self):
        self.doc.open_file(self.file_at(content="a\nb\nc\n"))
        self.assertEqual(self.buffer.get_property("cursor-position"), 0)

    def test_opening_a_missing_file_warns_and_does_not_blow_up(self):
        self.assertFalse(self.doc.open_file(self.folder / "nao-existe.tex"))
        self.assertIn("failed", self.signals)

    # ------------------------------------------------------------- saving

    def test_save_writes_and_cleans(self):
        path = self.file_at()
        self.doc.open_file(path)
        self.buffer.set_text("novo conteudo\n")
        self.doc.mark_dirty()
        self.assertTrue(self.doc.save())
        self.assertEqual(path.read_text(encoding="utf-8"), "novo conteudo\n")
        self.assertFalse(self.doc.dirty)

    def test_save_without_a_path_fails(self):
        self.assertFalse(self.doc.save())

    def test_mark_dirty_is_idempotent(self):
        self.doc.open_file(self.file_at())
        self.signals.clear()
        self.doc.mark_dirty()
        self.doc.mark_dirty()
        self.assertEqual(self.signals.count("dirty-changed"), 1)

    # --------------------------------------------------------------- disk

    def test_external_change_with_clean_buffer_reloads(self):
        path = self.file_at()
        self.doc.open_file(path)
        path.write_text("de fora\n", encoding="utf-8")
        self.assertTrue(until(lambda: self.doc.text == "de fora\n", 4000))
        self.assertIn("reloaded", self.signals)

    def test_external_change_with_dirty_buffer_warns_and_keeps_it(self):
        path = self.file_at()
        self.doc.open_file(path)
        self.buffer.set_text("meu trabalho\n")
        self.doc.mark_dirty()
        path.write_text("de fora\n", encoding="utf-8")
        self.assertTrue(until(lambda: "conflict" in self.signals, 4000))
        self.assertEqual(self.doc.text, "meu trabalho\n")

    def test_saving_does_not_fire_a_conflict(self):
        # Saving itself touches the file; comparing the content avoids the
        # false alarm, and is sturdier than ignoring the next event -- the
        # monitor emits more than one per save.
        path = self.file_at()
        self.doc.open_file(path)
        self.buffer.set_text("meu texto\n")
        self.doc.mark_dirty()
        self.doc.save()
        pump(1200)
        self.assertNotIn("conflict", self.signals)

    def test_reload_keeps_the_cursor_position(self):
        path = self.file_at(content="linha um\nlinha dois\nlinha tres\n")
        self.doc.open_file(path)
        self.buffer.place_cursor(self.buffer.get_iter_at_offset(12))
        path.write_text("linha um\nlinha DOIS\nlinha tres\n", encoding="utf-8")
        self.assertTrue(until(lambda: "DOIS" in self.doc.text, 4000))
        self.assertEqual(self.buffer.get_property("cursor-position"), 12)

    def test_reload_to_shorter_text_does_not_blow_up(self):
        path = self.file_at(content="um texto bem longo aqui\n")
        self.doc.open_file(path)
        self.buffer.place_cursor(self.buffer.get_end_iter())
        path.write_text("x\n", encoding="utf-8")
        self.assertTrue(until(lambda: self.doc.text == "x\n", 4000))
        self.assertLessEqual(self.buffer.get_property("cursor-position"),
                             self.buffer.get_char_count())

    def test_set_path_starts_watching_the_new_one(self):
        new = self.folder / "outro.tex"
        new.write_text("inicial\n", encoding="utf-8")
        self.doc.set_path(new)
        self.assertEqual(self.doc.path, new)
        self.assertEqual(self.doc.name, "outro.tex")


if __name__ == "__main__":
    unittest.main()
