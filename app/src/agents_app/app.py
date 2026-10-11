"""FastAPI factory and the `agents` / `agn` CLI.

`agents up` runs uvicorn detached and records pid + port under ~/.agents-app/
so `down`, a second `up`, and the bare status all read the same state.
"""

import argparse
import asyncio
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import (FileResponse, JSONResponse, PlainTextResponse,
                               StreamingResponse)
from fastapi.staticfiles import StaticFiles

from agents_app import chat, config, conversations, graph, kb

# src/agents_app/app.py -> repo root; valid while the project installs
# editable during development.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_UI_DIR = _REPO_ROOT / "ui"


_EFFORTS = ("low", "medium", "high", "xhigh", "max")


def model_well_formed(model: str) -> bool:
    """One validator for every surface that accepts a model name.

    A model string becomes an argv element next to `--model`, so a
    leading hyphen is the shape that could become a flag on some future
    CLI - codex's parser already rejects a dash-led value where the
    others silently accept it, so the difference is one upgrade away
    from mattering. Empty means "unset", which every caller allows.
    Security review 2026-08-29: the settings route validated this and
    the participants route did not.
    """
    if not model:
        return True
    if model.startswith("-"):
        return False
    return all(ch.isalnum() or ch in ".:_-" for ch in model)


_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


_LOOPBACK_PEERS = {"127.0.0.1", "::1"}


def host_is_loopback(host_header: str) -> bool:
    """True when the Host header names this machine's loopback. A page on
    another site cannot read a loopback response by cross-site request, but
    it can by DNS rebinding, where the browser sends its own domain as Host;
    refusing every other host closes that read. A scripted client can send
    any Host it likes, which is why the middleware checks the peer address
    as well: the API has no auth and can start agent processes, so even a
    bind moved off loopback by `AGENTS_APP_HOST` answers this machine only."""
    try:
        name = urllib.parse.urlsplit("//" + host_header.strip()).hostname
    except ValueError:
        return False
    return (name or "") in _LOOPBACK_HOSTS


