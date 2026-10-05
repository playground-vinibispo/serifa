# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Vinícius Bispo e colaboradores

"""User-facing writing and preview controls."""
from tests.support import GraphicalCase


class TestVisualWorkflow(GraphicalCase):
    def test_title_keeps_path_in_tooltip(self):
        path = self.file_at("draft.tex", "hello")
        self.window.open_file(path)
        self.assertEqual(self.window._title.get_subtitle(), "")
        self.assertEqual(self.window._title.get_tooltip_text(), str(path))

    def test_outline_wraps_and_tracks_cursor(self):
        self.buffer.set_text(
            r"\section{A very long section heading that needs wrapping}"
            + "\nbody\n" + r"\section{Second}" + "\nbody"
        )
        self.window._rebuild_outline()
        row = self.window._outline.get_row_at_index(0)
        self.assertTrue(row.get_child().get_wrap())
        self.editor.go_to_line(4)
        self.assertEqual(self.window._outline.get_selected_row().line_number, 3)

    def test_build_button_explains_busy_state(self):
        self.window._on_build_started(None, False)
        self.assertEqual(self.window._build_button.get_label(), "Compilando…")
        self.window._on_build_finished(None, False, "", [], False)
        self.assertEqual(self.window._build_button.get_label(), "Compilar")

    def test_zoom_label_tracks_zoom_without_document(self):
        preview = self.window._preview
        preview.apply_zoom(1.5)
        self.assertEqual(preview._zoom_label.get_label(), "150%")
        self.assertEqual(preview._page_label.get_label(), "Sem páginas")

    def test_writing_controls_change_measure_and_font(self):
        self.window.lookup_action("font-larger").activate(None)
        self.assertGreater(self.editor.font_size, 11.5)
        self.window.lookup_action("column-narrower").activate(None)
        self.assertLess(self.editor.measure, 74)

    def test_dark_theme_changes_editor_scheme(self):
        self.window.lookup_action("theme").activate(None)
        self.assertTrue(self.window.has_css_class("serifa-dark"))
        self.assertEqual(self.buffer.get_style_scheme().get_id(), "serifa-dark")

    def test_pdf_page_counter_follows_navigation(self):
        import cairo

        from tests.support import pump
        path = self.folder / "sample.pdf"
        surface = cairo.PDFSurface(str(path), 300, 500)
        context = cairo.Context(surface)
        for _ in range(3):
            context.show_page()
        surface.finish()
        preview = self.window._preview
        self.assertTrue(preview.load(path))
        pump(150)
        preview.go_to_page(2)
        self.assertEqual(preview._page_label.get_label(), "2 / 3")

    def test_preferences_survive_restore(self):
        self.window._toggle_theme()
        self.editor.adjust_writing(2, -12)
        self.window._save_state()
        self.window._toggle_theme()
        self.editor.adjust_writing(-2, 12)
        self.window._restore_state()
        self.assertTrue(self.window.has_css_class("serifa-dark"))
        self.assertEqual(self.editor.font_size, 13.5)
        self.assertEqual(self.editor.measure, 62)

    def test_diagnostic_click_goes_to_error_line(self):
        from serifa.build import Diagnostic
        self.buffer.set_text("one\ntwo\nthree")
        self.window._diagnostics = [Diagnostic("error", "Error", line=3)]
        self.window._fill_diagnostics()
        row = self.window._diagnostics_list.get_row_at_index(0)
        self.window._diagnostics_list.emit("row-activated", row)
        cursor = self.buffer.get_iter_at_mark(self.buffer.get_insert())
        self.assertEqual(cursor.get_line(), 2)

    def test_diagnostic_foreground_follows_app_theme_not_desktop(self):
        from gi.repository import Adw, Gtk

        from serifa.build import Diagnostic
        from tests.support import pump

        manager = Adw.StyleManager.get_default()
        original = manager.get_color_scheme()
        self.window._diagnostics = [Diagnostic("warning", "Test warning", line=1)]
        self.window._fill_diagnostics()
        row = self.window._diagnostics_list.get_row_at_index(0)

        def descendants(widget):
            yield widget
            child = widget.get_first_child()
            while child is not None:
                yield from descendants(child)
                child = child.get_next_sibling()

        try:
            for dark in (False, True):
                manager.set_color_scheme(
                    Adw.ColorScheme.FORCE_LIGHT if dark else Adw.ColorScheme.FORCE_DARK
                )
                if self.window.has_css_class("serifa-dark") != dark:
                    self.window._toggle_theme()
                for state in (Gtk.StateFlags.NORMAL, Gtk.StateFlags.PRELIGHT,
                              Gtk.StateFlags.SELECTED, Gtk.StateFlags.FOCUSED):
                    with self.subTest(dark=dark, state=state):
                        row.set_state_flags(state, True)
                        pump(250)
                        widgets = [row] + [
                            widget for widget in descendants(row)
                            if isinstance(widget, Gtk.Label | Gtk.Image)
                        ]
                        for widget in widgets:
                            color = widget.get_style_context().get_color()
                            brightness = (color.red + color.green + color.blue) / 3
                            self.assertGreater(color.alpha, 0.95)
                            if dark:
                                self.assertGreater(brightness, 0.75)
                            else:
                                self.assertLess(brightness, 0.3)
        finally:
            row.set_state_flags(Gtk.StateFlags.NORMAL, True)
            manager.set_color_scheme(original)
