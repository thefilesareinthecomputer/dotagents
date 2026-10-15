#!/usr/bin/env python3
"""harness-bench recording proxy: the one network path a harness under test gets.

Listens on a loopback port, forwards a fixed set of endpoints to an Ollama daemon on
loopback, and writes one JSON line per model request: endpoint, tag, task or auxiliary
call, the thinking and temperature the harness sent and what was applied, prompt and
output tokens, tool calls, malformed tool calls, wall clock and a hash of the system
prompt. It refuses any tag but the one under test and every endpoint it does not know.

A task call is a chat request that offers tools; anything else is auxiliary (a title, a
summary). Pins apply to task calls only, so a harness that turns thinking off for its
own housekeeping keeps that property and the log shows it.

    bench_proxy.py --tag <model> --log <file.jsonl> --port-file <file>
        [--think LEVEL] [--temperature T] [--upstream 127.0.0.1:11434]
"""

import argparse
import hashlib
import http.client
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

CHAT = {"/api/chat", "/v1/chat/completions"}
LISTING_GET = {"/api/tags", "/api/version", "/v1/models"}
LISTING_POST = {"/api/show"}
MAX_BODY = 32 * 1024 * 1024
READ = 64 * 1024
UPSTREAM_TIMEOUT = 900


class Config:
    def __init__(self, tag, log, think=None, temperature=None, upstream=("127.0.0.1", 11434), exchanges=None):
        self.tag = tag
        self.log = Path(log)
        self.think = think
        self.temperature = temperature
        self.upstream = upstream
        self.exchanges = Path(exchanges) if exchanges else None
        self.lock = threading.Lock()

    def write(self, rec: dict, path: Path | None = None) -> None:
        line = json.dumps(rec, sort_keys=True) + "\n"
        with self.lock, (path or self.log).open("a", encoding="utf-8") as f:
            f.write(line)


def parse_upstream(value: str) -> tuple[str, int]:
    """Loopback only: the proxy never forwards off the machine."""
    host, _, port = value.rpartition(":")
    if host not in ("127.0.0.1", "localhost") or not port.isdigit():
        raise ValueError(f"upstream must be 127.0.0.1:<port>, got {value!r}")
    return "127.0.0.1", int(port)


def system_hash(body: dict) -> str | None:
    for m in body.get("messages") or []:
        # OpenAI-shaped clients send the system prompt as "developer" (pi does)
        if isinstance(m, dict) and m.get("role") in ("system", "developer"):
            content = m.get("content")
            if not isinstance(content, str):
                content = json.dumps(content, sort_keys=True)
            return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    return None


def apply_pins(path: str, body: dict, cfg: Config, task: bool) -> dict:
    """Rewrite the task call's thinking and temperature to the run's pins. Returns what
    was sent and what was applied, for the log."""
    v1 = path == "/v1/chat/completions"
    key = "reasoning_effort" if v1 else "think"
    opts = body.get("options") if isinstance(body.get("options"), dict) else {}
    sent = {"think": body.get(key), "temperature": body.get("temperature") if v1 else opts.get("temperature")}
    if task and cfg.think is not None:
        body[key] = cfg.think
    if task and cfg.temperature is not None:
        if v1:
            body["temperature"] = cfg.temperature
        else:
            body["options"] = dict(opts, temperature=cfg.temperature)
    if v1 and body.get("stream") and not (body.get("stream_options") or {}).get("include_usage"):
        body["stream_options"] = dict(body.get("stream_options") or {}, include_usage=True)
    opts = body.get("options") if isinstance(body.get("options"), dict) else {}
    applied = {"think": body.get(key), "temperature": body.get("temperature") if v1 else opts.get("temperature")}
    return {"sent": sent, "applied": applied}


