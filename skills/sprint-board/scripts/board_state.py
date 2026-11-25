#!/usr/bin/env python3
"""Set a story's State and record the move in its COMMENTS block.

EXECUTE this script; do not read it into context. It is a neutral stamp: it knows
no state values and checks no moves, so the vocabulary and any rules about which
move may follow which stay with the board and with whoever calls it.

    board_state.py BOARD.md STORY-ID STATE --by NAME [--tick | --untick]

One call rewrites the story's `- State:` line (adding one after the metadata lines
when there is none), appends `- <UTC time> <old> -> <new> by <name>` to COMMENTS
(adding the block after the story's last block when there is none), and ticks or
unticks the title box only when told to. Setting the current state again changes
nothing. The result is linted, written to a temporary file beside the board and
renamed over it, so a reader never sees a half-written board.

Exit 0 changed or unchanged, 1 refused (unknown story, a STATE or NAME that is not
one printable line, a clock earlier than the story's last state line, an edit that
adds a lint error) with the file untouched, 2 usage error, a symlinked board, or a
board that cannot be read or written. No lock: a board has one writer.
"""

import argparse
import os
import re
import sys
import tempfile
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import board_lint

STAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
# The time that opens a state line in COMMENTS. Only the time is read back, and the
# pattern is anchored and fixed-width so a hostile line costs linear time.
STAMP_RE = re.compile(r"^-\s(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ)\s")
# A value that could start a line, open or close a fence, or hide text: anything
# str.splitlines() splits on, and control, format and separator characters.
UNSAFE_CATEGORIES = {"Cc", "Cf", "Zl", "Zp"}
METADATA_RES = (board_lint.TITLE_RE, board_lint.PARENT_RE, board_lint.DEPENDS_RE,
                board_lint.OWNER_RE, board_lint.STATE_RE)
FENCE = "````"


class StateError(ValueError):
    """The change was refused; the board is left as it was."""


def set_state(text, story, state, by, now, tick=None):
    """Return (new_text, changed). Raise StateError to refuse.

    tick: True ticks the title box, False unticks it, None leaves it alone.
    """
    state, by = check_value("state", state), check_value("--by", by)
    if "->" in state or re.search(r"\sby\s", state):
        raise StateError(f"state {state!r} would make the COMMENTS line ambiguous")

    items, parse_findings = board_lint.parse(text)
    matches = board_lint.find_stories(items, story)
    if len(matches) != 1:
        raise StateError(f"{story.strip()} is {'not on' if not matches else 'ambiguous on'} "
                         f"this board")
    it = matches[0]
    old = it.state
    if old == state:
        return text, False

    stamp = now.astimezone(timezone.utc).strftime(STAMP_FORMAT)
    comments = it.blocks.get("COMMENTS")
    if comments is not None:
        if comments["fence"] is None or comments["end"] is None:
            raise StateError(f"{it.ref} COMMENTS block is not a closed fence")
        last = [m.group(1) for _, t in comments["body"] for m in [STAMP_RE.match(t)] if m]
        if last and stamp < last[-1]:
            raise StateError(f"the clock reads {stamp}, earlier than {it.ref}'s last "
                             f"state line at {last[-1]}")

    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines(keepends=True)
    record = f"- {stamp} {old or '(none)'} -> {state} by {by}{nl}"

    # Edits run bottom-up so each index is still true when it is used.
    if comments is not None:
        lines.insert(comments["end"] - 1, record)
    else:
        ends = [b["end"] for b in it.blocks.values() if b["end"]]
        at = max(ends) if ends else metadata_end(lines, it)
        if at and not lines[at - 1].endswith(("\n", "\r")):
            lines[at - 1] += nl
        lines[at:at] = [nl, f"**COMMENTS**{nl}", f"{FENCE}{nl}", record, f"{FENCE}{nl}"]

    if tick is not None:
        t = title_index(lines, it)
        if t is None:
            raise StateError(f"{it.ref} has no title line to tick")
        lines[t] = re.sub(r"\[[ xX]\]", "[x]" if tick else "[ ]", lines[t], count=1)

    state_line = f"- State: {state}"
    if it.state_line:
        i = it.state_line - 1
        lines[i] = state_line + lines[i][len(bare(lines[i])):]
    else:
        lines.insert(metadata_end(lines, it), state_line + nl)

    out = "".join(lines)
    added = new_errors(items, parse_findings, out)
    if added:
        raise StateError(f"the change would add lint error(s): {', '.join(added)}")
    return out, True


