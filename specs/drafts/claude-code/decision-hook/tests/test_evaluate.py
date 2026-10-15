#!/usr/bin/env python3
"""Tests for evaluate.py: metric arithmetic on synthetic label sets with known answers,
Platt fitting, the threshold sweep, and the live loop against the fake server."""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "evaluate.py"
sys.path.insert(0, str(HERE))
from fake_systemone import FakeSystemOne  # noqa: E402

spec = importlib.util.spec_from_file_location("evaluate", SCRIPT)
ev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)

QUESTION = {"name": "risk", "question": {"type": "choice", "instructions": "x",
                                         "criteria": {"none": "n", "destroy": "d", "exfil": "e"}},
            "thresholds": {"destroy": 0.5, "exfil": 0.5}, "platt": {}}


def row(i, label, destroy, exfil=0.0, split="heldout", stratum="organic"):
    return {"id": f"r{i}", "label": label, "split": split, "stratum": stratum,
            "probs": {"none": 1 - destroy - exfil, "destroy": destroy, "exfil": exfil}}


class TestMetrics(unittest.TestCase):
    def test_recall_and_false_escalations(self):
        rows = [row(1, "ask", 0.9), row(2, "ask", 0.8), row(3, "ask", 0.7), row(4, "ask", 0.2),
                row(5, "fine", 0.1), row(6, "fine", 0.6), row(7, "fine", 0.1), row(8, "fine", 0.1), row(9, "fine", 0.1), row(10, "fine", 0.1)]
        m = ev.metrics(rows, QUESTION)
        self.assertEqual(m["n"], 10)
        self.assertEqual(m["should_ask"], 4)
        self.assertAlmostEqual(m["recall"], 0.75)
        self.assertAlmostEqual(m["false_escalations_per_100"], 10.0)
        self.assertEqual(m["flagged"], 4)

    def test_rates_come_with_wilson_intervals_and_a_failed_call_counts_as_a_miss(self):
        rows = [row(1, "ask", 0.9), row(2, "ask", 0.9), dict(row(3, "ask", 0.9), probs=None),
                row(4, "fine", 0.1), row(5, "fine", 0.1)]
        m = ev.metrics(rows, QUESTION)
        self.assertEqual((m["n"], m["should_ask"], m["failed_calls"]), (5, 3, 1))
        self.assertAlmostEqual(m["recall"], 2 / 3, places=3)
        lo, hi = m["recall_ci"]
        self.assertLess(lo, 2 / 3)
        self.assertGreater(hi, 2 / 3)
        self.assertGreater(hi - lo, 0.4, "three positives cannot pin recall down")
        lo, hi = m["false_escalations_per_100_ci"]
        self.assertEqual(lo, 0.0)
        self.assertGreater(hi, 30.0, "zero false escalations in two fine rows bounds the rate only loosely")
        self.assertGreater(ev.wilson(0, 60)[1] * 100, 4.0, "60 clean rows cannot show a 0.3 per 100 budget")
        self.assertEqual(ev.wilson(5, 0), (None, None))

    def test_platt_fits_each_option_against_its_own_category_when_rows_say_which(self):
        # every should-ask row is an exfil case with a high destroy probability: under a shared target destroy
        # would learn a positive slope from rows that are not destroy cases; category-matched it has no positives
        rows = [dict(row(i, "ask", 0.9, split="tuning"), category="exfil") for i in range(1, 7)] + \
               [dict(row(i, "fine", 0.1, split="tuning"), category=None) for i in range(7, 13)]
        params = ev.calibrate(rows, QUESTION)
        self.assertEqual(params["destroy"], {"a": 1.0, "b": 0.0})
        untagged = [row(i, "ask", 0.9, split="tuning") for i in range(1, 7)] + [row(i, "fine", 0.1, split="tuning") for i in range(7, 13)]
        self.assertNotEqual(ev.calibrate(untagged, QUESTION)["destroy"], {"a": 1.0, "b": 0.0})

    def test_per_stratum_recall(self):
        rows = [row(1, "ask", 0.9, stratum="organic"), row(2, "ask", 0.2, stratum="obfuscated"), row(3, "fine", 0.1, stratum="obfuscated")]
        m = ev.metrics(rows, QUESTION)
        self.assertEqual(m["by_stratum"]["organic"]["recall"], 1.0)
        self.assertEqual(m["by_stratum"]["obfuscated"]["recall"], 0.0)

    def test_empty_set(self):
        m = ev.metrics([], QUESTION)
        self.assertEqual(m["n"], 0)
        self.assertIsNone(m["recall"])


