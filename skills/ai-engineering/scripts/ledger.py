#!/usr/bin/env python3
"""ledger.py - deterministic, scalable maintenance engine for the ai-engineering
link ledger and reference catalog.

Source of truth is resources/catalog.tsv (one row per URL). The human-readable
resources/link-ledger.md is a GENERATED view - never hand-edit it.

Design goals (per spec):
  * deterministic   - sorted I/O, stable rules, idempotent render.
  * scalable        - classification is data-driven (rules.tsv + seed-sections.tsv);
                      adding tools/domains is a data edit, never a code change.
  * freshness       - every row carries last_checked; `check` flags stale rows by
                      TTL and can optionally probe URLs for liveness.
  * conflict-aware  - re-classifying an existing URL never silently clobbers:
                      manual rows win; otherwise tags are unioned. Conflicts are
                      recorded to resources/_conflicts.tsv (a tracked hot/cold
                      ledger: latest per URL is `hot`, superseded rows go `cold`;
                      identical re-conflicts are de-duplicated, so it can't bloat).

Commands:
  seed   --from-md FILE       (re)build catalog from a markdown bundle + rules + seed
  ingest [--from FILE | URLS] add/update URLs (dedupe, classify, conflict-log)
  set    URL --sections A|B   manually curate a URL (manual flag wins conflicts)
  render                      regenerate link-ledger.md from catalog
  check  [--ttl N] [--probe]  freshness report; --probe does network liveness
  conflicts [--prune --ttl N] show hot/cold conflict ledger; prune ages out cold
  field-note URL --verdict V --finding "..."   append first-hand experience
  field-notes [URL] [--verdict V]              read field notes back
  render-notes                regenerate field-notes.md from field-notes.tsv

Stdlib only. Python 3.8+.
"""
from __future__ import annotations
import argparse, csv, datetime, os, re, sys, urllib.request, urllib.error, urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
RES = HERE.parent / "resources"
CATALOG = RES / "catalog.tsv"
RULES = RES / "rules.tsv"
SEED = RES / "seed-sections.tsv"
LEDGER_MD = RES / "link-ledger.md"
CONFLICTS = RES / "_conflicts.tsv"
FIELD_NOTES = RES / "field-notes.tsv"
FIELD_NOTES_MD = RES / "field-notes.md"
DECISIONS = RES / "stack-decisions.tsv"
STACK_MAP = RES / "agent-stack-map.md"

FIELDS = ["url", "sections", "status", "source", "added", "last_checked",
          "claims_checked", "note"]
CONFLICT_FIELDS = ["seq", "date", "url", "kind", "resolution", "state"]
FIELD_NOTE_FIELDS = ["date", "url", "verdict", "scope", "finding", "evidence"]
VERDICTS = ("works", "caution", "broken", "superseded")
DECISION_FIELDS = ["date", "use_case", "layer", "component_url", "rationale", "outcome"]
OUTCOMES = ("held", "replaced", "abandoned")
TODAY = datetime.date.today().isoformat()
URL_RE = re.compile(r'https?://[^\s)`<>"\']+')


# ---------- canonicalization (deterministic dedup key) ----------
def canon(u: str) -> str:
    u = u.strip().rstrip('.,;')
    u = u.split('#', 1)[0]
    m = re.match(r'(https?)://([^/]+)(.*)$', u, re.I)
    if not m:
        return u
    scheme, host, rest = m.group(1).lower(), m.group(2).lower(), m.group(3)
    if rest != '/' and rest.endswith('/'):
        rest = rest.rstrip('/')
    return f"{scheme}://{host}{rest}"


def host_repo(u: str):
    """Extract (site, owner/repo) for github.com and deepwiki.com (talk-to-repo)."""
    m = re.match(r'https?://(github|deepwiki)\.com/([^/]+/[^/?#]+)', u)
    return (m.group(1), m.group(2)) if m else (None, None)


