#!/usr/bin/env python3
"""Deterministic AI-slop linter for generated UI code.

EXECUTE this — do not paraphrase its rules into a prompt and eyeball them.
The whole point is that these checks are mechanical: same input, same verdict,
no model in the loop. Stdlib only, no network, no API key.

    python3 slop_check.py <path>...          # human output, exit 1 on any FAIL
    python3 slop_check.py --json <path>...   # machine output
    python3 slop_check.py --warn-only <path> # never exit non-zero

Scope: UI source (.jsx .tsx .js .ts .html .css .scss .svelte .vue .astro).
Prose files are skipped by default — an em-dash is a tell in a headline, not
in your README.

Only rules that are COUNTABLE live here. Judgment calls ("is this motion
motivated?", "does this serif fit the brand?") are in SKILL.md and stay human;
a linter that pretends to score taste would be the same self-certifying theater
this skill exists to replace.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

UI_SUFFIXES = {".jsx", ".tsx", ".js", ".ts", ".html", ".css", ".scss", ".svelte", ".vue", ".astro"}

FAIL, WARN = "FAIL", "WARN"


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    severity: str
    rule: str
    message: str


# --- Line rules: (rule, severity, compiled pattern, message) ----------------
# Each fires per matching line. Keep every pattern narrow enough that a hit is
# a real defect, not a maybe — a linter that cries wolf gets muted, and then it
# protects nothing.

LINE_RULES: list[tuple[str, str, re.Pattern[str], str]] = [
    (
        "em-dash",
        FAIL,
        re.compile(r"[—–]"),
        "Em/en-dash in UI text. The single most reliable LLM tell. Use a hyphen, a comma, or two sentences.",
    ),
    (
        "banned-palette",
        FAIL,
        re.compile(
            r"#(?:f5f1ea|f7f5f1|fbf8f1|efeae0|ece6db|faf7f1|e8dfcb"  # cream/bone backgrounds
            r"|b08947|b6553a|9a2436|9c6e2a|bc7c3a|7d5621"  # brass/clay/oxblood accents
            r"|1a1714|1a1814|1b1814)\b",  # espresso text
            re.I,
        ),
        "The beige+brass 'premium consumer' palette. Every LLM reaches for it; the brand goes invisible. Pick another family.",
    ),
    (
        "pure-black-white",
        WARN,
        re.compile(r"#(?:000000|000|ffffff|fff)\b", re.I),
        "Pure #000/#fff kills depth. Use a near-black/near-white (e.g. #0a0a0a, #fafafa).",
    ),
    (
        "banned-font",
        WARN,
        re.compile(r"\b(Fraunces|Instrument[_ ]Serif|Playfair[_ ]Display)\b", re.I),
        "LLM-favorite display serif. Not wrong, but it is the reflex pick — justify it or rotate.",
    ),
    (
        "default-font",
        WARN,
        # Matches both CSS (font-family:) and JSX (fontFamily:) — the JSX spelling
        # is the one an agent actually emits, so missing it would gut the rule.
        # Quantifiers are BOUNDED: an unbounded [^;,}]* here overlaps the following
        # [:\s]\s* and backtracks quadratically (font-family + 40k spaces = 40s).
        re.compile(r"font-?family[^;,}]{0,120}[:\s]\s{0,20}['\"]?(Inter|Roboto|Open Sans|Helvetica|Arial)\b", re.I),
        "Default sans. Fine for a11y/public-sector briefs; a tell everywhere else.",
    ),
    (
        "lucide-icons",
        WARN,
        re.compile(r"""from\s+['"]lucide-react['"]"""),
        "lucide-react is the default reach. Acceptable if the project already uses it; otherwise pick one family and commit.",
    ),
    (
        "handrolled-icon",
        WARN,
        re.compile(r"<svg\b(?![^>]{0,300}aria-hidden=\"false\")[^>]{0,300}>\s{0,20}(?:<path\b|$)", re.I),
        "Hand-rolled inline SVG icon. Use an icon library; hand-drawn paths read as improvised.",
    ),
    (
        "emoji",
        FAIL,
        re.compile(
            "[\U0001f300-\U0001faff\U00002600-\U000027bf\U0001f1e6-\U0001f1ff]"
        ),
        "Emoji in UI. Reads as chat output, not product.",
    ),
    (
        "h-screen",
        FAIL,
        re.compile(r"\bh-screen\b"),
        "h-screen breaks on mobile browser chrome. Use min-h-[100dvh].",
    ),
    (
        "scroll-listener",
        FAIL,
        re.compile(r"addEventListener\(\s*['\"]scroll['\"]"),
        "Raw scroll listener. Janks the main thread; use IntersectionObserver, CSS scroll-timeline, or the framework's scroll primitive.",
    ),
    (
        "animate-layout-prop",
        WARN,
        re.compile(r"transition:[^;]*\b(top|left|width|height)\b|animate.*\b(top|left|width|height):"),
        "Animating a layout property forces reflow. Animate transform/opacity only.",
    ),
    (
        "flex-percent-math",
        WARN,
        re.compile(r"w-\[calc\([^\]]{0,80}%[^\]]{0,80}\)\]"),
        "Percentage flex math. This is what CSS Grid is for.",
    ),
    (
        "custom-cursor",
        WARN,
        re.compile(r"cursor:\s*url\("),
        "Custom cursor. Accessibility- and performance-hostile, and dated.",
    ),
    (
        "gradient-text",
        WARN,
        re.compile(r"bg-clip-text|background-clip:\s*text"),
        "Gradient text on a heading. The 2023 AI-landing-page signature.",
    ),
    (
        "placeholder-comment",
        FAIL,
        re.compile(
            r"//\s*(\.\.\.|rest of|implement|your code|add more|similar to|continue)"
            r"|/\*\s*\.\.\.\s*\*/"
            r"|\{/\*\s*\.\.\.\s*\*/\}",
            re.I,
        ),
        "Placeholder comment instead of code. The model stopped early; finish the work.",
    ),
    (
        "lorem-ipsum",
        FAIL,
        re.compile(r"\blorem ipsum\b", re.I),
        "Lorem ipsum. Write real copy; fake copy hides real layout problems.",
    ),
    (
        "stock-name",
        FAIL,
        re.compile(r"\b(John Doe|Jane Doe|Sarah Chan|Acme(?:\s+(?:Inc|Corp))?|Cloudly|SmartFlow)\b"),
        "Stock placeholder name/brand. Invent something specific or use real data.",
    ),
    (
        "filler-verb",
        WARN,
        re.compile(r"\b(Elevate|Seamless(?:ly)?|Unleash|Next-Gen|Revolutionize|Game-?changer|Delve)\b", re.I),
        "Marketing filler verb. Says nothing; every AI landing page says it.",
    ),
    (
        "scroll-cue",
        FAIL,
        re.compile(r"\b(Scroll to explore|Scroll to discover|↓\s*scroll|Scroll down)\b", re.I),
        "Scroll cue. The user is looking at the hero; they know what scrolling is.",
    ),
    (
        "performative-craft",
        WARN,
        re.compile(r"\b(Quietly (?:in use at|trusted by)|Field notes|From the field|Currently on the bench)\b", re.I),
        "Performative-craftsman copy. Mimics the signifiers of taste without the substance.",
    ),
    (
        "fake-precision",
        WARN,
        # No trailing \b: there is no word boundary between "%" and a space, so
        # anchoring the tail would silently never match.
        re.compile(r"\b(99\.99%|99\.9%|100% uptime|10x faster)", re.I),
        "Suspiciously round/absolute stat. Use real numbers or drop the claim.",
    ),
    (
        "hero-version-label",
        WARN,
        re.compile(r">\s*(?:v\d+\.\d+|BETA|EARLY ACCESS|INVITE[- ]ONLY|ALPHA)\s*<", re.I),
        "Version/beta label as hero decoration. Ships nothing; signals nothing.",
    ),
    (
        "section-number-eyebrow",
        WARN,
        re.compile(r">\s*0\d\s*[/·\-]\s*\w"),
        "Numbered section eyebrow (01 / INDEX). Decoration pretending to be structure.",
    ),
    (
        "placeholder-as-label",
        WARN,
        re.compile(r"<input\b(?![^>]{0,300}aria-label)(?![^>]{0,300}id=)[^>]{0,300}placeholder=", re.I),
        "Placeholder used as the only label. Fails a11y the moment the user types.",
    ),
]

