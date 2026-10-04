# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Vinícius Bispo e colaboradores

"""Completion.

A note on the road *not* taken. The elegant way would be a
GtkSourceCompletionProvider of our own, one that looks at the context left of
the cursor and decides whether to offer commands, environments, citation keys
or labels. It got as far as working, context detection included -- until the
popup showed up: GtkSourceView 5.14's ``populate_async``/``populate_finish``
pair crashes in C right after ``populate_finish`` returns the model, with no
Python frame in the backtrace. It is a binding bug, not a usage one: the same
crash happens with a minimal provider of three fixed items, with or without a
live reference to the GTask, returning a value or a boolean.

So completion is assembled from the two pieces GtkSourceView already ships,
both in C:

- ``GtkSourceCompletionSnippets``, fed by a .snippets file generated here from
  the lists below -- commands and environments, with tab stops;
- ``GtkSourceCompletionWords``, fed by the document itself and by an invisible
  buffer holding the .bib keys and the text's ``\\label``s.

Context awareness is lost here: citation keys show up anywhere, not only
inside ``\\cite{``. What is gained is not bringing the editor down. The four
cases where context really matters got it back later, through a popup of our
own -- see serifa/context.py.
"""

from __future__ import annotations

import re
from pathlib import Path
from xml.sax.saxutils import escape

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("GtkSource", "5")

from gi.repository import GLib, Gtk

# (trigger, snippet text). $1, $2 are tab stops; $0 is where the cursor lands.
COMMANDS: list[tuple[str, str]] = [
    ("documentclass", "\\documentclass[${1:12pt, a4paper}]{${2:article}}$0"),
    ("usepackage", "\\usepackage{$1}$0"),
    ("section", "\\section{$1}\n$0"),
    ("sectionx", "\\section*{$1}\n$0"),
    ("subsection", "\\subsection{$1}\n$0"),
    ("subsectionx", "\\subsection*{$1}\n$0"),
    ("subsubsection", "\\subsubsection{$1}\n$0"),
    ("paragraph", "\\paragraph{$1}$0"),
    ("chapter", "\\chapter{$1}\n$0"),
    ("title", "\\title{$1}$0"),
    ("author", "\\author{$1}$0"),
    ("maketitle", "\\maketitle$0"),
    ("textbf", "\\textbf{$1}$0"),
    ("textit", "\\textit{$1}$0"),
    ("texttt", "\\texttt{$1}$0"),
    ("textsc", "\\textsc{$1}$0"),
    ("emph", "\\emph{$1}$0"),
    ("underline", "\\underline{$1}$0"),
    ("footnote", "\\footnote{$1}$0"),
    ("enquote", "\\enquote{$1}$0"),
    ("label", "\\label{$1}$0"),
    ("ref", "\\ref{$1}$0"),
    ("eqref", "\\eqref{$1}$0"),
    ("pageref", "\\pageref{$1}$0"),
    ("cite", "\\cite{$1}$0"),
    ("citep", "\\citep{$1}$0"),
    ("citet", "\\citet{$1}$0"),
    ("bibliography",
     "\\bibliographystyle{${1:unsrt}}\n\\bibliography{${2:../../referencias}}$0"),
    ("input", "\\input{$1}$0"),
    ("include", "\\include{$1}$0"),
    ("includegraphics", "\\includegraphics[width=${1:0.8\\textwidth}]{$2}$0"),
    ("caption", "\\caption{$1}$0"),
    ("item", "\\item $0"),
    ("frac", "\\frac{$1}{$2}$0"),
    ("sqrt", "\\sqrt{$1}$0"),
    ("sum", "\\sum_{$1}^{$2}$0"),
    ("int", "\\int_{$1}^{$2}$0"),
    ("lim", "\\lim_{$1}$0"),
    ("newcommand", "\\newcommand{$1}{$2}$0"),
    ("renewcommand", "\\renewcommand{$1}{$2}$0"),
    ("linespread", "\\linespread{$1}$0"),
    ("setlength", "\\setlength{$1}{$2}$0"),
    ("vspace", "\\vspace{$1}$0"),
    ("hspace", "\\hspace{$1}$0"),
    ("newpage", "\\newpage$0"),
    ("clearpage", "\\clearpage$0"),
    ("partial", "\\partial$0"),
    ("infty", "\\infty$0"),
    ("cdot", "\\cdot$0"),
    ("times", "\\times$0"),
    ("approx", "\\approx$0"),
    ("neq", "\\neq$0"),
    ("leq", "\\leq$0"),
    ("geq", "\\geq$0"),
    ("ldots", "\\ldots$0"),
    ("quad", "\\quad$0"),
    ("rightarrow", "\\rightarrow$0"),
    ("Rightarrow", "\\Rightarrow$0"),
]

