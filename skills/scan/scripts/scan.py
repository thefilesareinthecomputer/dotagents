#!/usr/bin/env python3
"""scan.py - report-only malware and trust check of one file or folder on macOS.

Scan (the default), two lanes over the path given:
  clamav  `freshclam` first when the signatures are over a day old (the one network
          download; --no-update skips it), then `clamscan -r`. It never passes
          --remove, --move or --copy, so nothing scanned is changed on disk.
  apple   every .app bundle, .dmg, .pkg/.mpkg and bare Mach-O program found: the
          Gatekeeper verdict (`spctl --assess`), the signature and who signed it
          (`codesign`, or `pkgutil --check-signature` for installers), the quarantine
          tag, the download origin (`mdls kMDItemWhereFroms`) and a SHA-256 to compare
          against the vendor's download. Apple's XProtect rules are reported by age;
          updating them needs root, so the scan never does it.

Sweep (--sweep, a folder): a triage listing, no scanning. Files changed since --since
with no quarantine tag (made on this Mac, not downloaded by a browser), agent
instruction and auto-run files, and runnable files counted per top-level folder.

Usage: scan.py <path> [--json] [--no-update] | scan.py <folder> --sweep [--since YYYY-MM-DD] [--json]
Exit: 0 clean, 1 a finding, 2 bad path or arguments, 3 something to review and no
finding, 4 a tool missing or failed. Stdlib only; runs on the stock macOS python3.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys

UPDATE_HOURS = 24        # freshclam runs before a scan when the signatures are older than this
STALE_HOURS = 48         # still older than this after the update: the report warns
XPROTECT_STALE_DAYS = 30
BUNDLE_SUFFIXES = (".app", ".dmg", ".pkg", ".mpkg")
MAX_APPLE_ITEMS = 100
FORBIDDEN_CLAM_FLAGS = ("--remove", "--move", "--copy")
MACHO_MAGIC = {b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf", b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe"}
APPLE_AUTHORITIES = ("Software Signing", "Apple Mac OS Application Signing", "Apple iPhone OS Application Signing")
INSTRUCTION_NAMES = {"AGENTS.md", "CLAUDE.md", "GEMINI.md", ".cursorrules", ".mcp.json", ".envrc",
                     ".claude", ".codex", ".cursor", ".vscode"}
RUNNABLE_SUFFIXES = (".command", ".sh", ".py", ".scpt", ".workflow", ".terminal", ".plist", ".dylib")
SWEEP_LIST_CAP = 50


def run(argv: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)


# ---- ClamAV lane -------------------------------------------------------------------

def signature_age_hours(version_line: str, now: dt.datetime | None = None) -> float | None:
    """`ClamAV 1.5.2/28167/Wed Oct 28 01:24:17 2026` -> hours since the signature build."""
    parts = version_line.strip().split("/")
    if len(parts) < 3:
        return None
    try:
        built = dt.datetime.strptime(parts[2].strip(), "%a %b %d %H:%M:%S %Y")
    except ValueError:
        return None
    return ((now or dt.datetime.now()) - built).total_seconds() / 3600


def clam_argv(path: str) -> list[str]:
    argv = ["clamscan", "-r", "-i", "--stdout", path]
    assert not set(argv) & set(FORBIDDEN_CLAM_FLAGS)
    return argv


def refresh_signatures(lane: dict) -> None:
    """Run freshclam when the signatures are older than UPDATE_HOURS. A failed update is a
    warning, and the scan goes on with what is installed."""
    age = signature_age_hours(run(["clamscan", "--version"], timeout=60).stdout)
    if age is not None and age <= UPDATE_HOURS:
        return
    if not shutil.which("freshclam"):
        lane["warnings"].append("freshclam is not installed, so the signatures cannot be updated")
        return
    proc = run(["freshclam", "--stdout"], timeout=900)
    text = proc.stdout + proc.stderr
    lane["update"] = {"ran": True, "exit": proc.returncode}
    if proc.returncode not in (0, 1):   # 1 means the database was already current
        last = [l for l in text.splitlines() if l.strip()]
        lane["warnings"].append("signature update failed: " + (last[-1].strip() if last else f"exit {proc.returncode}"))
    if "OUTDATED" in text:
        lane["warnings"].append("the ClamAV engine itself is outdated; upgrade with: brew upgrade clamav")


def clamav_config_dir() -> str:
    """Where freshclam reads freshclam.conf: clamconf says, else Homebrew's etc/clamav."""
    if shutil.which("clamconf"):
        m = re.search(r"Checking configuration files in (\S+)", run(["clamconf"], timeout=60).stdout)
        if m:
            return m.group(1)
    prefix = run(["brew", "--prefix"], timeout=60).stdout.strip() if shutil.which("brew") else ""
    return os.path.join(prefix or "/opt/homebrew", "etc", "clamav")