class Tally:
    """Reads the response as it streams past and counts usage and tool calls, for both
    the OpenAI-shaped SSE stream and Ollama's newline-delimited JSON."""

    def __init__(self, v1: bool):
        self.v1 = v1
        self.buf = b""
        self.prompt = None
        self.output = None
        self.calls = {}        # v1: index -> accumulated arguments text
        self.names = {}        # v1: index -> tool name
        self.native_calls = []  # /api/chat: (name, arguments object)
        self.content = []
        self.reasoning = []
        self.error = None

    def response(self) -> dict:
        """The assistant turn as the harness received it, for the exchange record."""
        if self.v1:
            calls = [{"name": self.names.get(i), "arguments": self.calls[i]} for i in sorted(self.calls)]
        else:
            calls = [{"name": n, "arguments": a} for n, a in self.native_calls]
        return {"content": "".join(self.content), "reasoning": "".join(self.reasoning), "tool_calls": calls}

    def feed(self, chunk: bytes) -> None:
        self.buf += chunk
        while b"\n" in self.buf:
            line, self.buf = self.buf.split(b"\n", 1)
            self.line(line.strip())

    def finish(self) -> None:
        if self.buf.strip():
            self.line(self.buf.strip())
        self.buf = b""

    def line(self, line: bytes) -> None:
        if not line:
            return
        if self.v1:
            if not line.startswith(b"data:"):
                return
            line = line[5:].strip()
            if line == b"[DONE]":
                return
        try:
            obj = json.loads(line)
        except ValueError:
            return
        if isinstance(obj, dict):
            self.record(obj)

    def whole(self, data: bytes) -> None:
        """A non-streaming response is one JSON object."""
        try:
            obj = json.loads(data)
        except ValueError:
            return
        if not isinstance(obj, dict):
            return
        if self.v1:
            for ch in obj.get("choices") or []:
                msg = ch.get("message") or {}
                self.text(msg)
                for i, tc in enumerate(msg.get("tool_calls") or []):
                    fn = (tc or {}).get("function") or {}
                    self.names[i] = fn.get("name")
                    self.calls[i] = fn.get("arguments") if isinstance(fn.get("arguments"), str) else json.dumps(fn.get("arguments"))
            self.usage(obj.get("usage"))
        else:
            self.record(obj)

    def record(self, obj: dict) -> None:
        if obj.get("error"):
            self.error = str(obj.get("error"))[:300]
        if self.v1:
            for ch in obj.get("choices") or []:
                delta = ch.get("delta") or {}
                self.text(delta)
                for tc in delta.get("tool_calls") or []:
                    idx = tc.get("index", len(self.calls))
                    fn = tc.get("function") or {}
                    self.calls.setdefault(idx, "")
                    if fn.get("name"):
                        self.names[idx] = fn["name"]
                    if isinstance(fn.get("arguments"), str):
                        self.calls[idx] += fn["arguments"]
            self.usage(obj.get("usage"))
        else:
            msg = obj.get("message") or {}
            self.text(msg)
            for tc in msg.get("tool_calls") or []:
                fn = (tc or {}).get("function") or {}
                self.native_calls.append((fn.get("name"), fn.get("arguments")))
            if obj.get("done"):
                self.prompt = obj.get("prompt_eval_count", self.prompt)
                self.output = obj.get("eval_count", self.output)

    def text(self, msg: dict) -> None:
        if isinstance(msg.get("content"), str):
            self.content.append(msg["content"])
        for key in ("reasoning", "reasoning_content", "thinking"):
            if isinstance(msg.get(key), str):
                self.reasoning.append(msg[key])

    def usage(self, u) -> None:
        if isinstance(u, dict):
            self.prompt = u.get("prompt_tokens", self.prompt)
            self.output = u.get("completion_tokens", self.output)

    def tool_counts(self) -> tuple[int, int]:
        if self.v1:
            bad = 0
            for args in self.calls.values():
                try:
                    ok = isinstance(json.loads(args or "{}"), dict)
                except ValueError:
                    ok = False
                bad += 0 if ok else 1
            return len(self.calls), bad
        return len(self.native_calls), sum(1 for _, a in self.native_calls if not isinstance(a, dict))


