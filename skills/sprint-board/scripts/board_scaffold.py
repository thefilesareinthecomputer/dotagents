#!/usr/bin/env python3
"""Emit a structurally correct sprint-board markdown file from a spine.

EXECUTE this script; do not read it into context. It owns everything mechanical -
heading levels, ID assignment and regime, parent lines, dependency lines, fence
widths, separators, block skeletons - so the agent only ever writes prose into
the blocks. Output is deterministic: the same spine always produces the same
bytes.

    python3 board_scaffold.py SPINE.json [-o BOARD.md]

Spine shape (ids optional; titles required):

    {"epics": [
      {"id": "123456", "title": "Reporting Stability", "features": [
        {"title": "Delivery Reliability", "depends": ["234567"], "stories": [
          {"title": "Detect dropped jobs"}
        ]}
      ]}
    ]}

Any id present is preserved exactly. Missing ids are assigned: NNNNnn when the
spine already contains real six-digit ids, otherwise a zero-padded counter from
000000. Exit 0 on success, 2 on a malformed spine.
"""

import argparse
import json
import re
import sys
from pathlib import Path

REAL_ID_RE = re.compile(r"^\d{6}$")
SCRATCH_ID_RE = re.compile(r"^0{2}\d{4}$")

EPIC_BODY = """**OUTCOME**:

**PRIMARY QUESTION ANSWERED**:

**OUT OF SCOPE**:
-

**END STATE**:
-

**COMPLETION EVIDENCE**:
- """

FEATURE_BODY = """**PURPOSE**:

**KEY ACTIVITIES**:
- [ ]

**ACCEPTANCE CRITERIA**:
- [ ] Criterion 1 (STORY-{TRACE})

**SCOPE BOUNDARY**:

**PRIMARY OWNER**:
**CONTRIBUTORS**: """

STORY_BODY = """**ORIGINAL REQUEST**:
{The ask in the requester's own terms. Omit where the item came from the decomposition.}

**USER STORY**:
As a ({role} OR {team}), (I OR we) need {new functionality}. This is due to \
{business case}. To achieve this functionality, (I OR we) will \
{development actions}. This will enable {downstream functionality}.

**DEVELOPMENT APPROACH**:
- [ ] Step 1:
- [ ] Step n: """

STORY_AC = """- [ ] Criterion 1
- [ ] Criterion n

**VALIDATION**:
_Starter queries, adapt or extend as needed._
- [ ] Query or command evidencing a criterion:
- [ ] Step that cannot be queried: an approval, a deploy, a confirmation

**DEFINITION OF DONE**:
- [ ] Evidence linked:
- [ ] Reviewed and approved by {role}
- [ ] Stored in {location}
- [ ] Impacted documentation updated, or confirmed unaffected"""


class SpineError(ValueError):
    pass


def walk(spine):
    """Flatten the spine into (kind, node, parent_node) in document order."""
    if not isinstance(spine, dict) or "epics" not in spine:
        raise SpineError("spine must be an object with an 'epics' list")
    if not isinstance(spine["epics"], list) or not spine["epics"]:
        raise SpineError("'epics' must be a non-empty list")
    out = []
    for epic in spine["epics"]:
        require_title(epic, "epic")
        out.append(("epic", epic, None))
        for feature in epic.get("features", []) or []:
            require_title(feature, "feature")
            out.append(("feature", feature, epic))
            for story in feature.get("stories", []) or []:
                require_title(story, "story")
                out.append(("story", story, feature))
    return out


def require_title(node, kind):
    if not isinstance(node, dict):
        raise SpineError(f"each {kind} must be an object")
    if not str(node.get("title", "")).strip():
        raise SpineError(f"every {kind} needs a non-empty 'title'")


