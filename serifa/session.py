# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Vinícius Bispo e colaboradores

"""What the window remembers between one launch and the next.

Deliberately a small file: this is the only state that outlives the window,
and leaving it buried in the middle of window.py made it hard to see what
exactly gets persisted -- and hard to redirect in tests, which used to be done
by patching a module variable.
"""

from __future__ import annotations

import json
from pathlib import Path

from gi.repository import GLib

DEFAULT = Path(GLib.get_user_config_dir()) / "serifa" / "state.json"


def read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write(path: Path, data: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass   # the session is a convenience; failing here must break nothing
