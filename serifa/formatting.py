# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Vinícius Bispo e colaboradores

r"""LaTeX wrappers: \textbf{...} and relatives.

A text operation, not a widget: it takes the buffer and the command. It lives
here because the format table is consulted in three places -- the header
buttons, the submenu and the accelerators -- and because the operation itself
is the part that can be tested without opening a window.

The user-facing labels stay in Portuguese: whoever writes with this editor
writes in Portuguese.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk

# (action, LaTeX command, header icon or None, menu label)
FORMATS: list[tuple[str, str, str | None, str]] = [
    ("bold", "textbf", "format-text-bold-symbolic", "Negrito"),
    ("italic", "textit", "format-text-italic-symbolic", "Itálico"),
    ("underline", "underline", "format-text-underline-symbolic", "Sublinhado"),
    ("monospace", "texttt", None, "Monoespaçado"),
    ("emphasis", "emph", None, "Ênfase"),
    ("quote", "enquote", None, "Entre aspas"),
    ("footnote", "footnote", None, "Nota de rodapé"),
]

# Only the two everybody expects get a shortcut; the rest stay in the menu, so
# as not to trample more vim keys than necessary.
SHORTCUTS = {"bold": "<Control>b", "italic": "<Control>i"}


def wrap(buffer: Gtk.TextBuffer, command: str) -> None:
    r"""Wrap the selection in \command{...}, or open the braces at the cursor."""
    opening, closing = f"\\{command}{{", "}"

    buffer.begin_user_action()
    # In PyGObject this returns (start, end) when there is a selection and ()
    # when there is none -- not a boolean first, as the C signature suggests.
    bounds = buffer.get_selection_bounds()
    if bounds:
        start, end = bounds
        selected = buffer.get_text(start, end, True)
        mark = buffer.create_mark(None, start, True)
        buffer.delete(start, end)
        where = buffer.get_iter_at_mark(mark)
        buffer.insert(where, f"{opening}{selected}{closing}")
        buffer.delete_mark(mark)
    else:
        cursor = buffer.get_iter_at_mark(buffer.get_insert())
        inside = cursor.get_offset() + len(opening)
        # Inserted in one go: the auto-pairs only react to a single character,
        # so the closing brace here does not become two.
        buffer.insert(cursor, opening + closing)
        buffer.place_cursor(buffer.get_iter_at_offset(inside))
    buffer.end_user_action()
