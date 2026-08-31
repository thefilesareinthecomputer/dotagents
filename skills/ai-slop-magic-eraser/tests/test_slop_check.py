#!/usr/bin/env python3
"""Tests for slop_check.py - stdlib only.

    python3 -m unittest discover skills/ai-slop-magic-eraser/tests

Three questions the linter cannot answer about itself:

  1. Does it CATCH the tells?        sloppy.md must trip every named category.
  2. Does it stay QUIET otherwise?   clean.md must produce zero findings.
  3. Does --fix stay in its lane?    Mechanical characters only, never prose,
                                     and never inside fenced code.

(2) and (3) are the ones that matter. A linter that flags everything is noise,
and an auto-fixer that edits prose is a content-loss bug wearing a helpful hat.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
SCRIPT = SKILL / "scripts" / "slop_check.py"
sys.path.insert(0, str(SKILL / "scripts"))
import slop_check  # noqa: E402  (path set above)
FIXTURES = SKILL / "tests" / "fixtures"
SLOPPY = FIXTURES / "sloppy.md"
CLEAN = FIXTURES / "clean.md"

CATEGORIES = [
    "symbol",
    "sycophancy",
    "meta",
    "hedge",
    "register",
    "handwave",
    "filler",
    "cadence",
    "structure",
]


def run(*args: str) -> tuple[int, str, str]:
    p = subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True
    )
    return p.returncode, p.stdout, p.stderr


def findings(path: Path, *extra: str) -> list[dict]:
    _, out, _ = run("--json", *extra, str(path))
    return json.loads(out)


class TestCatchesTells(unittest.TestCase):
    def test_exits_nonzero_on_sloppy(self) -> None:
        code, _, _ = run(str(SLOPPY))
        self.assertEqual(code, 1)

    def test_every_category_fires(self) -> None:
        seen = {f["category"] for f in findings(SLOPPY)}
        for category in CATEGORIES:
            with self.subTest(category=category):
                self.assertIn(category, seen)

    def test_findings_carry_position_and_message(self) -> None:
        for f in findings(SLOPPY):
            self.assertGreaterEqual(f["line"], 1)
            self.assertGreaterEqual(f["col"], 1)
            self.assertTrue(f["matched"])
            self.assertTrue(f["message"])


class TestStaysQuiet(unittest.TestCase):
    def test_clean_fixture_exits_zero(self) -> None:
        code, out, _ = run(str(CLEAN))
        self.assertEqual(code, 0, out)
        self.assertIn("clean", out)

    def test_clean_fixture_has_no_findings(self) -> None:
        self.assertEqual(findings(CLEAN), [])


class TestExemptions(unittest.TestCase):
    """Fenced code, inline code and link targets hold whatever they need."""

    def _fence_span(self) -> tuple[int, int]:
        lines = SLOPPY.read_text(encoding="utf-8").splitlines()
        marks = [i for i, l in enumerate(lines, 1) if l.startswith("```")]
        return marks[0], marks[1]

    def test_fenced_code_is_exempt(self) -> None:
        start, end = self._fence_span()
        inside = [f for f in findings(SLOPPY) if start <= f["line"] <= end]
        self.assertEqual(inside, [], f"reported inside a code fence: {inside}")

    def test_inline_code_is_exempt(self) -> None:
        lines = SLOPPY.read_text(encoding="utf-8").splitlines()
        target = next(i for i, l in enumerate(lines, 1) if l.startswith("And `inline"))
        hits = [f for f in findings(SLOPPY) if f["line"] == target]
        self.assertEqual(hits, [], f"reported inside inline code: {hits}")


class TestSkillFilesAreNotProse(unittest.TestCase):
    """A SKILL.md is instructions to a model. Its subject IS the document, so
    'this skill does X' is content rather than the meta tell. Every other rule
    still applies, or the exemption becomes a hole."""

    BODY = (
        "# thing\n\n"
        "This skill governs six paths. Use this skill when the user asks.\n"
        "It is a working index, not a narrative.\n"
    )

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write(self, name: str) -> Path:
        p = self.dir / name
        p.write_text(self.BODY, encoding="utf-8")
        return p

    def test_skill_md_is_exempt_from_meta(self) -> None:
        hits = [f for f in findings(self._write("SKILL.md")) if f["category"] == "meta"]
        self.assertEqual(hits, [], f"meta reported in a SKILL.md: {hits}")

    def test_same_text_still_trips_meta_elsewhere(self) -> None:
        hits = [f for f in findings(self._write("README.md")) if f["category"] == "meta"]
        self.assertTrue(hits, "meta should still fire outside a SKILL.md")

    def test_other_rules_still_fire_in_a_skill_md(self) -> None:
        seen = {f["category"] for f in findings(self._write("SKILL.md"))}
        self.assertIn("cadence", seen, "the exemption must be meta-only")


class TestFenceNesting(unittest.TestCase):
    """CommonMark fence pairing. Documents that show markdown inside markdown
    nest fences, and a masker that mispairs them exposes code as prose (false
    findings, and --fix rewriting characters inside a script)."""

    def mask(self, text: str) -> list[bool]:
        return slop_check.code_line_mask(text.split("\n"))

    def test_longer_fence_wraps_shorter(self) -> None:
        # The ``` must NOT close the ```` block.
        m = self.mask('````markdown\n```bash\necho hi\n```\nstill inside\n````\nprose')
        self.assertEqual(m, [True] * 6 + [False])

    def test_shorter_fence_cannot_close_longer(self) -> None:
        m = self.mask('`````\n```\n`````\nprose')
        self.assertEqual(m[3], False, "five-backtick block closed by three")

    def test_tilde_does_not_close_backtick(self) -> None:
        m = self.mask('```\n~~~\ncode\n```\nprose')
        self.assertEqual(m, [True, True, True, True, False])

    def test_info_string_does_not_close(self) -> None:
        # ```python is an opener, never a closer.
        m = self.mask('```\ncode\n```python\nstill code\n```\nprose')
        self.assertEqual(m[5], False)

    def test_longer_run_may_close(self) -> None:
        # A closing fence may be longer than the opener.
        m = self.mask('```\ncode\n`````\nprose')
        self.assertEqual(m[3], False)

    def test_indent_up_to_three_opens_four_does_not(self) -> None:
        self.assertEqual(self.mask('   ```\ncode\n   ```\nprose')[3], False)
        self.assertEqual(self.mask('    ```\nprose')[1], False,
                         "4-space indent is an indented code block, not a fence")

    def test_unterminated_fence_runs_to_eof(self) -> None:
        self.assertEqual(self.mask('```\na\nb'), [True, True, True])

    def test_backtick_info_string_with_backtick_is_not_a_fence(self) -> None:
        self.assertEqual(self.mask('``` `x`\nprose')[1], False)

    def test_real_world_nested_template(self) -> None:
        doc = (
            '````markdown\n'
            '# Embedded doc with an em dash — here\n'
            '```bash\n'
            'echo "inner"\n'
            '```\n'
            'more embedded prose — still inside\n'
            '````\n'
            'Real prose — this one counts.\n'
        )
        m = self.mask(doc)
        self.assertTrue(all(m[:7]), "template body leaked out of the fence")
        self.assertFalse(m[7], "prose after the template was swallowed")


class TestFixStaysInItsLane(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.target = Path(self.tmp.name) / "doc.md"
        shutil.copy(SLOPPY, self.target)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_rewrites_mechanical_characters(self) -> None:
        before = self.target.read_text(encoding="utf-8")
        self.assertIn("—", before)
        run("--fix", str(self.target))
        prose = self.target.read_text(encoding="utf-8").split("```")[0]
        for ch in ("—", "–", "“", "”", "\U0001f680"):
            self.assertNotIn(ch, prose)

    def test_leaves_judgment_calls_alone(self) -> None:
        run("--fix", str(self.target))
        after = self.target.read_text(encoding="utf-8")
        for phrase in ("Great question", "leverage", "It's worth noting", "Furthermore"):
            self.assertIn(phrase, after, f"--fix removed a judgment call: {phrase}")

    def test_leaves_fenced_code_alone(self) -> None:
        run("--fix", str(self.target))
        fenced = self.target.read_text(encoding="utf-8").split("```")[1]
        self.assertIn("—", fenced)
        self.assertIn("\U0001f680", fenced)

    def test_is_idempotent(self) -> None:
        run("--fix", str(self.target))
        once = self.target.read_text(encoding="utf-8")
        run("--fix", str(self.target))
        self.assertEqual(self.target.read_text(encoding="utf-8"), once)

    def test_does_not_touch_a_clean_file(self) -> None:
        target = Path(self.tmp.name) / "clean.md"
        shutil.copy(CLEAN, target)
        before = target.read_text(encoding="utf-8")
        run("--fix", str(target))
        self.assertEqual(target.read_text(encoding="utf-8"), before)


class TestNonKeyboardCharacters(unittest.TestCase):
    """A standard typer produces ASCII. Everything else is reported, and sorted
    into rewrite / delete / report-only."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write(self, body: str, name: str = "doc.md") -> Path:
        p = self.dir / name
        p.write_text(body, encoding="utf-8")
        return p

    def _matched(self, body: str) -> set[str]:
        return {f["matched"] for f in findings(self._write(body), "--only", "symbol")}

    def test_reports_characters_with_an_ascii_form(self) -> None:
        for ch in ("…", "•", "→", "×", "≥", "ﬁ",
                   "′", " ", "−", "«"):
            with self.subTest(char=ch):
                self.assertIn(ch, self._matched(f"prose {ch} prose\n"))

    def test_reports_characters_with_no_ascii_form(self) -> None:
        for ch in ("é", "°", "┌", "日", "½", "†"):
            with self.subTest(char=ch):
                self.assertIn(ch, self._matched(f"prose {ch} prose\n"))

    def test_message_names_the_codepoint(self) -> None:
        f = findings(self._write("a … b\n"), "--only", "symbol")[0]
        self.assertIn("U+2026", f["message"])
        self.assertIn("HORIZONTAL ELLIPSIS", f["message"])

    def test_plain_ascii_is_silent(self) -> None:
        self.assertEqual(self._matched("Plain ASCII prose - nothing here.\n"), set())

    def test_invisible_characters_are_reported_even_inside_code(self) -> None:
        body = "```\ncode​here\n```\n"
        self.assertIn("​", self._matched(body))

    def test_visible_characters_inside_code_are_not_reported(self) -> None:
        body = "```\ncode — here\n```\n"
        self.assertNotIn("—", self._matched(body))

    def test_link_targets_are_exempt(self) -> None:
        self.assertEqual(self._matched("see [x](http://e.com/a—b)\n"), set())


