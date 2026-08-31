#!/usr/bin/env python3
"""Tests for closeout_state.py - stdlib only.

    python3 -m unittest discover skills/wrap-up/tests

Each test builds a throwaway repository, because the thing under test is what
git says has happened since a stamp. Identity is passed per-invocation so the
suite does not depend on, or disturb, the station's git config.

The property that matters most is the degradation: a ledger that is missing,
truncated or from another version must report "not covered", never "current".
Losing it costs one redundant pass; trusting a bad one costs an unreviewed diff.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "closeout_state.py"

GIT_ENV = {
    "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "test@example.com",
    "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null",
    "PATH": "/usr/bin:/bin:/usr/local/bin",
}


class StateCase(unittest.TestCase):
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

    def write(self, name: str, content: str) -> None:
        (self.repo / name).write_text(content, encoding="utf-8")

    def commit(self, message: str) -> None:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)

    def cli(self, *args: str) -> tuple[int, str, str]:
        proc = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=self.repo,
                              env=GIT_ENV, capture_output=True, text=True)
        return proc.returncode, proc.stdout, proc.stderr

    def status(self) -> dict:
        code, out, err = self.cli("status", "--json")
        self.assertEqual(code, 0, err)
        return json.loads(out)["steps"]


class TestCoverage(StateCase):
    def test_nothing_is_covered_before_the_first_record(self) -> None:
        self.assertEqual(self.status()["reflect"]["state"], "uncovered")

    def test_a_recorded_step_is_current_when_nothing_moves(self) -> None:
        self.cli("record", "security-review", "--tier", "A", "--notes", "clean")
        entry = self.status()["security-review"]
        self.assertEqual(entry["state"], "current")
        self.assertEqual(entry["entry"]["tier"], "A")
        self.assertEqual(entry["entry"]["notes"], "clean")

    def test_a_new_commit_makes_the_step_stale(self) -> None:
        self.cli("record", "security-review")
        self.write("more.md", "# more\n")
        self.commit("second")
        entry = self.status()["security-review"]
        self.assertEqual(entry["state"], "stale")
        self.assertEqual(len(entry["commits"]), 1)

    def test_an_uncommitted_edit_makes_the_step_stale(self) -> None:
        self.cli("record", "notes")
        self.write("README.md", "# repo, edited\n")
        entry = self.status()["notes"]
        self.assertEqual(entry["state"], "stale")
        self.assertTrue(entry["tree_changed"])
        self.assertEqual(entry["commits"], [])

    def test_a_new_untracked_file_makes_the_step_stale(self) -> None:
        self.cli("record", "notes")
        self.write("untracked.md", "# new\n")
        self.assertEqual(self.status()["notes"]["state"], "stale")

    def test_steps_are_tracked_independently(self) -> None:
        self.cli("record", "security-review")
        self.write("more.md", "# more\n")
        self.commit("second")
        self.cli("record", "reflect")
        states = self.status()
        self.assertEqual(states["security-review"]["state"], "stale")
        self.assertEqual(states["reflect"]["state"], "current")

    def test_status_names_the_range_a_rereview_should_read(self) -> None:
        self.cli("record", "security-review")
        short = self.git("rev-parse", "--short", "HEAD").strip()[:7]
        self.write("more.md", "# more\n")
        self.commit("second")
        code, out, err = self.cli("status")
        self.assertEqual(code, 0, err)
        self.assertIn(f"{short}..HEAD", out)


class TestDegradation(StateCase):
    def ledger(self) -> Path:
        return Path(self.git("rev-parse", "--absolute-git-dir").strip()) / "closeout-state.json"

    def test_a_corrupt_ledger_reports_uncovered(self) -> None:
        self.cli("record", "reflect")
        self.ledger().write_text("{not json", encoding="utf-8")
        self.assertEqual(self.status()["reflect"]["state"], "uncovered")

    def test_a_ledger_from_another_version_reports_uncovered(self) -> None:
        self.cli("record", "reflect")
        self.ledger().write_text(json.dumps({"version": 99, "steps": {"reflect": {}}}),
                                 encoding="utf-8")
        self.assertEqual(self.status()["reflect"]["state"], "uncovered")

    def test_a_vanished_base_commit_reports_uncovered_not_current(self) -> None:
        """A base that cannot be resolved says nothing about what was covered."""
        self.cli("record", "security-review")
        data = json.loads(self.ledger().read_text(encoding="utf-8"))
        data["steps"]["security-review"]["head"] = "0" * 40
        self.ledger().write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(self.status()["security-review"]["state"], "uncovered")

    def test_reset_forgets_everything(self) -> None:
        self.cli("record", "reflect")
        self.cli("reset")
        self.assertEqual(self.status()["reflect"]["state"], "uncovered")

    def test_an_unknown_step_is_rejected(self) -> None:
        code, _out, err = self.cli("record", "publish")
        self.assertEqual(code, 2)
        self.assertIn("invalid choice", err)


class TestStaysOutOfTheTree(StateCase):
    def test_the_ledger_never_appears_in_git_status(self) -> None:
        self.cli("record", "commit", "--notes", "one commit, pushed")
        self.assertEqual(self.git("status", "--porcelain").strip(), "")

    def test_the_ledger_lives_in_the_git_directory(self) -> None:
        self.cli("record", "inbox")
        self.assertTrue((self.repo / ".git" / "closeout-state.json").is_file())


if __name__ == "__main__":
    unittest.main()
