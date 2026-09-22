"""Test scaffolding.

The finding that makes the suite workable: **there is no need to run
`app.run()`**. It is enough to register the application, build the window, call
`present()` and pump the main loop by hand. The window maps, the editor gets
focus, and the tests run in seconds instead of depending on timers inside a
loop that never hands control back.

Nothing here touches the user's files: every test gets a temporary folder.
"""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GtkSource", "5")
gi.require_version("Gdk", "4.0")

from gi.repository import Adw, Gdk, GLib, Gtk, GtkSource

ROOT = Path(__file__).resolve().parent.parent

_started = False


def start() -> bool:
    """Brings GTK up once. Returns False when no window can be opened."""
    global _started
    if not _started:
        if not Gtk.init_check():
            return False
        Adw.init()
        GtkSource.init()
        _started = True
    return True


def pump(milliseconds: int = 200) -> None:
    """Lets the main loop run without it taking over execution."""
    context = GLib.MainContext.default()
    deadline = time.monotonic() + milliseconds / 1000
    while time.monotonic() < deadline:
        while context.pending():
            context.iteration(False)
        time.sleep(0.003)


def until(condition, limit_ms: int = 4000, step_ms: int = 50) -> bool:
    """Pumps until the condition holds or time runs out. Returns whether it held."""
    spent = 0
    while spent < limit_ms:
        if condition():
            return True
        pump(step_ms)
        spent += step_ms
    return condition()


def key_for(character: str) -> tuple[int, Gdk.ModifierType]:
    """Turns a character into (keyval, state), the way the keyboard delivers it."""
    needs_shift = character in '{}()<>"?:_|~^ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    state = Gdk.ModifierType.SHIFT_MASK if needs_shift else Gdk.ModifierType(0)
    return Gdk.unicode_to_keyval(ord(character)), state


class GraphicalCase(unittest.TestCase):
    """Base for the tests that need a window.

    Each case gets its own temporary folder and its own window, and both go
    away at the end. Session state is redirected into the test's folder, or
    the tests would read and write the user's real session.
    """

    continuous = False   # continuous build off unless it is the target

    @classmethod
    def setUpClass(cls) -> None:
        if not start():
            raise unittest.SkipTest("sem servidor gráfico")
        cls._app = Adw.Application(
            application_id=f"br.ufmg.vinibispo.SerifaTeste.{cls.__name__}"
        )
        cls._app.register(None)

    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory(prefix="serifa-teste-")
        self.folder = Path(self._temporary.name)

        import serifa.window as window_module

        self._original_state = window_module.STATE
        window_module.STATE = self.folder / "state.json"

        from serifa.window import Window

        self.window = Window(application=self._app)
        self.window._continuous_build = self.continuous
        self.window.present()
        self.editor = self.window._editor
        self.buffer = self.editor.buffer
        pump(250)

    def tearDown(self) -> None:
        import serifa.window as window_module

        window_module.STATE = self._original_state
        self.window.destroy()
        pump(60)
        self._temporary.cleanup()

    # ------------------------------------------------------------ utilities

    def file_at(self, name: str, content: str) -> Path:
        path = self.folder / name
        path.write_text(content, encoding="utf-8")
        return path

    def type_text(self, text: str) -> None:
        """Inserts character by character, as the keyboard does.

        Inserting the whole string at once is not the same thing: auto-pairing
        only reacts to a lone character, and that is how an early test gave a
        false negative.
        """
        for character in text:
            self.buffer.insert_at_cursor(character)

    def send_keys(self, sequence: str) -> list[bool]:
        """Sends the sequence down the real path: the window's controller.

        Emits Shift before the keys that need it, because the keyboard does --
        and it was exactly that Shift in the middle that broke vi{.
        """
        consumed = []
        for character in sequence:
            keyval, state = key_for(character)
            if state & Gdk.ModifierType.SHIFT_MASK:
                self.window._on_key_pressed(None, Gdk.KEY_Shift_L, 0, Gdk.ModifierType(0))
            consumed.append(self.window._on_key_pressed(None, keyval, 0, state))
        return consumed

    def selection(self) -> str | None:
        bounds = self.buffer.get_selection_bounds()
        if not bounds:
            return None
        return self.buffer.get_text(bounds[0], bounds[1], True)

    @property
    def text(self) -> str:
        return self.buffer.get_text(*self.buffer.get_bounds(), True)
