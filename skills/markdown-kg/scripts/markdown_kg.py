#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""markdown_kg.py - turn any markdown corpus into a queryable SQLite knowledge graph.

Stdlib only, Python 3.10+. Storage is `<vault>/.kg/markdown-kg.db`
(SQLite + FTS5) beside `<vault>/.kg/markdown-kg-config.json`; a vault built
under the old `markdown-kg/` or `vault-kg/` folder keeps using it in place. The vault
directory is always a CLI argument: nothing here is tied to any particular
vault, machine, or agent, and nothing here ever sends vault text anywhere - the
whole engine is offline.

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
  init <vault>                          scaffold .kg/ + confident config
  migrate <vault>                       move a legacy graph folder into .kg/
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
  props <vault> [--key K] [--note N]    query frontmatter properties
  annotations <vault> [--marker M]      inline **MARKER**: annotations
  diff <vault> [--against DB]           what changed vs the checkpoint
  trajectory <vault> <term>             a term's distribution over dates
  relate <vault> <section> <pred> <note> --quote Q   record an inferred relation
  relations <vault> [--conflicts]       list inferred relations
  coverage <vault> --session ID         a session's touched vs untouched territory
  links|backlinks <vault> <note> --anchors   links that name a heading or block
  fields <vault> [--field F] [--note N] links by the field they sit under
  tags <vault> [tag] --inline --nested  frontmatter tags plus body #tags
  related <vault> <note>                notes ranked by link-graph proximity
  communities <vault>                   clusters of notes that link together
  config <vault>                        what each config row matched
  refs <vault> <path>                   sections that link to a non-note file
  code <vault> <note>                   a note's linked files, as code-kg sees them
  code <vault> <note> --mentions        plus the files and symbols it names in code spans
  spans <vault> [text ...]              code spans shaped like a path or a name
