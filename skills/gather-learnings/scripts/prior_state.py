#!/usr/bin/env python3
"""The last known state of what today's notes and today's learnings entry name, from the
knowledge graph.

Two reads, both through `markdown-kg`'s own CLI and its JSON output:

  work items  Every work-item id named in today's `notes-*` sections is a registered graph
              entity, so `timeline` returns every section that mentions it, in any note, by
              date. The latest mention before today in each note is the state today's claim
              is checked against, whichever file it sits in.

  learnings   Each `###` subsection of today's learnings entry is matched against the older
              learnings subsections that share its identifiers: work items through `timeline`,
              backticked identifiers and `ABC-123` codes through an exact-phrase FTS `query`.
              Each hit is a supersession candidate to read, never a verdict. The authored
              notes that name the same identifiers are listed too, as correction targets.

Exact identifiers only. A claim phrased two ways with no shared identifier is not found
here, and the walk still has to catch it. The graph must already hold the older entries.
Today's notes and today's entry are read from the vault folder itself, so the graph can
be the vault's own or one ingested from a copy of it elsewhere (`--graph`).

    python3 prior_state.py <vault> [--graph <folder>] [--today YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

import vault_patterns as vp      # the skill's own copy, beside this script

LEARNINGS = 'notes-learnings'
# The markdown-kg engine, found as the sibling skill of that name. Resolving the symlink
# first means a station view of this skill still finds the engine beside the source.
KG = Path(__file__).resolve().parents[2] / 'markdown-kg' / 'scripts' / 'markdown_kg.py'
NO_LIMIT = '100000'
DATE = re.compile(r'(\d{4}-\d{2}-\d{2})')
CODE = re.compile(r'\b[A-Z]{2,}-\d+\b')
TICKED = re.compile(r'`([^`\n]+)`')
NOT_AUTHORED = ('notes-', 'code-', 'docs-', 'user-stories', 'user-runsheet', 'index', 'log')


def kg(*args: str) -> list | dict | None:
    """One markdown-kg call, parsed. None when the call fails, e.g. an unregistered entity."""
    # A read may re-ingest the vault first, which takes minutes on a large one.
    try:
        r = subprocess.run([sys.executable, str(KG), *args, '--json'],
                           capture_output=True, text=True, timeout=900)
    except subprocess.TimeoutExpired:
        return None
    if r.returncode != 0:
        return None
    return json.loads(r.stdout)


def identifier_like(term: str) -> bool:
    """A backticked span worth searching for: it has a separator, a digit or an inner
    capital. `main` and `overwrite` match half the corpus; `username_key` does not."""
    return (len(term) >= 4 and (re.search(r'[_./<>@\d-]', term) is not None
                                or re.search(r'[a-z][A-Z]', term) is not None))


def terms_of(text: str) -> tuple[set, set]:
    items = vp.work_item_ids(text)
    other = {t for t in TICKED.findall(text) if identifier_like(t)}
    other |= {c for c in CODE.findall(text) if c not in items}
    return items, other


def section_date(hit: dict) -> str:
    """A hit's date: its own doc_date, else the dated H2 in its heading path. Only the
    dated `notes-*` logs have one; any other note is a current-state document whose
    doc_date is a note-level stamp, so it is treated as undated."""
    if not hit.get('note_id', '').startswith('notes-'):
        return ''
    if hit.get('doc_date'):
        return hit['doc_date']
    m = DATE.search(hit.get('heading_path', ''))
    return m.group(1) if m else ''


def is_subsection(hit: dict) -> bool:
    return hit.get('heading_path', '').count(' > ') == 2


def work_item_state(vault: Path, wid: str, today: str) -> list | None:
    """The latest mention before today in each note, newest first. None when the id is not
    a registered entity."""
    tl = kg('timeline', str(vault), wid, '--limit', NO_LIMIT)
    if tl is None:
        return None
    latest: dict = {}
    for m in tl['mentions']:
        d = section_date(m)
        if d and d >= today:
            continue
        if m['note_id'] not in latest or d > section_date(latest[m['note_id']]):
            latest[m['note_id']] = m
    return sorted(latest.values(), key=section_date, reverse=True)


def own_text(vault: Path, hit: dict) -> str:
    """A hit's own lines in the folder the graph was ingested from, stopping at its first
    child heading."""
    path = vault / f'{hit["note_id"]}.md'
    # The note id comes from the graph, so it is confined to the vault before it is read.
    if not path.is_file() or not path.resolve().is_relative_to(vault.resolve()):
        return ''
    start, end = (int(n) for n in hit['lines'].split('-'))
    lines = path.read_text(encoding='utf-8').splitlines()[start - 1:end]
    own = lines[:1]
    for line in lines[1:]:
        if line.startswith('#'):
            break
        own.append(line)
    return '\n'.join(own)


def phrase_hits(vault: Path, term: str) -> list:
    """FTS hits whose own text holds the term. The index covers the heading path too, so
    without the check a term in an H2 title matches every subsection under it."""
    rows = kg('query', str(vault), '"' + term.replace('"', '""') + '"', '--limit', NO_LIMIT)
    return [h for h in rows or [] if term.lower() in own_text(vault, h).lower()]


def deepest(pairs: list) -> list:
    """Drop a hit whose child section in the same note is also a hit."""
    paths = {(h['note_id'], h['heading_path']) for h, _ in pairs}
    return [(h, s) for h, s in pairs
            if not any(n == h['note_id'] and p.startswith(h['heading_path'] + ' > ')
                       for n, p in paths)]


def learnings_candidates(vault: Path, text: str, today: str) -> tuple[list, list]:
    """(older learnings subsections, authored-note sections) sharing an identifier with
    one subsection of today's entry, each as (hit, shared terms), most shared first."""
    items, other = terms_of(text)
    found: dict = {}
    for wid in items:
        tl = kg('timeline', str(vault), wid, '--limit', NO_LIMIT)
        for m in (tl or {}).get('mentions', []):
            found.setdefault(m['section_id'], (m, set()))[1].add(wid)
    for term in other:
        for h in phrase_hits(vault, term):
            found.setdefault(h['section_id'], (h, set()))[1].add(f'`{term}`')

    older, authored = [], []
    for hit, shared in found.values():
        note = hit['note_id']
        if note == LEARNINGS and is_subsection(hit) and section_date(hit) < today:
            older.append((hit, shared))
        elif not note.startswith(NOT_AUTHORED) and not note.endswith(('decisions', 'glossary')):
            authored.append((hit, shared))
    rank = lambda p: (len(p[1]), section_date(p[0]))
    return (sorted(older, key=rank, reverse=True),
            sorted(deepest(authored), key=rank, reverse=True))


