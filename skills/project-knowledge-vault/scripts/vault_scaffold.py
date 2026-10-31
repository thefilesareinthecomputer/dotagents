#!/usr/bin/env python3
"""Seed a project knowledge vault from the shipped template.

    vault_scaffold.py --target <path> --name <NAME> [--dry-run] [--no-graph]
    vault_scaffold.py --into <folder> [--dry-run] [--no-graph]

Copies every file in templates/PROJECTS/ to <target>/PROJECTS/<NAME>/, or with --into
to <folder> itself (a vault inside a code repo, such as docs/; a folder that already has
its own AGENTS.md or CLAUDE.md is refused, since the vault's copies are its contract). A file that
already exists is skipped and reported, so a run against a partly built vault fills the
gaps and touches nothing else. Placeholders stay as placeholders: no date is resolved,
so two runs on different days produce byte-identical notes.

Then seeds the vault's knowledge graph, because that is how a grown vault is read: runs
markdown-kg's `init` when the vault has no graph config (a vault with only a legacy
vault-kg/ is skipped with a rename instruction), merges the rows in
templates/markdown-kg-profiles.md that the config lacks, seeds markdown-kg/.gitignore
so the database stays out of git, and ingests when a note or a row was added. markdown-kg is found beside this skill; when it is absent the step is
reported and skipped. `--no-graph` skips it.

Standard library only, offline. Exit 0 when every file was written or deliberately
skipped, 1 when any file could be neither or the graph step failed, 2 on a usage error.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = SKILL_DIR / "templates" / "PROJECTS"
PROFILES = SKILL_DIR / "templates" / "markdown-kg-profiles.md"
KG = SKILL_DIR.parent / "markdown-kg" / "scripts" / "markdown_kg.py"
JSON_BLOCK = re.compile(r"```json\n(.*?)```", re.S)
# A role whose file was renamed: a vault holding the older name already fills the role,
# so seeding the new name would give it two files for one role.
OLDER_NAMES = {"user-runsheet.md": ("user-stories-runsheet.md", "user-stories-tasks.md"),
               "notes-general-notes.md": ("notes-chat-notes-client.md", "notes-chat-notes-internal.md")}


def template_files() -> list[Path]:
    """Every seed file, in a stable order."""
    return sorted(p for p in TEMPLATE_DIR.iterdir() if p.is_file())


def scaffold(target: Path, name: str, dry_run: bool = False) -> tuple[list[str], list[str], list[str]]:
    """Copy the seed into target/PROJECTS/name. Returns (written, skipped, failed)."""
    return seed(target / "PROJECTS" / name, (target / "PROJECTS", target / "PROJECTS" / name), dry_run)


def is_contract(path: Path) -> bool:
    """Whether a rules file in the destination is the vault's own copy of the contract.

    CLAUDE.md is the one-line pointer and must match it whole, since a repo's own CLAUDE.md often
    opens with the same pointer; AGENTS.md is matched on its title, so an edited contract still counts."""
    template = TEMPLATE_DIR / path.name
    try:
        have = path.read_text(encoding="utf-8")
        want = template.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    if path.name == "CLAUDE.md":
        return have.strip() == want.strip()
    return bool(have.splitlines()) and have.splitlines()[0] == want.splitlines()[0]


def seed_into(dest: Path, dry_run: bool = False) -> tuple[list[str], list[str], list[str]]:
    """Copy the seed into dest itself, such as a code repo's docs/. Returns (written, skipped, failed).

    A folder that already holds its own AGENTS.md or CLAUDE.md belongs to something else: skipping
    those files would leave a vault without its contract, so the whole run is refused."""
    if dest.is_symlink():
        return [], [], [f"{dest}: is a symlink; refusing to seed through it"]
    for rules in ("AGENTS.md", "CLAUDE.md"):
        path = dest / rules
        if not (path.exists() or path.is_symlink()):
            continue
        if path.is_symlink() or not path.is_file() or not is_contract(path):
            return [], [], [f"{rules}: {dest} already has its own {rules}, not the vault contract; "
                             "seed into a folder of its own, such as docs/vault/"]
    return seed(dest, (dest,), dry_run)


def seed(dest: Path, guards: tuple[Path, ...], dry_run: bool) -> tuple[list[str], list[str], list[str]]:
    """Copy every template file into dest, never overwriting. Returns (written, skipped, failed)."""
    written: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []
    # A symlink anywhere on the destination path could carry the seed outside the vault.
    for part in guards:
        if part.is_symlink():
            return written, skipped, [f"{part}: is a symlink; refusing to seed through it"]
    for src in template_files():
        out = dest / src.name
        if out.is_symlink():
            failed.append(f"{src.name}: destination is a symlink; refusing to write through it")
            continue
        if out.exists():
            skipped.append(src.name)
            continue
        older = next((n for n in OLDER_NAMES.get(src.name, ()) if (dest / n).exists()), None)
        if older:
            skipped.append(f"{src.name} (the vault already has {older}, its older name)")
            continue
        if dry_run:
            written.append(src.name)
            continue
        try:
            dest.mkdir(parents=True, exist_ok=True)
            # O_EXCL and O_NOFOLLOW: create only, never through a link planted between the check and the write
            fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o644)
            with os.fdopen(fd, "wb") as fh:
                fh.write(src.read_bytes())
            written.append(src.name)
        except OSError as exc:
            failed.append(f"{src.name}: {exc}")
    return written, skipped, failed


def kg(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(KG), *args], capture_output=True, text=True)


def merge_profiles(config: Path) -> int:
    """Add the shipped ignore and profile rows whose path the config lacks. Returns rows added."""
    if config.is_symlink():
        raise OSError(f"{config} is a symlink; refusing to write through it")
    text = config.read_text(encoding="utf-8")
    block = JSON_BLOCK.search(text)
    shipped = JSON_BLOCK.search(PROFILES.read_text(encoding="utf-8"))
    if not block or not shipped:
        raise ValueError(f"no json block in {config if not block else PROFILES}")
    data = json.loads(block.group(1))
    if not isinstance(data, dict):
        raise ValueError(f"{config}: the json block is not an object")
    added = 0
    for key, rows in json.loads(shipped.group(1)).items():
        existing = data.setdefault(key, [])
        if not isinstance(existing, list) or not all(isinstance(r, dict) for r in existing):
            raise ValueError(f"{config}: '{key}' is not a list of objects")
        have = {row.get("path") for row in existing}
        for row in rows:
            if row["path"] not in have:
                existing.append(row)
                added += 1
    if added:
        body = json.dumps(data, indent=2) + "\n"
        replace_file(config, text[:block.start(1)] + body + text[block.end(1):])
    return added


def replace_file(path: Path, text: str) -> None:
    """Write beside the target and swap it in, so a crash mid-write never truncates the original."""
    tmp = path.with_name(f".{path.name}.tmp")
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o644)
    except FileExistsError:
        raise OSError(f"a previous run left {tmp}; delete it and re-run") from None
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def ignore_databases(kg_dir: Path) -> bool:
    """Seed markdown-kg/.gitignore so the graph database, which holds every note's full text, stays out of git.
    Returns whether the file ignores the database; an existing file is never rewritten."""
    gitignore = kg_dir / ".gitignore"
    try:
        fd = os.open(gitignore, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o644)
    except FileExistsError:
        return "*.db*" in gitignore.read_text(encoding="utf-8").split()
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write("*.db*\n")
    return True


def seed_graph(vault: Path, notes_written: int) -> tuple[bool, str]:
    """Initialize, configure and ingest the vault's graph. Returns (ok, report line)."""
    if not KG.is_file():
        return True, "graph: skipped, markdown-kg is not installed beside this skill; run its init and merge templates/markdown-kg-profiles.md by hand"
    kg_dir = vault / "markdown-kg"
    legacy = vault / "vault-kg"
    if kg_dir.exists() and not kg_dir.is_dir():
        return False, f"graph: {kg_dir} exists and is not a directory; refusing to initialize"
    # markdown-kg uses a legacy vault-kg/ in place when markdown-kg/ is not a directory, so init would write there
    if not kg_dir.is_dir() and not kg_dir.is_symlink() and (legacy.is_dir() or legacy.is_symlink()):
        return True, "graph: skipped, this vault has a legacy vault-kg/ graph; rename it to markdown-kg/ and re-run to manage it here"
    if kg_dir.is_symlink() or (kg_dir.is_dir() and any(p.is_symlink() for p in kg_dir.iterdir())):
        return False, f"graph: {kg_dir} is or contains a symlink; refusing to write through it"
    config = kg_dir / "markdown-kg-config.md"
    initialized = False
    if not config.exists():
        r = kg("init", str(vault))
        if r.returncode != 0:
            return False, f"graph: init failed: {(r.stderr or r.stdout).strip()}"
        initialized = True
    try:
        ignored = ignore_databases(kg_dir)
        added = merge_profiles(config)
    except (OSError, ValueError) as exc:
        return False, f"graph: could not configure markdown-kg/: {exc}"
    git_note = "the database is gitignored" if ignored else "WARNING: markdown-kg/.gitignore exists without a *.db* line; add it, the database holds every note's full text"
    if not (initialized or added or notes_written):
        return True, f"graph: config already has every profile row, nothing to ingest; {git_note}"
    r = kg("ingest", str(vault))
    if r.returncode != 0:
        return False, f"graph: ingest failed: {(r.stderr or r.stdout).strip()}"
    verb = "initialized" if initialized else "updated"
    return True, f"graph: {verb} markdown-kg/, {added} profile row(s) merged, ingested; {git_note}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--target", type=Path, help="folder that holds (or will hold) PROJECTS/; needs --name")
    parser.add_argument("--name", help="the project vault's folder name under PROJECTS/")
    parser.add_argument("--into", type=Path, help="seed the vault into this folder itself, such as a repo's docs/")
    parser.add_argument("--dry-run", action="store_true", help="print the file list and write nothing")
    parser.add_argument("--no-graph", action="store_true", help="seed the notes only, without the markdown-kg graph")
    args = parser.parse_args(argv)

    if args.into is not None:
        if args.target is not None or args.name is not None:
            parser.error("--into replaces --target and --name; give one form")
    elif args.target is None or args.name is None:
        parser.error("give --target with --name, or --into")
    else:
        bad = {os.sep, os.altsep or os.sep}
        if any(c in args.name for c in bad) or args.name in ("", ".", "..") or args.name.startswith(".") or not args.name.isprintable():
            parser.error("--name is a single, visible folder name")
    if not TEMPLATE_DIR.is_dir():
        parser.error(f"template folder missing: {TEMPLATE_DIR}")

    if args.into is not None:
        dest = args.into
        written, skipped, failed = seed_into(dest, args.dry_run)
    else:
        dest = args.target / "PROJECTS" / args.name
        written, skipped, failed = scaffold(args.target, args.name, args.dry_run)
    verb = "would write" if args.dry_run else "wrote"
    print(f"{dest}: {verb} {len(written)}, skipped {len(skipped)}, failed {len(failed)}")
    for f in written:
        print(f"  {verb:<11} {f}")
    for f in skipped:
        print(f"  skipped     {f} (exists)")
    for f in failed:
        print(f"  FAILED      {f}")
    if failed:
        return 1
    if args.no_graph:
        return 0
    if args.dry_run:
        print("graph: would initialize markdown-kg/ and merge the profile rows")
        return 0
    ok, report = seed_graph(dest, len(written))
    print(report)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
