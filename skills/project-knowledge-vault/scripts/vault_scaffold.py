#!/usr/bin/env python3
"""Seed a project knowledge vault from the shipped template.

    vault_scaffold.py --target <path> --name <NAME> [--dry-run] [--no-graph]
    vault_scaffold.py --into <folder> [--dry-run] [--no-graph]

Copies every file in templates/knowledge-vault/, plus templates/templates/brd.md as 00-brd.md,
to <target>/PROJECTS/<NAME>/ beside a <NAME>-DELIVERABLES/ folder, or with --into to <folder> itself,
such as a repo's kb/ (a folder whose own AGENTS.md or CLAUDE.md is not the vault contract is refused,
and so is a folder that is not a vault yet and holds subfolders, since a vault is flat). A file that
already exists is skipped and reported, so a run against a partly built vault fills the
gaps and touches nothing else. Placeholders stay as placeholders: no date is resolved,
so two runs on different days produce byte-identical notes.

--into is repo mode. It makes no deliverables folder: ADRs and designs go to the repo's docs/.
On every run it finds the repo root above the folder and derives the roles the repo owns: a
docs/SPEC.md or root SPEC.md skips 00-brd.md and 01-north-star.md, and the seed files that would
link them come from templates/knowledge-vault-repo/ instead.

Then seeds the vault's knowledge graph in .kg/, because that is how a grown vault is read:
runs markdown-kg's `init` when the vault has no graph config (a vault whose graph is still
in a legacy markdown-kg/ or vault-kg/ folder is skipped with a `migrate` instruction),
merges the rows in templates/markdown-kg-profiles.md that the config lacks (replacing the
rows init detected for files those rows cover), checks .kg/.gitignore keeps the database
out of git, and ingests when a note or a row was added. markdown-kg is found beside this skill; when it
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
import shlex
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = SKILL_DIR / "templates" / "knowledge-vault"
# Repo mode: the roles a repo's SPEC.md owns, the files that show it does, and the seed files
# whose base text links those roles.
REPO_TEMPLATE_DIR = SKILL_DIR / "templates" / "knowledge-vault-repo"
REPO_OWNED_ROLES = ("00-brd.md", "01-north-star.md")
REPO_SPECS = ("docs/SPEC.md", "SPEC.md")
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
# markdown-kg's files in a vault: its folder, shared with code-kg, and the earlier folders
# it keeps using in place until `migrate` moves them.
KG_DIR = ".kg"
KG_CONFIG = "markdown-kg-config.json"
LEGACY_KG_DIRS = ("markdown-kg", "vault-kg")
# A role whose file was renamed: a vault holding the older name already fills the role,
# so seeding the new name would give it two files for one role.
OLDER_NAMES = {"user-runsheet.md": ("user-stories-runsheet.md", "user-stories-tasks.md"),
               "notes-general-notes.md": ("notes-chat-notes-client.md", "notes-chat-notes-internal.md")}


def template_files(skip: tuple[str, ...] = ()) -> list[tuple[str, Path]]:
    """Every seed file as (vault filename, source), in a stable order. Roles in `skip` are left out,
    and then the repo-mode variants replace the files that would link them."""
    files = {p.name: p for p in TEMPLATE_DIR.iterdir() if p.is_file() and not p.name.startswith(".")}
    files.update(DOCUMENT_SEEDS)
    if skip:
        for name in skip:
            files.pop(name, None)
        files.update({p.name: p for p in REPO_TEMPLATE_DIR.iterdir()
                      if p.is_file() and not p.name.startswith(".")})
    return sorted(files.items())


def host_repo(folder: Path) -> Path | None:
    """The nearest folder at or above `folder` that holds `.git`."""
    folder = folder.resolve()
    return next((p for p in (folder, *folder.parents) if (p / ".git").exists()), None)


def repo_roles(folder: Path) -> tuple[str, ...]:
    """The vault roles a repo owns, derived on every run: a SPEC.md in docs/ or at the root of the
    repo above `folder` (else of its parent folder) owns the BRD and the north star."""
    root = host_repo(folder) or folder.resolve().parent
    return REPO_OWNED_ROLES if any((root / s).is_file() for s in REPO_SPECS) else ()


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


def seed_into(dest: Path, dry_run: bool = False,
              skip: tuple[str, ...] = ()) -> tuple[list[str], list[str], list[str]]:
    """Copy the seed into dest itself, such as a code repo's kb/, leaving out the roles in `skip`.
    Returns (written, skipped, failed).

    A folder whose AGENTS.md or CLAUDE.md is not the vault's own copy of the contract belongs to
    something else: skipping those files would leave a vault without its contract, so the whole run
    is refused. The vault's own copy is admitted, which is how a rerun fills a vault's gaps."""
    if dest.is_symlink():
        return [], [], [f"{dest}: is a symlink; refusing to seed through it"]
    for rules in ("AGENTS.md", "CLAUDE.md"):
        path = dest / rules
        if not (path.exists() or path.is_symlink()):
            continue
        if path.is_symlink() or not path.is_file() or not is_contract(path):
            return [], [], [f"{rules}: {dest} already has its own {rules}, not the vault contract; "
                             "seed into a folder of its own, such as kb/"]
    # A vault is one flat folder. A folder that is not a vault yet and already holds subfolders,
    # such as a code repo's docs/, would fail the linter's flat check from the first run. A folder
    # is already a vault when it holds the contract, or, from before the contract, index.md, log.md
    # and 00-brd.md together; a stray index.md alone does not make one.
    def plain(name: str) -> bool:
        return (dest / name).is_file() and not (dest / name).is_symlink()
    marked = (plain("AGENTS.md") and is_contract(dest / "AGENTS.md")) or all(
        plain(n) for n in ("index.md", "log.md", "00-brd.md"))
    if dest.is_dir() and not marked:
        try:
            sub = next((p.name for p in sorted(dest.iterdir()) if p.is_dir() and not p.name.startswith(".")
                        and p.name not in LEGACY_KG_DIRS), None)
        except OSError as exc:
            return [], [], [f"{dest}: cannot be listed: {exc}"]
        if sub:
            return [], [], [f"{dest} already holds {sub}/ and is not a vault; a vault is one flat folder, "
                            f"so seed into a folder of its own, such as {dest / 'kb'}/"]
    return seed(dest, (dest,), dry_run, template_files(skip))


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
            if os.open in os.supports_dir_fd:
                parent = os.open(out.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | nofollow)
                try:
                    fd = os.open(out.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow, 0o644, dir_fd=parent)
                finally:
                    os.close(parent)
            else:
                # Windows: no dir_fd and no folder handle, so refuse a linked folder by checking it
                if out.parent.is_symlink():
                    raise OSError(f"refusing to write through a linked folder: {out.parent}")
                fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            with os.fdopen(fd, "wb") as fh:
                fh.write(src.read_bytes())
            written.append(name)
        except OSError as exc:
            failed.append(f"{name}: {exc}")
    return written, skipped, failed


def kg(*args: str) -> subprocess.CompletedProcess:
    # An ingest of a large vault takes minutes; the cap only stops a hung one.
    return subprocess.run([sys.executable, str(KG), *args], capture_output=True, text=True, timeout=900)


def add_ignore_rows(folder: Path, rows: list[dict]) -> int:
    """Append the shipped ignore rows the folder's .kgignore lacks, each under its reason as a
    comment. Returns patterns added."""
    path = folder / ".kgignore"
    if path.is_symlink():
        raise OSError(f"{path} is a symlink; refusing to write through it")
    have = {ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()} \
        if path.is_file() else set()
    new = [r for r in rows if r["path"] not in have]
    if new:
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        lead = "\n" if text and not text.endswith("\n") else ""
        lines = [ln for r in new for ln in (f"# {r['reason']}", r["path"])]
        replace_file(path, text + lead + "\n".join(lines) + "\n")
    return len(new)


def merge_profiles(config: Path, replace_detected: bool = False, skip: tuple[str, ...] = ()) -> int:
    """Add the shipped profile rows whose path the config lacks, and the shipped ignore rows to the
    folder's .kgignore. Returns rows added.

    With replace_detected, which is set only when this run's `init` wrote the config, a profile row
    that a shipped row covers is dropped first. init writes exact-path rows for the dated notes it
    finds, and an exact path outranks the shipped `notes-*.md` glob, so its rows would hide the
    shipped slots. Rows in a config the operator already had are never dropped."""
    if config.is_symlink():
        raise OSError(f"{config} is a symlink; refusing to write through it")
    text = config.read_text(encoding="utf-8")
    shipped = JSON_BLOCK.search(PROFILES.read_text(encoding="utf-8"))
    if not shipped:
        raise ValueError(f"no json block in {PROFILES}")
    data = json.loads(text) if text.strip() else {}
    if not isinstance(data, dict):
        raise ValueError(f"{config}: the config is not a json object")
    shipped_rows = json.loads(shipped.group(1))
    # A role the repo owns is not seeded, so a row that only exists for it would match nothing.
    shipped_rows["profiles"] = [r for r in shipped_rows["profiles"]
                                if not any(fnmatch.fnmatchcase(n, r["path"]) for n in skip)]
    ignore_added = add_ignore_rows(config.parent.parent, shipped_rows.pop("ignore"))
    added = 0
    replaced = False
    for key, rows in shipped_rows.items():
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
        replace_file(config, json.dumps(data, indent=2) + "\n")
    return added + ignore_added


def replace_file(path: Path, text: str) -> None:
    """Write beside the target and swap it in, so a crash mid-write never truncates the original."""
    tmp = path.with_name(f".{path.name}.tmp")
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o644)
    except FileExistsError:
        raise OSError(f"a previous run left {tmp}; delete it and re-run") from None
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def ignore_databases(kg_dir: Path) -> bool:
    """Check .kg/.gitignore keeps the graph database, which holds every note's full text, out of git, seeding
    `*.db*` when the file is missing so the config stays committable. Returns whether it does (`*` or `*.db*`);
    an existing file is never rewritten."""
    gitignore = kg_dir / ".gitignore"
    try:
        fd = os.open(gitignore, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o644)
    except FileExistsError:
        lines = gitignore.read_text(encoding="utf-8").split()
        return "*" in lines or "*.db*" in lines
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("*.db*\n")
    return True


def graph_preflight(vault: Path) -> tuple[bool, str] | None:
    """The cases where the graph step stops before touching anything: (ok, report line), or None to proceed.
    The real run and the dry run both ask this, so a dry run never promises what the run would refuse."""
    if not KG.is_file():
        return True, "graph: skipped, markdown-kg is not installed beside this skill; run its init and merge templates/markdown-kg-profiles.md by hand"
    kg_dir = vault / KG_DIR
    if kg_dir.exists() and not kg_dir.is_dir():
        return False, f"graph: {kg_dir} exists and is not a directory; refusing to initialize"
    # markdown-kg keeps using a legacy folder in place until its files are in .kg/, so init would write there
    current = any(os.path.lexists(kg_dir / n) for n in (KG_CONFIG, "markdown-kg.db"))
    legacy = next((d for d in LEGACY_KG_DIRS if (vault / d).is_dir() or (vault / d).is_symlink()), None)
    if not current and legacy:
        return True, (f"graph: skipped, this vault's graph is in the legacy {legacy}/ folder; run markdown-kg's"
                      " `migrate` on the vault and re-run to manage it here")
    if kg_dir.is_symlink() or (kg_dir.is_dir() and any(p.is_symlink() for p in kg_dir.iterdir())):
        return False, f"graph: {kg_dir} is or contains a symlink; refusing to write through it"
    return None


def seed_graph(vault: Path, notes_written: int, skip: tuple[str, ...] = ()) -> tuple[bool, str]:
    """Initialize, configure and ingest the vault's graph. Returns (ok, report line)."""
    stop = graph_preflight(vault)
    if stop:
        return stop
    kg_dir = vault / KG_DIR
    config = kg_dir / KG_CONFIG
    initialized = False
    if not config.exists():
        r = kg("init", str(vault))
        if r.returncode != 0:
            return False, f"graph: init failed: {(r.stderr or r.stdout).strip()}"
        initialized = True
    try:
        ignored = ignore_databases(kg_dir)
        added = merge_profiles(config, replace_detected=initialized, skip=skip)
    except (OSError, ValueError) as exc:
        return False, f"graph: could not configure {KG_DIR}/: {exc}"
    git_note = "the database is gitignored" if ignored else f"WARNING: {KG_DIR}/.gitignore exists without a * or *.db* line; add one, the database holds every note's full text"
    if not (initialized or added or notes_written):
        return True, f"graph: config already has every profile row, nothing to ingest; {git_note}"
    r = kg("ingest", str(vault))
    if r.returncode != 0:
        return False, f"graph: ingest failed: {(r.stderr or r.stdout).strip()}"
    verb = "initialized" if initialized else "updated"
    return True, f"graph: {verb} {KG_DIR}/, {added} profile row(s) merged, ingested; {git_note}"