def create_app() -> FastAPI:
    app = FastAPI(title="agents")

    @app.middleware("http")
    async def loopback_only(request, call_next):
        peer = request.client.host if request.client else ""
        if peer not in _LOOPBACK_PEERS or not host_is_loopback(request.headers.get("host") or ""):
            return JSONResponse({"detail": "this server answers loopback clients only"},
                                status_code=421)
        return await call_next(request)

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(_UI_DIR / "index.html")

    @app.get("/kb/tree")
    def kb_tree() -> dict:
        return kb.tree()

    @app.get("/kb/file/{path:path}")
    def kb_file(path: str) -> PlainTextResponse:
        try:
            return PlainTextResponse(kb.file_text(path))
        except PermissionError:
            raise HTTPException(status_code=403, detail="path escapes the vault")
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="no such file")

    @app.get("/kb/search")
    def kb_search(q: str, scope: str = "content") -> list[dict]:
        if scope not in ("content", "filename"):
            raise HTTPException(status_code=422, detail="scope must be content or filename")
        return kb.search(q, scope)

    @app.get("/kb/stats")
    def kb_stats() -> dict:
        return kb.stats()

    @app.post("/kb/reindex")
    def kb_reindex() -> dict:
        return kb.reindex()

    @app.get("/kb/graph/subgraph")
    def kb_subgraph(file: str | None = None, heading: str | None = None,
                    depth: int = 2, max_nodes: int = 60, max_edges: int = 120,
                    scope: str | None = None) -> dict:
        con = kb.fresh_connection()
        try:
            if file:
                seeds = graph.seed_sections(con, file, heading)
                return graph.subgraph(con, seeds, depth, max_nodes,
                                      max_edges, scope or "")
            return graph.overview(con, scope or "", max_nodes, max_edges)
        finally:
            con.close()

    @app.get("/conversations")
    def conversations_list(limit: int | None = None, offset: int = 0) -> JSONResponse:
        page, total = conversations.listing(limit, offset)
        return JSONResponse(page, headers={"X-Total-Count": str(total)})

    @app.post("/conversations")
    def conversations_create() -> dict:
        return {"id": conversations.create()["id"]}

    @app.get("/conversations/{conversation_id}")
    def conversations_read(conversation_id: str) -> dict:
        try:
            return conversations.read(conversation_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="no such conversation")

    @app.delete("/conversations/{conversation_id}")
    def conversations_delete(conversation_id: str) -> dict:
        try:
            conversations.delete(conversation_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="no such conversation")
        return {"status": "ok"}

    # --- group-chat seats (SPEC-GROUP-CHAT-V1 G1) ---

    @app.get("/seats")
    def seats_roster() -> dict:
        return {"seats": config.seats_roster()}

    @app.post("/conversations/{conversation_id}/participants")
    def participant_add(conversation_id: str, body: dict) -> dict:
        name = (body.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=422, detail="name required")
        cwd = (body.get("cwd") or "").strip() or str(_REPO_ROOT)
        if not config.seat_root_allowed(cwd):
            raise HTTPException(
                status_code=422,
                detail=f"{cwd} is outside the permitted seat roots; run "
                       "`agents config roots` to review or change them")
        effort = (body.get("effort") or "").strip()
        if effort and effort not in _EFFORTS:
            raise HTTPException(status_code=422,
                                detail=f"effort must be one of {_EFFORTS}")
        if not model_well_formed(body.get("model") or ""):
            raise HTTPException(status_code=422, detail="malformed model")
        try:
            return conversations.add_participant(
                conversation_id, name, cwd=cwd,
                harness=body.get("harness") or "claude",
                model=body.get("model") or "", effort=effort,
                readonly=body.get("readonly") is True)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="no such conversation")
        except ValueError as reserved:
            raise HTTPException(status_code=422, detail=str(reserved))

    @app.get("/conversations/{conversation_id}/participants/{seat_id}/policy")
    def participant_policy(conversation_id: str, seat_id: str) -> dict:
        """The effective-policy card (PLAN-SEAT-HARDENING-V1 P5): what a
        seat may do before it runs, from the spawner's own resolver.
        GET only; there is no endpoint that writes a grant."""
        from agents_app import chat
        try:
            thread = conversations.read(conversation_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="no such conversation")
        seat = next((s for s in thread.get("participants", [])
                     if s.get("id") == seat_id), None)
        if seat is None:
            raise HTTPException(status_code=404, detail="no such seat")
        try:
            return chat.seat_policy(seat)
        except chat.PermissionSourceError as broken:
            raise HTTPException(status_code=503, detail=str(broken))

    @app.post("/conversations/{conversation_id}/cancel")
    def round_cancel(conversation_id: str) -> dict:
        try:
            conversations.read(conversation_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="no such conversation")
        from agents_app import group
        return {"cancelled": group.request_cancel(conversation_id)}

    @app.delete("/conversations/{conversation_id}/participants/{seat_id}")
    def participant_remove(conversation_id: str, seat_id: str) -> dict:
        try:
            conversations.remove_participant(conversation_id, seat_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="no such conversation")
        except KeyError:
            raise HTTPException(status_code=404, detail="no such seat")
        return {"status": "ok"}

    @app.post("/chat")
    async def chat_stream(body: dict) -> StreamingResponse:
        message = (body.get("message") or "").strip()
        conversation_id = body.get("conversation_id") or ""
        if not message:
            raise HTTPException(status_code=422, detail="message is required")
        try:
            conversations.read(conversation_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="no such conversation")
        return StreamingResponse(chat.stream_chat(message, conversation_id),
                                 media_type="text/event-stream")

    @app.get("/agents")
    def agents() -> dict:
        from agents_app import registry
        return {"agents": registry.snapshot()}

    @app.get("/settings/claude")
    def claude_settings() -> dict:
        return {"model": config.claude_model(),
                "effort": config.claude_effort(),
                "efforts": list(_EFFORTS)}

    @app.post("/settings/claude")
    def claude_settings_set(body: dict) -> dict:
        model = (body.get("model") or "").strip()
        effort = (body.get("effort") or "").strip()
        if effort and effort not in _EFFORTS:
            raise HTTPException(status_code=422,
                                detail=f"effort must be one of {_EFFORTS}")
        if not model_well_formed(model):
            raise HTTPException(status_code=422, detail="malformed model")
        stored = config.load_file()
        if model:
            stored["claude_model"] = model
        if effort:
            stored["claude_effort"] = effort
        config.save_file(stored)
        return {"model": config.claude_model(),
                "effort": config.claude_effort()}

    @app.get("/models")
    def models() -> dict:
        available, current = chat.available_models()
        return {"models": available, "current": current}

    @app.post("/model")
    def model_switch(body: dict) -> dict:
        model = body.get("model") or ""
        conversation_id = body.get("conversation_id") or None
        try:
            chat.set_model(model, conversation_id)
        except ValueError:
            raise HTTPException(status_code=422, detail="unknown model")
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="no such conversation")
        return {"model": model, "conversation_id": conversation_id}

    @app.get("/sse")
    async def ambient_sse(token: str = "") -> StreamingResponse:
        # Ambient channel: any non-empty token accepted, ping keepalive
        # every 30s (spec HTTP API table). Chat streams ride POST /chat.
        if not token:
            raise HTTPException(status_code=422, detail="token is required")

        async def pings():
            while True:
                yield b"event: ping\ndata: {}\n\n"
                await asyncio.sleep(30)

        return StreamingResponse(pings(), media_type="text/event-stream")

    app.mount("/ui", StaticFiles(directory=_UI_DIR), name="ui")
    return app


# --- process lifecycle ---

def _pid_file() -> Path:
    return config.app_home() / "pid"


def _read_pid_file() -> tuple[int, int] | None:
    """Return (pid, port) or None when absent or unparseable."""
    try:
        lines = _pid_file().read_text().split()
        return int(lines[0]), int(lines[1])
    except (OSError, ValueError, IndexError):
        return None


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    return True


def _browse_host(host: str) -> str:
    return "127.0.0.1" if host == "0.0.0.0" else host


