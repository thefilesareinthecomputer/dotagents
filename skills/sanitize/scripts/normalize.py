#!/usr/bin/env python3
"""Normalized matching for the sanitize engine.

A term list alone leaks under normalization: split tokens, inserted punctuation,
Unicode confusables, zero-width characters and base64 or hex encodings all defeat a
plain word match. This module builds a normalized view of the text with an index
map back to the original, finds listed terms in that view, and returns the original
spans to replace. Encoded runs are decoded and rescanned once, never recursively.

Stdlib only. Nothing here prints or logs text. Invisible characters are named by
codepoint so this file holds none of them.
"""

from __future__ import annotations

import base64
import binascii
import re
import unicodedata

# Characters with no width that hide inside a word: zero-width space, non-joiner,
# joiner, word joiner, byte-order mark, soft hyphen, Mongolian vowel separator.
ZERO_WIDTH = {chr(c) for c in (0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0x00AD, 0x180E)}

# Letters that look like ASCII and are not. NFKC does not fold these, so a table does.
CONFUSABLES = {
    # Cyrillic
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "х": "x", "у": "y",
    "і": "i", "ј": "j", "ѕ": "s", "һ": "h", "ԁ": "d", "ԛ": "q", "ԝ": "w",
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O",
    "Р": "P", "С": "C", "Т": "T", "Х": "X", "У": "Y", "І": "I", "Ј": "J", "Ѕ": "S",
    # Greek
    "α": "a", "ε": "e", "ι": "i", "κ": "k", "ν": "v", "ο": "o", "ρ": "p", "υ": "u",
    "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I", "Κ": "K",
    "Μ": "M", "Ν": "N", "Ο": "O", "Ρ": "P", "Τ": "T", "Υ": "Y", "Χ": "X",
    # Latin look-alikes and common accents
    "ı": "i", "ȷ": "j", "ɑ": "a", "ɡ": "g", "ɪ": "i", "ᴀ": "a", "ᴄ": "c", "ᴇ": "e",
    "ℓ": "l", "à": "a", "á": "a", "è": "e", "é": "e", "ì": "i", "í": "i",
    "ò": "o", "ó": "o", "ù": "u", "ú": "u",
}

MIN_NORMALIZED_TERM = 4

BASE64_RUN = re.compile(r"(?<![A-Za-z0-9+/=])[A-Za-z0-9+/]{16,}={0,2}(?![A-Za-z0-9+/=])")
HEX_RUN = re.compile(r"(?<![0-9A-Fa-f])(?:[0-9A-Fa-f]{2}){8,}(?![0-9A-Fa-f])")


def fold_char(ch: str) -> str:
    """One original character to its normalized characters (possibly several or none)."""
    if ch in ZERO_WIDTH:
        return ""
    out = []
    for c in unicodedata.normalize("NFKC", ch):
        c = CONFUSABLES.get(c, c)
        if c.isalnum() or c == "_":
            out.append(c)
    return "".join(out)


def normalized_view(text: str) -> tuple[str, list[int]]:
    """The text with whitespace, punctuation and zero-width characters removed and
    confusables folded, plus a map from each normalized index to its original index."""
    chars: list[str] = []
    index: list[int] = []
    for i, ch in enumerate(text):
        for c in fold_char(ch):
            chars.append(c)
            index.append(i)
    return "".join(chars), index


def normalize_term(term: str) -> str:
    return "".join(fold_char(ch) for ch in term)


def _is_word(ch: str) -> bool:
    return bool(ch) and (ch.isalnum() or ch == "_")


def _edge_ok(text: str, start: int, end: int) -> bool:
    """The original span must not sit inside a longer word: no word character touches it."""
    before = text[start - 1] if start > 0 else ""
    after = text[end] if end < len(text) else ""
    return not _is_word(before) and not _is_word(after)


def normalized_hits(text: str, terms: set[str]) -> list[tuple[int, int]]:
    """Original (start, end) spans where a term matches the normalized view. A single-case
    term matches any case, a mixed-case term as typed. Terms shorter than
    MIN_NORMALIZED_TERM after normalization are skipped as too noisy. Spans are merged
    and returned in order."""
    norm, index = normalized_view(text)
    if not norm:
        return []
    spans: list[tuple[int, int]] = []
    for term in terms:
        nt = normalize_term(term)
        if len(nt) < MIN_NORMALIZED_TERM:
            continue
        flags = re.I if (term == term.upper() or term == term.lower()) else 0
        for m in re.finditer(re.escape(nt), norm, flags):
            start = index[m.start()]
            end = index[m.end() - 1] + 1
            if _edge_ok(text, start, end):
                spans.append((start, end))
    return merge_spans(spans)


def merge_spans(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for s, e in sorted(spans):
        if out and s <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def replace_spans(text: str, spans: list[tuple[int, int]], placeholder: str) -> str:
    for s, e in sorted(spans, reverse=True):
        text = text[:s] + placeholder + text[e:]
    return text


def _printable_text(raw: bytes) -> str | None:
    """Decoded bytes as text when they look like text: valid UTF-8 and nearly all printable."""
    try:
        s = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if not s:
        return None
    printable = sum(1 for c in s if c.isprintable() or c in "\n\r\t")
    return s if printable / len(s) >= 0.9 else None


def decode_run(run: str) -> str | None:
    """The text inside a base64 or hex run, or None when it is not text."""
    if HEX_RUN.fullmatch(run):
        try:
            return _printable_text(bytes.fromhex(run))
        except ValueError:
            return None
    padded = run + "=" * (-len(run) % 4)
    try:
        return _printable_text(base64.b64decode(padded, validate=True))
    except (binascii.Error, ValueError):
        return None


def encoded_hits(text: str, hit_test) -> list[tuple[int, int]]:
    """Spans of base64 or hex runs whose decoded text satisfies hit_test(decoded).
    The decoded text is scanned once; nested encodings are not followed."""
    spans: list[tuple[int, int]] = []
    for regex in (HEX_RUN, BASE64_RUN):
        for m in regex.finditer(text):
            decoded = decode_run(m.group(0))
            if decoded is not None and hit_test(decoded):
                spans.append((m.start(), m.end()))
    return merge_spans(spans)
