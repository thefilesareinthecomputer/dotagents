"""Query a sprint board without reading the whole file.

READ. Answers the questions that otherwise get asked with a throwaway script every
time: what is open, who owns it, what sits under a feature, what is left to write.
Reuses board_lint's parser, so it sees exactly what the linter sees.

    board_query.py <board>                          every item, one line each
    board_query.py <board> --owner A --state open   filter by owner and state
    board_query.py <board> --kind story             epics, features or stories
    board_query.py <board> --parent FEATURE-NNNN01  direct children of one item
    board_query.py <board> --tree                   the hierarchy, indented
    board_query.py <board> --count                  totals by kind and state
    board_query.py <board> --json                   machine-readable

Filters combine. Exit 0 when at least one item matches, 1 when none do, so a query
can gate a script.
"""
import argparse
import json
import pathlib
import sys

import board_lint

STATE = {"open": False, "done": True}


def load(path):
    items, _ = board_lint.parse(pathlib.Path(path).read_text(encoding="utf-8"))
    return items


def select(items, kind=None, owner=None, state=None, parent=None):
    out = []
    for it in items:
        if kind and it.kind != kind:
            continue
        if owner and (it.owner or "").lower() != owner.lower():
            continue
        if state is not None and it.done != state:
            continue
        if parent and (it.parent or "").upper() != parent.upper():
            continue
        out.append(it)
    return out


def as_dict(it):
    return {"ref": it.ref, "kind": it.kind, "id": it.id, "title": it.title,
            "owner": it.owner, "done": it.done, "parent": it.parent,
            "predecessor": it.depends, "line": it.line}


def print_rows(rows):
    for it in rows:
        print(f"{'DONE' if it.done else 'OPEN':4}  {(it.owner or '-'):4}  "
              f"{it.ref:16}  {it.title or ''}")


def print_tree(items):
    by_parent = {}
    for it in items:
        by_parent.setdefault((it.parent or "").upper(), []).append(it)
    depth = {"epic": 0, "feature": 1, "story": 2}
    for it in items:
        pad = "    " * depth.get(it.kind, 0)
        mark = "x" if it.done else " "
        print(f"{pad}[{mark}] {it.ref}  {it.title or ''}")


def print_counts(items):
    rows = {}
    for it in items:
        k = rows.setdefault(it.kind, [0, 0])
        k[1 if it.done else 0] += 1
    print(f"{'kind':10} {'open':>5} {'done':>5} {'total':>6}")
    for kind in ("epic", "feature", "story"):
        if kind in rows:
            o, d = rows[kind]
            print(f"{kind:10} {o:>5} {d:>5} {o + d:>6}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Query a sprint-board markdown file.")
    ap.add_argument("board")
    ap.add_argument("--kind", choices=["epic", "feature", "story"])
    ap.add_argument("--owner")
    ap.add_argument("--state", choices=["open", "done"])
    ap.add_argument("--parent", help="direct children of this ref, e.g. FEATURE-NNNN01")
    ap.add_argument("--tree", action="store_true", help="print the hierarchy")
    ap.add_argument("--count", action="store_true", help="totals by kind and state")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    try:
        items = load(a.board)
    except OSError as e:
        print(f"cannot read board: {e}", file=sys.stderr)
        return 2

    rows = select(items, a.kind, a.owner,
                  STATE.get(a.state) if a.state else None, a.parent)

    if a.json:
        print(json.dumps([as_dict(i) for i in rows], indent=2))
    elif a.count:
        print_counts(rows)
    elif a.tree:
        print_tree(rows)
    else:
        print_rows(rows)
    return 0 if rows else 1


if __name__ == "__main__":
    sys.exit(main())
