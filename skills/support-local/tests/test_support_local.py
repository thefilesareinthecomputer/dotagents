#!/usr/bin/env python3
"""Tests for support_local.py. The headless worker is a fake claude on PATH (fake_claude.py);
no test spends tokens or reaches a model."""

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
SCRIPT = HERE.parent / "scripts" / "support_local.py"
AGENT = HERE.parent.parent.parent / "agents" / "support-local.md"

spec = importlib.util.spec_from_file_location("support_local", SCRIPT)
sl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sl)


def good_answer(**over):
    return dict({"goal": "g", "answer": "a", "answerable": True, "evidence": [], "coverage": "c", "local_calls": 1,
                 "stop_reason": "answered"}, **over)


class TestAgentDefinition(unittest.TestCase):
    def test_pins_haiku_5_5_and_cannot_spawn(self):
        text = AGENT.read_text()
        fm = text.split("---")[1]
        self.assertIn("model: claude-haiku-5-5", fm, "the haiku alias resolves to 4.5 in Claude Code 2.1.280; the full ID is the pin")
        self.assertIn("effort: high", fm)
        self.assertIn("maxTurns: 30", fm)
        self.assertRegex(fm, r"tools: Bash, Read, Grep, Glob\n")
        self.assertNotIn("Agent", fm.split("tools:")[1].split("\n")[0])
        self.assertEqual(sl.agent_model(), "claude-haiku-5-5")


class TestBrief(unittest.TestCase):
    def test_fills_every_section(self):
        brief = sl.build_brief("Where is the exit code table?", "/tmp/repo", "the file and line", "tests", 12, 5)
        for needle in ("## Goal\n\nWhere is the exit code table?", "## Corpus\n\n/tmp/repo", "the file and line", "tests",
                       "Turns: 12. Local calls: 5.", '"stop_reason"', '"quote"'):
            self.assertIn(needle, brief)
        self.assertNotIn("{goal}", brief)
        self.assertNotIn("{{", brief, "the template's JSON braces are unescaped in the output")

    def test_the_protocol_lives_once_in_the_agent_body_not_again_in_the_default_brief(self):
        # the headless run appends the agent body as the system prompt and a subagent has it as its definition, so a
        # brief that repeated the working rules and the failure protocol sent them twice per turn
        brief = sl.build_brief("g", "/tmp/repo", "", "", 12, 5)
        body = sl.agent_body()
        for rule in ("Never call Ollama directly", "exits 3", "stop_reason: \"blocked\"", "--keep-alive 300"):
            self.assertIn(rule, body, rule)
            self.assertNotIn(rule, brief, rule)
        self.assertIn("## When a call fails", sl.build_brief("g", "/tmp/repo", "", "", 12, 5, "full"))  # the comparison arm keeps its own

    def test_defaults_for_the_optional_sections(self):
        brief = sl.build_brief("goal", "/tmp/repo", "", "", 30, 20)
        self.assertIn("Every part of the goal answered", brief)
        self.assertIn("Anything outside the named corpus", brief)

    def test_variants_render_and_unknown_is_refused(self):
        for variant in ("default", "local-first", "full", "terse"):
            brief = sl.build_brief("goal", "/tmp/repo", "", "", 30, 20, variant)
            self.assertIn("goal", brief)
            self.assertIn('"stop_reason"', brief)
            self.assertIn("answerable: false", brief, "every variant says abstention is a correct result")
            self.assertNotIn("{goal}", brief)
        self.assertIn("Do not open files with Read before", sl.agent_body())   # the local-first rule, now in the one place the worker reads it
        self.assertEqual(sl.build_brief("g", "/tmp/repo", "", "", 30, 20, "local-first"), sl.build_brief("g", "/tmp/repo", "", "", 30, 20, "default"))
        self.assertTrue(sl.build_brief("g", "/tmp/repo", "", "", 30, 20, "full").startswith("# Brief for support-local (full variant)"))
        with self.assertRaises(sl.TaskError):
            sl.build_brief("g", "/tmp/repo", "", "", 30, 20, "bogus")

    def test_refuses_empty_or_oversized(self):
        for args in (("", "/tmp"), ("   ", "/tmp"), ("g", ""), ("x" * 2001, "/tmp")):
            with self.assertRaises(sl.TaskError):
                sl.build_brief(args[0], args[1], "", "", 30, 20)
        with self.assertRaises(sl.TaskError):
            sl.build_brief("g", "/tmp", "", "", 0, 20)


