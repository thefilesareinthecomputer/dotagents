#!/usr/bin/env python3
"""Inspect pending updates and compare an installed component with its incoming version.

Read-only: nothing here installs, updates or runs what it inspects.

    update.py plugins [--json] [--out DIR] [--no-network]
    update.py unpack ARCHIVE --dest DIR [--max-mb N]
    update.py delta --old DIR --new DIR [--plugin ID] [--seed FILE --seed-element NAME]
                    [--settings FILE] [--json | --markdown]

plugins  Lists installed Claude Code plugins from Claude Code's own registry. Latest versions
         come from the station's update-notice hook (plugin_update_check.py --report). For each
         plugin that is behind and comes from a GitHub marketplace, reads the marketplace's
         current catalog (raw.githubusercontent.com), takes the entry's pinned sha, or resolves
         its pinned ref or the repo head to a commit (api.github.com), and writes a
         web_download.py manifest for that commit's archive. Nothing is downloaded here.
unpack   Extracts a downloaded tar archive into a new, empty folder. Refuses absolute paths and
         `..` components, skips links and special files, drops execute bits, caps the size.
delta    Compares an installed folder with an incoming one, offline: files, hooks, MCP servers,
         network hosts, changelog lines, and, with a profile, settings defaults against the
         station seed and the live settings. Secret-looking values are never printed.

Exit 0 on success (findings are data), 2 on bad arguments or a refused input.

Environment overrides (tests):
  UPDATE_PLUGINS_HOME  Claude Code plugins folder (default ~/.claude/plugins)
  UPDATE_CHECKER       update-notice hook (default ~/.claude/hooks/plugin_update_check.py)
  UPDATE_GITHUB_API    GitHub API base (default https://api.github.com; loopback allowed for tests)
  UPDATE_RAW_BASE      raw content base (default https://raw.githubusercontent.com; loopback allowed)
Stdlib only, Python 3.9.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import lzma
import os
import re
import sys
import tarfile
import shutil
import tempfile
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zlib
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import procguard  # noqa: E402

AGENT = "update-skill"
HTTP_TIMEOUT = 15
CHECKER_TIMEOUT = 200
EXCLUDE_DIRS = {"node_modules", ".git"}
SCAN_LIMIT = 16 * 1024 * 1024
LIST_CAP = 200

# Values from marketplace files and package code are untrusted; each is checked before use.
VERSION = re.compile(r"^[0-9A-Za-z.+-]{1,40}$")
REPO = re.compile(r"^(?!\.\.?/)[A-Za-z0-9_.-]+/(?!\.\.?$)[A-Za-z0-9_.-]+$")
SHA = re.compile(r"^[0-9a-f]{40}$")
REF = re.compile(r"^(?!/)(?!.*\.\.)[A-Za-z0-9._/-]{1,100}$")
SEGMENT = re.compile(r"^(?!\.\.?$)[A-Za-z0-9._-]{1,100}$")
GITHUB_URL = re.compile(r"^https://github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?$")
URL_HOST = re.compile(r"https?://([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)")
BARE_HOST = re.compile(
    r"[\"'`]([a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|net|org|io|ai|dev|app|co|sh|cloud|run|so|xyz))[\"'`/:]")
SECRET_NAME = re.compile(r"TOKEN|SECRET|PASS|API_KEY|_KEY$|_KEYS$|CREDENTIAL|AUTH|BEARER|COOKIE|"
                         r"WEBHOOK|DSN|PRIVATE|DEVICE_ID|SESSION", re.I)
SECRET_SHAPE = re.compile(r"ghp_|gho_|ghs_|github_pat_|sk-|xox[abprs]-|AKIA|AIza|\d{6,}:AA|://[^/\s]*@|\?")
LONG_RUN = re.compile(r"[A-Za-z0-9_-]{20,}")
SAFE_VALUE = re.compile(r"^[A-Za-z0-9 .,:_/@+-]{0,80}$")
ON_VALUES = {"true", "1", "on", "yes"}
MAX_MEMBERS = 50000


# ---------------------------------------------------------------- shared helpers

def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def tilde(path) -> str:
    text, home = str(path), str(Path.home())
    return "~" + text[len(home):] if text == home or text.startswith(home + os.sep) else text


def private_dir(folder: Path) -> Path:
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    return folder


def shown(key: str, value):
    """A value safe to print. Masked when the key is secret-named, or the value looks like a
    credential, an identifier or anything unusual, whatever its key is called."""
    if value is None:
        return None
    text = str(value)
    if not text:
        return ""
    if SECRET_NAME.search(key) or SECRET_SHAPE.search(text) or not SAFE_VALUE.match(text):
        return "<set>"
    for run in LONG_RUN.findall(text):
        if re.search(r"[A-Za-z]", run) and re.search(r"[0-9]", run):
            return "<set>"
    if len(text) >= 24 and " " not in text and sum(c.isalnum() for c in text) >= 0.8 * len(text):
        return "<set>"  # a long opaque string, such as base64 split by / or +
    return text


def clean(text, cap: int = 300) -> str:
    """Untrusted text made safe to render: control and format characters (bidi, zero-width,
    tag plane) become visible escapes, backticks cannot close a code span, and length is capped."""
    out = []
    for ch in str(text):
        if ch == "\t":
            out.append(" ")
        elif unicodedata.category(ch) in ("Cc", "Cf", "Co", "Cs"):
            out.append(f"\\U{ord(ch):08x}" if ord(ch) > 0xFFFF else f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    result = "".join(out)
    return result if len(result) <= cap else result[:cap] + "..."


def inline(text, cap: int = 120) -> str:
    return clean(text, cap).replace("`", "'")


# ---------------------------------------------------------------- plugins

def plugins_home() -> Path:
    return Path(os.environ.get("UPDATE_PLUGINS_HOME") or Path.home() / ".claude" / "plugins")


def catalog_entry(catalog, name: str) -> dict:
    plugins = catalog.get("plugins") if isinstance(catalog, dict) else None
    return next((p for p in plugins or [] if isinstance(p, dict) and p.get("name") == name), {})


def subdir_of(path) -> str | None:
    """A repo-relative folder as './a/b', or None when any segment is unsafe."""
    if not isinstance(path, str):
        return None
    parts = [p for p in path.strip().split("/") if p not in ("", ".")]
    if len(parts) > 20 or not all(SEGMENT.match(p) for p in parts):
        return None
    return "./" + "/".join(parts)


def resolve_source(entry: dict, market_repo: str) -> dict:
    """Where a marketplace entry's code lives: repo, folder inside it, and any pinned sha or ref.
    Claude Code installs a pinned commit, so the inspection must use the same pin."""
    value = entry.get("source") if isinstance(entry, dict) else None
    out = {"repo": None, "subdir": None, "sha": None, "ref": None, "note": None}
    if isinstance(value, str):
        out.update(repo=market_repo, subdir=subdir_of(value))
    elif isinstance(value, dict):
        kind = value.get("source")
        if kind == "github":
            repo = value.get("repo")
            out.update(repo=repo if isinstance(repo, str) and REPO.match(repo) else None, subdir="./")
        elif kind in ("git-subdir", "url", "git"):
            match = GITHUB_URL.match(str(value.get("url") or ""))
            repo = match.group(1) if match and REPO.match(match.group(1)) else None
            out.update(repo=repo, subdir=subdir_of(value.get("path") or "./"))
            if not repo:
                out["note"] = "source is not a GitHub repository; fetch it by hand"
        else:
            out["note"] = f"source type {inline(kind, 40)!s} is not inspected"
        sha, ref = value.get("sha"), value.get("ref")
        if sha is not None:
            out["sha"] = sha if isinstance(sha, str) and SHA.match(sha) else "invalid"
        if ref is not None:
            out["ref"] = ref if isinstance(ref, str) and REF.match(ref) else "invalid"
    else:
        out["note"] = "plugin not found in its marketplace catalog"
    if out["repo"] and not out["subdir"]:
        out["note"], out["repo"] = "unsafe source path", None
    if "invalid" in (out["sha"], out["ref"]):
        out["note"], out["repo"] = "pinned sha or ref is malformed; not inspected", None
    return out


def inventory(home: Path) -> list[dict]:
    installed = (read_json(home / "installed_plugins.json") or {}).get("plugins") or {}
    markets = read_json(home / "known_marketplaces.json") or {}
    rows = []
    for plugin_id, installs in sorted(installed.items()):
        install = installs[0] if isinstance(installs, list) and installs else installs
        if not isinstance(install, dict):
            continue
        name, _, market = plugin_id.partition("@")
        market_info = markets.get(market) or {}
        src = market_info.get("source") or {}
        market_repo = src.get("repo") if src.get("source") == "github" else None
        market_repo = market_repo if isinstance(market_repo, str) and REPO.match(market_repo) else None
        source = {"repo": None, "subdir": None, "sha": None, "ref": None, "note": "marketplace not on GitHub"}
        location = market_info.get("installLocation")
        if market_repo and isinstance(location, str):
            catalog = read_json(Path(location) / ".claude-plugin" / "marketplace.json") or {}
            source = resolve_source(catalog_entry(catalog, name), market_repo)
        version = str(install.get("version") or "")
        commit = str(install.get("gitCommitSha") or "")
        rows.append({
            "plugin": plugin_id,
            "marketplace": market,
            "market_repo": market_repo,
            "repo": source["repo"],
            "source": source["subdir"],
            "installed": version if VERSION.match(version) else "unknown",
            "commit": commit if SHA.match(commit) else None,
            "path": tilde(install.get("installPath") or ""),
            "updated": str(install.get("lastUpdated") or install.get("installedAt") or "")[:10],
        })
    return rows


def latest_versions(checker: Path) -> dict:
    """Run the update-notice hook's foreground report into a private folder and read it."""
    if not checker.is_file():
        return {"status": f"update-notice hook not found at {tilde(checker)}; latest versions not checked"}
    state = Path(tempfile.mkdtemp(prefix="update-plugins-"))
    env = dict(os.environ, PLUGIN_UPDATE_STATE=str(state))
    try:
        procguard.run([sys.executable, "-I", str(checker), "--report"], timeout=CHECKER_TIMEOUT,
                      capture_output=True, text=True, env=env)
        report = read_json(state / "report.json")
    except Exception as exc:  # the hook fails open; a crash or timeout here is reported, not raised
        return {"status": f"update-notice hook failed: {type(exc).__name__}"}
    finally:
        shutil.rmtree(state, ignore_errors=True)
    if not isinstance(report, dict):
        return {"status": "update-notice hook wrote no report"}
    outdated = {}
    for item in report.get("outdated") or []:
        if isinstance(item, dict) and isinstance(item.get("plugin"), str):
            latest = str(item.get("latest") or "")
            outdated[item["plugin"]] = latest if len(latest) <= 60 else latest[:60]
    return {"status": "ok", "outdated": outdated,
            "not_checked": [str(x) for x in report.get("not_checked") or []],
            "errors": [str(x)[:120] for x in report.get("errors") or []]}