class TestNonKeyboardFix(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "doc.md"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _fix(self, body: str) -> str:
        self.path.write_text(body, encoding="utf-8")
        run("--fix", str(self.path))
        return self.path.read_text(encoding="utf-8")

    def test_rewrites_to_the_ascii_equivalent(self) -> None:
        got = self._fix("a… b• c→ d× e≥ fﬁ\n")
        self.assertEqual(got, "a... b- c-> dx e>= ffi\n")

    def test_deletes_invisible_characters(self) -> None:
        self.assertEqual(self._fix("a​b­c\n"), "abc\n")

    def test_deletes_invisible_characters_inside_code(self) -> None:
        self.assertEqual(self._fix("```\na​b\n```\n"), "```\nab\n```\n")

    def test_leaves_accented_prose_alone(self) -> None:
        body = "Café, José, naïve, 40°C.\n"
        self.assertEqual(self._fix(body), body)

    def test_leaves_inline_code_and_link_targets_alone(self) -> None:
        body = "`x — y` and [l](http://e.com/a—b)\n"
        self.assertEqual(self._fix(body), body)

    def test_nbsp_becomes_a_real_space(self) -> None:
        self.assertEqual(self._fix("a b\n"), "a b\n")


class TestCharacterTablesAreIntact(unittest.TestCase):
    """The tables hold characters that are invisible or near-invisible in a
    diff, so an editor, a paste or a --fix run over this file could empty a row
    without anyone seeing it. These assert the codepoints directly."""

    def test_invisible_set_holds_the_expected_codepoints(self) -> None:
        self.assertEqual(
            sorted(ord(c) for c in slop_check.INVISIBLE),
            [0x00AD, 0x200B, 0x200C, 0x200D, 0x202A, 0x202B, 0x202C, 0x202D,
             0x202E, 0x2060, 0x2066, 0x2067, 0x2068, 0x2069, 0xFEFF],
        )

    def test_space_rows_survive(self) -> None:
        for cp in (0x00A0, 0x2002, 0x2003, 0x2007, 0x2009,
                   0x200A, 0x202F, 0x205F, 0x3000):
            with self.subTest(cp=hex(cp)):
                self.assertEqual(slop_check.REPLACE.get(chr(cp)), " ")

    def test_every_replace_key_is_a_single_non_ascii_char(self) -> None:
        for k in slop_check.REPLACE:
            with self.subTest(key=repr(k)):
                self.assertEqual(len(k), 1)
                self.assertFalse(k.isascii(), "an ASCII key would rewrite normal text")

    def test_every_replacement_is_ascii(self) -> None:
        for k, v in slop_check.REPLACE.items():
            with self.subTest(key=repr(k)):
                self.assertTrue(v.isascii(), f"{k!r} maps to non-ASCII {v!r}")

    def test_replace_and_invisible_do_not_overlap(self) -> None:
        self.assertEqual(set(slop_check.REPLACE) & slop_check.INVISIBLE, set())


class TestUsage(unittest.TestCase):
    def test_missing_file_is_usage_error(self) -> None:
        code, _, _ = run(str(FIXTURES / "does-not-exist.md"))
        self.assertEqual(code, 2)

    def test_unknown_category_is_usage_error(self) -> None:
        code, _, err = run("--only", "nonsense", str(SLOPPY))
        self.assertEqual(code, 2)
        self.assertIn("known:", err)

    def test_only_filters_to_one_category(self) -> None:
        self.assertGreater(len({f["category"] for f in findings(SLOPPY)}), 1)
        filtered = {f["category"] for f in findings(SLOPPY, "--only", "symbol")}
        self.assertEqual(filtered, {"symbol"})


if __name__ == "__main__":
    unittest.main()