"""
from __future__ import annotations

import argparse
import bisect
import contextlib
import hashlib
import json
import math
import os
import posixpath
import re
import sqlite3
import sys
import urllib.parse
from datetime import date
from pathlib import Path

# The core both engines share lives in this repo's lib/ folder (SKILL.md:
# `ships: repo-lib`), found from this file's real location.
LIB_DIR = str(Path(__file__).resolve().parents[3] / "lib")
if LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)
try:
    from kg_core import (
        GIT_STATES, KG_DIR, RELATED_DAMPING, TREE_LIMIT, WORD_RE, ParseCache,
        Store, bfs_path, changed_keys, config_json_text, doc_rank, emit,
        engine_fingerprint, est_tokens, git_status, glob_match,
        greedy_modularity, line_starts, linked_store,
        now_utc, other_file_rows, path_filter, print_capped, rank_from,
        relation_ruling, render_migrate, ro_connect, run_cli, run_sibling,
        seal, search_rungs, tokenize, tree_command, unit_diff, walk_tree,
        write_checkpoint)
except ModuleNotFoundError as e:
    if e.name != "kg_core":
        raise
    sys.exit(f"error: markdown-kg needs {LIB_DIR}/kg_core.py; install the"
             " whole repo it ships in, not this skill folder alone")

# The engine's earlier folders, newest first, each with its own file names
# and a markdown config: read and written in place until `migrate`.
LEGACY_LAYOUTS = {
    "markdown-kg": {"markdown-kg.db": "markdown-kg.db",
                    "markdown-kg-config.json": "markdown-kg-config.md",
                    "markdown-kg-prev.db": "markdown-kg-prev.db"},
    "vault-kg": {"markdown-kg.db": "vault-kg.db",
                 "markdown-kg-config.json": "vault-kg-config.md",
                 "markdown-kg-prev.db": "vault-kg-prev.db"},
}
STORE = Store("markdown-kg", "vault", legacy=LEGACY_LAYOUTS)
DB_NAME, PREV_DB_NAME, CONFIG_NAME = STORE.db, STORE.prev_db, STORE.config
KG_DIRS = STORE.dirs
kg_dir, db_path, prev_db_path, config_path, migrate = (
    STORE.folder, STORE.db_path, STORE.prev_db_path, STORE.config_path,
    STORE.migrate)

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
# Bump when a parser or schema change must re-index a vault whose files have
# not changed. The manifest folds it in, so the next read command re-ingests
# once instead of serving sections the old parser cut.
INDEX_REV = 7

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

# How many best-ranked FTS matches `search` scores. A slot filter is applied
# inside the query so the cap counts only matches in that slot; a result that
# hit the cap says so in `capped`.
SEARCH_ROW_CAP = 400

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
  status       TEXT NOT NULL DEFAULT 'hot',
  git          TEXT NOT NULL DEFAULT 'none'  -- tracked|untracked|ignored|none
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
  section_hash TEXT NOT NULL DEFAULT '',
  setext       INTEGER NOT NULL DEFAULT 0   -- heading was underlined, not ATX
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
CREATE TABLE IF NOT EXISTS anchors(       -- links that name a heading or block
  src         TEXT NOT NULL,              -- note id
  section_id  TEXT NOT NULL DEFAULT '',   -- section the link was written in
  dst         TEXT,                       -- note id; NULL unless the note resolved
  target      TEXT NOT NULL,              -- note target as written; '' = same note
  anchor      TEXT NOT NULL,              -- what followed `#`, as written
  dst_section TEXT NOT NULL DEFAULT '',   -- smallest section holding the anchor
  dst_line    INTEGER NOT NULL DEFAULT 0, -- 1-indexed line of the heading/block
  syntax      TEXT NOT NULL,              -- 'wiki' | 'md'
  status      TEXT NOT NULL,              -- resolved|anchor-missing|unresolved|
                                          -- ambiguous|ignored
  PRIMARY KEY (src, section_id, syntax, target, anchor)
);
CREATE INDEX IF NOT EXISTS anchors_dst ON anchors(dst);
CREATE TABLE IF NOT EXISTS link_fields(   -- links written under a named field
  src        TEXT NOT NULL,               -- note id
  field      TEXT NOT NULL,               -- frontmatter key or inline field name
  origin     TEXT NOT NULL,               -- 'frontmatter' | 'inline'
  target     TEXT NOT NULL,               -- target as written
  dst        TEXT,                        -- note id; NULL unless resolved
  status     TEXT NOT NULL,               -- resolved|unresolved|ambiguous|ignored
  section_id TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (src, field, origin, target)
);
CREATE INDEX IF NOT EXISTS link_fields_dst ON link_fields(dst);
CREATE TABLE IF NOT EXISTS inline_tags(   -- `#tags` written in body text
  note_id    TEXT NOT NULL,
  section_id TEXT NOT NULL DEFAULT '',
  tag        TEXT NOT NULL,
  count      INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (note_id, section_id, tag)
);
CREATE TABLE IF NOT EXISTS file_links(    -- links to files that are not notes
  src        TEXT NOT NULL,               -- note id
  section_id TEXT NOT NULL DEFAULT '',    -- section the link was written in
  target     TEXT NOT NULL,               -- target as written
  path       TEXT NOT NULL,               -- vault-relative path it names; starts
                                          -- `../` when the file is outside the
                                          -- vault. A wikilink keeps what was
                                          -- written: it names the end of a path
  syntax     TEXT NOT NULL,               -- 'wiki' | 'md'
  PRIMARY KEY (src, section_id, syntax, target)
);
CREATE INDEX IF NOT EXISTS file_links_path ON file_links(path);
CREATE TABLE IF NOT EXISTS code_spans(    -- inline code shaped like a path or name
  note_id    TEXT NOT NULL,
  section_id TEXT NOT NULL DEFAULT '',
  text       TEXT NOT NULL,               -- the span as written, backticks off
  line       INTEGER NOT NULL,            -- 1-indexed line of its first use here
  PRIMARY KEY (note_id, section_id, text)
);
CREATE INDEX IF NOT EXISTS code_spans_text ON code_spans(text);
CREATE TABLE IF NOT EXISTS entities(
  canonical TEXT PRIMARY KEY,
  type      TEXT NOT NULL DEFAULT '',
  time      TEXT NOT NULL DEFAULT 'static',
  note      TEXT NOT NULL DEFAULT '',
  t_start   TEXT NOT NULL DEFAULT '',
  t_end     TEXT NOT NULL DEFAULT '',
  origin    TEXT NOT NULL DEFAULT 'config'  -- 'config' | 'note' (entity_sources)
);
CREATE TABLE IF NOT EXISTS entity_skips(  -- derived names an ingest left out
  note_id TEXT NOT NULL,
  name    TEXT NOT NULL,
  reason  TEXT NOT NULL,
  PRIMARY KEY (note_id, name)
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
CREATE TABLE IF NOT EXISTS other_files(   -- files in the vault that are not
  path   TEXT PRIMARY KEY,                -- notes: attachments and the rest,
  ext    TEXT NOT NULL,                   -- listed by `tree`, never read
  size   INTEGER NOT NULL,
  reason TEXT NOT NULL                    -- no-parser
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
CREATE TABLE IF NOT EXISTS session_reads(  -- coverage ledger: never wiped by ingest
  session_id TEXT NOT NULL,
  section_id TEXT NOT NULL,
  note_id    TEXT NOT NULL,
  cmd        TEXT NOT NULL,                -- query | search | read | sections
  at         TEXT NOT NULL,                -- UTC; first touch wins
  PRIMARY KEY (session_id, section_id)
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
# A link reference definition, `[label]: target`, at the start of a line with
# up to three spaces of indent; and a use of one: `[text][label]`,
# `[label][]` or a bare `[label]` that no `(`, `[` or `:` follows.
MD_REF_DEF_RE = re.compile(
    r"^ {0,3}\[([^\[\]\n]{1,200})\]:[ \t]*(<[^<>\n]*>|\S+)", re.MULTILINE)
MD_REF_USE_RE = re.compile(
    r"(?<![\]\[!\\])\[([^\[\]\n]{1,200})\](?:\[([^\[\]\n]{0,200})\])?(?![\[(:])")
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
ATX_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
SETEXT_RE = re.compile(r"^(=+|-+)\s*$")
THEMATIC_BREAK_RE = re.compile(r"^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$")
LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.*\S)\s*$")
# A line that opens a list item (an empty one too), and a line inside a
# blockquote or a table. The heading parser keeps a setext underline away from
# text in these containers, as CommonMark does; `stats` reuses the list marker
# to flag a heading whose text opens like an item.
LIST_MARKER_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])(?:\s|$)")
BLOCK_CONTAINER_RE = re.compile(r"^\s*[>|]")
THEMATIC_BREAK_RE = re.compile(r"^\s{0,3}(?:\*\s*){3,}$|^\s{0,3}(?:-\s*){3,}$"
                               r"|^\s{0,3}(?:_\s*){3,}$")


def vault_dir(arg: str) -> Path:
    vault = Path(arg).expanduser().resolve()
    if not vault.is_dir():
        sys.exit(f"error: vault directory not found: {arg}")
    return vault


# Columns a table gained after databases were already built; an older
# database degrades to unweighted rather than to broken until it re-ingests.
ADDED_COLUMNS = {
    "sections": [("weight", "REAL NOT NULL DEFAULT 1.0"),
                 ("setext", "INTEGER NOT NULL DEFAULT 0")],
    "entities": [("origin", "TEXT NOT NULL DEFAULT 'config'")],
    "notes": [("git", "TEXT NOT NULL DEFAULT 'none'")],
}


def connect(vault: Path, must_exist: bool = False) -> sqlite3.Connection:
    return STORE.connect(vault, SCHEMA, ADDED_COLUMNS, must_exist)


# ---------- config ----------
def load_config(vault: Path) -> dict:
    """Read the config file. A missing or empty config is not an error: the
    engine works with no config at all."""
    cfg_file = config_path(vault)
    if not cfg_file.exists():
        return {"profiles": [], "entities": [], "markers": []}
    text = config_json_text(cfg_file)
    if not text.strip():
        return {"profiles": [], "entities": [], "markers": []}
    try:
        cfg = json.loads(text)
    except json.JSONDecodeError as e:
        sys.exit(f"error: {cfg_file} has invalid json: {e}")
    if not isinstance(cfg, dict):
        sys.exit(f"error: {cfg_file} json block must be an object")
    if cfg.pop("ignore", None):
        # Exclusions live in .kgignore now; dropping these silently would
        # index what the vault meant to keep out.
        sys.exit(f"error: {cfg_file} has 'ignore' rows - "
                 + ("run `migrate`, which moves them to .kgignore"
                    if cfg_file.suffix == ".md" else
                    "move them to .kgignore (gitignore syntax)"))
    for key in ("profiles", "entities", "markers"):
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
    _check_extensions(cfg, cfg_file)
    return cfg


def _check_extensions(cfg: dict, cfg_file: Path) -> None:
    """The extension keys: `entity_sources` derives entities from notes that
    already have a page each, and `relations` names the inverse of a link
    field. Both are optional and absent means empty, so a config written
    before they existed loads exactly as it did."""
    for key in ("entity_sources", "relations"):
        cfg.setdefault(key, [])
        if not isinstance(cfg[key], list):
            sys.exit(f"error: {cfg_file}: '{key}' must be a list")
    if "link_resolution" in cfg and cfg["link_resolution"] not in LINK_MODES:
        sys.exit(f"error: {cfg_file}: 'link_resolution' must be"
                 f" {' or '.join(repr(m) for m in LINK_MODES)}")
    for row in cfg["entity_sources"]:
        if not isinstance(row, dict):
            sys.exit(f"error: {cfg_file}: entity_sources entries must be"
                     " objects")
        path = str(row.get("path", "")).strip()
        ktype = str(row.get("kg_type", "")).strip()
        if bool(path) == bool(ktype):
            sys.exit(f"error: {cfg_file}: an entity_sources row takes 'path'"
                     " or 'kg_type', exactly one")
        time = str(row.get("time", "") or "static").strip()
        if time not in ("static", "evolving"):
            # A span belongs to one event; a rule that covers many notes
            # cannot give them all the same start and end.
            sys.exit(f"error: {cfg_file}: entity_sources 'time' must be"
                     f" 'static' or 'evolving' ({(path or ktype)!r})")
    seen_fields: set[str] = set()
    for row in cfg["relations"]:
        if not isinstance(row, dict):
            sys.exit(f"error: {cfg_file}: relations entries must be objects")
        field = str(row.get("field", ""))
        inverse = str(row.get("inverse", ""))
        for label, tok in (("field", field), ("inverse", inverse)):
            if (tok or label == "field") and not FIELD_TOKEN_RE.fullmatch(tok):
                sys.exit(f"error: {cfg_file}: relations {label} {tok!r} must"
                         " be lowercase letters, digits, hyphen or"
                         " underscore, at most 64 characters")
        if field in RESERVED_FIELDS:
            sys.exit(f"error: {cfg_file}: {field!r} is a reserved property"
                     " and never a link field")
        if field in seen_fields:
            sys.exit(f"error: {cfg_file}: relations field {field!r}"
                     " declared twice")
        seen_fields.add(field)


def dump_config(cfg: dict) -> str:
    """Deterministic serialization: fixed key order, entities sorted by
    canonical, so a one-entity change is a one-line diff."""
    out = {
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
    # And for the extension keys: present once a vault declares a row.
    if cfg.get("entity_sources"):
        # Path rows first, as they resolve first.
        out["entity_sources"] = sorted(
            cfg["entity_sources"],
            key=lambda r: (not r.get("path"), str(r.get("path", "")),
                           str(r.get("kg_type", ""))))
    if cfg.get("relations"):
        out["relations"] = sorted(cfg["relations"],
                                  key=lambda r: str(r.get("field", "")))
    if "link_resolution" in cfg:
        out["link_resolution"] = cfg["link_resolution"]
    return json.dumps(out, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def write_config(vault: Path, cfg: dict) -> None:
    """Write `cfg` to the vault's config file. Only `init` and tests write
    one, and never into a legacy folder: `init` sends that to `migrate`."""
    path = config_path(vault)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(dump_config(cfg).encode("utf-8"))


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


def scan_wikilinks(text: str) -> list[tuple[str, str, str, int]]:
    """Wikilink (target, anchor, kind, char_offset) tuples in document order,
    from fence-stripped text. Target keeps its path fragment and drops the
    `|alias`; anchor is what followed `#` (a heading, a `#`-joined heading
    path or a `^block` id), '' when there was none. A same-note link
    (`[[#Heading]]`) comes back with an empty target."""
    out = []
    for m in WIKILINK_RE.finditer(strip_code(text)):
        inner = m.group(2).split("|", 1)[0]
        target, _, anchor = inner.partition("#")
        target = target.strip().rstrip("\\").strip()
        anchor = anchor.strip().rstrip("\\").strip()
        if not _single_line(target):
            # `[^\[\]]+` matches newlines, so an unclosed bracket can swallow
            # paragraphs of prose into a "target" that is then printed verbatim
            # into the generated index and into stats. No real link spans lines.
            continue
        if not _single_line(anchor):
            anchor = ""     # the same swallow, after a `#`: keep the note link
        if not target and not anchor:
            continue
        out.append((target, anchor, "embed" if m.group(1) else "link",
                    m.start()))
    return out


_PAREN_RE = re.compile(r"[()]")


def iter_md_links(text: str):
    """(start, inside) for every inline link `[text](inside)`: the matches
    of `(?<!!)\\[[^\\]]*\\]\\(([^()]+)\\)`, found in one pass. That pattern
    rescans to the next `]` from every `[`, so a note that is one long run of
    `[` costs time
    quadratic in its length, and a vault is untrusted input. Link text can
    never cross a `]`, so every `[` up to the next `]` shares one candidate
    close, and the text is walked close by close instead."""
    pos = 0
    while True:
        close = text.find("]", pos)
        if close == -1:
            return
        nxt = close + 1
        if text.startswith("(", nxt):
            paren = _PAREN_RE.search(text, nxt + 1)
            if paren and paren.group() == ")" and paren.start() > nxt + 1:
                # The leftmost `[` of this stretch that no `!` precedes: an
                # image is not a link, and a `[` after it still can be.
                start = text.find("[", pos, close)
                while start > 0 and text[start - 1] == "!":
                    start = text.find("[", start + 1, close)
                if start != -1:
                    yield start, text[nxt + 1:paren.start()]
                    nxt = paren.start() + 1
        pos = nxt


def _split_md_target(raw: str) -> tuple[str, str] | None:
    """(target, anchor) from the inside of `](...)` or a reference
    definition: `<...>` wrapping and a `"title"` suffix are stripped, the
    fragment is split off, and an external scheme returns None."""
    target = raw.strip()
    if target.startswith("<") and ">" in target:
        target = target[1:target.index(">")]
    elif len(target) > 1 and target.endswith('"'):
        # A trailing "title": whitespace, then a quoted run with no quote
        # inside it. Found from the right, because a pattern for it
        # backtracks quadratically over a long run of spaces.
        opener = target.rfind('"', 0, -1)
        if opener > 0 and target[opener - 1].isspace():
            target = target[:opener].rstrip()
    target, _, anchor = target.partition("#")
    target, anchor = target.strip(), anchor.strip()
    if not _single_line(target):
        return None
    if not _single_line(anchor):
        anchor = ""
    if re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", target):
        return None
    return target, anchor


def _ref_label(label: str) -> str:
    """Reference labels match case-insensitively with whitespace collapsed."""
    return " ".join(label.split()).casefold()


def scan_md_links(text: str) -> list[tuple[str, str, str, int]]:
    """Standard markdown link (target, anchor, style, char_offset) tuples in
    document order, from fence-stripped text. `style` is `inline` for
    `[text](target)` and `reference` for `[text][label]`, `[label][]` and a
    bare `[label]` that has a `[label]: target` definition. Images and
    external schemes are skipped. A same-note link (`[text](#heading)`) comes
    back with an empty target."""
    stripped = strip_code(text)
    out = []
    for start, inside in iter_md_links(stripped):
        parts = _split_md_target(inside)
        if parts and (parts[0] or parts[1]):
            out.append((parts[0], parts[1], "inline", start))
    defs: dict[str, tuple[str, str]] = {}
    for m in MD_REF_DEF_RE.finditer(stripped):
        label = _ref_label(m.group(1))
        parts = _split_md_target(m.group(2))
        # The first definition of a label wins, as CommonMark has it. A
        # footnote definition (`[^1]: text`) has the same shape and is not a
        # link at all.
        if label and not label.startswith("^") and parts and label not in defs:
            defs[label] = parts
    if defs:
        for m in MD_REF_USE_RE.finditer(stripped):
            label = _ref_label(m.group(2) or m.group(1))
            if label in defs and (defs[label][0] or defs[label][1]):
                out.append((defs[label][0], defs[label][1], "reference",
                            m.start()))
        out.sort(key=lambda r: r[3])
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


LINK_MODES = ("obsidian", "relative")


def link_mode(vault: Path, cfg: dict) -> tuple[str, str]:
    """How a markdown link that misses its relative path is read, and why:
    (mode, source). Config `link_resolution` decides when set. Otherwise a
    vault with an `.obsidian/` folder gets Obsidian's rules and any other
    tree gets plain relative paths, which is what its renderer follows."""
    mode = cfg.get("link_resolution")
    if mode in LINK_MODES:
        return mode, "config"
    if (vault / ".obsidian").is_dir():
        return "obsidian", "detected .obsidian/"
    return "relative", "default"


def resolve_md_note(target: str, src_rel: str, ids: list[str], known,
                    ignored_ids: set[str], by_base: dict[str, list[str]],
                    vault_wide: bool = False) -> tuple[str | None, str] | None:
    """Resolve a markdown link target to (note id, status), or None when the
    target is not a note link at all (an asset, or a path outside the vault).

    The path is read relative to the source file, or from the vault root
    with a leading `/`, which is what CommonMark and every docs tree mean.
    A target with no extension resolves the same way, and only when it
    names a note: an extensionless path that names none stays out of the
    broken-link worklist, because site routes and folders look the same.

    With `vault_wide` (an Obsidian vault), a target that misses its relative
    path and was not written as an explicit `./`, `../` or `/` path is read
    the way Obsidian writes markdown links: by basename or vault-root path,
    like a wikilink. That covers `[x](Note.md)` from another folder (the
    "shortest path" link format) and `[x](folder/Note.md)` (the "absolute
    path in vault" format). Outside an Obsidian vault those links are
    broken for every renderer, so they stay unresolved."""
    t = urllib.parse.unquote(target)
    is_md = t.lower().endswith(".md")
    stem = t[: -len(".md")] if is_md else t
    if t.startswith("/"):
        rel = posixpath.normpath(stem.lstrip("/"))
    else:
        rel = posixpath.normpath(posixpath.join(posixpath.dirname(src_rel),
                                                stem))
    if rel.startswith(".."):
        return None
    if rel in known:
        return rel, "resolved"
    if is_md and rel in ignored_ids:
        return None, "ignored"
    if not is_md and "." in stem.rsplit("/", 1)[-1]:
        return None             # some other extension: an asset
    if vault_wide and not t.startswith(("/", "./", "../")):
        dst, status = resolve_wikilink(stem, ids, by_base, {})
        if status != "unresolved":
            return dst, status
    return (None, "unresolved") if is_md else None


def file_link_path(written: str, src_rel: str) -> str:
    """The vault-relative path a markdown link to a non-note file names,
    read the way `resolve_md_note` reads a note target: from the source
    file's folder, or from the vault root with a leading `/`. A path that
    leaves the vault keeps its leading `../`, which is how a docs folder
    inside a repo reaches the code beside it."""
    if written.startswith("/"):
        return posixpath.normpath(written.lstrip("/") or ".")
    return posixpath.normpath(posixpath.join(posixpath.dirname(src_rel),
                                             written))


# ---------- anchors: links that name a heading or a block ----------
BLOCK_ID_RE = re.compile(r"(?:^|\s)\^([A-Za-z0-9-]+)[ \t]*$")
_ANCHOR_MARKUP_RE = re.compile(r"[*_`~\[\]#|^:]|%%")


def _anchor_key(text: str) -> str:
    return " ".join(text.split()).casefold()


def _anchor_plain(text: str) -> str:
    """Heading text as a link usually spells it: emphasis and the characters
    Obsidian drops from a heading link removed."""
    return " ".join(_ANCHOR_MARKUP_RE.sub(" ", text).split()).casefold()


def heading_slug(text: str) -> str:
    """The anchor GitHub and most docs renderers generate for a heading:
    lowercased, punctuation dropped except `-` and `_`, each space a hyphen."""
    kept = "".join(c for c in text.strip().lower()
                   if c.isalnum() or c in "-_ ")
    return kept.replace(" ", "-")


def anchor_index(text: str) -> dict:
    """Everything in one note a link can point at below note level: each
    heading (exact text, plain text, ancestor path, generated slug with the
    `-1`, `-2` suffixes a repeated heading gets) and each `^block-id`. Every
    target is a (char offset, 1-indexed line) pair."""
    nodes = parse_headings(text)
    build_tree(text, nodes)
    headings, slugs, seen = [], {}, {}
    for node in nodes:
        slug = heading_slug(node.heading)
        n = seen.get(slug, 0)
        seen[slug] = n + 1
        at = (node.char, node.line)
        slugs.setdefault(slug if n == 0 else f"{slug}-{n}", at)
        headings.append((at, _anchor_key(node.heading),
                         _anchor_plain(node.heading),
                         {key(p) for p in node.path[:-1]
                          for key in (_anchor_key, _anchor_plain)}))
    blocks: dict[str, tuple[int, int]] = {}
    mask = fence_mask(text)
    pos = 0
    for i, raw in enumerate(text.splitlines(keepends=True)):
        if not (i < len(mask) and mask[i]):
            m = BLOCK_ID_RE.search(raw.rstrip("\r\n"))
            if m:
                blocks.setdefault(m.group(1).lower(), (pos, i + 1))
        pos += len(raw)
    return {"headings": headings, "slugs": slugs, "blocks": blocks}


def resolve_anchor(index: dict, anchor: str) -> tuple[int, int] | None:
    """The (char offset, line) an anchor points at, or None. A `^id` is a
    block. Anything else is a heading, matched on its exact text, then its
    plain text, then its generated slug; `A#B` requires `A` among the
    ancestors of `B`. Where two headings match, the first in the note wins,
    which is what Obsidian and a rendered page both do."""
    anchor = anchor.strip()
    if anchor.startswith("^"):
        return index["blocks"].get(anchor[1:].strip().lower())
    parts = [p for p in (s.strip() for s in anchor.split("#")) if p]
    if not parts:
        return None
    for keyfn, col in ((_anchor_key, 1), (_anchor_plain, 2)):
        want = keyfn(parts[-1])
        ancestors = [keyfn(p) for p in parts[:-1]]
        if not want:
            continue
        for entry in index["headings"]:
            if entry[col] == want and all(a in entry[3] for a in ancestors):
                return entry[0]
    if len(parts) == 1:
        return index["slugs"].get(parts[0].lower())
    return None


# ---------- link fields and inline tags ----------
# A link written under a name: a frontmatter key (`up: "[[Parent]]"`) or an
# inline field (`up:: [[Parent]]` on its own line or list item, or bracketed
# mid-sentence as `[up:: [[Parent]]]` / `(up:: [[Parent]])`). The name is what
# types the relation; the link itself is already an edge.
_FIELD_NAME = r"[A-Za-z][A-Za-z0-9 _-]{0,63}"
FM_KEY_LINE_RE = re.compile(r"^([A-Za-z0-9_-]+):")
INLINE_FIELD_RE = re.compile(
    r"^[ \t]*(?:(?:[-*+]|\d+[.)])[ \t]+|>[ \t]*)*(" + _FIELD_NAME
    + r")::[ \t]*(.+)$")
BRACKET_FIELD_RE = re.compile(
    r"[\[(](" + _FIELD_NAME
    + r")::[ \t]*((?:\[\[[^\[\]\n]+\]\]|[^\[\]()\n])*)[\])]")
FIELD_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
RESERVED_FIELDS = {"tags", "aliases", "cssclasses"}
# One line longer than this is a minified blob or an undecoded file, never a
# field, and the scanners below run a pattern over every line they keep.
SCAN_LINE_MAX = 10000
# `#tag` in body text: letters, digits, `_`, `-` and `/` after a `#` that
# starts the line or follows whitespace, with at least one non-digit.
INLINE_TAG_RE = re.compile(r"(?<!\S)#([\w/-]{1,100})")


def _field_name(raw: str) -> str:
    return "-".join(raw.strip().lower().split())


def _code_free_lines(text: str) -> list[str]:
    """`strip_code`, kept as one entry per source line."""
    mask = fence_mask(text)
    return ["" if mask[i] else INLINE_CODE_RE.sub("", line)
            for i, line in enumerate(text.splitlines())]


def _links_in(value: str) -> list[tuple[str, str]]:
    """(syntax, target) for each wikilink and inline markdown link in one
    field value; anchors and aliases dropped, external targets skipped."""
    out = []
    for m in WIKILINK_RE.finditer(value):
        target = m.group(2).split("|", 1)[0].partition("#")[0]
        target = target.strip().rstrip("\\").strip()
        if target and _single_line(target):
            out.append(("wiki", target))
    for _, inside in iter_md_links(value):
        parts = _split_md_target(inside)
        if parts and parts[0]:
            out.append(("md", parts[0]))
    return out


def scan_field_links(text: str) -> list[tuple[str, str, str, str, int]]:
    """(field, origin, syntax, target, char_offset) for every link written
    under a frontmatter key or an inline field. `tags`, `aliases` and
    `cssclasses` are never fields; code and comments never carry one."""
    _, body_start = parse_frontmatter(text)
    code_free = _code_free_lines(text)
    cmask = _comment_mask(text)
    out, key, pos = [], None, 0
    for i, raw in enumerate(text.splitlines(keepends=True)):
        start, pos = pos, pos + len(raw)
        line = raw.rstrip("\r\n")
        if len(line) > SCAN_LINE_MAX:
            continue
        if start < body_start:
            m = FM_KEY_LINE_RE.match(line)
            if m:
                key = m.group(1).lower()
            if key and key not in RESERVED_FIELDS:
                out.extend((key, "frontmatter", syntax, target, start)
                           for syntax, target in _links_in(line))
            continue
        line = code_free[i]
        if cmask[i] or "::" not in line:
            continue
        m = INLINE_FIELD_RE.match(line)
        found = [m] if m else BRACKET_FIELD_RE.finditer(line)
        for fm in found:
            out.extend((_field_name(fm.group(1)), "inline", syntax, target,
                        start) for syntax, target in _links_in(fm.group(2)))
    return out


def scan_inline_tags(text: str) -> list[tuple[str, int]]:
    """(tag, char_offset) for every `#tag` in body text, outside frontmatter,
    code and comments. The offset is the start of the tag's line."""
    _, body_start = parse_frontmatter(text)
    code_free = _code_free_lines(text)
    cmask = _comment_mask(text)
    out, pos = [], 0
    for i, raw in enumerate(text.splitlines(keepends=True)):
        start, pos = pos, pos + len(raw)
        line = code_free[i]
        if (start < body_start or cmask[i] or "#" not in line
                or len(line) > SCAN_LINE_MAX):
            continue
        for m in INLINE_TAG_RE.finditer(line):
            tag = m.group(1).strip("/")
            if tag and re.search(r"[^\W\d]", tag):
                out.append((tag, start))
    return out


CODE_SPAN_RE = re.compile(r"`([^`\n]+)`")
# A span that could name a file or a symbol: one token of path and name
# characters with a letter in it, optionally called (`name()`). A flag
# (`--verbose`), an expression and a phrase are not names.
CODE_NAME_RE = re.compile(r"(?!-)(?=[^A-Za-z]*[A-Za-z])[\w./~@:#-]{2,200}"
                          r"(?:\(\))?")


def scan_code_spans(text: str) -> list[tuple[str, int]]:
    """(span, 1-indexed line) for every inline code span shaped like a path
    or a name, outside frontmatter, fenced code and comments. Docs write
    code names in backticks, and entity matching never reads inside them, so
    these spans are what a note says about code without linking to it."""
    _, body_start = parse_frontmatter(text)
    fmask = fence_mask(text)
    cmask = _comment_mask(text)
    out, pos = [], 0
    for i, raw in enumerate(text.splitlines(keepends=True)):
        start, pos = pos, pos + len(raw)
        if (start < body_start or fmask[i] or cmask[i] or "`" not in raw
                or len(raw) > SCAN_LINE_MAX):
            continue
        for m in CODE_SPAN_RE.finditer(raw):
            span = m.group(1).strip()
            if CODE_NAME_RE.fullmatch(span):
                out.append((span, i + 1))
    return out


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
        # after the date invalidate it: `2026-08-20-YY-ITEM-654321` would otherwise
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
                 "end_line", "children", "parent", "path", "setext")

    def __init__(self, level, heading, line, char, body_char, setext=False):
        self.level = level
        self.heading = heading
        self.setext = setext        # underlined with === or ---, not ATX
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
    # One pass, constant work per line: a hostile note made of underlines must
    # not turn the parse quadratic. `boundary` is the index of the last line
    # that closed a block (a heading line, a setext underline, a thematic break
    # or an empty list item), so the line after it opens a new paragraph.
    # `contained` says the current paragraph run opened in, or holds a line
    # from, a list item, a blockquote or a table.
    boundary = -1
    contained = False
    for i, raw in enumerate(lines):
        if offsets[i] < body_start or (i < len(mask) and mask[i]):
            contained = False
            continue
        line = raw.rstrip("\n")
        if not line.strip():
            contained = False
            continue
        m = ATX_RE.match(line)
        if m:
            nodes.append(Node(len(m.group(1)), _clip_heading(m.group(2)),
                              i + 1, offsets[i], offsets[i] + len(raw)))
            boundary = i
            contained = False
            continue
        sm = SETEXT_RE.match(line)
        if (sm and i > 0 and i - 1 != boundary and not contained
                and offsets[i - 1] >= body_start
                and not (i - 1 < len(mask) and mask[i - 1])
                and lines[i - 1].strip()):
            # CommonMark: an underline closes a paragraph at the top level.
            # Text inside a list item, a blockquote or a table is out of its
            # reach, so there `---` is a thematic break and `-` an empty list
            # item, a rule and a bullet in Obsidian. Promoting them would cut
            # the text that follows out of the heading above it.
            level = 1 if sm.group(1)[0] == "=" else 2
            nodes.append(Node(level, _clip_heading(lines[i - 1].strip()), i,
                              offsets[i - 1], offsets[i] + len(raw),
                              setext=True))
            boundary = i
            contained = False
            continue
        if (sm and sm.group(1)[0] == "-") or THEMATIC_BREAK_RE.match(line):
            # A dash line that is not an underline is a thematic break or an
            # empty list item, and `* * *` or `- - -` is a thematic break: a
            # block of its own, never paragraph text, and it ends whatever
            # list or paragraph came before it.
            boundary = i
            contained = False
        elif LIST_MARKER_RE.match(line) or BLOCK_CONTAINER_RE.match(line):
            contained = True
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
            is_unit, parent_id, doc_date="", oversize=0, heading="",
            setext=False):
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
            "oversize": oversize, "setext": int(setext),
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
                    max(lead_line, node.line), False, "", heading=node.heading,
                    setext=node.setext)
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
                  heading=node.heading, setext=node.setext)
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
        sec["own_body"] = _own_body(sec, out)
        sec["own_words"] = word_count(sec["own_body"])


