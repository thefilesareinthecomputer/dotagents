#!/usr/bin/env python3
"""Tests for the claude_mem_last_session.py SessionEnd hook and its --drain mode.
Target: the repo's hooks/claude_mem_last_session.py by default; HOOK_UNDER_TEST points the
run at a station copy such as ~/.claude/hooks/claude_mem_last_session.py.
Run: python3 tests/station-hooks/test-claude-mem-last-session.py   (or via unittest discover)

Contract: when the last Claude Code session ends, start a capped drain that asks the
claude-mem worker to shut down once its queue is idle. Do nothing when another session is
open, when the ending session is the worker's own summarizer, when the session carries on
(clear, resume), when claude-mem is not installed or its worker is down, or when the event
is not SessionEnd. The drain stops early when a session starts, gives up at its limit
while the worker is busy, and never signals a process itself. Fails open.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

TARGET = Path(os.environ.get("HOOK_UNDER_TEST")
              or Path(__file__).resolve().parents[2] / "hooks" / "claude_mem_last_session.py")
WORKER = 5000
ENDING = 6000
HOOK_PARENT = 6001          # the shell the harness runs the hook under

# pid ppid comm: the worker, its summarizer session, and the session that is ending.
BASE_LISTING = f"""\
    1     0 /sbin/launchd
 {WORKER}     1 /Users/u/.bun/bin/bun
 5001  {WORKER} /Users/u/.local/bin/claude
  700     1 /System/Applications/Utilities/Terminal.app/Contents/MacOS/Terminal
  701   700 /bin/zsh
 {ENDING}   701 /Users/u/.local/share/claude/versions/2.1.310
 {HOOK_PARENT}  {ENDING} /bin/sh
"""
OTHER_SESSION = " 7000   701 /Users/u/.local/bin/claude\n"


class FakeWorker:
    """A loopback stand-in for the worker's three routes."""

    def __init__(self, busy_polls: int = 0):
        self.busy_polls = busy_polls
        self.token = ""             # when set, every route but health needs X-Claude-Mem-Token
        self.status_calls = 0
        self.shutdowns = 0
        self.stopped = False
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, code: int, body: dict):
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def refused(self) -> bool:
                if outer.token and self.path != "/api/health" and \
                        self.headers.get("X-Claude-Mem-Token") != outer.token:
                    self.reply(401, {"error": "token required"})
                    return True
                return False

            def do_GET(self):
                if self.refused():
                    return
                if outer.stopped:
                    self.reply(503, {"status": "stopping"})
                elif self.path == "/api/health":
                    self.reply(200, {"status": "ok", "pid": WORKER})
                elif self.path == "/api/processing-status":
                    outer.status_calls += 1
                    busy = outer.status_calls <= outer.busy_polls
                    self.reply(200, {"isProcessing": busy, "queueDepth": 2 if busy else 0,
                                     "parkedSessions": 0})
                else:
                    self.reply(404, {})

            def do_POST(self):
                if self.refused():
                    return
                if self.path.startswith("/api/admin/shutdown"):
                    outer.shutdowns += 1
                    outer.stopped = True
                    self.reply(200, {"status": "shutting_down"})
                else:
                    self.reply(404, {})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.home = self.dir / "claude-mem"
        self.home.mkdir()
        (self.home / "settings.json").write_text("{}")
        self.ps = self.dir / "ps.txt"
        self.ps.write_text(BASE_LISTING)
        self.log = self.dir / "hook.log"
        self.worker = FakeWorker()
        self.addCleanup(self.worker.close)
        self.addCleanup(self.tmp.cleanup)

    def env(self, timing: str = "0,0.05,2,2", **extra) -> dict:
        env = dict(os.environ)
        env.update({"CLAUDE_MEM_LAST_HOME": str(self.home), "CLAUDE_MEM_LAST_BASE": self.worker.base,
                    "CLAUDE_MEM_LAST_PS": str(self.ps), "CLAUDE_MEM_LAST_PARENT": str(HOOK_PARENT),
                    "CLAUDE_MEM_LAST_TIMING": timing, "CLAUDE_MEM_LAST_LOG": str(self.log)})
        env.update(extra)
        return env

    def run_hook(self, payload, **env) -> subprocess.CompletedProcess:
        text = payload if isinstance(payload, str) else json.dumps(payload)
        return subprocess.run([sys.executable, str(TARGET)], input=text, capture_output=True,
                              text=True, timeout=20, env=self.env(**env))

    def run_drain(self, timing: str = "0,0.05,2,2") -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(TARGET), "--drain", "--ended", str(ENDING)],
                              capture_output=True, text=True, timeout=30, env=self.env(timing))

    def logged(self) -> str:
        return self.log.read_text() if self.log.exists() else ""

    def wait_for(self, predicate, seconds: float = 15.0) -> bool:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if predicate():
                return True
            time.sleep(0.05)
        return False


