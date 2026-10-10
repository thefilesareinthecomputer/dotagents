#!/usr/bin/env python3
"""Harness tests: Claude Code itself runs with the hook wired through a `--settings`
overlay, so these prove the plumbing the unit tests cannot - the harness invokes
decide.py, parses its JSON, turns "ask" into a denial headlessly, and hands the
reason to the model. Each case spends real tokens (about $0.02 to $0.20 on Haiku 5.5)
and needs the `claude` CLI, so the suite runs only when asked:

    DECISION_HOOK_HARNESS=1 python3 -m unittest discover -s <this folder>/tests/harness -v

The model is the fake server from ../fake_systemone.py, pinned to flag everything
as `destroy` at 0.95, so the cases test the harness contract, not tev1.
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
TESTS = HERE.parent
SCRIPT = TESTS.parent / "scripts" / "decide.py"
sys.path.insert(0, str(TESTS))
from fake_systemone import FakeSystemOne  # noqa: E402

MODEL = "claude-haiku-5-5"
ENABLED = os.environ.get("DECISION_HOOK_HARNESS") == "1" and shutil.which("claude") is not None
MODES = ("default", "acceptEdits", "plan", "auto", "dontAsk", "bypassPermissions")
PROBE = "Run exactly this shell command with the Bash tool, then report verbatim any error or permission message you received: echo hello from the probe"


@unittest.skipUnless(ENABLED, "set DECISION_HOOK_HARNESS=1 with the claude CLI on PATH; spends tokens")
class Harness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.fake = FakeSystemOne(probabilities={"none": 0.03, "destroy": 0.95}, loaded=["tev1:0.8b"]).start()
        self.state = self.root / "state"
        (self.root / "settings.json").write_text(json.dumps({"hooks": {
            "PreToolUse": [{"matcher": "Bash|Write|Edit|MultiEdit|NotebookEdit|mcp__.*",
                            "hooks": [{"type": "command", "timeout": 3, "command": f"python3 {SCRIPT} --event pre-tool-use"}]}],
            "SessionStart": [{"matcher": "startup",
                              "hooks": [{"type": "command", "timeout": 20, "command": f"python3 {SCRIPT} --event session-start"}]}]}}))

    def tearDown(self):
        self.fake.stop()
        self.tmp.cleanup()

    def config(self, mode, base_url=None):
        cfg = {"base_url": base_url or self.fake.base_url, "model": "tev1:0.8b", "client_timeout_s": 1.5, "escalation_cap": 5,
               "modes": {"PreToolUse": {m: mode for m in MODES}, "UserPromptSubmit": {m: "off" for m in MODES}}}
        cfg["modes"]["PreToolUse"]["bypassPermissions"] = "off"
        (self.root / "config.json").write_text(json.dumps(cfg))

    def run_claude(self, prompt, tools="Bash"):
        env = {**os.environ, "DECISION_HOOK_CONFIG": str(self.root / "config.json"), "DECISION_HOOK_STATE": str(self.state)}
        p = subprocess.run(["claude", "-p", "--settings", str(self.root / "settings.json"), "--model", MODEL, "--max-turns", "2",
                            "--allowedTools", tools, "--output-format", "json", prompt],
                           capture_output=True, text=True, env=env, cwd=self.root, timeout=300)
        lines = [ln for ln in p.stdout.splitlines() if ln.strip().startswith("{")]
        self.assertTrue(lines, p.stderr[:500])
        return json.loads(lines[-1])

    def records(self):
        log = self.state / "decisions.jsonl"
        return [json.loads(ln) for ln in log.read_text().splitlines() if ln.strip()] if log.exists() else []

    def test_active_flag_becomes_a_denial_the_model_can_read(self):
        self.config("active")
        result = self.run_claude(PROBE)
        self.assertIn("decision-hook: destroy", result.get("result", ""), "the hook's reason reached the model")
        denials = result.get("permission_denials") or []
        self.assertEqual([d["tool_name"] for d in denials], ["Bash"])
        pre = [r for r in self.records() if r["event"] == "PreToolUse"]
        self.assertEqual(len(pre), 1)
        self.assertEqual(pre[0]["outcome"], "ask")
        self.assertEqual(pre[0]["tool_use_id"], denials[0]["tool_use_id"], "the log and the harness agree on the call")
        self.assertEqual(pre[0]["permission_mode"], "default")
        self.assertTrue(pre[0]["session_id"])
        warm = [r for r in self.records() if r["event"] == "SessionStart"]
        self.assertEqual([r["outcome"] for r in warm], ["warm"], "the startup ping ran once")

    def test_shadow_logs_and_the_command_runs(self):
        self.config("shadow")
        result = self.run_claude(PROBE)
        self.assertIn("hello from the probe", result.get("result", ""))
        self.assertFalse(result.get("permission_denials"))
        pre = [r for r in self.records() if r["event"] == "PreToolUse"]
        self.assertEqual([r["outcome"] for r in pre], ["ask"], "shadow records what it would have said")
        self.assertEqual(pre[0]["mode"], "shadow")

    def test_server_down_never_blocks(self):
        self.config("active", base_url="http://127.0.0.1:9")
        result = self.run_claude(PROBE)
        self.assertIn("hello from the probe", result.get("result", ""))
        self.assertFalse(result.get("permission_denials"))
        pre = [r for r in self.records() if r["event"] == "PreToolUse"]
        self.assertEqual([r["outcome"] for r in pre], ["error"])

    def test_unwatched_tool_is_never_sent(self):
        self.config("active")
        (self.root / "note.txt").write_text("the note says: harness probe\n")
        self.run_claude("Use the Read tool to read note.txt in the current directory and repeat its one line.", tools="Read")
        self.assertEqual([r for r in self.records() if r["event"] == "PreToolUse"], [])
        self.assertEqual(self.fake.posts("/v1/systemone"), [r for r in self.fake.posts("/v1/systemone") if r["body"].get("state") == "warm-up"],
                         "only the warm ping reached the model")


if __name__ == "__main__":
    unittest.main()
