#!/usr/bin/env python3
"""Score a decision model or the routing index on the labeled sets.

    evaluate.py --set risk --model tev1:0.8b [--calibrate] [--sweep] [--budget 2.0] [--write-params]
    evaluate.py --set routing

Model answers are cached per (model, candidate) under the state directory, so a
re-run with new thresholds costs nothing. Platt scaling and thresholds are fitted
on the tuning split only; the held-out split is reported and never tuned on.
Reports hold numbers, never states. Stdlib only; loopback only.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("decide", HERE / "decide.py")
decide = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(decide)
platt = decide.platt

GRID = [i / 20 for i in range(1, 20)]   # 0.05 .. 0.95


# ------------------------------------------------------------------ metrics

def flagged_by(row: dict, question: dict) -> bool:
    return decide.decide_risk(row.get("probs") or {}, question) is not None


def metrics(rows: list[dict], question: dict) -> dict:
    n = len(rows)
    ask = [r for r in rows if r.get("label") == "ask"]
    fine = [r for r in rows if r.get("label") == "fine"]
    hits = sum(flagged_by(r, question) for r in ask)
    false = sum(flagged_by(r, question) for r in fine)
    out = {"n": n, "should_ask": len(ask), "flagged": hits + false,
           "recall": round(hits / len(ask), 4) if ask else None,
           "false_escalations_per_100": round(100.0 * false / n, 2) if n else None, "by_stratum": {}}
    for stratum in sorted({str(r.get("stratum")) for r in rows}):
        sub = [r for r in rows if str(r.get("stratum")) == stratum]
        out["by_stratum"][stratum] = metrics_flat(sub, question)
    return out


def metrics_flat(rows: list[dict], question: dict) -> dict:
    ask = [r for r in rows if r.get("label") == "ask"]
    fine = [r for r in rows if r.get("label") == "fine"]
    hits = sum(flagged_by(r, question) for r in ask)
    false = sum(flagged_by(r, question) for r in fine)
    return {"n": len(rows), "recall": round(hits / len(ask), 4) if ask else None,
            "false_escalations_per_100": round(100.0 * false / len(rows), 2) if rows else None}


# ------------------------------------------------------------------ calibration

def fit_platt(ps: list[float], ys: list[int], steps: int = 500) -> dict:
    """Logistic fit of y on logit(p): sigmoid(a*logit(p)+b), by gradient descent with a light L2 pull toward identity."""
    if len(ps) < 4 or len(set(ys)) < 2:
        return {"a": 1.0, "b": 0.0}
    xs = [math.log(min(max(p, 1e-6), 1 - 1e-6) / (1 - min(max(p, 1e-6), 1 - 1e-6))) for p in ps]
    a, b, lr, lam = 1.0, 0.0, 0.05, 0.01
    for _ in range(steps):
        ga = lam * (a - 1.0)
        gb = lam * b
        for x, y in zip(xs, ys):
            pred = 1.0 / (1.0 + math.exp(-(a * x + b)))
            ga += (pred - y) * x / len(xs)
            gb += (pred - y) / len(xs)
        a -= lr * ga
        b -= lr * gb
    return {"a": round(a, 4), "b": round(b, 4)}


def calibrate(rows: list[dict], question: dict) -> dict:
    """Per-option Platt parameters fitted on rows that carry probabilities and a label."""
    params = {}
    for option in question.get("thresholds") or {}:
        ps = [float((r.get("probs") or {}).get(option, 0.0)) for r in rows]
        ys = [1 if r.get("label") == "ask" else 0 for r in rows]
        params[option] = fit_platt(ps, ys)
    return params


def sweep(rows: list[dict], question: dict, budget_per_100: float, passes: int = 3) -> dict:
    """Coordinate descent over per-option thresholds: the most recall whose false escalations stay under budget."""
    options = list(question.get("thresholds") or {})
    thresholds = {o: 0.95 for o in options}

    def score(th):
        m = metrics_flat(rows, dict(question, thresholds=th))
        fe = m["false_escalations_per_100"] or 0.0
        rec = m["recall"] or 0.0
        return (fe <= budget_per_100, rec, -fe)

    for _ in range(passes):
        for option in options:
            best = max(GRID, key=lambda t: score(dict(thresholds, **{option: t})))
            thresholds[option] = best
    return thresholds


# ------------------------------------------------------------------ live loop

def cache_path(model: str) -> Path:
    d = decide.ensure_state() / "evals"
    d.mkdir(exist_ok=True, mode=0o700)
    return d / ("cache-" + "".join(c if c.isalnum() else "_" for c in model) + ".jsonl")


def load_cache(path: Path) -> dict:
    out = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
                out[r["id"]] = r
            except (ValueError, KeyError):
                continue
    except OSError:
        pass
    return out


def append_cache(path: Path, record: dict) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, separators=(",", ":")) + "\n")


def labeled(name: str, path: Path | None = None) -> list[dict]:
    path = path or decide.state_dir() / "labels" / f"{name}.jsonl"
    rows = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("label"):
                rows.append(r)
    except OSError:
        sys.exit(f"no labeled set at {path}; run label.py harvest and review first")
    if not rows:
        sys.exit(f"no labels in {path}; run label.py review first")
    return rows


def write_report(name: str, report: dict) -> Path:
    d = decide.ensure_state() / "evals"
    d.mkdir(exist_ok=True, mode=0o700)
    path = d / f"{name}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    return path


def eval_risk(a: argparse.Namespace) -> int:
    cfg = decide.load_config()
    question = decide.load_question()
    rows = labeled("risk", Path(a.labels) if a.labels else None)
    for r in rows:
        # a scenario file without splits gets the labeler's rule: a stable fifth held out by id hash
        r.setdefault("split", "heldout" if hashlib.sha256(str(r["id"]).encode()).digest()[0] % 5 == 0 else "tuning")
        r.setdefault("stratum", "organic")
    cache = load_cache(cache_path(a.model + ("-" + Path(a.labels).stem if a.labels else "")))
    client = decide.Client(cfg["base_url"], time.monotonic() + 3600)
    latencies = []
    asked = 0
    for r in rows:
        hit = cache.get(r["id"])
        if hit and hit.get("probs"):
            r["probs"] = hit["probs"]
            continue
        t = time.monotonic()
        try:
            reply = client.call("POST", "/v1/systemone", {"model": a.model, "state": r.get("state"), "keep_alive": "10m",
                                                          "questions": {question["name"]: question["question"]}})
            r["probs"] = decide.parse_probabilities(reply, question["name"])
        except decide.HookError as e:
            print(f"warn {r['id']}: {e}", file=sys.stderr)
            r["probs"] = None
            continue
        ms = round((time.monotonic() - t) * 1000)
        latencies.append(ms)
        asked += 1
        append_cache(cache_path(a.model + ("-" + Path(a.labels).stem if a.labels else "")), {"id": r["id"], "probs": r["probs"], "ms": ms})
    if asked:
        decide.unload(client, a.model)
    rows = [r for r in rows if r.get("probs")]
    tuning = [r for r in rows if r.get("split") == "tuning"]
    heldout = [r for r in rows if r.get("split") == "heldout"]
    q = dict(question)
    if a.calibrate:
        q["platt"] = calibrate(tuning, q)
    if a.sweep:
        q["thresholds"] = sweep(tuning, q, a.budget)
    lat = sorted(latencies)

    def by_category(subset):
        out: dict = {}
        for r in subset:
            if r.get("label") == "ask":
                c = out.setdefault(str(r.get("category", "?")), {"flagged": 0, "n": 0})
                c["n"] += 1
                c["flagged"] += flagged_by(r, q)
        return out

    report = {"set": "risk", "model": a.model, "when": decide.now(), "asked_now": asked, "n_labeled": len(rows),
              "params": {"thresholds": q["thresholds"], "platt": q.get("platt") or {}},
              "tuning": dict(metrics(tuning, q), by_category=by_category(tuning)),
              "heldout": dict(metrics(heldout, q), by_category=by_category(heldout)),
              "all": dict(metrics(rows, q), by_category=by_category(rows)),
              "p95_ms": lat[max(0, int(0.95 * len(lat)) - 1)] if lat else None,
              "median_ms": lat[len(lat) // 2] if lat else None}
    path = write_report("risk", report)
    h = report["heldout"]
    print(f"{a.model}: held-out n={h['n']} recall={h['recall']} false escalations per 100={h['false_escalations_per_100']}; "
          f"tuning n={report['tuning']['n']} recall={report['tuning']['recall']} fe/100={report['tuning']['false_escalations_per_100']}; "
          f"p95 {report['p95_ms']} ms over {asked} fresh calls")
    for name, part in (("held-out", h), ("all rows", report["all"])):
        for stratum, m in part["by_stratum"].items():
            print(f"  {name} {stratum}: n={m['n']} recall={m['recall']} fe/100={m['false_escalations_per_100']}")
        for cat, c in sorted(part["by_category"].items()):
            print(f"  {name} category {cat}: {c['flagged']}/{c['n']} flagged")
    print(f"params: thresholds {q['thresholds']}" + (f" platt {q['platt']}" if a.calibrate else ""))
    print(f"report {path}")
    if a.write_params:
        risk_path = decide.REFS / "risk.json"
        current = json.loads(risk_path.read_text())
        current["thresholds"] = q["thresholds"]
        current["platt"] = q.get("platt") or {}
        risk_path.write_text(json.dumps(current, indent=2) + "\n")
        print(f"wrote thresholds and platt parameters into {risk_path}")
    return 0


def eval_routing(a: argparse.Namespace) -> int:
    cfg = decide.load_config()
    rows = labeled("routing")
    try:
        index = json.loads(decide.index_path().read_text())
    except (OSError, ValueError):
        sys.exit(f"no routing index at {decide.index_path()}; run build_index.py")
    client = decide.Client(cfg["base_url"], time.monotonic() + 3600)
    cache = load_cache(cache_path("embed-" + str(index.get("model"))))
    for r in rows:
        hit = cache.get(r["id"])
        if hit and hit.get("vector"):
            r["vector"] = hit["vector"]
            continue
        reply = client.call("POST", "/api/embed", {"model": index.get("model"), "input": r["prompt"], "keep_alive": "5m"})
        r["vector"] = reply["embeddings"][0]
        append_cache(cache_path("embed-" + str(index.get("model"))), {"id": r["id"], "vector": r["vector"]})
    if any("vector" in r and r["id"] not in cache for r in rows):
        decide.unload(client, str(index.get("model")))

    def at(threshold):
        idx = dict(index, threshold=threshold)
        pos = [r for r in rows if r["label"] != "none"]
        neg = [r for r in rows if r["label"] == "none"]
        top1 = sum(decide.route(r["vector"], idx)[0] == r["label"] for r in pos)
        none = sum(decide.route(r["vector"], idx)[0] is None for r in neg)
        return {"threshold": threshold, "top1": round(top1 / len(pos), 3) if pos else None, "n_pos": len(pos),
                "none_rate": round(none / len(neg), 3) if neg else None, "n_neg": len(neg)}

    report = {"set": "routing", "model": index.get("model"), "when": decide.now(), "n_labeled": len(rows),
              "at_index_threshold": at(float(index.get("threshold", 0.8))),
              "sweep": [at(t) for t in (0.5, 0.6, 0.7, 0.8, 0.85, 0.9)]}
    path = write_report("routing", report)
    r0 = report["at_index_threshold"]
    print(f"routing at threshold {r0['threshold']}: top-1 {r0['top1']} on {r0['n_pos']} prompts; none {r0['none_rate']} on {r0['n_neg']}")
    for row in report["sweep"]:
        print(f"  threshold {row['threshold']}: top-1 {row['top1']} none {row['none_rate']}")
    print(f"report {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--set", required=True, choices=["risk", "routing"])
    p.add_argument("--model", default=None)
    p.add_argument("--calibrate", action="store_true")
    p.add_argument("--sweep", action="store_true")
    p.add_argument("--budget", type=float, default=2.0, help="false escalations per 100 calls the sweep may spend")
    p.add_argument("--write-params", action="store_true", help="write the fitted thresholds and platt into references/risk.json")
    p.add_argument("--labels", default=None, help="a labeled JSONL file to score instead of the state labels (references/scenarios.jsonl)")
    a = p.parse_args(argv)
    if a.set == "risk":
        a.model = a.model or decide.load_config()["model"]
        return eval_risk(a)
    return eval_routing(a)


if __name__ == "__main__":
    sys.exit(main())
