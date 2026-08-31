#!/usr/bin/env python3
"""Tests for unicode_smuggle_check.py - stdlib only.

    python3 -m unittest discover skills/my-security-review-checklist/tests

The quiet test matters most. A scanner that fires on ordinary prose - accents,
CJK, an emoji in a README - gets muted within a day, and a muted scanner
protects nothing.

Fixtures build the dangerous codepoints with chr() rather than pasting them.
A test file containing the literal characters would be unreadable in review and
would trip the scanner when the repo scans itself.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "unicode_smuggle_check.py"

TAG_A = chr(0xE0041)          # TAG LATIN CAPITAL LETTER A
RLO = chr(0x202E)             # RIGHT-TO-LEFT OVERRIDE
ZWSP = chr(0x200B)            # ZERO WIDTH SPACE
ZWJ = chr(0x200D)             # ZERO WIDTH JOINER
BOM = chr(0xFEFF)
VS16 = chr(0xFE0F)            # VARIATION SELECTOR-16


def run(*args: str) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True,
    )
    return proc.returncode, proc.stdout


class TestCatchesHidden(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def write(self, name: str, content: str) -> Path:
        path = self.dir / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_catches_tag_smuggling(self) -> None:
        path = self.write("SKILL.md", f"Run the tests.{TAG_A}\n")
        code, out = run(str(path))
        self.assertEqual(code, 1)
        self.assertIn("tag-smuggling", out)
        self.assertIn("U+E0041", out)

    def test_catches_bidi_override(self) -> None:
        path = self.write("app.py", f'if user.is_admin:  # {RLO}safe\n')
        code, out = run(str(path))
        self.assertEqual(code, 1)
        self.assertIn("bidi-override", out)

    def test_catches_zero_width(self) -> None:
        path = self.write("notes.md", f"del{ZWSP}ete everything\n")
        code, out = run(str(path))
        self.assertEqual(code, 1)
        self.assertIn("zero-width", out)

    def test_reports_line_and_column(self) -> None:
        path = self.write("doc.md", f"first line\nsecond{ZWJ} line\n")
        code, out = run("--json", str(path))
        self.assertEqual(code, 1)
        finding = json.loads(out)[0]
        self.assertEqual(finding["line"], 2)
        self.assertEqual(finding["column"], 7)

    def test_bom_mid_file_is_a_finding(self) -> None:
        path = self.write("doc.md", f"line one\nline{BOM} two\n")
        self.assertEqual(run(str(path))[0], 1)


class TestStaysQuiet(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def write(self, name: str, content: str) -> Path:
        path = self.dir / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_ordinary_prose_is_silent(self) -> None:
        path = self.write("README.md", "Café naïve résumé - 日本語 - Ελληνικά\n")
        code, out = run(str(path))
        self.assertEqual(code, 0)
        self.assertIn("clean", out)

    def test_leading_bom_is_allowed(self) -> None:
        path = self.write("doc.md", f"{BOM}# Title\n")
        self.assertEqual(run(str(path))[0], 0)

    def test_variation_selector_warns_but_does_not_fail(self) -> None:
        path = self.write("README.md", f"status: ✔{VS16}\n")
        code, out = run(str(path))
        self.assertEqual(code, 0)
        self.assertIn("WARN", out)
        self.assertEqual(run("--strict", str(path))[0], 1)

    def test_this_repos_own_skill_files_are_clean(self) -> None:
        skill_dir = SCRIPT.resolve().parent.parent
        code, out = run(str(skill_dir))
        self.assertEqual(code, 0, out)


class TestFailsClosed(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def test_invalid_utf8_is_a_finding(self) -> None:
        path = self.dir / "broken.md"
        path.write_bytes(b"valid text \xff\xfe then garbage\n")
        code, out = run(str(path))
        self.assertEqual(code, 1)
        self.assertIn("undecodable", out)

    def test_missing_file_is_a_finding(self) -> None:
        code, out = run(str(self.dir / "does-not-exist.md"))
        self.assertEqual(code, 1)
        self.assertIn("unreadable", out)

    def test_directory_scan_skips_binaries_and_vcs(self) -> None:
        (self.dir / ".git").mkdir()
        (self.dir / ".git" / "config.md").write_text(f"hidden{ZWSP}\n", encoding="utf-8")
        (self.dir / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        (self.dir / "clean.md").write_text("all good\n", encoding="utf-8")
        self.assertEqual(run(str(self.dir))[0], 0)


if __name__ == "__main__":
    unittest.main()
