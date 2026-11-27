#!/usr/bin/env python3
"""SessionStart hook: tell the user when claude-mem's worker or its semantic search is down.

claude-mem degrades quietly: when chroma-mcp fails to start, search falls back to
keyword matching and the only trace is a WARN line in the worker's own log, so a
breakage can sit unnoticed for days. This hook asks the worker directly at every
session start and resume and, when something is wrong, prints one line to the user
as a systemMessage and to the model as additionalContext. Healthy is silent.

Checks, against the host and port in claude-mem's settings.json:
  1. GET /api/health answers "ok". One retry after a short pause covers the worker
     that claude-mem's own SessionStart hook is still spawning.
  2. When CLAUDE_MEM_CHROMA_ENABLED is not "false" and the worker is past WARMUP_S:
     GET /api/chroma/status reports healthy. An explicit "unhealthy" is reported
     with the newest [CHROMA_MCP] warning from the newest log as the cause. No
     answer at all, with no such warning logged, means chroma-mcp is still making
     its first connection, and stays silent.
  3. The pydantic-cap uvx wrapper (bin/uvx in the data dir, seeded per
     SPEC-CLAUDE-CODE.md §3.1): reported when anything else sits in its folder,
     which the worker puts first on PATH; when it is not executable, since PATH
     lookup then skips it silently, and, while search is healthy, when the worker's
     version no longer matches the wrapper's "# cap-for: claude-mem X" line - the
     cue to re-test without the cap.
No claude-mem settings file means claude-mem is not installed here: exit 0 silently.
Exit 0 on every path.

Environment overrides (tests):
  CLAUDE_MEM_HEALTH_HOME   claude-mem data dir (default $CLAUDE_MEM_DATA_DIR, then ~/.claude-mem)
  CLAUDE_MEM_HEALTH_BASE   worker base URL (default from settings)
  CLAUDE_MEM_HEALTH_RETRY  seconds before the single health retry (default 3)
"""

import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

HOME = Path(os.environ.get("CLAUDE_MEM_HEALTH_HOME") or os.environ.get("CLAUDE_MEM_DATA_DIR")
            or Path.home() / ".claude-mem")
WARMUP_S = 120
STALL_S = 6 * 3600  # queued work with nothing stored for this long is a stalled observer
CHROMA_WARN = re.compile(r"\[(WARN |ERROR)\] \[CHROMA_MCP")


# No proxy: the worker is local, and a proxy env var must not route this request.
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


TOKEN = ""  # claude-mem's CLAUDE_MEM_LOCAL_API_TOKEN, when set: every route but /api/health needs it


def get_json(url: str, timeout: float):
    headers = {"X-Claude-Mem-Token": TOKEN} if TOKEN else {}
    try:
        with OPENER.open(urllib.request.Request(url, headers=headers), timeout=timeout) as r:
            doc = json.loads(r.read().decode("utf-8", "replace"))
    except Exception:
        return None
    return doc if isinstance(doc, dict) else None


