#!/usr/bin/env python3
"""stats_check.py - audit an analysis manifest for the errors that fool people.

Input is the JSON manifest stats.py writes with --manifest, or one written by
hand in the same shape. Unknown keys are ignored and missing optional keys are
tolerated: the auditor reports what is present rather than rejecting a file for
its schema. What it cannot see, it does not accuse.

Codes:
  P_VALUE_WITHOUT_EFFECT_SIZE    a p-value with no effect size beside it
  MISSING_INTERVAL               a p-value with no interval and no stated reason
  MISSING_N                      a result or a dataset with no n
  UNCORRECTED_MULTIPLICITY       more than one alternative tried, no correction
  IN_SAMPLE_AS_PERFORMANCE       a metric measured on the data the model was fit on
  CAUSAL_LANGUAGE_OBSERVATIONAL  causal language without random assignment
  SILENT_ROW_DROPS               rows dropped without being counted and reported
  UNSEEDED_RESAMPLING            a bootstrap, permutation or simulation with no seed
  DEGENERATE_SPREAD              a scale estimate of 0 used as if it measured spread
  MISSING_ASSUMPTION             (warning) nothing named that would overturn it
  MANIFEST_UNREADABLE            the file is not JSON, or not an object

Exit codes: 0 clean, 1 findings, 2 the file could not be read.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Finding:
    code: str          # "P_VALUE_WITHOUT_EFFECT_SIZE"
    severity: str      # "error" | "warning"
    where: str         # the manifest key or column the defect sits in
    message: str       # what is wrong
    fix: str           # what to do instead


CAUSAL_PATTERNS = [
    r"\bcause[sd]?\b", r"\bcausing\b", r"\bcausal\b",
    r"\bbecause of\b", r"\bdue to\b",
    r"\bleads? to\b", r"\bled to\b",
    r"\bdrives?\b", r"\bdrove\b", r"\bdriving\b",
    r"\bresults? in\b", r"\bresulted in\b",
    r"\bimpact of\b", r"\beffect of\b", r"\beffects? on\b",
    r"\bmakes? .{0,20}\b(rise|fall|increase|decrease)\b",
]
_CAUSAL_RE = re.compile("|".join(CAUSAL_PATTERNS), re.IGNORECASE)

RESAMPLING_RE = re.compile(
    r"bootstrap|permutation|monte carlo|simulation|resampl|randomi[sz]ed draw",
    re.IGNORECASE)

IN_SAMPLE_VALUES = {"in_sample", "in-sample", "insample", "train", "training", "fitted"}
UNKNOWN_VALUES = {"unknown", "unstated", "", None}


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _results(manifest: dict) -> list[dict]:
    results = manifest.get("results")
    if isinstance(results, dict):
        return [results]
    if isinstance(results, list):
        return [r for r in results if isinstance(r, dict)]
    return []


def _text_fields(manifest: dict) -> list[tuple[str, str]]:
    """Every free-text claim in the manifest, with the key it came from."""
    out: list[tuple[str, str]] = []
    for key in ("claims", "conclusions", "notes", "summary"):
        value = manifest.get(key)
        if isinstance(value, str):
            out.append((key, value))
        elif isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, str):
                    out.append((f"{key}[{i}]", item))
    for i, result in enumerate(_results(manifest)):
        for key in ("claim", "conclusion", "interpretation"):
            if isinstance(result.get(key), str):
                out.append((f"results[{i}].{key}", result[key]))
    return out


# --------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------

def check_effect_size(manifest: dict) -> list[Finding]:
    findings = []
    for i, result in enumerate(_results(manifest)):
        if result.get("p_value") is None:
            continue
        effect = result.get("effect_size")
        has_effect = (
            (isinstance(effect, dict) and effect.get("value") is not None)
            or _is_number(effect)
            or (isinstance(effect, str) and effect.strip() != "")
        )
        if not has_effect:
            findings.append(Finding(
                code="P_VALUE_WITHOUT_EFFECT_SIZE",
                severity="error",
                where=f"results[{i}].effect_size ({result.get('name', 'unnamed')})",
                message="a p-value is reported with no effect size beside it, so the "
                        "result says something happened without saying how much",
                fix="report the difference in the units of the data, or a standardized "
                    "effect size such as Cohen's d, next to the p-value",
            ))
    return findings


def check_interval(manifest: dict) -> list[Finding]:
    findings = []
    for i, result in enumerate(_results(manifest)):
        if result.get("p_value") is None:
            continue
        interval = result.get("interval")
        ok = isinstance(interval, dict) and interval.get("lo") is not None \
            and interval.get("hi") is not None
        if isinstance(interval, (list, tuple)) and len(interval) == 2:
            ok = True
        if ok or result.get("interval_omitted_reason"):
            continue
        findings.append(Finding(
            code="MISSING_INTERVAL",
            severity="error",
            where=f"results[{i}].interval ({result.get('name', 'unnamed')})",
            message="a p-value is reported with no interval, so the range of values "
                    "the data is compatible with is unstated",
            fix="add a confidence or bootstrap interval on the estimate, or state "
                "interval_omitted_reason if the quantity genuinely cannot carry one",
        ))
    return findings


def check_sample_size(manifest: dict) -> list[Finding]:
    findings = []
    data = manifest.get("data") if isinstance(manifest.get("data"), dict) else {}
    results = _results(manifest)
    data_n = data.get("n")
    for i, result in enumerate(results):
        if _is_number(result.get("n")):
            continue
        if _is_number(data_n):
            continue
        findings.append(Finding(
            code="MISSING_N",
            severity="error",
            where=f"results[{i}].n ({result.get('name', 'unnamed')})",
            message="this result carries no n, and the dataset block does not supply "
                    "one either, so its precision cannot be judged",
            fix="record the number of observations the result was computed from",
        ))
    if not results and not _is_number(data_n):
        findings.append(Finding(
            code="MISSING_N",
            severity="error",
            where="data.n",
            message="the manifest reports no sample size anywhere",
            fix="record n in the data block",
        ))
    return findings


def check_multiplicity(manifest: dict) -> list[Finding]:
    comparisons = manifest.get("comparisons")
    if not isinstance(comparisons, dict):
        return []
    tried = comparisons.get("tried")
    if not _is_number(tried) or tried <= 1:
        return []
    correction = comparisons.get("correction")
    if isinstance(correction, str) and correction.strip().lower() not in ("", "none"):
        return []
    return [Finding(
        code="UNCORRECTED_MULTIPLICITY",
        severity="error",
        where="comparisons.correction",
        message=f"{int(tried)} alternatives were tried and no correction was applied; "
                "with enough attempts a winner is guaranteed whether or not one exists",
        fix="apply Holm or Benjamini-Hochberg across the alternatives tried, or "
            "report the number tried beside the p-value and treat it as exploratory",
    )]


def check_in_sample(manifest: dict) -> list[Finding]:
    design = manifest.get("design") if isinstance(manifest.get("design"), dict) else {}
    value = design.get("evaluation_data")
    if isinstance(value, str) and value.strip().lower() in IN_SAMPLE_VALUES:
        return [Finding(
            code="IN_SAMPLE_AS_PERFORMANCE",
            severity="error",
            where="design.evaluation_data",
            message="the metrics were measured on the data the model was fit on, which "
                    "describes the fit and not expected performance",
            fix="evaluate on held-out rows or by cross-validation, and label the "
                "in-sample number as fit quality if it is reported at all",
        )]
    if value is not None and str(value).strip().lower() in UNKNOWN_VALUES:
        return [Finding(
            code="IN_SAMPLE_AS_PERFORMANCE",
            severity="warning",
            where="design.evaluation_data",
            message="the split is unstated, so nothing rules out that the model saw "
                    "these rows in training",
            fix="record whether these predictions are on held-out rows, "
                "cross-validated folds, or the training data",
        )]
    return []


def check_causal_claims(manifest: dict) -> list[Finding]:
    design = manifest.get("design") if isinstance(manifest.get("design"), dict) else {}
    randomized = design.get("randomized_assignment")
    if randomized is True:
        return []
    if design.get("observational") is False and randomized is not False:
        return []
    findings = []
    for where, text in _text_fields(manifest):
        match = _CAUSAL_RE.search(text)
        if not match:
            continue
        findings.append(Finding(
            code="CAUSAL_LANGUAGE_OBSERVATIONAL",
            severity="error",
            where=where,
            message=f"causal language ({match.group(0)!r}) in a claim from data with no "
                    "random assignment recorded",
            fix="say 'associated with' rather than 'causes', or record the assignment "
                "mechanism that licenses the causal reading",
        ))
    return findings


def check_row_drops(manifest: dict) -> list[Finding]:
    data = manifest.get("data")
    if not isinstance(data, dict):
        return []
    dropped = data.get("rows_dropped")
    reported = data.get("rows_dropped_reported")
    findings = []
    if _is_number(dropped) and dropped > 0 and reported is not True:
        findings.append(Finding(
            code="SILENT_ROW_DROPS",
            severity="error",
            where="data.rows_dropped_reported",
            message=f"{int(dropped)} rows were dropped without being reported to the "
                    "reader, and a dropped row is a claim that it did not matter",
            fix="count missing and non-numeric rows, report the counts beside the "
                "result, and set rows_dropped_reported once you have",
        ))
    rows_total, n = data.get("rows_total"), data.get("n")
    if (not _is_number(dropped) and _is_number(rows_total) and _is_number(n)
            and rows_total > n):
        findings.append(Finding(
            code="SILENT_ROW_DROPS",
            severity="error",
            where="data.rows_dropped",
            message=f"{int(rows_total)} rows went in and {int(n)} were used, with no "
                    "account of the difference",
            fix="record rows_dropped with the reason each row was unusable",
        ))
    return findings


def check_seeding(manifest: dict) -> list[Finding]:
    randomization = manifest.get("randomization")
    findings = []
    if isinstance(randomization, dict):
        seeded = randomization.get("seeded")
        seed = randomization.get("seed")
        if seeded is False or seed is None:
            findings.append(Finding(
                code="UNSEEDED_RESAMPLING",
                severity="error",
                where="randomization.seed",
                message="a randomized procedure ran with no seed recorded, so the "
                        "interval it produced cannot be reproduced",
                fix="pass --seed and record it; an unreproducible interval is not a result",
            ))
        return findings
    for i, result in enumerate(_results(manifest)):
        method = result.get("method")
        if isinstance(method, str) and RESAMPLING_RE.search(method):
            findings.append(Finding(
                code="UNSEEDED_RESAMPLING",
                severity="error",
                where=f"results[{i}].method",
                message=f"the method is resampling-based ({method!r}) but the manifest "
                        "records no seed",
                fix="record the seed and the number of replicates in a randomization block",
            ))
    return findings


def check_degenerate_spread(manifest: dict) -> list[Finding]:
    data = manifest.get("data") if isinstance(manifest.get("data"), dict) else {}
    if data.get("degenerate_scale") is not True:
        return []
    return [Finding(
        code="DEGENERATE_SPREAD",
        severity="error",
        where=f"data.degenerate_scale ({data.get('column', 'unnamed column')})",
        message="the robust scale estimate for this column is 0, so over half its "
                "values are identical and every distinct value looks like an outlier",
        fix="switch to the mean-absolute-deviation fallback, or treat the column as "
            "categorical and check its rates instead of its spread",
    )]


def check_assumptions(manifest: dict) -> list[Finding]:
    stated = manifest.get("assumptions")
    if isinstance(stated, str) and stated.strip():
        return []
    if isinstance(stated, list) and any(isinstance(s, str) and s.strip() for s in stated):
        return []
    for result in _results(manifest):
        if isinstance(result.get("assumption"), str) and result["assumption"].strip():
            return []
    return [Finding(
        code="MISSING_ASSUMPTION",
        severity="warning",
        where="assumptions",
        message="no assumption is named, so the reader cannot tell what would "
                "overturn the conclusion",
        fix="name the assumption whose violation would change the answer, such as "
            "independence, normality, exchangeability or a representative sample",
    )]


CHECKS = [
    check_effect_size,
    check_interval,
    check_sample_size,
    check_multiplicity,
    check_in_sample,
    check_causal_claims,
    check_row_drops,
    check_seeding,
    check_degenerate_spread,
    check_assumptions,
]


def audit(manifest: dict) -> list[Finding]:
    """Run every check. Order is stable so output is diffable."""
    findings: list[Finding] = []
    for check in CHECKS:
        findings.extend(check(manifest))
    return findings


def audit_path(path: str) -> list[Finding]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            manifest = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        return [Finding(
            code="MANIFEST_UNREADABLE",
            severity="error",
            where=path,
            message=f"could not read this manifest as JSON: {exc}",
            fix="pass the file stats.py wrote with --manifest, or valid JSON in that shape",
        )]
    if not isinstance(manifest, dict):
        return [Finding(
            code="MANIFEST_UNREADABLE",
            severity="error",
            where=path,
            message="the manifest is valid JSON but not an object",
            fix="the manifest is a JSON object with data, results and design keys",
        )]
    return audit(manifest)


def render_text(path: str, findings: list[Finding]) -> str:
    if not findings:
        return f"{path}: clean, 0 findings"
    lines = [f"{path}: {len(findings)} finding(s)"]
    for f in findings:
        lines.append(f"  [{f.severity}] {f.code} at {f.where}")
        lines.append(f"    {f.message}")
        lines.append(f"    fix: {f.fix}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="stats_check.py",
        description="Audit an analysis manifest for defects that a conclusion "
                    "cannot survive. Reports specific codes, not a vague warning.",
    )
    parser.add_argument("paths", nargs="+", help="manifest JSON files")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--warnings-as-errors", action="store_true",
                        help="exit non-zero on warnings too")
    args = parser.parse_args(argv)

    reports = []
    errors = warnings = 0
    unreadable = False
    for path in args.paths:
        findings = audit_path(path)
        errors += sum(1 for f in findings if f.severity == "error")
        warnings += sum(1 for f in findings if f.severity == "warning")
        unreadable = unreadable or any(f.code == "MANIFEST_UNREADABLE" for f in findings)
        reports.append({"path": path, "findings": [asdict(f) for f in findings]})

    if args.json:
        print(json.dumps({
            "reports": reports,
            "counts": {"error": errors, "warning": warnings},
        }, indent=2))
    else:
        for report, path in zip(reports, args.paths):
            print(render_text(path, [Finding(**f) for f in report["findings"]]))

    if unreadable:
        return 2
    if errors or (warnings and args.warnings_as_errors):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
