#!/usr/bin/env python3
"""Labeled sets for the decision hook, built from session transcripts and the shadow log.

    label.py harvest --since YYYY-MM-DD [--projects DIR] [--log FILE]
    label.py review --set risk|routing [--n 20] [--recheck]
    label.py add --set risk|routing --file CASES.jsonl --stratum NAME
    label.py stats --set risk|routing

Candidates and labels live under the hook's state directory in 0600 files and
never leave the machine. Stdlib only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("decide", HERE / "decide.py")
decide = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(decide)
_spec2 = importlib.util.spec_from_file_location("scrub", HERE / "scrub.py")
scrub = importlib.util.module_from_spec(_spec2)
_spec2.loader.exec_module(scrub)

# Every candidate is scrubbed as it is read: secrets by shape, then the station term
# list. The counts travel in SCRUBBED; the values never go anywhere.
SCRUBBED: dict = {}
TERMS: set = set()

SETS = ("risk", "routing")
REJECTED = "The user doesn't want to proceed"
BLOCKED_RE = re.compile(r"^PreToolUse:\S+ hook error")
OBFUSCATED_RE = re.compile(r"base64|fromhex|\\x[0-9a-fA-F]{2}|\beval\b|\$'|\w''\w|\w\"\"\w|\$\(\s*curl", re.I)
PROMPT_CUT = 500
RECHECK_AFTER_DAYS = 7
RECHECK_SHARE = 10


# ------------------------------------------------------------------ classification

def classify_result(content: str) -> str:
    text = content or ""
    if text.startswith(REJECTED):
        return "rejected"
    if BLOCKED_RE.match(text):
        return "blocked"
    return "ran"


def stratum_of(state: dict) -> str:
    if state.get("tool_name") == "Bash":
        command = str((state.get("tool_input") or {}).get("command", ""))
        if OBFUSCATED_RE.search(command):
            return "obfuscated"
    return "organic"


def split_of(candidate_id: str) -> str:
    return "heldout" if hashlib.sha256(candidate_id.encode()).digest()[0] % 5 == 0 else "tuning"


def make_id(*parts: str) -> str:
    return hashlib.sha256(":".join(parts).encode()).hexdigest()[:24]


def clean(value):
    """Scrub a state or prompt before it is stored; counts go to SCRUBBED."""
    return scrub.scrub_value(value, TERMS, SCRUBBED)


def result_text(block: dict) -> str:
    content = block.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(str(b.get("text", "")) for b in content if isinstance(b, dict))
    return ""


# ------------------------------------------------------------------ transcripts

def read_lines(path: Path) -> list[dict]:
    lines = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for raw in f:
                try:
                    d = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(d, dict):
                    lines.append(d)
    except OSError:
        return []
    return lines


def drift_check(lines: list[dict]) -> list[str]:
    """Names of the fields the harvester relies on that are missing from these lines, in a fixed order."""
    missing: list[str] = []

    def note(name):
        if name not in missing:
            missing.append(name)

    for d in lines:
        if d.get("type") not in ("user", "assistant"):
            continue
        content = (d.get("message") or {}).get("content")
        for b in content if isinstance(content, list) else []:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_use" and not b.get("id"):
                note("tool_use.id")
            if b.get("type") == "tool_result" and not b.get("tool_use_id"):
                note("tool_result.tool_use_id")
        if not d.get("timestamp"):
            note("timestamp")
        if not d.get("sessionId"):
            note("sessionId")
    return missing


def harvest_transcript(path: Path) -> tuple[list[dict], list[dict]]:
    lines = read_lines(path)
    results: dict[str, str] = {}
    for d in lines:
        if d.get("type") != "user":
            continue
        content = (d.get("message") or {}).get("content")
        for b in content if isinstance(content, list) else []:
            if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("tool_use_id"):
                results[str(b["tool_use_id"])] = result_text(b)
    risk: list[dict] = []
    routing: list[dict] = []
    mode = ""
    pending_prompt: dict | None = None
    for d in lines:
        kind = d.get("type")
        if kind not in ("user", "assistant"):
            continue
        session = str(d.get("sessionId") or d.get("session_id") or path.stem)
        ts = str(d.get("timestamp") or "")
        content = (d.get("message") or {}).get("content")
        if kind == "user":
            if d.get("permissionMode"):
                mode = str(d["permissionMode"])
            if isinstance(content, str):
                text = content.strip()
                if text and not text.startswith("<") and not d.get("isMeta") and not d.get("isCompactSummary") and not d.get("isSidechain"):
                    pending_prompt = {"id": make_id(session, str(d.get("uuid") or ts)), "ts": ts, "session": session,
                                      "source": "transcript", "prompt": clean(text[:PROMPT_CUT]), "weak": "none",
                                      "split": None, "label": None, "labeled_at": None, "rechecks": []}
                    pending_prompt["split"] = split_of(pending_prompt["id"])
                    routing.append(pending_prompt)
            continue
        for b in content if isinstance(content, list) else []:
            if not isinstance(b, dict) or b.get("type") != "tool_use":
                continue
            name = str(b.get("name") or "")
            if name == "Skill" and pending_prompt is not None and pending_prompt["weak"] == "none":
                pending_prompt["weak"] = str((b.get("input") or {}).get("skill") or "none")
                continue
            if not decide.WATCHED_TOOLS.match(name):
                continue
            tool_id = str(b.get("id") or "")
            state = clean(decide.build_state({"tool_name": name, "tool_input": b.get("input"), "cwd": d.get("cwd", ""),
                                              "permission_mode": mode}))
            cid = make_id(session, tool_id or json.dumps(state, sort_keys=True))
            risk.append({"id": cid, "ts": ts, "session": session, "source": "transcript", "state": state,
                         "weak": classify_result(results[tool_id]) if tool_id in results else "unknown",
                         "stratum": stratum_of(state), "split": split_of(cid), "label": None, "labeled_at": None,
                         "rechecks": []})
    return risk, routing


def harvest_log(path: Path) -> list[dict]:
    out = []
    for r in read_lines(path):
        if r.get("event") != "PreToolUse" or r.get("outcome") not in ("ask", "none", "capped") or not isinstance(r.get("state"), dict):
            continue
        cid = make_id(str(r.get("session_id") or ""), str(r.get("tool_use_id") or json.dumps(r["state"], sort_keys=True)))
        out.append({"id": cid, "ts": str(r.get("ts") or ""), "session": str(r.get("session_id") or ""), "source": "shadow",
                    "state": clean(r["state"]), "weak": "flagged" if r["outcome"] in ("ask", "capped") else "unflagged",
                    "stratum": stratum_of(r["state"]), "split": split_of(cid), "label": None, "labeled_at": None,
                    "rechecks": [], "probs": r.get("probs")})
    return out


# ------------------------------------------------------------------ storage

def labels_path(name: str) -> Path:
    d = decide.ensure_state() / "labels"
    d.mkdir(exist_ok=True, mode=0o700)
    return d / f"{name}.jsonl"


def load_set(name: str) -> list[dict]:
    return read_lines(labels_path(name))


def save_set(name: str, rows: list[dict]) -> None:
    path = labels_path(name)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, separators=(",", ":")) + "\n")


def merge(existing: list[dict], new: list[dict]) -> int:
    by_id = {r["id"]: r for r in existing}
    added = 0
    for r in new:
        if r["id"] in by_id:
            if r.get("probs") and not by_id[r["id"]].get("probs"):
                by_id[r["id"]]["probs"] = r["probs"]
            continue
        by_id[r["id"]] = r
        existing.append(r)
        added += 1
    return added


def projects_dir() -> Path:
    return Path(os.environ.get("DECISION_HOOK_PROJECTS") or Path.home() / ".claude" / "projects")


# ------------------------------------------------------------------ commands

def load_terms_or_warn() -> None:
    """Load the station term list or refuse: a label set written without it would hold identifiers scrubbed by shape only."""
    TERMS.clear()
    TERMS.update(scrub.load_terms())
    if not TERMS:
        print(f"label: no station term list at {scrub.terms_file()}; refusing to write a label set without it "
              f"(set IDENTIFIER_TERMS_FILE or create the list)", file=sys.stderr)
        sys.exit(3)


def cmd_harvest(a: argparse.Namespace) -> int:
    load_terms_or_warn()
    since = a.since
    since_ts = dt.datetime.fromisoformat(since).replace(tzinfo=dt.timezone.utc).timestamp()
    risk_new: list[dict] = []
    routing_new: list[dict] = []
    drift: list[str] = []
    files = 0
    for path in sorted(Path(a.projects).glob("*/*.jsonl")):
        try:
            if path.stat().st_mtime < since_ts:
                continue
        except OSError:
            continue
        files += 1
        r, p = harvest_transcript(path)
        risk_new += [c for c in r if c["ts"][:10] >= since]
        routing_new += [c for c in p if c["ts"][:10] >= since]
        if files <= 5:
            for name in drift_check(read_lines(path)[:200]):
                if name not in drift:
                    drift.append(name)
    log = Path(a.log) if a.log else decide.state_dir() / "decisions.jsonl"
    if log.exists():
        risk_new += [c for c in harvest_log(log) if c["ts"][:10] >= since]
    for name, new in (("risk", risk_new), ("routing", routing_new)):
        rows = load_set(name)
        added = merge(rows, new)
        save_set(name, rows)
        weak = {}
        for r in rows:
            weak[r["weak"]] = weak.get(r["weak"], 0) + 1
        print(f"{name}: {len(rows)} candidates (+{added} new) from {files} transcripts: "
              + ", ".join(f"{k}={v}" for k, v in sorted(weak.items())))
    print(f"scrubbed before storing: {scrub.summary(SCRUBBED)}; terms loaded: {len(TERMS)}")
    if drift:
        print("warn transcript shape drift: missing " + ", ".join(drift) + "; the harvester may be reading a newer format")
    return 0


def stratified(rows: list[dict], n: int) -> list[dict]:
    """Round-robin across (weak, stratum) classes so a review never sees only the common class."""
    classes: dict = {}
    for r in rows:
        classes.setdefault((r.get("weak"), r.get("stratum")), []).append(r)
    order = sorted(classes)
    picked: list[dict] = []
    i = 0
    while len(picked) < n and any(classes.values()):
        key = order[i % len(order)]
        if classes[key]:
            picked.append(classes[key].pop(0))
        i += 1
    return picked


def show(name: str, r: dict) -> None:
    if name == "risk":
        st = r["state"]
        ti = st.get("tool_input") or {}
        head = str(ti.get("command") or ti.get("file_path") or json.dumps(ti))[:300]
        print(f"\n[{r['weak']}/{r['stratum']}] {st.get('tool_name')} in {st.get('cwd')} ({st.get('permission_mode')})\n  {head}")
        if r.get("probs"):
            print("  model: " + ", ".join(f"{k}={v:.2f}" for k, v in r["probs"].items()))
    else:
        print(f"\n[{r['weak']}] {r['prompt'][:300]}")


def ask(prompt: str) -> str | None:
    sys.stdout.write(prompt)
    sys.stdout.flush()
    line = sys.stdin.readline()
    return line.strip() if line else None


def cmd_review(a: argparse.Namespace) -> int:
    name = a.set
    rows = load_set(name)
    if a.recheck:
        cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=RECHECK_AFTER_DAYS)).isoformat(timespec="seconds")
        due = [r for r in rows if r.get("label") and str(r.get("labeled_at") or "") < cutoff]
        due.sort(key=lambda r: (len(r.get("rechecks") or []), r["id"]))
        batch = due[:a.n if a.n else max(1, len(due) // RECHECK_SHARE)]
    else:
        batch = stratified([r for r in rows if not r.get("label")], a.n or 20)
    if not batch:
        print("nothing to review")
        return 0
    labeled = skipped = agree = 0
    for r in batch:
        show(name, r)
        answer = ask("  [y] should ask  [n] fine  [s] skip: " if name == "risk" else "  skill name, 'none', or [s] skip: ")
        if answer is None:
            break
        if answer.lower() in ("s", ""):
            skipped += 1
            continue
        if name == "risk":
            if answer.lower() not in ("y", "n"):
                skipped += 1
                continue
            label = "ask" if answer.lower() == "y" else "fine"
        else:
            label = answer
        if a.recheck:
            same = label == r["label"]
            r.setdefault("rechecks", []).append(same)
            agree += same
            labeled += 1
        else:
            r["label"] = label
            r["labeled_at"] = decide.now()
            labeled += 1
    save_set(name, rows)
    if a.recheck:
        print(f"\n{labeled} rechecked, {skipped} skipped; agreement {agree}/{labeled}")
    else:
        print(f"\n{labeled} labeled, {skipped} skipped; {sum(1 for r in rows if r.get('label'))} labeled in total")
    return 0


def cmd_add(a: argparse.Namespace) -> int:
    load_terms_or_warn()
    name = a.set
    rows = load_set(name)
    new = []
    for d in read_lines(Path(a.file)):
        if name == "risk":
            if not isinstance(d.get("state"), dict):
                continue
            state = clean(decide.build_state(d["state"]))
            cid = make_id("hand", json.dumps(state, sort_keys=True))
            new.append({"id": cid, "ts": decide.now(), "session": "hand", "source": "hand", "state": state, "weak": "hand",
                        "stratum": a.stratum, "split": split_of(cid), "label": d.get("label"),
                        "labeled_at": decide.now() if d.get("label") else None, "rechecks": []})
        else:
            prompt = clean(str(d.get("prompt") or "").strip())
            if not prompt:
                continue
            cid = make_id("hand", prompt)
            new.append({"id": cid, "ts": decide.now(), "session": "hand", "source": "hand", "prompt": prompt[:PROMPT_CUT],
                        "weak": "hand", "stratum": a.stratum, "split": split_of(cid), "label": d.get("label"),
                        "labeled_at": decide.now() if d.get("label") else None, "rechecks": []})
    added = merge(rows, new)
    save_set(name, rows)
    print(f"{name}: +{added} hand-written cases in stratum {a.stratum}; scrubbed: {scrub.summary(SCRUBBED)}")
    return 0


def cmd_stats(a: argparse.Namespace) -> int:
    rows = load_set(a.set)
    print(f"{a.set}: {len(rows)} candidates, {sum(1 for r in rows if r.get('label'))} labeled")
    for field in ("weak", "stratum", "split", "label", "source"):
        counts: dict = {}
        for r in rows:
            counts[str(r.get(field))] = counts.get(str(r.get(field)), 0) + 1
        print(f"  by {field}: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    checks = [c for r in rows for c in (r.get("rechecks") or [])]
    if checks:
        print(f"  self-agreement: {sum(checks)}/{len(checks)} on rechecks")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    h = sub.add_parser("harvest")
    h.add_argument("--since", required=True, help="YYYY-MM-DD")
    h.add_argument("--projects", default=str(projects_dir()))
    h.add_argument("--log", default=None)
    h.set_defaults(fn=cmd_harvest)
    r = sub.add_parser("review")
    r.add_argument("--set", required=True, choices=SETS)
    r.add_argument("--n", type=int, default=None, help="cases to show (default 20; a tenth of the labeled set with --recheck)")
    r.add_argument("--recheck", action="store_true")
    r.set_defaults(fn=cmd_review)
    ad = sub.add_parser("add")
    ad.add_argument("--set", required=True, choices=SETS)
    ad.add_argument("--file", required=True)
    ad.add_argument("--stratum", required=True)
    ad.set_defaults(fn=cmd_add)
    s = sub.add_parser("stats")
    s.add_argument("--set", required=True, choices=SETS)
    s.set_defaults(fn=cmd_stats)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
