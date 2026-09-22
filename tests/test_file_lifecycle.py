"""Saving, preview and the disk watcher.

The editor's most important invariant lives here: **typing does not write to
the user's file.** Until not long ago it did, as a side effect of the
continuous build.
"""

import shutil
import unittest

from serifa.build import Builder
from tests.support import GraphicalCase, pump, until

DOCUMENT = (
    "\\documentclass[12pt]{article}\n"
    "\\begin{document}\n"
    "Uma frase qualquer.\n"
    "\\end{document}\n"
)


class TestSaving(GraphicalCase):
    def setUp(self):
        super().setUp()
        self.path = self.file_at("texto.tex", DOCUMENT)
        self.original = self.path.read_text(encoding="utf-8")
        self.window.open_file(self.path)
        pump(200)

    def test_open_loads_the_text(self):
        self.assertIn("Uma frase qualquer", self.text)

    def test_typing_does_not_save(self):
        self.type_text("mexido ")
        pump(200)
        self.assertEqual(self.path.read_text(encoding="utf-8"), self.original)
        self.assertTrue(self.window._dirty)

    def test_preview_does_not_save(self):
        self.type_text("mexido ")
        self.window.preview_build()
        pump(400)
        self.assertEqual(self.path.read_text(encoding="utf-8"), self.original)

    @unittest.skipUnless(shutil.which("latexmk"), "latexmk não instalado")
    def test_preview_builds_in_the_shadow_outside_the_project(self):
        shadow = Builder.shadow_folder(self.path.parent)
        self.assertNotIn(str(self.folder), str(shadow))
        self.window.preview_build()
        self.assertTrue(until(lambda: (shadow / "previa.tex").exists(), 4000))
        # no build leftovers in the user's folder
        self.assertEqual(sorted(p.name for p in self.folder.iterdir()),
                         ["estado.json", "texto.tex"])

    def test_save_writes_and_clears_dirty(self):
        self.type_text("mexido ")
        self.window._write()
        self.assertIn("mexido", self.path.read_text(encoding="utf-8"))
        self.assertFalse(self.window._dirty)

    def test_closing_dirty_is_blocked(self):
        self.type_text("mexido ")
        self.assertTrue(self.window._on_close_request())

    def test_closing_clean_goes_straight_through(self):
        self.assertFalse(self.window._on_close_request())

    def test_save_button_reflects_the_state(self):
        self.assertFalse(self.window._save_button.get_sensitive())
        self.type_text("x")
        pump(100)
        self.assertTrue(self.window._save_button.get_sensitive())


class TestWatcher(GraphicalCase):
    def setUp(self):
        super().setUp()
        self.path = self.file_at("texto.tex", "linha um\nlinha dois\n")
        self.window.open_file(self.path)
        pump(300)

    def test_clean_buffer_reloads_on_its_own(self):
        self.path.write_text("MUDOU FORA\nlinha dois\n", encoding="utf-8")
        self.assertTrue(until(lambda: self.text.startswith("MUDOU FORA"), 4000))
        self.assertFalse(self._banner_visible())

    def test_dirty_buffer_is_kept_and_warned_about(self):
        self.type_text("EDICAO LOCAL ")
        pump(100)
        self.path.write_text("MUDOU FORA\n", encoding="utf-8")
        self.assertTrue(until(self._banner_visible, 4000))
        self.assertIn("EDICAO LOCAL", self.text)

    def test_reload_discards_and_brings_the_disk_back(self):
        self.type_text("EDICAO LOCAL ")
        pump(100)
        self.path.write_text("DO DISCO\n", encoding="utf-8")
        self.assertTrue(until(self._banner_visible, 4000))
        self.window._reload()
        self.assertTrue(self.text.startswith("DO DISCO"))
        self.assertFalse(self.window._dirty)

    def test_saving_from_the_editor_does_not_raise_the_banner(self):
        # Saving itself trips the watcher; the content is compared before
        # raising the alarm, which is sturdier than an "ignore the next event"
        # flag -- the monitor emits more than one.
        self.type_text("meu texto ")
        self.window._write()
        pump(1200)
        self.assertFalse(self._banner_visible())

    def _banner_visible(self):
        return self.window._banner.get_revealed()


class TestGuardWhenSwitchingFiles(GraphicalCase):
    """Switching files with pending changes must not swallow the text.

    Closing the window already asked; opening another file did not, and
    replaced the buffer silently. That was data loss, not a nuisance.
    """

    def setUp(self):
        super().setUp()
        self.one = self.file_at("um.tex", "conteudo do um\n")
        self.two = self.file_at("dois.tex", "conteudo do dois\n")
        self.window.open_file(self.one)
        pump(200)

    def test_clean_switches_straight_away(self):
        self.assertFalse(self.window._settle_pending(lambda: None))

    def test_dirty_defers_the_switch(self):
        self.type_text("mexido ")
        proceeded = []
        self.assertTrue(self.window._settle_pending(lambda: proceeded.append(1)))
        self.assertEqual(proceeded, [], "trocou antes de perguntar")

    def test_cancel_does_not_proceed_and_keeps_the_text(self):
        self.type_text("mexido ")
        proceeded = []
        self.window._apply_response("cancel", lambda: proceeded.append(1))
        self.assertEqual(proceeded, [])
        self.assertIn("mexido", self.text)
        self.assertTrue(self.window._dirty)

    def test_discard_proceeds_without_saving(self):
        self.type_text("mexido ")
        proceeded = []
        self.window._apply_response("discard", lambda: proceeded.append(1))
        self.assertEqual(proceeded, [1])
        self.assertNotIn("mexido", self.one.read_text(encoding="utf-8"))
        self.assertFalse(self.window._dirty)

    def test_save_writes_and_proceeds(self):
        self.type_text("mexido ")
        proceeded = []
        self.window._apply_response("save", lambda: proceeded.append(1))
        self.assertEqual(proceeded, [1])
        self.assertIn("mexido", self.one.read_text(encoding="utf-8"))
        self.assertFalse(self.window._dirty)

    def test_open_another_after_discarding(self):
        self.type_text("mexido ")
        self.window._apply_response("discard", lambda: self.window.open_file(self.two))
        pump(150)
        self.assertIn("conteudo do dois", self.text)
        self.assertEqual(self.window._file, self.two)

    def test_closing_uses_the_same_guard(self):
        self.type_text("mexido ")
        self.assertTrue(self.window._on_close_request())


if __name__ == "__main__":
    unittest.main()
