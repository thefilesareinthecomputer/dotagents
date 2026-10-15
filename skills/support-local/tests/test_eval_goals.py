#!/usr/bin/env python3
"""Tests for eval_goals.py: grading against keys, and the matrix runner against the fake claude."""

import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "eval_goals.py"
spec = importlib.util.spec_from_file_location("eval_goals", SCRIPT)
eg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eg)


def answer(text, answerable=True, refs=()):
    return {"goal": "g", "answer": text, "answerable": answerable,
            "evidence": [{"claim": "c", "ref": r, "verified": True} for r in refs], "coverage": "", "local_calls": 1, "stop_reason": "answered"}


class TestGrade(unittest.TestCase):
    def test_all_musts_present_is_correct(self):
        key = {"answerable": True, "must": ["EXIT_OK", "130"], "refs": ["scripts/a.py:33", "scripts/a.py"]}
        g = eg.grade(answer("The codes are exit_ok (0) and  130 on interrupt", refs=["scripts/a.py:33"]), key)
        self.assertTrue(g["correct"])
        self.assertEqual((g["must_hit"], g["must_n"]), (2, 2))
        self.assertEqual((g["refs_covered"], g["refs_n"]), (2, 2))

    def test_a_missing_must_is_wrong_and_named(self):
        g = eg.grade(answer("only EXIT_OK"), {"must": ["EXIT_OK", "EXIT_ARGS"]})
        self.assertFalse(g["correct"])
        self.assertEqual(g["missed"], ["EXIT_ARGS"])

    def test_musts_may_sit_in_evidence_claims(self):
        a = answer("see evidence")
        a["evidence"] = [{"claim": "EXIT_ARGS = 2 is the default", "ref": "a.py:1", "verified": False}]
        self.assertTrue(eg.grade(a, {"must": ["EXIT_ARGS"]})["correct"])

    def test_absent_goal_is_correct_only_when_the_worker_abstains(self):
        key = {"answerable": False, "must": [], "refs": []}
        self.assertTrue(eg.grade(answer("nothing found", answerable=False), key)["correct"])
        self.assertFalse(eg.grade(answer("made something up", answerable=True), key)["correct"])

    def test_answerable_goal_answered_as_absent_is_wrong(self):
        self.assertFalse(eg.grade(answer("", answerable=False), {"answerable": True, "must": []})["correct"])

    def test_an_answerable_goal_with_key_refs_needs_a_covered_ref_to_be_correct(self):
        key = {"must": ["EXIT_OK"], "refs": ["scripts/a.py:33"]}
        self.assertFalse(eg.grade(answer("EXIT_OK is the code", refs=[]), key)["correct"])
        self.assertFalse(eg.grade(answer("EXIT_OK is the code", refs=["scripts/other.py:1"]), key)["correct"])
        self.assertTrue(eg.grade(answer("EXIT_OK is the code", refs=["scripts/a.py:33"]), key)["correct"])
        self.assertTrue(eg.grade(answer("EXIT_OK is the code", refs=[]), {"must": ["EXIT_OK"]})["correct"])  # no refs in the key

    def test_ref_line_must_match_when_the_key_gives_one(self):
        g = eg.grade(answer("x", refs=["scripts/a.py:34"]), {"must": [], "refs": ["scripts/a.py:33"]})
        self.assertEqual(g["refs_covered"], 0)
        g = eg.grade(answer("x", refs=["/abs/corpus/scripts/a.py:33"]), {"must": [], "refs": ["scripts/a.py:33"]})
        self.assertEqual(g["refs_covered"], 1)


class TestMatrix(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        fake = self.bin / "claude"
        fake.write_text("#!/bin/sh\nexec " + sys.executable + " " + str(HERE / "fake_claude.py") + ' "$@"\n')
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        self.corpus = self.root / "corpus"
        self.corpus.mkdir()
        (self.corpus / "a.py").write_text("EXIT_OK = 0\n")
        self.goals = self.root / "goals.jsonl"
        self.goals.write_text("\n".join(json.dumps(g) for g in [
            {"id": "t-01", "corpus": str(self.corpus), "kind": "search", "goal": "where is the exit code table",
             "key": {"answerable": True, "must": ["EXIT_OK"], "refs": ["a.py:1"]}},
            {"id": "t-02", "corpus": str(self.corpus), "kind": "absent", "goal": "what is the retry limit",
             "key": {"answerable": False, "must": [], "refs": []}}]) + "\n")
        self.env = {**os.environ, "PATH": f"{self.bin}:{os.environ['PATH']}", "SUPPORT_LOCAL_STATE": str(self.root / "state")}

    def tearDown(self):
        self.tmp.cleanup()

    def test_dry_run_lists_cells(self):
        p = subprocess.run([sys.executable, str(SCRIPT), "--goals", str(self.goals), "--variants", "default,terse", "--efforts", "medium,high", "--dry-run"],
                           capture_output=True, text=True, env=self.env, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("8 runs: 2 goals x 2 variants x 2 efforts x 1", p.stdout)

    def test_matrix_runs_grades_and_writes_results(self):
        out = self.root / "results.jsonl"
        p = subprocess.run([sys.executable, str(SCRIPT), "--goals", str(self.goals), "--variants", "default,local-first", "--out", str(out)],
                           capture_output=True, text=True, env=self.env, timeout=120)
        self.assertEqual(p.returncode, 0, p.stderr)
        rows = [json.loads(l) for l in out.read_text().splitlines()]
        self.assertEqual(len(rows), 4)
        by = {(r["id"], r["variant"]): r for r in rows}
        self.assertTrue(by[("t-01", "default")]["correct"], "the fake answers with EXIT_OK and a verified a.py:1 ref")
        self.assertEqual(by[("t-01", "default")]["refs_covered"], 1)
        self.assertFalse(by[("t-02", "default")]["correct"], "the fake never abstains, so the absent goal is wrong")
        self.assertEqual(by[("t-01", "local-first")]["peak_context_tokens"], 1700)
        self.assertIn("default     effort=None    correct 1/2", p.stdout)
        self.assertIn("abstention ok 0/1", p.stdout)
        p = subprocess.run([sys.executable, str(SCRIPT), "--report", str(out)], capture_output=True, text=True, env=self.env, timeout=60)
        self.assertIn("t-01", p.stdout)


if __name__ == "__main__":
    unittest.main()