_FOCUS_TAB_SCRIPT = """
set res to "none"
if application "Google Chrome" is running then
  tell application "Google Chrome"
    repeat with w in windows
      set i to 0
      repeat with t in tabs of w
        set i to i + 1
        if URL of t starts with "%s" then
          set active tab index of w to i
          set index of w to 1
          activate
          set res to "focused"
          exit repeat
        end if
      end repeat
      if res is "focused" then exit repeat
    end repeat
  end tell
end if
res
"""


_FOCUS_SAFARI_SCRIPT = """
set res to "none"
if application "Safari" is running then
  tell application "Safari"
    repeat with w in windows
      repeat with t in tabs of w
        if URL of t starts with "%s" then
          set current tab of w to t
          set index of w to 1
          activate
          set res to "focused"
          exit repeat
        end if
      end repeat
      if res is "focused" then exit repeat
    end repeat
  end tell
end if
res
"""


def _open_browser(url: str) -> None:
    """Raise an already-open tab for url, else open a new one.

    Launch works in every browser (webbrowser.open hands the URL to the
    OS default). The focus-instead-of-duplicate trick needs a scriptable
    tab list, which on macOS Chrome and Safari expose and Firefox does
    not - so Chrome and Safari get focused, everything else gets a plain
    open. Never fatal - the server is already up.
    """
    if sys.platform == "darwin":
        for script in (_FOCUS_TAB_SCRIPT, _FOCUS_SAFARI_SCRIPT):
            try:
                done = subprocess.run(
                    ["osascript", "-e", script % url],
                    capture_output=True, text=True, timeout=5,
                )
                if done.stdout.strip() == "focused":
                    return
            except (OSError, subprocess.SubprocessError):
                pass
    webbrowser.open(url)


def _wait_for_port(host: str, port: int, timeout: float = 8.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def cmd_up(open_browser: bool = True) -> int:
    recorded = _read_pid_file()
    if recorded and _alive(recorded[0]):
        url = f"http://{_browse_host(config.host())}:{recorded[1]}"
        print(f"already running (pid {recorded[0]}) at {url}")
        if open_browser:
            _open_browser(url)
        return 0

    host, port = config.host(), config.port()
    home = config.app_home()
    home.mkdir(parents=True, exist_ok=True)
    log = (home / "server.log").open("a")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "agents_app.app:create_app",
         "--factory", "--host", host, "--port", str(port)],
        stdout=log, stderr=log, start_new_session=True,
    )
    _pid_file().write_text(f"{proc.pid}\n{port}\n")

    url = f"http://{_browse_host(host)}:{port}"
    if _wait_for_port(_browse_host(host), port):
        print(f"up (pid {proc.pid}) at {url}")
    else:
        print(f"started pid {proc.pid} but {url} is not answering yet; see {home / 'server.log'}")
    print(_backend_line())
    if open_browser:
        print("opening browser")
        _open_browser(url)
    return 0


def _signal_server(pid: int, sig: int) -> None:
    """Signal the server's whole process GROUP: `up` starts it with
    start_new_session, so pgid == pid and every CLI the lanes spawned
    (claude, cursor-agent, copilot) is in the group - `down` must never
    leave a headless agent running (user requirement 2026-08-27)."""
    try:
        os.killpg(pid, sig)
    except (ProcessLookupError, PermissionError):
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            pass


def cmd_down() -> int:
    recorded = _read_pid_file()
    if recorded is None:
        print("not running")
        return 0
    pid, _port = recorded
    if _alive(pid):
        _signal_server(pid, signal.SIGTERM)
        deadline = time.monotonic() + 5.0
        while _alive(pid) and time.monotonic() < deadline:
            time.sleep(0.1)
        if _alive(pid):
            _signal_server(pid, signal.SIGKILL)
        print(f"stopped (pid {pid} and its process group)")
    else:
        print("not running (stale pid file removed)")
    _pid_file().unlink(missing_ok=True)
    _release_local_models()
    return 0


def _release_local_models() -> None:
    """Session end for local models: unload any resident Ollama model this
    app plausibly loaded (the configured default and conversation pins) so
    `agents down` never strands gigabytes in memory. Models other apps
    loaded are left alone; everything here is best-effort and silent when
    the daemon is absent."""
    from agents_app import conversations, ollama
    try:
        resident = set(ollama.loaded())
        if not resident:
            return
        ours = {config.model_default()}
        try:
            threads, _ = conversations.listing()
            ours |= {thread.get("model") for thread in threads}
        except Exception:
            pass
        for model in sorted(resident & ours - {None, ""}):
            if ollama.unload(model):
                print(f"unloaded local model: {model}")
    except Exception:
        pass


_ENGINE = Path(__file__).resolve().parents[3] / "skills" / "obsidian-kg" / "scripts" / "obsidian_kg.py"


def cmd_build() -> int:
    vault = config.vault_path()
    if not vault.is_dir():
        print(f"agents build: vault path does not exist: {vault}", file=sys.stderr)
        return 1
    result = subprocess.run([sys.executable, str(_ENGINE), "ingest", str(vault)])
    if result.returncode == 0:
        missing = kb.parity(vault)
        if missing:
            print(f"WARNING: {len(missing)} note(s) on disk are NOT in the "
                  "graph - the enumeration cannot see them (gitignored "
                  "under git parity, or inside a nested repo):",
                  file=sys.stderr)
            for rel in missing[:20]:
                print(f"  {rel}", file=sys.stderr)
            if len(missing) > 20:
                print(f"  ... and {len(missing) - 20} more", file=sys.stderr)
    return result.returncode


