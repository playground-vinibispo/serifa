# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Vinícius Bispo e colaboradores

"""Documents stay independent inside one tabbed window."""
from tests.support import GraphicalCase, pump


class TestTabs(GraphicalCase):
    def setUp(self):
        super().setUp()
        from serifa.workspace import Workspace
        self.workspace = Workspace(application=self._app)
        self.workspace.present()

    def tearDown(self):
        self.workspace.destroy()
        super().tearDown()

    def test_open_switch_save_and_undo_are_independent(self):
        first_path = self.file_at("one.tex", "one")
        second_path = self.file_at("two.tex", "two")
        first = self.workspace.open_document(first_path)
        first.buffer.insert_at_cursor("edited ")
        second = self.workspace.open_document(second_path)
        second._continuous_build = False
        first._continuous_build = False
        self.assertEqual(self.workspace.tabs.get_n_pages(), 2)
        self.assertIs(self.workspace.active_document, second)
        self.assertEqual(first._editor.text, "edited one")
        second.buffer.insert_at_cursor("other ")
        second._document.save()
        self.assertEqual(first_path.read_text(), "one")
        self.assertEqual(second_path.read_text(), "other two")
        self.workspace.open_document(first_path)
        self.assertEqual(self.workspace.tabs.get_n_pages(), 2)
        self.assertIs(self.workspace.active_document, first)
        first.buffer.undo()
        self.assertEqual(first._editor.text, "one")

    def test_clean_tab_closes_without_closing_others(self):
        self.workspace.open_document(self.file_at("one.tex", "one"))
        second = self.workspace.open_document(self.file_at("two.tex", "two"))
        page = self.workspace.tabs.get_selected_page()
        self.workspace.tabs.close_page(page)
        pump(50)
        self.assertEqual(self.workspace.tabs.get_n_pages(), 1)
        self.assertIsNot(self.workspace.active_document, second)

    def test_dirty_title_and_close_confirmation(self):
        doc = self.workspace.open_document(self.file_at("one.tex", "one"))
        doc.buffer.insert_at_cursor("changed ")
        page = self.workspace.tabs.get_selected_page()
        self.assertIn("•", page.get_title())
        from unittest.mock import patch
        with patch.object(doc, "_settle_pending", return_value=True) as ask:
            self.workspace.tabs.close_page(page)
            ask.assert_called_once()
        self.assertEqual(self.workspace.tabs.get_n_pages(), 1)

    def test_actions_follow_selected_tab(self):
        first = self.workspace.open_document(self.file_at("one.tex", "one"))
        second = self.workspace.open_document(self.file_at("two.tex", "two"))
        self.workspace.activate_action("win.font-larger", None)
        self.assertEqual(first._editor.font_size, 12)
        self.assertEqual(second._editor.font_size, 12)

    def test_empty_tab_is_reused_for_first_file(self):
        self.workspace._new_document()
        self.workspace.open_document(self.file_at("one.tex", "one"))
        self.assertEqual(self.workspace.tabs.get_n_pages(), 1)

    def test_cancel_closing_workspace_keeps_dirty_tab(self):
        from unittest.mock import patch
        doc = self.workspace.open_document(self.file_at("one.tex", "one"))
        doc.buffer.insert_at_cursor("changed ")
        with patch.object(doc, "_settle_pending", return_value=True):
            self.assertTrue(self.workspace._close_workspace())
        self.assertEqual(self.workspace.tabs.get_n_pages(), 1)
        self.assertTrue(doc._dirty)

    def test_cancel_tab_close_allows_later_close(self):
        from unittest.mock import patch
        doc = self.workspace.open_document(self.file_at("one.tex", "one"))
        doc.buffer.insert_at_cursor("changed ")
        page = self.workspace.tabs.get_selected_page()
        def cancel(_proceed, on_cancel=None):
            on_cancel()
            return True
        with patch.object(doc, "_settle_pending", side_effect=cancel):
            self.workspace.tabs.close_page(page)
        self.assertEqual(self.workspace.tabs.get_n_pages(), 1)
        doc._document.save()
        self.workspace.tabs.close_page(page)
        self.assertEqual(self.workspace.tabs.get_n_pages(), 0)

    def test_appearance_is_shared_by_existing_and_new_tabs(self):
        first = self.workspace.open_document(self.file_at("one.tex", "one"))
        second = self.workspace.open_document(self.file_at("two.tex", "two"))
        second._toggle_theme()
        second._editor.adjust_writing(2, -12)
        third = self.workspace.open_document(self.file_at("three.tex", "three"))
        for doc in (first, second, third):
            self.assertTrue(doc.has_css_class("serifa-dark"))
            self.assertTrue(doc._tab_page.get_child().has_css_class("serifa-dark"))
            self.assertEqual(doc._editor.font_size, 13.5)
            self.assertEqual(doc._editor.measure, 62)
            self.assertEqual(doc.buffer.get_style_scheme().get_id(), "serifa-dark")
        self.assertTrue(self.workspace.has_css_class("serifa-dark"))
