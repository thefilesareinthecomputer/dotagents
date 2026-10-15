#!/usr/bin/env python3
"""seed-hooks: write one harness's native hook wiring from the hook manifests.

Reads the central manifest (hooks/manifest.json) plus the harness's own
(specs/<harness>/hooks/manifest.json), copies the scripts of both folders flat
into the harness's hooks folder, and merges the managed wiring entries into the
harness's wiring file: Claude Code's settings.json `hooks` key, Codex's
hooks.json. Diff first; nothing is written without `apply`. Only entries the
manifests name or a previous run installed are ever touched; anything the user
added by hand stays in place.

Commands
  plan   --harness H [--home DIR]   diff the files and the wiring, list every skip and its reason
  apply  --harness H [--home DIR]   write the plan (codex refuses until its capture fixture exists)
  render --harness H                print the generated wiring object
  seed   --harness claude-code      rewrite the hooks key of the repository seed settings.json

--home DIR stands in for the user's home (tests and dry runs); --repo DIR for
this repository. Stdlib only.
"""
import argparse
import difflib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(os.environ.get("AGENTS_REPO") or Path(__file__).resolve().parents[3])
LEDGER_NAME = ".seed-hooks.json"
# Never seeded: manifests, tests, caches, the station ledger (hidden, so the
# dot rule covers it too) and every markdown file - AGENTS.md, CLAUDE.md and
# any README beside the hooks are rules for agents editing the repo, not
# station files.
SKIP_FILES = {"manifest.json", "__pycache__", "tests", ".DS_Store", LEDGER_NAME}
SKIP_SUFFIXES = {".md"}
INTERPRETERS = {".sh": "bash", ".py": "python3"}
CODEX_FIXTURE = "hooks/tests/fixtures/codex.json"


class SeedError(Exception):
    pass


def load_input_module(repo: Path):
    src = repo / "hooks" / "_input.py"
    spec = importlib.util.spec_from_file_location("hook_input", src)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["hook_input"] = mod
    spec.loader.exec_module(mod)
    return mod


# --- manifests ---------------------------------------------------------------

def read_manifest(path: Path, harness_specific: str | None) -> list[dict]:
    if not path.is_file():
        return []
    data = json.loads(path.read_text())
    if data.get("schema") != 1 or not isinstance(data.get("entries"), list):
        raise SeedError(f"{path}: schema 1 with an entries list expected")
    entries = []
    for i, e in enumerate(data["entries"]):
        if not isinstance(e, dict) or not (e.get("script") or e.get("command")):
            raise SeedError(f"{path}: entry {i} needs script or command")
        if e.get("script") and e.get("command"):
            raise SeedError(f"{path}: entry {i} has both script and command")
        if e.get("script"):
            # A plain basename of a file this folder seeds: the name goes into a
            # shell command and a station path, so no separators, dots-only
            # names or spaces.
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", e["script"]):
                raise SeedError(f"{path}: entry {i} script name {e['script']!r} is not a plain filename")
            if e["script"] not in {f.name for f in seed_files(path.parent)}:
                raise SeedError(f"{path}: entry {i} names a missing script {e['script']}")
        if not isinstance(e.get("bindings"), list) or not e["bindings"]:
            raise SeedError(f"{path}: entry {i} needs at least one binding")
        for b in e["bindings"]:
            if not isinstance(b, dict) or not b.get("event"):
                raise SeedError(f"{path}: entry {i} has a binding without an event")
            if "matcher" in b and "sources" in b:
                raise SeedError(f"{path}: entry {i} binding names both matcher and sources")
            if "timeout" in b and (not isinstance(b["timeout"], int) or b["timeout"] <= 0):
                raise SeedError(f"{path}: entry {i} timeout must be a positive integer")
        entry = dict(e)
        entry["_folder"] = path.parent
        entry["_harnesses"] = [harness_specific] if harness_specific else list(e.get("harnesses") or [])
        entries.append(entry)
    return entries


