import unittest

from relay.memory.compact import compact, plan_compaction
from relay.memory.store import MemoryStore


class TestCompaction(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore(":memory:")
        for i in range(8):
            self.store.append("hot-key", f"version {i} of the note")
        self.store.append("cold-key", "only version")

    def tearDown(self):
        self.store.close()

    def test_plan_counts_surplus_only(self):
        plan = plan_compaction(self.store, keep_versions=3)
        self.assertEqual(plan.keys_examined, 1)
        self.assertEqual(plan.records_to_fold, 5)
        self.assertGreater(plan.estimated_bytes_saved, 0)

    def test_compact_preserves_latest(self):
        before = self.store.latest("hot-key")
        result = compact(self.store, keep_versions=3)
        self.assertEqual(result.keys_compacted, 1)
        self.assertEqual(result.records_folded, 5)
        after = self.store.latest("hot-key")
        self.assertIsNotNone(after)
        self.assertEqual(after.kind, "compacted")
        self.assertIn("compacted 5 versions", after.body)
        history = self.store.history("hot-key", limit=20)
        bodies = [r.body for r in history]
        self.assertIn(before.body, bodies)

    def test_untouched_key_survives(self):
        compact(self.store, keep_versions=3)
        cold = self.store.latest("cold-key")
        self.assertEqual(cold.body, "only version")

    def test_noop_when_under_threshold(self):
        fresh = MemoryStore(":memory:")
        fresh.append("k", "v")
        result = compact(fresh, keep_versions=3)
        self.assertEqual(result.records_folded, 0)
        fresh.close()


if __name__ == "__main__":
    unittest.main()
