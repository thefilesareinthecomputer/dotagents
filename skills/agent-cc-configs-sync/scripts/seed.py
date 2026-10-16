#!/usr/bin/env python3
"""seed: plan and apply one harness's station seeds from its specs/<harness>/seed.json.

Each row of that file names an element, one of the six shapes defined in
specs/SEEDING-SHAPES.md and the station path, and the dispatcher does what the
shape says: NATIVE reports the path the harness reads, POINTER writes a small
file only when it is absent, LINK runs sync-skills.sh, COPY diffs then copies,
FRAGMENT merges the named keys into a station-owned file and N/A prints the
reason. A harness whose binary and config home are both missing is reported as
not installed and skipped, so `--harness all` seeds whatever the station has.
Nothing is written without `apply`, and a FRAGMENT write is verified by
re-reading the file before it lands.

Commands
  plan   --harness H|all [--home DIR] [--element E ...] [--key K ...]   show every change the station needs
  apply  --harness H|all [--home DIR] [--element E ...] [--key K ...]   write the plan

--element takes a row, --key narrows a FRAGMENT row to named keys. A JSON
object or list value is written whole and the plan names the station-only
entries that drops, except that a permissions deny list is always the union.
An existing file is kept once as <name>.seed-bak, a symlinked file is written
through to its target, and apply shows the diff it writes. --home DIR stands in
for the user's home (tests and dry runs), --repo DIR for this repository,
--force seeds one harness the station does not seem to have. Stdlib only.
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness_probe  # noqa: E402

REPO = Path(os.environ.get("AGENTS_REPO") or Path(__file__).resolve().parents[3])
SHAPES = {"NATIVE", "POINTER", "LINK", "COPY", "FRAGMENT", "N/A"}
FORMATS = {"json", "json-flat", "toml", "yaml-flat", "profile", "json-entries"}
KEY_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_-]*(?:\.[A-Za-z0-9_][A-Za-z0-9_-]*)*")
PROFILE_KEY_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
BACKUP_SUFFIX = ".seed-bak"
SEED_HOOKS = Path(__file__).resolve().parent / "seed_hooks.py"
WHICH = shutil.which


class SeedError(Exception):
    pass


# --- the table ---------------------------------------------------------------

def load_table(repo: Path, harness: str) -> list[dict]:
    p = repo / "specs" / harness / "seed.json"
    if not p.is_file():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    if data.get("schema") != 1 or data.get("harness") != harness or not isinstance(data.get("rows"), list):
        raise SeedError(f"{p}: schema 1 for harness {harness} with a rows list expected")
    for i, r in enumerate(data["rows"]):
        where = f"{p}: row {i}"
        if not isinstance(r, dict) or not r.get("element") or r.get("shape") not in SHAPES:
            raise SeedError(f"{where} needs an element and one of the six shapes")
        if r["shape"] != "N/A" and not r.get("path"):
            raise SeedError(f"{where} needs a station path")
        if r.get("path") and (not r["path"].startswith("~/") or ".." in Path(r["path"]).parts):
            raise SeedError(f"{where} station path must be portable (~/...) with no ..")
        for k in ("source", "target"):
            if r.get(k) and (os.path.isabs(r[k]) or ".." in Path(r[k]).parts):
                raise SeedError(f"{where} {k} must be a repo-relative path with no ..")
        if r["shape"] == "FRAGMENT" and not r.get("via"):
            if r.get("format") not in FORMATS or r["format"] == "json-entries":
                raise SeedError(f"{where} fragment needs format json, json-flat, toml, yaml-flat or profile")
            keys = r.get("keys")
            if isinstance(keys, dict):
                names = list(keys)
            elif isinstance(keys, list) and r.get("source"):
                names = keys
            else:
                raise SeedError(f"{where} fragment needs keys (a dict of values, or a list read from source)")
            bad = [k for k in names if not KEY_RE.fullmatch(k)]
            if bad or not names:
                raise SeedError(f"{where} fragment key names are dotted identifiers: {bad or 'none given'}")
            if r["format"] in ("yaml-flat", "profile") and any("." in k for k in names):
                raise SeedError(f"{where} {r['format']} keys are flat, no dots")
            if r["format"] == "profile" and not all(PROFILE_KEY_RE.fullmatch(k) for k in names):
                raise SeedError(f"{where} profile keys are shell variable names")
        if r["shape"] == "POINTER" and not (r.get("source") or r.get("format") == "json-entries"):
            raise SeedError(f"{where} pointer needs a source file or format json-entries with a target")
        if r["shape"] == "COPY" and not (r.get("source") or r.get("via")):
            raise SeedError(f"{where} copy needs a source file")
        for k in ("source",):
            if r.get(k) and not (repo / r[k]).is_file():
                raise SeedError(f"{where} names a missing seed file {r[k]}")
    return data["rows"]


def probe_row(harness: str) -> harness_probe.Row | None:
    return next((r for r in harness_probe.ROWS if r.harness == harness), None)


def detected(row: harness_probe.Row, home: Path) -> tuple[bool, str]:
    """A harness counts as present when its binary is on PATH or its config
    home exists; the version is for the report only."""
    exe = WHICH(row.binary)
    cfg = home / row.config_home
    version = harness_probe.version_of(row.binary) if exe else "not installed"
    return bool(exe) or cfg.is_dir(), version


def expand(path_str: str, home: Path) -> Path:
    return Path(path_str.replace("~", str(home), 1)) if path_str.startswith("~") else Path(path_str)


# --- literals and merges ------------------------------------------------------

def toml_literal(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, str):
        return json.dumps(v)
    raise SeedError(f"toml fragment values are scalars, not {type(v).__name__}")


def yaml_literal(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, str) and re.fullmatch(r"[A-Za-z0-9_./:-]+", v) and v.lower() not in ("true", "false", "null", "yes", "no"):
        return v
    if isinstance(v, str):
        return json.dumps(v)
    raise SeedError(f"yaml fragment values are scalars, not {type(v).__name__}")


def profile_literal(v) -> str:
    s = str(v).lower() if isinstance(v, bool) else str(v)
    if not re.fullmatch(r"[A-Za-z0-9_./:-]*", s):
        raise SeedError(f"profile fragment value {s!r} needs quoting; seed a plain token")
    return s


def get_path(d: dict, dotted: str):
    cur = d
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None, False
        cur = cur[part]
    return cur, True


def set_path(d: dict, dotted: str, value) -> None:
    parts = dotted.split(".")
    cur = d
    for part in parts[:-1]:
        if not isinstance(cur.get(part), dict):
            cur[part] = {}
        cur = cur[part]
    cur[parts[-1]] = value


def json_style(text: str) -> tuple[str, str]:
    """The indent unit and line ending the station file already uses, so a
    one-key merge does not rewrite every line."""
    m = re.search(r"^([ \t]+)\S", text, re.M)
    indent = m.group(1) if m else "  "
    return indent, ("\n" if text.endswith("\n") or not text.strip() else "")


def describe(v) -> str:
    if isinstance(v, dict):
        return f"object of {len(v)} keys"
    if isinstance(v, list):
        return f"list of {len(v)}"
    return json.dumps(v)


def station_only(cur, new) -> list[str]:
    """Entries the station holds inside an object or list value that the seed
    value lacks, so the plan names what a whole-value write would drop."""
    if isinstance(cur, dict) and isinstance(new, dict):
        out = [k for k in cur if k not in new]
        for k in cur:
            if k in new:
                out += [f"{k}.{d}" for d in station_only(cur[k], new[k])]
        return out
    if isinstance(cur, list) and isinstance(new, list):
        return [json.dumps(x) for x in cur if x not in new]
    return []


def keep_denies(k: str, cur, new):
    """A seed never removes a restriction the station added: `permissions.deny`
    and `permissions.ask` are written as the union, a seed without the list
    counting as empty (invariant: widening keys move only tighter)."""
    if k.split(".")[-1] == "permissions" and isinstance(cur, dict) and isinstance(new, dict):
        new = dict(new)
        for lst in ("deny", "ask"):
            if isinstance(cur.get(lst), list):
                mine = new.get(lst) if isinstance(new.get(lst), list) else []
                new[lst] = mine + [d for d in cur[lst] if d not in mine]
    return new


def merge_json(text: str, keys: dict, flat: bool = False) -> tuple[str, list[str]]:
    """Dotted keys are paths into nested objects unless `flat`, where each key
    is one literal top-level name (VS Code's settings.json). An object or list
    value is written whole, with the station-only entries it drops named in
    the change line; deny lists are unioned, never shortened."""
    doc = json.loads(text) if text.strip() else {}
    if not isinstance(doc, dict):
        raise SeedError("the station file is not a JSON object")
    changes = []
    for k, v in keys.items():
        cur, present = (doc.get(k), k in doc) if flat else get_path(doc, k)
        if present:
            v = keep_denies(k, cur, v)
        if present and cur == v:
            continue
        line = f"{k} = {describe(v)}" + ("" if not present else f" (was {describe(cur)})")
        drops = station_only(cur, v) if present else []
        if drops:
            line += "; drops station-only " + ", ".join(drops)
        changes.append(line)
        if flat:
            doc[k] = v
        else:
            set_path(doc, k, v)
    indent, nl = json_style(text)
    return json.dumps(doc, indent=indent) + nl, changes


def merge_json_flat(text: str, keys: dict) -> tuple[str, list[str]]:
    return merge_json(text, keys, flat=True)


def merge_json_entries(text: str, target: str) -> tuple[str, list[str]]:
    """Antigravity's pointer file: an `entries` list of {"path": ...}; ours is
    added when no entry already names the target."""
    doc = json.loads(text) if text.strip() else {}
    if not isinstance(doc, dict):
        raise SeedError("the station file is not a JSON object")
    entries = doc.get("entries")
    if entries is None:
        entries = doc["entries"] = []
    if not isinstance(entries, list):
        raise SeedError("entries is not a list")
    if any(isinstance(e, dict) and e.get("path") == target for e in entries):
        return text, []
    entries.append({"path": target})
    return json.dumps(doc, indent=2) + "\n", [f"entries += {target}"]


def _header_re(table: str) -> re.Pattern:
    return re.compile(r"^\s*\[\s*" + re.escape(table) + r"\s*\]\s*(#.*)?$")


def merge_toml(text: str, keys: dict) -> tuple[str, list[str]]:
    import tomllib
    try:
        before = tomllib.loads(text)
    except ValueError as e:
        raise SeedError(f"the station config.toml does not parse: {e}")
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    changes = []
    any_header = re.compile(r"^\s*\[")
    for k, v in keys.items():
        cur, present = get_path(before, k)
        if present and cur == v:
            continue
        changes.append(f"{k} = {toml_literal(v)}" + ("" if not present else f" (was {toml_literal(cur) if isinstance(cur, (bool, int, float, str)) else '...'})"))
        table, _, leaf = k.rpartition(".")
        if not table:
            raise SeedError(f"toml fragment keys live in a table: {k}")
        hdr = _header_re(table)
        key_in = re.compile(r"^\s*" + re.escape(leaf) + r"\s*=")
        dotted = re.compile(r"^\s*" + re.escape(k) + r"\s*=")
        start = next((i for i, l in enumerate(lines) if hdr.match(l)), None)
        if start is not None:
            end = next((i for i in range(start + 1, len(lines)) if any_header.match(lines[i])), len(lines))
            hit = next((i for i in range(start + 1, end) if key_in.match(lines[i])), None)
            if hit is not None:
                lines[hit] = f"{leaf} = {toml_literal(v)}\n"
            else:
                lines.insert(start + 1, f"{leaf} = {toml_literal(v)}\n")
            continue
        first_header = next((i for i, l in enumerate(lines) if any_header.match(l)), len(lines))
        root_dotted = [i for i in range(first_header) if re.match(r"^\s*" + re.escape(table) + r"\.", lines[i])]
        hit = next((i for i in range(first_header) if dotted.match(lines[i])), None)
        if hit is not None:
            lines[hit] = f"{k} = {toml_literal(v)}\n"
        elif root_dotted:
            lines.insert(root_dotted[-1] + 1, f"{k} = {toml_literal(v)}\n")
        else:
            if lines and lines[-1].strip():
                lines.append("\n")
            lines.append(f"[{table}]\n{leaf} = {toml_literal(v)}\n")
    out = "".join(lines)
    try:
        after = tomllib.loads(out)
    except ValueError as e:
        raise SeedError(f"the merged config.toml would not parse, nothing written: {e}")
    for k, v in keys.items():
        got, present = get_path(after, k)
        if not present or got != v:
            raise SeedError(f"the merged config.toml does not read {k} = {toml_literal(v)}, nothing written")
    return out, changes


def merge_yaml_flat(text: str, keys: dict) -> tuple[str, list[str]]:
    """Top-level `KEY: value` lines only (goose's config.yaml). The last
    occurrence of a key wins in YAML, so every duplicate is folded into one."""
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    changes = []
    for k, v in keys.items():
        pat = re.compile(r"^" + re.escape(k) + r":\s*(.*?)\s*$")
        hits = [i for i, l in enumerate(lines) if pat.match(l)]
        want = yaml_literal(v)
        current = pat.match(lines[hits[-1]]).group(1) if hits else None
        if hits and current == want and len(hits) == 1:
            continue
        changes.append(f"{k}: {want}" + (f" (was {current})" if current is not None else ""))
        if hits:
            lines[hits[0]] = f"{k}: {want}\n"
            for i in reversed(hits[1:]):
                del lines[i]
        else:
            lines.append(f"{k}: {want}\n")
    out = "".join(lines)
    for k, v in keys.items():
        found = re.findall(r"^" + re.escape(k) + r":\s*(.*?)\s*$", out, re.M)
        if found[-1:] != [yaml_literal(v)]:
            raise SeedError(f"the merged yaml does not read {k}: {yaml_literal(v)}, nothing written")
    return out, changes


def merge_profile(text: str, keys: dict) -> tuple[str, list[str]]:
    """`export KEY=value` lines in a shell rc file; one line per key."""
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    changes = []
    for k, v in keys.items():
        pat = re.compile(r"^\s*export\s+" + re.escape(k) + r"=(\S*)\s*$")
        hits = [i for i, l in enumerate(lines) if pat.match(l)]
        want = profile_literal(v)
        current = pat.match(lines[hits[-1]]).group(1) if hits else None
        if hits and current == want and len(hits) == 1:
            continue
        changes.append(f"export {k}={want}" + (f" (was {current})" if current is not None else ""))
        if hits:
            lines[hits[0]] = f"export {k}={want}\n"
            for i in reversed(hits[1:]):
                del lines[i]
        else:
            lines.append(f"export {k}={want}\n")
    return "".join(lines), changes


MERGERS = {"json": merge_json, "json-flat": merge_json_flat, "toml": merge_toml,
           "yaml-flat": merge_yaml_flat, "profile": merge_profile}


def fragment_keys(row: dict, repo: Path) -> dict:
    keys = row["keys"]
    if isinstance(keys, dict):
        return keys
    src = json.loads((repo / row["source"]).read_text(encoding="utf-8"))
    out = {}
    for k in keys:
        v, present = get_path(src, k)
        if not present:
            raise SeedError(f"{row['source']} has no key {k}")
        out[k] = v
    return out


# --- the verbs ---------------------------------------------------------------

def read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def write_target(path: Path, home: Path) -> Path:
    """The file a write lands in: the path itself, or a symlink's target when
    that target is a real file under the home. A dangling or looping link, or
    a target outside the home, is refused rather than created."""
    if not path.is_symlink():
        return path
    try:
        target = path.resolve(strict=True)
    except (OSError, RuntimeError) as e:
        raise SeedError(f"{path} is a symlink that does not resolve ({e.__class__.__name__}); fix the link first")
    if home.resolve() not in target.parents:
        raise SeedError(f"{path} links outside the home, to {target}; not written")
    return target


def write_text_atomic(path: Path, text: str, home: Path) -> str:
    """Write through a symlink to its target (a dotfiles-managed ~/.zshrc stays
    managed), keep one rolling backup of an existing file, and swap in a temp
    file created in the target's folder with an unguessable name. Returns a
    note for the report."""
    target = write_target(path, home)
    note = f" (through the symlink, into {target})" if target != path else ""
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        bak = target.with_name(target.name + BACKUP_SUFFIX)
        if bak.is_symlink():
            bak.unlink()
        shutil.copy2(target, bak)
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".seed-tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    if target.exists():
        shutil.copymode(target, tmp)
    os.replace(tmp, target)
    return note


def udiff(before: str, after: str, label: str) -> str:
    d = "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                     f"{label} (station)", f"{label} (seeded)"))
    return d if not d or d.endswith("\n") else d + "\n"


def plan_row(row: dict, home: Path, repo: Path, harness: str, write: bool, only_keys: list[str] = ()) -> dict:
    """One row's plan: {"verb", "element", "lines": [...], "diff": str, "writes": [(path, text)]}.
    `write` only matters for the two verbs that call another script; `only_keys`
    narrows a FRAGMENT row to the keys named."""
    shape, element = row["shape"], row["element"]
    out = {"verb": shape.lower(), "element": element, "lines": [], "diff": "", "writes": [], "via": None, "summarize": False}
    path = expand(row["path"], home) if row.get("path") else None
    label = row.get("path", "")
    if path is not None and shape in ("POINTER", "COPY", "FRAGMENT") and path.is_symlink():
        out["lines"].append(f"{label} is a symlink; writes go through it, into {write_target(path, home)}")

    if shape == "N/A":
        out["lines"].append(row.get("note", "does not port to this harness"))
    elif shape == "NATIVE":
        out["lines"].append(f"reads {label}; nothing to do")
    elif row.get("via") == "seed_hooks":
        out["via"] = [sys.executable, str(SEED_HOOKS), "apply" if write else "plan",
                      "--harness", harness, "--home", str(home), "--repo", str(repo)]
    elif shape == "LINK":
        script = repo / "sync-skills.sh"
        if not script.is_file():
            raise SeedError(f"{script} is missing")
        if row.get("also"):
            out["element"] = f"{element} (also {', '.join(row['also'])})"
        out["via"] = ["bash", str(script)] + ([] if write else ["--dry-run"])
        out["summarize"] = True
    elif shape == "COPY":
        src = repo / row["source"]
        seed = src.read_text(encoding="utf-8")
        cur = read_text(path)
        if not path.exists():
            out["lines"].append(f"{label}: absent, copy {row['source']}")
            out["writes"].append((path, seed))
        elif cur == seed:
            out["lines"].append(f"{label}: in parity")
        else:
            out["lines"].append(f"{label}: differs from {row['source']}, seed replaces it")
            out["diff"] = udiff(cur, seed, label)
            out["writes"].append((path, seed))
    elif shape == "POINTER":
        if row.get("format") == "json-entries":
            target = str((repo / row["target"]).resolve())
            cur = read_text(path)
            try:
                merged, changes = merge_json_entries(cur, target)
            except ValueError as e:
                raise SeedError(f"{label} does not parse: {e}")
            if changes:
                out["lines"].append(f"{label}: " + ("absent, write pointer" if not path.exists() else "present without this repo") + f" -> {target}")
                out["diff"] = udiff(cur, merged, label)
                out["writes"].append((path, merged))
            else:
                out["lines"].append(f"{label}: names {target}")
        else:
            seed = (repo / row["source"]).read_text(encoding="utf-8")
            cur = read_text(path)
            if not path.exists():
                out["lines"].append(f"{label}: absent, write {row['source']}")
                out["writes"].append((path, seed))
            elif cur == seed:
                out["lines"].append(f"{label}: matches {row['source']}")
            else:
                out["lines"].append(f"{label}: present and differs from {row['source']}; a pointer is never overwritten, reconcile by hand")
                out["diff"] = udiff(cur, seed, label)
    elif shape == "FRAGMENT":
        if row.get("if_present") and not path.exists():
            out["lines"].append(f"{label}: not present, skipped (the seed does not create this file)")
            return out
        keys = fragment_keys(row, repo)
        if only_keys:
            unknown = [k for k in only_keys if k not in keys]
            if unknown:
                raise SeedError(f"{element}: --key names keys this row does not seed: {', '.join(unknown)}")
            keys = {k: v for k, v in keys.items() if k in only_keys}
        cur = read_text(path)
        try:
            merged, changes = MERGERS[row["format"]](cur, keys)
        except ValueError as e:
            raise SeedError(f"{label} does not parse: {e}")
        if changes:
            out["lines"].extend(f"{label}: set {c}" for c in changes)
            if row["format"] in ("json", "json-flat"):
                # Only the seeded keys: the rest of a station JSON file can
                # hold an auth cache, and it never belongs in the report.
                flat = row["format"] == "json-flat"
                out["diff"] = udiff(json_subset(cur, keys, flat), json_subset(merged, keys, flat), f"{label} (seeded keys)")
            else:
                out["diff"] = udiff(cur, merged, label)
            out["writes"].append((path, merged))
        else:
            out["lines"].append(f"{label}: {len(keys)} keys in parity")
    return out


def json_subset(text: str, keys: dict, flat: bool) -> str:
    doc = json.loads(text) if text.strip() else {}
    sub = {}
    for k in keys:
        cur, present = (doc.get(k), k in doc) if flat else get_path(doc, k)
        if present:
            sub[k] = cur
    return json.dumps(sub, indent=2) + "\n"


def summarize_links(text: str) -> list[str]:
    """sync-skills.sh prints one line per entry; refreshes of existing links
    are counted, everything else (new links, prunes, kept locals, errors) is
    shown as is."""
    counts: dict[str, int] = {}
    kept = []
    for line in text.splitlines():
        if line.startswith("DRY: ") or line.startswith("== ") or line.startswith("done."):
            continue
        tag = line.split(":", 1)[0].strip()
        if tag in ("link (refresh)", "link global", "prune dangling", "skip local"):
            counts[tag] = counts.get(tag, 0) + 1
            if tag != "link (refresh)":
                kept.append(line)
        elif line.strip():
            kept.append(line)
    head = ", ".join(f"{n} {t}" for t, n in counts.items()) or "nothing linked"
    return [head] + kept


def run_via(argv: list[str], home: Path) -> tuple[int, str]:
    env = dict(os.environ, HOME=str(home))
    p = subprocess.run(argv, text=True, capture_output=True, env=env, stdin=subprocess.DEVNULL)
    return p.returncode, (p.stdout + p.stderr)


def seed_harness(harness: str, home: Path, repo: Path, write: bool, elements: list[str], force: bool,
                 only_keys: list[str] = ()) -> int:
    row = probe_row(harness)
    if row is None:
        raise SeedError(f"unknown harness {harness}; one of {', '.join(r.harness for r in harness_probe.ROWS)}")
    present, version = detected(row, home)
    if not present and not force:
        print(f"seed {harness}: not installed (no {row.binary} on PATH, no ~/{row.config_home}); skipped")
        return 0
    table = load_table(repo, harness)
    if not table:
        print(f"seed {harness} ({version}): no specs/{harness}/seed.json; nothing to seed")
        return 0
    rows = [r for r in table if not elements or r["element"] in elements]
    if only_keys:
        rows = [r for r in rows if r["shape"] == "FRAGMENT"]   # --key names keys, so only key-bearing rows run
    print(f"seed {harness} ({version}, ~/{row.config_home}): {len(rows)} rows" + (" [apply]" if write else ""))
    rc = 0
    for r in rows:
        try:
            p = plan_row(r, home, repo, harness, write, only_keys if r["shape"] == "FRAGMENT" else ())
        except SeedError as e:
            print(f"  error    {r['element']}: {e}")
            rc = 1
            continue
        tag = f"  {p['verb']:<8} {p['element']}"
        if p["via"]:
            code, text = run_via(p["via"], home)
            print(f"{tag}: {Path(p['via'][1]).name} {' '.join(p['via'][2:3])}".rstrip())
            lines = summarize_links(text) if p["summarize"] else text.rstrip().splitlines()
            for line in lines:
                print(f"           {line}")
            rc = rc or code
            continue
        for i, line in enumerate(p["lines"]):
            print(f"{tag}: {line}" if i == 0 else f"  {'':<8} {'':<{len(p['element'])}}  {line}")
        # The diff is shown on apply too: the station may have moved since the
        # plan, and what lands is what this run computed.
        if p["diff"]:
            print(p["diff"], end="")
        if write:
            for path, text in p["writes"]:
                note = write_text_atomic(path, text, home)
                print(f"           wrote {path.name}{note}")
    return rc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "apply"):
        p = sub.add_parser(name)
        p.add_argument("--harness", default="claude-code", help="a harness name, or all")
        p.add_argument("--home", default="~")
        p.add_argument("--repo", default=str(REPO))
        p.add_argument("--element", action="append", default=[], help="seed only these elements (repeatable)")
        p.add_argument("--key", action="append", default=[], help="within FRAGMENT rows, seed only these keys (repeatable)")
        p.add_argument("--force", action="store_true", help="seed even when the harness is not detected")
    a = ap.parse_args(argv)
    if a.force and a.harness == "all":
        ap.error("--force takes one harness; with all it would create config homes for harnesses the station lacks")
    home = Path(a.home).expanduser().resolve()
    repo = Path(a.repo).resolve()
    names = [r.harness for r in harness_probe.ROWS] if a.harness == "all" else [a.harness]
    rc = 0
    try:
        for h in names:
            rc = seed_harness(h, home, repo, a.cmd == "apply", a.element, a.force, a.key) or rc
    except SeedError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