def seed_files(folder: Path) -> list[Path]:
    """The files a folder seeds: tracked files when the folder is in a git
    repository (so a scratch or ignored file never reaches a station), else
    every regular file; never manifests, tests, hidden files, caches or
    markdown (SKIP_FILES and SKIP_SUFFIXES)."""
    if not folder.is_dir():
        return []
    names: list[str] | None = None
    try:
        out = subprocess.run(["git", "-C", str(folder), "ls-files", "-z", "--", "."],
                             text=True, capture_output=True, check=True).stdout
        names = [n for n in out.split("\0") if n]
    except (OSError, subprocess.CalledProcessError):
        names = None
    if names is None:
        # Not a git repository (a test copy): every regular file. Inside a
        # repository an empty tracked set seeds nothing, so a scratch file
        # dropped into the folder never reaches a station.
        names = [p.name for p in folder.iterdir()]
    return sorted(folder / n for n in set(names)
                  if "/" not in n and (folder / n).is_file()
                  and n not in SKIP_FILES and not n.startswith(".")
                  and Path(n).suffix not in SKIP_SUFFIXES)


def load_seeds(repo: Path, harness: str) -> tuple[list[dict], list[Path]]:
    central = read_manifest(repo / "hooks" / "manifest.json", None)
    own = read_manifest(repo / "specs" / harness / "hooks" / "manifest.json", harness)
    files = seed_files(repo / "hooks") + seed_files(repo / "specs" / harness / "hooks")
    seen: dict[str, Path] = {}
    for f in files:
        if f.name in seen:
            raise SeedError(f"duplicate basename {f.name} in {seen[f.name].parent} and {f.parent}; "
                            "both folders land flat in one station folder")
        seen[f.name] = f
    return central + own, files


# --- rendering ---------------------------------------------------------------

def command_for(entry: dict, hook_home: str) -> str:
    if entry.get("command"):
        return entry["command"]
    script = entry["script"]
    interp = INTERPRETERS.get(Path(script).suffix)
    if not interp:
        raise SeedError(f"{script}: no interpreter for its extension")
    return f"{interp} {hook_home}/{script}"


def render(entries: list[dict], harness: str, hi) -> tuple[dict, list[str], list[str]]:
    """The harness's wiring object, the skip reasons, and the managed commands."""
    if harness not in hi.HARNESSES:
        raise SeedError(f"unknown harness {harness}; known: {', '.join(hi.HARNESSES)}")
    hook_home = hi.HOOK_HOME[harness]
    groups: dict[tuple[str, str], list[dict]] = {}
    skips: list[str] = []
    managed: list[str] = []
    for e in entries:
        name = e.get("script") or e["command"]
        if harness not in e["_harnesses"] and "all" not in e["_harnesses"]:
            skips.append(f"{name}: not tested against {harness} (harnesses: {', '.join(e['_harnesses']) or 'none'})")
            continue
        cmd = command_for(e, hook_home)
        for b in e["bindings"]:
            event = b["event"]
            if event not in hi.EVENTS[harness]:
                skips.append(f"{name}: {harness} has no {event} event")
                continue
            matcher = ""
            if "sources" in b:
                # Projected like tool classes: the sources the harness is known
                # to report are written, the rest reported, never an unmatched
                # entry, which would widen a startup-only hook.
                known = hi.SESSION_SOURCES.get(harness) or []
                have = [s for s in b["sources"] if s in known]
                bad = [s for s in b["sources"] if s not in known]
                if bad:
                    skips.append(f"{name}: {event} source {', '.join(bad)} not captured for {harness}"
                                 + (f"; written for {'|'.join(have)}" if have else "; binding skipped"))
                if not have:
                    continue
                matcher = "|".join(have)
            elif b.get("matcher"):
                matcher, unmapped = hi.expand_matcher(harness, b["matcher"])
                if unmapped:
                    skips.append(f"{name}: {event} class {', '.join(unmapped)} has no {harness} tool"
                                 + (f"; written for {matcher}" if matcher else "; binding skipped"))
                if not matcher:
                    continue
            hook = {"type": "command", "command": cmd}
            if "timeout" in b:
                hook["timeout"] = b["timeout"]
            groups.setdefault((event, matcher), []).append(hook)
            if cmd not in managed:
                managed.append(cmd)
    wiring: dict[str, list] = {}
    for (event, matcher), hooks in groups.items():
        g = {"matcher": matcher, "hooks": hooks} if matcher else {"hooks": hooks}
        wiring.setdefault(event, []).append(g)
    return wiring, skips, managed


