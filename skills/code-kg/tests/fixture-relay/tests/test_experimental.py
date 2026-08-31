import unittest

from relay.experimental.graph_notes import build_adjacency, orphan_keys
from relay.memory.store import MemoryStore


class TestGraphNotes(unittest.TestCase):
    def test_adjacency_and_orphans(self):
        store = MemoryStore(":memory:")
        store.append("alpha", "relates to beta directly")
        store.append("beta", "standalone note")
        store.append("gamma", "no links here")
        adjacency = build_adjacency(store, ["alpha", "beta", "gamma"])
        self.assertEqual(adjacency["alpha"], ["beta"])
        self.assertIn("gamma", orphan_keys(adjacency))
        store.close()


if __name__ == "__main__":
    unittest.main()