def _own_body(sec: dict, out: list[dict]) -> str:
    """The section's body minus the sections nested inside it, cut by slices."""
    start, end = sec["char_start"], sec["char_end"]
    nested = sorted((o["char_start"] - start, o["char_end"] - start) for o in out
                    if o is not sec and o["char_start"] >= start and o["char_end"] <= end
                    and 0 < o["char_end"] - o["char_start"] < end - start)
    body = sec["body"]
    limit = max(0, min(len(body), end - start))
    pieces, pos = [], 0
    for a, b in nested:
        if a > pos:
            pieces.append(body[min(pos, limit):min(a, limit)])
        pos = max(pos, b)
    pieces.append(body[min(pos, limit):limit])
    return "".join(pieces)


def _pack_sections(sections: list[dict]) -> list[dict]:
    """Sections without their text, which _unpack_sections cuts back out of the note."""
    return [{k: v for k, v in s.items() if k not in ("body", "own_body")} for s in sections]


def _unpack_sections(rows: list[dict], text: str) -> list[dict]:
    out = [dict(r, body=text[r["char_start"]:r["char_end"]]) for r in rows]
    for sec in out:
        sec["own_body"] = _own_body(sec, out)
    return out


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


# ---------- vault walking (dot folders excluded) ----------
def scan_vault(vault: Path, every: bool = False, walked: tuple | None = None) \
        -> tuple[list[Path], list[str], list[tuple[str, str]]]:
    """All vault .md files (with `every`, all files: the inventory `tree`
    tallies), sorted for determinism, the paths refused for pointing outside
    the vault, and (path, rule) for each one an ignore file excludes
    (`walk_tree`). Dot folders and files, SKIP_FOLDERS and the engine's
    folders are never part of it. `walked`, a scan with `every` the caller
    already made, is filtered instead of walking again."""
    def keep(rel: str) -> bool:
        return every or rel.endswith(".md")

    if walked is not None:
        files, escapes, ignored = walked
        return ([p for p in files if keep(p.name)],
                [r for r in escapes if keep(r)],
                [(rel, why) for rel, why in ignored if keep(rel)])
    found, ignored = walk_tree(
        vault, lambda rel: rel in KG_DIRS or rel.rsplit("/", 1)[-1] in
        SKIP_FOLDERS or rel.rsplit("/", 1)[-1].startswith("."),
        list_ignored=True)
    files = [p for p in found if keep(p.name) and not p.name.startswith(".")]
    result = []
    escapes = []
    root = vault.resolve()
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
            if not p.resolve().is_relative_to(root):
                escapes.append(p)
                continue
        except (OSError, RuntimeError):
            escapes.append(p)   # broken or cyclic link
            continue
        result.append(p)
    return (sorted(result),
            sorted(p.relative_to(vault).as_posix() for p in escapes),
            [(rel, why) for rel, why in ignored if keep(rel)])


def walk_vault(vault: Path) -> list[Path]:
    return scan_vault(vault)[0]


def manifest(vault: Path, walked: tuple | None = None) -> str:
    """Cheap fingerprint of the vault's file set: path, size, mtime. Read
    commands compare it to detect drift and re-ingest without being asked.
    `walked` is a scan with `every` the caller already made."""
    parts = []
    # Every file, not only notes: `tree` counts attachments too.
    for p in (walked or scan_vault(vault, every=True))[0]:
        st = p.stat()
        parts.append(f"{p.relative_to(vault).as_posix()}|{st.st_size}|"
                     f"{int(st.st_mtime_ns)}")
    cfg = config_path(vault)
    if cfg.exists():
        parts.append(f"__config__|{cfg.stat().st_size}|"
                     f"{int(cfg.stat().st_mtime_ns)}")
    if (vault / ".obsidian").is_dir():
        # Opening a folder in Obsidian changes how its markdown links
        # resolve (link_mode), so it has to count as drift.
        parts.append("__obsidian__")
    parts.append(f"__index__|{INDEX_REV}")
    digest = hashlib.sha256("\n".join(parts).encode()).hexdigest()
    # Sealed, so a database that arrives with the vault re-ingests here once.
    return seal(digest) or digest


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


def _first_h1(text: str) -> str | None:
    return next((n.heading for n in parse_headings(text) if n.level == 1), None)


# Tables whose rows belong to one note, keyed by its id: an incremental ingest
# rewrites them only for notes added, changed or removed.
PER_NOTE_TABLES = {"notes": "id", "properties": "note_id", "tags": "note_id",
                   "aliases": "note_id", "sections": "note_id", "members": "note_id",
                   "annotations": "note_id", "inline_tags": "note_id",
                   "code_spans": "note_id"}


def _table_columns(con: sqlite3.Connection) -> dict:
    return {t: tuple(r[1] for r in con.execute(f'PRAGMA table_info("{t}")'))
            for t in PER_NOTE_TABLES}


def _row_counts(con: sqlite3.Connection) -> str:
    """Row counts of the per-note tables plus a hash of the section row ids. The
    search index is tied to those ids, which a VACUUM or a dump and reload can
    renumber; an incremental update over renumbered rows would corrupt it."""
    state = {t: con.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0]
             for t in sorted(PER_NOTE_TABLES)}
    digest = hashlib.sha256()
    for rowid, sid in con.execute("SELECT rowid, id FROM sections ORDER BY rowid"):
        digest.update(f"{rowid}\0{sid}\n".encode())
    state["section rowids"] = digest.hexdigest()
    return json.dumps(state)


