"""A loopback HTTP server that speaks enough of Ollama's API to test the ollama harness
without a daemon or a model: /api/tags, /api/show and /api/chat. Binds 127.0.0.1 on a
free port and records every request."""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeOllama:
    def __init__(self, tags=("deepseek-v4.1-flash:cloud",), thinking=None, context=1048576,
                 reply="OK: the files say so.", thinking_text=None, status=200, model_in_reply=None,
                 fail_first=0, cut_stream=False, chunk_delay=0.0, framing="close", error_chunk=None,
                 raw_lines=None, dribble=None):
        self.tags = list(tags)
        self.thinking = thinking                  # the /api/show `thinking` block, or None to omit it
        self.context = context                    # model_info["<arch>.context_length"], or None to omit
        self.reply = reply                        # str, or callable(body) -> str
        self.thinking_text = thinking_text        # message.thinking, or None to omit the field
        self.status = status                      # HTTP status for /api/chat
        self.model_in_reply = model_in_reply      # reply `model`, default the requested tag
        self.fail_first = fail_first              # answer this many /api/chat calls with `status` (or 502), then succeed
        self.cut_stream = cut_stream              # close the stream before the final chunk
        self.chunk_delay = chunk_delay            # seconds between streamed chunks
        self.framing = framing                    # "close": no length header; "chunked": Transfer-Encoding chunked, and a cut stream ends inside a chunk (IncompleteRead)
        self.error_chunk = error_chunk            # a string: after the first content chunk, send {"error": <string>} and stop
        self.raw_lines = raw_lines                # a list of raw byte lines to send in place of the content chunks (malformed streams)
        self.dribble = dribble                    # (bytes_per_write, seconds_between): send one long line one byte group at a time, never a newline
        self.chat_calls = 0
        self.requests = []
        self._server = None

    def start(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, code, payload):
                data = json.dumps(payload).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                fake.requests.append({"method": "GET", "path": self.path})
                if self.path == "/api/tags":
                    self._send(200, {"models": [{"name": t, "size": 0} for t in fake.tags]})
                else:
                    self._send(404, {"error": "not found"})

            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length) or b"{}")
                fake.requests.append({"method": "POST", "path": self.path, "body": body})
                if self.path == "/api/show":
                    if body.get("model") not in fake.tags:
                        self._send(404, {"error": f"model '{body.get('model')}' not found"})
                        return
                    show = {"capabilities": ["completion", "thinking", "tools"], "details": {"family": "fake"},
                            "model_info": {"general.architecture": "fake"}}
                    if fake.context is not None:
                        show["model_info"]["fake.context_length"] = fake.context
                    if fake.thinking is not None:
                        show["thinking"] = fake.thinking
                    self._send(200, show)
                elif self.path == "/api/chat":
                    fake.chat_calls += 1
                    if fake.chat_calls <= fake.fail_first:
                        self._send(fake.status if fake.status != 200 else 502, {"error": "boom"})
                        return
                    if fake.status != 200:
                        self._send(fake.status, {"error": "boom"})
                        return
                    reply = fake.reply(body) if callable(fake.reply) else fake.reply
                    model = fake.model_in_reply or body.get("model")
                    prompt = sum(len(m.get("content", "")) for m in body.get("messages", []))
                    final = {"model": model, "done": True, "done_reason": "stop",
                             "message": {"role": "assistant", "content": ""},
                             "prompt_eval_count": prompt // 4, "prompt_eval_cached_count": 0,
                             "eval_count": max(1, len(reply) // 4), "total_duration": 123_000_000}
                    if not body.get("stream"):
                        final["message"]["content"] = reply
                        if fake.thinking_text is not None:
                            final["message"]["thinking"] = fake.thinking_text
                        self._send(200, final)
                        return
                    # the streaming shape: thinking chunks, then content in pieces, then the final chunk
                    chunks = []
                    if fake.thinking_text is not None:
                        half = max(1, len(fake.thinking_text) // 2)
                        for piece in (fake.thinking_text[:half], fake.thinking_text[half:]):
                            chunks.append({"model": model, "done": False, "message": {"role": "assistant", "content": "", "thinking": piece}})
                    for i in range(0, len(reply), 7):
                        chunks.append({"model": model, "done": False, "message": {"role": "assistant", "content": reply[i:i + 7]}})
                    lines = [(json.dumps(c) + "\n").encode() for c in chunks]
                    if fake.raw_lines is not None:
                        lines = [l if l.endswith(b"\n") else l + b"\n" for l in fake.raw_lines]
                    if fake.error_chunk is not None:
                        lines = lines[:1] + [(json.dumps({"error": fake.error_chunk}) + "\n").encode()]
                    elif not fake.cut_stream and fake.raw_lines is None:
                        lines.append((json.dumps(final) + "\n").encode())
                    self.send_response(200)
                    self.send_header("Content-Type", "application/x-ndjson")
                    chunked = fake.framing == "chunked"
                    if chunked:
                        self.send_header("Transfer-Encoding", "chunked")
                    self.end_headers()

                    def frame(data: bytes) -> bytes:
                        return (f"{len(data):x}\r\n".encode() + data + b"\r\n") if chunked else data

                    try:
                        if fake.dribble:
                            size, pause = fake.dribble
                            while True:
                                self.wfile.write(frame(b"x" * size))
                                self.wfile.flush()
                                time.sleep(pause)
                        for l in lines:
                            if fake.chunk_delay:
                                time.sleep(fake.chunk_delay)
                            self.wfile.write(frame(l))
                            self.wfile.flush()
                        if chunked:
                            if fake.cut_stream:
                                # announce a chunk and close inside it: the client's read raises IncompleteRead
                                self.wfile.write(b"400\r\n" + b"{")
                                self.wfile.flush()
                            else:
                                self.wfile.write(b"0\r\n\r\n")
                                self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        pass  # the client gave up on the stream, which a test may do on purpose
                else:
                    self._send(404, {"error": "not found"})

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self

    @property
    def host(self):
        return f"127.0.0.1:{self._server.server_address[1]}"

    def posts(self, path=None):
        return [r for r in self.requests if r["method"] == "POST" and (path is None or r["path"] == path)]

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server.server_close()
