#!/usr/bin/env python3
"""PreToolUse hook: refuse edits to published verbatim copies.

Some directories hold COPIES of files owned by another repo. They are
refreshed wholesale by a publisher, so an edit made here is erased by the
next republish - and worse, it silently reverts on a refresh long after
anyone remembers making it. The rule is that a change goes to the owner
repo and arrives back by republishing.

The rule already exists in prose (this repo's AGENTS.md says "Never edit
... anything under skills/"). Prose loses: it sits in context and nothing
consults it at the moment an obvious bug is sitting in an open file. On
2026-08-30 the rule was violated twice in one session by an agent that
could quote it. This hook interposes between the decision and the effect,
which prose cannot do.

A directory qualifies when its contents are produced by a generator rather
than authored in place. Three signals say so, and none of them names a
station, an account or a repo - this file travels, so the values live
outside it:

  MARKERS        a publisher leaves one of these in the directory it owns.
                 Any ancestor carrying one makes the target a published copy.
  MIRROR_SEGMENT a publication target is conventionally named `<name>-mirror`.
                 The whole tree is a copy; nothing in it is authored.
  PATHS_FILE     station-specific fragments for a published directory whose
                 publisher leaves no marker. One per line, `#` comments
                 allowed, read beside this hook and never committed with it.

Exit 2 blocks the call and feeds stderr back to the model.
Any internal error allows the write and says so, rather than bricking
every edit in every repo.
"""
import json
import os
import re
import sys
from pathlib import Path

# A publisher's own bookkeeping, left in the directory it refreshes. Their
# presence is the claim "this folder's contents come from somewhere else".
MARKERS = (".sources", ".published-copy")

# `<name>-mirror` is a publication target by convention, so the whole tree is
# a copy. Matched on a whole path segment: `foo-mirror/x` hits, `mirrors/x`
# and `foo-mirrored/x` do not.
MIRROR_SEGMENT = re.compile(r"(?:^|/)[^/]+-mirror(?:/|$)")

# Basenames authored INSIDE a published directory rather than published into
# it: the folder's own instructions to the local agent, and the publisher's
# source map. Allowed only at the root of the marked directory - a file of the
# same name one level down is published content like anything else.
ALLOWED_BASENAMES = {"AGENTS.md", "CLAUDE.md", ".sources", ".published-copy"}

# Station-specific fragments. A directory published by a tool that leaves no
# marker has nothing generic to match on, and the path that identifies it is a
# local constant - so it lives in a sidecar this file merely reads.
PATHS_FILE = Path(os.environ.get("PUBLISHED_COPY_PATHS_FILE")
                  or Path(__file__).resolve().with_name("published-copy-paths.txt"))

EDIT_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit", "Update", "Create"}


def station_fragments():
    """Path fragments from the sidecar. Missing file means no station entries,
    which is the correct state on a machine that publishes nothing."""
    try:
        lines = PATHS_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        entry = line.strip()
        if entry and not entry.startswith("#"):
            out.append(entry.replace(os.sep, "/"))
    return out


def marked_ancestor(posix):
    """The nearest ancestor directory carrying a publisher marker, or None.
    The target itself is not considered: a marker file is not published by the
    tool that writes it."""
    try:
        parents = list(Path(posix).parents)
    except Exception:
        return None
    for parent in parents:
        for marker in MARKERS:
            try:
                if (parent / marker).exists():
                    return parent
            except OSError:
                continue
    return None


def verdict(posix):
    """(reason, marked_root) when the path is a published copy, else None."""
    for fragment in station_fragments():
        if fragment in posix:
            return ("a published verbatim copy, refreshed wholesale by its "
                    "publisher", None)
    if MIRROR_SEGMENT.search(posix):
        return ("inside a publication target, which is refreshed wholesale "
                "from its source repo", None)
    root = marked_ancestor(posix)
    if root is not None:
        return ("a published verbatim copy, in a directory carrying a "
                "publisher marker", root)
    return None


def target_paths(payload):
    """Every filesystem path this call would write to."""
    ti = payload.get("tool_input") or {}
    out = []
    for key in ("file_path", "notebook_path", "path"):
        if ti.get(key):
            out.append(str(ti[key]))
    for edit in ti.get("edits") or []:
        if isinstance(edit, dict) and edit.get("file_path"):
            out.append(str(edit["file_path"]))
    return out


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    if payload.get("tool_name") not in EDIT_TOOLS:
        return 0

    for raw in target_paths(payload):
        try:
            path = os.path.realpath(os.path.expanduser(raw))
        except Exception:
            path = raw
        posix = path.replace(os.sep, "/")
        found = verdict(posix)
        if found is None:
            continue
        why, root = found
        # The folder's own files are authored in place, but only at its root.
        if root is not None and Path(posix).name in ALLOWED_BASENAMES \
                and Path(posix).parent == root:
            continue
        sys.stderr.write(
            f"REFUSED: {raw}\n"
            f"That file is {why}.\n\n"
            "An edit here is erased by the next republish, and it "
            "reverts silently rather than conflicting, so the fix "
            "looks done and is not.\n\n"
            "Do this instead:\n"
            "  1. Send the change to the owning agent (agent-mail).\n"
            "  2. Have it applied and confirmed non-breaking there.\n"
            "  3. Republish, which copies it back verbatim.\n\n"
            "If the difference is a deliberate publish-time "
            "transform rather than a fix, add it to the publisher's "
            "transform list so it survives every republish.\n"
        )
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # never brick editing on a bug in this hook
        sys.stderr.write(f"reject_published_copy_edits: internal error: {exc}\n")
        sys.exit(0)
