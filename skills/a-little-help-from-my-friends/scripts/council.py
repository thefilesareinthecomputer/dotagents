#!/usr/bin/env python3
"""a-little-help-from-my-friends: a panel of frontier models answers one hard question
about a fixed set of files, blind-reviews each other, and a chair synthesizes.

Commands:
  run    --question <file|-> --file <path> [--file ...] [--members claude,codex,cursor,antigravity]
         [--model harness=name ...] [--effort level | harness=level ...] [--out <dir>]
         [--chair claude|session] [--timeout 1500]
  tally  --run <dir>          recompute the ranking table from the stage-2 reviews
  clean  [--run <dir> | --older-than-days N]

Stages, after Karpathy's llm-council:
  1. first opinions   every member answers the question independently, read-only,
                      with only the named files in front of it
  2. blind review     every member ranks all stage-1 answers with the authors hidden
                      behind letters shuffled differently for each reviewer
  3. chair            Claude reads the answers, the de-anonymized reviews and the tally,
                      and writes one synthesis; or the session does, from chair-brief.md

Members are harnesses, each with its model: claude (Claude Code, Fable), codex (GPT-6
Astra), cursor (Grok 4.7), antigravity (Gemini 3.1 Pro). The staging, the harness
table and the read-only runners come from the agent-review skill; this script adds
the fan-out, the blinding, the tally and the chair. No member writes anything.

A member whose CLI is not installed is skipped up front and the run continues with the
rest (exit 3, `skipped` in run.json); fewer than two available members is exit 4 before
anything is created. A missing claude CLI turns the chair into `session`.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import random
import secrets
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
REFS = SKILL_DIR / "references"
sys.path.insert(0, str(SKILL_DIR.parent / "agent-review" / "scripts"))
import agent_review as ar  # noqa: E402

DEFAULT_MEMBERS = ["claude", "codex", "cursor", "antigravity"]
LABELS = "ABCDEFGHIJ"
DEFAULT_TIMEOUT = 1500
MAX_TIMEOUT = 1800

EXIT_OK, EXIT_ARGS, EXIT_PARTIAL, EXIT_FAILED = 0, 2, 3, 4


class CouncilError(Exception):
    def __init__(self, msg: str, code: int = EXIT_ARGS):
        super().__init__(msg)
        self.code = code


def state_dir() -> Path:
    raw = os.environ.get("COUNCIL_STATE") or os.path.join(
        os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"), "council")
    p = Path(raw).expanduser().resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def read_template(name: str) -> str:
    return (REFS / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------- roster ---

def parse_pairs(items: list[str] | None, what: str) -> tuple[dict[str, str], str | None]:
    """`--model harness=name` and `--effort harness=level` lists; a bare `--effort level`
    applies to every member. Returns (per-harness map, global value)."""
    per: dict[str, str] = {}
    global_value = None
    for item in items or []:
        if "=" in item:
            k, v = item.split("=", 1)
            per[k.strip()] = v.strip()
        elif what == "effort":
            global_value = item.strip()
        else:
            raise CouncilError(f"--{what} takes harness=value")
    return per, global_value


def roster(members: list[str], models: dict[str, str], efforts: dict[str, str], effort: str | None) -> dict[str, dict]:
    cfgs = {}
    for m in members:
        try:
            cfgs[m] = ar.resolve(m, models.get(m), efforts.get(m) or effort)
        except ar.ReviewError as exc:
            raise CouncilError(str(exc))
    return cfgs


# ---------------------------------------------------------------- stages ---

def _fan_out(cfgs: dict, briefs: dict[str, Path], stage: Path, timeout: int, work: Path) -> dict:
    results = {}
    with ThreadPoolExecutor(max_workers=max(1, len(cfgs))) as pool:
        futures = {name: pool.submit(ar.run_harness, cfg, briefs[name], stage, timeout, work) for name, cfg in cfgs.items()}
        for name, fut in futures.items():
            results[name] = fut.result()
    return results


def stage1(question: str, rels: list[str], cfgs: dict, stage: Path, out: Path, timeout: int) -> dict:
    (out / "stage1").mkdir()
    briefs = {}
    for name, cfg in cfgs.items():
        brief = ar.render(read_template("stage1.md"), QUESTION=question, FILES="\n".join(f"- {r}" for r in rels),
                          TOOLS=ar.TOOL_NOTES[cfg["runner"]])
        briefs[name] = out / "stage1" / f"{name}-brief.md"
        briefs[name].write_text(brief, encoding="utf-8")
    results = _fan_out(cfgs, briefs, stage, timeout, out / "stage1")
    for name, res in results.items():
        if res.get("text"):
            (out / "stage1" / f"{name}.md").write_text(res["text"], encoding="utf-8")
        (out / "stage1" / f"{name}.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    return results


def blinding_for(answered: list[str]) -> tuple[dict[str, str], int]:
    """A fresh permutation per reviewer, so no label means the same author twice."""
    seed = secrets.randbits(63)
    order = list(answered)
    random.Random(seed).shuffle(order)
    return {LABELS[i]: m for i, m in enumerate(order)}, seed


def stage2(question: str, rels: list[str], cfgs: dict, answers: dict, stage: Path, out: Path, timeout: int) -> tuple[dict, dict]:
    answered = [m for m in cfgs if answers[m].get("text")]
    (out / "stage2").mkdir()
    blinding: dict = {}
    briefs: dict[str, Path] = {}
    for reviewer, cfg in cfgs.items():
        labels, seed = blinding_for(answered)
        blinding[reviewer] = {"labels": labels, "seed": seed}
        responses = "\n\n".join(f"## Response {lab}\n\n{answers[m]['text']}" for lab, m in labels.items())
        brief = ar.render(read_template("stage2.md"), QUESTION=question, FILES="\n".join(f"- {r}" for r in rels),
                          RESPONSES=responses, LABELS=", ".join(labels), N=str(len(labels)),
                          TOOLS=ar.TOOL_NOTES[cfg["runner"]])
        briefs[reviewer] = out / "stage2" / f"{reviewer}-brief.md"
        briefs[reviewer].write_text(brief, encoding="utf-8")
    (out / "blinding.json").write_text(json.dumps(blinding, indent=1), encoding="utf-8")
    results = _fan_out(cfgs, briefs, stage, timeout, out / "stage2")
    for name, res in results.items():
        res["parsed"] = parse_review(res.get("text"), blinding[name]["labels"])
        if res.get("text"):
            (out / "stage2" / f"{name}.md").write_text(res["text"], encoding="utf-8")
        (out / "stage2" / f"{name}.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    return results, blinding


def parse_review(text: str | None, labels: dict[str, str]) -> dict:
    """The ranking block a reviewer returned, mapped back to members, or {valid: False, why}."""
    if not text:
        return {"valid": False, "why": "no text"}
    data = ar.extract_json_block(text, key="ranking")
    if not data or not isinstance(data.get("ranking"), list):
        return {"valid": False, "why": "no ranking block"}
    ranking = [str(x).strip().upper() for x in data["ranking"]]
    if sorted(ranking) != sorted(labels):
        return {"valid": False, "why": f"ranking labels {ranking} do not match {sorted(labels)}"}
    return {"valid": True, "ranking_labels": ranking, "ranking": [labels[x] for x in ranking],
            "rationale": {labels.get(k, k): v for k, v in (data.get("rationale") or {}).items()},
            "errors_found": data.get("errors_found"), "disagreements": data.get("disagreements")}


def compute_tally(reviews: dict, answered: list[str]) -> dict:
    """Borda count: a first place is worth n-1 points, last is 0. Reported with and without
    each reviewer's vote on its own answer."""
    n = len(answered)
    points_all = {m: 0 for m in answered}
    points_no_self = {m: 0 for m in answered}
    votes = 0
    for reviewer, res in reviews.items():
        parsed = res.get("parsed") or {}
        if not parsed.get("valid"):
            continue
        votes += 1
        for pos, m in enumerate(parsed["ranking"]):
            pts = n - 1 - pos
            points_all[m] += pts
            if m != reviewer:
                points_no_self[m] += pts
    order = sorted(answered, key=lambda m: (-points_no_self[m], -points_all[m], m))
    return {"answered": answered, "valid_reviews": votes,
            "points_all_votes": points_all, "points_excluding_self": points_no_self, "order": order,
            "invalid_reviews": {r: (res.get("parsed") or {}).get("why") for r, res in reviews.items()
                                if not (res.get("parsed") or {}).get("valid")}}


