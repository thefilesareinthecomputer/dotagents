#!/usr/bin/env python3
"""Select the dated sections a gather-learnings run reads, across one vault folder.

The `notes-*` logs are dated H2 sections, newest first: `## YYYY-MM-DD` with an
optional suffix (`## 2026-08-20-AB-AND-C`). File mtime cannot drive selection --
one edit restamps the whole file -- so the heading date is the only honest signal.
A heading is recognized by its date prefix alone, so `## 2026-08-20 - a title` is
listed too, flagged as non-canonical because section keys need the `-SUFFIX` form.

The default run is the daily one. Today's date comes from the clock unless pinned
with `--today`. Every `notes-*` file with a section dated today contributes those
sections, plus its most recent earlier date as the baseline they are checked
against. Files with nothing dated today are not in the run. The learnings file's
own entry for today, if one exists, is reported first, with every entry on its most
recent earlier date as the baseline today's entry is compared against once written.

`--days`, `--since`, `--calendar` and `--today-only` select the older lookback
windows instead.

`user-stories*.md` carry no dates at all. They are read by lookup instead: the
story ids named inside the selected sections are the keys, printed here so the
caller reads only those sections rather than a 272KB file.

stdlib only, one consumer (the gather-learnings skill).
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import vault_patterns as vp      # the skill's own copy, beside this script

LEARNINGS = 'notes-learnings.md'


def dated(path: Path, today: dt.date) -> tuple[list, int]:
    """(date, section) pairs for one file, loose headings included. Future dates are
    dropped, and a heading whose date is not a real date is counted, not listed."""
    secs, skipped = [], 0
    for s in vp.date_sections(path, loose=True):
        try:
            d = dt.date.fromisoformat(s['date'])
        except ValueError:
            skipped += 1
            continue
        if d <= today:
            secs.append((d, s))
    return secs, skipped


def previous(secs: list, today: dt.date) -> tuple[dt.date | None, list]:
    """Every section on the most recent date before today, however many share it."""
    earlier = [d for d, _ in secs if d < today]
    if not earlier:
        return None, []
    base = max(earlier)
    return base, [s for d, s in secs if d == base]


def today_and_baseline(secs: list, today: dt.date) -> tuple[list, dt.date | None, list]:
    """One file's sections dated today, and every section on its most recent earlier
    date. A file with nothing dated today returns nothing, baseline included."""
    todays = [s for d, s in secs if d == today]
    if not todays:
        return [], None, []
    return (todays, *previous(secs, today))


def learnings_state(vault: Path, today: dt.date) -> tuple[list, dt.date | None, list] | None:
    """The learnings file's entries dated today, and every entry on its most recent
    earlier date, which today's entry is compared against once written. None when
    the file is absent. The baseline is listed even before today's entry exists."""
    path = vault / LEARNINGS
    if not path.is_file():
        return None
    secs, _ = dated(path, today)
    return ([s for d, s in secs if d == today], *previous(secs, today))


def heading(s: dict) -> str:
    return s['body'].split('\n', 1)[0]


def key(s: dict) -> str | None:
    if not s['canonical']:
        return None
    return vp.section_key(s['file'], s['date'], s['suffix'], s['ord'])


def row(s: dict, indent: str, keyed: bool = True) -> str:
    """keyed=False for learnings entries, whose `## YYYY-MM-DD - title` heading is the
    house form and never needs a section key."""
    flag = '' if s['canonical'] or not keyed else '  [non-canonical heading, no section key]'
    return (f'{indent}L{s["start"]:>5}-{s["end"]:<5} {len(s["body"]):>7}b  '
            f'{heading(s)}{flag}')


def print_ids(ids: dict, what: str) -> None:
    if not ids:
        return
    print(f'\nwork items named in {what} ({len(ids)}) -- read these sections '
          f'from user-stories.md and the run sheet, not the whole file:')
    for wid in sorted(ids):
        print(f'    {wid:<16} {", ".join(sorted(ids[wid]))}')


def daily(vault: Path, today: dt.date, pinned: bool, ids_only: bool) -> None:
    runs, ids, skipped, quiet = [], {}, 0, []
    for path in vp.corpus(vault, 'notes'):        # excludes notes-learnings.md
        secs, bad = dated(path, today)
        skipped += bad
        todays, base, baseline = today_and_baseline(secs, today)
        if not todays:
            quiet.append(path.name)
            continue
        runs.append((path.name, todays, base, baseline))
        for s in todays:
            for wid in vp.work_item_ids(s['body']):
                ids.setdefault(wid, set()).add(key(s) or heading(s))

    if ids_only:
        for wid in sorted(ids):
            print(wid)
        return

    print(f'today {today}  ({"pinned with --today" if pinned else "runtime date"})')
    print(f'vault {vault}\n')

    state = learnings_state(vault, today)
    if state is None:
        print(f'learnings: no {LEARNINGS} in the vault')
    else:
        entries, base, baseline = state
        if not entries:
            print(f'learnings: no ## {today} entry yet -- create one at the top of the month block')
        else:
            print(f'learnings: ## {today} entry exists -- reconcile into it, never append a second')
            for s in entries:
                subs = sum(1 for ln in vp.lines_of(s['body']) if ln.startswith('### '))
                print(f'{row(s, "    ", keyed=False)}  ({subs} subsection(s))')
        if base is None:
            print('learnings baseline: none, no earlier dated entry')
        else:
            print(f'learnings baseline {base}  (after writing, compare today\'s entry against '
                  f'it and mark each supersession)')
            for s in baseline:
                print(row(s, '    ', keyed=False))

    if not runs:
        print(f'\nno section dated {today} in any notes-* file')
        if skipped:
            print(f'{skipped} unparseable date heading(s) skipped')
        return

    for name, todays, base, baseline in runs:
        print(f'\n{name}')
        if base is None:
            print('    baseline: none, no earlier dated section')
        else:
            print(f'    baseline {base}  (read first; check today against it)')
            for s in baseline:
                print(row(s, '        '))
        print(f'    today {today}')
        for s in todays:
            print(row(s, '        '))

    n_today = sum(len(r[1]) for r in runs)
    n_base = sum(len(r[3]) for r in runs)
    print(f'\n{n_today} section(s) dated today across {len(runs)} file(s); '
          f'{n_base} baseline section(s)')
    if quiet:
        print(f'not in this run (nothing dated {today}): {", ".join(quiet)}')
    if skipped:
        print(f'{skipped} unparseable date heading(s) skipped')
    print_ids(ids, "today's sections")


