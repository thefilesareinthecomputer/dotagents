#!/usr/bin/env python3
"""SessionEnd hook: stop claude-mem's worker once the last Claude Code session has closed.

claude-mem's hooks start a shared worker daemon that no session owns, so nothing stops it
when the sessions end. It then sits inside the process coalition of whichever app started
the first session. When that app quits, macOS still counts the app as running, so a restart
or logout can retry its quit forever. This hook gives the worker an owner: the set of open
sessions. When the last one closes, the worker stops through claude-mem's own graceful
shutdown, once the session's final summary is written.

Hook mode (SessionEnd payload on stdin):
  - Reason "clear" or "resume": the session process carries on. Exit.
  - No claude-mem settings file: claude-mem is not installed. Exit.
  - The worker does not answer GET /api/health: it is already stopped. Exit.
  - The ending session is the first Claude Code process above this hook. A session the
    worker started itself (its summarizer) is one of the worker's descendants. Exit.
  - Another Claude Code session is still running, apart from the ending one and the
    worker's own: exit.
  - Otherwise start this script with --drain under procguard's --detached mode, which
    caps its life at DRAIN_LIMIT plus a margin, and exit without waiting.

Drain mode (--drain --ended PID):
  Waits SETTLE seconds, since claude-mem's own SessionEnd hook may still be queueing the
  session's summary. Then it polls every POLL seconds. Each poll stops the drain when the
  worker no longer answers, or when a Claude Code session has started since. The worker is
  idle when GET /api/processing-status reports an empty queue, nothing processing and no
  parked session. After IDLE_POLLS idle polls in a row, the drain sends POST
  /api/admin/shutdown, claude-mem's own graceful stop, and waits for the worker to go away.
  After DRAIN_LIMIT seconds it gives up. The worker is then left to CLAUDE_MEM_IDLE_EXIT_SEC,
  claude-mem's own idle exit, which also covers sessions that ended without this event.

When claude-mem's CLAUDE_MEM_LOCAL_API_TOKEN is set in its settings file, every request
carries it in the X-Claude-Mem-Token header; the hook never prints or logs it.

It never signals a process; the worker stops itself on request. Each decision is one line
in <temp>/claude-mem-last-session-<uid>.log. Fails open: exit 0 on every path.

Environment overrides (tests):
  CLAUDE_MEM_LAST_HOME    claude-mem data dir (default $CLAUDE_MEM_DATA_DIR, then ~/.claude-mem)
  CLAUDE_MEM_LAST_BASE    worker base URL (default http://127.0.0.1:<port from settings>)
  CLAUDE_MEM_LAST_PS      file holding a `ps -o pid=,ppid=,comm=` listing to use instead of ps
  CLAUDE_MEM_LAST_PARENT  pid to start the search for the ending session (default: this hook's parent)
  CLAUDE_MEM_LAST_TIMING  "settle,poll,limit,idle_polls" in seconds and polls
  CLAUDE_MEM_LAST_LOG     log file path
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

SETTLE, POLL, DRAIN_LIMIT, IDLE_POLLS = 15.0, 5.0, 300.0, 3
MARGIN = 60
LOG_CAP = 256 * 1024
# A Claude Code process: the `claude` launcher, or the versioned binary it execs (2.1.310).
SESSION = re.compile(r"^(claude|[0-9]+\.[0-9]+\.[0-9]+)$")
CONTINUING = {"clear", "resume"}


def log(message: str) -> None:
    path = Path(os.environ.get("CLAUDE_MEM_LAST_LOG")
                or Path(tempfile.gettempdir()) / f"claude-mem-last-session-{os.getuid()}.log")
    line = f"{datetime.now().isoformat(timespec='seconds')} [{os.getpid()}] {message}\n"
    try:
        if path.exists() and path.stat().st_size > LOG_CAP:
            path.replace(path.with_name(path.name + ".1"))
        # O_NOFOLLOW: in a shared temp folder a planted symlink must not redirect the append.
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            os.write(fd, line.encode("utf-8"))
        finally:
            os.close(fd)
    except OSError:
        pass


def timing() -> tuple[float, float, float, int]:
    raw = os.environ.get("CLAUDE_MEM_LAST_TIMING", "")
    try:
        settle, poll, limit, polls = raw.split(",")
        return float(settle), float(poll), float(limit), int(polls)
    except ValueError:
        return SETTLE, POLL, DRAIN_LIMIT, IDLE_POLLS


def data_dir() -> Path:
    return Path(os.environ.get("CLAUDE_MEM_LAST_HOME") or os.environ.get("CLAUDE_MEM_DATA_DIR")
                or Path.home() / ".claude-mem")


def base_url(settings: dict) -> str:
    if os.environ.get("CLAUDE_MEM_LAST_BASE"):
        return os.environ["CLAUDE_MEM_LAST_BASE"].rstrip("/")
    # claude-mem's own default port is 37700 plus the uid mod 100. The admin routes answer
    # loopback callers only, so the hook always connects to 127.0.0.1.
    port = 37700 + os.getuid() % 100
    try:
        configured = int(str(settings.get("CLAUDE_MEM_WORKER_PORT") or port))
        port = configured if 1 <= configured <= 65535 else port
    except ValueError:
        pass
    return f"http://127.0.0.1:{port}"


TOKEN = ""
# No proxy: the worker is local, and a proxy env var must never route a request, or the token.
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def use_token(settings: dict) -> None:
    """claude-mem's optional local API token (CLAUDE_MEM_LOCAL_API_TOKEN): once set, every
    route but /api/health refuses a request that does not carry it."""
    global TOKEN
    value = settings.get("CLAUDE_MEM_LOCAL_API_TOKEN")
    TOKEN = value.strip() if isinstance(value, str) else ""


def request(url: str, method: str = "GET", timeout: float = 3.0):
    """The parsed JSON body, or None when the worker does not answer or answers an error."""
    headers = {"X-Claude-Mem-Token": TOKEN} if TOKEN else {}
    req = urllib.request.Request(url, data=b"" if method == "POST" else None, method=method,
                                 headers=headers)
    try:
        with OPENER.open(req, timeout=timeout) as resp:
            body = resp.read(65536)
        value = json.loads(body or b"{}")
        return value if isinstance(value, dict) else None
    except (OSError, ValueError, urllib.error.URLError):
        return None


def processes() -> dict[int, tuple[int, str]]:
    """pid -> (ppid, executable basename) for the user's processes."""
    fake = os.environ.get("CLAUDE_MEM_LAST_PS")
    if fake:
        text = Path(fake).read_text(encoding="utf-8")
    else:
        text = subprocess.run(["ps", "-U", str(os.getuid()), "-o", "pid=,ppid=,comm="],
                              capture_output=True, text=True, timeout=5).stdout
    table = {}
    for line in text.splitlines():
        parts = line.split(None, 2)
        if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
            table[int(parts[0])] = (int(parts[1]), os.path.basename(parts[2].strip()))
    return table


