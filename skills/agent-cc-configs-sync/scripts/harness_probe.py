#!/usr/bin/env python3
"""Probe the core harnesses on this station: installed version, config home,
whether the harness sees this repository's skills, and whether its remote
control, background daemon and telemetry switches are off.

Each row runs the harness's own version command and, where a listing exists
that needs no sign-in, looks for one of this repo's skills in it. Harnesses
with no such listing say so rather than guessing. The remote-control column is
read from config files and the process table alone. Config homes derive from
HOME. A missing binary is a row, never an error.

  python3 harness_probe.py            # text table
  python3 harness_probe.py --json     # one object per harness
  python3 harness_probe.py --skill code-kg

Stdlib only, and the script itself writes nothing. The version and listing
commands it runs belong to each harness and may contact the vendor or update
the binary (cursor-agent and agy self-update; agy moved from 1.3.3 to 1.3.5
between two probes on one evening), so a run is not offline.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

VERSION_RE = re.compile(r"\d+(?:\.\d+)+(?:-[0-9a-zA-Z]+)?")
SKILL_RE = re.compile(r"[a-z0-9][a-z0-9-]*")
TIMEOUT = 20


@dataclass(frozen=True)
class Row:
    harness: str
    binary: str
    config_home: str              # relative to HOME
    canary: str                   # "list", "symlink", "file" or "none"
    canary_arg: tuple[str, ...] = ()   # list: argv after the binary; symlink/file: a HOME-relative path


ROWS = (
    Row("claude-code", "claude", ".claude", "symlink", (".claude/skills/{skill}",)),
    Row("codex", "codex", ".codex", "none"),
    Row("cursor", "cursor-agent", ".cursor", "none"),
    Row("copilot", "copilot", ".copilot", "list", ("skill", "list")),
    Row("goose", "goose", ".config/goose", "list", ("skills", "list")),
    Row("pi", "pi", ".pi/agent", "none"),
    Row("antigravity", "agy", ".gemini/config", "file", (".gemini/config/skills.json",)),
)


def run(argv: list[str]) -> tuple[int | None, str, str]:
    """Return (exit code, stdout, stderr); None and empty strings when the
    command could not run or timed out."""
    try:
        p = subprocess.run(argv, text=True, capture_output=True, timeout=TIMEOUT, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return None, "", ""
    return p.returncode, p.stdout, p.stderr


def version_of(binary: str) -> str:
    exe = shutil.which(binary)
    if exe is None:
        return "not installed"
    _, out, err = run([exe, "--version"])
    m = VERSION_RE.search(out + err)
    return m.group(0) if m else "unknown"


def canary_of(row: Row, home: Path, skill: str, installed: bool) -> str:
    if row.canary == "list":
        if not installed:
            return "not installed"
        rc, out, _ = run([shutil.which(row.binary), *row.canary_arg])
        if rc != 0:
            return "listing failed"
        # Whole-name match on stdout only: a listing that names a rejected
        # skill on stderr, or a longer name sharing the prefix, is not a hit.
        hit = re.search(rf"(?<![\w-]){re.escape(skill)}(?![\w-])", out)
        return f"lists {skill}" if hit else f"does not list {skill}"
    if row.canary == "symlink":
        p = home / row.canary_arg[0].format(skill=skill)
        return "symlink present" if p.is_symlink() or p.exists() else "symlink absent"
    if row.canary == "file":
        p = home / row.canary_arg[0]
        return f"{p.name} present" if p.is_file() else f"{p.name} absent"
    return "no listing"


def _json_file(p: Path) -> dict:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def processes() -> list[str]:
    """Command lines of every process on the station (ps is world-readable)."""
    _, out, _ = run(["ps", "-axo", "command="])
    return out.splitlines()


def _sub(d: dict, key: str) -> dict:
    v = d.get(key)
    return v if isinstance(v, dict) else {}


_TOML_KEY_PART = r'(?:[A-Za-z0-9_-]+|"(?:[^"\\]|\\.)*"|\'[^\']*\')'
_TOML_KEY = _TOML_KEY_PART + r"(?:\s*\.\s*" + _TOML_KEY_PART + r")*"
_TOML_TABLE = re.compile(r"^\[\s*(" + _TOML_KEY + r")\s*\]\s*(?:#.*)?$")
_TOML_ARRAY_TABLE = re.compile(r"^\[\[\s*(" + _TOML_KEY + r")\s*\]\]\s*(?:#.*)?$")
_TOML_PAIR = re.compile(r"^(" + _TOML_KEY + r")\s*=\s*(.*)$")
_TOML_SCALAR = re.compile(r'^("(?:[^"\\]|\\.)*"|\'[^\']*\'|true|false|[+-]?\d[\d_]*(?:\.[\d_]+)?(?:[eE][+-]?\d+)?)\s*(?:#.*)?$')


def _toml_key_path(key: str) -> list:
    parts = re.findall(_TOML_KEY_PART, key)
    return [json.loads(p) if p.startswith('"') else p.strip("'") for p in parts]


def _toml_scalar(raw: str):
    if raw in ("true", "false"):
        return raw == "true"
    if raw[0] == '"':
        return json.loads(raw)
    if raw[0] == "'":
        return raw[1:-1]
    num = raw.replace("_", "")
    return float(num) if any(c in num for c in ".eE") else int(num)


def _toml_depth(s: str) -> int:
    """Open minus close brackets and braces in one line, counting only those
    outside quoted strings and before a comment."""
    depth, quote, i = 0, "", 0
    while i < len(s):
        c = s[i]
        if quote:
            if c == "\\" and quote == '"':
                i += 1
            elif c == quote:
                quote = ""
        elif c in "\"'":
            quote = c
        elif c == "#":
            break
        elif c in "[{":
            depth += 1
        elif c in "]}":
            depth -= 1
        i += 1
    return depth


def _toml_subset(text: str) -> dict:
    """A reader for the TOML that Codex's config.toml holds, for interpreters
    without tomllib: [table] headers and key = value pairs with bare, quoted or
    dotted keys and scalar values. Arrays, inline tables, multi-line strings and
    [[array]] tables are skipped, so their keys read as absent. Anything it
    cannot place - a line that is none of these, a repeated table or key, a
    value left open at the end - raises ValueError, as tomllib would, so a
    caller fails closed instead of misfiling a key under the wrong table."""
    doc: dict = {}
    table: list | None = []
    seen_tables: set = set()
    seen_keys: set = set()
    fence, depth = "", 0
    for n, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if fence:
            if fence in s:
                fence = ""
            continue
        if depth > 0:
            depth += _toml_depth(s)
            continue
        if not s or s.startswith("#"):
            continue
        if _TOML_ARRAY_TABLE.match(s):
            table = None
            continue
        m = _TOML_TABLE.match(s)
        if m:
            table = _toml_key_path(m.group(1))
            if tuple(table) in seen_tables:
                raise ValueError(f"line {n} repeats a table header")
            seen_tables.add(tuple(table))
            continue
        m = _TOML_PAIR.match(s)
        if not m:
            raise ValueError(f"line {n} is not TOML this reader understands: {s[:60]}")
        raw = m.group(2).strip()
        if not raw:
            raise ValueError(f"line {n} has no value")
        opener = next((f for f in ('"""', "'''") if raw.startswith(f)), "")
        if opener and raw.count(opener) < 2:
            fence = opener
            continue
        if raw[0] in "[{":
            depth = _toml_depth(raw)
            continue
        if table is None:
            continue
        sm = _TOML_SCALAR.match(raw)
        if not sm:
            continue
        path = table + _toml_key_path(m.group(1))
        if tuple(path) in seen_keys:
            raise ValueError(f"line {n} repeats a key")
        seen_keys.add(tuple(path))
        node = doc
        for part in path[:-1]:
            node = node.setdefault(part, {})
            if not isinstance(node, dict):
                raise ValueError(f"line {n} redefines a key as a table")
        node[path[-1]] = _toml_scalar(sm.group(1))
    if fence or depth > 0:
        raise ValueError("a multi-line value is never closed")
    return doc


