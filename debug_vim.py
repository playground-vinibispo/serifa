# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Vinícius Bispo e colaboradores

"""Bisecting vim mode: from the official recipe up to the whole of Serifa.

Every key that reaches the bubble phase is a key vim's context did NOT
filter. In normal mode, no printable key should ever get there.

Variants, in increasing order of "how much of Serifa is around it":

  minimal   GtkSourceView's official recipe, nothing more
  popup    the recipe + an inert capture controller ahead of vim, mimicking
           the one the completion popup used to have
  editor   the serifa.editor.Editor class, with vim turned on by its method
  window   the whole of Serifa, with the detector stuck to the real editor

Run them in order and stop at the first one that leaks: the layer that came
in there is the culprit.
"""

import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("GtkSource", "5")
gi.require_version("Gdk", "4.0")

from gi.repository import Gdk, Gtk, GtkSource

VARIANT = sys.argv[1] if len(sys.argv) > 1 else "minimal"
TEXT = "abcdef\nghijkl\nmnopqr\n"


def detector(view, report):
    """Sticks to the bubble phase and reports every key that escaped vim."""
    leaks = []

    def leaked(_c, keyval, _code, _state):
        name = Gdk.keyval_name(keyval) or "?"
        if name.startswith(("Shift", "Control", "Alt", "Super", "Meta", "ISO")):
            return False
        leaks.append(name)
        report(f"overwrite={view.get_overwrite()}   "
               f"VAZOU ({len(leaks)}): {' '.join(leaks[-12:])}")
        print(f"VAZOU: {name}", flush=True)
        return False

    bubble = Gtk.EventControllerKey()
    bubble.set_propagation_phase(Gtk.PropagationPhase.BUBBLE)
    bubble.connect("key-pressed", leaked)
    view.add_controller(bubble)


def build_full_window(app):
    """The 'window' variant: the real Serifa, with the detector attached."""
    import pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).parent))

    from serifa.window import Window

    window = Window(application=app)
    window.present()
    editor = window._editor
    window._vim_button.set_active(True)
    editor.grab_focus()
    detector(editor, lambda t: print(t, flush=True))

    # Logs every key at the exact point it reaches vim's controller, before
    # the filter. "consumida=True" means something in Serifa kept it and vim
    # never saw it.
    vim_controller = editor._vim_controller

    def peek(_c, keyval, _code, _state):
        name = Gdk.keyval_name(keyval) or "?"
        if name.startswith(("Shift", "Control", "Alt", "Super", "Meta", "ISO")):
            return False
        print(
            f"tecla {name:<12} "
            f"balão={'aberto' if window._popup.visible else 'fechado':<7} "
            f"seleção={bool(editor.buffer.get_selection_bounds())} "
            f"completacao_nativa="
            f"{editor.get_completion().get_property('view') is not None}",
            flush=True,
        )
        return False

    vim_controller.connect("key-pressed", peek)

    import os
    os.environ.setdefault("SERIFA_DEBUG", "1")   # turns on the [bloco] report
    print(f"variante=window  vim={editor.vim_active}  "
          f"overwrite={editor.get_overwrite()}", flush=True)
    print("Ponha o cursor dentro de {...} e tente: viw, depois ci{, depois vi{",
          flush=True)
    print("Cada tecla que o vim recebe aparece abaixo.", flush=True)


def build(app):
    if VARIANT == "window":
        return build_full_window(app)

    if VARIANT == "editor":
        sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
        from serifa.editor import Editor
        view = Editor()
        buffer = view.buffer
    else:
        view = GtkSource.View()
        buffer = view.get_buffer()
    buffer.set_text(TEXT)
    view.set_monospace(True)
    view.set_show_line_numbers(True)

    report = Gtk.Label(label="digite:  j  k  x  i")
    report.add_css_class("monospace")
    report.set_xalign(0.0)
    report.set_wrap(True)

    if VARIANT == "popup":
        # The controller Serifa's popup used to install, exactly as it was:
        # same phase, added BEFORE vim, always returning False.
        before = Gtk.EventControllerKey()
        before.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        before.connect("key-pressed", lambda *_: False)
        view.add_controller(before)

    if VARIANT == "editor":
        view.toggle_vim(True)   # Serifa's path, not the raw recipe
    else:
        vim = GtkSource.VimIMContext()
        keys = Gtk.EventControllerKey()
        keys.set_im_context(vim)
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        view.add_controller(keys)
        vim.set_client_widget(view)

    detector(view, report.set_label)

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    box.set_margin_start(12)
    box.set_margin_end(12)
    box.set_margin_top(12)
    box.set_margin_bottom(12)
    title = Gtk.Label()
    title.set_markup(
        f"<b>variante: {VARIANT}</b>  —  se o vim funciona, "
        "<tt>j</tt> e <tt>k</tt> andam e NÃO aparece VAZOU"
    )
    title.set_xalign(0.0)
    box.append(title)
    box.append(view)
    box.append(report)

    window = Gtk.ApplicationWindow(application=app, title=f"diagnóstico vim — {VARIANT}")
    window.set_default_size(560, 380)
    window.set_child(box)
    window.present()
    view.grab_focus()
    print(f"variante={VARIANT}  "
          f"overwrite após ligar o vim={view.get_overwrite()}", flush=True)


app = Gtk.Application(application_id=f"br.ufmg.vinibispo.DiagVim.{VARIANT}")
app.connect("activate", build)
sys.exit(app.run([]))
