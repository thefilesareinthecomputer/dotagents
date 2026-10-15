"""A fake Ollama daemon on loopback for the harness-bench tests. Never touches the network.

Records every request body it receives, and answers:
  POST /v1/chat/completions  an SSE stream (or one JSON object when stream is false) with
                             one tool call whose arguments arrive in two pieces, then usage
  POST /api/chat             newline-delimited JSON with one tool call and done counts
  GET  /api/tags, /v1/models a one-model listing
  anything else              200, so a test can prove the proxy refused it first
FakeDaemon.bad_args makes the v1 tool call's arguments invalid JSON.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeDaemon:
    def __init__(self):
        self.received = []
        self.bad_args = False
        daemon = self

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def send(self, code, body, ctype="application/json"):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                daemon.received.append(("GET", self.path, None))
                self.send(200, json.dumps({"models": [{"name": "fake:cloud"}], "data": []}).encode())

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}")
                daemon.received.append(("POST", self.path, body))
                if self.path == "/v1/chat/completions":
                    args = ['{"command": ', '"ls"}'] if not daemon.bad_args else ['{"command": ', '"ls"']
                    if not body.get("stream"):
                        obj = {"choices": [{"message": {"content": "", "tool_calls": [
                            {"function": {"name": "shell", "arguments": "".join(args)}}]}}],
                               "usage": {"prompt_tokens": 11, "completion_tokens": 7}}
                        return self.send(200, json.dumps(obj).encode())
                    events = [
                        {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"name": "shell", "arguments": args[0]}}]}}]},
                        {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": args[1]}}]}}]},
                        {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]},
                    ]
                    if (body.get("stream_options") or {}).get("include_usage"):
                        events.append({"choices": [], "usage": {"prompt_tokens": 11, "completion_tokens": 7}})
                    data = b"".join(b"data: " + json.dumps(e).encode() + b"\n\n" for e in events) + b"data: [DONE]\n\n"
                    return self.send(200, data, "text/event-stream")
                if self.path == "/api/chat":
                    lines = [
                        {"message": {"role": "assistant", "content": "",
                                     "tool_calls": [{"function": {"name": "shell", "arguments": {"command": "ls"}}}]},
                         "done": False},
                        {"message": {"role": "assistant", "content": ""}, "done": True,
                         "prompt_eval_count": 13, "eval_count": 5},
                    ]
                    data = b"".join(json.dumps(x).encode() + b"\n" for x in lines)
                    return self.send(200, data, "application/x-ndjson")
                self.send(200, b"{}")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
