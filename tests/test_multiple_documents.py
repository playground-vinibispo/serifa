# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Vinícius Bispo e colaboradores

"""Application file requests must open every document as a tab."""
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from tests.support import start


class TestMultipleDocuments(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not start():
            raise unittest.SkipTest("sem servidor gráfico")

    def test_file_request_opens_every_document(self):
        from serifa.main import Serifa
        app = Serifa()
        files = [MagicMock(), MagicMock()]
        files[0].get_path.return_value = "/tmp/first.tex"
        files[1].get_path.return_value = "/tmp/second.tex"
        workspace = MagicMock()
        with patch.object(app, "_ensure_window", return_value=workspace):
            app.do_open(files, 2, "")
        self.assertEqual(workspace.open_document.call_count, 2)
        workspace.open_document.assert_any_call(Path("/tmp/first.tex"))
        workspace.open_document.assert_any_call(Path("/tmp/second.tex"))

    def test_activate_creates_initial_tab(self):
        from serifa.main import Serifa
        app = Serifa()
        workspace = MagicMock()
        workspace.tabs.get_n_pages.return_value = 0
        with patch.object(app, "_ensure_window", return_value=workspace):
            app.do_activate()
        workspace._new_document.assert_called_once()
        workspace.present.assert_called_once()
