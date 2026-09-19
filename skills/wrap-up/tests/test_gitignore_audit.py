#!/usr/bin/env python3
"""Tests for gitignore_audit.py - stdlib only.

    python3 -m unittest discover skills/wrap-up/tests

Each test builds a throwaway repository. The property that matters most is
that a path an ignore rule already covers is never reported, and that a path
no rule covers always is, tracked or not.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "gitignore_audit.py"

GIT_ENV = {
    "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "test@example.com",
    "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null",
    "PATH": "/usr/bin:/bin:/usr/local/bin",
}


class AuditCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.git("init", "-q", "-b", "main")
        self.write("README.md", "# repo\n")
        self.commit("first")

    def git(self, *args: str) -> str:
        proc = subprocess.run(["git", *args], cwd=self.repo, env=GIT_ENV,
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout

    def write(self, name: str, content: str = "x\n") -> None:
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def commit(self, message: str) -> None:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)

    def cli(self, *args: str, cwd: Path | None = None) -> tuple[int, str, str]:
        proc = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd or self.repo,
                              env=GIT_ENV, capture_output=True, text=True)
        return proc.returncode, proc.stdout, proc.stderr

    def audit(self) -> tuple[int, dict]:
        code, out, err = self.cli("audit", "--json")
        self.assertIn(code, (0, 1), err)
        return code, json.loads(out)


class TestUncovered(AuditCase):
    def test_a_clean_tree_exits_zero(self) -> None:
        code, result = self.audit()
        self.assertEqual(code, 0)
        self.assertEqual(result["uncovered"], {})

    def test_an_untracked_env_file_is_reported_as_new(self) -> None:
        self.write(".env", "TOKEN=abc\n")
        code, result = self.audit()
        self.assertEqual(code, 1)
        item = result["uncovered"][".env"]["paths"][0]
        self.assertEqual(item["path"], ".env")
        self.assertTrue(item["new"])
        self.assertFalse(item["tracked"])

    def test_a_tracked_cache_file_is_reported_as_tracked(self) -> None:
        self.write("pkg/__pycache__/mod.cpython-312.pyc")
        self.commit("oops")
        code, result = self.audit()
        self.assertEqual(code, 1)
        item = result["uncovered"]["__pycache__/"]["paths"][0]
        self.assertTrue(item["tracked"])

    def test_a_covered_path_is_not_reported(self) -> None:
        self.write(".gitignore", ".env\n")
        self.write(".env", "TOKEN=abc\n")
        code, result = self.audit()
        self.assertEqual(code, 0)
        self.assertEqual(result["uncovered"], {})

    def test_a_nested_gitignore_counts(self) -> None:
        self.write("app/.gitignore", "*.log\n")
        self.write("app/debug.log")
        code, result = self.audit()
        self.assertEqual(code, 0)

    def test_env_example_is_exempt(self) -> None:
        self.write(".env.example", "TOKEN=\n")
        code, result = self.audit()
        self.assertEqual(code, 0)

    def test_paths_group_under_the_pattern_that_covers_them(self) -> None:
        self.write("a/.DS_Store")
        self.write("b/c/.DS_Store")
        _code, result = self.audit()
        paths = [p["path"] for p in result["uncovered"][".DS_Store"]["paths"]]
        self.assertEqual(paths, ["a/.DS_Store", "b/c/.DS_Store"])

    def test_run_from_a_subdirectory_still_audits_the_whole_repo(self) -> None:
        """The gate must not under-scan because the caller's cwd is a subtree."""
        self.write(".env", "TOKEN=abc\n")
        self.write("sub/keep.md")
        code, out, err = self.cli("audit", "--json", cwd=self.repo / "sub")
        self.assertEqual(code, 1, err)
        self.assertIn(".env", json.loads(out)["uncovered"])

    def test_text_output_marks_tags(self) -> None:
        self.write("notes.log")
        code, out, _err = self.cli("audit")
        self.assertEqual(code, 1)
        self.assertIn("[new] notes.log", out)
        self.assertIn("*.log", out)


class TestDeliberateKeeps(AuditCase):
    def test_a_negated_ignored_fixture_is_not_reported(self) -> None:
        self.write("fixtures/.venv/lib/mod.py")
        self.commit("fixture")
        self.write(".gitignore", ".venv/\n!fixtures/.venv/\n")
        code, result = self.audit()
        self.assertEqual(code, 0, result)

    def test_a_negation_marks_a_keep_even_when_nothing_ignores_it(self) -> None:
        self.write("fixtures/node_modules/left/index.js")
        self.commit("fixture")
        self.write(".gitignore", "!fixtures/node_modules/\n")
        code, result = self.audit()
        self.assertEqual(code, 0, result)

    def test_a_nested_gitignore_negation_is_anchored_to_its_folder(self) -> None:
        self.write("app/fixtures/build/out.js")
        self.write("other/build/out.js")
        self.write("app/.gitignore", "!fixtures/build/\n")
        _code, result = self.audit()
        paths = [p["path"] for p in result["uncovered"]["build/"]["paths"]]
        self.assertEqual(paths, ["other/build/out.js"])


class TestTrackedButIgnored(AuditCase):
    def test_a_tracked_file_with_a_rule_is_flagged(self) -> None:
        self.write("data.sqlite")
        self.commit("add db")
        self.write(".gitignore", "*.sqlite\n")
        code, result = self.audit()
        self.assertEqual(code, 1)
        self.assertEqual(result["tracked_but_ignored"], ["data.sqlite"])
        self.assertEqual(result["uncovered"], {})


class TestAdd(AuditCase):
    def test_add_appends_and_creates_the_file(self) -> None:
        code, out, _err = self.cli("add", "__pycache__/", "*.log")
        self.assertEqual(code, 0)
        self.assertIn("__pycache__/", out)
        self.assertEqual((self.repo / ".gitignore").read_text(), "__pycache__/\n*.log\n")

    def test_add_is_idempotent(self) -> None:
        self.write(".gitignore", "*.log")  # no trailing newline
        self.cli("add", "*.log", ".env")
        self.assertEqual((self.repo / ".gitignore").read_text(), "*.log\n.env\n")
        code, out, _err = self.cli("add", ".env")
        self.assertEqual(code, 0)
        self.assertIn("nothing to add", out)

    def test_add_then_audit_is_clean(self) -> None:
        self.write("run.log")
        self.cli("add", "*.log")
        code, _result = self.audit()
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
