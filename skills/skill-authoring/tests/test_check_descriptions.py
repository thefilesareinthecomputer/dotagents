#!/usr/bin/env python3
"""Tests for check_descriptions.py - stdlib only.

    python3 -m unittest discover -s skills/skill-authoring/tests

Parsing is tested on each YAML scalar style the repo's skills use, because the
length a harness sees is the parsed value, not the raw lines. The CLI is tested
over skill trees built in a temp directory, so the suite never depends on the
live repo's descriptions, which change every time a skill is edited.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
SCRIPT = SCRIPTS / "check_descriptions.py"
sys.path.insert(0, str(SCRIPTS))

import check_descriptions as cd  # noqa: E402


def skill_md(description_block: str, name: str = "example") -> str:
    return f"---\nname: {name}\n{description_block}\nlicense: MIT\n---\n\n# {name}\n"


def run(*args: str) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, str(SCRIPT), *args],
                          capture_output=True, text=True, timeout=30)
    return proc.returncode, proc.stdout


class ParseTest(unittest.TestCase):
    def test_plain_single_line(self):
        d = cd.parse_description(skill_md("description: Does a thing. Use when asked."))
        self.assertEqual(d, cd.Description("Does a thing. Use when asked.", "plain"))

    def test_plain_continuation_lines_join_with_spaces(self):
        d = cd.parse_description(skill_md("description: Does a thing.\n  Use when asked."))
        self.assertEqual(d.text, "Does a thing. Use when asked.")

    def test_folded_block_joins_lines(self):
        block = "description: >-\n  Does a thing: with a colon,\n  and more words.\n"
        d = cd.parse_description(skill_md(block))
        self.assertEqual(d, cd.Description("Does a thing: with a colon, and more words.", "folded"))

    def test_folded_block_blank_line_is_a_break(self):
        d = cd.parse_description(skill_md("description: >\n  One.\n\n  Two.\n"))
        self.assertEqual(d.text, "One.\nTwo.")

    def test_literal_block_keeps_breaks(self):
        d = cd.parse_description(skill_md("description: |\n  One.\n  Two.\n"))
        self.assertEqual(d, cd.Description("One.\nTwo.", "literal"))

    def test_double_quoted_strips_quotes(self):
        d = cd.parse_description(skill_md('description: "Says: \\"hi\\"."'))
        self.assertEqual(d, cd.Description('Says: "hi".', "quoted"))

    def test_single_quoted_unescapes_doubled_quote(self):
        d = cd.parse_description(skill_md("description: 'It''s here: now.'"))
        self.assertEqual(d, cd.Description("It's here: now.", "quoted"))

    def test_block_stops_at_next_key(self):
        d = cd.parse_description(skill_md("description: >-\n  Short.\nargument-hint: \"[x]\""))
        self.assertEqual(d.text, "Short.")

    def test_missing_description(self):
        self.assertEqual(cd.parse_description(skill_md("")).style, "missing")

    def test_no_frontmatter(self):
        self.assertEqual(cd.parse_description("# just a heading\n").style, "missing")

    def test_unclosed_frontmatter(self):
        self.assertEqual(cd.parse_description("---\ndescription: x\n").style, "missing")


class ProblemsTest(unittest.TestCase):
    def test_at_the_cap_passes(self):
        self.assertEqual(cd.problems(cd.Description("x" * cd.HOUSE_MAX, "plain")), [])

    def test_one_over_the_house_cap_fails(self):
        found = cd.problems(cd.Description("x" * (cd.HOUSE_MAX + 1), "plain"))
        self.assertEqual(len(found), 1)
        self.assertIn("house cap", found[0])

    def test_over_the_standard_limit_names_the_standard(self):
        found = cd.problems(cd.Description("x" * (cd.STANDARD_MAX + 1), "folded"))
        self.assertIn("standard's hard limit", found[0])

    def test_colon_space_in_plain_scalar_fails(self):
        found = cd.problems(cd.Description("Does this: that.", "plain"))
        self.assertTrue(any("': '" in f for f in found))

    def test_colon_space_in_folded_or_quoted_passes(self):
        for style in ("folded", "quoted", "literal"):
            self.assertEqual(cd.problems(cd.Description("Does this: that.", style)), [], style)

    def test_colon_without_space_passes(self):
        self.assertEqual(cd.problems(cd.Description("See https://example.com/a:b", "plain")), [])

    def test_missing_fails(self):
        self.assertEqual(cd.problems(cd.Description(None, "missing")), ["no description in the frontmatter"])


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def add_skill(self, name: str, description_block: str) -> Path:
        path = self.root / "skills" / name / "SKILL.md"
        path.parent.mkdir(parents=True)
        path.write_text(skill_md(description_block, name), encoding="utf-8")
        return path

    def test_clean_tree_exits_zero(self):
        self.add_skill("alpha", "description: Does alpha. Use when asked.")
        self.add_skill("beta", "description: >-\n  Does beta: folded.\n")
        code, out = run("--root", str(self.root))
        self.assertEqual(code, 0, out)
        self.assertIn("2 checked, 0 failing", out)

    def test_over_cap_skill_fails_and_is_named(self):
        self.add_skill("alpha", "description: Short.")
        self.add_skill("long", "description: " + "y" * (cd.HOUSE_MAX + 5))
        code, out = run("--root", str(self.root))
        self.assertEqual(code, 1)
        self.assertIn("skills/long/SKILL.md", out)
        self.assertIn(str(cd.HOUSE_MAX + 5), out)
        self.assertNotIn("skills/alpha/SKILL.md -", out)

    def test_colon_in_plain_scalar_fails(self):
        self.add_skill("colon", "description: Does this: that.")
        code, out = run("--root", str(self.root))
        self.assertEqual(code, 1)
        self.assertIn("plain scalar", out)

    def test_explicit_file_argument_checks_only_that_file(self):
        self.add_skill("long", "description: " + "y" * (cd.HOUSE_MAX + 1))
        ok = self.add_skill("fine", "description: Fine.")
        code, out = run("--root", str(self.root), str(ok))
        self.assertEqual(code, 0, out)
        self.assertIn("1 checked, 0 failing", out)

    def test_empty_root_exits_zero(self):
        code, out = run("--root", str(self.root))
        self.assertEqual(code, 0)
        self.assertIn("no skills found", out)


if __name__ == "__main__":
    unittest.main()
