"""Audit log: hash-chained JSON lines, verifiable after the fact.

Each entry carries the hash of the previous one, so truncation or edits are
detectable with nothing but the file. The executor writes one entry per run;
`verify_chain` replays the file and reports the first break.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass

_GENESIS = "0" * 64


@dataclass(frozen=True)
class AuditEntry:
    seq: int
    kind: str
    payload: dict
    prev_hash: str

    def canonical(self) -> str:
        return json.dumps(
            {"seq": self.seq, "kind": self.kind, "payload": self.payload,
             "prev": self.prev_hash},
            sort_keys=True, separators=(",", ":"))

    def digest(self) -> str:
        return hashlib.sha256(self.canonical().encode()).hexdigest()


@dataclass
class ChainReport:
    entries: int
    valid: bool
    first_break: int | None = None

    def describe(self) -> str:
        if self.valid:
            return f"chain valid across {self.entries} entries"
        return f"chain BROKEN at seq {self.first_break}"


class AuditLog:
    def __init__(self, path: str) -> None:
        self.path = path
        self._tail_hash = self._recover_tail()
        self._seq = self._recover_seq()

    def _recover_tail(self) -> str:
        last = self._last_line()
        if last is None:
            return _GENESIS
        return str(last.get("hash", _GENESIS))

    def _recover_seq(self) -> int:
        last = self._last_line()
        return int(last.get("seq", -1)) + 1 if last else 0

    def _last_line(self) -> dict | None:
        if not os.path.exists(self.path):
            return None
        tail = None
        with open(self.path, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    tail = line
        if tail is None:
            return None
        try:
            return json.loads(tail)
        except json.JSONDecodeError:
            return None

    def append(self, kind: str, payload: dict) -> AuditEntry:
        entry = AuditEntry(seq=self._seq, kind=kind, payload=payload,
                           prev_hash=self._tail_hash)
        record = json.loads(entry.canonical())
        record["hash"] = entry.digest()
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, sort_keys=True,
                                separators=(",", ":")) + "\n")
        self._tail_hash = record["hash"]
        self._seq += 1
        return entry

    def verify_chain(self) -> ChainReport:
        if not os.path.exists(self.path):
            return ChainReport(entries=0, valid=True)
        prev = _GENESIS
        count = 0
        with open(self.path, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    return ChainReport(count, False, first_break=count)
                entry = AuditEntry(
                    seq=int(record.get("seq", -1)),
                    kind=str(record.get("kind", "")),
                    payload=record.get("payload", {}),
                    prev_hash=str(record.get("prev", "")))
                if entry.prev_hash != prev \
                        or entry.digest() != record.get("hash"):
                    return ChainReport(count, False, first_break=entry.seq)
                prev = str(record["hash"])
                count += 1
        return ChainReport(entries=count, valid=True)
