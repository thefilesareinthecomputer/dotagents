"""Query a sprint board without reading the whole file.

READ. Answers the questions that otherwise get asked with a throwaway script every
time: what is open, who owns it, what sits under a feature, what state the board is
in, what blocks a parent from closing. Reuses board_lint's parser, so it sees exactly
what the linter sees.

    board_query.py <board>                          every item, one line each
    board_query.py <board> --owner A --open         filter by owner and title box
    board_query.py <board> --state Blocked          filter by the declared State field
    board_query.py <board> --kind story             epics, features or stories
    board_query.py <board> --parent FEATURE-NNNN01  direct children of one item
    board_query.py <board> --tree                   the hierarchy, indented
    board_query.py <board> --count                  totals by kind, box and State
    board_query.py <board> --status                 per item: boxes, state, disagreement;
                                                    per parent: closeable, or what blocks it
    board_query.py <board> --trace                  feature criteria <-> stories, both ways
    board_query.py <board> --json                   machine-readable, any mode

Filters combine. Exit 0 when at least one item matches, 1 when none do, so a query
can gate a script.

Box counts are an item's OWN boxes: the parser ends an item at the next heading of
any kind, so a parent's count never absorbs its children's.
"""
import argparse
import json
import pathlib
import re
import sys

import board_lint

CHECKED_RE = re.compile(r"^\s*-\s+\[[xX]\]")


def load(path):
    items, _ = board_lint.parse(pathlib.Path(path).read_text(encoding="utf-8"))
    return items


def select(items, kind=None, owner=None, done=None, parent=None, state=None):
    out = []
    for it in items:
        if kind and it.kind != kind:
            continue
        if owner and (it.owner or "").lower() != owner.lower():
            continue
        if done is not None and it.done != done:
            continue
        if parent and (it.parent or "").upper() != parent.upper():
            continue
        if state and (it.state or "").strip().lower() != state.strip().lower():
            continue
        out.append(it)
    return out


def as_dict(it):
    return {"ref": it.ref, "kind": it.kind, "id": it.id, "title": it.title,
            "owner": it.owner, "state": it.state, "done": it.done, "parent": it.parent,
            "predecessor": it.depends, "line": it.line}


# ---- status -------------------------------------------------------------------

def status(items, rows):
    """Per-item box counts and flags; per-parent closeability.

    A parent is closeable when every child is ticked done and every one of its own
    boxes is ticked. Blockers are named individually so the closeout knows where to go.
    """
    kids = board_lint.children_of(items)
    out = []
    for it in rows:
        checked, total = board_lint.box_counts(it)
        flags = []
        if it.done and total and checked < total:
            flags.append("title-done/boxes-open")
        if not it.done and total and checked == total:
            flags.append("boxes-done/title-open")
        entry = {**as_dict(it), "boxes": {"checked": checked, "total": total}, "flags": flags}
        if it.kind != "story":
            children = kids.get(it.id, [])
            blocking = [k.ref for k in children if not k.done]
            own_open = total - checked
            entry["children"] = {"done": len(children) - len(blocking), "total": len(children)}
            entry["closeable"] = not blocking and not own_open
            entry["blocked_by"] = blocking
            entry["own_open"] = own_open
        out.append(entry)
    return out


def print_status(entries):
    for e in entries:
        b = e["boxes"]
        boxes = f"{b['checked']}/{b['total']}" if b["total"] else "-"
        state = e["state"] or "-"
        flag = f"  !{' !'.join(e['flags'])}" if e["flags"] else ""
        print(f"{'DONE' if e['done'] else 'OPEN':4}  {state:10.10}  {e['ref']:16}  "
              f"boxes {boxes:>5}{flag}  {e['title'] or ''}")
        if "closeable" in e:
            c = e["children"]
            if e["closeable"]:
                verdict = "closeable" if not e["done"] else "closed"
            else:
                parts = []
                if e["blocked_by"]:
                    parts.append("blocked by " + ", ".join(e["blocked_by"]))
                if e["own_open"]:
                    parts.append(f"{e['own_open']} own box(es) open")
                verdict = "not closeable: " + "; ".join(parts)
            print(f"{'':4}  {'':10}  {'':16}  children {c['done']}/{c['total']}, {verdict}")


# ---- trace --------------------------------------------------------------------

def trace(items, rows):
    """The feature coverage map, read both ways.

    For each feature in rows: every acceptance criterion with the stories it names
    (empty when untraced), and every child story no criterion names. This is the
    graph the linter builds for criterion-untraced and story-uncovered, exposed
    whole instead of only where it is violated.
    """
    kids = board_lint.children_of(items)
    out = []
    for it in rows:
        if it.kind != "feature":
            continue
        children = kids.get(it.id, [])
        child_ids = {k.id.upper(): k for k in children}
        criteria, covered = [], set()
        for lineno, raw in criteria_lines(it):
            m = board_lint.CHECKBOX_RE.match(raw)
            if not m:
                continue
            condition, refs = board_lint.split_trace(m.group(1))
            checked = bool(CHECKED_RE.match(raw))
            stories = ["STORY-" + r for r in refs]
            misrouted = ["STORY-" + r for r in refs if r not in child_ids]
            covered |= {r for r in refs if r in child_ids}
            criteria.append({"line": lineno, "condition": condition, "checked": checked,
                             "stories": stories, "misrouted": misrouted})
        uncovered = [k.ref for k in children if k.id.upper() not in covered]
        out.append({"ref": it.ref, "title": it.title, "criteria": criteria,
                    "uncovered": uncovered})
    return out