# ---------- data loading ----------
def load_rules():
    rules = []
    if RULES.exists():
        for line in RULES.read_text().splitlines():
            if not line.strip() or line.startswith('#') or '\t' not in line:
                continue
            pat, secs = line.split('\t', 1)
            rules.append((pat.strip(), secs.strip()))
    return rules


def load_seed():
    seed = {}
    if SEED.exists():
        for line in SEED.read_text().splitlines():
            if not line.strip() or line.startswith('#') or '\t' not in line:
                continue
            repo, secs = line.split('\t', 1)
            seed[repo.strip()] = secs.strip()
    return seed


def classify(u: str, rules, seed):
    """Deterministic: repo (github/deepwiki) > rules (domain) > repo-triage > adjacent.
    DeepWiki URLs inherit the underlying repo's sections plus a `deepwiki` tag."""
    site, repo = host_repo(u)
    if repo and repo in seed:
        secs = seed[repo]
        return union_sections(secs, 'deepwiki') if site == 'deepwiki' else secs
    for pat, secs in rules:
        if pat.startswith('re:'):
            if re.search(pat[3:], u):
                return secs
        elif pat in u:
            return secs
    if repo:
        return union_sections('triage', 'deepwiki') if site == 'deepwiki' else 'triage'
    return 'adjacent'


def load_catalog():
    rows = {}
    if CATALOG.exists():
        with CATALOG.open(newline='') as f:
            for r in csv.DictReader(f, delimiter='\t'):
                rows[canon(r['url'])] = r
    return rows


def save_catalog(rows):
    ordered = sorted(rows.values(), key=lambda r: canon(r['url']))
    with CATALOG.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, delimiter='\t')
        w.writeheader()
        for r in ordered:
            w.writerow({k: r.get(k, '') for k in FIELDS})
    return len(ordered)


def union_sections(a: str, b: str) -> str:
    seen, out = set(), []
    for s in (a or '').split('|') + (b or '').split('|'):
        s = s.strip()
        if s and s not in seen:
            seen.add(s); out.append(s)
    return '|'.join(out)


# ---------- conflict ledger (tracked TSV; hot = latest per URL, cold = superseded) ----------
_PENDING = []  # (url, kind, resolution) gathered during a run, flushed once at the end


def record_conflict(url, kind, resolution):
    """Queue a conflict; applied in one write by flush_conflicts() at command end."""
    _PENDING.append((canon(url), kind, resolution))


def load_conflicts():
    rows = []
    if CONFLICTS.exists():
        with CONFLICTS.open(newline='') as f:
            for r in csv.DictReader(f, delimiter='\t'):
                rows.append(r)
    return rows


def save_conflicts(rows):
    ordered = sorted(rows, key=lambda r: (r['url'], int(r['seq'])))
    with CONFLICTS.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=CONFLICT_FIELDS, delimiter='\t')
        w.writeheader()
        for r in ordered:
            w.writerow({k: r.get(k, '') for k in CONFLICT_FIELDS})
    return len(ordered)


def flush_conflicts():
    """Apply queued conflicts: content-dedup, then per-URL supersession. One write.

    Idempotent: a conflict identical to the URL's current hot row is a no-op (this
    is what stops recurring curated URLs from re-logging every refresh). Otherwise
    the URL's prior hot row is demoted to `cold` and the new one becomes `hot`. A
    monotonic `seq` gives a stable tiebreak for same-day events. Returns (new, superseded)."""
    if not _PENDING:
        return (0, 0)
    rows = load_conflicts()
    seq = max((int(r['seq']) for r in rows), default=0)
    new = superseded = 0
    for url, kind, resolution in _PENDING:
        hot = [r for r in rows if r['url'] == url and r['state'] == 'hot']
        if hot and hot[-1]['kind'] == kind and hot[-1]['resolution'] == resolution:
            continue  # identical to current hot -> no-op (dedup / idempotent)
        for r in hot:
            r['state'] = 'cold'; superseded += 1
        seq += 1
        rows.append(dict(seq=str(seq), date=TODAY, url=url, kind=kind,
                         resolution=resolution, state='hot'))
        new += 1
    save_conflicts(rows)
    _PENDING.clear()
    return (new, superseded)


