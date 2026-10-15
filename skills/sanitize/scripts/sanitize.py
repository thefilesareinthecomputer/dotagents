#!/usr/bin/env python3
"""sanitize - one deterministic scrubbing engine for copies, answers and trees.

No model runs here. Text goes through fixed passes in a fixed order: secret shapes,
custom shape checks (email, phone, home path, role code, catalog), the station term
list on raw and normalized text, then any per-run ban list, terms and patterns.
Every hit becomes a class placeholder and is counted; no matched value is ever
printed, logged or written to a report.

Modes:
  answer   text on stdin -> text on stdout; a term-list hit withholds the whole answer (exit 3)
  copy     a file or folder -> a sanitized copy at --out (alias: corpus)
  tree     a repo path -> report only, exit 1 on hits
  doctor   station list present, normalization self-test

Exit codes: 0 clean or sanitized, 1 tree found hits, 2 bad arguments or a missing
station term list, 3 answer withheld, 4 masker error (Phase 2).

Stdlib only. The station term list is read from IDENTIFIER_TERMS_FILE or its default
location and is never copied anywhere; the examples in this file and its tests are
invented words.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import secrets
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import filetypes as ft  # noqa: E402
import normalize as nz  # noqa: E402

SECRET = "[SECRET]"
TERM = "[TERM]"

# ---------------------------------------------------------------- errors


class SanitizeError(Exception):
    def __init__(self, message: str, code: int = 2):
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------- secrets
# Each pattern masks group 1 when it has one, else the whole match.

SECRET_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    re.compile(r"(?:^|\s)--?(?:password|passwd|pwd|token|secret|api[-_]?key)[=\s]+[\"']?([^\s\"'`;&|]{6,})", re.I),
    re.compile(r"(?<!\S)-u\s+[^\s:]+:([^\s\"'`;&|]+)"),
    re.compile(r"\s-p([^\s\"'`;&|-]{6,})"),
    re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b|\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"),
    re.compile(r"\bsk_(?:live|test)_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\b(?:npm|hf)_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    re.compile(r"\b[a-z][a-z0-9+.-]*://[^/\s:@]+:([^/\s@]+)@", re.I),
    re.compile(r"\bbearer\s+([A-Za-z0-9._~+/=-]{16,})", re.I),
    # HTTP basic credentials are a secret whatever the decoded pair looks like
    re.compile(r"\bauthorization\s*[:=]\s*[\"']?basic\s+([A-Za-z0-9+/=_-]{8,})", re.I),
    re.compile(r"\b(?:authorization|x-api-key|api[-_]?key)\s*[:=]\s*[\"']?((?=[A-Za-z0-9._~+/=-]*\d)[A-Za-z0-9._~+/=-]{12,})(?![\w(])", re.I),
    # A key-like name assigned a credential-shaped value: 12 or more key characters holding at
    # least one digit, so `key = parts[0]`, `tokens = text.split()` and `TOKEN = "[SECRET]"`
    # in code are left alone while `API_TOKEN=9f3k...` is caught.
    re.compile(r"\b[A-Za-z0-9_]*(?:key|token|secret|password|passwd|pwd|credential)[A-Za-z0-9_]*\s*[=:]\s*[\"']?((?=[A-Za-z0-9_\-+/=~]*\d)[A-Za-z0-9_\-+/=~]{12,})(?![\w(.\[])", re.I),
]

# A parsed file hands the scrubber a key and a value apart, so `{"password": "..."}` never
# reaches the assignment rule as `password=...`. Field-aware scrubbing rejoins them.
CREDENTIAL_KEY_RE = re.compile(r"(?:key|token|secret|password|passwd|pwd|credential|authorization)", re.I)
KEY_VALUE_RULE = SECRET_PATTERNS[-1]


def scrub_field(key: str, value: str, counts: dict, scrub) -> str:
    """A string value under a credential-shaped key is judged as the assignment `key=value`
    would be: a credential-shaped value becomes [SECRET] whole; anything else goes through
    the ordinary scrub."""
    if isinstance(key, str) and isinstance(value, str) and value and CREDENTIAL_KEY_RE.search(key):
        probe = f"{key}={value}"
        m = KEY_VALUE_RULE.search(probe)
        if m and m.group(1) == value:
            counts["secret"] = counts.get("secret", 0) + 1
            return SECRET
    return scrub(value, counts)


# ---------------------------------------------------------------- custom shape checks
# (class, placeholder, pattern). Group 1, when present, is the part replaced.

CUSTOM_CHECKS = [
    ("email", "[EMAIL]", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    # International or national phone: optional +CC, then 3 groups separated by space, dot or dash,
    # 10 to 11 digits in all. Dotted version strings and bare ports have fewer digits and no separators.
    ("phone", "[PHONE]", re.compile(r"(?<![\w.])(?:\+\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?![\w.])")),
    # Built from two pieces so the pattern's own source does not form the shape it matches.
    ("home_path", "[HOME]", re.compile(r"(?<![\w/])(" + "/" + r"(?:Users|home)/[^/\s\"'`]+)(?=/|\s|$|[\"'`)])")),
    ("role_code", "[ROLE]", re.compile(r"\b[A-Z]{1,4}\s*\((?:DE|DA|ITL|BA|PM|QA|SA|SO)\d+\)")),
    ("catalog", "[CATALOG]", re.compile(r"\b(?:prod|uat|dev|test|stg)[-_]?(?:bronze|silver|gold|raw|landing)\b", re.I)),
]

# ---------------------------------------------------------------- the term list


def terms_file() -> Path:
    return Path(os.environ.get("IDENTIFIER_TERMS_FILE") or Path.home() / ".claude" / "private" / "identifier-terms.txt")


def read_term_file(path: Path) -> set[str]:
    """One term per line; a line that is `#` or starts with `# ` is a comment, `#tag` is a term."""
    lines = path.read_text(encoding="utf-8").splitlines()
    out = set()
    for ln in lines:
        s = ln.strip()
        if s and not (s == "#" or s.startswith("# ")):
            out.add(s)
    return out


def station_terms() -> set[str]:
    """The station term list, failing closed: a missing or unreadable list is a refusal."""
    path = terms_file()
    try:
        terms = read_term_file(path)
    except OSError as exc:
        raise SanitizeError(f"station term list not readable at {path}: {exc.strerror or exc}; "
                            "pass --no-station-terms to run without it on purpose", 2)
    if not terms:
        # comments and blank lines only: the backstop would be silently off
        raise SanitizeError(f"station term list at {path} holds no terms; "
                            "pass --no-station-terms to run without it on purpose", 2)
    return terms


SHORT_TERM = 4   # below this length a term matches as typed only; the normalized view skips it already


def term_pattern(term: str) -> re.Pattern:
    """The identifier hook's rule: a single-case term matches any case, a mixed-case term
    matches as typed, and the edges are 'no word character on either side' so a
    symbol-edged term still matches whole. A term shorter than SHORT_TERM matches as
    typed whatever its case: an all-caps two-letter term under the any-case rule is the
    common word it spells."""
    short = len(term) < SHORT_TERM
    flags = re.I if (not short and (term == term.upper() or term == term.lower())) else 0
    return re.compile(r"(?<!\w)" + re.escape(term) + r"(?!\w)", flags)


# ---------------------------------------------------------------- the passes


def _sub_counting(regex: re.Pattern, text: str, placeholder: str, counts: dict, cls: str) -> str:
    def repl(m):
        counts[cls] = counts.get(cls, 0) + 1
        if m.lastindex:
            return m.group(0)[:m.start(1) - m.start(0)] + placeholder + m.group(0)[m.end(1) - m.start(0):]
        return placeholder
    return regex.sub(repl, text)


def _raw_term_hit(text: str, terms: set[str]) -> bool:
    return any(term_pattern(t).search(text) for t in terms)


def _term_pass(text: str, terms: set[str], counts: dict, cls: str) -> str:
    """One term set, three views, all computed on the same original text: raw matches by
    the matching rule (counted as cls), the normalized view for split tokens, punctuation,
    confusables and zero-width characters (cls-normalized), and base64 or hex runs whose
    decoded text holds a term (cls-encoded). The spans are merged and replaced once, so a
    placeholder written for one view can neither be re-matched by the next nor hide a hit
    the next would have found (a council finding, 2026-10-10). Where spans overlap the
    longest wins, and at equal length the raw view, so the result is deterministic."""
    if not terms:
        return text
    raw: list[tuple[int, int]] = []
    for term in terms:
        raw += [(m.start(), m.end()) for m in term_pattern(term).finditer(text)]
    normalized = nz.normalized_hits(text, terms)
    encoded = nz.encoded_hits(text, lambda decoded: _raw_term_hit(decoded, terms)
                              or bool(nz.normalized_hits(decoded, terms)))
    candidates = ([(s, e, 0, cls) for s, e in nz.merge_spans(raw)]
                  + [(s, e, 1, f"{cls}-normalized") for s, e in normalized]
                  + [(s, e, 2, f"{cls}-encoded") for s, e in encoded])
    candidates.sort(key=lambda c: (-(c[1] - c[0]), c[0], c[2]))
    taken: list[tuple[int, int]] = []
    for s, e, _, key in candidates:
        if any(s < te and ts < e for ts, te in taken):
            continue
        taken.append((s, e))
        counts[key] = counts.get(key, 0) + 1
    return nz.replace_spans(text, taken, TERM) if taken else text


def _encoded_shape_pass(text: str, counts: dict) -> str:
    """An encoded run whose decoded text holds a secret or a custom shape is replaced whole
    by that class's placeholder (counted as `<class>-encoded`). Without this, a base64 key
    or email survives every view, since the term pass decodes runs for terms only."""
    taken: list[tuple[int, int, str, str]] = []
    for s, e, decoded in nz.encoded_runs(text):
        if any(regex.search(decoded) for regex in SECRET_PATTERNS):
            taken.append((s, e, SECRET, "secret-encoded"))
            continue
        for cls, placeholder, regex in CUSTOM_CHECKS:
            if regex.search(decoded):
                taken.append((s, e, placeholder, f"{cls}-encoded"))
                break
    if not taken:
        return text
    kept: list[tuple[int, int, str, str]] = []
    for s, e, placeholder, key in sorted(taken, key=lambda c: (-(c[1] - c[0]), c[0])):
        if any(s < te and ts < e for ts, te, _, _ in kept):
            continue
        kept.append((s, e, placeholder, key))
        counts[key] = counts.get(key, 0) + 1
    for s, e, placeholder, _ in sorted(kept, reverse=True):
        text = text[:s] + placeholder + text[e:]
    return text


def term_hit(counts: dict) -> bool:
    """True when any term-list or ban-list class fired, in any view."""
    return any(v for k, v in counts.items() if k.split("-")[0] in ("term", "ban"))


def scrub_text(text: str, terms: set[str], counts: dict | None = None, *,
               extra_terms: set[str] | None = None, extra_patterns: list[str] | None = None) -> str:
    """Return text with every hit replaced by its class placeholder; tally by class into counts.

    Order: secret shapes, custom shape checks, station terms, then the per-run ban terms
    and patterns. Longer terms are matched first so a multi-word term is one hit."""
    if not isinstance(text, str) or not text:
        return text
    counts = counts if counts is not None else {}
    for regex in SECRET_PATTERNS:
        text = _sub_counting(regex, text, SECRET, counts, "secret")
    for cls, placeholder, regex in CUSTOM_CHECKS:
        text = _sub_counting(regex, text, placeholder, counts, cls)
    text = _encoded_shape_pass(text, counts)
    text = _term_pass(text, set(terms or ()), counts, "term")
    text = _term_pass(text, set(extra_terms or ()), counts, "ban")
    for pat in extra_patterns or ():
        text = _sub_counting(re.compile(pat), text, "[PATTERN]", counts, "pattern")
    return text


# ---------------------------------------------------------------- run options


class Options:
    """The resolved term sets for one run."""

    def __init__(self, args: argparse.Namespace):
        self.terms: set[str] = set() if args.no_station_terms else station_terms()
        self.docx: bool = bool(getattr(args, "include_docx", False))
        self.extra_terms: set[str] = set()
        self.extra_patterns: list[str] = []
        config = self._load_config(getattr(args, "config", None))
        for ban in [config.get("ban_list"), getattr(args, "ban_list", None)]:
            if ban:
                try:
                    self.extra_terms |= read_term_file(Path(ban).expanduser())
                except OSError as exc:
                    raise SanitizeError(f"ban list not readable: {exc.strerror or exc}", 2)
        self.extra_terms |= {t.strip() for t in config.get("terms", []) if t.strip()}
        self.extra_terms |= {t.strip() for t in (getattr(args, "terms", None) or "").split(",") if t.strip()}
        for p in list(config.get("patterns", [])) + list(getattr(args, "patterns", None) or []):
            try:
                re.compile(p)
            except re.error as exc:
                raise SanitizeError(f"bad pattern regex: {exc}", 2)
            self.extra_patterns.append(p)

    @staticmethod
    def _load_config(path: str | None) -> dict:
        """A per-corpus config: {"ban_list": file, "terms": [...], "patterns": [...]}.
        Codenames go in as terms; they match by the same rule."""
        if not path:
            return {}
        try:
            cfg = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise SanitizeError(f"config not readable: {exc}", 2)
        if not isinstance(cfg, dict) or not set(cfg) <= {"ban_list", "terms", "patterns"}:
            raise SanitizeError("config must be an object with only ban_list, terms and patterns", 2)
        return cfg

    def scrub(self, text: str, counts: dict) -> str:
        return scrub_text(text, self.terms, counts, extra_terms=self.extra_terms, extra_patterns=self.extra_patterns)

    def field(self, key: str, value: str, counts: dict) -> str:
        return scrub_field(key, value, counts, self.scrub)


def add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--no-station-terms", action="store_true", help="run without the station term list, on purpose")
    p.add_argument("--ban-list", help="a second term list file for this run")
    p.add_argument("--terms", help="comma-separated extra terms for this run; visible in the process list, so prefer --ban-list or --config for protected values")
    p.add_argument("--patterns", nargs="*", help="extra regexes for this run")
    p.add_argument("--config", help="a per-corpus JSON config with ban_list, terms and patterns")
    p.add_argument("--include-docx", action="store_true",
                   help="scan Word files with the best-effort text-node pass; by default they are skipped as uninspected, since that pass misses attributes, CDATA and a term split across runs")


# ---------------------------------------------------------------- modes


def cmd_answer(args: argparse.Namespace) -> int:
    opts = Options(args)
    text = sys.stdin.read()
    # The term check runs on the original text: a term inside an address or a path would
    # otherwise be replaced by a shape pass first and never counted.
    probe: dict = {}
    _term_pass(text, opts.terms, probe, "term")
    _term_pass(text, opts.extra_terms, probe, "ban")
    if term_hit(probe):
        print("withheld: the answer touched a protected term")
        return 3
    counts: dict = {}
    out = opts.scrub(text, counts)
    if term_hit(counts):
        print("withheld: the answer touched a protected term")
        return 3
    if counts.get("pattern"):
        print("withheld: the answer touched a protected pattern")
        return 3
    sys.stdout.write(out)
    return 0


# ---------------------------------------------------------------- walking and the report

DEFAULT_EXCLUDES = [".git", "node_modules", "__pycache__", ".DS_Store", ".venv", "venv",
                    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", "dist", "build"]


def excluded(rel: Path, globs: list[str]) -> bool:
    parts = rel.parts
    return any(fnmatch.fnmatch(part, g) for part in parts for g in globs)


def tracked_files(src: Path) -> list[Path]:
    """Relative paths git tracks under src, or a refusal when src is not in a repository."""
    import subprocess
    try:
        res = subprocess.run(["git", "-C", str(src), "ls-files", "-z"], capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        # the path and git's own message are not repeated: either may hold a listed term
        raise SanitizeError(f"--tracked needs a git repository at the path given ({type(exc).__name__})", 2)
    return [Path(p) for p in res.stdout.decode("utf-8", "surrogateescape").split("\0") if p]


def iter_files(src: Path, globs: list[str], tracked: bool = False):
    """(path, relative path) for every regular file under src, sorted, excludes applied
    to any path component. A single file yields itself with its name as the relative path.
    With tracked, only files git tracks under src are walked."""
    if src.is_file():
        yield src, Path(src.name)
        return
    if tracked:
        rels = tracked_files(src)
    else:
        rels = [p.relative_to(src) for p in sorted(src.rglob("*")) if p.is_file() and not p.is_symlink()]
    for rel in rels:
        p = src / rel
        if excluded(rel, globs) or not p.is_file() or p.is_symlink():
            continue
        yield p, rel


class Report:
    def __init__(self, mode: str):
        self.mode = mode
        self.files = 0
        self.removed: dict = {}
        self.files_changed: list = []
        self.skipped: list = []
        self.withheld = 0
        self.verified: bool | None = None   # the release verifier's verdict on a copy; None when it did not run

    def add_counts(self, counts: dict) -> None:
        for k, v in counts.items():
            self.removed[k] = self.removed.get(k, 0) + v

    def as_dict(self) -> dict:
        out = {"mode": self.mode, "files": self.files, "removed": dict(sorted(self.removed.items())),
               "recall_layer": "off", "files_changed": self.files_changed, "skipped": self.skipped,
               "withheld": self.withheld}
        if self.mode == "copy":
            out["verified"] = self.verified
        return out


def scan_one(path: Path, rel: Path, opts: "Options", report: Report, max_bytes: int):
    """Sanitize one file in memory. Returns (clean relative path, sanitized bytes or None,
    skip reason or None). Path components go through the same engine, counted as 'path'."""
    counts: dict = {}
    path_counts: dict = {}
    clean_parts = [opts.scrub(part, path_counts) for part in rel.parts]
    for k, v in path_counts.items():
        counts["path"] = counts.get("path", 0) + v
    clean_rel = Path(*clean_parts)
    try:
        size = path.stat().st_size
        if size > max_bytes:
            report.skipped.append({"path": str(clean_rel), "why": "too-large"})
            report.add_counts(counts)
            return clean_rel, None, "too-large"
        data = path.read_bytes()
    except OSError:
        # a file this user cannot read is a reported skip, never a traceback holding its path
        report.skipped.append({"path": str(clean_rel), "why": "unreadable"})
        report.add_counts(counts)
        return clean_rel, None, "unreadable"
    out, why = ft.sanitize_bytes(path.name, data, opts.scrub, counts, opts.field, docx=opts.docx)
    report.add_counts(counts)
    if why:
        report.skipped.append({"path": str(clean_rel), "why": why})
        return clean_rel, None, why
    report.files += 1
    removed = sum(counts.values())
    if removed:
        # the report names files by their clean paths only; the origin is the clean top folder
        origin = clean_parts[0] if len(clean_parts) > 1 else clean_rel.name
        report.files_changed.append({"path": str(clean_rel), "origin": origin, "removed": removed,
                                     "classes": dict(sorted(counts.items()))})
    return clean_rel, out, None


REPORT_NAME = "sanitize-report.json"
UNINSPECTED = ("pdf", "docx", "too-large", "unreadable", "undecodable")   # skip reasons for files that could hold text


def write_private(path: Path, data: bytes, root: Path | None = None) -> None:
    """Create `path` as a new 0600 file under `root`, parents made 0700 as needed. Never
    follows a link and never overwrites: the copy is built in a fresh staging folder, so an
    existing file at the name means two sources cleaned to one path."""
    if root is not None:
        try:
            path.resolve().relative_to(root.resolve())
        except ValueError:
            raise SanitizeError("a clean path left the output folder; nothing was written", 2)
    for parent in reversed(path.parents):
        if root is not None and root not in parent.parents and parent != root:
            continue
        if parent.is_symlink():
            raise SanitizeError("a folder on the output path is a link; nothing was written", 2)
        if not parent.exists():
            parent.mkdir(mode=0o700)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        raise SanitizeError("two source files clean to the same clean path; rename one and rerun", 2)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)


def _replace_tree(staging: Path, out: Path) -> None:
    """Move the finished staging folder onto `out`, removing what was there. The copy
    appears whole or not at all, and `--force` never overlays stale files. Only an earlier
    copy is ever removed: a folder without a report at its top is somebody's data, and the
    run refuses rather than delete it."""
    if out.exists():
        if not (out / REPORT_NAME).is_file():
            raise SanitizeError("the output path given holds something other than an earlier copy (no report at its top); "
                                "choose another destination rather than replacing it", 2)
        shutil.rmtree(out)
    os.replace(staging, out)


def resolve_out(src: Path, out_arg: str | None, opts: "Options") -> Path:
    """The destination: `--out` as given, else a `-clean` sibling named from the source's
    scrubbed name, so a term in the source's own name never lands in the output path."""
    if out_arg:
        given = Path(out_arg).expanduser().absolute()
        if given.is_symlink():
            raise SanitizeError("the output path given is a link; nothing was written", 2)
        return given.resolve()
    stem = opts.scrub(src.stem if src.is_file() else src.name, {})
    return src.with_name(f"{stem}-clean{src.suffix}" if src.is_file() else f"{stem}-clean")


