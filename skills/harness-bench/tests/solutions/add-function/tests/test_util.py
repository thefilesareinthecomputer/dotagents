import unittest

from app.only_tested import experimental_merge
from app.util import ZoneLedger, peak_zone, summarize_zones


class TestUtil(unittest.TestCase):
    def test_summarize_zones(self):
        out = summarize_zones({"a": 60, "b": 70})
        self.assertEqual(out["zones"], 2)
        self.assertEqual(out["total"], 100)

    def test_ledger_clamps(self):
        ledger = ZoneLedger()
        ledger.record("north", 250)
        self.assertEqual(ledger.rows, [{"name": "north", "flow": 100}])

    def test_experimental_merge(self):
        self.assertEqual(experimental_merge({"x": 1}, {"y": 2}), {"x": 1, "y": 2})

    def test_peak_zone(self):
        self.assertEqual(peak_zone({"a": 1, "b": 2}), "b")


if __name__ == "__main__":
    unittest.main()
