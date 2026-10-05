# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Vinícius Bispo e colaboradores

"""The application icon must resolve from a source checkout."""

import unittest
from pathlib import Path

from tests.support import start


class TestAppIcon(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not start():
            raise unittest.SkipTest("no graphical display")

    def test_startup_resolves_bundled_icon(self):
        from gi.repository import Gdk, Gtk

        from serifa.main import Serifa

        app = Serifa()
        self.assertTrue(app.register(None))
        name = app.get_application_id()
        self.assertEqual(Gtk.Window.get_default_icon_name(), name)
        theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
        for size in (16, 32, 64):
            with self.subTest(size=size):
                icon = theme.lookup_icon(
                    name, None, size, 1, Gtk.TextDirection.NONE, Gtk.IconLookupFlags(0)
                )
                self.assertIsNotNone(icon.get_file())
                path = Path(icon.get_file().get_path())
                self.assertEqual(path.name, f"{name}.svg")