# --- File-level rules ------------------------------------------------------

EYEBROW = re.compile(r"uppercase[^\"'`]{0,80}tracking|tracking[^\"'`]{0,80}uppercase")
SECTION = re.compile(r"<section\b|<Section\b")
MIDDOT = re.compile(r"·")
RADIUS = re.compile(r"rounded-\[(\d+)(?:px|rem)\]|border-radius:\s*(\d+)")


# This linter reads code it did not write — LLM output, cloned repos, third-party
# deps. Untrusted input gets hard bounds, not good intentions: every quantifier
# above is bounded, and these caps stop a minified or crafted file from wedging
# the session before a regex ever runs.
MAX_FILE_BYTES = 1_000_000
MAX_LINE_CHARS = 2_000


def check_file(path: Path) -> list[Finding]:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return [
                Finding(
                    str(path),
                    0,
                    WARN,
                    "skipped-large",
                    f"File over {MAX_FILE_BYTES // 1000}KB — skipped (minified or generated; lint the source, not the build).",
                )
            ]
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [Finding(str(path), 0, WARN, "unreadable", f"Could not read: {exc}")]

    findings: list[Finding] = []
    lines = text.splitlines()

    for lineno, line in enumerate(lines, 1):
        if len(line) > MAX_LINE_CHARS:
            continue  # minified/pathological; nothing legible to judge here anyway
        for rule, severity, pattern, message in LINE_RULES:
            if pattern.search(line):
                findings.append(Finding(str(path), lineno, severity, rule, message))
        # Middle-dot is rationed, not banned: one per line reads as metadata,
        # three reads as a model decorating.
        if len(MIDDOT.findall(line)) > 1:
            findings.append(
                Finding(
                    str(path),
                    lineno,
                    WARN,
                    "middot-spam",
                    "More than one · on a line. Rationed to 1; it is a separator, not a texture.",
                )
            )

    # Eyebrow budget: at most one per three sections (hero counts as one).
    sections = len(SECTION.findall(text))
    eyebrows = len(EYEBROW.findall(text))
    if sections and eyebrows > math.ceil(sections / 3):
        findings.append(
            Finding(
                str(path),
                1,
                FAIL,
                "eyebrow-budget",
                f"{eyebrows} eyebrows across {sections} sections; budget is {math.ceil(sections / 3)}. "
                "Drop the extras — the fix is deletion, not rewording.",
            )
        )

    # One corner-radius scale per project. Round buttons in a square layout is
    # not a style, it is two styles. Square (0) and full-round (50%, 999px+)
    # are anchors OUTSIDE the scale, not steps in it - a real app's radius
    # language is typically {0, small, large, pill} and that is one language.
    # (Cost: a literal 50px scale step is excused too; acceptable, it is rare.)
    radii = {m[0] or m[1] for m in RADIUS.findall(text)}
    radii -= {"0", "50", "999", "9999"}
    if len(radii) > 2:
        findings.append(
            Finding(
                str(path),
                1,
                WARN,
                "radius-scale",
                f"{len(radii)} distinct corner radii ({', '.join(sorted(radii))}). Pick one scale and commit.",
            )
        )

    return findings


