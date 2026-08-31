"""Memory store: append-only records in SQLite, rebuilt views on read.

Records never mutate. A correction is a new record that supersedes the old
one by key, and reads resolve the latest per key - the same shape as an
event log, chosen so a crashed write can never corrupt history.
"""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import asdict, dataclass

from relay.errors import MemoryCorrupt

_SCHEMA = """
CREATE TABLE IF NOT EXISTS records(
  id      INTEGER PRIMARY KEY,
  key     TEXT NOT NULL,
  kind    TEXT NOT NULL DEFAULT 'note',
  body    TEXT NOT NULL,
  meta    TEXT NOT NULL DEFAULT '{}',
  created REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS records_key ON records(key);
CREATE VIRTUAL TABLE IF NOT EXISTS records_fts USING fts5(
  key, body, content='records', content_rowid='id');
"""


@dataclass(frozen=True)
class Record:
    key: str
    kind: str
    body: str
    meta: dict
    created: float

    def age_s(self, now: float | None = None) -> float:
        return (now or time.time()) - self.created

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)


class MemoryStore:
    def __init__(self, path: str) -> None:
        self.path = path
        self.con = sqlite3.connect(path)
        self.con.executescript(_SCHEMA)

    def close(self) -> None:
        self.con.close()

    def append(self, key: str, body: str, kind: str = "note",
               meta: dict | None = None) -> int:
        """Append one record; returns its id. Never updates in place."""
        created = time.time()
        with self.con:
            cur = self.con.execute(
                "INSERT INTO records(key, kind, body, meta, created)"
                " VALUES (?,?,?,?,?)",
                (key, kind, body, json.dumps(meta or {}), created))
            self.con.execute(
                "INSERT INTO records_fts(rowid, key, body) VALUES (?,?,?)",
                (cur.lastrowid, key, body))
        return int(cur.lastrowid or 0)

    def latest(self, key: str) -> Record | None:
        row = self.con.execute(
            "SELECT key, kind, body, meta, created FROM records"
            " WHERE key=? ORDER BY id DESC LIMIT 1", (key,)).fetchone()
        return self._to_record(row) if row else None

    def history(self, key: str, limit: int = 20) -> list[Record]:
        rows = self.con.execute(
            "SELECT key, kind, body, meta, created FROM records"
            " WHERE key=? ORDER BY id DESC LIMIT ?", (key, limit)).fetchall()
        return [self._to_record(r) for r in rows]

    def search(self, query: str, limit: int = 10) -> list[Record]:
        escaped = '"' + query.replace('"', '""') + '"'
        rows = self.con.execute(
            "SELECT r.key, r.kind, r.body, r.meta, r.created"
            " FROM records_fts f JOIN records r ON r.id = f.rowid"
            " WHERE records_fts MATCH ? ORDER BY bm25(records_fts)"
            " LIMIT ?", (escaped, limit)).fetchall()
        return [self._to_record(r) for r in rows]

    def integrity_check(self) -> None:
        status = self.con.execute("PRAGMA integrity_check").fetchone()[0]
        if status != "ok":
            raise MemoryCorrupt(f"sqlite integrity: {status}")

    def counts(self) -> dict:
        total = self.con.execute("SELECT count(*) FROM records").fetchone()[0]
        keys = self.con.execute(
            "SELECT count(DISTINCT key) FROM records").fetchone()[0]
        return {"records": total, "keys": keys}

    def _to_record(self, row: tuple) -> Record:
        try:
            meta = json.loads(row[3])
        except json.JSONDecodeError as exc:
            raise MemoryCorrupt(f"bad meta json for key {row[0]!r}") from exc
        return Record(key=row[0], kind=row[1], body=row[2], meta=meta,
                      created=row[4])
