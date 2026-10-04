# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Vinícius Bispo e colaboradores

r"""The window: outline, editor, preview, diagnostics and status bar."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("GtkSource", "5")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GLib, GObject, Gtk, GtkSource

from . import session
from .appearance import install_css
from .build import Builder, Diagnostic
from .complete import KeySource, prepare_snippets
from .context import Library, Popup
from .document import Document
from .editor import Editor
from .formatting import FORMATS, SHORTCUTS, wrap
from .preview import Preview

# What sits between the braces may break across lines and hold one level of
# nested braces (\section*{\normalsize 1 --- ...}), so no [^}]* here.
SECTION = re.compile(
    r"^[ \t]*\\(chapter|section|subsection|subsubsection|paragraph)\*?\s*"
    r"\{((?:[^{}]|\{[^{}]*\})*)\}",
    re.MULTILINE | re.DOTALL,
)
LEVEL = {"chapter": 0, "section": 0, "subsection": 1, "subsubsection": 2, "paragraph": 3}

STATE = session.DEFAULT


class Window(Adw.ApplicationWindow):
    __gtype_name__ = "SerifaWindow"

    def __init__(self, **kwargs) -> None:
        restore_session = kwargs.pop("restore_session", True)
        self._host = None
        super().__init__(**kwargs)

        self.set_title("Serifa")
        self.add_css_class("serifa-window")
        self.set_default_size(1500, 940)

        self._build_timer = 0
        self._outline_timer = 0
        self._continuous_build = True
        self._diagnostics: list[Diagnostic] = []

        self._builder = Builder()
        self._builder.connect("started", self._on_build_started)
        self._builder.connect("finished", self._on_build_finished)

        self._build_ui()
        self._install_actions()
        if restore_session:
            self._restore_state()
        self.connect("close-request", self._on_close_request)

        # In the capture phase GTK dispatches from the root down to the target,
        # so a controller here on the window runs before vim's controller,
        # which sits on the editor. It is the only place from which the keys
        # vim's input context would filter can be seen.
        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self._on_key_pressed)
        self.add_controller(keys)

    def _on_key_pressed(self, _controller, keyval: int, _keycode: int, state) -> bool:
        # is_focus, not has_focus: a key only gets here while the window is
        # active, so all that matters is whether the editor is its focus.
        # has_focus also demands an active window, which never holds in a
        # compositor with no keyboard (the tests).
        if not self._editor.is_focus():
            return False
        if self._popup.handle_key(keyval, state):
            return True
        return self._editor.handle_key(keyval, state)

    @property
    def _file(self) -> Path | None:
        return self._document.path

    @property
    def _dirty(self) -> bool:
        return self._document.dirty

    # ---------------------------------------------------------------- UI

    def _build_ui(self) -> None:
        install_css()
        self._editor = Editor()
        self.buffer = self._editor.buffer
        self._document = Document(self.buffer)
        self._document.connect("dirty-changed", self._on_dirty_changed)
        self._document.connect("reloaded", self._on_reloaded)
        self._document.connect("conflict", self._on_conflict)
        self._document.connect("failed", lambda _d, m: self._toast(m))
        self._editor.buffer.connect("changed", self._on_text_changed)
        self._editor.connect("cursor-moved", self._on_cursor_moved)

        # Commands and environments come from a .snippets generated in
        # serifa/complete.py.
        manager = GtkSource.SnippetManager.get_default()
        paths = list(manager.get_search_path() or [])
        snippets_folder = str(prepare_snippets())
        if snippets_folder not in paths:
            manager.set_search_path([snippets_folder, *paths])

        self._keys = KeySource()
        completion = self._editor.get_completion()
        completion.add_provider(GtkSource.CompletionSnippets.new())

        words = GtkSource.CompletionWords.new("Documento")
        words.register(self._editor.buffer)
        completion.add_provider(words)

        # .bib keys and \labels in a buffer of their own: that is how
        # CompletionWords gets to see words that are not in the open text.
        citations = GtkSource.CompletionWords.new("Citações e rótulos")
        citations.register(self._keys.buffer)
        completion.add_provider(citations)

        completion.set_property("select-on-show", True)

        # Inside \cite{, \ref{, \begin{ and \input{ a popup of our own answers
        # instead: see the header of serifa/context.py for why.
        self._library = Library()
        self._popup = Popup(self._editor, self._library)

        scroller = Gtk.ScrolledWindow()
        scroller.set_child(self._editor)
        scroller.set_vexpand(True)

        # --- search and replace
        self._search = GtkSource.SearchContext.new(self._editor.buffer, None)
        self._search.get_settings().set_wrap_around(True)
        self._search_entry = Gtk.SearchEntry()
        self._search_entry.set_placeholder_text("Buscar no texto")
        self._search_entry.connect("search-changed", self._on_search)
        self._search_entry.connect("activate", lambda *_: self._next_match())
        search_bar = Gtk.SearchBar()
        search_bar.set_child(self._search_entry)
        search_bar.connect_entry(self._search_entry)
        self._search_bar = search_bar

        # --- diagnostics
        self._diagnostics_list = Gtk.ListBox()
        self._diagnostics_list.add_css_class("boxed-list")
        self._diagnostics_list.connect("row-activated", self._on_diagnostic_activated)
        diagnostics_scroller = Gtk.ScrolledWindow()
        diagnostics_scroller.add_css_class("serifa-diagnostics")
        diagnostics_scroller.set_child(self._diagnostics_list)
        diagnostics_scroller.set_min_content_height(150)
        diagnostics_scroller.set_max_content_height(260)
        diagnostics_scroller.set_propagate_natural_height(True)
        self._diagnostics_panel = Gtk.Revealer()
        self._diagnostics_panel.set_child(diagnostics_scroller)
        self._diagnostics_panel.set_transition_type(
            Gtk.RevealerTransitionType.SLIDE_UP
        )

        editor_column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        editor_column.append(search_bar)
        editor_column.append(scroller)
        editor_column.append(self._diagnostics_panel)

        # --- outline
        self._outline = Gtk.ListBox()
        self._outline.add_css_class("navigation-sidebar")
        self._outline.connect("row-activated", self._on_outline_activated)
        outline_scroller = Gtk.ScrolledWindow()
        outline_scroller.set_child(self._outline)
        outline_scroller.set_vexpand(True)
        outline_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outline_box.add_css_class("serifa-outline")
        outline_header = Adw.HeaderBar()
        outline_header.set_show_end_title_buttons(False)
        outline_header.set_title_widget(Adw.WindowTitle(title="Sumário"))
        outline_box.append(outline_header)
        outline_box.append(outline_scroller)

        self._sidebar_split = Adw.OverlaySplitView()
        self._sidebar_split.set_sidebar(outline_box)
        self._sidebar_split.set_content(editor_column)
        self._sidebar_split.set_min_sidebar_width(220)
        self._sidebar_split.set_max_sidebar_width(260)
        self._sidebar_split.set_show_sidebar(True)

        # --- preview
        self._preview = Preview()
        self._split = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self._split.set_start_child(self._sidebar_split)
        self._split.set_end_child(self._preview)
        self._split.set_resize_start_child(True)
        self._split.set_resize_end_child(True)
        self._split.set_position(760)

        # --- header bar
        header = Adw.HeaderBar()
        self._header = header
        header.add_css_class("serifa-header")

        open_button = Gtk.Button(icon_name="document-open-symbolic")
        open_button.set_tooltip_text("Abrir (Ctrl+O)")
        open_button.connect("clicked", lambda *_: self.open_dialog())
        header.pack_start(open_button)

        # Text instead of an icon: current Adwaita's document-save-symbolic is
        # an arrow dropping into a tray, indistinguishable from "download".
        # And the button is only active when there is something to save, which
        # answers "have I saved?" at a glance.
        self._save_button = Gtk.Button(label="Salvar")
        self._save_button.set_tooltip_text("Salvar e compilar (Ctrl+S)")
        self._save_button.set_sensitive(False)
        self._save_button.connect("clicked", lambda *_: self.save())
        header.pack_start(self._save_button)

        outline_button = Gtk.ToggleButton(icon_name="view-list-symbolic")
        outline_button.set_tooltip_text("Sumário (F9)")
        outline_button.set_active(True)
        outline_button.connect(
            "toggled", lambda b: self._sidebar_split.set_show_sidebar(b.get_active())
        )
        header.pack_start(outline_button)

        formatting = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        formatting.add_css_class("linked")
        for name, _command, icon, label in self.FORMATS:
            if icon is None:
                continue
            format_button = Gtk.Button(icon_name=icon)
            hint = self.FORMATTING_SHORTCUTS.get(name, "")
            format_button.set_tooltip_text(
                f"{label} ({hint.replace('<Control>', 'Ctrl+')})" if hint else label
            )
            format_button.set_action_name(f"win.{name}")
            formatting.append(format_button)
        tools = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        tools.add_css_class("serifa-tools")
        pane_title = Gtk.Label(label="Texto", xalign=0)
        pane_title.add_css_class("serifa-pane-title")
        pane_title.set_hexpand(True)
        tools.append(pane_title)
        tools.append(formatting)
        editor_column.prepend(tools)

        self._title = Adw.WindowTitle(title="Serifa", subtitle="nenhum arquivo")
        header.set_title_widget(self._title)

        menu = Gio.Menu()
        file_section = Gio.Menu()
        file_section.append("Abrir…", "win.open")
        file_section.append("Salvar como…", "win.save-as")
        menu.append_section(None, file_section)
        view_section = Gio.Menu()
        view_section.append("Compilação contínua", "win.continuous")
        view_section.append("Preview", "win.preview")
        view_section.append("Conferir texto", "win.check")
        menu.append_section(None, view_section)
        format_section = Gio.Menu()
        for name, _command, _icon, label in self.FORMATS:
            format_section.append(label, f"win.{name}")
        menu.append_submenu("Formatar", format_section)
        zoom_section = Gio.Menu()
        zoom_section.append("Ampliar PDF", "win.zoom-in")
        zoom_section.append("Reduzir PDF", "win.zoom-out")
        zoom_section.append("Ajustar à largura", "win.zoom-fit")
        menu.append_section(None, zoom_section)
        writing = Gio.Menu()
        for label, action in (("Aumentar fonte", "font-larger"),
                              ("Diminuir fonte", "font-smaller"),
                              ("Estreitar texto", "column-narrower"),
                              ("Alargar texto", "column-wider"),
                              ("Alternar tema claro/escuro", "theme")):
            writing.append(label, f"win.{action}")
        menu.append_submenu("Aparência", writing)
        menu_button = Gtk.MenuButton(icon_name="open-menu-symbolic")
        menu_button.set_menu_model(menu)
        header.pack_end(menu_button)

        self._vim_button = Gtk.ToggleButton(label="Vim")
        self._vim_button.set_tooltip_text("Modo vim (Ctrl+Alt+V)")
        self._vim_button.add_css_class("flat")
        self._vim_button.connect("toggled", self._on_vim_toggled)
        header.pack_end(self._vim_button)

        self._build_button = Gtk.Button(label="Compilar")
        self._build_button.set_tooltip_text("Compilar (F5 ou Ctrl+Enter)")
        self._build_button.add_css_class("suggested-action")
        self._build_button.connect("clicked", lambda *_: self.build())
        header.pack_end(self._build_button)

        search_button = Gtk.ToggleButton(icon_name="edit-find-symbolic")
        search_button.set_tooltip_text("Buscar (Ctrl+F)")
        search_button.bind_property(
            "active", search_bar, "search-mode-enabled",
            GObject.BindingFlags.BIDIRECTIONAL,
        )
        header.pack_end(search_button)

        # --- status bar
        self._status_position = Gtk.Label(label="1:1")
        self._status_words = Gtk.Label(label="0 palavras")
        self._status_vim = Gtk.Label()
        self._status_vim.add_css_class("monospace")
        self._status_vim.set_xalign(0.0)
        self._status_command = Gtk.Label()
        self._status_command.add_css_class("monospace")
        self._status_command.set_hexpand(True)
        self._status_command.set_xalign(0.0)
        self._status_build = Gtk.Label(label="pronto")
        self._status_build.add_css_class("dim-label")

        status_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=18)
        status_bar.add_css_class("serifa-statusbar")
        status_bar.set_margin_start(12)
        status_bar.set_margin_end(12)
        status_bar.set_margin_top(4)
        status_bar.set_margin_bottom(4)
        for label in (self._status_position, self._status_words,
                      self._status_vim, self._status_command):
            label.add_css_class("dim-label")
            label.add_css_class("serifa-status")
            status_bar.append(label)
        status_bar.append(self._status_build)

        self._banner = Adw.Banner()
        self._banner.set_button_label("Recarregar")
        self._banner.connect("button-clicked", lambda *_: self._reload())
        self._banner.set_revealed(False)

        view = Adw.ToolbarView()
        view.add_top_bar(header)
        view.add_top_bar(self._banner)
        view.set_content(self._split)
        view.add_bottom_bar(status_bar)

        self._toasts = Adw.ToastOverlay()
        self._toasts.set_child(view)
        self.set_content(self._toasts)

    # ------------------------------------------------------------- actions

    def _install_actions(self) -> None:
        shortcuts = {
            "open": (self.open_dialog, "<Control>o"),
            "save": (self.save, "<Control>s"),
            "save-as": (self.save_as, "<Control><Shift>s"),
            # Ctrl+B moved from build to bold, which is where the whole world
            # expects to find it.
            "build": (self.build, "F5"),
            "build-enter": (self.build, "<Control>Return"),
            "search": (self._focus_search, "<Control>f"),
            "vim": (self._toggle_vim, "<Control><Alt>v"),
            "preview": (self._toggle_preview, "<Control><Shift>v"),
            "outline": (self._toggle_outline, "F9"),
            "zoom-in": (lambda: self._preview.apply_zoom(1.15), "<Control>plus"),
            "zoom-out": (lambda: self._preview.apply_zoom(0.87), "<Control>minus"),
            "zoom-fit": (self._preview.fit_width, "<Control>0"),
            "check": (self.check_text, "<Control><Shift>c"),
            "continuous": (self._toggle_continuous, None),
            "font-larger": (lambda: self._editor.adjust_writing(size_delta=0.5), None),
            "font-smaller": (lambda: self._editor.adjust_writing(size_delta=-0.5), None),
            "column-narrower": (
                lambda: self._editor.adjust_writing(measure_delta=-6), None
            ),
            "column-wider": (lambda: self._editor.adjust_writing(measure_delta=6), None),
            "theme": (self._toggle_theme, None),
        }
        for name, command, _icon, _label in self.FORMATS:
            shortcuts[name] = (lambda c=command: self.format_text(c), None)

        app = None
        for name, (function, accel) in shortcuts.items():
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda _a, _p, f=function: f())
            self.add_action(action)
            if accel:
                app = app or self.get_application()
                if app is not None:
                    app.set_accels_for_action(f"win.{name}", [accel])

        self._apply_formatting_shortcuts(enabled=True)

    # ------------------------------------------------------- file

    def open_dialog(self) -> None:
        dialog = Gtk.FileDialog()
        dialog.set_title("Abrir um .tex")
        latex = Gtk.FileFilter()
        latex.set_name("LaTeX")
        latex.add_pattern("*.tex")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(latex)
        dialog.set_filters(filters)
        if self._file:
            dialog.set_initial_folder(Gio.File.new_for_path(str(self._file.parent)))
        dialog.open(self._host or self, None, self._on_file_chosen)

    def _on_file_chosen(self, dialog, result) -> None:
        try:
            file = dialog.open_finish(result)
        except GLib.Error:
            return
        if file is None:
            return
        path = Path(file.get_path())
        app = self.get_application()
        if hasattr(app, "open_document"):
            app.open_document(path)
        elif not self._settle_pending(lambda: self.open_file(path)):
            self.open_file(path)

    def open_file(self, path: Path) -> None:
        if not self._document.open_file(path):
            return

        text = self._document.text
        self._popup.reset()
        self._keys.set_folder(path.parent)
        self._library.set_folder(path.parent)
        self._keys.update(text)
        self._update_title()
        self._rebuild_outline()
        self._update_word_count()

        pdf = Builder._pdf_for(path, path.parent)
        if pdf.exists():
            self._preview.load(pdf)
        if self._continuous_build:
            self.preview_build()
        # Gtk.FileDialog is modal and takes focus away; without handing it
        # back here, the next keys may never reach vim's context.
        self._editor.grab_focus()
        self._save_state()

    def save(self) -> bool:
        if self._file is None:
            self.save_as()
            return False
        if not self._write():
            return False
        self._builder.build(self._file)
        return True

    def save_as(self) -> None:
        dialog = Gtk.FileDialog()
        dialog.set_title("Salvar como")
        if self._file:
            dialog.set_initial_name(self._file.name)
        dialog.save(self._host or self, None, self._on_destination_chosen)

    def _on_destination_chosen(self, dialog, result) -> None:
        try:
            file = dialog.save_finish(result)
        except GLib.Error:
            return
        if file is not None:
            self._document.set_path(Path(file.get_path()))
            self._keys.set_folder(self._file.parent)
            self._library.set_folder(self._file.parent)
            self.save()

    # ------------------------------------------ file changed from outside

    def _on_conflict(self, _document, name: str) -> None:
        """The disk diverged and there is unsaved work. The user decides."""
        self._banner.set_title(f"{name} mudou no disco, e há alterações não salvas aqui")
        self._banner.set_revealed(True)

    def _on_reloaded(self, _document) -> None:
        self._banner.set_revealed(False)
        self._editor.scroll_to_mark(self.buffer.get_insert(), 0.25, True, 0.0, 0.35)
        self._rebuild_outline()
        self._toast(f"{self._document.name} recarregado do disco")

    def _on_dirty_changed(self, _document, dirty: bool) -> None:
        if not dirty:
            self._banner.set_revealed(False)
        self._update_title()

    def _reload(self) -> None:
        self._document.reload()

    # ----------------------------------------------------- building

    def build(self) -> None:
        """Ctrl+B: saves and builds the real file.

        Saving here is the user's decision, not a side effect -- asking to
        build is asking to make real what is on screen.
        """
        if self._file is None:
            self._toast("Salve o arquivo antes de compilar")
            return
        if self._dirty and not self._write():
            return
        self._builder.build(self._file)

    def preview_build(self) -> None:
        """The continuous one: builds the buffer without touching the user's file."""
        if self._file is None:
            return
        self._builder.build_preview(self._editor.text, self._file)

    def _write(self) -> bool:
        return self._document.save()

    def _on_build_started(self, _builder, preview: bool) -> None:
        self._status_build.set_label("prévia…" if preview else "compilando…")
        self._build_button.set_sensitive(False)
        self._build_button.set_label("Compilando…")

    def _on_build_finished(
        self, _builder, success: bool, pdf: str, diagnostics, preview: bool
    ) -> None:
        self._build_button.set_sensitive(True)
        self._build_button.set_label("Compilar")
        self._diagnostics = list(diagnostics)

        if pdf:
            self._preview.load(pdf)

        errors = sum(1 for d in self._diagnostics if d.severity == "error")
        warnings = len(self._diagnostics) - errors
        if success:
            pages = self._preview.pages
            plural = "s" if pages != 1 else ""
            summary = f"{'prévia' if preview else 'ok'} · {pages} página{plural}"
            if warnings:
                summary += f" · {warnings} aviso{'s' if warnings != 1 else ''}"
            self._status_build.set_label(summary)
        else:
            self._status_build.set_label(
                f"{errors} erro{'s' if errors != 1 else ''}" if errors else "falhou"
            )

        self._fill_diagnostics()

    def _fill_diagnostics(self) -> None:
        while (row := self._diagnostics_list.get_first_child()) is not None:
            self._diagnostics_list.remove(row)

        for diagnostic in self._diagnostics[:60]:
            row = Adw.ActionRow(title=GLib.markup_escape_text(diagnostic.summary))
            row.add_prefix(Gtk.Image.new_from_icon_name(diagnostic.icon))
            row.diagnostic = diagnostic
            if diagnostic.line:
                row.set_activatable(True)
            self._diagnostics_list.append(row)

        self._diagnostics_panel.set_reveal_child(bool(self._diagnostics))

    def _on_diagnostic_activated(self, _list, row) -> None:
        diagnostic = getattr(row, "diagnostic", None)
        if diagnostic and diagnostic.line:
            self._editor.go_to_line(diagnostic.line)

    # ------------------------------------------------------------ formatting

    FORMATS = FORMATS
    FORMATTING_SHORTCUTS = SHORTCUTS

    def format_text(self, command: str) -> None:
        wrap(self._editor.buffer, command)
        self._editor.grab_focus()

    # -------------------------------------------------------- text checker

    def check_text(self) -> None:
        """Runs the project's scripts/conferir-texto.py, when there is one."""
        if self._file is None:
            return
        folder = self._file.parent
        script = None
        for candidate in [folder, *folder.parents]:
            possible = candidate / "scripts" / "conferir-texto.py"
            if possible.is_file():
                script = possible
                break
        if script is None:
            self._toast("Este projeto não tem scripts/conferir-texto.py")
            return

        try:
            output = subprocess.run(
                ["/usr/bin/python3.12", str(script), str(folder)],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(script.parent.parent),
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            self._toast(f"O conferidor falhou: {error}")
            return

        # The checker's output is Portuguese: "ERRO" and "aviso" are its words.
        self._diagnostics = [
            Diagnostic("error" if "ERRO" in line else "warning", line.strip())
            for line in output.stdout.splitlines()
            if line.strip() and ("ERRO" in line or "aviso" in line)
        ] or [Diagnostic("warning", "conferidor: nada a resolver")]
        self._fill_diagnostics()

    # ------------------------------------------------------------ outline

    def _rebuild_outline(self) -> None:
        while (row := self._outline.get_first_child()) is not None:
            self._outline.remove(row)

        text = self._editor.text
        for match in SECTION.finditer(text):
            command, title = match.group(1), match.group(2)
            number = text.count("\n", 0, match.start()) + 1
            clean = re.sub(r"\\[A-Za-z]+\*?|[{}]", "", title)
            label = Gtk.Label(label=" ".join(clean.split()))
            label.set_xalign(0.0)
            label.set_wrap(True)
            label.set_max_width_chars(24)
            label.set_tooltip_text(" ".join(clean.split()))
            label.set_margin_start(8 + 14 * LEVEL.get(command, 0))
            label.set_margin_end(8)
            label.set_margin_top(4)
            label.set_margin_bottom(4)
            if LEVEL.get(command, 0) == 0:
                label.add_css_class("heading")
            row = Gtk.ListBoxRow()
            row.set_child(label)
            row.line_number = number
            self._outline.append(row)

        cursor = self.buffer.get_iter_at_mark(self.buffer.get_insert())
        self._select_section(cursor.get_line() + 1)

    def _select_section(self, line: int) -> None:
        selected = None
        row = self._outline.get_first_child()
        while row is not None:
            if row.line_number <= line:
                selected = row
            row = row.get_next_sibling()
        self._outline.select_row(selected)

    def _on_outline_activated(self, _list, row) -> None:
        number = getattr(row, "line_number", None)
        if number:
            self._editor.go_to_line(number)

    # ------------------------------------------------------------- search

    def _focus_search(self) -> None:
        self._search_bar.set_search_mode(True)
        self._search_entry.grab_focus()

    def _on_search(self, entry) -> None:
        self._search.get_settings().set_search_text(entry.get_text() or None)

    def _next_match(self) -> None:
        cursor = self._editor.buffer.get_iter_at_mark(self._editor.buffer.get_insert())
        cursor.forward_char()
        found, start, end, _ = self._search.forward(cursor)
        if found:
            self._editor.buffer.select_range(start, end)
            self._editor.scroll_to_iter(start, 0.25, True, 0.0, 0.35)

    # ------------------------------------------------------------- status

    def _on_text_changed(self, _buffer) -> None:
        self._document.mark_dirty()

        if self._outline_timer:
            GLib.source_remove(self._outline_timer)
        self._outline_timer = GLib.timeout_add(
            600, self._outline_task
        )

        if self._continuous_build and self._file is not None:
            if self._build_timer:
                GLib.source_remove(self._build_timer)
            self._build_timer = GLib.timeout_add(
                1400, self._build_task
            )

    def _outline_task(self) -> bool:
        self._outline_timer = 0
        self._rebuild_outline()
        self._update_word_count()
        self._keys.update(self._editor.text)
        return GLib.SOURCE_REMOVE

    def _build_task(self) -> bool:
        self._build_timer = 0
        self.preview_build()
        return GLib.SOURCE_REMOVE

    def _on_cursor_moved(self, _editor, line: int, column: int) -> None:
        self._status_position.set_label(f"{line}:{column}")
        self._select_section(line)

    def _update_word_count(self) -> None:
        total = self._editor.count_words()
        self._status_words.set_label(f"{total} palavras")

    def _update_title(self) -> None:
        self._save_button.set_sensitive(self._dirty and self._file is not None)
        if self._file is None:
            self._title.set_title("Serifa")
            self._title.set_subtitle("nenhum arquivo")
            self._title.set_tooltip_text(None)
            return
        mark = " •" if self._dirty else ""
        self._title.set_title(f"{self._file.name}{mark}")
        self._title.set_subtitle("")
        self._title.set_tooltip_text(str(self._file))
        if self._host is not None:
            self._host._title(self._tab_page)

    # ------------------------------------------------------------- toggles

    def _toggle_theme(self) -> None:
        dark = not self.has_css_class("serifa-dark")
        if dark:
            self.add_css_class("serifa-dark")
        else:
            self.remove_css_class("serifa-dark")
        scheme = GtkSource.StyleSchemeManager.get_default().get_scheme(
            "serifa-dark" if dark else "serifa"
        )
        self.buffer.set_style_scheme(scheme)
        if self._host is not None:
            content = self._tab_page.get_child()
            if dark:
                content.add_css_class("serifa-dark")
            else:
                content.remove_css_class("serifa-dark")
            self._host.sync_appearance(self)

    def _on_vim_toggled(self, button: Gtk.ToggleButton) -> None:
        vim = self._editor.toggle_vim(button.get_active())
        if vim is not None:
            # VimIMContext exposes the current mode nowhere: all it has is
            # command-bar-text (which carries "-- INSERT --", ":w", "/search")
            # and command-text (the command being typed, like "2d"). Showing
            # both raw is as close to a mode indicator as it gets -- and it
            # beats the fixed "-- modo vim --" that used to be here, which did
            # not say whether you were in normal or insert.
            vim.bind_property("command-bar-text", self._status_vim, "label")
            vim.bind_property("command-text", self._status_command, "label")
            self._status_vim.set_label("")
            self._apply_formatting_shortcuts(enabled=False)
            button.add_css_class("accent")
        else:
            self._status_vim.set_label("")
            self._status_command.set_label("")
            self._apply_formatting_shortcuts(enabled=True)
            button.remove_css_class("accent")
        self._editor.grab_focus()
        self._save_state()

    def _toggle_vim(self) -> None:
        self._vim_button.set_active(not self._vim_button.get_active())

    def _toggle_preview(self) -> None:
        visible = self._preview.get_visible()
        self._preview.set_visible(not visible)

    def _toggle_outline(self) -> None:
        self._sidebar_split.set_show_sidebar(
            not self._sidebar_split.get_show_sidebar()
        )

    def _toggle_continuous(self) -> None:
        self._continuous_build = not self._continuous_build
        self._toast(
            "Compilação contínua ligada"
            if self._continuous_build
            else "Compilação contínua desligada"
        )
        self._save_state()

    def _toast(self, message: str) -> None:
        # Not "_notify": GObject already has notify(), and shadowing it breaks
        # property notification in ways that are hard to trace.
        self._toasts.add_toast(Adw.Toast(title=message, timeout=3))

    def _apply_formatting_shortcuts(self, enabled: bool) -> None:
        """With vim on, Ctrl+B and Ctrl+I go back to being vim's.

        A window accelerator is resolved before the widget's controllers, so
        it would beat vim without so much as a warning. Vim users expect
        Ctrl+B to mean page up; the toolbar buttons keep working either way.
        """
        app = self.get_application()
        if app is None:
            return
        for name, accel in self.FORMATTING_SHORTCUTS.items():
            app.set_accels_for_action(f"win.{name}", [accel] if enabled else [])

    # ------------------------------------------------------------ closing

    def _settle_pending(self, proceed, on_cancel=None) -> bool:
        """Asks before throwing away unsaved changes.

        Returns True when the action was deferred until the answer, and False
        when there was nothing to settle -- in which case the caller goes
        ahead.

        Serves both closing and switching files. Closing already asked;
        opening another file replaced the buffer silently, which is data loss,
        not a nuisance.
        """
        if not self._dirty or self._file is None:
            return False

        dialog = Adw.AlertDialog(
            heading="Salvar antes de continuar?",
            body=f"As alterações em {self._file.name} não foram gravadas.",
        )
        dialog.add_response("cancel", "Cancelar")
        dialog.add_response("discard", "Descartar")
        dialog.add_response("save", "Salvar")
        dialog.set_response_appearance("discard", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("save")
        dialog.set_close_response("cancel")
        dialog.choose(
            self._host or self, None,
            lambda d, r: self._on_response(d, r, proceed, on_cancel)
        )
        return True

    def _on_response(self, dialog, result, proceed, on_cancel=None) -> None:
        try:
            response = dialog.choose_finish(result)
        except GLib.Error:
            if on_cancel:
                on_cancel()
            return
        if response == "cancel" and on_cancel:
            on_cancel()
        self._apply_response(response, proceed)
        if response == "save" and self._dirty and on_cancel:
            on_cancel()

    def _apply_response(self, response: str, proceed) -> None:
        """The decision itself, kept apart from the dialog so it can be tested."""
        if response == "cancel":
            return
        if response == "save" and not self._write():
            return
        self._document.mark_clean()   # the next close-request goes straight through
        proceed()

    def _on_close_request(self, *_args) -> bool:
        return self._settle_pending(self.close)

    # -------------------------------------------------------- persistence

    def _save_state(self) -> None:
        session.write(STATE, {
            "file": str(self._file) if self._file else None,
            "vim": self._vim_button.get_active(),
            "continuous": self._continuous_build,
            "split": self._split.get_position(),
            "dark": self.has_css_class("serifa-dark"),
            "font_size": self._editor.font_size,
            "measure": self._editor.measure,
        })

    def _restore_state(self) -> None:
        data = session.read(STATE)
        if not data:
            return
        self._editor.adjust_writing(
            size_delta=data.get("font_size", 11.5) - 11.5,
            measure_delta=data.get("measure", 74) - 74,
        )
        if data.get("dark"):
            self._toggle_theme()
        if data.get("vim"):
            self._vim_button.set_active(True)
        self._continuous_build = data.get("continuous", True)
        if position := data.get("split"):
            self._split.set_position(position)
        if (path := data.get("file")) and Path(path).exists():
            # Only restores if nothing was opened in the meantime: the command
            # line (do_open) arrives before this idle, and without the guard
            # the previous session overwrote the file that was asked for.
            def restore() -> bool:
                if self._file is None:
                    self.open_file(Path(path))
                return GLib.SOURCE_REMOVE

            GLib.idle_add(restore)