LOOPBACK = re.compile(r"^http://(127\.0\.0\.1|localhost)(:\d+)?$")


def base_url(env: str, default: str) -> str:
    """The only hosts this script calls; a test may point either at loopback."""
    base = (os.environ.get(env) or default).rstrip("/")
    if base != default and not LOOPBACK.match(base):
        raise ValueError(f"refusing {env} {base}")
    return base


def github_api() -> str:
    return base_url("UPDATE_GITHUB_API", "https://api.github.com")


def fetch(url: str, accept: str, limit: int) -> bytes | None:
    req = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept": accept})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            return resp.read(limit)
    except (OSError, urllib.error.URLError, ValueError):
        return None


def commit_of(repo: str, ref: str = "HEAD") -> str | None:
    quoted = urllib.parse.quote(ref, safe="/")
    data = fetch(f"{github_api()}/repos/{repo}/commits/{quoted}", "application/vnd.github.sha", 200)
    text = (data or b"").decode("ascii", "replace").strip()
    return text if SHA.match(text) else None


def remote_catalog(market_repo: str):
    raw = base_url("UPDATE_RAW_BASE", "https://raw.githubusercontent.com")
    data = fetch(f"{raw}/{market_repo}/HEAD/.claude-plugin/marketplace.json", "application/json",
                 4 * 1024 * 1024)
    try:
        return json.loads(data) if data else None
    except ValueError:
        return None


