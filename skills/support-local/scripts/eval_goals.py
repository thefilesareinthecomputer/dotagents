#!/usr/bin/env python3
"""Run the worker over a labeled goal set across brief variants, effort levels and budgets, and grade each run
against its key: every `must` literal present in the answer, `answerable` matching, key refs covered by verified
evidence. Writes one JSON line per run and prints a table. Spends tokens; each run is one `claude -p` worker.

    eval_goals.py --goals evals/goals.jsonl [--variants default,local-first,terse] [--efforts medium,high]
                  [--turns 15] [--calls 6] [--only agents-01,deck-02] [--repeat 1] [--out FILE] [--dry-run]
    eval_goals.py --report FILE          # re-print the table from a results file, no runs
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("support_local", HERE / "support_local.py")
sl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sl)


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip().lower()


def has_literal(literal: str, text: str) -> bool:
    """The literal as a whole token: `2` is not in `12` or `2026`, `ask` is not in `asked`."""
    return re.search(r"(?<![a-z0-9])" + re.escape(norm(literal)) + r"(?![a-z0-9])", text) is not None


# `answerable: false` is a finding only when the worker ended on its own account; a blocked, budget, dead or
# downgraded worker said nothing about the corpus
ABSTENTION_STOPS = ("answered", "no progress")


def grade(answer: dict, key: dict) -> dict:
    """Correctness against the key. `must` literals are matched case- and whitespace-insensitively, as whole tokens, in
    the answer text and the evidence claims; refs are matched by path, line optional. An absent goal is correct only
    when the worker abstained as a finding, not when it was blocked, salvaged or downgraded into `answerable: false`."""
    text = norm(answer.get("answer", "")) + " " + " ".join(norm(c.get("claim", "")) for c in answer.get("evidence", []) if isinstance(c, dict))
    musts = [m for m in key.get("must", []) if isinstance(m, str) and m.strip()]
    hits = [m for m in musts if has_literal(m, text)]
    want_answerable = bool(key.get("answerable", True))
    got_answerable = bool(answer.get("answerable"))
    abstained = (not got_answerable and answer.get("stop_reason") in ABSTENTION_STOPS and "downgraded" not in answer)
    verified_refs = [str(c.get("ref") or "") for c in answer.get("evidence", []) if isinstance(c, dict) and c.get("verified")]
    key_refs = [r for r in key.get("refs", []) if isinstance(r, str)]
    covered = 0
    for r in key_refs:
        path, _, line = r.partition(":")
        for v in verified_refs:
            vp, _, vl = v.partition(":")
            if vp.endswith(path) or path.endswith(vp):
                if not line or vl == line:
                    covered += 1
                    break
    if not want_answerable:
        correct = abstained
    else:
        # keyword presence is not correctness: when the key names the lines, one of them must be covered by a
        # claim the script verified
        correct = got_answerable and len(hits) == len(musts) and (not key_refs or covered > 0)
    return {"correct": correct, "answerable_ok": got_answerable == want_answerable, "must_hit": len(hits), "must_n": len(musts),
            "refs_covered": covered, "refs_n": len(key_refs), "missed": [m for m in musts if not has_literal(m, text)]}


def load_goals(paths: list[Path], only: set[str] | None) -> list[dict]:
    """Goals from one or more JSONL files. The published goals.jsonl holds goals over this repo; goals over the user's
    own repos live in the gitignored goals.local.jsonl beside it and are read when present."""
    goals = []
    for path in paths:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            g = json.loads(line)
            g["corpus"] = str(Path(g["corpus"]).expanduser())
            if only and g.get("id") not in only:
                continue
            goals.append(g)
    if not goals:
        sys.exit(f"no goals selected from {', '.join(str(p) for p in paths)}")
    return goals


def pressure() -> dict:
    """The kernel's memory verdict at the moment a cell starts, the same signals the station's memory gate reads. Two
    passes on 2026-10-15 differed by 6 of 12 on this alone, so it is recorded beside every row. None off macOS."""
    try:
        out = subprocess.run(["/usr/sbin/sysctl", "-n", "kern.memorystatus_vm_pressure_level", "kern.memorystatus_level"],
                             capture_output=True, text=True, timeout=2, check=True).stdout.split()
        return {"pressure_level": int(out[0]), "free_pct": int(out[1])}
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return {"pressure_level": None, "free_pct": None}


def run_cell(goal: dict, variant: str, effort: str | None, turns: int, calls: int, timeout: int, autocompact: str | None) -> dict:
    t = time.monotonic()
    row = {"id": goal["id"], "kind": goal.get("kind"), "corpus": goal["corpus"], "variant": variant, "effort": effort,
           "turns_budget": turns, "calls_budget": calls, **pressure()}
    try:
        answer, record = sl.run_goal(goal["goal"], goal["corpus"], goal.get("complete", ""), goal.get("out_of_scope", ""),
                                     turns, calls, None, timeout, variant, effort, autocompact)
        row.update({k: record.get(k) for k in ("model", "turns", "wall_ms", "list_cost_usd", "harness_cost_usd", "input_tokens",
                                                 "output_tokens", "cache_read", "cache_write", "peak_context_tokens", "mean_context_tokens",
                                                 "attempts", "salvaged", "answerable", "verified", "unsupported", "local_calls", "stop_reason")})
        row.update(grade(answer, goal.get("key") or {}))
        if record.get("salvaged"):
            row["correct"] = False   # a dead worker answered nothing, whatever shape the salvage took
        why: dict = {}
        for c in answer.get("evidence", []):
            if isinstance(c, dict) and not c.get("verified"):
                why[str(c.get("check"))] = why.get(str(c.get("check")), 0) + 1
        row["unsupported_why"] = why
        row["unverified_refs"] = [str(c.get("ref"))[:120] for c in answer.get("evidence", []) if isinstance(c, dict) and not c.get("verified")][:5]
        row["answer_head"] = str(answer.get("answer", ""))[:300]
        row["coverage_head"] = str(answer.get("coverage", ""))[:300]
        row["answer_full"] = answer   # the verified object, so a later grader can regrade this file without rerunning
        row["error"] = None
    except sl.TaskError as e:
        row.update({"error": f"{e} (exit {e.code})", "correct": False, "answerable_ok": False})
    row["elapsed_s"] = round(time.monotonic() - t, 1)
    return row


def table(rows: list[dict]) -> str:
    lines = [f"{'id':10s} {'kind':7s} {'variant':11s} {'effort':7s} {'ok':3s} {'must':5s} {'refs':5s} {'ver/uns':8s} {'turns':5s} "
             f"{'calls':5s} {'ctx/turn':9s} {'$ list':7s} {'wall s':6s} {'stop':11s} error"]
    for r in rows:
        if not r.get("peak_context_tokens") and r.get("turns"):
            # the harness result carries no per-request usage, so report the mean context per turn instead
            r["peak_context_tokens"] = round(((r.get("cache_read") or 0) + (r.get("cache_write") or 0) + (r.get("input_tokens") or 0)) / r["turns"])
        lines.append(f"{r['id']:10s} {str(r.get('kind'))[:7]:7s} {r['variant']:11s} {str(r.get('effort') or 'def')[:7]:7s} "
                     f"{'Y' if r.get('correct') else 'n':3s} {str(r.get('must_hit', '-'))+'/'+str(r.get('must_n', '-')):5s} "
                     f"{str(r.get('refs_covered', '-'))+'/'+str(r.get('refs_n', '-')):5s} "
                     f"{str(r.get('verified', '-'))+'/'+str(r.get('unsupported', '-')):8s} {str(r.get('turns') or '-'):5s} "
                     f"{str(r.get('local_calls') if r.get('local_calls') is not None else '-'):5s} "
                     f"{str(r.get('peak_context_tokens') or '-'):9s} {(r.get('list_cost_usd') or 0):7.4f} "
                     f"{((r.get('wall_ms') or 0)/1000):6.0f} {str(r.get('stop_reason') or '-')[:11]:11s} {str(r.get('error') or '')[:60]}")
    lines.append("")
    for variant in sorted({r["variant"] for r in rows}):
        for effort in sorted({str(r.get("effort")) for r in rows}):
            sub = [r for r in rows if r["variant"] == variant and str(r.get("effort")) == effort]
            if not sub:
                continue
            ok = sum(1 for r in sub if r.get("correct"))
            cost = sum(r.get("list_cost_usd") or 0 for r in sub)
            turns = sum(r.get("turns") or 0 for r in sub)
            lines.append(f"{variant:11s} effort={effort:7s} correct {ok}/{len(sub)}  list ${cost:.4f}  turns {turns}  "
                         f"abstention ok {sum(1 for r in sub if r.get('kind') == 'absent' and r.get('correct'))}/{sum(1 for r in sub if r.get('kind') == 'absent')}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--goals", action="append", default=None,
                   help="goal file(s); default evals/goals.jsonl plus evals/goals.local.jsonl when present")
    p.add_argument("--variants", default="default")
    p.add_argument("--efforts", default="", help="comma list; empty means the definition's effort")
    p.add_argument("--turns", type=int, default=15)
    p.add_argument("--calls", type=int, default=6)
    p.add_argument("--timeout", type=int, default=900)
    p.add_argument("--autocompact", default=None)
    p.add_argument("--only", default="", help="comma list of goal ids")
    p.add_argument("--repeat", type=int, default=1)
    p.add_argument("--out", default=None, help="results JSONL; default under the state directory's evals/")
    p.add_argument("--dry-run", action="store_true", help="list the cells and exit")
    p.add_argument("--report", default=None, help="re-print the table from a results file")
    a = p.parse_args(argv)
    if a.report:
        rows = [json.loads(l) for l in Path(a.report).read_text().splitlines() if l.strip()]
        print(table(rows))
        return 0
    paths = [Path(g) for g in a.goals] if a.goals else [HERE.parent / "evals" / "goals.jsonl", HERE.parent / "evals" / "goals.local.jsonl"]
    goals = load_goals(paths, set(filter(None, a.only.split(","))) or None)
    variants = [v for v in a.variants.split(",") if v]
    efforts = [e for e in a.efforts.split(",") if e] or [None]
    cells = [(g, v, e) for g in goals for v in variants for e in efforts for _ in range(a.repeat)]
    print(f"{len(cells)} runs: {len(goals)} goals x {len(variants)} variants x {len(efforts)} efforts x {a.repeat}")
    if a.dry_run:
        for g, v, e in cells:
            print(f"  {g['id']:10s} {v:11s} {e or 'def'}")
        return 0
    out = Path(a.out) if a.out else sl.state_dir() / "evals" / f"goals-{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    rows = []
    for i, (g, v, e) in enumerate(cells, 1):
        row = run_cell(g, v, e, a.turns, a.calls, a.timeout, a.autocompact)
        rows.append(row)
        fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, separators=(",", ":")) + "\n")
        print(f"[{i}/{len(cells)}] {row['id']} {v} {e or 'def'}: {'correct' if row.get('correct') else 'WRONG'} "
              f"{row.get('must_hit', '-')}/{row.get('must_n', '-')} must, {row.get('turns')} turns, ${row.get('list_cost_usd') or 0:.4f}"
              + (f", error {row['error']}" if row.get("error") else ""), flush=True)
    print()
    print(table(rows))
    print(f"results {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