def is_session(table: dict, pid: int) -> bool:
    return pid in table and bool(SESSION.match(table[pid][1]))


def ancestors(table: dict, pid: int) -> list[int]:
    chain, seen = [], set()
    while pid in table and pid not in seen and pid > 1:
        seen.add(pid)
        pid = table[pid][0]
        chain.append(pid)
    return chain


def ending_session(table: dict, start: int):
    for pid in [start] + ancestors(table, start):
        if is_session(table, pid):
            return pid
    return None


def other_sessions(table: dict, worker: int | None, exclude: set) -> list[int]:
    """Running sessions that keep the worker in use: not excluded and not the worker's own."""
    return [pid for pid in table
            if is_session(table, pid) and pid not in exclude
            and not (worker and worker in ancestors(table, pid))]


def worker_pid(health: dict):
    pid = health.get("pid")
    return pid if isinstance(pid, int) and pid > 1 else None


def start_drain(ended: int | None) -> bool:
    guard = Path(__file__).with_name("procguard.py")
    if not guard.exists():
        log("procguard.py missing beside the hook; leaving the worker to its idle exit")
        return False
    settle, poll, limit, _ = timing()
    argv = [sys.executable, "-I", str(guard), "--detached", "--timeout", str(int(settle + limit + MARGIN)),
            "--", sys.executable, "-I", str(Path(__file__).resolve()), "--drain", "--ended", str(ended or 0)]
    # procguard: exempt - the watchdog itself is started here; it leads its own group and caps the drain
    subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)
    return True