def clamav_setup_steps() -> list[str]:
    """The commands that stand between this machine and a working ClamAV; empty when ready.
    Missing signatures are not a step: the scan's own update downloads them."""
    installed = bool(shutil.which("clamscan") and shutil.which("freshclam"))
    conf_dir = clamav_config_dir()
    conf = os.path.join(conf_dir, "freshclam.conf")
    steps = [] if installed else ["brew install clamav"]
    if not os.path.isfile(conf):
        steps.append(f'cp "{conf}.sample" "{conf}"')
        steps.append(f"sed -i '' 's/^Example/#Example/' \"{conf}\"")
    else:
        with open(conf, encoding="utf-8", errors="replace") as f:
            if any(line.strip() == "Example" for line in f):
                steps.append(f"sed -i '' 's/^Example/#Example/' \"{conf}\"")
    if steps:
        steps.append("freshclam    # the first signature download, roughly 200 MB")
    return steps


def clamav_lane(path: str, update: bool = True) -> dict:
    steps = clamav_setup_steps()
    if steps:
        return {"status": "setup-needed", "setup": steps,
                "note": "ClamAV is not set up yet; run these in order, then scan again"}
    lane: dict = {"status": "ok", "found": [], "warnings": [], "update": {"ran": False}}
    if update:
        refresh_signatures(lane)
    version = run(["clamscan", "--version"], timeout=60).stdout.strip()
    lane["version"] = version
    age = signature_age_hours(version)
    lane["signature_age_hours"] = None if age is None else round(age, 1)
    if "/" not in version:   # `ClamAV 1.5.2` with no database version: nothing to scan with
        lane["status"] = "error"
        lane["note"] = "no signatures are installed; run freshclam and read its output for the cause"
        return lane
    if age is None:
        lane["warnings"].append("signature date unreadable; run freshclam if unsure")
    elif age > STALE_HOURS:
        lane["warnings"].append(f"signatures are {age / 24:.1f} days old"
                                + ("" if update else "; update with: freshclam"))
    proc = run(clam_argv(path))
    for line in proc.stdout.splitlines():
        if line.endswith(" FOUND"):
            file_part, _, sig = line[: -len(" FOUND")].rpartition(": ")
            lane["found"].append({"file": file_part, "signature": sig})
        m = re.match(r"(Scanned files|Infected files|Data scanned): (.+)", line)
        if m:
            lane[m.group(1).lower().replace(" ", "_")] = m.group(2)
    if proc.returncode == 1 and not lane["found"]:   # infected, but no line parsed: never read as clean
        lane["found"].append({"file": path, "signature": "unparsed: clamscan reported an infection"})
    if proc.returncode not in (0, 1):
        lane["status"] = "error"
        errs = [l for l in proc.stderr.splitlines() if l.strip()]
        lane["note"] = errs[-1] if errs else f"clamscan exited {proc.returncode}"
    return lane


# ---- Apple lane --------------------------------------------------------------------