def iter_targets(paths: list[str]) -> list[Path]:
    out: list[Path] = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            out.extend(
                f
                for f in sorted(p.rglob("*"))
                if f.suffix in UI_SUFFIXES
                # Don't follow symlinked files out of the tree the caller pointed at.
                # (rglob already declines to descend symlinked dirs.)
                and not f.is_symlink()
                and not any(part in {"node_modules", ".git", "dist", "build", ".next"} for part in f.parts)
            )
        elif p.suffix in UI_SUFFIXES:
            out.append(p)
    return out


def safe(path: str) -> str:
    """A POSIX filename may contain newlines. An agent reads this report as tool
    output, so an unescaped one lets a hostile filename forge a lint line."""
    return path.replace("\n", "\\n").replace("\r", "\\r")


def main() -> int:
    ap = argparse.ArgumentParser(description="Deterministic AI-slop linter for generated UI code.")
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--warn-only", action="store_true", help="always exit 0")
    args = ap.parse_args()

    targets = iter_targets(args.paths)
    if not targets:
        print("no UI files found (looked for: " + " ".join(sorted(UI_SUFFIXES)) + ")", file=sys.stderr)
        return 0

    findings = [f for t in targets for f in check_file(t)]
    fails = [f for f in findings if f.severity == FAIL]

    if args.json:
        print(json.dumps({"findings": [asdict(f) for f in findings], "files": len(targets)}, indent=2))
    else:
        for f in sorted(findings, key=lambda f: (f.path, f.line)):
            print(f"{safe(f.path)}:{f.line}: {f.severity}: {f.rule}: {f.message}")
        counts = f"{len(fails)} fail, {len(findings) - len(fails)} warn, {len(targets)} file(s)"
        print(f"\n{counts}")
        if not findings:
            print("clean — but a clean lint is a floor, not a ceiling. The judgment checks in SKILL.md still apply.")

    return 1 if fails and not args.warn_only else 0


if __name__ == "__main__":
    sys.exit(main())
