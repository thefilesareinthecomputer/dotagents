"""Recall scoring: which memories deserve the context window this step.

Score is keyword overlap weighted by recency decay. Decay is a tiebreaker,
never the ranking force - an old exact hit must beat a fresh loose one.
"""
from __future__ import annotations

import math
import re

from relay.memory.store import MemoryStore, Record

_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
_HALF_LIFE_S = 7 * 24 * 3600.0


def tokenize(text: str) -> set[str]:
    return {w.lower() for w in _WORD_RE.findall(text) if len(w) > 2}


def overlap_score(query_tokens: set[str], record: Record) -> float:
    body_tokens = tokenize(record.body)
    if not query_tokens or not body_tokens:
        return 0.0
    hits = len(query_tokens & body_tokens)
    return hits / math.sqrt(len(body_tokens))


def recency_factor(record: Record, now: float | None = None) -> float:
    """1.0 for new, asymptotically 0.9 for ancient. The band is narrow on
    purpose: recency breaks ties between comparable matches and must never
    let a fresh loose match outrank an old exact one."""
    age = record.age_s(now)
    return 0.9 + 0.1 * math.exp(-age * math.log(2) / _HALF_LIFE_S)


def score(query: str, record: Record, now: float | None = None) -> float:
    return overlap_score(tokenize(query), record) * recency_factor(record,
                                                                   now)


def recall(store: MemoryStore, query: str, budget_chars: int = 4000,
           candidates: int = 40) -> list[Record]:
    """Best records for the query that fit the character budget."""
    ranked = sorted(store.search(query, limit=candidates),
                    key=lambda r: score(query, r), reverse=True)
    kept: list[Record] = []
    total = 0
    for record in ranked:
        if total + len(record.body) > budget_chars:
            continue
        kept.append(record)
        total += len(record.body)
    return kept
