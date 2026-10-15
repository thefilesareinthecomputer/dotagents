#!/usr/bin/env python3
"""agent-review: one harness, one model, one read-only review of a fixed set of files.

  agent_review.py run --harness claude|codex|cursor|antigravity|ollama [--model NAME] [--effort LEVEL]
                      [--allow-cloud] --brief <file|-> --file <path> [--file ...] [--root <dir>] [--out <dir>]
                      [--topic SLUG] [--reviews-dir <dir>] [--no-sanitize] [--timeout 1500]
  agent_review.py harnesses          print the table: runner, default model, effort levels, how effort is passed,
                                     and whether the CLI is installed here

Exit codes: 0 review written; 2 bad arguments; 3 the harness is not installed on this
machine (nothing is created); 4 the harness ran and failed or returned nothing.

The named files, and nothing else, go into a one-commit staging repo, each through the
sanitize skill on the way (secrets and personal shapes replaced by placeholders, a term
hit refusing the run), so the only copy outside the source is the clean one; the
harness runs read-only in a worktree of it and hands its text back; this script
writes the review as `YYYY-MM-DD-review-<harness>-<model>-<topic>.md` into the repo's
`tasks/reviews/` (or `reviews/`; see `--reviews-dir`), never overwriting, and `run.json`
into the run folder. Nothing the harness produces is applied anywhere.
The agent-conference skill imports this module for its members. Stdlib only.

Every harness reviews the same way: one headless call, one turn, the clean staged files
inlined into the prompt with line numbers, no tool granted by this script, started in an
empty folder; Cursor and Antigravity also run under a Seatbelt write-deny profile, since
their read-only modes keep their tools. Multi-step work is the task skills'. The one-shot
forms:
  claude       `claude -p --tools "" --max-turns 1`, prompt on stdin; `--effort` low|medium|high|xhigh|max
  codex        `codex exec --json --ephemeral --ignore-user-config -s read-only`, prompt on stdin (`-`);
               `model_reasoning_effort` config key, low|medium|high|xhigh|max|ultra
  cursor       `agent -p --mode ask`, prompt on stdin; the level is a suffix of the model slug
  antigravity  `agy --print --mode plan`, prompt on argv only, so capped by bytes; `agy --effort`
  ollama       one POST to the local daemon's /api/chat; `:cloud` tags only, behind --allow-cloud;
               `think` from the tag's /api/show map
"""

from __future__ import annotations

import argparse
import datetime as _dt
import fcntl
import http.client
import ipaddress
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SKILLS_ROOT = SKILL_DIR.parent
REFS = SKILL_DIR / "references"

# Every harness reviews the same way: one headless call, one turn, the clean staged files
# inlined into the prompt with line numbers, no tool grant, an empty working directory. The
# CLI's read-only mode is the backstop behind that. `window` is the context the size check
# uses, in tokens: Claude and Gemini from their vendors' published 1M; Codex's and Grok's
# are stand-ins at 400K until a vendor figure is recorded.
HARNESSES = {
    "claude": {"runner": "claude", "bin": "claude", "model": "claude-fable-5-1", "window": 1_000_000,
               "levels": ("low", "medium", "high", "xhigh", "max"), "label": "Claude Code"},
    "codex": {"runner": "codex", "bin": "codex", "model": "gpt-6-astra", "window": 400_000,
              "levels": ("low", "medium", "high", "xhigh", "max", "ultra"), "label": "Codex CLI"},
    "cursor": {"runner": "cursor", "bin": "agent", "model": "grok-4.7", "window": 400_000,
               "levels": ("low", "medium", "high", "xhigh", "max"), "label": "Cursor agent CLI"},
    "antigravity": {"runner": "antigravity", "bin": "agy", "model": "gemini-3.1-pro", "window": 1_000_000,
                    "levels": ("low", "medium", "high", "xhigh", "max"), "label": "Antigravity CLI"},
    # No default model: the user names a `:cloud` tag, and the call is one request to the
    # local daemon's /api/chat. Effort maps onto the tag's own `think` values and the window
    # comes from /api/show, both read at run time.
    "ollama": {"runner": "ollama", "bin": None, "model": None, "window": None,
               "levels": ("off", "low", "medium", "high", "xhigh", "max"), "label": "Ollama cloud tag"},
}
OLLAMA_DEFAULT_HOST = "http://127.0.0.1:11434"
OLLAMA_TAG_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}:cloud$")
CONTEXT_FRACTION = 0.8
BYTES_PER_TOKEN = 3
# The streamed NDJSON carries about 300 bytes of framing per token, so a cap on wire bytes
# is the wrong unit: a 70K-token review is 20 MB on the wire. The text cap is on the
# characters of content and thinking; the wire cap only bounds a server sending framing.
OLLAMA_MAX_TEXT = 8 * 1024 * 1024
OLLAMA_MAX_RESPONSE = 512 * 1024 * 1024
OLLAMA_MAX_OUTPUT_TOKENS = 65536   # DeepSeek Flash at high thought 393K tokens on one brief and never answered
LOOP_LINE_REPEATS = 50             # one line this many times in the thinking is a loop, and the record says so
THINK_LADDER = ("low", "medium", "high", "xhigh", "max")
DEFAULT_EFFORT = "high"
# The one note every harness gets. The files are in the message, so no harness has anything
# to read, and the brief says so in the same words whatever CLI carries it.
TOOL_NOTE = ("The files are in this message, under \"File contents\", each in a fenced block headed by its "
             "path with every line prefixed by its line number. Read them there and cite file and line "
             "from those blocks. Do not use any tool, run any command, read any file or fetch anything: "
             "nothing outside this message is part of the review, and your working directory is empty.")
TOOL_NOTES = {name: TOOL_NOTE for name in ("claude", "codex", "cursor", "antigravity", "ollama")}
DEFAULT_TIMEOUT = 1500
MAX_TIMEOUT = 1800
MAX_FILE_BYTES = 5 * 1024 * 1024
AGY_MAX_PROMPT_BYTES = 900_000  # agy takes the prompt on argv only; ARG_MAX is 1 MiB
# When Fable is unavailable the CLI falls back to this model; an answer from it is accepted
# and recorded as a fallback, any other model is refused.
CLAUDE_FALLBACK_MODEL = "claude-opus-5-5"
ENV_ALLOW = ("HOME", "PATH", "USER", "LANG", "SHELL", "TERM", "TMPDIR")
TOKEN_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
FENCED_JSON = re.compile(r"```json\s*(\{.*?\})\s*```", re.S)

EXIT_OK, EXIT_ARGS, EXIT_UNAVAILABLE, EXIT_FAILED = 0, 2, 3, 4


class ReviewError(Exception):
    """`kind` classifies a failure structurally, so a retry decision never reads error
    text: `args`, `http` (with `status`), `transport`, `protocol`, `app`, `timeout`."""

    def __init__(self, msg: str, code: int = EXIT_ARGS, kind: str = "args", status: int | None = None):
        super().__init__(msg)
        self.code = code
        self.kind = kind
        self.status = status
        self.partial: dict | None = None   # text received before a stream failed, kept for the record


# ---------------------------------------------------------------- helpers ---