def tuples(wiring: dict, hi) -> set[tuple]:
    """The flattened effect of a wiring object: (event, matcher set, command, timeout)."""
    out = set()
    for event, groups in (wiring or {}).items():
        for g in groups or []:
            for h in g.get("hooks") or []:
                out.add((event, hi.matcher_set(g.get("matcher")), h.get("command", ""), h.get("timeout")))
    return out


# --- station -----------------------------------------------------------------

def expand(path_str: str, home: Path) -> Path:
    return Path(path_str.replace("~", str(home), 1)) if path_str.startswith("~") else Path(path_str)


def norm_cmd(cmd: str, home: Path) -> str:
    """A command compared with its home expanded and its script path resolved,
    so `bash ~/.claude/hooks/x.sh` and the same script by absolute or
    symlinked path are one command."""
    c = cmd.replace("~/", str(home) + "/").replace("$HOME/", str(home) + "/")
    m = re.match(r"^(\S+\s+)(\S+)$", c)
    if m and Path(m.group(2)).is_absolute():
        p = Path(m.group(2))
        try:
            p = p.resolve()
        except OSError:
            pass
        c = m.group(1) + str(p)
    return c


def read_ledger(hook_dir: Path) -> dict:
    """What earlier runs installed: wiring tuples and file names."""
    p = hook_dir / LEDGER_NAME
    if p.is_file():
        try:
            data = json.loads(p.read_text())
            if isinstance(data, dict):
                return {"entries": list(data.get("entries") or []), "files": list(data.get("files") or [])}
        except ValueError:
            pass
    return {"entries": [], "files": []}


def ledger_tuples(ledger: dict, hi) -> set[tuple]:
    out = set()
    for e in ledger.get("entries", []):
        if isinstance(e, list) and len(e) == 4:
            out.add((e[0], hi.matcher_set(e[1]), e[2], e[3]))
    return out


def merge(current: dict, rendered: dict, ledger: dict, home: Path, hi) -> tuple[dict, dict]:
    """Rendered managed entries plus the station's unmanaged ones, in place.
    A station entry is managed by its whole binding, (event, matcher, command),
    never by its command alone: it is managed when a current manifest renders
    that binding, or when a previous run installed it (the ledger). A hand-wired
    entry that reuses a manifest script on another event or matcher is the
    user's and stays."""
    report = {"kept_unmanaged": [], "retired": [], "added": [], "unchanged": [], "rewritten": []}
    after = tuples(rendered, hi)
    after_keys = {(t[0], t[1], norm_cmd(t[2], home)) for t in after}
    after_norm = {(t[0], t[1], norm_cmd(t[2], home), t[3]) for t in after}
    ledger_norm = {(t[0], t[1], norm_cmd(t[2], home), t[3]) for t in ledger_tuples(ledger, hi)}
    before = tuples(current, hi)
    out: dict[str, list] = {}
    events = list(rendered) + [e for e in (current or {}) if e not in rendered]
    for event in events:
        groups = list(rendered.get(event, []))
        for g in (current or {}).get(event, []) or []:
            mset = hi.matcher_set(g.get("matcher"))
            keep = []
            for h in g.get("hooks") or []:
                cmd = h.get("command", "")
                label = f"{event} {g.get('matcher', '')} {cmd}".strip()
                tn = (event, mset, norm_cmd(cmd, home), h.get("timeout"))
                if tn[:3] in after_keys:
                    (report["unchanged"] if tn in after_norm else report["rewritten"]).append(cmd)
                elif tn in ledger_norm:
                    report["retired"].append(label)
                else:
                    report["kept_unmanaged"].append(label)
                    keep.append(h)
            if keep:
                ng = dict(g)
                ng["hooks"] = keep
                groups.append(ng)
        if groups:
            out[event] = groups
    for t in sorted(after - before, key=str):
        report["added"].append(f"{t[0]} {'|'.join(sorted(t[1]))} {t[2]}".strip())
    return out, report