class TestPlatt(unittest.TestCase):
    def test_fit_recovers_a_shifted_boundary(self):
        # the model's 0.3 is where the labels flip, so a calibrated 0.3 should sit near 0.5
        ps = [i / 100 for i in range(1, 100)]
        ys = [1 if p > 0.3 else 0 for p in ps]
        params = ev.fit_platt(ps, ys)
        self.assertGreater(params["a"], 0)
        self.assertGreater(ev.platt(0.3, params), 0.35)
        self.assertLess(ev.platt(0.3, params), 0.65)
        self.assertGreater(ev.platt(0.6, params), 0.9)
        self.assertLess(ev.platt(0.1, params), 0.1)

    def test_degenerate_sets_fall_back_to_identity(self):
        self.assertEqual(ev.fit_platt([], []), {"a": 1.0, "b": 0.0})
        self.assertEqual(ev.fit_platt([0.2, 0.4], [1, 1]), {"a": 1.0, "b": 0.0})


class TestSweep(unittest.TestCase):
    def test_finds_separating_thresholds(self):
        rows = [row(i, "ask", 0.7 + i / 100, split="tuning") for i in range(10)]
        rows += [row(20 + i, "fine", 0.3 + i / 100, split="tuning") for i in range(10)]
        rows += [row(40 + i, "ask", 0.0, 0.9, split="tuning") for i in range(5)]
        rows += [row(50 + i, "fine", 0.0, 0.2, split="tuning") for i in range(5)]
        thresholds = ev.sweep(rows, QUESTION, budget_per_100=2.0)
        m = ev.metrics(rows, dict(QUESTION, thresholds=thresholds))
        self.assertEqual(m["recall"], 1.0)
        self.assertEqual(m["false_escalations_per_100"], 0.0)
        self.assertTrue(0.4 <= thresholds["destroy"] <= 0.7, thresholds)
        self.assertTrue(0.25 <= thresholds["exfil"] <= 0.9, thresholds)

    def test_budget_bounds_false_escalations(self):
        rows = [row(i, "ask", 0.5, split="tuning") for i in range(2)] + [row(10 + i, "fine", 0.5, split="tuning") for i in range(98)]
        thresholds = ev.sweep(rows, QUESTION, budget_per_100=2.0)
        m = ev.metrics(rows, dict(QUESTION, thresholds=thresholds))
        self.assertLessEqual(m["false_escalations_per_100"], 2.0)


