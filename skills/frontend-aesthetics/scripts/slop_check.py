#!/usr/bin/env python3
"""Deterministic AI-slop linter for generated UI code.

EXECUTE this — do not paraphrase its rules into a prompt and eyeball them.
The whole point is that these checks are mechanical: same input, same verdict,
no model in the loop. Stdlib only, no network, no API key.

    python3 slop_check.py <path>...          # human output, exit 1 on any FAIL
    python3 slop_check.py --json <path>...   # machine output
    python3 slop_check.py --warn-only <path> # never exit non-zero
    python3 slop_check.py --craft <path>...  # add WARN-only craft checks

--craft adds WARN-only transition, animation, focus, and coverage checks on .css,
<style> blocks, and class utilities; .scss files and non-CSS <style lang> blocks
are not parsed for craft declarations and are reported as scan-incomplete.

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
import bisect
import itertools
import json
import math
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass, asdict
from decimal import Decimal
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


def check_file(path: Path, craft: bool = False) -> list[Finding]:
    """Lint one file; ``craft=True`` appends the sorted WARN-only craft findings."""
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
            ] + _coverage(path, craft, f"file is over {MAX_FILE_BYTES} bytes, so no rule inspected it")
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [Finding(str(path), 0, WARN, "unreadable", f"Could not read: {exc}")] + _coverage(
            path, craft, "file could not be read, so no rule inspected it"
        )

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

    if craft:
        findings.extend(craft_findings(path, text))
    return findings


# --- Opt-in craft checks (--craft) -------------------------------------------
# Every craft finding is WARN: source text shows evidence, never the rendered
# result, so each message names the literal evidence and the review it asks
# for. The scanner is linear: comments and strings are blanked in place (line
# numbers survive), then one pass tracks braces, parentheses, and the selector
# of each block. var(), calc(), nesting, the cascade, CSS-in-JS, and JSX
# expressions stay unresolved on purpose; rendered review owns those.

STYLE_BLOCK_SUFFIXES = {".html", ".vue", ".svelte", ".astro"}
CSS_WIDE_KEYWORDS = {"inherit", "initial", "unset", "revert", "revert-layer"}
# Shorthand keywords that are not property names, so they cannot name one.
TRANSITION_KEYWORDS = CSS_WIDE_KEYWORDS | {
    "ease", "ease-in", "ease-out", "ease-in-out", "linear", "step-start", "step-end",
    "normal", "allow-discrete",
}
EASING_FUNCTIONS = ("cubic-bezier(", "steps(", "linear(")
SUBSTITUTIONS = ("var(", "env(", "attr(")
WIDTH_KEYWORDS = {"thin", "medium", "thick"}
LONG_TRANSITION_MS = 500
CRAFT_PROPERTIES = {
    "transition", "transition-property", "transition-duration", "animation",
    "animation-iteration-count", "outline", "outline-style", "outline-width", "box-shadow",
}
VENDOR_PREFIXES = ("-webkit-", "-moz-", "-ms-", "-o-")

# Every pattern below has bounded quantifiers or disjoint alternatives, so none
# can backtrack superlinearly.
_CSS_SKIPPABLE = re.compile(r"/\*|[\"']")
# A CSS string ends at its quote, an unescaped newline, or the region end.
_CSS_STRINGS = {
    '"': re.compile(r'"(?:[^"\\\n]|\\[\s\S])*"?'),
    "'": re.compile(r"'(?:[^'\\\n]|\\[\s\S])*'?"),
}
_CSS_STRUCTURE = re.compile(r"[{}();]")
_VALUE_SEPARATORS = re.compile(r"[(),]")
_TOKEN_PIECES = re.compile(r"[()]|[ \t\n\r\f]+|[^() \t\n\r\f]+")
_CSS_SPACE = re.compile(r"[ \t\n\r\f]+")
_NUMBER = r"[+-]?(?:\d{1,30}(?:\.\d{1,30})?|\.\d{1,30})(?:[eE][+-]?\d{1,5})?"
_TIME = re.compile(rf"({_NUMBER})(ms|s)", re.I)
_LENGTH = re.compile(rf"({_NUMBER})([a-zA-Z]{{1,10}}|%)?")
_IDENT = re.compile(r"-{0,2}[A-Za-z_][\w-]{0,200}")
# Complete pseudo-class tokens: :focus-within and escaped utility names such as
# .md\:focus\:outline-none do not count.
_FOCUS = re.compile(r"(?<!\\):focus(?:-visible)?(?![\w-])", re.I)
# A reset scoped by :not(:focus-visible) leaves the keyboard focus outline alone.
_NOT_FOCUS_VISIBLE = re.compile(r":not\([^)]{0,200}(?<!\\):focus-visible(?![\w-])", re.I)
_NOT_PARENS = re.compile(r"(?<!\\):not\(|[()]", re.I)
_STYLE_OPEN = re.compile(r"<style(?=[\s>/])", re.I)
_STYLE_CLOSE = re.compile(r"</style", re.I)
_STYLE_LANG = re.compile(r"""(?<![\w:-])lang[ \t\n\r\f]{0,20}=[ \t\n\r\f]{0,20}["']?([\w-]{1,30})""", re.I)
# Plain class and className attributes only; :class and v-bind:class hold
# expressions, and .className is a script assignment.
_CLASS_ATTR = re.compile(r"(?<![\w:.-])(?:class|className)[ \t\n\r\f]{0,20}=[ \t\n\r\f]{0,20}([\"'])", re.I)
_CLASS_WORD = re.compile(r"[^ \t\n\r\f]+")
_RESPONSIVE = r"(?:(?:max-)?(?:sm|md|lg|xl|2xl):)?"
_FOCUS_RESET_UTILITY = re.compile(_RESPONSIVE + r"(?:focus|focus-visible):outline-(?:none|0)")
_RING_UTILITY = re.compile(_RESPONSIVE + r"(?:focus|focus-visible):ring(?:-[1248])?")

