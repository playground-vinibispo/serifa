# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Vinícius Bispo e colaboradores

"""The editor itself.

A GtkSource.View set up for LaTeX. The less obvious parts:

- vim mode is GtkSourceVimIMContext, the same emulation GNOME Builder uses --
  written in C, not reimplemented in Python. Turning it on and off is just
  adding or removing an EventController;
- auto-pairing lives in the buffer's ``insert-text`` signal, not in a key
  controller. That is what lets it coexist with vim: in normal mode, typing
  ``{`` is a motion and inserts no text, so the signal simply never fires.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("GtkSource", "5")
gi.require_version("Gdk", "4.0")

from gi.repository import Gdk, GLib, GObject, Gtk, GtkSource

from .appearance import LEADING, character_width, margin_for
from .blocks import target

try:
    gi.require_version("Spelling", "1")
    from gi.repository import Spelling
except (ValueError, ImportError):  # pragma: no cover - depends on the system
    Spelling = None

CLOSERS = {"{": "}", "[": "]", "(": ")", "$": "$"}
# Typing the closer that is already under the cursor should step over it, not
# insert a second one. Without this, whoever types "\begin{align}" in full --
# which is the natural thing -- ends up with "}}".
SKIPPABLE = {"}", "]", ")", "$"}

# Keys that are not "a key" as far as a sequence goes: they arrive on their own
# in the middle of any combination. The one that matters is Shift, without
# which there is no "{" -- it shows up between the "i" and the "{" of a vi{.
MODIFIERS = {
    Gdk.KEY_Shift_L, Gdk.KEY_Shift_R, Gdk.KEY_Control_L, Gdk.KEY_Control_R,
    Gdk.KEY_Alt_L, Gdk.KEY_Alt_R, Gdk.KEY_Super_L, Gdk.KEY_Super_R,
    Gdk.KEY_Meta_L, Gdk.KEY_Meta_R, Gdk.KEY_Caps_Lock, Gdk.KEY_Shift_Lock,
    Gdk.KEY_Num_Lock, Gdk.KEY_Mode_switch,
    Gdk.KEY_ISO_Level3_Shift, Gdk.KEY_ISO_Level5_Shift,
}

# \begin{environment} followed by nothing but the rest of the line.
ENVIRONMENT_OPENING = re.compile(r"\\begin\{([A-Za-z@*]+)\}[^\n]*$")


class Editor(GtkSource.View):
    """The text area, with its buffer and editing behaviours."""

    __gtype_name__ = "SerifaEditor"

    __gsignals__ = {
        # Emitted when the cursor moves, for the status bar.
        "appearance-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "cursor-moved": (GObject.SignalFlags.RUN_FIRST, None, (int, int)),
    }

    def __init__(self) -> None:
        super().__init__()

        self.buffer = GtkSource.Buffer()
        self.set_buffer(self.buffer)
        schemes = GtkSource.StyleSchemeManager.get_default()
        schemes.append_search_path(str(Path(__file__).parent / "data" / "styles"))
        scheme = schemes.get_scheme("serifa")
        if scheme is not None:
            self.buffer.set_style_scheme(scheme)


        language = GtkSource.LanguageManager.get_default().get_language("latex")
        if language is not None:
            self.buffer.set_language(language)
        self.buffer.set_highlight_matching_brackets(True)

        # No line numbers, no 80-column ruler, no current-line highlight:
        # those are tools for code. See serifa/appearance.py.
        self.set_show_line_numbers(False)
        self.set_highlight_current_line(False)
        self.set_show_right_margin(False)
        self.set_auto_indent(True)
        self.set_indent_on_tab(True)
        self.set_insert_spaces_instead_of_tabs(True)
        self.set_tab_width(2)
        self.set_indent_width(2)
        self.set_smart_backspace(True)
        self.set_smart_home_end(GtkSource.SmartHomeEndType.BEFORE)
        self.set_wrap_mode(Gtk.WrapMode.WORD)
        self.set_top_margin(28)
        self.set_bottom_margin(240)  # lets the last line rise to mid-screen
        self.set_pixels_above_lines(LEADING // 2)
        self.set_pixels_below_lines(LEADING // 2)
        self.set_pixels_inside_wrap(LEADING // 2)
        self.add_css_class("serifa-editor")
        self._current_margin = -1
        self.font_size = 11.5
        self.measure = 74


        self._vim: GtkSource.VimIMContext | None = None
        self._vim_controller: Gtk.EventControllerKey | None = None
        self._focus_handler = 0
        self._sequence: list[str] = []   # keys since the last "v"
        self._length_at_v = 0
        self._auto_pairs = True
        self._inserting = False  # re-entrancy guard for insert-text

        # connect_after: in the "after" of insert-text the text is already in
        # and the iterator points right past it, so there is no need to defer
        # with idle_add. Deferring was the bug: if the buffer was swapped in
        # the meantime, the saved mark pointed into another document.
        self.buffer.connect("insert-text", self._before_insert)
        self.buffer.connect_after("insert-text", self._after_insert)
        self.buffer.connect("notify::cursor-position", self._on_cursor_moved)

        self._spelling_adapter = None
        self._setup_spelling()

    def do_size_allocate(self, width: int, height: int, baseline: int) -> None:
        """Centres the text column in the available width.

        GTK4 has no reallocation signal for widgets: "notify::width" does not
        exist and connecting to it does nothing. This vfunc is the way. The
        margin is only written when it changes, because touching a margin
        triggers a new allocation, and rewriting the same number on every pass
        is a loop.
        """
        if width > 0:
            margin = margin_for(width, character_width(self), self.measure)
            if margin != self._current_margin:
                self._current_margin = margin
                self.set_left_margin(margin)
                self.set_right_margin(margin)
        GtkSource.View.do_size_allocate(self, width, height, baseline)

    def adjust_writing(self, size_delta=0, measure_delta=0) -> None:
        self.remove_css_class(f"serifa-font-{round(self.font_size * 2)}")
        self.font_size = max(8, min(24, self.font_size + size_delta))
        self.measure = max(40, min(100, self.measure + measure_delta))
        self.add_css_class(f"serifa-font-{round(self.font_size * 2)}")
        self.queue_resize()
        self.emit("appearance-changed")

    # ------------------------------------------------------------------ vim

    @property
    def vim_active(self) -> bool:
        return self._vim is not None

    def toggle_vim(self, active: bool) -> GtkSource.VimIMContext | None:
        """Turns vim mode on or off. Returns the context when on."""
        if active and self._vim is None:
            vim = GtkSource.VimIMContext()
            controller = Gtk.EventControllerKey()
            controller.set_im_context(vim)
            # CAPTURE: vim has to see the key before GtkTextView does.
            controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
            self.add_controller(controller)
            vim.set_client_widget(self)

            # GtkEventControllerKey only tells the input context focus_in
            # when the widget GAINS focus after the controller exists.
            # Turning vim on with Ctrl+Alt+V does not move focus -- the editor
            # was already focused --, so without this nudge the context is
            # never activated and filters no key at all. And since vim has
            # already put the TextView in overwrite to draw normal mode's block
            # cursor, every key that leaks through does not insert: it
            # overwrites. That is the "replace mode" that shows up out of
            # nowhere.
            if self.has_focus():
                vim.focus_in()

            self._vim = vim
            self._vim_controller = controller
            self._focus_handler = self.connect(
                "notify::has-focus", self._on_focus_changed
            )
        elif not active and self._vim is not None:
            self._vim.focus_out()
            self.disconnect(self._focus_handler)
            self._focus_handler = 0
            self._sequence.clear()
            self.remove_controller(self._vim_controller)
            self._vim = None
            self._vim_controller = None
        return self._vim

    def _on_focus_changed(self, *_args) -> None:
        """Keeps the vim context in step with focus, both ways."""
        if self._vim is None:
            return
        if self.has_focus():
            self._vim.focus_in()
        else:
            self._vim.focus_out()

    # ------------------------------------------- text objects in visual mode

    def handle_key(self, keyval: int, state) -> bool:
        """Makes `vi{`, `va(`, `i"` and friends work in visual mode.

        GtkSourceView's visual mode has no text objects: the library ships
        gtk_source_vim_command_set_text_object and the insert variant, but the
        visual state only exposes clone, get_bounds, ignore_command, new and
        warp. Hence `ci{` works and `vi{` does not -- there the `i` is ignored
        and the `{` becomes the "previous paragraph" motion, which only moves
        the cursor.

        Here the sequence v -> i|a -> sign is recognised and the selection is
        made by hand. The `v` goes on to vim, which enters visual mode for
        real; the `i` and the sign are consumed, or vim would read them as
        motions.

        Called by the controller the window installs on itself, not by one
        connected to vim's controller. The difference is decisive:
        GtkEventControllerKey hands the key to the input context BEFORE
        emitting key-pressed, and if the context filters it -- which is what
        vim does with everything in normal mode -- the signal is never
        emitted. Only bare modifiers ever showed up there.
        """
        if self._vim is None:
            return False
        debugging = bool(os.environ.get("SERIFA_DEBUG"))

        if state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.ALT_MASK):
            self._sequence.clear()
            return False

        if keyval in MODIFIERS:
            # Does not clear the sequence: this is exactly what broke vi{.
            # "{" needs Shift, Shift arrives as a key of its own between the
            # "i" and the "{", and the sequence died there -- the "{" arrived
            # with the state machine already reset.
            return False

        code = Gdk.keyval_to_unicode(keyval)
        key = chr(code) if code else ""
        if debugging:
            print(
                f"[tecla] {key!r:5} keyval={keyval} sequência={self._sequence} "
                f"seleção={bool(self.buffer.get_selection_bounds())}",
                flush=True,
            )
        if not key:
            self._sequence.clear()
            return False

        if not self._sequence:
            # No requirement that nothing be selected: in normal mode vim may
            # keep a selection, and demanding there be none was what kept the
            # sequence from arming -- the "v" came and went without a trace.
            if key == "v":
                self._sequence.append("v")
                self._length_at_v = self.buffer.get_char_count()
            return False

        # If the text changed since the "v", we were in insert mode and that
        # "v" was just the letter v. Nothing to do here.
        if self.buffer.get_char_count() != self._length_at_v:
            if debugging:
                print("[tecla] texto mudou desde o v: era inserção, abortando",
                      flush=True)
            self._sequence.clear()
            return False

        if len(self._sequence) == 1:
            if key in ("i", "a"):
                self._sequence.append(key)
                return True   # vim has nothing to do with this in visual mode
            self._sequence.clear()
            return False

        inside = self._sequence[1] == "i"
        self._sequence.clear()
        found = self._select_block(key, inside)
        if debugging and not found:
            print(f"[tecla] nenhum bloco {key!r} em volta do cursor", flush=True)
        return found

    def _select_block(self, sign: str, inside: bool) -> bool:
        text = self.text
        cursor = self.buffer.get_iter_at_mark(self.buffer.get_insert())
        span = target(text, cursor.get_offset(), sign, inside)
        if span is None:
            return False

        start, end = span
        self._apply_selection(start, end)
        # Vim is in visual mode for real -- we let the "v" through -- and may
        # readjust the selection after us: vim's is inclusive of the character
        # under the cursor, GTK's is exclusive at the end. Rather than guess
        # the direction of the adjustment and be off by one either way, the
        # selection is measured in an idle and restored if it changed.
        GLib.idle_add(self._fix_selection, start, end, text)
        return True

    def _apply_selection(self, start: int, end: int) -> None:
        # Cursor at the end and anchor at the start, which is how vim leaves
        # visual mode.
        self.buffer.select_range(
            self.buffer.get_iter_at_offset(end),
            self.buffer.get_iter_at_offset(start),
        )

    def _fix_selection(self, start: int, end: int, text: str) -> bool:
        bounds = self.buffer.get_selection_bounds()
        current = (
            (bounds[0].get_offset(), bounds[1].get_offset()) if bounds else None
        )
        if current != (start, end):
            if os.environ.get("SERIFA_DEBUG"):
                print(
                    f"[bloco] queria ({start},{end})={text[start:end]!r}, "
                    f"o vim deixou {current}; repondo",
                    flush=True,
                )
            self._apply_selection(start, end)
        elif os.environ.get("SERIFA_DEBUG"):
            print(f"[bloco] ({start},{end})={text[start:end]!r} intacta", flush=True)
        return GLib.SOURCE_REMOVE

    # ------------------------------------------------ pairs and environments

    def _before_insert(
        self, buffer: GtkSource.Buffer, where: Gtk.TextIter, text: str, length: int
    ) -> None:
        """Steps over the closer instead of doubling it."""
        if self._inserting or not self._auto_pairs:
            return
        if text not in SKIPPABLE or where.is_end():
            return
        if where.get_char() != text:
            return
        buffer.stop_emission_by_name("insert-text")
        following = where.copy()
        following.forward_char()
        buffer.place_cursor(following)

    def _after_insert(
        self, buffer: GtkSource.Buffer, where: Gtk.TextIter, text: str, length: int
    ) -> None:
        if self._inserting or not self._auto_pairs:
            return
        if text in CLOSERS:
            self._close_pair(buffer, where, text)
        elif text == "\n":
            self._close_environment(buffer, where)

    def _close_pair(
        self, buffer: GtkSource.Buffer, where: Gtk.TextIter, opener: str
    ) -> None:
        # Does not double the $ when the next character already is a $: then
        # the user is closing inline math, not opening more.
        if opener == "$" and not where.is_end() and where.get_char() == "$":
            return

        between = where.get_offset()
        self._inserting = True
        buffer.insert(where, CLOSERS[opener])
        self._inserting = False
        buffer.place_cursor(buffer.get_iter_at_offset(between))

    def _close_environment(self, buffer: GtkSource.Buffer, where: Gtk.TextIter) -> None:
        if where.get_line() == 0:
            return
        start = buffer.get_iter_at_line(where.get_line() - 1)
        if isinstance(start, tuple):  # the signature changed between versions
            start = start[1]
        end = start.copy()
        if not end.ends_line():
            end.forward_to_line_end()
        line = start.get_text(end)

        match = ENVIRONMENT_OPENING.search(line)
        if match is None:
            return

        environment = match.group(1)
        indent = re.match(r"[ \t]*", line).group(0)
        inside = where.get_offset() + len(indent) + 2

        self._inserting = True
        buffer.insert(where, f"{indent}  \n{indent}\\end{{{environment}}}")
        self._inserting = False
        buffer.place_cursor(buffer.get_iter_at_offset(inside))

    # ------------------------------------------------------------- spelling

    def _setup_spelling(self) -> None:
        if Spelling is None:
            return
        provider = Spelling.Provider.get_default()
        languages = {language.get_code() for language in provider.list_languages()}
        # Preference: Brazilian Portuguese, European Portuguese, then generic.
        chosen = next(
            (c for c in ("pt_BR", "pt_PT", "pt") if c in languages), None
        )
        if chosen is None:
            # With no Portuguese dictionary installed, correcting in English a
            # text that is all Portuguese is worse than nothing: stay off.
            return
        checker = Spelling.Checker.new(provider, chosen)
        adapter = Spelling.TextBufferAdapter.new(self.buffer, checker)
        self.set_extra_menu(adapter.get_menu_model())
        self.insert_action_group("spelling", adapter)
        adapter.set_enabled(True)
        self._spelling_adapter = adapter

    @property
    def has_spellcheck(self) -> bool:
        return self._spelling_adapter is not None

    # ------------------------------------------------------------- utilities

    def _on_cursor_moved(self, *_args) -> None:
        where = self.buffer.get_iter_at_mark(self.buffer.get_insert())
        self.emit("cursor-moved", where.get_line() + 1, where.get_line_offset() + 1)

    def go_to_line(self, line: int) -> None:
        """Puts the cursor at the start of the line (1-based) and scrolls there."""
        line = max(0, line - 1)
        where = self.buffer.get_iter_at_line(line)
        if isinstance(where, tuple):  # the signature changed between versions
            where = where[1]
        self.buffer.place_cursor(where)
        self.scroll_to_iter(where, 0.25, True, 0.0, 0.35)
        self.grab_focus()

    @property
    def text(self) -> str:
        start, end = self.buffer.get_bounds()
        return self.buffer.get_text(start, end, True)

    def count_words(self) -> int:
        # Strip commands, math and comments before counting: what matters is
        # the prose, which is what the page limit charges for.
        text = re.sub(r"(?m)%.*$", "", self.text)
        text = re.sub(r"\$[^$]*\$", "", text)
        text = re.sub(r"\\[A-Za-z@]+\*?", " ", text)
        text = re.sub(r"[{}\[\]~\\]", " ", text)
        return len([w for w in text.split() if any(c.isalnum() for c in w)])
