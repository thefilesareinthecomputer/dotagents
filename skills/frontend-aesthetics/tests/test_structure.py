#!/usr/bin/env python3
"""Structural tests for the skill's interface, references, and eval files.

    python3 -B -m unittest discover -s skills/frontend-aesthetics/tests -p 'test_structure.py'

Checks the house limits (description cap, body budget, flat references with
contents lists), that every relative link and heading anchor resolves, that the
operator file names each shipped script, that no em dash, en dash, or emoji
reaches the published prose, and the shape of both eval files. Stdlib only, no
network.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
REPO = SKILL_DIR.parents[1]
SKILL = SKILL_DIR / "SKILL.md"
REFERENCES = SKILL_DIR / "references"
TRIGGERS = SKILL_DIR / "evals" / "triggers.json"
EVALS = SKILL_DIR / "evals" / "evals.json"
CHECKER = REPO / "skills" / "skill-authoring" / "scripts" / "check_descriptions.py"

DESCRIPTION_MAX = 800
BODY_MAX = 200
CONTENTS_THRESHOLD = 100
CONTENTS_WINDOW = 25
SCRIPTS = ("slop_check.py", "check_contrast.py", "render_probe.js")

# The same codepoint ranges as the emoji rule in scripts/slop_check.py.
EMOJI = re.compile("[\U0001f300-\U0001faff\U00002600-\U000027bf\U0001f1e6-\U0001f1ff]")
DASHES = (chr(0x2013), chr(0x2014))  # en dash, em dash

FENCE = re.compile(r"^\s*(```|~~~)")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
CODE_SPAN = re.compile(r"`[^`\n]*`")
LINK = re.compile(r"!?\[[^\]\n]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:|^//")
CONTENTS_ENTRY = re.compile(r"^\s*[-*] \[[^\]]+\]\(#[^)]+\)")

TRIGGER_KEYS = {"name", "query", "should_trigger", "why"}
ORIGINAL_TRIGGERS = [
    ("builds-a-landing-page", "Build me a landing page for my open-source ledger tool.", True),
    ("ui-looks-ai-generated", "This dashboard I generated looks like every other AI site. Fix it.", True),
    ("redesign-request", "Can you make this pricing page look less generic?", True),
    ("chart-not-page", "Plot the catalog growth over the last six months as a line chart.", False),
    ("backend-bug", "The ingest script is dropping rows when the TSV has a trailing tab.", False),
    ("pure-css-bug", "The nav overlaps the hero on Safari but not Chrome.", False),
]


def split_frontmatter(text: str) -> tuple[list[str], str]:
    """Return the frontmatter lines and the body after the closing `---`."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise AssertionError("SKILL.md does not open with a frontmatter fence")
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return [ln.rstrip("\n") for ln in lines[1:i]], "".join(lines[i + 1:])
    raise AssertionError("SKILL.md frontmatter has no closing fence")


def description(front: list[str]) -> str:
    """Parse a plain, quoted, or folded description value from frontmatter lines."""
    for i, line in enumerate(front):
        if not line.startswith("description:"):
            continue
        value = line[len("description:"):].strip()
        rest: list[str] = []
        for following in front[i + 1:]:
            if following.strip() and not following[0].isspace():
                break
            rest.append(following.strip())
        if value.startswith(">"):
            return " ".join(part for part in rest if part)
        joined = " ".join([value] + [part for part in rest if part])
        if len(joined) >= 2 and joined[0] in "'\"" and joined[-1] == joined[0]:
            return joined[1:-1]
        return joined
    raise AssertionError("no description in the frontmatter")


def prose_lines(text: str) -> list[str]:
    """Lines outside fenced code blocks, with inline code spans removed."""
    out: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence:
            out.append(CODE_SPAN.sub("", line))
    return out


def slug(heading: str) -> str:
    """GitHub's anchor rule: lowercase, drop punctuation except hyphens and underscores, spaces to hyphens."""
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def anchors(path: Path) -> set[str]:
    """Every heading anchor in a Markdown file, with GitHub's -1, -2 suffixes for repeats."""
    seen: dict[str, int] = {}
    found: set[str] = set()
    in_fence = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        match = None if in_fence else HEADING.match(line)
        if match is None:
            continue
        base = slug(match.group(2))
        count = seen.get(base, 0)
        found.add(base if count == 0 else f"{base}-{count}")
        seen[base] = count + 1
    return found


def reference_files() -> list[Path]:
    return sorted(p for p in REFERENCES.iterdir() if p.is_file() and p.suffix == ".md")


