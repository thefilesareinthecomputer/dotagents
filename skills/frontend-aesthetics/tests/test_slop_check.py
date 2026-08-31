#!/usr/bin/env python3
"""Tests for slop_check.py — stdlib only.

    python3 -m unittest discover skills/frontend-aesthetics/tests

Two questions these answer, which the linter cannot answer about itself:
  1. Does it CATCH the tells?      (sloppy.tsx must trip every named rule)
  2. Does it stay QUIET otherwise? (clean.tsx must produce zero findings)

(2) is the one that matters. A linter that flags everything is noise, and noise
gets ignored, and an ignored linter protects nothing.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "slop_check.py"
FIXTURES = ROOT / "tests" / "fixtures"


def run(*paths: Path) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), *[str(p) for p in paths]],
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout


class TestCatchesTells(unittest.TestCase):
    def setUp(self) -> None:
        self.code, self.out = run(FIXTURES / "sloppy.tsx")

    def test_exits_nonzero(self) -> None:
        self.assertEqual(self.code, 1, "sloppy fixture must fail the gate")

    def test_catches_each_rule(self) -> None:
        expected = [
            "em-dash",
            "banned-palette",
            "pure-black-white",
            "default-font",
            "lucide-icons",
            "emoji",
            "h-screen",
            "stock-name",
            "filler-verb",
            "scroll-cue",
            "fake-precision",
            "section-number-eyebrow",
            "placeholder-as-label",
            "placeholder-comment",
            "middot-spam",
        ]
        for rule in expected:
            with self.subTest(rule=rule):
                self.assertIn(rule, self.out, f"{rule} not caught in sloppy fixture")


class TestStaysQuiet(unittest.TestCase):
    def test_clean_fixture_is_silent(self) -> None:
        code, out = run(FIXTURES / "clean.tsx")
        self.assertEqual(code, 0, f"clean fixture must pass; got:\n{out}")
        self.assertIn("clean", out)

    def test_no_false_positives_on_clean(self) -> None:
        _, out = run(FIXTURES / "clean.tsx")
        for severity in ("FAIL:", "WARN:"):
            self.assertNotIn(severity, out, f"false positive on clean fixture:\n{out}")


class TestRadiusAnchors(unittest.TestCase):
    """0 and full-round (50%, 999px+) are anchors outside the radius scale.
    A vanilla app's {0, small, large, pill} language must pass; three real
    in-between steps must still trip (added 2026-08-27, from a live pass
    on a zero-dependency UI)."""

    def _scan(self, css: str) -> str:
        with tempfile.NamedTemporaryFile("w", suffix=".css",
                                         delete=False) as fh:
            fh.write(css)
            path = Path(fh.name)
        try:
            _, out = run(path)
            return out
        finally:
            path.unlink()

    def test_anchor_radii_do_not_count(self) -> None:
        out = self._scan("a{border-radius: 0}\nb{border-radius: 4px}\n"
                         "c{border-radius: 10px}\nd{border-radius: 50%}\n"
                         "e{border-radius: 999px}\n")
        self.assertNotIn("radius-scale", out)

    def test_three_scale_steps_still_trip(self) -> None:
        out = self._scan("a{border-radius: 3px}\nb{border-radius: 4px}\n"
                         "c{border-radius: 8px}\n")
        self.assertIn("radius-scale", out)


class TestHostileInput(unittest.TestCase):
    """This linter reads code it did not write. Untrusted input must not hang it.

    Regression: the default-font pattern once used an unbounded [^;,}]* that
    overlapped the following [:\\s]\\s*, backtracking quadratically —
    'font-family' + 40k spaces took 40 SECONDS, and a 1MB minified line
    extrapolated to hours. Found in security review 2026-07-14.
    """

    def _time_scan(self, content: str) -> float:
        import time

        sys.path.insert(0, str(ROOT / "scripts"))
        import slop_check

        with tempfile.NamedTemporaryFile("w", suffix=".tsx", delete=False) as fh:
            fh.write(content)
            path = Path(fh.name)
        try:
            start = time.perf_counter()
            slop_check.check_file(path)
            return time.perf_counter() - start
        finally:
            path.unlink()

    def test_redos_font_family_padding(self) -> None:
        elapsed = self._time_scan("font-family:" + " " * 40_000 + "x\n")
        self.assertLess(elapsed, 1.0, f"quadratic backtracking is back: {elapsed:.1f}s")

    def test_redos_svg_and_input_attrs(self) -> None:
        for payload in ("<svg " + "a" * 40_000, "<input " + "b" * 40_000):
            elapsed = self._time_scan(payload + "\n")
            self.assertLess(elapsed, 1.0, f"backtracking on {payload[:6]}: {elapsed:.1f}s")

    def test_long_lines_are_skipped(self) -> None:
        elapsed = self._time_scan("const x = '" + "—" * 100_000 + "';\n")
        self.assertLess(elapsed, 1.0, f"minified line not capped: {elapsed:.1f}s")


class TestSkillStructure(unittest.TestCase):
    """House invariants from the skill-authoring profile."""

    def test_skill_md_exists_and_is_bounded(self) -> None:
        skill = ROOT / "SKILL.md"
        self.assertTrue(skill.exists())
        body = skill.read_text(encoding="utf-8")
        self.assertLess(len(body.splitlines()), 500, "SKILL.md body must stay under 500 lines")

    def test_no_version_footer(self) -> None:
        for md in ROOT.rglob("*.md"):
            text = md.read_text(encoding="utf-8")
            self.assertNotRegex(text, r"(?m)^Version:", f"{md.name} carries a version footer")

    def test_frontmatter_name_matches_directory(self) -> None:
        head = (ROOT / "SKILL.md").read_text(encoding="utf-8").split("---")[1]
        self.assertIn(f"name: {ROOT.name}", head)

    def test_evals_exist_with_negative_case(self) -> None:
        import json

        cases = json.loads((ROOT / "evals" / "triggers.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(cases), 3, "house minimum is 3 eval cases")
        self.assertTrue(
            any(not c["should_trigger"] for c in cases),
            "needs at least one should-NOT-trigger case",
        )


if __name__ == "__main__":
    unittest.main()