def last_chroma_warning() -> str:
    """The newest [CHROMA_MCP] warning in the newest log. Log files are named by UTC
    date, so the local date is the wrong key for part of every day; mtime is not."""
    try:
        logs = sorted((HOME / "logs").glob("claude-mem-*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return ""
    for log in logs[:2]:
        try:
            lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in reversed(lines[-5000:]):
            if CHROMA_WARN.search(line):
                m = re.search(r"error=([^,}]+)", line)
                return (m.group(1) if m else line).strip()[:200]
    return ""


def wrapper_notes(version: str, chroma_healthy: bool) -> list[str]:
    w = HOME / "bin" / "uvx"
    if not w.is_file():
        return []
    try:
        extra = sorted(p.name for p in w.parent.iterdir() if p.name not in ("uvx", "uvx.seed-bak"))
    except OSError:
        extra = []
    if extra:
        # The worker puts this folder first on PATH for itself and every claude it
        # spawns, so any other executable here shadows a real command.
        return [f"{w.parent} holds {', '.join(extra[:5])} besides uvx. That folder is first on PATH for the "
                f"claude-mem worker and every claude it spawns; remove anything you did not put there."]
    if not os.access(w, os.X_OK):
        return [f"{w} is not executable, so PATH lookup skips it and the pydantic cap is not applied; chmod 755 it."]
    if not chroma_healthy:
        return []
    try:
        m = re.search(r"^# cap-for: claude-mem (\S+)", w.read_text(encoding="utf-8", errors="replace"), re.M)
    except OSError:
        return []
    if m and version and version != m.group(1):
        return [f"claude-mem is now {version}; the pydantic cap in {w} was set for {m.group(1)}. "
                f"Re-test without it: remove the wrapper and the CLAUDE_MEM_CHROMA_UVX_PATH env key, restart "
                f"the worker, check /api/chroma/status?deep=1, and update the seed in specs/claude-code/claude-mem/."]
    return []


def pipeline_notes(base: str, health: dict) -> list[str]:
    """claude-mem's capture pipeline can stall while /api/health stays "ok", so read its own
    stall signals from GET /api/processing-status: an authenticated route, which also proves the
    station's token is accepted. Silent on a worker younger than STALL_S or with no history."""
    status = get_json(f"{base}/api/processing-status", 3)
    if status is None:
        return ["claude-mem's worker answers health checks but refuses or drops its processing-status "
                "route, so capture may be failing unseen; the usual cause is a missing or changed "
                f"local API token. Check {HOME}/settings.json and {HOME}/logs."]
    notes = []
    abandoned = status.get("abandonedStallSessions") or []
    if abandoned:
        notes.append(f"claude-mem abandoned {len(abandoned)} stalled observer session(s); their queued "
                     f"observations are not being saved. Check {HOME}/logs.")
    expired = status.get("expiredObserverInputs") or 0
    if isinstance(expired, int) and expired > 0:
        notes.append(f"claude-mem dropped {expired} expired observer input(s) since the worker started; "
                     "capture is falling behind.")
    last = status.get("lastSuccessfulStoreAt")
    try:
        uptime = float(health.get("uptime") or 0)
    except (TypeError, ValueError):
        uptime = 0
    if isinstance(last, (int, float)) and last > 0 and uptime >= STALL_S:
        idle_h = (time.time() - last / 1000) / 3600
        if idle_h >= STALL_S / 3600 and (status.get("queueDepth") or status.get("isProcessing")):
            notes.append(f"claude-mem has stored nothing for {idle_h:.0f}h while work is queued; its "
                         f"observer is stalled. Check {HOME}/logs.")
    return notes


def emit(lines: list[str]) -> None:
    if not lines:
        return
    text = "".join(ch for ch in " ".join(lines) if ch.isprintable())[:600]
    print(json.dumps({"systemMessage": text, "suppressOutput": True,
                      "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}))


def main() -> int:
    try:
        settings = json.loads((HOME / "settings.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    if not isinstance(settings, dict):
        return 0
    global TOKEN
    host = settings.get("CLAUDE_MEM_WORKER_HOST") or "127.0.0.1"
    token = settings.get("CLAUDE_MEM_LOCAL_API_TOKEN")
    # The token travels over plain HTTP, so it goes to a loopback worker only.
    if isinstance(token, str) and host in ("127.0.0.1", "::1", "localhost"):
        TOKEN = token.strip()
    # claude-mem's own default port: 37700 plus the uid mod 100.
    port = settings.get("CLAUDE_MEM_WORKER_PORT") or str(37700 + os.getuid() % 100)
    base = (os.environ.get("CLAUDE_MEM_HEALTH_BASE") or f"http://{host}:{port}").rstrip("/")

    health = get_json(f"{base}/api/health", 2)
    if health is None:
        try:
            time.sleep(float(os.environ.get("CLAUDE_MEM_HEALTH_RETRY") or 3))
        except ValueError:
            time.sleep(3)
        health = get_json(f"{base}/api/health", 2)
    if health is None:
        emit([f"claude-mem worker is not answering at {base}: memory capture and search are down. "
              f"Check {HOME}/logs."])
        return 0
    if health.get("status") != "ok":
        emit([f"claude-mem worker at {base} reports status {health.get('status')!r}. Check {HOME}/logs."])
        return 0

    version = str(health.get("version") or "")
    # The station requires claude-mem's local API token (SPEC-CLAUDE-CODE.md §3.1): without it any
    # local process or browser page can call the worker. It is per machine, so no seed can set it.
    token_note = [] if TOKEN else [
        "claude-mem's local API token is not set, so any local process or browser page can call its "
        "worker. Set CLAUDE_MEM_LOCAL_API_TOKEN per SPEC-CLAUDE-CODE.md §3.1, then restart the worker."]
    token_note += pipeline_notes(base, health)
    chroma_on = str(settings.get("CLAUDE_MEM_CHROMA_ENABLED", "true")).lower() != "false"
    try:
        warm = float(health.get("uptime") or 0) >= WARMUP_S
    except (TypeError, ValueError):
        warm = True
    if not (chroma_on and warm):
        emit(token_note + wrapper_notes(version, False))
        return 0

    chroma = get_json(f"{base}/api/chroma/status", 4)
    healthy = chroma is not None and chroma.get("status") == "healthy"
    out = []
    if not healthy:
        cause = last_chroma_warning()
        if chroma is not None or cause:
            cause = cause or str(chroma.get("details") or "")[:200] or "no detail returned"
            out.append(f"claude-mem semantic search is down (chroma-mcp); worker log says: \"{cause}\". "
                       f"Search is falling back to keyword matching. Check {HOME}/logs.")
    emit(token_note + out + wrapper_notes(version, healthy))
    return 0


if __name__ == "__main__":
    sys.exit(main())