def hook() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(payload, dict) or payload.get("hook_event_name") != "SessionEnd":
        return 0
    if payload.get("reason") in CONTINUING:
        return 0
    settings_file = data_dir() / "settings.json"
    if not settings_file.is_file():
        return 0
    try:
        settings = json.loads(settings_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        settings = {}
    settings = settings if isinstance(settings, dict) else {}
    use_token(settings)
    base = base_url(settings)
    health = request(f"{base}/api/health", timeout=2)
    if health is None:
        return 0
    worker = worker_pid(health)
    table = processes()
    ended = ending_session(table, int(os.environ.get("CLAUDE_MEM_LAST_PARENT") or os.getppid()))
    if not table or ended is None:
        # Without a process list, or without finding the ending session in it, "no other
        # session open" cannot be shown, so the worker stays; its idle exit still applies.
        log("could not read the session list; worker stays")
        return 0
    if ended and worker and worker in ancestors(table, ended):
        return 0
    others = other_sessions(table, worker, {ended} if ended else set())
    if others:
        log(f"session {ended} ended; {len(others)} other session(s) still open, worker stays")
        return 0
    if start_drain(ended):
        log(f"session {ended} ended; no other session open, draining worker {worker}")
    return 0


def drain(ended: int) -> int:
    settle, poll, limit, needed = timing()
    settings = {}
    try:
        settings = json.loads((data_dir() / "settings.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    settings = settings if isinstance(settings, dict) else {}
    use_token(settings)
    base = base_url(settings)
    time.sleep(settle)
    deadline = time.monotonic() + limit
    streak = 0
    while time.monotonic() < deadline:
        health = request(f"{base}/api/health", timeout=2)
        if health is None:
            log("drain: worker already stopped")
            return 0
        worker = worker_pid(health)
        table = processes()
        if not table:
            log("drain: could not read the session list; worker stays")
            return 0
        others = other_sessions(table, worker, {ended})
        if others:
            log(f"drain: a session started ({others[0]}), worker stays")
            return 0
        status = request(f"{base}/api/processing-status", timeout=3)
        idle = (status is not None and status.get("queueDepth") == 0
                and status.get("isProcessing") is False and not status.get("parkedSessions"))
        streak = streak + 1 if idle else 0
        if streak >= needed:
            request(f"{base}/api/admin/shutdown", method="POST", timeout=5)
            for _ in range(int(20 / max(poll, 0.5)) + 1):
                if request(f"{base}/api/health", timeout=2) is None:
                    log(f"drain: worker {worker} stopped after its queue drained")
                    return 0
                time.sleep(min(poll, 1.0))
            log(f"drain: worker {worker} still answering after shutdown request; idle exit will retry")
            return 0
        time.sleep(poll)
    log(f"drain: still busy after {int(limit)}s; leaving the worker to its idle exit")
    return 0


def main(argv: list[str]) -> int:
    try:
        if argv[:1] == ["--drain"]:
            ended = int(argv[argv.index("--ended") + 1]) if "--ended" in argv else 0
            return drain(ended)
        return hook()
    except Exception as exc:  # fail open: a broken hook must never block a session from closing
        log(f"error: {type(exc).__name__}: {exc}")
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