def incoming(row: dict) -> tuple[dict, str | None]:
    """The source and commit Claude Code would install now, read from the marketplace's current
    catalog: a pinned sha as given, a pinned ref resolved, otherwise the source repo's head."""
    catalog = remote_catalog(row["market_repo"])
    if catalog is None:
        return {"note": "marketplace catalog could not be read"}, None
    source = resolve_source(catalog_entry(catalog, row["plugin"].partition("@")[0]), row["market_repo"])
    if not source["repo"]:
        return source, None
    if source["sha"]:
        return source, source["sha"]
    return source, commit_of(source["repo"], source["ref"] or "HEAD")


def cmd_plugins(args) -> int:
    rows = inventory(plugins_home())
    checker = Path(os.environ.get("UPDATE_CHECKER") or Path.home() / ".claude" / "hooks" / "plugin_update_check.py")
    latest = latest_versions(checker)
    outdated = latest.get("outdated") or {}
    manifest = []
    not_checked = set(latest.get("not_checked") or [])
    for row in rows:
        if row["plugin"] in outdated:
            row["latest"] = outdated[row["plugin"]]
        elif latest["status"] != "ok":
            row["latest"] = "unknown"
        else:
            row["latest"] = "not checked" if row["plugin"] in not_checked else "current"
        row["incoming_commit"] = None
        if row["plugin"] not in outdated:
            continue
        if not row["market_repo"]:
            row["note"] = "not a GitHub marketplace; fetch the incoming version by hand"
            continue
        if args.no_network:
            row["note"] = "incoming commit not resolved (--no-network)"
            continue
        source, sha = incoming(row)
        if not sha:
            row["note"] = source.get("note") or "incoming commit could not be read"
            continue
        row.update(repo=source["repo"], source=source["subdir"], incoming_commit=sha,
                   pinned=bool(source["sha"] or source["ref"]))
        name = re.sub(r"[^A-Za-z0-9._-]", "-", row["plugin"])
        manifest.append({"url": f"https://codeload.github.com/{row['repo']}/tar.gz/{sha}",
                         "name": f"{name}-{sha[:12]}.tar.gz",
                         "why": f"/update plugins: {row['plugin']} {row['installed']} -> {row['latest']}"})
    result = {"status": latest["status"], "plugins": rows,
              "not_checked": latest.get("not_checked", []), "errors": latest.get("errors", [])}
    if manifest:
        out = private_dir(Path(args.out) if args.out else Path(tempfile.mkdtemp(prefix="update-plugins-out-")))
        path = out / "download-manifest.jsonl"
        path.write_bytes("".join(json.dumps(m) + "\n" for m in manifest).encode("utf-8"))
        result["manifest"] = tilde(path)
    if args.json:
        print(json.dumps(result, indent=1))
        return 0
    if latest["status"] != "ok":
        print(f"note: {latest['status']}")
    for row in rows:
        line = f"{row['plugin']}: {row['installed']} -> {row['latest']}"
        if row.get("incoming_commit"):
            line += f" (incoming commit {row['incoming_commit'][:12]}, source {row['source'] or '?'})"
        if row.get("note"):
            line += f" - {row['note']}"
        print(line)
    for key in ("not_checked", "errors"):
        if result[key]:
            print(f"{key.replace('_', ' ')}: {', '.join(result[key])}")
    if manifest:
        print(f"download manifest: {result['manifest']}")
    return 0