def state_dir() -> Path:
    raw = os.environ.get("AGENT_REVIEW_STATE") or os.path.join(
        os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"), "agent-review")
    p = Path(raw).expanduser().resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def slug(text: str, limit: int = 64) -> str:
    """A file-name-safe slug: letters, digits and hyphens, no run of hyphens, no edge hyphen."""
    s = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-")
    if not s:
        raise ReviewError(f"{text!r} leaves nothing usable for a file name")
    return s[:limit]


def reviews_dir(start: Path, override: str | None) -> tuple[Path, str]:
    """Where a review lands, resolved once per run. Returns (dir, rule).

    `--reviews-dir` wins. Otherwise walk up from `start` to the nearest git root: one with a
    `tasks/` folder gets `tasks/reviews/`, one without gets `<root>/reviews/` (this script
    never creates `tasks/` in another repo), and no git root at all gets `<start>/reviews/`.
    A `tasks` or `reviews` component that is a symlink is refused: a reviewed repo must not
    be able to point model-written text at a folder of its choosing. The caller falls back
    to the run folder when the choice cannot be written."""
    if override:
        return Path(override).expanduser().resolve(), "reviews-dir"
    cur = start.resolve()
    while True:
        if (cur / ".git").exists():
            if (cur / "tasks").is_dir():
                _refuse_links(cur, ("tasks", "reviews"))
                return cur / "tasks" / "reviews", "git-root-tasks"
            _refuse_links(cur, ("reviews",))
            return cur / "reviews", "git-root"
        if cur.parent == cur:
            _refuse_links(start.resolve(), ("reviews",))
            return start.resolve() / "reviews", "no-git-root"
        cur = cur.parent


def _refuse_links(base: Path, parts: tuple[str, ...]) -> None:
    cur = base
    for part in parts:
        cur = cur / part
        if cur.is_symlink():
            raise ReviewError(f"{cur} is a symlink; reviews are written only into a real folder under the repo")


def ensure_writable(d: Path) -> bool:
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    return os.access(d, os.W_OK) and not d.is_symlink()


# Zero-width characters, bidi controls, the invisible tag block and the BOM, written as
# escapes so the source itself holds none of them.
INVISIBLE_RE = re.compile("[\\u115f\\u1160\\u180e\\u200b-\\u200f\\u202a-\\u202e\\u2060-\\u2064\\u2066-\\u2069\\u3164\\ufeff"
                          "\\U000e0000-\\U000e007f\\U000e0100-\\U000e01ef]")


def strip_invisible(text: str) -> tuple[str, int]:
    """Those codepoints removed from model output before it is written into the repo, where
    a later session will read it; the count is recorded beside the run."""
    return INVISIBLE_RE.subn("", text)


# Every harness's text passes through scan_output the moment it arrives, before another
# model reads it (the conference inlines stage-1 answers into stage-2 briefs), before it is
# ranked, and before it is written. Invisible and control codepoints are removed and
# counted; NUL means the output is not text and the member fails; the rest are flags,
# recorded beside the run and printed, never silently dropped.
CONTROL_RE = re.compile("[\\x00-\\x08\\x0b\\x0c\\x0e-\\x1f\\x7f-\\x9f]")
BLOB_RE = re.compile(r"[A-Za-z0-9+/_-]{200,}={0,2}|\b[0-9a-fA-F]{200,}\b")
DATA_URI_RE = re.compile(r"data:[\w/+.-]+;base64,", re.I)
ACTIVE_MARKUP_RE = re.compile(r"<\s*(?:script|iframe|object|embed)\b|javascript:", re.I)
INJECTION_PHRASES = ("ignore previous instructions", "ignore all previous", "ignore the above", "disregard your instructions",
                     "disregard the above", "you are now", "new instructions:", "system prompt:", "<|im_start|>", "<|system|>",
                     "[inst]", "do not tell the user", "run the following command", "execute the following command")
SCAN_FLAGS = ("blobs", "data_uris", "active_markup", "injection")


def scan_output(text: str) -> tuple[str, dict]:
    """(clean text, report). Removes and counts invisible and control codepoints; flags
    base64 or hex runs of 200 characters or more, base64 data URIs, script-like markup and
    instruction-shaped phrases; marks text holding NUL as binary."""
    report = {"binary": "\x00" in text}
    text, report["invisible"] = INVISIBLE_RE.subn("", text)
    text, report["control"] = CONTROL_RE.subn("", text)
    low = " ".join(text.lower().split())   # whitespace collapsed, so a doubled space does not split a phrase
    report["blobs"] = len(BLOB_RE.findall(text))
    report["data_uris"] = len(DATA_URI_RE.findall(text))
    report["active_markup"] = len(ACTIVE_MARKUP_RE.findall(text))
    report["injection"] = sum(low.count(p) for p in INJECTION_PHRASES)
    report["flagged"] = [k for k in SCAN_FLAGS if report[k]]
    return text, report


def scan_note(report: dict | None) -> str:
    """One short clause for stdout when a scan removed or flagged anything, else empty."""
    if not report:
        return ""
    parts = [f"{k} {report[k]}" for k in ("invisible", "control") if report.get(k)]
    parts += [f"{k} {report[k]}" for k in report.get("flagged", [])]
    return f"  scan: {', '.join(parts)}" if parts else ""


def write_new(path: Path, data: bytes) -> None:
    """Create `path` as a new 0600 file, never following a link and never overwriting: a
    dangling symlink planted at a predictable review name is refused, not written through."""
    try:
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        raise ReviewError(f"{path} already exists or is a link; nothing was written", EXIT_FAILED)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)


def unique_path(d: Path, stem: str, suffixes: tuple[str, ...] = (".md",)) -> Path:
    """`<d>/<stem>` with the first free `-2`, `-3`... suffix, checked against every suffix
    in the tuple at once so paired outputs (a folder and its .md) share one number."""
    n = 1
    while True:
        cand = stem if n == 1 else f"{stem}-{n}"
        if not any((d / (cand + s)).exists() for s in suffixes):
            return d / cand
        n += 1


def review_stem(kind: str, harness: str | None, model: str | None, topic: str,
                when: _dt.date | None = None) -> str:
    """`YYYY-MM-DD-review-<harness>-<model>-<topic>` or `YYYY-MM-DD-conference-<topic>`."""
    day = (when or _dt.date.today()).isoformat()
    parts = [day, kind] + ([harness, slug(model)] if harness else []) + [slug(topic)]
    return "-".join(parts)


def git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-c", "user.email=review@local", "-c", "user.name=review", *args],
                          cwd=str(cwd), text=True, capture_output=True, check=True, timeout=120)


def test_mode() -> bool:
    """The explicit opt-in under which fake binaries are honored. Without it an ambient
    AGENT_REVIEW_FAKE_BIN or AGENT_REVIEW_CLI_DIR cannot swap a real run for a fabricated one."""
    return os.environ.get("AGENT_REVIEW_TEST") == "1"


def cli_path(name: str) -> str | None:
    """The CLI binary: from AGENT_REVIEW_CLI_DIR in test mode (a folder of fakes under a
    skill's tests folder), else PATH."""
    if test_mode() and os.environ.get("AGENT_REVIEW_CLI_DIR"):
        d = Path(os.environ["AGENT_REVIEW_CLI_DIR"]).resolve()
        if d.parent.name != "tests" or d.parent.parent.parent != SKILLS_ROOT:
            raise ReviewError(f"AGENT_REVIEW_CLI_DIR must sit in a skill's tests folder, not {d}")
        p = d / name
        return str(p) if p.exists() else None
    return shutil.which(name)


def fake_bin() -> str | None:
    """The fake harness, honored only in test mode and only from a skill's tests folder."""
    if not test_mode():
        return None
    path = os.environ.get("AGENT_REVIEW_FAKE_BIN")
    if not path:
        return None
    resolved = Path(path).resolve()
    if resolved.parent.name != "tests" or resolved.parent.parent.parent != SKILLS_ROOT:
        raise ReviewError(f"AGENT_REVIEW_FAKE_BIN must sit in a skill's tests folder, not {resolved}")
    return str(resolved)


def child_env() -> dict[str, str]:
    """What a CLI is spawned with: ENV_ALLOW and nothing else, so a token the session
    carries never reaches a vendor's CLI. Test hooks pass only under the opt-in."""
    env = {k: os.environ[k] for k in ENV_ALLOW if k in os.environ}
    if test_mode():
        env.update({k: v for k, v in os.environ.items() if k.startswith(("AGENT_REVIEW_", "FAKE_"))})
    return env


def render(template: str, **fields: str) -> str:
    out = template
    for k, v in fields.items():
        out = out.replace("{{" + k + "}}", v)
    return out


# ---------------------------------------------------------------- resolution ---

