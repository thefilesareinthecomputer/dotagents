"""ollama.py client seam: loopback lockdown and lifecycle helpers.

The invariant under test (user directive 2026-08-27): this app NEVER sends
traffic to a non-local Ollama endpoint. Cloud models (`:cloud` tags) are
reached only as proxied through the loopback daemon.

The wire tests run the real urllib client against a fake daemon bound to
127.0.0.1, so request bodies, chunked streaming, error mapping and early
consumer exit are exercised end to end with no network beyond loopback.
"""

import asyncio
import http.server
import json
import select
import socket
import threading
import time

import pytest

from second_brain import config, ollama


class FakeDaemon(http.server.BaseHTTPRequestHandler):
    """Answers /api/tags, /api/ps and /api/chat like Ollama does. The
    server object carries the script: `chat_status`, `chat_lines` (sent
    as chunked NDJSON), `header_delay` (seconds before the response
    starts), `hold` (seconds to keep the stream open after the last line)
    and `bodies` (every POST body, parsed)."""

    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def _send_json(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/tags":
            self._send_json(200, {"models": [{"name": "qwen3:latest"},
                                             {"name": "llama3:8b"}]})
        elif self.path == "/api/ps":
            self._send_json(200, {"models": [{"name": "qwen3:latest"}]})
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        self.server.bodies.append(body)
        if not body.get("stream"):
            self._send_json(200, {"done": True})
            return
        time.sleep(self.server.header_delay)  # a cold model loading
        if self.server.chat_status != 200:
            self.send_response(self.server.chat_status)
            payload = self.server.chat_error.encode()
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        try:
            for line in self.server.chat_lines:
                data = line.encode()
                self.wfile.write(b"%x\r\n%s\r\n" % (len(data), data))
                self.wfile.flush()
            # Hold the stream open with no bytes flowing, so the client's
            # read stays blocked, and watch for the client hanging up.
            deadline = time.monotonic() + self.server.hold
            while time.monotonic() < deadline:
                readable, _, _ = select.select([self.connection], [], [],
                                               0.05)
                if readable and not self.connection.recv(1, socket.MSG_PEEK):
                    self.server.client_left.set()
                    return
            self.wfile.write(b"0\r\n\r\n")
        except OSError:
            self.server.client_left.set()


@pytest.fixture
def daemon(monkeypatch):
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeDaemon)
    server.daemon_threads = True
    server.bodies = []
    server.chat_status = 200
    server.chat_error = ""
    server.chat_lines = []
    server.hold = 0.0
    server.header_delay = 0.0
    server.client_left = threading.Event()
    threading.Thread(target=server.serve_forever,
                     kwargs={"poll_interval": 0.05}, daemon=True).start()
    monkeypatch.setenv("OLLAMA_URL",
                       f"http://127.0.0.1:{server.server_address[1]}")
    monkeypatch.setenv("OLLAMA_KEEP_ALIVE", "7m")
    yield server
    server.shutdown()
    server.server_close()


def collect(stream_args, limit=None):
    """Drain chat_stream into a list; stop after `limit` chunks."""
    async def gather():
        chunks = []
        stream = ollama.chat_stream(*stream_args)
        try:
            async for chunk in stream:
                chunks.append(chunk)
                if limit is not None and len(chunks) >= limit:
                    break
        finally:
            await stream.aclose()
        return chunks
    return asyncio.run(gather())


def test_base_accepts_loopback(monkeypatch):
    for url in ("http://localhost:11434", "http://127.0.0.1:11434",
                "http://[::1]:11434"):
        monkeypatch.setenv("OLLAMA_URL", url)
        assert ollama._base() == url


@pytest.mark.parametrize("url", [
    "https://ollama.com",
    "https://api.ollama.com/v1",
    "http://192.168.1.50:11434",
    "http://my-gpu-box.local:11434",
])
def test_base_refuses_non_local(monkeypatch, url):
    monkeypatch.setenv("OLLAMA_URL", url)
    with pytest.raises(ollama.OllamaError) as err:
        ollama._base()
    assert "non-local" in str(err.value)


def test_chat_stream_refuses_non_local(monkeypatch):
    monkeypatch.setenv("OLLAMA_URL", "https://ollama.com")

    async def first():
        stream = ollama.chat_stream("x", [])
        return await stream.__anext__()

    with pytest.raises(ollama.OllamaError):
        asyncio.run(first())


def test_tags_and_loaded_fail_closed_on_non_local(monkeypatch):
    monkeypatch.setenv("OLLAMA_URL", "https://ollama.com")
    assert ollama.tags() == []
    assert ollama.loaded() == []


def test_unload_fails_closed_on_non_local(monkeypatch):
    monkeypatch.setenv("OLLAMA_URL", "https://ollama.com")
    assert ollama.unload("x") is False


def test_no_tools_flag_on_error():
    assert ollama.OllamaError(400, "model does not support tools").no_tools
    assert not ollama.OllamaError(500, "boom").no_tools


def test_tool_schema_conversion():
    converted = ollama.tool_schemas([{
        "name": "search_kb", "description": "d",
        "input_schema": {"type": "object", "properties": {}}}])
    assert converted == [{"type": "function", "function": {
        "name": "search_kb", "description": "d",
        "parameters": {"type": "object", "properties": {}}}}]


