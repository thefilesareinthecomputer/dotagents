"""SQL tool: read-only queries against the relay memory database.

Statements are validated as single SELECTs before execution. The migration
files under migrations/ define the schema this tool queries; the path
constants keep that link visible to static analysis.
"""
from __future__ import annotations

import re
import sqlite3

from relay.errors import ToolFailed
from relay.tools.registry import tool

MIGRATIONS = ("migrations/001_init.sql", "migrations/002_runs.sql")
_ROW_CAP = 200
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|attach|pragma|vacuum)\b",
    re.IGNORECASE)


def validate_select(sql: str) -> str:
    stripped = sql.strip().rstrip(";")
    if ";" in stripped:
        raise ToolFailed("sql", "one statement only", retryable=False)
    if not stripped.lower().startswith("select"):
        raise ToolFailed("sql", "SELECT statements only", retryable=False)
    if _FORBIDDEN.search(stripped):
        raise ToolFailed("sql", "write keyword refused", retryable=False)
    return stripped


def apply_migrations(con: sqlite3.Connection, repo_root: str) -> int:
    """Replay every migration file in order; returns statements executed."""
    executed = 0
    for rel_path in MIGRATIONS:
        with open(f"{repo_root}/{rel_path}", encoding="utf-8") as fh:
            script = fh.read()
        con.executescript(script)
        executed += script.count(";")
    return executed


def _format_rows(cursor: sqlite3.Cursor) -> str:
    names = [d[0] for d in cursor.description or []]
    lines = ["\t".join(names)]
    for i, row in enumerate(cursor):
        if i >= _ROW_CAP:
            lines.append(f"[TRUNCATED at {_ROW_CAP} rows]")
            break
        lines.append("\t".join(str(v) for v in row))
    return "\n".join(lines)


@tool("sql", "Run one read-only SELECT against relay memory", timeout_s=10,
      tags=("local", "read"))
def query_memory(sql: str, db_path: str = "relay-memory.db") -> str:
    statement = validate_select(sql)
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        return _format_rows(con.execute(statement))
    except sqlite3.Error as exc:
        raise ToolFailed("sql", str(exc), retryable=False) from exc
    finally:
        con.close()