def resolve(harness: str, model: str | None, effort: str | None, allow_cloud: bool = False) -> dict:
    """The harness entry with the model and effort settled: a bare model keeps the effort
    beside it; a model that already names its level (gemini-3.1-pro-high, grok-4.7-xhigh)
    drops the effort, since both CLIs refuse the pair. The ollama harness takes a `:cloud`
    tag only, and only behind `allow_cloud`, since the files go to Ollama's cloud."""
    if harness not in HARNESSES:
        raise ReviewError(f"unknown harness {harness!r}; one of {', '.join(HARNESSES)}")
    cfg = dict(HARNESSES[harness])
    cfg["harness"] = harness
    if harness == "ollama":
        if not model:
            raise ReviewError("ollama has no default model; name a cloud tag with --model <name>:cloud")
        if not OLLAMA_TAG_RE.match(model):
            raise ReviewError(f"ollama runs cloud tags only, never a local model; {model!r} does not end in :cloud")
        if not allow_cloud:
            raise ReviewError(f"{model} is served by Ollama's cloud and the files are sent to it; pass --allow-cloud")
        effort = effort or DEFAULT_EFFORT
        if effort not in cfg["levels"]:
            raise ReviewError(f"ollama takes effort {', '.join(cfg['levels'])}, not {effort!r}")
        cfg.update(model=model, effort=effort)
        return cfg
    model = model or cfg["model"]
    if not TOKEN_RE.match(model):
        raise ReviewError("model must be a plain token")
    cfg["model"] = model
    names_level = any(model.endswith("-" + lv) or model.endswith("-" + lv + "-fast") for lv in cfg["levels"])
    if names_level:
        cfg["effort"] = None
    else:
        effort = effort or DEFAULT_EFFORT
        if effort not in cfg["levels"]:
            raise ReviewError(f"{harness} takes effort {', '.join(cfg['levels'])}, not {effort!r}")
        cfg["effort"] = effort
    return cfg


def availability(cfg: dict) -> str | None:
    """Why this harness cannot run on this machine, or None when it can. Only what is
    checkable without a paid call is checked: the CLI on PATH, or the daemon and the tag
    for ollama. A missing login or a refused model surfaces as a failed run with the
    CLI's own error."""
    if fake_bin():
        missing = os.environ.get("AGENT_REVIEW_FAKE_MISSING", "").split(",")
        return f"fake: {cfg['bin'] or cfg['harness']} not installed" if cfg.get("member", cfg["harness"]) in missing else None
    if cfg["runner"] == "ollama":
        base = ollama_base()
        try:
            tags = ollama_request("GET", "/api/tags", None, 10)
        except ReviewError as exc:
            return f"the Ollama daemon is not answering at {base}: {exc}"
        names = {m.get("name") for m in tags.get("models", []) if isinstance(m, dict)}
        if cfg.get("model") and cfg["model"] not in names:
            return f"{cfg['model']} is not registered with the daemon; run `ollama pull {cfg['model']}` first"
        return None
    if not cli_path(cfg["bin"]):
        return f"the {cfg['label']} CLI ({cfg['bin']}) is not on PATH"
    if cfg["runner"] in CLI_STATE and not Path(SANDBOX_EXEC).exists():
        return f"{SANDBOX_EXEC} is missing, so the write-deny profile cannot be applied"
    return None


# ---------------------------------------------------------------- ollama ---

def _loopback_literal(host: str) -> bool:
    host = host.strip("[]").split("%", 1)[0]
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def is_loopback_host(host: str) -> bool:
    """True when every address the host names is loopback. Its own copy, so this script
    never imports another skill's code."""
    if not host:
        return False
    if host != "localhost":
        return _loopback_literal(host)
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    return bool(infos) and all(_loopback_literal(info[4][0]) for info in infos)


def ollama_base() -> str:
    """The daemon's base URL: OLLAMA_HOST when set, loopback only, plain http only."""
    raw = os.environ.get("OLLAMA_HOST") or OLLAMA_DEFAULT_HOST
    if "://" not in raw:
        raw = "http://" + raw
    parts = urllib.parse.urlsplit(raw)
    host = parts.hostname or ""
    try:
        port = parts.port or 11434
    except ValueError:
        raise ReviewError(f"OLLAMA_HOST {raw!r} has a port that is not a number")
    if parts.scheme != "http" or not is_loopback_host(host):
        raise ReviewError(f"OLLAMA_HOST {raw!r} is not a loopback http address; this harness talks to the local daemon only")
    host = f"[{host}]" if ":" in host else host
    return f"http://{host}:{port}"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, f"redirect to {newurl} refused", headers, fp)


def ollama_request(method: str, path: str, body: dict | None, timeout: int) -> dict:
    """One JSON request to the daemon on loopback: no proxy, no redirect, bounded read."""
    url = ollama_base() + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json", "Accept": "application/json"})
    opener = urllib.request.build_opener(_NoRedirect(), urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=timeout) as resp:
            raw = resp.read(OLLAMA_MAX_RESPONSE + 1)
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read(500).decode("utf-8", "replace").strip()
        except (OSError, AttributeError):
            detail = ""
        raise ReviewError(f"{path} returned HTTP {exc.code}: {detail or exc.reason}", EXIT_FAILED, kind="http", status=exc.code)
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, TimeoutError) or isinstance(exc, TimeoutError):
            raise ReviewError(f"{path} did not answer within {timeout} s", EXIT_FAILED, kind="timeout")
        raise ReviewError(f"cannot reach the daemon for {path}: {reason}", EXIT_FAILED, kind="transport")
    if len(raw) > OLLAMA_MAX_RESPONSE:
        raise ReviewError(f"{path} answered with more than {OLLAMA_MAX_RESPONSE} bytes", EXIT_FAILED)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ReviewError(f"{path} did not answer with JSON", EXIT_FAILED)
    if not isinstance(value, dict):
        raise ReviewError(f"{path} answered with a non-object", EXIT_FAILED)
    return value


OLLAMA_RETRY_PAUSE_S = 5
OLLAMA_IDLE_S = 120            # a streaming chat that sends nothing for this long is dead
OLLAMA_MAX_LINE = 4 * 1024 * 1024   # one NDJSON chunk; a real chunk is a few hundred bytes
OLLAMA_READ_SIZE = 65536


def _chunk_field(chunk: dict, key: str) -> str:
    """A string field of a streamed message, or a protocol error for any other type."""
    msg = chunk.get("message")
    if msg is None:
        return ""
    if not isinstance(msg, dict):
        raise ReviewError("/api/chat sent a chunk whose message is not an object", EXIT_FAILED, kind="protocol")
    value = msg.get(key)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ReviewError(f"/api/chat sent a chunk whose message.{key} is not a string", EXIT_FAILED, kind="protocol")
    return value


