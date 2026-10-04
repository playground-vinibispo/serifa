# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Vinícius Bispo e colaboradores

"""One application window with independently editable document tabs."""
from pathlib import Path

from gi.repository import Adw, Gdk, Gio, Gtk

from . import session
from . import window as window_module
from .window import Window


class Workspace(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_title("Serifa")
        self.set_default_size(1500, 940)
        self.add_css_class("serifa-window")
        self._documents = []
        self._syncing_appearance = False
        self._appearance = session.read(window_module.STATE) or {}
        self.tabs = Adw.TabView()
        self.tabs.connect("notify::selected-page", self._selected)
        self.tabs.connect("close-page", self._close_page)
        bar = Adw.TabBar(view=self.tabs)
        bar.set_autohide(False)
        open_button = Gtk.Button(icon_name="document-open-symbolic")
        open_button.set_tooltip_text("Abrir documento em uma aba")
        open_button.connect("clicked", self._open_dialog)
        controls = Gtk.Box(spacing=6)
        controls.append(open_button)
        controls.append(Gtk.WindowControls(side=Gtk.PackType.END))
        bar.set_end_action_widget(controls)
        column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        column.append(bar)
        column.append(self.tabs)
        self.tabs.set_vexpand(True)
        self.set_content(column)
        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self._key)
        self.add_controller(keys)
        self.connect("close-request", self._close_workspace)

    @property
    def active_document(self):
        page = self.tabs.get_selected_page()
        return getattr(page, "document", None) if page else None

    def open_document(self, path: Path):
        path = path.resolve()
        for i in range(self.tabs.get_n_pages()):
            page = self.tabs.get_nth_page(i)
            if page.document._file == path:
                self.tabs.set_selected_page(page)
                return page.document
        for document in self._documents:
            if document._file is None and not document._dirty:
                document.open_file(path)
                self.tabs.set_selected_page(document._tab_page)
                self._title(document._tab_page)
                return document
        return self._new_document(path)

    def _new_document(self, path=None):
        document = Window(
            application=self.get_application(), restore_session=path is None
        )
        self._documents.append(document)
        document._host = self
        document._tab_actions = Gio.SimpleActionGroup()
        for name in document.list_actions():
            document._tab_actions.add_action(document.lookup_action(name))
        document._header.set_show_start_title_buttons(False)
        document._header.set_show_end_title_buttons(False)
        content = document.get_content()
        document.set_content(None)
        content.add_css_class("serifa-window")
        page = self.tabs.append(content)
        page.document = document
        document._tab_page = page
        document._document.connect("dirty-changed", lambda *_: self._title(page))
        if path is not None:
            document.open_file(path)
        self._apply_appearance(document)
        document._editor.connect(
            "appearance-changed", lambda *_: self.sync_appearance(document)
        )
        self._title(page)
        self.tabs.set_selected_page(page)
        self._selected()
        return document

    def _apply_appearance(self, document):
        previous = self._syncing_appearance
        self._syncing_appearance = True
        try:
            dark = self._appearance.get("dark", False)
            if document.has_css_class("serifa-dark") != dark:
                document._toggle_theme()
            content = document._tab_page.get_child()
            for widget in (self, content):
                if dark:
                    widget.add_css_class("serifa-dark")
                else:
                    widget.remove_css_class("serifa-dark")
            editor = document._editor
            size = self._appearance.get("font_size", 11.5)
            measure = self._appearance.get("measure", 74)
            if (size, measure) != (editor.font_size, editor.measure):
                editor.adjust_writing(size - editor.font_size, measure - editor.measure)
        finally:
            self._syncing_appearance = previous

    def sync_appearance(self, source):
        if self._syncing_appearance:
            return
        self._appearance = {
            "dark": source.has_css_class("serifa-dark"),
            "font_size": source._editor.font_size,
            "measure": source._editor.measure,
        }
        for document in self._documents:
            self._apply_appearance(document)
        source._save_state()

    def _open_dialog(self, *_args):
        document = self.active_document or self._new_document()
        document.open_dialog()

    def _title(self, page):
        document = page.document
        page.set_title((document._file.name if document._file else "Sem título")
                       + (" •" if document._dirty else ""))
        page.set_tooltip(str(document._file or ""))

    def _selected(self, *_args):
        document = self.active_document
        self.insert_action_group("win", None)
        if document:
            self.insert_action_group("win", document._tab_actions)
            self.set_title(document._title.get_title() + " — Serifa")
            document._apply_formatting_shortcuts(not document._editor.vim_active)
            document._editor.grab_focus()

    def _key(self, controller, keyval, keycode, state):
        control = state & Gdk.ModifierType.CONTROL_MASK
        if control and keyval == Gdk.KEY_w:
            page = self.tabs.get_selected_page()
            if page:
                self.tabs.close_page(page)
            return True
        if control and keyval in (Gdk.KEY_Page_Down, Gdk.KEY_Page_Up):
            if keyval == Gdk.KEY_Page_Down:
                self.tabs.select_next_page()
            else:
                self.tabs.select_previous_page()
            return True
        document = self.active_document
        return bool(document and document._on_key_pressed(
            controller, keyval, keycode, state
        ))

    def _close_page(self, _tabs, page):
        def finish():
            document = page.document
            self.tabs.close_page_finish(page, True)
            document.destroy()
            self._documents.remove(document)
        if not page.document._settle_pending(
            finish, on_cancel=lambda: self.tabs.close_page_finish(page, False)
        ):
            finish()
        return True

    def _close_workspace(self, *_args):
        while self.tabs.get_n_pages():
            page = self.tabs.get_selected_page()
            def proceed(p=page):
                self.tabs.close_page(p)
                self.close()
            if page.document._settle_pending(proceed):
                return True
            self.tabs.close_page(page)
        return False

