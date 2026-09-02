#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""obsidian_kg.py - turn any markdown corpus into a queryable SQLite knowledge graph.

Stdlib only, Python 3.10+. Storage is `<vault>/vault-kg/vault-kg.db` (SQLite +
FTS5) beside `<vault>/vault-kg/vault-kg-config.md`. The vault directory is
always a CLI argument: nothing here is tied to any particular vault, machine,
or agent, and nothing here ever sends vault text anywhere - the whole engine is
offline.

Design goals:
  * deterministic - `ingest` is a pure parse of the vault: same vault bytes
                    produce the same db content (the single `meta.ingested_at`
                    timestamp is the only exception). Every ingest is an
                    idempotent full rebuild in sorted file order.
  * faithful      - links are extracted fence-aware (fenced code blocks and
                    inline code never become edges) and wikilinks resolve the
                    way Obsidian resolves them: vault-wide case-insensitive
                    basename match, honoring frontmatter `aliases:`; a
                    path-qualified link disambiguates by path suffix; a bare
                    link whose basename collides is recorded AMBIGUOUS (edge
                    to none) - never guessed silently.
  * section-level - retrieval addresses sections, not whole files. A profile
                    declares what one unit is; a unit is never fragmented.
  * vault-agnostic - the engine knows markdown structure only. Anything
                    specific to one vault is config, never code.

Commands:
  ingest <vault>                        full rebuild: notes, sections, edges
  init <vault>                          scaffold vault-kg/ + confident config
  profile <vault>                       propose config rows; writes nothing
  query <vault> <fts-query>             raw FTS5 over sections
  search <vault> <question>             natural-language section search
  note <vault> <name>                   full note + frontmatter
  sections <vault> <name>               section outline of a note
  read <vault> <section-id>             one section, whole
  backlinks <vault> <note>              inbound edges + the section they sit in
  links <vault> <note> [--unresolved]   outbound edges
  neighbors <vault> <note> [--depth N]  BFS over resolved edges
  path <vault> <a> <b>                  shortest path over resolved edges
  tags <vault> [tag]                    tag counts, or notes bearing a tag
  entity <vault> <name>                 registered entity + its mentions
  timeline <vault> <entity>             mentions in date order
  during <vault> <event>                sections inside a bounded entity's span
  themes <vault> --from X --to Y        over-represented terms in a window
  trends <vault> --by month             what rose and fell between windows
  index <vault> [--out PATH]            render a vault index from the graph
  stats <vault>                         counts, orphans, unresolved/ambiguous
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import math
import os
import posixpath
import re
import shutil
import sqlite3
import subprocess
import sys
import urllib.parse
from datetime import date, datetime, timezone
from pathlib import Path

KG_DIR = "vault-kg"
DB_NAME = "vault-kg.db"
CONFIG_NAME = "vault-kg-config.md"

# Folders Obsidian hides or that are never vault notes; any dot folder/file is
# excluded too.
SKIP_FOLDERS = {".git", ".obsidian", ".trash", ".smart-env", "node_modules",
                ".venv", "venv", "__pycache__", ".pytest_cache"}

# Wikilink targets pointing at binary/asset embeds - never note edges.
ASSET_EXTS = {"png", "jpg", "jpeg", "gif", "svg", "webp", "bmp", "pdf",
              "mp3", "wav", "m4a", "ogg", "flac", "mp4", "mov", "mkv", "webm",
              "zip", "csv", "json", "canvas", "excalidraw"}

# Chunking limits, in words. The ceiling only ever splits structureless prose;
# a declared profile unit is never cut (see split_oversize).
SIZE_CEILING = 1000
SIZE_OVERLAP = 60
WORD_FLOOR = 25
HEADING_MAX = 120

PROFILES = {"log-dated", "reference", "dimension", "list", "generated", "hub",
            "freeform"}
SLOTS = {"authored", "quoted", "generated", "instrument", "routine", "superseded",
         "prep"}

# Prep for something that has not happened yet: talking points for a meeting with no
# entry, working notes for a story not yet picked up. It is CURRENT and worth finding, so
# it keeps full weight, but it is not a record of anything -- hence its own slot, so a
# caller asking for history can exclude it and a reader can never mistake it for one.
# It also carries no date, so it can never take a recency tier from the log around it.
PREP_MARK = "prep:"

# A section whose heading carries this marker is history: still indexed, still findable,
# still linked, but ranked below anything live. Detected from the heading itself rather
# than from a config list, so a corpus that supersedes facts continuously does not need a
# growing registry of dead headings to stay accurate.
SUPERSEDED_MARK = "(superseded"
SUPERSEDED_WEIGHT = 0.25

# What one `**ANCHOR**:` annotation adds to a section's search score. Additive
# and sized to the title boost (+1.5), so an anchor reorders comparable
# matches and can never lift a weak match over a strong one. Applied once per
# section however many ANCHOR lines it holds. Measured on a real 13k-section
# corpus: adjacent result gaps cluster either under 0.8 (near-ties, where a
# preference should decide) or above 2.1 (genuine relevance jumps, which this
# must not cross); 1.0 sits between the regimes.
ANCHOR_BOOST = 1.0

# Recency enters the search score additively, as `k * tier`, so it reorders hits
# whose relevance already sits within k of each other and can never bury a strong
# match under a weak newer one. Overridable per vault (`recency_k` in config) and
# per call (`--recency-k`); 0 switches it off.
RECENCY_K = 0.5

# Inline annotations: `**MARKER**: payload` at column 0 of a body line, ALL-CAPS
# token, colon immediately after the closing `**`. Only registered markers (this
# core set plus a vault config's `markers` array) are indexed; a grammar match
# with any other token lands in the stats candidate report instead, so a typo
# surfaces rather than silently minting vocabulary. Case is load-bearing:
# `**Note**:` is ordinary prose.
CORE_MARKERS = {
    "NOTE": "note to self and the assistant",
    "ANCHOR": "surface this: the section anchors a theme",
    "SUPERSEDED": "replaced; payload names the successor",
    "FOLLOW-UP": "open action attached to this spot",
    "CLARIFY": "open question attached to this spot",
    "DERIVED-FROM": "provenance: this content derives from the payload",
    "EVENT": "a dated occurrence; payload leads with the ISO date",
}

MARKER_LINE_RE = re.compile(r"\*\*([A-Z][A-Z0-9-]{1,31})\*\*:(?: (.*))?$")
# The token-plus-markup head of a marker line, for stripping before aggregate
# counting. Grammar-shaped rather than registry-checked on purpose: a typoed
# token is exactly as much vocabulary-not-theme as a registered one.
MARKER_HEAD_RE = re.compile(r"^\*\*[A-Z][A-Z0-9-]{1,31}\*\*: ?", re.MULTILINE)
# The ways a marker line is most naturally mis-placed: indented, behind a list
# bullet, a blockquote, or a table pipe. Detected only to feed the candidate
# report; the column-0 rule itself never bends.
MARKER_NEARMISS_RE = re.compile(r"^(?:[ \t>|]+|(?:[-*+]|\d+[.)])[ \t])+")
# Regex-gated before date.fromisoformat: 3.11+ accepts shapes 3.10 rejects
# (`20261104`, `2026-W45-1`), and an EVENT date must parse identically on every
# version the engine advertises.
MARKER_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def recency_weights(dates: list[str]) -> dict[str, float]:
    """Rank the distinct dates of ONE log and spread weight linearly across them.

    Recency is relative to the file, not to the calendar: a log with five represented
    dates has five tiers, the newest at 1.0 and the oldest at 1/5. A file that has been
    quiet for a month is still fully weighted at its own newest entry, because within that
    file that entry IS the current state. Comparing across files is the caller's job, and
    it has `doc_date` for that.

    Linear rather than exponential on purpose: a decay curve would bury a log's older
    entries below the noise of a chattier file, and the history is the point of keeping it.
    """
    uniq = sorted({d for d in dates if d}, reverse=True)
    n = len(uniq)
    if not n:
        return {}
    return {d: (n - i) / n for i, d in enumerate(uniq)}

STOPWORDS = {
    "a", "about", "above", "after", "again", "all", "am", "an", "and", "any",
    "are", "as", "at", "be", "because", "been", "before", "being", "below",
    "between", "both", "but", "by", "can", "did", "do", "does", "doing",
    "don", "down", "during", "each", "few", "for", "from", "further", "had",
    "has", "have", "having", "he", "her", "here", "hers", "him", "his", "how",
    "i", "if", "in", "into", "is", "it", "its", "just", "me", "more", "most",
    "my", "no", "nor", "not", "now", "of", "off", "on", "once", "only", "or",
    "other", "our", "ours", "out", "over", "own", "same", "she", "should",
    "so", "some", "such", "than", "that", "the", "their", "theirs", "them",
    "then", "there", "these", "they", "this", "those", "through", "to", "too",
    "under", "until", "up", "very", "was", "we", "were", "what", "when",
    "where", "which", "while", "who", "whom", "why", "will", "with", "you",
    "your", "yours",
}

MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS notes(
  id           TEXT PRIMARY KEY,      -- vault-relative path without .md
  path         TEXT NOT NULL UNIQUE,  -- vault-relative path with .md
  title        TEXT NOT NULL DEFAULT '',
  tags         TEXT NOT NULL DEFAULT '',
  aliases      TEXT NOT NULL DEFAULT '',
  content_hash TEXT NOT NULL,
  body         TEXT NOT NULL,             -- raw file text (offset base)
  profile      TEXT NOT NULL DEFAULT 'reference',
  weight       REAL NOT NULL DEFAULT 1.0,
  doc_date     TEXT NOT NULL DEFAULT '',  -- note-level date, if any
  status       TEXT NOT NULL DEFAULT 'hot'
  -- deliberately no observed_at: this table is wiped and rebuilt every ingest,
  -- so a per-note timestamp only restates meta.ingested_at while adding a
  -- second value that changes between two ingests of unchanged bytes. The
  -- determinism contract allows exactly one. It stays on `extractions`, where
  -- rows survive a rebuild and the time genuinely differs per row.
);
CREATE TABLE IF NOT EXISTS properties(
  note_id TEXT NOT NULL,
  key     TEXT NOT NULL,
  value   TEXT NOT NULL,
  PRIMARY KEY (note_id, key)
);
CREATE TABLE IF NOT EXISTS tags(
  note_id TEXT NOT NULL,
  tag     TEXT NOT NULL,
  PRIMARY KEY (note_id, tag)
);
CREATE TABLE IF NOT EXISTS aliases(
  note_id TEXT NOT NULL,
  alias   TEXT NOT NULL,
  PRIMARY KEY (note_id, alias)
);
CREATE TABLE IF NOT EXISTS edges(
  src        TEXT NOT NULL,           -- note id
  dst        TEXT,                    -- note id; NULL unless resolved
  target     TEXT NOT NULL,           -- target as written
  syntax     TEXT NOT NULL,           -- 'wiki' | 'md'
  kind       TEXT NOT NULL,           -- 'link' | 'embed'
  status     TEXT NOT NULL,           -- resolved|unresolved|ambiguous|ignored
  section_id TEXT NOT NULL DEFAULT '',-- section the link was written in
  PRIMARY KEY (src, syntax, kind, target)
);
CREATE TABLE IF NOT EXISTS sections(
  id           TEXT PRIMARY KEY,      -- deterministic: note + heading path + ord
  note_id      TEXT NOT NULL,
  parent_id    TEXT NOT NULL DEFAULT '',
  heading      TEXT NOT NULL DEFAULT '',
  heading_path TEXT NOT NULL DEFAULT '',
  level        INTEGER NOT NULL DEFAULT 0,
  ord          INTEGER NOT NULL DEFAULT 0,
  char_start   INTEGER NOT NULL,
  char_end     INTEGER NOT NULL,
  line_start   INTEGER NOT NULL,      -- 1-indexed, inclusive
  line_end     INTEGER NOT NULL,      -- 1-indexed, inclusive
  body         TEXT NOT NULL,
  own_body     TEXT NOT NULL DEFAULT '',  -- body minus nested sections
  doc_date     TEXT NOT NULL DEFAULT '',
  slot         TEXT NOT NULL DEFAULT '',
  weight       REAL NOT NULL DEFAULT 1.0,  -- recency tier within a dated log
  words        INTEGER NOT NULL DEFAULT 0,
  is_unit      INTEGER NOT NULL DEFAULT 0,
  oversize     INTEGER NOT NULL DEFAULT 0,
  section_hash TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS sections_note ON sections(note_id);
CREATE INDEX IF NOT EXISTS sections_date ON sections(doc_date);
CREATE TABLE IF NOT EXISTS members(       -- dimension-profile list members
  section_id TEXT NOT NULL,
  note_id    TEXT NOT NULL,
  group_name TEXT NOT NULL DEFAULT '',
  name       TEXT NOT NULL,
  ord        INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (section_id, name)
);
CREATE TABLE IF NOT EXISTS entities(
  canonical TEXT PRIMARY KEY,
  type      TEXT NOT NULL DEFAULT '',
  time      TEXT NOT NULL DEFAULT 'static',
  note      TEXT NOT NULL DEFAULT '',
  t_start   TEXT NOT NULL DEFAULT '',
  t_end     TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS entity_aliases(
  canonical TEXT NOT NULL,
  alias     TEXT NOT NULL,
  PRIMARY KEY (canonical, alias)
);
CREATE TABLE IF NOT EXISTS mentions(
  canonical  TEXT NOT NULL,
  section_id TEXT NOT NULL,
  note_id    TEXT NOT NULL,
  doc_date   TEXT NOT NULL DEFAULT '',
  count      INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (canonical, section_id)
);
CREATE TABLE IF NOT EXISTS ignored(       -- what an ingest excluded, and why
  path TEXT PRIMARY KEY,
  rule TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS annotations(   -- `**MARKER**:` lines, parsed at ingest
  note_id    TEXT NOT NULL,
  section_id TEXT NOT NULL DEFAULT '',    -- '' when no section contains the line
  line       INTEGER NOT NULL,            -- 1-indexed
  marker     TEXT NOT NULL,
  payload    TEXT NOT NULL DEFAULT '',
  target     TEXT NOT NULL DEFAULT '',    -- first wikilink target in the payload
  date       TEXT NOT NULL DEFAULT '',    -- leading ISO date in the payload
  PRIMARY KEY (note_id, line)
);
CREATE TABLE IF NOT EXISTS annotation_candidates( -- marker near-misses, for stats
  token TEXT NOT NULL,
  kind  TEXT NOT NULL,                    -- 'unregistered' | 'placement'
  count INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (token, kind)
);
CREATE TABLE IF NOT EXISTS extractions(   -- judgment: never wiped by ingest
  id           INTEGER PRIMARY KEY,
  section_id   TEXT NOT NULL,
  section_hash TEXT NOT NULL,
  kind         TEXT NOT NULL DEFAULT 'relation',
  subject      TEXT NOT NULL,
  predicate    TEXT NOT NULL DEFAULT '',
  object       TEXT NOT NULL DEFAULT '',
  quote        TEXT NOT NULL DEFAULT '',
  q_start      INTEGER,
  q_end        INTEGER,
  observed_at  TEXT NOT NULL DEFAULT '',
  doc_date     TEXT NOT NULL DEFAULT '',
  status       TEXT NOT NULL DEFAULT 'hot'
);
CREATE TABLE IF NOT EXISTS conflicts(     -- judgment: never wiped by ingest
  seq          INTEGER PRIMARY KEY AUTOINCREMENT,
  detected_at  TEXT NOT NULL DEFAULT '',
  key          TEXT NOT NULL,
  kind         TEXT NOT NULL,
  a_extraction INTEGER,
  b_extraction INTEGER,
  resolution   TEXT NOT NULL DEFAULT '',
  state        TEXT NOT NULL DEFAULT 'hot'
);
CREATE TABLE IF NOT EXISTS meta(
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS sections_fts USING fts5(
  id UNINDEXED, heading_path, body,
  content='sections', content_rowid='rowid');
"""

WIKILINK_RE = re.compile(r"(!?)\[\[([^\[\]]+)\]\]")
MD_LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^()]+)\)")
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
ATX_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
SETEXT_RE = re.compile(r"^(=+|-+)\s*$")
LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.*\S)\s*$")
THEMATIC_BREAK_RE = re.compile(r"^\s{0,3}(?:\*\s*){3,}$|^\s{0,3}(?:-\s*){3,}$"
                               r"|^\s{0,3}(?:_\s*){3,}$")
WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'_-]*")


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def vault_dir(arg: str) -> Path:
    vault = Path(arg).expanduser().resolve()
    if not vault.is_dir():
        sys.exit(f"error: vault directory not found: {arg}")
    return vault


def kg_dir(vault: Path) -> Path:
    return vault / KG_DIR


def db_path(vault: Path) -> Path:
    return kg_dir(vault) / DB_NAME


def prev_db_path(vault: Path) -> Path:
    """The one-deep checkpoint `ingest --keep-previous` writes and a bare
    `diff` compares against. Lives beside the live db; the gitignore pattern
    is vault-kg/*.db*, not the db filename, so this file and the SQLite
    journal/wal sidecars are covered too."""
    return kg_dir(vault) / "vault-kg-prev.db"


def config_path(vault: Path) -> Path:
    return kg_dir(vault) / CONFIG_NAME


def connect(vault: Path, must_exist: bool = False) -> sqlite3.Connection:
    db = db_path(vault)
    if must_exist and not db.exists():
        sys.exit(f"error: no database at {db} - run `ingest` on this vault first")
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db)
    con.executescript(SCHEMA)
    _add_missing_columns(con)
    return con


# Columns added to an existing table after a db was already built. `CREATE TABLE
# IF NOT EXISTS` is a no-op on a db that predates them, so the schema above alone
# leaves an older db one column short and the next ingest dies on the insert.
# ALTER TABLE ADD COLUMN is cheap and non-destructive; the default stands until a
# re-ingest computes real values, so an unmigrated db degrades to unweighted
# rather than to broken.
_ADDED_COLUMNS = {
    "sections": [("weight", "REAL NOT NULL DEFAULT 1.0")],
}


def _add_missing_columns(con: sqlite3.Connection) -> None:
    for table, columns in _ADDED_COLUMNS.items():
        try:
            have = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
        except sqlite3.DatabaseError:
            continue                      # table absent: SCHEMA just created it
        if not have:
            continue
        for name, decl in columns:
            if name not in have:
                con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
        con.commit()


# ---------- config ----------
def load_config(vault: Path) -> dict:
    """Read the one fenced json block out of vault-kg-config.md. A missing or
    empty config is not an error: the engine works with no config at all."""
    cfg_file = config_path(vault)
    if not cfg_file.exists():
        return {"ignore": [], "profiles": [], "entities": [], "markers": []}
    text = cfg_file.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^```json\s*\n(.*?)\n```", text, re.MULTILINE | re.DOTALL)
    if not m:
        return {"ignore": [], "profiles": [], "entities": [], "markers": []}
    try:
        cfg = json.loads(m.group(1))
    except json.JSONDecodeError as e:
        sys.exit(f"error: {cfg_file} has invalid json: {e}")
    if not isinstance(cfg, dict):
        sys.exit(f"error: {cfg_file} json block must be an object")
    for key in ("ignore", "profiles", "entities", "markers"):
        cfg.setdefault(key, [])
        if not isinstance(cfg[key], list):
            sys.exit(f"error: {cfg_file}: '{key}' must be a list")
    # A profiles row may match on frontmatter `kg-type` instead of a path
    # glob. `kg-type` is corpus content, so such a row is demotion-only: a
    # boost here would let a note pick its own weight class with one
    # frontmatter line - the exact hole profile_for refuses directly.
    seen_types: set[str] = set()
    for row in cfg["profiles"]:
        if not isinstance(row, dict) or "kg_type" not in row:
            continue
        ktype = str(row.get("kg_type", "")).strip().lower()
        if not ktype:
            sys.exit(f"error: {cfg_file}: empty kg_type in profiles row")
        if row.get("path"):
            sys.exit(f"error: {cfg_file}: a profiles row takes 'path' or"
                     f" 'kg_type', never both ({ktype!r})")
        if ktype in seen_types:
            sys.exit(f"error: {cfg_file}: kg_type {ktype!r} matched twice")
        seen_types.add(ktype)
        try:
            w = float(row.get("weight", 1.0))
        except (TypeError, ValueError):
            w = None
        if w is None or not math.isfinite(w) or not 0.0 <= w <= 1.0:
            sys.exit(f"error: {cfg_file}: kg_type {ktype!r} weight must be"
                     " between 0 and 1.0 - kg-type is frontmatter, and"
                     " frontmatter never buys rank")
    # Vocabulary registration only: no per-marker effects or weights exist, so
    # a config marker carries a name and a description and nothing else.
    seen_markers: set[str] = set()
    for row in cfg["markers"]:
        if not isinstance(row, dict):
            sys.exit(f"error: {cfg_file}: markers entries must be objects")
        tok = str(row.get("marker", ""))
        if not re.fullmatch(r"[A-Z][A-Z0-9-]{1,31}", tok):
            sys.exit(f"error: {cfg_file}: marker {tok!r} must be 2-32 chars"
                     " of A-Z, 0-9 and hyphen, starting with a letter")
        if tok in CORE_MARKERS:
            # The core vocabulary means the same thing in every vault; a
            # config row can add words, never redefine the shipped ones.
            sys.exit(f"error: {cfg_file}: {tok!r} is a core marker and"
                     " cannot be re-registered")
        if tok in seen_markers:
            sys.exit(f"error: {cfg_file}: marker {tok!r} registered twice")
        seen_markers.add(tok)
    if "recency_k" in cfg:
        k = cfg["recency_k"]
        if (isinstance(k, bool) or not isinstance(k, (int, float))
                or not math.isfinite(k) or k < 0):
            sys.exit(f"error: {cfg_file}: 'recency_k' must be a"
                     " non-negative number")
        cfg["recency_k"] = float(k)
    return cfg


def dump_config(cfg: dict) -> str:
    """Deterministic serialization: fixed key order, entities sorted by
    canonical, so a one-entity change is a one-line diff."""
    out = {
        "ignore": sorted(cfg.get("ignore", []),
                         key=lambda r: str(r.get("path", ""))),
        "profiles": sorted(cfg.get("profiles", []),
                           key=lambda r: str(r.get("path", ""))),
        "entities": sorted(cfg.get("entities", []),
                           key=lambda r: str(r.get("canonical", ""))),
    }
    # Written only when set: a vault that never chose a k keeps its default
    # implicit, so a config rewrite never plants the key.
    if "recency_k" in cfg:
        out["recency_k"] = cfg["recency_k"]
    # Same rule for markers: the array appears once a vault registers one.
    if cfg.get("markers"):
        out["markers"] = sorted(cfg["markers"],
                                key=lambda r: str(r.get("marker", "")))
    body = json.dumps(out, indent=2, ensure_ascii=False, sort_keys=True)
    return ("# vault-kg-config\n\n"
            "Configuration for the vault knowledge graph. Everything specific\n"
            "to this vault lives here; the engine itself knows only markdown\n"
            "structure. Edit this file directly.\n\n"
            "```json\n" + body + "\n```\n")


def profile_for(note_id: str, rel_path: str, meta: dict, cfg: dict) -> dict:
    """Resolve a note's profile row. First hit wins: frontmatter `kg-profile:`,
    then the config's `profiles` array (most specific glob), then the default."""
    fm = str(meta.get("kg-profile", "")).strip()
    if fm:
        row = {"profile": fm}
        # `weight` is deliberately not read from frontmatter. Config is curated
        # by the user; frontmatter is corpus content, and letting a note set its
        # own ranking multiplier lets one hostile file rank first on every query.
        for key in ("grain", "group_by", "date_from", "slots"):
            if key in meta:
                row[key] = meta[key]
        return row
    best, best_len = None, -1
    for row in cfg.get("profiles", []):
        pat = str(row.get("path", ""))
        if not pat:
            continue
        if glob_match(rel_path, pat) and len(pat) > best_len:
            best, best_len = row, len(pat)
    if best:
        return dict(best)
    # After path rows, never before them: a path glob is the user's explicit
    # curation, kg-type is the note's own claim about itself.
    ktype = str(meta.get("kg-type", "")).strip().lower()
    if ktype:
        for row in cfg.get("profiles", []):
            if str(row.get("kg_type", "")).strip().lower() == ktype:
                # A note self-selects into this row by writing one frontmatter
                # line, so the row hands over only what a note may choose:
                # never slots or date machinery, which frontmatter cannot
                # otherwise reach with a weight attached.
                return {k: row[k] for k in
                        ("kg_type", "profile", "weight", "description")
                        if k in row}
    return {"profile": "reference"}


GLOB_MAX_LEN = 500


def _match_segment(name: str, pat: str) -> bool:
    """Wildcard match within one path segment: `*` any run, `?` one character.

    Two pointers with a remembered star position. A regex of chained `[^/]*`
    reads more naturally and is the reason this function exists: it backtracks
    exponentially, and `*a*a*a*a*a*a*a*a*a*a*b` against one ordinary filename
    measured over a minute. Patterns come from files inside the vault, so that
    is a denial of service anybody who hands over a corpus can trigger. This
    runs in time proportional to the two lengths, always.
    """
    n = p = mark = 0
    star = -1
    while n < len(name):
        if p < len(pat) and pat[p] in ("?", name[n]):
            n += 1
            p += 1
        elif p < len(pat) and pat[p] == "*":
            star = p
            mark = n
            p += 1
        elif star >= 0:
            p = star + 1
            mark += 1
            n = mark
        else:
            return False
    while p < len(pat) and pat[p] == "*":
        p += 1
    return p == len(pat)


def _match_segments(parts: list[str], pats: list[str]) -> bool:
    """The same trick one level up, with `**` spanning whole segments."""
    n = p = mark = 0
    star = -1
    while n < len(parts):
        if p < len(pats) and pats[p] == "**":
            star = p
            mark = n
            p += 1
        elif p < len(pats) and _match_segment(parts[n], pats[p]):
            n += 1
            p += 1
        elif star >= 0:
            p = star + 1
            mark += 1
            n = mark
        else:
            return False
    while p < len(pats) and pats[p] == "**":
        p += 1
    return p == len(pats)


def glob_match(rel_path: str, pattern: str) -> bool:
    """Glob with `**` meaning any number of path segments. A bare pattern with
    no slash also matches on basename, the way gitignore does."""
    pattern = pattern.strip().lstrip("./")
    if not pattern or len(pattern) > GLOB_MAX_LEN:
        return False
    if pattern.endswith("/"):
        pattern += "**"
    if _match_segments(rel_path.split("/"), pattern.split("/")):
        return True
    if "/" not in pattern:
        return _match_segment(rel_path.rsplit("/", 1)[-1], pattern)
    return False


def load_kgignore(vault: Path) -> list[str]:
    f = vault / ".kgignore"
    if not f.exists():
        return []
    out = []
    for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def ignore_rule(rel_path: str, meta: dict, cfg: dict,
                kgignore: list[str]) -> str | None:
    """Return the rule that excludes this file, or None. Precedence matches
    profiles: frontmatter, then config, then .kgignore."""
    val = meta.get("kg-ignore")
    if isinstance(val, str) and val.strip().lower() in ("true", "yes"):
        return "frontmatter kg-ignore"
    if val is True:
        return "frontmatter kg-ignore"
    for row in cfg.get("ignore", []):
        pat = str(row.get("path", ""))
        if pat and glob_match(rel_path, pat):
            reason = str(row.get("reason", "")).strip()
            return f"config ignore {pat}" + (f" ({reason})" if reason else "")
    for pat in kgignore:
        neg = pat.startswith("!")
        if neg:
            continue
        if glob_match(rel_path, pat):
            return f".kgignore {pat}"
    return None


# ---------- parsing (deterministic, stdlib) ----------
def parse_frontmatter(text: str) -> tuple[dict, int]:
    """Parse the YAML subset Obsidian Properties use: scalar `key: value`
    (optionally quoted), inline lists `[a, b]`, block lists, and one level of
    nested mapping (used by `slots:`). Returns (meta, body_start). Files
    without valid frontmatter get ({}, 0)."""
    if not text.startswith("---\n"):
        return {}, 0
    end = text.find("\n---\n", 3)
    if end < 0:
        return {}, 0
    meta: dict = {}
    key = None
    for line in text[4:end].splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        item = re.match(r"\s+-\s+(.*)$", line)
        if item and key:
            if not isinstance(meta.get(key), list):
                meta[key] = []
            meta[key].append(_unquote(item.group(1)))
            continue
        nested = re.match(r"\s+([A-Za-z0-9_-]+):\s*(.*)$", line)
        if nested and key and meta.get(key) in ({}, []):
            # `key:` followed by indented `k: v` lines is a mapping, not a list
            if not isinstance(meta.get(key), dict):
                meta[key] = {}
            meta[key][nested.group(1)] = _unquote(nested.group(2).strip())
            continue
        if nested and key and isinstance(meta.get(key), dict):
            meta[key][nested.group(1)] = _unquote(nested.group(2).strip())
            continue
        m = re.match(r"([A-Za-z0-9_-]+):\s*(.*)$", line)
        if not m:
            continue
        key, raw = m.group(1), m.group(2).strip()
        if raw.startswith("[") and raw.endswith("]"):
            meta[key] = [_unquote(v.strip()) for v in raw[1:-1].split(",")
                         if v.strip()]
        elif raw.startswith("{") and raw.endswith("}"):
            meta[key] = _inline_map(raw)
        elif raw == "":
            meta[key] = []  # a block list or nested map may follow
        else:
            meta[key] = _unquote(raw)
    # a `key:` that got neither list items nor nested keys stays an empty list
    return meta, end + 5


def _inline_map(raw: str) -> dict:
    out = {}
    for part in raw[1:-1].split(","):
        if ":" in part:
            k, v = part.split(":", 1)
            out[_unquote(k.strip())] = _unquote(v.strip())
    return out


def _unquote(v: str) -> str:
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    return v


def _listify(v) -> list[str]:
    """Frontmatter tags/aliases may be a list or a comma-joined scalar."""
    if isinstance(v, list):
        return [str(x).strip().lstrip("#") for x in v if str(x).strip()]
    if isinstance(v, dict):
        return []
    return [t.strip().lstrip("#") for t in str(v).split(",") if t.strip()]


def fence_mask(text: str) -> list[bool]:
    """One flag per line: True where the line is inside (or is) a code fence.
    Fences pair by CommonMark rules - the closer must be at least as long as
    the opener and use the same character."""
    mask, marker = [], ""
    for line in text.splitlines():
        s = line.lstrip()
        if marker:
            mask.append(True)
            if (s.startswith(marker[0] * len(marker))
                    and set(s.strip()) <= {marker[0]}):
                marker = ""
            continue
        m = re.match(r"(`{3,}|~{3,})", s)
        if m:
            marker = m.group(1)
            mask.append(True)
            continue
        mask.append(False)
    return mask


def strip_code(text: str) -> str:
    """Blank out fenced code blocks and inline code spans, keeping line
    structure, so link and mention extraction never see code."""
    mask = fence_mask(text)
    out = []
    for i, line in enumerate(text.splitlines()):
        out.append("" if mask[i] else INLINE_CODE_RE.sub("", line))
    return "\n".join(out)


def _comment_mask(text: str) -> list[bool]:
    """One flag per line: True where the line BEGINS inside a comment - HTML
    `<!-- -->` or Obsidian's native `%% %%`, which toggles comment mode at
    every occurrence. Such a line is invisible in Obsidian's rendered view,
    and an invisible line must never carry an annotation in a corpus the
    engine treats as untrusted. Delimiters inside code fences do not open or
    close comments, matching how the renderer treats them."""
    fmask = fence_mask(text)
    mask, state = [], ""          # '' | 'html' | 'pct'
    for i, line in enumerate(text.splitlines()):
        mask.append(bool(state))
        if fmask[i]:
            continue
        pos = 0
        while True:
            if state == "html":
                j = line.find("-->", pos)
                if j == -1:
                    break
                pos, state = j + 3, ""
            elif state == "pct":
                j = line.find("%%", pos)
                if j == -1:
                    break
                pos, state = j + 2, ""
            else:
                h = line.find("<!--", pos)
                p = line.find("%%", pos)
                if h == -1 and p == -1:
                    break
                if p == -1 or (h != -1 and h < p):
                    pos, state = h + 4, "html"
                else:
                    pos, state = p + 2, "pct"
    return mask


def scan_annotations(text: str,
                     registered: set[str]) -> tuple[list[dict], list[tuple]]:
    """`**MARKER**: payload` lines at column 0 of the note body - never in
    frontmatter, a fence, an HTML comment, or a line the heading parser claimed
    as a setext heading. Returns (annotations, candidates): registered markers
    with payload, first wikilink target and any leading ISO date, plus the
    (token, kind) near-misses for the stats candidate report."""
    _, body_start = parse_frontmatter(text)
    fmask = fence_mask(text)
    cmask = _comment_mask(text)
    heading_starts = {n.char for n in parse_headings(text)}
    anns: list[dict] = []
    cands: list[tuple] = []
    pos = 0
    for i, raw in enumerate(text.splitlines(keepends=True)):
        start, pos = pos, pos + len(raw)
        line = raw.rstrip("\r\n")
        if start < body_start or fmask[i] or cmask[i] or not line:
            continue
        m = MARKER_LINE_RE.match(line)
        if m:
            if start in heading_starts:
                continue
            token = m.group(1)
            if token not in registered:
                cands.append((token, "unregistered"))
                continue
            # Trailing whitespace goes - a CRLF remnant or a markdown
            # hard-break must not make the same annotation hash differently
            # on two machines.
            payload = (m.group(2) or "").rstrip()
            wl = WIKILINK_RE.search(payload)
            target = wl.group(2).split("|")[0].strip() if wl else ""
            adate = ""
            dm = MARKER_DATE_RE.match(payload)
            if dm:
                try:
                    date.fromisoformat(dm.group(0))
                    adate = dm.group(0)
                except ValueError:
                    pass
            anns.append({"line": i + 1, "char": start, "marker": token,
                         "payload": payload, "target": target, "date": adate})
            continue
        pm = MARKER_NEARMISS_RE.match(line)
        if pm:
            m2 = MARKER_LINE_RE.match(line[pm.end():])
            if m2:
                cands.append((m2.group(1), "placement"))
    return anns, cands


def extract_wikilinks(text: str) -> list[tuple[str, str, int]]:
    """Wikilink (target, kind, char_offset) triples in document order, from
    fence-stripped text. Target keeps its path fragment but drops
    `#heading`/`#^block` and `|alias` parts."""
    out = []
    for m in WIKILINK_RE.finditer(strip_code(text)):
        inner = m.group(2).split("|", 1)[0]
        target = inner.split("#", 1)[0].strip().rstrip("\\").strip()
        if not target or not _single_line(target):
            # `[^\[\]]+` matches newlines, so an unclosed bracket can swallow
            # paragraphs of prose into a "target" that is then printed verbatim
            # into the generated index and into stats. No real link spans lines.
            continue
        out.append((target, "embed" if m.group(1) else "link", m.start()))
    return out


def extract_md_links(text: str) -> list[tuple[str, int]]:
    """Standard markdown link (target, char_offset) pairs in document order,
    from fence-stripped text. Images, external schemes and bare fragments are
    skipped; `<...>` wrapping, `"title"` suffixes and fragments are stripped."""
    out = []
    for m in MD_LINK_RE.finditer(strip_code(text)):
        target = m.group(1).strip()
        if target.startswith("<") and ">" in target:
            target = target[1:target.index(">")]
        else:
            tm = re.match(r'^(.*?)\s+"[^"]*"$', target)  # trailing "title"
            if tm:
                target = tm.group(1)
        target = target.split("#", 1)[0].strip()
        if not target or not _single_line(target):
            continue
        if re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", target):
            continue
        out.append((target, m.start()))
    return out


def _single_line(target: str) -> bool:
    """A link target that carries a line break or a control character is not a
    link; it is prose that got swallowed by an unclosed bracket. Refusing it
    here is what keeps `stats` and the generated index from reproducing vault
    text as if the engine had written it.

    `splitlines()` rather than a list of characters, so this stands on its own:
    it catches all ten break codepoints including VT, FF and U+2028, instead of
    relying on `strip_code` having normalized them first. C0 and C1 controls go
    too - `stats` prints targets straight to a terminal, and an escape sequence
    in one rewrites what a human sees in the output.
    """
    if len(target.splitlines()) > 1:
        return False
    return not any(ord(c) < 0x20 or 0x7F <= ord(c) < 0xA0 for c in target)


def resolve_md_link(target: str, src_rel: str) -> str | None:
    """Resolve a markdown link target to a note id (vault-relative, no .md),
    or None if it is not a .md file inside the vault."""
    target = urllib.parse.unquote(target)
    if not target.lower().endswith(".md"):
        return None
    if target.startswith("/"):
        rel = posixpath.normpath(target.lstrip("/"))
    else:
        rel = posixpath.normpath(posixpath.join(posixpath.dirname(src_rel),
                                                target))
    if rel.startswith(".."):
        return None
    return rel[: -len(".md")]


def resolve_wikilink(target: str, ids: list[str], by_base: dict[str, list[str]],
                     by_alias: dict[str, list[str]]) -> tuple[str | None, str]:
    """Resolve a wikilink target the way Obsidian does. Returns (dst, status):
      * path fragment present -> unique case-insensitive path-suffix match,
        multiple matches AMBIGUOUS, none unresolved
      * bare name -> case-insensitive basename match; unique wins, collision
        is AMBIGUOUS (never guessed); no basename hit falls through to
        frontmatter aliases (same unique/ambiguous rule)
    """
    t = target.strip().strip("/")
    if t.lower().endswith(".md"):
        t = t[: -len(".md")]
    tl = t.lower()
    if "/" in tl:
        cands = sorted(i for i in ids
                       if i.lower() == tl or i.lower().endswith("/" + tl))
    else:
        cands = sorted(by_base.get(tl, []))
        if not cands:
            cands = sorted(by_alias.get(tl, []))
    if len(cands) == 1:
        return cands[0], "resolved"
    if len(cands) > 1:
        return None, "ambiguous"
    return None, "unresolved"


# ---------- dates: inferred, never a hardcoded format ----------
def date_shape(text: str) -> tuple[tuple, tuple] | None:
    """Decompose a string into a date shape without assuming any format.
    Returns ((kinds...), (values...)) where kind is 'y' (4-digit or >31),
    'm' (month name), or 'n' (an ambiguous 1-2 digit number), or None if the
    string has no date-looking run. The caller decides ordering, which is how
    the format is learned from the corpus rather than hardcoded."""
    # Whole digit runs, so a work-item id is one token rather than several. Splitting
    # `199512` into 1995 + 12 makes the first look like a year and the second a month.
    tokens = re.findall(r"\d+|[A-Za-z]{3,9}", text)
    kinds, values = [], []
    for tok in tokens:
        if tok.isdigit():
            n = int(tok)
            if len(tok) == 4 and 1000 <= n <= 9999:
                kinds.append("y")
            elif len(tok) <= 4 and 0 < n <= 31:
                kinds.append("n")
            else:
                # No date field looks like this: a work-item id, a row count, a zero.
                # It ends whatever run was accumulating and the scan continues, so a
                # heading that leads with an id still dates from its suffix.
                kinds, values = [], []
                continue
            values.append(n)
        else:
            month = MONTHS.get(tok.lower())
            if month is None:
                continue  # a stray word (weekday, label) is not part of the date
            kinds.append("m")
            values.append(month)
        # Stop at the FIRST complete date run. Scanning the whole string lets a number
        # after the date invalidate it: `2026-08-20-YY-STORY-654321` would otherwise
        # reset on 654321 after a valid date had already been read. A log whose headings
        # carry a work-item id then silently dates every section from its note-level
        # fallback instead of its own heading.
        if "y" in kinds and len(kinds) >= 3:
            return tuple(kinds), tuple(values)
    return None


def infer_order(shapes: list[tuple[tuple, tuple]]) -> tuple[str, ...] | None:
    """Learn the field order used across a set of headings. The dominant kind
    signature wins; where two numeric fields are ambiguous, any instance whose
    value exceeds 12 fixes which one is the day for the whole corpus."""
    from collections import Counter
    sig_counts = Counter(k for k, _ in shapes)
    if not sig_counts:
        return None
    sig, _ = sig_counts.most_common(1)[0]
    if sig.count("y") != 1:
        return None
    if "m" in sig:
        order = tuple("d" if k == "n" else k for k in sig)
        return order if order.count("d") == 1 else None
    if sig.count("n") != 2:
        return None
    slots = [i for i, k in enumerate(sig) if k == "n"]
    day_slot = None
    for kinds, values in shapes:
        if kinds != sig:
            continue
        for i in slots:
            if values[i] > 12:
                day_slot = i
                break
        if day_slot is not None:
            break
    if day_slot is None:
        # Nothing in the corpus disambiguates. Year-first reads Y-M-D and
        # year-last reads D-M-Y, which is what those two layouts conventionally
        # mean; this is recorded in config so it can be corrected.
        day_slot = slots[1] if sig[0] == "y" else slots[0]
    return tuple("d" if i == day_slot else ("m" if k == "n" else k)
                 for i, k in enumerate(sig))


def apply_order(shape: tuple[tuple, tuple], order: tuple[str, ...]) -> str:
    """Render a shape as an ISO date using a learned order, or '' if it does
    not fit that order."""
    kinds, values = shape
    if len(kinds) != len(order):
        return ""
    got = {}
    for k, o, v in zip(kinds, order, values):
        if k == "y" and o != "y":
            return ""
        if k == "m" and o != "m":
            return ""
        got[o] = v
    if not {"y", "m", "d"} <= set(got):
        return ""
    try:
        return date(got["y"], got["m"], got["d"]).isoformat()
    except ValueError:
        return ""


def order_label(order: tuple[str, ...]) -> str:
    return "-".join(order)


def parse_order(label: str) -> tuple[str, ...] | None:
    parts = tuple(p for p in label.split("-") if p)
    return parts if set(parts) == {"y", "m", "d"} else None


# ---------- headings and sections ----------
class Node:
    __slots__ = ("level", "heading", "line", "char", "body_char", "end_char",
                 "end_line", "children", "parent", "path")

    def __init__(self, level, heading, line, char, body_char):
        self.level = level
        self.heading = heading
        self.line = line            # 1-indexed line of the heading
        self.char = char            # char offset of the heading line
        self.body_char = body_char  # char offset just after the heading
        self.end_char = 0
        self.end_line = 0
        self.children: list[Node] = []
        self.parent: Node | None = None
        self.path: tuple[str, ...] = ()


def parse_headings(text: str) -> list[Node]:
    """Every ATX and setext heading, fence-aware, in document order. Headings
    inside fenced blocks are not headings, and neither is anything in the
    frontmatter block - its closing `---` otherwise reads as a setext
    underline and turns the last property into a heading."""
    _, body_start = parse_frontmatter(text)
    lines = text.splitlines(keepends=True)
    mask = fence_mask(text)
    offsets, pos = [], 0
    for ln in lines:
        offsets.append(pos)
        pos += len(ln)
    nodes: list[Node] = []
    for i, raw in enumerate(lines):
        if offsets[i] < body_start:
            continue
        if i < len(mask) and mask[i]:
            continue
        line = raw.rstrip("\n")
        m = ATX_RE.match(line)
        if m:
            nodes.append(Node(len(m.group(1)), _clip_heading(m.group(2)),
                              i + 1, offsets[i], offsets[i] + len(raw)))
            continue
        sm = SETEXT_RE.match(line)
        if sm and i > 0 and not (i - 1 < len(mask) and mask[i - 1]):
            prev = lines[i - 1].rstrip("\n").strip()
            if prev and not ATX_RE.match(prev) and not prev.startswith(">"):
                if nodes and nodes[-1].line == i:
                    continue
                level = 1 if sm.group(1)[0] == "=" else 2
                nodes.append(Node(level, _clip_heading(prev), i,
                                  offsets[i - 1], offsets[i] + len(raw)))
    return nodes


def _clip_heading(text: str) -> str:
    """Heading text goes into the heading path, and the heading path is half of
    a section id. A pathological heading - a whole paragraph on one line, or a
    file whose newlines were never decoded - would otherwise produce an id
    nobody can cite. Clip it and say so."""
    text = text.strip()
    return text if len(text) <= HEADING_MAX else text[:HEADING_MAX].rstrip() + "..."


def build_tree(text: str, nodes: list[Node]) -> None:
    """Close every node's span and attach it to the nearest shallower node.
    A heading stack of strictly lower levels keeps level skips from corrupting
    the path."""
    total = len(text)
    total_lines = len(text.splitlines())
    for i, node in enumerate(nodes):
        end = total
        end_line = total_lines
        for other in nodes[i + 1:]:
            if other.level <= node.level:
                end = other.char
                end_line = other.line - 1
                break
        node.end_char = end
        node.end_line = max(end_line, node.line)
    stack: list[Node] = []
    for node in nodes:
        while stack and stack[-1].level >= node.level:
            stack.pop()
        if stack:
            node.parent = stack[-1]
            stack[-1].children.append(node)
        node.path = tuple(n.heading for n in stack) + (node.heading,)
        stack.append(node)


def word_count(text: str) -> int:
    return len(WORD_RE.findall(text))


def section_id(note_id: str, heading_path: tuple[str, ...],
               seen: dict[str, int]) -> str:
    """Deterministic id: note id plus heading path plus an ordinal that only
    appears when the same path repeats. Never a rowid - citations and mentions
    must survive a re-ingest."""
    label = " > ".join(heading_path) if heading_path else "(top)"
    base = f"{note_id}#{label}"
    n = seen.get(base, 0)
    seen[base] = n + 1
    return base if n == 0 else f"{base}~{n}"


def split_prose(text: str, base_line: int, base_char: int) -> list[tuple]:
    """Break a run of structureless prose at scored break points. Thematic
    break 60, blank line 20, never inside a fenced block. Returns
    (char_start, char_end, line_start, line_end) tuples covering the text.
    Returns [] when no usable break point exists - the caller then keeps the
    unit whole and marks it oversize."""
    lines = text.splitlines(keepends=True)
    mask = fence_mask(text)
    offsets, pos = [], 0
    for ln in lines:
        offsets.append(pos)
        pos += len(ln)
    offsets.append(pos)

    scores = []
    for i, raw in enumerate(lines):
        if i < len(mask) and mask[i]:
            continue
        line = raw.strip()
        if THEMATIC_BREAK_RE.match(raw.rstrip("\n")):
            scores.append((i, 60))
        elif not line:
            scores.append((i, 20))
    if not scores:
        return []

    out = []
    start = 0
    # A break point only counts once a piece carries real content. Without the
    # half-ceiling clamp, a ceiling below the overlap makes every blank line a
    # candidate and the first cut lands right after the heading.
    step_floor = max(1, SIZE_CEILING - min(SIZE_OVERLAP, SIZE_CEILING // 2))
    while start < len(lines):
        acc, cut = 0, None
        best_score, best_at = -1, None
        for i in range(start, len(lines)):
            acc += word_count(lines[i])
            for at, sc in scores:
                if at == i and acc >= step_floor and sc > best_score:
                    best_score, best_at = sc, i
            if acc >= SIZE_CEILING and best_at is not None:
                cut = best_at
                break
        if cut is None or cut <= start:
            cut = len(lines) - 1
        end = cut + 1
        out.append((base_char + offsets[start], base_char + offsets[end],
                    base_line + start, base_line + end - 1))
        if end >= len(lines):
            break
        start = end
    return out if len(out) > 1 else []


def unit_level_for(profile: str, nodes: list[Node], row: dict,
                   learned: dict) -> int | None:
    """Which heading level is one profile unit, or None for whole-file units."""
    if profile == "freeform" or not nodes:
        return None
    if profile == "log-dated":
        lvl = learned.get("date_level")
        if lvl:
            return lvl
        src = str(row.get("date_from", "heading"))
        if src != "heading":
            return None
        return min(n.level for n in nodes)
    if profile == "dimension":
        group_by = str(row.get("group_by", "h2"))
        m = re.match(r"h(\d)", group_by)
        return int(m.group(1)) if m else 2
    return min(n.level for n in nodes)


def build_sections(note_id: str, text: str, row: dict, learned: dict) -> list[dict]:
    """Split one note into sections under its profile. Two levels are indexed:
    the profile's unit, plus every heading beneath it as a child."""
    profile = str(row.get("profile", "reference"))
    slots = row.get("slots") if isinstance(row.get("slots"), dict) else {}
    nodes = parse_headings(text)
    build_tree(text, nodes)
    unit_level = unit_level_for(profile, nodes, row, learned)
    order = learned.get("date_order")
    total_lines = len(text.splitlines()) or 1
    seen: dict[str, int] = {}
    out: list[dict] = []

    def declared_slot(path: tuple[str, ...]) -> str:
        for part in reversed(path):
            key = part.strip().lower()
            for name, value in slots.items():
                if str(name).strip().lower() == key and value in SLOTS:
                    return str(value)
        return ""

    def slot_for(path: tuple[str, ...]) -> str:
        # The marker wins over the note's profile: a superseded section inside an authored
        # note is history, whatever the note around it is.
        if any(SUPERSEDED_MARK in part.lower() for part in path):
            return "superseded"
        if any(part.lower().startswith(PREP_MARK) for part in path):
            return "prep"
        return declared_slot(path) or ("generated" if profile == "generated"
                                       else "authored")

    def add(path, level, char_start, char_end, line_start, line_end,
            is_unit, parent_id, doc_date="", oversize=0, heading=""):
        body = text[char_start:char_end]
        words = word_count(body)
        sid = section_id(note_id, path, seen)
        out.append({
            "id": sid, "note_id": note_id, "parent_id": parent_id,
            "heading": heading, "heading_path": " > ".join(path),
            "level": level, "ord": len(out),
            "char_start": char_start, "char_end": char_end,
            "line_start": line_start, "line_end": line_end,
            "body": body, "doc_date": doc_date, "slot": slot_for(path),
            "words": words, "is_unit": 1 if is_unit else 0,
            "oversize": oversize,
            "section_hash": hashlib.sha256(body.encode()).hexdigest()[:16],
        })
        return sid

    # Text between the frontmatter and the first heading is its own unit when
    # it carries content.
    _, body_start = parse_frontmatter(text)
    body_line = text.count("\n", 0, body_start) + 1
    first_char = nodes[0].char if nodes else len(text)
    first_line = nodes[0].line - 1 if nodes else total_lines
    if word_count(text[body_start:first_char]) >= WORD_FLOOR or not nodes:
        add((), 0, body_start, first_char, body_line, max(first_line, body_line),
            True, "")

    if not nodes:
        _split_if_oversize(out, out[-1] if out else None, text, note_id, seen)
        _finish_sections(out, text)
        return out

    unit_ids: dict[int, str] = {}  # id(Node) -> section id of its unit
    for node in nodes:
        is_unit = unit_level is not None and node.level == unit_level
        if unit_level is not None and node.level < unit_level:
            # An ancestor of units: index only its own lead text, so nothing is
            # duplicated and its introduction is still retrievable.
            lead_end = node.children[0].char if node.children else node.end_char
            if word_count(text[node.char:lead_end]) >= WORD_FLOOR:
                lead_line = (node.children[0].line - 1 if node.children
                             else node.end_line)
                add(node.path, node.level, node.char, lead_end, node.line,
                    max(lead_line, node.line), False, "", heading=node.heading)
            continue
        doc_date = ""
        if is_unit and profile == "log-dated" and order:
            shape = date_shape(node.heading)
            if shape:
                doc_date = apply_order(shape, order)
        parent_id = ""
        anc = node.parent
        while anc is not None:
            if id(anc) in unit_ids:
                parent_id = unit_ids[id(anc)]
                break
            anc = anc.parent
        body_words = word_count(text[node.char:node.end_char])
        if not is_unit and body_words < WORD_FLOOR and not declared_slot(node.path):
            # rolls up into its parent, whose body already contains it. A
            # declared slot never rolls up: swallowing a short `generated` or
            # `instrument` section is exactly how its words get counted as the
            # author's own.
            continue
        sid = add(node.path, node.level, node.char, node.end_char, node.line,
                  node.end_line, is_unit, parent_id, doc_date,
                  heading=node.heading)
        if is_unit:
            unit_ids[id(node)] = sid
            if body_words > SIZE_CEILING and not node.children:
                _split_if_oversize(out, out[-1], text, note_id, seen)
            elif body_words > SIZE_CEILING:
                out[-1]["oversize"] = 1  # represented by its children
    if profile == "dimension":
        _add_members(out, text, row)
    _finish_sections(out, text)
    return out


def build_list_sections(note_id: str, text: str, row: dict) -> list[dict]:
    """The `list` profile: one unit per list item, so a roster or a link list
    is addressable row by row instead of as one undifferentiated note."""
    lines = text.splitlines(keepends=True)
    mask = fence_mask(text)
    _, body_start = parse_frontmatter(text)
    offsets, pos = [], 0
    for ln in lines:
        offsets.append(pos)
        pos += len(ln)
    offsets.append(pos)
    seen: dict[str, int] = {}
    out: list[dict] = []
    heading_path: tuple[str, ...] = ()
    for i, raw in enumerate(lines):
        if offsets[i] < body_start or (i < len(mask) and mask[i]):
            continue
        atx = ATX_RE.match(raw.rstrip("\n"))
        if atx:
            heading_path = (atx.group(2).strip(),)
            continue
        m = LIST_ITEM_RE.match(raw.rstrip("\n"))
        if not m:
            continue
        name = re.sub(r"[*_`\[\]]", "", m.group(1)).strip()
        path = heading_path + (name[:60],)
        body = raw
        out.append({
            "id": section_id(note_id, path, seen), "note_id": note_id,
            "parent_id": "", "heading": name,
            "heading_path": " > ".join(path), "level": 0, "ord": len(out),
            "char_start": offsets[i], "char_end": offsets[i + 1],
            "line_start": i + 1, "line_end": i + 1, "body": body,
            "doc_date": "", "slot": "authored", "words": word_count(body),
            "is_unit": 1, "oversize": 0,
            "section_hash": hashlib.sha256(body.encode()).hexdigest()[:16],
        })
    if not out:
        return build_sections(note_id, text, {**row, "profile": "reference"},
                              {})
    _finish_sections(out, text)
    return out


def _finish_sections(out: list[dict], text: str) -> None:
    """Two passes every section needs before it is stored. A child inherits its
    unit's date, so a window query reaches the slots inside a dated entry. And
    every section gets an `own_body` - its text minus the sections nested inside
    it - so an aggregate can count each word exactly once and a `generated` or
    `instrument` slot can actually be excluded rather than merely labelled."""
    by_id = {s["id"]: s for s in out}
    for sec in out:
        if not sec["doc_date"] and sec["parent_id"]:
            parent = by_id.get(sec["parent_id"])
            if parent:
                sec["doc_date"] = parent["doc_date"]
    for sec in out:
        keep = [True] * (sec["char_end"] - sec["char_start"])
        for other in out:
            if other is sec:
                continue
            if (other["char_start"] >= sec["char_start"]
                    and other["char_end"] <= sec["char_end"]
                    and (other["char_end"] - other["char_start"])
                    < (sec["char_end"] - sec["char_start"])):
                for i in range(other["char_start"] - sec["char_start"],
                               other["char_end"] - sec["char_start"]):
                    keep[i] = False
        body = sec["body"]
        sec["own_body"] = "".join(c for c, k in zip(body, keep) if k)
        sec["own_words"] = word_count(sec["own_body"])


def _split_if_oversize(out: list[dict], unit: dict | None, text: str,
                       note_id: str, seen: dict) -> None:
    """A unit with no child headings and no room left: split its prose at
    scored break points, or leave it whole and mark it oversize. The unit row
    itself is never truncated."""
    if unit is None or unit["words"] <= SIZE_CEILING:
        return
    pieces = split_prose(unit["body"], unit["line_start"], unit["char_start"])
    if not pieces:
        unit["oversize"] = 1
        return
    unit["oversize"] = 1
    path = tuple(p for p in unit["heading_path"].split(" > ") if p)
    for n, (cs, ce, ls, le) in enumerate(pieces, 1):
        body = text[cs:ce]
        sid = section_id(note_id, path + (f"part {n}",), seen)
        out.append({
            "id": sid, "note_id": note_id, "parent_id": unit["id"],
            "heading": f"part {n}",
            "heading_path": " > ".join(path + (f"part {n}",)),
            "level": unit["level"] + 1, "ord": len(out),
            "char_start": cs, "char_end": ce,
            "line_start": ls, "line_end": le,
            "body": body, "doc_date": unit["doc_date"], "slot": unit["slot"],
            "words": word_count(body), "is_unit": 0, "oversize": 0,
            "section_hash": hashlib.sha256(body.encode()).hexdigest()[:16],
        })


def _add_members(sections: list[dict], text: str, row: dict) -> None:
    """Dimension profile: each list item under a group heading is a member."""
    grain = str(row.get("grain", "list-item"))
    if grain != "list-item":
        return
    for sec in sections:
        if not sec["is_unit"]:
            continue
        members = []
        for line in sec["body"].splitlines():
            m = LIST_ITEM_RE.match(line)
            if m:
                name = re.sub(r"[*_`\[\]]", "", m.group(1)).strip()
                # `Name - description` and `Name: description` are both common;
                # the member is the part before the separator.
                name = re.split(r"\s+[-–]\s+|:\s+", name, maxsplit=1)[0].strip()
                if name:
                    members.append(name)
        sec["members"] = members


# ---------- vault walking (git parity, dot folders excluded) ----------
def scan_vault(vault: Path) -> tuple[list[Path], list[str]]:
    """All vault .md files, sorted for determinism, plus the paths that were
    refused for pointing outside the vault. In a git repo, enumerate
    via `git ls-files --cached --others --exclude-standard`; otherwise a
    skip-folder os.walk. Dot folders/files, SKIP_FOLDERS and the engine's own
    vault-kg/ folder are always excluded."""
    files: list[Path] | None = None
    try:
        # `-c core.fsmonitor=` because a vault is untrusted content: a repo
        # whose .git/config sets fsmonitor would otherwise run that command
        # here. ls-files itself runs no hooks. No shell, fixed argv.
        out = subprocess.run(
            ["git", "-c", "core.fsmonitor=", "--no-optional-locks",
             "-C", str(vault), "ls-files", "-z",
             "--cached", "--others", "--exclude-standard"],
            capture_output=True, text=True, timeout=30)
        if out.returncode == 0:
            files = [vault / ln for ln in out.stdout.split("\0")
                     if ln.endswith(".md")]
    except Exception:
        files = None
    # A vault can be deliberately gitignored, and then `git ls-files` returns
    # nothing and the ingest reads as a clean zero-note success. Falling back to
    # the walk whenever git yields no notes makes that impossible to mistake.
    if not files:
        files = None
    if files is None:
        files = []
        for root, dirs, names in os.walk(vault):
            dirs[:] = [d for d in dirs
                       if d not in SKIP_FOLDERS and not d.startswith(".")
                       and not (Path(root) == vault and d == KG_DIR)]
            files.extend(Path(root) / n for n in names if n.endswith(".md"))
    result = []
    escapes = []
    for p in files:
        # A vault is untrusted content. `is_file()` follows symlinks, so a link
        # named *.md pointing at ~/.ssh/id_rsa or a .env would otherwise be
        # ingested, stored, indexed and handed back by `search` - reading a
        # secret into the agent's context without any file-read ever being
        # issued for it. Confine to what genuinely lives inside the vault.
        if p.is_symlink():
            escapes.append(p)
            continue
        if not p.is_file():
            continue
        try:
            rel = p.relative_to(vault)
        except ValueError:
            continue
        if any(part.startswith(".") for part in rel.parts):
            continue
        if any(part in SKIP_FOLDERS for part in rel.parts):
            continue
        if rel.parts and rel.parts[0] == KG_DIR:
            continue
        try:
            if not p.resolve().is_relative_to(vault.resolve()):
                escapes.append(p)
                continue
        except (OSError, RuntimeError):
            escapes.append(p)   # broken or cyclic link
            continue
        result.append(p)
    return sorted(set(result)), sorted(
        {p.relative_to(vault).as_posix() for p in escapes
         if _under(p, vault)})


def walk_vault(vault: Path) -> list[Path]:
    return scan_vault(vault)[0]


def _under(p: Path, vault: Path) -> bool:
    try:
        p.relative_to(vault)
        return True
    except ValueError:
        return False


def manifest(vault: Path) -> str:
    """Cheap fingerprint of the vault's file set: path, size, mtime. Read
    commands compare it to detect drift and re-ingest without being asked."""
    parts = []
    for p in walk_vault(vault):
        st = p.stat()
        parts.append(f"{p.relative_to(vault).as_posix()}|{st.st_size}|"
                     f"{int(st.st_mtime_ns)}")
    cfg = config_path(vault)
    if cfg.exists():
        parts.append(f"__config__|{cfg.stat().st_size}|"
                     f"{int(cfg.stat().st_mtime_ns)}")
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


# ---------- ingest (idempotent full rebuild) ----------
def learn_note(text: str, row: dict) -> dict:
    """Per-note learned facts a profile needs: which heading level carries the
    dates, and the field order those dates use. Learned from the note itself,
    never from a hardcoded format list."""
    learned: dict = {}
    if str(row.get("profile", "")) != "log-dated":
        return learned
    nodes = parse_headings(text)
    if not nodes:
        return learned
    by_level: dict[int, list] = {}
    for node in nodes:
        by_level.setdefault(node.level, []).append(node)
    best_level, best_hits = None, 0
    for level in sorted(by_level):
        shapes = [date_shape(n.heading) for n in by_level[level]]
        hits = [s for s in shapes if s]
        if len(by_level[level]) >= 2 and len(hits) >= 0.6 * len(by_level[level]):
            if len(hits) > best_hits:
                best_level, best_hits = level, len(hits)
    if best_level is None:
        return learned
    shapes = [s for s in (date_shape(n.heading) for n in by_level[best_level])
              if s]
    declared = parse_order(str(row.get("date_order", "")))
    order = declared or infer_order(shapes)
    if order is None:
        return learned
    learned["date_level"] = best_level
    learned["date_order"] = order
    return learned


def ingest(vault: Path, keep_previous: bool = False) -> dict:
    checkpoint = None
    if keep_previous:
        # Copy before connect(): connect runs the schema script, and the
        # checkpoint must be the db exactly as the last ingest left it.
        live = db_path(vault)
        if live.exists():
            prev = prev_db_path(vault)
            # Copy to a sibling temp and replace: a synced or cloned vault can
            # carry a planted symlink or hardlink at the checkpoint name, and a
            # direct copy2 would write through it to a target the planter
            # chose. os.replace swaps the name itself, atomically, so the
            # plant is discarded and a crash never leaves a half checkpoint.
            tmp = prev.with_name(prev.name + ".tmp")
            shutil.copy2(live, tmp)
            os.replace(tmp, prev)
            checkpoint = str(prev)
    con = connect(vault)
    cfg = load_config(vault)
    kgignore = load_kgignore(vault)
    report = {"notes": 0, "sections": 0, "resolved": 0, "unresolved": 0,
              "ambiguous": 0, "ignored_files": 0, "ignored_links": 0,
              "skipped_assets": 0, "entities": 0, "mentions": 0,
              "annotations": 0, "bad_profiles": []}
    registered_markers = set(CORE_MARKERS) | {
        str(r.get("marker", "")) for r in cfg.get("markers", [])}
    cand_counts: dict[tuple, int] = {}

    parsed: dict[str, dict] = {}
    ignored: list[tuple[str, str]] = []
    files, escaped = scan_vault(vault)
    for rel in escaped:
        ignored.append((rel, "symlink or path outside the vault"))
    for f in files:
        rel = f.relative_to(vault).as_posix()
        text = f.read_text(encoding="utf-8", errors="replace")
        meta, _ = parse_frontmatter(text)
        rule = ignore_rule(rel, meta, cfg, kgignore)
        if rule:
            ignored.append((rel, rule))
            continue
        if str(meta.get("auto-generated", "")).strip().lower() == "true":
            ignored.append((rel, "auto-generated index"))
            continue
        row = profile_for(rel[: -len(".md")], rel, meta, cfg)
        parsed[rel[: -len(".md")]] = {"rel": rel, "text": text, "meta": meta,
                                      "row": row}
    report["ignored_files"] = len(ignored)

    ids = sorted(parsed)
    ignored_ids = {r[: -len(".md")] for r, _ in ignored}
    by_base: dict[str, list[str]] = {}
    by_alias: dict[str, list[str]] = {}
    for nid in ids:
        by_base.setdefault(nid.rsplit("/", 1)[-1].lower(), []).append(nid)
        for alias in _listify(parsed[nid]["meta"].get("aliases", [])):
            by_alias.setdefault(alias.lower(), []).append(nid)

    for table in ("notes", "properties", "tags", "aliases", "edges", "sections",
                  "members", "entities", "entity_aliases", "mentions",
                  "ignored", "annotations", "annotation_candidates", "meta"):
        con.execute(f"DELETE FROM {table}")
    con.execute("INSERT INTO sections_fts(sections_fts) VALUES ('delete-all')")

    for rel, rule in sorted(ignored):
        con.execute("INSERT INTO ignored(path, rule) VALUES (?,?)", (rel, rule))

    all_sections: list[dict] = []
    for nid in ids:
        doc = parsed[nid]
        meta, text, row = doc["meta"], doc["text"], doc["row"]
        heading = next((n.heading for n in parse_headings(text) if n.level == 1),
                       None)
        title = str(meta.get("title") or heading or nid.rsplit("/", 1)[-1])
        tag_list = _listify(meta.get("tags", []))
        alias_list = _listify(meta.get("aliases", []))
        profile = str(row.get("profile", "reference"))
        if profile not in PROFILES:
            # A typo in a config profile name is invisible otherwise: the note
            # indexes fine as `reference` and the row looks like it is working.
            report["bad_profiles"].append(f"{doc['rel']}: {profile!r}")
            profile = "reference"
        try:
            weight = float(row.get("weight", 1.0))
        except (TypeError, ValueError):
            weight = 1.0
        if not math.isfinite(weight):
            weight = 1.0
        weight = min(max(weight, 0.0), 10.0)
        if profile == "generated" and "weight" not in row:
            weight = 0.2
        note_date = ""
        for key in ("date", "created", "date-created", "timestamp"):
            if meta.get(key):
                shape = date_shape(str(meta[key]))
                if shape:
                    order = infer_order([shape])
                    if order:
                        note_date = apply_order(shape, order)
                if note_date:
                    break
        con.execute(
            "INSERT INTO notes(id, path, title, tags, aliases, content_hash,"
            " body, profile, weight, doc_date, status)"
            " VALUES (?,?,?,?,?,?,?,?,?,?, 'hot')",
            (nid, doc["rel"], title, ", ".join(tag_list), ", ".join(alias_list),
             hashlib.sha256(text.encode()).hexdigest(), text, profile, weight,
             note_date))
        report["notes"] += 1
        for tag in sorted(set(tag_list)):
            con.execute("INSERT INTO tags(note_id, tag) VALUES (?,?)",
                        (nid, tag))
        for alias in sorted(set(alias_list)):
            con.execute("INSERT INTO aliases(note_id, alias) VALUES (?,?)",
                        (nid, alias))
        for key in sorted(meta):
            val = meta[key]
            if key in ("tags", "aliases"):
                continue
            if isinstance(val, list):
                val = ", ".join(str(v) for v in val)
            elif isinstance(val, dict):
                val = ", ".join(f"{k}={v}" for k, v in sorted(val.items()))
            con.execute(
                "INSERT INTO properties(note_id, key, value) VALUES (?,?,?)",
                (nid, key, str(val)))

        learned = learn_note(text, row)
        if learned.get("date_order"):
            con.execute(
                "INSERT OR REPLACE INTO properties(note_id, key, value)"
                " VALUES (?,?,?)",
                (nid, "kg-date-order", order_label(learned["date_order"])))
        if profile == "list":
            sections = build_list_sections(nid, text, row)
        else:
            sections = build_sections(nid, text, {**row, "profile": profile},
                                      learned)
        anns, cands = scan_annotations(text, registered_markers)
        for tok_kind in cands:
            # Bounded: counts keep accumulating for known tokens, but past
            # 1000 distinct tokens no new rows are minted - a hostile corpus
            # gets a full-size db table out of gibberish otherwise.
            # Deterministic because notes are processed in sorted order.
            if tok_kind in cand_counts or len(cand_counts) < 1000:
                cand_counts[tok_kind] = cand_counts.get(tok_kind, 0) + 1
        by_sid = {s["id"]: s for s in sections}
        for ann in anns:
            ann["section_id"] = _section_at(sections, ann["char"])
            # `**SUPERSEDED**:` is a second spelling of the fact the
            # `(superseded` heading mark already states: it sets the enclosing
            # section's slot, taking the same precedence over profile- and
            # config-declared slots, and the existing weight and query paths do
            # the rest. When both spellings mark one section the slot is set
            # twice to the same value, so the discount applies exactly once.
            if ann["marker"] == "SUPERSEDED" and ann["section_id"]:
                by_sid[ann["section_id"]]["slot"] = "superseded"
        for sec in sections:
            # Prep describes the future, so inheriting the note's date would either date it
            # wrongly or drop it to the oldest recency tier. It stays undated and full
            # weight: current, findable, and never competing with the record.
            if not sec["doc_date"] and note_date and sec["slot"] != "prep":
                sec["doc_date"] = note_date
        # Recency tiers, computed per note once every section's date is settled.
        tiers = recency_weights([s["doc_date"] for s in sections])
        for sec in sections:
            w = 1.0 if sec["slot"] == "prep" else tiers.get(sec["doc_date"], 1.0)
            if sec["slot"] == "superseded":
                w *= SUPERSEDED_WEIGHT
            con.execute(
                "INSERT INTO sections(id, note_id, parent_id, heading,"
                " heading_path, level, ord, char_start, char_end, line_start,"
                " line_end, body, own_body, doc_date, slot, weight, words,"
                " is_unit, oversize, section_hash)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (sec["id"], sec["note_id"], sec["parent_id"], sec["heading"],
                 sec["heading_path"], sec["level"], sec["ord"],
                 sec["char_start"], sec["char_end"], sec["line_start"],
                 sec["line_end"], sec["body"], sec["own_body"],
                 sec["doc_date"], sec["slot"], w, sec["words"], sec["is_unit"],
                 sec["oversize"], sec["section_hash"]))
            for i, name in enumerate(sec.get("members", [])):
                con.execute(
                    "INSERT OR IGNORE INTO members(section_id, note_id,"
                    " group_name, name, ord) VALUES (?,?,?,?,?)",
                    (sec["id"], nid, sec["heading"], name, i))
        for ann in anns:
            con.execute(
                "INSERT INTO annotations(note_id, section_id, line, marker,"
                " payload, target, date) VALUES (?,?,?,?,?,?,?)",
                (nid, ann["section_id"], ann["line"], ann["marker"],
                 ann["payload"], ann["target"], ann["date"]))
        report["annotations"] += len(anns)
        report["sections"] += len(sections)
        all_sections.extend(sections)
        doc["sections"] = sections

    # edges, once every note id is known, so collision detection stays global
    for nid in ids:
        doc = parsed[nid]
        text, sections = doc["text"], doc["sections"]
        rows: list[tuple] = []
        for target, kind, off in extract_wikilinks(text):
            base = target.rsplit("/", 1)[-1]
            ext = base.rsplit(".", 1)[-1].lower() if "." in base else ""
            if ext in ASSET_EXTS:
                report["skipped_assets"] += 1
                continue
            dst, status = resolve_wikilink(target, ids, by_base, by_alias)
            if status == "unresolved":
                probe, _ = resolve_wikilink(target, sorted(ignored_ids),
                                            _index_by_base(ignored_ids),
                                            {})
                if probe is not None:
                    status = "ignored"
            rows.append((nid, dst, target, "wiki", kind, status,
                         _section_at(sections, off)))
        for target, off in extract_md_links(text):
            dst = resolve_md_link(target, doc["rel"])
            if dst is None:
                report["skipped_assets"] += 1
                continue
            if dst in parsed:
                status = "resolved"
            elif dst in ignored_ids:
                status, dst = "ignored", None
            else:
                status, dst = "unresolved", None
            rows.append((nid, dst, urllib.parse.unquote(target), "md", "link",
                         status, _section_at(sections, off)))
        for row_ in rows:
            cur = con.execute(
                "INSERT OR IGNORE INTO edges(src, dst, target, syntax, kind,"
                " status, section_id) VALUES (?,?,?,?,?,?,?)", row_)
            if cur.rowcount:
                key = ("ignored_links" if row_[5] == "ignored" else row_[5])
                if key in report:
                    report[key] += 1

    for (token, kind), n in sorted(cand_counts.items()):
        con.execute(
            "INSERT INTO annotation_candidates(token, kind, count)"
            " VALUES (?,?,?)", (token, kind, n))

    ent_report = load_entities(con, cfg, all_sections)
    report.update(ent_report)

    con.execute("INSERT INTO sections_fts(sections_fts) VALUES ('rebuild')")
    con.execute("INSERT INTO meta(key, value) VALUES ('ingested_at', ?)",
                (now_utc(),))
    con.commit()
    con.execute("INSERT INTO meta(key, value) VALUES ('manifest', ?)",
                (manifest(vault),))
    reconcile_extractions(con)
    con.commit()
    con.close()
    if keep_previous:
        report["checkpoint"] = checkpoint
    return report


def _index_by_base(ids) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for nid in ids:
        out.setdefault(nid.rsplit("/", 1)[-1].lower(), []).append(nid)
    return out


def _section_at(sections: list[dict], offset: int) -> str:
    """The smallest indexed section containing a character offset."""
    best, best_size = "", None
    for sec in sections:
        if sec["char_start"] <= offset < sec["char_end"]:
            size = sec["char_end"] - sec["char_start"]
            if best_size is None or size < best_size:
                best, best_size = sec["id"], size
    return best


def reconcile_extractions(con: sqlite3.Connection) -> None:
    """Judgment tables survive a rebuild. An extraction whose section no longer
    exists goes cold with its provenance intact; one whose section came back
    with the same hash goes hot again. Nothing is deleted."""
    live = {r[0]: r[1] for r in con.execute(
        "SELECT id, section_hash FROM sections")}
    # 'retired' is sticky: it records a human/agent judgment that the row was
    # wrong, and a section coming back must not resurrect it.
    for eid, sid, shash in con.execute(
            "SELECT id, section_id, section_hash FROM extractions"
            " WHERE status != 'retired'").fetchall():
        status = "hot" if live.get(sid) == shash else "cold"
        con.execute("UPDATE extractions SET status=? WHERE id=?", (status, eid))
    con.execute("UPDATE conflicts SET state='cold' WHERE a_extraction IN"
                " (SELECT id FROM extractions WHERE status='cold')"
                " OR b_extraction IN"
                " (SELECT id FROM extractions WHERE status='cold')")


# ---------- registry ----------
def alias_pattern(alias: str) -> re.Pattern:
    """Case-insensitive, word-boundary, tolerating a possessive or plural."""
    return re.compile(r"(?<![\w])" + re.escape(alias) + r"(?:'s|’s|s|es)?(?![\w])",
                      re.IGNORECASE)


def load_entities(con: sqlite3.Connection, cfg: dict,
                  sections: list[dict]) -> dict:
    """Gazetteer matching from config. Longest alias wins; matches inside code
    fences do not count. Derived from a file, so it is wiped and rebuilt."""
    rows = [r for r in cfg.get("entities", []) if isinstance(r, dict)
            and str(r.get("canonical", "")).strip()]
    seen_alias: dict[str, str] = {}
    pairs: list[tuple[str, str]] = []
    for row in sorted(rows, key=lambda r: str(r.get("canonical"))):
        canonical = str(row["canonical"]).strip()
        time = str(row.get("time", "") or "static").strip()
        t_start = t_end = ""
        if ".." in time:
            a, b = time.split("..", 1)
            t_start, t_end = a.strip(), b.strip()
            time = "bounded"
        elif time not in ("static", "evolving"):
            time = "static"
        con.execute(
            "INSERT OR REPLACE INTO entities(canonical, type, time, note,"
            " t_start, t_end) VALUES (?,?,?,?,?,?)",
            (canonical, str(row.get("type", "")), time,
             str(row.get("note", "")), t_start, t_end))
        names = [canonical] + [str(a).strip() for a in
                               (row.get("aliases") or []) if str(a).strip()]
        for name in names:
            key = name.lower()
            if key in seen_alias and seen_alias[key] != canonical:
                sys.exit(f"error: alias {name!r} is claimed by both "
                         f"{seen_alias[key]!r} and {canonical!r}")
            seen_alias[key] = canonical
            con.execute(
                "INSERT OR IGNORE INTO entity_aliases(canonical, alias)"
                " VALUES (?,?)", (canonical, name))
            pairs.append((name, canonical))

    # longest alias first, so a longer name is never eaten by a shorter one
    pairs.sort(key=lambda p: (-len(p[0]), p[0]))
    compiled = [(alias_pattern(name), canonical) for name, canonical in pairs]
    mentions = 0
    for sec in sections:
        # own_body, so a name inside a child section is counted against that
        # child and not a second time against the unit that contains it
        text = strip_code(sec["own_body"])
        claimed = [False] * len(text)
        counts: dict[str, int] = {}
        for pattern, canonical in compiled:
            for m in pattern.finditer(text):
                if any(claimed[m.start():m.end()]):
                    continue
                for i in range(m.start(), m.end()):
                    claimed[i] = True
                counts[canonical] = counts.get(canonical, 0) + 1
        for canonical in sorted(counts):
            con.execute(
                "INSERT OR REPLACE INTO mentions(canonical, section_id,"
                " note_id, doc_date, count) VALUES (?,?,?,?,?)",
                (canonical, sec["id"], sec["note_id"], sec["doc_date"],
                 counts[canonical]))
            mentions += 1
    return {"entities": len(rows), "mentions": mentions}


# ---------- staleness ----------
def ensure_fresh(vault: Path) -> None:
    """Every read command re-ingests on drift. A skill whose correctness
    depends on the user remembering a step is wrong on the day it matters."""
    db = db_path(vault)
    if not db.exists():
        sys.exit(f"error: no database at {db} - run `ingest` on this vault first")
    con = sqlite3.connect(db)
    con.executescript(SCHEMA)
    row = con.execute("SELECT value FROM meta WHERE key='manifest'").fetchone()
    con.close()
    if row is None or row[0] != manifest(vault):
        ingest(vault)


def open_fresh(vault: Path) -> sqlite3.Connection:
    ensure_fresh(vault)
    return connect(vault, must_exist=True)


# ---------- note / section access ----------
def resolve_note_arg(con: sqlite3.Connection, name: str) -> str:
    """Resolve a CLI note argument to a note id: exact id/path, then
    case-insensitive path suffix or basename, then frontmatter alias."""
    n = name.strip().strip("/")
    if n.lower().endswith(".md"):
        n = n[: -len(".md")]
    ids = [r[0] for r in con.execute("SELECT id FROM notes ORDER BY id")]
    if n in ids:
        return n
    nl = n.lower()
    cands = sorted(i for i in ids
                   if i.lower() == nl or i.lower().endswith("/" + nl))
    if not cands:
        cands = sorted(r[0] for r in con.execute(
            "SELECT note_id FROM aliases WHERE lower(alias) = ?", (nl,)))
    if len(cands) == 1:
        return cands[0]
    con.close()
    if cands:
        sys.exit(f"error: ambiguous note {name!r} - candidates: "
                 + ", ".join(cands))
    sys.exit(f"error: unknown note {name!r} (find notes with `search`)")


def emit(args: argparse.Namespace, payload, render) -> int:
    """Every command speaks json on demand and prose otherwise. The prose path
    runs behind a sanitizing stdout so no renderer - present or future - can
    pass a control sequence from vault text to the terminal. The json path
    relies on json.dumps, which escapes C0 controls but (with ensure_ascii
    False) passes C1 through: machine-read output, not terminal output - pipe
    it to a parser, not to a screen."""
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
        return 0
    real = sys.stdout

    class _SafeOut:
        def write(self, s):
            return real.write(_term_safe(s))

        def flush(self):
            return real.flush()

    sys.stdout = _SafeOut()
    try:
        return render(payload)
    finally:
        sys.stdout = real


# ---------- search ----------
def tokenize(question: str) -> tuple[list[str], list[str]]:
    """Split a natural-language question into (phrases, terms). Quoted spans
    stay whole; stopwords are dropped from the loose terms."""
    phrases = re.findall(r'"([^"]+)"', question)
    rest = re.sub(r'"[^"]*"', " ", question)
    terms = [t.lower() for t in WORD_RE.findall(rest)]
    terms = [t for t in terms if t not in STOPWORDS and len(t) > 1]
    seen, out = set(), []
    for t in terms:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return phrases, out


def fts_escape(term: str) -> str:
    return '"' + term.replace('"', '""') + '"'


def search_rungs(phrases: list[str], terms: list[str]) -> list[tuple[str, str]]:
    """The ladder: exact phrase, then all-terms AND, then OR. The first rung
    that returns hits wins - a lower rung never dilutes a higher one."""
    rungs = []
    if phrases:
        rungs.append(("phrase", " AND ".join(fts_escape(p) for p in phrases)))
    if phrases and terms:
        rungs.append(("phrase+terms",
                      " AND ".join(fts_escape(p) for p in phrases + terms)))
    if terms:
        rungs.append(("all-terms", " AND ".join(fts_escape(t) for t in terms)))
        if len(terms) > 1:
            rungs.append(("any-term", " OR ".join(fts_escape(t) for t in terms)))
    return rungs


def _hub_notes(con: sqlite3.Connection) -> set[str]:
    return {r[0] for r in con.execute(
        "SELECT id FROM notes WHERE profile='hub'")}


def _degree(con: sqlite3.Connection, skip_hubs: bool = False) -> dict[str, int]:
    """Link degree per note. An index note links to everything, so counting its
    edges as a relevance prior would lift every note it happens to list; a
    `hub` profile takes it out of that signal."""
    hubs = _hub_notes(con) if skip_hubs else set()
    deg: dict[str, int] = {}
    for src, dst in con.execute(
            "SELECT src, dst FROM edges WHERE status='resolved'"):
        if src in hubs or dst in hubs:
            continue
        deg[src] = deg.get(src, 0) + 1
        deg[dst] = deg.get(dst, 0) + 1
    return deg


def note_tiers(con: sqlite3.Connection,
               note_ids: set[str]) -> dict[str, dict[str, float]]:
    """Recency tiers per note, recomputed from every dated section the note
    holds - the same input ingest used, so the tier is a property of the note
    and not of whichever sections a query happened to hit."""
    out: dict[str, dict[str, float]] = {}
    if not note_ids:
        return out
    marks = ",".join("?" * len(note_ids))
    dates: dict[str, list[str]] = {}
    for nid, ddate in con.execute(
            "SELECT DISTINCT note_id, doc_date FROM sections"
            f" WHERE note_id IN ({marks}) AND doc_date != ''",
            tuple(sorted(note_ids))):
        dates.setdefault(nid, []).append(ddate)
    for nid in note_ids:
        out[nid] = recency_weights(dates.get(nid, []))
    return out


def section_tier(tiers: dict[str, dict[str, float]], note_id: str,
                 doc_date: str, slot: str) -> float:
    """The rule ingest applies when it stores `sections.weight`: prep is pinned
    at 1.0, undated sections take 1.0, dated ones take their note's tier."""
    if slot == "prep":
        return 1.0
    return tiers.get(note_id, {}).get(doc_date, 1.0)


def search(vault: Path, question: str, limit: int = 10,
           per_note: int = 3, budget: int | None = None,
           slot: str | None = None, recency_k: float | None = None) -> dict:
    con = open_fresh(vault)
    if recency_k is None:
        recency_k = load_config(vault).get("recency_k", RECENCY_K)
    phrases, terms = tokenize(question)
    if not phrases and not terms:
        con.close()
        return {"query": question, "rung": None, "status": "COMPLETE",
                "total": 0, "results": []}
    deg = _degree(con, skip_hubs=True)
    max_deg = max(deg.values()) if deg else 1
    rows: list[sqlite3.Row] = []
    used_rung = None
    for name, expr in search_rungs(phrases, terms):
        try:
            rows = con.execute(
                "SELECT s.id, s.note_id, s.heading_path, s.doc_date, s.slot,"
                " s.line_start, s.line_end, s.words, s.is_unit, s.oversize,"
                " n.title, n.weight, n.path,"
                " bm25(sections_fts) AS rank,"
                " snippet(sections_fts, 2, '[', ']', ' ... ', 14)"
                " FROM sections_fts"
                " JOIN sections s ON s.rowid = sections_fts.rowid"
                " JOIN notes n ON n.id = s.note_id"
                " WHERE sections_fts MATCH ? ORDER BY rank LIMIT 400",
                (expr,)).fetchall()
        except sqlite3.OperationalError:
            continue
        if rows:
            used_rung = name
            break
    if not rows:
        con.close()
        return {"query": question, "rung": None, "status": "COMPLETE",
                "total": 0, "results": []}

    needles = [p.lower() for p in phrases] + terms
    tiers = note_tiers(con, {r[1] for r in rows})
    # ANCHOR is derived at query time from the annotations table - never from
    # sections.weight, which means the recency tier and nothing else. DISTINCT
    # makes stacked ANCHOR lines in one section count once.
    anchored = {r[0] for r in con.execute(
        "SELECT DISTINCT section_id FROM annotations"
        " WHERE marker='ANCHOR' AND section_id != ''")}
    scored = []
    for r in rows:
        (sid, nid, hpath, ddate, sslot, lstart, lend, words, is_unit,
         oversize, title, weight, npath, rank, snip) = r
        if slot and sslot != slot:
            continue
        score = -float(rank)
        low_title = (title or "").lower()
        low_head = (hpath or "").lower()
        if any(n in low_title for n in needles):
            score += 1.5
        if any(n in low_head for n in needles):
            score += 1.0
        if any(n == low_title for n in needles):
            score += 1.0     # a note that defines the term
        # Additive, in the same band as the title and heading boosts, applied
        # before the note-weight multiplier: an ANCHOR is a preference among
        # comparable matches, and corpus text must never out-shout the match
        # itself. A multiplier here was the veto the recency work removed; it
        # does not come back.
        if sid in anchored:
            score += ANCHOR_BOOST
        score += 0.3 * (deg.get(nid, 0) / max_deg)
        # Recency is additive and sits inside the multiplies below: bm25 orders
        # the hits, and `k * tier` reorders only those within k of each other.
        # As a multiplier it was a veto - the oldest entry of a 200-day log was
        # scaled by 1/200 and no match strength could recover from that.
        score += recency_k * section_tier(tiers, nid, ddate, sslot)
        # not `weight or 1.0`: a deliberate 0.0 is falsy, so suppressing a note
        # would silently give it full weight instead
        score *= 1.0 if weight is None else float(weight)
        # Supersession stays multiplicative. Superseded sections stay in the
        # index and stay linked -- the history is the point of keeping them --
        # but rank below anything still true whatever their match strength, so
        # a dead fact never outranks what replaced it.
        if sslot == "superseded":
            score *= SUPERSEDED_WEIGHT
        scored.append({
            "section_id": sid, "note_id": nid, "path": npath, "title": title,
            "heading_path": hpath or "(top)", "doc_date": ddate, "slot": sslot,
            "lines": f"{lstart}-{lend}", "line_start": lstart,
            "line_end": lend, "words": words, "is_unit": bool(is_unit),
            "oversize": bool(oversize), "score": round(score, 4),
            "snippet": snip,
        })
    # The sort key uses the date only among sections whose scores agree to
    # three places, which is what remains of recency once k is 0.
    scored.sort(key=lambda h: (-round(h["score"], 3), h["doc_date"] == "",
                               _neg_date(h["doc_date"]), h["section_id"]))

    kept: list[dict] = []
    per: dict[str, int] = {}
    for hit in scored:
        if per.get(hit["note_id"], 0) >= per_note:
            continue
        per[hit["note_id"]] = per.get(hit["note_id"], 0) + 1
        kept.append(hit)
    total = len(kept)

    if budget:
        packed, spent = [], 0
        for hit in kept:
            sec = con.execute(
                "SELECT body FROM sections WHERE id=?",
                (hit["section_id"],)).fetchone()
            body = sec[0] if sec else ""
            cost = est_tokens(body)
            if spent + cost > budget:
                children = con.execute(
                    "SELECT id, heading_path, line_start, line_end, body"
                    " FROM sections WHERE parent_id=? ORDER BY ord",
                    (hit["section_id"],)).fetchall()
                # A unit that does not fit is represented by its children, never
                # by a truncated body - a half-entry reads as a whole one.
                added = False
                for cid, chp, cls, cle, cbody in children:
                    ccost = est_tokens(cbody)
                    if spent + ccost > budget:
                        continue
                    packed.append({**hit, "section_id": cid,
                                   "heading_path": chp,
                                   "lines": f"{cls}-{cle}", "text": cbody,
                                   "substituted_for": hit["section_id"]})
                    spent += ccost
                    added = True
                if not added:
                    continue
                continue
            packed.append({**hit, "text": body})
            spent += cost
        result = {"query": question, "rung": used_rung,
                  "budget": budget, "spent": spent,
                  "total": total, "results": packed[:limit] if limit else packed}
        result["status"] = ("COMPLETE" if len(result["results"]) == total
                            else f"TRUNCATED {len(result['results'])} of {total}")
        con.close()
        return result

    con.close()
    out = kept[:limit]
    return {"query": question, "rung": used_rung, "total": total,
            "status": ("COMPLETE" if len(out) == total
                       else f"TRUNCATED {len(out)} of {total}"),
            "results": out}


def trajectory(vault: Path, term: str, slot: str | None = None,
               limit: int = 50) -> dict:
    """A term's distribution over time: the same FTS match `search` runs,
    grouped by date instead of ranked, so "is this recurring" is answered by
    the dates themselves. No row cap: the earliest occurrence is the point,
    and a cap ordered by rank is exactly what would drop it."""
    con = open_fresh(vault)
    phrases, terms = tokenize(term)
    empty = {"term": term, "rung": None, "slot": slot, "earliest": None,
             "peak": None, "latest": None, "distinct_dates": 0,
             "span_days": 0, "undated": 0, "status": "COMPLETE", "dates": []}
    if not phrases and not terms:
        con.close()
        return empty
    rows: list = []
    used_rung = None
    for name, expr in search_rungs(phrases, terms):
        try:
            rows = con.execute(
                "SELECT s.id, s.doc_date, s.slot, s.line_start, s.line_end,"
                " bm25(sections_fts) AS rank"
                " FROM sections_fts JOIN sections s ON s.rowid = sections_fts.rowid"
                " WHERE sections_fts MATCH ? ORDER BY rank, s.id",
                (expr,)).fetchall()
        except sqlite3.OperationalError:
            continue
        if rows:
            used_rung = name
            break
    con.close()
    by_date: dict[str, dict] = {}
    undated = 0
    for sid, ddate, sslot, lstart, lend, rank in rows:
        if slot and sslot != slot:
            continue
        if not ddate:
            undated += 1
            continue
        entry = by_date.get(ddate)
        if entry is None:
            # rows arrive best-rank first, so the first one seen per date is
            # that date's best section
            by_date[ddate] = {"doc_date": ddate, "sections": 1,
                              "best_bm25": round(float(rank), 4),
                              "section_id": sid, "lines": f"{lstart}-{lend}"}
        else:
            entry["sections"] += 1
    if not by_date:
        return {**empty, "rung": used_rung, "undated": undated}
    dates = [by_date[d] for d in sorted(by_date)]
    peak = min(dates, key=lambda d: (d["best_bm25"], d["doc_date"]))
    span = 0
    try:
        from datetime import date
        span = (date.fromisoformat(dates[-1]["doc_date"])
                - date.fromisoformat(dates[0]["doc_date"])).days
    except ValueError:
        pass
    shown = dates[:limit] if limit else dates
    return {"term": term, "rung": used_rung, "slot": slot,
            "earliest": dates[0]["doc_date"], "peak": peak["doc_date"],
            "latest": dates[-1]["doc_date"], "distinct_dates": len(dates),
            "span_days": span, "undated": undated,
            "status": ("COMPLETE" if len(shown) == len(dates)
                       else f"TRUNCATED {len(shown)} of {len(dates)}"),
            "dates": shown}


def _stripped_hash(body: str, heading: str) -> str:
    """Hash of a section's body below its heading line. The stored
    section_hash covers the heading itself, so it cannot pair a pure rename;
    this one can, and it is derived from columns both databases already hold."""
    if heading and body.startswith("#"):
        nl = body.find("\n")
        body = body[nl + 1:] if nl >= 0 else ""
    # A section's body carries the blank separator to its successor, so the
    # last section of a note differs by trailing whitespace from the same text
    # mid-note; strip both ends or a move to end-of-file never pairs.
    return hashlib.sha256(body.strip().encode()).hexdigest()[:16]


def _base_id(sid: str) -> str:
    """A section id minus the ~n ordinal that repeated heading paths get, so an
    insertion that shifts its later siblings' ordinals can still pair them."""
    return re.sub(r"~\d+$", "", sid)


def _ro_connect(path: str) -> sqlite3.Connection:
    """Open a db read-only, with the path percent-encoded into the URI. Bare
    concatenation would let a path containing '?' terminate the URI early and
    smuggle its own query parameters - `mode=rwc` among them - so the encoding
    is what makes the mode=ro claim true."""
    quoted = urllib.parse.quote(str(Path(path).resolve()))
    return sqlite3.connect(f"file:{quoted}?mode=ro", uri=True)


def _term_safe(text: str) -> str:
    """Vault-derived text about to be printed for a human: control characters
    (C0 and C1) become their escaped repr so an ANSI sequence in a heading or
    property value cannot rewrite what the terminal shows. Newline and tab
    stay: section text legitimately carries both and neither drives a
    terminal. Same rule `_single_line` enforces for link targets; JSON output
    needs nothing, json.dumps escapes these already."""
    return "".join(c if c in "\n\t"
                   or not (ord(c) < 0x20 or 0x7F <= ord(c) < 0xA0)
                   else repr(c)[1:-1] for c in text)


def _diff_rows(con: sqlite3.Connection) -> dict[str, tuple]:
    return {r[0]: r for r in con.execute(
        "SELECT id, note_id, heading_path, heading, section_hash, body"
        " FROM sections")}


def diff(vault: Path, against: str | None = None) -> dict:
    """What changed between the live graph and a checkpoint or another vault's
    db. Read-only on the against side; complete or erroring, never truncated."""
    con = open_fresh(vault)
    if against is None:
        prev = prev_db_path(vault)
        if not prev.exists():
            con.close()
            sys.exit(f"error: no checkpoint at {prev} - run"
                     " `ingest <vault> --keep-previous` to create one")
        against = str(prev)
    elif not Path(against).is_file():
        con.close()
        sys.exit(f"error: --against {against} is not a file")
    # Never through connect(): that runs the schema script and the column
    # migration, both writes, and the against side may be someone else's db.
    old_con = _ro_connect(against)
    try:
        have = {r[0] for r in old_con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
            " AND name IN ('sections', 'notes')")}
    except sqlite3.DatabaseError:
        have = set()
    if have != {"sections", "notes"}:
        old_con.close()
        con.close()
        sys.exit(f"error: --against {against} is not an obsidian-kg db"
                 " (no sections/notes tables)")
    new = _diff_rows(con)
    old = _diff_rows(old_con)
    old_con.close()
    con.close()

    # Pass 1 - exact: same id, same stored hash. Everything else, including
    # same-id-different-hash, stays in the pools: an id match is not yet an
    # edit, because an insertion in a run of repeated heading paths shifts
    # every later sibling's ~n ordinal and parks different sections under the
    # same id on the two sides.
    unchanged = 0
    old_left = dict(old)
    new_left: dict[str, tuple] = {}
    for sid, row in new.items():
        other = old_left.get(sid)
        if other is not None and other[4] == row[4]:
            del old_left[sid]
            unchanged += 1
        else:
            new_left[sid] = row

    def pair(key_of):
        """Pair leftovers count-for-count in deterministic id order, so
        duplicate bodies never pair many-to-one."""
        pairs = []
        old_by: dict = {}
        for sid in sorted(old_left):
            old_by.setdefault(key_of(old_left[sid]), []).append(sid)
        for sid in sorted(new_left):
            cands = old_by.get(key_of(new_left[sid]))
            if not cands:
                continue
            osid = cands.pop(0)
            pairs.append((old_left.pop(osid), new_left.pop(sid)))
        return pairs

    # Pass 2 - ordinal shift: same note, same base id, same full stored hash.
    # The ~n suffix moved and nothing else did; counted as unchanged.
    unchanged += len(pair(lambda r: (r[1], _base_id(r[0]), r[4])))
    # Pass 3 - edited: what still shares an exact id changed content.
    edited = pair(lambda r: r[0])
    # Pass 4 - renamed: same note, same content below a different heading.
    renamed = pair(lambda r: (r[1], _stripped_hash(r[5], r[3])))
    # Pass 5 - moved: same content in a different note.
    moved = pair(lambda r: _stripped_hash(r[5], r[3]))

    def entry(r):
        return {"section_id": r[0], "heading_path": r[2] or "(top)"}

    def pair_entry(o, n):
        return {"from_id": o[0], "to_id": n[0],
                "from_heading_path": o[2] or "(top)",
                "to_heading_path": n[2] or "(top)"}

    # Note level, from content_hash where both sides have the notes table.
    def note_hashes(path):
        c = _ro_connect(path)
        rows = dict(c.execute("SELECT id, content_hash FROM notes"))
        c.close()
        return rows

    new_notes = note_hashes(db_path(vault))
    old_notes = note_hashes(against)
    notes = {
        "added": sorted(set(new_notes) - set(old_notes)),
        "removed": sorted(set(old_notes) - set(new_notes)),
        "edited": sorted(nid for nid in set(new_notes) & set(old_notes)
                         if new_notes[nid] != old_notes[nid]),
    }

    return {
        "against": against,
        "notes": notes,
        "added": [entry(new_left[s]) for s in sorted(new_left)],
        "removed": [entry(old_left[s]) for s in sorted(old_left)],
        "edited": [pair_entry(o, n)
                   for o, n in sorted(edited, key=lambda p: p[1][0])],
        "renamed": [pair_entry(o, n)
                    for o, n in sorted(renamed, key=lambda p: p[1][0])],
        "moved": [pair_entry(o, n)
                  for o, n in sorted(moved, key=lambda p: p[1][0])],
        "unchanged": unchanged,
    }


def _prop_date(value: str):
    """A property value as a date, or None. Comma-joined values are list
    properties at ingest, so their first element parsing cleanly would compare
    wrong-but-plausibly; they never parse. Non-ISO shapes land in the caller's
    unparsed bucket by design - the bucket is the prompt to fix frontmatter."""
    from datetime import date
    v = value.strip().strip("'\"").strip()
    if "," in v:
        return None
    try:
        return date.fromisoformat(v[:10])
    except ValueError:
        return None


def props(vault: Path, key: str | None = None, note: str | None = None,
          older_than: str | None = None, newer_than: str | None = None,
          missing: bool = False) -> dict:
    """Read path over the properties table ingest already fills. The date
    comparison lives here because each caller hand-rolling it is where a
    lexical compare silently misorders non-ISO strings."""
    from datetime import date
    con = open_fresh(vault)
    if note is not None:
        nid = resolve_note_arg(con, note)
        rows = con.execute(
            "SELECT key, value FROM properties WHERE note_id=?"
            " ORDER BY key", (nid,)).fetchall()
        con.close()
        return {"note": nid,
                "properties": [{"key": k, "value": v} for k, v in rows]}
    if key is None:
        rows = con.execute(
            "SELECT key, COUNT(*) FROM properties GROUP BY key"
            " ORDER BY key").fetchall()
        con.close()
        return {"keys": [{"key": k, "notes": n} for k, n in rows]}
    if missing:
        rows = con.execute(
            "SELECT id FROM notes WHERE id NOT IN"
            " (SELECT note_id FROM properties WHERE key=?) ORDER BY id",
            (key,)).fetchall()
        con.close()
        return {"key": key, "missing": [r[0] for r in rows]}
    rows = con.execute(
        "SELECT note_id, value FROM properties WHERE key=?"
        " ORDER BY note_id", (key,)).fetchall()
    con.close()
    older = date.fromisoformat(older_than) if older_than else None
    newer = date.fromisoformat(newer_than) if newer_than else None
    matched, unparsed = [], []
    for nid, value in rows:
        entry = {"note_id": nid, "value": value}
        if older is None and newer is None:
            matched.append(entry)
            continue
        d = _prop_date(value)
        if d is None:
            unparsed.append(entry)
            continue
        # strict on both bounds: the boundary date itself matches neither
        if older is not None and not d < older:
            continue
        if newer is not None and not d > newer:
            continue
        matched.append(entry)
    out = {"key": key, "notes": matched}
    if older is not None or newer is not None:
        # never silently dropped: a staleness query that hides the rows it
        # could not read reports a false clean
        out["unparsed"] = unparsed
    return out


def annotations_list(vault: Path, marker: str | None = None,
                     note: str | None = None, older_than: str | None = None,
                     newer_than: str | None = None, limit: int = 50) -> dict:
    """The worklist view over the annotations table: what needs follow-up,
    what was marked superseded, what events are coming up. Date filters use
    the exact `props` semantics - strict on both bounds, and rows whose marker
    line carries no parseable date land in a labeled `unparsed` bucket rather
    than being dropped, because "upcoming events" must not silently omit the
    undated ones."""
    con = open_fresh(vault)
    sql = ("SELECT note_id, section_id, line, marker, payload, target, date"
           " FROM annotations")
    conds, params = [], []
    if marker:
        conds.append("marker = ?")
        params.append(marker)
    if note is not None:
        conds.append("note_id = ?")
        params.append(resolve_note_arg(con, note))
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    rows = con.execute(sql + " ORDER BY marker, note_id, line",
                       params).fetchall()
    con.close()
    older = date.fromisoformat(older_than) if older_than else None
    newer = date.fromisoformat(newer_than) if newer_than else None
    matched, unparsed = [], []
    for nid, sid, ln, mk, payload, target, adate in rows:
        entry = {"marker": mk, "note_id": nid, "section_id": sid, "line": ln,
                 "payload": payload, "target": target, "date": adate}
        if older is None and newer is None:
            matched.append(entry)
            continue
        if not adate:
            unparsed.append(entry)
            continue
        d = date.fromisoformat(adate)
        if older is not None and not d < older:
            continue
        if newer is not None and not d > newer:
            continue
        matched.append(entry)
    total = len(matched)
    out = {"total": total,
           "status": ("COMPLETE" if total <= limit
                      else f"TRUNCATED {limit} of {total}"),
           "annotations": matched[:limit]}
    if older is not None or newer is not None:
        out["unparsed"] = unparsed
    return out


def _neg_date(d: str) -> str:
    """Sort key that puts newer dates first without reversing the whole tuple."""
    if not d:
        return "0"
    return "".join(chr(ord("9") - int(c)) if c.isdigit() else c for c in d)


def est_tokens(text: str) -> int:
    """Token estimate for budgeting. Deliberately crude and deliberately high:
    over-estimating keeps a pack inside its budget."""
    return max(1, len(text) // 3)


# ---------- aggregates ----------
def window_sections(con: sqlite3.Connection, frm: str | None, to: str | None,
                    slot: str | None) -> list[tuple[str, str]]:
    """Aggregates count `own_body`, never `body`: a unit's body contains its
    children, so counting bodies would count a generated or instrument slot as
    the author's own words no matter how it is labelled."""
    sql = "SELECT id, own_body FROM sections WHERE doc_date != ''"
    params: list = []
    if frm:
        sql += " AND doc_date >= ?"
        params.append(frm)
    if to:
        sql += " AND doc_date <= ?"
        params.append(to)
    if slot:
        sql += " AND slot = ?"
        params.append(slot)
    return con.execute(sql + " ORDER BY id", params).fetchall()


def term_counts(bodies: list[str]) -> dict[str, int]:
    """Marker heads are stripped before counting: four hundred `NOTE` tokens
    are vocabulary, not a theme. The payload still counts - v1 tracks no
    authorship, and pretending agent-written payloads are separable would be
    worse than counting them."""
    counts: dict[str, int] = {}
    for body in bodies:
        text = MARKER_HEAD_RE.sub("", strip_code(body))
        for word in WORD_RE.findall(text.lower()):
            if word in STOPWORDS or len(word) < 3 or word.isdigit():
                continue
            counts[word] = counts.get(word, 0) + 1
    return counts


def log_likelihood(a: int, b: int, c: int, d: int) -> float:
    """Dunning (1993) log-likelihood ratio for over-representation of a term in
    a window (a of c words) against a reference corpus (b of d words). Signed:
    negative where the term is under-represented."""
    if a == 0 or c == 0 or d == 0:
        return 0.0
    e1 = c * (a + b) / (c + d)
    e2 = d * (a + b) / (c + d)
    ll = 0.0
    if a > 0 and e1 > 0:
        ll += a * math.log(a / e1)
    if b > 0 and e2 > 0:
        ll += b * math.log(b / e2)
    ll *= 2
    return ll if (a / c) >= ((a + b) / (c + d)) else -ll


def themes(vault: Path, frm: str | None, to: str | None, slot: str | None,
           limit: int = 20) -> dict:
    con = open_fresh(vault)
    slot = slot or "authored"
    win = window_sections(con, frm, to, slot)
    allsec = window_sections(con, None, None, slot)
    con.close()
    win_ids = {i for i, _ in win}
    win_counts = term_counts([b for _, b in win])
    ref_counts = term_counts([b for i, b in allsec if i not in win_ids])
    win_total = sum(win_counts.values())
    ref_total = sum(ref_counts.values())
    out = []
    for term, a in win_counts.items():
        if a < 2:
            continue
        b = ref_counts.get(term, 0)
        ll = log_likelihood(a, b, win_total, ref_total)
        if ll <= 0:
            continue
        out.append({"term": term, "count": a, "baseline": b,
                    "log_likelihood": round(ll, 3)})
    out.sort(key=lambda r: (-r["log_likelihood"], r["term"]))
    return {"from": frm or "", "to": to or "", "slot": slot,
            "sections": len(win), "words": win_total,
            "terms": out[:limit]}


def bucket_of(iso: str, by: str) -> str:
    y, m, _ = iso.split("-")
    if by == "month":
        return f"{y}-{m}"
    if by == "quarter":
        return f"{y}-Q{(int(m) - 1) // 3 + 1}"
    if by == "week":
        d = date.fromisoformat(iso).isocalendar()
        return f"{d[0]}-W{d[1]:02d}"
    return y


def trends(vault: Path, by: str, slot: str | None, limit: int = 8) -> dict:
    con = open_fresh(vault)
    slot = slot or "authored"
    rows = con.execute(
        "SELECT doc_date, own_body FROM sections WHERE doc_date != ''"
        + (" AND slot=?" if slot else "") + " ORDER BY doc_date",
        ([slot] if slot else [])).fetchall()
    con.close()
    buckets: dict[str, list[str]] = {}
    for ddate, body in rows:
        buckets.setdefault(bucket_of(ddate, by), []).append(body)
    keys = sorted(buckets)
    out = []
    for prev, cur in zip(keys, keys[1:]):
        a_counts = term_counts(buckets[cur])
        b_counts = term_counts(buckets[prev])
        a_total = sum(a_counts.values()) or 1
        b_total = sum(b_counts.values()) or 1
        moves = []
        for term in set(a_counts) | set(b_counts):
            a, b = a_counts.get(term, 0), b_counts.get(term, 0)
            if a + b < 3:
                continue
            ll = log_likelihood(a, b, a_total, b_total)
            if abs(ll) < 1:
                continue
            moves.append({"term": term, "now": a, "before": b,
                          "log_likelihood": round(ll, 3)})
        moves.sort(key=lambda r: -r["log_likelihood"])
        out.append({"window": cur, "previous": prev,
                    "rose": moves[:limit],
                    "fell": list(reversed(moves[-limit:]))})
    return {"by": by, "slot": slot, "windows": out}


# ---------- entities ----------
def entity_row(con: sqlite3.Connection, name: str) -> tuple:
    row = con.execute(
        "SELECT canonical, type, time, note, t_start, t_end FROM entities"
        " WHERE lower(canonical)=lower(?)", (name,)).fetchone()
    if row:
        return row
    hit = con.execute(
        "SELECT canonical FROM entity_aliases WHERE lower(alias)=lower(?)",
        (name,)).fetchone()
    if hit:
        return con.execute(
            "SELECT canonical, type, time, note, t_start, t_end FROM entities"
            " WHERE canonical=?", (hit[0],)).fetchone()
    con.close()
    sys.exit(f"error: {name!r} is not a registered entity - add it to "
             f"{CONFIG_NAME} if a retrieval needed it")


def entity(vault: Path, name: str, limit: int = 20) -> dict:
    con = open_fresh(vault)
    canonical, etype, etime, note, t0, t1 = entity_row(con, name)
    aliases = [r[0] for r in con.execute(
        "SELECT alias FROM entity_aliases WHERE canonical=? ORDER BY alias",
        (canonical,))]
    rows = con.execute(
        "SELECT m.section_id, m.note_id, m.doc_date, m.count, s.heading_path,"
        " s.line_start, s.line_end FROM mentions m"
        " JOIN sections s ON s.id = m.section_id WHERE m.canonical=?"
        " ORDER BY m.doc_date DESC, m.section_id", (canonical,)).fetchall()
    con.close()
    return {"canonical": canonical, "type": etype, "time": etime,
            "note": note, "span": f"{t0}..{t1}" if t0 or t1 else "",
            "aliases": aliases, "mention_count": len(rows),
            "mentions": [{"section_id": r[0], "note_id": r[1], "doc_date": r[2],
                          "count": r[3], "heading_path": r[4] or "(top)",
                          "lines": f"{r[5]}-{r[6]}"} for r in rows[:limit]]}


def timeline(vault: Path, name: str, limit: int = 50) -> dict:
    con = open_fresh(vault)
    canonical, etype, etime, note, t0, t1 = entity_row(con, name)
    rows = con.execute(
        "SELECT m.section_id, m.note_id, m.doc_date, s.heading_path,"
        " s.line_start, s.line_end FROM mentions m"
        " JOIN sections s ON s.id = m.section_id"
        " WHERE m.canonical=? ORDER BY m.doc_date, m.section_id",
        (canonical,)).fetchall()
    con.close()
    dated = [r for r in rows if r[2]]
    out = []
    for i, r in enumerate(dated):
        state = "current" if (etime == "evolving" and i == len(dated) - 1) \
            else ("superseded" if etime == "evolving" else "")
        out.append({"section_id": r[0], "note_id": r[1], "doc_date": r[2],
                    "heading_path": r[3] or "(top)",
                    "lines": f"{r[4]}-{r[5]}", "state": state})
    return {"canonical": canonical, "time": etime, "count": len(out),
            "undated": len(rows) - len(dated), "mentions": out[:limit]}


def during(vault: Path, name: str, limit: int = 50) -> dict:
    con = open_fresh(vault)
    canonical, etype, etime, note, t0, t1 = entity_row(con, name)
    if etime != "bounded":
        con.close()
        sys.exit(f"error: {canonical!r} has no bounded time span "
                 f"(set time to '<start>..<end>' in {CONFIG_NAME})")
    rows = con.execute(
        "SELECT id, note_id, doc_date, heading_path, line_start, line_end"
        " FROM sections WHERE is_unit=1 AND doc_date != ''"
        " AND doc_date >= ? AND doc_date <= ? ORDER BY doc_date, id",
        (t0, t1)).fetchall()
    con.close()
    return {"event": canonical, "from": t0, "to": t1, "count": len(rows),
            "sections": [{"section_id": r[0], "note_id": r[1], "doc_date": r[2],
                          "heading_path": r[3] or "(top)",
                          "lines": f"{r[4]}-{r[5]}"} for r in rows[:limit]]}


# ---------- detection ----------
def detect(vault: Path) -> dict:
    """Two mechanical detectors. `init` writes what is confident; `profile`
    prints everything and writes nothing."""
    con = open_fresh(vault)
    notes = con.execute("SELECT id, path, body FROM notes ORDER BY id").fetchall()
    deg = _degree(con)
    con.close()
    dated, hubs, generated = [], [], []
    for nid, npath, body in notes:
        row = learn_note(body, {"profile": "log-dated"})
        if row.get("date_order"):
            dated.append({"path": npath, "profile": "log-dated",
                          "date_from": "heading",
                          "date_level": row["date_level"],
                          "date_order": order_label(row["date_order"])})
        meta, _ = parse_frontmatter(body)
        for key in ("generator", "generated-by", "kg-generator"):
            if meta.get(key):
                generated.append({"path": npath, "profile": "generated",
                                  "weight": 0.2,
                                  "evidence": f"frontmatter {key}"})
                break
    if deg:
        # The median runs over every note, not only the linked ones: a vault of
        # mostly orphans has a median of zero and that is the honest baseline.
        vals = sorted(deg.get(nid, 0) for nid, _, _ in notes)
        median = vals[len(vals) // 2]
        cutoff = max(median * 3, 3)
        paths = {nid: npath for nid, npath, _ in notes}
        for nid, d in sorted(deg.items(), key=lambda kv: (-kv[1], kv[0])):
            if d >= cutoff:
                hubs.append({"path": paths.get(nid, nid + ".md"),
                             "profile": "hub", "degree": d,
                             "median_degree": median})
    return {"dated_logs": dated, "hubs": hubs, "generated": generated}


# ---------- index generation ----------
def render_index(vault: Path) -> str:
    con = open_fresh(vault)
    notes = con.execute(
        "SELECT id, path, title FROM notes ORDER BY path").fetchall()
    deg = _degree(con)
    sec_counts = dict(con.execute(
        "SELECT note_id, COUNT(*) FROM sections GROUP BY note_id"))
    words = dict(con.execute(
        "SELECT note_id, SUM(words) FROM sections WHERE is_unit=1"
        " GROUP BY note_id"))
    orphans = [r[0] for r in con.execute(
        "SELECT id FROM notes WHERE id NOT IN"
        " (SELECT src FROM edges WHERE status='resolved') AND id NOT IN"
        " (SELECT dst FROM edges WHERE status='resolved' AND dst IS NOT NULL)"
        " ORDER BY id")]
    broken = con.execute(
        "SELECT src, target, status FROM edges"
        " WHERE status IN ('unresolved','ambiguous') ORDER BY src, target"
    ).fetchall()
    # The engine's own generated index is excluded from this listing as well as
    # from the graph: including it would make the file's content depend on
    # whether it already exists, so the first run and the second would differ.
    ignored = con.execute(
        "SELECT path, rule FROM ignored WHERE rule != 'auto-generated index'"
        " ORDER BY path").fetchall()
    con.close()

    lines = ["---", "auto-generated: true",
             "generator: obsidian_kg.py index", "---", "",
             "# Vault index", "",
             f"{len(notes)} notes, {sum(sec_counts.values())} sections.", ""]
    lines.append("## Notes")
    lines.append("")
    for nid, npath, title in notes:
        lines.append(f"- [[{nid}]] - {title} "
                     f"({sec_counts.get(nid, 0)} sections, "
                     f"{words.get(nid, 0) or 0} words, "
                     f"degree {deg.get(nid, 0)})")
    lines += ["", "## What only the graph knows", ""]
    hubs = sorted(deg.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
    lines.append("### Hub notes by degree")
    lines.append("")
    lines += [f"- {nid} ({d})" for nid, d in hubs] or ["- none"]
    lines += ["", "### Orphans", ""]
    lines += [f"- {nid}" for nid in orphans] or ["- none"]
    lines += ["", "### Broken and ambiguous links", ""]
    lines += [f"- {src} -> `{target}` ({status})"
              for src, target, status in broken] or ["- none"]
    lines += ["", "### Largest notes", ""]
    biggest = sorted(words.items(), key=lambda kv: (-(kv[1] or 0), kv[0]))[:10]
    lines += [f"- {nid} ({w} words)" for nid, w in biggest] or ["- none"]
    if ignored:
        lines += ["", "### Excluded from the index", ""]
        lines += [f"- {p} ({rule})" for p, rule in ignored]
    return "\n".join(lines) + "\n"


# ---------- commands ----------
def cmd_ingest(args: argparse.Namespace) -> int:
    r = ingest(vault_dir(args.vault), keep_previous=args.keep_previous)
    if args.json:
        print(json.dumps(r, indent=2, sort_keys=True))
        return 0
    if args.keep_previous:
        print(f"checkpoint: {r['checkpoint']}" if r["checkpoint"]
              else "checkpoint: none written (no previous db to keep)")
    print(f"ingest: {r['notes']} notes, {r['sections']} sections; edges: "
          f"{r['resolved']} resolved, {r['unresolved']} unresolved, "
          f"{r['ambiguous']} ambiguous; {r['ignored_files']} files ignored; "
          f"{r['skipped_assets']} non-note targets skipped; "
          f"{r['entities']} entities, {r['mentions']} mentions")
    for bad in r["bad_profiles"]:
        print(f"  warning: unknown profile, indexed as reference - {bad}")
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    vault = vault_dir(args.vault)
    kg_dir(vault).mkdir(parents=True, exist_ok=True)
    cfg_file = config_path(vault)
    if cfg_file.exists() and not args.force:
        sys.exit(f"error: {cfg_file} already exists - edit it directly, or "
                 f"pass --force to rewrite the scaffold")
    ingest(vault)
    found = detect(vault)
    cfg = {"ignore": [], "profiles": [], "entities": []}
    for row in found["dated_logs"]:
        cfg["profiles"].append({"path": row["path"], "profile": "log-dated",
                                "date_from": "heading",
                                "date_order": row["date_order"]})
    for row in found["generated"]:
        cfg["profiles"].append({"path": row["path"], "profile": "generated",
                                "weight": 0.2})
    cfg_file.write_text(dump_config(cfg), encoding="utf-8")
    ingest(vault)
    print(f"init: wrote {cfg_file} with {len(cfg['profiles'])} confident "
          f"profile rows ({len(found['dated_logs'])} dated logs, "
          f"{len(found['generated'])} generated)")
    print(f"      db at {db_path(vault)} - gitignore {KG_DIR}/*.db*"
          " (covers the diff checkpoint and SQLite journal/wal sidecars;"
          " the config stays tracked)")
    return 0


def cmd_profile(args: argparse.Namespace) -> int:
    found = detect(vault_dir(args.vault))
    if args.json:
        print(json.dumps(found, indent=2, sort_keys=True))
        return 0
    if not any(found.values()):
        print("profile: nothing detected with confidence")
        return 0
    for key, rows in sorted(found.items()):
        if not rows:
            continue
        print(f"{key}:")
        for row in rows:
            print("  " + json.dumps(row, sort_keys=True))
    print(f"\nNothing was written. Copy what is right into "
          f"{KG_DIR}/{CONFIG_NAME}.")
    return 0


def cmd_query(args: argparse.Namespace) -> int:
    vault = vault_dir(args.vault)
    con = open_fresh(vault)
    try:
        rows = con.execute(
            "SELECT s.id, s.note_id, s.heading_path, s.line_start, s.line_end,"
            " snippet(sections_fts, 2, '[', ']', ' ... ', 14)"
            " FROM sections_fts JOIN sections s ON s.rowid = sections_fts.rowid"
            " WHERE sections_fts MATCH ? ORDER BY bm25(sections_fts) LIMIT ?",
            (args.fts_query, args.limit)).fetchall()
    except sqlite3.OperationalError as e:
        con.close()
        sys.exit(f"error: invalid FTS5 query {args.fts_query!r}: {e}")
    con.close()
    payload = [{"section_id": r[0], "note_id": r[1],
                "heading_path": r[2] or "(top)", "lines": f"{r[3]}-{r[4]}",
                "snippet": r[5]} for r in rows]

    def render(rows_):
        if not rows_:
            print("no matches")
            return 0
        for h in rows_:
            print(f"{h['section_id']}  [{h['lines']}]\n    {h['snippet']}")
        return 0
    return emit(args, payload, render)


def query(vault: Path, q: str, limit: int = 20) -> list[dict]:
    """Library entry point for raw FTS5 search over sections."""
    con = open_fresh(vault)
    try:
        rows = con.execute(
            "SELECT s.id, s.note_id, s.heading_path, s.line_start, s.line_end,"
            " snippet(sections_fts, 2, '[', ']', ' ... ', 14)"
            " FROM sections_fts JOIN sections s ON s.rowid = sections_fts.rowid"
            " WHERE sections_fts MATCH ? ORDER BY bm25(sections_fts) LIMIT ?",
            (q, limit)).fetchall()
    except sqlite3.OperationalError as e:
        con.close()
        raise ValueError(f"invalid FTS5 query {q!r}: {e}") from e
    con.close()
    return [{"section_id": r[0], "id": r[1], "note_id": r[1],
             "heading_path": r[2], "lines": f"{r[3]}-{r[4]}", "snippet": r[5]}
            for r in rows]


def cmd_search(args: argparse.Namespace) -> int:
    payload = search(vault_dir(args.vault), args.question, args.limit,
                     args.per_note, args.budget, args.slot, args.recency_k)

    def render(res):
        if not res["results"]:
            print(f"no matches for {res['query']!r}")
            return 0
        print(f"{res['status']}  (rung: {res['rung']})")
        for h in res["results"]:
            head = f"{_term_safe(h['section_id'])}  [{h['lines']}]"
            if h.get("doc_date"):
                head += f"  {h['doc_date']}"
            print(head)
            if "text" in h:
                print(_term_safe(h["text"].rstrip()))
                print("---")
            else:
                print(f"    {_term_safe(h['snippet'])}")
        if res.get("budget"):
            print(f"budget {res['spent']}/{res['budget']} tokens")
        return 0
    return emit(args, payload, render)


def cmd_props(args: argparse.Namespace) -> int:
    if (args.older_than or args.newer_than) and not args.key:
        sys.exit("error: --older-than/--newer-than require --key")
    if args.missing and not args.key:
        sys.exit("error: --missing requires --key")
    payload = props(vault_dir(args.vault), args.key, args.note,
                    args.older_than, args.newer_than, args.missing)

    def render(p):
        safe = _term_safe
        if "properties" in p:
            for e in p["properties"]:
                print(f"{safe(e['key'])}: {safe(e['value'])}")
        elif "keys" in p:
            for e in p["keys"]:
                print(f"{safe(e['key'])}  ({e['notes']} notes)")
        elif "missing" in p:
            for nid in p["missing"]:
                print(safe(nid))
            print(f"{len(p['missing'])} note(s) without '{safe(p['key'])}'")
        else:
            for e in p["notes"]:
                print(f"{safe(e['note_id'])}  {safe(e['value'])}")
            print(f"{len(p['notes'])} note(s) matched")
            for e in p.get("unparsed", []):
                print(f"unparsed: {safe(e['note_id'])}  {safe(e['value'])!r}")
        return 0
    return emit(args, payload, render)


def cmd_annotations(args: argparse.Namespace) -> int:
    payload = annotations_list(vault_dir(args.vault), args.marker, args.note,
                               args.older_than, args.newer_than, args.limit)

    def render(p):
        safe = _term_safe
        current = None
        for e in p["annotations"]:
            if e["marker"] != current:
                current = e["marker"]
                print(f"{current}:")
            where = e["section_id"] or e["note_id"]
            extra = f"  [{safe(e['date'])}]" if e["date"] else ""
            print(f"  {safe(where)}:{e['line']}{extra}  {safe(e['payload'])}")
        print(f"{p['status']}  ({p['total']} annotation(s))")
        for e in p.get("unparsed", []):
            print(f"unparsed: {safe(e['marker'])}"
                  f"  {safe(e['section_id'] or e['note_id'])}:{e['line']}"
                  f"  {safe(e['payload'])}")
        return 0
    return emit(args, payload, render)


def cmd_diff(args: argparse.Namespace) -> int:
    payload = diff(vault_dir(args.vault), args.against)

    def render(d):
        safe = _term_safe
        for bucket in ("added", "removed"):
            for e in d[bucket]:
                print(f"{bucket}: {safe(e['section_id'])}"
                      f"  ({safe(e['heading_path'])})")
        for bucket in ("edited", "renamed", "moved"):
            for e in d[bucket]:
                arrow = ("" if e["from_id"] == e["to_id"]
                         else f" -> {safe(e['to_id'])}")
                print(f"{bucket}: {safe(e['from_id'])}{arrow}")
        n = d["notes"]
        if any(n.values()):
            names = ", ".join(safe(x) for x in
                              n["added"] + n["removed"] + n["edited"])
            print(f"notes: {len(n['added'])} added, {len(n['removed'])} "
                  f"removed, {len(n['edited'])} edited"
                  + (f" - {names}" if names else ""))
        print(f"sections: {len(d['added'])} added, {len(d['removed'])} "
              f"removed, {len(d['edited'])} edited, {len(d['renamed'])} "
              f"renamed, {len(d['moved'])} moved, {d['unchanged']} unchanged"
              f"  (against {d['against']})")
        return 0
    return emit(args, payload, render)


def cmd_trajectory(args: argparse.Namespace) -> int:
    payload = trajectory(vault_dir(args.vault), args.term, args.slot,
                         args.limit)

    def render(t):
        if not t["distinct_dates"]:
            print(f"no dated matches for {t['term']!r}"
                  f" ({t['undated']} undated)")
            return 0
        for d in t["dates"]:
            print(f"{d['doc_date']}  {d['sections']:>3} section(s)  "
                  f"{_term_safe(d['section_id'])}  [{d['lines']}]  "
                  f"bm25 {d['best_bm25']}")
        print(f"{t['status']}  (rung: {t['rung']})")
        print(f"{t['distinct_dates']} distinct dates over {t['span_days']} "
              f"days: earliest {t['earliest']}, peak {t['peak']}, "
              f"latest {t['latest']}; {t['undated']} undated match(es)")
        return 0
    return emit(args, payload, render)


def cmd_note(args: argparse.Namespace) -> int:
    vault = vault_dir(args.vault)
    con = open_fresh(vault)
    nid = resolve_note_arg(con, args.note)
    path_, title, tags, aliases, body, profile = con.execute(
        "SELECT path, title, tags, aliases, body, profile FROM notes"
        " WHERE id=?", (nid,)).fetchone()
    props = con.execute(
        "SELECT key, value FROM properties WHERE note_id=? ORDER BY key",
        (nid,)).fetchall()
    con.close()
    payload = {"id": nid, "path": path_, "title": title, "profile": profile,
               "tags": tags, "aliases": aliases,
               "properties": {k: v for k, v in props}, "body": body}

    def render(p):
        print(f"id:      {p['id']}")
        print(f"path:    {p['path']}")
        print(f"title:   {p['title']}")
        print(f"profile: {p['profile']}")
        if p["tags"]:
            print(f"tags:    {p['tags']}")
        if p["aliases"]:
            print(f"aliases: {p['aliases']}")
        for k, v in sorted(p["properties"].items()):
            print(f"{k}: {v}")
        print("---")
        print(p["body"], end="" if p["body"].endswith("\n") else "\n")
        return 0
    return emit(args, payload, render)


def cmd_sections(args: argparse.Namespace) -> int:
    vault = vault_dir(args.vault)
    con = open_fresh(vault)
    nid = resolve_note_arg(con, args.note)
    rows = con.execute(
        "SELECT id, heading_path, level, line_start, line_end, words, is_unit,"
        " oversize, doc_date, slot FROM sections WHERE note_id=? ORDER BY ord",
        (nid,)).fetchall()
    con.close()
    payload = [{"section_id": r[0], "heading_path": r[1] or "(top)",
                "level": r[2], "lines": f"{r[3]}-{r[4]}", "words": r[5],
                "is_unit": bool(r[6]), "oversize": bool(r[7]),
                "doc_date": r[8], "slot": r[9]} for r in rows]

    def render(rows_):
        if not rows_:
            print("no sections")
            return 0
        for s in rows_:
            mark = "unit" if s["is_unit"] else "    "
            over = "  OVERSIZE" if s["oversize"] else ""
            date_ = f"  {s['doc_date']}" if s["doc_date"] else ""
            print(f"{mark}  {s['section_id']}  [{s['lines']}] "
                  f"{s['words']}w{date_}{over}")
        return 0
    return emit(args, payload, render)


def cmd_read(args: argparse.Namespace) -> int:
    vault = vault_dir(args.vault)
    con = open_fresh(vault)
    row = con.execute(
        "SELECT id, note_id, heading_path, line_start, line_end, body,"
        " doc_date, slot, words, oversize FROM sections WHERE id=?",
        (args.section_id,)).fetchone()
    if row is None:
        con.close()
        sys.exit(f"error: unknown section {args.section_id!r} "
                 f"(list them with `sections`)")
    npath = con.execute("SELECT path FROM notes WHERE id=?",
                        (row[1],)).fetchone()[0]
    con.close()
    body = row[5]
    offset = max(0, args.offset)
    payload = {"section_id": row[0], "note_id": row[1], "path": npath,
               "heading_path": row[2] or "(top)",
               "lines": f"{row[3]}-{row[4]}", "doc_date": row[6],
               "slot": row[7], "words": row[8], "oversize": bool(row[9]),
               "text": body[offset:] if offset else body}

    def render(p):
        print(f"# {p['path']}  [{p['lines']}]  {p['heading_path']}")
        if p["doc_date"]:
            print(f"date: {p['doc_date']}")
        if p["oversize"]:
            print("note: this unit is over the size ceiling and is returned "
                  "whole; its children are separately addressable")
        print("---")
        print(p["text"], end="" if p["text"].endswith("\n") else "\n")
        return 0
    return emit(args, payload, render)


def cmd_links(args: argparse.Namespace) -> int:
    vault = vault_dir(args.vault)
    con = open_fresh(vault)
    if args.unresolved and args.note is None:
        rows = con.execute(
            "SELECT src, dst, target, syntax, kind, status, section_id"
            " FROM edges WHERE status IN ('unresolved','ambiguous')"
            " ORDER BY src, target").fetchall()
    else:
        if args.note is None:
            con.close()
            sys.exit("error: links needs a note (or --unresolved for the "
                     "whole vault)")
        nid = resolve_note_arg(con, args.note)
        sql = ("SELECT src, dst, target, syntax, kind, status, section_id"
               " FROM edges WHERE src=?")
        if args.unresolved:
            sql += " AND status IN ('unresolved','ambiguous')"
        rows = con.execute(sql + " ORDER BY status, syntax, kind, target",
                           (nid,)).fetchall()
    payload = [{"src": r[0], "dst": r[1], "target": r[2], "syntax": r[3],
                "kind": r[4], "status": r[5], "section_id": r[6]}
               for r in rows]
    # Provenance appears only behind the flag, so the default output shape
    # stays byte-identical for every existing consumer.
    if getattr(args, "include_inferred", False):
        for e in payload:
            e["provenance"] = "extracted"
        if args.note is not None:
            nid = resolve_note_arg(con, args.note)
            for i, sid, s, p, o, q, at, st in _inferred_rows(con):
                if s == nid:
                    payload.append({"src": s, "dst": o, "target": o,
                                    "syntax": "inferred", "kind": p,
                                    "status": "hot", "section_id": sid,
                                    "provenance": "inferred"})
    con.close()

    def render(rows_):
        if not rows_:
            print("no outbound links")
            return 0
        for e in rows_:
            where = f"  in {e['section_id']}" if e["section_id"] else ""
            if e.get("provenance") == "inferred":
                print(f"inferred/{e['kind']}  ->  {e['dst']}{where}")
            elif e["status"] == "resolved":
                print(f"{e['syntax']}/{e['kind']}  ->  {e['dst']}  "
                      f"(as {e['target']!r}){where}")
            else:
                print(f"{e['syntax']}/{e['kind']}  ->  "
                      f"{e['status'].upper()}  (as {e['target']!r}) "
                      f"from {e['src']}{where}")
        return 0
    return emit(args, payload, render)


def cmd_backlinks(args: argparse.Namespace) -> int:
    vault = vault_dir(args.vault)
    con = open_fresh(vault)
    nid = resolve_note_arg(con, args.note)
    rows = con.execute(
        "SELECT e.src, e.target, e.syntax, e.kind, e.section_id,"
        " COALESCE(s.heading_path, '') FROM edges e"
        " LEFT JOIN sections s ON s.id = e.section_id"
        " WHERE e.dst=? ORDER BY e.src, e.syntax, e.kind", (nid,)).fetchall()
    payload = [{"src": r[0], "target": r[1], "syntax": r[2], "kind": r[3],
                "section_id": r[4], "heading_path": r[5] or "(top)"}
               for r in rows]
    if getattr(args, "include_inferred", False):
        for e in payload:
            e["provenance"] = "extracted"
        for i, sid, s, p, o, q, at, st in _inferred_rows(con):
            if o == nid:
                hp = con.execute(
                    "SELECT heading_path FROM sections WHERE id=?",
                    (sid,)).fetchone()
                payload.append({"src": s, "target": o, "syntax": "inferred",
                                "kind": p, "section_id": sid,
                                "heading_path": (hp[0] if hp and hp[0]
                                                 else "(top)"),
                                "provenance": "inferred"})
    con.close()

    def render(rows_):
        if not rows_:
            print("no backlinks")
            return 0
        for e in rows_:
            if e.get("provenance") == "inferred":
                print(f"inferred/{e['kind']}  <-  {e['src']}  "
                      f"in {e['heading_path']}")
            else:
                print(f"{e['syntax']}/{e['kind']}  <-  {e['src']}  "
                      f"(as {e['target']!r})  in {e['heading_path']}")
        return 0
    return emit(args, payload, render)


def _inferred_rows(con: sqlite3.Connection,
                   include_cold: bool = False) -> list[tuple]:
    """Inferred relations: `extractions` rows of kind 'relation'. Hot rows
    only by default - a cold row's anchoring section changed or vanished, so
    its evidence can no longer be read where it was recorded."""
    sql = ("SELECT id, section_id, subject, predicate, object, quote,"
           " observed_at, status FROM extractions WHERE kind='relation'")
    if not include_cold:
        sql += " AND status='hot'"
    return con.execute(sql + " ORDER BY id").fetchall()


def _adjacency(con: sqlite3.Connection,
               include_inferred: bool = False) -> dict[str, list[tuple[str, str]]]:
    """Undirected adjacency over resolved edges: id -> [(other, syntax/kind)].
    Inferred relations (hot only) join behind the explicit flag, labeled
    `inferred/<predicate>`, and never by default - extracted edges are what
    the corpus states, inferred ones are what someone concluded."""
    adj: dict[str, list[tuple[str, str]]] = {}
    for src, dst, syntax, kind in con.execute(
            "SELECT src, dst, syntax, kind FROM edges WHERE status='resolved'"):
        label = f"{syntax}/{kind}"
        adj.setdefault(src, []).append((dst, label))
        adj.setdefault(dst, []).append((src, label))
    if include_inferred:
        for _, _, subject, predicate, obj, _, _, _ in _inferred_rows(con):
            label = f"inferred/{predicate}"
            adj.setdefault(subject, []).append((obj, label))
            adj.setdefault(obj, []).append((subject, label))
    return adj


def relate(vault: Path, section_id: str, predicate: str, target: str,
           quote: str) -> dict:
    """Record one inferred relation into the never-wiped `extractions` table:
    subject is the anchoring section's note, object resolves like any note
    argument, and the quote must actually occur in the anchoring section -
    evidence is verified at write time, not trusted. Ingest never calls this;
    inference is always an explicit judgment recorded after the fact."""
    con = open_fresh(vault)
    row = con.execute(
        "SELECT note_id, body, char_start, doc_date, section_hash"
        " FROM sections WHERE id=?", (section_id,)).fetchone()
    if row is None:
        con.close()
        sys.exit(f"error: no section with id {section_id!r} - cite an id from"
                 " `sections` or `search`")
    note_id, body, char_start, doc_date, section_hash = row
    predicate = predicate.strip()
    if not predicate:
        con.close()
        sys.exit("error: predicate must be non-empty")
    obj = resolve_note_arg(con, target)
    at = body.find(quote)
    if not quote or at == -1:
        con.close()
        sys.exit("error: quote not found in the anchoring section - an"
                 " inferred relation records evidence, and the evidence must"
                 " be readable where it is cited")
    q_start, q_end = char_start + at, char_start + at + len(quote)
    dup = con.execute(
        "SELECT id FROM extractions WHERE kind='relation' AND section_id=?"
        " AND subject=? AND predicate=? AND object=? AND status='hot'",
        (section_id, note_id, predicate, obj)).fetchone()
    if dup:
        con.close()
        return {"id": dup[0], "existing": True, "subject": note_id,
                "predicate": predicate, "object": obj, "conflicts": []}
    conflicts = [r[0] for r in con.execute(
        "SELECT id FROM extractions WHERE kind='relation' AND subject=?"
        " AND predicate=? AND object != ? AND status='hot' ORDER BY id",
        (note_id, predicate, obj))]
    cur = con.execute(
        "INSERT INTO extractions(section_id, section_hash, kind, subject,"
        " predicate, object, quote, q_start, q_end, observed_at, doc_date,"
        " status) VALUES (?,?,'relation',?,?,?,?,?,?,?,?,'hot')",
        (section_id, section_hash, note_id, predicate, obj, quote,
         q_start, q_end, now_utc(), doc_date))
    new_id = cur.lastrowid
    seqs = []
    for other in conflicts:
        cur = con.execute(
            "INSERT INTO conflicts(detected_at, key, kind, a_extraction,"
            " b_extraction, state) VALUES (?,?,?,?,?,'hot')",
            (now_utc(), f"{note_id}|{predicate}", "relation", other, new_id))
        seqs.append(cur.lastrowid)
    con.commit()
    con.close()
    return {"id": new_id, "existing": False, "subject": note_id,
            "predicate": predicate, "object": obj, "conflicts": seqs}


def retire_relation(vault: Path, rid: int) -> dict:
    """The exit route for a wrong judgment row. The never-delete rule holds -
    the row keeps its evidence with status 'retired' (sticky across ingests) -
    but it leaves traversal, the default listing, and the dup/conflict checks,
    and its open conflicts close."""
    con = open_fresh(vault)
    row = con.execute("SELECT status FROM extractions WHERE id=? AND"
                      " kind='relation'", (rid,)).fetchone()
    if row is None:
        con.close()
        sys.exit(f"error: no inferred relation #{rid}")
    con.execute("UPDATE extractions SET status='retired' WHERE id=?", (rid,))
    con.execute("UPDATE conflicts SET state='cold' WHERE kind='relation'"
                " AND (a_extraction=? OR b_extraction=?)", (rid, rid))
    con.commit()
    con.close()
    return {"id": rid, "was": row[0], "status": "retired"}


def resolve_conflict(vault: Path, seq: int, resolution: str) -> dict:
    """Record the ruling on a relation conflict and close it. The rows it
    names stay as they are - retiring the losing relation is a separate,
    deliberate act."""
    if not resolution.strip():
        sys.exit("error: a resolution must say something")
    con = open_fresh(vault)
    row = con.execute("SELECT seq FROM conflicts WHERE seq=? AND"
                      " kind='relation'", (seq,)).fetchone()
    if row is None:
        con.close()
        sys.exit(f"error: no relation conflict #{seq}")
    con.execute("UPDATE conflicts SET resolution=?, state='cold'"
                " WHERE seq=?", (resolution.strip(), seq))
    con.commit()
    con.close()
    return {"seq": seq, "state": "cold", "resolution": resolution.strip()}


def relations_list(vault: Path, note: str | None = None,
                   include_cold: bool = False,
                   show_conflicts: bool = False) -> dict:
    """The read surface for inferred relations, and the conflict worklist."""
    con = open_fresh(vault)
    nid = resolve_note_arg(con, note) if note is not None else None
    rows = [{"id": i, "section_id": sid, "subject": s, "predicate": p,
             "object": o, "quote": q, "observed_at": at, "status": st}
            for i, sid, s, p, o, q, at, st
            in _inferred_rows(con, include_cold=include_cold)
            if nid is None or nid in (s, o)]
    out: dict = {"relations": rows}
    if show_conflicts:
        out["conflicts"] = [
            {"seq": seq, "key": key, "a": a, "b": b, "state": state,
             "resolution": res}
            for seq, key, a, b, state, res in con.execute(
                "SELECT seq, key, a_extraction, b_extraction, state,"
                " resolution FROM conflicts WHERE kind='relation'"
                " ORDER BY seq")]
    con.close()
    return out


def neighbors(vault: Path, name: str, depth: int = 1,
              include_inferred: bool = False) -> list[dict]:
    """BFS out to `depth` hops over resolved edges (both directions)."""
    con = open_fresh(vault)
    nid = resolve_note_arg(con, name)
    adj = _adjacency(con, include_inferred=include_inferred)
    hubs = _hub_notes(con) - {nid}
    con.close()
    out, seen, frontier = [], {nid}, [nid]
    for d in range(1, depth + 1):
        nxt = []
        for node in frontier:
            for other, label in sorted(adj.get(node, [])):
                if other not in seen:
                    seen.add(other)
                    # a hub is a neighbor, but never a bridge: expanding
                    # through an index note drags in the whole vault
                    if other not in hubs:
                        nxt.append(other)
                    out.append({"id": other, "depth": d, "via": node,
                                "edge": label})
        frontier = nxt
    return out


def path(vault: Path, a: str, b: str,
         include_inferred: bool = False) -> list[str] | None:
    """Shortest undirected path over resolved edges, or None if disconnected."""
    con = open_fresh(vault)
    a = resolve_note_arg(con, a)
    b = resolve_note_arg(con, b)
    adj = _adjacency(con, include_inferred=include_inferred)
    con.close()
    if a == b:
        return [a]
    prev: dict[str, str] = {a: a}
    frontier = [a]
    while frontier:
        nxt = []
        for node in frontier:
            for other, _ in sorted(adj.get(node, [])):
                if other in prev:
                    continue
                prev[other] = node
                if other == b:
                    chain = [b]
                    while chain[-1] != a:
                        chain.append(prev[chain[-1]])
                    return list(reversed(chain))
                nxt.append(other)
        frontier = nxt
    return None


def cmd_neighbors(args: argparse.Namespace) -> int:
    got = neighbors(vault_dir(args.vault), args.note, args.depth,
                    include_inferred=args.include_inferred)

    def render(rows_):
        if not rows_:
            print("no neighbors")
            return 0
        for n in rows_:
            print(f"{n['depth']}  {n['id']}  ({n['edge']} via {n['via']})")
        return 0
    return emit(args, got, render)


def cmd_path(args: argparse.Namespace) -> int:
    chain = path(vault_dir(args.vault), args.a, args.b,
                 include_inferred=args.include_inferred)
    if args.json:
        print(json.dumps({"path": chain}, indent=2))
        return 0 if chain else 1
    if chain is None:
        print(_term_safe(f"no path between {args.a} and {args.b}"))
        return 1
    # Note ids derive from vault file paths, so this join is corpus text and
    # goes through the sanitizer like every other prose renderer.
    print(_term_safe(" -> ".join(chain)))
    return 0


def cmd_relate(args: argparse.Namespace) -> int:
    payload = relate(vault_dir(args.vault), args.section_id, args.predicate,
                     args.target, args.quote)

    def render(p):
        verb = "already recorded" if p["existing"] else "recorded"
        print(f"{verb} #{p['id']}: {p['subject']}"
              f" -[{p['predicate']}]-> {p['object']}")
        for seq in p["conflicts"]:
            print(f"conflict #{seq}: same subject and predicate already"
                  " points elsewhere - see `relations --conflicts`")
        return 0
    return emit(args, payload, render)


def cmd_relations(args: argparse.Namespace) -> int:
    if args.retire is not None:
        payload = retire_relation(vault_dir(args.vault), args.retire)
        return emit(args, payload,
                    lambda p: print(f"#{p['id']}: {p['was']} -> retired") or 0)
    if args.resolve is not None:
        seq, text = args.resolve
        try:
            seq = int(seq)
        except ValueError:
            sys.exit(f"error: conflict seq must be a number, got {seq!r}")
        payload = resolve_conflict(vault_dir(args.vault), seq, text)
        return emit(args, payload,
                    lambda p: print(f"conflict #{p['seq']} closed:"
                                    f" {_term_safe(p['resolution'])}") or 0)
    payload = relations_list(vault_dir(args.vault), args.note,
                             args.include_cold, args.conflicts)

    def render(p):
        safe = _term_safe
        for r in p["relations"]:
            mark = f"  [{r['status']}]" if r["status"] != "hot" else ""
            print(f"#{r['id']}  {safe(r['subject'])}"
                  f" -[{safe(r['predicate'])}]-> {safe(r['object'])}"
                  f"{mark}  ({safe(r['section_id'])})")
        print(f"{len(p['relations'])} inferred relation(s)")
        for c in p.get("conflicts", []):
            res = f"  resolution: {safe(c['resolution'])}" \
                if c["resolution"] else ""
            print(f"conflict #{c['seq']} [{c['state']}]  {safe(c['key'])}"
                  f"  #{c['a']} vs #{c['b']}{res}")
        return 0
    return emit(args, payload, render)


def cmd_tags(args: argparse.Namespace) -> int:
    vault = vault_dir(args.vault)
    con = open_fresh(vault)
    if args.tag:
        rows = [r[0] for r in con.execute(
            "SELECT note_id FROM tags WHERE lower(tag) = lower(?)"
            " ORDER BY note_id", (args.tag.lstrip("#"),))]
        con.close()
        if args.json:
            print(json.dumps(rows, indent=2))
            return 0 if rows else 1
        if not rows:
            print(f"no notes tagged {args.tag!r}")
            return 1
        for nid in rows:
            print(nid)
        return 0
    rows = con.execute(
        "SELECT lower(tag), COUNT(*) FROM tags GROUP BY lower(tag)"
        " ORDER BY COUNT(*) DESC, lower(tag)").fetchall()
    con.close()
    payload = [{"tag": t, "count": c} for t, c in rows]

    def render(rows_):
        if not rows_:
            print("no tags")
            return 0
        for r in rows_:
            print(f"{r['count']:4d}  {r['tag']}")
        return 0
    return emit(args, payload, render)


def cmd_entity(args: argparse.Namespace) -> int:
    payload = entity(vault_dir(args.vault), args.name, args.limit)

    def render(p):
        print(f"{p['canonical']}  [{p['type'] or 'untyped'}] "
              f"time={p['time']}{' ' + p['span'] if p['span'] else ''}")
        if p["aliases"]:
            print("aliases: " + ", ".join(p["aliases"]))
        if p["note"]:
            print(f"note: {p['note']}")
        print(f"mentions: {p['mention_count']}")
        for m in p["mentions"]:
            print(f"  {m['doc_date'] or '(undated)'}  {m['section_id']}  "
                  f"[{m['lines']}]")
        return 0
    return emit(args, payload, render)


def cmd_timeline(args: argparse.Namespace) -> int:
    payload = timeline(vault_dir(args.vault), args.name, args.limit)

    def render(p):
        print(f"{p['canonical']}  time={p['time']}  {p['count']} dated "
              f"mentions ({p['undated']} undated)")
        for m in p["mentions"]:
            state = f"  [{m['state']}]" if m["state"] else ""
            print(f"  {m['doc_date']}  {m['section_id']}  "
                  f"[{m['lines']}]{state}")
        return 0
    return emit(args, payload, render)


def cmd_during(args: argparse.Namespace) -> int:
    payload = during(vault_dir(args.vault), args.event, args.limit)

    def render(p):
        print(f"{p['event']}  {p['from']}..{p['to']}  {p['count']} sections")
        for s in p["sections"]:
            print(f"  {s['doc_date']}  {s['section_id']}  [{s['lines']}]")
        return 0
    return emit(args, payload, render)


def cmd_themes(args: argparse.Namespace) -> int:
    payload = themes(vault_dir(args.vault), args.frm, args.to, args.slot,
                     args.limit)

    def render(p):
        span = f"{p['from'] or 'start'}..{p['to'] or 'end'}"
        print(f"themes {span}  slot={p['slot']}  "
              f"{p['sections']} sections, {p['words']} words")
        if not p["terms"]:
            print("  nothing over-represented in this window")
            return 0
        for t in p["terms"]:
            print(f"  {t['log_likelihood']:8.2f}  {t['term']}  "
                  f"({t['count']} here, {t['baseline']} elsewhere)")
        return 0
    return emit(args, payload, render)


def cmd_trends(args: argparse.Namespace) -> int:
    payload = trends(vault_dir(args.vault), args.by, args.slot, args.limit)

    def render(p):
        if not p["windows"]:
            print("not enough dated windows to compare")
            return 0
        for w in p["windows"]:
            print(f"{w['previous']} -> {w['window']}")
            print("  rose: " + ", ".join(t["term"] for t in w["rose"]))
            print("  fell: " + ", ".join(t["term"] for t in w["fell"]))
        return 0
    return emit(args, payload, render)


def _is_generated(path: Path) -> bool:
    try:
        head = path.read_text(encoding="utf-8", errors="replace")[:400]
    except OSError:
        return False
    meta, _ = parse_frontmatter(head)
    return (str(meta.get("auto-generated", "")).strip().lower() == "true"
            and str(meta.get("generator", "")).startswith("obsidian_kg.py"))


def _corpus_paths(vault: Path) -> set[Path]:
    if not db_path(vault).exists():
        return set()
    con = connect(vault, must_exist=True)
    rows = [r[0] for r in con.execute("SELECT path FROM notes")]
    con.close()
    return {(vault / r).resolve() for r in rows}


def cmd_index(args: argparse.Namespace) -> int:
    vault = vault_dir(args.vault)
    out = Path(args.out).expanduser() if args.out else vault / "Vault Index.md"
    if not out.is_absolute():
        out = vault / out
    # Vault text is what persuades a model to choose a command, so the write
    # target is confined regardless of what the argument says: `--out` can not
    # escape the vault, can not create directory trees elsewhere, and does not
    # clobber an existing file without being told to.
    try:
        resolved = out.resolve()
        resolved.relative_to(vault.resolve())
    except (ValueError, OSError):
        sys.exit(f"error: --out must stay inside the vault ({vault}); "
                 f"refusing to write {out}")
    if not resolved.parent.exists():
        sys.exit(f"error: no such directory: {resolved.parent}")
    corpus = _corpus_paths(vault)
    if resolved in corpus and not _is_generated(resolved):
        # --force exists to replace an index, not to destroy a note. The engine
        # knows which paths are corpus, so this closes the last destructive
        # target a link in the vault could steer a model toward.
        sys.exit(f"error: {resolved} is an indexed note - refusing to replace "
                 f"corpus with a generated index, even with --force")
    if resolved.exists() and not args.force and not _is_generated(resolved):
        # Regenerating this engine's own index is the normal case and must stay
        # frictionless; overwriting something a person wrote is the accident
        # worth blocking. The generator stamp is what tells them apart.
        sys.exit(f"error: {resolved} exists and was not written by this "
                 f"engine - pass --force to replace it")
    text = render_index(vault)
    resolved.write_text(text, encoding="utf-8")
    print(f"index: wrote {resolved} ({len(text.splitlines())} lines)")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    vault = vault_dir(args.vault)
    con = open_fresh(vault)
    notes = con.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
    sections = con.execute("SELECT COUNT(*) FROM sections").fetchone()[0]
    units = con.execute(
        "SELECT COUNT(*) FROM sections WHERE is_unit=1").fetchone()[0]
    oversize = con.execute(
        "SELECT COUNT(*) FROM sections WHERE oversize=1").fetchone()[0]
    edges = con.execute(
        "SELECT syntax, kind, status, COUNT(*) FROM edges"
        " GROUP BY syntax, kind, status ORDER BY syntax, kind, status"
    ).fetchall()
    orphans = [r[0] for r in con.execute(
        "SELECT id FROM notes WHERE id NOT IN"
        " (SELECT src FROM edges WHERE status='resolved') AND id NOT IN"
        " (SELECT dst FROM edges WHERE status='resolved' AND dst IS NOT NULL)"
        " ORDER BY id")]
    problems = {}
    for status in ("unresolved", "ambiguous", "ignored"):
        problems[status] = con.execute(
            "SELECT src, target FROM edges WHERE status=? ORDER BY src, target",
            (status,)).fetchall()
    ignored = con.execute(
        "SELECT path, rule FROM ignored ORDER BY path").fetchall()
    # Repeated heading paths within one note are the reason to care: their
    # section ids are disambiguated by ordinal, so inserting a new one shifts
    # every later id and breaks any citation to it. Renaming the headings is
    # the fix, and nothing else surfaces the problem.
    collisions = con.execute(
        "SELECT note_id, heading_path, COUNT(*) c FROM sections"
        " GROUP BY note_id, heading_path HAVING c > 1"
        " ORDER BY c DESC, note_id, heading_path").fetchall()
    tag_count = con.execute(
        "SELECT COUNT(DISTINCT lower(tag)) FROM tags").fetchone()[0]
    ent = con.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
    men = con.execute("SELECT COUNT(*) FROM mentions").fetchone()[0]
    ann_counts = con.execute(
        "SELECT marker, COUNT(*) FROM annotations GROUP BY marker"
        " ORDER BY COUNT(*) DESC, marker").fetchall()
    # Bounded on purpose: bold-caps-colon at column 0 is standard glossary
    # formatting in docs vaults, so this report must stay a capped summary,
    # never a raw dump of corpus lines.
    cand_total = con.execute(
        "SELECT COUNT(*) FROM annotation_candidates").fetchone()[0]
    cand_rows = con.execute(
        "SELECT token, kind, count FROM annotation_candidates"
        " ORDER BY count DESC, token, kind LIMIT 20").fetchall()
    con.close()
    custom_markers = [
        {"marker": str(r.get("marker", "")),
         "description": str(r.get("description", ""))}
        for r in load_config(vault).get("markers", [])]
    payload = {
        "notes": notes, "sections": sections, "units": units,
        "oversize_units": oversize, "tags": tag_count,
        "entities": ent, "mentions": men,
        "edges": [{"syntax": s, "kind": k, "status": st, "count": c}
                  for s, k, st, c in edges],
        "orphans": orphans,
        "link_problems": {k: [{"src": s, "target": t} for s, t in v]
                          for k, v in problems.items()},
        "ignored_files": [{"path": p, "rule": r} for p, r in ignored],
        "heading_collisions": [
            {"note_id": n, "heading_path": h or "(top)", "count": c}
            for n, h, c in collisions],
        "annotations": [{"marker": m, "count": c} for m, c in ann_counts],
        "custom_markers": custom_markers,
        "marker_candidates": {
            "total": cand_total,
            "status": ("COMPLETE" if cand_total <= 20
                       else f"TRUNCATED 20 of {cand_total}"),
            "tokens": [{"token": t, "kind": k, "count": c}
                       for t, k, c in cand_rows]},
    }

    def render(p):
        print(f"notes: {p['notes']}")
        print(f"sections: {p['sections']} ({p['units']} units, "
              f"{p['oversize_units']} oversize)")
        print("edges by syntax/kind:")
        for e in p["edges"]:
            print(f"  {e['syntax']}/{e['kind']} [{e['status']}]: {e['count']}")
        print(f"orphan notes: {len(p['orphans'])}"
              + (f" ({', '.join(p['orphans'][:5])})" if p["orphans"] else ""))
        for status, rows in sorted(p["link_problems"].items()):
            line = f"{status} links: {len(rows)}"
            if rows:
                line += " (e.g. " + "; ".join(
                    f"{r['src']} -> [[{r['target']}]]" for r in rows[:3]) + ")"
            print(line)
        print(f"ignored files: {len(p['ignored_files'])}")
        for row in p["ignored_files"][:5]:
            print(f"  {row['path']}  ({row['rule']})")
        dupes = p["heading_collisions"]
        print(f"repeated heading paths: {len(dupes)}"
              + ("  (their section ids carry an ordinal, so inserting one "
                 "shifts the rest - rename them)" if dupes else ""))
        for row in dupes[:5]:
            print(f"  {row['note_id']}  {row['heading_path']}  "
                  f"x{row['count']}")
        print(f"tags: {p['tags']}")
        print(f"entities: {p['entities']} ({p['mentions']} mentions)")
        if p["annotations"]:
            print("annotations by marker:")
            for row in p["annotations"]:
                print(f"  {row['marker']}: {row['count']}")
        for row in p["custom_markers"]:
            desc = f"  ({_term_safe(row['description'])})" \
                if row["description"] else ""
            print(f"registered marker: {row['marker']}{desc}")
        mc = p["marker_candidates"]
        if mc["total"]:
            print(f"marker candidates: {mc['total']} token(s)"
                  f" [{mc['status']}] - unregistered or mis-placed"
                  " **TOKEN**: lines")
            for row in mc["tokens"]:
                print(f"  {row['token']} ({row['kind']}): {row['count']}")
        return 0
    return emit(args, payload, render)


# ---------- CLI ----------
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="obsidian_kg.py",
        description="markdown vault -> SQLite knowledge graph")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help_):
        p = sub.add_parser(name, help=help_)
        p.add_argument("vault")
        p.add_argument("--json", action="store_true",
                       help="machine-readable output")
        p.set_defaults(fn=fn)
        return p

    p = add("ingest", cmd_ingest, "full rebuild: notes, sections, edges")
    p.add_argument("--keep-previous", action="store_true",
                   help="checkpoint the current db to vault-kg-prev.db first"
                        " (what a bare `diff` compares against)")

    p = add("init", cmd_init, "scaffold vault-kg/ and a confident config")
    p.add_argument("--force", action="store_true",
                   help="rewrite an existing config scaffold")

    add("profile", cmd_profile, "propose config rows; writes nothing")

    p = add("query", cmd_query, "raw FTS5 search over sections")
    p.add_argument("fts_query")
    p.add_argument("--limit", type=int, default=20)

    p = add("search", cmd_search, "natural-language section search")
    p.add_argument("question")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--per-note", type=int, default=3,
                   help="diversity cap: max sections from any one note")
    p.add_argument("--budget", type=int, default=None,
                   help="return a token-bounded pack of section text")
    p.add_argument("--slot", default=None, choices=sorted(SLOTS))
    p.add_argument("--recency-k", type=float, default=None,
                   help="recency weight for this call (config recency_k,"
                        f" else {RECENCY_K}); 0 disables recency")

    p = add("props", cmd_props, "query frontmatter properties")
    p.add_argument("--key", default=None,
                   help="list notes carrying this key (omit: keys + counts)")
    p.add_argument("--note", default=None, metavar="name-or-path",
                   help="every property on one note")
    p.add_argument("--older-than", default=None, metavar="YYYY-MM-DD",
                   help="with --key: values strictly before this date")
    p.add_argument("--newer-than", default=None, metavar="YYYY-MM-DD",
                   help="with --key: values strictly after this date")
    p.add_argument("--missing", action="store_true",
                   help="with --key: notes that lack the key entirely")

    p = add("annotations", cmd_annotations,
            "list inline **MARKER**: annotations (the worklist view)")
    p.add_argument("--marker", default=None, metavar="MARKER",
                   help="one marker only, e.g. FOLLOW-UP")
    p.add_argument("--note", default=None, metavar="name-or-path",
                   help="annotations in one note")
    p.add_argument("--older-than", default=None, metavar="YYYY-MM-DD",
                   help="captured dates strictly before this date;"
                        " undated rows land in an unparsed bucket")
    p.add_argument("--newer-than", default=None, metavar="YYYY-MM-DD",
                   help="captured dates strictly after this date;"
                        " undated rows land in an unparsed bucket")
    p.add_argument("--limit", type=int, default=50)

    p = add("diff", cmd_diff,
            "what changed vs the checkpoint or another vault's db")
    p.add_argument("--against", default=None, metavar="DB",
                   help="an obsidian-kg db to compare with (default:"
                        " vault-kg-prev.db from `ingest --keep-previous`)")

    p = add("trajectory", cmd_trajectory,
            "a term's distribution over dates: earliest, peak, latest, span")
    p.add_argument("term")
    p.add_argument("--slot", default=None, choices=sorted(SLOTS))
    p.add_argument("--limit", type=int, default=50,
                   help="dates listed; the summary always covers every date")

    p = add("note", cmd_note, "full note + frontmatter")
    p.add_argument("note", metavar="name-or-path")

    p = add("sections", cmd_sections, "section outline of a note")
    p.add_argument("note", metavar="name-or-path")

    p = add("read", cmd_read, "one section, whole")
    p.add_argument("section_id")
    p.add_argument("--offset", type=int, default=0)

    inferred_help = ("also traverse hot inferred relations (recorded by"
                     " `relate`); default traversal is extracted edges only")

    p = add("backlinks", cmd_backlinks, "inbound edges + their section")
    p.add_argument("note")
    p.add_argument("--include-inferred", action="store_true",
                   help=inferred_help)

    p = add("links", cmd_links, "outbound edges")
    p.add_argument("note", nargs="?", default=None)
    p.add_argument("--unresolved", action="store_true",
                   help="only broken and ambiguous links (vault-wide if no note)")
    p.add_argument("--include-inferred", action="store_true",
                   help=inferred_help)

    p = add("neighbors", cmd_neighbors, "BFS neighborhood of a note")
    p.add_argument("note")
    p.add_argument("--depth", type=int, default=1)
    p.add_argument("--include-inferred", action="store_true",
                   help=inferred_help)

    p = add("path", cmd_path, "shortest path between two notes")
    p.add_argument("a")
    p.add_argument("b")
    p.add_argument("--include-inferred", action="store_true",
                   help=inferred_help)

    p = add("relate", cmd_relate,
            "record an inferred relation with verified evidence")
    p.add_argument("section_id", help="anchoring section (evidence location)")
    p.add_argument("predicate", help="free-text relation, e.g. supersedes")
    p.add_argument("target", help="object note, resolved like any note arg")
    p.add_argument("--quote", required=True,
                   help="evidence text; must occur in the anchoring section")

    p = add("relations", cmd_relations,
            "list inferred relations (and --conflicts)")
    p.add_argument("--note", default=None,
                   help="only relations where this note is subject or object")
    p.add_argument("--include-cold", action="store_true",
                   help="include relations whose anchoring section changed,"
                        " and retired ones")
    p.add_argument("--conflicts", action="store_true",
                   help="also list recorded relation conflicts")
    p.add_argument("--retire", type=int, default=None, metavar="ID",
                   help="mark a relation retired: keeps its evidence, leaves"
                        " traversal and the worklist, closes its conflicts")
    p.add_argument("--resolve", nargs=2, default=None,
                   metavar=("SEQ", "TEXT"),
                   help="record the ruling on a conflict and close it")

    p = add("tags", cmd_tags, "tag counts, or notes bearing a tag")
    p.add_argument("tag", nargs="?", default=None)

    p = add("entity", cmd_entity, "a registered entity and its mentions")
    p.add_argument("name")
    p.add_argument("--limit", type=int, default=20)

    p = add("timeline", cmd_timeline, "an entity's mentions in date order")
    p.add_argument("name")
    p.add_argument("--limit", type=int, default=50)

    p = add("during", cmd_during, "sections inside a bounded entity's span")
    p.add_argument("event")
    p.add_argument("--limit", type=int, default=50)

    p = add("themes", cmd_themes, "over-represented terms in a date window")
    p.add_argument("--from", dest="frm", default=None)
    p.add_argument("--to", default=None)
    p.add_argument("--slot", default=None, choices=sorted(SLOTS))
    p.add_argument("--limit", type=int, default=20)

    p = add("trends", cmd_trends, "what rose and fell between windows")
    p.add_argument("--by", default="month",
                   choices=["week", "month", "quarter", "year"])
    p.add_argument("--slot", default=None, choices=sorted(SLOTS))
    p.add_argument("--limit", type=int, default=8)

    p = add("index", cmd_index, "render a vault index from the graph")
    p.add_argument("--out", default=None,
                   help="destination inside the vault (default 'Vault Index.md')")
    p.add_argument("--force", action="store_true",
                   help="replace an existing file at that path")

    add("stats", cmd_stats, "counts, orphans, unresolved/ambiguous")

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
