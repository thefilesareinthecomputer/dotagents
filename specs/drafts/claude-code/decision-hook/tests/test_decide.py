#!/usr/bin/env python3
"""Tests for decision-hook/scripts/decide.py.

Stdlib unittest. Every model call goes to a fake server on 127.0.0.1
(fake_systemone.py); no test reaches a real model or the network.
Run: python3 -m unittest discover -s specs/drafts/claude-code/decision-hook/tests -v
"""

import importlib.util
import json
import os
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "decide.py"
sys.path.insert(0, str(HERE))
from fake_systemone import FakeSystemOne  # noqa: E402

spec = importlib.util.spec_from_file_location("decide", SCRIPT)
dh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dh)

MODES = ("default", "acceptEdits", "plan", "auto", "dontAsk", "bypassPermissions")
ASK_SHAPE = {"hookEventName": "PreToolUse", "permissionDecision": "ask"}


def pre_tool_use(command="git status", tool="Bash", mode="default", session="s1", **extra):
    tool_input = {"command": command} if tool == "Bash" else {"file_path": command, "content": "x"}
    return dict({"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input, "cwd": "/tmp/proj",
                 "permission_mode": mode, "session_id": session, "tool_use_id": "t1"}, **extra)


def user_prompt(prompt, mode="default", session="s1"):
    return {"hook_event_name": "UserPromptSubmit", "prompt": prompt, "permission_mode": mode, "session_id": session}


# ---------------------------------------------------------------- unit

class TestHookOutput(unittest.TestCase):
    def test_only_ask_or_nothing(self):
        rng = random.Random(7)
        for _ in range(500):
            event = rng.choice(["PreToolUse", "UserPromptSubmit", "SessionStart", "Stop", "x"])
            out = dh.hook_output(event, rng.random() < 0.5, "r" * rng.randint(0, 50))
            if out is None:
                continue
            self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "ask")
            self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "PreToolUse")
            self.assertEqual(event, "PreToolUse")

    def test_source_has_no_allow_deny_or_block_literal(self):
        src = SCRIPT.read_text()
        for word in ('"allow"', '"deny"', '"block"', "'allow'", "'deny'", "'block'", "exit(2)", "sys.exit(2"):
            self.assertNotIn(word, src, word)

    def test_context_output_only_adds_context(self):
        out = dh.context_output("Suggested skill: x")
        self.assertEqual(set(out["hookSpecificOutput"]), {"hookEventName", "additionalContext"})
        self.assertNotIn("decision", out)


class TestState(unittest.TestCase):
    def test_strings_are_cut_at_the_limit(self):
        st = dh.build_state({"tool_name": "Write", "tool_input": {"file_path": "a", "content": "x" * 5000,
                                                                  "nested": {"deep": ["y" * 3000, 1, None]}},
                             "cwd": "/p", "permission_mode": "default"})
        self.assertEqual(len(st["tool_input"]["content"]), dh.MAX_FIELD)
        self.assertEqual(len(st["tool_input"]["nested"]["deep"][0]), dh.MAX_FIELD)
        self.assertEqual(st["tool_input"]["nested"]["deep"][1:], [1, None])
        self.assertEqual(st["tool_name"], "Write")
        self.assertEqual(st["cwd"], "/p")

    def test_state_body_stays_under_the_endpoint_limit(self):
        huge = {f"k{i}": "z" * 4000 for i in range(40)}
        st = dh.build_state({"tool_name": "Bash", "tool_input": huge, "cwd": "/p", "permission_mode": "default"})
        self.assertLessEqual(len(json.dumps(st)), dh.MAX_STATE)