def toml_loads(text: str) -> dict:
    """Parse TOML with tomllib (stdlib from 3.11), else with _toml_subset so
    stock macOS's 3.9 reads Codex's config.toml too. Raises ValueError."""
    try:
        import tomllib
    except ImportError:
        return _toml_subset(text)
    return tomllib.loads(text)


def _toml_file(p: Path) -> dict:
    """Parsed config.toml, or {} when unreadable."""
    try:
        return toml_loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _launch_agents_name(home: Path, needle: str) -> bool:
    """True when a plist in either LaunchAgents folder runs the named binary."""
    for folder in (home / "Library" / "LaunchAgents", Path("/Library/LaunchAgents")):
        if not folder.is_dir():
            continue
        for p in folder.glob("*.plist"):
            try:
                if needle in p.read_text(encoding="utf-8", errors="replace"):
                    return True
            except OSError:
                continue
    return False


def remote_of(row: Row, home: Path, procs: list[str], env: dict[str, str]) -> str:
    """The remote-control, daemon and telemetry state of one harness, read from
    its config files and the process table only (SPEC.md invariant 7). "off"
    means every switch the harness exposes and the probe can read is off; a
    note after it names what the probe cannot read. Anything else names the
    switch that is on."""
    if row.harness == "claude-code":
        s = _json_file(home / ".claude" / "settings.json")
        on = [] if s.get("disableRemoteControl") is True else ["disableRemoteControl unset"]
        if _sub(s, "env").get("DISABLE_TELEMETRY") != "1":
            on.append("env.DISABLE_TELEMETRY unset")
        return "off" if not on else "ON: " + ", ".join(on)
    if row.harness == "codex":
        t = _toml_file(home / ".codex" / "config.toml")
        on = []
        if _sub(t, "features").get("daemon_auto_start") is not False:
            on.append("features.daemon_auto_start not false")
        if _sub(t, "analytics").get("enabled") is not False:
            on.append("analytics.enabled not false")
        if any("codex app-server" in p for p in procs):
            on.append("app-server daemon running")
        return "off" if not on else "ON: " + ", ".join(on)
    if row.harness == "cursor":
        if any("cursor-agent worker" in p for p in procs):
            return "ON: cloud worker running"
        c = _json_file(home / ".cursor" / "cli-config.json")
        ghost = _sub(c, "privacyCache").get("ghostMode")
        return "off" if ghost is True else "ON: privacy mode not ghost"
    if row.harness == "copilot":
        for p in procs:
            toks = p.split()
            if "copilot" in p and ("--remote" in toks or "--remote-export" in toks):
                return "ON: a session with --remote or --remote-export"
        return "off; per session only (--no-remote-export)"
    if row.harness == "goose":
        if any("goose serve" in p for p in procs):
            return "ON: goose serve running"
        val = env.get("GOOSE_TELEMETRY_ENABLED")
        if val is None:
            try:
                yaml = (home / ".config" / "goose" / "config.yaml").read_text(encoding="utf-8")
            except OSError:
                yaml = ""
            hits = re.findall(r"^GOOSE_TELEMETRY_ENABLED:\s*(\S+)", yaml, re.M)
            val = hits[-1] if hits else None   # the last key wins in YAML
        return "off" if str(val).lower() == "false" else "ON: GOOSE_TELEMETRY_ENABLED not false"
    if row.harness == "pi":
        return "off" if env.get("PI_TELEMETRY", "").lower() in ("0", "false", "no") else "ON: PI_TELEMETRY unset (install telemetry)"
    if row.harness == "antigravity":
        for p in procs:
            toks = p.split()
            if toks and (toks[0] == "agy" or toks[0].endswith("/agy")) and "remote-control" in toks:
                return "ON: remote-control daemon running"
        if _launch_agents_name(home, "/agy"):
            return "ON: remote-control launch agent registered"
        return "off; telemetry switch unverified"
    return "unknown"


