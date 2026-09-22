r"""Asynchronous compilation and reading of the LaTeX log.

There are two modes, and what tells them apart is what each one writes to disk.

- **Build** (Ctrl+B, Ctrl+S) writes your .tex and compiles that file, through
  the project's scripts/compilar.sh when there is one.
- **Preview** (the continuous one, while you type) never touches your file: it
  dumps the buffer into a shadow file inside the cache and compiles from
  there, with the working directory set to the text's own folder. That last
  detail is what keeps ``\input{../../preambulo.tex}`` resolving, since TeX
  resolves relative paths against the working directory, not against the
  input file.

The process runs through Gio.Subprocess so the window does not freeze during
latexmk's few seconds. The log is read from the file rather than from the
terminal output, because in the terminal TeX wraps messages at 79 columns.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path

from gi.repository import Gio, GLib, GObject


@dataclass(frozen=True)
class Diagnostic:
    """A LaTeX error or warning, with file and line when they can be known."""

    severity: str  # "error" | "warning"
    message: str
    file: str | None = None
    line: int | None = None

    @property
    def icon(self) -> str:
        if self.severity == "error":
            return "dialog-error-symbolic"
        return "dialog-warning-symbolic"

    @property
    def summary(self) -> str:
        where = ""
        if self.file:
            where = f"{Path(self.file).name}"
            if self.line:
                where += f":{self.line}"
            where += " — "
        return f"{where}{self.message}"


# "! Undefined control sequence." and friends.
ERROR = re.compile(r"^! (.+)$", re.MULTILINE)
# "l.23 \foo" -- the line TeX reports right after the error.
ERROR_LINE = re.compile(r"^l\.(\d+)", re.MULTILINE)
WARNING = re.compile(
    r"^(?:LaTeX|Package|Class)(?: (\S+))? Warning: (.+)$", re.MULTILINE
)
# "on input line 12" shows up mid-message as often as at the end --
# "Reference `x' on input line 12 undefined." is the commonest shape. Looking
# only at the end lost the number in most warnings.
INPUT_LINE = re.compile(r"on input line (\d+)")

# TeX cuts its output at max_print_line, 79 by default, without indenting the
# continuation. The exact length is what says "continues on the next line",
# not the indentation -- the first attempt here keyed on indentation and
# joined nothing.
TEX_WIDTH = 79

# "(./file.tex" -- the stack of files TeX opens.
OPENS_FILE = re.compile(r"\((\.{0,2}/?[^()\s]*\.tex)")


def _unwrap(raw: str) -> str:
    """Rebuild the lines TeX cut at 79 columns.

    Decided by the length of the ORIGINAL line, not of the already-joined one:
    a message broken into three pieces has 79 characters in the first two, and
    looking at the accumulated length would leave the third one out.
    """
    joined: list[str] = []
    continuing = False
    for line in raw.split("\n"):
        if continuing and joined:
            joined[-1] += line
        else:
            joined.append(line)
        continuing = len(line) == TEX_WIDTH
    return "\n".join(joined)


def read_log(log_path: Path) -> list[Diagnostic]:
    """Extract errors and warnings from a LaTeX .log."""
    try:
        raw = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    text = _unwrap(raw)
    diagnostics: list[Diagnostic] = []

    for match in ERROR.finditer(text):
        message = match.group(1).strip()
        rest = text[match.end() : match.end() + 2000]
        line = ERROR_LINE.search(rest)
        file = None
        previous = OPENS_FILE.findall(text[: match.start()])
        if previous:
            file = previous[-1]
        diagnostics.append(
            Diagnostic("error", message, file, int(line.group(1)) if line else None)
        )

    for match in WARNING.finditer(text):
        package, message = match.groups()
        if "Rerun" in message:  # noise: latexmk sorts this out by itself
            continue
        where = INPUT_LINE.search(message)
        label = f"{package}: {message}" if package else message
        diagnostics.append(
            Diagnostic("warning", label.strip(), None,
                       int(where.group(1)) if where else None)
        )

    return diagnostics


class Builder(GObject.Object):
    """Runs latexmk and reports when it is done."""

    __gsignals__ = {
        "started": (GObject.SignalFlags.RUN_FIRST, None, (bool,)),
        # (succeeded, pdf path or "", diagnostics, was a preview)
        "finished": (GObject.SignalFlags.RUN_FIRST, None, (bool, str, object, bool)),
    }

    def __init__(self) -> None:
        super().__init__()
        self._process: Gio.Subprocess | None = None
        self._pending: tuple | None = None

    @property
    def busy(self) -> bool:
        return self._process is not None

    # -------------------------------------------------------- the two modes

    def build(self, tex_file: Path) -> None:
        """Compile the user's file, which must already be on disk."""
        folder = tex_file.parent
        script = self._project_script(folder)
        if script is not None:
            arguments = [str(script), str(folder)]
            directory = str(script.parent.parent)
        else:
            arguments = [
                "latexmk", "-pdf", "-interaction=nonstopmode",
                "-halt-on-error", "-synctex=1", tex_file.name,
            ]
            directory = str(folder)
        self._launch(
            arguments,
            directory,
            self._pdf_for(tex_file, folder),
            self._log_for(tex_file, folder),
            preview=False,
        )

    def build_preview(self, text: str, tex_file: Path) -> None:
        """Compile the buffer without touching the user's file."""
        shadow = self.shadow_folder(tex_file.parent)
        try:
            shadow.mkdir(parents=True, exist_ok=True)
            (shadow / "previa.tex").write_text(text, encoding="utf-8")
        except OSError as error:
            self.emit("finished", False, "", [Diagnostic("error", str(error))], True)
            return

        self._launch(
            [
                "latexmk", "-pdf", "-interaction=nonstopmode", "-halt-on-error",
                f"-output-directory={shadow}", str(shadow / "previa.tex"),
            ],
            # The working directory is the text's folder, not the shadow's:
            # that is what keeps the document's relative paths resolving.
            str(tex_file.parent),
            shadow / "previa.pdf",
            shadow / "previa.log",
            preview=True,
        )

    @staticmethod
    def shadow_folder(text_folder: Path) -> Path:
        key = hashlib.sha1(str(text_folder).encode()).hexdigest()[:12]
        return Path(GLib.get_user_cache_dir()) / "serifa" / "previa" / key

    # ----------------------------------------------------------- execution

    def _launch(
        self, arguments: list[str], directory: str, pdf: Path, log: Path, preview: bool
    ) -> None:
        if self._process is not None:
            # One at a time; the last one asked for wins.
            self._pending = (arguments, directory, pdf, log, preview)
            return

        launcher = Gio.SubprocessLauncher.new(
            Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE
        )
        launcher.set_cwd(directory)
        try:
            self._process = launcher.spawnv(arguments)
        except GLib.Error as error:
            self.emit("finished", False, "", [Diagnostic("error", str(error))], preview)
            return

        self.emit("started", preview)
        self._process.wait_async(None, self._on_finished, (pdf, log, preview))

    def _on_finished(self, process: Gio.Subprocess, result, data) -> None:
        pdf, log, preview = data
        with contextlib.suppress(GLib.Error):
            process.wait_finish(result)
        self._process = None

        diagnostics = read_log(log)
        has_pdf = pdf.exists()
        # latexmk returns a failure code even when the PDF came out; what
        # decides is the file existing and the log carrying no error.
        succeeded = has_pdf and not any(d.severity == "error" for d in diagnostics)
        self.emit("finished", succeeded, str(pdf) if has_pdf else "",
                  diagnostics, preview)

        if self._pending is not None:
            pending, self._pending = self._pending, None
            self._launch(*pending)

    # ------------------------------------------------------------- paths

    @staticmethod
    def _project_script(folder: Path) -> Path | None:
        """Walk up looking for an executable scripts/compilar.sh."""
        for candidate in [folder, *folder.parents]:
            script = candidate / "scripts" / "compilar.sh"
            if script.is_file() and os.access(script, os.X_OK):
                return script
        return None

    @staticmethod
    def _pdf_for(tex_file: Path, folder: Path) -> Path:
        # compilar.sh names the PDF after the folder; bare latexmk, after the
        # .tex file.
        by_folder_name = folder / f"{folder.name}.pdf"
        if by_folder_name.exists():
            return by_folder_name
        return tex_file.with_suffix(".pdf")

    @staticmethod
    def _log_for(tex_file: Path, folder: Path) -> Path:
        by_folder_name = folder / f"{folder.name}.log"
        if by_folder_name.exists():
            return by_folder_name
        return tex_file.with_suffix(".log")
