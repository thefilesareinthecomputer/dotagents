#!/usr/bin/env python3
"""SessionStart + UserPromptSubmit - advisory only, NEVER blocks.

Keeps chat replies short by measurement rather than by standing instruction.

SessionStart: injects one line telling the model that cmon is enforced this
session and what the threshold is, so the first long reply is less likely, not
just the second.

UserPromptSubmit: reads the model's previous reply from the transcript, counts
the words outside fenced code blocks, and if the count is over the threshold
injects one line naming the count and pointing at the cmon rules. The model
decides: compress, or carry on because the user asked for that length (a spec,
a plan, a walkthrough). Under the threshold the hook exits silently.

Fail-open by construction: a missing transcript, a malformed line, a reply
with no text - every path exits 0 with no output. Cheap by construction: one
pass over the transcript, stdlib only.

Tunable: CMON_WORDS (default 150).
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

DEFAULT_WORDS = 150
FENCE = re.compile(r"```.*?```", re.DOTALL)


def threshold() -> int:
    try:
        return max(1, int(os.environ.get("CMON_WORDS", DEFAULT_WORDS)))
    except ValueError:
        return DEFAULT_WORDS


def is_human_prompt(row: dict) -> bool:
    """A user row typed by the person, not a tool result returning to the model."""
    if row.get("type") != "user":
        return False
    content = (row.get("message") or {}).get("content")
    if isinstance(content, str):
        return True
    if isinstance(content, list):
        return any(isinstance(b, dict) and b.get("type") == "text" for b in content)
    return False


def assistant_text(row: dict) -> str:
    if row.get("type") != "assistant":
        return ""
    content = (row.get("message") or {}).get("content")
    if not isinstance(content, list):
        return ""
    return "\n".join(b.get("text", "") for b in content
                     if isinstance(b, dict) and b.get("type") == "text")


def last_reply(transcript: Path) -> str:
    """Text of the model's most recent completed turn, main thread only.

    Turns are segmented by human prompts. The prompt now being submitted may
    or may not already be in the file, so the last non-empty segment is the
    one that counts either way.
    """
    segments: list[list[str]] = [[]]
    with transcript.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if not isinstance(row, dict) or row.get("isSidechain"):
                continue
            if is_human_prompt(row):
                segments.append([])
                continue
            text = assistant_text(row)
            if text:
                segments[-1].append(text)
    for seg in reversed(segments):
        if seg:
            return "\n".join(seg)
    return ""


def word_count(text: str) -> int:
    return len(FENCE.sub(" ", text).split())


def emit(event: str, context: str) -> None:
    print(json.dumps({
        "suppressOutput": True,
        "hookSpecificOutput": {"hookEventName": event, "additionalContext": context},
    }))


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(payload, dict):
        return 0
    event = payload.get("hook_event_name", "")
    limit = threshold()

    if event == "SessionStart":
        emit(event, (
            f"cmon is enforced this session: a chat reply over {limit} words outside "
            "code fences gets a nudge on the user's next message. Lead with the answer, "
            "keep only the support that changes what the reader does next, and stop - "
            "unless the user asked for that length. Rules: /cmon."
        ))
        return 0

    if event != "UserPromptSubmit":
        return 0
    path = payload.get("transcript_path")
    if not path:
        return 0
    try:
        text = last_reply(Path(path))
    except OSError:
        return 0
    count = word_count(text)
    if count <= limit:
        return 0
    emit(event, (
        f"Previous reply was {count} words outside code fences (limit {limit}). "
        "Apply cmon to this reply unless the user asked for that length: answer "
        "first, support that earns its place, stop."
    ))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # advisory hook: never block on its own failure
        sys.exit(0)
