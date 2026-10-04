# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Vinícius Bispo e colaboradores

"""Scrolling must render pages outside the initial viewport."""
import cairo

from tests.support import GraphicalCase, pump


class TestPreviewScroll(GraphicalCase):
    def test_scrolling_redraws_newly_visible_pages(self):
        path = self.folder / "long.pdf"
        surface = cairo.PDFSurface(str(path), 500, 900)
        context = cairo.Context(surface)
        for i in range(4):
            context.move_to(40, 80)
            context.show_text(f"Page {i + 1}")
            context.show_page()
        surface.finish()
        preview = self.window._preview
        positions = []
        original = preview._draw
        def draw(*args):
            positions.append(preview._scroller.get_vadjustment().get_value())
            original(*args)
        preview._area.set_draw_func(draw)
        self.assertTrue(preview.load(path))
        pump(300)
        positions.clear()
        preview.go_to_page(3)
        pump(300)
        self.assertEqual(preview.current_page, 3)
        self.assertTrue(any(position > 0 for position in positions),
                        "Scrolled pages must be rendered, not remain blank")

    def test_open_refreshes_stale_pdf_without_saving_source(self):
        from unittest.mock import patch

        source = self.file_at("report.tex", "Current text")
        self.window._continuous_build = True
        with patch.object(self.window._builder, "build_preview") as build:
            self.window.open_file(source)
            build.assert_called_once_with("Current text", source)
        self.assertEqual(source.read_text(), "Current text")

    def test_scroll_explicitly_invalidates_visible_page_drawing(self):
        from unittest.mock import patch

        preview = self.window._preview
        adjustment = preview._scroller.get_vadjustment()
        adjustment.configure(0, 0, 5000, 10, 100, 400)
        with patch.object(preview._area, "queue_draw") as redraw:
            adjustment.set_value(1100)
            redraw.assert_called()
