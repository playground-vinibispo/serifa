r"""Typography and the width of the text column.

**Colours are not set here.** There was an attempt to impose a paper palette,
with LaTeX markup receding and prose in full ink; it was reverted at the
user's request, who prefers GtkSourceView's default scheme. A palette is the
taste of whoever writes, and they have already chosen.

What remains is what is not taste: this is not a code editor. Line numbers, an
80-column ruler and current-line highlighting are instruments for someone
navigating by address, not for someone reading a hundred-word argument. And
the column is capped, because long lines tire the eye -- the professor's
one-page limit is precisely about reading.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")

from gi.repository import Gdk, Gtk

FONT = "JetBrainsMono NF"
BODY_SIZE = 11.5
MEASURE = 74          # characters per line
MINIMUM_MARGIN = 24
LEADING = 6           # pixels added above and below each line

CSS = f"""
/* Typography only. Colours come from the GtkSourceView scheme, which is the
   user's choice. */
textview.serifa-editor {{
    font-family: "{FONT}", "Red Hat Mono", monospace;
    font-size: {BODY_SIZE}pt;
}}
.serifa-status {{
    font-size: 0.85em;
}}
"""


def install_css() -> None:
    provider = Gtk.CssProvider()
    provider.load_from_string(CSS)
    display = Gdk.Display.get_default()
    if display is not None:
        Gtk.StyleContext.add_provider_for_display(
            display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )


def character_width(widget: Gtk.Widget) -> int:
    """Width of one character in the editor font, in pixels."""
    context = widget.get_pango_context()
    metrics = context.get_metrics(context.get_font_description(), None)
    return max(1, metrics.get_approximate_char_width() // 1024)


def margin_for(width: int, char_width: int) -> int:
    """Side margin that centres a column of MEASURE characters.

    A pure function so it can be checked without a widget. On a narrow pane
    the arithmetic goes negative and the minimum applies -- the line is then
    shorter than the measure, which is the desired behaviour.
    """
    column = MEASURE * char_width
    return max(MINIMUM_MARGIN, (width - column) // 2)
