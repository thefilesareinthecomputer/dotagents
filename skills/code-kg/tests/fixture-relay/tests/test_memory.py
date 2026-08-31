import time
import unittest

from relay.memory.recall import recall, score, tokenize
from relay.memory.store import MemoryStore, Record


class TestStore(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore(":memory:")

    def tearDown(self):
        self.store.close()

    def test_append_and_latest(self):
        self.store.append("zone", "north valve is stuck")
        self.store.append("zone", "north valve replaced")
        latest = self.store.latest("zone")
        self.assertIsNotNone(latest)
        self.assertIn("replaced", latest.body)

    def test_search_finds_body_terms(self):
        self.store.append("irrigation", "drip line pressure normal")
        hits = self.store.search("pressure")
        self.assertEqual(len(hits), 1)


class TestRecall(unittest.TestCase):
    def test_exact_old_beats_loose_new(self):
        now = time.time()
        old_exact = Record("a", "note", "drip line pressure drop zone four",
                           {}, now - 30 * 24 * 3600)
        new_loose = Record("b", "note", "pressure", {}, now)
        query = "drip line pressure drop"
        self.assertGreater(score(query, old_exact, now),
                           score(query, new_loose, now))

    def test_recall_respects_budget(self):
        store = MemoryStore(":memory:")
        for i in range(10):
            store.append(f"k{i}", "valve inspection " + "x" * 500)
        kept = recall(store, "valve inspection", budget_chars=1200)
        self.assertLessEqual(sum(len(r.body) for r in kept), 1200)
        store.close()

    def test_tokenize_drops_short(self):
        self.assertNotIn("of", tokenize("of the zone"))


if __name__ == "__main__":
    unittest.main()
