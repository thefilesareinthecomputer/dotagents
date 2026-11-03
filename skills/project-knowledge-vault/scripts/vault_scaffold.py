#!/usr/bin/env python3
"""Seed a project knowledge vault from the shipped template.

    vault_scaffold.py --target <path> --name <NAME> [--dry-run] [--no-graph]
    vault_scaffold.py --into <folder> [--dry-run] [--no-graph]

Copies every file in templates/knowledge-vault/, plus templates/templates/brd.md as 00-brd.md,
to <target>/PROJECTS/<NAME>/, the one home for a new vault, or with --into to <folder> itself (a vault that already lives elsewhere; a folder that
already has its own AGENTS.md or CLAUDE.md is refused, since the vault's copies are its contract). A file that
already exists is skipped and reported, so a run against a partly built vault fills the
gaps and touches nothing else. Placeholders stay as placeholders: no date is resolved,
so two runs on different days produce byte-identical notes.

Then seeds the vault's knowledge graph, because that is how a grown vault is read: runs
markdown-kg's `init` when the vault has no graph config (a vault with only a legacy
vault-kg/ is skipped with a rename instruction), merges the rows in
templates/markdown-kg-profiles.md that the config lacks (replacing the rows init detected
for files those rows cover), seeds markdown-kg/.gitignore so the database stays out of git,
and ingests when a note or a row was added. markdown-kg is found beside this skill; when it
is absent the step is reported and skipped. `--no-graph` skips it.

Last, prints the pointer line for the host repo's AGENTS.md and the agent's memory, so later
sessions find the vault without searching.

Standard library only, offline. Exit 0 when every file was written or deliberately
skipped, 1 when any file could be neither or the graph step failed, 2 on a usage error.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = SKILL_DIR / "templates" / "knowledge-vault"
# Document templates that are also vault notes: each keeps its one copy in templates/templates/
# and is seeded under its vault filename.
DOCUMENT_SEEDS = {"00-brd.md": SKILL_DIR / "templates" / "templates" / "brd.md"}
# The deliverables folder beside every vault: its own seed, a copy of the templates its documents
# start from, and the two folders those documents go in.
DELIVERABLES_DIR = SKILL_DIR / "templates" / "deliverables"
DELIVERABLE_DOCS = {f"templates/{n}": SKILL_DIR / "templates" / "templates" / n
                    for n in ("adr.md", "solution-design.md")}
DELIVERABLE_FOLDERS = ("adrs", "solution-designs")
PROFILES = SKILL_DIR / "templates" / "markdown-kg-profiles.md"
KG = SKILL_DIR.parent / "markdown-kg" / "scripts" / "markdown_kg.py"
JSON_BLOCK = re.compile(r"```json\n(.*?)```", re.S)
# A role whose file was renamed: a vault holding the older name already fills the role,
# so seeding the new name would give it two files for one role.
OLDER_NAMES = {"user-runsheet.md": ("user-stories-runsheet.md", "user-stories-tasks.md"),
               "notes-general-notes.md": ("notes-chat-notes-client.md", "notes-chat-notes-internal.md")}


def template_files() -> list[tuple[str, Path]]:
    """Every seed file as (vault filename, source), in a stable order."""
    files = {p.name: p for p in TEMPLATE_DIR.iterdir() if p.is_file() and not p.name.startswith(".")}
    files.update(DOCUMENT_SEEDS)
    return sorted(files.items())


def deliverable_files() -> list[tuple[str, Path]]:
    """Every deliverables seed file as (path in the folder, source), in a stable order."""
    files = {p.name: p for p in DELIVERABLES_DIR.iterdir() if p.is_file() and not p.name.startswith(".")}
    files.update(DELIVERABLE_DOCS)
    return sorted(files.items())


def deliverables_for(vault: Path) -> Path:
    """The vault's deliverables folder: its sibling, named for it."""
    vault = vault.resolve()  # once, so `.` or `..` in the path cannot put it inside the vault
    return vault.parent / f"{vault.name}-DELIVERABLES"


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


def seed(dest: Path, guards: tuple[Path, ...], dry_run: bool, files: list[tuple[str, Path]] | None = None,
         folders: tuple[str, ...] = ()) -> tuple[list[str], list[str], list[str]]:
    """Copy every seed file into dest and make its folders, never overwriting. Returns (written, skipped, failed).
    The files default to the vault seed."""
    written: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []
    # A symlink anywhere on the destination path could carry the seed outside the vault.
    for part in guards:
        if part.is_symlink():
            return written, skipped, [f"{part}: is a symlink; refusing to seed through it"]
    for folder in folders:
        path = dest / folder
        if path.is_symlink() or (path.exists() and not path.is_dir()):
            failed.append(f"{folder}/: exists and is not a plain folder; refusing to use it")
        elif path.is_dir():
            skipped.append(f"{folder}/")
        elif dry_run:
            written.append(f"{folder}/")
        else:
            try:
                path.mkdir(parents=True)
                written.append(f"{folder}/")
            except OSError as exc:
                failed.append(f"{folder}/: {exc}")
    for name, src in (template_files() if files is None else files):
        out = dest / name
        if out.is_symlink() or (out.parent != dest and out.parent.is_symlink()):
            failed.append(f"{name}: destination is a symlink; refusing to write through it")
            continue
        if out.exists():
            skipped.append(name)
            continue
        older = next((n for n in OLDER_NAMES.get(name, ()) if (dest / n).exists()), None)
        if older:
            skipped.append(f"{name} (the vault already has {older}, its older name)")
            continue
        if dry_run:
            written.append(name)
            continue
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            # O_EXCL and O_NOFOLLOW on the file and on its folder: create only, never through a link
            # planted between the check and the write
            nofollow = getattr(os, "O_NOFOLLOW", 0)
            parent = os.open(out.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | nofollow)
            try:
                fd = os.open(out.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow, 0o644, dir_fd=parent)
            finally:
                os.close(parent)
            with os.fdopen(fd, "wb") as fh:
                fh.write(src.read_bytes())
            written.append(name)
        except OSError as exc:
            failed.append(f"{name}: {exc}")
    return written, skipped, failed