def write_text_atomic(path: Path, text: str) -> None:
    if path.is_symlink():
        raise SeedError(f"{path} is a symlink; refusing to write through it")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def copy_file(src: Path, dst: Path) -> None:
    """Copy through a temp file in the same folder, so a hook firing mid-copy
    never reads a truncated script."""
    if dst.is_symlink():
        raise SeedError(f"{dst} is a symlink; refusing to write through it")
    fd, tmp = tempfile.mkstemp(prefix=f".{dst.name}.", dir=str(dst.parent))
    os.close(fd)
    try:
        shutil.copy2(src, tmp)
        os.replace(tmp, dst)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def file_plan(files: list[Path], hook_dir: Path, ledger: dict) -> dict:
    plan = {"copy": [], "update": [], "same": [], "retired": []}
    names = {f.name for f in files}
    for f in files:
        dst = hook_dir / f.name
        if not dst.exists():
            plan["copy"].append(f)
        elif dst.read_bytes() != f.read_bytes():
            plan["update"].append(f)
        else:
            plan["same"].append(f)
    for name in ledger.get("files", []):
        if name not in names and (hook_dir / name).exists():
            plan["retired"].append(name)
    return plan


def requirements(entries: list[dict], harness: str) -> list[str]:
    missing = []
    for e in entries:
        if harness not in e["_harnesses"] and "all" not in e["_harnesses"]:
            continue
        for b in e.get("requires") or []:
            if shutil.which(b) is None:
                missing.append(f"{e.get('script') or e['command']}: needs {b}, not on PATH")
    return missing


def codex_features_off(home: Path) -> bool:
    cfg = home / ".codex" / "config.toml"
    if not cfg.is_file():
        return False
    in_features = False
    for line in cfg.read_text().splitlines():
        s = line.strip()
        if s.startswith("["):
            in_features = s == "[features]"
        elif in_features and re.match(r"^hooks\s*=\s*false", s):
            return True
    return False


def load_wiring(path: Path, key: str) -> tuple[dict, dict]:
    if not path.is_file():
        return {}, {}
    try:
        doc = json.loads(path.read_text())
    except ValueError as e:
        raise SeedError(f"{path} is not valid JSON: {e}")
    if not isinstance(doc, dict):
        raise SeedError(f"{path}: an object expected")
    return doc, doc.get(key) or {}


def dumps(obj) -> str:
    return json.dumps(obj, indent=2) + "\n"


def wiring_diff(before: dict, after: dict, label: str) -> str:
    a = dumps(before).splitlines(keepends=True)
    b = dumps(after).splitlines(keepends=True)
    return "".join(difflib.unified_diff(a, b, f"{label} (station)", f"{label} (seeded)"))


# --- commands ----------------------------------------------------------------

