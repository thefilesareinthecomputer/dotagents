#!/usr/bin/env python3
"""One reader for hook input across harnesses, plus the tables seed_hooks.py maps with.

A hook reads its event through `read_event()` and gets the same shape whatever
harness ran it: which harness, which event, the tool's class (shell, file-write,
file-read, search, agent, mcp, other), the command, the paths touched, the text
about to be written and the text it replaces. Fields a harness does not supply
come back empty rather than missing.

Verified readers, each against a capture in tests/fixtures/: claude-code
(2.1.280) and codex (0.162.1), both 2026-10-13. Codex differences that matter:
the shell tool is `Bash` with `command` as in Claude Code, but every edit is
`apply_patch` whose `tool_input.command` holds the whole patch text, so the
paths and the new text are parsed out of the patch; `tool_response` is a plain
string; the payload has `turn_id` and `model` and no `prompt_id`; and Codex
sets no environment variable of its own, so the harness is told apart by the
payload when the environment says nothing. Stdlib only, Python 3.10 or newer. A hook that loads this file through
importlib must register the module in sys.modules before exec_module, or the
dataclass below cannot resolve its annotations.
"""
import json
import os
import re
import sys
from dataclasses import dataclass, field

# Tool classes per harness: class -> the harness's tool names (regex alternatives
# as the harness matches them). The order inside a class is the order the
# expanded matcher is written in.
TOOL_CLASSES: dict[str, dict[str, list[str]]] = {
    "claude-code": {
        "shell": ["Bash"],
        "file-write": ["Write", "Edit", "MultiEdit", "NotebookEdit", "Update", "Create"],
        "file-read": ["Read"],
        "search": ["Grep", "Glob"],
        "agent": ["Agent", "Workflow"],
        "mcp": ["mcp__.*"],
    },
    # Captured 2026-10-13 (tests/fixtures/codex.json). Codex has no read or
    # search tool: reads go through the shell, so a read guard cannot see them.
    "codex": {
        "shell": ["Bash"],
        "file-write": ["apply_patch"],
        "mcp": ["mcp__.*"],
    },
}

CLASSES = ("shell", "file-write", "file-read", "search", "agent", "mcp")

# Events a binding may name per harness. Claude Code's list is its documented
# set (the home harness; the station wires four of them). Codex's list is the
# five that fired in the capture; its reference also names SessionEnd,
# PermissionRequest, PreCompact, PostCompact, SubagentStart, SubagentStop and
# Interrupt, which stay out until one is captured.
EVENTS: dict[str, list[str]] = {
    "claude-code": ["PreToolUse", "PostToolUse", "PermissionRequest", "UserPromptSubmit", "Stop",
                    "SubagentStart", "SubagentStop", "SessionStart", "SessionEnd", "PreCompact",
                    "Notification"],
    "codex": ["SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"],
}

# SessionStart sources a harness reports in `source`, as captured; a binding is
# written for the sources a harness is known to have and the rest is reported.
# Codex: only `startup` captured so far (exec); resume, clear and compact unknown.
SESSION_SOURCES: dict[str, list[str]] = {
    "claude-code": ["startup", "resume", "clear", "compact"],
    "codex": ["startup"],
}

# Where each harness keeps its hook scripts and its wiring (portable form).
HOOK_HOME: dict[str, str] = {"claude-code": "~/.claude/hooks", "codex": "~/.codex/hooks"}
WIRING: dict[str, tuple[str, str]] = {
    "claude-code": ("~/.claude/settings.json", "hooks"),
    "codex": ("~/.codex/hooks.json", "hooks"),
}

HARNESSES = tuple(TOOL_CLASSES)

_FILE_PATH_KEYS = ("file_path", "notebook_path", "path")


@dataclass
class Event:
    harness: str = "unknown"
    event: str = ""
    tool_name: str = ""
    tool_class: str = ""
    command: str = ""
    paths: list[str] = field(default_factory=list)
    new_text: str = ""
    old_text: str = ""
    cwd: str = ""
    session_id: str = ""
    source: str = ""
    raw: dict = field(default_factory=dict)


def detect_harness(environ: dict | None = None, payload: dict | None = None) -> str:
    """Which harness ran the hook. The payload decides first, because a Codex
    started from inside a Claude Code session inherits CLAUDECODE and the rest
    of that environment: Codex events have `turn_id` (or `model` with no
    `prompt_id` on SessionStart), Claude Code events have `prompt_id`. A
    HOOK_HARNESS variable, when a wiring sets one, overrides everything."""
    env = os.environ if environ is None else environ
    if env.get("HOOK_HARNESS") in HARNESSES:
        return env["HOOK_HARNESS"]
    p = payload or {}
    if "turn_id" in p:
        return "codex"
    if "prompt_id" in p:
        return "claude-code"
    if "model" in p:
        return "codex"
    if env.get("CLAUDECODE") or env.get("CLAUDE_PROJECT_DIR") or env.get("CLAUDE_CODE_SESSION_ID"):
        return "claude-code"
    if any(k.startswith("CODEX_") for k in env):
        return "codex"
    return "unknown"


