"""A loopback HTTP server that speaks enough of Ollama's API to test decide.py
without a model: GET /api/ps, GET /api/tags, POST /v1/systemone, POST /api/embed.

It binds 127.0.0.1 on a free port and records every request it receives.
"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeSystemOne:
    def __init__(self, probabilities=None, loaded=(), tags=("tev1:0.8b", "embeddinggemma"),
                 delay=0.0, status=200, body=None, embedding=None, runner="mlx"):
        self.probabilities = probabilities or {"none": 0.9, "destroy": 0.05, "exfil": 0.02,
                                               "creds": 0.01, "config": 0.01, "install": 0.01}
        self.loaded = list(loaded)        # names reported by /api/ps
        self.tags = list(tags)            # names reported by /api/tags
        self.delay = delay                # seconds before a systemone or embed reply
        self.status = status              # HTTP status for systemone and embed replies
        self.body = body                  # raw reply text overriding the JSON reply
        self.embedding = embedding        # list[float], or callable(text) -> list[float]
        self.runner = runner
        self.requests = []
        self._server = None

    @property
    def base_url(self):
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def start(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, code, payload):
                data = (payload if isinstance(payload, str) else json.dumps(payload)).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                fake.requests.append({"method": "GET", "path": self.path})
                if self.path == "/api/ps":
                    self._send(200, {"models": [{"name": m, "model": m, "size": 1_400_000_000, "runner": fake.runner}
                                                for m in fake.loaded]})
                elif self.path == "/api/tags":
                    self._send(200, {"models": [{"name": m, "model": m, "size": 812_000_000} for m in fake.tags]})
                else:
                    self._send(404, {"error": "not found"})

            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                try:
                    body = json.loads(self.rfile.read(length) or b"{}")
                except ValueError:
                    body = {}
                fake.requests.append({"method": "POST", "path": self.path, "body": body})
                if fake.delay:
                    time.sleep(fake.delay)
                if fake.status != 200:
                    self._send(fake.status, fake.body or '{"error": "boom"}')
                    return
                if fake.body is not None:
                    self._send(200, fake.body)
                    return
                if self.path == "/api/generate":   # Ollama's unload call
                    self._send(200, {"model": body.get("model"), "done": True, "done_reason": "unload"})
                    return
                if self.path == "/v1/systemone":
                    answers = {}
                    table = fake.probabilities(body.get("state")) if callable(fake.probabilities) else fake.probabilities
                    for name, q in (body.get("questions") or {}).items():
                        if q.get("type") == "choice":
                            probs = {k: table.get(k, 0.0) for k in q.get("criteria", {})}
                            best = max(probs, key=probs.get) if probs else ""
                            answers[name] = {"type": "choice", "choice": best, "probabilities": probs,
                                             "confidence": probs.get(best, 0.0)}
                        else:
                            answers[name] = {"type": "noul", "noul": table.get(name, 0.5)}
                    self._send(200, {"model": body.get("model"), "answers": answers,
                                     "usage": {"input_tokens": 100, "output_tokens": 0}})
                elif self.path == "/api/embed":
                    inputs = body.get("input")
                    inputs = inputs if isinstance(inputs, list) else [inputs]
                    vecs = [fake.embedding(t) if callable(fake.embedding) else (fake.embedding or [1.0, 0.0, 0.0])
                            for t in inputs]
                    self._send(200, {"model": body.get("model"), "embeddings": vecs})
                else:
                    self._send(404, {"error": "not found"})

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server.server_close()

    def posts(self, path):
        return [r for r in self.requests if r["method"] == "POST" and r["path"] == path]
