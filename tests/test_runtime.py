# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Vinícius Bispo e colaboradores

"""The launcher must reject incompatible runtimes before opening GTK."""

import os
import runpy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
CHECK = runpy.run_path(str(ROOT / "bin" / "runtime.py"))["check"]


class TestRuntime(unittest.TestCase):
    def test_old_python_has_actionable_error(self):
        with (
            patch.object(sys, "version_info", (3, 11)),
            self.assertRaisesRegex(RuntimeError, "Python 3.12"),
        ):
            CHECK()

    def test_explicit_python_missing_gi_does_not_fall_back(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "gi.py").write_text(
                'raise ImportError("bindings indisponíveis")'
            )
            result = subprocess.run(
                [str(ROOT / "bin" / "python"), "--check"],
                cwd=folder,
                env={**os.environ, "SERIFA_PYTHON": sys.executable, "PYTHONPATH": folder},
                capture_output=True,
                text=True,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("bindings indisponíveis", result.stderr)
        self.assertIn("README", result.stderr)
        self.assertNotIn("OK", result.stdout)

    def test_missing_explicit_interpreter_does_not_fall_back(self):
        with tempfile.TemporaryDirectory() as folder:
            result = subprocess.run(
                [str(ROOT / "bin" / "python"), "--check"],
                env={**os.environ, "SERIFA_PYTHON": str(Path(folder, "missing-python"))},
                capture_output=True,
                text=True,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SERIFA_PYTHON", result.stderr)