def test_keep_alive_config(monkeypatch, tmp_path):
    monkeypatch.setenv("SECOND_BRAIN_HOME", str(tmp_path))
    monkeypatch.delenv("OLLAMA_KEEP_ALIVE", raising=False)
    assert config.ollama_keep_alive() == "5m"
    monkeypatch.setenv("OLLAMA_KEEP_ALIVE", "0")
    assert config.ollama_keep_alive() == "0"


# --- the wire, against a loopback fake daemon ---

def test_tags_and_loaded_read_the_daemon(daemon):
    assert ollama.tags() == ["qwen3:latest", "llama3:8b"]
    assert ollama.loaded() == ["qwen3:latest"]


def test_tags_empty_when_nothing_listens(monkeypatch):
    monkeypatch.setenv("OLLAMA_URL", "http://127.0.0.1:9")
    assert ollama.tags() == []
    assert ollama.loaded() == []
    assert ollama.unload("x") is False


def test_requests_bypass_proxy_settings(daemon, monkeypatch):
    """An HTTP_PROXY in the environment must not route loopback daemon
    traffic anywhere else; the dead proxy port proves it is unused."""
    for name in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"):
        monkeypatch.setenv(name, "http://127.0.0.1:9")
    for name in ("NO_PROXY", "no_proxy"):
        monkeypatch.delenv(name, raising=False)
    assert ollama.tags() == ["qwen3:latest", "llama3:8b"]
    daemon.chat_lines = ['{"done": true}\n']
    assert collect(("qwen3:latest", [])) == [{"done": True}]


def test_unload_posts_keep_alive_zero(daemon):
    assert ollama.unload("qwen3:latest") is True
    assert daemon.bodies == [{"model": "qwen3:latest", "messages": [],
                              "keep_alive": 0, "stream": False}]


def test_chat_stream_parses_lines_and_sends_keep_alive(daemon):
    daemon.chat_lines = [
        '{"message": {"content": "Hel"}, "done": false}\n',
        '\n',
        '{"message": {"content": "lo"}, "done": false}\n{"done": true, ',
        '"eval_count": 3}\n',
    ]
    tools = ollama.tool_schemas([{"name": "search_kb", "description": "d",
                                  "input_schema": {"type": "object"}}])
    messages = [{"role": "user", "content": "hi"}]
    chunks = collect(("qwen3:latest", messages, tools))
    assert chunks == [{"message": {"content": "Hel"}, "done": False},
                      {"message": {"content": "lo"}, "done": False},
                      {"done": True, "eval_count": 3}]
    assert daemon.bodies == [{"model": "qwen3:latest", "messages": messages,
                              "stream": True, "keep_alive": "7m",
                              "tools": tools}]


def test_chat_stream_omits_empty_tools(daemon):
    daemon.chat_lines = ['{"done": true}\n']
    collect(("qwen3:latest", [], None))
    assert "tools" not in daemon.bodies[0]


def test_chat_stream_maps_error_status_to_ollama_error(daemon):
    daemon.chat_status = 400
    daemon.chat_error = json.dumps(
        {"error": "qwen2:0.5b does not support tools"})
    with pytest.raises(ollama.OllamaError) as err:
        collect(("qwen2:0.5b", []))
    assert err.value.status == 400 and err.value.no_tools
    assert str(err.value) == "ollama 400: qwen2:0.5b does not support tools"

    daemon.chat_status = 500
    daemon.chat_error = "plain text failure"
    with pytest.raises(ollama.OllamaError) as err:
        collect(("qwen3:latest", []))
    assert err.value.status == 500 and not err.value.no_tools
    assert "plain text failure" in str(err.value)


def test_chat_stream_waits_past_connect_timeout_for_a_cold_model(
        daemon, monkeypatch):
    """The connect timeout bounds only the connect; the wait for the
    first byte rides the read timeout, which covers a model load."""
    monkeypatch.setattr(ollama, "_CONNECT_TIMEOUT", 0.2)
    daemon.header_delay = 0.6
    daemon.chat_lines = ['{"done": true}\n']
    assert collect(("qwen3:latest", [])) == [{"done": True}]

    monkeypatch.setattr(ollama, "_READ_TIMEOUT", 0.2)
    with pytest.raises(OSError):  # TimeoutError, a subclass of OSError
        collect(("qwen3:latest", []))


def test_chat_stream_bad_line_raises(daemon):
    daemon.chat_lines = ['not json\n']
    with pytest.raises(ValueError):
        collect(("qwen3:latest", []))


def test_chat_stream_consumer_exit_closes_the_connection(daemon):
    """A consumer that stops after the first chunk must not leave the
    worker reading a stream the daemon would hold open for 20 s: the
    socket is shut down, the worker ends, and asyncio.run (which waits
    for executor threads) returns at once."""
    daemon.chat_lines = ['{"message": {"content": "a"}, "done": false}\n']
    daemon.hold = 20.0
    started = time.monotonic()
    chunks = collect(("qwen3:latest", []), limit=1)
    assert chunks == [{"message": {"content": "a"}, "done": False}]
    assert time.monotonic() - started < 5.0
    assert daemon.client_left.wait(5.0)
