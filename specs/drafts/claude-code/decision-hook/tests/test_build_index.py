#!/usr/bin/env python3
"""Tests for build_index.py: the routing exemplars from every skill's triggers.json."""

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "build_index.py"
sys.path.insert(0, str(HERE))
from fake_systemone import FakeSystemOne  # noqa: E402

spec = importlib.util.spec_from_file_location("build_index", SCRIPT)
bi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bi)


class TestBuildIndex(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for skill, cases in {"alpha": [{"name": "a1", "query": "do alpha", "should_trigger": True, "why": "x"},
                                       {"name": "a2", "query": "not alpha", "should_trigger": False, "why": "y"}],
                             "beta": [{"name": "b1", "query": "do beta", "should_trigger": True}]}.items():
            d = self.root / "skills" / skill / "evals"
            d.mkdir(parents=True)
            (d / "triggers.json").write_text(json.dumps(cases))
        (self.root / "skills" / "gamma").mkdir()   # a skill with no evals contributes nothing
        self.fake = FakeSystemOne(embedding=lambda t: [float(len(t)), 1.0, 0.0]).start()
        self.out = self.root / "routing-index.json"

    def tearDown(self):
        self.fake.stop()
        self.tmp.cleanup()

    def test_collects_every_case_with_its_skill_and_label(self):
        cases = bi.collect_cases(self.root / "skills")
        self.assertEqual([(c["skill"], c["should_trigger"]) for c in cases],
                         [("alpha", True), ("alpha", False), ("beta", True)])

    def test_writes_index_with_vectors_and_threshold(self):
        n = bi.build(self.root / "skills", self.out, self.fake.base_url, "embeddinggemma", 0.75)
        self.assertEqual(n, 3)
        index = json.loads(self.out.read_text())
        self.assertEqual(index["model"], "embeddinggemma")
        self.assertEqual(index["threshold"], 0.75)
        self.assertEqual(len(index["exemplars"]), 3)
        ex = index["exemplars"][0]
        self.assertEqual(set(ex), {"skill", "should_trigger", "query", "vector"})
        self.assertEqual(ex["vector"], [8.0, 1.0, 0.0])
        body = self.fake.posts("/api/embed")[0]["body"]
        self.assertEqual(body["model"], "embeddinggemma")
        self.assertIsInstance(body["input"], list)
        unloads = [r["body"] for r in self.fake.posts("/api/generate")]
        self.assertEqual(unloads, [{"model": "embeddinggemma", "keep_alive": 0}], "the model is dropped when the build finishes")

    def test_refuses_a_non_loopback_endpoint(self):
        with self.assertRaises(SystemExit):
            bi.build(self.root / "skills", self.out, "http://192.168.1.4:11434", "embeddinggemma", 0.75)
        self.assertFalse(self.out.exists())

    def test_leave_one_out_report(self):
        bi.build(self.root / "skills", self.out, self.fake.base_url, "embeddinggemma", 0.0)
        index = json.loads(self.out.read_text())
        rep = bi.leave_one_out(index, [0.0, 0.5, 0.99])
        self.assertEqual(set(rep), {0.0, 0.5, 0.99})
        for thr, row in rep.items():
            self.assertEqual(set(row), {"top1", "should_trigger_n", "none_rate", "should_not_n"})
            self.assertEqual(row["should_trigger_n"], 2)
            self.assertEqual(row["should_not_n"], 1)


if __name__ == "__main__":
    unittest.main()