def ingest(vault: Path, keep_previous: bool = False,
           walked: tuple | None = None) -> dict:
    """Index the vault, rewriting only the notes that changed. `walked` is a
    `scan_vault(every=True)` result the caller already holds."""
    checkpoint = None
    refused = linked_store(vault, kg_dir(vault), db_path(vault))
    if refused:
        sys.exit(f"error: {refused}")
    if keep_previous:
        # Copy before connect(): connect runs the schema script, and the
        # checkpoint must be the db exactly as the last ingest left it.
        live = db_path(vault)
        if live.exists():
            # A synced or cloned vault can carry a planted link at the
            # checkpoint name or at a predictable temp name beside it.
            write_checkpoint(live, prev_db_path(vault))
            checkpoint = str(prev_db_path(vault))
    # The per-note tables as the last ingest left them, read before connect()
    # runs the schema script: a table it creates or migrates holds none of the
    # unchanged notes' rows, so that ingest has to be a full one.
    prior_columns = None
    if db_path(vault).exists():
        try:
            ro = ro_connect(str(db_path(vault)))
            try:
                prior_columns = _table_columns(ro)
            finally:
                ro.close()
        except sqlite3.DatabaseError:
            prior_columns = None
    con = connect(vault)
    engine = engine_fingerprint(__file__, globals())
    memo = ParseCache(con, engine)
    cfg = load_config(vault)
    report = {"notes": 0, "sections": 0, "resolved": 0, "unresolved": 0,
              "ambiguous": 0, "ignored_files": 0, "ignored_links": 0,
              "skipped_assets": 0, "entities": 0, "mentions": 0,
              "annotations": 0, "bad_profiles": []}
    registered_markers = set(CORE_MARKERS) | {
        str(r.get("marker", "")) for r in cfg.get("markers", [])}
    cand_counts: dict[tuple, int] = {}

    parsed: dict[str, dict] = {}
    walked = walked or scan_vault(vault, every=True)
    # Taken before any note is read, so an edit made during this ingest
    # still reads as drift afterwards.
    fingerprint = manifest(vault, walked)
    files, escaped, ignored = scan_vault(vault, walked=walked)
    for rel in escaped:
        ignored.append((rel, "symlink or path outside the vault"))
    for f in files:
        rel = f.relative_to(vault).as_posix()
        text = f.read_text(encoding="utf-8", errors="replace")
        meta, _ = parse_frontmatter(text)
        if str(meta.get("auto-generated", "")).strip().lower() == "true":
            ignored.append((rel, "auto-generated index"))
            continue
        row = profile_for(rel[: -len(".md")], rel, meta, cfg)
        parsed[rel[: -len(".md")]] = {"rel": rel, "text": text, "meta": meta,
                                      "row": row,
                                      "hash": hashlib.sha256(text.encode()).hexdigest()}
    report["ignored_files"] = len(ignored)

    ids = sorted(parsed)
    ignored_ids = {r[: -len(".md")] for r, _ in ignored}
    by_base: dict[str, list[str]] = {}
    by_alias: dict[str, list[str]] = {}
    for nid in ids:
        by_base.setdefault(nid.rsplit("/", 1)[-1].lower(), []).append(nid)
        for alias in _listify(parsed[nid]["meta"].get("aliases", [])):
            by_alias.setdefault(alias.lower(), []).append(nid)

    # Incremental: when the engine and config match the last ingest,
    # only notes added, changed or removed are rewritten in the per-note tables.
    # The cross-note tables (links, anchors, mentions, candidates) are rebuilt in
    # full every time, since a change in one note reaches them through the others;
    # they come from the parse cache, so that stays cheap.
    # Sealed to this machine: a database built elsewhere is rebuilt in full.
    basis = seal(json.dumps([engine, cfg, link_mode(vault, cfg)],
                            sort_keys=True, default=str)) or ""
    prev = con.execute("SELECT value FROM meta WHERE key = 'ingest_basis'").fetchone()
    counts = con.execute("SELECT value FROM meta WHERE key = 'per_note_counts'").fetchone()
    old = dict(con.execute("SELECT id, content_hash FROM notes"))
    # The last ingest's row counts must still hold: a table something else dropped,
    # recreated or edited since then cannot pass as up to date.
    incremental = (bool(basis) and prev is not None and prev[0] == basis
                   and prior_columns == _table_columns(con)
                   and counts is not None and counts[0] == _row_counts(con))
    dirty = ({nid for nid in ids if old.get(nid) != parsed[nid]["hash"]} | (set(old) - set(ids))
             if incremental else set(ids) | set(old))
    per_note = PER_NOTE_TABLES
    for table in ("edges", "entities", "entity_aliases", "mentions", "ignored",
                  "annotation_candidates", "meta", "anchors", "link_fields",
                  "entity_skips", "file_links", "other_files"):
        con.execute(f"DELETE FROM {table}")
    con.execute("CREATE TEMP TABLE IF NOT EXISTS dirty_notes(id TEXT PRIMARY KEY)")
    con.execute("DELETE FROM dirty_notes")
    con.executemany("INSERT INTO dirty_notes(id) VALUES (?)", [(n,) for n in dirty])
    if incremental:
        con.execute(
            "INSERT INTO sections_fts(sections_fts, rowid, id, heading_path, body)"
            " SELECT 'delete', rowid, id, heading_path, body FROM sections"
            " WHERE note_id IN (SELECT id FROM dirty_notes)")
        for table, col in per_note.items():
            con.execute(f"DELETE FROM {table} WHERE {col} IN (SELECT id FROM dirty_notes)")
    else:
        for table in per_note:
            con.execute(f"DELETE FROM {table}")
        con.execute("INSERT INTO sections_fts(sections_fts) VALUES ('delete-all')")
    con.executemany(
        "INSERT INTO other_files(path, ext, size, reason) VALUES (?,?,?,?)",
        [(rel, posixpath.splitext(posixpath.basename(rel))[1].lower(),
          p.stat().st_size, "no-parser")
         for p in walked[0]
         if not (rel := p.relative_to(vault).as_posix()).endswith(".md")])

    for rel, rule in sorted(ignored):
        con.execute("INSERT INTO ignored(path, rule) VALUES (?,?)", (rel, rule))

    all_sections: list[dict] = []
    for nid in ids:
        doc = parsed[nid]
        meta, text, row = doc["meta"], doc["text"], doc["row"]
        text_hash = doc["hash"]
        # A clean note is still parsed (from the cache) for the cross-note tables,
        # but its own rows are already in the database and are not written again.
        put = con.execute if nid in dirty else (lambda *a: None)
        heading = memo.get("h1", [text_hash], lambda: _first_h1(text))
        title = str(meta.get("title") or heading or nid.rsplit("/", 1)[-1])
        tag_list = _listify(meta.get("tags", []))
        alias_list = _listify(meta.get("aliases", []))
        doc["title"], doc["aliases"] = title, alias_list
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
        put(
            "INSERT INTO notes(id, path, title, tags, aliases, content_hash,"
            " body, profile, weight, doc_date, status)"
            " VALUES (?,?,?,?,?,?,?,?,?,?, 'hot')",
            (nid, doc["rel"], title, ", ".join(tag_list), ", ".join(alias_list),
             text_hash, text, profile, weight, note_date))
        report["notes"] += 1
        for tag in sorted(set(tag_list)):
            put("INSERT INTO tags(note_id, tag) VALUES (?,?)",
                        (nid, tag))
        for alias in sorted(set(alias_list)):
            put("INSERT INTO aliases(note_id, alias) VALUES (?,?)",
                        (nid, alias))
        for key in sorted(meta):
            val = meta[key]
            if key in ("tags", "aliases"):
                continue
            if isinstance(val, list):
                val = ", ".join(str(v) for v in val)
            elif isinstance(val, dict):
                val = ", ".join(f"{k}={v}" for k, v in sorted(val.items()))
            put(
                "INSERT INTO properties(note_id, key, value) VALUES (?,?,?)",
                (nid, key, str(val)))

        learned = memo.get("learn_note", [text_hash, row], lambda: learn_note(text, row))
        if learned.get("date_order"):
            put(
                "INSERT OR REPLACE INTO properties(note_id, key, value)"
                " VALUES (?,?,?)",
                (nid, "kg-date-order", order_label(learned["date_order"])))
        unpack = lambda rows: _unpack_sections(rows, text)  # noqa: E731
        if profile == "list":
            sections = memo.get("build_list_sections", [nid, text_hash, row],
                                lambda: build_list_sections(nid, text, row),
                                _pack_sections, unpack)
        else:
            sections = memo.get("build_sections", [nid, text_hash, row, profile, learned],
                                lambda: build_sections(nid, text, {**row, "profile": profile},
                                                       learned),
                                _pack_sections, unpack)
        anns, cands = memo.get("scan_annotations", [text_hash, sorted(registered_markers)],
                               lambda: scan_annotations(text, registered_markers))
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
            put(
                "INSERT INTO sections(id, note_id, parent_id, heading,"
                " heading_path, level, ord, char_start, char_end, line_start,"
                " line_end, body, own_body, doc_date, slot, weight, words,"
                " is_unit, oversize, section_hash, setext)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (sec["id"], sec["note_id"], sec["parent_id"], sec["heading"],
                 sec["heading_path"], sec["level"], sec["ord"],
                 sec["char_start"], sec["char_end"], sec["line_start"],
                 sec["line_end"], sec["body"], sec["own_body"],
                 sec["doc_date"], sec["slot"], w, sec["words"], sec["is_unit"],
                 sec["oversize"], sec["section_hash"], sec.get("setext", 0)))
            for i, name in enumerate(sec.get("members", [])):
                put(
                    "INSERT OR IGNORE INTO members(section_id, note_id,"
                    " group_name, name, ord) VALUES (?,?,?,?,?)",
                    (sec["id"], nid, sec["heading"], name, i))
        for ann in anns:
            put(
                "INSERT INTO annotations(note_id, section_id, line, marker,"
                " payload, target, date) VALUES (?,?,?,?,?,?,?)",
                (nid, ann["section_id"], ann["line"], ann["marker"],
                 ann["payload"], ann["target"], ann["date"]))
        report["annotations"] += len(anns)
        report["sections"] += len(sections)
        all_sections.extend(sections)
        doc["sections"] = sections

    # edges, once every note id is known, so collision detection stays global
    vault_wide = link_mode(vault, cfg)[0] == "obsidian"
    ignored_sorted = sorted(ignored_ids)
    ignored_by_base = _index_by_base(ignored_ids)
    anchor_cache: dict[str, dict] = {}

    def wiki_dst(target: str) -> tuple[str | None, str]:
        dst, status = resolve_wikilink(target, ids, by_base, by_alias)
        if status == "unresolved":
            probe, _ = resolve_wikilink(target, ignored_sorted,
                                        ignored_by_base, {})
            if probe is not None:
                status = "ignored"
        return dst, status

    def anchor_row(src: str, sec: str, dst: str | None, target: str,
                   anchor: str, syntax: str, status: str) -> tuple:
        """One `anchors` row. The note-level status stands unless the note
        resolved; then the anchor either lands in a section or is missing."""
        dst_section, dst_line = "", 0
        if status == "resolved" and dst:
            def resolve():
                if dst not in anchor_cache:
                    anchor_cache[dst] = anchor_index(parsed[dst]["text"])
                return resolve_anchor(anchor_cache[dst], anchor)
            at = memo.get("resolve_anchor", [parsed[dst]["hash"], anchor], resolve)
            if at is None:
                status = "anchor-missing"
            else:
                dst_section = _section_at(parsed[dst]["sections"], at[0])
                dst_line = at[1]
        return (src, sec, dst, target, anchor, dst_section, dst_line, syntax,
                status)

    for nid in ids:
        doc = parsed[nid]
        text, sections = doc["text"], doc["sections"]
        rows: list[tuple] = []
        anchor_rows: list[tuple] = []
        file_rows: list[tuple] = []
        # The two link scanners read the code-stripped text, which keeps
        # every line of the note and not every character, so an offset from
        # them falls short of its place in `text` by all the code above it.
        # The line is exact, so the section is found by line.
        h = doc["hash"]
        starts = memo.get("line_starts", [h], lambda: line_starts(strip_code(text)))

        def section_of(off: int) -> str:
            return _section_on_line(sections,
                                    bisect.bisect_right(starts, off))

        for target, anchor, kind, off in memo.get("scan_wikilinks", [h],
                                                  lambda: list(scan_wikilinks(text))):
            sec = section_of(off)
            dst, status = nid, "resolved"       # a same-note link
            if target:
                base = target.rsplit("/", 1)[-1]
                ext = base.rsplit(".", 1)[-1].lower() if "." in base else ""
                if ext in ASSET_EXTS:
                    report["skipped_assets"] += 1
                    file_rows.append((nid, sec, target, posixpath.normpath(
                        target.strip("/")), "wiki"))
                    continue
                dst, status = wiki_dst(target)
                rows.append((nid, dst, target, "wiki", kind, status, sec))
            if anchor:
                anchor_rows.append(anchor_row(nid, sec, dst, target, anchor,
                                              "wiki", status))
        for target, anchor, style, off in memo.get("scan_md_links", [h],
                                                   lambda: list(scan_md_links(text))):
            sec = section_of(off)
            dst, status = nid, "resolved"       # a same-note link
            written = urllib.parse.unquote(target)
            if target:
                found = resolve_md_note(target, doc["rel"], ids, parsed,
                                        ignored_ids, by_base, vault_wide)
                if found is None:
                    if style == "inline":
                        report["skipped_assets"] += 1
                    file_rows.append((nid, sec, written, file_link_path(
                        written, doc["rel"]), "md"))
                    continue
                dst, status = found
                rows.append((nid, dst, written, "md", "link", status, sec))
            if anchor:
                anchor_rows.append(anchor_row(
                    nid, sec, dst, written, urllib.parse.unquote(anchor),
                    "md", status))
        for row_ in rows:
            cur = con.execute(
                "INSERT OR IGNORE INTO edges(src, dst, target, syntax, kind,"
                " status, section_id) VALUES (?,?,?,?,?,?,?)", row_)
            if cur.rowcount:
                key = ("ignored_links" if row_[5] == "ignored" else row_[5])
                if key in report:
                    report[key] += 1
        con.executemany(
            "INSERT OR IGNORE INTO anchors(src, section_id, dst, target,"
            " anchor, dst_section, dst_line, syntax, status)"
            " VALUES (?,?,?,?,?,?,?,?,?)", anchor_rows)
        con.executemany(
            "INSERT OR IGNORE INTO file_links(src, section_id, target, path,"
            " syntax) VALUES (?,?,?,?,?)", file_rows)
        for field, origin, syntax, target, off in memo.get(
                "scan_field_links", [h], lambda: list(scan_field_links(text))):
            if syntax == "wiki":
                dst, status = wiki_dst(target)
            else:
                found = resolve_md_note(target, doc["rel"], ids, parsed,
                                        ignored_ids, by_base, vault_wide)
                if found is None:
                    continue
                dst, status = found
            con.execute(
                "INSERT OR IGNORE INTO link_fields(src, field, origin,"
                " target, dst, status, section_id) VALUES (?,?,?,?,?,?,?)",
                (nid, field, origin, urllib.parse.unquote(target), dst,
                 status, _section_at(sections, off)))
        tag_counts: dict[tuple[str, str], int] = {}
        for tag, off in memo.get("scan_inline_tags", [h], lambda: list(scan_inline_tags(text))):
            key_ = (_section_at(sections, off), tag)
            tag_counts[key_] = tag_counts.get(key_, 0) + 1
        if nid not in dirty:
            continue        # its inline tags and code spans are already stored
        con.executemany(
            "INSERT INTO inline_tags(note_id, section_id, tag, count)"
            " VALUES (?,?,?,?)",
            [(nid, sec, tag, n) for (sec, tag), n in sorted(tag_counts.items())])
        con.executemany(
            "INSERT OR IGNORE INTO code_spans(note_id, section_id, text,"
            " line) VALUES (?,?,?,?)",
            [(nid, _section_on_line(sections, line), span, line)
             for span, line in memo.get("scan_code_spans", [h],
                                        lambda: list(scan_code_spans(text)))])

    for (token, kind), n in sorted(cand_counts.items()):
        con.execute(
            "INSERT INTO annotation_candidates(token, kind, count)"
            " VALUES (?,?,?)", (token, kind, n))

    ent_report = load_entities(con, cfg, all_sections, [
        {"id": nid, "rel": parsed[nid]["rel"], "meta": parsed[nid]["meta"],
         "title": parsed[nid]["title"], "aliases": parsed[nid]["aliases"]}
        for nid in ids], memo)
    report.update(ent_report)
    memo.flush()

    if incremental:
        con.execute(
            "INSERT INTO sections_fts(rowid, id, heading_path, body)"
            " SELECT rowid, id, heading_path, body FROM sections"
            " WHERE note_id IN (SELECT id FROM dirty_notes)")
    else:
        con.execute("INSERT INTO sections_fts(sections_fts) VALUES ('rebuild')")
    # Every note, not only the dirty ones: `git add` changes a label, never bytes.
    paths = [parsed[nid]["rel"] for nid in ids]
    con.executemany("UPDATE notes SET git = ? WHERE path = ?",
                    [(g, p) for p, g in git_status(vault, paths).items()])
    con.execute("INSERT INTO meta(key, value) VALUES ('ingest_basis', ?)", (basis,))
    con.execute("INSERT INTO meta(key, value) VALUES ('per_note_counts', ?)",
                (_row_counts(con),))
    con.execute("INSERT INTO meta(key, value) VALUES ('ingested_at', ?)",
                (now_utc(),))
    con.commit()
    con.execute("INSERT INTO meta(key, value) VALUES ('manifest', ?)",
                (fingerprint,))
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


def _section_on_line(sections: list[dict], line: int) -> str:
    """The smallest indexed section whose line range holds a line."""
    best, best_size = "", None
    for sec in sections:
        if sec["line_start"] <= line <= sec["line_end"]:
            size = sec["line_end"] - sec["line_start"]
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


def _case_fold_tables() -> tuple[dict, dict] | None:
    """Tables that fold text the way re.IGNORECASE compares it, character by
    character: U+0130 to its one-character lowercase, then str.lower(), then each
    of re's extra equivalence groups (dotless i, long s, Greek variants) to one
    member. None when this Python hides the groups; callers then skip the fold."""
    try:
        from re import _casefix
        groups = [(k, *v) for k, v in _casefix._EXTRA_CASES.items()]
    except Exception:           # private API: any change in a new Python turns the fold off
        try:
            import sre_compile
            groups = [tuple(g) for g in sre_compile._equivalences]
        except Exception:
            return None
    equiv = {}
    for group in groups:
        rep = chr(min(group))
        for cp in group:
            equiv[cp] = rep
    return {0x130: "i"}, equiv


_FOLD = _case_fold_tables()


def case_fold(text: str) -> str | None:
    """`text` folded so that a case-insensitive alias match implies the folded
    alias is a substring of it; None when the fold is unavailable."""
    if _FOLD is None:
        return None
    if text.isascii():          # both tables leave ASCII unchanged
        return text.lower()
    return text.translate(_FOLD[0]).lower().translate(_FOLD[1])


ENTITY_NAME_MIN = 3      # a derived name shorter than this matches too much
ENTITY_NAME_MAX = 120


def entity_source_for(rel_path: str, meta: dict, cfg: dict) -> dict | None:
    """The `entity_sources` row that makes this note an entity, or None.
    Resolved the way profiles are: the longest matching path glob, then a
    `kg_type` row matching the note's own `kg-type:` frontmatter."""
    best, best_len = None, -1
    for row in cfg.get("entity_sources", []):
        pat = str(row.get("path", "")).strip()
        if pat and glob_match(rel_path, pat) and len(pat) > best_len:
            best, best_len = row, len(pat)
    if best:
        return best
    ktype = str(meta.get("kg-type", "")).strip().lower()
    if ktype:
        for row in cfg.get("entity_sources", []):
            if str(row.get("kg_type", "")).strip().lower() == ktype:
                return row
    return None


def derive_entities(con: sqlite3.Connection, cfg: dict, notes: list[dict],
                    seen_alias: dict[str, str], explicit_notes: set[str],
                    pairs: list[tuple[str, str]]) -> int:
    """Entities from notes an `entity_sources` row matches: the title is the
    canonical name, the file name and frontmatter aliases are aliases, and
    the note is the entity's own page. A hand-written `entities` row always
    wins. Note content must never be able to fail an ingest, so a derived
    name that collides or is too short is left out and recorded in
    `entity_skips`, where the hand-written registry fails loudly instead."""
    derived = 0

    def skip(note_id: str, name: str, reason: str) -> None:
        con.execute("INSERT OR IGNORE INTO entity_skips(note_id, name, reason)"
                    " VALUES (?,?,?)", (note_id, name, reason))

    def usable(note_id: str, name: str) -> bool:
        if not _single_line(name) or len(name) > ENTITY_NAME_MAX:
            skip(note_id, name[:ENTITY_NAME_MAX], "not one short line")
        elif len(name) < ENTITY_NAME_MIN:
            skip(note_id, name, f"shorter than {ENTITY_NAME_MIN} characters")
        elif name.lower() in seen_alias:
            skip(note_id, name, f"claimed by {seen_alias[name.lower()]!r}")
        else:
            return True
        return False

    for note in sorted(notes, key=lambda n: n["id"]):
        row = entity_source_for(note["rel"], note["meta"], cfg)
        if row is None:
            continue
        canonical = note["title"].strip()
        if note["id"].lower() in explicit_notes:
            skip(note["id"], canonical, "an entities row already names this"
                                        " note")
            continue
        if not usable(note["id"], canonical):
            continue
        time = str(row.get("time", "") or "static").strip()
        con.execute(
            "INSERT OR REPLACE INTO entities(canonical, type, time, note,"
            " t_start, t_end, origin) VALUES (?,?,?,?,'','','note')",
            (canonical, str(row.get("type", "")), time, note["id"]))
        seen_alias[canonical.lower()] = canonical
        names = [canonical]
        for name in [note["id"].rsplit("/", 1)[-1]] + list(note["aliases"]):
            name = str(name).strip()
            if name and name.lower() != canonical.lower() \
                    and usable(note["id"], name):
                seen_alias[name.lower()] = canonical
                names.append(name)
        for name in names:
            con.execute("INSERT OR IGNORE INTO entity_aliases(canonical, alias)"
                        " VALUES (?,?)", (canonical, name))
            pairs.append((name, canonical))
        derived += 1
    return derived


