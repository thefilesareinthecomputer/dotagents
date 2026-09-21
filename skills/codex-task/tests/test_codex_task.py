#!/usr/bin/env python3
"""Tests for skills/codex-task/scripts/codex_task.py.

Stdlib unittest, synthetic fixture repo, fake `codex` binary. No network, no
real Codex. Run: python3 -m unittest discover -s skills/codex-task/tests -v
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "codex_task.py"
FAKE = HERE / "fake_codex.py"


def git(args, cwd):
    return subprocess.run(["git", *args], cwd=str(cwd), text=True, capture_output=True, check=True)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="codex-task-test-"))
        self.repo = self.tmp / "repo"
        (self.repo / "src").mkdir(parents=True)
        (self.repo / "src" / "allowed.py").write_text("def f():\n    return 1\n")
        (self.repo / "src" / "other.py").write_text("ORIG = True\n")
        (self.repo / "README.md").write_text("orig\n")
        git(["init", "-q", "-b", "main"], self.repo)
        git(["-c", "user.email=t@t", "-c", "user.name=t", "add", "-A"], self.repo)
        git(["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "init"], self.repo)
        self.state = self.tmp / "state"
        self.brief = self.tmp / "brief.md"
        self.brief.write_text("Make f return 2.\n")
        self.real_home = self.tmp / "real-codex-home"
        self.real_home.mkdir()
        (self.real_home / "auth.json").write_text('{"fake": true}')
        (self.real_home / "config.toml").write_text('model = "x"\n')
        self.env = dict(os.environ, CODEX_TASK_BIN=str(FAKE), CODEX_TASK_STATE=str(self.state),
                        CODEX_TASK_REAL_HOME=str(self.real_home),
                        TMPDIR="/nonexistent-tmpdir-for-tests", FAKE_CODEX_ARGV=str(self.tmp / "argv.json"))

    def tearDown(self):
        for d in self.state.glob("*/ws"):
            subprocess.run(["git", "worktree", "remove", "--force", str(d)], cwd=str(self.repo), capture_output=True)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_cmd(self, *args, mode="clean", timeout=None):
        env = dict(self.env, FAKE_CODEX_MODE=mode)
        return subprocess.run([sys.executable, str(SCRIPT), *args], env=env, text=True,
                              capture_output=True, timeout=timeout or 60)

    def run_task(self, allow=("src/allowed.py", "src/new_allowed.py"), mode="clean", extra=()):
        args = ["run", "--repo", str(self.repo), "--brief", str(self.brief), *extra]
        for a in allow:
            args += ["--allow", a]
        return self.run_cmd(*args, mode=mode)

    def report(self):
        runs = sorted(p for p in self.state.iterdir() if p.is_dir() and p.name != "home")
        self.assertEqual(len(runs), 1, runs)
        return json.loads((runs[0] / "report.json").read_text()), runs[0]

    def repo_snapshot(self):
        return {p.relative_to(self.repo).as_posix(): p.read_bytes()
                for p in self.repo.rglob("*") if p.is_file() and ".git" not in p.parts}


class TestRunAndApply(Base):
    def test_out_of_scope_edits_are_dropped_and_reported(self):
        r = self.run_task(mode="edit")
        self.assertEqual(r.returncode, 3, r.stderr)
        rpt, run_dir = self.report()
        self.assertEqual(rpt["changed_in_scope"], ["src/allowed.py", "src/new_allowed.py"])
        self.assertEqual(rpt["changed_out_of_scope"], ["README.md", "src/other.py"])
        patch = (run_dir / "allowed.patch").read_text()
        self.assertIn("src/allowed.py", patch)
        self.assertIn("src/new_allowed.py", patch)
        self.assertNotIn("other.py", patch)
        self.assertNotIn("README.md", patch)
        self.assertTrue((run_dir / "dropped.patch").exists())
        self.assertEqual(rpt["usage"]["input_tokens"], 10)
        self.assertEqual(rpt["result"]["summary"], "fake edit")

    def test_apply_changes_only_allowed_files(self):
        self.assertEqual(self.run_task(mode="edit").returncode, 3)
        rpt, _ = self.report()
        before = self.repo_snapshot()
        r = self.run_cmd("apply", "--run", rpt["run_id"])
        self.assertEqual(r.returncode, 0, r.stderr)
        after = self.repo_snapshot()
        self.assertEqual(after["src/allowed.py"], b"def f():\n    return 2\n")
        self.assertEqual(after["src/new_allowed.py"], b"NEW = True\n")
        for k, v in before.items():
            if k not in ("src/allowed.py", "src/new_allowed.py"):
                self.assertEqual(after[k], v, k)

    def test_apply_refilters_even_if_patch_was_edited(self):
        self.assertEqual(self.run_task(mode="edit").returncode, 3)
        rpt, run_dir = self.report()
        # Smuggle the dropped hunks into allowed.patch.
        p = run_dir / "allowed.patch"
        p.write_text(p.read_text() + (run_dir / "dropped.patch").read_text())
        r = self.run_cmd("apply", "--run", rpt["run_id"])
        self.assertEqual(r.returncode, 0, r.stderr)
        after = self.repo_snapshot()
        self.assertEqual(after["src/other.py"], b"ORIG = True\n")
        self.assertEqual(after["README.md"], b"orig\n")
        self.assertEqual(after["src/allowed.py"], b"def f():\n    return 2\n")

    def test_committed_changes_in_worktree_are_still_harvested(self):
        r = self.run_task(mode="commit")
        self.assertEqual(r.returncode, 3, r.stderr)
        rpt, run_dir = self.report()
        self.assertEqual(rpt["changed_in_scope"], ["src/allowed.py", "src/new_allowed.py"])
        self.assertEqual(rpt["changed_out_of_scope"], ["README.md", "src/other.py"])
        self.assertIn("return 2", (run_dir / "allowed.patch").read_text())

    def test_clean_run_exits_zero(self):
        r = self.run_task(mode="clean")
        self.assertEqual(r.returncode, 0, r.stderr)
        rpt, _ = self.report()
        self.assertEqual(rpt["changed_out_of_scope"], [])

    def test_apply_refuses_when_head_moved(self):
        self.assertEqual(self.run_task().returncode, 0)
        rpt, _ = self.report()
        (self.repo / "README.md").write_text("moved\n")
        git(["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qam", "move"], self.repo)
        r = self.run_cmd("apply", "--run", rpt["run_id"])
        self.assertEqual(r.returncode, 2)
        self.assertIn("HEAD moved", r.stderr)
        r = self.run_cmd("apply", "--run", rpt["run_id"], "--force-base")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_apply_refuses_dirty_allowed_file(self):
        self.assertEqual(self.run_task().returncode, 0)
        rpt, _ = self.report()
        (self.repo / "src" / "allowed.py").write_text("dirty\n")
        r = self.run_cmd("apply", "--run", rpt["run_id"])
        self.assertEqual(r.returncode, 2)
        self.assertIn("uncommitted", r.stderr)


class TestValidation(Base):
    def assert_rejected(self, allow, needle):
        r = self.run_task(allow=[allow])
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn(needle, r.stderr)
        self.assertFalse(self.state.exists() and any(self.state.iterdir()), "no run dir should exist")

    def test_dotdot_rejected(self):
        self.assert_rejected("src/../../etc/passwd", "escapes")

    def test_absolute_outside_rejected(self):
        self.assert_rejected("/etc/passwd", "outside")

    def test_git_dir_rejected(self):
        self.assert_rejected(".git/hooks/pre-commit", ".git/")

    def test_symlink_rejected(self):
        os.symlink(self.tmp, self.repo / "link")
        self.assert_rejected("link/x.py", "symlink")

    def test_glob_rejected(self):
        self.assert_rejected("src/*.py", "glob")

    def test_directory_rejected(self):
        self.assert_rejected("src", "directory")

    def test_state_dir_under_tmp_rejected(self):
        env = dict(self.env, CODEX_TASK_STATE="/tmp/codex-task-x", FAKE_CODEX_MODE="clean")
        r = subprocess.run([sys.executable, str(SCRIPT), "run", "--repo", str(self.repo),
                            "--allow", "src/allowed.py", "--brief", str(self.brief)],
                           env=env, text=True, capture_output=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("/tmp", r.stderr)

    def test_state_dir_under_tmpdir_env_rejected(self):
        env = dict(self.env, TMPDIR=str(self.tmp), FAKE_CODEX_MODE="clean")
        r = subprocess.run([sys.executable, str(SCRIPT), "run", "--repo", str(self.repo),
                            "--allow", "src/allowed.py", "--brief", str(self.brief)],
                           env=env, text=True, capture_output=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("TMPDIR", r.stderr)


class TestProcessControl(Base):
    def test_timeout_kills_process_group(self):
        r = self.run_task(mode="child-sleep", extra=["--timeout", "30"])
        # --timeout minimum is 30 s; shorten via the fake's own clock instead.
        self.assertIn(r.returncode, (5,), r.stderr)

    def test_fast_timeout(self):
        env = dict(self.env, FAKE_CODEX_MODE="sleep", FAKE_CODEX_SLEEP="120")
        r = subprocess.run([sys.executable, str(SCRIPT), "run", "--repo", str(self.repo),
                            "--allow", "src/allowed.py", "--brief", str(self.brief), "--timeout", "30"],
                           env=env, text=True, capture_output=True, timeout=70)
        self.assertEqual(r.returncode, 5, r.stderr)
        rpt, _ = self.report()
        self.assertEqual(rpt["exit_reason"], "timeout")

    def test_undrained_stdin_still_times_out(self):
        self.brief.write_text("x" * 300_000)  # well past the pipe buffer
        env = dict(self.env, FAKE_CODEX_MODE="bigprompt")
        r = subprocess.run([sys.executable, str(SCRIPT), "run", "--repo", str(self.repo),
                            "--allow", "src/allowed.py", "--brief", str(self.brief), "--timeout", "30"],
                           env=env, text=True, capture_output=True, timeout=70)
        self.assertEqual(r.returncode, 5, r.stderr)

    def test_noread_stdin_does_not_hang(self):
        r = self.run_task(mode="noread")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_codex_error_exit_four(self):
        r = self.run_task(mode="error")
        self.assertEqual(r.returncode, 4, r.stderr)
        rpt, _ = self.report()
        self.assertIn("fake failure", rpt["codex_errors"][0])


class TestArgv(Base):
    def test_locked_flags_present_and_no_danger(self):
        self.assertEqual(self.run_task().returncode, 0)
        argv = json.loads((self.tmp / "argv.json").read_text())["argv"]
        joined = " ".join(argv)
        for bad in ("--dangerously-", "danger-full-access", "network_access=true"):
            self.assertNotIn(bad, joined)
        for must in ("--ephemeral", "--ignore-user-config", "workspace-write",
                     "sandbox_workspace_write.network_access=false",
                     "sandbox_workspace_write.exclude_slash_tmp=true",
                     "sandbox_workspace_write.exclude_tmpdir_env_var=true",
                     'approval_policy="never"', "analytics.enabled=false",
                     "shell_environment_policy.include_only=",
                     "features.memories=false", "--output-schema"):
            self.assertIn(must, joined, must)
        self.assertEqual(argv[-1], "-")
        ws = argv[argv.index("-C") + 1]
        self.assertTrue(ws.startswith(str(self.state.resolve())), ws)
        self.assertNotEqual(Path(ws).resolve(), self.repo.resolve())

    def test_isolated_codex_home_with_linked_auth(self):
        self.assertEqual(self.run_task().returncode, 0)
        seen = json.loads((self.tmp / "argv.json").read_text())
        home = Path(seen["codex_home"])
        self.assertEqual(home, (self.state / "home").resolve())
        self.assertTrue((home / "auth.json").is_symlink())
        self.assertEqual((home / "auth.json").resolve(), (self.real_home / "auth.json").resolve())
        self.assertFalse((home / "config.toml").exists())
        self.assertEqual((self.real_home / "config.toml").read_text(), 'model = "x"\n')
        rpt, _ = self.report()
        self.assertEqual(rpt["warnings"], [])

    def test_missing_auth_fails_before_spawn(self):
        (self.real_home / "auth.json").unlink()
        r = self.run_task()
        self.assertEqual(r.returncode, 2)
        self.assertIn("codex login", r.stderr)
        self.assertFalse((self.tmp / "argv.json").exists())

    def test_replaced_auth_symlink_is_relinked_and_warned(self):
        self.assertEqual(self.run_task().returncode, 0)
        link = self.state / "home" / "auth.json"
        link.unlink()
        link.write_text("{}")
        shutil.rmtree(next(p for p in self.state.iterdir() if p.name != "home"))
        self.assertEqual(self.run_task().returncode, 0)
        self.assertTrue(link.is_symlink())
        rpt, _ = self.report()
        self.assertTrue(any("relinked" in w for w in rpt["warnings"]))

    def test_worktree_never_under_tmp(self):
        self.assertEqual(self.run_task().returncode, 0)
        rpt, run_dir = self.report()
        for banned in ("/tmp", "/private/tmp"):
            self.assertFalse(str(run_dir).startswith(banned))

    def child_env(self):
        return json.loads((self.tmp / "argv.json").read_text())["env"]

    def test_child_env_is_scrubbed_to_the_allowlist(self):
        # Codex does not apply its own shell_environment_policy.include_only
        # (verified live at 0.155.1), so the scrub has to happen here. Anything
        # outside the allowlist must not reach the Codex process at all.
        secret = "cv-scrub-canary-value"
        env = dict(self.env, CLAUDE_CODE_MESSAGING_TOKEN=secret,
                   COPILOT_DEBUG_NONCE=secret, AWS_SESSION_TOKEN=secret,
                   GITHUB_TOKEN=secret, SOME_UNRELATED_VAR=secret)
        args = ["run", "--repo", str(self.repo), "--brief", str(self.brief),
                "--allow", "src/allowed.py", "--allow", "src/new_allowed.py"]
        r = subprocess.run([sys.executable, str(SCRIPT), *args],
                           env=dict(env, FAKE_CODEX_MODE="clean"), text=True,
                           capture_output=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        seen = self.child_env()
        for leaked in ("CLAUDE_CODE_MESSAGING_TOKEN", "COPILOT_DEBUG_NONCE",
                       "AWS_SESSION_TOKEN", "GITHUB_TOKEN", "SOME_UNRELATED_VAR"):
            self.assertNotIn(leaked, seen, f"{leaked} reached Codex")
        self.assertNotIn(secret, json.dumps(seen))

    def test_child_env_keeps_what_codex_needs(self):
        self.assertEqual(self.run_task().returncode, 0)
        seen = self.child_env()
        for keep in ("HOME", "PATH", "CODEX_HOME"):
            self.assertIn(keep, seen, keep)
        self.assertEqual(seen["HOME"], os.environ["HOME"])
        self.assertEqual(seen["PATH"], os.environ["PATH"])
        self.assertEqual(Path(seen["CODEX_HOME"]), (self.state / "home").resolve())

    def test_brief_carries_allowlist_and_task(self):
        self.assertEqual(self.run_task().returncode, 0)
        _, run_dir = self.report()
        brief = (run_dir / "brief.md").read_text()
        self.assertIn("Make f return 2.", brief)
        self.assertIn("- src/allowed.py", brief)
        self.assertIn("- src/new_allowed.py", brief)


class TestClean(Base):
    def test_clean_removes_run_and_worktree(self):
        self.assertEqual(self.run_task().returncode, 0)
        rpt, run_dir = self.report()
        r = self.run_cmd("clean", "--run", rpt["run_id"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(run_dir.exists())
        self.assertNotIn(str(run_dir), git(["worktree", "list"], self.repo).stdout)


if __name__ == "__main__":
    unittest.main()
