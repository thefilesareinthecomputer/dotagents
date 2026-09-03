#!/usr/bin/env python3
"""Seed a project knowledge vault from the shipped template.

    vault_scaffold.py --target <path> --name <NAME> [--dry-run]

Copies every file in templates/PROJECTS/ to <target>/PROJECTS/<NAME>/. A file that
already exists is skipped and reported, so a run against a partly built vault fills the
gaps and touches nothing else. Placeholders stay as placeholders: no date is resolved,
so two runs on different days produce byte-identical trees.

Standard library only, offline. Exit 0 when every file was written or deliberately
skipped, 1 when any file could be neither, 2 on a usage error.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "PROJECTS"


def template_files() -> list[Path]:
    """Every seed file, in a stable order."""
    return sorted(p for p in TEMPLATE_DIR.iterdir() if p.is_file())


def scaffold(target: Path, name: str, dry_run: bool = False) -> tuple[list[str], list[str], list[str]]:
    """Copy the seed into target/PROJECTS/name. Returns (written, skipped, failed)."""
    dest = target / "PROJECTS" / name
    written: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []
    # A symlink anywhere on the destination path could carry the seed outside the vault.
    for part in (target / "PROJECTS", dest):
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--target", required=True, type=Path, help="folder that holds (or will hold) PROJECTS/")
    parser.add_argument("--name", required=True, help="the project vault's folder name under PROJECTS/")
    parser.add_argument("--dry-run", action="store_true", help="print the file list and write nothing")
    args = parser.parse_args(argv)

    bad = {os.sep, os.altsep or os.sep}
    if any(c in args.name for c in bad) or args.name in ("", ".", "..") or args.name.startswith(".") or not args.name.isprintable():
        parser.error("--name is a single, visible folder name")
    if not TEMPLATE_DIR.is_dir():
        parser.error(f"template folder missing: {TEMPLATE_DIR}")

    written, skipped, failed = scaffold(args.target, args.name, args.dry_run)
    verb = "would write" if args.dry_run else "wrote"
    dest = args.target / "PROJECTS" / args.name
    print(f"{dest}: {verb} {len(written)}, skipped {len(skipped)}, failed {len(failed)}")
    for f in written:
        print(f"  {verb:<11} {f}")
    for f in skipped:
        print(f"  skipped     {f} (exists)")
    for f in failed:
        print(f"  FAILED      {f}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
