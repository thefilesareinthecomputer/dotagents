#!/usr/bin/env python3
"""Deterministic half of the compact-notes skill.

Lists the sections still to compact, backs a section up before it is overwritten in
place, and verifies that the rewritten section is in the fixed format. The rewriting
itself is model work in-session; this script decides what is still to do and whether an
edit KEPT what it had to keep.

Subcommands (all read-only except `backup`):
  candidates [--before DATE] FILE...      sections not yet compacted
  inspect    FILE HEADING                 one section: span, bytes, hash, stamps, subsections
  backup     --root DIR --project NAME FILE HEADING
                                          copy the section verbatim under
                                          __archive/_BACKUPS/compact-notes/ (idempotent)
  verify     --backup PATH --pre-hash H [--pre-subs A,B] FILE HEADING

Exit codes: 0 ok; 2 usage/target not found; 4 verify failed (the format or a kept
subsection did not survive the edit, or the backup is missing or does not hold the
pre-edit section); 6 backup refused (a different file already holds the path, or the
path would leave the backup root).
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

from vault_patterns import (date_sections, lines_of,  # the skill's own copy, beside this script
                            section_hash, section_key)

COMPACT_MARK = 'COMPACTED'
# Sections stamped SUMMARIZED by an earlier version of this skill count as done too.
DONE_MARKS = (COMPACT_MARK, 'SUMMARIZED')
REQUIRED_SUBS = ('DECISIONS', 'QUESTIONS', 'ACTIONS')
STAMP = '- [x] REFINED'
BACKUP_DIR = Path('__archive') / '_BACKUPS' / 'compact-notes'
NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]*$')
# Code points, not literals: a literal U+2028 in source is a line break to every editor
# and splitlines(), and a literal zero-width character is the thing this check hunts.
INVISIBLES = ((0x00A0, 'U+00A0 nbsp'), (0x200B, 'U+200B zwsp'), (0x200C, 'U+200C zwnj'),
              (0x200D, 'U+200D zwj'), (0xFEFF, 'U+FEFF bom'), (0x2028, 'U+2028 ls'),
              (0x2029, 'U+2029 ps'), (0x0085, 'U+0085 nel'), (0x2060, 'U+2060 wj'))
UNSAFE = re.compile(r'[^A-Za-z0-9._~-]')


def section_status(sec: dict) -> dict:
    body_lines = lines_of(sec['body'])
    stamp = next((l for l in body_lines[1:3] if l.startswith(STAMP)), '')
    return {
        'key': section_key(sec['file'], sec['date'], sec['suffix'], sec['ord']),
        'hash': section_hash(sec),
        'heading': body_lines[0][3:].strip(),
        'start': sec['start'], 'end': sec['end'],
        'bytes': len(sec['body'].encode('utf-8')),
        'stamp': stamp,
        'compacted': any(m in stamp for m in DONE_MARKS),
        'subsections': [l[4:].split(' (')[0].strip() for l in body_lines
                        if l.startswith('### ')],
    }


def find_by_heading(path: Path, heading: str) -> dict | None:
    """The section under a heading. A trailing `~N`, as section keys write it, picks
    the Nth section with that heading; without it the first one is returned."""
    want = heading.strip().lstrip('#').strip()
    m = re.match(r'^(.*?)~(\d{1,6})$', want)
    want, ordinal = (m.group(1).strip(), int(m.group(2))) if m else (want, None)
    for sec in date_sections(path):
        if lines_of(sec['body'])[0][3:].strip() == want and ordinal in (None, sec['ord']):
            return sec
    return None


def cmd_candidates(args) -> int:
    rows = []
    for f in args.files:
        p = Path(f)
        if not p.exists():
            print(f'missing file: {f}', file=sys.stderr)
            return 2
        for sec in date_sections(p):
            st = section_status(sec)
            if st['compacted']:
                continue
            if args.before and sec['date'] >= args.before:
                continue
            rows.append(st)
    print(json.dumps(rows, indent=2))
    print(f'{len(rows)} section(s) not yet compacted', file=sys.stderr)
    return 0


def cmd_inspect(args) -> int:
    sec = find_by_heading(Path(args.file), args.heading)
    if sec is None:
        print(f'section not found: {args.heading} in {args.file}', file=sys.stderr)
        return 2
    st = section_status(sec)
    print(json.dumps(st, indent=2))
    if st['compacted']:
        print('already compacted', file=sys.stderr)
    return 0


def backup_path(root: Path, project: str, sec: dict, day: datetime.date) -> Path:
    """`<root>/__archive/_BACKUPS/compact-notes/<project>/<note>/<day>-<key>@<hash>.md`.

    The key is the section part of `section_key`, so duplicate headings get distinct
    files. A heading suffix is free text and may carry `/`, so it is flattened here."""
    section = section_key(sec['file'], sec['date'], sec['suffix'], sec['ord']).split('#', 1)[1]
    name = f"{day.isoformat()}-{UNSAFE.sub('-', section)}@{section_hash(sec)}.md"
    return root / BACKUP_DIR / project / Path(sec['file']).name / name


def cmd_backup(args) -> int:
    if not NAME.fullmatch(args.project):
        print(f'BACKUP REFUSED: the project name may hold only letters, digits, '
              f'_ and -: {args.project!r}', file=sys.stderr)
        return 6
    sec = find_by_heading(Path(args.file), args.heading)
    if sec is None:
        print(f'section not found: {args.heading} in {args.file}', file=sys.stderr)
        return 2
    root = Path(args.root).resolve()
    base = (root / BACKUP_DIR).resolve()
    if not base.is_relative_to(root):
        print(f'BACKUP REFUSED: the backup root {base} resolves outside {root}', file=sys.stderr)
        return 6
    dest = backup_path(root, args.project, sec, args.date).resolve()
    if not dest.is_relative_to(base):
        print(f'BACKUP REFUSED: {dest} is outside {base}', file=sys.stderr)
        return 6
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with dest.open('x', encoding='utf-8', newline='\n') as f:     # exclusive create: never overwrites
            f.write(sec['body'])
    except FileExistsError:
        if dest.read_text(encoding='utf-8') != sec['body']:
            print(f'BACKUP REFUSED: {dest} already holds a different file', file=sys.stderr)
            return 6
    print(dest)
    return 0


def backup_problem(path: Path, pre_hash: str) -> str | None:
    """Why the backup cannot stand in for the pre-edit section, or None when it can."""
    if not path.is_file():
        return f'backup missing: {path}'
    if section_hash({'body': path.read_text(encoding='utf-8')}) != pre_hash:
        return f'backup {path} does not hold the pre-edit section (hash {pre_hash})'
    return None


def cmd_verify(args) -> int:
    errs = []
    if problem := backup_problem(Path(args.backup), args.pre_hash):
        errs.append(problem)
    sec = find_by_heading(Path(args.file), args.heading)
    if sec is None:
        print(f'section not found after edit: {args.heading} in {args.file}',
              file=sys.stderr)
        return 4
    st = section_status(sec)
    if st['hash'] == args.pre_hash:
        errs.append('section unchanged since --pre-hash: the backup was taken after the '
                    'edit, or nothing was rewritten')
    found = sorted({name for cp, name in INVISIBLES if chr(cp) in sec['body']})
    if found:
        errs.append(f"invisible characters in the rewritten section: {', '.join(found)}")
    if not st['stamp']:
        errs.append(f'stamp line missing (expected `{STAMP} <date> ({COMPACT_MARK} <date>)` '
                    f'under the heading)')
    elif COMPACT_MARK not in st['stamp']:
        errs.append(f'{COMPACT_MARK} marker missing from the stamp line')
    must_keep = [s for s in (args.pre_subs or '').split(',') if s]
    must_keep += [s for s in REQUIRED_SUBS if s not in must_keep]
    for sub in must_keep:
        if sub not in st['subsections']:
            errs.append(f'subsection missing: ### {sub}')
    if errs:
        print('VERIFY FAILED', file=sys.stderr)
        for e in errs:
            print(f'  - {e}', file=sys.stderr)
        return 4
    print(f"ok: {st['key']} at {st['bytes']} bytes, subsections {st['subsections']}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest='cmd', required=True)

    c = sub.add_parser('candidates')
    c.add_argument('files', nargs='+')
    c.add_argument('--before', help='date cutoff YYYY-MM-DD, exclusive')

    i = sub.add_parser('inspect')
    i.add_argument('file')
    i.add_argument('heading')

    b = sub.add_parser('backup')
    b.add_argument('file')
    b.add_argument('heading')
    b.add_argument('--root', required=True, help='the folder the backup sits under, outside the vault')
    b.add_argument('--project', required=True, help='the vault folder name')
    b.add_argument('--date', type=datetime.date.fromisoformat, default=datetime.date.today(),
                   help='backup date YYYY-MM-DD; defaults to today')

    v = sub.add_parser('verify')
    v.add_argument('file')
    v.add_argument('heading')
    v.add_argument('--backup', required=True, help='the path `backup` printed')
    v.add_argument('--pre-hash', required=True, help='the `hash` `inspect` printed before the edit')
    v.add_argument('--pre-subs', default='',
                   help='comma-joined ### names from before the edit that must survive')

    args = ap.parse_args(argv)
    return {'candidates': cmd_candidates, 'inspect': cmd_inspect,
            'backup': cmd_backup, 'verify': cmd_verify}[args.cmd](args)


if __name__ == '__main__':
    if sys.platform == 'win32':  # the console code page is not UTF-8; note text often is
        for _stream in (sys.stdout, sys.stderr):
            _stream.reconfigure(encoding='utf-8', errors='replace')
    raise SystemExit(main())
