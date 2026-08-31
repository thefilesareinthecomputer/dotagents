#!/usr/bin/env python3
"""Distil a Claude Code session transcript into the last N projected parts.

A raw tail does not work. Transcript lines are JSONL and a single tool result
can run to hundreds of KB, so a line-count tail is unpredictable in bytes and a
byte-count tail starts mid-line. This projects every `user` and `assistant`
event to (role, kind, text), caps each part, keeps the last N, and enforces a
hard byte ceiling by dropping the oldest parts first.

Stdlib only. Reads the transcript, writes to stdout, never writes to disk.

Usage:
    distil_transcript.py [TRANSCRIPT] [--session-id ID] [--n 300]
                         [--cap 500] [--max-bytes 80000]

With no positional path the transcript is derived: transcripts live at
~/.claude/projects/<sanitized-cwd>/<session-id>.jsonl where sanitized-cwd is the
absolute working directory with `/` and `.` both replaced by `-`. Without
--session-id the newest *.jsonl in that project directory is used.

Tunable: DISTIL_TRANSCRIPT_BYTES (default 80000), following the
READ_ADVISORY_BYTES convention. The --max-bytes flag wins over the env var. The
ceiling covers the parts and the header together; the header itself is always
emitted, so a ceiling set below its size yields the header alone.
"""

import argparse
import json
import os
import sys
from collections import deque

# The event types that carry no review signal, per the transcript survey.
NOISE_TYPES = frozenset(
    (
        "mode",
        "permission-mode",
        "ai-title",
        "last-prompt",
        "file-history-snapshot",
        "queue-operation",
        "attachment",
    )
)

# Only these two carry signal. Anything else, noise or unknown, is skipped.
SIGNAL_TYPES = frozenset(("user", "assistant"))

DEFAULT_N = 300
DEFAULT_CAP = 500
DEFAULT_MAX_BYTES = 80000


def sanitize_cwd(path):
    """Absolute path to the project-directory name Claude Code uses."""
    return path.replace("/", "-").replace(".", "-")


def project_dir(cwd=None, home=None):
    home = home or os.path.expanduser("~")
    cwd = cwd or os.getcwd()
    return os.path.join(home, ".claude", "projects", sanitize_cwd(os.path.abspath(cwd)))


def resolve_transcript(path=None, session_id=None, cwd=None, home=None):
    """Positional path wins, then --session-id, then the newest *.jsonl."""
    if path:
        return path
    directory = project_dir(cwd=cwd, home=home)
    if session_id:
        return os.path.join(directory, session_id + ".jsonl")
    try:
        entries = [
            os.path.join(directory, name)
            for name in os.listdir(directory)
            if name.endswith(".jsonl")
        ]
    except OSError:
        return None
    if not entries:
        return None
    return max(entries, key=lambda p: os.path.getmtime(p))


def _blocks(message):
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if isinstance(content, list):
        return [b for b in content if isinstance(b, dict)]
    return []


def _render_block(block):
    """Return (kind, text) or None for a block type with nothing to show."""
    kind = block.get("type")
    if kind == "text":
        return "text", block.get("text") or ""
    if kind == "thinking":
        return "text", block.get("thinking") or ""
    if kind == "tool_use":
        name = block.get("name") or "?"
        try:
            args = json.dumps(block.get("input"), ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError):
            args = str(block.get("input"))
        return "tool_call", "{} {}".format(name, args)
    if kind == "tool_result":
        content = block.get("content")
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            text = " ".join(
                str(e.get("text", "")) for e in content if isinstance(e, dict)
            )
        elif content is None:
            text = ""
        else:
            text = str(content)
        if block.get("is_error"):
            text = "[error] " + text
        return "tool_result", text
    return None


def _cap(text, cap):
    text = text.strip()
    if len(text) <= cap:
        return text
    return "{} ...[+{} chars]".format(text[:cap], len(text) - cap)


def iter_parts(lines, cap=DEFAULT_CAP):
    """Yield (ordinal, role, kind, text) for each projected part.

    A malformed or truncated line is skipped, never fatal; it yields the
    sentinel ("malformed", None, None, None) so the caller can count it.
    """
    ordinal = 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except (ValueError, UnicodeDecodeError):
            yield ("malformed", None, None, None)
            continue
        if not isinstance(event, dict):
            yield ("malformed", None, None, None)
            continue
        etype = event.get("type")
        if etype not in SIGNAL_TYPES:
            continue
        for block in _blocks(event.get("message")):
            rendered = _render_block(block)
            if rendered is None:
                continue
            kind, text = rendered
            text = _cap(text, cap)
            if not text:
                continue
            ordinal += 1
            yield (ordinal, etype, kind, text)


def _render_part(part):
    ordinal, role, kind, text = part
    return "[#{} {} {}]\n{}\n".format(ordinal, role, kind, text)


def distil(lines, n=DEFAULT_N, cap=DEFAULT_CAP, max_bytes=DEFAULT_MAX_BYTES,
           source="-"):
    window = deque(maxlen=max(1, n))
    total = 0
    malformed = 0
    for part in iter_parts(lines, cap=cap):
        if part[0] == "malformed":
            malformed += 1
            continue
        total = part[0]
        window.append(part)

    rendered = [(p[0], _render_part(p)) for p in window]

    header_lines = ["# transcript: {}".format(source)]
    if malformed:
        header_lines.append("# skipped {} malformed lines".format(malformed))

    def header(first, last, dropped):
        head = list(header_lines)
        if rendered:
            head.insert(
                1,
                "# parts {}-{} of {} (cap {} chars/part)".format(
                    first, last, total, cap
                ),
            )
        else:
            head.insert(1, "# no parts (cap {} chars/part)".format(cap))
        if dropped:
            head.append(
                "# byte ceiling {}: dropped {} oldest parts".format(max_bytes, dropped)
            )
        return "\n".join(head) + "\n\n"

    dropped = 0
    while True:
        first = rendered[0][0] if rendered else 0
        last = rendered[-1][0] if rendered else 0
        head = header(first, last, dropped)
        size = len(head.encode("utf-8")) + sum(
            len(body.encode("utf-8")) for _, body in rendered
        )
        if size <= max_bytes or not rendered:
            return head + "".join(body for _, body in rendered)
        rendered.pop(0)
        dropped += 1


def _env_int(name, default):
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Distil a Claude Code transcript to its last N projected parts."
    )
    parser.add_argument("transcript", nargs="?", help="path to the .jsonl transcript")
    parser.add_argument("--session-id", help="session id, used to derive the path")
    parser.add_argument("--n", type=int, default=DEFAULT_N, help="parts to keep")
    parser.add_argument("--cap", type=int, default=DEFAULT_CAP, help="chars per part")
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=None,
        help="hard output ceiling (env DISTIL_TRANSCRIPT_BYTES)",
    )
    args = parser.parse_args(argv)

    max_bytes = args.max_bytes
    if max_bytes is None:
        max_bytes = _env_int("DISTIL_TRANSCRIPT_BYTES", DEFAULT_MAX_BYTES)

    path = resolve_transcript(args.transcript, args.session_id)
    if not path:
        sys.stderr.write(
            "no transcript found under {}\n".format(project_dir())
        )
        return 2
    try:
        handle = open(path, "r", encoding="utf-8", errors="replace")
    except OSError as exc:
        sys.stderr.write("cannot read {}: {}\n".format(path, exc))
        return 2
    with handle:
        sys.stdout.write(
            distil(handle, n=args.n, cap=args.cap, max_bytes=max_bytes, source=path)
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
