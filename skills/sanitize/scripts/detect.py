#!/usr/bin/env python3
"""detect - every content detector the station uses, in one place.

The sanitize engine scrubs with these tables, and the commit gate, the review sweep,
agent-mail's send-time check and the write-time hooks report with them. No other
file in the repo defines a content pattern, an allowance, a codepoint table or a
severity table; they import this one.

  find(text, terms)          -> [Hit]   secrets, personal shapes, identifiers, terms, invisibles
  find_message(text, terms)  -> [Hit]   the commit-message rules plus the identifier shapes
  severity(consumer, hit, path) -> "block" | "warn" | None

A Hit holds offsets, a class and a rule name. It never holds the matched text, so a
caller cannot print a value by accident; it reports a line and a class instead.

Stdlib only. Codepoints are written as numbers and the home-path pattern is built
from pieces, so this file does not match its own detectors.
"""

from __future__ import annotations

import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

BLOCK, WARN = "block", "warn"


@dataclass(frozen=True)
class Hit:
    start: int
    end: int
    cls: str
    rule: str


# ---------------------------------------------------------------- secrets
# Each pattern masks group 1 when it has one, else the whole match. The scrubber in
# sanitize.py walks this list in order, so the key-value rule stays last.
# Vendor-prefix shapes end at "no further key character" rather than \b, because \b
# does not fire between a key and a glued `_xxxx`, which hid the whole key.

SECRET_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}(?![0-9A-Za-z])"),
    re.compile(r"(?:^|\s)--?(?:password|passwd|pwd|token|secret|api[-_]?key)[=\s]+[\"']?([^\s\"'`;&|]{6,})", re.I),
    # curl's -u flag with a user and a password joined by a colon; the user part is name
    # characters only, so a date format after `date -u` is not read as one
    re.compile(r"(?<!\S)-u\s+[A-Za-z0-9._@-]+:([^\s\"'`;&|]+)"),
    # mysql's -p<password>, glued; the value must end the word, so `-points[m]` in code is not one
    re.compile(r"\s-p([^\s\"'`;&|\-\[\](),]{6,})(?=\s|$)"),
    re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}(?![A-Za-z0-9])|\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bxox[abeprs]-[A-Za-z0-9-]{10,}(?![A-Za-z0-9-])"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"),
    re.compile(r"\b[rs]k_(?:live|test)_[A-Za-z0-9]{16,}(?![A-Za-z0-9])"),
    re.compile(r"\bwhsec_[A-Za-z0-9]{24,}(?![A-Za-z0-9])"),
    re.compile(r"\b(?:npm|hf)_[A-Za-z0-9]{30,}(?![A-Za-z0-9])"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    re.compile(r"\b[a-z][a-z0-9+.-]*://[^/\s:@]+:([^/\s@]+)@", re.I),
    re.compile(r"\bbearer\s+([A-Za-z0-9._~+/=-]{16,})", re.I),
    # HTTP basic credentials are a secret whatever the decoded pair looks like
    re.compile(r"\bauthorization\s*[:=]\s*[\"']?basic\s+([A-Za-z0-9+/=_-]{8,})", re.I),
    re.compile(r"\b(?:authorization|x-api-key|api[-_]?key)[\"']?\s*[:=]\s*[\"']?((?=[A-Za-z0-9._~+/=-]*\d)[A-Za-z0-9._~+/=-]{12,})(?![\w(])", re.I),
    # A key-like name assigned a credential-shaped value: 12 or more key characters holding at
    # least one digit, so `key = parts[0]`, `tokens = text.split()` and `TOKEN = "[SECRET]"`
    # in code are left alone while `API_TOKEN=9f3k...` is caught. The optional quote after the
    # name is the quoted-key form, `"api_key": "<value>"`.
    re.compile(r"\b[A-Za-z0-9_]*(?:key|token|secret|password|passwd|pwd|credential)[A-Za-z0-9_]*[\"']?\s*[=:]\s*[\"']?((?=[A-Za-z0-9_\-+/=~]*\d)[A-Za-z0-9_\-+/=~]{12,})(?![\w(.\[])", re.I),
]
KEY_VALUE_RULE = SECRET_PATTERNS[-1]
# A key name that makes a parsed field's value a credential candidate (sanitize's
# field-aware scrub judges `key=value` with KEY_VALUE_RULE).
CREDENTIAL_KEY = re.compile(r"(?:key|token|secret|password|passwd|pwd|credential|authorization)", re.I)

