import unittest

from relay.errors import RelayError
from relay.limits import RateLimiter
from relay.scheduler import Scheduler


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class TestScheduler(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.ran: list[str] = []
        self.sched = Scheduler(
            lambda goal: self.ran.append(goal) or {"ok": True},
            clock=self.clock)

    def test_not_due_until_interval(self):
        self.sched.add("hourly", "sweep the logs", 3600)
        self.assertEqual(self.sched.tick(), [])
        self.clock.now += 3601
        self.assertEqual(self.sched.tick(), ["hourly"])
        self.assertEqual(self.ran, ["sweep the logs"])

    def test_outage_skips_ahead_without_replay(self):
        self.sched.add("minutely", "ping", 60)
        self.clock.now += 60 * 45  # 45 missed periods
        self.sched.tick()
        self.assertEqual(len(self.ran), 1)
        self.assertEqual(self.sched.tick(), [])

    def test_duplicate_name_refused(self):
        self.sched.add("a", "x", 10)
        with self.assertRaises(RelayError):
            self.sched.add("a", "y", 10)


class TestRateLimiter(unittest.TestCase):
    def test_burst_then_deny_then_refill(self):
        clock = FakeClock()
        limiter = RateLimiter(capacity=3, refill_per_s=1.0, clock=clock)
        for _ in range(3):
            self.assertTrue(limiter.check("client-1").allowed)
        denied = limiter.check("client-1")
        self.assertFalse(denied.allowed)
        self.assertGreater(denied.retry_after_s, 0)
        clock.now += 2.0
        self.assertTrue(limiter.check("client-1").allowed)

    def test_keys_are_isolated(self):
        clock = FakeClock()
        limiter = RateLimiter(capacity=1, refill_per_s=0.1, clock=clock)
        self.assertTrue(limiter.check("a").allowed)
        self.assertTrue(limiter.check("b").allowed)
        self.assertFalse(limiter.check("a").allowed)


if __name__ == "__main__":
    unittest.main()