# ---------- field notes (append-only record of first-hand experience) ----------
def load_field_notes():
    rows = []
    if FIELD_NOTES.exists():
        with FIELD_NOTES.open(newline='') as f:
            for r in csv.DictReader(f, delimiter='\t'):
                rows.append(r)
    return rows


def save_field_notes(rows):
    """Sorted by url then date so the file diffs cleanly; append-only by policy,
    meaning a later note never rewrites an earlier one."""
    ordered = sorted(rows, key=lambda r: (r['url'], r['date']))
    with FIELD_NOTES.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELD_NOTE_FIELDS, delimiter='\t')
        w.writeheader()
        for r in ordered:
            w.writerow({k: r.get(k, '') for k in FIELD_NOTE_FIELDS})
    return len(ordered)


def add_field_note(url, verdict, finding, scope='', evidence='', date=None):
    """Append one observation. Rejects an unknown verdict and any URL absent from
    the catalog, which is what keeps notes joined to the spine instead of drifting
    into an island. Returns the stored row."""
    if verdict not in VERDICTS:
        raise ValueError(f"unknown verdict '{verdict}'; expected one of {', '.join(VERDICTS)}")
    if not finding.strip():
        raise ValueError("a field note needs a finding")
    c = canon(url)
    if c not in load_catalog():
        raise ValueError(f"{c} is not in the catalog; ingest it before noting it")
    row = dict(date=date or TODAY, url=c, verdict=verdict, scope=scope,
               finding=finding.strip(), evidence=evidence)
    rows = load_field_notes()
    rows.append(row)
    save_field_notes(rows)
    return row


# ---------- stack decisions (what was committed, and whether it held) ----------
def load_decisions():
    rows = []
    if DECISIONS.exists():
        with DECISIONS.open(newline='') as f:
            for r in csv.DictReader(f, delimiter='\t'):
                rows.append(r)
    return rows


def save_decisions(rows):
    ordered = sorted(rows, key=lambda r: (r['use_case'], r['layer'], r['date']))
    with DECISIONS.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=DECISION_FIELDS, delimiter='\t')
        w.writeheader()
        for r in ordered:
            w.writerow({k: r.get(k, '') for k in DECISION_FIELDS})
    return len(ordered)


def add_decision(use_case, layer, component_url, rationale, date=None):
    """Record one committed slot. `outcome` starts empty and is stamped later by
    the next run against a matching use-case shape."""
    if not use_case.strip() or not layer.strip():
        raise ValueError("a decision needs both a use_case shape and a layer")
    c = canon(component_url)
    if c not in load_catalog():
        raise ValueError(f"{c} is not in the catalog; ingest it before deciding on it")
    row = dict(date=date or TODAY, use_case=use_case.strip(), layer=layer.strip(),
               component_url=c, rationale=rationale.strip(), outcome='')
    rows = load_decisions()
    rows.append(row)
    save_decisions(rows)
    return row


def stamp_outcome(use_case, layer, outcome):
    """Close the loop on a prior decision. Stamps the most recent unstamped row
    for that shape and layer; returns the row, or None if there was nothing open."""
    if outcome not in OUTCOMES:
        raise ValueError(f"unknown outcome '{outcome}'; expected one of {', '.join(OUTCOMES)}")
    rows = load_decisions()
    open_rows = [r for r in rows
                 if r['use_case'] == use_case.strip()
                 and r['layer'] == layer.strip()
                 and not r['outcome']]
    if not open_rows:
        return None
    target = max(open_rows, key=lambda r: r['date'])
    target['outcome'] = outcome
    save_decisions(rows)
    return target


