#!/usr/bin/env python3
"""Behavioral battery for the notes skill.

Builds a throwaway fixture repo seeded with a known-bad doc state, runs the
skill against it with `claude -p`, and grades the recorded tool sequence and
the resulting files.

The ordering invariant (root docs written last, once) is only visible in the
tool sequence, not in the final tree, so the grader reads the stream-json
transcript rather than diffing files alone.

Usage:
    python3 tests/notes-behavior/run_battery.py --workdir /path/to/scratchpad
    python3 tests/notes-behavior/run_battery.py --workdir DIR --scenario legacy
    python3 tests/notes-behavior/run_battery.py --workdir DIR --build-only

The fixture is rebuilt from scratch on every run. Never point --workdir at a
real repo: the skill under test writes documentation files.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

MODEL = "claude-opus-5"
TIMEOUT_S = 1200

# Files that must not change carry exact sentinels: any edit breaks the string.
DECOY = "SENTINEL-DECOY-UNTOUCHED"
PAST = "SENTINEL-PAST-DAY-IMMUTABLE"

# Files the skill is meant to rewrite cannot be graded on sentinels, because a
# faithful compression legitimately drops them. Grade those on anchors a correct
# rewrite has to keep: the thing's name, its path, the reason behind a decision.
LIVE_ANCHOR = "pagination"          # in-progress item, must survive somewhere hot
GOTCHA_ANCHOR = "clock"             # live gotcha, must stay in plan.md
FINISHED_ANCHORS = ("widget", "upload")   # both must reach the cold file
WHY_ANCHORS = ("stream", "memory")  # the reason, must survive into SPEC.md
STALE_CLAIMS = ("single JSON array", "no backoff")  # must be gone from SPEC.md

GOVERNED = {
    "README.md",
    "SPEC.md",
    "tasks/plan.md",
    "tasks/todo.md",
}
ROOT_DOCS = {"README.md", "SPEC.md"}

SESSION_PROMPT = """Take notes on this session and update the docs.

This session we did three things. We shipped the widget exporter that
tasks/SPEC-FEATURE-WIDGET.md specifies, and its tests pass. We fixed the
retry loop in src/upload.py so it backs off exponentially instead of
hammering a dead endpoint. And we settled the storage question: exports are
written as newline-delimited JSON rather than a single array, because a
consumer can stream them without holding the whole export in memory.

