#!/usr/bin/env python3
"""SessionStart hook: tell the user, at most once a day, which installed plugins are behind upstream.

It never installs or updates anything. Updating stays the user's call, after a review.

Hook mode (SessionStart, startup):
  - When the last report lists outdated plugins and has not been shown today, print it to the
    user as a systemMessage.
  - When no check has started today, start this script with --refresh under procguard's
    --detached mode (capped at REFRESH_TIMEOUT) and return at once. Its findings appear at the
    next session start.

Refresh mode (--refresh) reads Claude Code's own plugin registry (installed_plugins.json and
known_marketplaces.json under ~/.claude/plugins). For each installed plugin whose marketplace
is a GitHub repository, it fetches that marketplace's current .claude-plugin/marketplace.json:
  - when the entry declares a version that differs from the installed one, the plugin is
    behind by version;
  - when the entry declares no version and its source is a folder of the marketplace repo,
    the newest commit touching that folder is compared with the plugin's install time.
Marketplaces from other sources are listed as not checked. The report is written to
<temp>/plugin-update-check-<uid>/report.json. Network: raw.githubusercontent.com and
api.github.com, unauthenticated, once a day.

--report runs a refresh in the foreground and prints the result as plain text.
Fails open: exit 0 on every path.

Environment overrides (tests):
  PLUGIN_UPDATE_HOME   Claude Code plugins dir (default ~/.claude/plugins)
  PLUGIN_UPDATE_STATE  state dir (default <temp>/plugin-update-check-<uid>)
  PLUGIN_UPDATE_RAW    raw content base URL (default https://raw.githubusercontent.com)
  PLUGIN_UPDATE_API    API base URL (default https://api.github.com)
  PLUGIN_UPDATE_TODAY  today's date as YYYY-MM-DD
"""
from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

REFRESH_TIMEOUT = 180
HTTP_TIMEOUT = 15
AGENT = "plugin-update-check"
# The marketplace file is untrusted, and its version string reaches the user's screen.
VERSION = re.compile(r"^[0-9A-Za-z.+-]{1,40}$")
REPO = re.compile(r"^(?!\.\.?/)[A-Za-z0-9_.-]+/(?!\.\.?$)[A-Za-z0-9_.-]+$")  # no . or .. segment


def today() -> str:
    return os.environ.get("PLUGIN_UPDATE_TODAY") or date.today().isoformat()


def plugins_dir() -> Path:
    return Path(os.environ.get("PLUGIN_UPDATE_HOME") or Path.home() / ".claude" / "plugins")


def state_dir() -> Path:
    return Path(os.environ.get("PLUGIN_UPDATE_STATE")
                or Path(tempfile.gettempdir()) / f"plugin-update-check-{os.getuid()}")


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def private_dir(folder: Path) -> None:
    """Create the state folder owner-only, and refuse one that is a symlink or someone else's
    (a shared /tmp on Linux would otherwise let another user plant the report)."""
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = os.lstat(folder)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise OSError(f"state folder is not a private directory: {folder}")


def write_text(path: Path, text: str) -> None:
    private_dir(path.parent)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def fetch_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return json.loads(resp.read(4 * 1024 * 1024))


def parse_time(value: str):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def folder_of(entry: dict, catalog: dict):
    """The repo-relative folder of a plugin that lives inside its marketplace repo, else None."""
    source = entry.get("source")
    if not isinstance(source, str) or not source.startswith("./"):
        return None
    root = ((catalog.get("metadata") or {}).get("pluginRoot") or "").strip("./")
    path = source[2:].strip("/")
    return f"{root}/{path}".strip("/") if root and not path.startswith(root) else path