_ALL_REVIEW = "list the properties meant to animate, or confirm that animating every property is intended"
_LONG_REVIEW = "explain its purpose and confirm the transition can be interrupted"
_INFINITE_REVIEW = "review its purpose, a pause or static alternative, and reduced-motion behavior"
_COVERAGE_REVIEW = "review that coverage by other means"
_STYLE_REVIEW = "review transitions, animations, and focus styles by other means"
_FOCUS_REVIEW = (
    "and this file has no :focus or :focus-visible outline, box-shadow, or ring replacement; "
    "verify the rendered focus indicator"
)


def _incomplete(path: str, line: int, evidence: str) -> Finding:
    return Finding(path, line, WARN, "scan-incomplete", f"{evidence}; {_COVERAGE_REVIEW}")


def _coverage(path: Path, craft: bool, evidence: str) -> list[Finding]:
    return [_incomplete(str(path), 0, evidence)] if craft else []


def no_target_finding(raw: str) -> Finding:
    """Craft-mode report for an input path that yields no UI targets."""
    looked_for = " ".join(sorted(UI_SUFFIXES))
    return _incomplete(raw, 0, f"no UI files found for this input (looked for: {looked_for}), so nothing was inspected")


def _show(text: str, limit: int = 60) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 3] + "..."


def _blank(text: str) -> str:
    """Same-length spaces that keep newlines, so offsets and line numbers hold."""
    return "\n".join(" " * len(part) for part in text.split("\n"))


def _blank_css(text: str, start: int, end: int) -> str:
    """Return text[start:end] with CSS comments and strings blanked."""
    out: list[str] = []
    pos = start
    while True:
        match = _CSS_SKIPPABLE.search(text, pos, end)
        if match is None:
            out.append(text[pos:end])
            return "".join(out)
        out.append(text[pos : match.start()])
        if match.group() == "/*":
            close = text.find("*/", match.end(), end)
            stop = end if close < 0 else close + 2
        else:
            stop = _CSS_STRINGS[match.group()].match(text, match.start(), end).end()
        out.append(_blank(text[match.start() : stop]))
        pos = stop


def _style_blocks(text: str) -> list[tuple[int, int, int, bool]]:
    """(tag, start, end, is_plain_css) for each <style> block, where tag is the
    offset of the opening tag and start:end is the body; an unclosed one runs to EOF.

    A block whose lang is not css (scss, less, postcss) is blanked for the class
    scan but not parsed, matching the .scss exclusion; the caller reports it.
    """
    blocks: list[tuple[int, int, int, bool]] = []
    pos = 0
    while True:
        opening = _STYLE_OPEN.search(text, pos)
        if opening is None:
            return blocks
        tag_end = text.find(">", opening.end())
        if tag_end < 0:
            return blocks
        closing = _STYLE_CLOSE.search(text, tag_end + 1)
        end = closing.start() if closing else len(text)
        lang = _STYLE_LANG.search(text, opening.end(), tag_end)
        blocks.append((opening.start(), tag_end + 1, end, lang is None or lang.group(1).lower() == "css"))
        if closing is None:
            return blocks
        pos = closing.end()