def probe(skill: str) -> list[dict]:
    home = Path.home()
    procs = processes()
    out = []
    for row in ROWS:
        version = version_of(row.binary)
        installed = version != "not installed"
        cfg = home / row.config_home
        out.append({
            "harness": row.harness,
            "binary": row.binary,
            "version": version,
            "config_home": str(cfg),
            "config_home_present": cfg.is_dir(),
            "canary": canary_of(row, home, skill, installed),
            "remote_control": remote_of(row, home, procs, dict(os.environ)),
        })
    return out


def table(rows: list[dict]) -> str:
    """The text table shows config homes as ~/..., so a pasted table never
    holds a home path; --json keeps the real path for scripts."""
    home = str(Path.home())
    cols = ("harness", "version", "config_home", "config_home_present", "canary", "remote_control")
    heads = ("harness", "version", "config home", "present", "skills canary", "remote control")
    cells = []
    for r in rows:
        vals = [str(r[c]) for c in cols]
        if vals[2].startswith(home):
            vals[2] = "~" + vals[2][len(home):]
        cells.append(vals)
    widths = [max(len(h), *(len(c[i]) for c in cells)) for i, h in enumerate(heads)]
    fmt = "  ".join("{:<%d}" % w for w in widths)
    return "\n".join([fmt.format(*heads)] + [fmt.format(*c) for c in cells])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true", help="emit one JSON object per harness")
    ap.add_argument("--skill", default="skill-authoring", help="repo skill to look for in listings")
    a = ap.parse_args(argv)
    if not SKILL_RE.fullmatch(a.skill):
        ap.error("--skill must be a skill name: lowercase letters, digits and hyphens")
    rows = probe(a.skill)
    print(json.dumps(rows, indent=2) if a.json else table(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
