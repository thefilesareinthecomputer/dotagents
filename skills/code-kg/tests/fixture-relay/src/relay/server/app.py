"""HTTP surface: stdlib server, table-routed JSON endpoints.

ROUTES is the routing table - (method, path) to handler name - and
handlers.py holds the handlers. The table is data so the /routes endpoint
can print it and tests can assert on it without a socket.
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from relay.config import Config
from relay.limits import RateLimiter
from relay.memory.store import MemoryStore
from relay.server import handlers

ROUTES: dict[tuple[str, str], str] = {
    ("GET", "/health"): "health",
    ("GET", "/config"): "show_config",
    ("GET", "/routes"): "list_routes",
    ("GET", "/memory/search"): "memory_search",
    ("POST", "/runs"): "start_run",
    ("GET", "/runs/latest"): "latest_run",
}


class RelayServer:
    def __init__(self, config: Config, store: MemoryStore) -> None:
        self.config = config
        self.store = store
        self.limiter = RateLimiter(capacity=30, refill_per_s=5.0)

    def dispatch(self, method: str, path: str, body: dict,
                 client: str = "local") -> tuple[int, dict]:
        """Route one request; the runtime edge into handlers lives here."""
        decision = self.limiter.check(client)
        if not decision.allowed:
            return 429, {"error": "rate limited",
                         "retry_after_s": decision.retry_after_s}
        base_path = path.split("?")[0]
        handler_name = ROUTES.get((method, base_path))
        if handler_name is None:
            return 404, {"error": f"no route for {method} {base_path}"}
        handler = getattr(handlers, handler_name)
        return handler(self, path=path, body=body)

    def serve_forever(self) -> None:  # pragma: no cover - socket loop
        server = ThreadingHTTPServer(
            ("127.0.0.1", self.config.server_port),
            _make_handler_class(self))
        server.serve_forever()


def _make_handler_class(app: RelayServer):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - stdlib naming
            self._respond("GET")

        def do_POST(self):  # noqa: N802 - stdlib naming
            self._respond("POST")

        def _respond(self, method: str) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                body = json.loads(raw or b"{}")
            except json.JSONDecodeError:
                body = {}
            status, payload = app.dispatch(method, self.path, body)
            data = json.dumps(payload, sort_keys=True).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, fmt, *args):  # noqa: A003
            return  # telemetry handles logging; stdlib default is noise

    return Handler