def _split_commas(value: str) -> list[str]:
    """Split at commas outside parentheses; strings are already blanked."""
    items: list[str] = []
    depth = start = 0
    for match in _VALUE_SEPARATORS.finditer(value):
        char = match.group()
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif depth == 0:
            items.append(value[start : match.start()])
            start = match.end()
    items.append(value[start:])
    return items


def _tokens(item: str) -> list[str]:
    """Whitespace-separated tokens, keeping a function call as one token."""
    if "(" not in item and ")" not in item:
        return [token for token in _CSS_SPACE.split(item) if token]
    tokens: list[str] = []
    current: list[str] = []
    depth = 0
    for match in _TOKEN_PIECES.finditer(item):
        piece = match.group()
        if piece == "(":
            depth += 1
        elif piece == ")":
            depth = max(0, depth - 1)
        elif piece[0] in " \t\n\r\f":
            if depth == 0:
                if current:
                    tokens.append("".join(current))
                    current = []
                continue
            piece = " "
        current.append(piece)
    if current:
        tokens.append("".join(current))
    return tokens


def _strip_important(value: str) -> str:
    trimmed = value.rstrip()
    if trimmed.lower().endswith("important"):
        head = trimmed[: -len("important")].rstrip()
        if head.endswith("!"):
            return head[:-1]
    return value


def _length(token: str) -> tuple[Decimal, str] | None:
    match = _LENGTH.fullmatch(token)
    return (Decimal(match.group(1)), match.group(2) or "") if match else None


def _is_zero_width(token: str) -> bool:
    length = _length(token)
    return length is not None and length[0] == 0


def _is_positive_width(token: str) -> bool:
    if token in WIDTH_KEYWORDS:
        return True
    length = _length(token)
    return length is not None and length[0] > 0 and length[1] not in ("", "%")


def _outside_not(member: str) -> str:
    """The selector with every :not(...) argument removed, nesting included; an
    unclosed :not( runs to the end."""
    kept: list[str] = []
    pos = depth = 0
    inside = -1  # the depth where the open :not( began, or -1 outside one
    for match in _NOT_PARENS.finditer(member):
        if match.group() == ")":
            depth = max(0, depth - 1)
            if depth == inside:
                inside = -1
                pos = match.end()
            continue
        if inside < 0 and match.group() != "(":
            kept.append(member[pos : match.start()])
            inside = depth
        depth += 1
    if inside < 0:
        kept.append(member[pos:])
    return " ".join(kept)


def _focus_scope(selector: str) -> tuple[str | None, bool]:
    """(reset pseudo-class, replacement allowed) for a rule's selector list.

    Each top-level comma member is classified alone. A member is focus-scoped
    when :focus or :focus-visible appears outside every :not(...); it can hold a
    replacement, and it can reset the outline unless :not(:focus-visible) scopes
    it away from keyboard focus. The reset value is the first such member's
    pseudo-class, used as evidence.
    """
    reset: str | None = None
    replaces = False
    for member in _split_commas(selector):
        focus = _FOCUS.search(_outside_not(member))
        if focus is None:
            continue
        replaces = True
        if reset is None and not _NOT_FOCUS_VISIBLE.search(member):
            reset = focus.group().lower()
    return reset, replaces


def _declarations(css: str) -> Iterator[tuple[tuple[str | None, bool], str, str, int]]:
    """Yield (focus scope, property, value, offset) for each watched declaration.

    The focus scope classifies the prelude of the innermost open block once, when
    the block opens, so a long selector costs one pass however many declarations
    it holds; nesting stays unresolved. A semicolon inside parentheses does not
    end a declaration.
    """
    selectors: list[tuple[str | None, bool]] = []
    segment = depth = 0
    for match in _CSS_STRUCTURE.finditer(css):
        char = match.group()
        if char == "(":
            depth += 1
            continue
        if char == ")":
            depth = max(0, depth - 1)
            continue
        if char == ";" and depth:
            continue
        if char == "{":
            selectors.append(_focus_scope(css[segment : match.start()]))
        elif selectors:
            found = _declaration(selectors[-1], css, segment, match.start())
            if found:
                yield found
            if char == "}":
                selectors.pop()
        depth = 0
        segment = match.end()
    if selectors:
        found = _declaration(selectors[-1], css, segment, len(css))
        if found:
            yield found


