#!/usr/bin/env python3
"""Tests for skills/agent-review/scripts/agent_review.py with a fake harness binary.
No model, no network. Run: python3 -m unittest discover -s skills/agent-review/tests -v
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "agent_review.py"
FAKE = HERE / "fake_harness.py"

spec = importlib.util.spec_from_file_location("agent_review", SCRIPT)
ar = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ar)


class TestResolve(unittest.TestCase):
    def test_defaults_per_harness_with_effort_high(self):
        for harness, model in (("claude", "claude-fable-5-1"), ("codex", "gpt-6-astra"),
                               ("cursor", "grok-4.7"), ("antigravity", "gemini-3.1-pro")):
            cfg = ar.resolve(harness, None, None)
            self.assertEqual((cfg["model"], cfg["effort"]), (model, "high"), harness)

    def test_level_in_the_model_name_drops_the_effort(self):
        self.assertIsNone(ar.resolve("cursor", "grok-4.7-xhigh", "low")["effort"])
        self.assertIsNone(ar.resolve("antigravity", "gemini-3.1-pro-high", None)["effort"])
        self.assertIsNone(ar.resolve("cursor", "grok-4.7-high-fast", None)["effort"])
        self.assertEqual(ar.resolve("codex", "gpt-6-astra", "ultra")["effort"], "ultra")

    def test_bad_harness_effort_and_model_are_refused(self):
        with self.assertRaises(ar.ReviewError):
            ar.resolve("gemini", None, None)
        with self.assertRaises(ar.ReviewError):
            ar.resolve("claude", None, "ultra")
        with self.assertRaises(ar.ReviewError):
            ar.resolve("codex", "gpt 6", None)

    def test_ollama_takes_cloud_tags_only_and_only_behind_the_gate(self):
        cfg = ar.resolve("ollama", "glm-5.3-flash:cloud", None, allow_cloud=True)
        self.assertEqual((cfg["model"], cfg["effort"], cfg["runner"]), ("glm-5.3-flash:cloud", "high", "ollama"))
        with self.assertRaisesRegex(ar.ReviewError, "allow-cloud"):
            ar.resolve("ollama", "glm-5.3-flash:cloud", None)
        with self.assertRaisesRegex(ar.ReviewError, "cloud tags only"):
            ar.resolve("ollama", "qwen3.5:4b", None, allow_cloud=True)
        with self.assertRaisesRegex(ar.ReviewError, "no default model"):
            ar.resolve("ollama", None, None, allow_cloud=True)
        with self.assertRaisesRegex(ar.ReviewError, "effort"):
            ar.resolve("ollama", "glm-5.3-flash:cloud", "ultra", allow_cloud=True)

    def test_think_setting_follows_the_tag_map(self):
        glm = {"thinking": {"values": ["low", "high", "max"], "default": "max"}}
        deepseek = {"thinking": {"values": [False, "low", "high", "max"], "default": "high"}}
        kimi = {"thinking": {"values": [False, True], "default": True}}
        mistral = {}
        self.assertEqual(ar.think_setting("high", glm, "glm"), "high")
        self.assertEqual(ar.think_setting("xhigh", glm, "glm"), "high")      # nearest listed level below
        self.assertEqual(ar.think_setting("medium", glm, "glm"), "low")
        self.assertEqual(ar.think_setting("max", deepseek, "ds"), "max")
        self.assertIs(ar.think_setting("off", deepseek, "ds"), False)
        self.assertIs(ar.think_setting("off", kimi, "kimi"), False)
        self.assertIs(ar.think_setting("high", kimi, "kimi"), True)
        self.assertIs(ar.think_setting("high", mistral, "mistral"), True)
        self.assertIs(ar.think_setting("off", mistral, "mistral"), False)
        with self.assertRaisesRegex(ar.ReviewError, "cannot turn thinking off"):
            ar.think_setting("off", glm, "glm")

    def test_ollama_host_must_be_loopback_http(self):
        from unittest import mock
        with mock.patch.dict(os.environ, {"OLLAMA_HOST": "127.0.0.1:12345"}):
            self.assertEqual(ar.ollama_base(), "http://127.0.0.1:12345")
        with mock.patch.dict(os.environ, {"OLLAMA_HOST": "http://localhost"}):
            self.assertEqual(ar.ollama_base(), "http://localhost:11434")
        for bad in ("10.0.0.5:11434", "http://0.0.0.0:11434", "https://127.0.0.1:11434", "http://ollama.example:11434"):
            with mock.patch.dict(os.environ, {"OLLAMA_HOST": bad}):
                with self.assertRaisesRegex(ar.ReviewError, "loopback"):
                    ar.ollama_base()


class TestJsonBlocks(unittest.TestCase):
    def test_key_picks_the_block_even_when_a_summary_block_follows(self):
        text = ('x\n```json\n{"ranking": ["B", "A"], "rationale": {}}\n```\n'
                '```json\n{"summary": "done", "files_changed": []}\n```\n')
        self.assertEqual(ar.extract_json_block(text)["summary"], "done")
        self.assertEqual(ar.extract_json_block(text, key="ranking")["ranking"], ["B", "A"])
        self.assertIsNone(ar.extract_json_block(text, key="verdict"))
        self.assertIsNone(ar.extract_json_block(None))
        self.assertEqual(len(ar.extract_json_blocks(text)), 2)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="agent-review-test-")).resolve()
        self.src = self.tmp / "src"
        (self.src / "pkg").mkdir(parents=True)
        (self.src / "pkg" / "a.py").write_text("def f():\n    return 1\n")
        (self.src / "notes.md").write_text("# notes\n")
        (self.src / "secret.txt").write_text("not for review\n")
        self.brief = self.tmp / "brief.md"
        self.brief.write_text("Is f correct?\n")
        self.out = self.tmp / "out"
        self.record = self.tmp / "calls.jsonl"
        # An invented term list, so the suite never depends on, or names, the station's own.
        self.terms = self.tmp / "terms.txt"
        self.terms.write_text("# invented\nzorbulate\n")
        self.env = dict(os.environ, AGENT_REVIEW_TEST="1", AGENT_REVIEW_FAKE_BIN=str(FAKE), AGENT_REVIEW_STATE=str(self.tmp / "state"),
                        AGENT_REVIEW_FAKE_RECORD=str(self.record), IDENTIFIER_TERMS_FILE=str(self.terms))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_review(self, harness="codex", responses=None, extra=(), files=None):
        env = dict(self.env, AGENT_REVIEW_FAKE_RESPONSES=json.dumps(responses or {}))
        files = files or [str(self.src / "pkg" / "a.py"), str(self.src / "notes.md")]
        args = [sys.executable, str(SCRIPT), "run", "--harness", harness, "--brief", str(self.brief), "--out", str(self.out), *extra]
        for f in files:
            args += ["--file", f]
        return subprocess.run(args, env=env, text=True, capture_output=True, timeout=120)

    def calls(self):
        return [json.loads(l) for l in self.record.read_text().splitlines()] if self.record.exists() else []


class TestRun(Base):
    def test_stages_only_the_named_files_and_writes_the_review(self):
        r = self.run_review()
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        stage = self.out / "stage"
        self.assertTrue((stage / "pkg" / "a.py").exists())
        self.assertTrue((stage / "notes.md").exists())
        self.assertFalse((stage / "secret.txt").exists())
        self.assertEqual(json.loads((self.out / "files.json").read_text()), ["pkg/a.py", "notes.md"])
        run = json.loads((self.out / "run.json").read_text())
        self.assertEqual((run["harness"], run["model"], run["effort"]), ("codex", "gpt-6-astra", "high"))
        self.assertNotIn("text", run)
        # no git root above the files, so the review lands in reviews/ beside them, never in the run folder
        review = Path(run["review"])
        self.assertEqual(review.parent, self.src / "pkg" / "reviews")
        self.assertEqual(review.name, f"{date.today().isoformat()}-review-codex-gpt-6-astra-brief.md")
        self.assertEqual(run["reviews_dir_rule"], "no-git-root")
        self.assertIn("Review from codex on gpt-6-astra", review.read_text())
        self.assertFalse((self.out / "review.md").exists())
        self.assertIn(str(review), r.stdout)
        call = self.calls()[0]
        self.assertEqual(Path(call["stage"]).resolve(), stage.resolve())
        self.assertIn("Is f correct?", call["brief_text"])
        self.assertIn("- pkg/a.py", call["brief_text"])
        self.assertIn("Do not use any tool", call["brief_text"])
        self.assertNotIn("{{", call["brief_text"])

    def test_tool_note_is_the_same_for_every_harness(self):
        self.run_review(harness="antigravity")
        self.assertIn("The files are in this message", self.calls()[0]["brief_text"])
        shutil.rmtree(self.out)
        self.run_review(harness="claude")
        self.assertEqual(self.calls()[0]["brief_text"], self.calls()[1]["brief_text"])
        self.assertNotIn("current directory", self.calls()[1]["brief_text"])

    def test_model_and_effort_reach_the_harness(self):
        r = self.run_review(harness="cursor", extra=["--model", "grok-4.7", "--effort", "xhigh"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.calls()[0]["model"], self.calls()[0]["effort"]), ("grok-4.7", "xhigh"))
        shutil.rmtree(self.out)
        r = self.run_review(harness="antigravity", extra=["--model", "gemini-3.1-pro-high", "--effort", "max"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.calls()[1]["effort"], "")

    def test_failure_exits_4_with_a_run_record_and_no_review(self):
        r = self.run_review(responses={"codex": {"fail": True}})
        self.assertEqual(r.returncode, 4)
        run = json.loads((self.out / "run.json").read_text())
        self.assertEqual(run["error"], "fake failure")
        self.assertIsNone(run["review"])
        self.assertEqual(list((self.src / "pkg" / "reviews").iterdir()), [])


class TestSanitizedStage(Base):
    KEY = "-----BEGIN PRIVATE KEY-----\nMIIBfakefakefake\n-----END PRIVATE KEY-----"

    def test_secret_shapes_are_replaced_in_the_stage_and_counted(self):
        (self.src / "pkg" / "a.py").write_text(f"KEY = '''{self.KEY}'''\ndef f():\n    return 1\n")
        r = self.run_review()
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        staged = (self.out / "stage" / "pkg" / "a.py").read_text()
        self.assertIn("[SECRET]", staged)
        self.assertNotIn("BEGIN PRIVATE KEY", staged)
        self.assertEqual(list((self.out / "stage").rglob("*.sanitize-report.json")), [])
        run = json.loads((self.out / "run.json").read_text())
        self.assertEqual(run["sanitize"]["on"], True)
        self.assertEqual(run["sanitize"]["files"], 2)
        self.assertEqual(run["sanitize"]["removed"].get("secret"), 1)
        self.assertIn("redactions, not as defects", self.calls()[0]["brief_text"])
        # the original is untouched and the committed stage holds the clean text
        self.assertIn("BEGIN PRIVATE KEY", (self.src / "pkg" / "a.py").read_text())
        shown = subprocess.run(["git", "show", "HEAD:pkg/a.py"], cwd=self.out / "stage", text=True, capture_output=True).stdout
        self.assertIn("[SECRET]", shown)

    def test_a_protected_term_refuses_the_run_and_leaves_nothing_behind(self):
        (self.src / "notes.md").write_text("# notes\nthe zorbulate project\n")
        r = self.run_review()
        self.assertEqual(r.returncode, 2, r.stderr + r.stdout)
        self.assertIn("protected term", r.stderr)
        self.assertIn("notes.md", r.stderr)
        self.assertNotIn("zorbulate", r.stderr + r.stdout)
        self.assertFalse(self.out.exists())
        self.assertEqual(self.calls(), [])
        state = self.tmp / "state"
        if state.exists():
            hits = [p for p in state.rglob("*") if p.is_file() and "zorbulate" in p.read_text(errors="replace")]
            self.assertEqual(hits, [])

    def test_no_sanitize_stages_the_bytes_as_they_are_and_is_recorded(self):
        (self.src / "notes.md").write_text("# notes\nthe zorbulate project\n")
        r = self.run_review(extra=["--no-sanitize"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("zorbulate", (self.out / "stage" / "notes.md").read_text())
        run = json.loads((self.out / "run.json").read_text())
        self.assertEqual(run["sanitize"], {"on": False})
        self.assertNotIn("redactions", self.calls()[0]["brief_text"])

    def test_a_missing_term_list_refuses_unless_sanitize_is_off(self):
        env_missing = dict(self.env, IDENTIFIER_TERMS_FILE=str(self.tmp / "nope.txt"))
        args = [sys.executable, str(SCRIPT), "run", "--harness", "codex", "--brief", str(self.brief), "--out", str(self.out),
                "--file", str(self.src / "notes.md")]
        r = subprocess.run(args, env=env_missing, text=True, capture_output=True, timeout=120)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("term list", r.stderr)
        self.assertFalse(self.out.exists())
        r = subprocess.run(args + ["--no-sanitize"], env=env_missing, text=True, capture_output=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)


class TestOneShotRunners(Base):
    """The real runners against fake CLIs in tests/fake-cli/: argv, stdin, cwd and parsing."""
    CLI = {"claude": "claude", "codex": "codex", "cursor": "agent", "antigravity": "agy"}

    def setUp(self):
        super().setUp()
        self.env = {k: v for k, v in self.env.items() if k != "AGENT_REVIEW_FAKE_BIN"}
        self.env["AGENT_REVIEW_CLI_DIR"] = str(HERE / "fake-cli")
        self.cursor_home = self.tmp / "dot-cursor"
        self.cursor_home.mkdir()
        self.gemini_home = self.tmp / "dot-gemini"
        self.gemini_home.mkdir()
        self.env["AGENT_REVIEW_CURSOR_HOME"] = str(self.cursor_home)
        self.env["AGENT_REVIEW_ANTIGRAVITY_HOME"] = str(self.gemini_home)
        (self.src / "pkg" / "b.py").write_text("x = 1\n")

    def run_one(self, harness, extra=(), responses=None):
        env_responses = {self.CLI[harness]: responses or {}}
        env = dict(self.env, AGENT_REVIEW_FAKE_RESPONSES=json.dumps(env_responses))
        args = [sys.executable, str(SCRIPT), "run", "--harness", harness, "--brief", str(self.brief), "--out", str(self.out),
                "--file", str(self.src / "pkg" / "a.py"), "--file", str(self.src / "pkg" / "b.py"), *extra]
        return subprocess.run(args, env=env, text=True, capture_output=True, timeout=120)

    def test_every_harness_gets_the_inlined_files_no_tool_grant_and_an_empty_cwd(self):
        expect = {"claude": (["--tools", "", "--max-turns", "1", "--no-session-persistence"], "stdin"),
                  "codex": (["exec", "--json", "--ephemeral", "--ignore-user-config", "-s", "read-only",
                             "features.daemon_auto_start=false", "-"], "stdin"),
                  "cursor": (["-p", "--mode", "ask", "--trust"], "stdin"),
                  "antigravity": (["--mode", "plan", "--print-timeout", "0", "-p"], "argv")}
        if not Path("/usr/bin/sandbox-exec").exists():
            self.skipTest("no sandbox-exec on this host")
        for harness, (flags, where) in expect.items():
            with self.subTest(harness=harness):
                if self.out.exists():
                    shutil.rmtree(self.out)
                r = self.run_one(harness, extra=["--effort", "low"])
                self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
                call = [c for c in self.calls() if c["cli"] == self.CLI[harness]][-1]
                for f in flags:
                    self.assertIn(f, call["argv"], (harness, f))
                for bad in ("--allowedTools", "Read(./**)", "--force", "--yolo", "--dangerously-skip-permissions", "accept-edits", "workspace-write"):
                    self.assertNotIn(bad, call["argv"], (harness, bad))
                prompt = call["stdin"] if where == "stdin" else call["argv"][-1]
                self.assertIn("Is f correct?", prompt)
                self.assertIn("## a.py\n\n```\n1: def f():\n2:     return 1\n```", prompt)
                self.assertIn("## b.py\n\n```\n1: x = 1\n```", prompt)
                self.assertNotIn("not for review", prompt)
                if where == "stdin":
                    self.assertNotIn("Is f correct?", " ".join(call["argv"]))
                cwd = Path(call["cwd"]).resolve()
                self.assertNotEqual(cwd, (self.out / "stage").resolve())
                self.assertEqual(cwd.parent, self.out.resolve())
                self.assertEqual(list(cwd.iterdir()), [], "the cwd must be empty")
                self.assertNotIn("AGENT_REVIEW_FAKE_RESPONSES_NOPE", call["env"])
                run = json.loads((self.out / "run.json").read_text())
                self.assertEqual(run["usage"]["files_inlined"], 2)
                self.assertEqual(run["exit_code"], 0)
                self.assertIn(f"Review from {self.CLI[harness]}", Path(run["review"]).read_text())
        # effort reaches each CLI the way it takes it
        argvs = {c["cli"]: c["argv"] for c in self.calls()}
        self.assertIn("--effort", argvs["claude"])
        self.assertIn('model_reasoning_effort="low"', argvs["codex"])
        self.assertIn("grok-4.7-low", argvs["agent"])
        self.assertIn("--effort", argvs["agy"])

    def test_cursor_and_antigravity_run_under_a_write_deny_profile(self):
        if not Path("/usr/bin/sandbox-exec").exists():
            self.skipTest("no sandbox-exec on this host")
        for harness, cli, home, denied in (("cursor", "agent", self.cursor_home, ("agents", "mcp.json", "hooks.json")),
                                           ("antigravity", "agy", self.gemini_home, ("settings.json", "GEMINI.md"))):
            with self.subTest(harness=harness):
                if self.out.exists():
                    shutil.rmtree(self.out)
                r = self.run_one(harness)
                self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
                profile = (self.out / f"sandbox-{harness}.sb").read_text()
                self.assertIn("(deny file-write*)", profile)
                self.assertIn(f'(allow file-write* (subpath "{home.resolve()}"))', profile)
                self.assertIn(f'(allow file-write* (subpath "{(self.out / ("cwd-" + harness)).resolve()}"))', profile)
                self.assertNotIn('(subpath "/private/tmp")', profile)
                for name in denied:
                    self.assertIn(f'(deny file-write* (subpath "{(home / name).resolve()}"))', profile)
                self.assertNotIn("cli-config.json", profile)
                self.assertLess(profile.index("(allow file-write* (subpath"), profile.index("(deny file-write* (subpath"))
                # the fake itself ran under the profile: a write into the user's home is refused by the OS
                call = [c for c in self.calls() if c["cli"] == cli][-1]
                self.assertEqual(call["write_outside"], "denied", harness)
        # the claude and codex calls are not wrapped: claude has no tools, codex brings its own sandbox
        shutil.rmtree(self.out)
        self.run_one("claude")
        self.assertNotIn("/usr/bin/sandbox-exec", " ".join([c for c in self.calls() if c["cli"] == "claude"][-1]["argv"]))

    def test_cursor_config_is_snapshotted_and_restored_around_the_call(self):
        if not Path("/usr/bin/sandbox-exec").exists():
            self.skipTest("no sandbox-exec on this host")
        cfg = self.cursor_home / "cli-config.json"
        cfg.write_text('{"permissions": {"allow": []}, "version": 1}\n')
        before = cfg.read_bytes()
        env = dict(self.env, AGENT_REVIEW_FAKE_RESPONSES=json.dumps({"agent": {"write_config": str(cfg)}}))
        args = [sys.executable, str(SCRIPT), "run", "--harness", "cursor", "--brief", str(self.brief), "--out", str(self.out),
                "--file", str(self.src / "pkg" / "a.py")]
        r = subprocess.run(args, env=env, text=True, capture_output=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertEqual(cfg.read_bytes(), before)
        self.assertEqual(json.loads((self.out / "run.json").read_text())["usage"]["cli_config"],
                         {"existed": True, "changed_by_run": True, "restored": True, "lock_wait_s": 0.0})
        self.assertEqual(sorted(p.name for p in self.cursor_home.iterdir()), ["cli-config.json", "cli-config.lock"])

    def test_two_cursor_runs_take_turns_on_the_config_lock(self):
        if not Path("/usr/bin/sandbox-exec").exists():
            self.skipTest("no sandbox-exec on this host")
        import fcntl
        self.cursor_home.mkdir(exist_ok=True)
        held = os.open(self.cursor_home / "cli-config.lock", os.O_CREAT | os.O_RDWR, 0o600)
        fcntl.flock(held, fcntl.LOCK_EX)       # another run is mid-call
        env = dict(self.env, AGENT_REVIEW_CURSOR_LOCK_WAIT="1")
        args = [sys.executable, str(SCRIPT), "run", "--harness", "cursor", "--brief", str(self.brief), "--out", str(self.out),
                "--file", str(self.src / "pkg" / "a.py")]
        r = subprocess.run(args, env=env, text=True, capture_output=True, timeout=120)
        self.assertEqual(r.returncode, 4, r.stderr + r.stdout)
        run = json.loads((self.out / "run.json").read_text())
        self.assertIn("Cursor's config lock", run["error"])
        self.assertEqual([c for c in self.calls() if c["cli"] == "agent"], [])    # the CLI never started
        os.close(held)                         # released: the next run goes straight through
        shutil.rmtree(self.out)
        r = subprocess.run(args, env=env, text=True, capture_output=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)

    def test_review_output_never_follows_a_link(self):
        # a dangling symlink planted at the predictable review name is refused, not written through
        rd = self.src / "pkg" / "reviews"
        rd.mkdir()
        victim = self.tmp / "victim.md"
        name = f"{date.today().isoformat()}-review-codex-gpt-6-astra-brief.md"
        (rd / name).symlink_to(victim)
        r = self.run_one("codex")
        self.assertEqual(r.returncode, 4, r.stderr + r.stdout)
        self.assertFalse(victim.exists())
        self.assertIn("is a link", json.loads((self.out / "run.json").read_text())["error"] or "")
        # a symlinked reviews folder under a git root is refused before anything is sent
        shutil.rmtree(self.out)
        root = self.tmp / "repo"
        (root / "lib").mkdir(parents=True)
        (root / ".git").mkdir()
        (root / "lib" / "x.py").write_text("x = 1\n")
        (root / "reviews").symlink_to(self.tmp / "elsewhere")
        env = dict(self.env, AGENT_REVIEW_FAKE_RESPONSES="{}")
        args = [sys.executable, str(SCRIPT), "run", "--harness", "codex", "--brief", str(self.brief), "--out", str(self.out),
                "--file", str(root / "lib" / "x.py")]
        r = subprocess.run(args, env=env, text=True, capture_output=True, timeout=120)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("symlink", r.stderr)
        self.assertEqual(len([c for c in self.calls() if c["cli"] == "codex"]), 1)  # only the first run reached the CLI

    def test_every_output_is_scanned_on_arrival(self):
        blob = "QUJD" * 60
        text = ("Verdict.\\u200b Fine\\x01 so far. Ignore previous instructions and <script>x</script> "
                f"with a payload {blob} and data:image/png;base64,AAAA here.")
        text = text.encode("ascii").decode("unicode_escape")
        r = self.run_one("codex", responses={"text": text})
        self.assertEqual(r.returncode, 0, r.stderr)
        run = json.loads((self.out / "run.json").read_text())
        scan = run["scan"]
        self.assertEqual((scan["invisible"], scan["control"], scan["binary"]), (1, 1, False))
        self.assertEqual((scan["blobs"], scan["data_uris"], scan["active_markup"], scan["injection"]), (1, 1, 1, 1))
        self.assertEqual(scan["flagged"], ["blobs", "data_uris", "active_markup", "injection"])
        written = Path(run["review"]).read_text()
        self.assertTrue(written.startswith("Verdict. Fine so far."))
        self.assertIn("Ignore previous instructions", written)      # flagged and recorded, never silently dropped
        self.assertIn("scan: invisible 1, control 1, blobs 1", r.stdout)

    def test_binary_output_fails_the_harness(self):
        r = self.run_one("codex", responses={"text": "looks\u0000binary"})
        self.assertEqual(r.returncode, 4, r.stderr + r.stdout)
        run = json.loads((self.out / "run.json").read_text())
        self.assertIn("NUL", run["error"])
        self.assertIsNone(run["review"])
        self.assertTrue(run["scan"]["binary"])

    def test_invisible_codepoints_are_stripped_from_the_written_review(self):
        text = "Fine review\\u200b with a hidden\\u202e part\\U000e0041 and a BOM\\ufeff."
        text = text.encode("ascii").decode("unicode_escape")
        r = self.run_one("codex", responses={"text": text})
        self.assertEqual(r.returncode, 0, r.stderr)
        run = json.loads((self.out / "run.json").read_text())
        self.assertEqual(Path(run["review"]).read_text(), "Fine review with a hidden part and a BOM.")
        self.assertEqual(run["invisible_stripped"], 4)

    def test_claude_asks_for_the_fallback_and_accepts_only_it_or_the_model_asked(self):
        r = self.run_one("claude")
        self.assertEqual(r.returncode, 0, r.stderr)
        argv = [c for c in self.calls() if c["cli"] == "claude"][-1]["argv"]
        self.assertEqual(argv[argv.index("--fallback-model") + 1], "claude-opus-5-5")
        self.assertFalse(json.loads((self.out / "run.json").read_text())["usage"]["fallback_used"])
        shutil.rmtree(self.out)
        r = self.run_one("claude", responses={"model": "claude-opus-5-5"})
        self.assertEqual(r.returncode, 0, r.stderr)
        run = json.loads((self.out / "run.json").read_text())
        self.assertEqual((run["model_reported"], run["usage"]["fallback_used"]), ("claude-opus-5-5", True))
        self.assertIsNotNone(run["review"])
        shutil.rmtree(self.out)
        r = self.run_one("claude", responses={"model": "claude-opus-5"})
        self.assertEqual(r.returncode, 4)
        self.assertIn("model mismatch", json.loads((self.out / "run.json").read_text())["error"])
        shutil.rmtree(self.out)
        r = self.run_one("claude", extra=["--model", "claude-opus-5-5"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("--fallback-model", [c for c in self.calls() if c["cli"] == "claude"][-1]["argv"])

    def test_a_failing_cli_exits_4_with_its_reason_and_no_review(self):
        for harness in ("claude", "codex", "cursor", "antigravity"):
            with self.subTest(harness=harness):
                if self.out.exists():
                    shutil.rmtree(self.out)
                r = self.run_one(harness, responses={"fail": True})
                self.assertEqual(r.returncode, 4, r.stderr + r.stdout)
                run = json.loads((self.out / "run.json").read_text())
                self.assertIn("fake failure", run["error"])
                self.assertIsNone(run["review"])

    def test_oversized_prompt_is_refused_by_the_window_and_agy_by_argv_bytes(self):
        (self.src / "pkg" / "b.py").write_text("x = 1\n" * 160_000)  # about 960 KB, about 320K tokens
        r = self.run_one("codex")  # 400K stand-in window: 320K is over 80%
        self.assertEqual(r.returncode, 4, r.stderr + r.stdout)
        self.assertRegex(json.loads((self.out / "run.json").read_text())["error"], r"over 80% of gpt-6-astra's 400000-token window")
        self.assertEqual([c for c in self.calls() if c["cli"] == "codex"], [])
        shutil.rmtree(self.out)
        r = self.run_one("antigravity")  # 1M window passes; argv does not
        self.assertEqual(r.returncode, 4, r.stderr + r.stdout)
        self.assertIn("agy takes it on argv", json.loads((self.out / "run.json").read_text())["error"])
        self.assertEqual([c for c in self.calls() if c["cli"] == "agy"], [])

    def test_a_missing_cli_exits_3_before_anything_is_created_and_the_fake_dir_is_bounded(self):
        self.env["AGENT_REVIEW_CLI_DIR"] = str(self.tmp / "no-such")
        r = self.run_one("antigravity")
        self.assertEqual(r.returncode, 2, r.stderr)  # the fake dir must sit in a skill's tests folder
        self.assertIn("tests folder", r.stderr)
        empty = HERE / f"empty-cli-{os.getpid()}"
        empty.mkdir()
        try:
            self.env["AGENT_REVIEW_CLI_DIR"] = str(empty)
            r = self.run_one("antigravity")
            self.assertEqual(r.returncode, 3, r.stderr)
            self.assertIn("not on PATH", r.stderr)
            self.assertFalse(self.out.exists())
        finally:
            empty.rmdir()
        # PATH is not consulted when the fake dir is set: the fakes answer with PATH emptied
        self.env["AGENT_REVIEW_CLI_DIR"] = str(HERE / "fake-cli")
        env = dict(self.env, AGENT_REVIEW_FAKE_RESPONSES="{}", PATH=os.path.dirname(shutil.which("git")))
        args = [sys.executable, str(SCRIPT), "run", "--harness", "antigravity", "--brief", str(self.brief), "--out", str(self.out),
                "--file", str(self.src / "pkg" / "a.py")]
        r = subprocess.run(args, env=env, text=True, capture_output=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)


class TestOllama(Base):
    """The real ollama runner against a fake daemon on loopback; no fake harness binary."""
    TAG = "deepseek-v4.1-flash:cloud"
    KEY_LINE = "-----BEGIN PRIVATE KEY----- fixture -----END PRIVATE KEY-----"

    def setUp(self):
        super().setUp()
        self.fake = None
        self.env = {k: v for k, v in self.env.items() if k != "AGENT_REVIEW_FAKE_BIN"}

    def tearDown(self):
        if self.fake:
            self.fake.stop()
        super().tearDown()

    def serve(self, **kw):
        if str(HERE) not in sys.path:
            sys.path.insert(0, str(HERE))
        from fake_ollama import FakeOllama
        self.fake = FakeOllama(**kw).start()
        self.env["OLLAMA_HOST"] = self.fake.host
        return self.fake

    def run_ollama(self, extra=(), tag=None, files=None):
        return self.run_review(harness="ollama", extra=["--model", tag or self.TAG, "--allow-cloud", *extra], files=files)

    def test_files_are_inlined_with_line_numbers_and_nothing_else_is_sent(self):
        fake = self.serve(thinking={"values": [False, "low", "high", "max"], "default": "high"})
        (self.src / "pkg" / "b.py").write_text(f"x = 1\ny = 2\nKEY = '{self.KEY_LINE}'\n")
        r = self.run_ollama(files=[str(self.src / "pkg" / "a.py"), str(self.src / "pkg" / "b.py")])
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        chat = fake.posts("/api/chat")
        self.assertEqual(len(chat), 1)
        body = chat[0]["body"]
        self.assertEqual((body["model"], body["stream"], body["options"], body["think"]),
                         (self.TAG, True, {"temperature": 0, "num_predict": ar.OLLAMA_MAX_OUTPUT_TOKENS}, "high"))
        self.assertEqual([m["role"] for m in body["messages"]], ["system", "user"])
        self.assertIn("line number", body["messages"][0]["content"])
        user = body["messages"][1]["content"]
        self.assertIn("Is f correct?", user)
        self.assertIn("## a.py\n\n```\n1: def f():\n2:     return 1\n```", user)
        self.assertIn("## b.py\n\n```\n1: x = 1\n2: y = 2\n3: KEY = '[SECRET]'\n```", user)
        self.assertNotIn("PRIVATE KEY", user)  # the request body carries the clean stage, never the original
        self.assertNotIn("not for review", user)
        self.assertNotIn("# notes", user)
        run = json.loads((self.out / "run.json").read_text())
        self.assertEqual((run["harness"], run["model"], run["effort"], run["model_reported"]), ("ollama", self.TAG, "high", self.TAG))
        self.assertEqual(run["usage"]["think"], "high")
        self.assertEqual(run["usage"]["files_inlined"], 2)
        self.assertEqual(run["usage"]["context_length"], 1048576)
        self.assertIsNone(run["thinking"])
        self.assertIn("OK: the files say so.", Path(run["review"]).read_text())
        self.assertEqual(Path(run["review"]).name, f"{date.today().isoformat()}-review-ollama-deepseek-v4-1-flash-cloud-brief.md")

    def test_thinking_goes_beside_the_run_and_never_into_the_review(self):
        self.serve(thinking={"values": [False, True], "default": True}, thinking_text="private reasoning")
        r = self.run_ollama(extra=["--effort", "max"])
        self.assertEqual(r.returncode, 0, r.stderr)
        run = json.loads((self.out / "run.json").read_text())
        self.assertIs(run["usage"]["think"], True)
        self.assertEqual(Path(run["thinking"]), self.out / "thinking-deepseek-v4-1-flash-cloud.md")
        self.assertEqual(Path(run["thinking"]).read_text(), "private reasoning")
        self.assertNotIn("private reasoning", Path(run["review"]).read_text())

    def test_off_is_sent_as_false_and_refused_where_the_tag_cannot_stop_thinking(self):
        fake = self.serve(thinking={"values": [False, "low", "high"], "default": "high"})
        r = self.run_ollama(extra=["--effort", "off"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIs(fake.posts("/api/chat")[0]["body"]["think"], False)
        fake.stop()
        fake = self.serve(thinking={"values": ["low", "high", "max"], "default": "max"})
        shutil.rmtree(self.out)
        r = self.run_ollama(extra=["--effort", "off"])
        self.assertEqual(r.returncode, 4)
        self.assertEqual(fake.posts("/api/chat"), [])
        run = json.loads((self.out / "run.json").read_text())
        self.assertIn("cannot turn thinking off", run["error"])

    def test_oversized_input_is_refused_before_the_call_and_names_the_figure(self):
        fake = self.serve(context=200)
        r = self.run_ollama()
        self.assertEqual(r.returncode, 4, r.stderr + r.stdout)
        self.assertEqual(fake.posts("/api/chat"), [])
        run = json.loads((self.out / "run.json").read_text())
        self.assertRegex(run["error"], r"about \d+ tokens, over 80% of .*200-token window")
        self.assertIsNone(run["review"])

    def test_cloud_gate_both_ways_exits_2_before_anything_is_created(self):
        self.serve(tags=(self.TAG, "qwen3.5:4b"))
        r = self.run_review(harness="ollama", extra=["--model", self.TAG])
        self.assertEqual(r.returncode, 2)
        self.assertIn("--allow-cloud", r.stderr)
        r = self.run_review(harness="ollama", extra=["--model", "qwen3.5:4b", "--allow-cloud"])
        self.assertEqual(r.returncode, 2)
        self.assertIn("cloud tags only", r.stderr)
        self.assertFalse(self.out.exists())
        self.assertEqual(self.fake.requests, [])

    def test_non_loopback_host_is_refused_and_a_missing_tag_or_daemon_exits_3(self):
        self.serve(tags=("other:cloud",))
        r = self.run_ollama()
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertIn("ollama pull", r.stderr)
        self.assertFalse(self.out.exists())
        self.env["OLLAMA_HOST"] = "http://10.0.0.5:11434"
        r = self.run_ollama()
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("loopback", r.stderr)
        self.fake.stop()
        self.env["OLLAMA_HOST"] = self.fake.host  # now a dead port
        r = self.run_ollama()
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertIn("not answering", r.stderr)
        self.fake = None

    def test_reported_model_may_drop_the_cloud_suffix_but_not_change(self):
        self.serve(model_in_reply="deepseek-v4.1-flash")
        r = self.run_ollama()
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertEqual(json.loads((self.out / "run.json").read_text())["model_reported"], "deepseek-v4.1-flash")
        self.fake.stop()
        shutil.rmtree(self.out)
        self.serve(model_in_reply="other-model")
        r = self.run_ollama()
        self.assertEqual(r.returncode, 4)
        self.assertIn("model mismatch", json.loads((self.out / "run.json").read_text())["error"])

    def test_the_chat_is_streamed_and_reassembled(self):
        fake = self.serve(thinking={"values": [False, True], "default": True}, thinking_text="step one, step two",
                          reply="A long reply that arrives in several chunks of seven characters.")
        r = self.run_ollama()
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        body = fake.posts("/api/chat")[0]["body"]
        self.assertIs(body["stream"], True)
        run = json.loads((self.out / "run.json").read_text())
        self.assertEqual(Path(run["review"]).read_text(), "A long reply that arrives in several chunks of seven characters.")
        self.assertEqual(Path(run["thinking"]).read_text(), "step one, step two")
        self.assertEqual((run["usage"]["attempts"], run["usage"]["retried_after"]), (1, None))
        self.assertGreater(run["usage"]["eval_count"], 0)

    def test_a_5xx_or_a_cut_stream_is_retried_once_and_recorded(self):
        fake = self.serve(fail_first=1)
        r = self.run_ollama()
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertEqual(len(fake.posts("/api/chat")), 2)
        run = json.loads((self.out / "run.json").read_text())
        self.assertEqual(run["usage"]["attempts"], 2)
        self.assertIn("HTTP 502", run["usage"]["retried_after"])
        self.fake.stop()
        shutil.rmtree(self.out)
        fake = self.serve(fail_first=2)
        r = self.run_ollama()
        self.assertEqual(r.returncode, 4)
        self.assertEqual(len(fake.posts("/api/chat")), 2)
        self.assertIn("HTTP 502", json.loads((self.out / "run.json").read_text())["error"])
        self.fake.stop()
        shutil.rmtree(self.out)
        fake = self.serve(cut_stream=True)
        r = self.run_ollama()
        self.assertEqual(r.returncode, 4)
        self.assertEqual(len(fake.posts("/api/chat")), 2)
        self.assertIn("before its final chunk", json.loads((self.out / "run.json").read_text())["error"])

    def test_a_4xx_and_an_empty_reply_are_not_retried(self):
        fake = self.serve(status=404)
        r = self.run_ollama()
        self.assertEqual(r.returncode, 4)
        self.assertEqual(len(fake.posts("/api/chat")), 1)
        self.assertIn("HTTP 404", json.loads((self.out / "run.json").read_text())["error"])
        self.fake.stop()
        shutil.rmtree(self.out)
        fake = self.serve(reply="")
        r = self.run_ollama()
        self.assertEqual(r.returncode, 4)
        self.assertEqual(len(fake.posts("/api/chat")), 1)
        self.assertIn("no content", json.loads((self.out / "run.json").read_text())["error"])

    def in_process(self, fake, timeout, effort="high"):
        """Call the runner directly with a short timeout, so the clock tests stay fast."""
        from unittest import mock
        with mock.patch.dict(os.environ, {"OLLAMA_HOST": fake.host, "AGENT_REVIEW_TEST": "1"}):
            cfg = ar.resolve("ollama", self.TAG, effort, allow_cloud=True)
            stage = Path(tempfile.mkdtemp(prefix="stage-", dir=self.tmp))
            (stage / "a.py").write_text("x = 1\n")
            started = time.monotonic()
            res = ar.run_harness(cfg, self.brief, stage, timeout, self.tmp)
        return res, time.monotonic() - started

    def test_the_wall_clock_is_the_scripts_not_the_sockets(self):
        # chunks keep arriving, so a socket idle timeout never fires; the call's own deadline does
        fake = self.serve(chunk_delay=0.3, reply="x" * 70)  # ten content chunks, three seconds
        res, elapsed = self.in_process(fake, 1)
        self.assertEqual(res["exit_code"], 4)
        self.assertIn("did not finish within", res["error"])
        self.assertLess(elapsed, 2.5)
        self.assertEqual(len(fake.posts("/api/chat")), 1)

    def test_a_dribbled_line_without_a_newline_is_bounded_by_the_deadline(self):
        fake = self.serve(dribble=(64, 0.05))  # bytes forever, never a newline: readline would block past any clock
        res, elapsed = self.in_process(fake, 1)
        self.assertEqual(res["exit_code"], 4)
        self.assertIn("did not finish within", res["error"])
        self.assertLess(elapsed, 2.5)

    def test_output_is_bounded_and_a_thinking_loop_is_named(self):
        looped = "\n".join(["A's claim \"x.py lines 1-2\" is correct."] * 60 + ["one more thought"])
        fake = self.serve(thinking={"values": [False, "low", "high"], "default": "high"}, thinking_text=looped, reply="")
        res, _ = self.in_process(fake, 30)
        self.assertEqual(res["exit_code"], 4, res)
        self.assertIn("looped in its thinking (one line repeated 60 times)", res["error"])
        self.assertEqual(res["usage"]["thinking_loop"], 60)
        body = fake.posts("/api/chat")[0]["body"]
        self.assertEqual(body["options"]["num_predict"], ar.OLLAMA_MAX_OUTPUT_TOKENS)
        self.assertTrue(Path(res["thinking"]).exists())        # the thinking is still on disk for the record
        self.assertEqual(ar.thinking_loop("a\nb\nc"), 0)

    def test_a_failed_stream_keeps_the_text_received_so_far(self):
        fake = self.serve(raw_lines=[b'{"done": false, "message": {"role": "assistant", "content": "good so far "}}',
                                     b'{"done": false, "message": {"role": "assistant", "thinking": "hmm"}}',
                                     b"not json at all"])
        res, _ = self.in_process(fake, 30)
        self.assertEqual(res["exit_code"], 4, res)
        self.assertIsNone(res["text"])
        self.assertIn("not JSON", res["error"])
        self.assertIn("12 characters of content kept at", res["error"])
        partial = self.tmp / f"partial-{ar.slug(self.TAG)}.md"
        self.assertEqual(partial.read_text(), "good so far ")
        self.assertEqual((self.tmp / f"partial-thinking-{ar.slug(self.TAG)}.md").read_text(), "hmm")

    def test_the_text_cap_is_on_characters_and_a_cut_reply_is_kept(self):
        from unittest import mock
        fake = self.serve(reply="y" * 700)
        with mock.patch.object(ar, "OLLAMA_MAX_TEXT", 100):
            res, _ = self.in_process(fake, 30)
        self.assertEqual(res["exit_code"], 4, res)
        self.assertIsNone(res["text"])
        self.assertTrue(res["usage"]["truncated"])
        self.assertIn("was cut", res["error"])
        kept = (self.tmp / f"partial-{ar.slug(self.TAG)}.md").read_text()
        self.assertGreaterEqual(len(kept), 100)
        self.assertLess(len(kept), 200)
        self.assertEqual(len(fake.posts("/api/chat")), 1)       # a cut is not retried
        # framing is not text: 700 characters of content arrive as about 100 chunks of
        # a few hundred bytes each, and the default text cap lets the whole reply through
        self.fake.stop()
        fake = self.serve(reply="y" * 700)
        res, _ = self.in_process(fake, 30)
        self.assertEqual(res["exit_code"], 0, res)
        self.assertFalse(res["usage"]["truncated"])
        self.assertEqual(len(res["text"]), 700)

    def test_an_oversized_chunk_is_refused_before_it_is_buffered(self):
        fake = self.serve(raw_lines=[b"x" * (ar.OLLAMA_MAX_LINE + 10)])
        res, _ = self.in_process(fake, 30)
        self.assertEqual(res["exit_code"], 4)
        self.assertIn("chunk over", res["error"])
        self.assertEqual(len(fake.posts("/api/chat")), 1)  # a malformed stream is not retried

    def test_malformed_chunks_are_protocol_errors_not_partial_successes(self):
        cases = {
            b"not json at all": "not JSON",
            b'["a", "list"]': "not an object",
            b'{"done": "false", "message": {"role": "assistant", "content": "x"}}': "done is not a boolean",
            b'{"done": false, "message": {"role": "assistant", "content": ["x"]}}': "content is not a string",
            b'{"done": false, "message": "x"}': "message is not an object",
        }
        for raw, expect in cases.items():
            with self.subTest(raw=raw):
                if self.fake:
                    self.fake.stop()
                fake = self.serve(raw_lines=[b'{"done": false, "message": {"role": "assistant", "content": "good "}}', raw])
                res, _ = self.in_process(fake, 30)
                self.assertEqual(res["exit_code"], 4, res)
                self.assertIn(expect, res["error"])
                self.assertIsNone(res["text"])
                self.assertEqual(len(fake.posts("/api/chat")), 1)

    def test_an_error_chunk_is_final_and_never_retried_whatever_it_says(self):
        fake = self.serve(error_chunk="upstream returned HTTP 502: connection to the daemon dropped")
        res, _ = self.in_process(fake, 30)
        self.assertEqual(res["exit_code"], 4)
        self.assertIn("/api/chat reported: upstream returned HTTP 502", res["error"])
        self.assertIsNone(res["text"])
        self.assertEqual(len(fake.posts("/api/chat")), 1)

    def test_a_chunked_response_cut_mid_chunk_is_a_dropped_connection_and_is_retried(self):
        # http.client raises IncompleteRead, an HTTPException and not an OSError, for a chunked
        # body that ends inside a chunk; the runner must treat it as a dropped connection
        fake = self.serve(framing="chunked", cut_stream=True)
        res, _ = self.in_process(fake, 60)
        self.assertEqual(res["exit_code"], 4)
        self.assertEqual(len(fake.posts("/api/chat")), 2)
        self.assertIn("attempt 2 of 2 failed", res["error"])
        self.assertIn("attempt 1 failed", res["error"])
        self.assertIn("IncompleteRead", res["error"])

    def test_the_retry_shares_one_deadline_and_the_pause_counts_against_it(self):
        fake = self.serve(fail_first=1)
        res, elapsed = self.in_process(fake, 40)
        self.assertEqual(res["exit_code"], 0, res)
        self.assertEqual(res["usage"]["attempts"], 2)
        self.assertGreaterEqual(elapsed, ar.OLLAMA_RETRY_PAUSE_S)
        self.assertLess(elapsed, 40)
        self.fake.stop()
        fake = self.serve(fail_first=1)
        res, elapsed = self.in_process(fake, 34)  # under the pause plus 30 s floor: no retry
        self.assertEqual(res["exit_code"], 4)
        self.assertEqual(len(fake.posts("/api/chat")), 1)
        self.assertLess(elapsed, 3)

    def test_harnesses_table_lists_ollama(self):
        self.serve()
        r = subprocess.run([sys.executable, str(SCRIPT), "harnesses"], env=self.env, text=True, capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        line = [l for l in r.stdout.splitlines() if l.startswith("ollama")][0]
        self.assertIn("(a :cloud tag)", line)
        self.assertIn("yes", line)


class TestReviewPaths(Base):
    def _git_root(self, name: str, with_tasks: bool) -> Path:
        root = self.tmp / name
        (root / "deep" / "er").mkdir(parents=True)
        (root / ".git").mkdir()
        if with_tasks:
            (root / "tasks").mkdir()
        (root / "deep" / "er" / "x.py").write_text("x = 1\n")
        return root

    def test_git_root_with_tasks_gets_tasks_reviews_and_without_gets_reviews(self):
        root = self._git_root("repo-a", with_tasks=True)
        r = self.run_review(files=[str(root / "deep" / "er" / "x.py")])
        self.assertEqual(r.returncode, 0, r.stderr)
        run = json.loads((self.out / "run.json").read_text())
        self.assertEqual(Path(run["review"]).parent, root / "tasks" / "reviews")
        self.assertEqual(run["reviews_dir_rule"], "git-root-tasks")
        shutil.rmtree(self.out)
        root = self._git_root("repo-b", with_tasks=False)
        r = self.run_review(files=[str(root / "deep" / "er" / "x.py")])
        self.assertEqual(r.returncode, 0, r.stderr)
        run = json.loads((self.out / "run.json").read_text())
        self.assertEqual(Path(run["review"]).parent, root / "reviews")
        self.assertEqual(run["reviews_dir_rule"], "git-root")
        self.assertFalse((root / "tasks").exists())

    def test_root_flag_sets_the_start_and_the_first_file_wins_otherwise(self):
        root = self._git_root("repo-c", with_tasks=True)
        other = self.src / "notes.md"
        r = self.run_review(files=[str(other), str(root / "deep" / "er" / "x.py")], extra=["--root", str(self.tmp)])
        self.assertEqual(r.returncode, 0, r.stderr)
        run = json.loads((self.out / "run.json").read_text())
        self.assertEqual(Path(run["review"]).parent, self.tmp / "reviews")
        self.assertEqual(run["reviews_dir_rule"], "no-git-root")

    def test_topic_reviews_dir_and_model_slug(self):
        rd = self.tmp / "elsewhere"
        r = self.run_review(harness="cursor", extra=["--topic", "Sanitize Phase 1b!", "--reviews-dir", str(rd),
                                                     "--model", "grok-4.7-xhigh"])
        self.assertEqual(r.returncode, 0, r.stderr)
        run = json.loads((self.out / "run.json").read_text())
        self.assertEqual(Path(run["review"]), rd / f"{date.today().isoformat()}-review-cursor-grok-4-7-xhigh-Sanitize-Phase-1b.md")
        self.assertEqual((run["topic"], run["reviews_dir_rule"]), ("Sanitize-Phase-1b", "reviews-dir"))

    def test_same_day_rerun_gets_a_suffix_and_the_first_file_is_untouched(self):
        r1 = self.run_review(responses={"codex": {"text": "first text"}})
        self.assertEqual(r1.returncode, 0, r1.stderr)
        first = Path(json.loads((self.out / "run.json").read_text())["review"])
        before = first.read_bytes()
        shutil.rmtree(self.out)
        r2 = self.run_review(responses={"codex": {"text": "second text"}})
        self.assertEqual(r2.returncode, 0, r2.stderr)
        second = Path(json.loads((self.out / "run.json").read_text())["review"])
        self.assertEqual(second.name, first.stem + "-2.md")
        self.assertEqual(first.read_bytes(), before)
        shutil.rmtree(self.out)
        r3 = self.run_review()
        third = Path(json.loads((self.out / "run.json").read_text())["review"])
        self.assertEqual(third.name, first.stem + "-3.md")

    @unittest.skipIf(os.geteuid() == 0, "root can write anywhere")
    def test_unwritable_reviews_dir_falls_back_to_the_run_folder(self):
        rd = self.tmp / "ro"
        rd.mkdir()
        os.chmod(rd, 0o500)
        try:
            r = self.run_review(extra=["--reviews-dir", str(rd)])
            self.assertEqual(r.returncode, 0, r.stderr)
            run = json.loads((self.out / "run.json").read_text())
            self.assertEqual(Path(run["review"]).parent, self.out)
            self.assertEqual(run["reviews_dir_rule"], "fallback-run-folder")
            self.assertIn("not writable", r.stdout)
        finally:
            os.chmod(rd, 0o700)

    def test_symlink_missing_and_outside_root_are_refused_before_staging(self):
        os.symlink(self.src / "notes.md", self.src / "link.md")
        self.assertEqual(self.run_review(files=[str(self.src / "link.md")]).returncode, 2)
        self.assertEqual(self.run_review(files=[str(self.src / "nope.md")]).returncode, 2)
        r = self.run_review(files=[str(self.src / "notes.md"), str(self.brief)], extra=["--root", str(self.src)])
        self.assertEqual(r.returncode, 2)
        self.assertIn("outside", r.stderr)
        self.assertFalse(self.out.exists())

    def test_bad_harness_and_effort_exit_2(self):
        self.assertEqual(self.run_review(harness="gemini").returncode, 2)
        self.assertEqual(self.run_review(extra=["--effort", "ludicrous"]).returncode, 2)

    def test_fake_bin_needs_the_opt_in_and_a_tests_folder(self):
        from unittest import mock
        with mock.patch.dict(os.environ, {"AGENT_REVIEW_FAKE_BIN": str(FAKE)}, clear=False):
            os.environ.pop("AGENT_REVIEW_TEST", None)
            self.assertIsNone(ar.fake_bin())
            self.assertNotIn("AGENT_REVIEW_FAKE_BIN", ar.child_env())
            os.environ["AGENT_REVIEW_TEST"] = "1"
            self.assertEqual(ar.fake_bin(), str(FAKE.resolve()))
            os.environ["AGENT_REVIEW_FAKE_BIN"] = str(self.tmp / "evil.py")
            with self.assertRaises(ar.ReviewError):
                ar.fake_bin()
        run_json = None
        r = self.run_review()
        self.assertEqual(r.returncode, 0, r.stderr)
        run_json = json.loads((self.out / "run.json").read_text())
        self.assertTrue(run_json["test_mode"])
        self.assertEqual(run_json["fake_bin"], str(FAKE.resolve()))

    def test_symlinked_parent_below_the_base_is_refused(self):
        link_dir = self.src / "linkdir"
        os.symlink(self.src / "pkg", link_dir)
        r = self.run_review(files=[str(self.src / "notes.md"), str(link_dir / "a.py")])
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("symlink", r.stderr)
        # a single file reached through a link above its own parent stages the real file
        r = self.run_review(files=[str(link_dir / "a.py")])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads((self.out / "files.json").read_text()), ["a.py"])

    def test_harnesses_table_prints_availability(self):
        env = dict(self.env, AGENT_REVIEW_FAKE_MISSING="cursor")
        r = subprocess.run([sys.executable, str(SCRIPT), "harnesses"], env=env, text=True, capture_output=True)
        self.assertEqual(r.returncode, 0)
        rows = {line.split()[0]: line for line in r.stdout.splitlines()[1:]}
        for name in ("claude", "codex", "antigravity"):
            self.assertIn("yes", rows[name], rows[name])
        self.assertIn("not installed", rows["cursor"])

    def test_missing_cli_exits_3_before_anything_is_created(self):
        env = {k: v for k, v in self.env.items() if k not in ("AGENT_REVIEW_FAKE_BIN", "AGENT_REVIEW_TEST")}
        empty = self.tmp / "nobin"
        empty.mkdir()
        env["PATH"] = str(empty)
        args = [sys.executable, str(SCRIPT), "run", "--harness", "claude", "--brief", str(self.brief),
                "--out", str(self.out), "--file", str(self.src / "notes.md")]
        r = subprocess.run(args, env=env, text=True, capture_output=True, timeout=120)
        self.assertEqual(r.returncode, 3, r.stderr + r.stdout)
        self.assertIn("not on PATH", r.stderr)
        self.assertFalse(self.out.exists())

    def test_fake_missing_harness_exits_3_in_test_mode(self):
        self.env["AGENT_REVIEW_FAKE_MISSING"] = "codex"
        r = self.run_review(harness="codex")
        self.assertEqual(r.returncode, 3, r.stderr + r.stdout)
        self.assertIn("unavailable", r.stderr)
        self.assertFalse(self.out.exists())
        self.assertEqual(self.calls(), [])


if __name__ == "__main__":
    unittest.main()
