#!/usr/bin/env python3
"""PostToolUse(Write|Edit) linter for the file-based memory dirs.

Fires after a write whose path is a memory file
(~/.claude/projects/<slug>/memory/*.md) and lints that dir. Split by what is
actually verifiable:

  DETERMINISTIC -> exit 2 (blocks / returns stderr to the agent so it is fixed
  now). Footgun, verified: exit 2 returns stderr to the agent; exit 1 is
  swallowed silently. A lint that exits 1 does nothing - so failures use 2.

  JUDGMENT -> advisory, exit 0, delivered as PostToolUse additionalContext on
  stdout. Stderr at exit 0 is swallowed by the harness (the same footgun), so
  an advisory printed there reaches nobody.

Stdlib only, no network. Fails OPEN: any error in the lint itself exits 0 so a
lint bug can never block a real memory write.
"""

import json
import re
import sys
from pathlib import Path

VALID_TYPES = {"user", "feedback", "project", "reference"}


def frontmatter(text: str) -> str | None:
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    return m.group(1) if m else None


def clean(s: str) -> str:
    """Escape control chars before echoing a captured value to the agent's
    stderr - a memory file's `name:`/`type:` is untrusted-ish and could carry
    ANSI escapes otherwise."""
    return s.encode("unicode_escape").decode("ascii", "replace")


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    fp = (payload.get("tool_input") or {}).get("file_path", "")
    if not fp:
        return 0
    p = Path(fp)

    # Only memory files: .../projects/<slug>/memory/<name>.md
    if p.suffix != ".md" or p.parent.name != "memory" or "projects" not in p.parts:
        return 0

    memdir = p.parent
    index = memdir / "MEMORY.md"
    try:
        index_text = index.read_text(encoding="utf-8", errors="replace") if index.exists() else ""
        mem_files = sorted(f for f in memdir.glob("*.md") if f.name != "MEMORY.md")
    except OSError:
        return 0  # can't read the dir → don't block the write

    errors: list[str] = []   # deterministic → exit 2
    warns: list[str] = []    # advisory

    if not index.exists():
        errors.append("MEMORY.md index is missing - every memory dir needs one")

    names = {f.stem for f in mem_files}
    body_all = []

    for f in mem_files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        body_all.append(text)
        stem = f.stem

        # Pointer in the index (unindexed memory is never recalled).
        if f.name not in index_text and stem not in index_text:
            errors.append(f"{f.name}: no pointer line in MEMORY.md (an unindexed memory is dead weight)")

        fm = frontmatter(text)
        if fm is None:
            errors.append(f"{f.name}: no YAML frontmatter")
            continue

        nm = re.search(r"(?m)^name:\s*(\S+)", fm)
        if not nm:
            errors.append(f"{f.name}: frontmatter missing `name:`")
        elif nm.group(1) != stem:
            errors.append(f"{f.name}: `name: {clean(nm.group(1))}` does not match filename stem `{stem}`")

        if not re.search(r"(?m)^description:\s*\S", fm):
            errors.append(f"{f.name}: frontmatter missing `description:`")

        tm = re.search(r"(?m)^\s*type:\s*(\S+)", fm)
        if not tm:
            errors.append(f"{f.name}: frontmatter missing `metadata.type`")
        elif tm.group(1) not in VALID_TYPES:
            errors.append(f"{f.name}: `type: {clean(tm.group(1))}` not in {sorted(VALID_TYPES)}")

    # Every index pointer resolves to a file that exists.
    for link in re.findall(r"\]\(([^)]+\.md)\)", index_text):
        if not (memdir / Path(link).name).exists():
            errors.append(f"MEMORY.md pointer → {link} does not resolve to a file")

    # Advisory: dangling wikilinks are ALLOWED (mark a memory worth writing later).
    # Only closed, single-line links of bounded length count, and the link text
    # is escaped and the list capped: this text now reaches the model as context,
    # and a stray `[[` must not drag a file's worth of prose into it.
    link_re = r"\[\[([^\]\|#\n]{1,120})(?:[|#][^\]\n]{0,120})?\]\]"
    dangling = sorted({wl.strip() for wl in re.findall(link_re, "".join(body_all))
                       if wl.strip() not in names})
    for wl in dangling[:10]:
        warns.append(f"dangling [[{clean(wl)}]] - allowed; marks a memory worth writing later")
    if len(dangling) > 10:
        warns.append(f"+{len(dangling) - 10} more dangling links")

    warns.append(
        "reconcile: does this repo's own documentation still agree with this memory? "
        "If this memory CORRECTS something, correct the doc too - a memory and a doc that disagree are worse than either alone."
    )

    if errors:
        for w in warns:
            print(f"memory-lint [advisory]: {w}", file=sys.stderr)
        for e in errors:
            print(f"memory-lint [FAIL]: {e}", file=sys.stderr)
        return 2
    # Advisory only: the verified channel at exit 0 is additionalContext.
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": "memory-lint [advisory]: " + " | ".join(warns),
    }}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)  # fail-open: a lint bug must never block a memory write