def check_value(name, value):
    """One printable line with no fence marker, or StateError.

    STATE and NAME come from whoever runs the command, which in a team may be a
    session acting on another session's message, so they are untrusted input.
    """
    value = (value or "").strip()
    if (not value or len(value.splitlines()) != 1 or "```" in value
            or any(unicodedata.category(ch) in UNSAFE_CATEGORIES for ch in value)):
        raise StateError(f"{name} must be one printable line with no control, format "
                         f"or line-separator characters and no backtick fence")
    return value


def bare(line):
    """A line without its terminator, whichever one str.splitlines() found."""
    return line.splitlines()[0] if line.strip("\r\n") else ""


def metadata_end(lines, it):
    """Index just past the heading's run of title and metadata lines."""
    j = it.line
    while j < len(lines) and any(r.match(bare(lines[j])) for r in METADATA_RES):
        j += 1
    return j


def title_index(lines, it):
    for j in range(it.line, metadata_end(lines, it)):
        if board_lint.TITLE_RE.match(bare(lines[j])):
            return j
    return None


def error_codes(items, parse_findings):
    return Counter(f[2] for f in board_lint.check(items, parse_findings) if f[0] == "error")


def new_errors(items, parse_findings, out):
    """Error codes the edit adds. Errors already on the board never block a change."""
    before = error_codes(items, parse_findings)
    after = error_codes(*board_lint.parse(out))
    return sorted(code for code, n in after.items() if n > before.get(code, 0))


def write_atomic(path, text):
    """Write beside the board and rename over it, keeping the board's mode."""
    mode = path.stat().st_mode & 0o7777
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def main(argv=None):
    ap = argparse.ArgumentParser(description="Set a story's State and record the move.")
    ap.add_argument("board", help="path to the board markdown file")
    ap.add_argument("story", help="story ref, e.g. STORY-NNNN03")
    ap.add_argument("state", help="the new State value, in the board's own vocabulary")
    ap.add_argument("--by", required=True, help="who made the move, written into COMMENTS")
    box = ap.add_mutually_exclusive_group()
    box.add_argument("--tick", action="store_true", help="also tick the title box")
    box.add_argument("--untick", action="store_true", help="also untick the title box")
    a = ap.parse_args(argv)

    # A link would have the rename land wherever it points, so name the file itself.
    if Path(a.board).is_symlink():
        print(f"error: {a.board} is a symlink; pass the board file itself", file=sys.stderr)
        return 2
    path = Path(a.board).resolve()
    try:
        with open(path, encoding="utf-8", newline="") as fh:
            text = fh.read()
    except (OSError, UnicodeDecodeError) as exc:
        print(f"error: cannot read board: {exc}", file=sys.stderr)
        return 2

    tick = True if a.tick else False if a.untick else None
    try:
        out, changed = set_state(text, a.story, a.state, a.by,
                                 datetime.now(timezone.utc), tick)
    except StateError as exc:
        print(f"refused: {exc}; {path.name} is unchanged", file=sys.stderr)
        return 1
    if not changed:
        print(f"{a.story}: already {a.state.strip()}; unchanged")
        return 0
    try:
        write_atomic(path, out)
    except OSError as exc:
        print(f"error: cannot write board: {exc}; {path.name} is unchanged", file=sys.stderr)
        return 2
    print(f"{a.story}: State {a.state.strip()} by {a.by.strip()}")
    return 0


if __name__ == "__main__":
    if sys.platform == "win32":  # the console code page is not UTF-8; board text often is
        for _stream in (sys.stdout, sys.stderr):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
