#!/usr/bin/env python3
"""Build the routing index: every should-trigger and should-not case from each
skill's evals/triggers.json, embedded once on loopback.

    build_index.py [--skills DIR] [--out FILE] [--base-url URL] [--model NAME] [--threshold T] [--report]

--report prints the leave-one-out routing accuracy at a few thresholds instead
of only writing the file. Stdlib only; loopback only.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("decide", HERE / "decide.py")
decide = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(decide)

DEFAULT_SKILLS = Path.home() / ".agents" / "skills"
DEFAULT_OUT = HERE.parent / "references" / "routing-index.json"
BATCH = 32


def collect_cases(skills_dir: Path) -> list[dict]:
    cases = []
    for path in sorted(skills_dir.glob("*/evals/triggers.json")):
        skill = path.parent.parent.name
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError) as e:
            print(f"skip {path}: {e}", file=sys.stderr)
            continue
        for c in data if isinstance(data, list) else []:
            if isinstance(c, dict) and isinstance(c.get("query"), str) and c["query"].strip():
                cases.append({"skill": skill, "should_trigger": bool(c.get("should_trigger")), "query": c["query"].strip()})
    return cases


def embed_all(base_url: str, model: str, texts: list[str]) -> list[list[float]]:
    client = decide.Client(base_url, time.monotonic() + 600)
    vectors: list[list[float]] = []
    try:
        for i in range(0, len(texts), BATCH):
            reply = client.call("POST", "/api/embed", {"model": model, "input": texts[i:i + BATCH], "keep_alive": "5m"})
            batch = reply.get("embeddings") if isinstance(reply, dict) else None
            if not isinstance(batch, list) or len(batch) != len(texts[i:i + BATCH]):
                raise decide.HookError("error", "embed reply holds the wrong number of vectors")
            vectors.extend(batch)
    finally:
        decide.unload(client, model)
    return vectors


def build(skills_dir: Path, out: Path, base_url: str, model: str, threshold: float) -> int:
    cases = collect_cases(skills_dir)
    if not cases:
        sys.exit(f"no triggers.json cases under {skills_dir}")
    try:
        vectors = embed_all(base_url, model, [c["query"] for c in cases])
    except decide.HookError as e:
        sys.exit(f"cannot build the index: {e}")
    index = {"model": model, "threshold": threshold, "built": decide.now(), "dim": len(vectors[0]) if vectors else 0,
             "exemplars": [dict(c, vector=v) for c, v in zip(cases, vectors)]}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(index, separators=(",", ":")) + "\n")
    return len(cases)


def leave_one_out(index: dict, thresholds: list[float]) -> dict:
    exemplars = index.get("exemplars") or []
    report = {}
    for thr in thresholds:
        top1 = none = n_pos = n_neg = 0
        for i, case in enumerate(exemplars):
            rest = {"threshold": thr, "exemplars": exemplars[:i] + exemplars[i + 1:]}
            skill, _ = decide.route(case["vector"], rest)
            if case["should_trigger"]:
                n_pos += 1
                top1 += skill == case["skill"]
            else:
                n_neg += 1
                none += skill is None
        report[thr] = {"top1": round(top1 / n_pos, 3) if n_pos else None, "should_trigger_n": n_pos,
                       "none_rate": round(none / n_neg, 3) if n_neg else None, "should_not_n": n_neg}
    return report


def main(argv: list[str] | None = None) -> int:
    cfg = decide.load_config()
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--skills", type=Path, default=DEFAULT_SKILLS)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--base-url", default=cfg["base_url"])
    p.add_argument("--model", default=cfg["embed_model"])
    p.add_argument("--threshold", type=float, default=0.8)
    p.add_argument("--report", action="store_true", help="print leave-one-out accuracy at 0.6, 0.7, 0.8, 0.85")
    a = p.parse_args(argv)
    n = build(a.skills, a.out, a.base_url, a.model, a.threshold)
    print(f"{n} exemplars from {a.skills} -> {a.out}")
    if a.report:
        index = json.loads(a.out.read_text())
        for thr, row in leave_one_out(index, [0.6, 0.7, 0.8, 0.85]).items():
            print(f"threshold {thr:.2f}: top-1 {row['top1']} on {row['should_trigger_n']} should-trigger cases; "
                  f"none {row['none_rate']} on {row['should_not_n']} should-not cases")
    return 0


if __name__ == "__main__":
    sys.exit(main())