# A private-key header with key material under it is a secret even when the END line is
# out of view (a diff hunk, a truncated paste); a bare header is ordinary text in a fixture
# or a rule table and is reported as `key_header`. PEM metadata lines and blank lines sit
# between an encrypted key's header and its body, so they do not use up the lookahead.
KEY_HEADER = re.compile(r"BEGIN (?:RSA |EC |DSA |OPENSSH |PGP |ENCRYPTED )?PRIVATE KEY")
KEY_BODY = re.compile(r"^[A-Za-z0-9+/=]{40,}$")
PEM_FILLER = re.compile(r"^\s*(?:$|[A-Za-z-]+:\s|-{5})")
KEY_LOOKAHEAD = 8

# ---------------------------------------------------------------- personal shapes
# (class, placeholder, pattern). Group 1, when present, is the part replaced.

CUSTOM_CHECKS = [
    ("email", "[EMAIL]", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    # International or national phone: optional +CC, then 3 groups separated by space, dot or dash,
    # 10 to 11 digits in all. Dotted version strings and bare ports have fewer digits and no separators.
    ("phone", "[PHONE]", re.compile(r"(?<![\w.])(?:\+\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?![\w.])")),
    # A macOS, Linux or Windows home directory with its user name. Built from pieces so the
    # pattern's own source does not form the shape it matches.
    ("home_path", "[HOME]", re.compile(r"(?<![\w/\\])((?:" + "/" + r"(?:Users|home)/|[Cc]:\\Users\\)[^/\\\s\"'`]+)(?=[/\\]|\s|$|[\"'`)])")),
    ("role_code", "[ROLE]", re.compile(r"\b[A-Z]{1,4}\s*\((?:DE|DA|ITL|BA|PM|QA|SA|SO)\d+\)")),
    ("catalog", "[CATALOG]", re.compile(r"\b(?:prod|uat|dev|test|stg)[-_]?(?:bronze|silver|gold|raw|landing)\b", re.I)),
]

# Shapes reported by find() only; a copy never rewrites them.
# The work-item prefixes are an explicit list: a generic `[A-Z]{2,6}-\d{4,}` arm fires on
# ISO-8601, UTF-8 and RFC numbers, and a sweep that does that gets muted.
WORK_ITEM = re.compile(r"\b(?:STORY|TASK|BUG|FEATURE|EPIC|DEF|WI)[-_](\d{3,})\b", re.I)
GUID = re.compile(r"(?<![0-9A-Fa-f-])[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}(?![0-9A-Fa-f-])")

# ---------------------------------------------------------------- invisible codepoints
# One table. `smuggle` is the review severity the hidden-character scan has always used:
# "fail" for the attack classes, "warn" for variation selectors (legitimate in emoji),
# None for characters that are only cosmetic. `fold` marks the characters the normalized
# term view drops, so a term split by one of them still matches.
# (first, last, rule, smuggle, fold, why)
CODEPOINTS = (
    (0xE0000, 0xE007F, "tag-smuggling", "fail", False,
     "Unicode TAG plane mirrors ASCII invisibly - the ASCII-smuggling injection vector"),
    (0x202A, 0x202E, "bidi-override", "fail", False,
     "bidirectional override reorders displayed text without reordering bytes (Trojan Source)"),
    (0x2066, 0x2069, "bidi-isolate", "fail", False,
     "bidirectional isolate reorders displayed text without reordering bytes (Trojan Source)"),
    (0x200B, 0x200D, "zero-width", "fail", True,
     "zero-width character renders as nothing and can split or hide keywords"),
    (0x2060, 0x2060, "zero-width", "fail", True,
     "word joiner renders as nothing and can split or hide keywords"),
    (0x2061, 0x2064, "invisible-operator", "fail", False,
     "invisible math operator renders as nothing outside a maths context"),
    (0x180E, 0x180E, "zero-width", "fail", True,
     "Mongolian vowel separator renders as nothing in modern fonts"),
    (0x115F, 0x1160, "zero-width", "fail", False,
     "Hangul filler renders as nothing outside Korean jamo composition"),
    (0x3164, 0x3164, "zero-width", "fail", False,
     "Hangul filler renders as nothing and is a known blank-name abuse character"),
    (0xFEFF, 0xFEFF, "zero-width", "fail", True,
     "zero-width no-break space (BOM) mid-file renders as nothing"),
    (0xFE00, 0xFE0F, "variation-selector", "warn", False,
     "variation selector can carry hidden bytes, but is legitimate in emoji sequences"),
    (0xE0100, 0xE01EF, "variation-selector", "warn", False,
     "variation-selector supplement can carry hidden bytes"),
    (0x00AD, 0x00AD, "soft-hyphen", None, True, "soft hyphen renders as nothing mid-word"),
    (0x034F, 0x034F, "filler", None, False, "combining grapheme joiner renders as nothing"),
    (0x17B4, 0x17B5, "filler", None, False, "Khmer inherent vowel renders as nothing"),
    (0x180B, 0x180D, "mongolian-selector", None, False, "Mongolian free variation selector"),
    (0xFFA0, 0xFFA0, "filler", None, False, "halfwidth Hangul filler renders as blank"),
    (0x2800, 0x2800, "filler", None, False, "blank braille pattern renders as blank"),
    (0x2028, 0x2029, "line-separator", None, False, "Unicode line or paragraph separator"),
)
# Everything else that renders as nothing or as a look-alike space, by category.
CATEGORY_RULES = {"Cf": "format", "Co": "private-use", "Cc": "control"}
PLAIN_WHITESPACE = {"\t", "\n", "\r", " "}
BOM = chr(0xFEFF)
INVISIBLE_ATTACK = frozenset({"tag-smuggling", "bidi-override", "bidi-isolate", "zero-width", "invisible-operator"})
FOLD_CHARS = frozenset(chr(c) for first, last, _r, _s, fold, _w in CODEPOINTS if fold
                       for c in range(first, last + 1))
# Candidates for the per-character check: anything outside printable ASCII and plain whitespace.
_NON_PLAIN = re.compile(r"[^\t\n\r\x20-\x7e]")


def codepoint_rule(ch: str) -> tuple[str, str | None, str] | None:
    """(rule, smuggle severity, why) for a character that renders as nothing or as a
    look-alike space, else None."""
    if ch in PLAIN_WHITESPACE:
        return None
    cp = ord(ch)
    for first, last, rule, smuggle, _fold, why in CODEPOINTS:
        if first <= cp <= last:
            return rule, smuggle, why
    cat = unicodedata.category(ch)
    if cat in CATEGORY_RULES:
        return CATEGORY_RULES[cat], None, f"{cat} character renders as nothing"
    if cat == "Zs":
        return "exotic-space", None, "space character that is not U+0020"
    return None


def hidden_chars(text: str, *, skip_leading_bom: bool = True) -> list[tuple[int, str]]:
    """(offset, rule) for every character the codepoint table classifies. A BOM at offset 0
    is an encoding marker in a file; a writer that blocks all of them passes False."""
    out = []
    for m in _NON_PLAIN.finditer(text):
        ch = m.group(0)
        if skip_leading_bom and ch == BOM and m.start() == 0:
            continue
        found = codepoint_rule(ch)
        if found:
            out.append((m.start(), found[0]))
    return out


def invisible_hits(text: str) -> list[Hit]:
    return [Hit(i, i + 1, "invisible", rule) for i, rule in hidden_chars(text)]


# ---------------------------------------------------------------- the term list


def terms_file() -> Path:
    return Path(os.environ.get("IDENTIFIER_TERMS_FILE") or Path.home() / ".claude" / "private" / "identifier-terms.txt")


def read_term_file(path: Path) -> set[str]:
    """One term per line; a line that is `#` or starts with `# ` is a comment, `#tag` is a term."""
    out = set()
    for ln in path.read_text(encoding="utf-8").splitlines():
        s = ln.strip()
        if s and not (s == "#" or s.startswith("# ")):
            out.add(s)
    return out


def station_terms_lenient() -> set[str] | None:
    """The station term list, or None when it is missing, unreadable or empty. Callers that
    must refuse without it (sanitize copy) use sanitize.station_terms instead."""
    try:
        terms = read_term_file(terms_file())
    except (OSError, UnicodeDecodeError):
        return None
    return terms or None


SHORT_TERM = 4   # below this length a term matches as typed only; the normalized view skips it already


def term_pattern(term: str) -> re.Pattern:
    """A single-case term matches any case, a mixed-case term matches as typed, and the
    edges are 'no word character on either side' so a symbol-edged term still matches
    whole. A term shorter than SHORT_TERM matches as typed whatever its case: an all-caps
    two-letter term under the any-case rule is the common word it spells."""
    short = len(term) < SHORT_TERM
    flags = re.I if (not short and (term == term.upper() or term == term.lower())) else 0
    return re.compile(r"(?<!\w)" + re.escape(term) + r"(?!\w)", flags)


def raw_term_hit(text: str, terms) -> bool:
    return any(term_pattern(t).search(text) for t in terms)


def term_spans(text: str, terms) -> list[tuple[int, int, str]]:
    """(start, end, view) for every term hit, views "raw", "normalized" and "encoded", all
    computed on the same original text. Where spans overlap the longest wins, and at equal
    length the raw view, so the result is deterministic and one placeholder never hides a
    hit another view would have found."""
    if not terms:
        return []
    import normalize as nz   # imported here: normalize reads FOLD_CHARS from this module
    raw: list[tuple[int, int]] = []
    for term in terms:
        raw += [(m.start(), m.end()) for m in term_pattern(term).finditer(text)]
    normalized = nz.normalized_hits(text, terms)
    encoded = nz.encoded_hits(text, lambda decoded: raw_term_hit(decoded, terms)
                              or bool(nz.normalized_hits(decoded, terms)))
    candidates = ([(s, e, 0, "raw") for s, e in nz.merge_spans(raw)]
                  + [(s, e, 1, "normalized") for s, e in normalized]
                  + [(s, e, 2, "encoded") for s, e in encoded])
    candidates.sort(key=lambda c: (-(c[1] - c[0]), c[0], c[2]))
    taken: list[tuple[int, int, str]] = []
    for s, e, _, view in candidates:
        if any(s < te and ts < e for ts, te, _ in taken):
            continue
        taken.append((s, e, view))
    return taken


# Project subjects from a repo's own PROJECTS/ folders, so a new project needs no edit.
# Only engagement-shaped folders count: one with a vault suffix whose head is not a
# generic stand-in.
PROJECT_SUFFIXES = ("-okf", "-enrich", "-staging", "-prev")
PLACEHOLDER_WORDS = frozenset({
    "poc", "alias", "project", "vault", "name", "out", "x", "y", "v", "id",
    "acme", "test", "example", "sample", "foo", "bar", "contoso", "client",
    "certs", "drafts", "shared", "common", "archive", "templates",
})


def project_aliases(repo: Path | None) -> set[str]:
    found: set[str] = set()
    if repo is None:
        return found
    try:
        base = Path(repo) / "PROJECTS"
        if not base.is_dir():
            return found
        for child in base.iterdir():
            if not child.is_dir() or not any(s in child.name.lower() for s in PROJECT_SUFFIXES):
                continue
            head = re.split(r"[-_]", child.name, maxsplit=1)[0]
            if len(head) >= 2 and not head.isdigit() and head.lower() not in PLACEHOLDER_WORDS:
                found.add(head)
    except OSError:
        pass
    return found


# ---------------------------------------------------------------- allowances
# Each one clears a finding of the class it names, judged on that finding's own text,
# and never rewrites the text before detection: a term inside an allowed address is
# still a term.

RESERVED_DOMAINS = ("example.com", "example.net", "example.org", "example", "test", "invalid",
                    "localhost", "local", "noreply.github.com")
PLACEHOLDER_OWNERS = frozenset({
    "me", "you", "user", "username", "name", "someone", "example", "test",
    "alice", "bob", "foo", "bar", "runner", "your-name", "yourname", "owner",
})
# A redaction marker, an all-x placeholder, or one of this engine's own placeholders.
SECRET_PLACEHOLDER = re.compile(r"\{redacted[-_][A-Za-z0-9_-]+\}|(?:[A-Za-z]{1,12}_)*[xX*]{4,}|\[[A-Z]+\]")
# Values no one issues as a credential: what a fixture or a compose file writes as the
# password of a local database URL or a documentation example.
SECRET_STANDINS = frozenset({"pw", "pass", "password", "secret", "changeme", "example", "test",
                             "dummy", "app", "postgres", "root", "admin", "user"})
FICTIONAL_PHONE = re.compile(r"555[-. ]?01\d\d$")


def synthetic(digits: str) -> bool:
    """True for a run no tracker would issue: every digit the same, a consecutive
    ascending or descending run, or a zero-padded counter under three digits.
    Hex digits count too, for a GUID's."""
    if len(set(digits.lower())) == 1:
        return True
    stripped = digits.lstrip("0")
    if stripped != digits and len(stripped) <= 2:
        return True
    seq = [int(c, 16) for c in digits]
    steps = {b - a for a, b in zip(seq, seq[1:])}
    return steps in ({1}, {-1})


def allowed(hit: Hit, text: str) -> bool:
    value = text[hit.start:hit.end]
    if hit.cls == "email":
        domain = value.rsplit("@", 1)[-1].lower().rstrip(".")
        return any(domain == d or domain.endswith("." + d) for d in RESERVED_DOMAINS)
    if hit.cls == "home_path":
        # a one-letter owner is a placeholder; two letters can be a real login
        owner = re.split(r"[/\\]", value.rstrip("/\\"))[-1]
        return (len(owner) == 1 or owner.lower() in PLACEHOLDER_OWNERS
                or not re.fullmatch(r"[A-Za-z0-9._-]+", owner))
    if hit.cls == "phone":
        return bool(FICTIONAL_PHONE.search(re.sub(r"[^\d. -]", "", value).strip()))
    if hit.cls == "secret":
        return bool(SECRET_PLACEHOLDER.fullmatch(value)) or value.lower() in SECRET_STANDINS
    if hit.cls == "work_item":
        m = WORK_ITEM.fullmatch(value)
        return bool(m and synthetic(m.group(1)))
    if hit.cls == "guid":
        # a stand-in such as 00000000-0000-4000-8000-000000000001: skip the version
        # and variant digits, which a fixture writer sets to make the GUID valid
        hexdigits = value.replace("-", "")
        if hexdigits not in (hexdigits.lower(), hexdigits.upper()):
            return False   # mixed case could carry data past the same-digit check
        return synthetic(hexdigits[:12] + hexdigits[13:16] + hexdigits[17:])
    return False


# ---------------------------------------------------------------- finding


def _key_header_hits(text: str, secret_spans: list[tuple[int, int]]) -> list[Hit]:
    out = []
    for m in KEY_HEADER.finditer(text):
        if any(s <= m.start() < e for s, e in secret_spans):
            continue   # inside a whole PEM block, already a secret
        body, examined = False, 0
        line_end = text.find("\n", m.end())
        rest = text[line_end + 1:].splitlines() if line_end != -1 else []
        for nxt in rest:
            if PEM_FILLER.match(nxt):
                continue
            examined += 1
            body = bool(KEY_BODY.match(nxt.strip()))
            if body or examined >= KEY_LOOKAHEAD:
                break
        out.append(Hit(m.start(), m.end(), "secret" if body else "key_header",
                       "key-material" if body else "bare-header"))
    return out


def find(text: str, terms=None, *, allow: bool = True) -> list[Hit]:
    """Every detector over text. terms is a set of term-list entries, or None to skip the
    term class. Allowances are applied unless allow is False."""
    if not isinstance(text, str) or not text:
        return []
    import normalize as nz
    hits: list[Hit] = []
    secret_spans: list[tuple[int, int]] = []
    for regex in SECRET_PATTERNS:
        for m in regex.finditer(text):
            s, e = (m.start(1), m.end(1)) if m.lastindex else (m.start(), m.end())
            secret_spans.append((m.start(), m.end()))
            hits.append(Hit(s, e, "secret", "shape"))
    hits += _key_header_hits(text, secret_spans)
    for cls, _placeholder, regex in CUSTOM_CHECKS:
        for m in regex.finditer(text):
            s, e = (m.start(1), m.end(1)) if m.lastindex else (m.start(), m.end())
            hits.append(Hit(s, e, cls, "shape"))
    for m in WORK_ITEM.finditer(text):
        hits.append(Hit(m.start(), m.end(), "work_item", "shape"))
    for m in GUID.finditer(text):
        hits.append(Hit(m.start(), m.end(), "guid", "shape"))
    # an encoded run whose decoded text holds a secret or a personal shape
    for s, e, decoded in nz.encoded_runs(text):
        if any(regex.search(decoded) for regex in SECRET_PATTERNS):
            hits.append(Hit(s, e, "secret", "encoded"))
            continue
        for cls, _placeholder, regex in CUSTOM_CHECKS:
            if regex.search(decoded):
                hits.append(Hit(s, e, cls, "encoded"))
                break
    hits += [Hit(s, e, "term", view) for s, e, view in term_spans(text, terms or ())]
    hits += invisible_hits(text)
    if allow:
        hits = [h for h in hits if not allowed(h, text)]
    return sorted(set(hits), key=lambda h: (h.start, h.end, h.cls))


# ---------------------------------------------------------------- commit messages
# A commit message is permanent, searchable and never scrubbed. One that names what was
# removed is a signpost: it gives the category, the files and the date window. DISCLOSURE
# is the message describing sensitivity instead of the change.

DISCLOSURE = re.compile(
    r"\b("
    r"de-?identif\w*|anonymi[sz]\w*|pseudonymi[sz]\w*|"
    r"identifiers?\s+(removed|stripped|cleared|out)|"
    r"(private|client|project)\s+(alias|aliases|identifiers?|names?|data)|"
    r"real\s+(incident|incidents|names?|people|dates?)|"
    r"person(al)?\s+(initials|identifiers?)|work-?item\s+identifiers?"
    r")\b",
    re.I,
)
# Verbs that are also ordinary engineering vocabulary. They count unless the message uses
# them in a listed harmless collocation, so an unlisted subject fails closed.
DISCLOSURE_VERB = re.compile(
    r"\b(scrub(bed|bing|s)?|saniti[sz](e|es|ed|er|ers|ing|ation)|redact(s|ed|ing|ion)?|"
    r"leak(ed|ing|s|age)?|expos(e|es|ed|ure|ing)|mask(ed|ing|s)?)\b",
    re.I,
)
HARMLESS_USE = re.compile(
    r"\b(memory|connection|resource|handle|fd|file[- ]descriptor|goroutine|thread|socket)"
    r"\s+leak(s|ed|age)?\b|"
    r"\bsaniti[sz]\w*\s+(the\s+)?((user|untrusted)\s+)?(input|inputs|html|sql|args|arguments|"
    r"query|queries)\b|"
    r"\bsaniti[sz]\w*\s+(the\s+)?(user|untrusted)\s+(output|markdown|filename|filenames|"
    r"url|urls|path|paths)\b|"
    r"\bexpos\w*\s+(a\s+|the\s+)?(port|ports|endpoint|endpoints|api|metric|metrics|method|"
    r"methods|function|functions|prop|props|option|options|flag|flags|hook|hooks|"
    r"type|types|interface|interfaces)\b|"
    r"\bscrub\w*\s+(stale\s+)?(the\s+)?(cache|caches|build|builds|artifact|artifacts|tmp|temp)\b|"
    r"\b(bit|subnet|net|affinity|signal)\s*mask(s|ed|ing)?\b|\bmask\s+(bits?|the\s+cursor)\b|"
    # The skill named sanitize, as a proper noun: a subject prefix, the spec file, a
    # backticked name, its script's file name, or "the sanitize skill" (user ruling 2026-10-09).
    r"(?:^|\n)\s*saniti[sz]e:|`saniti[sz]e`|\bSPEC-SANITIZE\b|\bsaniti[sz]e\.py\b|"
    r"\b(the\s+)?saniti[sz]e\s+(skill|spec|engine|command|gate)\b",
    re.I,
)
PROJECT_FOLDER = re.compile(r"(?:PROJECTS/)?[\w]+[-_](?:OKF|ENRICH|STAGING|PREV)\b")
MESSAGE_CLASSES = ("role_code", "catalog", "work_item", "term", "secret")


def find_message(text: str, terms=None) -> list[Hit]:
    """The commit-message rules: DISCLOSURE (class `disclosure`), then the identifier
    shapes, work items, project folder names, terms and secrets. A harmless collocation
    exempts only the verb inside it, so a second subject elsewhere still counts."""
    if not isinstance(text, str) or not text.strip():
        return []
    hits = [Hit(m.start(), m.end(), "disclosure", "phrase") for m in DISCLOSURE.finditer(text)]
    safe = [m.span() for m in HARMLESS_USE.finditer(text)]
    hits += [Hit(m.start(), m.end(), "disclosure", "verb") for m in DISCLOSURE_VERB.finditer(text)
             if not any(a <= m.start() < b for a, b in safe)]
    hits += [Hit(m.start(), m.end(), "project_folder", "shape") for m in PROJECT_FOLDER.finditer(text)]
    hits += [h for h in find(text, terms) if h.cls in MESSAGE_CLASSES]
    return sorted(set(hits), key=lambda h: (h.start, h.end, h.cls))


# ---------------------------------------------------------------- severity tables
# One detector set, one table per consumer. A class missing from a table is not reported
# by that consumer. Invisible characters are judged by rule: the attack rules block, the
# variation selectors warn, and the cosmetic rules follow the consumer's "other" entry.

# Paths that legitimately hold project identifiers: a project workspace, working state,
# drafts and the archive. A term there is a warning in the review sweep, not a failure.
PROJECT_PATHS = ("/PROJECTS/", "/_PROJECTS/", "/tasks/", "/DRAFTS/", "/__archive/")

TIERS = {
    "gate": {
        "secret": BLOCK, "disclosure": BLOCK, "home_path": BLOCK,
        "term": WARN, "email": WARN, "phone": WARN, "key_header": WARN,
        "work_item": WARN, "role_code": WARN, "catalog": WARN, "guid": WARN, "project_folder": WARN,
        "invisible-attack": BLOCK, "invisible-selector": WARN, "invisible-other": WARN,
    },
    "review": {
        "secret": BLOCK, "term": BLOCK, "home_path": BLOCK, "email": BLOCK,
        "key_header": WARN, "work_item": WARN, "role_code": WARN, "catalog": WARN,
        "invisible-attack": BLOCK, "invisible-selector": WARN,
    },
    "mail": {
        "secret": BLOCK, "term": BLOCK, "email": BLOCK, "phone": BLOCK, "key_header": BLOCK,
        "work_item": BLOCK, "role_code": BLOCK, "catalog": BLOCK,
        "invisible-attack": BLOCK,
    },
}


def tier_key(hit: Hit) -> str:
    if hit.cls != "invisible":
        return hit.cls
    if hit.rule in INVISIBLE_ATTACK:
        return "invisible-attack"
    return "invisible-selector" if hit.rule == "variation-selector" else "invisible-other"


def severity(consumer: str, hit: Hit, path: str | None = None) -> str | None:
    """block, warn or None (not reported) for one hit in one consumer."""
    level = TIERS[consumer].get(tier_key(hit))
    if consumer == "review" and hit.cls == "term" and path is not None:
        normalized = "/" + str(path).replace(os.sep, "/").lstrip("/")
        if any(marker in normalized for marker in PROJECT_PATHS):
            return WARN
    return level


def line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1
