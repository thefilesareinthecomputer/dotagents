#!/usr/bin/env python3
"""Tests for the skill_description_lint.py PostToolUse hook.
Target: ~/.claude/hooks/skill_description_lint.py (seeded from SPEC-CLAUDE-CODE.md §8).
Run: python3 tests/station-hooks/test-skill-description-lint.py

Contract: a SKILL.md whose description breaks the cap or the colon rule exits 2
with the reason on stderr; a clean SKILL.md, any other file, and fixture paths
exit 0; a missing checker or unreadable payload fails OPEN (exit 0).
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path.home() / ".claude" / "hooks" / "skill_description_lint.py"
CHECKER = Path(__file__).resolve().parents[2] / "skills" / "skill-authoring" / "scripts" / "check_descriptions.py"


def run(file_path: str, checker: Path | None = CHECKER, raw: str | None = None) -> tuple[int, str]:
    env = dict(os.environ)
    env["SKILL_DESCRIPTION_CHECKER"] = str(checker) if checker else "/nonexistent/check_descriptions.py"
    payload = raw if raw is not None else json.dumps({"tool_name": "Edit", "tool_input": {"file_path": file_path}})
    p = subprocess.run([sys.executable, str(HOOK)], input=payload, capture_output=True, text=True, env=env, timeout=30)
    return p.returncode, p.stderr


def skill(description: str) -> str:
    return f"---\nname: example\ndescription: {description}\n---\n\n# example\n"


class SkillDescriptionLintTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "skills" / "example"
        self.dir.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, text: str, name: str = "SKILL.md", where: Path | None = None) -> Path:
        path = (where or self.dir) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_clean_skill_passes(self):
        code, err = run(str(self.write(skill("Does a thing. Use when asked."))))
        self.assertEqual((code, err), (0, ""))

    def test_over_cap_exits_2_with_length(self):
        code, err = run(str(self.write(skill("x" * 805))))
        self.assertEqual(code, 2)
        self.assertIn("805 characters", err)
        self.assertIn("house cap", err)

    def test_colon_in_plain_scalar_exits_2(self):
        code, err = run(str(self.write(skill("Runs at two moments: before and after."))))
        self.assertEqual(code, 2)
        self.assertIn("plain scalar", err)

    def test_folded_block_with_colon_passes(self):
        text = "---\nname: example\ndescription: >-\n  Runs at two moments: before and after.\n---\n"
        code, _ = run(str(self.write(text)))
        self.assertEqual(code, 0)

    def test_other_markdown_is_ignored(self):
        code, _ = run(str(self.write(skill("x" * 900), name="README.md")))
        self.assertEqual(code, 0)

    def test_fixture_paths_are_skipped(self):
        where = Path(self.tmp.name) / "skills" / "example" / "tests" / "fixtures" / "bad"
        code, _ = run(str(self.write(skill("x" * 900), where=where)))
        self.assertEqual(code, 0)

    def test_missing_checker_fails_open(self):
        code, _ = run(str(self.write(skill("x" * 900))), checker=None)
        self.assertEqual(code, 0)

    def test_garbage_payload_fails_open(self):
        code, _ = run("", raw="not json")
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