CITED = re.compile(r'(\d{4}-\d{2}-\d{2}) entry')


def cited_entries(vault: Path, text: str, today: str) -> list[dict]:
    """Older learnings entries a subsection cites by date ("the 2026-09-11 entry"). A cited
    entry is related by the author's own reference, whether or not it shares an identifier."""
    dates = {d for d in CITED.findall(text) if d < today}
    path = vault / f'{LEARNINGS}.md'
    if not dates or not path.is_file():
        return []
    return [s for s in vp.date_sections(path, loose=True) if s['date'] in dates]


def subsections(body: str) -> list[tuple[str, str]]:
    out, head, buf = [], None, []
    for line in body.splitlines():
        if line.startswith('### '):
            if head:
                out.append((head, '\n'.join(buf)))
            head, buf = line[4:].strip(), []
        elif head:
            buf.append(line)
    if head:
        out.append((head, '\n'.join(buf)))
    return out


def graph_db(vault: Path) -> Path:
    """The vault's graph database, as the engine names it; the engine owns that folder name."""
    import importlib.util
    spec = importlib.util.spec_from_file_location('markdown_kg', KG)
    engine = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(engine)
    return Path(engine.db_path(vault))


def fresh(graph: Path, written_today: bool) -> str | None:
    """Why the graph cannot be used, or None. A missing engine, a missing graph and a graph
    older than the learnings file all stop the run. Once today's entry is written that file
    is newer by design, so the age check is skipped."""
    if not KG.is_file():
        return f'no markdown-kg engine at {KG}'
    try:
        db = graph_db(graph)
    except (ImportError, AttributeError, OSError, SyntaxError) as e:
        return f'the markdown-kg engine at {KG} could not name the graph ({e})'
    note = graph / f'{LEARNINGS}.md'
    if not db.is_file():
        return f'no graph at {db}; run markdown-kg ingest first'
    if not written_today and note.is_file() and note.stat().st_mtime > db.stat().st_mtime:
        return f'the graph is older than {LEARNINGS}.md; run markdown-kg ingest first'
    return None