def _ask(prompt: str, default: str) -> str:
    """Prompt with a default; non-interactive stdin accepts the default."""
    if not sys.stdin.isatty():
        return default
    shown = f" [{default}]" if default else ""
    try:
        answer = input(f"{prompt}{shown}: ").strip()
    except EOFError:
        return default
    return answer or default


def cmd_config() -> int:
    stored = config.load_file()
    print("agents setup (writes ~/.agents-app/config; env vars override per invocation)")
    values = {
        "name": _ask("What should the agent call you", stored.get("name", "")),
        "vault": _ask("Vault path", stored.get("vault", str(config.vault_path()))),
        "host": _ask("Host", stored.get("host", "127.0.0.1")),
        "port": _ask("Port", stored.get("port", "8765")),
        "model": _ask("Default model (blank = lane default)", stored.get("model", "")),
        "harness": _ask("Agent harness driving chat (claude | codex | opencode | "
                        "cursor | copilot | gemini | none)",
                        stored.get("harness", "claude")),
        "gitignored": _ask("Vault folders to gitignore (comma-separated)",
                           stored.get("gitignored", "_USER")),
        "agentignored": _ask("Vault folders agents must not read (comma-separated)",
                             stored.get("agentignored", "")),
        "claudeignored": _ask("Vault folders to claudeignore (comma-separated)",
                              stored.get("claudeignored", "")),
    }
    home = config.app_home()
    home.mkdir(parents=True, exist_ok=True)
    lines = ["# agents config; `agents config` rewrites this file"]
    lines += [f"{key} = {value}" for key, value in values.items()]
    config.config_file().write_text("\n".join(lines) + "\n")
    print(f"wrote {config.config_file()}")
    return 0


# `agents config get/set`: the non-interactive config surface, allowlisted
# for the chat agent so settings change conversationally (the wizard needs
# a TTY the agent never has). Effective values, not just stored ones, so
# `get` answers "what is it actually using" with env overrides applied.
_CONFIG_EFFECTIVE = {
    "name": config.preferred_name,
    "vault": lambda: str(config.vault_path()),
    "data": lambda: str(config.data_path()),
    "host": config.host,
    "port": lambda: str(config.port()),
    "model": config.model_default,
    "harness": config.harness,
    "claude_model": config.claude_model,
    "claude_effort": config.claude_effort,
    "ollama_url": config.ollama_url,
    "ollama_keep_alive": config.ollama_keep_alive,
    # readable, never settable: see cmd_config_roots
    "seat_roots": lambda: ", ".join(str(r) for r in config.seat_roots()),
    "gitignored": lambda: config.load_file().get("gitignored", ""),
    "agentignored": lambda: config.load_file().get("agentignored", ""),
    "claudeignored": lambda: config.load_file().get("claudeignored", ""),
}
_RESTART_KEYS = {"vault", "data", "host", "port"}
_HARNESS_CHOICES = {"claude", "codex", "opencode", "cursor", "copilot",
                    "gemini", "none"}


def cmd_config_roots(print_only: bool = False) -> int:
    """Show the seat roots and route the user to edit them.

    Read-and-route only: it never writes the value. An agent may run it
    to show the user exactly how to make the change, and still cannot
    make the change itself (security review 2026-08-29)."""
    stored = config.load_file().get("seat_roots", "")
    print("seat roots - directories where a group-chat seat may run:")
    for root in config.seat_roots():
        print(f"  {root}")
    if not stored:
        print("\n(derived from your roster; no `seat_roots` line set yet)")
    print(f"\nThis one setting is yours alone - `agents config set` cannot "
          f"touch it, because nothing that decides what an agent may do "
          f"should be writable by an agent.\n"
          f"\nEdit:  {config.config_file()}\n"
          f"Line:  seat_roots = " + ", ".join(
              str(root) for root in config.seat_roots()) +
          "\n       (comma-separated absolute paths; ~ is expanded)")
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
    if print_only or not editor:
        if not editor and not print_only:
            print("\nSet $EDITOR to have this open the file for you.")
        return 0
    config.app_home().mkdir(parents=True, exist_ok=True)
    if not config.config_file().exists():
        config.save_file(config.load_file())
    print(f"\nOpening in {editor}...")
    try:
        subprocess.run([editor, str(config.config_file())])
    except (OSError, subprocess.SubprocessError) as err:
        print(f"could not launch {editor}: {err}", file=sys.stderr)
        return 1
    return 0


def cmd_config_get(key: str | None) -> int:
    if key is not None and key not in _CONFIG_EFFECTIVE:
        print(f"agents config: unknown key: {key}", file=sys.stderr)
        print("keys: " + ", ".join(sorted(_CONFIG_EFFECTIVE)), file=sys.stderr)
        return 1
    if key is not None:
        print(_CONFIG_EFFECTIVE[key]())
        return 0
    for name in sorted(_CONFIG_EFFECTIVE):
        value = _CONFIG_EFFECTIVE[name]() or "(unset - lane default)"
        print(f"{name} = {value}")
    return 0