class TestVerify(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.corpus = Path(self.tmp.name) / "corpus"
        self.corpus.mkdir()
        (self.corpus / "a.py").write_text("EXIT_OK = 0\nEXIT_ARGS = 2\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_references_are_resolved_by_the_script_not_the_worker(self):
        obj = good_answer(evidence=[{"claim": "ok line", "ref": "a.py:2", "quote": "EXIT_ARGS = 2", "verified": False},
                                    {"claim": "past the end", "ref": "a.py:9", "quote": "x", "verified": True},
                                    {"claim": "file level", "ref": "a.py", "quote": "EXIT_OK = 0", "verified": False},
                                    {"claim": "missing file", "ref": "b.py:1", "quote": "x", "verified": True},
                                    {"claim": "vault", "ref": "vault:notes#s12", "verified": True},
                                    {"claim": "no ref", "verified": True},
                                    "not an object"])
        out = sl.verify_answer(obj, self.corpus)
        self.assertEqual([c["verified"] for c in out["evidence"]], [True, False, True, False, False, False, False])
        self.assertEqual(out["verified_count"], 2)
        self.assertEqual(out["unsupported_count"], 5)
        self.assertIn("only the vault", out["evidence"][4]["check"])

    def test_a_verified_claim_needs_its_quote_at_the_cited_line(self):
        # the line existing is not evidence; the quote the worker relies on must sit at that line
        obj = good_answer(evidence=[{"claim": "no quote", "ref": "a.py:2"},
                                    {"claim": "quote elsewhere", "ref": "a.py:2", "quote": "EXIT_OK = 0"},
                                    {"claim": "quote here, spacing aside", "ref": "a.py:2", "quote": "EXIT_ARGS=2"},
                                    {"claim": "quote too short", "ref": "a.py:2", "quote": "= 2"},
                                    {"claim": "file level, quote in file", "ref": "a.py", "quote": "EXIT_ARGS = 2"},
                                    {"claim": "file level, quote absent", "ref": "a.py", "quote": "EXIT_NOPE"},
                                    {"claim": "range holds it", "ref": "a.py:1-2", "quote": "EXIT_ARGS = 2"}])
        out = sl.verify_answer(obj, self.corpus)
        self.assertEqual([c["verified"] for c in out["evidence"]], [False, False, True, False, True, False, True])
        self.assertEqual(out["evidence"][0]["check"], "no quote to check against the cited line")
        self.assertEqual(out["evidence"][1]["check"], "quote not found at the cited line")
        self.assertEqual(out["evidence"][2]["check"], "quote found at the cited line")
        self.assertIn("shorter than", out["evidence"][3]["check"])
        self.assertEqual(out["evidence"][5]["check"], "quote not found in the file")

    def test_an_answer_with_nothing_verified_is_downgraded_to_unanswerable(self):
        obj = good_answer(answerable=True, evidence=[{"claim": "bare", "ref": "a.py:2"}])
        out = sl.verify_answer(obj, self.corpus)
        self.assertFalse(out["answerable"])
        self.assertEqual(out["downgraded"], "answerable set to false: no claim verified")
        obj = good_answer(answerable=True, evidence=[])
        self.assertFalse(sl.verify_answer(obj, self.corpus)["answerable"])
        obj = good_answer(answerable=True, evidence=[{"claim": "ok", "ref": "a.py:2", "quote": "EXIT_ARGS = 2"}])
        out = sl.verify_answer(obj, self.corpus)
        self.assertTrue(out["answerable"])
        self.assertNotIn("downgraded", out)
        obj = good_answer(answerable=False, evidence=[])
        self.assertNotIn("downgraded", sl.verify_answer(obj, self.corpus))

    def test_line_ranges_resolve(self):
        obj = good_answer(evidence=[{"claim": "range ok", "ref": "a.py:1-2", "quote": "EXIT_OK = 0"},
                                    {"claim": "range past end", "ref": "a.py:1-9", "quote": "EXIT_OK = 0"},
                                    {"claim": "backwards", "ref": "a.py:2-1", "quote": "EXIT_OK = 0"}])
        out = sl.verify_answer(obj, self.corpus)
        self.assertEqual([c["verified"] for c in out["evidence"]], [True, False, False])
        self.assertEqual(out["evidence"][0]["check"], "quote found at the cited line")

    def test_absolute_refs_are_unverified_without_a_corpus_root(self):
        # an index or vault corpus has no path, so without --corpus-root nothing bounds an absolute ref
        obj = good_answer(evidence=[{"claim": "abs", "ref": str(self.corpus / "a.py") + ":1", "quote": "EXIT_OK = 0"}])
        out = sl.verify_answer(obj, None)
        self.assertFalse(out["evidence"][0]["verified"])
        self.assertIn("corpus root", out["evidence"][0]["check"])
        self.assertTrue(sl.verify_answer(good_answer(evidence=obj["evidence"]), self.corpus)["evidence"][0]["verified"])

    def test_corpus_root_names_the_files_behind_an_index_corpus(self):
        self.assertEqual(sl.corpus_root("kg:myindex", str(self.corpus)), self.corpus)
        self.assertEqual(sl.corpus_root(str(self.corpus), None), self.corpus)
        self.assertIsNone(sl.corpus_root("vault:notes", None))
        self.assertIsNone(sl.corpus_root("not-a-dir-or-index", None))

    def test_refs_outside_the_corpus_stay_unverified(self):
        outside = Path(self.tmp.name) / "outside.py"
        outside.write_text("x = 1\n")
        obj = good_answer(evidence=[{"claim": "escape", "ref": str(outside) + ":1"}, {"claim": "dotdot", "ref": "../outside.py:1"}])
        out = sl.verify_answer(obj, self.corpus)
        self.assertEqual([c["verified"] for c in out["evidence"]], [False, False])
        self.assertEqual(out["evidence"][0]["check"], "outside the corpus")

    def test_schema_failures(self):
        for bad in ({}, [], good_answer(answerable="yes"), good_answer(local_calls=True), good_answer(evidence="x")):
            with self.assertRaises(sl.TaskError) as cm:
                sl.verify_answer(bad, self.corpus)
            self.assertEqual(cm.exception.code, sl.EXIT_SCHEMA)

    def test_parse_tolerates_fences_and_prose(self):
        obj = good_answer()
        self.assertEqual(sl.parse_json_object(json.dumps(obj)), obj)
        self.assertEqual(sl.parse_json_object("Here it is:\n```json\n" + json.dumps(obj) + "\n```\nDone."), obj)
        self.assertEqual(sl.parse_json_object("prose " + json.dumps(obj) + " trailing"), obj)
        with self.assertRaises(sl.TaskError):
            sl.parse_json_object("no json here")

    def test_capsule_never_prints_file_content(self):
        obj = sl.verify_answer(good_answer(answer="EXIT_OK lives on line one",
                                           evidence=[{"claim": "c", "ref": "a.py:1", "quote": "EXIT_OK = 0"}]), self.corpus)
        text = sl.capsule(obj)
        self.assertIn("1 verified, 0 unsupported", text)
        self.assertNotIn("EXIT_ARGS = 2", text)


class TestHeadlessRun(unittest.TestCase):
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
        self.args = self.root / "args.json"
        self.env = {**os.environ, "PATH": f"{self.bin}:{os.environ['PATH']}", "SUPPORT_LOCAL_STATE": str(self.root / "state"),
                    "FAKE_CLAUDE_ARGS": str(self.args)}

    def tearDown(self):
        self.tmp.cleanup()

    def run_cmd(self, *args, env=None):
        return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, env=env or self.env, timeout=60)

    def argv_calls(self):
        return [json.loads(l) for l in self.args.read_text().splitlines() if l.strip()]

    def test_run_pins_the_model_and_verifies_the_answer(self):
        p = self.run_cmd("run", "--goal", "where is the exit code table", "--corpus", str(self.corpus), "--budget-turns", "9")
        self.assertEqual(p.returncode, 0, p.stderr)
        argv = self.argv_calls()[0]
        self.assertEqual(argv[argv.index("--model") + 1], "claude-haiku-5-5")
        self.assertEqual(argv[argv.index("--max-turns") + 1], "9")
        allowed = argv[argv.index("--allowedTools") + 1]
        self.assertNotIn(",Bash,", "," + allowed + ",", "no bare Bash: an unmatched command is denied headlessly")
        self.assertIn("Bash(python3 ~/.agents/skills/local-model-task/scripts/local_model_task.py:*)", allowed)
        self.assertTrue(allowed.startswith("Read,Grep,Glob,"))
        self.assertIn("## Goal\n\nwhere is the exit code table", argv[-1])
        self.assertIn("support-local worker", argv[argv.index("--append-system-prompt") + 1])
        self.assertIn("worker claude-haiku-5-5: 3 turns", p.stdout)
        self.assertIn("1 verified, 1 unsupported", p.stdout)
        runs = [json.loads(l) for l in (self.root / "state" / "runs.jsonl").read_text().splitlines()]
        self.assertEqual(runs[0]["model"], "claude-haiku-5-5")
        self.assertEqual(runs[0]["input_tokens"], 1200)
        self.assertEqual(runs[0]["cache_write"], 2000)
        self.assertEqual(runs[0]["harness_cost_usd"], 0.0123)
        # 1200*0.10 + 300*0.50 + 2000*0.125 + 500*0.01 = 120 + 150 + 250 + 5 micro-dollars
        self.assertAlmostEqual(runs[0]["list_cost_usd"], 0.000525, places=6)
        self.assertIn("list price $0.0005", p.stdout)
        self.assertEqual(oct((self.root / "state" / "runs.jsonl").stat().st_mode & 0o777), "0o600")

    def test_run_passes_effort_variant_and_autocompact_and_records_peak_context(self):
        p = self.run_cmd("run", "--goal", "g", "--corpus", str(self.corpus), "--variant", "terse", "--effort", "medium", "--autocompact", "60000")
        self.assertEqual(p.returncode, 0, p.stderr)
        argv = self.argv_calls()[0]
        self.assertEqual(argv[argv.index("--effort") + 1], "medium")
        self.assertEqual(argv[argv.index("--autocompact") + 1], "60000")
        self.assertTrue(argv[-1].startswith("# Brief for support-local (terse variant)"))
        runs = [json.loads(l) for l in (self.root / "state" / "runs.jsonl").read_text().splitlines()]
        self.assertEqual(runs[-1]["variant"], "terse")
        self.assertEqual(runs[-1]["effort"], "medium")
        self.assertEqual(runs[-1]["peak_context_tokens"], 1700)
        self.assertEqual(runs[-1]["wall_ms"], 4200)

    def test_run_refuses_a_lower_model(self):
        env = {**self.env, "FAKE_CLAUDE_MODEL": "claude-haiku-4-5-20251001"}
        p = self.run_cmd("run", "--goal", "g", "--corpus", str(self.corpus), env=env)
        self.assertEqual(p.returncode, sl.EXIT_REFUSED)
        self.assertIn("claude-haiku-4-5-20251001", p.stderr)
        self.assertFalse((self.root / "state" / "runs.jsonl").exists())

    def runs(self):
        return [json.loads(l) for l in (self.root / "state" / "runs.jsonl").read_text().splitlines()]

    def test_prose_result_is_salvaged_retried_once_and_recorded(self):
        env = {**self.env, "FAKE_CLAUDE_RESULT": "I could not finish."}
        p = self.run_cmd("run", "--goal", "g", "--corpus", str(self.corpus), "--budget-turns", "12", env=env)
        self.assertEqual(p.returncode, sl.EXIT_WORKER)
        self.assertIn("ended without an answer on every attempt", p.stderr)
        self.assertIn("answerable: False", p.stdout)
        self.assertIn("worker ended without a JSON answer", p.stdout, "the salvage reason is in coverage")
        calls = self.argv_calls()
        self.assertEqual(len(calls), 2, "one retry, no more")
        self.assertEqual(calls[1][calls[1].index("--max-turns") + 1], "6", "the retry gets half the turns")
        self.assertIn("## Prior attempt", calls[1][-1])
        self.assertNotIn("## Prior attempt", calls[0][-1])
        rec = self.runs()[-1]
        self.assertEqual(rec["attempts"], 2)
        self.assertTrue(rec["salvaged"])
        self.assertEqual(rec["stop_reason"], "error")
        self.assertEqual(rec["turns"], 6, "both attempts' turns are summed")
        self.assertEqual(rec["output_tokens"], 600)
        self.assertAlmostEqual(rec["list_cost_usd"], 2 * 0.000525, places=6)

    def test_max_turns_death_then_success_on_retry(self):
        env = {**self.env, "FAKE_CLAUDE_MODE": "max_turns", "FAKE_CLAUDE_FAIL_FIRST": str(self.root / "counter")}
        p = self.run_cmd("run", "--goal", "g", "--corpus", str(self.corpus), "--budget-turns", "15", env=env)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("1 verified, 1 unsupported", p.stdout, "the second attempt's real answer wins")
        rec = self.runs()[-1]
        self.assertEqual(rec["attempts"], 2)
        self.assertFalse(rec["salvaged"])
        self.assertEqual(rec["attempt_log"][0]["stop_reason"], "budget")
        self.assertTrue(rec["attempt_log"][0]["salvaged"])
        self.assertEqual(rec["turns"], 15 + 3)
        calls = self.argv_calls()
        self.assertIn("ran out of turns before verifying", calls[1][-1], "the retry brief holds the prior attempt's text")
        self.assertEqual(calls[1][calls[1].index("--max-turns") + 1], "7")

    def test_crash_with_no_retries_is_recorded_and_refused(self):
        env = {**self.env, "FAKE_CLAUDE_MODE": "crash"}
        p = self.run_cmd("run", "--goal", "g", "--corpus", str(self.corpus), "--retries", "0", env=env)
        self.assertEqual(p.returncode, sl.EXIT_WORKER)
        self.assertEqual(len(self.argv_calls()), 1)
        rec = self.runs()[-1]
        self.assertEqual(rec["attempts"], 1)
        self.assertIn("exit 1", rec["attempt_log"][0]["stop_reason"] + " " + json.dumps(rec))
        self.assertIn("something broke", p.stdout, "the crash text survives in coverage")

    def test_hung_worker_is_killed_and_salvaged(self):
        env = {**self.env, "FAKE_CLAUDE_MODE": "hang"}
        p = self.run_cmd("run", "--goal", "g", "--corpus", str(self.corpus), "--timeout", "2", "--retries", "0", env=env)
        self.assertEqual(p.returncode, sl.EXIT_WORKER)
        rec = self.runs()[-1]
        self.assertEqual(rec["stop_reason"], "timeout")
        self.assertIn("killed after 2 s", json.dumps(rec))

    def test_blocked_stop_reason_passes_the_schema(self):
        obj = good_answer(answerable=False, stop_reason="blocked", coverage="local search denied by the memory gate")
        self.assertEqual(sl.verify_answer(obj, self.corpus)["stop_reason"], "blocked")

    def test_verify_from_stdin(self):
        obj = good_answer(evidence=[{"claim": "c", "ref": "a.py:1", "quote": "EXIT_OK = 0"}])
        p = subprocess.run([sys.executable, str(SCRIPT), "verify", "--answer", "-", "--corpus", str(self.corpus)],
                           input=json.dumps(obj), capture_output=True, text=True, env=self.env, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("1 verified, 0 unsupported", p.stdout)


if __name__ == "__main__":
    unittest.main()