def ollama_chat_stream(body: dict, deadline: float) -> dict:
    """One streaming `/api/chat` call, accumulated into the non-streaming shape: `message`
    with the full `content` and `thinking`, plus the final chunk's counts. Streaming keeps
    bytes flowing while a long answer generates, which a non-streaming call does not: the
    daemon's own log showed a single non-streamed call dropped by the cloud with an EOF at
    11 minutes. The clock is this function's: `deadline` (monotonic) bounds the
    whole call including the final chunk, reads are bounded to OLLAMA_READ_SIZE so a server
    that dribbles bytes cannot hold a read open, a line is capped at OLLAMA_MAX_LINE before
    it is buffered, and OLLAMA_IDLE_S bounds the gap between bytes."""
    url = ollama_base() + "/api/chat"
    data = json.dumps(dict(body, stream=True)).encode()
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json", "Accept": "application/x-ndjson"})
    opener = urllib.request.build_opener(_NoRedirect(), urllib.request.ProxyHandler({}))

    def remaining() -> float:
        left = deadline - time.monotonic()
        if left <= 0:
            raise ReviewError("/api/chat did not finish within the time allowed", EXIT_FAILED, kind="timeout")
        return left

    content, thinking, final, total, text_total, truncated = [], [], None, 0, 0, False
    buf = b""

    def partial() -> dict | None:
        """Whatever the model had said before a failure travels with the error, so a
        three-minute answer is never thrown away with the connection."""
        return {"content": "".join(content), "thinking": "".join(thinking)} if content or thinking else None

    def fail(msg: str, kind: str, status: int | None = None) -> ReviewError:
        err = ReviewError(msg, EXIT_FAILED, kind=kind, status=status)
        err.partial = partial()
        return err

    try:
        with opener.open(req, timeout=min(OLLAMA_IDLE_S, remaining())) as resp:
            eof = False
            while not eof and final is None and not truncated:
                remaining()
                piece = resp.read1(OLLAMA_READ_SIZE) if hasattr(resp, "read1") else resp.read(OLLAMA_READ_SIZE)
                if not piece:
                    eof = True
                total += len(piece)
                if total > OLLAMA_MAX_RESPONSE:
                    raise ReviewError(f"/api/chat answered with more than {OLLAMA_MAX_RESPONSE} bytes", EXIT_FAILED, kind="protocol")
                buf += piece
                if len(buf) > OLLAMA_MAX_LINE and b"\n" not in buf:
                    raise ReviewError(f"/api/chat sent a chunk over {OLLAMA_MAX_LINE} bytes", EXIT_FAILED, kind="protocol")
                while final is None and not truncated:
                    nl = buf.find(b"\n")
                    if nl < 0:
                        if eof and buf.strip():
                            line, buf = buf, b""
                        else:
                            break
                    else:
                        line, buf = buf[:nl], buf[nl + 1:]
                    line = line.strip()
                    if not line:
                        continue
                    if len(line) > OLLAMA_MAX_LINE:
                        raise ReviewError(f"/api/chat sent a chunk over {OLLAMA_MAX_LINE} bytes", EXIT_FAILED, kind="protocol")
                    try:
                        chunk = json.loads(line.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        raise ReviewError("/api/chat sent a chunk that is not JSON", EXIT_FAILED, kind="protocol")
                    if not isinstance(chunk, dict):
                        raise ReviewError("/api/chat sent a chunk that is not an object", EXIT_FAILED, kind="protocol")
                    if chunk.get("error"):
                        raise ReviewError(f"/api/chat reported: {str(chunk['error'])[:300]}", EXIT_FAILED, kind="app")
                    c, t = _chunk_field(chunk, "content"), _chunk_field(chunk, "thinking")
                    if c:
                        content.append(c)
                    if t:
                        thinking.append(t)
                    text_total += len(c) + len(t)
                    if text_total > OLLAMA_MAX_TEXT:
                        truncated = True   # keep what arrived; the caller records it as cut
                        break
                    done = chunk.get("done", False)
                    if not isinstance(done, bool):
                        raise ReviewError("/api/chat sent a chunk whose done is not a boolean", EXIT_FAILED, kind="protocol")
                    if done:
                        remaining()  # a final chunk after the deadline is late, not a success
                        final = chunk
    except ReviewError as exc:
        exc.partial = partial()
        raise
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read(500).decode("utf-8", "replace").strip()
        except (OSError, AttributeError, http.client.HTTPException):
            detail = ""
        raise fail(f"/api/chat returned HTTP {exc.code}: {detail or exc.reason}", "http", exc.code)
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, TimeoutError) or isinstance(exc, TimeoutError):
            raise fail(f"/api/chat sent nothing for {OLLAMA_IDLE_S} s", "timeout")
        raise fail(f"the connection to the daemon dropped during /api/chat: {type(exc).__name__}: {reason}", "transport")
    if final is None and not truncated:
        raise fail("the stream from /api/chat ended before its final chunk", "transport")
    result = dict(final) if final is not None else {"model": body.get("model"), "done": False}
    result["truncated"] = truncated
    result["message"] = {"role": "assistant", "content": "".join(content), "thinking": "".join(thinking)}
    return result


def thinking_loop(thinking: str) -> int:
    """The highest count of one repeated non-blank line in a model's thinking when it reaches
    LOOP_LINE_REPEATS, else 0. DeepSeek Flash's runaway repeated one line 2,868 times."""
    counts: dict[str, int] = {}
    for line in thinking.splitlines():
        line = line.strip()
        if len(line) > 8:
            counts[line] = counts.get(line, 0) + 1
    top = max(counts.values(), default=0)
    return top if top >= LOOP_LINE_REPEATS else 0


def _retryable(exc: ReviewError) -> bool:
    """A 5xx or a dropped connection is the vendor's side and gets one more try. A 4xx, an
    error the model reported, a malformed stream, a refusal of ours, or a timeout we chose
    does not. The decision reads the error's kind, never its text."""
    return (exc.kind == "http" and exc.status is not None and 500 <= exc.status <= 599) or exc.kind == "transport"


def think_setting(effort: str, show: dict, tag: str):
    """`--effort` mapped onto the tag's own `think` values from /api/show. The server
    accepts any value and the GLM family leaks its reasoning into `content` under an
    unlisted `false`, so only listed values are ever sent. `off` is
    strict; a level the tag does not list takes the nearest listed level below it, and a
    boolean-only or unmapped tag takes `true`."""
    block = show.get("thinking") if isinstance(show.get("thinking"), dict) else {}
    values = block.get("values") if isinstance(block.get("values"), list) else None
    strings = [v for v in (values or []) if isinstance(v, str)]
    if effort == "off":
        if values is None or any(v is False for v in values):
            return False
        raise ReviewError(f"{tag} cannot turn thinking off; its listed think values are {values}; use --effort low")
    if strings:
        idx = THINK_LADDER.index(effort)
        below = [lv for lv in THINK_LADDER[: idx + 1] if lv in strings]
        if below:
            return below[-1]
        ranked = sorted(strings, key=lambda s: THINK_LADDER.index(s) if s in THINK_LADDER else len(THINK_LADDER))
        return ranked[0]
    return True


def context_length(show: dict) -> int | None:
    info = show.get("model_info") if isinstance(show.get("model_info"), dict) else {}
    for key, value in info.items():
        if key.endswith("context_length") and isinstance(value, int):
            return value
    return None


def inline_files(stage: Path) -> tuple[str, int]:
    """Every staged file as a fenced block headed by its path, each line prefixed by its
    number, so a model with no tools can cite file and line."""
    blocks = []
    files = sorted(p for p in stage.rglob("*") if p.is_file() and ".git" not in p.relative_to(stage).parts)
    for p in files:
        rel = p.relative_to(stage).as_posix()
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        width = len(str(max(1, len(lines))))
        numbered = "\n".join(f"{i:>{width}}: {line}" for i, line in enumerate(lines, 1))
        blocks.append(f"## {rel}\n\n```\n{numbered}\n```")
    return "\n\n".join(blocks), len(files)


def build_prompt(brief_path: Path, stage: Path, window: int | None, label: str) -> tuple[str, dict]:
    """The one prompt every harness gets: the brief, then every staged file inlined. Refuses
    when it would not fit CONTEXT_FRACTION of the window, naming the figure; nothing is
    truncated. Returns (prompt, {estimated_prompt_tokens, files_inlined, window})."""
    files_text, n = inline_files(stage)
    prompt = brief_path.read_text(encoding="utf-8").rstrip() + "\n\n# File contents\n\n" + files_text + "\n"
    est = (len(TOOL_NOTE.encode()) + len(prompt.encode())) // BYTES_PER_TOKEN
    if window and est > CONTEXT_FRACTION * window:
        raise ReviewError(f"the brief and {n} files come to about {est} tokens, over {int(CONTEXT_FRACTION * 100)}% "
                          f"of {label}'s {window}-token window; nothing is truncated, so split the review", EXIT_FAILED)
    return prompt, {"estimated_prompt_tokens": est, "files_inlined": n, "window": window}


SANDBOX_EXEC = "/usr/bin/sandbox-exec"
SB_PATH_BAD = re.compile(r'[\x00-\x1f"()\\]')
# Each CLI's own state folder stays writable for its chats, caches and auth; the names
# under it that the CLI or its IDE would load later as code or config are denied, since a
# later Seatbelt rule wins and a steered run must not change the CLI's behavior for the
# next one. Cursor's config file is allowed because CLI 2026.10.01 rewrites it at startup;
# it is snapshotted and restored byte for byte after the run instead.
CLI_STATE = {
    "cursor": ("~/.cursor", ("agents", "rules", "plugins", "extensions", "mcp.json", "hooks.json")),
    "antigravity": ("~/.gemini", ("antigravity-cli/settings.json", "settings.json", "GEMINI.md", "extensions")),
}
CURSOR_CLI_CONFIG = "cli-config.json"