def is_macho(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            head = f.read(8)
    except OSError:
        return False
    if head[:4] in MACHO_MAGIC:
        return True
    # a universal binary; Java class files share the magic but hold a version of 45+ here
    return head[:4] == b"\xca\xfe\xba\xbe" and len(head) == 8 and int.from_bytes(head[4:], "big") < 45


def is_program(path: str) -> bool:
    return (os.path.isfile(path) and not os.path.islink(path)
            and os.stat(path).st_mode & 0o111 != 0 and is_macho(path))


def kind_of(item: str) -> str:
    if item.endswith(".app"):
        return "app"
    if item.endswith(".dmg"):
        return "dmg"
    if item.endswith((".pkg", ".mpkg")):
        return "pkg"
    return "program"


def apple_items(path: str) -> list[str]:
    if path.endswith(BUNDLE_SUFFIXES) or is_program(path):
        return [path]
    if not os.path.isdir(path):
        return []
    items = []
    for root, dirs, files in os.walk(path):
        for d in list(dirs):
            if d.endswith(".app"):
                items.append(os.path.join(root, d))
                dirs.remove(d)   # a bundle is judged whole, never file by file
        for f in files:
            p = os.path.join(root, f)
            if f.endswith(BUNDLE_SUFFIXES[1:]) or is_program(p):
                items.append(p)
    return sorted(items)


def gatekeeper(item: str) -> dict:
    kind = kind_of(item)
    if kind == "dmg":
        argv = ["spctl", "--assess", "--type", "open", "--context", "context:primary-signature", "-vv", item]
    elif kind == "pkg":
        argv = ["spctl", "--assess", "--type", "install", "-vv", item]
    else:
        argv = ["spctl", "--assess", "--type", "execute", "-vv", item]
    proc = run(argv, timeout=120)
    out = {"verdict": "accepted" if proc.returncode == 0 else "rejected"}
    for line in (proc.stderr + proc.stdout).splitlines():
        if "=" in line and line.split("=", 1)[0] in ("source", "origin"):
            key, val = line.split("=", 1)
            out[key] = val
    return out


def signer_of(codesign_dv: str) -> dict:
    """Who signed it, from `codesign -dv --verbose=2` output."""
    auths = re.findall(r"^Authority=(.+)$", codesign_dv, re.M)
    team = re.search(r"^TeamIdentifier=(.+)$", codesign_dv, re.M)
    team_id = team.group(1).strip() if team and team.group(1).strip() != "not set" else None
    if "Signature=adhoc" in codesign_dv:
        kind = "ad-hoc"
    elif auths and auths[0].startswith("Developer ID"):
        kind = "Developer ID"
    elif auths and auths[0] in APPLE_AUTHORITIES:
        kind = "Apple"
    elif auths:
        kind = "other certificate"
    else:
        kind = "unknown"
    return {"kind": kind, "authority": auths[0] if auths else None, "team": team_id}


def signature(item: str) -> dict:
    if kind_of(item) == "pkg":
        proc = run(["pkgutil", "--check-signature", item], timeout=120)
        status = next((l.split(":", 1)[1].strip() for l in proc.stdout.splitlines()
                       if l.strip().startswith("Status:")), "")
        first = re.search(r"^\s*1\.\s+(.+)$", proc.stdout, re.M)
        if proc.returncode == 0 and "no signature" not in status:
            authority = first.group(1).strip() if first else None
            kind = "Developer ID" if authority and authority.startswith("Developer ID") else (
                "Apple" if authority and "Apple" in authority else "other certificate")
            return {"state": "valid", "detail": status, "signer": {"kind": kind, "authority": authority}}
        return {"state": "unsigned" if "no signature" in status else "invalid", "detail": status}
    argv = ["codesign", "--verify", "--strict"] + (["--deep"] if item.endswith(".app") else []) + [item]
    proc = run(argv, timeout=300)
    if proc.returncode != 0:
        detail = next((l for l in proc.stderr.splitlines() if l.strip()), "")
        return {"state": "unsigned" if "not signed at all" in detail else "invalid", "detail": detail}
    info = run(["codesign", "-dv", "--verbose=2", item], timeout=60)
    return {"state": "valid", "signer": signer_of(info.stderr + info.stdout)}


def quarantine(item: str) -> dict | None:
    proc = run(["xattr", "-p", "com.apple.quarantine", item], timeout=30)
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    fields = proc.stdout.strip().split(";")
    tag: dict = {"agent": fields[2] if len(fields) > 2 and fields[2] else None}
    try:
        tag["date"] = dt.datetime.fromtimestamp(int(fields[1], 16)).strftime("%Y-%m-%d %H:%M")
    except (IndexError, ValueError):
        tag["date"] = None
    return tag


def origin(item: str) -> list[str]:
    proc = run(["mdls", "-raw", "-name", "kMDItemWhereFroms", item], timeout=30)
    return re.findall(r'"([^"]+)"', proc.stdout) if proc.returncode == 0 else []


def sha256(item: str) -> dict | None:
    """The fingerprint of what actually runs: an app's main executable, else the file."""
    target = item
    if item.endswith(".app"):
        try:
            with open(os.path.join(item, "Contents", "Info.plist"), "rb") as f:
                exe = plistlib.load(f).get("CFBundleExecutable")
        except (OSError, plistlib.InvalidFileException, ValueError):
            exe = None
        if not isinstance(exe, str) or not exe or "/" in exe or exe in (".", ".."):   # untrusted plist
            return None
        target = os.path.join(item, "Contents", "MacOS", exe)
        if not os.path.realpath(target).startswith(os.path.realpath(item) + os.sep):   # a link out of the bundle
            return None
    if not os.path.isfile(target):
        return None
    h = hashlib.sha256()
    with open(target, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return {"file": target, "sha256": h.hexdigest()}


def xprotect_version(now: dt.datetime | None = None) -> dict | None:
    """`Version: 5368 Installed: 2026-10-22 19:12:22 +0000`. Reading needs no root; checking
    for or installing an update does, so the scan reports the age and never updates it."""
    if not shutil.which("xprotect"):
        return None
    out = run(["xprotect", "version"], timeout=30).stdout
    m = re.search(r"Version:\s*(\S+)\s+Installed:\s*(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d [+-]\d{4})", out)
    if not m:
        return None
    installed = dt.datetime.strptime(m.group(2), "%Y-%m-%d %H:%M:%S %z")
    age = (now or dt.datetime.now(dt.timezone.utc)) - installed
    return {"version": m.group(1), "installed": m.group(2), "age_days": age.days}


def level_of(entry: dict) -> str:
    sig, gk = entry["signature"], entry["gatekeeper"]
    if sig["state"] == "invalid":
        return "finding"
    if entry["kind"] == "dmg" and sig["state"] == "unsigned":
        return "note"
    if gk["verdict"] == "rejected" or sig["state"] == "unsigned":
        return "unverified"
    return "ok"


def reason_of(entry: dict) -> str | None:
    sig, gk = entry["signature"], entry["gatekeeper"]
    if entry["level"] == "finding":
        return "the signature is broken: the file changed after it was signed"
    if entry["level"] == "note":
        return "unsigned disk image, which is common; mount it and scan the app inside"
    if entry["level"] != "unverified":
        return None
    if sig["state"] == "unsigned":
        return "unsigned: nothing says who made it"
    kind = sig.get("signer", {}).get("kind")
    if kind == "ad-hoc":
        return "ad-hoc signed and not notarized: a self-built or unofficial build; compare its SHA-256 with the vendor's"
    return "Gatekeeper refuses it (not notarized, or the certificate was revoked)"


def apple_lane(path: str) -> dict:
    if not shutil.which("spctl"):
        return {"status": "skipped", "note": "not macOS: spctl is unavailable", "items": []}
    lane: dict = {"status": "ok", "items": [], "warnings": []}
    status = run(["spctl", "--status"], timeout=30)
    lane["gatekeeper_enabled"] = "assessments enabled" in (status.stdout + status.stderr)
    lane["xprotect"] = xprotect_version()
    days = lane["xprotect"].get("age_days") if lane["xprotect"] else None
    if days is not None and days > XPROTECT_STALE_DAYS:
        lane["warnings"].append(f"Apple's XProtect rules are {days} days old; updating needs root: sudo xprotect update")
    items = apple_items(path)
    if len(items) > MAX_APPLE_ITEMS:
        lane["note"] = f"{len(items)} apps, installers and programs found; checked the first {MAX_APPLE_ITEMS}"
        items = items[:MAX_APPLE_ITEMS]
    for item in items:
        entry = {"item": item, "kind": kind_of(item), "gatekeeper": gatekeeper(item),
                 "signature": signature(item), "quarantine": quarantine(item),
                 "origin": origin(item), "sha256": sha256(item)}
        entry["level"] = level_of(entry)
        entry["reason"] = reason_of(entry)
        lane["items"].append(entry)
    return lane


# ---- Sweep ------------------------------------------------------------------------

def top_folder(root: str, path: str) -> str:
    return os.path.relpath(path, root).split(os.sep)[0]


def by_folder(root: str, paths: list[str]) -> dict:
    counts: dict = {}
    for p in paths:
        k = top_folder(root, p)
        counts[k] = counts.get(k, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def sweep(path: str, since: dt.date) -> dict:
    proc = run(["/usr/bin/find", path, "-newermt", since.isoformat(),
                "!", "-xattrname", "com.apple.quarantine", "-print"])
    made = sorted(p for p in proc.stdout.splitlines()
                  if p and p != path and os.path.basename(p) != ".DS_Store")
    instructions, runnable = [], []
    for root, dirs, files in os.walk(path):
        for name in dirs + files:
            if name in INSTRUCTION_NAMES:
                instructions.append(os.path.join(root, name))
        for f in files:
            p = os.path.join(root, f)
            try:
                executable = not os.path.islink(p) and os.stat(p).st_mode & 0o111 != 0
            except OSError:
                executable = False
            if executable or f.endswith(RUNNABLE_SUFFIXES):
                runnable.append(p)
    return {"path": path, "since": since.isoformat(),
            "made_on_this_mac": {"count": len(made), "by_folder": by_folder(path, made),
                                 "paths": made[:SWEEP_LIST_CAP]},
            "instruction_files": sorted(instructions),
            "runnable_by_folder": by_folder(path, runnable),
            "find_error": proc.stderr.strip() if proc.returncode != 0 else None}


def render_sweep(s: dict) -> str:
    out = [f"sweep: {s['path']} (changed since {s['since']})"]
    m = s["made_on_this_mac"]
    out.append(f"  made on this Mac, no quarantine tag: {m['count']}")
    out += [f"    {n:>5}  {k}" for k, n in m["by_folder"].items()]
    out.append(f"  agent instruction or auto-run files: {len(s['instruction_files'])}")
    out += [f"    {p}" for p in s["instruction_files"]]
    out.append("  runnable files by folder:")
    out += [f"    {n:>5}  {k}" for k, n in s["runnable_by_folder"].items()]
    if s["find_error"]:
        out.append(f"  error: find: {s['find_error']}")
    out.append("  next: scan anything you do not recognize with scan.py \"<item>\"")
    out.append(f"  verdict: {s['verdict']}")
    return "\n".join(printable(line) for line in out)


# ---- Report ------------------------------------------------------------------------

def signer_text(sig: dict) -> str:
    s = sig.get("signer") or {}
    if s.get("kind") == "ad-hoc":
        return "ad-hoc (no publisher)"
    return s.get("authority") or s.get("kind") or ""


def render(report: dict) -> str:
    out = [f"scan: {report['path']}"]
    c = report["clamav"]
    if c["status"] == "setup-needed":
        out.append(f"  clamav: {c['note']}:")
        out += [f"    {i}. {s}" for i, s in enumerate(c["setup"], 1)]
    else:
        age = c.get("signature_age_hours")
        out.append(f"  clamav: {c.get('scanned_files', '?')} files, {len(c['found'])} infected"
                   + (f", signatures {age / 24:.1f} days old" if age is not None else ""))
        if c["update"]["ran"]:
            out.append("    signatures updated with freshclam before the scan"
                       if c["update"]["exit"] in (0, 1) else "    signature update attempted")
        out += [f"    FOUND {f['signature']}: {f['file']}" for f in c["found"]]
        out += [f"    warning: {w}" for w in c["warnings"]]
        if c["status"] == "error":
            out.append(f"    error: {c['note']}")
    a = report["apple"]
    if a["status"] == "skipped":
        out.append(f"  apple: {a['note']}")
    else:
        n = len(a["items"])
        out.append(f"  apple: {n} app{'' if n == 1 else 's'}, installer{'' if n == 1 else 's'} or program{'' if n == 1 else 's'}"
                   + ("" if a["gatekeeper_enabled"] else " (Gatekeeper assessments are disabled)"))
        x = a.get("xprotect")
        if x:
            out.append(f"    XProtect rules {x['version']}, installed {x['age_days']} days ago")
        out += [f"    warning: {w}" for w in a["warnings"]]
        for e in a["items"]:
            g, s, q = e["gatekeeper"], e["signature"], e["quarantine"]
            mark = {"finding": "FINDING ", "unverified": "UNVERIFIED "}.get(e["level"], "")
            out.append(f"    {mark}{e['item']}")
            out.append(f"      gatekeeper {g['verdict']}" + (f" ({g['source']})" if g.get("source") else ""))
            sig = f"      signature {s['state']}"
            if s["state"] == "valid" and signer_text(s):
                sig += f", {signer_text(s)}"
            elif s.get("detail"):
                sig += f": {s['detail']}"
            out.append(sig)
            if q:
                out.append(f"      quarantined by {q['agent'] or 'unknown app'} on {q['date'] or 'unknown date'}")
            else:
                out.append("      no quarantine tag: not downloaded by a browser")
            if e["origin"]:
                out.append(f"      downloaded from {e['origin'][0]}")
            if e["sha256"]:
                out.append(f"      sha256 {e['sha256']['sha256']}")
            if e["reason"]:
                out.append(f"      {e['level']}: {e['reason']}")
        if a.get("note"):
            out.append(f"    note: {a['note']}")
    out.append(f"  verdict: {report['verdict']}")
    return "\n".join(printable(line) for line in out)


def printable(text: str) -> str:
    """File names come from the scanned folder: escape anything that could steer a terminal."""
    return "".join(ch if ch.isprintable() else f"\\x{ord(ch):02x}" for ch in text)


def main(argv: list[str] | None = None) -> int:
    try:
        return run_main(argv)
    except Exception as exc:   # exit 1 means a finding, so a crash is never 1
        print(f"scan: a tool failed or timed out ({type(exc).__name__}); nothing was concluded", file=sys.stderr)
        return 4


def run_main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Report-only ClamAV and macOS trust check.")
    ap.add_argument("path")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--sweep", action="store_true", help="triage listing of a folder, no scanning")
    ap.add_argument("--no-update", action="store_true", help="skip the freshclam update (offline)")
    ap.add_argument("--since", help="sweep: changed on or after YYYY-MM-DD (default: 30 days ago)")
    args = ap.parse_args(argv)
    path = os.path.realpath(os.path.expanduser(args.path))
    if not os.path.exists(path):
        print(f"scan: no such file or folder: {args.path}", file=sys.stderr)
        return 2
    if args.sweep:
        if not os.path.isdir(path):
            print("scan: --sweep takes a folder", file=sys.stderr)
            return 2
        try:
            since = (dt.date.fromisoformat(args.since) if args.since
                     else dt.date.today() - dt.timedelta(days=30))
        except ValueError:
            print(f"scan: --since must be YYYY-MM-DD, got {args.since}", file=sys.stderr)
            return 2
        s = sweep(path, since)
        review = s["made_on_this_mac"]["count"] or s["instruction_files"]
        s["verdict"] = "review" if review else ("incomplete" if s["find_error"] else "clean")
        print(json.dumps(s, indent=2) if args.json else render_sweep(s))
        return 3 if review else (4 if s["find_error"] else 0)
    report = {"path": path, "clamav": clamav_lane(path, update=not args.no_update), "apple": apple_lane(path)}
    levels = {e["level"] for e in report["apple"]["items"]}
    found = bool(report["clamav"].get("found")) or "finding" in levels
    failed = report["clamav"]["status"] in ("setup-needed", "error")
    report["verdict"] = ("findings" if found else "incomplete" if failed
                         else "unverified" if "unverified" in levels else "clean")
    print(json.dumps(report, indent=2) if args.json else render(report))
    return {"findings": 1, "incomplete": 4, "unverified": 3, "clean": 0}[report["verdict"]]


if __name__ == "__main__":
    sys.exit(main())
