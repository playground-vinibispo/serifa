"""The PDF pane.

Renders with Poppler straight into cairo -- no PNGs on disk in between, which
is what makes Neovim's preview slower with every rebuild. Pages are drawn on
demand: only the visible band ever gets rasterised.
"""

from __future__ import annotations

from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Poppler", "0.18")

from gi.repository import Gdk, Gtk, Poppler

PAGE_GAP = 12


class Preview(Gtk.Box):
    """Continuous vertical scroll through the PDF's pages."""

    __gtype_name__ = "SerifaPreview"

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)

        self._document: Poppler.Document | None = None
        self._zoom = 1.0
        self._fit_width = True
        self._path: Path | None = None

        self._area = Gtk.DrawingArea()
        self._area.set_draw_func(self._draw)

        self._scroller = Gtk.ScrolledWindow()
        self._scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self._scroller.set_child(self._area)
        self._scroller.set_vexpand(True)
        self._scroller.get_hadjustment().connect("changed", self._on_width_changed)

        self._empty = Gtk.Label()
        self._empty.set_markup(
            "<span size='large'>Sem PDF ainda</span>\n"
            "<span alpha='60%'>Ctrl+B compila</span>"
        )
        self._empty.set_justify(Gtk.Justification.CENTER)
        self._empty.set_vexpand(True)

        self._stack = Gtk.Stack()
        self._stack.add_named(self._empty, "empty")
        self._stack.add_named(self._scroller, "pdf")
        self._stack.set_vexpand(True)
        self.append(self._stack)

        # Ctrl+scroll zooms, as in any viewer.
        wheel = Gtk.EventControllerScroll.new(
            Gtk.EventControllerScrollFlags.VERTICAL
        )
        wheel.connect("scroll", self._on_scroll)
        self._area.add_controller(wheel)

    # ----------------------------------------------------------- document

    def load(self, path: str | Path) -> bool:
        path = Path(path)
        if not path.exists():
            return False

        position = self._scroller.get_vadjustment().get_value()
        try:
            self._document = Poppler.Document.new_from_file(path.as_uri(), None)
        except Exception:
            return False

        self._path = path
        self._stack.set_visible_child_name("pdf")
        self._remeasure()
        # Rebuilding should not throw the reader back to the top.
        self._scroller.get_vadjustment().set_value(position)
        return True

    def reload(self) -> bool:
        return self.load(self._path) if self._path else False

    @property
    def pages(self) -> int:
        return self._document.get_n_pages() if self._document else 0

    # ---------------------------------------------------------------- zoom

    def apply_zoom(self, factor: float) -> None:
        self._fit_width = False
        self._zoom = max(0.2, min(6.0, self._zoom * factor))
        self._remeasure()

    def fit_width(self) -> None:
        self._fit_width = True
        self._remeasure()

    @property
    def zoom(self) -> float:
        return self._zoom

    def _on_scroll(self, controller, dx: float, dy: float) -> bool:
        state = controller.get_current_event_state()
        if state & Gdk.ModifierType.CONTROL_MASK:
            self.apply_zoom(0.9 if dy > 0 else 1.1)
            return True
        return False

    def _on_width_changed(self, *_args) -> None:
        if self._fit_width:
            self._remeasure()

    # ------------------------------------------------------------- drawing

    def _page_size(self, index: int) -> tuple[float, float]:
        return self._document.get_page(index).get_size()

    def _scale(self) -> float:
        if not self._document:
            return self._zoom
        if self._fit_width:
            available = self._scroller.get_width()
            if available > 1:
                width, _ = self._page_size(0)
                self._zoom = max(0.2, (available - 2 * PAGE_GAP) / width)
        return self._zoom

    def _remeasure(self) -> None:
        if not self._document:
            return
        scale = self._scale()
        width = 0.0
        height = float(PAGE_GAP)
        for i in range(self.pages):
            page_width, page_height = self._page_size(i)
            width = max(width, page_width * scale)
            height += page_height * scale + PAGE_GAP
        self._area.set_content_width(int(width + 2 * PAGE_GAP))
        self._area.set_content_height(int(height))
        self._area.queue_draw()

    def _draw(self, area: Gtk.DrawingArea, ctx, width: int, height: int) -> None:
        if not self._document:
            return

        scale = self._zoom
        adjustment = self._scroller.get_vadjustment()
        visible_top = adjustment.get_value()
        visible_bottom = visible_top + adjustment.get_page_size()

        y = float(PAGE_GAP)
        for i in range(self.pages):
            page_width, page_height = self._page_size(i)
            drawn_width = page_width * scale
            drawn_height = page_height * scale
            x = (width - drawn_width) / 2

            # Only rasterise what is (nearly) in view.
            if y + drawn_height >= visible_top - 200 and y <= visible_bottom + 200:
                ctx.save()
                # A hairline around the sheet, not a soft shadow: grey shadow
                # under everything is what makes an interface look like a pile
                # of cards.
                ctx.set_source_rgba(0, 0, 0, 0.28)
                ctx.rectangle(x - 1, y - 1, drawn_width + 2, drawn_height + 2)
                ctx.fill()
                # The paper is always white, even in the dark theme: it is what
                # the professor will see printed.
                ctx.set_source_rgb(1, 1, 1)
                ctx.rectangle(x, y, drawn_width, drawn_height)
                ctx.fill()
                ctx.translate(x, y)
                ctx.scale(scale, scale)
                self._document.get_page(i).render(ctx)
                ctx.restore()

            y += drawn_height + PAGE_GAP

    # ------------------------------------------------------------ navigation

    def go_to_page(self, number: int) -> None:
        if not self._document:
            return
        scale = self._zoom
        y = float(PAGE_GAP)
        for i in range(max(0, min(number, self.pages) - 1)):
            _, page_height = self._page_size(i)
            y += page_height * scale + PAGE_GAP
        self._scroller.get_vadjustment().set_value(y - PAGE_GAP)

    @property
    def current_page(self) -> int:
        if not self._document:
            return 0
        target = self._scroller.get_vadjustment().get_value()
        scale = self._zoom
        y = float(PAGE_GAP)
        for i in range(self.pages):
            _, page_height = self._page_size(i)
            y += page_height * scale + PAGE_GAP
            if y > target + 40:
                return i + 1
        return self.pages