# ---------------------------------------------------------------- unpack

class Refused(Exception):
    pass


def extract_member(tar, member, root: Path, state: dict, max_bytes: int, max_members: int) -> None:
    state["count"] += 1
    if state["count"] > max_members:
        raise Refused(f"archive has more than {max_members} entries")
    parts = [p for p in Path(member.name).parts if p != "."]
    if member.name.startswith(("/", "\\")) or ".." in parts:
        raise Refused(f"unsafe path in archive: {inline(member.name)}")
    if not parts:
        return  # the archive's own top entry, "."
    if not (member.isfile() or member.isdir()):
        state["skipped"].append(clean(member.name, 200))
        return
    target = root.joinpath(*parts).resolve()
    if root not in target.parents:
        raise Refused(f"path leaves the destination: {inline(member.name)}")
    state["tops"].add(parts[0])
    if member.isdir():
        target.mkdir(mode=0o700, parents=True, exist_ok=True)
        return
    state["total"] += member.size
    if state["total"] > max_bytes:
        raise Refused(f"archive is larger than {max_bytes // (1024 * 1024)} MB")
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    data = tar.extractfile(member)
    with open(target, "xb") as handle:  # exclusive: a repeated name is refused, never overwritten
        shutil.copyfileobj(data, handle, 1024 * 1024)
    os.chmod(target, 0o600)
    state["files"] += 1


