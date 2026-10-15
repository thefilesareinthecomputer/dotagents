import unittest

from app.alerts import evaluate


class TestAlerts(unittest.TestCase):
    def test_alert_then_normal(self):
        t = {"default": {"high": 80, "low": 60}}
        self.assertEqual(evaluate([(1, "a", 80), (2, "a", 60)], t),
                         [{"t": 1, "zone": "a", "state": "alert"}, {"t": 2, "zone": "a", "state": "normal"}])


if __name__ == "__main__":
    unittest.main()
