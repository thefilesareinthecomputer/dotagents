#!/usr/bin/env python3
"""Tests for the harness_version_check.py SessionStart hook.
Target: the repo's hooks/harness_version_check.py by default; HOOK_UNDER_TEST points the run
at a station copy such as ~/.claude/hooks/harness_version_check.py (seeded per SPEC-CLAUDE-CODE.md §8).
Run: python3 tests/station-hooks/test-harness-version-check.py   (or via unittest discover)

Contract: exit 0 on every path. Runs harness-bench's `versions --quiet` at most once
per local date, decided by a stamp file written before the check, and prints a
systemMessage plus additionalContext only when that command reports something newer.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TARGET = Path(os.environ.get("HOOK_UNDER_TEST") or Path(__file__).resolve().parents[2] / "hooks" / "harness_version_check.py")

FAKE_BENCH = """import sys
from pathlib import Path
calls = Path(__file__).with_name("calls")
calls.write_text(calls.read_text() + "x" if calls.exists() else "x")
assert sys.argv[1:] == ["versions", "--quiet"], sys.argv
print(Path(__file__).with_name("reply").read_text(), end="")
"""


class TestHarnessVersionCheck(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="hvc-test-"))
        self.bench = self.tmp / "harness_bench.py"
        self.bench.write_text(FAKE_BENCH)
        (self.tmp / "reply").write_text("harness updates available: pi 1.1.0 -> 1.2.0. Re-run the egress audit.\n")
        self.stamp = self.tmp / "state" / "version-check.stamp"

    def run_hook(self, today="2026-10-13", bench=None, project=None):
        env = dict(os.environ, HARNESS_VERSION_STAMP=str(self.stamp), HARNESS_VERSION_TODAY=today,
                   HARNESS_BENCH_SCRIPT=str(bench or self.bench), HARNESS_VERSION_REPO=str(self.tmp),
                   CLAUDE_PROJECT_DIR=str(project or self.tmp))
        return subprocess.run([sys.executable, str(TARGET)], input="{}", env=env, capture_output=True,
                              text=True, timeout=30)

    def calls(self):
        f = self.tmp / "calls"
        return len(f.read_text()) if f.exists() else 0

    def test_first_run_of_the_day_reports(self):
        r = self.run_hook()
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertIn("pi 1.1.0 -> 1.2.0", out["systemMessage"])
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "SessionStart")
        self.assertEqual(self.stamp.read_text().strip(), "2026-10-13")
        self.assertEqual(self.calls(), 1)

    def test_second_run_the_same_day_is_silent_and_checks_nothing(self):
        self.run_hook()
        r = self.run_hook()
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        self.assertEqual(self.calls(), 1)

    def test_next_day_checks_again(self):
        self.run_hook(today="2026-10-13")
        r = self.run_hook(today="2026-10-14")
        self.assertIn("1.2.0", r.stdout)
        self.assertEqual(self.calls(), 2)

    def test_nothing_newer_prints_nothing(self):
        (self.tmp / "reply").write_text("")
        r = self.run_hook()
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        self.assertEqual(self.calls(), 1)

    def test_missing_bench_is_silent_and_still_stamps(self):
        r = self.run_hook(bench=self.tmp / "nope.py")
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        self.assertEqual(self.stamp.read_text().strip(), "2026-10-13")

    def test_other_projects_are_silent_and_leave_the_stamp(self):
        other = self.tmp / "other-repo"
        other.mkdir()
        r = self.run_hook(project=other)
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        self.assertFalse(self.stamp.exists())
        self.assertEqual(self.calls(), 0)
        self.assertIn("1.2.0", self.run_hook().stdout)  # the bench repo still gets today's check

    def test_no_project_dir_is_silent(self):
        env = dict(os.environ, HARNESS_VERSION_STAMP=str(self.stamp), HARNESS_BENCH_SCRIPT=str(self.bench),
                   HARNESS_VERSION_REPO=str(self.tmp))
        env.pop("CLAUDE_PROJECT_DIR", None)
        r = subprocess.run([sys.executable, str(TARGET)], input="{}", env=env, capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        self.assertFalse(self.stamp.exists())

    def test_a_hung_check_is_killed_with_its_children(self):
        tag = f"hvc-grandchild-{os.getpid()}"
        slow = self.tmp / "slow_bench.py"
        slow.write_text("import subprocess, sys, time\n"
                        f"subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)', '{tag}'])\n"
                        "time.sleep(60)\n")
        env = dict(os.environ, HARNESS_VERSION_STAMP=str(self.stamp), HARNESS_BENCH_SCRIPT=str(slow),
                   HARNESS_VERSION_REPO=str(self.tmp), CLAUDE_PROJECT_DIR=str(self.tmp),
                   HARNESS_VERSION_TIMEOUT="1")
        r = subprocess.run([sys.executable, str(TARGET)], input="{}", env=env, capture_output=True, text=True,
                           timeout=30)
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        left = subprocess.run(["pgrep", "-f", tag], capture_output=True, text=True).stdout.strip()
        self.assertEqual(left, "", "a grandchild outlived the hook's timeout")

    def test_control_characters_are_stripped(self):
        (self.tmp / "reply").write_text("harness updates available: x\x1b[31m 1 -> 2\x07\n")
        out = json.loads(self.run_hook().stdout)
        self.assertNotIn("\x1b", out["systemMessage"])
        self.assertNotIn("\x07", out["systemMessage"])


if __name__ == "__main__":
    unittest.main()
