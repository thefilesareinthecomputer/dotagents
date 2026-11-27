#!/usr/bin/env python3
"""Tests for the claude_mem_health.py SessionStart hook.
Target: the repo's hooks/claude_mem_health.py by default; HOOK_UNDER_TEST points the run
at a station copy such as ~/.claude/hooks/claude_mem_health.py (seeded per SPEC-CLAUDE-CODE.md §8).
Run: python3 tests/station-hooks/test-claude-mem-health.py   (or via unittest discover)

Contract: exit 0 on every path. Silent when claude-mem is absent or healthy; one
systemMessage plus additionalContext when the worker does not answer or is degraded,
when chroma reports anything but healthy past the warm-up, when the uvx wrapper is not
executable, when the worker's version has moved past the wrapper's cap-for line, when the
local API token is unset or refused, or when the capture pipeline reports abandoned or
expired work, or nothing stored for hours while work is queued. The token never appears.
"""

import contextlib
import http.server
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

TARGET = Path(os.environ.get("HOOK_UNDER_TEST") or Path(__file__).resolve().parents[2] / "hooks" / "claude_mem_health.py")
MCP_WARN = ("[2026-10-17 14:02:12.701] [WARN ] [CHROMA_MCP] Connection attempt failed; Chroma unavailable "
            "{error=chroma-mcp prewarm failed: chroma-mcp prewarm exited with code 1}\n")
SYNC_WARN = ("[2026-10-17 14:02:12.702] [WARN ] [CHROMA_SYNC] Prompt watermark bump skipped - write failed, "
             "row marked pending {promptId=4567, project=demo, written=0}\n")
OK_HEALTH = {"status": "ok", "uptime": 900, "version": "13.25.1"}


TOKEN = "tok_xxxxxxxxxxxxxxxx"
OK_STATUS = {"isProcessing": False, "queueDepth": 0, "parkedSessions": 0,
             "lastSuccessfulStoreAt": int(time.time() * 1000), "abandonedStallSessions": [],
             "expiredObserverInputs": 0}
DEFAULTS = {"/api/processing-status": OK_STATUS}


class Stub(http.server.BaseHTTPRequestHandler):
    routes: dict = {}
    delay: dict = {}
    token: str = TOKEN      # every route but /api/health needs it, as claude-mem's guard does

    def do_GET(self):
        path = self.path.split("?")[0]
        time.sleep(self.delay.get(path, 0))
        if path != "/api/health" and self.token and self.headers.get("X-Claude-Mem-Token") != self.token:
            self.send_response(401)
            self.end_headers()
            return
        body = self.routes[path] if path in self.routes else DEFAULTS.get(path)
        if body is None:
            self.send_response(404)
            self.end_headers()
            return
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