def cmd_copy(args: argparse.Namespace) -> int:
    opts = Options(args)
    src = Path(args.src).expanduser().resolve()
    if not src.exists():
        raise SanitizeError("the source path given does not exist", 2)
    out = resolve_out(src, args.out, opts)
    if out.is_symlink():
        raise SanitizeError("the output path given is a link; nothing was written", 2)
    if out == src or src in out.parents or (src.is_dir() and out in src.parents):
        raise SanitizeError("the output path must sit outside the source", 2)
    if out.exists() and (out.is_file() or any(out.iterdir())) and not args.force:
        raise SanitizeError("the output path given already exists; pass --force to replace it", 2)
    max_bytes = int(args.max_mb * 1024 * 1024)
    report = Report("copy")
    # Everything is written into a fresh staging folder beside the destination and moved
    # onto it in one rename at the end, so a refused or failed run leaves nothing behind
    # and --force replaces the old copy rather than overlaying it.
    out.parent.mkdir(parents=True, exist_ok=True)
    staging = out.parent / f".{out.name}.sanitize-{secrets.token_hex(4)}"
    staging.mkdir(mode=0o700)
    try:
        for path, rel in iter_files(src, DEFAULT_EXCLUDES + (args.exclude or [])):
            if not src.is_file() and rel == Path(REPORT_NAME):
                raise SanitizeError(f"a source file uses the reserved report name {REPORT_NAME}; rename it and rerun", 2)
            clean_rel, data, why = scan_one(path, rel, opts, report, max_bytes)
            dst = staging / (out.name if src.is_file() else clean_rel)
            if data is None:
                if why in ("binary", "pdf") and args.include_binary:
                    write_private(dst, path.read_bytes(), staging)
                    report.skipped[-1]["copied"] = True
                else:
                    report.skipped[-1]["copied"] = False
                continue
            write_private(dst, data, staging)
        if not args.no_verify:
            run_verifier(staging, opts, args.include_binary, report)
        body = json.dumps(report.as_dict(), indent=2) + "\n"
        if src.is_file():
            write_private(staging / (out.name + "." + REPORT_NAME), body.encode("utf-8"), staging)
            if out.exists() or out.is_symlink():
                if not Path(str(out) + "." + REPORT_NAME).is_file():
                    raise SanitizeError("the output path given exists and is not an earlier copy (no report beside it); "
                                        "choose another destination rather than replacing it", 2)
                out.unlink()
            os.replace(staging / out.name, out)
            report_path = Path(str(out) + "." + REPORT_NAME)
            if report_path.exists():
                report_path.unlink()
            os.replace(staging / (out.name + "." + REPORT_NAME), report_path)
            staging.rmdir()
        else:
            write_private(staging / REPORT_NAME, body.encode("utf-8"), staging)
            _replace_tree(staging, out)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    print(body, end="")
    return 0


