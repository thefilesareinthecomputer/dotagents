#!/usr/bin/env python3
"""Scrub text before it is copied anywhere: secrets by shape, then the station's
term list by the identifier hook's own matching rule. Hits are replaced with a
class placeholder and counted. Nothing here ever prints a matched value.

This is the first layer; the sanitize skill, when built, is the full pass that
runs before any training. Stdlib only.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

SECRET = "[SECRET]"
TERM = "[TERM]"

# Each pattern masks group 1 when it has one, else the whole match.
SECRET_PATTERNS = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"), "private key"),
    (re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), "aws access key"),
    (re.compile(r"(?:^|\s)--?(?:password|passwd|pwd|token|secret|api[-_]?key)[=\s]+[\"']?([^\s\"'`;&|]{6,})", re.I), "flag credential"),
    (re.compile(r"\s-u\s+[^\s:]+:([^\s\"'`;&|]+)"), "basic-auth password"),
    (re.compile(r"\s-p([^\s\"'`;&|-]{6,})"), "inline password flag"),
    (re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{16,}\b"), "api key"),
    (re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b|\bgithub_pat_[A-Za-z0-9_]{20,}\b"), "github token"),
    (re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b"), "gitlab token"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), "slack token"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"), "google api key"),
    (re.compile(r"\bsk_(?:live|test)_[A-Za-z0-9]{16,}\b"), "stripe key"),
    (re.compile(r"\b(?:npm|hf)_[A-Za-z0-9]{30,}\b"), "registry token"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"), "jwt"),
    (re.compile(r"\b[a-z][a-z0-9+.-]*://[^/\s:@]+:([^/\s@]+)@", re.I), "url password"),
    (re.compile(r"\bbearer\s+([A-Za-z0-9._~+/=-]{16,})", re.I), "bearer token"),
    (re.compile(r"\b(?:authorization|x-api-key|api[-_]?key)\s*[:=]\s*[\"']?([A-Za-z0-9._~+/=-]{8,})", re.I), "header credential"),
    (re.compile(r"\b[A-Za-z0-9_]*(?:key|token|secret|password|passwd|pwd|credential)[A-Za-z0-9_]*\s*[=:]\s*[\"']?([^\s\"'`;&|\[]{8,})", re.I),
     "key-like assignment"),   # the value class excludes '[' so an already-masked value is not counted twice
]


def terms_file() -> Path:
    return Path(os.environ.get("IDENTIFIER_TERMS_FILE") or Path.home() / ".claude" / "private" / "identifier-terms.txt")


def load_terms() -> set[str]:
    """The station term list: one term per line, `# ` comments allowed. Missing file means no terms."""
    try:
        lines = terms_file().read_text(encoding="utf-8").splitlines()
    except OSError:
        return set()
    out = set()
    for ln in lines:
        s = ln.strip()
        if s and not (s == "#" or s.startswith("# ")):
            out.add(s)
    return out


def term_pattern(term: str) -> re.Pattern:
    """The identifier hook's rule: single-case terms match any case, mixed-case terms match as typed,
    and the edges are 'no word character on either side' so symbol-edged terms still match whole."""
    flags = re.I if (term == term.upper() or term == term.lower()) else 0
    return re.compile(r"(?<!\w)" + re.escape(term) + r"(?!\w)", flags)


def scrub_text(text: str, terms: set[str] | None = None, counts: dict | None = None) -> str:
    """Return text with secrets and listed terms replaced by placeholders; tally by class into counts."""
    if not isinstance(text, str) or not text:
        return text
    counts = counts if counts is not None else {}
    for regex, why in SECRET_PATTERNS:
        def repl(m, why=why):
            counts[why] = counts.get(why, 0) + 1
            if m.lastindex:
                return m.group(0)[:m.start(1) - m.start(0)] + SECRET + m.group(0)[m.end(1) - m.start(0):]
            return SECRET
        text = regex.sub(repl, text)
    for term in sorted(terms or (), key=len, reverse=True):
        text, n = term_pattern(term).subn(TERM, text)
        if n:
            counts["term"] = counts.get("term", 0) + n
    return text


def scrub_value(value, terms: set[str] | None, counts: dict):
    if isinstance(value, str):
        return scrub_text(value, terms, counts)
    if isinstance(value, dict):
        return {k: scrub_value(v, terms, counts) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub_value(v, terms, counts) for v in value]
    return value


def summary(counts: dict) -> str:
    return ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "nothing"
