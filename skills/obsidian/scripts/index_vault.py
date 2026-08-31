#!/usr/bin/env python3
"""index_vault.py - generate a vault meta-index (INDEX.md) for any Obsidian vault.

Portable, stdlib-only. Enforces one indexing method across every vault:

  * **gitignore parity + no dot folders** - in a git repo, files are enumerated via
    `git ls-files --cached --others --exclude-standard`, i.e. exactly the set git does
    NOT ignore; outside a git repo it falls back to a skip-folder walk. Dot folders and
    dotfiles (`.obsidian`, `.git`, `.claude`, `.trash`, …) are always excluded - Obsidian
    hides them, so they are not vault notes.
  * **root first, then subfolders alphabetically (recursive)** - deterministic order.
  * **per-file header tree as heading wiki-links** - under each `[[file]]`, its section
    headers are nested as `[[file#Heading|Heading]]`, 4-space indent per level. This makes
    INDEX.md a navigable deep-index and a hub in the Obsidian graph. Convention-agnostic:
    any heading style counts; fence-aware (ignores `#` inside code blocks); the leading
    H1 title is dropped (it's already the file link).

Usage:
  python3 index_vault.py [--vault PATH] [--output INDEX.md] [--no-trees]
                         [--tree-exclude DIR,DIR] [--max-headings N]

Vault root: --vault, else the nearest ancestor of CWD containing `.obsidian/`, else CWD.
"""

import os
import re
import sys
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

SKIP_FOLDERS = {'.git', '.obsidian', '.trash', '.smart-env', 'node_modules',
                '.venv', 'venv', '__pycache__', '.pytest_cache'}
_LINK_BREAKERS = set('[]#|')


def find_vault_root(start: Path) -> Path:
    """Nearest ancestor (incl. start) containing `.obsidian/`, else start."""
    start = start.resolve()
    for d in [start, *start.parents]:
        if (d / '.obsidian').is_dir():
            return d
    return start


def frontmatter_tags_dates(raw: str):
    """Cheap frontmatter scan for tags + date-created/last-modified + body offset.

    Returns (tags:list, date_created:str, last_modified:str, has_fm:bool, body:str).
    Deliberately minimal - no PyYAML, no full parse.
    """
    if not raw.startswith('---'):
        return [], '', '', False, raw
    m = re.search(r'\n---\s*\n', raw)
    if not m:
        return [], '', '', False, raw
    block, body = raw[3:m.start()], raw[m.end():]
    tags, dc, lm, cur = [], '', '', None
    for line in block.splitlines():
        km = re.match(r'^(\w[\w-]*):\s*(.*)$', line)
        if km:
            cur = km.group(1)
            val = km.group(2).strip()
            if cur == 'date-created':
                dc = val.strip('"\'')
            elif cur == 'last-modified':
                lm = val.strip('"\'')
            elif cur == 'tags' and val.startswith('['):
                tags = [t.strip().strip('"\'') for t in val[1:-1].split(',') if t.strip()]
            continue
        lm2 = re.match(r'^\s+-\s+(.*)$', line)
        if lm2 and cur == 'tags':
            tags.append(lm2.group(1).strip().strip('"\''))
    return tags, dc, lm, True, body


def extract_headings(body: str, max_headings: int):
    """ATX headings as [(level, text)], fence-aware, leading-H1 title dropped."""
    heads, in_fence, marker = [], False, None
    for line in body.splitlines():
        s = line.lstrip()
        if s.startswith('```') or s.startswith('~~~'):
            mk = s[:3]
            if not in_fence:
                in_fence, marker = True, mk
            elif s.startswith(marker):
                in_fence, marker = False, None
            continue
        if in_fence:
            continue
        m = re.match(r'^(#{1,6})\s+(.+?)\s*#*\s*$', line)
        if m:
            heads.append((len(m.group(1)), m.group(2).strip()))
    if heads and heads[0][0] == 1:
        heads = heads[1:]
    return heads[:max_headings]


def render_heading_tree(basename: str, headings, base_indent='    '):
    """Nested wiki-link list under a file entry; monotonic-stack depth; 4-space indent."""
    if not headings:
        return []
    lines, ancestors = [], []
    for level, text in headings:
        while ancestors and ancestors[-1] >= level:
            ancestors.pop()
        depth = len(ancestors)
        ancestors.append(level)
        indent = base_indent + '    ' * depth
        if text and not (_LINK_BREAKERS & set(text)):
            node = f'[[{basename}#{text}|{text}]]'
        else:
            node = text
        lines.append(f'{indent}- {node}')
    return lines


def list_markdown_files(vault: Path):
    """`.md` files under vault with gitignore parity (git), else a skip-folder walk."""
    files = None
    try:
        out = subprocess.run(
            ['git', '-C', str(vault), 'ls-files', '--cached', '--others', '--exclude-standard'],
            capture_output=True, text=True)
        if out.returncode == 0:
            files = [vault / ln for ln in out.stdout.splitlines() if ln.endswith('.md')]
    except Exception:
        files = None
    if files is None:
        files = []
        for root, dirs, names in os.walk(vault):
            dirs[:] = [d for d in dirs if d not in SKIP_FOLDERS]
            files.extend(Path(root) / n for n in names if n.endswith('.md'))
    result = []
    for p in files:
        if not p.exists():
            continue
        rel = p.relative_to(vault)
        # Exclude dot folders / dotfiles (Obsidian hides them) and curated skip folders.
        if any(part.startswith('.') for part in rel.parts):
            continue
        if any(part in SKIP_FOLDERS for part in rel.parts):
            continue
        result.append(p)
    return result