def _declaration(
    scope: tuple[str | None, bool], css: str, start: int, end: int
) -> tuple[tuple[str | None, bool], str, str, int] | None:
    colon = css.find(":", start, end)
    if colon < 0:
        return None
    raw_name = css[start:colon]
    name = raw_name.strip().lower()
    for prefix in VENDOR_PREFIXES:
        if name.startswith(prefix):
            name = name[len(prefix) :]
            break
    if name not in CRAFT_PROPERTIES:
        return None
    offset = start + len(raw_name) - len(raw_name.lstrip())
    return scope, name, _strip_important(css[colon + 1 : end]), offset


def _transition_all(prop: str, value: str, items: list[list[str]]) -> str | None:
    """Evidence text when a transition names all or omits its property."""
    if prop == "transition-property":
        if any(token.lower() == "all" for tokens in items for token in tokens):
            return f'transition-property value "{_show(value)}" includes all'
        return None
    if len(items) == 1 and len(items[0]) == 1 and items[0][0].lower() in CSS_WIDE_KEYWORDS | {"none"}:
        return None
    for item in items:
        tokens = [token.lower() for token in item]
        if "all" in tokens:
            return f'transition value "{_show(value)}" names all'
        if any(sub in token for token in tokens for sub in SUBSTITUTIONS):
            continue  # a variable may supply the property
        has_duration = any(_TIME.fullmatch(token) for token in tokens)
        has_property = any(_IDENT.fullmatch(token) and token not in TRANSITION_KEYWORDS for token in tokens)
        if has_duration and not has_property:
            return f'transition value "{_show(value)}" sets a duration with no property, which applies to all'
    return None


def _long_duration(items: list[list[str]]) -> str | None:
    """The first literal duration over the limit; the second time is a delay."""
    for item in items:
        for token in item:
            time = _TIME.fullmatch(token)
            if time:
                scale = 1 if time.group(2).lower() == "ms" else 1000
                if Decimal(time.group(1)) * scale > LONG_TRANSITION_MS:
                    return token
                break
            if "(" in token and not token.lower().startswith(EASING_FUNCTIONS):
                break  # var(), calc(), and friends may be the duration
    return None


def _is_outline_reset(prop: str, tokens: list[str]) -> bool:
    if prop == "outline":
        return "none" in tokens or any(_is_zero_width(token) for token in tokens)
    if prop == "outline-style":
        return tokens == ["none"]
    if prop == "outline-width":
        return any(_is_zero_width(token) for token in tokens)
    return False


def _is_replacement(prop: str, items: list[list[str]], tokens: list[str]) -> bool:
    """A focus indicator candidate: an outline with a positive literal width, or
    any box-shadow other than none or a CSS-wide keyword, var() included."""
    if prop == "outline":
        return "none" not in tokens and any(_is_positive_width(token) for token in tokens)
    if prop == "outline-width":
        return any(_is_positive_width(token) for token in tokens)
    if prop == "box-shadow":
        for item in items:
            words = [token.lower() for token in item]
            if len(words) > 1 or (words and words[0] != "none" and words[0] not in CSS_WIDE_KEYWORDS):
                return True
    return False