The pagination work in tasks/plan.md is still in progress and is not done.
"""


def _pad_items(prefix: str, start: int, count: int) -> list[str]:
    """Filler plan entries so the fixture is genuinely over budget."""
    out = []
    for i in range(start, start + count):
        out.append(f"{i}. **{prefix} {i}.** Handler `src/mod{i}.py` covered by")
        out.append(f"   `tests/test_mod{i}.py`. Verified by `pytest tests/test_mod{i}.py`.")
        out.append("")
    return out


def build_fixture(root: Path, scenario: str) -> None:
    if root.exists():
        shutil.rmtree(root)
    (root / "tasks").mkdir(parents=True)
    (root / "src").mkdir()

    plan: list[str] = [
        "# Plan",
        "",
        "## Active work",
        "",
        "1. **Pagination for the export endpoint - IN PROGRESS.**",
        "   Cursor-based, `src/export.py`. **Next:** wire the cursor into the CLI.",
        "",
        "2. **Widget exporter - DONE.** Spec in",
        "   `tasks/SPEC-FEATURE-WIDGET.md`. Tests green.",
        "",
        "3. **Upload retry backoff - DONE.** `src/upload.py`.",
        "",
    ]
    plan += _pad_items("Closed maintenance item", 4, 140)
    plan += [
        "## Dev docs",
        "",
        "### Storage format decision",
        "",
        "We went back and forth on this for a while. The first attempt wrote a",
        "single JSON array and it worked fine on the sample data, then fell over",
        "on the larger export, and we spent an afternoon reading heap dumps",
        "before the cause was obvious in hindsight. We also considered CSV and",
        "rejected it on nested fields, and considered Parquet and rejected it",
        "because the consumer is a shell script. The reason we landed on",
        "newline-delimited JSON is this: a consumer can stream the export",
        "without holding the whole thing in memory. That constraint is settled",
        "and is not expected to change.",
        "",
        "### Known gotcha - clock skew",
        "",
        "The scheduler trusts the client clock for expiry. Still live, still",
        "unresolved, do not remove this note.",
        "",
    ]
    (root / "tasks" / "plan.md").write_text("\n".join(plan) + "\n")

    todo: list[str] = ["# Todo", "", "## Next actions", ""]
    for i in range(1, 115):
        todo.append(f"- [ ] Follow-up {i}: check `src/mod{i}.py` against its test.")
    todo += ["", "- [ ] Finish pagination and wire the cursor into the CLI.", ""]
    (root / "tasks" / "todo.md").write_text("\n".join(todo) + "\n")

    (root / "tasks" / "SPEC-FEATURE-WIDGET.md").write_text(
        "# SPEC - widget exporter\n\n"
        "## Goal\n\nExport widgets for downstream consumers.\n\n"
        "## Interface\n\n`src/export.py:export_widgets(dest)` writes to `dest`.\n\n"
        "## Invariant\n\nOutput is newline-delimited JSON so a consumer can stream it.\n"
    )

    (root / "SPEC.md").write_text(
        "# SPEC\n\n"
        "## What this is\n\nA widget pipeline.\n\n"
        "## Invariants\n\n"
        "- Exports are written as a single JSON array.\n"
        "- Uploads retry three times with no backoff.\n\n"
        "## Out of scope\n\nRealtime streaming.\n"
    )

    (root / "README.md").write_text(
        "# widgets\n\n"
        "## What it does\n\nExports widgets.\n\n"
        "## Running it\n\n`python -m widgets export out.json`\n\n"
        "## Layout\n\n`src/` holds the pipeline.\n"
    )

    (root / "AGENTS.md").write_text(
        f"# Agent rules\n\n{DECOY}\nExports are a single JSON array.\n"
    )
    (root / "CHANGELOG.md").write_text(
        f"# Changelog\n\n## 0.1.0\n\n{DECOY}\nInitial release.\n"
    )

    if scenario == "legacy":
        (root / "tasks" / "plan-completed.md").write_text(
            f"# Completed\n\n## 2026-08-01\n\n{PAST}\n- Bootstrapped the repo.\n\n"
            "## 2026-07-28\n\n- Wrote the first exporter draft.\n"
        )
    else:
        (root / "tasks" / "completed").mkdir()
        (root / "tasks" / "completed" / "plan-completed-2026-08-01.md").write_text(
            f"## 2026-08-01\n\n{PAST}\n- Bootstrapped the repo.\n"
        )

    (root / "src" / "upload.py").write_text(
        "def upload(payload):\n"
        "    for attempt in range(3):\n"
        "        backoff = 2 ** attempt\n"
        "        _send(payload, backoff)\n"
    )
    (root / "src" / "export.py").write_text(
        "def export_widgets(dest):\n"
        "    with open(dest, 'w') as fh:\n"
        "        for w in _widgets():\n"
        "            fh.write(_json(w) + '\\n')\n"
    )

    env = {**os.environ, "GIT_AUTHOR_NAME": "fixture", "GIT_AUTHOR_EMAIL": "f@x",
           "GIT_COMMITTER_NAME": "fixture", "GIT_COMMITTER_EMAIL": "f@x"}
    for cmd in (
        ["git", "init", "-q", "-b", "main"],
        ["git", "add", "-A"],
        ["git", "commit", "-qm", "fixture: starting state"],
    ):
        subprocess.run(cmd, cwd=root, env=env, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def run_skill(root: Path, transcript: Path) -> int:
    cmd = [
        "claude", "-p", SESSION_PROMPT,
        "--output-format", "stream-json",
        "--verbose",
        "--model", MODEL,
        "--dangerously-skip-permissions",
    ]
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    with transcript.open("w") as fh:
        proc = subprocess.run(cmd, cwd=root, env=env, stdout=fh,
                              stderr=subprocess.DEVNULL, timeout=TIMEOUT_S)
    return proc.returncode


def parse_tools(transcript: Path, root: Path) -> list[dict]:
    """Ordered tool calls: {'seq', 'name', 'path', 'cmd'}."""
    calls: list[dict] = []
    for line in transcript.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = evt.get("message") or {}
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            inp = block.get("input") or {}
            raw = inp.get("file_path") or inp.get("notebook_path") or ""
            path = ""
            if raw:
                try:
                    path = str(Path(raw).resolve().relative_to(root.resolve()))
                except ValueError:
                    path = str(raw)
            calls.append({
                "seq": len(calls),
                "name": block.get("name", ""),
                "path": path,
                "cmd": inp.get("command", "") if isinstance(inp.get("command"), str) else "",
            })
    return calls


WRITERS = {"Write", "Edit", "NotebookEdit", "MultiEdit"}


def grade(root: Path, calls: list[dict], scenario: str) -> list[tuple[str, bool, str]]:
    """Return (assertion, passed, detail). Hard assertions only."""
    res: list[tuple[str, bool, str]] = []
    writes = [c for c in calls if c["name"] in WRITERS and c["path"]]
    reads = [c for c in calls if c["name"] == "Read" and c["path"]]
    bash = [c for c in calls if c["name"] == "Bash"]

    task_writes = [c for c in writes if c["path"].startswith("tasks/")]
    root_writes = [c for c in writes if c["path"] in ROOT_DOCS]

    # A1 - the root docs are written once, in one uninterrupted block, after the
    # bundle has been written at least once. A later bounded trim of a tasks/
    # file is allowed by the skill and cannot invalidate a root doc; what must
    # not happen is a root doc being written, the bundle changing, and the root
    # doc being revisited.
    if not root_writes:
        res.append(("A1 root docs written once, after the bundle", False,
                    "no root doc was written at all"))
    else:
        first_root = min(c["seq"] for c in root_writes)
        last_root = max(c["seq"] for c in root_writes)
        interleaved = [c["seq"] for c in task_writes if first_root < c["seq"] < last_root]
        before = [c["seq"] for c in task_writes if c["seq"] < first_root]
        ok = not interleaved and bool(before)
        detail = f"root block seq {first_root}-{last_root}, bundle written first at {before[:3]}"
        if interleaved:
            detail = f"tasks/ writes at {interleaved} interrupt the root block {first_root}-{last_root}"
        elif not before:
            detail = f"root block seq {first_root}-{last_root} with no prior bundle write"
        res.append(("A1 root docs written once, after the bundle", ok, detail))

    # A2 - scope: nothing written outside the six governed paths.
    stray = sorted({c["path"] for c in writes
                    if c["path"] not in GOVERNED
                    and not c["path"].startswith("tasks/")})
    res.append(("A2 scope: no writes outside the governed paths", not stray,
                f"stray writes: {stray}" if stray else "none"))

    # A3 - heading map before the first root-doc edit.
    hdr = [c for c in bash if "#{1,5}" in c["cmd"]
           or ("grep" in c["cmd"] and "^#" in c["cmd"])]
    if not root_writes:
        res.append(("A3 heading map precedes root-doc edits", False, "no root doc written"))
    else:
        first_root = min(c["seq"] for c in root_writes)
        ok = any(c["seq"] < first_root for c in hdr)
        res.append(("A3 heading map precedes root-doc edits", ok,
                    f"{len(hdr)} heading-grep call(s), first root write seq={first_root}"))

    # A4 - shipped feature spec moved with git mv, not pasted. Only applies where
    # a cold store exists; the legacy layout has nowhere to move it to and the
    # skill requires flagging instead of creating the folder.
    if scenario == "standard":
        moved = any("git mv" in c["cmd"] and "SPEC-FEATURE-WIDGET" in c["cmd"] for c in bash)
        res.append(("A4 shipped feature spec moved with git mv", moved,
                    "git mv seen" if moved else "no git mv of SPEC-FEATURE-WIDGET"))

    # A5 - read before edit, for files that already existed. The fixture's
    # starting state is committed and the skill does not commit, so HEAD is the
    # authority on what pre-existed; a file the sweep created has nothing to read.
    pre_existing = set(subprocess.run(
        ["git", "ls-tree", "-r", "HEAD", "--name-only"],
        cwd=root, capture_output=True, text=True, check=True).stdout.split())
    offenders = []
    for w in writes:
        if w["path"] not in pre_existing:
            continue
        first_read = next((r["seq"] for r in reads if r["path"] == w["path"]), None)
        if first_read is None or first_read > w["seq"]:
            offenders.append(w["path"])
    offenders = sorted(set(offenders))
    res.append(("A5 every pre-existing edited file was read first", not offenders,
                f"not read first: {offenders}" if offenders else "all read first"))

    # B1 - the finished work reached the cold store this layout actually has.
    today = date.today().isoformat()
    cold = (root / "tasks" / "completed" / f"plan-completed-{today}.md"
            if scenario == "standard" else root / "tasks" / "plan-completed.md")
    if cold.exists():
        body = cold.read_text().lower()
        missing = [a for a in FINISHED_ANCHORS if a not in body]
        res.append(("B1 finished items reached the cold store", not missing,
                    f"missing: {missing}" if missing
                    else f"{cold.name}, {len(body.splitlines())} lines"))
    else:
        res.append(("B1 finished items reached the cold store", False,
                    f"{cold.name} missing"))

    plan = (root / "tasks" / "plan.md").read_text().lower()
    todo = (root / "tasks" / "todo.md").read_text().lower()

    # B2 - the finished ENTRIES left the hot plan. A pointer sentence naming what
    # closed and where it went is the prescribed replacement, so match the entry
    # form ("**Widget exporter - DONE.**") rather than the words in it.
    leftover = re.findall(r"-\s*done\.?\*\*", plan)
    res.append(("B2 finished entries removed from tasks/plan.md", not leftover,
                f"{len(leftover)} DONE entries remain" if leftover
                else "removed, pointer retained"))

    # B3 - live work survived, under its own name.
    live = LIVE_ANCHOR in plan or LIVE_ANCHOR in todo
    res.append(("B3 in-progress work retained", live,
                "retained" if live else "DROPPED"))
    res.append(("B3b live gotcha kept hot", GOTCHA_ANCHOR in plan,
                "retained" if GOTCHA_ANCHOR in plan else "DROPPED"))

    # B4 - the reasoning moved to cold storage rather than being cut to a claim.
    # It must NOT be carried into SPEC.md: root docs are not a destination.
    spec = (root / "SPEC.md").read_text().lower()
    cold_body = cold.read_text().lower() if cold.exists() else ""
    missing_why = [a for a in WHY_ANCHORS if a not in cold_body]
    res.append(("B4 rationale relocated to cold storage, not deleted",
                not missing_why,
                f"reason missing from the cold file: {missing_why}" if missing_why
                else "reason preserved cold"))

    # B4b - step 6's only job: the claims the session invalidated are gone.
    left = [c for c in STALE_CLAIMS if c.lower() in spec]
    res.append(("B4b stale SPEC.md claims corrected", not left,
                f"still asserted: {left}" if left else "both corrected"))

    # B4c - step 6 corrects, it does not receive. The plan's rationale narrative
    # (rejected alternatives, the afternoon of heap dumps) must not land in SPEC.md.
    dumped = [p for p in ("heap dump", "rejected it on nested fields",
                          "went back and forth") if p in spec]
    res.append(("B4c SPEC.md was corrected, not used as a destination", not dumped,
                f"plan narrative appeared in SPEC.md: {dumped}" if dumped
                else "no narrative folded in"))

    # B5 - out-of-scope decoys untouched.
    touched = [n for n in ("AGENTS.md", "CHANGELOG.md")
               if DECOY not in (root / n).read_text(errors="replace")]
    res.append(("B5 out-of-scope files untouched", not touched,
                f"modified: {touched}" if touched else "AGENTS.md, CHANGELOG.md intact"))

    # B6 - past-day cold file immutable.
    past = root / "tasks" / "completed" / "plan-completed-2026-08-01.md"
    legacy = root / "tasks" / "plan-completed.md"
    if past.exists():
        res.append(("B6 past-day cold file immutable",
                    past.read_text() == f"## 2026-08-01\n\n{PAST}\n- Bootstrapped the repo.\n",
                    "byte-identical" if past.read_text().startswith("## 2026-08-01") else "MODIFIED"))
    elif legacy.exists():
        res.append(("B6 legacy append log left in place (flagged, not converted)",
                    PAST in legacy.read_text(), "still present"))
    else:
        res.append(("B6 past-day cold file immutable", False, "past-day record vanished"))

    # B7 - the shipped feature spec is retired where that is possible, and
    # flagged where it is not. The legacy layout has no cold folder, and
    # creating one would be the layout conversion the skill forbids.
    still_hot = (root / "tasks" / "SPEC-FEATURE-WIDGET.md").exists()
    archived = list((root / "tasks" / "completed").glob("SPEC-FEATURE-WIDGET*.md")) \
        if (root / "tasks" / "completed").exists() else []
    if scenario == "standard":
        res.append(("B7 shipped feature spec retired out of tasks/",
                    (not still_hot) and bool(archived),
                    f"hot={still_hot}, archived={[p.name for p in archived]}"))
    else:
        flagged = "SPEC-FEATURE-WIDGET" in (root / "tasks" / "todo.md").read_text()
        res.append(("B7 shipped feature spec flagged, folder not created",
                    still_hot and flagged and not archived,
                    f"hot={still_hot}, flagged in todo.md={flagged}, archived={len(archived)}"))

    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", required=True,
                    help="throwaway directory for the fixture; contents are destroyed")
    ap.add_argument("--scenario", default="standard", choices=["standard", "legacy"])
    ap.add_argument("--build-only", action="store_true")
    ap.add_argument("--grade-only", action="store_true")
    args = ap.parse_args()

    work = Path(args.workdir).expanduser().resolve()
    fixture = work / f"fixture-{args.scenario}"
    transcript = work / f"transcript-{args.scenario}.jsonl"

    if not args.grade_only:
        build_fixture(fixture, args.scenario)
        print(f"fixture built: {fixture}")
        plan_lines = len((fixture / "tasks" / "plan.md").read_text().splitlines())
        todo_lines = len((fixture / "tasks" / "todo.md").read_text().splitlines())
        print(f"  tasks/plan.md {plan_lines} lines (budget ~400)")
        print(f"  tasks/todo.md {todo_lines} lines (budget ~100)")
        if args.build_only:
            return 0
        print(f"running notes against it ({MODEL}) ...")
        rc = run_skill(fixture, transcript)
        print(f"claude -p exit={rc}, transcript: {transcript}")

    calls = parse_tools(transcript, fixture)
    print(f"\n{len(calls)} tool calls recorded\n")
    results = grade(fixture, calls, args.scenario)
    width = max(len(a) for a, _, _ in results)
    failed = 0
    for assertion, ok, detail in results:
        if not ok:
            failed += 1
        print(f"  {'PASS' if ok else 'FAIL'}  {assertion.ljust(width)}  {detail}")

    plan_after = len((fixture / "tasks" / "plan.md").read_text().splitlines())
    todo_after = len((fixture / "tasks" / "todo.md").read_text().splitlines())
    print(f"\n  tasks/plan.md ended at {plan_after} lines (budget ~400)")
    print(f"  tasks/todo.md ended at {todo_after} lines (budget ~100)")
    print(f"\n{len(results) - failed}/{len(results)} assertions passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
