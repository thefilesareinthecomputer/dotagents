"""Experimental: link memory records into a graph. Only tests import this;
it has never shipped. The fixture's planted test-only module."""
from __future__ import annotations

from relay.memory.store import MemoryStore


def build_adjacency(store: MemoryStore, keys: list[str]) -> dict:
    """Edges between records whose bodies mention each other's keys."""
    adjacency: dict[str, set[str]] = {k: set() for k in keys}
    for key in keys:
        record = store.latest(key)
        if record is None:
            continue
        for other in keys:
            if other != key and other in record.body:
                adjacency[key].add(other)
    return {k: sorted(v) for k, v in adjacency.items()}


def orphan_keys(adjacency: dict) -> list[str]:
    linked = {o for targets in adjacency.values() for o in targets}
    return sorted(k for k, targets in adjacency.items()
                  if not targets and k not in linked)