def tally_markdown(tally: dict, cfgs: dict) -> str:
    total = tally["valid_reviews"] + len(tally["invalid_reviews"])
    lines = ["# Tally", "", f"Valid reviews: {tally['valid_reviews']} of {total}", "",
             "| Rank | Member | Model | Points (excluding self) | Points (all votes) |", "|---|---|---|---|---|"]
    for i, m in enumerate(tally["order"], 1):
        lines.append(f"| {i} | {m} | {cfgs[m]['model']} | {tally['points_excluding_self'][m]} | {tally['points_all_votes'][m]} |")
    if tally["invalid_reviews"]:
        lines += ["", "Reviews excluded: " + "; ".join(f"{r} ({why})" for r, why in tally["invalid_reviews"].items())]
    return "\n".join(lines) + "\n"


def chair_brief(question: str, rels: list[str], answers: dict, reviews: dict, tally: dict, cfgs: dict) -> str:
    parts = [f"## Answer from {m} ({cfgs[m]['model']})\n\n{answers[m]['text']}" for m in tally["answered"]]
    rev_parts = []
    for r, res in reviews.items():
        parsed = res.get("parsed") or {}
        if parsed.get("valid"):
            ranking = ", ".join(f"{i + 1}. {m}" for i, m in enumerate(parsed["ranking"]))
            rationale = "\n".join(f"- on {m}: {txt}" for m, txt in (parsed.get("rationale") or {}).items())
            rev_parts.append(f"## Review by {r} ({cfgs[r]['model']})\n\nRanking: {ranking}\n\n{rationale}\n\n"
                             f"Errors found: {parsed.get('errors_found') or 'none stated'}\n\n"
                             f"Disagreements: {parsed.get('disagreements') or 'none stated'}")
        else:
            rev_parts.append(f"## Review by {r} ({cfgs[r]['model']})\n\nExcluded: {parsed.get('why')}")
    return ar.render(read_template("chair.md"), QUESTION=question, FILES="\n".join(f"- {r}" for r in rels),
                     ANSWERS="\n\n".join(parts), REVIEWS="\n\n".join(rev_parts), TALLY=tally_markdown(tally, cfgs),
                     TOOLS=ar.TOOL_NOTES["claude"])