END = {"hook_event_name": "SessionEnd", "reason": "prompt_input_exit", "session_id": "s"}


class HookMode(Case):
    def test_last_session_starts_drain_and_worker_stops(self):
        """End to end: the real detached drain under procguard reaches the shutdown route."""
        proc = self.run_hook(END)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, "")
        self.assertIn("draining worker", self.logged())
        self.assertTrue(self.wait_for(lambda: self.worker.shutdowns == 1), self.logged())
        self.assertTrue(self.wait_for(lambda: "stopped after its queue drained" in self.logged()),
                        self.logged())

    def test_other_session_open_keeps_worker(self):
        self.ps.write_text(BASE_LISTING + OTHER_SESSION)
        self.assertEqual(self.run_hook(END).returncode, 0)
        self.assertIn("1 other session(s) still open", self.logged())
        time.sleep(0.5)
        self.assertEqual(self.worker.shutdowns, 0)

    def test_summarizer_session_ending_is_ignored(self):
        listing = BASE_LISTING + f" 5002  5001 /bin/sh\n"
        self.ps.write_text(listing)
        self.assertEqual(self.run_hook(END, CLAUDE_MEM_LAST_PARENT="5002").returncode, 0)
        self.assertEqual(self.logged(), "")

    def test_clear_and_resume_are_ignored(self):
        for reason in ("clear", "resume"):
            self.assertEqual(self.run_hook(dict(END, reason=reason)).returncode, 0)
        self.assertEqual(self.logged(), "")

    def test_other_events_and_bad_input_are_ignored(self):
        for payload in ({"hook_event_name": "Stop"}, "not json", "[]", ""):
            self.assertEqual(self.run_hook(payload).returncode, 0)
        self.assertEqual(self.logged(), "")

    def test_not_installed_is_silent(self):
        (self.home / "settings.json").unlink()
        self.assertEqual(self.run_hook(END).returncode, 0)
        self.assertEqual(self.logged(), "")

    def test_unreadable_process_list_keeps_worker(self):
        self.ps.write_text("")
        self.assertEqual(self.run_hook(END).returncode, 0)
        self.assertIn("could not read the session list", self.logged())
        time.sleep(0.5)
        self.assertEqual(self.worker.shutdowns, 0)

    def test_worker_down_is_silent(self):
        self.worker.close()
        proc = self.run_hook(END, CLAUDE_MEM_LAST_BASE="http://127.0.0.1:9")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(self.logged(), "")


class DrainMode(Case):
    def test_waits_for_queue_then_stops(self):
        self.worker.busy_polls = 3
        self.assertEqual(self.run_drain().returncode, 0)
        self.assertEqual(self.worker.shutdowns, 1)
        self.assertGreaterEqual(self.worker.status_calls, 5)   # 3 busy, then 2 idle in a row

    def test_new_session_cancels_drain(self):
        self.ps.write_text(BASE_LISTING + OTHER_SESSION)
        self.assertEqual(self.run_drain().returncode, 0)
        self.assertEqual(self.worker.shutdowns, 0)
        self.assertIn("a session started", self.logged())

    def test_busy_past_limit_leaves_worker(self):
        self.worker.busy_polls = 10 ** 6
        self.assertEqual(self.run_drain("0,0.05,0.5,2").returncode, 0)
        self.assertEqual(self.worker.shutdowns, 0)
        self.assertIn("leaving the worker to its idle exit", self.logged())

    def test_worker_gone_ends_drain(self):
        self.worker.stopped = True
        self.assertEqual(self.run_drain().returncode, 0)
        self.assertEqual(self.worker.shutdowns, 0)
        self.assertIn("worker already stopped", self.logged())

    def test_summarizer_sessions_do_not_hold_the_worker(self):
        self.assertEqual(self.run_drain().returncode, 0)
        self.assertEqual(self.worker.shutdowns, 1)

    def test_local_api_token_is_sent_and_never_logged(self):
        self.worker.token = "tok_xxxxxxxxxxxxxxxx"
        (self.home / "settings.json").write_text(json.dumps({"CLAUDE_MEM_LOCAL_API_TOKEN": self.worker.token}))
        self.assertEqual(self.run_drain().returncode, 0)
        self.assertEqual(self.worker.shutdowns, 1)
        self.assertNotIn(self.worker.token, self.logged())

    def test_missing_token_never_stops_a_guarded_worker(self):
        self.worker.token = "tok_xxxxxxxxxxxxxxxx"
        self.assertEqual(self.run_drain("0,0.05,0.5,2").returncode, 0)
        self.assertEqual(self.worker.shutdowns, 0)
        self.assertIn("leaving the worker to its idle exit", self.logged())


if __name__ == "__main__":
    unittest.main(verbosity=2)