def run_verifier(target: Path, opts: "Options", allow_binary: bool, report: Report | None) -> None:
    """The independent pass over what was written (`verify.py`): flat text, every zip member,
    every path, every matcher, no parser shared with the engine. A residual hit or a part it
    could not inspect is a refusal, so a parser gap can never ship a copy as clean."""
    import verify as vf
    result = vf.verify_tree(target, opts, allow_binary=allow_binary, skip_names=(REPORT_NAME,))
    if report is not None:
        report.verified = result["ok"]
    if not result["ok"]:
        what = []
        if result["hits"]:
            what.append(f"{len(result['hits'])} file(s) with residual hits: "
                        + "; ".join(f"{h['path']} {h['classes']}" for h in result["hits"][:5]))
        if result["uninspected"]:
            what.append(f"{len(result['uninspected'])} part(s) not inspected: "
                        + "; ".join(f"{u['path']} ({u['why']})" for u in result["uninspected"][:5]))
        raise SanitizeError("the verifier refused the copy: " + " | ".join(what), 5)


def cmd_verify(args: argparse.Namespace) -> int:
    opts = Options(args)
    target = Path(args.src).expanduser().resolve()
    if not target.exists():
        raise SanitizeError("the path given does not exist", 2)
    import verify as vf
    result = vf.verify_tree(target, opts, allow_binary=args.allow_binary, skip_names=(REPORT_NAME,))
    print(json.dumps(result, indent=2))
    if result["hits"]:
        return 1
    return 4 if result["uninspected"] else 0