# ---------------------------------------------------------------- commands ---

def cmd_run(a: argparse.Namespace) -> int:
    question = sys.stdin.read() if a.question == "-" else Path(a.question).read_text(encoding="utf-8")
    if not question.strip():
        raise CouncilError("the question is empty")
    members = [m.strip() for m in a.members.split(",") if m.strip()]
    if len(members) < 2:
        raise CouncilError("a council needs at least two members")
    if len(members) > len(LABELS):
        raise CouncilError(f"at most {len(LABELS)} members")
    models, _ = parse_pairs(a.model, "model")
    efforts, effort = parse_pairs(a.effort, "effort")
    cfgs = roster(members, models, efforts, effort)
    if a.chair not in ("claude", "session"):
        raise CouncilError("--chair is claude or session")
    # A member whose CLI is not installed here is skipped before anything is spent, and
    # the run goes on with the rest; a login or model refusal still shows up as a stage-1
    # failure, which drops that member the same way.
    skipped = {m: why for m in members if (why := ar.availability(cfgs[m]))}
    members = [m for m in members if m not in skipped]
    cfgs = {m: cfgs[m] for m in members}
    if len(members) < 2:
        raise CouncilError("fewer than two members are available on this machine; skipped: "
                           + "; ".join(f"{m} ({why})" for m, why in skipped.items()), EXIT_FAILED)
    chair = a.chair
    chair_fallback = None
    if chair == "claude":
        chair_cfg = ar.resolve("claude", models.get("claude"), efforts.get("claude") or effort)
        chair_fallback = ar.availability(chair_cfg)
        if chair_fallback:
            chair = "session"
    timeout = int(a.timeout)
    if not 60 <= timeout <= MAX_TIMEOUT:
        raise CouncilError(f"--timeout must be between 60 and {MAX_TIMEOUT}")
    try:
        paths, rels = ar.validate_files(a.file, a.root)
    except ar.ReviewError as exc:
        raise CouncilError(str(exc))

    run_id = _dt.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)
    out = Path(a.out).expanduser().resolve() if a.out else state_dir() / run_id
    if out.exists() and any(out.iterdir()):
        raise CouncilError(f"output dir {out} is not empty")
    out.mkdir(parents=True, exist_ok=True)
    os.chmod(out, 0o700)
    (out / "question.md").write_text(question, encoding="utf-8")
    stage = ar.stage_files(paths, rels, out)
    (out / "files.json").write_text(json.dumps(rels, indent=1), encoding="utf-8")

    started = time.time()
    print(f"council {run_id}: {len(members)} members, {len(rels)} files, out {out}")
    for m, why in skipped.items():
        print(f"  skipped {m:<12} {why}")
    run_extra = {"skipped": skipped, "chair": chair, "chair_fallback": chair_fallback}
    answers = stage1(question, rels, cfgs, stage, out, timeout)
    for m in members:
        state = "ok" if answers[m].get("text") else f"FAILED ({answers[m].get('error')})"
        print(f"  stage 1 {m:<12} {answers[m]['elapsed_s']:>7}s  {state}")
    answered = [m for m in members if answers[m].get("text")]
    if len(answered) < 2:
        _write_run(out, run_id, cfgs, rels, answers, {}, {}, None, started, EXIT_FAILED, run_extra)
        raise CouncilError("fewer than two members answered; nothing to review", EXIT_FAILED)

    reviews, blinding = stage2(question, rels, cfgs, answers, stage, out, timeout)
    for m in members:
        parsed = reviews[m].get("parsed") or {}
        state = "ok" if parsed.get("valid") else f"excluded ({parsed.get('why')})"
        print(f"  stage 2 {m:<12} {reviews[m]['elapsed_s']:>7}s  {state}")
    tally = compute_tally(reviews, answered)
    (out / "tally.json").write_text(json.dumps(tally, indent=1), encoding="utf-8")
    (out / "tally.md").write_text(tally_markdown(tally, cfgs), encoding="utf-8")
    (out / "chair-brief.md").write_text(chair_brief(question, rels, answers, reviews, tally, cfgs), encoding="utf-8")

    synthesis = None
    if chair == "claude":
        res = ar.run_harness(chair_cfg, out / "chair-brief.md", stage, timeout, out)
        res["role"] = "chair"
        (out / "chair.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
        if res.get("text"):
            (out / "synthesis.md").write_text(res["text"], encoding="utf-8")
            synthesis = str(out / "synthesis.md")
            print(f"  chair   claude       {res['elapsed_s']:>7}s  ok")
        else:
            print(f"  chair   claude       {res['elapsed_s']:>7}s  FAILED ({res.get('error')}); write the synthesis from chair-brief.md")
    elif chair_fallback:
        print(f"  chair   session: claude is unavailable ({chair_fallback}); write synthesis.md from chair-brief.md")
    else:
        print("  chair   session: write synthesis.md from chair-brief.md")

    partial = (bool(skipped) or bool(chair_fallback) or len(answered) < len(members)
               or tally["valid_reviews"] < len(members) or (chair == "claude" and not synthesis))
    code = EXIT_PARTIAL if partial else EXIT_OK
    _write_run(out, run_id, cfgs, rels, answers, reviews, tally, synthesis, started, code, run_extra)
    print(f"  order   : {' > '.join(tally['order'])}")
    dropped = {m: answers[m].get("error") for m in members if m not in answered}
    if skipped or dropped or tally.get("invalid_reviews"):
        print("  without : " + "; ".join(
            [f"{m} skipped ({why})" for m, why in skipped.items()]
            + [f"{m} failed stage 1 ({err})" for m, err in dropped.items()]
            + [f"{m} review excluded" for m in tally.get("invalid_reviews", [])]))
    print(f"  out     : {out}")
    return code


def _write_run(out, run_id, cfgs, rels, answers, reviews, tally, synthesis, started, code, extra=None):
    run = {"run_id": run_id, "members": cfgs, "files": rels, **(extra or {}),
           "stage1": {m: {k: v for k, v in r.items() if k != "text"} for m, r in answers.items()},
           "stage2": {m: {k: v for k, v in r.items() if k != "text"} for m, r in reviews.items()},
           "tally": tally, "synthesis": synthesis, "elapsed_s": round(time.time() - started, 1), "exit_code": code}
    (out / "run.json").write_text(json.dumps(run, indent=1), encoding="utf-8")


def cmd_tally(a: argparse.Namespace) -> int:
    out = Path(a.run).expanduser().resolve()
    run = json.loads((out / "run.json").read_text(encoding="utf-8"))
    blinding = json.loads((out / "blinding.json").read_text(encoding="utf-8"))
    reviews = {}
    for m in run["members"]:
        text_path = out / "stage2" / f"{m}.md"
        text = text_path.read_text(encoding="utf-8") if text_path.exists() else None
        reviews[m] = {"parsed": parse_review(text, blinding[m]["labels"])}
    answered = [m for m in run["members"] if (out / "stage1" / f"{m}.md").exists()]
    tally = compute_tally(reviews, answered)
    (out / "tally.json").write_text(json.dumps(tally, indent=1), encoding="utf-8")
    (out / "tally.md").write_text(tally_markdown(tally, run["members"]), encoding="utf-8")
    print((out / "tally.md").read_text(encoding="utf-8"))
    return EXIT_OK


def cmd_clean(a: argparse.Namespace) -> int:
    sdir = state_dir()
    if a.run:
        target = Path(a.run).expanduser().resolve()
        if target.parent != sdir or not (target / "run.json").exists():
            raise CouncilError("--run must name a run directory under the state dir")
        shutil.rmtree(target)
        print(f"removed {target}")
        return EXIT_OK
    cutoff = time.time() - int(a.older_than_days) * 86400
    n = 0
    for d in sdir.iterdir():
        if d.is_dir() and (d / "run.json").exists() and d.stat().st_mtime < cutoff:
            shutil.rmtree(d, ignore_errors=True)
            n += 1
    print(f"removed {n} run(s)")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="council.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run the three stages over a question and a file set")
    r.add_argument("--question", required=True, help="file holding the question and context, or - for stdin")
    r.add_argument("--file", action="append", required=True, help="a file the panel may read; repeatable")
    r.add_argument("--root", help="directory the files are relative to (default: their common parent)")
    r.add_argument("--members", default=",".join(DEFAULT_MEMBERS), help="harnesses: " + ", ".join(ar.HARNESSES))
    r.add_argument("--model", action="append", help="override a member's model: harness=name; repeatable")
    r.add_argument("--effort", action="append", help="a level for every member, or harness=level; repeatable")
    r.add_argument("--out", help="output directory (default: a new run under the state dir)")
    r.add_argument("--chair", default="claude", help="claude runs the chair headless; session leaves chair-brief.md for you")
    r.add_argument("--timeout", default=DEFAULT_TIMEOUT, help=f"seconds per member per stage, max {MAX_TIMEOUT}")
    r.set_defaults(fn=cmd_run)
    t = sub.add_parser("tally", help="recompute the tally from a run's stage-2 reviews")
    t.add_argument("--run", required=True)
    t.set_defaults(fn=cmd_tally)
    c = sub.add_parser("clean")
    c.add_argument("--run")
    c.add_argument("--older-than-days", default=14)
    c.set_defaults(fn=cmd_clean)
    a = ap.parse_args(argv)
    try:
        return a.fn(a)
    except CouncilError as e:
        print(f"council: {e}", file=sys.stderr)
        return e.code
    except subprocess.CalledProcessError as e:
        print(f"council: {' '.join(e.cmd)} failed:\n{(e.stderr or '').strip()}", file=sys.stderr)
        return EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