def check() -> dict:
    raw_base = os.environ.get("PLUGIN_UPDATE_RAW", "https://raw.githubusercontent.com").rstrip("/")
    api_base = os.environ.get("PLUGIN_UPDATE_API", "https://api.github.com").rstrip("/")
    installed = (read_json(plugins_dir() / "installed_plugins.json") or {}).get("plugins") or {}
    markets = read_json(plugins_dir() / "known_marketplaces.json") or {}
    report = {"date": today(), "checked": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "outdated": [], "not_checked": [], "errors": []}
    catalogs: dict = {}
    for plugin_id, installs in sorted(installed.items()):
        name, _, market = plugin_id.partition("@")
        install = installs[0] if isinstance(installs, list) and installs else installs
        if not isinstance(install, dict):
            continue
        source = (markets.get(market) or {}).get("source") or {}
        repo = source.get("repo") if source.get("source") == "github" else None
        if not isinstance(repo, str) or not REPO.match(repo):
            report["not_checked"].append(plugin_id)
            continue
        try:
            if repo not in catalogs:
                catalogs[repo] = fetch_json(f"{raw_base}/{repo}/HEAD/.claude-plugin/marketplace.json")
            catalog = catalogs[repo]
            entry = next((p for p in catalog.get("plugins", []) if p.get("name") == name), None)
            if entry is None:
                report["not_checked"].append(plugin_id)
                continue
            have, latest = str(install.get("version") or ""), entry.get("version")
            if latest:
                if not VERSION.match(str(latest)):
                    report["errors"].append(f"{plugin_id}: bad version")
                elif str(latest) != have:
                    report["outdated"].append({"plugin": plugin_id, "installed": have, "latest": str(latest)})
                continue
            folder = folder_of(entry, catalog)
            if not folder:
                report["not_checked"].append(plugin_id)
                continue
            query = urllib.parse.urlencode({"path": folder, "per_page": 1})
            commits = fetch_json(f"{api_base}/repos/{repo}/commits?{query}")
            changed = parse_time(((commits or [{}])[0].get("commit") or {}).get("committer", {}).get("date", ""))
            since = parse_time(install.get("lastUpdated") or install.get("installedAt") or "")
            if changed and since and changed > since:
                report["outdated"].append({"plugin": plugin_id, "installed": have,
                                           "latest": f"changed upstream {changed.date().isoformat()}"})
        except (OSError, ValueError, urllib.error.URLError, AttributeError, IndexError, KeyError,
                TypeError) as exc:
            report["errors"].append(f"{plugin_id}: {type(exc).__name__}")
    return report


def summary(report: dict) -> str:
    items = "; ".join(f"{o['plugin']} {o['installed']} -> {o['latest']}" for o in report.get("outdated", []))
    return (f"Plugin updates available (checked {report.get('date')}): {items}. "
            "Run /update plugins to inspect the changes and plan the cutover before "
            "`claude plugin update <plugin>`.")


def refresh() -> int:
    report = check()
    write_text(state_dir() / "report.json", json.dumps(report, indent=1))
    return 0


def hook() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(payload, dict) or payload.get("hook_event_name") != "SessionStart":
        return 0
    if payload.get("source", "startup") != "startup":
        return 0
    state = state_dir()
    private_dir(state)          # a planted or foreign folder raises here, and main() stays silent
    report = read_json(state / "report.json")
    shown = state / "shown"
    message = None
    if isinstance(report, dict) and report.get("outdated") and \
            (shown.read_text().strip() if shown.exists() else "") != today():
        message = summary(report)
        write_text(shown, today())
    started = state / "started"
    if (started.read_text().strip() if started.exists() else "") != today():
        write_text(started, today())
        guard = Path(__file__).with_name("procguard.py")
        if guard.exists():
            argv = [sys.executable, "-I", str(guard), "--detached", "--timeout", str(REFRESH_TIMEOUT),
                    "--", sys.executable, "-I", str(Path(__file__).resolve()), "--refresh"]
            # procguard: exempt - the watchdog itself is started here; it leads its own group and caps the check
            subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
    if message:
        print(json.dumps({"systemMessage": message}))
    return 0


def main(argv: list[str]) -> int:
    try:
        if argv[:1] == ["--refresh"]:
            return refresh()
        if argv[:1] == ["--report"]:
            report = check()
            write_text(state_dir() / "report.json", json.dumps(report, indent=1))
            print(summary(report) if report["outdated"] else "plugins: all current")
            for key in ("not_checked", "errors"):
                if report[key]:
                    print(f"{key.replace('_', ' ')}: {', '.join(report[key])}")
            return 0
        return hook()
    except Exception:  # fail open: an update notice must never block a session
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
