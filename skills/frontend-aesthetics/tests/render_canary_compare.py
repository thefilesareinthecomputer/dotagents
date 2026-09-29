#!/usr/bin/env python3
"""Compare one render_probe.js result with the canary expectations.

    python3 render_canary_compare.py --page defects.html --width 320 probe-output.json
    python3 render_canary_compare.py --page clean.html --width 1440 probe-output.json

The probe output file holds the object the probe returned, or a JSON string of it.
fixtures/render/expected.json names, per page and width, the status every check must
report and the seeded ids that must appear in its items, in targets.inline, or as
unmeasurable contrast items. The echoed viewport.innerWidth must equal --width, and
the clean page may not report findings anywhere.

Prints one line per mismatch, then PASS or FAIL. Exit 0 on pass, 1 on mismatch, and
2 on bad input. Stdlib only, no network, no file writes.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

EXPECTED = Path(__file__).resolve().parent / "fixtures" / "render" / "expected.json"


def show(value: object) -> str:
    """Echo a probe value on one line; probe output is page-derived and untrusted."""
    return json.dumps(value, ensure_ascii=True)[:80]


def load_probe(path: Path) -> dict:
    """Return the probe object from a file holding the object or a JSON string of it."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, str):
        data = json.loads(data)
    if not isinstance(data, dict):
        raise ValueError("probe output is not a JSON object")
    return data


def find_seed(entries: object, seed: str) -> dict | None:
    """Return the first entry whose sel names the seeded id, if any."""
    if not isinstance(entries, list):
        return None
    pattern = re.compile("#" + re.escape(seed) + r"(?![\w-])")
    for entry in entries:
        if isinstance(entry, dict) and isinstance(entry.get("sel"), str) and pattern.search(entry["sel"]):
            return entry
    return None


def compare(expected: dict, probe: dict, width: int) -> list[str]:
    """Return one line per difference between a probe result and one page-width expectation."""
    problems: list[str] = []
    viewport = probe.get("viewport")
    inner = viewport.get("innerWidth") if isinstance(viewport, dict) else None
    if inner != width:
        problems.append(f"viewport.innerWidth is {show(inner)}, expected {width}")
    checks = probe.get("checks") if isinstance(probe.get("checks"), dict) else {}
    clean = expected.get("noFindings") is True
    cut = " (probe output was truncated)" if probe.get("truncated") is True else ""

    for name, spec in expected["checks"].items():
        check = checks.get(name)
        if not isinstance(check, dict):
            problems.append(f"{name}: missing from probe output")
            continue
        status = check.get("status")
        if status != spec["status"]:
            why = ""
            if clean and status == "findings":
                why = "; the clean page may not report findings"
            elif name == "focus" and status == "unmeasurable" and expected.get("focusMeasured") is True:
                why = f"; press Tab {expected.get('tabPresses', 1)} time(s) after loading, then evaluate"
            problems.append(f"{name}: status is {show(status)}, expected {show(spec['status'])}{why}")
        items = check.get("items") if isinstance(check.get("items"), list) else []
        odd = [i for i in items if isinstance(i, dict) and i.get("unmeasurable") is True]
        plain = [i for i in items if not (isinstance(i, dict) and i.get("unmeasurable") is True)]
        for seed in spec.get("items", []):
            if find_seed(plain, seed) is None:
                problems.append(f"{name}: {seed} missing from items{cut}")
        for seed in spec.get("unmeasurable", []):
            if find_seed(odd, seed) is None:
                problems.append(f"{name}: {seed} missing from unmeasurable items{cut}")
        for seed in spec.get("inline", []):
            if find_seed(check.get("inline"), seed) is None:
                problems.append(f"{name}: {seed} missing from inline{cut}")
        for seed in spec.get("notItems", []):
            if find_seed(items, seed) is not None:
                problems.append(f"{name}: {seed} must not appear in items")
        for seed, reasons in spec.get("reasons", {}).items():
            entry = find_seed(plain, seed)
            if entry is not None and entry.get("reasons") != reasons:
                problems.append(f"{name}: {seed} reasons are {show(entry.get('reasons'))}, expected {show(reasons)}")

    if clean:
        for name, check in checks.items():
            if name not in expected["checks"] and isinstance(check, dict) and check.get("status") == "findings":
                problems.append(f"{show(name)}: the clean page may not report findings")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description="Compare a render_probe.js result with the canary expectations.")
    ap.add_argument("--page", required=True, help="fixture page name, for example defects.html")
    ap.add_argument("--width", required=True, type=int, help="requested viewport width in CSS px")
    ap.add_argument("probe_output", type=Path, help="file holding the probe result")
    args = ap.parse_args()

    expected = json.loads(EXPECTED.read_text(encoding="utf-8"))
    page = expected["pages"].get(args.page)
    if page is None or str(args.width) not in page:
        print(f"error: no expectation for {args.page} at {args.width} px", file=sys.stderr)
        return 2
    try:
        probe = load_probe(args.probe_output)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        print(f"error: cannot read probe output: {exc}", file=sys.stderr)
        return 2

    problems = compare(page[str(args.width)], probe, args.width)
    if probe.get("probe") != expected["probe"]:
        problems.insert(0, f"probe is {show(probe.get('probe'))}, expected {show(expected['probe'])}")
    for line in problems:
        print(line)
    print("FAIL" if problems else "PASS")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
