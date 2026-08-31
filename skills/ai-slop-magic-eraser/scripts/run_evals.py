#!/usr/bin/env python3
"""
Run this skill's trigger evals in a disposable sandbox.

EXECUTE this script. It exists because running the eval harness naively is
unsafe and unreliable, in two specific ways this wrapper fixes:

  1. CONTAINMENT. Each probe is a real `claude -p` session with tools. It can
     create and edit files in its working directory. Run it in a repo and the
     probes write into the repo. This script runs every probe inside a fresh
     temp directory that is deleted afterwards, so nothing reaches the repo.

  2. FIXTURE PRESENCE. A prompt that names a document which is not present makes
     the model ask "which file?" instead of acting, and the harness scores that
     as a trigger failure. It is not; it is an eval-design failure, and it looks
     identical to a bad description. Files declared under an eval's `files` key
     are copied into the sandbox so the prompt refers to something real.

    python3 scripts/run_evals.py                 # all evals, haiku, 3 runs
    python3 scripts/run_evals.py --model sonnet --runs 5
    python3 scripts/run_evals.py --keep           # leave the sandbox for inspection

Exit 0 all passed, 1 any failed, 2 setup error.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
SKILL_NAME = SKILL.name
EVALS_DIR = SKILL / "evals"
EVAL_FILENAMES = ("triggers.json", "evals.json")

HARNESS_CANDIDATES = [
    Path.home()
    / ".claude/plugins/marketplaces/claude-plugins-official/plugins/skill-creator"
    / "skills/skill-creator",
]


def find_harness() -> Path:
    for root in HARNESS_CANDIDATES:
        if (root / "scripts" / "run_eval.py").is_file():
            return root
    hits = sorted((Path.home() / ".claude/plugins").rglob("skill-creator/scripts/run_eval.py"))
    if hits:
        return hits[0].parent.parent
    print(
        "skill-creator plugin not found. Install it with:\n"
        "  /plugin install skill-creator@claude-plugins-official",
        file=sys.stderr,
    )
    raise SystemExit(2)


def load_cases() -> list[dict]:
    """Read whichever eval file the skill ships.

    Two shapes are in use: a bare list of harness-shaped cases (triggers.json),
    and {"skill_name": ..., "evals": [...]} in the house schema (evals.json).
    """
    for name in EVAL_FILENAMES:
        path = EVALS_DIR / name
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else data["evals"]
    print(
        f"no eval set in {EVALS_DIR} (looked for {', '.join(EVAL_FILENAMES)})",
        file=sys.stderr,
    )
    raise SystemExit(2)


def build_sandbox(cases: list[dict], sandbox: Path) -> None:
    """Copy every declared fixture in, flattened to its basename."""
    wanted = {f for c in cases for f in c.get("files", [])}
    for rel in sorted(wanted):
        src = SKILL / rel
        if not src.is_file():
            print(f"declared fixture missing: {rel}", file=sys.stderr)
            raise SystemExit(2)
        shutil.copy(src, sandbox / src.name)


def case_query(case: dict) -> str:
    """The prompt text, under whichever key the case's shape uses."""
    return case["query"] if "query" in case else case["prompt"]


def to_harness_schema(cases: list[dict]) -> list[dict]:
    """Either shape -> the {query, should_trigger} pairs the harness reads."""
    return [
        {
            "query": case_query(c),
            "should_trigger": (
                c["should_trigger"]
                if "should_trigger" in c
                else c.get("expected_skill") == SKILL_NAME
            ),
        }
        for c in cases
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default="haiku", help="pin a cheap model (default haiku)")
    ap.add_argument("--runs", type=int, default=3, help="runs per query")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--keep", action="store_true", help="do not delete the sandbox")
    args = ap.parse_args()

    harness = find_harness()
    cases = load_cases()
    by_prompt = {case_query(c): c for c in cases}

    sandbox = Path(tempfile.mkdtemp(prefix=f"{SKILL_NAME}-evals-"))
    try:
        build_sandbox(cases, sandbox)
        eval_set = sandbox / "_evalset.json"
        eval_set.write_text(json.dumps(to_harness_schema(cases)), encoding="utf-8")

        print(f"sandbox: {sandbox}")
        print(f"skill:   {SKILL_NAME}")
        print(f"model:   {args.model}   runs/query: {args.runs}\n")

        proc = subprocess.run(
            [
                sys.executable,
                str(harness / "scripts" / "run_eval.py"),
                "--eval-set", str(eval_set),
                "--skill-path", str(SKILL),
                "--model", args.model,
                "--runs-per-query", str(args.runs),
                "--num-workers", str(args.workers),
            ],
            cwd=sandbox,
            env={**__import__("os").environ, "PYTHONPATH": str(harness)},
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0 and not proc.stdout.strip():
            print(proc.stderr[-2000:], file=sys.stderr)
            return 2

        try:
            report = json.loads(proc.stdout)
        except json.JSONDecodeError:
            print("harness produced no parseable report:", file=sys.stderr)
            print(proc.stdout[-2000:], file=sys.stderr)
            return 2

        rows = report["results"]
        width = max(len(by_prompt[r["query"]].get("name", "?")) for r in rows)
        for r in sorted(rows, key=lambda r: (r["pass"], not r["should_trigger"])):
            case = by_prompt[r["query"]]
            mark = "PASS" if r["pass"] else "FAIL"
            want = "fire" if r["should_trigger"] else "quiet"
            print(
                f"{mark}  {case.get('name','?'):<{width}}  want={want:<5} "
                f"rate={r['trigger_rate']:.2f} ({r['triggers']}/{r['runs']})"
            )

        s = report["summary"]
        print(f"\n{s['passed']}/{s['total']} passed")

        failed = [r for r in rows if not r["pass"]]
        if failed:
            all_zero = all(r["trigger_rate"] == 0.0 for r in rows if r["should_trigger"])
            if all_zero:
                print(
                    "\nEvery should-fire case scored exactly 0.00. That is usually the\n"
                    "harness or the fixtures, not the description. Check that the skill is\n"
                    "symlinked into ~/.claude/skills (run ~/.agents/sync-skills.sh) and that\n"
                    "each prompt naming a document declares it under 'files'.",
                    file=sys.stderr,
                )
        return 0 if not failed else 1
    finally:
        if args.keep:
            print(f"\nsandbox kept at {sandbox}")
        else:
            shutil.rmtree(sandbox, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
