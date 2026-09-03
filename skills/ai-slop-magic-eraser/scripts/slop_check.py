#!/usr/bin/env python3
"""
Detect the countable tells of machine-generated prose.

EXECUTE this script. Do not read it and reimplement its checks inline.

Covers only what is mechanically decidable: every character a standard keyboard
cannot produce, fixed phrases, and a few shapes with low false-positive rates.
Cadence, structure and factual errors need judgment and live in the skill's
procedure and references/tells.md.

    python3 slop_check.py FILE [FILE...]
    python3 slop_check.py --json FILE
    python3 slop_check.py --fix FILE      # mechanical class only
    python3 slop_check.py --only symbol,sycophancy FILE

Exit 0 clean, 1 findings, 2 usage error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from dataclasses import dataclass, asdict
from pathlib import Path

# --------------------------------------------------------------------------
# Fenced code, inline code and link targets are exempt. Slop inside a code
# block is usually data, and a detector that cannot be quoted is unusable.
# --------------------------------------------------------------------------

FENCE = re.compile(r"^(?P<indent> {0,3})(?P<run>`{3,}|~{3,})(?P<info>.*)$")


def code_line_mask(lines: list[str]) -> list[bool]:
    """True where the line sits inside a fenced block (fences included).

    Follows CommonMark fence rules, which matter because documents nest fences
    to show markdown inside markdown:

      * a fence is 3+ backticks or 3+ tildes, indented at most 3 spaces;
      * a closing fence uses the SAME character and is AT LEAST as long as the
        opener, so ``` cannot close a ```` block (the nesting case);
      * a closing fence carries no info string, so ```` ```python ```` opens a
        block rather than closing one;
      * backtick fences may not carry a backtick in the info string.

    An unterminated fence runs to end of input, matching how renderers treat it.
    """
    mask: list[bool] = []
    char = ""      # fence character of the open block ('`' or '~'), "" if closed
    length = 0     # run length of the opening fence

    for line in lines:
        m = FENCE.match(line)
        if not m:
            mask.append(bool(char))
            continue

        run, info = m.group("run"), m.group("info")
        if not char:
            # Backtick openers cannot contain a backtick in the info string.
            if run[0] == "`" and "`" in info:
                mask.append(False)
                continue
            char, length = run[0], len(run)
            mask.append(True)
        elif run[0] == char and len(run) >= length and not info.strip():
            char, length = "", 0
            mask.append(True)
        else:
            # Wrong character, too short, or carrying an info string: content.
            mask.append(True)
    return mask


INLINE_CODE = re.compile(r"`[^`\n]*`")
LINK_TARGET = re.compile(r"\]\([^)\n]*\)")


def blank_exempt(line: str) -> str:
    """Blank out inline code and link targets, preserving column positions."""
    out = line
    for pat in (INLINE_CODE, LINK_TARGET):
        out = pat.sub(lambda m: " " * len(m.group(0)), out)
    return out


# --------------------------------------------------------------------------
# Rules
# --------------------------------------------------------------------------


@dataclass
class Finding:
    file: str
    line: int
    col: int
    category: str
    matched: str
    message: str


# --------------------------------------------------------------------------
# Non-keyboard characters
#
# A standard typer produces ASCII. Anything outside it arrived from a model, a
# word processor's autocorrect, or a paste, so every non-ASCII character is
# reported and sorted into one of three tiers.
#
#   REPLACE  - an unambiguous ASCII equivalent exists; --fix rewrites it.
#   DELETE   - invisible, or banned by house style; --fix removes it.
#   report   - everything else. Named, never rewritten, because an accented
#              proper noun and a stray math symbol are the same class to a
#              scanner and only a human can tell them apart.
# --------------------------------------------------------------------------

REPLACE: dict[str, str] = {
    # dashes and hyphens
    "—": " - ",    # em dash
    "–": "-",      # en dash
    "‒": "-",      # figure dash
    "―": "-",      # horizontal bar
    "‐": "-",      # hyphen
    "‑": "-",      # non-breaking hyphen
    "−": "-",      # minus sign
    # quotes
    "“": '"',
    "”": '"',
    "‘": "'",
    "’": "'",
    "‚": "'",      # single low-9
    "„": '"',      # double low-9
    "«": '"',      # left guillemet
    "»": '"',      # right guillemet
    "‹": "'",
    "›": "'",
    "′": "'",      # prime
    "″": '"',      # double prime
    # spaces that are not a space
    " ": " ",      # no-break space
    " ": " ",      # figure space
    " ": " ",      # thin space
    " ": " ",      # hair space
    " ": " ",      # en space
    " ": " ",      # em space
    " ": " ",      # narrow no-break space
    " ": " ",      # medium mathematical space
    "　": " ",      # ideographic space
    # punctuation
    "…": "...",    # ellipsis
    "•": "-",      # bullet
    # arrows, which are usually ASCII operators in disguise
    "→": "->",
    "←": "<-",
    "↔": "<->",
    "⇒": "=>",
    "⇐": "<=",
    "⇔": "<=>",
    # math and units
    "×": "x",
    "÷": "/",
    "≤": "<=",
    "≥": ">=",
    "≠": "!=",
    "≈": "~=",
    # ligatures, which paste in from PDFs and break every grep
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬀ": "ff",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
}

# Invisible characters. They are also the vector for instructions hidden from a
# human reviewer, so these are reported even inside code fences.
INVISIBLE = {
    "\N{ZERO WIDTH SPACE}",
    "\N{ZERO WIDTH NON-JOINER}",
    "\N{ZERO WIDTH JOINER}",
    "\N{WORD JOINER}",
    "\N{ZERO WIDTH NO-BREAK SPACE}",  # byte order mark
    "\N{SOFT HYPHEN}",
    "\N{LEFT-TO-RIGHT EMBEDDING}", "\N{RIGHT-TO-LEFT EMBEDDING}",
    "\N{POP DIRECTIONAL FORMATTING}", "\N{LEFT-TO-RIGHT OVERRIDE}",
    "\N{RIGHT-TO-LEFT OVERRIDE}",  # bidi embedding
    "\N{LEFT-TO-RIGHT ISOLATE}", "\N{RIGHT-TO-LEFT ISOLATE}",
    "\N{FIRST STRONG ISOLATE}", "\N{POP DIRECTIONAL ISOLATE}",
}


def _is_tag_char(ch: str) -> bool:
    return 0xE0000 <= ord(ch) <= 0xE007F


EMOJI = re.compile(
    "["
    "\U0001f300-\U0001faff"
    "\U00002600-\U000027bf"
    "\U0001f1e6-\U0001f1ff"
    "\U00002b00-\U00002bff"
    "\U0000fe0f"
    "]"
)

NON_ASCII = re.compile(r"[^\x00-\x7f]")


def char_verdict(ch: str) -> tuple[str, str]:
    """Return (kind, message) for one non-ASCII character.

    kind is 'replace', 'delete' or 'report'.
    """
    if ch in INVISIBLE or _is_tag_char(ch):
        return "delete", (
            f"invisible character {_codepoint(ch)}; it is not on any keyboard "
            "and can hide text from a human reviewer - delete it"
        )
    if EMOJI.match(ch):
        return "delete", f"emoji {_codepoint(ch)}; cut it"
    if ch in REPLACE:
        target = REPLACE[ch]
        return "replace", (
            f"{_codepoint(ch)} is not on a standard keyboard; "
            f"use {target!r}"
        )
    return "report", (
        f"{_codepoint(ch)} is not on a standard keyboard; retype it in ASCII, "
        "or keep it only if a quoted source or proper noun spells it that way"
    )


def _codepoint(ch: str) -> str:
    try:
        name = unicodedata.name(ch)
    except ValueError:
        name = "unnamed"
    return f"U+{ord(ch):04X} {name}"


def scan_chars(
    raw: str, blanked: str, lineno: int, path: Path, in_code: bool
) -> list[Finding]:
    """Findings for every non-ASCII character on one line.

    Visible characters follow the same exemptions as every other rule: fenced
    code, inline code and link targets hold whatever they need, or a detector
    that cannot be quoted is unusable.

    Invisible characters are reported everywhere, exemptions included. A code
    block legitimately holds any visible character and never legitimately holds
    a zero-width space, and the exempt spans are exactly where something hidden
    from a human reviewer would be put.
    """
    out: list[Finding] = []
    for m in NON_ASCII.finditer(raw):
        ch = m.group(0)
        pos = m.start()
        kind, message = char_verdict(ch)
        hidden = ch in INVISIBLE or _is_tag_char(ch)
        if not hidden:
            if in_code:
                continue
            if pos >= len(blanked) or blanked[pos] != ch:
                continue  # blanked out as inline code or a link target
        out.append(
            Finding(
                file=str(path),
                line=lineno,
                col=pos + 1,
                category="symbol",
                matched=ch,
                message=message,
            )
        )
    return out


def phrase(*alts: str) -> re.Pattern:
    """Case-insensitive, word-bounded alternation."""
    body = "|".join(alts)
    return re.compile(rf"(?<![\w-])({body})(?![\w-])", re.IGNORECASE)


# category -> (pattern, message, mechanically_fixable)
RULES: list[tuple[str, re.Pattern, str, bool]] = [
    (
        "sycophancy",
        phrase(
            r"great question",
            r"excellent (question|point|observation)",
            r"that'?s a (great|really|very) (good |insightful )?\w+",
            r"you'?re absolutely right",
            r"i'?d be happy to",
            r"happy to help",
            r"what a (great|fascinating|interesting)",
            r"good catch",
        ),
        "sycophancy; cut it and answer",
        False,
    ),
    (
        "meta",
        phrase(
            r"this (document|section|guide|runbook|file|skill)",
            r"in this (section|document|guide|chapter)",
            r"as (mentioned|noted|described|discussed) (above|below|earlier|previously)",
            r"as we('ll| will) see",
            r"the (following|below) (section|table|list)",
            r"supersedes",
            r"how to read this",
        ),
        "meta-commentary; the subject is the document, not the subject matter",
        False,
    ),
    (
        "hedge",
        phrase(
            r"it'?s worth noting( that)?",
            r"it should be noted( that)?",
            r"it'?s important to (note|understand|remember)",
            r"may or may not",
            r"generally speaking",
            r"arguably",
            r"somewhat",
            r"fairly \w+",
            r"relatively \w+",
            r"in most cases",
        ),
        "hedge; state the fact, or cut the claim entirely",
        False,
    ),
    (
        "register",
        phrase(
            r"leverage[sd]?",
            r"utili[sz]e[sd]?",
            r"facilitate[sd]?",
            r"delve[sd]? into",
            r"seamless(ly)?",
            r"robust",
            r"comprehensive",
            r"holistic",
            r"cutting[- ]edge",
            r"state[- ]of[- ]the[- ]art",
            r"best[- ]in[- ]class",
            r"game[- ]chang(er|ing)",
            r"revolutioni[sz]e[sd]?",
            r"empower[sed]*",
            r"unlock[s]?",
            r"myriad",
            r"plethora",
            r"paradigm",
            r"synerg(y|ies)",
            r"tapestry",
            r"testament to",
            r"landscape",
            r"realm",
        ),
        "inflated register; use the plain word",
        False,
    ),
    (
        "handwave",
        phrase(
            r"significantly",
            r"dramatically",
            r"vastly",
            r"incredibly",
            r"crucial(ly)?",
            r"vital(ly)?",
            r"essential(ly)?",
            r"carefully",
            r"properly",
            r"appropriately",
            r"orders of magnitude",
            r"very",
            r"extremely",
            r"a wide (range|variety) of",
        ),
        "hand-waving; give the mechanism or the number",
        False,
    ),
    (
        "filler",
        phrase(
            r"that said",
            r"furthermore",
            r"moreover",
            r"additionally",
            r"in order to",
            r"at the end of the day",
            r"when it comes to",
            r"it goes without saying",
            r"in today'?s [\w-]+ world",
            r"first and foremost",
            r"let'?s dive in",
            r"in conclusion",
            r"to summari[sz]e",
        ),
        "filler transition; cut it",
        False,
    ),
    (
        "cadence",
        re.compile(r",\s+not\s+(just\s+)?\w", re.IGNORECASE),
        "'X, not Y' antithesis; keep only where the wrong belief is common",
        False,
    ),
    (
        "cadence",
        phrase(r"not only \w+ but also", r"isn'?t just", r"is not just"),
        "correlative padding; state the thing that matters",
        False,
    ),
    (
        "cadence",
        re.compile(r"^\s*#{1,6}\s+.*\?\s*$"),
        "rhetorical question as a heading; use the answer",
        False,
    ),
    (
        "structure",
        re.compile(r"^\s*#{1,6}\s*(key takeaways|tl;?dr|summary of|at a glance)\b", re.I),
        "bolted-on summary section; if it is needed, the document is too long",
        False,
    ),
    (
        "structure",
        re.compile(r"^( {6,}|\t{3,})[-*+]\s"),
        "bullet nested three or more deep",
        False,
    ),
]



def scan(path: Path, only: set[str] | None) -> list[Finding]:
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        print(f"{path}: cannot read: {e}", file=sys.stderr)
        return []

    lines = raw.splitlines()
    in_code = code_line_mask(lines)
    findings: list[Finding] = []

    # A SKILL.md is instructions to a model, not prose a person reads. Its
    # subject IS the document, so "this skill does X" is content, not the
    # tell. Every other rule still applies to it.
    skip = {"meta"} if path.name == "SKILL.md" else set()

    for i, line in enumerate(lines, start=1):
        scannable = blank_exempt(line)
        if only is None or "symbol" in only:
            findings.extend(scan_chars(line, scannable, i, path, in_code[i - 1]))
        if in_code[i - 1]:
            continue
        for category, pattern, message, _ in RULES:
            if category in skip:
                continue
            if only and category not in only:
                continue
            for m in pattern.finditer(scannable):
                if not m.group(0).strip():
                    continue
                findings.append(
                    Finding(
                        file=str(path),
                        line=i,
                        col=m.start() + 1,
                        category=category,
                        matched=m.group(0).strip(),
                        message=message,
                    )
                )
    return findings


def apply_fix(path: Path) -> int:
    """Rewrite only characters with an unambiguous ASCII form, plus delete the
    invisible ones. Report-only characters are never touched: an accented
    proper noun is not a defect, and guessing at one is content loss.

    Fenced code is exempt from rewriting, but NOT from invisible-character
    deletion - a code block legitimately holds any visible character and never
    legitimately holds a zero-width space.
    """
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines(keepends=True)
    in_code = code_line_mask([l.rstrip("\n") for l in lines])

    changed = 0
    out = []
    for line, code in zip(lines, in_code):
        blanked = blank_exempt(line)
        buf: list[str] = []
        deleted = False
        for pos, ch in enumerate(line):
            if ch.isascii():
                buf.append(ch)
                continue
            kind, _ = char_verdict(ch)
            hidden = ch in INVISIBLE or _is_tag_char(ch)
            if hidden:
                changed += 1
                deleted = True
                continue
            # Visible characters obey the same exemptions the scanner does:
            # a fenced block, an inline-code span or a link target keeps what
            # it holds, and rewriting a URL is content loss, not a fix.
            if code or pos >= len(blanked) or blanked[pos] != ch:
                buf.append(ch)
                continue
            if kind == "replace":
                changed += 1
                buf.append(REPLACE[ch])
            elif kind == "delete":
                changed += 1
                deleted = True
            else:
                buf.append(ch)
        new = "".join(buf)
        if deleted and not code:
            indent = new[: len(new) - len(new.lstrip())]
            trail = new[len(new.rstrip()):]
            new = indent + re.sub(r"[ \t]{2,}", " ", new.strip()) + trail
        out.append(new)

    if changed:
        path.write_text("".join(out), encoding="utf-8")
    return changed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("paths", nargs="+", type=Path)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument(
        "--fix",
        action="store_true",
        help="rewrite non-keyboard characters that have an ASCII form, delete "
        "invisible ones and emoji; leaves judgment calls and accented text alone",
    )
    ap.add_argument("--only", help="comma-separated categories to report")
    args = ap.parse_args()

    only = set(c.strip() for c in args.only.split(",")) if args.only else None
    if only:
        known = {c for c, _, _, _ in RULES} | {"symbol"}
        unknown = only - known
        if unknown:
            print(f"unknown categories: {', '.join(sorted(unknown))}", file=sys.stderr)
            print(f"known: {', '.join(sorted(known))}", file=sys.stderr)
            return 2

    files = [p for p in args.paths if p.is_file()]
    if not files:
        print("no readable files given", file=sys.stderr)
        return 2

    if args.fix:
        total = sum(apply_fix(p) for p in files)
        print(f"fixed {total} mechanical character(s) across {len(files)} file(s)")

    findings: list[Finding] = []
    for p in files:
        findings.extend(scan(p, only))

    if args.json:
        print(json.dumps([asdict(f) for f in findings], indent=2))
        return 1 if findings else 0

    if not findings:
        print(f"clean: {len(files)} file(s), no countable tells")
        return 0

    by_cat: dict[str, int] = {}
    for f in findings:
        by_cat[f.category] = by_cat.get(f.category, 0) + 1

    for f in findings:
        print(f"{f.file}:{f.line}:{f.col}  [{f.category}]  {f.matched!r}  {f.message}")

    print()
    print(f"{len(findings)} finding(s) across {len(files)} file(s)")
    for cat, n in sorted(by_cat.items(), key=lambda kv: -kv[1]):
        print(f"  {cat:12} {n}")
    print()
    print("Counts matter more than instances for 'cadence': a handful is style,")
    print("a couple of dozen is the machine signal. Judgment calls are in")
    print("references/tells.md; this script only sees what is countable.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