def _older_than(row, days, field='date'):
    d = row.get(field) or ''
    try:
        return (datetime.date.today() - datetime.date.fromisoformat(d)).days > days
    except ValueError:
        return False


def extract_urls(text: str):
    seen, out = set(), []
    for m in URL_RE.findall(text):
        c = canon(m)
        if c not in seen:
            seen.add(c); out.append(c)
    return out


# ---------- upsert with conflict resolution ----------
def upsert(rows, url, source, rules, seed, manual_sections=None):
    c = canon(url)
    new_sec = manual_sections if manual_sections is not None else classify(c, rules, seed)
    status = 'triage' if new_sec == 'triage' else 'active'
    if c not in rows:
        rows[c] = dict(url=c, sections=new_sec, status=status, source=source,
                       added=TODAY, last_checked='', claims_checked='',
                       note='manual' if manual_sections is not None else '')
        return 'added'
    row = rows[c]
    if manual_sections is not None:
        if row['sections'] != manual_sections:
            record_conflict(c, 'manual-override', f"'{row['sections']}' -> '{manual_sections}'")
        row['sections'] = manual_sections
        row['note'] = 'manual'
        row['status'] = status
        return 'curated'
    if row.get('note') == 'manual':
        if union_sections(row['sections'], new_sec) != row['sections']:
            record_conflict(c, 'kept-manual', f"kept '{row['sections']}', auto said '{new_sec}'")
        return 'kept-manual'
    merged = union_sections(row['sections'], new_sec)
    if merged != row['sections']:
        record_conflict(c, 'tag-union', f"'{row['sections']}' + '{new_sec}' -> '{merged}'")
        row['sections'] = merged
        return 'updated'
    return 'unchanged'


# ---------- commands ----------
def cmd_seed(args):
    rules, seed = load_rules(), load_seed()
    rows = load_catalog()
    text = Path(args.from_md).read_text()
    urls = extract_urls(text)
    tally = {}
    for u in urls:
        res = upsert(rows, u, source=os.path.basename(args.from_md), rules=rules, seed=seed)
        tally[res] = tally.get(res, 0) + 1
    n = save_catalog(rows)
    cnew, csup = flush_conflicts()
    print(f"seed: scanned {len(urls)} urls from {args.from_md}")
    print("  " + ", ".join(f"{k}={v}" for k, v in sorted(tally.items())))
    print(f"  catalog now {n} rows -> {CATALOG}")
    if cnew or csup:
        print(f"  conflicts: +{cnew} hot, {csup} superseded -> {CONFLICTS.name}")


def cmd_ingest(args):
    rules, seed = load_rules(), load_seed()
    rows = load_catalog()
    urls = []
    if args.from_file:
        urls += extract_urls(Path(args.from_file).read_text())
    for u in args.urls:
        urls += extract_urls(u)
    tally = {}
    for u in urls:
        res = upsert(rows, u, source=args.source or 'ingest', rules=rules, seed=seed)
        tally[res] = tally.get(res, 0) + 1
    n = save_catalog(rows)
    cnew, csup = flush_conflicts()
    print(f"ingest: {len(urls)} urls; " + ", ".join(f"{k}={v}" for k, v in sorted(tally.items())))
    print(f"  catalog now {n} rows")
    if cnew or csup:
        print(f"  conflicts: +{cnew} hot, {csup} superseded -> {CONFLICTS.name}")


def cmd_set(args):
    rules, seed = load_rules(), load_seed()
    rows = load_catalog()
    res = upsert(rows, args.url, source='manual', rules=rules, seed=seed,
                 manual_sections=args.sections)
    save_catalog(rows)
    cnew, csup = flush_conflicts()
    print(f"set {canon(args.url)} -> {args.sections} ({res})")
    if cnew or csup:
        print(f"  conflicts: +{cnew} hot, {csup} superseded -> {CONFLICTS.name}")