def where(hit: dict) -> str:
    return f'{hit["note_id"]} L{hit["lines"]}  {hit["heading_path"]}'


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('vault', help='the target vault folder')
    ap.add_argument('--graph', default=None,
                    help='the folder the graph was ingested from, when it is not the vault itself')
    ap.add_argument('--today', help='YYYY-MM-DD; pin today for a repeatable run')
    ap.add_argument('--top', type=int, default=5, help='candidates listed per subsection')
    args = ap.parse_args(argv)

    vault = Path(args.vault).expanduser()
    graph = Path(args.graph).expanduser() if args.graph else vault
    today = args.today or dt.date.today().isoformat()
    learnings = vault / f'{LEARNINGS}.md'
    entries = [s for s in vp.date_sections(learnings, loose=True)
               if s['date'] == today] if learnings.is_file() else []
    problem = fresh(graph, bool(entries))
    if problem:
        print(f'ERROR: {problem}', file=sys.stderr)
        return 2

    ids: dict = {}
    for path in vp.corpus(vault, 'notes'):
        for s in vp.date_sections(path, loose=True):
            if s['date'] == today:
                for wid in vp.work_item_ids(s['body']):
                    ids.setdefault(wid, set()).add(path.name)

    print(f'work items named in notes-* sections dated {today} ({len(ids)}): '
          f'latest mention before today, per note')
    unregistered = []
    for wid in sorted(ids):
        state = work_item_state(graph, wid, today)
        if state is None:
            unregistered.append(wid)
            continue
        print(f'  {wid}  (named today in {", ".join(sorted(ids[wid]))})')
        for m in state[:args.top] or []:
            print(f'      {section_date(m) or "current":<10}  {where(m)}')
        if not state:
            print('      no earlier mention')
    if unregistered:
        print(f'  not in the graph registry: {", ".join(unregistered)} -- register them as '
              f'entities in the graph config and re-ingest')

    if not entries:
        print(f'\nno learnings entry dated {today} yet; rerun after it is written')
        return 0
    print(f'\nsupersession candidates for the {today} learnings entry '
          f'(read each; mark only what today changes):')
    for entry in entries:
        for head, text in subsections(entry['body']):
            older, authored = learnings_candidates(graph, f'{head}\n{text}', today)
            print(f'  ### {head}')
            for hit, shared in older[:args.top]:
                print(f'      {section_date(hit)}  L{hit["lines"]}  '
                      f'{hit["heading_path"].split(" > ")[-1]}  shared: {", ".join(sorted(shared))}')
            if not older:
                print('      no older learnings subsection shares an identifier')
            for s in cited_entries(vault, text, today):
                print(f'      cited: L{s["start"]}-{s["end"]}  {s["body"].splitlines()[0]}')
            for hit, shared in authored[:3]:
                print(f'      authored: {where(hit)}  shared: {", ".join(sorted(shared))}')
    return 0


if __name__ == '__main__':
    if sys.platform == 'win32':  # the console code page is not UTF-8; note text often is
        for _stream in (sys.stdout, sys.stderr):
            _stream.reconfigure(encoding='utf-8', errors='replace')
    raise SystemExit(main())
