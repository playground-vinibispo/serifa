# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Vinícius Bispo e colaboradores

"""Context-aware completion.

GtkSourceView cannot help here. A GtkSourceCompletionProvider of our own would
be the natural route, but the ``populate_async``/``populate_finish`` pair
cannot be implemented in PyGObject: GtkSourceView's C callback receives a
``result`` that is not the GTask and a corrupted ``user_data``, and the process
dies in ``gtk_source_completion_context_set_proposals_for_provider``. The
backtrace is in the README. It is not a usage error -- the binding has no way
to pass back the original ``user_data`` of a ``GAsyncReadyCallback`` coming
from a vfunc.

So the popup for these four cases is a widget of its own:

- ``\\cite{`` -> keys from the project's .bib files, with the title alongside;
- ``\\ref{``  -> the ``\\label``s of the open document;
- ``\\begin{``/``\\end{`` -> environments;
- ``\\input{``/``\\includegraphics{`` -> files in the folder.

General completion (commands, environments as snippets, words from the
document) is still GtkSourceView's native one. This one only shows up inside
the braces of those commands, where the native one would have nothing to offer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("GtkSource", "5")
gi.require_version("Gdk", "4.0")

from gi.repository import Gdk, GLib, Gtk

# What sits immediately left of the cursor decides the source. The captured
# group is what has already been typed inside the braces.
CITATION = re.compile(r"\\[A-Za-z]*cite[A-Za-z]*\*?(?:\[[^\]]*\])*\{([^}]*)$")
REFERENCE = re.compile(r"\\(?:page|eq|auto|name|c)?ref\*?\{([^}]*)$")
ENVIRONMENT = re.compile(r"\\(?:begin|end)\{([^}]*)$")
# Kept apart because they ask for different things: \input wants source,
# \includegraphics wants an image. Offering both together is noise.
INPUT = re.compile(r"\\(?:input|include|bibliography)(?:\[[^\]]*\])?\{([^}]*)$")
GRAPHIC = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]*)$")

BIB_KEY = re.compile(r"@\w+\s*\{\s*([^,\s]+)", re.MULTILINE)
BIB_FIELD = re.compile(
    r"(title|author)\s*=\s*[{\"](.+?)[}\"]\s*,", re.IGNORECASE | re.DOTALL
)
LABEL = re.compile(r"\\label\{([^}]+)\}")

ENVIRONMENTS = [
    "document", "abstract", "itemize", "enumerate", "description",
    "figure", "table", "tabular", "center", "flushleft", "flushright",
    "quote", "quotation", "verse", "verbatim", "equation", "equation*",
    "align", "align*", "gather", "gather*", "matrix", "pmatrix", "bmatrix",
    "cases", "array", "minipage", "thebibliography",
]

EXTENSIONS = {
    "input": {".tex", ".bib"},
    "graphic": {".png", ".jpg", ".jpeg", ".pdf", ".eps"},
}


@dataclass(frozen=True)
class Item:
    text: str          # what gets inserted
    detail: str = ""   # what shows dimmed alongside
    icon: str = ""


@dataclass(frozen=True)
class Context:
    kind: str          # "citation"|"reference"|"environment"|"input"|"graphic"|""
    prefix: str        # what has been typed inside the braces so far
    start: int         # offset where the prefix begins, for replacing it


def detect(text_to_the_left: str, cursor_offset: int) -> Context:
    """Decides the context from the text left of the cursor.

    A pure function on purpose: it is the piece that can be tested without
    opening a window.
    """
    for kind, pattern in (
        ("citation", CITATION),
        ("reference", REFERENCE),
        ("environment", ENVIRONMENT),
        ("graphic", GRAPHIC),   # before INPUT: \includegraphics matches both
        ("input", INPUT),
    ):
        match = pattern.search(text_to_the_left)
        if match is not None:
            prefix = match.group(1)
            # In a multiple citation (\cite{a,b}), only the part after the
            # last comma counts as the prefix.
            if kind == "citation" and "," in prefix:
                prefix = prefix.rsplit(",", 1)[1].lstrip()
            return Context(kind, prefix, cursor_offset - len(prefix))
    return Context("", "", cursor_offset)


class Library:
    """The data sources: .bib keys, labels and files in the folder."""

    def __init__(self) -> None:
        self._folder: Path | None = None
        self._citations: list[Item] = []
        self._files: dict[str, list[Item]] = {"input": [], "graphic": []}

    def set_folder(self, folder: Path | None) -> None:
        if folder == self._folder:
            return
        self._folder = folder
        self._citations = self._read_bibs(folder) if folder else []
        self._files = {
            kind: self._list_files(folder, kind) if folder else []
            for kind in EXTENSIONS
        }

    def items(self, context: Context, document_text: str) -> list[Item]:
        if context.kind == "citation":
            candidates = self._citations
        elif context.kind == "reference":
            candidates = [
                Item(r, "label", "mark-location-symbolic")
                for r in sorted(set(LABEL.findall(document_text)))
            ]
        elif context.kind == "environment":
            candidates = [
                Item(e, "ambiente", "view-list-symbolic") for e in ENVIRONMENTS
            ]
        elif context.kind in self._files:
            candidates = self._files[context.kind]
        else:
            return []

        wanted = context.prefix.lower()
        if not wanted:
            return candidates
        # Subsequence matching, as in a code editor: "eif" finds
        # "einstein_infeld".
        return [i for i in candidates if _is_subsequence(wanted, i.text.lower())]

    # ------------------------------------------------------------- reading

    @staticmethod
    def _read_bibs(folder: Path) -> list[Item]:
        items: list[Item] = []
        seen: set[str] = set()
        # The file's folder and up to three levels above: covers the
        # assignment/ -> referencias.bib at the repository root layout.
        for directory in [folder, *list(folder.parents)[:3]]:
            try:
                files = sorted(directory.glob("*.bib"))
            except OSError:
                continue
            for file in files:
                try:
                    raw = file.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                for entry in re.split(r"(?=@\w+\s*\{)", raw):
                    key = BIB_KEY.search(entry)
                    if not key or key.group(1) in seen:
                        continue
                    seen.add(key.group(1))
                    fields = {f.lower(): v for f, v in BIB_FIELD.findall(entry)}
                    summary = fields.get("title") or fields.get("author") or file.name
                    items.append(
                        Item(
                            key.group(1),
                            " ".join(summary.split())[:60],
                            "user-bookmarks-symbolic",
                        )
                    )
        return items

    @staticmethod
    def _list_files(folder: Path, kind: str) -> list[Item]:
        items: list[Item] = []
        accepted = EXTENSIONS[kind]
        for base in (folder, folder.parent, folder.parent.parent):
            try:
                entries = sorted(base.iterdir())
            except OSError:
                continue
            for entry in entries:
                if not entry.is_file() or entry.suffix.lower() not in accepted:
                    continue
                try:
                    name = str(entry.relative_to(folder))
                except ValueError:
                    # Climb with ../ while that stays reasonable.
                    hops = len(folder.relative_to(base).parts)
                    name = "../" * hops + entry.name
                # \input does not need the .tex extension.
                if entry.suffix == ".tex":
                    name = name[: -len(".tex")]
                if not any(i.text == name for i in items):
                    icon = ("image-x-generic-symbolic" if kind == "graphic"
                            else "text-x-generic-symbolic")
                    items.append(Item(name, entry.suffix.lstrip("."), icon))
        return items[:60]


def _is_subsequence(needle: str, haystack: str) -> bool:
    position = 0
    for character in needle:
        position = haystack.find(character, position) + 1
        if position == 0:
            return False
    return True


class Popup:
    """The completion bubble, anchored at the cursor.

    Navigation keys arrive through handle_key, called by the controller the
    window installs on itself in the capture phase. That is the only place
    they can be seen from with vim on; vim's own controller stays in CAPTURE
    the whole time the bubble is open -- turning it off was a wrong fix that
    killed normal mode.
    """

    def __init__(self, editor, library: Library) -> None:
        self._editor = editor
        self._library = library
        self._items: list[Item] = []
        self._context = Context("", "", 0)
        self._timer = 0
        self._suppress = False
        self._by_edit = False

        self._list = Gtk.ListBox()
        self._list.set_activate_on_single_click(True)
        self._list.connect(
            "row-activated", lambda _l, row: self._accept(row.get_index())
        )

        scroller = Gtk.ScrolledWindow()
        scroller.set_child(self._list)
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_max_content_height(260)
        scroller.set_propagate_natural_height(True)
        scroller.set_propagate_natural_width(True)

        self._bubble = Gtk.Popover()
        self._bubble.set_child(scroller)
        self._bubble.set_autohide(False)          # focus stays in the editor
        self._bubble.set_position(Gtk.PositionType.BOTTOM)
        self._bubble.set_has_arrow(False)
        self._bubble.set_parent(editor)

        editor.buffer.connect_after("changed", self._schedule_by_edit)
        editor.buffer.connect("notify::cursor-position", self._schedule_by_motion)

    # ------------------------------------------------------------- state

    @property
    def visible(self) -> bool:
        return self._bubble.get_visible()

    def reset(self) -> None:
        """Forgets whatever was pending. Called when switching files.

        Loading a file fires ``changed`` like any typing, and the 60 ms timer
        merges that load with the cursor move right behind it into a single
        evaluation -- which then rightly thinks it came "from an edit" and
        opens the bubble with nobody having typed a thing.
        """
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0
        self._by_edit = False
        self._suppress = False
        self.close()

    def _schedule_by_edit(self, *_args) -> None:
        self._by_edit = True
        self._schedule()

    def _schedule_by_motion(self, *_args) -> None:
        self._schedule()

    def _schedule(self) -> None:
        if self._timer:
            GLib.source_remove(self._timer)
        self._timer = GLib.timeout_add(60, self._reevaluate)

    def _reevaluate(self) -> bool:
        self._timer = 0
        # Consumed here at the top, before any early return. Consuming it
        # further down left the flag dangling whenever the evaluation bailed
        # out early -- on an empty context, say, which is the case right after
        # opening a file --, and the next motion inherited someone else's edit
        # and opened the bubble with nobody having typed anything.
        by_edit, self._by_edit = self._by_edit, False
        if self._suppress:
            # The insertion we just made fires a reevaluation of its own;
            # without this latch the popup would reopen over what the user
            # just picked.
            self._suppress = False
            return GLib.SOURCE_REMOVE
        buffer = self._editor.buffer
        cursor = buffer.get_iter_at_mark(buffer.get_insert())
        line_start = cursor.copy()
        line_start.set_line_offset(0)

        self._context = detect(line_start.get_text(cursor), cursor.get_offset())
        if not self._context.kind:
            self.close()
            return GLib.SOURCE_REMOVE

        self._items = self._library.items(self._context, self._editor.text)
        if not self._items:
            self.close()
            return GLib.SOURCE_REMOVE

        # Only opens on an edit. Moving the cursor across a \begin{...} that
        # is already written is not a request for completion -- and that was
        # what brought vim's normal mode down: the bubble opened on the way
        # past, silenced vim to get the arrow keys, and the next key fell
        # through to the TextView, which is in overwrite because of the block
        # cursor. The "l" for moving right became an "l" overwriting a letter.
        if not by_edit and not self._bubble.get_visible():
            return GLib.SOURCE_REMOVE

        self._fill()
        self._place(cursor)
        self._bubble.popup()
        # The native one and this one must not show up together.
        self._editor.get_completion().hide()
        return GLib.SOURCE_REMOVE

    def close(self) -> None:
        self._bubble.popdown()

    # ---------------------------------------------------------------- UI

    def _fill(self) -> None:
        while (row := self._list.get_first_child()) is not None:
            self._list.remove(row)

        for item in self._items[:40]:
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            box.set_margin_start(8)
            box.set_margin_end(8)
            box.set_margin_top(3)
            box.set_margin_bottom(3)
            if item.icon:
                box.append(Gtk.Image.new_from_icon_name(item.icon))
            name = Gtk.Label(label=item.text)
            name.add_css_class("monospace")
            name.set_xalign(0.0)
            box.append(name)
            if item.detail:
                detail = Gtk.Label(label=item.detail)
                detail.add_css_class("dim-label")
                detail.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
                detail.set_xalign(0.0)
                detail.set_hexpand(True)
                box.append(detail)
            row = Gtk.ListBoxRow()
            row.set_child(box)
            self._list.append(row)

        first = self._list.get_row_at_index(0)
        if first is not None:
            self._list.select_row(first)

    def _place(self, cursor) -> None:
        area = self._editor.get_iter_location(cursor)
        x, y = self._editor.buffer_to_window_coords(
            Gtk.TextWindowType.WIDGET, area.x, area.y + area.height
        )
        self._bubble.set_pointing_to(Gdk.Rectangle(x=x, y=y, width=1, height=1))

    # ------------------------------------------------------------ keyboard

    def handle_key(self, keyval: int, state) -> bool:
        """Bubble navigation. Called by the window's controller.

        It has to come from an ancestor: a controller on the editor itself, or
        a handler hung on vim's controller, would never see these keys with
        vim on -- the input context filters them before the signal goes out.
        """
        if not self.visible:
            return False

        selected = self._list.get_selected_row()
        index = selected.get_index() if selected else 0
        total = min(len(self._items), 40)

        if keyval in (Gdk.KEY_Down, Gdk.KEY_Tab):
            self._select((index + 1) % total)
            return True
        if keyval in (Gdk.KEY_Up, Gdk.KEY_ISO_Left_Tab):
            self._select((index - 1) % total)
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self._accept(index)
            return True
        if keyval == Gdk.KEY_Escape:
            self.close()
            return True
        return False

    def _select(self, index: int) -> None:
        row = self._list.get_row_at_index(index)
        if row is not None:
            self._list.select_row(row)
            row.grab_focus()
            self._editor.grab_focus()  # focus goes back: the editor is who types

    def _accept(self, index: int) -> None:
        if not (0 <= index < len(self._items)):
            return
        item = self._items[index]
        buffer = self._editor.buffer
        cursor = buffer.get_iter_at_mark(buffer.get_insert())
        start = buffer.get_iter_at_offset(self._context.start)

        self.close()
        self._suppress = True
        buffer.begin_user_action()
        buffer.delete(start, cursor)
        buffer.insert(start, item.text)
        buffer.end_user_action()

        # Skip the } that auto-pairing left ahead: that is where the cursor
        # would go anyway.
        after = buffer.get_iter_at_mark(buffer.get_insert())
        if not after.is_end() and after.get_char() == "}":
            after.forward_char()
            buffer.place_cursor(after)

        self._editor.grab_focus()