def _loopback_url(value: str) -> bool:
    host = (urllib.parse.urlparse(value).hostname or "").lower()
    return host in {"localhost", "127.0.0.1", "::1"}


def _refuse_inside_seat(command: str) -> bool:
    """The spawn env marks a seat's processes with AGENTS_APP_SEAT (chat._cli_env).
    The --disallowedTools prefix only sees a literal `agents seat ...`; a
    seat repo's broad shell grant reaches this entry point through a
    compound command or a subprocess that inherits the env, so the command
    refuses here too. It does not cover a shell that clears the variable
    first (`env -u AGENTS_APP_SEAT agents seat ...`): that is the P6 boundary,
    a shell grant is unscopeable. Seating and config changes take a user
    turn in the main lane."""
    seat = os.environ.get("AGENTS_APP_SEAT")
    if not seat:
        return False
    print(f"{command}: refused - this process runs inside seat {seat!r}; "
          "seating and config changes are made by the user in their own "
          "turn, never from a seat", file=sys.stderr)
    return True


def cmd_config_set(key: str | None, value: str | None) -> int:
    if _refuse_inside_seat("agents config set"):
        return 1
    if not key or value is None:
        print("usage: agents config set <key> <value>", file=sys.stderr)
        return 1
    if key == "seat_roots":
        print("agents config: seat_roots is not settable here - it bounds "
              "what agents may do, so only you change it. Run `agents config "
              "roots`.", file=sys.stderr)
        return 1
    if key not in _CONFIG_EFFECTIVE:
        print(f"agents config: unknown key: {key}", file=sys.stderr)
        print("keys: " + ", ".join(sorted(_CONFIG_EFFECTIVE)), file=sys.stderr)
        return 1
    if key == "model":
        return cmd_model(value)  # same validation and save as `agents model`
    if key == "port":
        try:
            int(value)
        except ValueError:
            print(f"agents config: port must be a number: {value}",
                  file=sys.stderr)
            return 1
    if key == "harness" and value not in _HARNESS_CHOICES:
        print("agents config: harness must be one of "
              + " | ".join(sorted(_HARNESS_CHOICES)), file=sys.stderr)
        return 1
    if key == "claude_effort" and value not in _EFFORTS:
        print("agents config: claude_effort must be one of "
              + " | ".join(_EFFORTS), file=sys.stderr)
        return 1
    if key == "ollama_url" and not _loopback_url(value):
        print("agents config: ollama_url must be loopback "
              "(localhost / 127.0.0.1 / ::1) - the app never talks to a "
              "remote Ollama", file=sys.stderr)
        return 1
    if key == "host" and value not in {"127.0.0.1", "localhost", "::1"}:
        # single-user local posture: markdown renders unsanitized and
        # there is no auth, so binding off loopback is a decision the
        # user makes deliberately in the config file or the environment,
        # never through an agent-reachable command (security review
        # 2026-08-29)
        print("agents config: host must be loopback (127.0.0.1 / localhost "
              "/ ::1). To bind elsewhere, edit ~/.agents-app/config directly or "
              "set AGENTS_APP_HOST - there is no auth on this server.",
              file=sys.stderr)
        return 1
    stored = config.load_file()
    stored[key] = value
    config.save_file(stored)
    print(f"{key} = {value}")
    if key in _RESTART_KEYS:
        print("restart to apply: agents down && agents up")
    return 0


def cmd_model(name: str | None) -> int:
    """`agents model` shows current + available; `agents model <name>` writes
    the default into ~/.agents-app/config (a set default also picks the lane).
    Lanes read config at call time, so a running server follows along."""
    from agents_app import chat
    models, current = chat.available_models()
    if not name:
        harness_by_entry = {entry["model_entry"]: (hname, entry["lane"])
                            for hname, entry in chat.HARNESSES.items()}
        built_lanes = {"claude_code", "cursor", "copilot"}
        print(f"current: {current}")
        for model in models:
            if model in harness_by_entry:
                hname, lane = harness_by_entry[model]
                if lane == "claude_code":
                    label = "claude CLI session"
                elif lane in built_lanes:
                    label = f"{hname} CLI (group seats only)"
                else:
                    label = f"{hname} CLI (driver pending)"
            else:
                if "embed" in model:
                    continue  # embedding models cannot chat
                label = "ollama"
            print(f"  {model:<28} {label}")
        print("set the default with: agents model <name>")
        return 0
    if name not in models:
        print(f"agents model: unknown model: {name}", file=sys.stderr)
        print("available: " + ", ".join(models), file=sys.stderr)
        return 1
    stored = config.load_file()
    stored["model"] = name
    config.save_file(stored)
    print(f"default model: {name}")
    return 0


_SEAT_USAGE = """usage: agents seat                     show the global roster
       agents seat add <name> <cwd> [harness] [model] [effort]
                                       seat an agent permanently
                                       (model/effort default to the seat
                                       lane: sonnet, low)
       agents seat remove <name>       drop a roster seat
       agents seat <conversation-id> <name> [cwd]
                                       invite a guest into one conversation"""


