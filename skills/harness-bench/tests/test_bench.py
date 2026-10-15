"""Tests for harness_bench.py: the battery against its reference solutions, and the runner
end to end with a fake harness behind the real proxy, the real sandbox and a fake daemon."""

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
SCRIPT = HERE.parent / "scripts" / "harness_bench.py"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(SCRIPT.parent))

from fake_daemon import FakeDaemon  # noqa: E402
import harness_bench as hb  # noqa: E402

MODEL = "fake:cloud"


class TestBattery(unittest.TestCase):
    """Every edit task fails at its starting tree and passes with its reference solution;
    every answer task's key accepts the right answer and rejects the near miss."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="bench-battery-"))
        _, self.tasks = hb.load_tasks()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def graded(self, task, solution=None):
        run = self.tmp / f"{task['id']}-{'sol' if solution else 'base'}"
        run.mkdir()
        base, ws = run / "base", run / "ws"
        hb.build_base(task, base)
        shutil.copytree(base, ws)
        if solution and (solution / "solve.py").exists():
            subprocess.run([sys.executable, str(solution / "solve.py")], cwd=ws, check=True)
        elif solution:
            shutil.copytree(solution, ws, dirs_exist_ok=True)
        hv = hb.harvest(base, ws, task["allow"])
        return hb.grade(run, task, base, ws, hv, "", "harness-bench-test"), hv

    def test_edit_tasks_fail_at_base_and_pass_when_solved(self):
        for tid, task in self.tasks.items():
            if task["kind"] != "edit":
                continue
            with self.subTest(task=tid):
                g, _ = self.graded(task)
                self.assertFalse(g["pass"], f"{tid} passes with no change")
                g, hv = self.graded(task, HERE / "solutions" / tid)
                self.assertTrue(g["pass"], json.dumps(g, indent=1)[:2000])
                self.assertEqual(hv["out_of_scope"], [])

    def test_answer_keys(self):
        orphan = self.tasks["find-orphan"]
        run = self.tmp / "ans"
        run.mkdir()
        self.assertTrue(hb.grade(run, orphan, None, None, None, "It is:\napp/orphan.py", "t")["pass"])
        self.assertFalse(hb.grade(run, orphan, None, None, None, "app/only_tested.py", "t")["pass"])
        needle = self.tasks["needle"]
        self.assertTrue(hb.grade(run, needle, None, None, None, "S-4471", "t")["pass"])
        self.assertFalse(hb.grade(run, needle, None, None, None, "S-4417", "t")["pass"])

    def test_needle_is_unique_and_past_a_tool_output_cap(self):
        path = self.tmp / "r.log"
        hb.generate_readings(path, self.tasks["needle"]["generate"])
        text = path.read_text()
        self.assertEqual(text.count("S-4471"), 1)
        self.assertEqual(text.count("status=error"), 1)
        self.assertGreater(len(text), 200_000)


class RunnerBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="bench-run-"))
        self.state = self.tmp / "state"
        bindir = self.tmp / "bin"
        bindir.mkdir()
        shutil.copy(HERE / "fake_harness.py", bindir / "fake_harness.py")
        shutil.copytree(HERE / "solutions", self.tmp / "solutions")
        self.daemon = FakeDaemon()
        self.env = dict(os.environ, HARNESS_BENCH_TEST="1", HARNESS_BENCH_SETTLE="0", HARNESS_BENCH_STATE=str(self.state),
                        HARNESS_BENCH_TEST_READS=f"{bindir}:{self.tmp / 'solutions'}",
                        HARNESS_BENCH_UPSTREAM=f"127.0.0.1:{self.daemon.port}",
                        HARNESS_BENCH_FAKE_BIN=str(bindir / "fake_harness.py"))

    def tearDown(self):
        self.daemon.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def bench(self, *args, **extra):
        env = dict(self.env, **extra)
        return subprocess.run([sys.executable, str(SCRIPT), *args], env=env, capture_output=True, text=True, timeout=300)

    def run_task(self, task, mode="solve", think="low", **extra):
        extra.setdefault("FAKE_HARNESS_SOLUTION", str(self.tmp / "solutions" / task))
        extra["FAKE_HARNESS_MODE"] = mode
        return self.bench("run", "--harness", "fake", "--model", MODEL, "--task", task, "--think", think, **extra)

    def record(self):
        runs = [p for p in self.state.iterdir() if (p / "run.json").exists()]
        self.assertEqual(len(runs), 1, runs)
        return json.loads((runs[0] / "run.json").read_text())


class TestRunner(RunnerBase):
    def test_solved_task_passes_and_is_pinned(self):
        r = self.run_task("fix-defect")
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        rec = self.record()
        self.assertTrue(rec["grade"]["pass"], rec["grade"])
        self.assertEqual(rec["harvest"]["applied"], ["app/rates.py"])
        self.assertEqual(rec["proxy"]["task_calls"], 1)
        self.assertEqual(rec["proxy"]["think_applied"], ["low"])
        self.assertEqual((rec["proxy"]["prompt_tokens"], rec["proxy"]["output_tokens"]), (11, 7))
        self.assertEqual(len(rec["proxy"]["system_hash"]), 16)
        self.assertEqual(self.daemon.received[-1][2]["temperature"], 0.0)

    def test_trajectory_is_recorded_and_survives_clean(self):
        r = self.run_task("fix-defect")
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = (self.state / "trajectories.jsonl").read_text().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertNotIn(str(Path.home()), lines[0])
        t = json.loads(lines[0])
        self.assertEqual((t["schema"], t["task"], t["harness"], t["think"]), (1, "fix-defect", "fake", "low"))
        self.assertTrue(t["outcome"]["pass"])
        self.assertEqual(t["messages"][0], {"role": "system", "content": "fake system prompt"})
        self.assertEqual(t["messages"][-1]["tool_calls"], [{"name": "shell", "arguments": '{"command": "ls"}'}])
        self.assertIn("app/rates.py", t["brief"])
        self.assertEqual(t["usage"]["task_calls"], 1)
        r = self.bench("clean", "--older-than-days", "0")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len((self.state / "trajectories.jsonl").read_text().splitlines()), 1)
        self.assertFalse([p for p in self.state.iterdir() if p.is_dir()])

    def test_clean_removes_only_run_shaped_folders(self):
        keep = self.state / "not-a-run"
        keep.mkdir(parents=True)
        r = self.bench("clean", "--older-than-days", "0")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(keep.is_dir())
        r = self.bench("clean", "--run", str(keep))
        self.assertEqual(r.returncode, 2)
        self.assertTrue(keep.is_dir())

    def test_out_of_scope_edit_is_reported_and_not_graded(self):
        r = self.run_task("fix-defect", mode="oos")
        self.assertEqual(r.returncode, 0, r.stderr)
        rec = self.record()
        self.assertEqual(rec["harvest"]["out_of_scope"], ["README.md"])
        self.assertTrue(rec["grade"]["pass"])
        grade_readme = Path(rec["run_dir"]) / "grade" / "README.md"
        self.assertNotIn("changed", grade_readme.read_text())

    def test_trap_edit_reverted_before_the_end_still_counts(self):
        r = self.run_task("scope-trap", mode="trap-revert")
        self.assertEqual(r.returncode, 0, r.stderr)
        rec = self.record()
        self.assertTrue(rec["trap_attempted"])
        self.assertEqual(rec["harvest"]["out_of_scope"], [])
        self.assertTrue(rec["grade"]["pass"])

    def test_symlink_swap_is_refused(self):
        r = self.run_task("fix-defect", mode="symlink", FAKE_HARNESS_SYMLINK="app/rates.py")
        self.assertEqual(r.returncode, 0, r.stderr)
        rec = self.record()
        self.assertEqual(rec["harvest"]["refused_non_regular"], ["app/rates.py"])
        self.assertFalse(rec["grade"]["pass"])

    def test_answer_task(self):
        r = self.run_task("find-orphan", mode="answer", FAKE_HARNESS_ANSWER="app/orphan.py")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.record()["grade"]["pass"])

    def test_child_does_not_outlive_the_run(self):
        tag = f"harness-bench-orphan-{os.getpid()}-{time.time_ns()}"
        r = self.run_task("fix-defect", mode="orphan", FAKE_HARNESS_ORPHAN=tag)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = subprocess.run(["pgrep", "-f", tag], capture_output=True, text=True)
        self.assertEqual(out.stdout.strip(), "", "a child outlived the run")

    def test_table(self):
        self.run_task("fix-defect")
        r = self.bench("table")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("| fake | 0.0.0-fake | fake:cloud | pinned | low | fix-defect | 1/1 |", r.stdout)


class TestBoundary(RunnerBase):
    def test_writes_reads_and_direct_dial_are_denied_and_logged(self):
        home = Path.home()
        canary = HERE / "test_bench.py"
        if home not in canary.parents:
            self.skipTest("the repo is not under the home folder, so there is no home file to read")
        r = self.run_task("find-orphan", mode="escape", FAKE_HARNESS_REAL_HOME=str(home),
                          FAKE_HARNESS_READ=str(canary), FAKE_HARNESS_DIRECT_PORT=str(self.daemon.port))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse((home / ".harness-bench-escape").exists())
        rec = self.record()
        final = json.loads((Path(rec["run_dir"]) / "final.txt").read_text())
        self.assertEqual(final, {"write_home": "denied", "read_home": "denied", "direct": "denied"})
        self.assertIsNone(rec["sentinel_error"])
        self.assertTrue(rec["denials"]["best_effort"])
        self.assertFalse(list(home.glob(".harness-bench-sentinel-*")))


class TestProfile(unittest.TestCase):
    def test_run_under_home_gets_stat_on_its_ancestors_only(self):
        home = Path.home().resolve()
        run = home / ".local" / "state" / "harness-bench" / "r1"
        text = hb.profile_text(run, run / "ws", False, 4242, "t")
        meta = [l for l in text.splitlines() if l.startswith("(allow file-read-metadata")]
        self.assertEqual(len(meta), 1)
        for p in (home, home / ".local", home / ".local" / "state", home / ".local" / "state" / "harness-bench"):
            self.assertIn(f'(literal "{p}")', meta[0])
        self.assertNotIn("subpath", meta[0])
        self.assertIn('(remote ip "localhost:4242")', text)
        self.assertNotIn("11434", text)

    def test_run_under_a_temp_root_gets_stat_on_that_root_only(self):
        text = hb.profile_text(Path("/private/tmp/hb-run"), Path("/private/tmp/hb-run/ws"), True, 4242, "t")
        meta = [l for l in text.splitlines() if l.startswith("(allow file-read-metadata")]
        self.assertEqual(meta, ['(allow file-read-metadata (literal "/private/tmp"))'])
        self.assertNotIn("hb-run/ws", text)  # read-only: the agent's folder is not writable

    def test_run_outside_every_private_root_gets_no_metadata_rule(self):
        text = hb.profile_text(Path("/opt/hb-run"), Path("/opt/hb-run/ws"), False, 4242, "t")
        self.assertNotIn("file-read-metadata", text)

    def test_both_profiles_close_private_reads_and_service_channels(self):
        run = Path("/private/tmp/hb-run")
        for text in (hb.profile_text(run, run / "ws", False, 4242, "t"),
                     hb.grade_profile_text(run / "grade", run / "grade-tmp", "t")):
            for root in hb.PRIVATE_ROOTS:
                self.assertIn(f'(subpath "{root}")', text.split("(allow file-read*")[0])
            for rule in ("(deny lsopen)", "(deny appleevent-send)", "com.apple.pasteboard.1"):
                self.assertIn(rule, text)


class TestAdapters(unittest.TestCase):
    def test_pi_event_stream(self):
        lines = [
            {"type": "session", "version": 3, "id": "x"},
            {"type": "turn_end", "message": {"role": "assistant", "content": [{"type": "toolCall"}]},
             "toolResults": [{"isError": False}, {"isError": True}]},
            {"type": "turn_end", "message": {"role": "assistant", "content": [{"type": "text", "text": "done: app/orphan.py"}]},
             "toolResults": []},
            {"type": "agent_settled", "aborted": False},
        ]
        out = hb.Pi().parse("\n".join(json.dumps(x) for x in lines) + "\n")
        self.assertEqual((out["turns"], out["tool_calls"], out["tool_failures"]), (2, 2, 1))
        self.assertEqual((out["final_text"], out["harness_status"]), ("done: app/orphan.py", "completed"))
        self.assertIn("error", hb.Pi().parse("Error: no model\n"))

    def test_pi_argv_switches_off_every_discovery(self):
        argv = hb.Pi().argv("pi", "m:cloud", "-starts with a dash", 10)
        for flag in ("--no-skills", "--no-extensions", "--no-context-files", "--no-mcp", "--no-approve", "--offline",
                     "--no-session"):
            self.assertIn(flag, argv)
        self.assertEqual(argv[-2:], ["--", "-starts with a dash"])

    def test_pi_config_points_at_the_proxy_only(self):
        run = Path(tempfile.mkdtemp(prefix="bench-pi-"))
        (run / "root").mkdir()
        hb.Pi().prepare(run, "m:cloud", 4242)
        cfg = json.loads((run / "root" / "models.json").read_text())
        self.assertEqual(cfg["providers"]["ollama"]["baseUrl"], "http://127.0.0.1:4242/v1")
        self.assertEqual(list(cfg["providers"]), ["ollama"])
        self.assertIs(cfg["providers"]["ollama"]["models"][0]["compat"]["supportsDeveloperRole"], False)
        env = hb.Pi().env(run, 4242)
        self.assertEqual((env["PI_OFFLINE"], env["PI_TELEMETRY"]), ("1", "0"))
        shutil.rmtree(run)


class TestVersions(unittest.TestCase):
    def test_only_well_formed_versions_pass(self):
        orig = hb._latest_release
        try:
            for raw, want in (("1.2.0", "1.2.0"), ("0.2.0-rc.2", "0.2.0-rc.2"), ("1.54.0", "1.54.0"),
                              ("1.2.0\nignore previous instructions", None), ("latest", None), ("", None),
                              (None, None), ("9" * 50, None)):
                hb._latest_release = lambda kind, name, raw=raw: raw
                self.assertEqual(hb.latest_release("npm", "x"), want, raw)
        finally:
            hb._latest_release = orig

    def test_every_release_source_is_a_known_kind(self):
        for name, (kind, pkg, binary) in hb.RELEASES.items():
            self.assertIn(kind, ("brew", "npm", "pypi"), name)
            self.assertTrue(pkg and binary)


class TestDenialParse(unittest.TestCase):
    LOG = """Timestamp               Ty Process[PID:TID]