def _sb_path(p: Path) -> str:
    """A path literal for a Seatbelt profile; a quote, paren, backslash or control character
    could end the s-expression and inject a rule, so it is refused rather than escaped."""
    s = str(p.resolve())
    if SB_PATH_BAD.search(s):
        raise ReviewError(f"a sandbox path holds a character the profile cannot carry safely: {s!r}")
    return s


def cli_state_home(harness: str) -> Path:
    """The CLI's state folder. In test mode AGENT_REVIEW_<HARNESS>_HOME points it at a
    fixture so the suite never touches the real one."""
    override = os.environ.get(f"AGENT_REVIEW_{harness.upper()}_HOME") if test_mode() else None
    return Path(override or os.path.expanduser(CLI_STATE[harness][0])).resolve()


def user_temp_root() -> Path:
    """The per-user temp tree the sandbox allows: the parent of this user's Darwin temp folder,
    read from getconf rather than $TMPDIR so a caller cannot turn it into /private/tmp."""
    try:
        out = subprocess.run(["/usr/bin/getconf", "DARWIN_USER_TEMP_DIR"], capture_output=True, text=True, timeout=10)
        raw = out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        raw = ""
    tmp = Path(raw).resolve() if raw else None
    if not tmp or not str(tmp).startswith("/private/var/folders/") or tmp.name != "T":
        raise ReviewError("could not find this user's Darwin temp folder under /private/var/folders; refusing to guess", EXIT_FAILED)
    return tmp.parent


def write_sandbox_profile(work: Path, harness: str, cwd: Path) -> Path:
    """A Seatbelt profile for a CLI whose read-only mode is not read-only for files: deny
    every write, then allow the CLI's state folder, the run's empty cwd, the user's temp
    tree and the terminal devices, then deny the loader names under the state folder.
    Reads and the network stay open, since the CLI needs its vendor."""
    home = cli_state_home(harness)
    lines = ["(version 1)", "(allow default)", "(deny file-write*)"]
    for p in (home, cwd, user_temp_root()):
        lines.append(f'(allow file-write* (subpath "{_sb_path(p)}"))')
    lines.append('(allow file-write* (literal "/dev/null") (literal "/dev/tty") (regex #"^/dev/ttys[0-9]+$"))')
    for name in CLI_STATE[harness][1]:
        lines.append(f'(deny file-write* (subpath "{_sb_path(home / name)}"))')
    profile = work / f"sandbox-{harness}.sb"
    profile.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return profile


def sandboxed(argv: list[str], profile: Path) -> list[str]:
    if not Path(SANDBOX_EXEC).exists():
        raise ReviewError(f"{SANDBOX_EXEC} is missing, so the write-deny profile cannot be applied", EXIT_FAILED)
    return [SANDBOX_EXEC, "-f", str(profile), *argv]


def snapshot_cursor_config() -> bytes | None:
    try:
        return (cli_state_home("cursor") / CURSOR_CLI_CONFIG).read_bytes()
    except OSError:
        return None


def restore_cursor_config(before: bytes | None) -> dict:
    """Put Cursor's config back exactly as it was and say whether the run changed it. The
    replacement is written through a fresh temp file from mkstemp, so a link planted at a
    predictable name inside the CLI's folder is never followed."""
    path = cli_state_home("cursor") / CURSOR_CLI_CONFIG
    try:
        after = path.read_bytes()
    except OSError:
        after = None
    changed = after != before
    if changed:
        if before is None:
            path.unlink(missing_ok=True)
        else:
            fd, tmp = tempfile.mkstemp(prefix=CURSOR_CLI_CONFIG + ".", dir=str(path.parent))
            try:
                with os.fdopen(fd, "wb") as fh:
                    fh.write(before)
                    os.fchmod(fh.fileno(), 0o600)
                os.replace(tmp, path)
            finally:
                Path(tmp).unlink(missing_ok=True)
    return {"existed": before is not None, "changed_by_run": changed, "restored": changed}


CURSOR_LOCK = "cli-config.lock"


class CursorConfigLock:
    """One Cursor call at a time per user. The snapshot and restore of Cursor's config file
    cannot interleave: two runs that overlap (two conferences, or a conference and a
    cursor-task) would restore each other's copy. The lock file sits beside the config, so
    cursor-task shares it. The wait is bounded by the call's own timeout, and in test mode
    by AGENT_REVIEW_CURSOR_LOCK_WAIT."""

    def __init__(self, timeout: float):
        self.timeout = timeout
        self.waited = 0.0
        self.fd: int | None = None

    def __enter__(self) -> "CursorConfigLock":
        path = cli_state_home("cursor") / CURSOR_LOCK
        path.parent.mkdir(parents=True, exist_ok=True)
        self.fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        wait = self.timeout
        if test_mode() and os.environ.get("AGENT_REVIEW_CURSOR_LOCK_WAIT"):
            wait = float(os.environ["AGENT_REVIEW_CURSOR_LOCK_WAIT"])
        start = time.monotonic()
        while True:
            try:
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() - start >= wait:
                    os.close(self.fd)
                    self.fd = None
                    raise ReviewError(f"another run held Cursor's config lock ({path}) for the whole wait of {wait:g} s",
                                      EXIT_FAILED, kind="timeout")
                time.sleep(0.5)
        self.waited = round(time.monotonic() - start, 1)
        return self

    def __exit__(self, *exc) -> None:
        if self.fd is not None:
            os.close(self.fd)   # closing releases the flock
            self.fd = None


def empty_cwd(work: Path, cfg: dict) -> Path:
    """An empty folder the CLI is started in, so a tool call it makes anyway finds nothing.
    The staged files reach the model only through the prompt."""
    d = work / f"cwd-{slug(cfg.get('member') or cfg['harness'])}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _failed(error: str) -> dict:
    return {"text": None, "usage": None, "model_reported": None, "exit_code": EXIT_FAILED, "error": error[:500]}


def _spawn(argv: list[str], stdin_text: str | None, timeout: int, cwd: Path, work: Path, name: str) -> subprocess.CompletedProcess | dict:
    """One CLI call, stdout kept beside the run. Returns the process, or a failure record."""
    try:
        proc = subprocess.run(argv, input=stdin_text, capture_output=True, text=True, timeout=timeout,
                              cwd=str(cwd), env=child_env())
    except subprocess.TimeoutExpired:
        return _failed(f"timeout after {timeout} s")
    (work / f"{name}-stdout.txt").write_text(proc.stdout, encoding="utf-8")
    if proc.stderr.strip():
        (work / f"{name}-stderr.txt").write_text(proc.stderr, encoding="utf-8")
    return proc


def _run_claude(cfg: dict, brief_path: Path, stage: Path, timeout: int, work: Path) -> dict:
    """`claude -p` with every tool removed and one turn; the prompt on stdin."""
    prompt, meta = build_prompt(brief_path, stage, cfg["window"], cfg["model"])
    argv = [cli_path("claude"), "-p", "--model", cfg["model"], "--output-format", "json", "--tools", "",
            "--max-turns", "1", "--no-session-persistence", "--strict-mcp-config"]
    if cfg["model"] != CLAUDE_FALLBACK_MODEL:
        argv += ["--fallback-model", CLAUDE_FALLBACK_MODEL]
    if cfg["effort"]:
        argv += ["--effort", cfg["effort"]]
    proc = _spawn(argv, prompt, timeout, empty_cwd(work, cfg), work, f"claude-{slug(cfg.get('member') or 'claude')}")
    if isinstance(proc, dict):
        return proc
    try:
        data = json.loads(proc.stdout.strip().splitlines()[-1]) if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        return _failed("claude output is not JSON")
    used = list((data.get("modelUsage") or {}).keys())
    accepted = (cfg["model"], CLAUDE_FALLBACK_MODEL)
    fallback_used = bool(used) and not any(m.startswith(cfg["model"]) for m in used)
    error = None
    if data.get("is_error"):
        error = str(data.get("result") or data.get("subtype"))
    elif not data.get("result"):
        error = (proc.stderr or "the reply had no content")
    elif used and not any(m.startswith(a) for a in accepted for m in used):
        error = f"model mismatch: asked {cfg['model']} (fallback {CLAUDE_FALLBACK_MODEL}), got {used}"
    usage = dict(data.get("usage") or {}, **meta, turns=data.get("num_turns"), fallback_used=fallback_used)
    return {"text": None if error else data.get("result"), "usage": usage, "model_reported": used[0] if used else None,
            "exit_code": EXIT_FAILED if error else EXIT_OK, "error": error[:500] if error else None}