def unpack(archive: Path, dest: Path, max_bytes: int, max_members: int = MAX_MEMBERS) -> dict:
    if dest.exists() and (not dest.is_dir() or any(dest.iterdir())):
        raise Refused(f"destination is not a new, empty folder: {tilde(dest)}")
    private_dir(dest)
    root = dest.resolve()
    state = {"files": 0, "total": 0, "count": 0, "skipped": [], "tops": set()}
    try:
        with tarfile.open(archive, "r:*") as tar:
            for member in tar:
                extract_member(tar, member, root, state, max_bytes, max_members)
    except Refused:
        raise
    except (OSError, tarfile.TarError, EOFError, zlib.error, lzma.LZMAError) as exc:
        raise Refused(f"archive could not be unpacked safely: {type(exc).__name__}")
    files, total, skipped, tops = state["files"], state["total"], state["skipped"], state["tops"]
    top = next(iter(tops)) if len(tops) == 1 else None
    return {"dest": tilde(dest), "root": tilde(dest / top) if top else tilde(dest),
            "files": files, "bytes": total, "skipped": skipped[:LIST_CAP]}


def cmd_unpack(args) -> int:
    try:
        result = unpack(Path(args.archive), Path(args.dest), args.max_mb * 1024 * 1024)
    except Refused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=1))
    return 0


# ---------------------------------------------------------------- delta

def walk(root: Path) -> dict[str, Path]:
    found = {}
    for folder, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDE_DIRS)
        for name in names:
            path = Path(folder) / name
            if path.is_file() and not path.is_symlink():
                found[path.relative_to(root).as_posix()] = path
    return found


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def text_of(path: Path) -> str | None:
    try:
        if path.stat().st_size > SCAN_LIMIT:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    if b"\0" in data[:8192]:
        return None
    return data.decode("utf-8", "replace")


def hook_set(root: Path) -> set[str]:
    found = set()
    for doc in (read_json(root / "hooks" / "hooks.json"), (read_json(root / ".claude-plugin" / "plugin.json") or {})):
        hooks = (doc or {}).get("hooks") if isinstance(doc, dict) else None
        if not isinstance(hooks, dict):
            continue
        for event, groups in hooks.items():
            for group in groups if isinstance(groups, list) else []:
                if not isinstance(group, dict):
                    continue
                matcher = str(group.get("matcher") or "*")
                for hook in group.get("hooks") or []:
                    if isinstance(hook, dict):
                        what = str(hook.get("command") or hook.get("url") or hook.get("type") or "")
                        found.add(f"{event} [{matcher[:120]}] {' '.join(what.split())[:160]}")
    return found