def load_entities(con: sqlite3.Connection, cfg: dict, sections: list[dict],
                  notes: list[dict] | None = None, memo: ParseCache | None = None) -> dict:
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

    derived = 0
    if notes and cfg.get("entity_sources"):
        explicit_notes = set()
        for row in rows:
            ref = str(row.get("note", "")).strip().strip("/").lower()
            if ref:
                explicit_notes.add(ref[:-3] if ref.endswith(".md") else ref)
        derived = derive_entities(con, cfg, notes, seen_alias, explicit_notes,
                                  pairs)

    # longest alias first, so a longer name is never eaten by a shorter one
    pairs.sort(key=lambda p: (-len(p[0]), p[0]))
    compiled = [(case_fold(name), alias_pattern(name), canonical) for name, canonical in pairs]
    gazetteer = hashlib.sha256(json.dumps(pairs).encode()).hexdigest()

    def count_mentions(own_body: str) -> dict[str, int]:
        # own_body, so a name inside a child section is counted against that
        # child and not a second time against the unit that contains it
        text = strip_code(own_body)
        folded = case_fold(text)
        claimed = [False] * len(text)
        counts: dict[str, int] = {}
        for alias_folded, pattern, canonical in compiled:
            # A cheap substring test first: the regex can only match where the
            # folded alias occurs, and most sections name no entity at all.
            if folded is not None and alias_folded not in folded:
                continue
            for m in pattern.finditer(text):
                if any(claimed[m.start():m.end()]):
                    continue
                for i in range(m.start(), m.end()):
                    claimed[i] = True
                counts[canonical] = counts.get(canonical, 0) + 1
        return counts

    mentions = 0
    for sec in sections:
        own = sec["own_body"]
        counts = (memo.get("mentions", [hashlib.sha256(own.encode()).hexdigest(), gazetteer],
                           lambda: count_mentions(own))
                  if memo is not None else count_mentions(own))
        for canonical in sorted(counts):
            con.execute(
                "INSERT OR REPLACE INTO mentions(canonical, section_id,"
                " note_id, doc_date, count) VALUES (?,?,?,?,?)",
                (canonical, sec["id"], sec["note_id"], sec["doc_date"],
                 counts[canonical]))
            mentions += 1
    return {"entities": len(rows) + derived, "mentions": mentions}


# ---------- staleness ----------
def ensure_fresh(vault: Path) -> None:
    STORE.refresh(vault, lambda v: scan_vault(v, every=True), manifest,
                  lambda v, w: ingest(v, walked=w))


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


def record_session_reads(vault: Path, session: str | None,
                         section_ids: list[str], cmd: str) -> None:
    """Append surfaced section ids to a per-session coverage ledger. First
    touch wins. Errors are loud: a session flag that quietly stops recording
    corrupts the caller's coverage map."""
    if not session or not section_ids:
        return
    con = connect(vault, must_exist=True)
    at = now_utc()
    con.executemany(
        "INSERT OR IGNORE INTO session_reads"
        " (session_id, section_id, note_id, cmd, at)"
        " SELECT ?, id, note_id, ?, ? FROM sections WHERE id=?",
        [(session, cmd, at, sid) for sid in section_ids])
    con.commit()
    con.close()


def _top_segment(heading_path: str) -> str:
    return heading_path.split(" > ", 1)[0] if heading_path else "(top)"


def coverage(vault: Path, session: str, scope: str | None = None,
             limit: int = 20) -> dict:
    """Session coverage against the current graph. Touched means surfaced to
    the caller by a read-path command carrying --session. A touched section
    covers itself and its descendants (its body contains theirs); a child
    never covers its parent; an empty heading path covers only itself, since
    an empty prefix would otherwise cover the whole note."""
    con = open_fresh(vault)
    secs = con.execute(
        "SELECT id, note_id, heading_path, words FROM sections").fetchall()
    ledger = {r[0] for r in con.execute(
        "SELECT section_id FROM session_reads WHERE session_id=?",
        (session,))}
    con.close()

    stale = len(ledger - {r[0] for r in secs})
    if scope:
        secs = [r for r in secs
                if glob_match(r[1] + ".md", scope) or glob_match(r[1], scope)]

    by_note: dict[str, list[tuple]] = {}
    for sid, nid, hpath, words in secs:
        by_note.setdefault(nid, []).append((sid, hpath, words))

    covered: set[str] = set()
    for nid, rows in by_note.items():
        prefixes = [hp + " > " for sid, hp, _ in rows
                    if sid in ledger and hp]
        for sid, hp, _ in rows:
            if sid in ledger or any(hp.startswith(p) for p in prefixes):
                covered.add(sid)

    sec_total = len(secs)
    sec_touched = len(covered)
    word_total = sum(w for _, _, _, w in secs)
    word_touched = sum(w for sid, _, _, w in secs if sid in covered)
    note_total = len(by_note)
    note_touched = sum(1 for rows in by_note.values()
                       if any(sid in covered for sid, _, _ in rows))

    def pct(t: int, total: int) -> float:
        return round(100.0 * t / total, 1) if total else 0.0

    untouched: list[dict] = []
    for nid in sorted(by_note):
        rows = by_note[nid]
        if not any(sid in covered for sid, _, _ in rows):
            untouched.append({"kind": "note", "note_id": nid,
                              "sections": len(rows),
                              "words": sum(w for _, _, w in rows)})
            continue
        groups: dict[str, list[tuple]] = {}
        for sid, hp, w in rows:
            groups.setdefault(_top_segment(hp), []).append((sid, w))
        for seg in sorted(groups):
            members = groups[seg]
            if any(sid in covered for sid, _ in members):
                continue
            untouched.append({"kind": "subtree", "note_id": nid,
                              "heading": seg, "sections": len(members),
                              "words": sum(w for _, w in members)})
    untouched.sort(key=lambda u: (-u["words"], u["note_id"],
                                  u.get("heading", "")))
    total_untouched = len(untouched)
    if limit:
        untouched = untouched[:limit]
    return {
        "session": session, "scope": scope,
        "sections": {"touched": sec_touched, "total": sec_total,
                     "percent": pct(sec_touched, sec_total)},
        "words": {"touched": word_touched, "total": word_total,
                  "percent": pct(word_touched, word_total)},
        "notes": {"touched": note_touched, "total": note_total,
                  "percent": pct(note_touched, note_total)},
        "stale": stale,
        "untouched": untouched,
        "status": ("COMPLETE" if len(untouched) == total_untouched
                   else f"TRUNCATED {len(untouched)} of {total_untouched}"),
    }


# ---------- search ----------
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
           slot: str | None = None, recency_k: float | None = None,
           path: str | None = None, git: str = "all") -> dict:
    con = open_fresh(vault)
    if recency_k is None:
        recency_k = load_config(vault).get("recency_k", RECENCY_K)
    phrases, terms = tokenize(question, STOPWORDS)
    if not phrases and not terms:
        con.close()
        return {"query": question, "rung": None, "capped": False,
                "status": "COMPLETE", "total": 0, "results": []}
    deg = _degree(con, skip_hubs=True)
    max_deg = max(deg.values()) if deg else 1
    rows: list[sqlite3.Row] = []
    used_rung = None
    # The slot filter runs inside the query, before the row cap. Applied after
    # it, the cap was taken by whichever notes match the term most densely (a
    # copied book, a quotes file), and a long generated section of a journal
    # ranked past the cap among all matches was dropped before the filter
    # could keep it.
    slot_sql = ((" AND s.slot = ?" if slot else "")
                + " AND (? = 'all' OR n.git = ?)"
                + path_filter(con, path, "n.path"))
    for name, expr in search_rungs(phrases, terms):
        params = (expr,) + ((slot,) if slot else ()) + (git, git)
        try:
            rows = con.execute(
                "SELECT s.id, s.note_id, s.heading_path, s.doc_date, s.slot,"
                " s.line_start, s.line_end, s.words, s.is_unit, s.oversize,"
                " n.title, n.weight, n.path, n.git,"
                " bm25(sections_fts) AS rank,"
                " snippet(sections_fts, 2, '[', ']', ' ... ', 14)"
                " FROM sections_fts"
                " JOIN sections s ON s.rowid = sections_fts.rowid"
                " JOIN notes n ON n.id = s.note_id"
                " WHERE sections_fts MATCH ?" + slot_sql +
                f" ORDER BY rank LIMIT {SEARCH_ROW_CAP}",
                params).fetchall()
        except sqlite3.OperationalError:
            continue
        if rows:
            used_rung = name
            break
    if not rows:
        con.close()
        return {"query": question, "rung": None, "capped": False,
                "status": "COMPLETE", "total": 0, "results": []}

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
         oversize, title, weight, npath, ngit, rank, snip) = r
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
            "section_id": sid, "note_id": nid, "path": npath, "git": ngit,
            "title": title,
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
    capped = len(rows) >= SEARCH_ROW_CAP

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
        result = {"query": question, "rung": used_rung, "capped": capped,
                  "budget": budget, "spent": spent,
                  "total": total, "results": packed[:limit] if limit else packed}
        result["status"] = ("COMPLETE" if len(result["results"]) == total
                            else f"TRUNCATED {len(result['results'])} of {total}")
        con.close()
        return result

    con.close()
    out = kept[:limit]
    return {"query": question, "rung": used_rung, "capped": capped, "total": total,
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
    phrases, terms = tokenize(term, STOPWORDS)
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


def _diff_rows(con: sqlite3.Connection) -> dict[str, tuple]:
    return {r[0]: r for r in con.execute(
        "SELECT id, note_id, heading_path, heading, section_hash, body"
        " FROM sections")}


def diff(vault: Path, against: str | None = None) -> dict:
    """What changed between the live graph and a checkpoint or another vault's
    db. Read-only on the against side; complete or erroring, never truncated."""
    with contextlib.closing(open_fresh(vault)) as con:
        against, old_con = STORE.open_against(vault, against,
                                              ("sections", "notes"))
        with contextlib.closing(old_con):
            new, old = _diff_rows(con), _diff_rows(old_con)
            new_notes, old_notes = (
                dict(c.execute("SELECT id, content_hash FROM notes"))
                for c in (con, old_con))

    # An id match alone is not an edit: an insertion in a run of repeated
    # heading paths shifts every later sibling's ~n ordinal, which the
    # ordinal-shift pass in `classify_units` pairs back as unchanged.
    def units(rows: dict) -> dict:
        return {sid: (sid, r[1], r[4], _stripped_hash(r[5], r[3]),
                      r[2] or "(top)") for sid, r in rows.items()}

    return {"against": against, "notes": changed_keys(new_notes, old_notes),
            **unit_diff(units(old), units(new), "section_id", "heading_path")}


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


# ---------- aggregates ----------
def has_log_dated(con: sqlite3.Connection) -> bool:
    return con.execute(
        "SELECT 1 FROM notes WHERE profile = 'log-dated' LIMIT 1").fetchone() is not None


def window_sections(con: sqlite3.Connection, frm: str | None, to: str | None,
                    slot: str | None) -> list[tuple[str, str]]:
    """Aggregates count `own_body`, never `body`: a unit's body contains its
    children, so counting bodies would count a generated or instrument slot as
    the author's own words no matter how it is labelled.

    Only log-dated notes count. Ingest stamps a note's frontmatter date onto its
    undated sections whatever the profile, so without this filter a dated
    reference, hub or generated note would count as the author's own log."""
    sql = ("SELECT s.id, s.own_body FROM sections s JOIN notes n ON n.id = s.note_id"
           " WHERE s.doc_date != '' AND n.profile = 'log-dated'")
    params: list = []
    if frm:
        sql += " AND s.doc_date >= ?"
        params.append(frm)
    if to:
        sql += " AND s.doc_date <= ?"
        params.append(to)
    if slot:
        sql += " AND s.slot = ?"
        params.append(slot)
    return con.execute(sql + " ORDER BY s.id", params).fetchall()


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
    if not has_log_dated(con):
        con.close()
        return {"from": frm or "", "to": to or "", "slot": slot, "sections": 0,
                "words": 0, "terms": [], "status": "NO_LOG_DATED_NOTES"}
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
            "terms": out[:limit], "status": "COMPLETE"}


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
    if not has_log_dated(con):
        con.close()
        return {"by": by, "slot": slot, "windows": [], "status": "NO_LOG_DATED_NOTES"}
    # log-dated notes only, for the reason window_sections gives
    rows = con.execute(
        "SELECT s.doc_date, s.own_body FROM sections s JOIN notes n ON n.id = s.note_id"
        " WHERE s.doc_date != '' AND n.profile = 'log-dated'"
        + (" AND s.slot=?" if slot else "") + " ORDER BY s.doc_date",
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
        # Term breaks ties: the candidates come out of a set, whose order
        # changes with the hash seed, and equal scores are the common case.
        moves.sort(key=lambda r: (-r["log_likelihood"], r["term"]))
        out.append({"window": cur, "previous": prev,
                    "rose": moves[:limit],
                    "fell": list(reversed(moves[-limit:]))})
    return {"by": by, "slot": slot, "windows": out, "status": "COMPLETE"}


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
             "the vault's config if a retrieval needed it")


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
                 "(set time to '<start>..<end>' in"
                 f" {config_path(vault).relative_to(vault).as_posix()})")
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
             "generator: markdown_kg.py index", "---", "",
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
    vault = vault_dir(args.vault)
    with STORE.rebuild_lock(vault):
        r = ingest(vault, keep_previous=args.keep_previous)
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
    # The config is written here, so a link planted at it is refused too.
    refused = linked_store(vault, kg_dir(vault), config_path(vault))
    if refused:
        sys.exit(f"error: {refused}")
    if kg_dir(vault).name in LEGACY_LAYOUTS:
        sys.exit(f"error: this vault's graph is in the legacy "
                 f"{kg_dir(vault).name}/ folder - run `migrate` first")
    cfg_file = config_path(vault)
    if cfg_file.exists() and not args.force:
        sys.exit(f"error: {cfg_file} already exists - edit it directly, or "
                 f"pass --force to rewrite the scaffold")
    with STORE.rebuild_lock(vault):
        ingest(vault)
        found = detect(vault)
        cfg = {"profiles": [], "entities": []}
        for row in found["dated_logs"]:
            cfg["profiles"].append({"path": row["path"],
                                    "profile": "log-dated",
                                    "date_from": "heading",
                                    "date_order": row["date_order"]})
        for row in found["generated"]:
            cfg["profiles"].append({"path": row["path"],
                                    "profile": "generated", "weight": 0.2})
        write_config(vault, cfg)
        ingest(vault)
    print(f"init: wrote {cfg_file} with {len(cfg['profiles'])} confident "
          f"profile rows ({len(found['dated_logs'])} dated logs, "
          f"{len(found['generated'])} generated)")
    print(f"      db at {db_path(vault)}; {kg_dir(vault).name}/.gitignore keeps the databases"
          " out of git, and the config is committed with the vault")
    return 0


def cmd_migrate(args: argparse.Namespace) -> int:
    return emit(args, migrate(vault_dir(args.vault)), render_migrate)


def cmd_profile(args: argparse.Namespace) -> int:
    vault = vault_dir(args.vault)
    found = detect(vault)
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
          f"{config_path(vault).relative_to(vault).as_posix()}.")
    return 0


def cmd_query(args: argparse.Namespace) -> int:
    vault = vault_dir(args.vault)
    try:
        rows = query(vault, args.fts_query, args.limit, args.path, args.git)
    except ValueError as e:
        sys.exit(f"error: {e}")
    payload = [{"section_id": r["section_id"], "note_id": r["note_id"],
                "heading_path": r["heading_path"] or "(top)",
                "lines": r["lines"], "snippet": r["snippet"], "git": r["git"]}
               for r in rows]
    record_session_reads(vault, args.session,
                         [h["section_id"] for h in payload], "query")

    def render(rows_):
        if not rows_:
            print("no matches")
            return 0
        for h in rows_:
            print(f"{h['section_id']}  [{h['lines']}]\n    {h['snippet']}")
        return 0
    return emit(args, payload, render)


