"""Rate limiting: token bucket per client key, shared clock, no threads.

The server consults one RateLimiter before dispatch. Buckets refill
continuously rather than on a timer tick, so a burst after quiet time is
allowed up to capacity and sustained pressure settles at the refill rate.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable


@dataclass
class Bucket:
    capacity: float
    tokens: float
    refill_per_s: float
    updated: float

    def refill(self, now: float) -> None:
        elapsed = max(0.0, now - self.updated)
        self.tokens = min(self.capacity,
                          self.tokens + elapsed * self.refill_per_s)
        self.updated = now

    def try_take(self, now: float, cost: float = 1.0) -> bool:
        self.refill(now)
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        return False

    def retry_after_s(self, cost: float = 1.0) -> float:
        deficit = max(0.0, cost - self.tokens)
        if self.refill_per_s <= 0:
            return float("inf")
        return round(deficit / self.refill_per_s, 2)


@dataclass(frozen=True)
class Decision:
    allowed: bool
    retry_after_s: float = 0.0

    def headers(self) -> dict:
        if self.allowed:
            return {}
        return {"Retry-After": str(self.retry_after_s)}


class RateLimiter:
    def __init__(self, capacity: float = 20, refill_per_s: float = 2.0,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.capacity = capacity
        self.refill_per_s = refill_per_s
        self.clock = clock
        self.buckets: dict[str, Bucket] = {}
        self.denied = 0

    def check(self, key: str, cost: float = 1.0) -> Decision:
        now = self.clock()
        bucket = self.buckets.get(key)
        if bucket is None:
            bucket = Bucket(capacity=self.capacity, tokens=self.capacity,
                            refill_per_s=self.refill_per_s, updated=now)
            self.buckets[key] = bucket
        if bucket.try_take(now, cost):
            return Decision(allowed=True)
        self.denied += 1
        return Decision(allowed=False,
                        retry_after_s=bucket.retry_after_s(cost))

    def prune(self, idle_s: float = 600.0) -> int:
        """Drop buckets idle long enough to be full again; returns count."""
        now = self.clock()
        stale = [k for k, b in self.buckets.items()
                 if now - b.updated > idle_s]
        for key in stale:
            del self.buckets[key]
        return len(stale)

    def snapshot(self) -> dict:
        return {"buckets": len(self.buckets), "denied": self.denied}