GREEK_LETTERS = [
    "alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta",
    "iota", "kappa", "lambda", "mu", "nu", "xi", "pi", "rho", "sigma", "tau",
    "phi", "chi", "psi", "omega", "Gamma", "Delta", "Theta", "Lambda", "Xi",
    "Pi", "Sigma", "Phi", "Psi", "Omega",
]

ENVIRONMENTS = [
    "document", "abstract", "itemize", "enumerate", "description",
    "figure", "table", "tabular", "center", "flushleft", "flushright",
    "quote", "quotation", "verse", "verbatim", "equation", "equationx",
    "align", "alignx", "gather", "matrix", "pmatrix", "bmatrix",
    "cases", "array", "minipage", "thebibliography",
]

BIB_KEY = re.compile(r"@\w+\s*\{\s*([^,\s]+)", re.MULTILINE)
LABEL = re.compile(r"\\label\{([^}]+)\}")


def _snippet(trigger: str, description: str, text: str) -> str:
    # GtkSourceView's parser contradicts its own snippets.rng in three places,
    # all found by trial and error: it demands the underscore forms (_group,
    # _name, _description) and rejects the plain ones; it rejects the version
    # attribute, which the RNG declares required; and it demands languages on
    # <text>, which the RNG declares optional. Touching this without testing
    # breaks everything at once, silently -- the error is just a WARNING on
    # the console.
    return (
        f'  <snippet _name="{escape(trigger)}" trigger="{escape(trigger)}"\n'
        f'           _description="{escape(description)}">\n'
        f'    <text languages="latex;"><![CDATA[{text}]]></text>\n'
        f"  </snippet>\n"
    )


def prepare_snippets() -> Path:
    """Generates the .snippets file from the lists above and returns its folder.

    Generated at run time on purpose: the Python lists stay the single source
    of truth, and there is no XML to forget to update.
    """
    folder = Path(GLib.get_user_cache_dir()) / "serifa" / "snippets"
    folder.mkdir(parents=True, exist_ok=True)

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>\n<snippets _group="LaTeX">\n'
    ]
    for trigger, text in COMMANDS:
        parts.append(_snippet(trigger, text.replace("$0", "").strip(), text))
    for letter in GREEK_LETTERS:
        parts.append(_snippet(letter, f"\\{letter}", f"\\{letter}$0"))
    for environment in ENVIRONMENTS:
        # "equationx" is the trigger for equation*: an asterisk is no good as
        # a trigger.
        real = environment[:-1] + "*" if environment.endswith("x") else environment
        body = f"\\begin{{{real}}}\n  $1\n\\end{{{real}}}$0"
        parts.append(_snippet(environment, f"ambiente {real}", body))
        parts.append(_snippet(f"beg{environment}", f"ambiente {real}", body))
    parts.append("</snippets>\n")

    (folder / "latex.snippets").write_text("".join(parts), encoding="utf-8")
    return folder


class KeySource:
    """Invisible buffer with the .bib keys and the document's labels.

    Feeds GtkSourceCompletionWords, which only completes words that exist in
    some buffer registered with it.
    """

    def __init__(self) -> None:
        self.buffer = Gtk.TextBuffer()
        self._folder: Path | None = None
        self._bib_keys: list[str] = []

    def set_folder(self, folder: Path | None) -> None:
        if folder == self._folder:
            return
        self._folder = folder
        self._bib_keys = self._read_bibs(folder) if folder else []

    def update(self, document_text: str) -> None:
        labels = sorted(set(LABEL.findall(document_text)))
        self.buffer.set_text("\n".join([*self._bib_keys, *labels]))

    @property
    def keys(self) -> list[str]:
        return list(self._bib_keys)

    @staticmethod
    def _read_bibs(folder: Path) -> list[str]:
        found: list[str] = []
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
                    text = file.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                for key in BIB_KEY.findall(text):
                    if key not in seen:
                        seen.add(key)
                        found.append(key)
        return found