def mcp_map(root: Path) -> dict[str, str]:
    servers = {}
    for doc in (read_json(root / ".mcp.json"), read_json(root / ".claude-plugin" / "plugin.json")):
        if not isinstance(doc, dict):
            continue
        block = doc.get("mcpServers") if isinstance(doc.get("mcpServers"), dict) else (
            doc if doc and all(isinstance(v, dict) and ("command" in v or "url" in v) for v in doc.values()) else {})
        for name, spec in block.items():
            servers[str(name)] = json.dumps(spec, sort_keys=True)[:300]
    return servers


def manifest_of(root: Path) -> dict[str, str]:
    """Top-level plugin.json keys with a short summary of each value."""
    doc = read_json(root / ".claude-plugin" / "plugin.json") or read_json(root / "plugin.json") or {}
    if not isinstance(doc, dict):
        return {}
    return {str(k): json.dumps(v, sort_keys=True)[:200] for k, v in doc.items()}


def hosts_in(texts: dict[str, str]) -> set[str]:
    found = set()
    for text in texts.values():
        found.update(h.lower().rstrip(".") for h in URL_HOST.findall(text))
        found.update(h.lower() for h in BARE_HOST.findall(text))
    return found


def changelog_added(old: Path, new: Path) -> list[str]:
    def find(root: Path):
        for name in ("CHANGELOG.md", "changelog.md", "CHANGES.md", "HISTORY.md"):
            if (root / name).is_file():
                return root / name
        return None
    new_file = find(new)
    if not new_file:
        return []
    old_file = find(old)
    before = (text_of(old_file) or "").splitlines() if old_file else []
    after = (text_of(new_file) or "").splitlines()
    added = [line[1:] for line in difflib.unified_diff(before, after, lineterm="", n=0)
             if line.startswith("+") and not line.startswith("+++")]
    return added[:300]


def defaults_in(root: Path, profile: dict) -> dict[str, str]:
    pattern = re.compile(
        r"(?<![A-Za-z0-9_\"'.])(" + profile["key_pattern"] + r")\s*:\s*"
        r"(\"(?:[^\"\\\n]|\\.){0,400}\"|'(?:[^'\\\n]|\\.){0,400}'|-?\d+(?:\.\d+)?\b|true\b|false\b|!0|!1)")
    votes: dict[str, Counter] = {}
    for rel, path in walk(root).items():
        if not any(Path(rel).match(glob) for glob in profile.get("defaults_glob", ["*"])):
            continue
        text = text_of(path)
        if not text:
            continue
        for key, raw in pattern.findall(text):
            value = {"!0": "true", "!1": "false"}.get(raw, raw)
            if value[:1] in "\"'":
                value = value[1:-1]
            votes.setdefault(key, Counter())[value] += 1
    return {key: counter.most_common(1)[0][0] for key, counter in sorted(votes.items())}


def seed_keys(seed: Path, element: str) -> dict:
    doc = read_json(seed) or {}
    for row in doc.get("rows") or []:
        if isinstance(row, dict) and row.get("element") == element and isinstance(row.get("keys"), dict):
            return {str(k): v for k, v in row["keys"].items()}
    raise Refused(f"no seed row named {element!r} with keys in {tilde(seed)}")


def settings_compare(old: dict, new: dict, seed: dict | None, live: dict | None) -> dict:
    def extra(key: str) -> dict:
        out = {}
        if seed is not None:
            out["seed"] = shown(key, seed.get(key)) if key in seed else None
        if live is not None:
            out["live"] = shown(key, live.get(key)) if key in live else None
        return out

    result = {
        "new_keys": [dict(key=k, default=shown(k, v), default_on=str(v).lower() in ON_VALUES, **extra(k))
                     for k, v in new.items() if k not in old],
        "changed_defaults": [dict(key=k, old=shown(k, old[k]), new=shown(k, v), **extra(k))
                             for k, v in new.items() if k in old and old[k] != v],
        "removed_keys": [dict(key=k, **extra(k)) for k in old if k not in new],
    }
    if seed is not None:
        result["seed_keys_unknown_to_new"] = sorted(k for k in seed if k not in new)
        result["default_on_not_in_seed"] = sorted(
            k for k, v in new.items() if str(v).lower() in ON_VALUES and k not in seed)
    return result


