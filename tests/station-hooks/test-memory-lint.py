#!/usr/bin/env python3
"""Tests for the memory_lint.py PostToolUse hook.
Target: ~/.claude/hooks/memory_lint.py (seeded from SPEC-CLAUDE-CODE.md §8).
Run: python3 tests/station-hooks/test-memory-lint.py   (or via unittest discover)

Contract: deterministic violations exit 2 (return to agent); judgment checks are
advisory (exit 0); a non-memory path is ignored (exit 0); the lint fails OPEN.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent.parent  # placeholder; set below
HOOK = Path.home() / ".claude" / "hooks" / "memory_lint.py"

GOOD_MEM = """---
name: sample-fact
description: a valid repo-specific memory used by the lint tests
metadata:
  type: project
---

A repo-specific fact. Links to [[sample-fact]] (self, resolves).
"""

GOOD_INDEX = "# Memory Index\n\n- [Sample](sample-fact.md) - a valid memory\n"


def run(file_path: str) -> tuple[int, str]:
    payload = json.dumps({"tool_name": "Write", "tool_input": {"file_path": file_path}})
    p = subprocess.run([sys.executable, str(HOOK)], input=payload, capture_output=True, text=True)
    return p.returncode, p.stderr


def make_dir(tmp: Path, mem: str = GOOD_MEM, index: str | None = GOOD_INDEX, name: str = "sample-fact.md") -> Path:
    d = tmp / "projects" / "some-slug" / "memory"
    d.mkdir(parents=True)
    (d / name).write_text(mem, encoding="utf-8")
    if index is not None:
        (d / "MEMORY.md").write_text(index, encoding="utf-8")
    return d / name


class TestPasses(unittest.TestCase):
    def test_good_memory_dir_passes(self):
        with tempfile.TemporaryDirectory() as t:
            f = make_dir(Path(t))
            code, err = run(str(f))
            self.assertEqual(code, 0, err)

    def test_advisory_never_fails(self):
        """The doc-reconcile advisory always prints, on exit 0."""
        with tempfile.TemporaryDirectory() as t:
            f = make_dir(Path(t))
            code, err = run(str(f))
            self.assertEqual(code, 0)
            self.assertIn("reconcile", err)

    def test_dangling_wikilink_is_advisory_not_fail(self):
        mem = GOOD_MEM.replace("[[sample-fact]]", "[[not-a-real-memory]]")
        with tempfile.TemporaryDirectory() as t:
            f = make_dir(Path(t), mem=mem)
            code, err = run(str(f))
            self.assertEqual(code, 0, err)
            self.assertIn("dangling", err)


class TestDeterministicFails(unittest.TestCase):
    def _fail(self, **kw):
        with tempfile.TemporaryDirectory() as t:
            f = make_dir(Path(t), **kw)
            return run(str(f))

    def test_missing_pointer_fails(self):
        code, err = self._fail(index="# Memory Index\n\n(empty)\n")
        self.assertEqual(code, 2)
        self.assertIn("no pointer", err)

    def test_missing_index_fails(self):
        code, err = self._fail(index=None)
        self.assertEqual(code, 2)
        self.assertIn("MEMORY.md", err)

    def test_no_frontmatter_fails(self):
        code, err = self._fail(mem="just a body, no frontmatter\n")
        self.assertEqual(code, 2)
        self.assertIn("frontmatter", err)

    def test_bad_type_fails(self):
        mem = GOOD_MEM.replace("type: project", "type: banana")
        code, err = self._fail(mem=mem)
        self.assertEqual(code, 2)
        self.assertIn("banana", err)

    def test_name_mismatch_fails(self):
        mem = GOOD_MEM.replace("name: sample-fact", "name: wrong-name")
        code, err = self._fail(mem=mem)
        self.assertEqual(code, 2)
        self.assertIn("does not match filename", err)

    def test_dead_pointer_fails(self):
        idx = GOOD_INDEX + "- [Ghost](ghost.md) - points at nothing\n"
        code, err = self._fail(index=idx)
        self.assertEqual(code, 2)
        self.assertIn("does not resolve", err)


class TestScopeAndSafety(unittest.TestCase):
    def test_non_memory_path_ignored(self):
        with tempfile.TemporaryDirectory() as t:
            f = Path(t) / "notes.md"
            f.write_text("x")
            code, err = run(str(f))
            self.assertEqual(code, 0)
            self.assertEqual(err, "")

    def test_garbage_payload_fails_open(self):
        p = subprocess.run([sys.executable, str(HOOK)], input="not json", capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)

    def test_empty_payload_fails_open(self):
        p = subprocess.run([sys.executable, str(HOOK)], input="{}", capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)


if __name__ == "__main__":
    unittest.main()
