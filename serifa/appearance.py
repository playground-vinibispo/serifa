# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Vinícius Bispo e colaboradores

r"""Visual design and the width of the text column.

The interface uses a cool paper palette and restrained syntax colours.
The user authorized a full redesign, replacing the earlier default scheme.

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
window.serifa-window {{
    background: #f6f8fc; color: #24344b;
    --accent-bg-color: #305fa8; --accent-color: #305fa8;
    --window-bg-color: #f6f8fc; --window-fg-color: #24344b;
    --headerbar-bg-color: #f6f8fc; --headerbar-fg-color: #24344b;
    --view-bg-color: #ffffff; --view-fg-color: #24344b;
}}
.serifa-header {{ padding: 10px 16px; background: #f6f8fc; box-shadow: none; }}
.serifa-header windowtitle title {{ font-size: 16px; font-weight: 600; }}
.serifa-header windowtitle subtitle {{ color: #68788e; font-size: 11px; }}
.serifa-header button {{ border-radius: 8px; padding: 8px 12px; }}
.serifa-header button.suggested-action {{ background: #305fa8; color: white; }}
.serifa-tabs {{
    background: #f6f8fc; box-shadow: none; border: none; padding: 6px 12px 0;
}}
.serifa-tabs > box {{ background: transparent; box-shadow: none; }}
.serifa-tabs tabbox {{ background: transparent; }}
.serifa-tabs tab {{
    min-width: 130px; border-radius: 8px 8px 0 0;
    background: transparent; color: #68788e; box-shadow: none;
}}
.serifa-tabs tab:hover {{ background: #edf1f8; color: #24344b; }}
.serifa-tabs tab:selected {{
    background: #e8eef8; color: #244f91;
    box-shadow: inset 0 -2px #305fa8;
}}
.serifa-tabs tab label {{ font-size: 12px; }}
.serifa-tabs tab:selected label {{ font-weight: 600; }}
.serifa-tabs .serifa-tab-controls {{ padding: 0 4px 4px 8px; }}
.serifa-tabs .serifa-tab-controls button {{ border-radius: 7px; }}
textview.serifa-editor {{
    font-family: "{FONT}", "Red Hat Mono", monospace;
    font-size: {BODY_SIZE}pt; background: #ffffff; color: #24344b;
}}
.serifa-tools {{
    padding: 10px 22px; background: white;
    border-bottom: 1px solid #e6ebf3;
}}
.serifa-tools button {{ background: transparent; color: #526882; }}
.serifa-pane-title {{ font-weight: 600; font-size: 12px; color: #526882; }}
.serifa-outline {{ background: #eef2f8; border-right: 1px solid #dfe6f0; }}
.serifa-outline headerbar {{
    min-height: 50px; background: transparent; box-shadow: none;
}}
.serifa-outline row {{
    margin: 3px 12px; border-radius: 7px; padding: 5px 2px;
    color: #526882; font-weight: normal;
}}
.serifa-outline row:hover {{ background: #e1e9f5; }}
.serifa-outline row:selected {{ background: #d9e5f8; color: #244f91; }}
.serifa-statusbar {{
    padding: 9px 16px; background: #f6f8fc; border-top: 1px solid #dfe6f0;
}}
.serifa-status {{ font-size: 11px; color: #68788e; }}
.serifa-diagnostics {{ padding: 12px 18px; background: #eef2f8; }}
.serifa-preview {{ background: #e4eaf3; color: #526882; }}
.serifa-preview-tools {{
    padding: 10px 18px; background: #eef2f8; border-bottom: 1px solid #d6dfed;
}}
.serifa-preview-tools button {{ color: #526882; }}
.serifa-empty {{ padding: 40px; color: #526882; }}
.serifa-window paned > separator {{ background: #d6dfed; min-width: 1px; }}
"""

CSS += """
window.serifa-dark { background: #202937; color: #dce5f2;
 --window-bg-color: #202937; --window-fg-color: #dce5f2;
 --view-bg-color: #253041; --view-fg-color: #dce5f2;
 --headerbar-bg-color: #202937; --headerbar-fg-color: #dce5f2;
}
.serifa-dark .serifa-header, .serifa-dark .serifa-statusbar { background: #202937; }
.serifa-dark .serifa-tools, .serifa-dark .serifa-outline,
.serifa-dark .serifa-preview-tools, .serifa-dark .serifa-diagnostics {
 background: #253041; border-color: #3a485b; }
.serifa-dark .serifa-tabs { background: #202937; }
.serifa-dark .serifa-tabs tab { color: #acbed6; }
.serifa-dark .serifa-tabs tab:hover { background: #2a3648; color: #dce5f2; }
.serifa-dark .serifa-tabs tab:selected {
 background: #2c3d55; color: #dce9ff; box-shadow: inset 0 -2px #91b8f5; }
.serifa-dark textview.serifa-editor { background: #1d2633; color: #dce5f2; }
.serifa-dark .serifa-preview { background: #17202d; }
.serifa-dark .serifa-pane-title, .serifa-dark .serifa-outline row,
.serifa-dark .serifa-status, .serifa-dark .serifa-tools button,
.serifa-dark .serifa-preview-tools button,
.serifa-dark .serifa-preview-tools label, .serifa-dark .serifa-empty { color: #acbed6; }
.serifa-dark .serifa-outline row:selected { background: #354d70; color: #e6efff; }
.serifa-dark .serifa-outline row:hover { background: #304158; }
.serifa-dark paned > separator { background: #3a485b; }
"""

CSS += "\n".join(
    f"textview.serifa-editor.serifa-font-{size} {{ font-size: {size / 2}pt; }}"
    for size in range(16, 49)
)


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


def margin_for(width: int, char_width: int, measure: int = MEASURE) -> int:
    """Side margin that centres a column of MEASURE characters.

    A pure function so it can be checked without a widget. On a narrow pane
    the arithmetic goes negative and the minimum applies -- the line is then
    shorter than the measure, which is the desired behaviour.
    """
    column = measure * char_width
    return max(MINIMUM_MARGIN, (width - column) // 2)