class TestModes(unittest.TestCase):
    def test_resolution(self):
        cfg = {"modes": {"PreToolUse": {"default": "active", "auto": "shadow"}}}
        self.assertEqual(dh.resolve_mode(cfg, "PreToolUse", "default"), "active")
        self.assertEqual(dh.resolve_mode(cfg, "PreToolUse", "auto"), "shadow")
        self.assertEqual(dh.resolve_mode(cfg, "PreToolUse", "plan"), "off", "an unlisted mode is off")
        self.assertEqual(dh.resolve_mode(cfg, "UserPromptSubmit", "default"), "off", "an unlisted event is off")
        self.assertEqual(dh.resolve_mode({"modes": {"PreToolUse": {"default": "bogus"}}}, "PreToolUse", "default"), "off")

    def test_default_config_is_shadow_risk_off_routing_off_bypass(self):
        cfg = dh.default_config()
        for mode in MODES:
            self.assertEqual(dh.resolve_mode(cfg, "PreToolUse", mode), "off" if mode == "bypassPermissions" else "shadow", mode)
            self.assertEqual(dh.resolve_mode(cfg, "UserPromptSubmit", mode), "off", mode)
        self.assertNotIn("active", json.dumps(cfg))


class TestDecision(unittest.TestCase):
    QUESTION = {"thresholds": {"destroy": 0.5, "exfil": 0.5, "creds": 0.5, "config": 0.6, "install": 0.7},
                "platt": {"destroy": {"a": 1.0, "b": 0.0}}}

    def test_highest_calibrated_option_over_its_threshold_wins(self):
        probs = {"none": 0.2, "destroy": 0.55, "exfil": 0.1, "creds": 0.1, "config": 0.05, "install": 0.0}
        self.assertEqual(dh.decide_risk(probs, self.QUESTION), ("destroy", 0.55))

    def test_none_when_nothing_clears(self):
        probs = {"none": 0.5, "destroy": 0.3, "exfil": 0.2, "creds": 0.0, "config": 0.0, "install": 0.69}
        self.assertIsNone(dh.decide_risk(probs, self.QUESTION))

    def test_platt_moves_the_probability(self):
        q = {"thresholds": {"destroy": 0.5}, "platt": {"destroy": {"a": 1.0, "b": 2.0}}}
        self.assertIsNotNone(dh.decide_risk({"none": 0.7, "destroy": 0.3}, q), "b=2 lifts 0.3 to about 0.76")
        q = {"thresholds": {"destroy": 0.5}, "platt": {"destroy": {"a": 1.0, "b": -2.0}}}
        self.assertIsNone(dh.decide_risk({"none": 0.3, "destroy": 0.7}, q), "b=-2 drops 0.7 to about 0.24")

    def test_platt_identity(self):
        for p in (0.01, 0.3, 0.5, 0.9):
            self.assertAlmostEqual(dh.platt(p, {"a": 1.0, "b": 0.0}), p, places=6)
        self.assertAlmostEqual(dh.platt(0.0, {"a": 1.0, "b": 0.0}), 0.0, places=3)
        self.assertAlmostEqual(dh.platt(1.0, {"a": 1.0, "b": 0.0}), 1.0, places=3)

    def test_malformed_answers_raise(self):
        for reply in ({}, {"answers": {}}, {"answers": {"risk": {"type": "choice"}}},
                      {"answers": {"risk": {"probabilities": "x"}}}, {"answers": {"risk": {"probabilities": {"a": "b"}}}}):
            with self.assertRaises(dh.HookError):
                dh.parse_probabilities(reply, "risk")