def query(vault: Path, q: str, limit: int = 20,
          path: str | None = None, git: str = "all") -> list[dict]:
    """Library entry point for raw FTS5 search over sections."""
    con = open_fresh(vault)
    try:
        rows = con.execute(
            "SELECT s.id, s.note_id, s.heading_path, s.line_start, s.line_end,"
            " snippet(sections_fts, 2, '[', ']', ' ... ', 14), n.git"
            " FROM sections_fts JOIN sections s ON s.rowid = sections_fts.rowid"
            " JOIN notes n ON n.id = s.note_id"
            " WHERE sections_fts MATCH ? AND (? = 'all' OR n.git = ?)"
            + path_filter(con, path, "n.path")
            + " ORDER BY bm25(sections_fts) LIMIT ?",
            (q, git, git, limit)).fetchall()
    except sqlite3.OperationalError as e:
        con.close()
        raise ValueError(f"invalid FTS5 query {q!r}: {e}") from e
    con.close()
    return [{"section_id": r[0], "id": r[1], "note_id": r[1],
             "heading_path": r[2], "lines": f"{r[3]}-{r[4]}", "snippet": r[5],
             "git": r[6]} for r in rows]


def cmd_search(args: argparse.Namespace) -> int:
    vault = vault_dir(args.vault)
    payload = search(vault, args.question, args.limit,
                     args.per_note, args.budget, args.slot, args.recency_k,
                     args.path, args.git)
    record_session_reads(vault, args.session,
                         [h["section_id"] for h in payload["results"]],
                         "search")

    def render(res):
        if not res["results"]:
            print(f"no matches for {res['query']!r}")
            return 0
        print(f"{res['status']}  (rung: {res['rung']})"
              + ("  CAPPED - only the best-ranked matches were scored;"
                 " narrow the query or add --slot" if res.get("capped") else ""))
        for h in res["results"]:
            head = f"{h['section_id']}  [{h['lines']}]"
            if h.get("doc_date"):
                head += f"  {h['doc_date']}"
            print(head)
            if "text" in h:
                print(h["text"].rstrip())
                print("---")
            else:
                print(f"    {h['snippet']}")
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
        if "properties" in p:
            for e in p["properties"]:
                print(f"{e['key']}: {e['value']}")
        elif "keys" in p:
            for e in p["keys"]:
                print(f"{e['key']}  ({e['notes']} notes)")
        elif "missing" in p:
            for nid in p["missing"]:
                print(nid)
            print(f"{len(p['missing'])} note(s) without '{p['key']}'")
        else:
            for e in p["notes"]:
                print(f"{e['note_id']}  {e['value']}")
            print(f"{len(p['notes'])} note(s) matched")
            for e in p.get("unparsed", []):
                print(f"unparsed: {e['note_id']}  {e['value']!r}")
        return 0
    return emit(args, payload, render)


def cmd_annotations(args: argparse.Namespace) -> int:
    payload = annotations_list(vault_dir(args.vault), args.marker, args.note,
                               args.older_than, args.newer_than, args.limit)

    def render(p):
        current = None
        for e in p["annotations"]:
            if e["marker"] != current:
                current = e["marker"]
                print(f"{current}:")
            where = e["section_id"] or e["note_id"]
            extra = f"  [{e['date']}]" if e["date"] else ""
            print(f"  {where}:{e['line']}{extra}  {e['payload']}")
        print(f"{p['status']}  ({p['total']} annotation(s))")
        for e in p.get("unparsed", []):
            print(f"unparsed: {e['marker']}"
                  f"  {e['section_id'] or e['note_id']}:{e['line']}"
                  f"  {e['payload']}")
        return 0
    return emit(args, payload, render)


def cmd_diff(args: argparse.Namespace) -> int:
    payload = diff(vault_dir(args.vault), args.against)

    def render(d):
        for bucket in ("added", "removed"):
            for e in d[bucket]:
                print(f"{bucket}: {e['section_id']}  ({e['heading_path']})")
        for bucket in ("edited", "renamed", "moved"):
            for e in d[bucket]:
                arrow = ("" if e["from_id"] == e["to_id"]
                         else f" -> {e['to_id']}")
                print(f"{bucket}: {e['from_id']}{arrow}")
        n = d["notes"]
        if any(n.values()):
            names = ", ".join(n["added"] + n["removed"] + n["edited"])
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
                  f"{d['section_id']}  [{d['lines']}]  "
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
    record_session_reads(vault, args.session,
                         [h["section_id"] for h in payload], "sections")

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
    record_session_reads(vault, args.session, [payload["section_id"]], "read")

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


ANCHOR_COLS = ("src", "section_id", "dst", "target", "anchor", "dst_section",
               "dst_line", "syntax", "status")


def cmd_link_anchors(args: argparse.Namespace, con: sqlite3.Connection,
                     inbound: bool) -> int:
    """`links --anchors` and `backlinks --anchors`: the links that name a
    heading or a block, with the section each one resolved to. With
    `--unresolved` the list is the anchors whose note exists and whose
    heading or block does not - a broken note is already in the plain
    `links --unresolved` worklist."""
    sql = f"SELECT {', '.join(ANCHOR_COLS)} FROM anchors"
    where, params = [], []
    if args.note is not None:
        nid = resolve_note_arg(con, args.note)
        where.append("dst=? AND status='resolved'" if inbound else "src=?")
        params.append(nid)
    elif not getattr(args, "unresolved", False):
        con.close()
        sys.exit("error: links --anchors needs a note (or --unresolved for"
                 " the whole vault)")
    if getattr(args, "unresolved", False):
        where.append("status='anchor-missing'")
    rows = con.execute(
        sql + (" WHERE " + " AND ".join(where) if where else "")
        + " ORDER BY src, section_id, syntax, target, anchor",
        params).fetchall()
    con.close()
    payload = [dict(zip(ANCHOR_COLS, r)) for r in rows]

    def render(rows_):
        if not rows_:
            print("no anchored links")
            return 0
        for e in rows_:
            where_ = f"  in {e['section_id']}" if e["section_id"] else ""
            name = e["target"] or "(this note)"
            here = f"{e['dst_section'] or e['dst']} (line {e['dst_line']})"
            if inbound:
                print(f"{e['syntax']}  {here}  <-  "
                      f"{e['src']}  (as {name!r} # {e['anchor']!r}){where_}")
            elif e["status"] == "resolved":
                print(f"{e['syntax']}  ->  {here}  "
                      f"(as {name!r} # {e['anchor']!r}){where_}")
            else:
                print(f"{e['syntax']}  ->  {e['status'].upper()}  "
                      f"(as {name!r} # {e['anchor']!r}) from {e['src']}"
                      f"{where_}")
        return 0
    return emit(args, payload, render)


def cmd_links(args: argparse.Namespace) -> int:
    vault = vault_dir(args.vault)
    con = open_fresh(vault)
    if getattr(args, "anchors", False):
        return cmd_link_anchors(args, con, inbound=False)
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
    if getattr(args, "anchors", False):
        return cmd_link_anchors(args, con, inbound=True)
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
    return bfs_path(
        {n: {other for other, _ in edges} for n, edges in adj.items()}, a, b)


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
        print(f"no path between {args.a} and {args.b}")
        return 1
    print(" -> ".join(chain))
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
    ruled = relation_ruling(args, lambda: open_fresh(vault_dir(args.vault)))
    if ruled is not None:
        return ruled
    payload = relations_list(vault_dir(args.vault), args.note,
                             args.include_cold, args.conflicts)

    def render(p):
        for r in p["relations"]:
            mark = f"  [{r['status']}]" if r["status"] != "hot" else ""
            print(f"#{r['id']}  {r['subject']} -[{r['predicate']}]->"
                  f" {r['object']}{mark}  ({r['section_id']})")
        print(f"{len(p['relations'])} inferred relation(s)")
        for c in p.get("conflicts", []):
            res = f"  resolution: {c['resolution']}" if c["resolution"] else ""
            print(f"conflict #{c['seq']} [{c['state']}]  {c['key']}"
                  f"  #{c['a']} vs #{c['b']}{res}")
        return 0
    return emit(args, payload, render)


# ---------- links to files, and the code-kg skill ----------
def file_refs(con: sqlite3.Connection, path: str) -> list[dict]:
    """The sections that link to one file, by vault-relative path. A
    markdown link matches on the path it resolves to. A wikilink names a
    file the way Obsidian finds one, by the end of its path, so it matches
    when the path ends with what was written."""
    path = posixpath.normpath(path)
    tail = "/" + path.lower()
    rows = con.execute(
        "SELECT f.src, n.path, f.section_id, COALESCE(s.heading_path, ''),"
        " s.line_start, s.line_end, f.target, f.syntax, f.path"
        " FROM file_links f JOIN notes n ON n.id = f.src"
        " LEFT JOIN sections s ON s.id = f.section_id"
        " WHERE f.path = ? OR f.syntax = 'wiki'"
        " ORDER BY f.src, s.line_start, f.target", (path,)).fetchall()
    return [{"src": r[0], "note_path": r[1], "section_id": r[2],
             "heading_path": r[3] or "(top)", "line_start": r[4],
             "line_end": r[5], "target": r[6], "syntax": r[7]}
            for r in rows
            if r[8] == path or tail.endswith("/" + r[8].lower())]


def cmd_refs(args: argparse.Namespace) -> int:
    vault = vault_dir(args.vault)
    con = open_fresh(vault)
    payload = file_refs(con, args.path)
    con.close()

    def render(rows_):
        if not rows_:
            print(f"no section links to {posixpath.normpath(args.path)}")
            return 0
        for r in rows_:
            where = (f"{r['section_id']}  L{r['line_start']}-{r['line_end']}"
                     if r["section_id"] else f"{r['src']}  (top)")
            print(f"{where}  ({r['syntax']} as {r['target']!r})")
        return 0
    return emit(args, payload, render)


# The code-kg skill, reached through its command line only. CODE_KG_DBS is
# where it keeps the database of a repo it has indexed, current folder first;
# the file marks the repo and is never opened from here.
SIBLING_CLI = (Path(__file__).resolve().parents[2]
               / "code-kg" / "scripts" / "code_kg.py")
CODE_KG_DBS = (".kg/code-kg.db", ".code-kg/code-kg.db")


def sibling_json(*argv: str) -> tuple[object, str]:
    return run_sibling(SIBLING_CLI, "code-kg", argv)


def find_code_repo(vault: Path) -> Path | None:
    """The nearest folder at or above the vault that code-kg has indexed,
    looking no higher than the repo the vault is in (the first folder that
    holds `.git`) and never as high as the home folder. A symlinked engine
    folder or database is passed over: that skill's refresh would write
    wherever the link points."""
    home = Path.home()
    for d in (vault, *vault.parents):
        if d == home:
            break
        dbs = [d / db for db in CODE_KG_DBS]
        if any(db.is_file() for db in dbs) and not any(
                db.is_symlink() or db.parent.is_symlink() for db in dbs):
            return d
        if os.path.lexists(d / ".git"):
            break
    return None


MENTION_CAP = 500       # distinct spans one `code --mentions` call resolves


def note_mentions(spans: dict[str, list[str]], repo: Path | None,
                  missing: list[str], linked: set[str]) -> list[dict]:
    """What code-kg makes of a note's code spans: a file, a symbol, several
    definitions (`ambiguous`), or one definition the name alone is weak
    evidence for (`weak`). A span that names nothing is left out. With no
    code graph to ask, every span comes back with a status of None.

    A symbol is `corroborated` when the same note also names or links the
    file that defines it. A bare name can coincide with an unrelated word
    (a config key called `project_dir`, say); the file beside it is the
    second piece of evidence. A path is its own evidence."""
    answers: dict[str, dict] = {}
    if repo is not None and spans:
        got, why = sibling_json("resolve", str(repo),
                                *list(spans)[:MENTION_CAP])
        if isinstance(got, list):
            answers = {r["text"]: r for r in got
                       if isinstance(r, dict) and "text" in r}
            if len(spans) > MENTION_CAP:
                missing.append(f"{len(spans) - MENTION_CAP} of {len(spans)}"
                               " spans not resolved")
        else:
            missing.append(why or "code-kg resolve: unexpected answer")
    out = []
    for text, sections in spans.items():
        r = answers.get(text, {})
        if r.get("status") == "none":
            continue
        out.append({"text": text, "status": r.get("status"),
                    "file": r.get("file"), "symbol": r.get("symbol"),
                    "kind": r.get("kind"), "lines": r.get("lines"),
                    "count": r.get("count"),
                    "candidates": r.get("candidates", []),
                    "sections": sections})
    named = linked | {m["file"] for m in out if m["status"] == "file"}
    for m in out:
        m["corroborated"] = m["status"] == "file" or (
            m["status"] == "symbol" and m["file"] in named)
    return out


def code_report(vault: Path, name: str, limit: int = 30,
                mentions: bool = False) -> dict:
    """The files one note links to, each with what the code graph holds for
    it: role, language, liveness tier, and inbound edges counted by kind.
    With `mentions`, also the files and symbols the note names in code
    spans. Whatever is missing - that skill, its database, a file it does
    not hold - is said in `missing` or on the file, and the links
    themselves are always returned."""
    con = open_fresh(vault)
    nid = resolve_note_arg(con, name)
    rows = con.execute(
        "SELECT path, section_id FROM file_links WHERE src=?"
        " ORDER BY path, section_id", (nid,)).fetchall()
    spans: dict[str, list[str]] = {}
    if mentions:
        for text, sid in con.execute(
                "SELECT text, section_id FROM code_spans WHERE note_id=?"
                " ORDER BY text, section_id", (nid,)):
            spans.setdefault(text, []).append(sid)
    con.close()
    files: dict[str, dict] = {}
    for path, sid in rows:
        f = files.setdefault(path, {
            "path": path, "repo_path": None, "sections": [], "indexed": None,
            "role": None, "language": None, "tier": None, "inbound": None})
        if sid and sid not in f["sections"]:
            f["sections"].append(sid)
    missing: list[str] = []
    tiers = None
    repo = find_code_repo(vault)
    if repo is None:
        missing.append(f"no code-kg database at or above {vault}: run that"
                       " skill's `ingest` on the repo")
    else:
        dead, why = sibling_json("dead", str(repo))
        if isinstance(dead, dict) and isinstance(dead.get("tiers"), dict):
            tiers = {f: tier for tier, members in dead["tiers"].items()
                     for f in members}
        else:
            missing.append(why or "code-kg dead: unexpected answer")
    if tiers is not None:
        prefix = vault.relative_to(repo).as_posix()
        asked = 0
        for f in files.values():
            rp = posixpath.normpath(posixpath.join(prefix, f["path"]))
            if rp == ".." or rp.startswith("../"):
                f["indexed"] = False        # the link leaves the repo
                continue
            f["repo_path"] = rp
            if asked >= limit:
                continue
            asked += 1
            got, _ = sibling_json("file", str(repo), rp)
            # code-kg also resolves a path by its ending; only the exact
            # file is the one the note linked.
            f["indexed"] = isinstance(got, dict) and got.get("file") == rp
            if f["indexed"]:
                f["role"], f["language"] = got.get("role"), got.get("language")
                f["tier"] = tiers.get(rp)
                kinds = [k for _, k in sorted({
                    (e["src"], e["kind"]) for e in got.get("inbound", [])})]
                f["inbound"] = {k: kinds.count(k) for k in sorted(set(kinds))}
        left = sum(1 for f in files.values() if f["indexed"] is None)
        if left:
            missing.append(f"{left} of {len(files)} files not looked up:"
                           f" raise --limit (now {limit})")
    out = {"note": nid, "repo": str(repo) if repo else None,
           "files": list(files.values()), "missing": missing}
    if mentions:
        out["spans"] = len(spans)
        out["mentions"] = note_mentions(
            spans, repo if tiers is not None else None, missing,
            {f["repo_path"] for f in files.values() if f["repo_path"]})
    return out