def kg(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(KG), *args], capture_output=True, text=True)


def merge_profiles(config: Path, replace_detected: bool = False) -> int:
    """Add the shipped ignore and profile rows whose path the config lacks. Returns rows added.

    With replace_detected, which is set only when this run's `init` wrote the config, a profile row
    that a shipped row covers is dropped first. init writes exact-path rows for the dated notes it
    finds, and an exact path outranks the shipped `notes-*.md` glob, so its rows would hide the
    shipped slots. Rows in a config the operator already had are never dropped."""
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
    replaced = False
    for key, rows in json.loads(shipped.group(1)).items():
        existing = data.setdefault(key, [])
        if not isinstance(existing, list) or not all(isinstance(r, dict) for r in existing):
            raise ValueError(f"{config}: '{key}' is not a list of objects")
        if replace_detected and key == "profiles":
            covered = [r for r in existing
                       if any(fnmatch.fnmatchcase(str(r.get("path", "")), s["path"]) for s in rows)]
            existing[:] = [r for r in existing if r not in covered]
            replaced = replaced or bool(covered)
        have = {row.get("path") for row in existing}
        for row in rows:
            if row["path"] not in have:
                existing.append(row)
                added += 1
    if added or replaced:
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


def graph_preflight(vault: Path) -> tuple[bool, str] | None:
    """The cases where the graph step stops before touching anything: (ok, report line), or None to proceed.
    The real run and the dry run both ask this, so a dry run never promises what the run would refuse."""
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
    return None


def seed_graph(vault: Path, notes_written: int) -> tuple[bool, str]:
    """Initialize, configure and ingest the vault's graph. Returns (ok, report line)."""
    stop = graph_preflight(vault)
    if stop:
        return stop
    kg_dir = vault / "markdown-kg"
    config = kg_dir / "markdown-kg-config.md"
    initialized = False
    if not config.exists():
        r = kg("init", str(vault))
        if r.returncode != 0:
            return False, f"graph: init failed: {(r.stderr or r.stdout).strip()}"
        initialized = True
    try:
        ignored = ignore_databases(kg_dir)
        added = merge_profiles(config, replace_detected=initialized)
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


def dry_run_graph(vault: Path, notes_to_write: int) -> str:
    """What seed_graph would do, read from the vault without writing anything."""
    stop = graph_preflight(vault)
    if stop:
        return stop[1].replace("graph: ", "graph (dry run): ", 1)
    kg_dir = vault / "markdown-kg"
    if not (kg_dir / "markdown-kg-config.md").is_file():
        return "graph: would initialize markdown-kg/, merge the profile rows and ingest"
    ingest = "and ingest, since notes would be added" if notes_to_write else "and ingest only if a row is missing"
    return f"graph: markdown-kg/ present; would merge any missing profile rows {ingest}"


def pointer_steps(vault: Path, root: Path) -> str:
    """The lines that tell a host repo, and the next session's memory, where this vault lives.
    Paths are relative to the nearest git root above the vault, else to the root given."""
    vault = vault.resolve()
    host = next((p for p in (vault, *vault.parents) if (p / ".git").exists()), root.resolve())
    rel = vault.relative_to(host).as_posix() if vault.is_relative_to(host) else vault.name
    line = (f"Project knowledge vault: `{rel}/` - its `AGENTS.md` is the contract, "
            f"its graph is `{rel}/markdown-kg/`, and its deliverables are in `{rel}-DELIVERABLES/`.")
    return ("next: record where this vault lives, so later sessions find it without searching:\n"
            "  1. add this line to the host repo's root AGENTS.md (CLAUDE.md where it has no AGENTS.md), unless it is there:\n"
            f"     {line}\n"
            "  2. save the same line to your harness's persistent memory for this project, where it has one")


def report_seed(dest: Path, verb: str, written: list[str], skipped: list[str], failed: list[str]) -> None:
    print(f"{dest}: {verb} {len(written)}, skipped {len(skipped)}, failed {len(failed)}")
    for f in written:
        print(f"  {verb:<11} {f}")
    for f in skipped:
        print(f"  skipped     {f} (exists)")
    for f in failed:
        print(f"  FAILED      {f}")


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
    report_seed(dest, verb, written, skipped, failed)
    if failed:
        return 1
    deliverables = deliverables_for(dest)
    d_written, d_skipped, d_failed = seed(deliverables, (deliverables,), args.dry_run,
                                          deliverable_files(), DELIVERABLE_FOLDERS)
    report_seed(deliverables, verb, d_written, d_skipped, d_failed)
    if d_failed:
        return 1
    folders = ((dest, len(written)), (deliverables, len(d_written)))
    if args.dry_run:
        if not args.no_graph:
            for folder, count in folders:
                print(f"{folder.resolve().name}: {dry_run_graph(folder, count)}")
        return 0
    ok = True
    if not args.no_graph:
        for folder, count in folders:
            folder_ok, report = seed_graph(folder, count)
            print(f"{folder.resolve().name}: {report}")
            ok = ok and folder_ok
    if ok:
        print(pointer_steps(dest, args.target if args.target is not None else dest.parent))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