def load_profile(plugin: str | None, name: str | None) -> dict | None:
    profiles = read_json(HERE.parent / "references" / "profiles.json") or {}
    key = name or plugin
    if not key:
        return None
    profile = (profiles.get("profiles") or {}).get(key)
    if profile is None and name:
        raise Refused(f"no profile named {name!r}")
    return profile


def delta(old: Path, new: Path, profile: dict | None, seed: dict | None, live: dict | None) -> dict:
    old_files, new_files = walk(old), walk(new)
    changed = sorted(r for r in set(old_files) & set(new_files) if digest(old_files[r]) != digest(new_files[r]))
    old_hooks, new_hooks = hook_set(old), hook_set(new)
    old_mcp, new_mcp = mcp_map(old), mcp_map(new)
    old_man, new_man = manifest_of(old), manifest_of(new)
    old_text = {r: t for r, p in old_files.items() if (t := text_of(p)) is not None}
    new_text = {r: t for r, p in new_files.items() if (t := text_of(p)) is not None}
    report = {
        "old": tilde(old), "new": tilde(new),
        "files": {"added": sorted(set(new_files) - set(old_files))[:LIST_CAP],
                  "removed": sorted(set(old_files) - set(new_files))[:LIST_CAP],
                  "changed": changed[:LIST_CAP],
                  "counts": {"added": len(set(new_files) - set(old_files)),
                             "removed": len(set(old_files) - set(new_files)), "changed": len(changed)}},
        "manifest": {"added": {k: new_man[k] for k in sorted(set(new_man) - set(old_man))},
                     "removed": sorted(set(old_man) - set(new_man)),
                     "changed": {k: [old_man[k], new_man[k]] for k in sorted(set(old_man) & set(new_man))
                                 if old_man[k] != new_man[k]}},
        "hooks": {"added": sorted(new_hooks - old_hooks), "removed": sorted(old_hooks - new_hooks)},
        "mcp_servers": {"added": sorted(set(new_mcp) - set(old_mcp)),
                        "removed": sorted(set(old_mcp) - set(new_mcp)),
                        "changed": sorted(k for k in set(old_mcp) & set(new_mcp) if old_mcp[k] != new_mcp[k])},
        "new_hosts": sorted(hosts_in(new_text) - hosts_in(old_text))[:LIST_CAP],
        "changelog_added": changelog_added(old, new),
    }
    if profile:
        report["settings"] = settings_compare(defaults_in(old, profile), defaults_in(new, profile), seed, live)
    return report