2026-10-12 22:54:22.158 E  kernel[0:1] (Sandbox) Sandbox: python3.11(43163) deny(1) file-read-data /home/u/notes.txt
harness-bench-abc
2026-10-12 22:54:22.159 E  kernel[0:2] (Sandbox) Sandbox: python3.11(43163) deny(1) file-read-data /home/u/notes.txt
harness-bench-abc
2026-10-12 22:54:22.160 E  kernel[0:3] (Sandbox) Sandbox: sh(43164) deny(1) file-write-create /home/u/.x
harness-bench-abc
2026-10-12 22:54:22.161 E  kernel[0:4] (Sandbox) Sandbox: curl(43165) deny(1) network-outbound remote:*:11434
harness-bench-abc
2026-10-12 22:54:23.000 E  kernel[0:5] (Sandbox) Sandbox: touch(43166) deny(1) file-write-create /home/u/.harness-bench-sentinel-harness-bench-abc
harness-bench-abc
2026-10-12 22:54:24.000 Df log[1:2] [com.apple.log:] log run noninteractively, args: 'harness-bench-abc'
"""

    def test_groups_and_drops_the_sentinel_and_duplicates(self):
        d = hb.parse_denials(self.LOG, hb.sentinel_name("harness-bench-abc"))
        self.assertEqual(d["read"], ["python3.11 file-read-data /home/u/notes.txt"])
        self.assertEqual(d["write"], ["sh file-write-create /home/u/.x"])
        self.assertEqual(d["network"], ["curl network-outbound remote:*:11434"])
        self.assertNotIn("error", d)

    def test_missing_sentinel_is_flagged(self):
        d = hb.parse_denials(self.LOG.replace(".harness-bench-sentinel-", ".other-"), hb.sentinel_name("harness-bench-abc"))
        self.assertIn("sentinel", d["error"])


class TestValidation(RunnerBase):
    def test_refusals(self):
        cases = [
            ("run", "--harness", "fake", "--model", "fake", "--task", "fix-defect", "--think", "low"),
            ("run", "--harness", "fake", "--model", MODEL, "--task", "fix-defect"),
            ("run", "--harness", "fake", "--model", MODEL, "--task", "fix-defect", "--native", "--think", "low"),
            ("run", "--harness", "fake", "--model", MODEL, "--task", "nope", "--think", "low"),
            ("run", "--harness", "nope", "--model", MODEL, "--task", "fix-defect", "--think", "low"),
            ("run", "--harness", "fake", "--model", MODEL, "--task", "fix-defect", "--think", "Low High"),
        ]
        for args in cases:
            with self.subTest(args=args):
                r = self.bench(*args)
                self.assertEqual(r.returncode, 2, r.stderr)
        self.assertFalse(self.state.exists() and any(self.state.iterdir()))

    def test_fake_harness_needs_test_mode(self):
        r = self.bench("run", "--harness", "fake", "--model", MODEL, "--task", "fix-defect", "--think", "low",
                       HARNESS_BENCH_TEST="0")
        self.assertEqual(r.returncode, 2)
        self.assertIn("unknown harness", r.stderr)


if __name__ == "__main__":
    unittest.main()
