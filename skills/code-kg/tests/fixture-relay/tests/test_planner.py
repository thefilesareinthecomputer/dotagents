import unittest

from relay.config import load_config
from relay.llm.client import LLMClient
from relay.planner import Planner, route_keyword


class TestRouting(unittest.TestCase):
    def test_keyword_table(self):
        self.assertEqual(route_keyword("fetch the status page"), "web")
        self.assertEqual(route_keyword("query the runs table"), "sql")
        self.assertEqual(route_keyword("read the error log"), "shell")
        self.assertEqual(route_keyword("something opaque"), "shell")


class TestPlanner(unittest.TestCase):
    def setUp(self):
        self.config = load_config(max_steps=4)
        self.planner = Planner(self.config, LLMClient(self.config))

    def test_plan_splits_and_caps(self):
        plan = self.planner.plan(
            "read the log and query the runs table and fetch "
            "https://example.com then grep errors and list files")
        self.assertLessEqual(len(plan.steps), 4)
        self.assertIn("sql", plan.tool_names())

    def test_replan_drops_failed_step(self):
        plan = self.planner.plan("read the log and query the runs table")
        failed = plan.steps[0]
        revised = self.planner.replan_after_failure(plan, failed, "boom")
        self.assertNotIn(failed.name, [s.name for s in revised.steps])


if __name__ == "__main__":
    unittest.main()
