#!/usr/bin/env python3
"""Check a project knowledge vault against the contract in its AGENTS.md.

    vault_lint.py <vault-path> [--json]

Ten checks, each firing on positive evidence. Exit 0 clean, 1 on any finding or any file
the linter could not inspect, 2 on a usage error. Standard library only, offline.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

CONTRACT_FILES = {"AGENTS.md", "CLAUDE.md"}
RESERVED_FILES = {"index.md", "log.md"}
TOOLING_DIRS = {"vault-kg"}

# filename prefix -> allowed type values, most specific first
FAMILIES: list[tuple[re.Pattern[str], set[str]]] = [
    (re.compile(r"^notes-chat\.md$"), {"chat_log"}),
    (re.compile(r"^notes-meetings\.md$"), {"meeting_note"}),
    (re.compile(r"^notes-[a-z0-9-]+\.md$"), {"note"}),
    (re.compile(r"^user-stories(-[a-z0-9-]+)?\.md$"), {"user_story"}),
    (re.compile(r"^\d\d-[a-z0-9-]+\.md$"), {"reference"}),
    (re.compile(r"^agents-[a-z0-9-]+\.md$"), {"reference"}),
    (re.compile(r"^code-[a-z0-9-]+\.md$"), {"code"}),
    (re.compile(r"^docs-[a-z0-9-]+\.md$"), {"doc"}),
]
KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*\.md$")
ISO_DATE = r"\d{4}-\d{2}-\d{2}"
DATED_H2_RE = re.compile(rf"^## (({ISO_DATE}|YYYY-MM-DD)(-\S.*)?|PREP: \S.*|Related)$")
ISO_RE = re.compile(rf"\b{ISO_DATE}\b")
PLACEHOLDER_RE = re.compile(r"\bYYYY-MM-DD\b")
WIKILINK_RE = re.compile(r"\[\[([^\]\|#]+)(?:#([^\]\|]+))?(?:\|[^\]]*)?\]\]")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
BOARD_GRAMMAR_RE = re.compile(r"(EPIC|FEATURE|STORY)-\{id\}|- Parent: FEATURE-\{")
DATED_CAPTURE_EXEMPT = {"notes-questions.md"}


@dataclass
class Finding:
    check: str
    file: str
    line: int
    message: str

    def render(self) -> str:
        where = f"{self.file}:{self.line}" if self.line else self.file
        return f"{where}: [{self.check}] {self.message}"


def strip_fences_and_comments(text: str) -> list[str]:
    """Lines with fenced code and HTML comments blanked, so neither produces findings."""
    out: list[str] = []
    in_fence = False
    in_comment = False
    for line in text.splitlines():
        if not in_comment and FENCE_RE.match(line):
            in_fence = not in_fence
            out.append("")
            continue
        if in_fence:
            out.append("")
            continue
        if in_comment:
            if "-->" in line:
                in_comment = False
                line = line.split("-->", 1)[1]
            else:
                out.append("")
                continue
        if "<!--" in line:
            before, rest = line.split("<!--", 1)
            if "-->" in rest:
                line = before + rest.split("-->", 1)[1]
            else:
                in_comment = True
                line = before
        line = re.sub(r"`[^`]*`", "", line)
        out.append(line)
    return out


def parse_frontmatter(text: str) -> tuple[dict[str, str] | None, int]:
    """Top-level keys of a leading YAML block, or None when there is none.
    Returns (keys, body_start_line). Values are the raw string after the colon."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, 0
    keys: dict[str, str] = {}
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return keys, i + 1
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if m:
            keys[m.group(1)] = m.group(2).strip().strip("'\"")
    return None, 0  # opened, never closed


def headings(lines: list[str]) -> list[tuple[int, int, str]]:
    """(line number, level, text) for every heading outside fences and comments."""
    found = []
    for n, line in enumerate(lines, start=1):
        m = HEADING_RE.match(line)
        if m:
            found.append((n, len(m.group(1)), m.group(2)))
    return found


