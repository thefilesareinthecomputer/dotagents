#!/usr/bin/env python3
"""Ledger of what a closeout has already covered, so re-entry is not redoing.

A closeout assumes the session ends at the commit. Sessions do not cooperate:
work continues, three more commits land, and the second closeout re-reviews,
re-reflects and re-documents everything the first one already did, because
nothing recorded where it got to.

This records that. Each step stamps the HEAD it covered and a digest of the
uncommitted tree it saw. On re-entry, `status` reports per step whether anything
has happened since, and names the range a re-review should actually read.

    python3 closeout_state.py status
    python3 closeout_state.py record security-review --tier A --notes "clean"
    python3 closeout_state.py reset

The ledger lives in the repository's own git directory. That is per-repo, never
committed, needs no ignore rule in any consumer repo, and disappears with the
clone - which is right for state whose whole purpose is one session's memory.

A missing or unreadable ledger degrades to "nothing covered", never to a skipped
step. Losing the ledger costs a redundant pass; trusting a corrupt one would cost
an unreviewed diff.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

VERSION = 1

# A fixed vocabulary: a typo must fail, not invent a step nothing will ever read.
STEPS = ("security-review", "inbox", "reflect", "notes", "commit")


def git(*args: str, cwd: Path | None = None) -> str:
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def git_dir() -> Path:
    return Path(git("rev-parse", "--absolute-git-dir").strip())


def head_sha() -> str:
    try:
        return git("rev-parse", "HEAD").strip()
    except RuntimeError:
        return ""  # a repo with no commits yet


def tree_digest() -> str:
    """Fingerprint of everything not yet committed: the diff plus untracked bytes."""
    h = hashlib.sha256()
    try:
        h.update(git("diff", "HEAD").encode("utf-8", "replace"))
    except RuntimeError:
        h.update(git("diff").encode("utf-8", "replace"))
    root = Path(git("rev-parse", "--show-toplevel").strip())
    for name in sorted(git("ls-files", "--others", "--exclude-standard").split("\n")):
        if not name.strip():
            continue
        h.update(name.encode())
        path = root / name
        try:
            h.update(path.read_bytes())
        except OSError:
            h.update(b"<unreadable>")
    return h.hexdigest()[:16]


def load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": VERSION, "steps": {}}
    if not isinstance(data, dict) or data.get("version") != VERSION:
        return {"version": VERSION, "steps": {}}
    data.setdefault("steps", {})
    return data


def save(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def commits_since(sha: str) -> list[str] | None:
    """Commits landed since `sha`, or None when the base cannot be resolved."""
    if not sha:
        return []
    try:
        out = git("log", "--oneline", f"{sha}..HEAD")
    except RuntimeError:
        return None
    return [line for line in out.strip().split("\n") if line.strip()]


def step_status(entry: dict | None, head: str, digest: str) -> dict:
    if entry is None:
        return {"state": "uncovered", "commits": [], "tree_changed": True}
    new_commits = commits_since(entry.get("head", ""))
    if new_commits is None:
        # The recorded commit is gone - rebased, reset, or the ledger is wrong.
        # Nothing about its scope can be trusted, so the step has to run in full.
        return {"state": "uncovered", "commits": [], "tree_changed": True}
    tree_changed = entry.get("digest") != digest
    if not new_commits and not tree_changed:
        return {"state": "current", "commits": [], "tree_changed": False}
    return {"state": "stale", "commits": new_commits, "tree_changed": tree_changed}


def report(data: dict, head: str, digest: str) -> str:
    lines: list[str] = []
    for step in STEPS:
        entry = data["steps"].get(step)
        status = step_status(entry, head, digest)
        if status["state"] == "uncovered":
            lines.append(f"{step:16} not covered this session - run it in full")
            continue
        stamp = entry.get("head", "")[:7] or "(no commit)"
        detail = f"tier {entry['tier']}" if entry.get("tier") else ""
        notes = entry.get("notes", "")
        head_line = f"{step:16} covered through {stamp}"
        if detail:
            head_line += f" ({detail})"
        lines.append(head_line)
        if notes:
            lines.append(f"{'':16} recorded: {notes}")
        if status["state"] == "current":
            lines.append(f"{'':16} nothing new since - do not run it again")
            continue
        moved = []
        if status["commits"]:
            moved.append(f"{len(status['commits'])} new commit(s)")
        if status["tree_changed"]:
            moved.append("uncommitted changes")
        lines.append(f"{'':16} new since: {', '.join(moved)}")
        scope = f"{stamp}..HEAD" if status["commits"] else "the uncommitted diff only"
        lines.append(f"{'':16} scope this step to: {scope}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    show = sub.add_parser("status", help="what each step covered, and what is new")
    show.add_argument("--json", action="store_true")

    mark = sub.add_parser("record", help="stamp a step as covered up to now")
    mark.add_argument("step", choices=STEPS)
    mark.add_argument("--tier", choices=("A", "B"), help="the tier the review ran at")
    mark.add_argument("--notes", default="", help="verdict or findings worth carrying")

    sub.add_parser("reset", help="forget this session's coverage")

    args = parser.parse_args(argv)

    try:
        path = git_dir() / "closeout-state.json"
        head, digest = head_sha(), tree_digest()
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.command == "reset":
        path.unlink(missing_ok=True)
        print("ledger cleared - the next closeout covers everything")
        return 0

    data = load(path)

    if args.command == "record":
        data["steps"][args.step] = {
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "head": head,
            "digest": digest,
            "tier": args.tier,
            "notes": args.notes,
        }
        save(path, data)
        print(f"recorded {args.step} at {head[:7] or '(no commit)'}")
        return 0

    if args.json:
        print(json.dumps({
            "head": head,
            "steps": {
                step: {"entry": data["steps"].get(step),
                       **step_status(data["steps"].get(step), head, digest)}
                for step in STEPS
            },
        }, indent=2))
    else:
        print(report(data, head, digest))
    return 0


if __name__ == "__main__":
    sys.exit(main())