class TestClaudeMemHealth(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="cmh-test-"))
        (self.home / "settings.json").write_text(json.dumps({"CLAUDE_MEM_CHROMA_ENABLED": "true",
                                                             "CLAUDE_MEM_LOCAL_API_TOKEN": TOKEN}))
        Stub.routes, Stub.delay, Stub.token = {}, {}, TOKEN
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Stub)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def run_hook(self, base=None, env_home=True):
        env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_MEM_HEALTH_HOME", "CLAUDE_MEM_DATA_DIR")}
        env.update(CLAUDE_MEM_HEALTH_BASE=base or self.base, CLAUDE_MEM_HEALTH_RETRY="0")
        if env_home:
            env["CLAUDE_MEM_HEALTH_HOME"] = str(self.home)
        else:
            env["CLAUDE_MEM_DATA_DIR"] = str(self.home)
        return subprocess.run([sys.executable, str(TARGET)], input="{}", env=env, capture_output=True,
                              text=True, timeout=30)

    def message(self, r):
        self.assertEqual(r.returncode, 0, r.stderr)
        if not r.stdout.strip():
            return None
        out = json.loads(r.stdout)
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "SessionStart")
        self.assertEqual(out["systemMessage"], out["hookSpecificOutput"]["additionalContext"])
        return out["systemMessage"]

    def log(self, name, text, age=0):
        logs = self.home / "logs"
        logs.mkdir(exist_ok=True)
        p = logs / name
        p.write_text(text)
        t = time.time() - age
        os.utime(p, (t, t))

    def wrapper(self, cap="13.25.1", mode=0o755):
        b = self.home / "bin"
        b.mkdir(exist_ok=True)
        w = b / "uvx"
        w.write_text(f"#!/bin/sh\n# cap-for: claude-mem {cap}\nexec uvx \"$@\"\n")
        w.chmod(mode)

    def test_absent_claude_mem_is_silent(self):
        (self.home / "settings.json").unlink()
        self.assertIsNone(self.message(self.run_hook()))

    def test_healthy_is_silent(self):
        Stub.routes = {"/api/health": OK_HEALTH, "/api/chroma/status": {"status": "healthy", "connected": True}}
        self.wrapper()
        self.assertIsNone(self.message(self.run_hook()))

    def test_data_dir_env_is_honored(self):
        (self.home / "settings.json").unlink()
        self.assertIsNone(self.message(self.run_hook(env_home=False)))
        (self.home / "settings.json").write_text("{}")
        self.assertIn("not answering", self.message(self.run_hook(base="http://127.0.0.1:9", env_home=False)))

    def healthy(self, **status):
        Stub.routes = {"/api/health": OK_HEALTH, "/api/chroma/status": {"status": "healthy"},
                       "/api/processing-status": dict(OK_STATUS, **status)}
        self.wrapper()
        return self.message(self.run_hook())

    def test_missing_token_is_reported(self):
        (self.home / "settings.json").write_text(json.dumps({"CLAUDE_MEM_CHROMA_ENABLED": "true"}))
        Stub.token = ""
        self.assertIn("local API token is not set", self.healthy())

    def test_refused_token_is_reported_not_silent(self):
        Stub.token = "tok_yyyyyyyyyyyyyyyy"           # the worker holds a different token
        Stub.routes = {"/api/health": OK_HEALTH, "/api/chroma/status": {"status": "healthy"}}
        self.wrapper()
        msg = self.message(self.run_hook())
        self.assertIn("refuses or drops its processing-status", msg)

    def test_token_never_appears_in_output(self):
        Stub.token = "tok_yyyyyyyyyyyyyyyy"
        self.wrapper()
        r = self.run_hook()
        self.assertNotIn(TOKEN, r.stdout + r.stderr)

    def test_abandoned_sessions_are_reported(self):
        self.assertIn("abandoned 2 stalled", self.healthy(abandonedStallSessions=[{"id": 1}, {"id": 2}]))

    def test_expired_inputs_are_reported(self):
        self.assertIn("dropped 7 expired", self.healthy(expiredObserverInputs=7))

    def test_stalled_observer_with_queued_work_is_reported(self):
        old = int((time.time() - 8 * 3600) * 1000)
        Stub.routes = {}
        OK = dict(OK_HEALTH, uptime=9 * 3600)
        Stub.routes = {"/api/health": OK, "/api/chroma/status": {"status": "healthy"},
                       "/api/processing-status": dict(OK_STATUS, lastSuccessfulStoreAt=old, queueDepth=4)}
        self.wrapper()
        self.assertIn("stored nothing for 8h while work is queued", self.message(self.run_hook()))

    def test_idle_worker_with_nothing_queued_is_not_a_stall(self):
        old = int((time.time() - 8 * 3600) * 1000)
        Stub.routes = {"/api/health": dict(OK_HEALTH, uptime=9 * 3600), "/api/chroma/status": {"status": "healthy"},
                       "/api/processing-status": dict(OK_STATUS, lastSuccessfulStoreAt=old)}
        self.wrapper()
        self.assertIsNone(self.message(self.run_hook()))

    def test_worker_down_reports(self):
        self.assertIn("worker is not answering", self.message(self.run_hook(base="http://127.0.0.1:9")))

    def test_degraded_worker_is_named_as_such(self):
        Stub.routes = {"/api/health": {"status": "degraded", "uptime": 900}}
        msg = self.message(self.run_hook())
        self.assertIn("'degraded'", msg)
        self.assertNotIn("not answering", msg)

    def test_chroma_down_quotes_the_newest_log_and_mcp_lines_only(self):
        Stub.routes = {"/api/health": OK_HEALTH, "/api/chroma/status": {"status": "unhealthy", "connected": False}}
        # The worker names logs by UTC date: the newest file can carry tomorrow's local date.
        self.log("claude-mem-2026-10-16.log", "[WARN ] [CHROMA_MCP] stale {error=old cause}\n", age=3600)
        self.log("claude-mem-2026-10-17.log", MCP_WARN + SYNC_WARN)
        msg = self.message(self.run_hook())
        self.assertIn("semantic search is down", msg)
        self.assertIn("prewarm exited with code 1", msg)
        self.assertNotIn("watermark", msg)
        self.assertNotIn("old cause", msg)

    def test_chroma_no_answer_without_a_warning_is_still_starting(self):
        Stub.routes = {"/api/health": OK_HEALTH, "/api/chroma/status": {"status": "healthy"}}
        Stub.delay = {"/api/chroma/status": 6}
        self.assertIsNone(self.message(self.run_hook()))

    def test_chroma_no_answer_with_a_warning_reports(self):
        Stub.routes = {"/api/health": OK_HEALTH}
        self.log("claude-mem-2026-10-17.log", MCP_WARN)
        self.assertIn("prewarm exited with code 1", self.message(self.run_hook()))

    def test_chroma_skipped_during_warmup(self):
        Stub.routes = {"/api/health": {"status": "ok", "uptime": 5}, "/api/chroma/status": {"status": "unhealthy"}}
        self.assertIsNone(self.message(self.run_hook()))

    def test_chroma_disabled_is_not_checked(self):
        (self.home / "settings.json").write_text(json.dumps({"CLAUDE_MEM_CHROMA_ENABLED": "false",
                                                             "CLAUDE_MEM_LOCAL_API_TOKEN": TOKEN}))
        Stub.routes = {"/api/health": OK_HEALTH}
        self.assertIsNone(self.message(self.run_hook()))

    def test_non_executable_wrapper_reports(self):
        Stub.routes = {"/api/health": OK_HEALTH, "/api/chroma/status": {"status": "healthy"}}
        self.wrapper(mode=0o644)
        self.assertIn("not executable", self.message(self.run_hook()))

    def test_anything_else_in_the_wrapper_folder_reports(self):
        Stub.routes = {"/api/health": OK_HEALTH, "/api/chroma/status": {"status": "healthy"}}
        self.wrapper()
        (self.home / "bin" / "uvx.seed-bak").write_text("old\n")
        self.assertIsNone(self.message(self.run_hook()))
        (self.home / "bin" / "git").write_text("#!/bin/sh\n")
        self.assertIn("holds git besides uvx", self.message(self.run_hook()))

    def test_version_past_the_cap_says_to_retest(self):
        Stub.routes = {"/api/health": dict(OK_HEALTH, version="13.26.0"), "/api/chroma/status": {"status": "healthy"}}
        self.wrapper(cap="13.25.1")
        msg = self.message(self.run_hook())
        self.assertIn("now 13.26.0", msg)
        self.assertIn("set for 13.25.1", msg)

    def test_default_port_follows_the_uid(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("claude_mem_health", TARGET)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        (self.home / "settings.json").write_text("{}")
        mod.HOME, urls = self.home, []
        mod.get_json = lambda url, timeout: urls.append(url)
        saved = os.environ.pop("CLAUDE_MEM_HEALTH_BASE", None)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                mod.main()
        finally:
            if saved is not None:
                os.environ["CLAUDE_MEM_HEALTH_BASE"] = saved
        self.assertEqual(urls[0], f"http://127.0.0.1:{37700 + os.getuid() % 100}/api/health")


if __name__ == "__main__":
    unittest.main()