class TestRouting(unittest.TestCase):
    INDEX = {"model": "fake", "threshold": 0.8, "exemplars": [
        {"skill": "deep-research", "should_trigger": True, "query": "research x", "vector": [1.0, 0.0, 0.0]},
        {"skill": "deep-research", "should_trigger": False, "query": "quick fact", "vector": [0.0, 1.0, 0.0]},
        {"skill": "wrap-up", "should_trigger": True, "query": "finish up", "vector": [0.0, 0.0, 1.0]}]}

    def test_nearest_should_trigger_over_threshold_routes(self):
        self.assertEqual(dh.route([0.9, 0.1, 0.0], self.INDEX)[0], "deep-research")

    def test_nearest_should_not_case_routes_nowhere(self):
        self.assertIsNone(dh.route([0.1, 0.9, 0.0], self.INDEX)[0])

    def test_under_threshold_routes_nowhere(self):
        skill, sim = dh.route([0.6, 0.0, 0.6], self.INDEX)
        self.assertIsNone(skill)
        self.assertLess(sim, 0.8)

    def test_cosine(self):
        self.assertAlmostEqual(dh.cosine([1, 0], [1, 0]), 1.0)
        self.assertAlmostEqual(dh.cosine([1, 0], [0, 1]), 0.0)
        self.assertEqual(dh.cosine([0, 0], [1, 0]), 0.0)


class TestMemory(unittest.TestCase):
    def test_mlx_runner_size_comes_from_rss_not_ps(self):
        ps = [{"name": "tev1:0.8b", "size": 8_000_000_000, "runner": "mlx"}]
        rss = {"tev1:0.8b": 700_000_000}
        self.assertEqual(dh.loaded_bytes(ps, rss), 700_000_000)

    def test_llamacpp_runner_takes_the_larger_reading(self):
        ps = [{"name": "qwen3.5:4b", "size": 3_000_000_000, "runner": "llamacpp"}]
        self.assertEqual(dh.loaded_bytes(ps, {"qwen3.5:4b": 5_000_000_000}), 5_000_000_000)
        self.assertEqual(dh.loaded_bytes(ps, {"qwen3.5:4b": 1_000_000_000}), 3_000_000_000)

    def test_parse_runner_rss(self):
        text = ("  1024 /Applications/Ollama.app/Contents/MacOS/Ollama\n"
                " 716800 /Applications/Ollama.app/Contents/Resources/ollama runner --model tev1:0.8b --port 1\n"
                "  40000 /Applications/Ollama.app/Contents/Resources/ollama serve\n")
        self.assertEqual(dh.parse_runner_rss(text), {"tev1:0.8b": 716800 * 1024})

    def test_budget_refuses_when_over_cap(self):
        budget = {"max_total_gb": 2.0, "reserve_gb": 1.0}
        self.assertIsNone(dh.over_budget(budget, loaded=1 << 30, estimate=512 << 20, free=8 << 30))
        self.assertIn("cap", dh.over_budget(budget, loaded=1 << 30, estimate=1536 << 20, free=8 << 30))
        self.assertIn("free", dh.over_budget(budget, loaded=0, estimate=512 << 20, free=1 << 30))


# ---------------------------------------------------------------- integration

class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.fake = FakeSystemOne().start()
        self.config_path = self.root / "config.json"
        self.state = self.root / "state"
        self.write_config({})

    def tearDown(self):
        self.fake.stop()
        self.tmp.cleanup()

    def write_config(self, overrides, modes=None):
        cfg = dh.default_config()
        cfg["base_url"] = self.fake.base_url
        cfg["client_timeout_s"] = 1.0
        if modes:
            cfg["modes"] = modes
        cfg.update(overrides)
        self.config_path.write_text(json.dumps(cfg))

    def active(self, event="PreToolUse"):
        self.write_config({}, modes={event: {m: "active" for m in MODES}})

    def run_hook(self, payload, event="pre-tool-use", raw=None):
        env = {**os.environ, "DECISION_HOOK_CONFIG": str(self.config_path), "DECISION_HOOK_STATE": str(self.state),
               "DECISION_HOOK_INDEX": str(self.root / "routing-index.json")}
        p = subprocess.run([sys.executable, str(SCRIPT), "--event", event], input=raw if raw is not None else json.dumps(payload),
                           capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr)
        return p

    def records(self):
        log = self.state / "decisions.jsonl"
        if not log.exists():
            return []
        return [json.loads(l) for l in log.read_text().splitlines() if l.strip()]

    def write_index(self, exemplars, threshold=0.8):
        (self.root / "routing-index.json").write_text(json.dumps({"model": "embeddinggemma", "threshold": threshold,
                                                                   "exemplars": exemplars}))


