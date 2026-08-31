"""Route handlers: pure functions from (app, request) to (status, payload).

Each takes the RelayServer for its config and store, returns JSON-ready
dicts, and raises nothing - errors become status codes here, at the edge.
"""
from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from relay.errors import RelayError
from relay.executor import Executor
from relay.server import app as app_module


def _query_param(path: str, name: str, default: str = "") -> str:
    parsed = parse_qs(urlparse(path).query)
    values = parsed.get(name, [])
    return values[0] if values else default


def health(app, path: str, body: dict) -> tuple[int, dict]:
    counts = app.store.counts()
    return 200, {"status": "ok", "memory": counts}


def show_config(app, path: str, body: dict) -> tuple[int, dict]:
    return 200, {"config": app.config.describe()}


def list_routes(app, path: str, body: dict) -> tuple[int, dict]:
    table = sorted(f"{m} {p} -> {h}"
                   for (m, p), h in app_module.ROUTES.items())
    return 200, {"routes": table}


def memory_search(app, path: str, body: dict) -> tuple[int, dict]:
    query = _query_param(path, "q")
    if not query:
        return 400, {"error": "missing query parameter q"}
    records = app.store.search(query, limit=10)
    return 200, {"query": query,
                 "hits": [{"key": r.key, "kind": r.kind,
                           "body": r.body[:300]} for r in records]}


def start_run(app, path: str, body: dict) -> tuple[int, dict]:
    goal = str(body.get("goal", "")).strip()
    if not goal:
        return 400, {"error": "body must carry a non-empty goal"}
    executor = Executor(app.config, app.store)
    try:
        result = executor.run(goal)
    except RelayError as exc:
        return 422, {"error": str(exc)}
    return 200, result.summary()


def latest_run(app, path: str, body: dict) -> tuple[int, dict]:
    for record in app.store.search("run", limit=5):
        if record.kind == "run":
            return 200, {"key": record.key, "meta": record.meta,
                         "body": record.body}
    return 404, {"error": "no runs recorded yet"}
