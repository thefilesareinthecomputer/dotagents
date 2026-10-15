#!/usr/bin/env python3
"""Tests for skills/antigravity-task/scripts/antigravity_task.py.

Stdlib unittest, synthetic fixture repo, a fake `agy` binary and a fake
`sandbox-exec` that records the profile and runs the command unconfined. One test
runs the generated profile under the real sandbox-exec when the host has it.
Run: python3 -m unittest discover -s skills/antigravity-task/tests -v
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "antigravity_task.py"
FAKE = HERE / "fake_agy.py"
FAKE_SB = HERE / "fake_sandbox.py"
REAL_SB = Path("/usr/bin/sandbox-exec")


def git(args, cwd):
    return subprocess.run(["git", *args], cwd=str(cwd), text=True, capture_output=True, check=True)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="agy-task-test-"))
        self.repo = self.tmp / "repo"
        (self.repo / "src").mkdir(parents=True)
        (self.repo / "src" / "allowed.py").write_text("def f():\n    return 1\n")
        (self.repo / "src" / "other.py").write_text("ORIG = True\n")
        (self.repo / "README.md").write_text("orig\n")
        git(["init", "-q", "-b", "main"], self.repo)
        git(["-c", "user.email=t@t", "-c", "user.name=t", "add", "-A"], self.repo)
        git(["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "init"], self.repo)
        # The state dir must sit outside the user's temp tree, which the sandbox allows
        # writes to, so the fixture puts it under ~/.cache and removes it in tearDown.
        self.state = Path.home() / ".cache" / f"agy-task-test-{self.tmp.name}"
        self.brief = self.tmp / "brief.md"
        self.brief.write_text("Make f return 2.\n")
        self.agent_home = self.tmp / "dot-gemini"
        (self.agent_home / "antigravity-cli").mkdir(parents=True)
        (self.agent_home / "antigravity-cli" / "settings.json").write_text(json.dumps({"permissions": {"allow": ["write_file(*)"]}}))
        self.env = dict(os.environ, ANTIGRAVITY_TASK_TEST="1", ANTIGRAVITY_TASK_BIN=str(FAKE), ANTIGRAVITY_TASK_SANDBOX_BIN=str(FAKE_SB),
                        ANTIGRAVITY_TASK_STATE=str(self.state), ANTIGRAVITY_TASK_AGENT_HOME=str(self.agent_home),
                        TMPDIR="/nonexistent-tmpdir-for-tests",
                        FAKE_AGY_ARGV=str(self.tmp / "argv.json"),
                        FAKE_SANDBOX_RECORD=str(self.tmp / "profile.sb"))

    def tearDown(self):
        for d in self.state.glob("*/ws"):
            subprocess.run(["git", "worktree", "remove", "--force", str(d)], cwd=str(self.repo), capture_output=True)
        shutil.rmtree(self.tmp, ignore_errors=True)
        shutil.rmtree(self.state, ignore_errors=True)

    def run_cmd(self, *args, mode="clean", timeout=None, env_extra=None):
        env = dict(self.env, FAKE_AGY_MODE=mode, **(env_extra or {}))
        return subprocess.run([sys.executable, str(SCRIPT), *args], env=env, text=True,
                              capture_output=True, timeout=timeout or 60)

    def run_task(self, allow=("src/allowed.py", "src/new_allowed.py"), mode="clean", extra=()):
        args = ["run", "--repo", str(self.repo), "--brief", str(self.brief), *extra]
        for a in allow:
            args += ["--allow", a]
        return self.run_cmd(*args, mode=mode)

    def report(self):
        runs = sorted(p for p in self.state.iterdir() if p.is_dir())
        self.assertEqual(len(runs), 1, runs)
        return json.loads((runs[0] / "report.json").read_text()), runs[0]

    def repo_snapshot(self):
        return {p.relative_to(self.repo).as_posix(): p.read_bytes()
                for p in self.repo.rglob("*") if p.is_file() and ".git" not in p.parts}

    def seen(self):
        return json.loads((self.tmp / "argv.json").read_text())


class TestRunAndApply(Base):
    def test_out_of_scope_edits_are_dropped_and_reported(self):
        r = self.run_task(mode="edit")
        self.assertEqual(r.returncode, 3, r.stderr)
        rpt, run_dir = self.report()
        self.assertEqual(rpt["changed_in_scope"], ["src/allowed.py", "src/new_allowed.py"])
        self.assertEqual(rpt["changed_out_of_scope"], ["README.md", "src/other.py"])
        self.assertNotIn("other.py", (run_dir / "allowed.patch").read_text())
        self.assertTrue((run_dir / "dropped.patch").exists())
        self.assertEqual(rpt["usage"]["input_tokens"], 10)
        self.assertEqual(rpt["result"]["summary"], "fake edit")
        self.assertEqual(rpt["conversation_id"], "fake-conv")

    def test_apply_changes_only_allowed_files(self):
        self.assertEqual(self.run_task(mode="edit").returncode, 3)
        rpt, _ = self.report()
        before = self.repo_snapshot()
        self.assertEqual(self.run_cmd("apply", "--run", rpt["run_id"]).returncode, 0)
        after = self.repo_snapshot()
        self.assertEqual(after["src/allowed.py"], b"def f():\n    return 2\n")
        for k, v in before.items():
            if k not in ("src/allowed.py", "src/new_allowed.py"):
                self.assertEqual(after[k], v, k)

    def test_apply_refilters_even_if_patch_was_edited(self):
        self.assertEqual(self.run_task(mode="edit").returncode, 3)
        rpt, run_dir = self.report()
        p = run_dir / "allowed.patch"
        p.write_text(p.read_text() + (run_dir / "dropped.patch").read_text())
        self.assertEqual(self.run_cmd("apply", "--run", rpt["run_id"]).returncode, 0)
        self.assertEqual(self.repo_snapshot()["src/other.py"], b"ORIG = True\n")

    def test_committed_changes_in_worktree_are_still_harvested(self):
        r = self.run_task(mode="commit")
        self.assertEqual(r.returncode, 3, r.stderr)
        rpt, run_dir = self.report()
        self.assertIn("return 2", (run_dir / "allowed.patch").read_text())

    def test_clean_run_exits_zero(self):
        r = self.run_task(mode="clean")
        self.assertEqual(r.returncode, 0, r.stderr)
        rpt, run_dir = self.report()
        self.assertEqual(rpt["warnings"], [])
        self.assertIn("I made the change.", (run_dir / "result.md").read_text())

    def test_read_only_run_uses_plan_mode_and_applies_nothing(self):
        r = self.run_cmd("run", "--repo", str(self.repo), "--brief", str(self.brief), "--read-only", mode="readonly")
        self.assertEqual(r.returncode, 0, r.stderr)
        rpt, run_dir = self.report()
        self.assertTrue(rpt["read_only"])
        self.assertEqual(rpt["result"]["summary"], "answered")
        argv = self.seen()["argv"]
        self.assertEqual(argv[argv.index("--mode") + 1], "plan")
        self.assertNotIn("--disable-slash-commands", argv)
        self.assertNotIn(str((run_dir / "ws").resolve()), (self.tmp / "profile.sb").read_text())
        r = self.run_cmd("apply", "--run", rpt["run_id"])
        self.assertIn("read-only", r.stdout)

    def test_headless_denial_is_an_error_not_a_success(self):
        r = self.run_task(mode="denied")
        self.assertEqual(r.returncode, 4, r.stderr)
        rpt, _ = self.report()
        self.assertTrue(any("empty response" in e for e in rpt["agent_errors"]))

    def test_missing_permissions_block_warns_in_write_mode(self):
        (self.agent_home / "antigravity-cli" / "settings.json").write_text(json.dumps({"colorScheme": "x"}))
        self.assertEqual(self.run_task().returncode, 0)
        rpt, _ = self.report()
        self.assertTrue(any("permissions" in w for w in rpt["warnings"]))

    def test_apply_refuses_when_head_moved(self):
        self.assertEqual(self.run_task().returncode, 0)
        rpt, _ = self.report()
        (self.repo / "README.md").write_text("moved\n")
        git(["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qam", "move"], self.repo)
        self.assertEqual(self.run_cmd("apply", "--run", rpt["run_id"]).returncode, 2)
        self.assertEqual(self.run_cmd("apply", "--run", rpt["run_id"], "--force-base").returncode, 0)


class TestValidation(Base):
    def assert_rejected(self, allow, needle):
        r = self.run_task(allow=[allow])
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn(needle, r.stderr)
        self.assertFalse(self.state.exists() and any(self.state.iterdir()))

    def test_dotdot_rejected(self):
        self.assert_rejected("src/../../etc/passwd", "escapes")

    def test_absolute_outside_rejected(self):
        self.assert_rejected("/etc/passwd", "outside")

    def test_git_dir_rejected(self):
        self.assert_rejected(".git/hooks/pre-commit", ".git/")

    def test_symlink_rejected(self):
        os.symlink(self.tmp, self.repo / "link")
        self.assert_rejected("link/x.py", "symlink")

    def test_glob_and_directory_rejected(self):
        self.assert_rejected("src/*.py", "glob")

    def test_no_allowlist_without_read_only_rejected(self):
        r = self.run_cmd("run", "--repo", str(self.repo), "--brief", str(self.brief))
        self.assertEqual(r.returncode, 2)
        self.assertIn("--read-only", r.stderr)

    def test_bad_effort_rejected(self):
        r = self.run_task(extra=["--effort", "ultra"])
        self.assertEqual(r.returncode, 2)
        self.assertIn("effort", r.stderr)

    def test_state_dir_under_tmp_rejected(self):
        r = self.run_cmd("run", "--repo", str(self.repo), "--allow", "src/allowed.py", "--brief", str(self.brief),
                         env_extra={"ANTIGRAVITY_TASK_STATE": "/tmp/agy-task-x"})
        self.assertEqual(r.returncode, 2)

    def test_missing_sandbox_binary_refuses_before_worktree(self):
        r = self.run_cmd("run", "--repo", str(self.repo), "--allow", "src/allowed.py", "--brief", str(self.brief),
                         env_extra={"ANTIGRAVITY_TASK_SANDBOX_BIN": str(self.tmp / "no-such-sandbox")})
        self.assertEqual(r.returncode, 2)
        self.assertIn("sandbox", r.stderr)


class TestProcessControl(Base):
    def test_normal_exit_kills_a_surviving_child(self):
        tag = f"antigravity-task-orphan-{os.getpid()}-{time.time_ns()}"
        self.env["FAKE_AGY_ORPHAN"] = tag
        r = self.run_task()
        self.assertEqual(r.returncode, 0, r.stderr)
        out = subprocess.run(["pgrep", "-f", tag], capture_output=True, text=True)
        self.assertEqual(out.stdout.strip(), "", "a child outlived the agent's normal exit")

    def test_timeout_kills_process_group(self):
        r = self.run_task(mode="child-sleep", extra=["--timeout", "30"])
        self.assertEqual(r.returncode, 5, r.stderr)
        time.sleep(1)
        out = subprocess.run(["pgrep", "-f", "fake_agy.py"], capture_output=True, text=True)
        self.assertEqual(out.stdout.strip(), "", "a child survived the timeout")

    def test_agent_error_exit_four(self):
        r = self.run_task(mode="error")
        self.assertEqual(r.returncode, 4, r.stderr)
        rpt, _ = self.report()
        self.assertIn("fake failure", rpt["agent_errors"][0])


class TestArgvAndSandbox(Base):
    def test_locked_flags_and_no_forbidden_argv(self):
        self.assertEqual(self.run_task(extra=["--effort", "xhigh"]).returncode, 0)
        argv = self.seen()["argv"]
        joined = " ".join(argv)
        for bad in ("--dangerously-", "--remote-control", "--continue", "--conversation"):
            self.assertNotIn(bad, joined)
        for must in ("--output-format", "json", "--model", "gemini-3.1-pro", "--print-timeout", "0",
                     "--mode", "accept-edits", "--effort", "xhigh", "-p"):
            self.assertIn(must, argv, must)

    def test_default_effort_is_high_and_a_level_slug_drops_the_flag(self):
        self.assertEqual(self.run_task().returncode, 0)
        argv = self.seen()["argv"]
        self.assertEqual(argv[argv.index("--effort") + 1], "high")
        shutil.rmtree(self.state)
        self.assertEqual(self.run_task(extra=["--model", "gemini-3.1-pro-high", "--effort", "max"]).returncode, 0)
        argv = self.seen()["argv"]
        self.assertNotIn("--effort", argv)
        self.assertIn("gemini-3.1-pro-high", argv)
        self.assertIn("Make f return 2.", argv[-1])
        self.assertIn("- src/allowed.py", argv[-1])
        _, run_dir = self.report()
        self.assertEqual(Path(self.seen()["cwd"]).resolve(), (run_dir / "ws").resolve())

    def test_profile_denies_writes_by_default_and_allows_only_the_run_paths(self):
        self.assertEqual(self.run_task().returncode, 0)
        profile = (self.tmp / "profile.sb").read_text()
        _, run_dir = self.report()
        self.assertIn("(deny file-write*)", profile)
        self.assertIn(f'(subpath "{(run_dir / "ws").resolve()}")', profile)
        self.assertIn(f'(subpath "{self.agent_home.resolve()}")', profile)
        self.assertNotIn(str(self.repo.resolve()), profile)

    def test_child_env_is_scrubbed_and_tmpdir_is_run_local(self):
        secret = "cv-scrub-canary-value"
        r = self.run_cmd("run", "--repo", str(self.repo), "--brief", str(self.brief),
                         "--allow", "src/allowed.py", "--allow", "src/new_allowed.py",
                         env_extra={"CLAUDE_CODE_MESSAGING_TOKEN": secret, "GEMINI_API_KEY": secret, "SOME_UNRELATED_VAR": secret})
        self.assertEqual(r.returncode, 0, r.stderr)
        seen = self.seen()["env"]
        for leaked in ("CLAUDE_CODE_MESSAGING_TOKEN", "GEMINI_API_KEY", "SOME_UNRELATED_VAR", "ANTIGRAVITY_TASK_STATE"):
            self.assertNotIn(leaked, seen, f"{leaked} reached agy")
        self.assertNotIn(secret, json.dumps(seen))
        self.assertEqual(seen["HOME"], os.environ["HOME"])
        _, run_dir = self.report()
        self.assertEqual(Path(seen["TMPDIR"]).resolve(), (run_dir / "tmp").resolve())

    def test_argv_json_does_not_hold_the_brief(self):
        self.assertEqual(self.run_task().returncode, 0)
        _, run_dir = self.report()
        self.assertEqual(json.loads((run_dir / "argv.json").read_text())[-1], "<brief>")

    @unittest.skipUnless(REAL_SB.exists(), "no sandbox-exec on this host")
    def test_generated_profile_holds_under_the_real_sandbox(self):
        self.assertEqual(self.run_task().returncode, 0)
        _, run_dir = self.report()
        ws = run_dir / "ws"
        outside = Path(f"/tmp/agy-task-escape-{os.getpid()}.txt")
        script = (f'echo in > "{ws}/sb-inside.txt" && echo inside-ok; '
                  f'echo out > "{outside}" 2>/dev/null && echo outside-ok || echo outside-denied; '
                  f'echo h > "$HOME/agy-task-sb-probe.txt" 2>/dev/null && echo home-ok || echo home-denied')
        r = subprocess.run([str(REAL_SB), "-f", str(run_dir / "sandbox.sb"), "/bin/zsh", "-c", script],
                           capture_output=True, text=True)
        self.assertIn("inside-ok", r.stdout)
        self.assertIn("outside-denied", r.stdout)
        self.assertIn("home-denied", r.stdout)
        self.assertFalse(outside.exists())


class TestBoundaryHardening(Base):
    def test_overrides_are_ignored_without_the_test_opt_in(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("antigravity_task", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        from unittest import mock
        with mock.patch.dict(os.environ, {"ANTIGRAVITY_TASK_BIN": "/nope/agy", "ANTIGRAVITY_TASK_AGENT_HOME": "/nope",
                                          "FAKE_AGY_MODE": "clean"}, clear=False):
            os.environ.pop("ANTIGRAVITY_TASK_TEST", None)
            self.assertEqual(mod.agent_bin(), "agy")
            self.assertNotIn("FAKE_AGY_MODE", mod.child_env(self.tmp))
            self.assertEqual(mod.agent_state_home(), Path(os.path.expanduser("~/.gemini")).resolve())
            if Path("/usr/bin/sandbox-exec").exists():
                os.environ["ANTIGRAVITY_TASK_SANDBOX_BIN"] = "/nope/sb"
                self.assertEqual(mod.sandbox_bin(), "/usr/bin/sandbox-exec")

    def test_gitdir_pointer_rewrite_is_refused_at_harvest(self):
        r = self.run_task(mode="gitdir")
        self.assertEqual(r.returncode, 4, r.stderr + r.stdout)
        rpt, run_dir = self.report()
        self.assertTrue(any(".git pointer changed" in e for e in rpt["agent_errors"]))
        self.assertEqual((run_dir / "allowed.patch").read_text(), "")
        self.assertEqual(git(["status", "--porcelain"], self.repo).stdout, "")

    def test_profile_denies_the_settings_file_and_skips_the_folders_root(self):
        self.assertEqual(self.run_task().returncode, 0)
        profile = (self.tmp / "profile.sb").read_text()
        self.assertNotIn('(subpath "/private/var/folders")', profile)
        for name in ("antigravity-cli/settings.json", "settings.json", "GEMINI.md", "extensions"):
            self.assertIn(f'(deny file-write* (subpath "{(self.agent_home / name).resolve()}"))', profile)
        self.assertLess(profile.index("(allow file-write* (subpath"), profile.index("(deny file-write* (subpath"))
        rpt, run_dir = self.report()
        self.assertEqual(rpt["agent_bin"], str(FAKE))

    def test_pathspec_magic_filename_does_not_abort_the_run(self):
        r = self.run_task(mode="pathspec")
        self.assertIn(r.returncode, (0, 3), r.stderr)
        rpt, run_dir = self.report()
        self.assertIn(":(exclude)sneaky.txt", rpt["changed_out_of_scope"])

    def test_symlink_swap_of_an_allowed_file_is_refused(self):
        self.run_task(mode="symlink")
        rpt, run_dir = self.report()
        self.assertNotIn("src/allowed.py", rpt["changed_in_scope"])
        self.assertFalse((self.repo / "src" / "allowed.py").is_symlink())

    def test_run_id_cannot_traverse_out_of_the_state_dir(self):
        self.assertEqual(self.run_task().returncode, 0)
        rpt, _ = self.report()
        (self.state.parent / "report.json").write_text(json.dumps(rpt))
        for cmd in ("clean", "apply"):
            self.assertEqual(self.run_cmd(cmd, "--run", "..").returncode, 2, cmd)
        self.assertTrue(self.state.exists())


class TestClean(Base):
    def test_clean_removes_run_and_worktree(self):
        self.assertEqual(self.run_task().returncode, 0)
        rpt, run_dir = self.report()
        self.assertEqual(self.run_cmd("clean", "--run", rpt["run_id"]).returncode, 0)
        self.assertFalse(run_dir.exists())


if __name__ == "__main__":
    unittest.main()