def markdown(report: dict) -> str:
    """Every string that came from a package goes through inline() or clean() here."""
    def code(value, cap: int = 120) -> str:
        return f"`{inline(value, cap)}`"

    def where(item: dict) -> str:
        return f"seed {code(item.get('seed'))}, live {code(item.get('live'))}"

    out = [f"## Delta: {inline(report['old'], 300)} -> {inline(report['new'], 300)}", ""]
    c = report["files"]["counts"]
    out.append(f"Files: {c['added']} added, {c['removed']} removed, {c['changed']} changed.")
    man = report["manifest"]
    if man["added"] or man["removed"] or man["changed"]:
        out += ["", "### Plugin manifest"]
        out += [f"- added {code(k)} = {code(v, 200)}" for k, v in man["added"].items()]
        out += [f"- removed {code(k)}" for k in man["removed"]]
        out += [f"- changed {code(k)}: {code(a, 200)} -> {code(b, 200)}" for k, (a, b) in man["changed"].items()]
    for title, key in (("Hooks added", ("hooks", "added")), ("Hooks removed", ("hooks", "removed")),
                       ("MCP servers added", ("mcp_servers", "added")),
                       ("MCP servers removed", ("mcp_servers", "removed")),
                       ("MCP servers changed", ("mcp_servers", "changed"))):
        items = report[key[0]][key[1]]
        if items:
            out += ["", f"### {title}", *[f"- {code(i, 300)}" for i in items]]
    if report["new_hosts"]:
        out += ["", "### Hosts named only in the incoming code", *[f"- {code(h)}" for h in report["new_hosts"]]]
    settings = report.get("settings")
    if settings:
        out += ["", "### Settings"]
        for item in settings["new_keys"]:
            flag = " (default on)" if item["default_on"] else ""
            out.append(f"- new {code(item['key'])} = {code(item['default'])}{flag}; {where(item)}")
        for item in settings["changed_defaults"]:
            out.append(f"- changed {code(item['key'])}: {code(item['old'])} -> {code(item['new'])}; {where(item)}")
        for item in settings["removed_keys"]:
            out.append(f"- removed {code(item['key'])}; {where(item)}")
        if settings.get("seed_keys_unknown_to_new"):
            out.append("- seed keys the incoming version does not define: "
                       + ", ".join(code(k) for k in settings["seed_keys_unknown_to_new"]))
        if settings.get("default_on_not_in_seed"):
            out.append("- default-on keys the seed does not pin: "
                       + ", ".join(code(k) for k in settings["default_on_not_in_seed"]))
    if report["changelog_added"]:
        lines = [clean(line, 300) for line in report["changelog_added"][:120]]
        longest = max((len(run) for line in lines for run in re.findall(r"`+", line)), default=0)
        fence = "`" * max(3, longest + 1)
        out += ["", "### Changelog lines added (untrusted text)", "", f"{fence}text", *lines, fence]
    return "\n".join(out) + "\n"


def cmd_delta(args) -> int:
    old, new = Path(args.old), Path(args.new)
    if not old.is_dir() or not new.is_dir():
        print("refused: --old and --new must be folders", file=sys.stderr)
        return 2
    try:
        profile = load_profile(args.plugin, args.profile)
        seed = seed_keys(Path(args.seed), args.seed_element) if args.seed else None
    except Refused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    live = None
    settings = args.settings or (profile or {}).get("settings")
    if settings:
        doc = read_json(Path(os.path.expanduser(settings)))
        live = doc if isinstance(doc, dict) else None
    report = delta(old, new, profile, seed, live)
    print(markdown(report) if args.markdown else json.dumps(report, indent=1))
    return 0


# ---------------------------------------------------------------- main

def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="update.py", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plugins", help="installed plugins, latest versions, download manifest")
    p.add_argument("--json", action="store_true")
    p.add_argument("--out", help="folder for the download manifest (default: a new temp folder)")
    p.add_argument("--no-network", action="store_true", help="skip resolving incoming commits")
    p.set_defaults(func=cmd_plugins)
    u = sub.add_parser("unpack", help="extract a downloaded archive safely")
    u.add_argument("archive")
    u.add_argument("--dest", required=True)
    u.add_argument("--max-mb", type=int, default=500)
    u.set_defaults(func=cmd_unpack)
    d = sub.add_parser("delta", help="compare an installed folder with an incoming one")
    d.add_argument("--old", required=True)
    d.add_argument("--new", required=True)
    d.add_argument("--plugin", help="plugin id, used to pick its profile")
    d.add_argument("--profile", help="profile name in references/profiles.json")
    d.add_argument("--seed", help="station seed.json")
    d.add_argument("--seed-element", help="seed row whose keys hold this component's settings")
    d.add_argument("--settings", help="live settings file (default: the profile's)")
    fmt = d.add_mutually_exclusive_group()
    fmt.add_argument("--json", action="store_true")
    fmt.add_argument("--markdown", action="store_true")
    d.set_defaults(func=cmd_delta)
    args = parser.parse_args(argv)
    if getattr(args, "seed", None) and not args.seed_element:
        parser.error("--seed needs --seed-element")
    procguard.install_signal_handlers()
    return args.func(args)


if __name__ == "__main__":
    if sys.platform == "win32":  # the console code page is not UTF-8; changelog text often is
        for _stream in (sys.stdout, sys.stderr):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv[1:]))