def _run_codex(cfg: dict, brief_path: Path, stage: Path, timeout: int, work: Path) -> dict:
    """`codex exec` in its read-only sandbox, ephemeral, user config ignored, the prompt on
    stdin (`-`), parsed from its JSONL events."""
    prompt, meta = build_prompt(brief_path, stage, cfg["window"], cfg["model"])
    cwd = empty_cwd(work, cfg)
    argv = [cli_path("codex"), "exec", "--json", "--ephemeral", "--ignore-user-config", "--skip-git-repo-check",
            "-s", "read-only", "-C", str(cwd), "-m", cfg["model"],
            "-c", f'model_reasoning_effort="{cfg["effort"] or DEFAULT_EFFORT}"', "-c", 'approval_policy="never"',
            "-c", "analytics.enabled=false", "-c", "features.memories=false", "-"]
    proc = _spawn(argv, prompt, timeout, cwd, work, f"codex-{slug(cfg.get('member') or 'codex')}")
    if isinstance(proc, dict):
        return proc
    text, usage, errors = None, None, []
    for line in proc.stdout.splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        item = ev.get("item") if isinstance(ev.get("item"), dict) else {}
        if ev.get("type") == "item.completed" and item.get("type") == "agent_message":
            text = item.get("text") or text
        elif ev.get("type") == "turn.completed":
            usage = ev.get("usage")
        elif ev.get("type") in ("error", "turn.failed"):
            errors.append(str(ev.get("message") or ev.get("error") or ev)[:300])
    error = errors[0] if errors else (None if text else (proc.stderr.strip()[-300:] or "the reply had no content"))
    return {"text": None if error else text, "usage": dict(usage or {}, **meta), "model_reported": None,
            "exit_code": EXIT_FAILED if error else EXIT_OK, "error": error}


def _run_cursor(cfg: dict, brief_path: Path, stage: Path, timeout: int, work: Path) -> dict:
    """The Cursor agent CLI in print mode and ask mode, the prompt on stdin, one JSON
    result; the level rides on the model slug. Ask mode still writes files, so the call runs
    under a Seatbelt write-deny profile, and Cursor's config file is restored afterwards."""
    prompt, meta = build_prompt(brief_path, stage, cfg["window"], cfg["model"])
    model = cfg["model"] if not cfg["effort"] else f"{cfg['model']}-{cfg['effort']}"
    cwd = empty_cwd(work, cfg)
    argv = sandboxed([cli_path("agent"), "-p", "--output-format", "json", "--model", model, "--trust",
                      "--workspace", str(cwd), "--mode", "ask"], write_sandbox_profile(work, "cursor", cwd))
    with CursorConfigLock(timeout) as lock:
        before = snapshot_cursor_config()
        try:
            proc = _spawn(argv, prompt, max(30, int(timeout - lock.waited)), cwd, work,
                          f"cursor-{slug(cfg.get('member') or 'cursor')}")
        finally:
            cli_config = restore_cursor_config(before)
            cli_config["lock_wait_s"] = lock.waited
    if isinstance(proc, dict):
        return proc
    meta = dict(meta, cli_config=cli_config)
    data = {}
    for line in reversed(proc.stdout.strip().splitlines()):
        try:
            data = json.loads(line)
            break
        except json.JSONDecodeError:
            continue
    if not data:
        return _failed(proc.stderr.strip()[-300:] or "cursor output is not JSON")
    error = None
    if data.get("is_error"):
        error = str(data.get("result") or data.get("subtype"))
    elif not data.get("result"):
        error = "the reply had no content"
    return {"text": None if error else data.get("result"), "usage": dict(data.get("usage") or {}, **meta), "model_reported": None,
            "exit_code": EXIT_FAILED if error else EXIT_OK, "error": error[:500] if error else None}


def _run_agy(cfg: dict, brief_path: Path, stage: Path, timeout: int, work: Path) -> dict:
    """The Antigravity CLI in print mode and plan mode, one JSON result, under a Seatbelt
    write-deny profile. It takes the prompt on argv only, so the prompt is capped by bytes."""
    prompt, meta = build_prompt(brief_path, stage, cfg["window"], cfg["model"])
    if len(prompt.encode()) > AGY_MAX_PROMPT_BYTES:
        raise ReviewError(f"the prompt is {len(prompt.encode())} bytes and agy takes it on argv, capped at "
                          f"{AGY_MAX_PROMPT_BYTES}; split the review", EXIT_FAILED)
    cwd = empty_cwd(work, cfg)
    argv = [cli_path("agy"), "--output-format", "json", "--model", cfg["model"], "--print-timeout", "0", "--mode", "plan"]
    if cfg["effort"]:
        argv += ["--effort", cfg["effort"]]
    argv += ["-p", prompt]
    argv = sandboxed(argv, write_sandbox_profile(work, "antigravity", cwd))
    proc = _spawn(argv, None, timeout, cwd, work, f"agy-{slug(cfg.get('member') or 'antigravity')}")
    if isinstance(proc, dict):
        return proc
    data = {}
    for line in reversed(proc.stdout.strip().splitlines()):
        try:
            data = json.loads(line)
            break
        except json.JSONDecodeError:
            continue
    if not data:
        return _failed(proc.stderr.strip()[-300:] or "agy output is not JSON")
    error = None
    if data.get("status") not in (None, "SUCCESS"):
        error = f"status {data.get('status')}: {str(data.get('response') or '')[:200]}"
    elif not data.get("response"):
        error = "the reply had no content"
    usage = dict(data.get("usage") or {}, **meta, turns=data.get("num_turns"))
    return {"text": None if error else data.get("response"), "usage": usage, "model_reported": None,
            "exit_code": EXIT_FAILED if error else EXIT_OK, "error": error}