def build_index(vault: Path, output: str, trees: bool, tree_exclude: set, max_headings: int):
    entries = []
    for path in list_markdown_files(vault):
        rel = path.relative_to(vault)
        raw = path.read_text(encoding='utf-8', errors='replace')
        tags, dc, lm, has_fm, body = frontmatter_tags_dates(raw)
        folder = str(rel.parent) if str(rel.parent) != '.' else '(root)'
        top = rel.parts[0] if len(rel.parts) > 1 else '(root)'
        heads = []
        if trees and path.name != output and top not in tree_exclude:
            heads = extract_headings(body, max_headings)
        entries.append({'rel': str(rel), 'folder': folder, 'basename': path.name[:-3],
                        'tags': tags, 'dc': dc, 'lm': lm, 'has_fm': has_fm, 'heads': heads})
    # root first, then folders alphabetically (recursive); files alphabetical within.
    entries.sort(key=lambda e: (0 if e['folder'] == '(root)' else 1,
                                e['folder'].lower(), e['rel'].lower()))

    today = datetime.now().strftime('%Y-%m-%d')
    out = ['---', f'date-created: {today}', f'last-modified: {today}',
           'auto-generated: true', 'tags:', '  - index', '  - vault', '---', '',
           '# Vault Index', '',
           f'Auto-generated **meta-index** of all {len(entries)} non-ignored markdown files, '
           'root first then subfolders alphabetically. Each file links to its sections as '
           '`[[file#heading]]` wiki-links - a navigable deep-index and an Obsidian graph hub. '
           'Regenerate with `index_vault.py`.', '']

    from itertools import groupby
    for folder, grp in groupby(entries, key=lambda e: e['folder']):
        out.append(f'## {folder}')
        out.append('')
        for e in grp:
            date = ''
            if e['dc'] and e['lm']:
                date = f' (created {e["dc"]}, modified {e["lm"]})'
            elif e['dc']:
                date = f' (created {e["dc"]})'
            tagstr = (' ' + ' '.join(f'`#{t}`' for t in e['tags'])) if e['tags'] else ''
            badge = '' if e['has_fm'] else ' `[no frontmatter]`'
            out.append(f'- [[{e["basename"]}]]{date}{tagstr}{badge}')
            out.extend(render_heading_tree(e['basename'], e['heads']))
        out.append('')

    # Meta: tag index.
    tag_map = {}
    for e in entries:
        for t in e['tags']:
            tag_map.setdefault(t, []).append(e['basename'])
    if tag_map:
        out.append('## By Tag')
        out.append('')
        for tag in sorted(tag_map, key=str.lower):
            names = sorted(set(tag_map[tag]), key=str.lower)
            links = ', '.join(f'[[{n}]]' for n in names[:20])
            overflow = f' (+{len(names) - 20} more)' if len(names) > 20 else ''
            out.append(f'- `#{tag}`: {links}{overflow}')
        out.append('')

    # Meta: stats.
    fm_count = sum(1 for e in entries if e['has_fm'])
    tree_count = sum(1 for e in entries if e['heads'])
    out.append('## Stats')
    out.append('')
    out.append(f'- Total markdown files: {len(entries)}')
    out.append(f'- With frontmatter: {fm_count}')
    out.append(f'- With section trees: {tree_count}')
    out.append(f'- Unique tags: {len(tag_map)}')
    out.append('')

    (vault / output).write_text('\n'.join(out), encoding='utf-8')
    return len(entries)


def main():
    ap = argparse.ArgumentParser(description='Generate a vault meta-index (INDEX.md).')
    ap.add_argument('--vault', default=None, help='Vault root (default: auto-detect .obsidian, else CWD)')
    ap.add_argument('--output', default='INDEX.md', help='Index filename at vault root')
    ap.add_argument('--no-trees', action='store_true', help='Skip per-file header trees')
    ap.add_argument('--tree-exclude', default='', help='Comma-separated top folders to list without trees')
    ap.add_argument('--max-headings', type=int, default=60, help='Cap headings per file')
    args = ap.parse_args()

    # --output is a filename at the vault root, never a path. An absolute value
    # would replace the vault prefix entirely under pathlib's / operator.
    if Path(args.output).parent != Path('.'):
        print(f'ERROR: --output must be a bare filename, not a path: {args.output}',
              file=sys.stderr)
        sys.exit(1)

    vault = Path(args.vault).resolve() if args.vault else find_vault_root(Path.cwd())
    if not vault.is_dir():
        print(f'ERROR: not a directory: {vault}', file=sys.stderr)
        sys.exit(1)
    excl = {d.strip() for d in args.tree_exclude.split(',') if d.strip()}
    n = build_index(vault, args.output, not args.no_trees, excl, args.max_headings)
    print(f'Index written: {vault / args.output} ({n} files, gitignore-parity)')


if __name__ == '__main__':
    main()
