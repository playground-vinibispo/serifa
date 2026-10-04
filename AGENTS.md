# Agent guide

These instructions apply to this repository. Read [README.md](README.md) for
installation and architecture, and [CONTRIBUTING.md](CONTRIBUTING.md) for the
contribution workflow.

## Project

Serifa is a native Linux LaTeX editor built with Python 3.12+, GTK4,
GtkSourceView 5, libadwaita and Poppler. Keep the native GTK architecture and
reuse existing widgets and helpers before adding dependencies.

Code, script names, command-line options and developer-facing messages use
English. The editor's user interface and current user documentation use
Brazilian Portuguese. Follow the style of the module you change and preserve
GPL-3.0-only license notices.

## Environment and commands

The graphics bindings come from system packages. Do not install PyGObject via
pip to work around missing system libraries or hardcode a Python version path.
Use `bin/python`, which selects a compatible interpreter, and `bin/setup`,
which prepares a venv with system-site-packages and the versions in `uv.lock`.
Do not upgrade dependencies or regenerate the lockfile unless the task needs it.

| Task | Command |
|---|---|
| Check Python and system libraries | `make doctor` |
| Prepare development dependencies | `make setup` |
| Open the editor | `make run` |
| Lint | `make lint` |
| Full test suite | `make test` |
| Lint, then tests | `make check` |
| Coverage | `make coverage` |
| One test module | `bin/test tests.test_document` |

Make is optional; its targets delegate to scripts in `bin/`. Keep implementation
logic in those scripts, and update CI, hooks and documentation when commands
change. Wrapper options such as `--coverage` and `--show-windows` precede
unittest arguments.

## Implementation constraints

- Call `gi.require_version()` before importing from `gi.repository`.
- Keep compilation and other expensive work off the GTK event loop.
- Preserve independent buffers, undo history, previews and actions across tabs.
- Typing and continuous preview must not save or overwrite the source file.
  Preview compilation uses a shadow file; preserve relative-path resolution.
- Preserve confirmation before discarding unsaved changes and handling of
  external file changes. Never validate using a user's personal documents.
- Use temporary files and isolated session state for tests. Reuse `unittest`,
  `GraphicalCase` and the helpers in `tests/support.py`.

## Validation

Run lint and the relevant existing tests for behavior changes. Add a regression
test when it protects changed behavior; avoid tests that only duplicate literal
text or CSS. Run the full suite before submitting changes to runtime behavior.
For documentation-only changes, verify commands, local links and
`git diff --check`; no additional behavior tests are needed.

Graphical tests require a display. `bin/test` uses isolated headless Mutter when
available; Xvfb is another option, as described in CONTRIBUTING. Tests may be
skipped without a display or `latexmk`: report skipped tests and environment
limitations, and do not present them as verified flows.

For UI changes, inspect the real GTK window in light and dark themes, including
long filenames, multiple tabs and a smaller window. For document lifecycle
changes, verify save, discard and cancel with pending edits. Include screenshots
when presentation changes; refresh README screenshots when they become outdated.

## Git and pull requests

Inspect the worktree before editing and preserve unrelated changes. Work on a
focused branch; avoid destructive Git operations and rewriting published history
without an explicit request. Do not commit virtual environments, caches,
personal documents or generated LaTeX output.

Use the PR template and describe the problem, resulting behavior and actual
validation. Keep a PR focused on one concern. Do not merge a PR without explicit
maintainer authorization; when authorized, confirm that all required checks have
passed on the current head commit before merging.