def _run_ollama(cfg: dict, brief_path: Path, stage: Path, timeout: int, work: Path) -> dict:
    tag = cfg["model"]
    show = ollama_request("POST", "/api/show", {"model": tag}, 30)
    think = think_setting(cfg["effort"], show, tag)
    ctx = context_length(show)
    user, meta = build_prompt(brief_path, stage, ctx, tag)
    n, est = meta["files_inlined"], meta["estimated_prompt_tokens"]
    system = TOOL_NOTE
    # num_predict bounds thinking plus content, so a model that loops in its reasoning stops
    # at a known cost instead of running to the deadline.
    body = {"model": tag, "options": {"temperature": 0, "num_predict": OLLAMA_MAX_OUTPUT_TOKENS},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    if think is not None:
        body["think"] = think
    # One absolute deadline for the whole call: both attempts and the pause between them
    # share it, so a retry never extends `timeout`.
    attempts, retried_after = 0, None
    deadline = time.monotonic() + timeout
    name = slug(cfg.get("member") or tag)

    def keep_partial(partial: dict | None) -> str:
        """A failed call's text, written beside the run as partial-<name>.md (and its
        thinking), so what the model said is on disk even when the call does not count."""
        if not partial or not (partial.get("content") or partial.get("thinking")):
            return ""
        path = work / f"partial-{name}.md"
        path.write_text(scan_output(partial.get("content") or "")[0], encoding="utf-8")   # scanned like any output
        if partial.get("thinking"):
            (work / f"partial-thinking-{name}.md").write_text(scan_output(partial["thinking"])[0], encoding="utf-8")
        return f"; {len(partial.get('content') or '')} characters of content kept at {path}"

    while True:
        attempts += 1
        try:
            data = ollama_chat_stream(body, deadline)
            break
        except ReviewError as exc:
            left = deadline - time.monotonic()
            if attempts == 1 and _retryable(exc) and left > OLLAMA_RETRY_PAUSE_S + 30:
                retried_after = str(exc)[:300]
                time.sleep(OLLAMA_RETRY_PAUSE_S)
                continue
            kept = keep_partial(exc.partial)
            if attempts > 1:
                raise ReviewError(f"attempt {attempts} of {attempts} failed: {exc}{kept}; attempt 1 failed: {retried_after}",
                                  exc.code, kind=exc.kind, status=exc.status)
            raise ReviewError(f"{exc}{kept}", exc.code, kind=exc.kind, status=exc.status)
    msg = data.get("message") if isinstance(data.get("message"), dict) else {}
    text = msg.get("content") or None
    thinking_path = None
    if msg.get("thinking"):
        thinking_path = work / f"thinking-{name}.md"
        thinking_path.write_text(str(msg["thinking"]), encoding="utf-8")
    usage = {k: data.get(k) for k in ("prompt_eval_count", "eval_count", "prompt_eval_cached_count", "total_duration")}
    usage.update({"think": think, "context_length": ctx, "estimated_prompt_tokens": est, "files_inlined": n,
                  "attempts": attempts, "retried_after": retried_after, "truncated": bool(data.get("truncated"))})
    reported = data.get("model")
    error = None
    if data.get("truncated"):
        kept = keep_partial({"content": text or "", "thinking": ""})
        error = f"the reply passed {OLLAMA_MAX_TEXT} characters of text and was cut{kept}"
    elif not text:
        loop = thinking_loop(str(msg.get("thinking") or ""))
        spent = data.get("eval_count")
        if loop:
            error = (f"the model looped in its thinking (one line repeated {loop} times) and produced no content"
                     + (f"; {spent} tokens generated" if isinstance(spent, int) else ""))
        elif isinstance(spent, int) and spent >= OLLAMA_MAX_OUTPUT_TOKENS:
            error = f"the model spent its {OLLAMA_MAX_OUTPUT_TOKENS}-token output budget thinking and produced no content"
        else:
            error = "the reply had no content"
        usage["thinking_loop"] = loop
    # The daemon answers with the tag minus its `:cloud` suffix.
    elif reported and reported not in (tag, tag[: -len(":cloud")]):
        error = f"model mismatch: asked {tag}, got {reported}"
    return {"text": None if error else text, "usage": usage, "model_reported": reported,
            "exit_code": EXIT_FAILED if error else EXIT_OK, "error": error,
            "thinking": str(thinking_path) if thinking_path else None}


# ---------------------------------------------------------------- staging ---

def validate_files(files: list[str], root: str | None) -> tuple[list[Path], list[str]]:
    """Resolve the named files and their relative paths, refusing symlinks, directories,
    missing and oversized files and anything outside --root, before anything is created."""
    if not files:
        raise ReviewError("at least one --file is required")
    paths = []
    for raw in files:
        p = Path(raw).expanduser()
        if p.is_symlink():
            raise ReviewError(f"{raw} is a symlink; name the real file")
        p = p.resolve()
        if not p.is_file():
            raise ReviewError(f"{raw} is not a file")
        if p.stat().st_size > MAX_FILE_BYTES:
            raise ReviewError(f"{raw} is over {MAX_FILE_BYTES // (1024 * 1024)} MB")
        paths.append(p)
    base = Path(root).expanduser().resolve() if root else Path(os.path.commonpath([str(p.parent) for p in paths]))
    rels = []
    for p, raw in zip(paths, files):
        try:
            rel = p.relative_to(base)
        except ValueError:
            raise ReviewError(f"{p} is outside --root {base}")
        # Every component below the base, not only the last: a symlinked parent inside the
        # tree would be resolved silently. System links above the base (/var on macOS) are fine.
        cur = Path(raw).expanduser()
        cur = cur if cur.is_absolute() else Path.cwd() / cur
        walk = Path(os.path.normpath(cur))
        probe = walk
        for _ in rel.parts:
            if probe.is_symlink():
                raise ReviewError(f"{raw} crosses a symlink at {probe}; name the real path")
            probe = probe.parent
        rels.append(rel.as_posix())
    if len(set(rels)) != len(rels):
        raise ReviewError("two files map to the same relative path")
    return paths, rels


SANITIZE_SCRIPT = SKILLS_ROOT / "sanitize" / "scripts" / "sanitize.py"
REDACTION_NOTE = ("Placeholders such as [SECRET], [TERM], [EMAIL] or [HOME] mark text removed before "
                  "you saw the files. Treat them as redactions, not as defects to report.")


def stage_files(paths: list[Path], rels: list[str], out: Path, sanitize: bool = True) -> tuple[Path, dict]:
    """Stage the validated files, and nothing else, into out/stage as a one-commit git repo.

    With `sanitize` on, the only copy that ever exists outside the source repo is the clean
    one: each file goes through `sanitize copy` straight into its stage path, the per-file
    reports are folded into counts and removed from the stage, and a hit on the term list
    refuses the run before anything is sent anywhere. Returns (stage, sanitize record)."""
    stage = out / "stage"
    stage.mkdir(parents=True)
    record: dict = {"on": sanitize}
    if sanitize:
        if not SANITIZE_SCRIPT.exists():
            raise ReviewError(f"the sanitize skill is missing at {SANITIZE_SCRIPT}; pass --no-sanitize to stage the files as they are")
        removed: dict = {}
        env = {k: os.environ[k] for k in (*ENV_ALLOW, "IDENTIFIER_TERMS_FILE") if k in os.environ}
        for p, rel in zip(paths, rels):
            dst = stage / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            proc = subprocess.run([sys.executable, str(SANITIZE_SCRIPT), "copy", str(p), "--out", str(dst)],
                                  capture_output=True, text=True, timeout=600, env=env)
            report_path = Path(str(dst) + ".sanitize-report.json")
            if proc.returncode != 0:
                raise ReviewError(f"sanitize refused {rel}: {(proc.stderr or proc.stdout).strip()[-300:]}")
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                raise ReviewError(f"sanitize wrote no report for {rel}")
            report_path.unlink()
            if report.get("skipped"):
                why = ", ".join(s.get("why", "?") for s in report["skipped"])
                raise ReviewError(f"sanitize skipped {rel} ({why}); the stage would be missing a named file")
            counts = report.get("removed") or {}
            for k, v in counts.items():
                removed[k] = removed.get(k, 0) + v
            hits = {k: v for k, v in counts.items() if k.split("-")[0] in ("term", "ban", "path") and v}
            if hits:
                raise ReviewError(f"{rel} holds a protected term ({', '.join(f'{k} {v}' for k, v in sorted(hits.items()))}); "
                                  "nothing was sent. Review the file or drop it from the list")
            if not dst.exists():
                raise ReviewError(f"sanitize wrote nothing for {rel}")
            os.chmod(dst, 0o600)
        record.update({"files": len(paths), "removed": dict(sorted(removed.items()))})
    else:
        for p, rel in zip(paths, rels):
            dst = stage / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, dst)
            os.chmod(dst, 0o600)
    git(["init", "-q"], stage)
    git(["add", "-A"], stage)
    git(["commit", "-q", "-m", "files under review"], stage)
    return stage, record


# ---------------------------------------------------------------- runners ---

def run_harness(cfg: dict, brief_path: Path, stage: Path, timeout: int, work: Path) -> dict:
    """Run one harness read-only against the staging repo. Returns
    {text, usage, model_reported, exit_code, error, elapsed_s, harness, model, effort}. Never raises."""
    started = time.time()
    try:
        if fake_bin():
            res = _run_fake(cfg, brief_path, stage)
            res["fake_bin"] = fake_bin()
        else:
            runner = {"claude": _run_claude, "codex": _run_codex, "cursor": _run_cursor,
                      "antigravity": _run_agy, "ollama": _run_ollama}[cfg["runner"]]
            res = runner(cfg, brief_path, stage, timeout, work)
    except Exception as exc:  # a harness failing must not take the caller down
        res = {"text": None, "usage": None, "model_reported": None, "exit_code": EXIT_FAILED, "error": str(exc)[:500]}
    if res.get("text"):
        clean, scan = scan_output(res["text"])
        res["scan"] = scan
        if scan["binary"]:
            res.update(text=None, exit_code=EXIT_FAILED, error="the output holds NUL bytes and is not text")
        else:
            res["text"] = clean
    res.update({"elapsed_s": round(time.time() - started, 1), "harness": cfg["harness"],
                "model": cfg["model"], "effort": cfg["effort"]})
    return res