class Linter:
    def __init__(self, vault: Path) -> None:
        self.vault = vault
        self.findings: list[Finding] = []
        self.notes: dict[str, str] = {}
        self.clean: dict[str, list[str]] = {}

    def add(self, check: str, file: str, line: int, message: str) -> None:
        self.findings.append(Finding(check, file, line, message))

    def run(self) -> list[Finding]:
        self.check_flat()
        self.load()
        self.check_reserved()
        for name in sorted(self.notes):
            if name in CONTRACT_FILES:
                continue
            self.check_filename(name)
            if name in RESERVED_FILES:
                continue
            self.check_frontmatter(name)
        self.check_links()
        self.check_dated_grammar()
        self.check_log_order()
        self.check_board_deferral()
        self.check_placeholders()
        return self.findings

    def check_flat(self) -> None:
        for p in sorted(self.vault.iterdir()):
            if p.is_dir() and p.name not in TOOLING_DIRS and not p.name.startswith("."):
                self.add("flat", p.name, 0, "subdirectory under the vault root; the vault is one flat directory")

    def load(self) -> None:
        for p in sorted(self.vault.glob("*.md")):
            try:
                text = p.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                self.add("unreadable", p.name, 0, f"could not inspect: {exc}")
                continue
            self.notes[p.name] = text
            self.clean[p.name] = strip_fences_and_comments(text)

    def check_reserved(self) -> None:
        for name in sorted(RESERVED_FILES):
            if name not in self.notes:
                self.add("reserved", name, 0, "reserved file missing")
                continue
            keys, _ = parse_frontmatter(self.notes[name])
            if keys is None:
                continue
            extra = set(keys) - ({"okf_version"} if name == "index.md" else set())
            if extra:
                self.add("reserved", name, 1, f"frontmatter not allowed on a reserved file: {', '.join(sorted(extra))}")

    def check_filename(self, name: str) -> None:
        if not KEBAB_RE.match(name):
            self.add("filename", name, 0, "not lowercase-kebab")

    def check_frontmatter(self, name: str) -> None:
        keys, _ = parse_frontmatter(self.notes[name])
        if keys is None:
            self.add("frontmatter", name, 1, "no parseable YAML frontmatter")
            return
        typ = keys.get("type", "")
        if not typ:
            self.add("frontmatter", name, 1, "frontmatter has no non-empty type")
            return
        for pattern, allowed in FAMILIES:
            if pattern.match(name):
                if typ not in allowed:
                    self.add("family", name, 1, f"type '{typ}' is not allowed for this family (expected {', '.join(sorted(allowed))})")
                return
        self.add("family", name, 0, "filename prefix belongs to no family in the contract")

    def check_links(self) -> None:
        stems = {Path(n).stem: n for n in self.notes}
        for name, lines in self.clean.items():
            for n, line in enumerate(lines, start=1):
                for m in WIKILINK_RE.finditer(line):
                    target, anchor = m.group(1).strip(), m.group(2)
                    key = Path(target).name
                    key = key[:-3] if key.endswith(".md") else key
                    if key not in stems:
                        self.add("wikilink", name, n, f"[[{target}]] resolves to no note in the vault")
                        continue
                    if anchor:
                        want = anchor.strip()
                        have = {h[2] for h in headings(self.clean[stems[key]])}
                        if want not in have:
                            self.add("anchor", name, n, f"[[{target}#{want}]] names a heading that does not exist")

    def check_dated_grammar(self) -> None:
        for name, lines in self.clean.items():
            if not name.startswith("notes-") or name in DATED_CAPTURE_EXEMPT:
                continue
            for n, level, text in headings(lines):
                if level == 2 and not DATED_H2_RE.match(f"## {text}"):
                    self.add("dated", name, n, f"H2 '{text}' is not YYYY-MM-DD-...")

    def check_log_order(self) -> None:
        lines = self.clean.get("log.md")
        if not lines:
            return
        dates = []
        for n, level, text in headings(lines):
            if level != 2:
                continue
            if text == "YYYY-MM-DD":
                continue
            if not re.fullmatch(ISO_DATE, text):
                self.add("dated", "log.md", n, f"H2 '{text}' is not an ISO date")
                continue
            dates.append((n, text))
        for (n1, d1), (n2, d2) in zip(dates, dates[1:]):
            if d2 > d1:
                self.add("dated", "log.md", n2, f"{d2} appears below {d1}; log.md is newest first")

    def check_board_deferral(self) -> None:
        text = self.notes.get("user-stories.md")
        if not text:
            return
        for n, line in enumerate(text.splitlines(), start=1):
            if BOARD_GRAMMAR_RE.search(line):
                self.add("board", "user-stories.md", n, "restates sprint-board's grammar instead of pointing at the skill")

    def check_placeholders(self) -> None:
        for name, lines in self.clean.items():
            # ingested families are byte-identical upstream content, never hand-edited
            if name in CONTRACT_FILES or name.startswith(("code-", "docs-")):
                continue
            body = "\n".join(lines)
            if not ISO_RE.search(body):
                continue
            for n, line in enumerate(lines, start=1):
                if PLACEHOLDER_RE.search(line):
                    self.add("placeholder", name, n, "literal YYYY-MM-DD in a note that already carries real dates")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("vault", type=Path, help="the project vault folder")
    parser.add_argument("--json", action="store_true", help="emit findings as JSON")
    args = parser.parse_args(argv)
    if not args.vault.is_dir():
        parser.error(f"not a directory: {args.vault}")

    findings = Linter(args.vault).run()
    if args.json:
        print(json.dumps([f.__dict__ for f in findings], indent=2))
    else:
        for f in findings:
            print(f.render())
        print(f"{len(findings)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
