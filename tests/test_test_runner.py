# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Vinícius Bispo e colaboradores

"""Wrapper options must reach unittest and preserve failure status."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestTestRunner(unittest.TestCase):
    def run_wrapper(self, *args, fail=False):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "bin").mkdir()
            shutil.copy2(ROOT / "bin" / "test", root / "bin" / "test")
            python = root / "bin" / "python"
            python.write_text(
                "#!/usr/bin/env bash\n"
                'printf "%s\\0" "$@" >> "$TEST_ARG_LOG"\n'
                'printf "\\n" >> "$TEST_ARG_LOG"\n'
                'exit "${TEST_EXIT_CODE:-0}"\n'
            )
            python.chmod(0o755)
            log = root / "arguments"
            result = subprocess.run(
                [str(root / "bin" / "test"), *args],
                env={**os.environ, "SERIFA_TEST_ISOLATED": "1",
                     "TEST_ARG_LOG": str(log), "TEST_EXIT_CODE": "7" if fail else "0"},
                capture_output=True,
                text=True,
            )
            calls = [
                line.rstrip("\0").split("\0") for line in log.read_text().splitlines()
            ]
            return result, calls

    def test_coverage_and_visible_session_work_in_either_order(self):
        for options in (("--coverage", "--show-windows"),
                        ("--show-windows", "--coverage")):
            with self.subTest(options=options):
                result, calls = self.run_wrapper(*options, "tests.test_blocks")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(calls, [
                    ["-m", "coverage", "run", "-m", "unittest", "tests.test_blocks"],
                    ["-m", "coverage", "report", "-m"],
                ])

    def test_verbose_suite_uses_discovery(self):
        result, calls = self.run_wrapper("-v")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [
            ["-m", "unittest", "discover", "-s", "tests", "-t", ".", "-v"]
        ])

    def test_failed_coverage_run_does_not_report_success(self):
        result, calls = self.run_wrapper("--coverage", fail=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(calls), 1)
