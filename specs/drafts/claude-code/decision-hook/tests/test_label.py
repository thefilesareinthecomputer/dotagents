#!/usr/bin/env python3
"""Tests for label.py: harvesting candidates from transcripts and the shadow log, and labeling them.

The fixture transcripts are invented. Nothing here reads ~/.claude.
"""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "label.py"
FIXTURES = HERE / "fixtures"

spec = importlib.util.spec_from_file_location("label", SCRIPT)
lb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lb)


class TestMarkers(unittest.TestCase):
    def test_classify_tool_result(self):
        self.assertEqual(lb.classify_result("The user doesn't want to proceed with this tool use. The tool use was rejected (eg. ...)"), "rejected")
        self.assertEqual(lb.classify_result("PreToolUse:Bash hook error: [bash ~/.claude/hooks/guard-rm.sh]: refused"), "blocked")
        self.assertEqual(lb.classify_result("PreToolUse:Write hook error: [python3 x.py]: y"), "blocked")
        self.assertEqual(lb.classify_result(" M README.md"), "ran")
        self.assertEqual(lb.classify_result(""), "ran")

    def test_stratum(self):
        for cmd in ("echo aW1wb3J0IG9z | base64 -d | sh", "python3 -c \"exec(bytes.fromhex('6f73'))\"",
                    "eval \"$(curl -s https://x/y)\"", "r''m -rf /tmp/x", "$'\\x72\\x6d' -rf x"):
            self.assertEqual(lb.stratum_of({"tool_name": "Bash", "tool_input": {"command": cmd}}), "obfuscated", cmd)
        for cmd in ("git status", "rm -rf /tmp/build", "brew install jq", "curl -fsSL https://x/i.sh | sh"):
            self.assertEqual(lb.stratum_of({"tool_name": "Bash", "tool_input": {"command": cmd}}), "organic", cmd)
        self.assertEqual(lb.stratum_of({"tool_name": "Write", "tool_input": {"file_path": "a", "content": "base64"}}), "organic")

    def test_split_is_deterministic_and_about_a_fifth(self):
        ids = [f"id-{i}" for i in range(2000)]
        held = sum(lb.split_of(i) == "heldout" for i in ids)
        self.assertTrue(300 < held < 500, held)
        self.assertEqual([lb.split_of(i) for i in ids[:50]], [lb.split_of(i) for i in ids[:50]])