def dry_run_graph(vault: Path, notes_to_write: int) -> str:
    """What seed_graph would do, read from the vault without writing anything."""
    stop = graph_preflight(vault)
    if stop:
        return stop[1].replace("graph: ", "graph (dry run): ", 1)
    if not (vault / KG_DIR / KG_CONFIG).is_file():
        return f"graph: would initialize {KG_DIR}/, merge the profile rows and ingest"
    ingest = "and ingest, since notes would be added" if notes_to_write else "and ingest only if a row is missing"
    return f"graph: {KG_DIR}/ present; would merge any missing profile rows {ingest}"


def pointer_steps(vault: Path, root: Path, repo_mode: bool = False) -> str:
    """The lines that tell a host repo, and the next session's memory, where this vault lives.
    Paths are relative to the nearest git root above the vault, else to the root given. In repo
    mode, also the command that indexes the repo's docs/ when it has no graph yet."""
    vault = vault.resolve()
    host = host_repo(vault) or root.resolve()
    rel = vault.relative_to(host).as_posix() if vault.is_relative_to(host) else vault.name
    if repo_mode:
        line = (f"This repo's project vault is `{rel}/` (graph `{rel}/{KG_DIR}/`); "
                "graduated docs are in `docs/`.")
    else:
        line = (f"Project knowledge vault: `{rel}/` - its `AGENTS.md` is the contract, "
                f"its graph is `{rel}/{KG_DIR}/`, and its deliverables are in `{rel}-DELIVERABLES/`.")
    steps = ("next: record where this vault lives, so later sessions find it without searching:\n"
             "  1. add this line to the host repo's root AGENTS.md (CLAUDE.md where it has no AGENTS.md), unless it is there:\n"
             f"     {line}\n"
             "  2. save the same line to your harness's persistent memory for this project, where it has one")
    docs = host / "docs"
    if repo_mode and docs.is_dir() and not (docs / KG_DIR / KG_CONFIG).is_file():
        steps += ("\n  3. give the repo's docs/ its own graph, so it can be searched beside the vault:\n"
                  f"     python3 {shlex.quote(str(KG))} init {shlex.quote(str(docs))} && "
                  f"python3 {shlex.quote(str(KG))} ingest {shlex.quote(str(docs))}\n"
                  "     If the repo tracks folders it never publishes, list them under \"holdback\" in\n"
                  "     docs/.kg/markdown-kg-config.json, such as [\"/tasks/\"] (the lanes reference in this skill)")
    return steps


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
    parser.add_argument("--into", type=Path, help="repo mode: seed the vault into this folder itself, such as a repo's kb/")
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

    repo_mode = args.into is not None
    skip: tuple[str, ...] = ()
    if repo_mode:
        dest = args.into
        skip = repo_roles(dest)
        written, skipped, failed = seed_into(dest, args.dry_run, skip)
    else:
        dest = args.target / "PROJECTS" / args.name
        written, skipped, failed = scaffold(args.target, args.name, args.dry_run)
    verb = "would write" if args.dry_run else "wrote"
    report_seed(dest, verb, written, skipped, failed)
    if skip:
        print(f"  repo mode: the repo's SPEC.md owns {', '.join(skip)}, so they are not seeded")
    if failed:
        return 1
    folders = [(dest, len(written), skip)]
    if not repo_mode:
        # A workspace vault ships its documents from a sibling folder; a vault in a repo uses docs/.
        deliverables = deliverables_for(dest)
        d_written, d_skipped, d_failed = seed(deliverables, (deliverables,), args.dry_run,
                                              deliverable_files(), DELIVERABLE_FOLDERS)
        report_seed(deliverables, verb, d_written, d_skipped, d_failed)
        if d_failed:
            return 1
        folders.append((deliverables, len(d_written), ()))
    if args.dry_run:
        if not args.no_graph:
            for folder, count, _ in folders:
                print(f"{folder.resolve().name}: {dry_run_graph(folder, count)}")
        return 0
    ok = True
    if not args.no_graph:
        for folder, count, roles in folders:
            folder_ok, report = seed_graph(folder, count, roles)
            print(f"{folder.resolve().name}: {report}")
            ok = ok and folder_ok
    if ok:
        print(pointer_steps(dest, args.target if args.target is not None else dest.parent, repo_mode))
    return 0 if ok else 1


if __name__ == "__main__":
    if sys.platform == "win32":  # the console code page is not UTF-8; note text often is
        for _stream in (sys.stdout, sys.stderr):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
