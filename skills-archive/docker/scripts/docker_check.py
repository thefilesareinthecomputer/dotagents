#!/usr/bin/env python3
"""Deterministic Dockerfile / compose linter - the checks the standard tools miss.

EXECUTE this. It is NOT a replacement for hadolint/trivy/dockle: those are
mature, battle-tested, and this script deliberately does not reimplement them.
It covers the gaps that matter when an AGENT is writing the container:

  - host-escape grants in compose (docker.sock at ANY path, privileged,
    cap_add, namespace-host, unconfined seccomp/apparmor, /dev and sensitive
    bind mounts, user: root) - hadolint does not read compose at all
  - secrets baked into image layers (ENV/ARG/RUN export/COPY .env) - a layer is
    forever, and `docker history` reads it back even after a later delete
  - cache-destroying layer order, non-root USER (per-stage), pinned base, etc.

Stdlib only. Offline. No network, no subprocess, no docker daemon contact.

This tool FAILS CLOSED. A line too long to scan safely, or a file too large,
is reported as a finding to review - never silently skipped - because an
adversary padding past a length cap must not slip a socket mount past the gate.

    python3 docker_check.py <path>...        # exit 1 on any FAIL
    python3 docker_check.py --json <path>
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

FAIL, WARN = "FAIL", "WARN"

MAX_FILE_BYTES = 1_000_000
MAX_LINE_CHARS = 2_000

DOCKERFILE_NAMES = ("dockerfile",)
COMPOSE_NAMES = ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")
# Canonical names plus the environment-suffixed variants everyone actually ships
# (compose.dev.yml, docker-compose.override.yml). Matching only the four canonical
# names silently skipped every compose file this skill's own scaffold prescribes.
COMPOSE_RE = re.compile(r"^(?:docker-)?compose(?:\.[a-z0-9_-]+)*\.ya?ml$")


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    severity: str
    rule: str
    message: str


def strip_comment(line: str) -> str:
    """Drop a trailing/leading YAML or Dockerfile comment so a commented-out
    example (`# privileged: true`) does not trip a FAIL - a linter that fires on
    inert lines gets muted. A '#' inside quotes is left alone."""
    out, quote = [], None
    for ch in line:
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            out.append(ch)
        elif ch == "#":
            break
        else:
            out.append(ch)
    return "".join(out)


# --- Dockerfile rules ------------------------------------------------------
# Every quantifier is BOUNDED and anchored: this reads files it did not write.

SECRET_NAME = re.compile(
    r"(PASSWORD|PASSWD|SECRET|TOKEN|API[_-]?KEY|ACCESS[_-]?KEY|PRIVATE[_-]?KEY|CREDENTIAL)",
    re.I,
)
SECRET_LITERAL = re.compile(r"(sk-[a-z0-9]|ghp_[a-z0-9]|gho_[a-z0-9]|AKIA[A-Z0-9]|xox[baprs]-)", re.I)
KV_TOKEN = re.compile(r"([A-Za-z_][\w.]{0,60})\s*=\s*(\S+)")

COPY_ENV_FILE = re.compile(r"^\s*(?:COPY|ADD)\b[^\n]{0,200}?(?<![\w.])\.env(?:\.\w+)?\b", re.I)
ADD_REMOTE = re.compile(r"^\s*ADD\s+https?://", re.I)
CURL_PIPE_SH = re.compile(r"(?:curl|wget)\b[^\n|]{0,200}\|\s*(?:sudo\s+)?(?:ba)?sh\b", re.I)
RUN_EXPORT_SECRET = re.compile(r"^\s*RUN\b[^\n]{0,200}?\bexport\s+\w{0,40}", re.I)
LATEST_TAG = re.compile(r"^\s*FROM\s+\S{1,200}:latest\b", re.I)
CHMOD_777 = re.compile(r"\bchmod\s+(?:-\w+\s+)?777\b")
SUDO = re.compile(r"^\s*RUN\b[^\n]{0,200}\bsudo\b", re.I)
PIP_NO_CACHE = re.compile(r"\bpip3?\s+install\b(?![^\n]{0,200}--no-cache-dir)", re.I)
APT_NO_RECOMMENDS = re.compile(r"\bapt-get\s+install\b(?![^\n]{0,200}--no-install-recommends)", re.I)
COPY_ALL = re.compile(r"^\s*COPY\s+\.\s+", re.I)
INSTALL_CMD = re.compile(r"^\s*RUN\b[^\n]{0,300}\b(pip3?\s+install|npm\s+(?:ci|install)|poetry\s+install|uv\s+sync|yarn)\b", re.I)
USER_ROOT = re.compile(r"^\s*USER\s+(?:root|0)\b", re.I)
USER_NONROOT = re.compile(r"^\s*USER\s+(?!root\b|0\b)\S", re.I)
HEALTHCHECK = re.compile(r"^\s*HEALTHCHECK\b", re.I)
FROM_LINE = re.compile(r"^\s*FROM\b", re.I)
FROM_UNPINNED = re.compile(r"^\s*FROM\s+(?!scratch\b)([^\s:@]{1,200})\s*(?:AS\s+\w+)?\s*$", re.I)


def scan_secret_line(line: str) -> str | None:
    """A logical Dockerfile line (continuations already joined). Returns a
    message if it bakes a secret, else None. Handles multi-var ENV/ARG."""
    if SECRET_LITERAL.search(line):
        return ("Literal credential (sk-/ghp_/AKIA/xox…) baked into the image. "
                "Rotate it - assume it is already public.")
    m = re.match(r"^\s*(ENV|ARG|RUN\b[^\n]{0,80}?\bexport)\b", line, re.I)
    if not m:
        return None
    for key, _val in KV_TOKEN.findall(line):
        if SECRET_NAME.search(key):
            return ("Secret in ENV/ARG/export. Image layers are permanent and readable via "
                    "`docker history` even if a later layer deletes it. Use BuildKit "
                    "`--mount=type=secret` or inject at runtime.")
    return None


# --- compose rules ---------------------------------------------------------
# The host-escape grants. This is the reason the script exists: hadolint does
# not read compose files, and these are where root-on-host is handed out.

DOCKER_SOCK = re.compile(r"docker\.sock\b", re.I)               # ANY path, not just /var/run
FS_ROOT_MOUNT = re.compile(r"^\s*-\s*['\"]?/\s*:", re.I)
SENSITIVE_MOUNT = re.compile(r"^\s*-\s*['\"]?(/etc|/root|/var/run|/sys|/proc|/boot|/dev)\b", re.I)
PRIVILEGED = re.compile(r"^\s*privileged:\s*true\b", re.I)
NS_HOST = re.compile(r"^\s*(pid|ipc|userns_mode|network_mode):\s*['\"]?(host|container:)", re.I)
UNCONFINED = re.compile(r"(seccomp|apparmor)\s*[:=]\s*unconfined", re.I)
CAP_DANGEROUS = re.compile(
    r"^\s*-\s*['\"]?(ALL|SYS_ADMIN|SYS_MODULE|SYS_PTRACE|SYS_RAWIO|DAC_READ_SEARCH|DAC_OVERRIDE|NET_ADMIN|BPF)\b",
    re.I,
)
USER_ROOT_COMPOSE = re.compile(r"^\s*user:\s*['\"]?(root|0)(?::|['\"]|\s|$)", re.I)
SECRET_COMPOSE = re.compile(
    r"^[ \t]*(?:-[ \t]*)?\w{0,40}(PASSWORD|SECRET|TOKEN|API[_-]?KEY)\w{0,40}[ \t]*[:=][ \t]*(?!\$|\{\{)\S",
    re.I,
)

# (rule, severity, pattern, message). Applies to compose lines (comment-stripped).
COMPOSE_LINE_RULES: list[tuple[str, str, re.Pattern[str], str]] = [
    ("docker-socket-mount", FAIL, DOCKER_SOCK,
     "Mounting the Docker socket (any path) is root on the host, full stop. A container with it can start a privileged "
     "container mounting / and own the machine. Never grant it to anything that reads untrusted input, including an agent."),
    ("privileged", FAIL, PRIVILEGED,
     "privileged: true disables essentially every container boundary. Grant the specific cap_add you need instead."),
    ("root-fs-mount", FAIL, FS_ROOT_MOUNT,
     "Bind-mounting / hands the container the whole host filesystem."),
    ("sensitive-mount", FAIL, SENSITIVE_MOUNT,
     "Bind-mounting a host system path (/etc, /root, /proc, /sys, /dev, …). Read/write access to host internals; escape-adjacent."),
    ("namespace-host", FAIL, NS_HOST,
     "Sharing a host namespace (pid/ipc/network/userns: host). Removes the isolation the container is for; pid:host + SYS_PTRACE is host process injection."),
    ("unconfined-profile", FAIL, UNCONFINED,
     "seccomp/apparmor: unconfined turns off the syscall/MAC filter - a large chunk of the container security model, gone."),
    ("device-passthrough", WARN, re.compile(r"^\s*-\s*['\"]?/dev/(mem|kmem|sda|nvme|kvm)\b", re.I),
     "Raw host device passthrough. /dev/mem is host physical memory. Almost never what you meant."),
    ("compose-user-root", WARN, USER_ROOT_COMPOSE,
     "user: root in compose overrides a correct non-root USER in the image. The container runs as root regardless of the Dockerfile."),
    ("secret-in-compose", WARN, SECRET_COMPOSE,
     "Hardcoded credential in compose. Use an env_file (gitignored) or a secrets provider, not a literal."),
]


def _read_lines(path: Path) -> tuple[list[str] | None, Finding | None]:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            # Fail closed: a >1MB container file is not 'clean', it is unreviewed.
            return None, Finding(str(path), 0, FAIL, "file-too-large",
                                 "File over 1MB - not scanned. Too large to gate safely; review by hand or split it. "
                                 "(Reported as FAIL, not skipped, so padding cannot hide a grant behind the size cap.)")
        return path.read_text(encoding="utf-8", errors="replace").splitlines(), None
    except OSError as exc:
        return None, Finding(str(path), 0, WARN, "unreadable", f"Could not read: {exc}")


def _overlong(path: str, lineno: int, kind: str) -> Finding:
    return Finding(path, lineno, FAIL, "line-too-long",
                   f"{kind} line over {MAX_LINE_CHARS} chars - not scanned. Reported as FAIL so a padded line cannot "
                   "slip a secret or a grant past the gate. Reformat it to be reviewable.")


def _join_continuations(lines: list[str]) -> list[tuple[int, str]]:
    """Yield (lineno, logical_line) with backslash-continuations joined, so a
    secret split across `ENV FOO=bar \\` / `    API_KEY=sk-…` is seen whole."""
    out: list[tuple[int, str]] = []
    buf, start = "", 0
    for i, raw in enumerate(lines, 1):
        if not buf:
            start = i
        stripped = raw.rstrip()
        if stripped.endswith("\\"):
            buf += stripped[:-1] + " "
        else:
            out.append((start, buf + raw))
            buf = ""
    if buf:
        out.append((start, buf))
    return out


def check_dockerfile(path: Path) -> list[Finding]:
    lines, err = _read_lines(path)
    if lines is None:
        return [err] if err else []

    findings: list[Finding] = []
    stage_has_user = True   # becomes False at each FROM; the LAST stage is what ships
    stage_from_line = 0
    saw_healthcheck = False
    copy_all_line = install_line = 0

    for start, logical in _join_continuations(lines):
        if len(logical) > MAX_LINE_CHARS:
            findings.append(_overlong(str(path), start, "Dockerfile"))
            continue
        line = strip_comment(logical)

        if FROM_LINE.search(line):
            # Only the FINAL stage's USER is judged (after the loop) - an
            # intermediate stage running as root is discarded and does not ship.
            stage_has_user = False
            stage_from_line = start
            if LATEST_TAG.search(line):
                findings.append(Finding(str(path), start, WARN, "latest-tag",
                                        "FROM …:latest is not reproducible. Pin a version, ideally a digest."))
            elif FROM_UNPINNED.search(line):
                findings.append(Finding(str(path), start, WARN, "unpinned-base",
                                        "FROM with no tag resolves to :latest implicitly. Pin it."))

        if USER_NONROOT.search(line):
            stage_has_user = True
        if USER_ROOT.search(line):
            stage_has_user = False   # explicit re-root; the stage ends as root

        if (msg := scan_secret_line(line)):
            rule = "secret-literal" if SECRET_LITERAL.search(line) else "secret-in-layer"
            findings.append(Finding(str(path), start, FAIL, rule, msg))

        for rule, severity, pattern, message in (
            ("copy-env-file", FAIL, COPY_ENV_FILE, "Copying a .env into the image; the layer keeps it. Add it to .dockerignore and inject at runtime."),
            ("add-remote-url", FAIL, ADD_REMOTE, "ADD from a URL fetches unverified content at build time. Use RUN curl with a checksum, or COPY a vendored file."),
            ("curl-pipe-sh", FAIL, CURL_PIPE_SH, "curl | sh executes whatever the server returns today. Pin a version and verify a checksum."),
            ("sudo-in-run", WARN, SUDO, "sudo in RUN. Build steps already run as root; sudo signals confusion and is often not installed."),
            ("chmod-777", WARN, CHMOD_777, "chmod 777 is world-writable. Set an owner and a real mode."),
            ("pip-cache", WARN, PIP_NO_CACHE, "pip install without --no-cache-dir bloats the layer with a wheel cache nothing reads."),
            ("apt-recommends", WARN, APT_NO_RECOMMENDS, "apt-get install without --no-install-recommends pulls in packages you did not ask for."),
        ):
            if pattern.search(line):
                findings.append(Finding(str(path), start, severity, rule, message))

        if HEALTHCHECK.search(line):
            saw_healthcheck = True
        if COPY_ALL.search(line) and not copy_all_line:
            copy_all_line = start
        if INSTALL_CMD.search(line) and not install_line:
            install_line = start

    # Only the FINAL stage's user matters - it is what runs.
    if not stage_has_user:
        findings.append(Finding(str(path), stage_from_line or 1, FAIL, "runs-as-root",
                                "The final stage has no non-root USER (or was re-rooted). The shipped container runs as root; "
                                "a container escape is then a host root escape."))

    if copy_all_line and install_line and copy_all_line < install_line:
        findings.append(Finding(str(path), copy_all_line, WARN, "cache-busting-copy",
                                f"`COPY . .` (line {copy_all_line}) precedes the dependency install (line {install_line}); every "
                                "source change reinstalls everything. Copy the manifest, install, then copy the source."))
    if not saw_healthcheck:
        findings.append(Finding(str(path), 1, WARN, "no-healthcheck",
                                "No HEALTHCHECK. The orchestrator cannot tell 'running' from 'wedged'."))
    if not (path.parent / ".dockerignore").exists():
        findings.append(Finding(str(path), 1, WARN, "no-dockerignore",
                                "No .dockerignore beside the Dockerfile. .git, .env and node_modules get shipped to the daemon and can land in the image."))

    return findings


def check_compose(path: Path) -> list[Finding]:
    lines, err = _read_lines(path)
    if lines is None:
        return [err] if err else []

    findings: list[Finding] = []
    in_cap_add = False   # cap_add: is dangerous; cap_drop: [ALL] is the CORRECT hardening
    for lineno, raw in enumerate(lines, 1):
        if len(raw) > MAX_LINE_CHARS:
            findings.append(_overlong(str(path), lineno, "compose"))
            continue
        line = strip_comment(raw)

        key = re.match(r"^\s*(cap_add|cap_drop):", line, re.I)
        if key:
            in_cap_add = key.group(1).lower() == "cap_add"
        elif line.strip() and not line.lstrip().startswith("-"):
            in_cap_add = False   # left the list block on any non-list key
        if in_cap_add and CAP_DANGEROUS.search(line):
            findings.append(Finding(str(path), lineno, FAIL, "cap-dangerous",
                                    "Dangerous capability under cap_add. ALL == privileged; SYS_MODULE loads host kernel modules; "
                                    "SYS_PTRACE injects into host processes; DAC_* reads any host file. Drop it or justify the exact one."))

        for rule, severity, pattern, message in COMPOSE_LINE_RULES:
            if pattern.search(line):
                findings.append(Finding(str(path), lineno, severity, rule, message))
    return findings


def classify(path: Path) -> str | None:
    name = path.name.lower()
    if COMPOSE_RE.match(name):
        return "compose"
    if name.startswith(DOCKERFILE_NAMES) or name.endswith(".dockerfile"):
        return "dockerfile"
    return None


def iter_targets(paths: list[str]) -> tuple[list[tuple[Path, str]], bool]:
    """Returns (targets, missing) - missing is True if the user named an explicit
    path that resolved to nothing, so a mistyped path fails the gate rather than
    reading as green."""
    out: list[tuple[Path, str]] = []
    missing = False
    for raw in paths:
        p = Path(raw)
        if not p.exists():
            missing = True
            continue
        if p.is_dir():
            hit = False
            for f in sorted(p.rglob("*")):
                if f.is_symlink() or any(part in {".git", "node_modules"} for part in f.parts):
                    continue
                if (kind := classify(f)):
                    out.append((f, kind))
                    hit = True
            if not hit:
                missing = True
        elif (kind := classify(p)):
            out.append((p, kind))
        else:
            missing = True
    return out, missing


def safe(path: str) -> str:
    return path.replace("\n", "\\n").replace("\r", "\\r")


def main() -> int:
    ap = argparse.ArgumentParser(description="Dockerfile/compose linter for the checks hadolint does not make.")
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--warn-only", action="store_true")
    args = ap.parse_args()

    targets, missing = iter_targets(args.paths)
    if not targets:
        print("no Dockerfile or compose file found at the given path(s)", file=sys.stderr)
        return 0 if not missing else 1

    findings: list[Finding] = []
    for path, kind in targets:
        findings.extend(check_dockerfile(path) if kind == "dockerfile" else check_compose(path))

    fails = [f for f in findings if f.severity == FAIL]

    if args.json:
        print(json.dumps({"findings": [asdict(f) for f in findings], "files": len(targets), "missing": missing}, indent=2))
    else:
        for f in sorted(findings, key=lambda f: (f.path, f.line)):
            print(f"{safe(f.path)}:{f.line}: {f.severity}: {f.rule}: {f.message}")
        print(f"\n{len(fails)} fail, {len(findings) - len(fails)} warn, {len(targets)} file(s)")
        if not findings:
            print("clean - now run hadolint/trivy/dockle for the checks this script deliberately does not duplicate.")

    hard = bool(fails) or missing
    return 1 if hard and not args.warn_only else 0


if __name__ == "__main__":
    sys.exit(main())