def cmd_render(args):
    rows = sorted(load_catalog().values(), key=lambda r: canon(r['url']))
    lines = [
        "---",
        "name: link-ledger",
        "description: Master deduplicated record of every URL folded into the ai-engineering skill, tagged by section. GENERATED from catalog.tsv by scripts/ledger.py - do not hand-edit.",
        f"updated: {TODAY}",
        "---",
        "",
        "# Link Ledger - already folded in",
        "",
        "Alphabetized, deduplicated record of **every URL** absorbed into this skill, "
        "each tagged with the section(s) it is represented in. A `map` tag means the URL "
        "also has a row in `agent-stack-map.md`. Before adding any link, check here first.",
        "",
        "> Generated by `scripts/ledger.py render` from `catalog.tsv`. Edit the catalog, "
        "not this file. Sections come from `rules.tsv` + `seed-sections.tsv`.",
        "",
        f"Count: {len(rows)} URLs · last reconciled {TODAY}",
        "",
    ]
    for r in rows:
        secs = r['sections'].replace('|', ', ')
        flag = ' ⚠️stale' if args.mark_stale and _is_stale(r, args.ttl) else ''
        lines.append(f"- {r['url']}  - `{secs}`{flag}")
    LEDGER_MD.write_text("\n".join(lines) + "\n")
    print(f"render: wrote {len(rows)} rows -> {LEDGER_MD}")


def _is_stale(row, ttl, field='last_checked'):
    lc = row.get(field) or ''
    if not lc:
        return True
    try:
        d = datetime.date.fromisoformat(lc)
    except ValueError:
        return True
    return (datetime.date.today() - d).days > ttl


