"""Check the system bindings without opening a window or requiring a display."""

import importlib
import sys


def check() -> None:
    if sys.version_info < (3, 12):  # noqa: UP036 — checks candidate interpreters
        raise RuntimeError("Python 3.12 ou superior é necessário")
    gi = importlib.import_module("gi")
    for namespace, version in (("Gtk", "4.0"), ("Adw", "1"),
                               ("GtkSource", "5"), ("Poppler", "0.18")):
        gi.require_version(namespace, version)
        importlib.import_module(f"gi.repository.{namespace}")
    importlib.import_module("cairo")
    gi.require_foreign("cairo")
    gtk = importlib.import_module("gi.repository.Gtk")
    adw = importlib.import_module("gi.repository.Adw")
    if not hasattr(gtk, "FileDialog"):
        raise RuntimeError("GTK 4.10 ou superior é necessário (Gtk.FileDialog)")
    if not hasattr(adw, "AlertDialog"):
        raise RuntimeError("libadwaita 1.5 ou superior é necessária (Adw.AlertDialog)")


if __name__ == "__main__":
    try:
        check()
    except (ImportError, ValueError, RuntimeError) as error:
        print(f"{sys.executable}: {error}", file=sys.stderr)
        sys.exit(1)
