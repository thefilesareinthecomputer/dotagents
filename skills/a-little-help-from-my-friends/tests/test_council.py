#!/usr/bin/env python3
"""Tests for skills/a-little-help-from-my-friends/scripts/council.py with a fake member
binary. No model, no network.
Run: python3 -m unittest discover -s skills/a-little-help-from-my-friends/tests -v
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
SCRIPT = HERE.parent / "scripts" / "council.py"
FAKE = HERE / "fake_member.py"
MEMBERS = ["claude", "codex", "cursor", "antigravity"]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="council-test-"))
        self.src = self.tmp / "src"
        (self.src / "pkg").mkdir(parents=True)
        (self.src / "pkg" / "a.py").write_text("def f():\n    return 1\n")
        (self.src / "notes.md").write_text("# notes\nthe answer is 42\n")
        (self.src / "secret.txt").write_text("not for the panel\n")
        self.question = self.tmp / "q.md"
        self.question.write_text("Is f correct?\n")
        self.out = self.tmp / "out"
        self.record = self.tmp / "calls.jsonl"
        self.env = dict(os.environ, AGENT_REVIEW_TEST="1", AGENT_REVIEW_FAKE_BIN=str(FAKE), COUNCIL_STATE=str(self.tmp / "state"),
                        AGENT_REVIEW_FAKE_RECORD=str(self.record))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_council(self, responses=None, extra=(), files=None):
        if responses is None:
            responses = {m: {"stage2": "ABCD"} for m in MEMBERS}
        env = dict(self.env, AGENT_REVIEW_FAKE_RESPONSES=json.dumps(responses))
        files = files or [str(self.src / "pkg" / "a.py"), str(self.src / "notes.md")]
        args = [sys.executable, str(SCRIPT), "run", "--question", str(self.question), "--out", str(self.out), *extra]
        for f in files:
            args += ["--file", f]
        return subprocess.run(args, env=env, text=True, capture_output=True, timeout=120)

    def calls(self):
        return [json.loads(l) for l in self.record.read_text().splitlines()] if self.record.exists() else []


class TestStaging(Base):
    def test_only_named_files_are_staged_with_relative_paths(self):
        r = self.run_council()
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        stage = self.out / "stage"
        self.assertTrue((stage / "pkg" / "a.py").exists())
        self.assertTrue((stage / "notes.md").exists())
        self.assertFalse((stage / "secret.txt").exists())
        self.assertTrue((stage / ".git").exists())
        self.assertEqual(json.loads((self.out / "files.json").read_text()), ["pkg/a.py", "notes.md"])
        for call in self.calls():
            self.assertEqual(Path(call["stage"]).resolve(), stage.resolve())

    def test_symlink_missing_and_outside_root_are_refused(self):
        os.symlink(self.src / "notes.md", self.src / "link.md")
        r = self.run_council(files=[str(self.src / "link.md"), str(self.src / "notes.md")])
        self.assertEqual(r.returncode, 2)
        self.assertIn("symlink", r.stderr)
        r = self.run_council(files=[str(self.src / "nope.md"), str(self.src / "notes.md")])
        self.assertEqual(r.returncode, 2)
        r = self.run_council(files=[str(self.src / "notes.md"), str(self.question)], extra=["--root", str(self.src)])
        self.assertEqual(r.returncode, 2)
        self.assertIn("outside", r.stderr)
        self.assertFalse((self.out / "stage").exists())


class TestStages(Base):
    def test_full_run_writes_every_stage_and_the_synthesis(self):
        responses = {m: {"stage2": "ABCD"} for m in MEMBERS}
        responses["claude"]["chair"] = "The chair's synthesis."
        r = self.run_council(responses)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        for m in MEMBERS:
            self.assertTrue((self.out / "stage1" / f"{m}.md").exists(), m)
            self.assertTrue((self.out / "stage1" / f"{m}-brief.md").exists(), m)
            self.assertTrue((self.out / "stage2" / f"{m}.md").exists(), m)
            self.assertTrue((self.out / "stage2" / f"{m}-brief.md").exists(), m)
        # the tool note is per runner: Codex reads through the shell, agy must not touch it
        self.assertIn("read-only shell commands", (self.out / "stage1" / "codex-brief.md").read_text())
        self.assertIn("Do not run any shell command", (self.out / "stage2" / "antigravity-brief.md").read_text())
        self.assertIn("Read tool", (self.out / "chair-brief.md").read_text())
        self.assertNotIn("{{", (self.out / "stage1" / "cursor-brief.md").read_text())
        for name in ("blinding.json", "tally.json", "tally.md", "chair-brief.md", "synthesis.md", "run.json", "question.md"):
            self.assertTrue((self.out / name).exists(), name)
        self.assertEqual((self.out / "synthesis.md").read_text(), "The chair's synthesis.")
        run = json.loads((self.out / "run.json").read_text())
        self.assertEqual(run["exit_code"], 0)
        self.assertEqual(run["stage1"]["cursor"]["model"], "grok-4.7")
        self.assertEqual(run["stage1"]["cursor"]["effort"], "high")
        self.assertNotIn("text", run["stage1"]["cursor"])
        # one stage-1 call, one stage-2 call per member, plus the chair
        self.assertEqual(len(self.calls()), 2 * len(MEMBERS) + 1)
        last = self.calls()[-1]
        self.assertEqual(last["member"], "claude")
        self.assertTrue(last["brief"].endswith("chair-brief.md"))

    def test_stage2_briefs_hide_authors_and_shuffle_per_reviewer(self):
        responses = {m: {"stage1": f"UNIQUE-{m.upper()}-TEXT", "stage2": "ABCD"} for m in MEMBERS}
        r = self.run_council(responses)
        self.assertEqual(r.returncode, 0, r.stderr)
        blinding = json.loads((self.out / "blinding.json").read_text())
        maps = set()
        for m in MEMBERS:
            brief = (self.out / "stage2" / f"{m}-brief.md").read_text()
            for name in MEMBERS + ["claude-fable", "gpt-6", "gemini-3", "grok-4", "Astra", "Fable"]:
                self.assertNotIn(name, brief, f"{name} visible to {m}")
            for member in MEMBERS:
                self.assertIn(f"UNIQUE-{member.upper()}-TEXT", brief)
            labels = blinding[m]["labels"]
            self.assertEqual(sorted(labels), ["A", "B", "C", "D"])
            self.assertEqual(sorted(labels.values()), sorted(MEMBERS))
            maps.add(tuple(labels[k] for k in "ABCD"))
        self.assertGreater(len(maps), 1, "every reviewer saw the same permutation")

    def test_tally_is_a_borda_count_with_and_without_self_votes(self):
        # Every reviewer ranks the labels in the order shown, so the ranking equals the
        # blinding permutation; recompute the expected points from blinding.json.
        responses = {m: {"stage2": "ABCD"} for m in MEMBERS}
        r = self.run_council(responses)
        self.assertEqual(r.returncode, 0, r.stderr)
        blinding = json.loads((self.out / "blinding.json").read_text())
        tally = json.loads((self.out / "tally.json").read_text())
        exp_all = {m: 0 for m in MEMBERS}
        exp_self = {m: 0 for m in MEMBERS}
        for reviewer, b in blinding.items():
            for pos, lab in enumerate("ABCD"):
                m = b["labels"][lab]
                exp_all[m] += 3 - pos
                if m != reviewer:
                    exp_self[m] += 3 - pos
        self.assertEqual(tally["points_all_votes"], exp_all)
        self.assertEqual(tally["points_excluding_self"], exp_self)
        self.assertEqual(tally["valid_reviews"], 4)
        self.assertEqual(tally["order"][0], max(MEMBERS, key=lambda m: (exp_self[m], exp_all[m])))

    def test_invalid_review_is_excluded_and_run_is_partial(self):
        responses = {m: {"stage2": "ABCD"} for m in MEMBERS}
        responses["cursor"]["stage2"] = "invalid"
        r = self.run_council(responses)
        self.assertEqual(r.returncode, 3, r.stderr + r.stdout)
        tally = json.loads((self.out / "tally.json").read_text())
        self.assertEqual(tally["valid_reviews"], 3)
        self.assertIn("cursor", tally["invalid_reviews"])

    def test_failed_member_is_dropped_from_review_and_run_is_partial(self):
        responses = {m: {"stage2": "ABC"} for m in MEMBERS}
        responses["antigravity"] = {"fail": True}
        r = self.run_council(responses)
        self.assertEqual(r.returncode, 3, r.stderr + r.stdout)
        self.assertFalse((self.out / "stage1" / "antigravity.md").exists())
        tally = json.loads((self.out / "tally.json").read_text())
        self.assertEqual(sorted(tally["answered"]), ["claude", "codex", "cursor"])
        brief = (self.out / "stage2" / "claude-brief.md").read_text()
        self.assertNotIn("## Response D", brief)

    def test_two_failures_leave_too_few_to_review(self):
        responses = {"antigravity": {"fail": True}, "cursor": {"fail": True}, "codex": {"fail": True}}
        r = self.run_council(responses)
        self.assertEqual(r.returncode, 4)
        self.assertIn("fewer than two", r.stderr)
        self.assertTrue((self.out / "run.json").exists())

    def test_chair_session_leaves_the_brief_and_no_synthesis(self):
        responses = {m: {"stage2": "ABCD"} for m in MEMBERS}
        r = self.run_council(responses, extra=["--chair", "session"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.out / "chair-brief.md").exists())
        self.assertFalse((self.out / "synthesis.md").exists())
        brief = (self.out / "chair-brief.md").read_text()
        for m in MEMBERS:
            self.assertIn(f"## Answer from {m}", brief)
            self.assertIn(f"## Review by {m}", brief)
        self.assertIn("| Rank | Member |", brief)

    def test_member_subset_and_model_and_effort_overrides(self):
        responses = {m: {"stage2": "AB"} for m in ("claude", "cursor")}
        r = self.run_council(responses, extra=["--members", "claude,cursor", "--model", "cursor=cursor-grok-4.6-xhigh",
                                               "--effort", "claude=max", "--chair", "session"])
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        run = json.loads((self.out / "run.json").read_text())
        self.assertEqual(sorted(run["members"]), ["claude", "cursor"])
        self.assertEqual(run["members"]["cursor"]["model"], "cursor-grok-4.6-xhigh")
        self.assertIsNone(run["members"]["cursor"]["effort"])
        self.assertEqual(run["members"]["claude"]["effort"], "max")
        self.assertEqual(self.calls()[0]["effort"] if self.calls()[0]["member"] == "claude" else self.calls()[1]["effort"], "max")

    def test_global_effort_applies_to_every_member(self):
        r = self.run_council(extra=["--effort", "xhigh", "--chair", "session"])
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        run = json.loads((self.out / "run.json").read_text())
        for m in MEMBERS:
            self.assertEqual(run["members"][m]["effort"], "xhigh", m)

    def test_unknown_member_bad_effort_and_single_member_are_rejected(self):
        self.assertEqual(self.run_council(extra=["--members", "claude,hal9000"]).returncode, 2)
        self.assertEqual(self.run_council(extra=["--members", "claude"]).returncode, 2)
        r = self.run_council(extra=["--effort", "ludicrous"])
        self.assertEqual(r.returncode, 2)
        self.assertIn("effort", r.stderr)

    def test_tally_command_recomputes(self):
        responses = {m: {"stage2": "ABCD"} for m in MEMBERS}
        self.assertEqual(self.run_council(responses, extra=["--chair", "session"]).returncode, 0)
        before = json.loads((self.out / "tally.json").read_text())
        (self.out / "tally.json").unlink()
        r = subprocess.run([sys.executable, str(SCRIPT), "tally", "--run", str(self.out)], env=self.env, text=True, capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads((self.out / "tally.json").read_text())["points_all_votes"], before["points_all_votes"])
        self.assertIn("| Rank |", r.stdout)


if __name__ == "__main__":
    unittest.main()
