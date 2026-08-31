"""Compaction: fold superseded records into summaries without losing keys.

The store is append-only, so growth is unbounded by design; compaction is
the pressure valve. Old superseded versions of a key collapse into one
summary record, and the latest record per key is never touched.
"""
from __future__ import annotations

from dataclasses import dataclass

from relay.memory.store import MemoryStore


@dataclass
class CompactionPlan:
    keys_examined: int
    records_to_fold: int
    estimated_bytes_saved: int

    def worth_running(self, threshold_bytes: int = 50_000) -> bool:
        return self.estimated_bytes_saved >= threshold_bytes


@dataclass
class CompactionResult:
    keys_compacted: int
    records_folded: int

    def describe(self) -> str:
        return (f"folded {self.records_folded} records"
                f" across {self.keys_compacted} keys")


def plan_compaction(store: MemoryStore, keep_versions: int = 3) -> CompactionPlan:
    """Dry run: what would compaction fold, and is it worth it."""
    keys = 0
    to_fold = 0
    saved = 0
    rows = store.con.execute(
        "SELECT key, count(*) FROM records GROUP BY key"
        " HAVING count(*) > ?", (keep_versions,)).fetchall()
    for key, count in rows:
        keys += 1
        surplus = count - keep_versions
        to_fold += surplus
        row = store.con.execute(
            "SELECT sum(length(body)) FROM records WHERE key=?"
            " AND id NOT IN (SELECT id FROM records WHERE key=?"
            " ORDER BY id DESC LIMIT ?)",
            (key, key, keep_versions)).fetchone()
        saved += int(row[0] or 0)
    return CompactionPlan(keys_examined=keys, records_to_fold=to_fold,
                          estimated_bytes_saved=saved)


def compact(store: MemoryStore, keep_versions: int = 3) -> CompactionResult:
    """Fold surplus history into one summary record per key."""
    plan = plan_compaction(store, keep_versions)
    if plan.records_to_fold == 0:
        return CompactionResult(keys_compacted=0, records_folded=0)
    folded = 0
    keys_done = 0
    rows = store.con.execute(
        "SELECT key, count(*) FROM records GROUP BY key"
        " HAVING count(*) > ?", (keep_versions,)).fetchall()
    for key, count in rows:
        history = store.history(key, limit=count)
        surplus = history[keep_versions:]
        if not surplus:
            continue
        summary = " | ".join(r.body[:80] for r in reversed(surplus))
        with store.con:
            store.con.execute(
                "DELETE FROM records WHERE key=? AND id NOT IN"
                " (SELECT id FROM records WHERE key=?"
                " ORDER BY id DESC LIMIT ?)",
                (key, key, keep_versions))
        store.append(key, f"[compacted {len(surplus)} versions] {summary}",
                     kind="compacted")
        folded += len(surplus)
        keys_done += 1
    return CompactionResult(keys_compacted=keys_done, records_folded=folded)
