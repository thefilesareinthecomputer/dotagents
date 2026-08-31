#!/usr/bin/env python3
"""Report eval coverage per skill, and catch a file whose shape contradicts its name.

EXECUTE this as part of the completion gate; it is the deterministic half of
gate item 4. It answers two questions the prose alone never enforced:

  - which of the two eval files each skill has, and
  - whether a present file's SHAPE matches its NAME.

The second is the silent failure. `evals/triggers.json` is a flat JSON list of
`{query, should_trigger}` objects read by `run_eval.py`; `evals/evals.json` is
`{skill_name, evals[]}` read by `aggregate_benchmark.py`. Trigger cases stored
in a file named `evals.json` match neither consumer, and no upstream tool says
so - it just silently measures nothing.

A skill whose SKILL.md frontmatter carries `disable-model-invocation: true`
never auto-fires, so it has no triggering to measure and is exempt from
`triggers.json`.

    python3 check_eval_coverage.py                 # this repo, human-readable
    python3 check_eval_coverage.py --root PATH     # another checkout
    python3 check_eval_coverage.py --json

Exit status is 1 only when a present file's shape contradicts its name, which
includes a file no consumer can parse. A missing file is reported and does not
fail: backfill is opportunistic, and a gate nobody can pass gets ignored.

Stdlib only. Offline. Read-only: nothing here writes or deletes.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

TRIGGERS = "triggers.json"
EVALS = "evals.json"

OK = "ok"
MISSING = "missing"
EXEMPT = "exempt"
MISMATCH = "mismatch"
UNPARSEABLE = "unparseable"

FAILING = (MISMATCH, UNPARSEABLE)

SHAPE_OF_NAME = {TRIGGERS: "triggers", EVALS: "evals"}


@dataclass(frozen=True)
class FileReport:
    name: str
    status: str
    detail: str


@dataclass(frozen=True)
class SkillReport:
    skill: str
    exempt: bool
    has_evals_dir: bool
    files: list[FileReport]

    def status_of(self, name: str) -> str:
        for f in self.files:
            if f.name == name:
                return f.status
        return MISSING


def detect_shape(data: object) -> tuple[str, str]:
    """Classify parsed JSON as the triggers shape, the evals shape, or neither."""
    if isinstance(data, list):
        if not data:
            return "unknown", "empty list - no cases to identify a shape from"
        if not all(isinstance(item, dict) for item in data):
            return "unknown", "list contains non-object entries"
        missing = [
            key for key in ("query", "should_trigger")
            if not all(key in item for item in data)
        ]
        if missing:
            return "unknown", f"list of objects, but {' and '.join(missing)} is absent from some case"
        return "triggers", f"flat list of {len(data)} query/should_trigger cases"
    if isinstance(data, dict):
        if "skill_name" in data and isinstance(data.get("evals"), list):
            return "evals", f"skill_name plus {len(data['evals'])} benchmark cases"
        absent = [key for key in ("skill_name", "evals") if key not in data]
        if absent:
            return "unknown", f"object missing {' and '.join(absent)}"
        return "unknown", "object with a non-list evals value"
    return "unknown", f"top-level JSON is {type(data).__name__}, expected a list or an object"


def read_eval_file(path: Path, name: str) -> FileReport:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        return FileReport(name, UNPARSEABLE, f"cannot read file: {exc.strerror or exc}")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return FileReport(name, UNPARSEABLE, f"invalid JSON at line {exc.lineno} column {exc.colno}: {exc.msg}")
    shape, detail = detect_shape(data)
    expected = SHAPE_OF_NAME[name]
    if shape == expected:
        return FileReport(name, OK, detail)
    if shape == "unknown":
        return FileReport(name, MISMATCH, f"not the {expected} shape - {detail}")
    return FileReport(name, MISMATCH, f"{shape} cases in a file named {name} - {detail}")


def is_exempt(skill_md: Path) -> bool:
    """True when frontmatter sets disable-model-invocation: true at the top level."""
    try:
        text = skill_md.read_text(encoding="utf-8")
    except OSError:
        return False
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return False
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, sep, value = line.partition(":")
        if sep and key == "disable-model-invocation" and value.strip().lower() == "true":
            return True
    return False


def check_skill(skill_dir: Path) -> SkillReport:
    exempt = is_exempt(skill_dir / "SKILL.md")
    evals_dir = skill_dir / "evals"
    files: list[FileReport] = []
    for name in (TRIGGERS, EVALS):
        path = evals_dir / name
        if path.is_file():
            files.append(read_eval_file(path, name))
        elif name == TRIGGERS and exempt:
            files.append(FileReport(name, EXEMPT, "disable-model-invocation: true - the skill never auto-fires"))
        else:
            files.append(FileReport(name, MISSING, "no such file"))
    return SkillReport(skill_dir.name, exempt, evals_dir.is_dir(), files)


def check_root(root: Path) -> list[SkillReport]:
    skills_dir = root / "skills"
    if not skills_dir.is_dir():
        return []
    return [
        check_skill(child)
        for child in sorted(skills_dir.iterdir())
        if child.is_dir() and (child / "SKILL.md").is_file()
    ]


def summarize(reports: list[SkillReport]) -> dict[str, int]:
    counts = {
        "skills": len(reports),
        "triggers_ok": 0, "triggers_missing": 0, "triggers_exempt": 0,
        "evals_ok": 0, "evals_missing": 0,
        "mismatches": 0, "unparseable": 0,
        "no_evals_dir": 0,
    }
    for report in reports:
        if not report.has_evals_dir:
            counts["no_evals_dir"] += 1
        for f in report.files:
            key = "triggers" if f.name == TRIGGERS else "evals"
            if f.status == OK:
                counts[f"{key}_ok"] += 1
            elif f.status == MISSING:
                counts[f"{key}_missing"] += 1
            elif f.status == EXEMPT:
                counts["triggers_exempt"] += 1
            elif f.status == MISMATCH:
                counts["mismatches"] += 1
            elif f.status == UNPARSEABLE:
                counts["unparseable"] += 1
    return counts


def render(reports: list[SkillReport], counts: dict[str, int]) -> str:
    lines: list[str] = []
    width = max((len(r.skill) for r in reports), default=0)
    for report in reports:
        if not report.has_evals_dir:
            note = " (exempt from triggers.json)" if report.exempt else ""
            lines.append(f"{report.skill:<{width}}  no evals/ directory{note}")
            continue
        parts = [f"{f.name} {f.status}" for f in report.files]
        lines.append(f"{report.skill:<{width}}  {parts[0]:<24}{parts[1]}")
    problems = [
        (r.skill, f) for r in reports for f in r.files if f.status in FAILING
    ]
    if problems:
        lines.append("")
        for skill, f in problems:
            lines.append(f"{f.status.upper()} skills/{skill}/evals/{f.name} - {f.detail}")
    lines.append("")
    lines.append(
        f"{counts['skills']} skills | "
        f"{TRIGGERS}: {counts['triggers_ok']} ok, {counts['triggers_missing']} missing, "
        f"{counts['triggers_exempt']} exempt | "
        f"{EVALS}: {counts['evals_ok']} ok, {counts['evals_missing']} missing | "
        f"{counts['mismatches']} shape-name mismatches, {counts['unparseable']} unparseable | "
        f"{counts['no_evals_dir']} with no evals/ directory"
    )
    return "\n".join(lines)


def default_root() -> Path:
    """The repo this script ships in: <root>/skills/skill-authoring/scripts/."""
    return Path(__file__).resolve().parents[3]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=None,
                        help="repo root holding skills/ (default: the repo this script sits in)")
    parser.add_argument("--json", action="store_true", help="emit the report as JSON")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve() if args.root else default_root()
    reports = check_root(root)
    counts = summarize(reports)
    failed = counts["mismatches"] + counts["unparseable"] > 0

    if args.json:
        print(json.dumps({
            "root": str(root),
            "skills": [asdict(r) for r in reports],
            "summary": counts,
            "failed": failed,
        }, indent=2))
    elif not reports:
        print(f"no skills found under {root}/skills")
    else:
        print(render(reports, counts))

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