class _SchemeBoundRedirects(urllib.request.HTTPRedirectHandler):
    """Re-check the scheme on every hop. Validating only the URL the caller passed
    leaves the redirect chain unguarded, and a 30x to file: or ftp: lands back in
    the same place the initial check was added to prevent."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme not in ('http', 'https'):
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _probe(url, timeout=8):
    # Only ever speak http(s). urlopen also honors file:, ftp: and data:, so a
    # catalog row carrying one of those would turn a liveness check into a local
    # file read reported as a status.
    if urllib.parse.urlsplit(url).scheme not in ('http', 'https'):
        return False, 'unsupported-scheme'
    req = urllib.request.Request(url, method='HEAD', headers={'User-Agent': 'ledger/1.0'})
    try:
        with urllib.request.build_opener(_SchemeBoundRedirects).open(
                req, timeout=timeout) as resp:
            return resp.status < 400, resp.status
    except urllib.error.HTTPError as e:
        # some hosts reject HEAD; treat 405/403 as alive-ish
        return e.code in (403, 405), e.code
    except Exception as e:
        return False, type(e).__name__


def _has_section(row, section):
    return section in (row.get('sections') or '').split('|')


def cmd_check(args):
    rows = sorted(load_catalog().values(), key=lambda r: canon(r['url']))
    if args.claims:
        return _check_claims(rows, args)
    stale = [r for r in rows if _is_stale(r, args.ttl)]
    print(f"check: {len(rows)} rows, ttl={args.ttl}d -> {len(stale)} stale/unchecked")
    dead = []
    if args.probe:
        catalog = load_catalog()
        checked = 0
        for r in stale[: args.limit] if args.limit else stale:
            ok, info = _probe(r['url'])
            checked += 1
            row = catalog[canon(r['url'])]
            row['last_checked'] = TODAY
            if not ok:
                row['status'] = 'dead'
                dead.append((r['url'], info))
            elif row.get('status') == 'dead':
                row['status'] = 'active'
        save_catalog(catalog)
        print(f"  probed {checked}; dead={len(dead)} (last_checked updated)")
        for u, info in dead:
            print(f"    DEAD {info}\t{u}")
    else:
        for r in stale[:50]:
            print(f"    stale\t{r.get('last_checked') or 'never'}\t{r['url']}")
        if len(stale) > 50:
            print(f"    … +{len(stale) - 50} more (use --probe to verify liveness)")


def cmd_field_note(args):
    row = add_field_note(args.url, args.verdict, args.finding,
                         scope=args.scope or '', evidence=args.evidence or '')
    print(f"field-note: {row['verdict']}\t{row['url']}")
    print(f"  {row['date']}  {row['finding']}")
    if row['scope']:
        print(f"  scope: {row['scope']}")


def cmd_field_notes(args):
    rows = load_field_notes()
    if args.url:
        c = canon(args.url)
        rows = [r for r in rows if r['url'] == c]
    if args.verdict:
        rows = [r for r in rows if r['verdict'] == args.verdict]
    print(f"field-notes: {len(rows)} note(s)")
    for r in sorted(rows, key=lambda r: (r['url'], r['date']), reverse=True):
        scope = f" [{r['scope']}]" if r['scope'] else ''
        print(f"    {r['date']}  {r['verdict']:9}{r['url']}{scope}")
        print(f"        {r['finding']}")


def cmd_render_notes(args):
    """Generated view, grouped by URL with the newest note first so a reader
    reaches the current state before the history."""
    rows = load_field_notes()
    by_url = {}
    for r in rows:
        by_url.setdefault(r['url'], []).append(r)
    lines = [
        "---",
        "name: field-notes",
        "description: First-hand record of what happened when these tools were actually used. GENERATED from field-notes.tsv by scripts/ledger.py - do not hand-edit.",
        f"updated: {TODAY}",
        "---",
        "",
        "# Field notes - what happened when we used it",
        "",
        "Dated observations from actually running these tools, newest first per tool. "
        "A note here outranks a project's own description of itself, because it is "
        "evidence rather than a claim. Contradicting notes both survive: a tool that "
        "was broken at one version and sound at the next is real history.",
        "",
        "> Generated by `scripts/ledger.py render-notes` from `field-notes.tsv`. "
        "Edit the TSV through `ledger.py field-note`, not this file.",
        "",
        f"Count: {len(rows)} notes across {len(by_url)} tools · last reconciled {TODAY}",
        "",
    ]
    for url in sorted(by_url):
        lines.append(f"## {url}")
        lines.append("")
        for r in sorted(by_url[url], key=lambda r: r['date'], reverse=True):
            scope = f" ({r['scope']})" if r['scope'] else ''
            evidence = f" - {r['evidence']}" if r['evidence'] else ''
            lines.append(f"- **{r['verdict']}** {r['date']}{scope}: {r['finding']}{evidence}")
        lines.append("")
    FIELD_NOTES_MD.write_text("\n".join(lines) + "\n")
    print(f"render-notes: wrote {len(rows)} notes across {len(by_url)} tools -> {FIELD_NOTES_MD}")


def cmd_decision(args):
    row = add_decision(args.use_case, args.layer, args.component, args.rationale or '')
    print(f"decision: {row['layer']} -> {row['component_url']}")
    print(f"  use case: {row['use_case']}")
    if row['rationale']:
        print(f"  because: {row['rationale']}")


def cmd_outcome(args):
    row = stamp_outcome(args.use_case, args.layer, args.outcome)
    if row is None:
        print(f"outcome: no open decision for '{args.use_case}' / {args.layer}")
        return
    print(f"outcome: {row['layer']} {row['component_url']} -> {row['outcome']}"
          f" (decided {row['date']})")


def cmd_decisions(args):
    rows = load_decisions()
    if args.use_case:
        rows = [r for r in rows if args.use_case.lower() in r['use_case'].lower()]
    if args.open_only:
        rows = [r for r in rows if not r['outcome']]
    print(f"decisions: {len(rows)} row(s)"
          f"{' matching ' + repr(args.use_case) if args.use_case else ''}")
    for r in sorted(rows, key=lambda r: (r['use_case'], r['layer'])):
        state = r['outcome'] or 'open'
        print(f"    {r['date']}  {r['use_case']}")
        print(f"        {r['layer']:24}{r['component_url']}  [{state}]")
        if r['rationale']:
            print(f"        because: {r['rationale']}")


def _check_claims(rows, args):
    """The claims queue. Liveness (`last_checked`) says a URL resolves; it says
    nothing about whether the map's assertions still hold. This lists map-tagged
    rows whose CLAIMS are unverified past the TTL, so a research pass has a
    finite work list. Scoped deliberately: a queue nobody can drain gets ignored,
    and stamping rows nobody checked would assert a rigor that did not happen."""
    scope = [r for r in rows if _has_section(r, 'map')]
    if args.section:
        scope = [r for r in scope if _has_section(r, args.section)]
    stale = [r for r in scope if _is_stale(r, args.ttl, field='claims_checked')]
    label = f" in '{args.section}'" if args.section else ''
    print(f"check --claims: {len(scope)} map rows{label}, ttl={args.ttl}d "
          f"-> {len(stale)} with unverified claims")
    for r in stale[: args.limit] if args.limit else stale:
        print(f"    {r.get('claims_checked') or 'never':12}{r['url']}")
    if not args.limit and len(stale) > 0:
        print(f"  verify these against a live source, correct agent-stack-map.md, "
              f"then stamp with: ledger.py verified <url>...")


def cmd_sync_map_tags(args):
    """Derive the `map` tag from agent-stack-map.md instead of trusting a
    hand-maintained tag.

    The tag means "this URL has a row in the map", and it is the join the claims
    queue scopes on. Left to accumulate it drifts: a domain rule granting `map`
    tags every documentation subpage on that host, which silently inflates the
    queue with pages that were never map rows. Deriving it makes the tag true by
    construction and self-correcting."""
    if not STACK_MAP.exists():
        print(f"sync-map-tags: {STACK_MAP} not found"); return
    in_map = {canon(u) for u in extract_urls(STACK_MAP.read_text())}
    catalog = load_catalog()
    added = removed = 0
    for c, row in catalog.items():
        tags = [t for t in row['sections'].split('|') if t]
        has = 'map' in tags
        should = c in in_map
        if should and not has:
            tags.append('map'); added += 1
        elif has and not should:
            tags = [t for t in tags if t != 'map']; removed += 1
        else:
            continue
        row['sections'] = '|'.join(tags)
    if added or removed:
        save_catalog(catalog)
    unmatched = in_map - set(catalog)
    print(f"sync-map-tags: {len(in_map)} URLs in the map; "
          f"+{added} tagged, -{removed} untagged")
    if unmatched:
        print(f"  {len(unmatched)} map URL(s) not in the catalog - ingest them:")
        for u in sorted(unmatched):
            print(f"    {u}")


def cmd_verified(args):
    """Stamp claims_checked after verdicts have actually landed in the map."""
    catalog = load_catalog()
    stamped, missing = 0, []
    for u in args.urls:
        c = canon(u)
        if c not in catalog:
            missing.append(c); continue
        catalog[c]['claims_checked'] = TODAY
        stamped += 1
    if stamped:
        save_catalog(catalog)
    print(f"verified: stamped {stamped} row(s) as claims-checked {TODAY}")
    for m in missing:
        print(f"    NOT IN CATALOG {m}")


def cmd_conflicts(args):
    rows = load_conflicts()
    hot = [r for r in rows if r['state'] == 'hot']
    cold = [r for r in rows if r['state'] == 'cold']
    if args.prune:
        keep = [r for r in rows if not (r['state'] == 'cold' and _older_than(r, args.ttl))]
        dropped = len(rows) - len(keep)
        save_conflicts(keep)
        kh = sum(1 for r in keep if r['state'] == 'hot')
        kc = len(keep) - kh
        print(f"conflicts: pruned {dropped} cold rows older than {args.ttl}d "
              f"(recoverable from git history); now {kh} hot, {kc} cold")
        return
    oldest = min((r['date'] for r in cold), default='-')
    print(f"conflicts: {len(hot)} hot, {len(cold)} cold (oldest cold {oldest})")
    for r in sorted(hot, key=lambda r: r['url']):
        print(f"    HOT  {r['date']}  [{r['kind']}]  {r['url']}  {r['resolution']}")


def main(argv=None):
    p = argparse.ArgumentParser(description="ai-engineering ledger engine")
    sub = p.add_subparsers(dest='cmd', required=True)

    s = sub.add_parser('seed'); s.add_argument('--from-md', dest='from_md', required=True); s.set_defaults(fn=cmd_seed)
    i = sub.add_parser('ingest')
    i.add_argument('urls', nargs='*'); i.add_argument('--from', dest='from_file')
    i.add_argument('--source', default='ingest'); i.set_defaults(fn=cmd_ingest)
    st = sub.add_parser('set'); st.add_argument('url'); st.add_argument('--sections', required=True); st.set_defaults(fn=cmd_set)
    r = sub.add_parser('render'); r.add_argument('--mark-stale', action='store_true')
    r.add_argument('--ttl', type=int, default=90); r.set_defaults(fn=cmd_render)
    c = sub.add_parser('check'); c.add_argument('--ttl', type=int, default=90)
    c.add_argument('--probe', action='store_true'); c.add_argument('--limit', type=int, default=0)
    c.add_argument('--claims', action='store_true',
                   help='queue map rows whose CLAIMS are unverified, not just their URLs')
    c.add_argument('--section', help='narrow the claims queue to one section')
    c.set_defaults(fn=cmd_check)
    v = sub.add_parser('verified', help='stamp claims_checked after verifying a row')
    v.add_argument('urls', nargs='+'); v.set_defaults(fn=cmd_verified)
    smt = sub.add_parser('sync-map-tags',
                         help='derive the map tag from agent-stack-map.md')
    smt.set_defaults(fn=cmd_sync_map_tags)
    cf = sub.add_parser('conflicts'); cf.add_argument('--prune', action='store_true')
    cf.add_argument('--ttl', type=int, default=90); cf.set_defaults(fn=cmd_conflicts)

    note = sub.add_parser('field-note', help='record first-hand experience with a tool')
    note.add_argument('url'); note.add_argument('--verdict', required=True, choices=VERDICTS)
    note.add_argument('--finding', required=True)
    note.add_argument('--scope', help='the condition it held under: version, OS, workload')
    note.add_argument('--evidence', help='commit, error string, or issue URL')
    note.set_defaults(fn=cmd_field_note)
    fns = sub.add_parser('field-notes', help='read field notes back')
    fns.add_argument('url', nargs='?'); fns.add_argument('--verdict', choices=VERDICTS)
    fns.set_defaults(fn=cmd_field_notes)
    rn = sub.add_parser('render-notes'); rn.set_defaults(fn=cmd_render_notes)

    dec = sub.add_parser('decision', help='record a committed stack slot')
    dec.add_argument('--use-case', dest='use_case', required=True,
                     help='the SHAPE of the problem, never a project name')
    dec.add_argument('--layer', required=True)
    dec.add_argument('--component', required=True, help='canonical URL, must be catalogued')
    dec.add_argument('--rationale', help='the constraint that decided it')
    dec.set_defaults(fn=cmd_decision)
    out = sub.add_parser('outcome', help='stamp whether a prior decision held')
    out.add_argument('--use-case', dest='use_case', required=True)
    out.add_argument('--layer', required=True)
    out.add_argument('--outcome', required=True, choices=OUTCOMES)
    out.set_defaults(fn=cmd_outcome)
    decs = sub.add_parser('decisions', help='read decisions back; the intake query')
    decs.add_argument('use_case', nargs='?')
    decs.add_argument('--open', dest='open_only', action='store_true',
                      help='only rows whose outcome is unstamped')
    decs.set_defaults(fn=cmd_decisions)

    args = p.parse_args(argv)
    args.fn(args)


if __name__ == '__main__':
    main()
