"""A loopback HTTP server that speaks enough of Ollama's API and the OpenAI API
to test model_task.py without a real model.

It binds 127.0.0.1 on a free port and records every request it receives.
"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeBackend:
    def __init__(self, reply="ok", prompt_eval_count=None, delay=0.0, status=200,
                 models=("qwen3.5:4b",), error_body=None):
        self.reply = reply                    # str, or callable(body) -> str
        self.prompt_eval_count = prompt_eval_count
        self.delay = delay
        self.status = status
        self.models = list(models)
        self.error_body = error_body          # callable(headers) -> str, for error replies
        self.requests = []
        self._server = None

    def start(self):
        backend = self

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
                backend.requests.append({"method": "GET", "path": self.path, "headers": dict(self.headers)})
                entries = [m if isinstance(m, dict) else {"name": m} for m in backend.models]
                if self.path == "/api/tags":
                    self._send(200, {"models": entries})
                elif self.path.endswith("/models"):
                    self._send(200, {"data": [{"id": e["name"]} for e in entries]})
                else:
                    self._send(404, {"error": "not found"})

            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length) or b"{}")
                backend.requests.append({"method": "POST", "path": self.path, "body": body,
                                         "headers": dict(self.headers)})
                if self.path == "/api/generate":   # Ollama's unload call
                    self._send(200, {"model": body.get("model"), "done": True, "done_reason": "unload"})
                    return
                if backend.delay:
                    time.sleep(backend.delay)
                if backend.status != 200:
                    text = backend.error_body(dict(self.headers)) if backend.error_body else '{"error": "boom"}'
                    self._send(backend.status, text)
                    return
                reply = backend.reply(body) if callable(backend.reply) else backend.reply
                prompt = "".join(m.get("content", "") for m in body.get("messages", []))
                pec = backend.prompt_eval_count if backend.prompt_eval_count is not None else len(prompt) // 4
                if self.path == "/api/chat":
                    self._send(200, {"model": body.get("model"), "done": True,
                                     "message": {"role": "assistant", "content": reply},
                                     "prompt_eval_count": pec, "eval_count": max(1, len(reply) // 4)})
                elif self.path.endswith("/chat/completions"):
                    self._send(200, {"choices": [{"message": {"role": "assistant", "content": reply}}],
                                     "usage": {"prompt_tokens": pec, "completion_tokens": max(1, len(reply) // 4)}})
                else:
                    self._send(404, {"error": "not found"})

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self

    @property
    def port(self):
        return self._server.server_address[1]

    @property
    def url(self):
        return f"http://127.0.0.1:{self.port}"

    def posts(self):
        return [r for r in self.requests if r["method"] == "POST"]

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server.server_close()
