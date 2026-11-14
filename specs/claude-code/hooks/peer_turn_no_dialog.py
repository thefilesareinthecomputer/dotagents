#!/usr/bin/env python3
"""PreToolUse on the dialog tools (AskUserQuestion, ExitPlanMode) - blocks.

A dialog opened on a turn the user did not start lands on top of whatever the
user is typing or dictating at that moment, and the text in the prompt is lost.
Turns start without the user all the time: another session's message, a
subagent's hand-back, a background task finishing.

The hook finds what started the current turn: the most recent main-thread row
in the transcript that names its origin. Claude Code marks each such row with
`origin.kind` - `human` for the person, `peer` for another session,
`task-notification` for a background task. Any origin other than `human` means
the user is not at the prompt waiting for this turn, so the dialog is denied
and the model is told to answer in plain text instead. A row with no `origin`
field (an older harness) is judged by its opening text.

Fail-open by construction: a missing transcript, a malformed line or no row
with an origin all exit 0 with no output.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

NOT_HUMAN_OPENINGS = (
    "Another Claude session sent a message",
    "<cross-session-message",
    "<agent-message",
    "<task-notification>",
)

REASON = (
    "This turn was started by {origin}, not by the user. A dialog opened now "
    "replaces whatever the user is typing or dictating, and that text is lost. "
    "Do not retry the dialog on this turn: answer a peer with SendMessage, and "
    "put any question for the user in your plain-text reply, so the user answers "
    "it on their own turn."
)


def row_text(row: dict) -> str:
    content = (row.get("message") or {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content
                         if isinstance(b, dict) and b.get("type") == "text")
    return ""


def turn_origin(transcript: Path) -> str:
    """'human', another origin kind, or '' when the transcript names none."""
    origin = ""
    with transcript.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line or '"user"' not in line:  # only user rows matter; most lines skip the parse
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if not isinstance(row, dict) or row.get("type") != "user" or row.get("isSidechain"):
                continue
            kind = (row.get("origin") or {}).get("kind") if isinstance(row.get("origin"), dict) else None
            if isinstance(kind, str) and kind:
                origin = kind
                continue
            text = row_text(row).lstrip()
            if text.startswith(NOT_HUMAN_OPENINGS):
                origin = "peer"
    return origin


def describe(origin: str) -> str:
    return {
        "peer": "another session's message",
        "task-notification": "a background task finishing",
    }.get(origin, f"a '{origin}' event")


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(payload, dict) or payload.get("hook_event_name") != "PreToolUse":
        return 0
    path = payload.get("transcript_path")
    if not path:
        return 0
    try:
        origin = turn_origin(Path(path))
    except OSError:
        return 0
    if origin in ("", "human"):
        return 0
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": REASON.format(origin=describe(origin)),
        }
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