def cmd_code(args: argparse.Namespace) -> int:
    payload = code_report(vault_dir(args.vault), args.note, args.limit,
                          args.mentions)

    def render_mentions(p):
        print(f"mentions: {len(p['mentions'])} of {p['spans']} code spans")
        for m in p["mentions"]:
            line = f"  `{m['text']}`"
            if m["status"] in ("file", "symbol"):
                line += f"  {m['file']}"
                if m["symbol"]:
                    line += f"  {m['symbol']}  L{m['lines']}"
            elif m["status"] == "ambiguous":
                line += f"  ambiguous: {m['count']} definitions"
            elif m["status"] == "weak":
                c = m["candidates"][0]
                line += f"  weak: {c['file']}  {c['symbol']}"
            print(line)

    def render(p):
        print(f"{p['note']}: {len(p['files'])} linked files"
              + (f", code graph at {p['repo']}" if p["repo"] else ""))
        for f in p["files"]:
            line = f"  {f['repo_path'] or f['path']}"
            if f["indexed"]:
                line += "  " + ", ".join(
                    x for x in (f["role"], f["tier"]) if x)
                if f["inbound"]:
                    line += "  inbound: " + ", ".join(
                        f"{k} {n}" for k, n in f["inbound"].items())
            elif f["indexed"] is False:
                line += "  not in the code graph"
            print(line)
            for sid in f["sections"]:
                print(f"      in {sid}")
        if "mentions" in p:
            render_mentions(p)
        for line in p["missing"]:
            print(f"  {line}")
        return 0
    return emit(args, payload, render)


SPANS_LIMIT = 50
SPAN_COLS = ("text", "src", "note_path", "section_id", "heading_path",
             "line_start", "line_end", "line")


def cmd_spans(args: argparse.Namespace) -> int:
    """With no text: every distinct code span and how many sections hold
    it, most sections first. With texts: the sections that hold each one,
    primary docs first. `--limit` cuts either list after ranking."""
    con = open_fresh(vault_dir(args.vault))
    if args.text:
        payload = []
        for text in sorted(set(args.text)):
            rows = [dict(zip(SPAN_COLS, r)) for r in con.execute(
                "SELECT c.text, c.note_id, n.path, c.section_id,"
                " COALESCE(s.heading_path, '(top)'), s.line_start,"
                " s.line_end, c.line FROM code_spans c"
                " JOIN notes n ON n.id = c.note_id"
                " LEFT JOIN sections s ON s.id = c.section_id"
                " WHERE c.text=? ORDER BY c.note_id, c.line", (text,))]
            payload += sorted(rows, key=lambda r: doc_rank(r["note_path"]))
        rank = "primary docs first"
    else:
        payload = [{"text": t, "sections": n} for t, n in con.execute(
            "SELECT text, count(*) FROM code_spans GROUP BY text"
            " ORDER BY count(*) DESC, text")]
        rank = "most sections first"
    con.close()
    total = len(payload)
    if args.limit > 0 and total > args.limit:
        payload = payload[:args.limit]
    cut = (f"TRUNCATED {len(payload)} of {total}, {rank};"
           " --limit 0 for all" if len(payload) < total else "")
    if cut and getattr(args, "json", False):
        print(f"spans: {cut}", file=sys.stderr)

    def render(rows_):
        if not rows_:
            print("no code spans")
        for r in rows_:
            if "src" in r:
                print(f"`{r['text']}`  {r['section_id'] or r['src']}"
                      f"  line {r['line']}")
            else:
                print(f"{r['sections']:>5}  `{r['text']}`")
        if cut:
            print(cut)
        return 0
    return emit(args, payload, render)


# ---------- link fields ----------
FIELD_COLS = ("src", "field", "origin", "target", "dst", "status",
              "section_id")


def fields_report(vault: Path, field: str | None = None,
                  note: str | None = None) -> dict:
    """Links grouped by the field they were written under. With no argument,
    one row per field name; with `field`, every link under it; with `note`,
    the note's own field links and the ones that point at it, each inbound
    row carrying the inverse name a config `relations` row declares."""
    cfg = load_config(vault)
    inverse = {str(r.get("field", "")): str(r.get("inverse", ""))
               for r in cfg.get("relations", [])}
    con = open_fresh(vault)
    select = f"SELECT {', '.join(FIELD_COLS)} FROM link_fields"
    wanted = _field_name(field) if field else None
    if note is not None:
        nid = resolve_note_arg(con, note)
        clause, extra = ("", ())
        if wanted:
            clause, extra = " AND field=?", (wanted,)
        out = con.execute(select + " WHERE src=?" + clause
                          + " ORDER BY field, origin, target",
                          (nid,) + extra).fetchall()
        inbound = con.execute(select + " WHERE dst=? AND status='resolved'"
                              + clause + " ORDER BY field, src, origin",
                              (nid,) + extra).fetchall()
        con.close()
        return {"note": nid,
                "out": [dict(zip(FIELD_COLS, r)) for r in out],
                "in": [dict(zip(FIELD_COLS, r),
                            inverse=inverse.get(r[1], "")) for r in inbound]}
    if wanted:
        rows = con.execute(select + " WHERE field=? ORDER BY src, origin,"
                           " target", (wanted,)).fetchall()
        con.close()
        return {"field": wanted, "inverse": inverse.get(wanted, ""),
                "links": [dict(zip(FIELD_COLS, r)) for r in rows]}
    rows = con.execute(
        "SELECT field, count(*), sum(status='resolved'), count(DISTINCT src)"
        " FROM link_fields GROUP BY field").fetchall()
    con.close()
    seen = {r[0] for r in rows}
    rows += [(f, 0, 0, 0) for f in sorted(inverse) if f not in seen]
    return {"fields": [
        {"field": f, "links": n, "resolved": int(ok or 0), "notes": notes,
         "inverse": inverse.get(f, ""), "declared": f in inverse}
        for f, n, ok, notes in sorted(rows, key=lambda r: (-r[1], r[0]))]}


def cmd_fields(args: argparse.Namespace) -> int:
    payload = fields_report(vault_dir(args.vault), args.field, args.note)

    def line(e: dict, arrow: str, other: str, label: str) -> str:
        where = f"  in {e['section_id']}" if e["section_id"] else ""
        state = "" if e["status"] == "resolved" \
            else f"  {e['status'].upper()} (as {e['target']!r})"
        return f"{label}  {arrow}  {other}{state}  [{e['origin']}]{where}"

    def render(p):
        if "fields" in p:
            if not p["fields"]:
                print("no link fields")
                return 0
            for r in p["fields"]:
                inv = f"  (inverse: {r['inverse']})" if r["inverse"] else ""
                print(f"{r['links']:4d}  {r['field']}  "
                      f"{r['resolved']} resolved in {r['notes']} notes{inv}")
            return 0
        if "links" in p:
            if not p["links"]:
                print(f"no links under field {p['field']!r}")
                return 0
            for e in p["links"]:
                print(line(e, "->", e["dst"] or "?", e["src"]))
            return 0
        if not p["out"] and not p["in"]:
            print("no field links")
            return 0
        for e in p["out"]:
            print(line(e, "->", e["dst"] or "?", e["field"]))
        for e in p["in"]:
            print(line(e, "<-", e["src"], e["inverse"] or e["field"]))
        return 0
    return emit(args, payload, render)


# ---------- related notes: personalized PageRank ----------
def _note_graph(con: sqlite3.Connection, include_inferred: bool = False,
                keep: str | None = None) -> dict[str, dict[str, float]]:
    """Undirected weighted note graph over resolved edges, hubs removed. Two
    notes joined by several links (a wikilink and an embed, or links both
    ways) weigh more than a pair joined once. `keep` names one note that
    stays in even if it is a hub."""
    hubs = _hub_notes(con) - {keep}
    graph: dict[str, dict[str, float]] = {}
    for a, others in sorted(_adjacency(con, include_inferred).items()):
        if a in hubs:
            continue
        for b, _ in sorted(others):
            if b in hubs or b == a:
                continue
            graph.setdefault(a, {})
            graph[a][b] = graph[a].get(b, 0.0) + 1.0
    return graph


def related(vault: Path, name: str, limit: int = 10,
            include_inferred: bool = False) -> dict:
    """Notes ranked by personalized PageRank from one seed note.

    A walker starts on the seed and follows links at random; at every step it
    returns to the seed with probability 1 - damping. A note's score is the
    share of time the walker spends on it, so a note scores high when many
    short, independent link paths lead to it from the seed - which a
    neighbor list cannot show, because it ranks every two-hop note the same.

    The score measures position in the link graph, not similarity of
    content: it only knows what the corpus links. Hub notes are left out for
    the reason `neighbors` never walks through one. Fixed damping, no
    randomness, sorted iteration: the same graph always returns the same
    ranking."""
    con = open_fresh(vault)
    nid = resolve_note_arg(con, name)
    graph = _note_graph(con, include_inferred, keep=nid)
    con.close()
    if not graph.get(nid):
        return {"note": nid, "status": "NO_LINKS", "related": [],
                "nodes": 1, "iterations": 0, "damping": RELATED_DAMPING}
    return {"note": nid, **rank_from(graph, nid, limit)}


def cmd_related(args: argparse.Namespace) -> int:
    payload = related(vault_dir(args.vault), args.note, args.limit,
                      include_inferred=args.include_inferred)

    def render(p):
        if p["status"] == "NO_LINKS":
            print(f"{p['note']} has no resolved links to rank from")
            return 0
        print(f"Ranked by link-graph proximity to {p['note']}, not by"
              " content: read a note before treating it as relevant.")
        for r in p["related"]:
            print(f"  {r['score']:.4f}  {r['hops']} hop"
                  f"{'' if r['hops'] == 1 else 's'}  {r['id']}")
        if p["status"] != "COMPLETE":
            print(p["status"])
        return 0
    return emit(args, payload, render)


# ---------- communities ----------
def communities(vault: Path, include_inferred: bool = False) -> dict:
    """Clusters of notes that link to each other far more than to the rest
    of the vault. Read `modularity` first: above about 0.3 the groups are
    real structure, near zero the vault has none and the split is
    arbitrary. Hub notes are left out, since an index links everything to
    everything; a note with no resolved link cannot be placed and is listed
    under `unplaced`."""
    con = open_fresh(vault)
    adj = _note_graph(con, include_inferred)
    hubs = sorted(_hub_notes(con))
    all_notes = [r[0] for r in con.execute("SELECT id FROM notes ORDER BY id")]
    con.close()
    deg = {n: sum(w.values()) for n, w in adj.items()}
    m = sum(deg.values()) / 2.0
    comm = greedy_modularity(adj, deg, m)
    groups: dict[int, list[str]] = {}
    for node, cid in comm.items():
        groups.setdefault(cid, []).append(node)
    kept = [sorted(g) for g in groups.values() if len(g) > 1]

    def label(notes: list[str]) -> str:
        inside = set(notes)
        return min(notes, key=lambda n: (-sum(
            w for b, w in adj[n].items() if b in inside), n))

    kept.sort(key=lambda g: (-len(g), label(g), g))
    placed = {n for g in kept for n in g}
    out, q = [], 0.0
    for idx, notes in enumerate(kept):
        inside = set(notes)
        internal = sum(w for a in notes for b, w in adj[a].items()
                       if b in inside) / 2.0
        external = sum(w for a in notes for b, w in adj[a].items()
                       if b not in inside)
        out.append({"id": idx, "label": label(notes), "size": len(notes),
                    "notes": notes, "internal_edges": int(internal),
                    "external_edges": int(external)})
    for notes in kept + [[n] for n in sorted(adj) if n not in placed]:
        inside = set(notes)
        in_w = sum(w for a in notes for b, w in adj[a].items()
                   if b in inside) / 2.0
        q += in_w / m - (sum(deg[a] for a in notes) / (2.0 * m)) ** 2
    return {"communities": out, "modularity": round(q, 4), "hubs": hubs,
            "unplaced": [n for n in all_notes
                         if n not in placed and n not in hubs],
            "edge_weight": int(m)}


def cmd_communities(args: argparse.Namespace) -> int:
    payload = communities(vault_dir(args.vault),
                          include_inferred=args.include_inferred)

    def render(p):
        q = p["modularity"]
        verdict = ("real structure" if q >= 0.3 else
                   "weak - read these groups as a hint, not a map")
        print(f"Note clusters inferred from the link graph."
              f"  modularity {q} ({verdict})")
        for c in p["communities"]:
            print(f"\naround {c['label']}  ({c['size']} notes,"
                  f" {c['internal_edges']} internal /"
                  f" {c['external_edges']} external links)")
            print_capped(c["notes"], args.limit)
        for title, key in (("hubs, left out", "hubs"),
                           ("unplaced: no resolved link to cluster on",
                            "unplaced")):
            if p[key]:
                print(f"\n{title} ({len(p[key])}):")
                print_capped(p[key], args.limit)
        return 0
    return emit(args, payload, render)


# ---------- config check ----------
def config_report(vault: Path) -> dict:
    """What each config row matched, from the current graph. Reads and
    reports only. A row that matches nothing is a warning and never an
    error: the registry is allowed to be ahead of the corpus."""
    cfg_file = config_path(vault)
    cfg = load_config(vault)        # exits loudly on a malformed file
    con = open_fresh(vault)
    notes = con.execute("SELECT id, path, profile FROM notes"
                        " ORDER BY id").fetchall()
    kg_types = {nid: str(v).strip().lower() for nid, v in con.execute(
        "SELECT note_id, value FROM properties WHERE key='kg-type'")}
    mention_counts = dict(con.execute(
        "SELECT canonical, count(*) FROM mentions GROUP BY canonical"))
    derived = con.execute(
        "SELECT canonical, note FROM entities WHERE origin='note'"
        " ORDER BY canonical").fetchall()
    skips = con.execute("SELECT note_id, name, reason FROM entity_skips"
                        " ORDER BY note_id, name").fetchall()
    marker_counts = dict(con.execute(
        "SELECT marker, count(*) FROM annotations GROUP BY marker"))
    field_counts = dict(con.execute(
        "SELECT field, count(*) FROM link_fields GROUP BY field"))
    con.close()
    warnings: list[str] = []

    profile_rows = []
    for row in cfg.get("profiles", []):
        if not isinstance(row, dict):
            continue
        pat = str(row.get("path", ""))
        ktype = str(row.get("kg_type", "")).strip().lower()
        if pat:
            n = sum(1 for _, path_, _ in notes if glob_match(path_, pat))
        else:
            n = sum(1 for nid, _, _ in notes if kg_types.get(nid) == ktype)
        label = pat or f"kg_type {ktype}"
        profile = str(row.get("profile", "reference"))
        profile_rows.append({"match": label, "profile": profile,
                             "matched": n})
        if not n:
            warnings.append(f"profiles row matched nothing: {label}")
        if profile not in PROFILES:
            warnings.append(f"profiles row names an unknown profile:"
                            f" {profile!r} ({label})")

    entity_rows = []
    for row in cfg.get("entities", []):
        if not isinstance(row, dict):
            continue
        canonical = str(row.get("canonical", "")).strip()
        if not canonical:
            continue
        n = mention_counts.get(canonical, 0)
        entity_rows.append({"canonical": canonical, "sections": n})
        if not n:
            warnings.append(f"entity is never mentioned: {canonical}")

    source_rows = []
    sources = cfg.get("entity_sources", [])
    owner = {nid: entity_source_for(path_, {"kg-type": kg_types.get(nid, "")},
                                    cfg) for nid, path_, _ in notes}
    derived_notes = {note for _, note in derived}
    for row in sources:
        label = (str(row.get("path", "")).strip()
                 or f"kg_type {str(row.get('kg_type', '')).strip().lower()}")
        matched = [nid for nid, src in owner.items() if src is row]
        source_rows.append({
            "match": label, "type": str(row.get("type", "")),
            "matched": len(matched),
            "derived": sum(1 for nid in matched if nid in derived_notes)})
        if not matched:
            warnings.append(f"entity_sources row matched nothing: {label}")
    if skips:
        warnings.append(f"{len(skips)} derived entity names were left out"
                        " (see skipped)")

    relation_rows = []
    declared = set()
    for row in cfg.get("relations", []):
        field = str(row.get("field", ""))
        declared.add(field)
        n = field_counts.get(field, 0)
        relation_rows.append({"field": field,
                              "inverse": str(row.get("inverse", "")),
                              "links": n})
        if not n:
            warnings.append(f"relations field is never used: {field}")

    core = set(CORE_MARKERS)
    mode, mode_source = link_mode(vault, cfg)
    return {
        "path": cfg_file.relative_to(vault).as_posix(),
        "exists": cfg_file.exists(),
        "status": "WARNINGS" if warnings else "OK", "warnings": warnings,
        "link_resolution": {"mode": mode, "source": mode_source},
        "profiles": profile_rows,
        "entities": entity_rows, "entity_sources": source_rows,
        "derived_entities": len(derived),
        "skipped": [{"note": n, "name": name, "reason": why}
                    for n, name, why in skips],
        "markers": [{"marker": str(r.get("marker", "")),
                     "count": marker_counts.get(str(r.get("marker", "")), 0)}
                    for r in cfg.get("markers", []) if isinstance(r, dict)
                    and str(r.get("marker", "")) not in core],
        "relations": relation_rows,
        "undeclared_fields": [
            {"field": f, "links": n} for f, n in
            sorted(field_counts.items(), key=lambda kv: (-kv[1], kv[0]))
            if f not in declared]}