def craft_findings(path: Path, text: str) -> list[Finding]:
    """WARN-only craft findings for one file's text, sorted by line, rule, message.

    Lines over MAX_LINE_CHARS are left out, as the legacy rules do, and reported
    once per file through scan-incomplete.
    """
    name = str(path)
    lines = text.splitlines()
    kept = ["" if len(line) > MAX_LINE_CHARS else line for line in lines]
    skipped = [number for number, line in enumerate(lines, 1) if len(line) > MAX_LINE_CHARS]
    norm = "\n".join(kept)
    starts = list(itertools.accumulate((len(line) + 1 for line in kept[:-1]), initial=0))

    def line_of(offset: int) -> int:
        return bisect.bisect_right(starts, offset)

    hits: list[tuple[int, str, str]] = []
    if skipped:
        hits.append((
            skipped[0], "scan-incomplete",
            f"{len(skipped)} line(s) over {MAX_LINE_CHARS} characters, starting at line {skipped[0]}, "
            f"were not inspected; {_COVERAGE_REVIEW}",
        ))

    css_regions: list[tuple[int, int]] = []
    markup = ""
    if path.suffix == ".css":
        css_regions = [(0, len(norm))]
    elif path.suffix in STYLE_BLOCK_SUFFIXES:
        blocks = _style_blocks(norm)
        css_regions = [(start, end) for _, start, end, plain in blocks if plain]
        pieces: list[str] = []
        pos = 0
        for tag, start, end, plain in blocks:
            pieces += [norm[pos:start], _blank(norm[start:end])]
            pos = end
            if not plain:
                hits.append((
                    line_of(tag), "scan-incomplete",
                    f"{_show(norm[tag:start])} block is not parsed for craft declarations; {_STYLE_REVIEW}",
                ))
        markup = "".join(pieces) + norm[pos:]
    elif path.suffix == ".scss":
        # No class scan either: stylesheets have no class attributes, only strings that look like them.
        hits.append((0, "scan-incomplete", f"SCSS is not parsed for craft declarations in this file; {_STYLE_REVIEW}"))
    else:
        markup = norm

    resets: list[tuple[int, str]] = []
    replaced = False
    for region_start, region_end in css_regions:
        css = _blank_css(norm, region_start, region_end)
        for (focus_reset, focus_replaces), prop, value, offset in _declarations(css):
            line = line_of(region_start + offset)
            items = [_tokens(item) for item in _split_commas(value)]
            if prop in ("transition", "transition-property"):
                evidence = _transition_all(prop, value, items)
                if evidence:
                    hits.append((line, "transition-all", f"{evidence}; {_ALL_REVIEW}"))
            if prop in ("transition", "transition-duration"):
                duration = _long_duration(items)
                if duration:
                    hits.append((
                        line, "long-transition",
                        f"{prop} duration {duration} is over {LONG_TRANSITION_MS}ms; {_LONG_REVIEW}",
                    ))
            if prop in ("animation", "animation-iteration-count"):
                if any(token.lower() == "infinite" for item in items for token in item):
                    hits.append((
                        line, "infinite-animation",
                        f'{prop} value "{_show(value)}" repeats infinitely; {_INFINITE_REVIEW}',
                    ))
            if prop in ("outline", "outline-style", "outline-width", "box-shadow"):
                # focus-outline-reset: a reset in a :focus or :focus-visible rule
                # warns unless the file has a replacement in a :focus or
                # :focus-visible rule or a focus: or focus-visible: ring utility.
                # _focus_scope says which selector list members qualify.
                tokens = [token.lower() for item in items for token in item]
                if focus_reset and _is_outline_reset(prop, tokens):
                    resets.append((line, f'"{prop}: {_show(value)}" in a {focus_reset} rule'))
                if focus_replaces and _is_replacement(prop, items, tokens):
                    replaced = True

    for offset, token in _class_tokens(markup):
        if token.rsplit(":", 1)[-1].strip("!") == "transition-all":
            hits.append((line_of(offset), "transition-all", f'class token "{_show(token)}" transitions all properties; {_ALL_REVIEW}'))
        if _FOCUS_RESET_UTILITY.fullmatch(token):
            resets.append((line_of(offset), f'class token "{token}" resets the focus outline'))
        if _RING_UTILITY.fullmatch(token):
            replaced = True

    if not replaced:
        hits += [(line, "focus-outline-reset", f"{evidence}, {_FOCUS_REVIEW}") for line, evidence in resets]
    return [Finding(name, line, WARN, rule, message) for line, rule, message in sorted(hits)]


def _class_tokens(text: str) -> Iterator[tuple[int, str]]:
    """(offset, token) for each word inside a quoted class or className value."""
    pos = 0
    while True:
        attr = _CLASS_ATTR.search(text, pos)
        if attr is None:
            return
        close = text.find(attr.group(1), attr.end())
        if close < 0:
            return
        for word in _CLASS_WORD.finditer(text, attr.end(), close):
            yield word.start(), word.group()
        pos = close + 1


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
    ap.add_argument(
        "--craft",
        action="store_true",
        help="add WARN-only checks for broad or long transitions, infinite animation, "
        "focus outline resets, and scan coverage (an input with no UI files becomes a finding)",
    )
    args = ap.parse_args()

    if args.craft:
        targets: list[Path] = []
        findings: list[Finding] = []
        for raw in args.paths:
            found = iter_targets([raw])
            if not found:
                findings.append(no_target_finding(raw))
            findings += [f for t in found for f in check_file(t, craft=True)]
            targets += found
    else:
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