def _run_fake(cfg: dict, brief_path: Path, stage: Path) -> dict:
    proc = subprocess.run([fake_bin(), cfg.get("member") or cfg["harness"], str(brief_path), str(stage),
                           cfg["model"], cfg["effort"] or ""],
                          capture_output=True, text=True, timeout=60, env=child_env())
    data = json.loads(proc.stdout) if proc.stdout.strip() else {}
    return {"text": data.get("text"), "usage": data.get("usage"), "model_reported": data.get("model"),
            "exit_code": data.get("exit_code", proc.returncode), "error": data.get("error")}


def extract_json_blocks(text: str | None) -> list[dict]:
    """Every fenced JSON object in a message, in order. Untrusted output; the caller
    reads them as claims."""
    out: list[dict] = []
    for block in FENCED_JSON.findall(text or ""):
        try:
            value = json.loads(block)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            out.append(value)
    return out


def extract_json_block(text: str | None, key: str | None = None) -> dict | None:
    """The last fenced JSON object in a message, or with key, the last one holding that
    key; None when there is none. A harness may append its own summary block after the
    one the caller asked for, so the key, not the position, picks it."""
    blocks = extract_json_blocks(text)
    if key is not None:
        blocks = [b for b in blocks if key in b]
    return blocks[-1] if blocks else None


# ---------------------------------------------------------------- commands ---

def cmd_run(a: argparse.Namespace) -> int:
    cfg = resolve(a.harness, a.model, a.effort, allow_cloud=a.allow_cloud)
    why = availability(cfg)
    if why:
        raise ReviewError(f"{cfg['harness']} is unavailable here: {why}", EXIT_UNAVAILABLE)
    brief = sys.stdin.read() if a.brief == "-" else Path(a.brief).read_text(encoding="utf-8")
    if not brief.strip():
        raise ReviewError("the brief is empty")
    timeout = int(a.timeout)
    if not 60 <= timeout <= MAX_TIMEOUT:
        raise ReviewError(f"--timeout must be between 60 and {MAX_TIMEOUT}")
    paths, rels = validate_files(a.file, a.root)
    topic = a.topic or ("stdin" if a.brief == "-" else Path(a.brief).stem)
    topic = slug(topic)

    run_id = _dt.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)
    out = Path(a.out).expanduser().resolve() if a.out else state_dir() / run_id
    if out.exists() and any(out.iterdir()):
        raise ReviewError(f"output dir {out} is not empty")
    out.mkdir(parents=True, exist_ok=True)
    os.chmod(out, 0o700)
    start = Path(a.root).expanduser().resolve() if a.root else paths[0].parent
    rdir, rule = reviews_dir(start, a.reviews_dir)
    if not ensure_writable(rdir):
        print(f"  reviews dir {rdir} is not writable; the review stays in the run folder")
        rdir, rule = out, "fallback-run-folder"
    try:
        stage, sanitized = stage_files(paths, rels, out, sanitize=not a.no_sanitize)
    except ReviewError:
        shutil.rmtree(out, ignore_errors=True)
        raise
    (out / "files.json").write_text(json.dumps(rels, indent=1), encoding="utf-8")
    full = render((REFS / "brief.md").read_text(encoding="utf-8"), BRIEF=brief.strip(),
                  FILES="\n".join(f"- {r}" for r in rels), TOOLS=TOOL_NOTES[cfg["runner"]],
                  REDACTION=REDACTION_NOTE if sanitized["on"] else "")
    (out / "brief.md").write_text(full, encoding="utf-8")

    print(f"agent-review {run_id}: {cfg['harness']} {cfg['model']}"
          f"{' effort ' + cfg['effort'] if cfg['effort'] else ''}, {len(rels)} files, out {out}")
    res = run_harness(cfg, out / "brief.md", stage, timeout, out)
    review = None
    if res.get("text"):
        review = rdir / (unique_path(rdir, review_stem("review", cfg["harness"], cfg["model"], topic)).name + ".md")
        text, stripped = strip_invisible(res["text"])
        try:
            write_new(review, text.encode("utf-8"))
            res["invisible_stripped"] = stripped + (res.get("scan") or {}).get("invisible", 0)
        except ReviewError as exc:
            review, res["text"] = None, None
            res.update(error=str(exc), exit_code=EXIT_FAILED)
    run = {"run_id": run_id, "files": rels, "brief": str(out / "brief.md"), "topic": topic, "sanitize": sanitized,
           "review": str(review) if review else None, "reviews_dir": str(rdir), "reviews_dir_rule": rule,
           "test_mode": test_mode(), "fake_bin": res.get("fake_bin"),
           **{k: v for k, v in res.items() if k != "text"}}
    (out / "run.json").write_text(json.dumps(run, indent=1), encoding="utf-8")
    state = "ok" if res.get("text") else f"FAILED ({res.get('error')})"
    print(f"  {res['elapsed_s']:>7}s  {state}{scan_note(res.get('scan'))}")
    print(f"  review : {review or '(none)'}")
    print(f"  run    : {out / 'run.json'}")
    return EXIT_OK if res.get("text") and res.get("exit_code") == EXIT_OK else EXIT_FAILED


def cmd_harnesses(a: argparse.Namespace) -> int:
    print(f"{'harness':<12} {'runner':<18} {'default model':<18} {'levels':<40} {'effort is passed as':<36} available")
    print("every harness: one headless call, one turn, the clean files inlined with line numbers, no tool grant, an empty cwd")
    how = {"claude": "claude -p --effort", "codex": "model_reasoning_effort config key",
           "cursor": "a suffix of the model slug", "antigravity": "agy --effort, or a level slug",
           "ollama": "think, from the tag's /api/show map"}
    for name, cfg in HARNESSES.items():
        try:
            why = availability(dict(cfg, harness=name))
        except ReviewError as exc:
            why = str(exc)
        print(f"{name:<12} {cfg['runner']:<18} {cfg['model'] or '(a :cloud tag)':<18} {', '.join(cfg['levels']):<40} "
              f"{how[cfg['runner']]:<36} {'yes' if why is None else 'no: ' + why}")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="agent_review.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="one harness reviews the named files read-only")
    r.add_argument("--harness", required=True, help=", ".join(HARNESSES))
    r.add_argument("--model", default=None, help="model for the harness; default per harness")
    r.add_argument("--effort", default=None, help=f"reasoning level, default {DEFAULT_EFFORT}; dropped when the model names its level; for ollama, mapped onto the tag's think values")
    r.add_argument("--allow-cloud", action="store_true", help="required for ollama: the tag is served by Ollama's cloud and the files are sent to it")
    r.add_argument("--no-sanitize", action="store_true", help="stage the files as they are; by default each goes through the sanitize skill into the stage, and a term hit refuses the run")
    r.add_argument("--brief", required=True, help="what to review and what a complete answer holds; a file, or - for stdin")
    r.add_argument("--file", action="append", required=True, help="a file the harness may read; repeatable")
    r.add_argument("--root", help="directory the files are relative to (default: their common parent)")
    r.add_argument("--out", help="run folder for the staging repo, the brief and run.json (must be empty); default: a new run under the state dir")
    r.add_argument("--topic", help="slug in the review's file name; default: the brief file's stem")
    r.add_argument("--reviews-dir", help="where the review lands; default: tasks/reviews/ under the nearest git root with a tasks/ folder, else <git-root>/reviews/, else reviews/ beside the files")
    r.add_argument("--timeout", default=DEFAULT_TIMEOUT, help=f"seconds, max {MAX_TIMEOUT}")
    r.set_defaults(fn=cmd_run)
    h = sub.add_parser("harnesses", help="print the harness table")
    h.set_defaults(fn=cmd_harnesses)
    a = ap.parse_args(argv)
    try:
        return a.fn(a)
    except ReviewError as e:
        print(f"agent-review: {e}", file=sys.stderr)
        return e.code
    except subprocess.CalledProcessError as e:
        print(f"agent-review: {' '.join(e.cmd)} failed:\n{(e.stderr or '').strip()}", file=sys.stderr)
        return EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
