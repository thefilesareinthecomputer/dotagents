"""Scheduler: recurring goals on fixed intervals, cooperatively ticked.

No threads. The server (or any loop) calls `tick()` and due jobs run
through the callback it was built with, so the scheduler stays testable
with a fake clock and a recording callback.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

from relay.errors import RelayError

RunCallback = Callable[[str], dict]


@dataclass
class Job:
    name: str
    goal: str
    interval_s: float
    next_due: float
    runs: int = 0
    failures: int = 0
    last_result: dict = field(default_factory=dict)

    def due(self, now: float) -> bool:
        return now >= self.next_due

    def reschedule(self, now: float) -> None:
        # Anchor on the planned time, not the actual run time, so drift
        # does not accumulate; a long outage skips ahead rather than
        # replaying every missed tick.
        periods_behind = max(1, int((now - self.next_due)
                                    // self.interval_s) + 1)
        self.next_due += periods_behind * self.interval_s


class Scheduler:
    def __init__(self, run_callback: RunCallback,
                 clock: Callable[[], float] = time.time) -> None:
        self.run_callback = run_callback
        self.clock = clock
        self.jobs: dict[str, Job] = {}

    def add(self, name: str, goal: str, interval_s: float) -> Job:
        if interval_s <= 0:
            raise RelayError(f"job {name!r}: interval must be positive")
        if name in self.jobs:
            raise RelayError(f"job {name!r} already scheduled")
        job = Job(name=name, goal=goal, interval_s=interval_s,
                  next_due=self.clock() + interval_s)
        self.jobs[name] = job
        return job

    def remove(self, name: str) -> bool:
        return self.jobs.pop(name, None) is not None

    def due_jobs(self) -> list[Job]:
        now = self.clock()
        return sorted((j for j in self.jobs.values() if j.due(now)),
                      key=lambda j: j.next_due)

    def tick(self) -> list[str]:
        """Run every due job once; returns the names that ran."""
        ran: list[str] = []
        now = self.clock()
        for job in self.due_jobs():
            try:
                job.last_result = self.run_callback(job.goal)
            except RelayError as exc:
                job.failures += 1
                job.last_result = {"error": str(exc)}
            finally:
                job.runs += 1
                job.reschedule(now)
                ran.append(job.name)
        return ran

    def snapshot(self) -> list[dict]:
        return [{"name": j.name, "goal": j.goal, "runs": j.runs,
                 "failures": j.failures,
                 "next_due_in_s": round(j.next_due - self.clock(), 1)}
                for _, j in sorted(self.jobs.items())]