class TestPreToolUse(Base):
    def test_shadow_logs_and_prints_nothing(self):
        self.fake.probabilities = {"none": 0.1, "destroy": 0.9}
        self.fake.loaded = ["tev1:0.8b"]
        p = self.run_hook(pre_tool_use("rm -rf ~/x"))
        self.assertEqual(p.stdout, "")
        rec = self.records()
        self.assertEqual(len(rec), 1)
        self.assertEqual(rec[0]["outcome"], "ask")
        self.assertEqual(rec[0]["mode"], "shadow")
        self.assertEqual(rec[0]["flag"], "destroy")
        self.assertEqual(rec[0]["state"]["tool_input"]["command"], "rm -rf ~/x")
        self.assertIn("latency_ms", rec[0])
        self.assertEqual(oct(self.state.stat().st_mode & 0o777), "0o700")
        self.assertEqual(oct((self.state / "decisions.jsonl").stat().st_mode & 0o777), "0o600")

    def test_active_escalation_prints_ask(self):
        self.active()
        self.fake.probabilities = {"none": 0.1, "destroy": 0.9}
        self.fake.loaded = ["tev1:0.8b"]
        p = self.run_hook(pre_tool_use("rm -rf ~/x"))
        out = json.loads(p.stdout)
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "ask")
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "PreToolUse")
        self.assertIn("destroy", out["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertEqual(set(out), {"hookSpecificOutput"})

    def test_active_no_flag_prints_nothing(self):
        self.active()
        self.fake.loaded = ["tev1:0.8b"]
        self.assertEqual(self.run_hook(pre_tool_use()).stdout, "")
        self.assertEqual(self.records()[0]["outcome"], "none")

    def test_log_is_scrubbed_but_the_model_sees_the_raw_call(self):
        self.fake.loaded = ["tev1:0.8b"]
        key = "AKIA" + "IOSFODNN7EXAMPLE"
        self.run_hook(pre_tool_use(f"export AWS_ACCESS_KEY_ID={key} && aws s3 ls"))
        sent = self.fake.posts("/v1/systemone")[0]["body"]["state"]["tool_input"]["command"]
        self.assertIn(key, sent, "the judgment needs the real call")
        logged = self.records()[0]["state"]["tool_input"]["command"]
        self.assertNotIn(key, logged)
        self.assertIn("[SECRET]", logged)
        self.assertNotIn(key, (self.state / "decisions.jsonl").read_text())

    def test_bypass_mode_is_off_whatever_the_config_says(self):
        self.write_config({}, modes={"PreToolUse": {"bypassPermissions": "active"}})
        self.fake.loaded = ["tev1:0.8b"]
        self.fake.probabilities = {"none": 0.1, "destroy": 0.9}
        self.assertEqual(self.run_hook(pre_tool_use("rm -rf ~/x", mode="bypassPermissions")).stdout, "")
        self.assertEqual(self.fake.posts("/v1/systemone"), [])
        self.assertEqual(dh.resolve_mode({"modes": {"PreToolUse": {"bypassPermissions": "active"}}}, "PreToolUse", "bypassPermissions"), "off")

    def test_request_shape(self):
        self.fake.loaded = ["tev1:0.8b"]
        self.run_hook(pre_tool_use("git push --force origin main"))
        body = self.fake.posts("/v1/systemone")[0]["body"]
        self.assertEqual(body["model"], "tev1:0.8b")
        self.assertEqual(body["keep_alive"], dh.default_config()["keep_alive"])
        self.assertEqual(list(body["questions"]), ["risk"])
        self.assertEqual(body["questions"]["risk"]["type"], "choice")
        self.assertIn("none", body["questions"]["risk"]["criteria"])
        self.assertEqual(body["state"]["tool_input"]["command"], "git push --force origin main")
        self.assertEqual(body["state"]["permission_mode"], "default")

    def test_escalation_cap_goes_quiet(self):
        self.active()
        self.write_config({"escalation_cap": 2}, modes={"PreToolUse": {m: "active" for m in MODES}})
        self.fake.probabilities = {"none": 0.1, "destroy": 0.9}
        self.fake.loaded = ["tev1:0.8b"]
        outs = [self.run_hook(pre_tool_use("rm -rf ~/x", session="cap")).stdout for _ in range(4)]
        self.assertTrue(outs[0] and outs[1])
        self.assertEqual(outs[2:], ["", ""])
        self.assertEqual([r["outcome"] for r in self.records()], ["ask", "ask", "capped", "capped"])
        other = self.run_hook(pre_tool_use("rm -rf ~/x", session="fresh")).stdout
        self.assertTrue(other, "the cap is per session")

    def test_slow_reply_means_no_decision(self):
        self.active()
        self.fake.delay = 2.0
        self.fake.probabilities = {"none": 0.1, "destroy": 0.9}
        self.fake.loaded = ["tev1:0.8b"]
        self.assertEqual(self.run_hook(pre_tool_use("rm -rf ~/x")).stdout, "")
        self.assertEqual(self.records()[0]["outcome"], "timeout")

    def test_missing_endpoint_means_no_decision(self):
        self.active()
        self.fake.status = 404
        self.fake.loaded = ["tev1:0.8b"]
        self.assertEqual(self.run_hook(pre_tool_use("rm -rf ~/x")).stdout, "")
        self.assertEqual(self.records()[0]["outcome"], "error")
        self.assertIn("404", self.records()[0]["reason"])

    def test_garbage_reply_means_no_decision(self):
        self.active()
        self.fake.body = "<html>nope"
        self.fake.loaded = ["tev1:0.8b"]
        self.assertEqual(self.run_hook(pre_tool_use("rm -rf ~/x")).stdout, "")
        self.assertEqual(self.records()[0]["outcome"], "error")

    def test_another_model_loaded_skips_before_any_model_call(self):
        self.active()
        self.fake.loaded = ["qwen3.5:4b"]
        self.assertEqual(self.run_hook(pre_tool_use("rm -rf ~/x")).stdout, "")
        self.assertEqual(self.records()[0]["outcome"], "skipped")
        self.assertIn("another model", self.records()[0]["reason"])
        self.assertEqual(self.fake.posts("/v1/systemone"), [])

    def test_server_down_means_no_decision(self):
        self.active()
        self.fake.stop()
        self.assertEqual(self.run_hook(pre_tool_use("rm -rf ~/x")).stdout, "")
        self.assertEqual(self.records()[0]["outcome"], "error")

    def test_off_mode_makes_no_request_and_no_log(self):
        self.write_config({}, modes={"PreToolUse": {"default": "off"}})
        self.fake.loaded = ["tev1:0.8b"]
        self.assertEqual(self.run_hook(pre_tool_use("rm -rf ~/x")).stdout, "")
        self.assertEqual(self.fake.requests, [])
        self.assertEqual(self.records(), [])

    def test_garbage_stdin_exits_zero_silently(self):
        self.active()
        self.assertEqual(self.run_hook(None, raw="not json").stdout, "")
        self.assertEqual(self.run_hook(None, raw="").stdout, "")
        self.assertEqual(self.run_hook(None, raw='{"tool_name": 5}').stdout, "")

    def test_unwatched_tool_is_not_sent(self):
        self.active()
        self.fake.loaded = ["tev1:0.8b"]
        self.assertEqual(self.run_hook(pre_tool_use("/a", tool="Read")).stdout, "")
        self.assertEqual(self.fake.posts("/v1/systemone"), [])

    def test_never_allow_property_end_to_end(self):
        self.active()
        self.fake.loaded = ["tev1:0.8b"]
        rng = random.Random(11)
        options = ["none", "destroy", "exfil", "creds", "config", "install"]
        for i in range(12):
            self.fake.probabilities = {k: rng.random() for k in options}
            if i % 4 == 3:
                self.fake.body = rng.choice(['{"answers": 1}', "x", '{"answers": {"risk": {"probabilities": {"none": "a"}}}}'])
            else:
                self.fake.body = None
            payload = pre_tool_use("".join(rng.choice("abc /-~;|&$") for _ in range(rng.randint(0, 40))),
                                   tool=rng.choice(["Bash", "Write", "Edit"]), mode=rng.choice(MODES), session=f"p{i}")
            out = self.run_hook(payload).stdout
            if out:
                hs = json.loads(out)["hookSpecificOutput"]
                self.assertEqual({k: hs[k] for k in ASK_SHAPE}, ASK_SHAPE)
                self.assertEqual(set(hs), {"hookEventName", "permissionDecision", "permissionDecisionReason"})


class TestMemoryGate(Base):
    def test_cold_load_refused_over_budget(self):
        self.active()
        self.fake.loaded = []
        (self.root / "budget.json").write_text(json.dumps({"max_total_gb": 0.5, "reserve_gb": 0.0}))
        self.write_config({"budget_path": str(self.root / "budget.json")}, modes={"PreToolUse": {m: "active" for m in MODES}})
        self.assertEqual(self.run_hook(pre_tool_use("rm -rf ~/x")).stdout, "")
        self.assertEqual(self.records()[0]["outcome"], "skipped")
        self.assertIn("budget", self.records()[0]["reason"])
        self.assertEqual(self.fake.posts("/v1/systemone"), [])

    def test_cold_load_allowed_under_budget(self):
        self.fake.loaded = []
        (self.root / "budget.json").write_text(json.dumps({"max_total_gb": 64, "reserve_gb": 0.0}))
        self.write_config({"budget_path": str(self.root / "budget.json")})
        self.run_hook(pre_tool_use("rm -rf ~/x"))
        self.assertEqual(len(self.fake.posts("/v1/systemone")), 1)


class TestUserPromptSubmit(Base):
    def setUp(self):
        super().setUp()
        self.write_config({}, modes={"UserPromptSubmit": {m: "shadow" for m in MODES}})
        self.write_index([
            {"skill": "deep-research", "should_trigger": True, "query": "research x", "vector": [1.0, 0.0, 0.0]},
            {"skill": "deep-research", "should_trigger": False, "query": "quick fact", "vector": [0.0, 1.0, 0.0]},
            {"skill": "wrap-up", "should_trigger": True, "query": "finish up", "vector": [0.0, 0.0, 1.0]}])

    def test_shadow_logs_and_prints_nothing(self):
        self.fake.embedding = [0.95, 0.05, 0.0]
        p = self.run_hook(user_prompt("research the thing"), event="user-prompt-submit")
        self.assertEqual(p.stdout, "")
        rec = self.records()[0]
        self.assertEqual(rec["event"], "UserPromptSubmit")
        self.assertEqual(rec["skill"], "deep-research")
        self.assertEqual(rec["outcome"], "suggest")
        self.assertNotIn("research the thing", json.dumps(rec), "the prompt text is not logged, only its embedding and result")

    def test_active_prints_one_context_line(self):
        self.active("UserPromptSubmit")
        self.fake.embedding = [0.95, 0.05, 0.0]
        out = json.loads(self.run_hook(user_prompt("research the thing"), event="user-prompt-submit").stdout)
        hs = out["hookSpecificOutput"]
        self.assertEqual(hs["hookEventName"], "UserPromptSubmit")
        self.assertRegex(hs["additionalContext"], r"^Suggested skill: deep-research \(similarity [01]\.\d\d\)")
        self.assertIn("ignore if it does not fit", hs["additionalContext"])
        self.assertEqual(set(hs), {"hookEventName", "additionalContext"})
        self.assertNotIn("decision", out)

    def test_nearest_should_not_case_prints_nothing(self):
        self.active("UserPromptSubmit")
        self.fake.embedding = [0.05, 0.95, 0.0]
        self.assertEqual(self.run_hook(user_prompt("quick fact please"), event="user-prompt-submit").stdout, "")
        self.assertEqual(self.records()[0]["outcome"], "none")

    def test_under_threshold_prints_nothing(self):
        self.active("UserPromptSubmit")
        self.fake.embedding = [0.6, 0.0, 0.6]
        self.assertEqual(self.run_hook(user_prompt("something else"), event="user-prompt-submit").stdout, "")

    def test_other_model_loaded_skips(self):
        self.active("UserPromptSubmit")
        self.fake.loaded = ["qwen3.5:4b"]
        self.assertEqual(self.run_hook(user_prompt("research x"), event="user-prompt-submit").stdout, "")
        self.assertEqual(self.records()[0]["outcome"], "skipped")
        self.assertEqual(self.fake.posts("/api/embed"), [])

    def test_embed_model_loaded_proceeds(self):
        self.active("UserPromptSubmit")
        self.fake.loaded = ["embeddinggemma:latest"]
        self.fake.embedding = [0.95, 0.05, 0.0]
        self.assertTrue(self.run_hook(user_prompt("research x"), event="user-prompt-submit").stdout)

    def test_missing_index_means_nothing(self):
        self.active("UserPromptSubmit")
        (self.root / "routing-index.json").unlink()
        self.assertEqual(self.run_hook(user_prompt("research x"), event="user-prompt-submit").stdout, "")
        self.assertEqual(self.records()[0]["outcome"], "error")

    def test_empty_prompt_is_ignored(self):
        self.active("UserPromptSubmit")
        self.assertEqual(self.run_hook(user_prompt("   "), event="user-prompt-submit").stdout, "")
        self.assertEqual(self.fake.posts("/api/embed"), [])


class TestSessionStart(Base):
    def test_warm_ping_loads_the_model_when_nothing_is_loaded(self):
        (self.root / "budget.json").write_text(json.dumps({"max_total_gb": 64, "reserve_gb": 0.0}))
        self.write_config({"budget_path": str(self.root / "budget.json")})
        p = self.run_hook({"hook_event_name": "SessionStart", "session_id": "s", "permission_mode": "default"}, event="session-start")
        self.assertEqual(p.stdout, "")
        self.assertEqual(len(self.fake.posts("/v1/systemone")), 1)

    def test_warm_ping_yields_to_a_loaded_model(self):
        self.fake.loaded = ["qwen3.5:4b"]
        self.run_hook({"hook_event_name": "SessionStart", "session_id": "s", "permission_mode": "default"}, event="session-start")
        self.assertEqual(self.fake.posts("/v1/systemone"), [])


class TestReport(Base):
    def test_report_counts_per_mode(self):
        self.fake.loaded = ["tev1:0.8b"]
        self.fake.probabilities = {"none": 0.1, "destroy": 0.9}
        self.run_hook(pre_tool_use("rm -rf ~/x", mode="default"))
        self.run_hook(pre_tool_use("rm -rf ~/x", mode="auto"))
        self.fake.loaded = ["qwen3.5:4b"]
        self.run_hook(pre_tool_use("ls", mode="default"))
        env = {**os.environ, "DECISION_HOOK_CONFIG": str(self.config_path), "DECISION_HOOK_STATE": str(self.state)}
        p = subprocess.run([sys.executable, str(SCRIPT), "report"], capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("default", p.stdout)
        self.assertIn("auto", p.stdout)
        self.assertIn("skipped", p.stdout)
        self.assertNotIn("rm -rf", p.stdout, "the report prints counts, never states")


if __name__ == "__main__":
    unittest.main()
