# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Vinícius Bispo e colaboradores

r"""The open file: read it, save it, know whether it is dirty, watch the disk.

This used to be scattered across the window, mixed with widget assembly and
status-bar updates. It is a single concept, and it is where the defects that
cost the user text live -- saving without being asked, reloading over unsaved
work -- which is reason enough to live apart and have a name.

The document decides nothing about the interface. When the disk diverges from
what is on screen, it **reports** and lets the window resolve: reloading on its
own would erase somebody's work, and that call belongs to whoever is writing.
"""

from __future__ import annotations

from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gio, GObject, Gtk


class Document(GObject.Object):
    """Binds a text buffer to a file on disk."""

    __gsignals__ = {
        # Dirty state changed; the window refreshes the title and the button.
        "dirty-changed": (GObject.SignalFlags.RUN_FIRST, None, (bool,)),
        # Reloaded from disk, either on its own or on request.
        "reloaded": (GObject.SignalFlags.RUN_FIRST, None, ()),
        # The disk diverged and there is unsaved work: the window decides.
        "conflict": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "failed": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self, buffer: Gtk.TextBuffer) -> None:
        super().__init__()
        self._buffer = buffer
        self._path: Path | None = None
        self._dirty = False
        self._monitor: Gio.FileMonitor | None = None

    # ------------------------------------------------------------- state

    @property
    def path(self) -> Path | None:
        return self._path

    @property
    def name(self) -> str:
        return self._path.name if self._path else ""

    @property
    def dirty(self) -> bool:
        return self._dirty

    def mark_dirty(self) -> None:
        if not self._dirty:
            self._dirty = True
            self.emit("dirty-changed", True)

    def mark_clean(self) -> None:
        self._buffer.set_modified(False)
        if self._dirty:
            self._dirty = False
        self.emit("dirty-changed", False)

    @property
    def text(self) -> str:
        return self._buffer.get_text(*self._buffer.get_bounds(), True)

    # -------------------------------------------------------------- disk

    def open_file(self, path: Path) -> bool:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as error:
            self.emit("failed", f"Não deu para abrir: {error}")
            return False

        self._buffer.begin_irreversible_action()
        self._buffer.set_text(text)
        self._buffer.end_irreversible_action()
        self._buffer.place_cursor(self._buffer.get_start_iter())

        self._path = path
        self.mark_clean()
        self._watch(path)
        return True

    def save(self) -> bool:
        if self._path is None:
            return False
        try:
            self._path.write_text(self.text, encoding="utf-8")
        except OSError as error:
            self.emit("failed", f"Não deu para salvar: {error}")
            return False
        self.mark_clean()
        return True

    def set_path(self, path: Path) -> None:
        """Used by save-as, before the first write."""
        self._path = path
        self._watch(path)

    def reload(self) -> bool:
        """Re-read the file, keeping the cursor where it was."""
        if self._path is None:
            return False
        try:
            text = self._path.read_text(encoding="utf-8")
        except OSError as error:
            self.emit("failed", f"Não deu para recarregar: {error}")
            return False

        where = self._buffer.get_iter_at_mark(self._buffer.get_insert()).get_offset()
        self._buffer.begin_irreversible_action()
        self._buffer.set_text(text)
        self._buffer.end_irreversible_action()
        self._buffer.place_cursor(
            self._buffer.get_iter_at_offset(min(where, self._buffer.get_char_count()))
        )
        self.mark_clean()
        self.emit("reloaded")
        return True

    # ----------------------------------------------------------- watcher

    def _watch(self, path: Path) -> None:
        """Observe the file, so the editor does not race the disk."""
        if self._monitor is not None:
            self._monitor.cancel()
        self._monitor = Gio.File.new_for_path(str(path)).monitor_file(
            Gio.FileMonitorFlags.NONE, None
        )
        self._monitor.connect("changed", self._on_disk_change)

    def _on_disk_change(self, _monitor, _file, _other, event) -> None:
        if event not in (
            Gio.FileMonitorEvent.CHANGES_DONE_HINT,
            Gio.FileMonitorEvent.CREATED,
        ):
            return
        if self._path is None:
            return
        try:
            on_disk = self._path.read_text(encoding="utf-8")
        except OSError:
            return

        # Our own save trips the watcher. Comparing the contents is sturdier
        # than an "ignore the next event" flag, because the monitor emits more
        # than one per write.
        if on_disk == self.text:
            self.emit("dirty-changed", self._dirty)
            return

        if self._dirty:
            self.emit("conflict", self.name)
        else:
            self.reload()
