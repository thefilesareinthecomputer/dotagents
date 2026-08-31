#!/usr/bin/env python3
"""Tests for django_check.py - stdlib only.

    python3 -m unittest discover skills/django/tests
"""

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "django_check.py"
FIXTURES = ROOT / "tests" / "fixtures"


def run(*paths: Path) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), *[str(p) for p in paths]],
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout


class TestCatchesFootguns(unittest.TestCase):
    def setUp(self) -> None:
        self.code, self.out = run(FIXTURES / "bad_api.py")

    def test_blocks(self) -> None:
        self.assertEqual(self.code, 1)

    def test_catches_fail_open_defaults(self) -> None:
        """DRF fails OPEN: no DEFAULT_PERMISSION_CLASSES means a public API."""
        for rule in ("drf-permissions-unset", "view-no-permissions"):
            with self.subTest(rule=rule):
                self.assertIn(rule, self.out)

    def test_catches_serializer_overexposure(self) -> None:
        for rule in ("serializer-fields-all", "serializer-writable-privilege-field"):
            with self.subTest(rule=rule):
                self.assertIn(rule, self.out)

    def test_catches_injection_and_settings(self) -> None:
        for rule in ("sql-injection", "hardcoded-secret-key", "allowed-hosts-wildcard", "cors-wildcard"):
            with self.subTest(rule=rule):
                self.assertIn(rule, self.out)

    def test_catches_performance(self) -> None:
        for rule in ("possible-n-plus-1", "serializer-depth", "drf-no-pagination"):
            with self.subTest(rule=rule):
                self.assertIn(rule, self.out)


class TestReviewFindings(unittest.TestCase):
    """Regression tests for the 2026-07-14 security review of this checker."""

    def test_annotated_settings_are_not_bypassed(self) -> None:
        """The old visit_Assign-only checker missed every annotated setting -
        including ones this skill's own scaffold ships."""
        _, out = run(FIXTURES / "bad_annotated.py")
        for rule in ("hardcoded-secret-key", "allowed-hosts-wildcard", "cors-wildcard", "drf-permissions-unset"):
            with self.subTest(rule=rule):
                self.assertIn(rule, out)

    def test_write_only_password_is_clean(self) -> None:
        """The legitimate registration/set-password serializer must not FAIL -
        blocking it mutes the tool."""
        code, out = run(FIXTURES / "good_password.py")
        self.assertEqual(code, 0, f"write_only password must pass; got:\n{out}")
        self.assertNotIn("serializer-writable-privilege-field", out)

    def test_drf_used_without_any_permission_config(self) -> None:
        """A whole project that uses DRF but never configures permissions."""
        code, out = run(FIXTURES / "bad_no_perms")
        self.assertIn("drf-no-permission-config", out)


class TestStaysQuiet(unittest.TestCase):
    def test_good_fixture_is_silent(self) -> None:
        code, out = run(FIXTURES / "good_api.py")
        self.assertEqual(code, 0, f"correct DRF code must pass; got:\n{out}")
        for severity in ("FAIL:", "WARN:"):
            self.assertNotIn(severity, out, f"false positive:\n{out}")


class TestRobustness(unittest.TestCase):
    def test_syntax_error_does_not_crash(self) -> None:
        """It reads code mid-edit. A parse failure is a WARN, never a traceback."""
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
            fh.write("def broken(:\n")
            path = Path(fh.name)
        try:
            code, out = run(path)
            self.assertIn("unparseable", out)
            self.assertEqual(code, 0, "a syntax error is not a security failure")
        finally:
            path.unlink()

    def test_never_executes_the_code_it_reads(self) -> None:
        """ast.parse only. If this ever imported the target, a malicious settings.py
        would run arbitrary code just by being linted.

        `ast.literal_eval` is explicitly ALLOWED: it parses literals and refuses
        anything else. The bare builtins are what must never appear - hence the
        negative lookbehind rather than a substring match.
        """
        import re

        src = SCRIPT.read_text(encoding="utf-8")
        forbidden = [
            r"(?<!literal_)\beval\(",
            r"\bexec\(",
            r"\b__import__\b",
            r"\bimport importlib\b",
            r"\bimport subprocess\b",
            r"\bcompile\(",
        ]
        for pattern in forbidden:
            self.assertIsNone(
                re.search(pattern, src),
                f"{pattern} must not appear - this tool reads code, it does not run it",
            )


class TestSkillStructure(unittest.TestCase):
    def test_skill_md_bounded(self) -> None:
        self.assertLess(len((ROOT / "SKILL.md").read_text(encoding="utf-8").splitlines()), 500)

    def test_name_matches_directory(self) -> None:
        head = (ROOT / "SKILL.md").read_text(encoding="utf-8").split("---")[1]
        self.assertIn(f"name: {ROOT.name}", head)

    def test_evals_have_negative_case(self) -> None:
        cases = json.loads((ROOT / "evals" / "triggers.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(cases), 3)
        self.assertTrue(any(not c["should_trigger"] for c in cases))


if __name__ == "__main__":
    unittest.main()
