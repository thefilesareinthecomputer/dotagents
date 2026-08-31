import unittest

from relay.config import load_config
from relay.executor import Executor
from relay.memory.store import MemoryStore
from relay.report import as_markdown, as_text, as_tree


class TestReport(unittest.TestCase):
    def setUp(self):
        config = load_config(max_steps=2, memory_path=":memory:")
        self.store = MemoryStore(":memory:")
        executor = Executor(config, self.store)
        executor.audit.path = "/dev/null"
        self.result = executor.run("read the log and query the runs table")

    def tearDown(self):
        self.store.close()

    def test_tree_counts_match(self):
        tree = as_tree(self.result)
        self.assertEqual(tree["counts"]["completed"],
                         len(self.result.completed))

    def test_text_carries_goal(self):
        self.assertIn(self.result.goal, as_text(self.result))

    def test_markdown_has_table(self):
        self.assertIn("| step | tool | ok |", as_markdown(self.result))


if __name__ == "__main__":
    unittest.main()
