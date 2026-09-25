#!/usr/bin/env python3
"""Check each skill's frontmatter description against the length caps and the colon rule.

EXECUTE this after editing any SKILL.md frontmatter; it is the deterministic half of
audit item 2. A description loads into every session whether its skill fires or not,
so the house caps it at HOUSE_MAX characters, inside the open standard's hard limit
of STANDARD_MAX. A plain scalar (unquoted, not a block) containing ": " fails too:
Claude Code's lenient parser accepts it, and stricter harnesses reject the skill.

    python3 check_descriptions.py                 # every skills/*/SKILL.md in this repo
    python3 check_descriptions.py --root PATH     # another checkout
    python3 check_descriptions.py FILE...         # specific SKILL.md files

Length is counted on the parsed value. A folded block (`>` or `>-`) joins its lines
with single spaces, a literal block (`|`) keeps its line breaks, and the quotes
around a quoted scalar do not count.

Exit status is 1 when any description is missing, over a cap, or a plain scalar
containing ": ". Stdlib only. Offline. Read-only.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

HOUSE_MAX = 800
STANDARD_MAX = 1024


@dataclass(frozen=True)
class Description:
    text: str | None
    style: str  # plain, quoted, folded, literal, or missing


def frontmatter(text: str) -> list[str] | None:
    """The lines between the opening and closing `---`, or None when absent."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return lines[1:i]
    return None


def fold(lines: list[str]) -> str:
    """YAML folding: lines join with spaces, and a blank line becomes a line break."""
    paragraphs: list[str] = []
    current: list[str] = []
    for line in lines:
        if line:
            current.append(line)
        elif current:
            paragraphs.append(" ".join(current))
            current = []
    if current:
        paragraphs.append(" ".join(current))
    return "\n".join(paragraphs)


def parse_description(text: str) -> Description:
    lines = frontmatter(text)
    if lines is None:
        return Description(None, "missing")
    for i, line in enumerate(lines):
        if not line.startswith("description:"):
            continue
        value = line[len("description:"):].strip()
        continuation: list[str] = []
        for following in lines[i + 1:]:
            if following.strip() and not following[0].isspace():
                break
            continuation.append(following.strip())
        while continuation and not continuation[-1]:
            continuation.pop()
        if value.startswith(">"):
            return Description(fold(continuation), "folded")
        if value.startswith("|"):
            return Description("\n".join(continuation), "literal")
        joined = " ".join([value] + [part for part in continuation if part])
        quote = value[:1]
        if quote in ("'", '"') and len(joined) >= 2 and joined.endswith(quote):
            inner = joined[1:-1]
            inner = inner.replace("''", "'") if quote == "'" else inner.replace('\\"', '"')
            return Description(inner, "quoted")
        return Description(joined, "plain")
    return Description(None, "missing")


def problems(desc: Description) -> list[str]:
    if desc.text is None:
        return ["no description in the frontmatter"]
    found: list[str] = []
    length = len(desc.text)
    if length > STANDARD_MAX:
        found.append(f"over the standard's hard limit of {STANDARD_MAX}")
    elif length > HOUSE_MAX:
        found.append(f"over the house cap of {HOUSE_MAX}")
    if desc.style == "plain" and ": " in desc.text:
        found.append("plain scalar contains ': ' - use a spaced hyphen or a >- folded block")
    return found


def default_root() -> Path:
    """The repo this script ships in: <root>/skills/skill-authoring/scripts/."""
    return Path(__file__).resolve().parents[3]


def skill_files(root: Path) -> list[Path]:
    skills_dir = root / "skills"
    if not skills_dir.is_dir():
        return []
    return sorted(p for p in skills_dir.glob("*/SKILL.md") if p.is_file())


def display(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root))
    except ValueError:
        return str(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="*", help="SKILL.md files to check (default: every skill in the repo)")
    parser.add_argument("--root", default=None,
                        help="repo root holding skills/ (default: the repo this script sits in)")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve() if args.root else default_root()
    paths = [Path(f) for f in args.files] if args.files else skill_files(root)
    if not paths:
        print(f"no skills found under {root}/skills")
        return 0

    failing = 0
    longest = (0, "")
    for path in paths:
        try:
            desc = parse_description(path.read_text(encoding="utf-8"))
        except OSError as exc:
            print(f"FAIL  {display(path, root)} - cannot read: {exc.strerror or exc}")
            failing += 1
            continue
        length = len(desc.text) if desc.text is not None else 0
        if length > longest[0]:
            longest = (length, display(path, root))
        found = problems(desc)
        if found:
            failing += 1
            print(f"FAIL  {length:>5}  {display(path, root)} - {'; '.join(found)}")

    print(f"{len(paths)} checked, {failing} failing | house cap {HOUSE_MAX}, "
          f"standard limit {STANDARD_MAX} | longest {longest[0]} ({longest[1] or 'none'})")
    return 1 if failing else 0


if __name__ == "__main__":
    sys.exit(main())