def assign_ids(nodes):
    """Fill in missing ids under the regime the spine implies."""
    given = [str(n.get("id")).strip() for _, n, _ in nodes if n.get("id")]
    for ident in given:
        if not REAL_ID_RE.match(ident) and not re.match(r"^NNNN\d{2}$", ident):
            raise SpineError(
                f"id {ident!r} is neither a six-digit number nor an NNNNnn placeholder"
            )
    if len(set(given)) != len(given):
        raise SpineError("spine contains duplicate ids")

    gapfill = any(REAL_ID_RE.match(i) and not SCRATCH_ID_RE.match(i) for i in given)
    used = set(given)
    counter = 0
    for _, node, _ in nodes:
        if node.get("id"):
            node["_id"] = str(node["id"]).strip()
            continue
        while True:
            counter += 1
            ident = f"NNNN{counter:02d}" if gapfill else f"{counter - 1:06d}"
            if ident not in used:
                break
        used.add(ident)
        node["_id"] = ident
    return gapfill


def depends_line(node):
    """The predecessor line, or nothing at all.

    Parent is the only link an item must declare. A predecessor is written only
    where something blocks the start, so an item with none carries no line rather
    than a line reading "none".
    """
    deps = node.get("depends") or []
    if isinstance(deps, str):
        deps = [deps]
    cleaned = [str(d).strip() for d in deps if str(d).strip()]
    return f"- Predecessor: {', '.join(cleaned)}\n" if cleaned else ""


def render(spine):
    nodes = walk(spine)
    assign_ids(nodes)
    # A feature criterion names the story that satisfies it, so the stub carries
    # the feature's first real child rather than a number nothing resolves to.
    first_child = {}
    for kind, node, parent in nodes:
        if kind == "story" and parent is not None:
            first_child.setdefault(id(parent), node["_id"])
    parts = []
    for kind, node, parent in nodes:
        ident = node["_id"]
        title = str(node["title"]).strip()
        if kind == "epic":
            parts.append(
                f"# EPIC-{ident}\n"
                f"- [ ] {title}\n\n"
                f"**DESCRIPTION**\n````\n{EPIC_BODY}\n````\n"
            )
        elif kind == "feature":
            parts.append(
                f"## FEATURE-{ident}\n"
                f"- [ ] {title}\n"
                f"- Parent: EPIC-{parent['_id']}\n"
                f"{depends_line(node)}\n"
                f"**DESCRIPTION**\n````\n"
                f"{FEATURE_BODY.replace('{TRACE}', first_child.get(id(node), '000000'))}"
                f"\n````\n"
            )
        else:
            parts.append(
                f"### STORY-{ident}\n"
                f"- [ ] {title}\n"
                f"- Parent: FEATURE-{parent['_id']}\n"
                f"{depends_line(node)}\n"
                f"**DESCRIPTION**\n````\n{STORY_BODY}\n````\n\n"
                f"**ACCEPTANCE CRITERIA**\n````\n{STORY_AC}\n````\n"
            )
    return "\n---\n\n".join(parts)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Scaffold a sprint-board markdown file.")
    ap.add_argument("spine", help="path to the spine JSON file")
    ap.add_argument("-o", "--output", help="write here instead of stdout")
    ap.add_argument("--force", action="store_true",
                    help="overwrite --output if it already exists")
    args = ap.parse_args(argv)

    path = Path(args.spine)
    if not path.is_file():
        print(f"error: no such file: {path}", file=sys.stderr)
        return 2
    try:
        spine = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"error: spine is not valid JSON: {exc}", file=sys.stderr)
        return 2
    try:
        text = render(spine)
    except SpineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.output:
        out = Path(args.output)
        # A board carries tracker IDs and hand edits. Refuse rather than
        # truncate: the scaffolder cannot know what it would be replacing.
        if out.exists() and not args.force:
            print(f"error: {out} exists; pass --force to overwrite",
                  file=sys.stderr)
            return 2
        out.write_text(text + "\n", encoding="utf-8")
    else:
        sys.stdout.write(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
