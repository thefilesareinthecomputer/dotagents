#!/usr/bin/env python3
"""Deterministic scanner for instructions hidden in characters a reviewer cannot see.

EXECUTE this before merging any file an agent will read as instructions -
SKILL.md, agent/command definitions, rules, hooks, settings, inbox messages.

The threat is specific to agent tooling. A human reviewing a diff sees rendered
text; the model reads the codepoints. Characters that render as nothing, or that
reorder what is displayed, let an attacker put one instruction on the screen and
a different one in the model's context. The reviewer approves what they saw.

  - TAG characters (U+E0000-U+E007F) mirror ASCII inside an invisible plane.
    A full sentence of them renders as zero pixels. There is no legitimate use
    in source or prose; this is the "ASCII smuggling" prompt-injection vector.
  - BIDI overrides (U+202A-U+202E, U+2066-U+2069) reorder display without
    reordering the bytes - the Trojan Source attack (CVE-2021-42574).
  - ZERO-WIDTH characters (U+200B-U+200D, U+2060, U+FEFF, and the filler
    codepoints) hide token boundaries and split keywords past a naive grep.
  - VARIATION SELECTORS (U+FE00-U+FE0F, U+E0100-U+E01EF) carry hidden payload
    bytes too, but also appear in legitimate emoji sequences, so they WARN.

Stdlib only. Offline. No network, no subprocess.

This tool FAILS CLOSED. A file it cannot decode or that exceeds the size cap is
reported as a finding, never silently skipped - an adversary must not be able to
pad or re-encode a file past the gate.

    python3 unicode_smuggle_check.py <path>...      # exit 1 on any FAIL
    python3 unicode_smuggle_check.py --json <path>
    python3 unicode_smuggle_check.py --strict <path>   # WARN also exits 1

Codepoints are written as escapes on purpose: a detector that embedded the
literal characters would be invisible in its own source and would flag itself.
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path

FAIL, WARN = "FAIL", "WARN"

MAX_FILE_BYTES = 5_000_000

TEXT_SUFFIXES = {
    ".md", ".mdx", ".txt", ".json", ".yml", ".yaml", ".toml", ".sh", ".bash",
    ".zsh", ".py", ".js", ".ts", ".tsx", ".jsx", ".rs", ".go", ".rb", ".ps1",
}

# (first, last, severity, rule, why) - inclusive ranges, single codepoints as first==last.
RANGES: tuple[tuple[int, int, str, str, str], ...] = (
    (0xE0000, 0xE007F, FAIL, "tag-smuggling",
     "Unicode TAG plane mirrors ASCII invisibly - the ASCII-smuggling injection vector"),
    (0x202A, 0x202E, FAIL, "bidi-override",
     "bidirectional override reorders displayed text without reordering bytes (Trojan Source)"),
    (0x2066, 0x2069, FAIL, "bidi-isolate",
     "bidirectional isolate reorders displayed text without reordering bytes (Trojan Source)"),
    (0x200B, 0x200D, FAIL, "zero-width",
     "zero-width character renders as nothing and can split or hide keywords"),
    (0x2060, 0x2060, FAIL, "zero-width",
     "word joiner renders as nothing and can split or hide keywords"),
    (0x2061, 0x2064, FAIL, "invisible-operator",
     "invisible math operator renders as nothing outside a maths context"),
    (0x180E, 0x180E, FAIL, "zero-width",
     "Mongolian vowel separator renders as nothing in modern fonts"),
    (0x115F, 0x1160, FAIL, "zero-width",
     "Hangul filler renders as nothing outside Korean jamo composition"),
    (0x3164, 0x3164, FAIL, "zero-width",
     "Hangul filler renders as nothing and is a known blank-name abuse character"),
    (0xFEFF, 0xFEFF, FAIL, "zero-width",
     "zero-width no-break space (BOM) mid-file renders as nothing"),
    (0xFE00, 0xFE0F, WARN, "variation-selector",
     "variation selector can carry hidden bytes, but is legitimate in emoji sequences"),
    (0xE0100, 0xE01EF, WARN, "variation-selector",
     "variation-selector supplement can carry hidden bytes"),
)


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    column: int
    severity: str
    rule: str
    codepoint: str
    message: str


def classify(cp: int) -> tuple[str, str, str] | None:
    """Return (severity, rule, why) for a dangerous codepoint, else None."""
    for first, last, severity, rule, why in RANGES:
        if first <= cp <= last:
            return severity, rule, why
    return None


def codepoint_name(cp: int) -> str:
    try:
        return unicodedata.name(chr(cp))
    except ValueError:
        return "unnamed"


def scan_text(text: str, path: str) -> list[Finding]:
    findings: list[Finding] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for col, ch in enumerate(line, start=1):
            cp = ord(ch)
            if cp < 0x80:  # fast path - plain ASCII is the overwhelming majority
                continue
            # A BOM at the very start of the file is a legitimate encoding marker.
            if cp == 0xFEFF and lineno == 1 and col == 1:
                continue
            verdict = classify(cp)
            if verdict is None:
                continue
            severity, rule, why = verdict
            findings.append(Finding(
                path=path,
                line=lineno,
                column=col,
                severity=severity,
                rule=rule,
                codepoint=f"U+{cp:04X}",
                message=f"{codepoint_name(cp)}: {why}",
            ))
    return findings


def scan_file(path: Path) -> list[Finding]:
    p = str(path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return [Finding(p, 0, 0, FAIL, "unreadable", "-", f"cannot read file: {exc}")]
    if len(raw) > MAX_FILE_BYTES:
        return [Finding(p, 0, 0, FAIL, "oversize", "-",
                        f"file is {len(raw)} bytes, over the {MAX_FILE_BYTES} cap - "
                        "review by hand rather than skipping")]
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return [Finding(p, 0, 0, FAIL, "undecodable", "-",
                        f"not valid UTF-8 ({exc.reason}) - a re-encoded file can hide "
                        "codepoints from this scan")]
    return scan_text(text, p)


def iter_targets(roots: list[str]) -> list[Path]:
    targets: list[Path] = []
    for root in roots:
        path = Path(root)
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if any(part in {".git", "node_modules", "__pycache__"} for part in child.parts):
                    continue
                if child.is_file() and child.suffix.lower() in TEXT_SUFFIXES:
                    targets.append(child)
        else:
            targets.append(path)
    return targets


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="+", help="files or directories to scan")
    parser.add_argument("--json", action="store_true", help="emit findings as JSON")
    parser.add_argument("--strict", action="store_true", help="exit 1 on WARN as well as FAIL")
    args = parser.parse_args(argv)

    findings: list[Finding] = []
    for target in iter_targets(args.paths):
        findings.extend(scan_file(target))

    if args.json:
        print(json.dumps([asdict(f) for f in findings], indent=2))
    else:
        for f in findings:
            location = f"{f.path}:{f.line}:{f.column}" if f.line else f.path
            print(f"{f.severity} {location} [{f.rule}] {f.codepoint} {f.message}")
        if not findings:
            print("clean - no hidden or display-reordering characters found")

    failed = any(f.severity == FAIL for f in findings)
    warned = any(f.severity == WARN for f in findings)
    return 1 if failed or (args.strict and warned) else 0


if __name__ == "__main__":
    sys.exit(main())