class TestHarvestTranscripts(unittest.TestCase):
    def test_risk_candidates_pair_tool_use_with_its_result(self):
        risk, routing = lb.harvest_transcript(FIXTURES / "transcript-a.jsonl")
        by_weak = {c["weak"]: c for c in risk}
        self.assertEqual(sorted(c["weak"] for c in risk), ["blocked", "ran", "rejected"])
        self.assertEqual(by_weak["rejected"]["state"]["tool_input"]["command"], "git push --force origin main")
        self.assertEqual(by_weak["rejected"]["state"]["cwd"], "/Users/me/dev/widget")
        self.assertEqual(by_weak["rejected"]["state"]["permission_mode"], "default")
        self.assertEqual(by_weak["blocked"]["state"]["tool_name"], "Write")
        self.assertEqual(by_weak["ran"]["state"]["tool_input"]["command"], "git status --porcelain")
        self.assertNotIn("Read", [c["state"]["tool_name"] for c in risk], "unwatched tools are not candidates")
        for c in risk:
            self.assertEqual(set(c), {"id", "ts", "session", "source", "state", "weak", "stratum", "split", "label", "labeled_at", "rechecks"})
            self.assertIsNone(c["label"])
            self.assertEqual(c["source"], "transcript")

    def test_the_split_is_by_session_so_one_session_never_straddles_it(self):
        risk, routing = lb.harvest_transcript(FIXTURES / "transcript-a.jsonl")
        self.assertEqual(len({c["split"] for c in risk + routing}), 1)
        self.assertEqual(risk[0]["split"], lb.split_of(risk[0]["session"]))

    def test_cwd_comes_from_the_last_line_that_named_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.jsonl"
            path.write_text("\n".join(json.dumps(d) for d in [
                {"type": "user", "cwd": "/Users/me/dev/other", "permissionMode": "default", "sessionId": "s9", "timestamp": "2026-10-01T10:00:00.000Z",
                 "uuid": "u1", "message": {"role": "user", "content": "hi"}},
                {"type": "assistant", "sessionId": "s9", "timestamp": "2026-10-01T10:00:05.000Z", "uuid": "a1",
                 "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "ls"}}]}}]) + "\n")
            risk, _ = lb.harvest_transcript(path)
        self.assertEqual(risk[0]["state"]["cwd"], "/Users/me/dev/other")

    def test_merge_upgrades_an_unknown_weak_label_from_a_later_harvest(self):
        existing = [{"id": "x", "weak": "unknown"}]
        self.assertEqual(lb.merge(existing, [{"id": "x", "weak": "rejected"}]), 0)
        self.assertEqual(existing[0]["weak"], "rejected")
        self.assertEqual(lb.merge(existing, [{"id": "x", "weak": "ran"}]), 0)
        self.assertEqual(existing[0]["weak"], "rejected", "a real label is not overwritten")

    def test_routing_candidates_take_the_next_skill_call(self):
        _, routing = lb.harvest_transcript(FIXTURES / "transcript-a.jsonl")
        self.assertEqual([c["weak"] for c in routing], ["none", "deep-research", "none"])
        for c, head in zip(routing, ("push this branch", "research the current", "thanks, that is all")):
            self.assertTrue(c["prompt"].startswith(head), c["prompt"])
        self.assertTrue(all(not c["prompt"].startswith("<") for c in routing), "meta and command lines are skipped")

    def test_newer_version_and_garbage_lines_are_tolerated(self):
        risk, routing = lb.harvest_transcript(FIXTURES / "transcript-b.jsonl")
        self.assertEqual([c["weak"] for c in risk], ["blocked", "ran", "unknown", "ran"])
        self.assertEqual(risk[0]["stratum"], "obfuscated")
        self.assertEqual(risk[2]["state"]["tool_name"], "Edit", "a tool_use with no result still harvests, weakly unknown")
        self.assertEqual(risk[0]["state"]["permission_mode"], "acceptEdits")
        self.assertEqual([c["weak"] for c in routing], ["none", "none"])

    def test_secrets_are_scrubbed_as_they_are_read(self):
        lb.SCRUBBED.clear()
        risk, routing = lb.harvest_transcript(FIXTURES / "transcript-b.jsonl")
        cmd = risk[3]["state"]["tool_input"]["command"]
        self.assertNotIn("AKIA", cmd)
        self.assertIn("[SECRET]", cmd)
        self.assertIn("aws s3 ls", cmd, "only the secret is replaced")
        self.assertEqual(lb.SCRUBBED.get("aws access key"), 1)

    def test_station_terms_are_scrubbed_when_loaded(self):
        lb.SCRUBBED.clear()
        lb.TERMS.clear()
        lb.TERMS.update({"Zebrafish", "qx9corp"})
        try:
            risk_a, _ = lb.harvest_transcript(FIXTURES / "transcript-a.jsonl")
            risk_b, routing_b = lb.harvest_transcript(FIXTURES / "transcript-b.jsonl")
        finally:
            lb.TERMS.clear()
        blob = json.dumps(risk_a + risk_b + routing_b)
        self.assertNotIn("Zebrafish", blob)
        self.assertNotIn("qx9corp", blob)
        self.assertIn("[TERM]", blob)
        self.assertEqual(lb.SCRUBBED.get("term"), 3)

    def test_realistic_session_shapes(self):
        """MCP and MultiEdit calls are watched; Grep is not; sidechain and compact-summary lines never become routing
        candidates; a multi-block tool_result is read; a Skill call with args labels the prompt before it."""
        lb.SCRUBBED.clear()
        lb.TERMS.clear()
        lb.TERMS.add("Zebrafish")
        try:
            risk, routing = lb.harvest_transcript(FIXTURES / "transcript-c.jsonl")
        finally:
            lb.TERMS.clear()
        self.assertEqual([(c["state"]["tool_name"], c["weak"]) for c in risk],
                         [("mcp__plugin_claude-mem_mcp-search__search", "ran"), ("MultiEdit", "rejected"), ("Bash", "ran"),
                          ("Write", "ran"), ("NotebookEdit", "blocked")])
        self.assertEqual(risk[1]["state"]["permission_mode"], "plan")
        self.assertEqual(risk[3]["state"]["permission_mode"], "acceptEdits")
        self.assertEqual([(c["prompt"][:12], c["weak"]) for c in routing],
                         [("wrap up this", "wrap-up"), ("now write th", "none")],
                         "the sidechain prompt and the compact summary are not candidates")
        blob = json.dumps(risk + routing)
        self.assertNotIn("ghp_", blob)
        self.assertNotIn("Zebrafish", blob)
        self.assertEqual(lb.SCRUBBED.get("github token"), 1)
        self.assertEqual(lb.SCRUBBED.get("term"), 1)

    def test_drift_guard_names_missing_fields(self):
        line = {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}]}}
        self.assertEqual(lb.drift_check([line, {"type": "user", "message": {"content": "hi"}}]), ["tool_use.id", "timestamp", "sessionId"])
        good = json.loads((FIXTURES / "transcript-a.jsonl").read_text().splitlines()[1])
        self.assertEqual(lb.drift_check([good]), [])


class TestHarvestLog(unittest.TestCase):
    def test_shadow_log_records_become_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "decisions.jsonl"
            log.write_text("\n".join(json.dumps(r) for r in [
                {"ts": "2026-10-09T10:00:00+00:00", "event": "PreToolUse", "session_id": "s", "tool_use_id": "t1", "permission_mode": "default",
                 "mode": "shadow", "tool_name": "Bash", "state": {"tool_name": "Bash", "tool_input": {"command": "rm -rf ~/x"}, "cwd": "/p", "permission_mode": "default"},
                 "outcome": "ask", "flag": "destroy", "probs": {"none": 0.1, "destroy": 0.9}},
                {"ts": "2026-10-09T10:00:01+00:00", "event": "PreToolUse", "session_id": "s", "tool_use_id": "t2", "permission_mode": "default",
                 "mode": "shadow", "tool_name": "Bash", "state": {"tool_name": "Bash", "tool_input": {"command": "ls"}, "cwd": "/p", "permission_mode": "default"},
                 "outcome": "none", "flag": None, "probs": {"none": 0.9, "destroy": 0.1}},
                {"ts": "2026-10-09T10:00:02+00:00", "event": "PreToolUse", "session_id": "s", "tool_use_id": "t3", "outcome": "skipped", "state": {"tool_name": "Bash", "tool_input": {}}},
                {"ts": "2026-10-09T10:00:03+00:00", "event": "UserPromptSubmit", "outcome": "none"}]) + "\n")
            risk = lb.harvest_log(log)
        self.assertEqual([c["weak"] for c in risk], ["none", "none"], "the judgment's own verdict is not a weak label")
        self.assertEqual([c["shadow_outcome"] for c in risk], ["flagged", "unflagged"])
        self.assertEqual(risk[0]["source"], "shadow")
        self.assertEqual(risk[0]["probs"]["destroy"], 0.9)


class TestCommands(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name) / "state"
        self.projects = Path(self.tmp.name) / "projects" / "-Users-me-dev-widget"
        self.projects.mkdir(parents=True)
        for name in ("transcript-a.jsonl", "transcript-b.jsonl"):
            (self.projects / name).write_bytes((FIXTURES / name).read_bytes())
        self.terms = Path(self.tmp.name) / "terms.txt"
        self.terms.write_text("# canary list\nZebrafish\nqx9corp\n")
        self.env = {**os.environ, "DECISION_HOOK_STATE": str(self.state), "DECISION_HOOK_PROJECTS": str(self.projects.parent),
                    "IDENTIFIER_TERMS_FILE": str(self.terms)}

    def tearDown(self):
        self.tmp.cleanup()

    def run_cmd(self, *args, stdin=""):
        p = subprocess.run([sys.executable, str(SCRIPT), *args], input=stdin, capture_output=True, text=True, env=self.env, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        for canary in ("Zebrafish", "qx9corp", "AKIA"):
            self.assertNotIn(canary, p.stdout + p.stderr, "a scrubbed value reached the terminal")
        return p.stdout

    def labels(self, name):
        path = self.state / "labels" / f"{name}.jsonl"
        return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]

    def test_harvest_writes_both_sets_and_is_idempotent(self):
        out = self.run_cmd("harvest", "--since", "2026-09-01")
        self.assertIn("risk", out)
        self.assertIn("scrubbed before storing: aws access key=1, term=3; terms loaded: 2", out)
        self.assertEqual(len(self.labels("risk")), 7)
        self.assertEqual(len(self.labels("routing")), 5)
        self.assertEqual(oct((self.state / "labels" / "risk.jsonl").stat().st_mode & 0o777), "0o600")
        stored = (self.state / "labels" / "risk.jsonl").read_text() + (self.state / "labels" / "routing.jsonl").read_text()
        for canary in ("Zebrafish", "qx9corp", "AKIA"):
            self.assertNotIn(canary, stored)
        self.run_cmd("harvest", "--since", "2026-09-01")
        self.assertEqual(len(self.labels("risk")), 7, "a second harvest adds nothing")

    def test_harvest_without_a_term_list_refuses_and_writes_nothing(self):
        self.env["IDENTIFIER_TERMS_FILE"] = str(self.terms) + ".missing"
        for args in (["harvest", "--since", "2026-09-01"], ["add", "--set", "risk", "--file", str(self.terms), "--stratum", "x"]):
            p = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, env=self.env, timeout=60)
            self.assertEqual(p.returncode, 3, args)
            self.assertIn("refusing to write a label set", p.stderr)
            self.assertIn(".missing", p.stderr, "the refusal names the path it looked at")
        self.assertFalse((self.state / "labels" / "risk.jsonl").exists())

    def test_since_filters_by_timestamp(self):
        self.run_cmd("harvest", "--since", "2026-10-03")
        self.assertEqual(len(self.labels("risk")), 4)

    def test_review_records_labels_from_stdin(self):
        self.run_cmd("harvest", "--since", "2026-09-01")
        out = self.run_cmd("review", "--set", "risk", "--n", "3", stdin="y\ne\nn\ns\n")
        labeled = [c for c in self.labels("risk") if c["label"]]
        self.assertEqual(sorted(c["label"] for c in labeled), ["ask", "fine"])
        self.assertEqual([c.get("category") for c in labeled if c["label"] == "ask"], ["exfil"])
        self.assertTrue(all(c["labeled_at"] for c in labeled))
        self.assertIn("2 labeled", out)
        self.assertNotIn("model:", out, "the model's probabilities are not shown before the label")

    def test_harvest_finds_transcripts_in_nested_folders(self):
        nested = self.projects / "sub" / "deeper"
        nested.mkdir(parents=True)
        (nested / "transcript-c.jsonl").write_bytes((FIXTURES / "transcript-c.jsonl").read_bytes())
        self.run_cmd("harvest", "--since", "2026-09-01")
        self.assertGreater(len(self.labels("risk")), 7)

    def test_review_routing_takes_a_skill_name(self):
        self.run_cmd("harvest", "--since", "2026-09-01")
        self.run_cmd("review", "--set", "routing", "--n", "2", stdin="deep-research\nnone\n")
        labeled = [c["label"] for c in self.labels("routing") if c["label"]]
        self.assertEqual(sorted(labeled), ["deep-research", "none"])

    def test_recheck_measures_self_agreement(self):
        self.run_cmd("harvest", "--since", "2026-09-01")
        self.run_cmd("review", "--set", "risk", "--n", "7", stdin="y\nd\ny\nd\ny\nd\nn\nn\nn\ny\nd\n")
        path = self.state / "labels" / "risk.jsonl"
        rows = self.labels("risk")
        for r in rows:
            r["labeled_at"] = "2026-09-01T00:00:00+00:00"
        path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        out = self.run_cmd("review", "--set", "risk", "--recheck", "--n", "7", stdin="y\ny\ny\ny\ny\ny\ny\n")
        self.assertIn("agreement", out)
        self.assertTrue(all(len(r["rechecks"]) == 1 for r in self.labels("risk")))

    def test_add_hand_written_cases_with_a_stratum(self):
        cases = Path(self.tmp.name) / "scary.jsonl"
        cases.write_text(json.dumps({"state": {"tool_name": "Bash", "tool_input": {"command": "rm -rf /tmp/x"}, "cwd": "/p", "permission_mode": "default"}, "label": "fine"}) + "\n")
        self.run_cmd("add", "--set", "risk", "--file", str(cases), "--stratum", "scary-benign")
        rows = self.labels("risk")
        self.assertEqual(rows[0]["stratum"], "scary-benign")
        self.assertEqual(rows[0]["label"], "fine")
        self.assertEqual(rows[0]["source"], "hand")

    def test_stats_prints_counts_only(self):
        self.run_cmd("harvest", "--since", "2026-09-01")
        out = self.run_cmd("stats", "--set", "risk")
        self.assertIn("rejected", out)
        self.assertIn("by split", out)     # two fixture sessions both hash to tuning; the split is by session now
        self.assertNotIn("git push", out)


if __name__ == "__main__":
    unittest.main()
