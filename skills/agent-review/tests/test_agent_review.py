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
import unittest
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
        self.tmp = Path(tempfile.mkdtemp(prefix="agent-review-test-"))
        self.src = self.tmp / "src"
        (self.src / "pkg").mkdir(parents=True)
        (self.src / "pkg" / "a.py").write_text("def f():\n    return 1\n")
        (self.src / "notes.md").write_text("# notes\n")
        (self.src / "secret.txt").write_text("not for review\n")
        self.brief = self.tmp / "brief.md"
        self.brief.write_text("Is f correct?\n")
        self.out = self.tmp / "out"
        self.record = self.tmp / "calls.jsonl"
        self.env = dict(os.environ, AGENT_REVIEW_TEST="1", AGENT_REVIEW_FAKE_BIN=str(FAKE), AGENT_REVIEW_STATE=str(self.tmp / "state"),
                        AGENT_REVIEW_FAKE_RECORD=str(self.record))

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
        self.assertIn("Review from codex on gpt-6-astra", (self.out / "review.md").read_text())
        run = json.loads((self.out / "run.json").read_text())
        self.assertEqual((run["harness"], run["model"], run["effort"]), ("codex", "gpt-6-astra", "high"))
        self.assertNotIn("text", run)
        call = self.calls()[0]
        self.assertEqual(Path(call["stage"]).resolve(), stage.resolve())
        self.assertIn("Is f correct?", call["brief_text"])
        self.assertIn("- pkg/a.py", call["brief_text"])
        self.assertIn("read-only shell commands", call["brief_text"])
        self.assertNotIn("{{", call["brief_text"])

    def test_tool_note_follows_the_harness(self):
        self.run_review(harness="antigravity")
        self.assertIn("Do not run any shell command", self.calls()[0]["brief_text"])
        shutil.rmtree(self.out)
        self.run_review(harness="claude")
        self.assertIn("Read tool", self.calls()[1]["brief_text"])

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
        self.assertFalse((self.out / "review.md").exists())
        run = json.loads((self.out / "run.json").read_text())
        self.assertEqual(run["error"], "fake failure")

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

    def test_harnesses_table_prints(self):
        r = subprocess.run([sys.executable, str(SCRIPT), "harnesses"], env=self.env, text=True, capture_output=True)
        self.assertEqual(r.returncode, 0)
        for name in ("claude", "codex", "cursor", "antigravity"):
            self.assertIn(name, r.stdout)


if __name__ == "__main__":
    unittest.main()