class DescriptionAndBody(unittest.TestCase):
    def setUp(self) -> None:
        self.front, self.body = split_frontmatter(SKILL.read_text(encoding="utf-8"))

    def test_frontmatter_names_the_skill(self) -> None:
        self.assertIn(f"name: {SKILL_DIR.name}", self.front)
        self.assertIn("license: MIT", self.front)

    def test_description_within_house_cap(self) -> None:
        text = description(self.front)
        self.assertGreater(len(text), 0)
        self.assertLessEqual(len(text), DESCRIPTION_MAX, f"description is {len(text)} characters")

    @unittest.skipUnless(CHECKER.is_file(), "skill-authoring's check_descriptions.py is not in this checkout")
    def test_check_descriptions_passes(self) -> None:
        result = subprocess.run(
            [sys.executable, "-B", str(CHECKER), str(SKILL)],
            cwd=REPO, capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_body_within_budget(self) -> None:
        lines = len(self.body.splitlines())
        self.assertLessEqual(lines, BODY_MAX, f"SKILL.md body is {lines} lines")

    def test_names_each_shipped_script(self) -> None:
        text = SKILL.read_text(encoding="utf-8")
        for name in SCRIPTS:
            with self.subTest(script=name):
                self.assertTrue((SKILL_DIR / "scripts" / name).is_file(), f"scripts/{name} is missing")
                self.assertIn(name, text)


class LinksAndReferences(unittest.TestCase):
    def test_relative_links_and_anchors_resolve(self) -> None:
        for source in [SKILL, *reference_files()]:
            for line in prose_lines(source.read_text(encoding="utf-8")):
                for target in LINK.findall(line):
                    if SCHEME.match(target):
                        continue
                    path_part, _, fragment = target.partition("#")
                    dest = (source.parent / path_part).resolve() if path_part else source
                    with self.subTest(file=source.name, link=target):
                        self.assertTrue(dest.is_file(), f"{target} does not resolve to a file")
                        if fragment and dest.suffix == ".md":
                            self.assertIn(fragment, anchors(dest), f"no heading for #{fragment} in {dest.name}")

    def test_long_references_have_contents(self) -> None:
        for path in reference_files():
            lines = path.read_text(encoding="utf-8").splitlines()
            if len(lines) <= CONTENTS_THRESHOLD:
                continue
            entries = [ln for ln in lines[:CONTENTS_WINDOW] if CONTENTS_ENTRY.match(ln)]
            with self.subTest(reference=path.name):
                self.assertGreaterEqual(len(entries), 3, f"{path.name} has no contents list in its first {CONTENTS_WINDOW} lines")

    def test_references_are_one_level_deep(self) -> None:
        nested = [p.name for p in REFERENCES.iterdir() if p.is_dir()]
        self.assertEqual(nested, [], "references/ must not contain subdirectories")

    def test_no_dashes_or_emoji(self) -> None:
        for path in [SKILL, *reference_files()]:
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                with self.subTest(file=path.name, line=number):
                    for dash in DASHES:
                        self.assertNotIn(dash, line, f"U+{ord(dash):04X} on line {number}")
                    self.assertIsNone(EMOJI.search(line), f"emoji on line {number}")


class EvalFiles(unittest.TestCase):
    def test_triggers_shape(self) -> None:
        cases = json.loads(TRIGGERS.read_text(encoding="utf-8"))
        self.assertIsInstance(cases, list)
        self.assertEqual(len(cases), 24)
        for case in cases:
            with self.subTest(case=case.get("name") if isinstance(case, dict) else case):
                self.assertIsInstance(case, dict)
                self.assertEqual(set(case), TRIGGER_KEYS)
                self.assertIsInstance(case["should_trigger"], bool)
                for key in ("name", "query", "why"):
                    self.assertIsInstance(case[key], str)
                    self.assertTrue(case[key].strip())
        names = [case["name"] for case in cases]
        self.assertEqual(len(names), len(set(names)), "trigger names must be unique")
        self.assertIn(False, [case["should_trigger"] for case in cases])

    def test_original_triggers_preserved(self) -> None:
        cases = json.loads(TRIGGERS.read_text(encoding="utf-8"))
        head = [(c["name"], c["query"], c["should_trigger"]) for c in cases[: len(ORIGINAL_TRIGGERS)]]
        self.assertEqual(head, ORIGINAL_TRIGGERS)

    def test_behavior_evals_shape(self) -> None:
        data = json.loads(EVALS.read_text(encoding="utf-8"))
        self.assertEqual(data["skill_name"], SKILL_DIR.name)
        self.assertEqual(len(data["evals"]), 6)
        for scenario in data["evals"]:
            with self.subTest(eval=scenario.get("name", scenario.get("id"))):
                self.assertTrue(scenario["files"])
                for rel in scenario["files"]:
                    self.assertTrue((REPO / rel).is_file(), f"{rel} does not exist")


if __name__ == "__main__":
    unittest.main()