def cmd_plan(args, write: bool) -> int:
    repo = Path(args.repo).resolve()
    home = Path(args.home).expanduser().resolve()
    hi = load_input_module(repo)
    harness = args.harness
    entries, files = load_seeds(repo, harness)
    rendered, skips, managed = render(entries, harness, hi)
    hook_dir = expand(hi.HOOK_HOME[harness], home)
    wiring_path_s, key = hi.WIRING[harness]
    wiring_path = expand(wiring_path_s, home)
    ledger = read_ledger(hook_dir)
    doc, current = load_wiring(wiring_path, key)
    merged, report = merge(current, rendered, ledger, home, hi)
    # Files land only where something is wired; a harness with no managed
    # command gets no scripts.
    fplan = file_plan(files if managed else [], hook_dir, ledger)
    missing = requirements(entries, harness)
    # Grouping is not behavior, so the wiring is rewritten only when its effect
    # changes; Codex re-trusts every edited hook, so a byte-only rewrite costs.
    effect_changed = tuples(current, hi) != tuples(merged, hi)

    print(f"seed-hooks {harness}: {len(files)} seed files, {len(managed)} managed commands, wiring {wiring_path_s}")
    for s in skips:
        print(f"  skip     {s}")
    for m in missing:
        print(f"  missing  {m}")
    for f in fplan["copy"]:
        print(f"  copy     {f.name}")
    for f in fplan["update"]:
        print(f"  update   {f.name} (differs from the station copy)")
    for n in fplan["retired"]:
        print(f"  retired  {n} (installed by an earlier run, no longer seeded; remove by hand)")
    print(f"  same     {len(fplan['same'])} files")
    for k in ("added", "rewritten", "retired", "kept_unmanaged"):
        for line in report[k]:
            print(f"  {k:<8} {line}")
    print(f"  unchanged {len(report['unchanged'])} wiring entries")
    d = wiring_diff(current, merged, key) if effect_changed else ""
    if d:
        print(d, end="")
    elif not managed:
        print("  wiring   nothing to wire for this harness")
    elif current != merged:
        print("  wiring   same effect; grouping differs, left as is")
    changed = bool(fplan["copy"] or fplan["update"] or d)
    if not changed:
        print("  clean: nothing to apply")
    if harness == "codex":
        if codex_features_off(home):
            print("  note     ~/.codex/config.toml sets [features] hooks = false; nothing wired will run")
        if not (repo / CODEX_FIXTURE).is_file():
            print(f"  note     no capture fixture at {CODEX_FIXTURE}; apply refuses until the probe lands")
    if not write:
        return 0
    if harness == "codex" and not (repo / CODEX_FIXTURE).is_file():
        print("refused: codex apply needs the capture fixture first", file=sys.stderr)
        return 3
    if not changed:
        return 0
    hook_dir.mkdir(parents=True, exist_ok=True)
    for f in fplan["copy"] + fplan["update"]:
        copy_file(f, hook_dir / f.name)
    if d:
        doc[key] = merged
        write_text_atomic(wiring_path, dumps(doc))
    entries = sorted(([t[0], "|".join(sorted(t[1])), t[2], t[3]] for t in tuples(rendered, hi)),
                     key=lambda e: (e[0], e[1], e[2], e[3] or 0))
    write_text_atomic(hook_dir / LEDGER_NAME, dumps({"harness": harness, "entries": entries,
                                                     "files": [f.name for f in files] if managed else []}))
    print(f"applied: {len(fplan['copy']) + len(fplan['update'])} files, wiring {'written' if d else 'unchanged'}")
    if harness == "codex" and d:
        print("  codex trusts a hook definition once per edit: open codex, run /hooks, and trust the entries above")
    return 0


def cmd_render(args) -> int:
    repo = Path(args.repo).resolve()
    hi = load_input_module(repo)
    entries, _ = load_seeds(repo, args.harness)
    rendered, skips, _ = render(entries, args.harness, hi)
    print(dumps(rendered), end="")
    for s in skips:
        print(f"skip: {s}", file=sys.stderr)
    return 0


def cmd_seed(args) -> int:
    if args.harness != "claude-code":
        raise SeedError("seed rewrites the repository seed, which only claude-code has")
    repo = Path(args.repo).resolve()
    hi = load_input_module(repo)
    entries, _ = load_seeds(repo, args.harness)
    rendered, skips, _ = render(entries, args.harness, hi)
    for s in skips:
        print(f"skip: {s}", file=sys.stderr)
    seed = repo / "specs" / "claude-code" / "settings.json"
    doc = json.loads(seed.read_text())
    if doc.get("hooks") == rendered:
        print(f"{seed.relative_to(repo)}: hooks key already matches the manifests")
        return 0
    doc["hooks"] = rendered
    seed.write_text(dumps(doc))
    print(f"{seed.relative_to(repo)}: hooks key regenerated")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "apply", "render", "seed"):
        p = sub.add_parser(name)
        p.add_argument("--harness", default="claude-code")
        p.add_argument("--repo", default=str(REPO))
        if name in ("plan", "apply"):
            p.add_argument("--home", default="~")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "plan":
            return cmd_plan(args, write=False)
        if args.cmd == "apply":
            return cmd_plan(args, write=True)
        if args.cmd == "render":
            return cmd_render(args)
        return cmd_seed(args)
    except SeedError as e:
        print(f"seed-hooks: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
