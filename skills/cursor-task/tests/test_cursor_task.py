#!/usr/bin/env python3
"""Tests for skills/cursor-task/scripts/cursor_task.py.

Stdlib unittest, synthetic fixture repo, a fake `agent` binary and a fake
`sandbox-exec` that records the profile and runs the command unconfined. One test
runs the generated profile under the real sandbox-exec when the host has it.
Run: python3 -m unittest discover -s skills/cursor-task/tests -v
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
SCRIPT = HERE.parent / "scripts" / "cursor_task.py"
FAKE = HERE / "fake_agent.py"
FAKE_SB = HERE / "fake_sandbox.py"
REAL_SB = Path("/usr/bin/sandbox-exec")


def git(args, cwd):
    return subprocess.run(["git", *args], cwd=str(cwd), text=True, capture_output=True, check=True)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cursor-task-test-"))
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
        self.state = Path.home() / ".cache" / f"cursor-task-test-{self.tmp.name}"
        self.brief = self.tmp / "brief.md"
        self.brief.write_text("Make f return 2.\n")
        self.cursor_home = self.tmp / "dot-cursor"
        self.cursor_home.mkdir()
        self.env = dict(os.environ, CURSOR_TASK_TEST="1", CURSOR_TASK_BIN=str(FAKE), CURSOR_TASK_SANDBOX_BIN=str(FAKE_SB),
                        CURSOR_TASK_STATE=str(self.state), CURSOR_TASK_CURSOR_HOME=str(self.cursor_home),
                        TMPDIR="/nonexistent-tmpdir-for-tests",
                        FAKE_AGENT_ARGV=str(self.tmp / "argv.json"),
                        FAKE_SANDBOX_RECORD=str(self.tmp / "profile.sb"))

    def tearDown(self):
        for d in self.state.glob("*/ws"):
            subprocess.run(["git", "worktree", "remove", "--force", str(d)], cwd=str(self.repo), capture_output=True)
        shutil.rmtree(self.tmp, ignore_errors=True)
        shutil.rmtree(self.state, ignore_errors=True)

    def run_cmd(self, *args, mode="clean", timeout=None, env_extra=None):
        env = dict(self.env, FAKE_AGENT_MODE=mode, **(env_extra or {}))
        return subprocess.run([sys.executable, str(SCRIPT), *args], env=env, text=True,
                              capture_output=True, timeout=timeout or 60)

    def run_task(self, allow=("src/allowed.py", "src/new_allowed.py"), mode="clean", extra=(), env_extra=None):
        args = ["run", "--repo", str(self.repo), "--brief", str(self.brief), *extra]
        for a in allow:
            args += ["--allow", a]
        return self.run_cmd(*args, mode=mode, env_extra=env_extra)

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
        patch = (run_dir / "allowed.patch").read_text()
        self.assertIn("src/allowed.py", patch)
        self.assertNotIn("other.py", patch)
        self.assertTrue((run_dir / "dropped.patch").exists())
        self.assertEqual(rpt["usage"]["inputTokens"], 10)
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
        p = run_dir / "allowed.patch"
        p.write_text(p.read_text() + (run_dir / "dropped.patch").read_text())
        self.assertEqual(self.run_cmd("apply", "--run", rpt["run_id"]).returncode, 0)
        after = self.repo_snapshot()
        self.assertEqual(after["src/other.py"], b"ORIG = True\n")
        self.assertEqual(after["README.md"], b"orig\n")

    def test_committed_changes_in_worktree_are_still_harvested(self):
        r = self.run_task(mode="commit")
        self.assertEqual(r.returncode, 3, r.stderr)
        rpt, run_dir = self.report()
        self.assertEqual(rpt["changed_in_scope"], ["src/allowed.py", "src/new_allowed.py"])
        self.assertIn("return 2", (run_dir / "allowed.patch").read_text())

    def test_clean_run_exits_zero_and_keeps_the_result_text(self):
        r = self.run_task(mode="clean")
        self.assertEqual(r.returncode, 0, r.stderr)
        rpt, run_dir = self.report()
        self.assertEqual(rpt["changed_out_of_scope"], [])
        self.assertIn("I made the change.", (run_dir / "result.md").read_text())

    def test_read_only_run_needs_no_allowlist_and_applies_nothing(self):
        r = self.run_cmd("run", "--repo", str(self.repo), "--brief", str(self.brief), "--read-only", mode="readonly")
        self.assertEqual(r.returncode, 0, r.stderr)
        rpt, run_dir = self.report()
        self.assertTrue(rpt["read_only"])
        self.assertEqual(rpt["allowlist"], [])
        self.assertEqual(rpt["result"]["summary"], "answered")
        self.assertIn("The answer is 42.", (run_dir / "result.md").read_text())
        argv = self.seen()["argv"]
        self.assertIn("ask", argv[argv.index("--mode") + 1])
        self.assertNotIn("--force", argv)
        # ask mode can still write files, so the OS profile denies the worktree too
        profile = (self.tmp / "profile.sb").read_text()
        self.assertNotIn(str((run_dir / "ws").resolve()), profile)
        self.assertIn(f'(subpath "{self.cursor_home.resolve()}")', profile)
        r = self.run_cmd("apply", "--run", rpt["run_id"])
        self.assertEqual(r.returncode, 0)
        self.assertIn("read-only", r.stdout)

    def test_apply_refuses_when_head_moved(self):
        self.assertEqual(self.run_task().returncode, 0)
        rpt, _ = self.report()
        (self.repo / "README.md").write_text("moved\n")
        git(["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qam", "move"], self.repo)
        r = self.run_cmd("apply", "--run", rpt["run_id"])
        self.assertEqual(r.returncode, 2)
        self.assertIn("HEAD moved", r.stderr)
        self.assertEqual(self.run_cmd("apply", "--run", rpt["run_id"], "--force-base").returncode, 0)

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

    def test_no_allowlist_without_read_only_rejected(self):
        r = self.run_cmd("run", "--repo", str(self.repo), "--brief", str(self.brief))
        self.assertEqual(r.returncode, 2)
        self.assertIn("--read-only", r.stderr)

    def test_state_dir_under_tmp_rejected(self):
        r = self.run_cmd("run", "--repo", str(self.repo), "--allow", "src/allowed.py", "--brief", str(self.brief),
                         env_extra={"CURSOR_TASK_STATE": "/tmp/cursor-task-x"})
        self.assertEqual(r.returncode, 2)
        self.assertIn("/tmp", r.stderr)

    def test_missing_sandbox_binary_refuses_before_worktree(self):
        r = self.run_cmd("run", "--repo", str(self.repo), "--allow", "src/allowed.py", "--brief", str(self.brief),
                         env_extra={"CURSOR_TASK_SANDBOX_BIN": str(self.tmp / "no-such-sandbox")})
        self.assertEqual(r.returncode, 2)
        self.assertIn("sandbox", r.stderr)
        self.assertFalse(self.state.exists() and any(self.state.iterdir()))

    def test_oversized_brief_rejected(self):
        self.brief.write_text("x" * 250_000)
        r = self.run_task()
        self.assertEqual(r.returncode, 2)
        self.assertIn("bytes", r.stderr)


class TestProcessControl(Base):
    def test_timeout_kills_process_group(self):
        r = self.run_task(mode="child-sleep", extra=["--timeout", "30"])
        self.assertEqual(r.returncode, 5, r.stderr)
        rpt, _ = self.report()
        self.assertEqual(rpt["exit_reason"], "timeout")
        time.sleep(1)
        out = subprocess.run(["pgrep", "-f", "fake_agent.py"], capture_output=True, text=True)
        self.assertEqual(out.stdout.strip(), "", "a child survived the timeout")

    def test_normal_exit_kills_a_surviving_child(self):
        tag = f"cursor-task-orphan-{os.getpid()}-{time.time_ns()}"
        r = self.run_task(env_extra={"FAKE_AGENT_ORPHAN": tag})
        self.assertEqual(r.returncode, 0, r.stderr)
        out = subprocess.run(["pgrep", "-f", tag], capture_output=True, text=True)
        self.assertEqual(out.stdout.strip(), "", "a child outlived the agent's normal exit")

    def test_agent_error_exit_four(self):
        r = self.run_task(mode="error")
        self.assertEqual(r.returncode, 4, r.stderr)
        rpt, _ = self.report()
        self.assertIn("fake failure", rpt["agent_errors"][0])

    def test_agent_is_killed_when_the_parent_is_interrupted(self):
        env = dict(self.env, FAKE_AGENT_MODE="sleep", FAKE_AGENT_SLEEP="60")
        args = ["run", "--repo", str(self.repo), "--brief", str(self.brief), "--allow", "src/allowed.py", "--timeout", "60"]
        proc = subprocess.Popen([sys.executable, str(SCRIPT), *args], env=env, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        deadline = time.time() + 20
        child = None
        while time.time() < deadline and child is None:
            out = subprocess.run(["pgrep", "-f", "fake_agent.py"], capture_output=True, text=True)
            child = out.stdout.strip() or None
            if child is None:
                time.sleep(0.3)
        self.assertIsNotNone(child, "fake agent never started")
        proc.terminate()
        proc.wait(timeout=20)
        time.sleep(2)
        out = subprocess.run(["pgrep", "-f", "fake_agent.py"], capture_output=True, text=True)
        self.assertEqual(out.stdout.strip(), "", "the agent survived the parent")


class TestArgvAndSandbox(Base):
    def test_locked_flags_and_no_forbidden_argv(self):
        self.assertEqual(self.run_task().returncode, 0)
        argv = self.seen()["argv"]
        joined = " ".join(argv)
        for bad in ("--yolo", "--approve-mcps", "--api-key", "--sandbox disabled", "--dangerously-"):
            self.assertNotIn(bad, joined)
        for must in ("-p", "--output-format", "json", "--model", "grok-4.7-high", "--trust", "--workspace", "--force"):
            self.assertIn(must, argv, must)
        ws = argv[argv.index("--workspace") + 1]
        self.assertTrue(ws.startswith(str(self.state.resolve())), ws)
        self.assertNotEqual(Path(ws).resolve(), self.repo.resolve())
        self.assertIn("Make f return 2.", argv[-1])
        self.assertIn("- src/allowed.py", argv[-1])

    def test_effort_composes_the_slug_unless_the_model_names_a_level(self):
        self.assertEqual(self.run_task(extra=["--effort", "xhigh"]).returncode, 0)
        self.assertIn("grok-4.7-xhigh", self.seen()["argv"])
        shutil.rmtree(self.state)
        self.assertEqual(self.run_task(extra=["--model", "cursor-grok-4.6-max", "--effort", "low"]).returncode, 0)
        self.assertIn("cursor-grok-4.6-max", self.seen()["argv"])
        r = self.run_task(extra=["--effort", "ultra"])
        self.assertEqual(r.returncode, 2)
        self.assertIn("--effort", r.stderr)

    def test_profile_denies_writes_by_default_and_allows_only_the_run_paths(self):
        self.assertEqual(self.run_task().returncode, 0)
        profile = (self.tmp / "profile.sb").read_text()
        rpt, run_dir = self.report()
        self.assertIn("(deny file-write*)", profile)
        self.assertIn(f'(subpath "{(run_dir / "ws").resolve()}")', profile)
        self.assertIn(f'(subpath "{(run_dir / "tmp").resolve()}")', profile)
        self.assertIn(f'(subpath "{self.cursor_home.resolve()}")', profile)
        self.assertNotIn(str(self.repo.resolve()), profile)
        self.assertNotIn(os.path.expanduser("~") + '")', profile)

    def test_child_env_is_scrubbed_and_tmpdir_is_run_local(self):
        secret = "cv-scrub-canary-value"
        r = self.run_cmd("run", "--repo", str(self.repo), "--brief", str(self.brief),
                         "--allow", "src/allowed.py", "--allow", "src/new_allowed.py",
                         env_extra={"CLAUDE_CODE_MESSAGING_TOKEN": secret, "AWS_SESSION_TOKEN": secret,
                                    "GITHUB_TOKEN": secret, "SOME_UNRELATED_VAR": secret})
        self.assertEqual(r.returncode, 0, r.stderr)
        seen = self.seen()["env"]
        for leaked in ("CLAUDE_CODE_MESSAGING_TOKEN", "AWS_SESSION_TOKEN", "GITHUB_TOKEN", "SOME_UNRELATED_VAR",
                       "CURSOR_TASK_STATE", "CURSOR_TASK_CURSOR_HOME"):
            self.assertNotIn(leaked, seen, f"{leaked} reached the agent")
        self.assertNotIn(secret, json.dumps(seen))
        self.assertEqual(seen["HOME"], os.environ["HOME"])
        # A pyenv shim on PATH prepends its own dirs when it re-executes python, so the
        # session's PATH is asserted as a suffix rather than an exact match.
        self.assertTrue(seen["PATH"].endswith(os.environ["PATH"]), seen["PATH"])
        _, run_dir = self.report()
        self.assertEqual(Path(seen["TMPDIR"]).resolve(), (run_dir / "tmp").resolve())

    def test_argv_json_does_not_hold_the_brief(self):
        self.assertEqual(self.run_task().returncode, 0)
        _, run_dir = self.report()
        recorded = json.loads((run_dir / "argv.json").read_text())
        self.assertEqual(recorded[-1], "<brief>")
        self.assertIn("Make f return 2.", (run_dir / "brief.md").read_text())

    @unittest.skipUnless(REAL_SB.exists(), "no sandbox-exec on this host")
    def test_generated_profile_holds_under_the_real_sandbox(self):
        self.assertEqual(self.run_task().returncode, 0)
        _, run_dir = self.report()
        profile = run_dir / "sandbox.sb"
        ws = run_dir / "ws"
        # The test's own temp dir sits in the per-user temp tree the profile allows, so the
        # escape probe targets /tmp, which the profile denies.
        outside = Path(f"/tmp/cursor-task-escape-{os.getpid()}.txt")
        script = (f'echo in > "{ws}/sb-inside.txt" && echo inside-ok; '
                  f'echo out > "{outside}" 2>/dev/null && echo outside-ok || echo outside-denied; '
                  f'echo h > "$HOME/cursor-task-sb-probe.txt" 2>/dev/null && echo home-ok || echo home-denied')
        r = subprocess.run([str(REAL_SB), "-f", str(profile), "/bin/zsh", "-c", script], capture_output=True, text=True)
        self.assertIn("inside-ok", r.stdout)
        self.assertIn("outside-denied", r.stdout)
        self.assertIn("home-denied", r.stdout)
        self.assertFalse(outside.exists())
        self.assertFalse(Path(os.path.expanduser("~/cursor-task-sb-probe.txt")).exists())


class TestBoundaryHardening(Base):
    def test_overrides_are_ignored_without_the_test_opt_in(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("cursor_task", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        from unittest import mock
        with mock.patch.dict(os.environ, {"CURSOR_TASK_BIN": "/nope/agent", "CURSOR_TASK_SANDBOX_BIN": "/nope/sb",
                                          "CURSOR_TASK_CURSOR_HOME": "/nope/home", "FAKE_AGENT_MODE": "clean"}, clear=False):
            os.environ.pop("CURSOR_TASK_TEST", None)
            self.assertEqual(mod.agent_bin(), "agent")
            self.assertNotIn("FAKE_AGENT_MODE", mod.child_env(self.tmp))
            self.assertEqual(mod.cursor_state_home(), Path(os.path.expanduser("~/.cursor")).resolve())
            if Path("/usr/bin/sandbox-exec").exists():
                self.assertEqual(mod.sandbox_bin(), "/usr/bin/sandbox-exec")
            else:
                with self.assertRaises(mod.TaskError):
                    mod.sandbox_bin()

    @unittest.skipUnless(Path("/usr/bin/getconf").exists(), "no getconf on this host")
    def test_user_temp_root_ignores_tmpdir_and_never_returns_private_tmp(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("cursor_task", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        from unittest import mock
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TMPDIR", None)
            root = mod.user_temp_root()
        self.assertTrue(str(root).startswith("/private/var/folders/"), root)
        self.assertNotEqual(str(root), "/private/tmp")
        with mock.patch.dict(os.environ, {"TMPDIR": "/private/tmp"}, clear=False):
            self.assertEqual(mod.user_temp_root(), root)

    def test_gitdir_pointer_rewrite_is_refused_at_harvest(self):
        r = self.run_task(mode="gitdir")
        self.assertEqual(r.returncode, 4, r.stderr + r.stdout)
        rpt, run_dir = self.report()
        self.assertTrue(any(".git pointer changed" in e for e in rpt["agent_errors"]))
        self.assertEqual(rpt["changed_in_scope"], [])
        self.assertEqual((run_dir / "allowed.patch").read_text(), "")
        self.assertEqual(git(["status", "--porcelain"], self.repo).stdout, "")

    def test_profile_path_with_a_quote_or_newline_is_refused(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("cursor_task", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for bad in ('a"b', "a\nb", "a(b)", "a\\b"):
            with self.assertRaises(mod.TaskError):
                mod._sb_path(self.tmp / bad)

    def test_profile_allows_the_user_temp_root_not_the_folders_root_and_denies_the_loaders(self):
        self.assertEqual(self.run_task().returncode, 0)
        profile = (self.tmp / "profile.sb").read_text()
        self.assertNotIn('(subpath "/private/var/folders")', profile)
        for name in ("agents", "rules", "plugins", "extensions", "mcp.json", "hooks.json"):
            self.assertIn(f'(deny file-write* (subpath "{(self.cursor_home / name).resolve()}"))', profile)
        # the CLI rewrites its own config at startup, so that one write is allowed and undone after
        self.assertNotIn("cli-config.json", profile)
        self.assertLess(profile.index("(allow file-write* (subpath"), profile.index("(deny file-write* (subpath"))

    def test_cli_config_is_restored_byte_for_byte_after_the_run(self):
        cfg = self.cursor_home / "cli-config.json"
        cfg.write_text('{"permissions": {"allow": []}, "version": 1}\n')
        before = cfg.read_bytes()
        write = {"FAKE_AGENT_WRITE_CONFIG": str(cfg)}
        r = self.run_task(allow=(), mode="readonly", extra=["--read-only"], env_extra=write)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        rpt, run_dir = self.report()
        self.assertEqual(rpt["cli_config"], {"existed": True, "changed_by_run": True, "restored": True, "lock_wait_s": 0.0})
        self.assertEqual(cfg.read_bytes(), before)
        self.assertEqual([p.name for p in cfg.parent.iterdir() if p.name.startswith("cli-config.json.")], [])
        # a link planted at a predictable temp name inside the CLI's folder is never followed
        victim = self.tmp / "victim.txt"
        victim.write_text("keep me\n")
        (cfg.parent / "cli-config.json.restore").symlink_to(victim)
        shutil.rmtree(self.report()[1])
        r = self.run_task(allow=(), mode="readonly", extra=["--read-only"], env_extra=write)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertEqual(cfg.read_bytes(), before)
        self.assertEqual(victim.read_text(), "keep me\n")
        (cfg.parent / "cli-config.json.restore").unlink()
        shutil.rmtree(self.report()[1])
        r = self.run_task(allow=(), mode="readonly", extra=["--read-only"])
        self.assertEqual(r.returncode, 0, r.stderr)
        rpt, run_dir = self.report()
        self.assertEqual(rpt["cli_config"], {"existed": True, "changed_by_run": False, "restored": False, "lock_wait_s": 0.0})
        shutil.rmtree(run_dir)
        cfg.unlink()
        r = self.run_task(allow=(), mode="readonly", extra=["--read-only"], env_extra=write)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.report()[0]["cli_config"], {"existed": False, "changed_by_run": True, "restored": True, "lock_wait_s": 0.0})
        self.assertFalse(cfg.exists())

    def test_two_cursor_runs_take_turns_on_the_config_lock(self):
        import fcntl
        self.cursor_home.mkdir(exist_ok=True)
        held = os.open(self.cursor_home / "cli-config.lock", os.O_CREAT | os.O_RDWR, 0o600)
        fcntl.flock(held, fcntl.LOCK_EX)       # another run, or agent-review's Cursor member, is mid-call
        r = self.run_task(allow=(), mode="readonly", extra=["--read-only"], env_extra={"CURSOR_TASK_LOCK_WAIT": "1"})
        self.assertEqual(r.returncode, 5, r.stderr + r.stdout)
        self.assertIn("Cursor's config lock", r.stderr)
        os.close(held)
        for d in self.state.iterdir():       # the refused run left its record; clear it so report() finds one
            if d.is_dir():
                shutil.rmtree(d)
        r = self.run_task(allow=(), mode="readonly", extra=["--read-only"], env_extra={"CURSOR_TASK_LOCK_WAIT": "1"})
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertEqual(self.report()[0]["cli_config"]["lock_wait_s"], 0.0)

    def test_report_names_the_binaries_and_prints_the_anchored_line(self):
        r = self.run_task()
        self.assertEqual(r.returncode, 0)
        rpt, run_dir = self.report()
        self.assertEqual(rpt["agent_bin"], str(FAKE))
        self.assertEqual(rpt["sandbox_bin"], str(FAKE_SB))
        last = r.stdout.strip().splitlines()[-1]
        self.assertTrue(last.startswith("report_json="), last)
        self.assertEqual(Path(last[len("report_json="):]).resolve(), (run_dir / "report.json").resolve())

    def test_pathspec_magic_filename_does_not_abort_the_run(self):
        r = self.run_task(mode="pathspec")
        self.assertIn(r.returncode, (0, 3), r.stderr)
        rpt, run_dir = self.report()
        self.assertIn(":(exclude)sneaky.txt", rpt["changed_out_of_scope"])
        self.assertIn("sneaky.txt", (run_dir / "dropped.patch").read_text())

    def test_symlink_swap_of_an_allowed_file_is_refused(self):
        self.run_task(mode="symlink")
        rpt, run_dir = self.report()
        self.assertNotIn("src/allowed.py", rpt["changed_in_scope"])
        self.assertNotIn("120000", (run_dir / "allowed.patch").read_text())
        self.assertFalse((self.repo / "src" / "allowed.py").is_symlink())

    def test_run_id_cannot_traverse_out_of_the_state_dir(self):
        self.assertEqual(self.run_task().returncode, 0)
        rpt, _ = self.report()
        (self.state.parent / "report.json").write_text(json.dumps(rpt))
        for cmd in ("clean", "apply"):
            r = self.run_cmd(cmd, "--run", "..")
            self.assertEqual(r.returncode, 2, f"{cmd} accepted '..'")
        self.assertTrue(self.state.exists())


class TestClean(Base):
    def test_clean_removes_run_and_worktree(self):
        self.assertEqual(self.run_task().returncode, 0)
        rpt, run_dir = self.report()
        self.assertEqual(self.run_cmd("clean", "--run", rpt["run_id"]).returncode, 0)
        self.assertFalse(run_dir.exists())
        self.assertNotIn(str(run_dir), git(["worktree", "list"], self.repo).stdout)


if __name__ == "__main__":
    unittest.main()
