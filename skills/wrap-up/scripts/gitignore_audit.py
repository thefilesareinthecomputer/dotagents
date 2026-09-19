#!/usr/bin/env python3
"""Find files in the tree that look ignore-worthy but are not covered by .gitignore.

Run before the closeout commit. It walks every tracked and untracked path,
matches each against a fixed list of things that are almost never meant to be
committed - env files, caches, build output, OS and editor litter, logs, local
databases - and asks git whether an ignore rule already covers it. Whatever is
not covered comes back grouped by the pattern that would cover it, with paths
new this session marked, so the user can be asked per pattern.

    python3 gitignore_audit.py audit            # exit 1 when anything is uncovered
    python3 gitignore_audit.py audit --json
    python3 gitignore_audit.py add '__pycache__/' '*.log'   # append to the root .gitignore

Two classes are reported:

  uncovered   matches a pattern below and no ignore rule covers it. Untracked
              ones will be swept into the next `git add -A`; tracked ones are
              already in history and keep changing with every commit.
  tracked but ignored   an ignore rule exists and the file is in the index anyway,
              so the rule does nothing for it until `git rm --cached`.

A path under a `!` negation rule in any .gitignore is a deliberate keep (a test
fixture that ships a node_modules/, say) and is never reported, so the same
question is not asked at every closeout.

The script never edits the index. `add` only appends lines to the root
.gitignore; untracking a file is a visible change the user approves first.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
import sys
from pathlib import Path

# (pattern, reason). A trailing slash means "any directory component of that
# name"; anything else is matched against the basename with fnmatch.
RULES: tuple[tuple[str, str], ...] = (
    (".env", "environment file, usually holds secrets"),
    (".env.*", "environment file, usually holds secrets"),
    ("*.pem", "private key or certificate"),
    ("*.key", "private key"),
    ("*.p12", "keystore"),
    ("*.pfx", "keystore"),
    ("*.jks", "keystore"),
    ("id_rsa*", "ssh private key"),
    ("id_ed25519*", "ssh private key"),
    (".netrc", "stored credentials"),
    ("secrets.json", "secret store"),
    ("secrets.yaml", "secret store"),
    ("secrets.yml", "secret store"),
    ("*.tfstate", "terraform state, holds secrets"),
    ("*.tfstate.backup", "terraform state, holds secrets"),
    (".terraform/", "terraform provider cache"),
    (".DS_Store", "macOS folder metadata"),
    ("._*", "macOS resource fork"),
    ("Thumbs.db", "Windows thumbnail cache"),
    ("desktop.ini", "Windows folder metadata"),
    ("*.swp", "editor swap file"),
    ("*.swo", "editor swap file"),
    ("*~", "editor backup"),
    (".idea/", "IDE project state"),
    ("*.iml", "IDE project state"),
    ("__pycache__/", "python bytecode cache"),
    ("*.pyc", "python bytecode"),
    ("*.pyo", "python bytecode"),
    (".venv/", "python virtualenv"),
    ("venv/", "python virtualenv"),
    ("*.egg-info/", "python package build metadata"),
    (".pytest_cache/", "test cache"),
    (".mypy_cache/", "type-check cache"),
    (".ruff_cache/", "lint cache"),
    (".tox/", "tox environments"),
    (".hypothesis/", "hypothesis example database"),
    (".ipynb_checkpoints/", "notebook checkpoints"),
    (".coverage", "coverage data"),
    ("htmlcov/", "coverage report"),
    ("node_modules/", "installed node packages"),
    (".next/", "next.js build output"),
    (".nuxt/", "nuxt build output"),
    (".turbo/", "turborepo cache"),
    (".parcel-cache/", "parcel cache"),
    ("npm-debug.log*", "package manager log"),
    ("yarn-error.log", "package manager log"),
    ("dist/", "build output"),
    ("build/", "build output"),
    ("target/", "build output"),
    ("*.o", "compiled object"),
    ("*.so", "compiled library"),
    ("*.dylib", "compiled library"),
    ("*.class", "compiled java class"),
    ("*.log", "log output"),
    ("logs/", "log output"),
    ("*.tmp", "temporary file"),
    ("*.bak", "backup copy"),
    ("*.orig", "merge leftover"),
    ("*.rej", "merge leftover"),
    ("tmp/", "temporary files"),
    (".cache/", "tool cache"),
    ("*.sqlite", "local database"),
    ("*.sqlite3", "local database"),
    ("*.db", "local database"),
    (".code-kg/", "code-kg index database"),
    ("settings.local.json", "per-machine Claude Code settings"),
    ("docker-compose.override.yml", "local compose override"),
)

# Basenames that match a rule above but are meant to be committed.
EXEMPT_BASENAMES = frozenset({
    ".env.example", ".env.sample", ".env.template", ".env.dist",
})


def git(*args: str, cwd: Path | None = None, ok: tuple[int, ...] = (0,)) -> str:
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if proc.returncode not in ok:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def repo_root() -> Path:
    return Path(git("rev-parse", "--show-toplevel").strip())


def split_z(out: str) -> list[str]:
    return [p for p in out.split("\0") if p]


def tracked_paths() -> list[str]:
    return split_z(git("ls-files", "-z"))


def untracked_paths() -> list[str]:
    return split_z(git("ls-files", "-z", "--others", "--exclude-standard"))


def new_this_session(tracked: list[str], untracked: list[str]) -> set[str]:
    """Paths added since the last push: untracked, staged-added, or committed-added."""
    new = set(untracked)
    new.update(split_z(git("diff", "-z", "--cached", "--name-only", "--diff-filter=A")))
    try:
        upstream = git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}").strip()
    except RuntimeError:
        upstream = ""
    if upstream:
        new.update(split_z(git("diff", "-z", "--name-only", "--diff-filter=A", f"{upstream}..HEAD")))
    return new & (set(tracked) | set(untracked))


def match_rule(path: str) -> tuple[str, str] | None:
    parts = path.split("/")
    base = parts[-1]
    if base in EXEMPT_BASENAMES:
        return None
    for pattern, reason in RULES:
        if pattern.endswith("/"):
            name = pattern[:-1]
            if any(fnmatch.fnmatchcase(part, name) for part in parts[:-1]):
                return pattern, reason
        elif fnmatch.fnmatchcase(base, pattern):
            return pattern, reason
    return None


def deliberate_keeps(root: Path) -> list[tuple[str, str]]:
    """Negation rules (`!pattern`) from every .gitignore in the tree.

    A `!` rule is the one idiom git has for "this path is tracked on purpose",
    so a candidate under one is never reported, whether or not the negation
    changes what git ignores. Returned as (gitignore_dir, pattern) pairs with
    the leading `!`, any leading `/` and trailing `/` stripped.
    """
    keeps: list[tuple[str, str]] = []
    for name in split_z(git("ls-files", "-z", "--cached", "--others", "--exclude-standard")):
        if Path(name).name != ".gitignore":
            continue
        base = str(Path(name).parent).replace("\\", "/")
        base = "" if base == "." else base
        try:
            lines = (root / name).read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line.startswith("!"):
                continue
            pattern = line[1:].strip().strip("/")
            if pattern:
                keeps.append((base, pattern))
    return keeps


def is_kept(path: str, keeps: list[tuple[str, str]]) -> bool:
    parts = path.split("/")
    for base, pattern in keeps:
        if "/" in pattern:
            anchored = f"{base}/{pattern}" if base else pattern
            if path == anchored or path.startswith(anchored + "/"):
                return True
        else:
            scope = parts if not base else (
                parts[len(base.split("/")):] if path.startswith(base + "/") else [])
            if any(fnmatch.fnmatchcase(part, pattern) for part in scope):
                return True
    return False


def ignored_subset(paths: list[str]) -> set[str]:
    """Which of `paths` an ignore rule covers, tracked or not."""
    if not paths:
        return set()
    proc = subprocess.run(
        ["git", "check-ignore", "--no-index", "-z", "--stdin"],
        input="\0".join(paths) + "\0", capture_output=True, text=True,
    )
    if proc.returncode not in (0, 1):  # 1 means "none ignored"
        raise RuntimeError(f"git check-ignore failed: {proc.stderr.strip()}")
    return set(split_z(proc.stdout))


def audit(root: Path) -> dict:
    tracked = tracked_paths()
    untracked = untracked_paths()
    tracked_set = set(tracked)
    new = new_this_session(tracked, untracked)
    keeps = deliberate_keeps(root)

    candidates: dict[str, tuple[str, str]] = {}
    for path in tracked + untracked:
        hit = match_rule(path)
        if hit and not is_kept(path, keeps):
            candidates[path] = hit

    # Untracked paths already passed --exclude-standard; a `!` keep is not a finding.
    ignored = {p for p in ignored_subset(tracked) if not is_kept(p, keeps)}
    uncovered: dict[str, dict] = {}
    for path, (pattern, reason) in sorted(candidates.items()):
        if path in ignored:
            continue
        group = uncovered.setdefault(pattern, {"reason": reason, "paths": []})
        group["paths"].append({
            "path": path,
            "new": path in new,
            "tracked": path in tracked_set,
        })

    tracked_but_ignored = sorted(ignored)
    return {"uncovered": uncovered, "tracked_but_ignored": tracked_but_ignored}


def render(result: dict) -> str:
    uncovered = result["uncovered"]
    lines: list[str] = []
    if uncovered:
        lines.append(f"gitignore audit: {len(uncovered)} pattern(s) not covered by .gitignore")
        for pattern, group in uncovered.items():
            lines.append(f"  {pattern:24} {group['reason']}")
            for item in group["paths"]:
                tags = [t for t, on in (("new", item["new"]), ("tracked", item["tracked"])) if on]
                tag = f"[{', '.join(tags)}] " if tags else ""
                lines.append(f"    {tag}{item['path']}")
    else:
        lines.append("gitignore audit: nothing uncovered")
    if result["tracked_but_ignored"]:
        lines.append("tracked but ignored (rule exists, file is still in the index):")
        for path in result["tracked_but_ignored"]:
            lines.append(f"    {path}")
    return "\n".join(lines)


def add_patterns(root: Path, patterns: list[str]) -> list[str]:
    """Append patterns to the root .gitignore, skipping lines already present."""
    target = root / ".gitignore"
    existing = target.read_text(encoding="utf-8") if target.is_file() else ""
    present = {line.strip() for line in existing.splitlines()}
    added = [p for p in patterns if p.strip() and p.strip() not in present]
    if not added:
        return []
    text = existing
    if text and not text.endswith("\n"):
        text += "\n"
    text += "".join(f"{p}\n" for p in added)
    target.write_text(text, encoding="utf-8")
    return added


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("audit", help="report ignore-worthy paths no rule covers")
    run.add_argument("--json", action="store_true")
    add = sub.add_parser("add", help="append patterns to the root .gitignore")
    add.add_argument("patterns", nargs="+")
    args = parser.parse_args(argv)

    try:
        root = repo_root()
        os.chdir(root)  # every git call below is root-relative, whatever the caller's cwd
        if args.command == "add":
            added = add_patterns(root, args.patterns)
            if added:
                print("added to .gitignore: " + ", ".join(added))
            else:
                print("nothing to add - every pattern is already present")
            return 0
        result = audit(root)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result, indent=2) if args.json else render(result))
    return 1 if result["uncovered"] or result["tracked_but_ignored"] else 0


if __name__ == "__main__":
    sys.exit(main())