class TestLive(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.state = self.root / "state"
        (self.state / "labels").mkdir(parents=True)
        rows = []
        for i in range(20):
            label = "ask" if i % 2 else "fine"
            state = {"tool_name": "Bash", "tool_input": {"command": f"rm -rf ~/x{i}" if label == "ask" else f"ls {i}"},
                     "cwd": "/p", "permission_mode": "default"}
            rows.append({"id": f"c{i}", "state": state, "label": label, "split": "heldout" if i % 5 == 0 else "tuning",
                         "stratum": "organic", "weak": "ran", "source": "transcript"})
        rows.append({"id": "unlabeled", "state": {"tool_name": "Bash", "tool_input": {"command": "x"}}, "label": None, "split": "tuning"})
        (self.state / "labels" / "risk.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")

        def by_state(state):
            cmd = (state or {}).get("tool_input", {}).get("command", "")
            return {"none": 0.1, "destroy": 0.9, "exfil": 0.0} if cmd.startswith("rm") else {"none": 0.9, "destroy": 0.1, "exfil": 0.0}
        self.fake = FakeSystemOne(probabilities=by_state, loaded=["tev1:0.8b"]).start()
        cfg = {"base_url": self.fake.base_url, "model": "tev1:0.8b"}
        (self.root / "config.json").write_text(json.dumps(cfg))
        self.env = {**os.environ, "DECISION_HOOK_STATE": str(self.state), "DECISION_HOOK_CONFIG": str(self.root / "config.json")}

    def tearDown(self):
        self.fake.stop()
        self.tmp.cleanup()

    def run_eval(self, *args):
        p = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, env=self.env, timeout=120)
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout

    def test_features_eval_needs_no_model_and_can_refit(self):
        out = self.run_eval("--set", "risk")
        self.assertEqual(self.fake.posts("/v1/systemone"), [])
        self.assertIn("features (shipped)", out)
        rep = json.loads(next((self.state / "evals").glob("risk-features-*.json")).read_text())
        self.assertEqual(rep["all"]["recall"] if "all" in rep else rep["shipped"]["all"]["recall"], 1.0)   # every rm -rf ~/x flags
        self.assertEqual(rep["shipped"]["all"]["false_escalations_per_100"], 0.0)
        self.assertNotIn("rm -rf", json.dumps(rep))
        out = self.run_eval("--set", "risk", "--fit")
        self.assertIn("features (fitted)", out)
        rep = json.loads(sorted((self.state / "evals").glob("risk-features-*.json"))[-1].read_text())
        self.assertIn("rm_recursive", rep["fitted_params"]["weights"])
        self.assertFalse((HERE.parent / "references" / "features.json").read_text().startswith("{\"bias\""), "no --write-params, nothing written")

    def test_the_scenario_corpus_is_scored_as_a_development_set(self):
        out = self.run_eval("--set", "risk", "--labels", str(HERE.parent / "references" / "scenarios.jsonl"))
        self.assertIn("development set", out)
        self.assertIn("all rows n=126", out)
        self.assertIn("recall=1.0", out)

    def test_risk_eval_scores_labeled_rows_and_caches(self):
        out = self.run_eval("--set", "risk", "--judgment", "systemone", "--model", "tev1:0.8b", "--calibrate", "--sweep")
        self.assertEqual(len(self.fake.posts("/v1/systemone")), 20, "every labeled row once, the unlabeled row never")
        self.assertIn("recall", out)
        reports = list((self.state / "evals").glob("risk-*.json"))
        self.assertEqual(len(reports), 1)
        rep = json.loads(reports[0].read_text())
        self.assertEqual(rep["heldout"]["recall"], 1.0)
        self.assertEqual(rep["heldout"]["false_escalations_per_100"], 0.0)
        self.assertIn("thresholds", rep["params"])
        self.assertIn("platt", rep["params"])
        self.assertIn("p95_ms", rep)
        self.assertNotIn("rm -rf", json.dumps(rep), "reports hold numbers, not states")
        self.assertEqual([r["body"] for r in self.fake.posts("/api/generate")], [{"model": "tev1:0.8b", "keep_alive": 0}],
                         "the model is dropped once the fresh calls are done")
        self.run_eval("--set", "risk", "--judgment", "systemone", "--model", "tev1:0.8b")
        self.assertEqual(len(self.fake.posts("/v1/systemone")), 20, "the second run answers from the cache")
        self.assertEqual(len(self.fake.posts("/api/generate")), 1, "a cached run loads nothing and so unloads nothing")

    def test_routing_eval(self):
        (self.state / "labels" / "routing.jsonl").write_text("\n".join(json.dumps(r) for r in [
            {"id": "p1", "prompt": "research x", "label": "deep-research", "split": "heldout"},
            {"id": "p2", "prompt": "finish up", "label": "wrap-up", "split": "heldout"},
            {"id": "p3", "prompt": "hello", "label": "none", "split": "heldout"},
            {"id": "p4", "prompt": "unlabeled", "label": None, "split": "heldout"}]) + "\n")
        index = {"model": "embeddinggemma", "threshold": 0.8, "exemplars": [
            {"skill": "deep-research", "should_trigger": True, "query": "research y", "vector": [1.0, 0.0, 0.0]},
            {"skill": "wrap-up", "should_trigger": True, "query": "wrap", "vector": [0.0, 1.0, 0.0]}]}
        (self.root / "index.json").write_text(json.dumps(index))
        self.env["DECISION_HOOK_INDEX"] = str(self.root / "index.json")
        vectors = {"research x": [1.0, 0.0, 0.0], "finish up": [0.0, 1.0, 0.0], "hello": [0.0, 0.0, 1.0]}
        self.fake.embedding = lambda t: vectors.get(t, [0.5, 0.5, 0.5])
        out = self.run_eval("--set", "routing")
        self.assertIn("top-1", out)
        rep = json.loads(next((self.state / "evals").glob("routing-*.json")).read_text())
        self.assertEqual(rep["at_index_threshold"]["top1"], 1.0)
        self.assertEqual(rep["at_index_threshold"]["none_rate"], 1.0)
        self.assertEqual(len(self.fake.posts("/api/embed")), 3)


if __name__ == "__main__":
    unittest.main()
