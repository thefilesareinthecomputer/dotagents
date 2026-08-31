"""Telemetry: structured events on stderr, counters in memory.

No third-party client and no network; a deployment that wants OTLP wraps
this. Events are single-line JSON so any log shipper can lift them.
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter

_LEVELS = {"debug": 10, "info": 20, "warning": 30, "error": 40}


class Timer:
    def __init__(self) -> None:
        self.started = time.monotonic()

    def elapsed_s(self) -> float:
        return round(time.monotonic() - self.started, 4)


class Telemetry:
    def __init__(self, level: str = "info") -> None:
        self.threshold = _LEVELS.get(level, 20)
        self.counters: Counter[str] = Counter()

    def event(self, name: str, level: str = "info", **fields) -> None:
        self.counters[name] += 1
        if _LEVELS.get(level, 20) < self.threshold:
            return
        payload = {"event": name, "ts": round(time.time(), 3), **fields}
        print(json.dumps(payload, sort_keys=True), file=sys.stderr)

    def timer(self) -> Timer:
        return Timer()

    def snapshot(self) -> dict:
        return dict(sorted(self.counters.items()))