def lookback(vault: Path, today: dt.date, args) -> None:
    days = 3 if args.days is None else args.days
    if args.today_only:
        floor = today
    elif args.since:
        floor = dt.date.fromisoformat(args.since)
    else:
        floor = today - dt.timedelta(days=days)

    hits, ids, skipped = [], {}, 0
    for path in vp.corpus(vault, 'notes'):        # excludes notes-learnings.md
        secs, bad = dated(path, today)
        skipped += bad

        # PER-FILE REPRESENTED DATES, not a calendar window. "The last 3 days" means the
        # last 3 dates this file actually carries: a file that went quiet on Tuesday should
        # contribute Monday rather than dropping out of the sweep entirely. Files therefore
        # reach back different distances, and the walk still orders by real date across the
        # union.
        if args.today_only:
            keep = {today}
        elif args.since or args.calendar:
            keep = {d for d, _ in secs if d >= floor}
        else:
            # Bounded: a file with four entries all from July would otherwise drag the
            # window back seven weeks on the letter of "its last 4 dates". The reach cap
            # keeps the weekend/quiet-day tolerance without letting a dormant file decide
            # how far back the sweep goes.
            cap = today - dt.timedelta(days=args.max_reach)
            keep = {d for d in sorted({d for d, _ in secs}, reverse=True)[:days + 1]
                    if d >= cap}

        for d, s in secs:
            if d not in keep:
                continue
            hits.append((path.name, s))
            for wid in vp.work_item_ids(s['body']):
                ids.setdefault(wid, set()).add(key(s) or heading(s))

    if args.ids_only:
        for wid in sorted(ids):
            print(wid)
        return

    dates = sorted({s['date'] for _, s in hits})
    if args.today_only:
        mode = '--today-only'
    elif args.since:
        mode = '--since'
    elif args.calendar:
        mode = f'--days {days} calendar'
    else:
        mode = f'last {days + 1} represented dates per file'
    lo = dates[0] if dates else str(floor)
    print(f'window {lo} .. {today}  ({len(dates)} distinct date(s), {mode})')
    print(f'vault {vault}\n')
    if not hits:
        print('no dated sections in window')
        return

    current = None
    for name, s in sorted(hits, key=lambda h: (h[0], h[1]['date'], h[1]['suffix'],
                                                h[1]['start'])):
        if name != current:
            print(f'{name}')
            current = name
        print(row(s, '    '))

    print(f'\n{len(hits)} section(s) in window across '
          f'{len({h[0] for h in hits})} file(s)')
    if skipped:
        print(f'{skipped} unparseable date heading(s) skipped')
    print_ids(ids, 'in-window')


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('vault', help='the target vault folder')
    ap.add_argument('--days', type=int, default=None,
                    help='lookback mode: the last N dates per file PLUS the newest, 3 when '
                         'another lookback flag is given without it. Counted per file in '
                         'DATES THAT APPEAR, not calendar days, so a weekend gap or a quiet '
                         'Tuesday does not consume the window.')
    ap.add_argument('--calendar', action='store_true',
                    help='lookback mode, counting calendar days instead of represented dates')
    ap.add_argument('--max-reach', type=int, default=14, dest='max_reach',
                    help='hard floor in days for represented-date mode, default 14, so a '
                         'dormant file cannot drag the window back weeks')
    ap.add_argument('--since', help='lookback mode from an explicit YYYY-MM-DD floor')
    ap.add_argument('--today-only', action='store_true', dest='today_only',
                    help='today alone, with no baseline')
    ap.add_argument('--today', help='YYYY-MM-DD; pin today for a repeatable run')
    ap.add_argument('--ids-only', action='store_true', help='print just the work-item ids')
    args = ap.parse_args(argv)

    vault = Path(args.vault).expanduser()
    if not vault.is_dir():
        sys.exit(f'not a directory: {vault}')

    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    if args.today_only or args.since or args.calendar or args.days is not None:
        lookback(vault, today, args)
    else:
        daily(vault, today, bool(args.today), args.ids_only)


if __name__ == '__main__':
    if sys.platform == 'win32':  # the console code page is not UTF-8; note text often is
        for _stream in (sys.stdout, sys.stderr):
            _stream.reconfigure(encoding='utf-8', errors='replace')
    main()