_PATCH_FILE = re.compile(r"^\s*\*\*\* (Add File|Update File|Delete File|Move to):\s*(.+?)\s*$")


def parse_apply_patch(text: str) -> tuple[list[str], str, str]:
    """Paths, added text and removed text from a Codex apply_patch body. Lines
    split on newline only, as Codex splits them, so a U+2028 or form feed inside
    a path stays in the path; headers are trimmed, as Codex trims them (its own
    parser's trimming is inferred, not read)."""
    paths: list[str] = []
    new: list[str] = []
    old: list[str] = []
    for line in (text or "").split("\n"):
        line = line.rstrip("\r")
        m = _PATCH_FILE.match(line)
        if m:
            if m.group(2) not in paths:
                paths.append(m.group(2))
        elif line.startswith("*** ") or line.startswith("@@"):
            continue
        elif line.startswith("+"):
            new.append(line[1:])
        elif line.startswith("-"):
            old.append(line[1:])
    return paths, "\n".join(new), "\n".join(old)


def tool_class(harness: str, tool_name: str) -> str:
    """The class a tool name falls in for a harness, or 'other'."""
    table = TOOL_CLASSES.get(harness, {})
    for cls in CLASSES:
        for pat in table.get(cls, []):
            if re.fullmatch(pat, tool_name or ""):
                return cls
    return "other"


def expand_matcher(harness: str, classes: list[str]) -> tuple[str, list[str]]:
    """Expand matcher classes into the harness's regex union. Returns the
    matcher string and the classes the harness could not map."""
    table = TOOL_CLASSES.get(harness, {})
    names: list[str] = []
    unmapped: list[str] = []
    for cls in classes:
        alts = table.get(cls)
        if alts:
            names.extend(a for a in alts if a not in names)
        else:
            unmapped.append(cls)
    return "|".join(names), unmapped


def matcher_set(matcher: str | None) -> frozenset[str]:
    """A matcher compared as the set of its alternatives, since order is not behavior."""
    if not matcher:
        return frozenset()
    return frozenset(matcher.split("|"))


def _paths(ti: dict) -> list[str]:
    out: list[str] = []
    for k in _FILE_PATH_KEYS:
        v = ti.get(k)
        if isinstance(v, str) and v:
            out.append(v)
    for e in ti.get("edits") or []:
        if isinstance(e, dict) and isinstance(e.get("file_path"), str) and e["file_path"]:
            out.append(e["file_path"])
    return out


def _texts(ti: dict) -> tuple[str, str]:
    if isinstance(ti.get("content"), str):
        return ti["content"], ""
    edits = ti.get("edits")
    if isinstance(edits, list) and edits:
        new = "\n".join(e.get("new_string") or "" for e in edits if isinstance(e, dict))
        old = "\n".join(e.get("old_string") or "" for e in edits if isinstance(e, dict))
        return new, old
    return ti.get("new_string") or "", ti.get("old_string") or ""


def parse_event(payload: dict, harness: str | None = None, environ: dict | None = None) -> Event:
    """Normalize one hook payload. `harness` overrides environment detection."""
    h = harness or detect_harness(environ, payload)
    ev = Event(harness=h, raw=payload)
    ev.event = str(payload.get("hook_event_name") or "")
    ev.cwd = str(payload.get("cwd") or "")
    ev.session_id = str(payload.get("session_id") or "")
    ev.source = str(payload.get("source") or "")
    ev.tool_name = str(payload.get("tool_name") or "")
    ti = payload.get("tool_input")
    ti = ti if isinstance(ti, dict) else {}
    if ev.tool_name:
        ev.tool_class = tool_class(h, ev.tool_name)
    cmd = ti.get("command")
    if h == "codex" and ev.tool_name == "apply_patch":
        # The patch body travels in `command`; it is an edit, not a shell command.
        # Patch paths are relative to cwd, so they are resolved to absolute
        # paths like the ones Claude Code hands a guard.
        ev.paths, ev.new_text, ev.old_text = parse_apply_patch(cmd if isinstance(cmd, str) else "")
        ev.paths = [os.path.normpath(os.path.join(ev.cwd, p)) if ev.cwd else p for p in ev.paths]
    elif h in ("claude-code", "codex"):
        ev.command = cmd if isinstance(cmd, str) else ""
        ev.paths = _paths(ti)
        ev.new_text, ev.old_text = _texts(ti)
    return ev


def read_event(stream=None, harness: str | None = None) -> Event:
    """Read and normalize the payload on stdin. A payload that is not JSON gives
    an Event with only the harness set, so a hook can choose to allow or refuse."""
    raw = (stream or sys.stdin).read()
    try:
        payload = json.loads(raw)
    except (ValueError, TypeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    return parse_event(payload, harness)


if __name__ == "__main__":
    e = read_event()
    print(json.dumps({k: v for k, v in e.__dict__.items() if k != "raw"}, indent=1))