def criteria_lines(item):
    """(line, text) for every checkbox under a feature's ACCEPTANCE CRITERIA label,
    in file order. A list rather than board_lint.section_lines' text-keyed dict, so
    two criteria worded identically stay two rows."""
    block = item.blocks.get("DESCRIPTION")
    if not block:
        return []
    out, inside = [], False
    for lineno, text in block.get("body", []):
        m = board_lint.LABEL_RE.match(text)
        if m:
            inside = m.group(1).strip() == "ACCEPTANCE CRITERIA"
            continue
        if inside and board_lint.CHECKBOX_RE.match(text):
            out.append((lineno, text))
    return out


def print_trace(entries):
    for e in entries:
        print(f"{e['ref']}  {e['title'] or ''}")
        if not e["criteria"]:
            print("    (no acceptance criteria)")
        for c in e["criteria"]:
            mark = "x" if c["checked"] else " "
            target = ", ".join(c["stories"]) if c["stories"] else "UNTRACED"
            note = f"  (misrouted: {', '.join(c['misrouted'])})" if c["misrouted"] else ""
            print(f"    [{mark}] {c['condition'][:70]:70}  -> {target}{note}")
        for ref in e["uncovered"]:
            print(f"    uncovered: {ref}")


# ---- plain views ----------------------------------------------------------------

def print_rows(rows):
    for it in rows:
        print(f"{'DONE' if it.done else 'OPEN':4}  {(it.owner or '-'):4}  "
              f"{it.ref:16}  {it.title or ''}")


def print_tree(items):
    depth = {"epic": 0, "feature": 1, "story": 2}
    for it in items:
        pad = "    " * depth.get(it.kind, 0)
        mark = "x" if it.done else " "
        print(f"{pad}[{mark}] {it.ref}  {it.title or ''}")


def counts(rows):
    by_kind, by_state = {}, {}
    for it in rows:
        k = by_kind.setdefault(it.kind, [0, 0])
        k[1 if it.done else 0] += 1
        if it.state:
            by_state[it.state.strip()] = by_state.get(it.state.strip(), 0) + 1
    return by_kind, by_state


def print_counts(rows):
    by_kind, by_state = counts(rows)
    print(f"{'kind':10} {'open':>5} {'done':>5} {'total':>6}")
    for kind in ("epic", "feature", "story"):
        if kind in by_kind:
            o, d = by_kind[kind]
            print(f"{kind:10} {o:>5} {d:>5} {o + d:>6}")
    if by_state:
        print(f"\n{'state':20} {'items':>5}")
        for value, n in sorted(by_state.items(), key=lambda kv: -kv[1]):
            print(f"{value:20.20} {n:>5}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Query a sprint-board markdown file.")
    ap.add_argument("board")
    ap.add_argument("--kind", choices=["epic", "feature", "story"])
    ap.add_argument("--owner")
    ap.add_argument("--state", help="declared '- State:' value, matched case-insensitively")
    box = ap.add_mutually_exclusive_group()
    box.add_argument("--open", action="store_true", help="title box unticked")
    box.add_argument("--done", action="store_true", help="title box ticked")
    ap.add_argument("--parent", help="direct children of this ref, e.g. FEATURE-NNNN01")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--tree", action="store_true", help="print the hierarchy")
    mode.add_argument("--count", action="store_true", help="totals by kind, box and State")
    mode.add_argument("--status", action="store_true",
                      help="boxes, state and disagreement per item; closeability per parent")
    mode.add_argument("--trace", action="store_true",
                      help="feature criteria and the stories they name, both directions")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    try:
        items = load(a.board)
    except OSError as e:
        print(f"cannot read board: {e}", file=sys.stderr)
        return 2

    done = True if a.done else False if a.open else None
    rows = select(items, a.kind, a.owner, done, a.parent, a.state)

    if a.status:
        entries = status(items, rows)
        print(json.dumps(entries, indent=2)) if a.json else print_status(entries)
    elif a.trace:
        entries = trace(items, rows)
        print(json.dumps(entries, indent=2)) if a.json else print_trace(entries)
    elif a.count:
        if a.json:
            by_kind, by_state = counts(rows)
            print(json.dumps({"by_kind": {k: {"open": v[0], "done": v[1]} for k, v in by_kind.items()},
                              "by_state": by_state}, indent=2))
        else:
            print_counts(rows)
    elif a.json:
        print(json.dumps([as_dict(i) for i in rows], indent=2))
    elif a.tree:
        print_tree(rows)
    else:
        print_rows(rows)
    return 0 if rows else 1


if __name__ == "__main__":
    sys.exit(main())