def make_handler(cfg: Config):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # the JSONL log is the record
            pass

        def refuse(self, code: int, reason: str) -> None:
            body = json.dumps({"error": f"harness-bench proxy: {reason}"}).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            cfg.write({"ts": time.time(), "endpoint": self.path, "refused": reason, "status": code})

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path not in LISTING_GET:
                return self.refuse(403, f"endpoint not allowed: GET {path}")
            self.forward("GET", path, None)

        def do_POST(self):
            path = self.path.split("?", 1)[0]
            if path not in CHAT and path not in LISTING_POST:
                return self.refuse(403, f"endpoint not allowed: POST {path}")
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return self.refuse(400, "bad Content-Length")
            if n <= 0 or n > MAX_BODY:
                return self.refuse(413 if n > MAX_BODY else 400, "missing or oversized body")
            raw = self.rfile.read(n)
            if path in LISTING_POST:
                return self.forward("POST", path, raw)
            try:
                body = json.loads(raw)
            except ValueError:
                return self.refuse(400, "body is not JSON")
            if not isinstance(body, dict):
                return self.refuse(400, "body is not a JSON object")
            if body.get("model") != cfg.tag:
                return self.refuse(403, f"model not under test: {str(body.get('model'))[:80]!r}")
            task = bool(body.get("tools"))
            pins = apply_pins(path, body, cfg, task)
            rec = {"ts": time.time(), "endpoint": path, "model": cfg.tag, "call": "task" if task else "aux",
                   "think_sent": pins["sent"]["think"], "think_applied": pins["applied"]["think"],
                   "temperature_sent": pins["sent"]["temperature"],
                   "temperature_applied": pins["applied"]["temperature"],
                   "stream": bool(body.get("stream", path == "/api/chat")),
                   "system_hash": system_hash(body), "messages": len(body.get("messages") or []),
                   "roles": sorted({m.get("role") for m in body.get("messages") or [] if isinstance(m, dict)} - {None})}
            self.forward("POST", path, json.dumps(body).encode(), rec, body)

        def forward(self, method, path, data, rec=None, req_body=None):
            t0 = time.time()
            conn = http.client.HTTPConnection(*cfg.upstream, timeout=UPSTREAM_TIMEOUT)
            try:
                headers = {"Content-Type": "application/json"} if data is not None else {}
                conn.request(method, path, body=data, headers=headers)
                resp = conn.getresponse()
            except OSError as e:
                conn.close()
                if rec is not None:
                    cfg.write(dict(rec, status=502, error=f"upstream: {e}"[:300], wall_s=round(time.time() - t0, 3)))
                body = json.dumps({"error": f"harness-bench proxy: upstream unreachable: {e}"}).encode()
                self.send_response(502)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            tally = Tally(path == "/v1/chat/completions") if rec is not None else None
            streaming = rec is not None and rec["stream"]
            logged = False

            def log_once(error=None):
                # Written before the response's last byte, so a harness that exits on the
                # answer never leaves the runner reading a log that lacks this request.
                nonlocal logged
                if rec is None or logged:
                    return
                logged = True
                calls, bad = tally.tool_counts()
                out = dict(rec, status=resp.status, wall_s=round(time.time() - t0, 3),
                           prompt_tokens=tally.prompt, output_tokens=tally.output,
                           tool_calls=calls, malformed_tool_calls=bad)
                if error or tally.error:
                    out["error"] = error or tally.error
                cfg.write(out)
                if cfg.exchanges is not None and req_body is not None:
                    # The full request as forwarded and the assembled answer: a harness-
                    # independent trajectory, one line per model call.
                    cfg.write({"ts": rec["ts"], "endpoint": path, "call": rec["call"], "request": req_body,
                               "response": tally.response(), "status": out["status"]}, cfg.exchanges)

            try:
                self.send_response(resp.status)
                self.send_header("Content-Type", resp.getheader("Content-Type") or "application/json")
                if streaming:
                    self.send_header("Transfer-Encoding", "chunked")
                    self.end_headers()
                    while True:
                        chunk = resp.read1(READ) if hasattr(resp, "read1") else resp.read(READ)
                        if not chunk:
                            break
                        tally.feed(chunk)
                        self.wfile.write(b"%x\r\n%s\r\n" % (len(chunk), chunk))
                        self.wfile.flush()
                    tally.finish()
                    log_once()
                    self.wfile.write(b"0\r\n\r\n")
                else:
                    payload = resp.read()
                    if tally is not None:
                        tally.whole(payload)
                    log_once()
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError) as e:
                log_once(f"client went away: {e}"[:300])
            finally:
                conn.close()
                log_once()

    return Handler


def serve(cfg: Config, port_file: Path) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cfg))
    server.daemon_threads = True
    tmp = port_file.with_name(port_file.name + ".tmp")
    tmp.write_text(str(server.server_address[1]), encoding="utf-8")
    os.replace(tmp, port_file)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--tag", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--port-file", required=True)
    ap.add_argument("--think")
    ap.add_argument("--temperature", type=float)
    ap.add_argument("--upstream", default="127.0.0.1:11434")
    ap.add_argument("--exchanges", help="also append each chat request and its assembled response here")
    a = ap.parse_args(argv)
    try:
        upstream = parse_upstream(a.upstream)
    except ValueError as e:
        print(f"bench_proxy: {e}", file=sys.stderr)
        return 2
    serve(Config(a.tag, a.log, a.think, a.temperature, upstream, a.exchanges), Path(a.port_file))
    return 0


if __name__ == "__main__":
    sys.exit(main())