def cmd_seat(params: list[str]) -> int:
    """Group-chat seats (SPEC-GROUP-CHAT-V1 G1). The global roster in
    ~/.agents-app/seats.json is the seat home: `add`/`remove` write it directly
    and a roster seat is @-callable in any conversation. The guest form
    goes through the running server (which serializes the write against
    any streaming round) and touches one conversation only. Agents run
    these on user instruction; the allow rule is `Bash(agents seat:*)` - a
    plain word prefix, immune to the quoting/URL hazards a raw curl recipe
    hit in live testing."""
    if params and _refuse_inside_seat("agents seat"):
        return 1
    if not params:
        roster = config.seats_roster()
        if roster:
            for entry in roster:
                extras = " ".join(filter(None, [entry.get("harness"),
                                                entry.get("model"),
                                                entry.get("effort")]))
                print(f"  @{conversations.slug(entry['name'])}  "
                      f"{entry['name']}  {entry['cwd']}"
                      + (f"  ({extras})" if extras else ""))
        else:
            print("no seats in the roster")
        print(_SEAT_USAGE)
        return 0

    if params[0] == "add":
        if len(params) < 3:
            print(_SEAT_USAGE, file=sys.stderr)
            return 1
        name, cwd = params[1], params[2]
        if conversations.slug(name) in conversations.RESERVED_SPEAKERS:
            print(f"agents seat: {name!r} is a reserved speaker name",
                  file=sys.stderr)
            return 1
        path = Path(cwd).expanduser().resolve()
        if not path.is_dir():
            print(f"agents seat: no such directory: {path}", file=sys.stderr)
            return 1
        if not config.seat_root_allowed(path):
            print(f"agents seat: {path} is outside the permitted seat roots:",
                  file=sys.stderr)
            for root in config.seat_roots():
                print(f"  {root}", file=sys.stderr)
            print("A seat runs a real agent session in that directory, so "
                  "the roots are yours to set: run `agents config roots`.",
                  file=sys.stderr)
            return 1
        entry = {"name": name, "cwd": str(path)}
        if len(params) > 3 and params[3]:
            entry["harness"] = params[3]
        if len(params) > 4 and params[4]:
            if not model_well_formed(params[4]):
                print(f"agents seat: malformed model: {params[4]}",
                      file=sys.stderr)
                return 1
            entry["model"] = params[4]
        if len(params) > 5 and params[5]:
            if params[5] not in _EFFORTS:
                print(f"agents seat: effort must be one of {_EFFORTS}",
                      file=sys.stderr)
                return 1
            entry["effort"] = params[5]
        if len(params) > 6 and params[6]:
            if params[6] != "readonly":
                print("agents seat: the seventh word can only be 'readonly'",
                      file=sys.stderr)
                return 1
            entry["readonly"] = True
        roster = [e for e in config.seats_roster()
                  if e["name"].lower() != name.lower()]
        roster.append(entry)
        config.save_seats_roster(roster)
        print(f"seated {name} in {path} - call it with "
              f"@{conversations.slug(name)} in any conversation")
        return 0

    if params[0] == "remove":
        if len(params) < 2:
            print(_SEAT_USAGE, file=sys.stderr)
            return 1
        name = params[1]
        roster = config.seats_roster()
        kept = [e for e in roster if e["name"].lower() != name.lower()]
        if len(kept) == len(roster):
            print(f"agents seat: no roster seat named {name}", file=sys.stderr)
            return 1
        config.save_seats_roster(kept)
        print(f"removed {name} from the roster")
        return 0

    if len(params) < 2:
        print(_SEAT_USAGE, file=sys.stderr)
        return 1
    conversation_id, name = params[0], params[1]
    cwd = params[2] if len(params) > 2 else ""
    body = {"name": name, "cwd": cwd}
    if not cwd:
        # A bare roster name invites with its saved definition.
        match = next((e for e in config.seats_roster()
                      if e["name"].lower() == name.lower()
                      or conversations.slug(e["name"]) == name.lower()), None)
        if match:
            body = {"name": match["name"], "cwd": match["cwd"],
                    "harness": match.get("harness") or "claude",
                    "model": match.get("model") or "",
                    "effort": match.get("effort") or ""}
    url = (f"http://{_browse_host(config.host())}:{config.port()}"
           f"/conversations/{conversation_id}/participants")
    request = urllib.request.Request(
        url, method="POST",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            seat = json.loads(response.read())
    except urllib.error.HTTPError as err:
        print(f"agents seat: server refused ({err.code}): "
              f"{err.read().decode()[:200]}", file=sys.stderr)
        return 1
    except urllib.error.URLError:
        print("agents seat: server not running - `agents up` first",
              file=sys.stderr)
        return 1
    print(f"seated {seat['id']} ({seat['name']}) in {seat['cwd']}")
    return 0


def cmd_search(params: list[str]) -> int:
    """`agents search <query>` - query the vault knowledge graph through
    the running server (GET /kb/search). This is the chat agent's
    allowlisted retrieval path (`Bash(agents search:*)`, same word-prefix
    pattern as agents seat): search names the sections, the agent Reads
    the named files, and those Reads light the graph HUD."""
    if not params:
        print("usage: agents search <query>", file=sys.stderr)
        return 1
    query = " ".join(params)
    url = (f"http://{_browse_host(config.host())}:{config.port()}"
           "/kb/search?" + urllib.parse.urlencode({"q": query}))
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            hits = json.loads(response.read())
    except urllib.error.URLError:
        print("agents search: server not running - `agents up` first",
              file=sys.stderr)
        return 1
    if not hits:
        print("no hits")
        return 0
    for hit in hits:
        heading = f"  # {hit['heading']}" if hit.get("heading") else ""
        print(f"vault/{hit['path']}{heading}  (score {hit['score']})")
        if hit.get("snippet"):
            print(f"    {' '.join(hit['snippet'].split())[:160]}")
    return 0


def _server_url() -> str | None:
    """Base URL of the running server, or None when it is down."""
    recorded = _read_pid_file()
    if recorded and _alive(recorded[0]):
        return f"http://{_browse_host(config.host())}:{recorded[1]}"
    return None


def _style(text: str, code: str) -> str:
    """ANSI-wrap text for a TTY; plain everywhere else (pipes, NO_COLOR).
    Codes: 2 dim, 1 bold, 31 red, 36 cyan."""
    if sys.stdout.isatty() and not os.environ.get("NO_COLOR"):
        return f"\033[{code}m{text}\033[0m"
    return text


def _tool_summary(args: dict) -> str:
    """The one argument a human wants from a tool call: the command, the
    path, the query - never the raw JSON envelope."""
    for key in ("command", "file_path", "filename", "query", "pattern"):
        value = args.get(key)
        if isinstance(value, str) and value:
            return value if len(value) <= 100 else value[:100] + "..."
    for value in args.values():
        if isinstance(value, str) and value:
            return value if len(value) <= 100 else value[:100] + "..."
    return ""


def _render_sse(lines) -> None:
    """Print one turn's SSE frames as terminal output: token text inline
    in the default foreground (the content is the star), meta dimmed -
    speaker headers when attributed frames change speaker, one humanized
    line per tool call, heartbeats that carry news - errors in red.
    Everything else stays silent. Mirrors the wire contract of
    chat.sse(): token/thinking payloads are percent-encoded strings (the
    web UI decodeURIComponents them), error is plain text, the rest is
    JSON."""
    event = ""
    speaker = None
    for raw in lines:
        line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
        if line.startswith("event: "):
            event = line[len("event: "):]
            continue
        if not line.startswith("data: "):
            continue
        data = line[len("data: "):]
        if event in ("token", "thinking"):
            if event == "token":
                print(urllib.parse.unquote(data), end="", flush=True)
            continue
        try:
            payload = json.loads(data)
        except ValueError:
            payload = data
        if isinstance(payload, dict) and payload.get("speaker") and \
                payload["speaker"] != speaker:
            speaker = payload["speaker"]
            print("\n\n" + _style(f"[{speaker}]", "1;36"), flush=True)
        if event == "tool_call":
            tool = payload.get("tool", "?") if isinstance(payload, dict) \
                else str(payload)
            args = payload.get("args", {}) if isinstance(payload, dict) else {}
            line_out = f"[{tool}] {_tool_summary(args)}".rstrip()
            print("\n" + _style(line_out, "2"), flush=True)
        elif event == "heartbeat" and isinstance(payload, dict) and \
                payload.get("label"):
            label = payload["label"]
            # tool_call already narrates the tool; turn-start is visible
            # from the prompt itself - neither label carries news here
            if not label.startswith("Running ") and label != "Session ready":
                print("\n" + _style(f"[{label}]", "2"), flush=True)
        elif event == "error":
            print("\n" + _style(f"[error] {payload}", "31"), flush=True)
    print(flush=True)


def cmd_chat(conversation_id: str | None) -> int:
    """Terminal REPL over the same server, lanes, and conversation store
    as the web UI (POST /chat SSE). Starts the server if needed, without
    opening a browser; an optional argument resumes that conversation."""
    url = _server_url()
    if not url:
        code = cmd_up(open_browser=False)
        if code != 0:
            return code
        url = _server_url()
    if not url:
        print("agents chat: server did not come up; see "
              f"{config.app_home() / 'server.log'}", file=sys.stderr)
        return 1

    def post(path: str, payload: dict):
        req = urllib.request.Request(
            url + path, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"})
        return urllib.request.urlopen(req)

    if conversation_id:
        try:
            urllib.request.urlopen(f"{url}/conversations/{conversation_id}")
        except (urllib.error.URLError, OSError):
            print(f"agents chat: no such conversation: {conversation_id}",
                  file=sys.stderr)
            return 1
    else:
        with post("/conversations", {}) as resp:
            conversation_id = json.loads(resp.read())["id"]

    from agents_app import chat as chat_module
    lane = chat_module.pick_lane()
    if lane == "claude_code":
        lane_note = (f"claude session, model {config.claude_model()}, "
                     f"effort {config.claude_effort()} - bills your "
                     "subscription")
    else:
        lane_note = lane
    print(_style("agents chat", "1")
          + _style(f"   {lane_note}", "2"))
    print(_style(f"conversation {conversation_id} - Ctrl-D or /quit "
                 "leaves, Ctrl-C cancels a turn, same thread in the "
                 "web UI", "2"))
    prompt = "\n" + _style("you>", "1;36") + " "
    while True:
        try:
            message = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not message:
            continue
        if message in {"/quit", "/exit"}:
            break
        try:
            with post("/chat", {"message": message,
                                "conversation_id": conversation_id}) as resp:
                _render_sse(resp)
        except KeyboardInterrupt:
            try:
                post(f"/conversations/{conversation_id}/cancel", {}).close()
            except (urllib.error.URLError, OSError):
                pass
            print("\n" + _style("[turn cancelled]", "2"))
        except urllib.error.HTTPError as err:
            detail = err.read().decode("utf-8", errors="replace")[:200]
            print(_style(f"[error] HTTP {err.code}: {detail}", "31"),
                  file=sys.stderr)
        except (urllib.error.URLError, OSError) as err:
            print(_style(f"[error] {err}", "31"), file=sys.stderr)
    print(_style(f"conversation saved; reopen with `agents chat "
                 f"{conversation_id}` or in the web UI", "2"))
    return 0


def _first_run_check() -> None:
    """Any command with ~/.agents-app/config absent writes defaults and says so.

    No wizard at first contact: every setting has a working default, and
    all of them are changeable later (`agents config` runs the full wizard,
    `agents config set` changes one key, or ask the chat agent). Nine blind
    prompts before the app has even opened once was the wrong trade."""
    if not config.config_file().exists():
        config.save_file({
            "name": "",
            "vault": str(config.vault_path()),
            "host": "127.0.0.1",
            "port": "8765",
            "model": "",
            "harness": "claude",
            "gitignored": "_USER",
            "agentignored": "",
            "claudeignored": "",
        })
        print(f"first run: wrote defaults to {config.config_file()}")
        print("customize any time: `agents config` (wizard), "
              "`agents config set <key> <value>`, or just ask the chat agent")


def _backend_line() -> str:
    """One line naming the chat backend a message would use right now,
    or how to get one - so the gap surfaces before the first message,
    not inside it."""
    from agents_app import chat
    configured = config.harness()
    if configured in chat.HARNESSES and chat.harness_bin(configured):
        return f"chat backend: {configured} CLI"
    if chat.ollama_tags():
        return "chat backend: local Ollama"
    return ("chat backend: none found - install the configured harness "
            "CLI (claude by default) or pull an Ollama model")


def _status() -> None:
    vault = config.vault_path()
    vault_note = "" if vault.is_dir() else " (missing)"
    recorded = _read_pid_file()
    if recorded and _alive(recorded[0]):
        state = f"running (pid {recorded[0]}) at http://{_browse_host(config.host())}:{recorded[1]}"
    else:
        state = "not running"
    print("agents")
    print(f"  state: {state}")
    print(f"  {_backend_line()}")
    print(f"  vault: {vault}{vault_note}")
    print("  commands:")
    print("    agents up      launch the server and open the browser")
    print("    agents chat    chat with the agent in this terminal (`agents chat <id>` resumes)")
    print("    agents down    stop the running server")
    print("    agents build   rebuild the vault knowledge graph")
    print("    agents config  interactive setup, writes ~/.agents-app/config")
    print("    agents config get [key] / set <key> <value>   read or change one setting")
    print("    agents config roots   show and edit where seats may run (yours alone)")
    print("    agents model   show models; `agents model <name>` sets the default")
    print("    agents seat    show the seat roster; add/remove seats, invite guests")
    print("    agents search  query the vault knowledge graph (`agents search <query>`)")


def main() -> None:
    parser = argparse.ArgumentParser(prog="agents")
    parser.add_argument("cmd", nargs="?",
                        choices=["up", "down", "build", "config", "model",
                                 "seat", "search", "chat"])
    parser.add_argument("arg", nargs="?")
    parser.add_argument("extra", nargs="*")
    parser.add_argument("--print", dest="print_only", action="store_true",
                        help="`config roots`: show without opening an editor")
    args = parser.parse_args()

    if args.cmd == "config":
        if args.arg == "roots":
            raise SystemExit(cmd_config_roots(print_only=args.print_only))
        if args.arg == "get":
            raise SystemExit(cmd_config_get(
                args.extra[0] if args.extra else None))
        if args.arg == "set":
            key = args.extra[0] if args.extra else None
            value = (" ".join(args.extra[1:])
                     if len(args.extra) > 1 else None)
            raise SystemExit(cmd_config_set(key, value))
        raise SystemExit(cmd_config())
    _first_run_check()
    if args.cmd == "chat":
        raise SystemExit(cmd_chat(args.arg))
    if args.cmd == "up":
        raise SystemExit(cmd_up())
    if args.cmd == "down":
        raise SystemExit(cmd_down())
    if args.cmd == "build":
        raise SystemExit(cmd_build())
    if args.cmd == "model":
        raise SystemExit(cmd_model(args.arg))
    if args.cmd == "seat":
        params = ([args.arg] if args.arg else []) + args.extra
        raise SystemExit(cmd_seat(params))
    if args.cmd == "search":
        params = ([args.arg] if args.arg else []) + args.extra
        raise SystemExit(cmd_search(params))
    _status()