def cmd_tree(args: argparse.Namespace) -> int:
    opts = Options(args)
    src = Path(args.src).expanduser().resolve()
    if not src.exists():
        raise SanitizeError("the path given does not exist", 2)
    max_bytes = int(args.max_mb * 1024 * 1024)
    report = Report("tree")
    for path, rel in iter_files(src, DEFAULT_EXCLUDES + (args.exclude or []), tracked=args.tracked):
        scan_one(path, rel, opts, report, max_bytes)
    print(json.dumps(report.as_dict(), indent=2))
    if any(report.removed.values()):
        return 1
    # a file that could hold text and was not inspected is not a clean verdict; a known
    # binary type is not text and does not count
    if any(s["why"] in UNINSPECTED for s in report.skipped):
        return 4
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    code = 0
    try:
        terms = station_terms()
        print(f"station term list: present ({len(terms)} terms)")
    except SanitizeError as exc:
        print("station term list: " + ("holds no terms" if "no terms" in str(exc) else "missing") + f" at {terms_file()}")
        code = 2
    sample = "zоrbulаte"  # Cyrillic o and a inside an invented word
    norm, _ = nz.normalized_view("z o r b " + sample[4:])
    ok = norm == "zorbulate" and nz.normalized_hits(sample, {"zorbulate"}) == [(0, len(sample))]
    print(f"normalization self-test: {'ok' if ok else 'FAILED'}")
    print("recall layer: off (Phase 2)")
    return code if ok else 4


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="sanitize", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("answer", help="text on stdin to text on stdout; a term hit withholds the answer")
    add_common(a)
    a.set_defaults(fn=cmd_answer)

    c = sub.add_parser("copy", aliases=["corpus"], help="write a sanitized copy of a file or folder")
    c.add_argument("src")
    c.add_argument("--out", help="destination (default: a -clean sibling)")
    c.add_argument("--force", action="store_true", help="write into an existing destination")
    c.add_argument("--include-binary", action="store_true", help="copy binaries and PDFs through unchanged")
    c.add_argument("--no-verify", action="store_true", help="skip the independent verifier pass over the copy; recorded as verified null")
    c.add_argument("--max-mb", type=float, default=50, help="skip files over this size (default 50)")
    c.add_argument("--exclude", nargs="*", help=f"path-component globs to skip, added to {' '.join(DEFAULT_EXCLUDES)}")
    add_common(c)
    c.set_defaults(fn=cmd_copy)

    t = sub.add_parser("tree", help="report hits under a path without writing anything; exit 1 on hits")
    t.add_argument("src")
    t.add_argument("--max-mb", type=float, default=50)
    t.add_argument("--exclude", nargs="*")
    t.add_argument("--tracked", action="store_true", help="scan only the files git tracks under the path")
    add_common(t)
    t.set_defaults(fn=cmd_tree)

    v = sub.add_parser("verify", help="the parser-free pass over a written copy: flat text, zip members and paths against every matcher; exit 1 on a hit, 4 on an uninspected part")
    v.add_argument("src")
    v.add_argument("--allow-binary", action="store_true", help="binaries were copied through on purpose; do not count them as uninspected")
    add_common(v)
    v.set_defaults(fn=cmd_verify)

    d = sub.add_parser("doctor", help="station list present, normalization self-test, masker status")
    d.set_defaults(fn=cmd_doctor)
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    try:
        args = ap.parse_args(argv)
    except SystemExit as exc:
        return 2 if exc.code else 0
    try:
        return args.fn(args)
    except SanitizeError as exc:
        print(f"sanitize: {exc}", file=sys.stderr)
        return exc.code
    except OSError as exc:
        # strerror only: the filename on the exception may hold a listed term
        print(f"sanitize: a file operation failed: {exc.strerror or type(exc).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