def cmd_config(args: argparse.Namespace) -> int:
    payload = config_report(vault_dir(args.vault))

    def render(p):
        state = "" if p["exists"] else " (not created; defaults in use)"
        print(f"{p['path']}{state}: {p['status']}")
        for w in p["warnings"]:
            print(f"  warning: {w}")
        print(f"  markdown links: {p['link_resolution']['mode']}"
              f" ({p['link_resolution']['source']})")
        for r in p["profiles"]:
            print(f"  profile {r['profile']} on {r['match']}:"
                  f" {r['matched']} notes")
        for r in p["entities"]:
            print(f"  entity {r['canonical']}: {r['sections']} sections")
        for r in p["entity_sources"]:
            print(f"  entity source {r['match']}: {r['matched']} notes,"
                  f" {r['derived']} entities")
        for r in p["skipped"][:20]:
            print(f"  skipped {r['name']!r} from {r['note']}: {r['reason']}")
        if len(p["skipped"]) > 20:
            print(f"  TRUNCATED: {len(p['skipped']) - 20} more skipped names"
                  " (--json lists all)")
        for r in p["markers"]:
            print(f"  marker {r['marker']}: {r['count']} annotations")
        for r in p["relations"]:
            inv = f" (inverse: {r['inverse']})" if r["inverse"] else ""
            print(f"  relation {r['field']}{inv}: {r['links']} links")
        if p["undeclared_fields"]:
            print("  link fields with no relations row: " + ", ".join(
                f"{r['field']} ({r['links']})"
                for r in p["undeclared_fields"][:20]))
        return 0
    return emit(args, payload, render)


def _tag_hit(tag: str, want: str, nested: bool) -> bool:
    tag = tag.lower()
    return tag == want or (nested and tag.startswith(want + "/"))


def tags_report(con: sqlite3.Connection, tag: str | None, inline: bool,
                nested: bool):
    """`tags --inline` and `tags --nested`: frontmatter tags joined with the
    `#tags` written in body text, and a parent tag matching its children."""
    front = con.execute("SELECT note_id, tag FROM tags").fetchall()
    body = (con.execute("SELECT DISTINCT note_id, tag FROM inline_tags")
            .fetchall() if inline else [])
    if tag:
        want = tag.lstrip("#").strip("/").lower()
        return sorted({nid for nid, t in front + body
                       if _tag_hit(t, want, nested)})
    notes: dict[str, tuple[set, set]] = {}
    for rows, slot in ((front, 0), (body, 1)):
        for nid, t in rows:
            notes.setdefault(t.lower(), (set(), set()))[slot].add(nid)
    return [{"tag": t, "count": len(f | b), "frontmatter": len(f),
             "inline": len(b)}
            for t, (f, b) in sorted(notes.items(),
                                    key=lambda kv: (-len(kv[1][0] | kv[1][1]),
                                                    kv[0]))]


def cmd_tags(args: argparse.Namespace) -> int:
    vault = vault_dir(args.vault)
    con = open_fresh(vault)
    inline = getattr(args, "inline", False)
    nested = getattr(args, "nested", False)
    if inline or (nested and args.tag):
        got = tags_report(con, args.tag, inline, nested)
        con.close()
        if args.tag:
            if args.json:
                print(json.dumps(got, indent=2))
                return 0 if got else 1
            if not got:
                print(f"no notes tagged {args.tag!r}")
                return 1
            for nid in got:
                print(nid)
            return 0

        def render_counts(rows_):
            if not rows_:
                print("no tags")
                return 0
            for r in rows_:
                print(f"{r['count']:4d}  {r['tag']}  "
                      f"({r['frontmatter']} frontmatter, {r['inline']} inline)")
            return 0
        return emit(args, got, render_counts)
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


NO_LOG_DATED_LINE = ("no log-dated notes in this graph, so there is nothing to aggregate - "
                     "give a dated log the log-dated profile in the vault's config")


def cmd_themes(args: argparse.Namespace) -> int:
    payload = themes(vault_dir(args.vault), args.frm, args.to, args.slot,
                     args.limit)

    def render(p):
        if p["status"] == "NO_LOG_DATED_NOTES":
            print(NO_LOG_DATED_LINE)
            return 0
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
        if p["status"] == "NO_LOG_DATED_NOTES":
            print(NO_LOG_DATED_LINE)
            return 0
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
            and str(meta.get("generator", "")).startswith(("markdown_kg.py", "obsidian_kg.py")))


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
    resolved.write_bytes(text.encode("utf-8"))
    print(f"index: wrote {resolved} ({len(text.splitlines())} lines)")
    return 0


def cmd_coverage(args: argparse.Namespace) -> int:
    vault = vault_dir(args.vault)
    if args.forget and args.session:
        sys.exit("error: pass --session to report or --forget to delete, "
                 "not both")
    if args.forget:
        con = connect(vault, must_exist=True)
        n = con.execute("DELETE FROM session_reads WHERE session_id=?",
                        (args.forget,)).rowcount
        con.commit()
        con.close()
        payload = {"forgot": args.forget, "rows": n}

        def render(p):
            print(f"forgot session {p['forgot']!r}: "
                  f"{p['rows']} ledger row(s) deleted")
            return 0
        return emit(args, payload, render)
    if not args.session:
        sys.exit("error: coverage needs --session ID (or --forget ID)")
    payload = coverage(vault, args.session, args.scope, args.limit)

    def render(c):
        line = (f"coverage: {c['sections']['touched']}/"
                f"{c['sections']['total']} sections "
                f"({c['sections']['percent']}%), "
                f"{c['words']['touched']}/{c['words']['total']} words "
                f"({c['words']['percent']}%), "
                f"{c['notes']['touched']}/{c['notes']['total']} notes")
        if c["scope"]:
            line += f"  [scope {c['scope']}]"
        if c["stale"]:
            line += f"; {c['stale']} stale ledger row(s)"
        print(line)
        if c["untouched"]:
            print("untouched:")
            for u in c["untouched"]:
                where = (u["note_id"] if u["kind"] == "note"
                         else f"{u['note_id']} # {u['heading']}")
                print(f"  {u['kind']:<7} {where}  "
                      f"{u['sections']} section(s)  {u['words']}w")
        print(c["status"])
        return 0
    return emit(args, payload, render)


def cmd_tree(args: argparse.Namespace) -> int:
    vault = vault_dir(args.vault)
    with contextlib.closing(open_fresh(vault)) as con:
        rows = [{"path": p, "language": "markdown", "ext": ".md",
                 "lines": body.count("\n") + (not body.endswith("\n")),
                 "size": len(body.encode("utf-8"))}
                for p, body in con.execute("SELECT path, body FROM notes")]
        rows += other_file_rows(con)
    return tree_command(args, vault, rows)


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
    # A heading the parser may have invented, or that nobody can cite: one
    # that was underlined (a line right above a `---` divider reads as one),
    # one whose text opens like a list item, or one clipped at HEADING_MAX.
    # The vault owner tells a mis-parse from a real heading here, instead of
    # finding out when a section boundary has swallowed an entry.
    suspects = []
    for note_id, heading, line_start, setext in con.execute(
            "SELECT note_id, heading, line_start, setext FROM sections"
            " WHERE heading != '' ORDER BY note_id, ord"):
        reasons = [name for name, hit in (
            ("setext", setext),
            ("list-marker", LIST_MARKER_RE.match(heading)),
            ("clipped", len(heading) > HEADING_MAX)) if hit]
        if reasons:
            suspects.append({"note_id": note_id, "line": line_start,
                             "heading": heading[:60], "reasons": reasons})
    suspect_cap = 50
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
        "suspect_headings": {
            "total": len(suspects),
            "status": ("COMPLETE" if len(suspects) <= suspect_cap
                       else f"TRUNCATED {suspect_cap} of {len(suspects)}"),
            "rows": suspects[:suspect_cap]},
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
        sh = p["suspect_headings"]
        print(f"suspect headings: {sh['total']}"
              + (f"  [{sh['status']}] - underlined, list-marker or clipped;"
                 " check the file before trusting the section"
                 if sh["total"] else ""))
        for row in sh["rows"][:5]:
            print(f"  {row['note_id']}:{row['line']}  {row['heading']}  "
                  f"({', '.join(row['reasons'])})")
        print(f"tags: {p['tags']}")
        print(f"entities: {p['entities']} ({p['mentions']} mentions)")
        if p["annotations"]:
            print("annotations by marker:")
            for row in p["annotations"]:
                print(f"  {row['marker']}: {row['count']}")
        for row in p["custom_markers"]:
            desc = f"  ({row['description']})" if row["description"] else ""
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
        prog="markdown_kg.py",
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
                   help=f"checkpoint the current db to {PREV_DB_NAME} first"
                        " (what a bare `diff` compares against)")

    p = add("init", cmd_init, f"scaffold {KG_DIR}/ and a confident config")
    p.add_argument("--force", action="store_true",
                   help="rewrite an existing config scaffold")

    add("migrate", cmd_migrate,
        f"move a legacy markdown-kg/ or vault-kg/ graph into {KG_DIR}/")

    add("profile", cmd_profile, "propose config rows; writes nothing")

    session_help = ("append returned section ids to this coverage session's"
                    " ledger (report with `coverage`)")
    path_help = "only notes whose path matches this glob, e.g. 'docs/**'"

    p = add("query", cmd_query, "raw FTS5 search over sections")
    p.add_argument("fts_query")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--session", default=None, metavar="ID", help=session_help)
    p.add_argument("--path", default=None, metavar="GLOB", help=path_help)
    p.add_argument("--git", default="all", choices=("all",) + GIT_STATES,
                   help="only notes with this git status; every row shows it")

    p = add("search", cmd_search, "natural-language section search")
    p.add_argument("question")
    p.add_argument("--path", default=None, metavar="GLOB", help=path_help)
    p.add_argument("--git", default="all", choices=("all",) + GIT_STATES,
                   help="only notes with this git status; every row shows it")
    p.add_argument("--session", default=None, metavar="ID", help=session_help)
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
                   help="a markdown-kg db to compare with (default:"
                        f" {PREV_DB_NAME} from `ingest --keep-previous`)")

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
    p.add_argument("--session", default=None, metavar="ID", help=session_help)

    p = add("read", cmd_read, "one section, whole")
    p.add_argument("section_id")
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--session", default=None, metavar="ID", help=session_help)

    inferred_help = ("also traverse hot inferred relations (recorded by"
                     " `relate`); default traversal is extracted edges only")

    p = add("backlinks", cmd_backlinks, "inbound edges + their section")
    p.add_argument("note")
    p.add_argument("--include-inferred", action="store_true",
                   help=inferred_help)
    p.add_argument("--anchors", action="store_true",
                   help="inbound links that name a heading or block here,"
                        " with the section each one points at")

    p = add("links", cmd_links, "outbound edges")
    p.add_argument("note", nargs="?", default=None)
    p.add_argument("--unresolved", action="store_true",
                   help="only broken and ambiguous links (vault-wide if no note)")
    p.add_argument("--include-inferred", action="store_true",
                   help=inferred_help)
    p.add_argument("--anchors", action="store_true",
                   help="links that name a heading or block, with the section"
                        " each resolved to; with --unresolved, the anchors"
                        " whose heading or block does not exist")

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
    p.add_argument("--inline", action="store_true",
                   help="also count `#tags` written in body text")
    p.add_argument("--nested", action="store_true",
                   help="with a tag: also match its children (tag/child)")

    p = add("fields", cmd_fields,
            "links by the frontmatter key or inline field they sit under")
    p.add_argument("--field", default=None, metavar="NAME",
                   help="every link under one field")
    p.add_argument("--note", default=None, metavar="name-or-path",
                   help="one note's field links, outbound and inbound")

    p = add("related", cmd_related,
            "notes ranked by link-graph proximity to one note")
    p.add_argument("note")
    p.add_argument("--limit", type=int, default=10,
                   help="rows, default 10; 0 or less for all")
    p.add_argument("--include-inferred", action="store_true",
                   help=inferred_help)

    p = add("communities", cmd_communities,
            "clusters of notes that link mostly to each other")
    p.add_argument("--limit", type=int, default=25,
                   help="max notes listed per group; --json is never"
                        " truncated")
    p.add_argument("--include-inferred", action="store_true",
                   help=inferred_help)

    add("config", cmd_config, "what each config row matched; writes nothing")

    p = add("refs", cmd_refs, "the sections that link to a file that is not"
                              " a note")
    p.add_argument("path", help="vault-relative, as a note reaches it:"
                                " ../src/tool.py for a file beside the vault")

    p = add("code", cmd_code, "the files a note links to, with what the"
                              " code-kg skill holds for each")
    p.add_argument("note")
    p.add_argument("--limit", type=int, default=30,
                   help="files looked up in the code graph")
    p.add_argument("--mentions", action="store_true",
                   help="also the files and symbols the note names in code"
                        " spans, resolved by code-kg")

    p = add("spans", cmd_spans, "inline code spans shaped like a path or a"
                                " name; with texts, the sections that hold"
                                " them")
    p.add_argument("text", nargs="*")
    p.add_argument("--limit", type=int, default=SPANS_LIMIT,
                   help=f"rows returned, default {SPANS_LIMIT}; 0 for all."
                        " The listing is ranked by section count, the"
                        " sections for given texts put primary docs first"
                        " and archives last; a cut prints TRUNCATED N of M"
                        " (on stderr with --json)")

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

    p = add("coverage", cmd_coverage,
            "a session's touched vs untouched territory")
    p.add_argument("--session", default=None, metavar="ID",
                   help="the coverage session to report")
    p.add_argument("--scope", default=None, metavar="GLOB",
                   help="restrict totals and inventory to notes matching"
                        " this glob")
    p.add_argument("--limit", type=int, default=20,
                   help="untouched entries listed")
    p.add_argument("--forget", default=None, metavar="ID",
                   help="delete one session's ledger rows instead of"
                        " reporting")

    add("stats", cmd_stats, "counts, orphans, unresolved/ambiguous")
    p = add("tree", cmd_tree,
            "every file by folder: direct and recursive counts, notes, and"
            " the extensions of files that are not notes")
    p.add_argument("folder", nargs="?",
                   help="a vault-relative folder; default the whole vault")
    p.add_argument("--depth", type=int, default=0,
                   help="levels shown, 1 for the folder alone; default 0,"
                        " every level")
    p.add_argument("--files", action="store_true",
                   help="also list each file: a note with its line count,"
                        " any other file with why it is not read")
    p.add_argument("--absolute", action="store_true",
                   help="with --files, give each file's absolute path in"
                        " this system's form")
    p.add_argument("--limit", type=int, default=TREE_LIMIT,
                   help=f"folders, and files, shown; default {TREE_LIMIT},"
                        " 0 for all")

    return run_cli(ap.parse_args(argv))


if __name__ == "__main__":
    if sys.platform == "win32":  # the console code page is not UTF-8; note text often is
        for _stream in (sys.stdout, sys.stderr):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
