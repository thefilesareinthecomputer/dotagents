#!/usr/bin/env python3
"""gate - the content check behind the station's git hooks.

  sanitize.py gate --staged               pre-commit: added lines in the effective index
  sanitize.py gate --refs [--remote R]    pre-push: ref tuples on stdin
  sanitize.py gate --range A..B           on demand: every commit in a range
  sanitize.py gate --message FILE         commit-msg: the message text
  sanitize.py gate --files PATH...        whole files at the review tier

Every detector runs over the full post-image of each touched file, and a finding is
reported only when its span touches an added line. A range is scanned commit by commit,
diff and message, so a secret added in one commit and removed in the next still blocks.

Output is one line per finding on stderr, `path:line  class  tier`, never the matched
value; --json prints the same as a list on stdout. Exit 0 when clean or warn-only, 3 on a
block, 2 on bad arguments. A git object the gate cannot read blocks. A bug in the gate
itself exits 0 with one stderr line: a global hook that refuses every commit on its own
error would stop every agent on the machine, and agents cannot pass --no-verify.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import detect  # noqa: E402

EXIT_BLOCK = 3
ZERO = "0" * 40
# The detectors run at about 0.4 s per MB. Up to FULL_SCAN_BYTES a text file is scanned
# whole; above it, only the lines within WINDOW_LINES of an added line are scanned, so the
# time follows the size of the change rather than the file. A text file over MAX_TEXT_BYTES
# is not read at all, and that blocks: a file the gate cannot check never passes as clean.
FULL_SCAN_BYTES = 8 * 1024 * 1024
MAX_TEXT_BYTES = 1024 * 1024 * 1024
WINDOW_LINES = 64          # wider than a 4096-bit PEM key block, so one stays whole
MAX_COMMITS = 5000
# Agent-mail inboxes hold other agents' messages; committing one is refused unless the
# commit sets this variable to 1, which lifts this rule alone.
INBOX = re.compile(r"(^|/)\.(claude|agents)/inbox/")
INBOX_BYPASS = "AGENT_MAIL_COMMIT_INBOX"
EXCLUDED = ("*.lock", "package-lock.json", "npm-shrinkwrap.json", "pnpm-lock.yaml", "*.pbxproj",
            "*.min.js", "*.min.css")
HUNK = re.compile(rb"^@@@* (?:-\d+(?:,\d+)? )+\+(\d+)(?:,(\d+))? @@@*")
GIT = ["git", "-c", "core.quotePath=false", "-c", "diff.renames=true"]
# --text: a repo's `-diff` attribute would otherwise print "Binary files differ" and
# keep a text file out of the scan entirely.
DIFF_FLAGS = ["-U0", "--text", "--no-color", "--no-ext-diff", "--no-textconv",
              "--src-prefix=a/", "--dst-prefix=b/"]
GITLINK_MODE = b"160000"
# A NUL byte in one of these is expected; in anything else it earns a warning, since
# a NUL near the top is also how a text file would slip past as "binary".
BINARY_SUFFIXES = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".icns", ".heic", ".bmp", ".tiff", ".psd",
    ".pdf", ".zip", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".tar", ".jar", ".class", ".whl",
    ".mp3", ".mp4", ".mov", ".m4a", ".wav", ".ogg", ".webm", ".woff", ".woff2", ".ttf", ".otf",
    ".eot", ".sqlite", ".db", ".pyc", ".so", ".dylib", ".dll", ".exe", ".bin", ".parquet",
})


class GitError(Exception):
    """A git call failed or an object could not be read: never a clean result."""


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    cls: str
    rule: str
    tier: str


# ---------------------------------------------------------------- git plumbing


def git(*args: str, input: bytes | None = None) -> bytes:
    try:
        res = subprocess.run([*GIT, *args], input=input, capture_output=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GitError(f"git {args[0]} did not run ({type(exc).__name__})")
    if res.returncode != 0:
        raise GitError(f"git {args[0]} failed (exit {res.returncode})")
    return res.stdout


class Blobs:
    """One `git cat-file --batch` process for every object read in a run."""

    def __init__(self):
        try:
            self.proc = subprocess.Popen([*GIT, "cat-file", "--batch"], stdin=subprocess.PIPE,
                                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except OSError as exc:
            raise GitError(f"git cat-file did not run ({type(exc).__name__})")

    def read(self, rev: str, path: str) -> bytes | None:
        spec = f"{rev}:{path}"
        if "\n" in spec:
            return git("cat-file", "blob", spec)     # --batch input is line-based
        self.proc.stdin.write(spec.encode("utf-8", "surrogateescape") + b"\n")
        self.proc.stdin.flush()
        header = self.proc.stdout.readline().split()
        if len(header) == 3 and header[1] != b"blob":
            # not file content (a commit object behind a gitlink): consume it, scan nothing
            self.proc.stdout.read(int(header[2]) + 1)
            return None
        if len(header) != 3:
            raise GitError(f"cannot read {display(path)} at {rev or 'the index'}")
        data = self.proc.stdout.read(int(header[2]))
        self.proc.stdout.read(1)
        return data

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=10)
        except Exception:
            self.proc.kill()


def unquote(raw: bytes) -> str:
    """A path from a diff header. git C-quotes a path holding a quote, a backslash or a
    control character even with core.quotePath off."""
    if raw.startswith(b'"') and raw.endswith(b'"'):
        out, i, body = bytearray(), 0, raw[1:-1]
        simple = {ord("n"): 10, ord("t"): 9, ord('"'): 34, ord("\\"): 92, ord("a"): 7,
                  ord("b"): 8, ord("f"): 12, ord("r"): 13, ord("v"): 11}
        while i < len(body):
            c = body[i]
            if c == 92 and i + 1 < len(body):
                n = body[i + 1]
                if n in simple:
                    out.append(simple[n])
                    i += 2
                    continue
                if 48 <= n <= 55 and i + 3 < len(body):
                    out.append(int(body[i + 1:i + 4], 8))
                    i += 4
                    continue
            out.append(c)
            i += 1
        raw = bytes(out)
    return raw.decode("utf-8", "surrogateescape")


def added_lines(patch: bytes) -> dict[str, set[int]]:
    """{post-image path: added line numbers} from a -U0 patch (plain or combined).

    Split on LF only: bytes.splitlines() also splits on a lone CR, so an added line
    holding `\\r+++ ...` would read as a new file header and hide later hunks. Header
    lines count only between a `diff` line and the file's first hunk, so an added line
    whose text starts with `++ ` (shown as `+++ `) is content, not a header. A
    submodule pointer (mode 160000) has no content to scan and is skipped."""
    out: dict[str, set[int]] = {}
    current = None
    gitlink = False
    in_header = False
    for line in patch.split(b"\n"):
        if line.startswith((b"diff --git ", b"diff --cc ", b"diff --combined ")):
            current, gitlink, in_header = None, False, True
            continue
        # The mode is compared as a whole field: "160000" can also appear inside an
        # abbreviated blob hash on the index line, which would skip a real file.
        if in_header and line.startswith(b"index "):
            fields = line.split()
            gitlink = gitlink or (len(fields) == 3 and fields[2] == GITLINK_MODE)
            continue
        if in_header and line.startswith((b"new file mode ", b"new mode ", b"mode ")):
            gitlink = gitlink or line.split()[-1].split(b"..")[-1] == GITLINK_MODE
            continue
        if in_header and line.startswith(b"@@"):
            in_header = False
        if in_header and line.startswith(b"+++ "):
            target = line[4:]
            # git ends a header path holding a space with a tab; a path that truly holds
            # a tab is C-quoted, so a raw trailing tab is always the terminator
            if target.endswith(b"\t"):
                target = target[:-1]
            current = None if (gitlink or target == b"/dev/null") else unquote(target)
            if current is not None:
                current = current[2:] if current.startswith("b/") else current
                out.setdefault(current, set())
            continue
        if current is None:
            continue
        m = HUNK.match(line)
        if m:
            start = int(m.group(1))
            count = 1 if m.group(2) is None else int(m.group(2))
            out[current].update(range(start, start + count))
    return out


# ---------------------------------------------------------------- scanning


def display(path: str) -> str:
    """A path as it may be printed: control and non-printable characters escaped."""
    return path if path.isprintable() else repr(path)[1:-1]


def excluded(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(name, pat) for pat in EXCLUDED)


def decode(data: bytes) -> str | None:
    """Text, or None for a binary file (a NUL byte in the first 8 KB)."""
    if b"\0" in data[:8192]:
        return None
    return data.decode("utf-8", "replace")


SCANNED = [0]   # texts scanned this run, so the missing-term-list note prints only when it mattered


def scan_text(path: str, text: str, terms, consumer: str, lines: set[int] | None,
              message: bool = False) -> list[Finding]:
    """Findings for one text. lines limits them to spans touching those line numbers;
    None reports every line."""
    SCANNED[0] += 1
    hits = detect.find_message(text, terms) if message else detect.find(text, terms)
    out = []
    for h in hits:
        first, last = detect.line_of(text, h.start), detect.line_of(text, max(h.start, h.end - 1))
        if lines is not None and not any(n in lines for n in range(first, last + 1)):
            continue
        tier = detect.severity(consumer, h, path)
        if tier:
            out.append(Finding(path, first, h.cls, h.rule, tier))
    return out


def scan_blob(blobs: Blobs, rev: str, path: str, lines: set[int], terms, label: str) -> list[Finding]:
    if excluded(path) or not lines:
        return []
    data = blobs.read(rev, path)
    if data is None:
        return []
    if b"\0" in data[:8192]:
        if Path(path).suffix.lower() in BINARY_SUFFIXES:
            return []
        return [Finding(label + path, 0, "binary-skipped", "nul-byte", detect.WARN)]
    if len(data) > MAX_TEXT_BYTES:
        return [Finding(label + path, 0, "too-large", "over-1-GiB", detect.BLOCK)]
    text = decode(data) if len(data) <= FULL_SCAN_BYTES else windowed(data, lines)
    return [Finding(label + f.path, f.line, f.cls, f.rule, f.tier)
            for f in scan_text(path, text, terms, "gate", lines)]


def windowed(data: bytes, lines: set[int]) -> str:
    """The file with every line farther than WINDOW_LINES from an added line blanked, so
    line numbers still match and only the neighborhood of the change is scanned."""
    keep: set[int] = set()
    for n in lines:
        keep.update(range(n - WINDOW_LINES, n + WINDOW_LINES + 1))
    return "\n".join(part.decode("utf-8", "replace") if i in keep else ""
                     for i, part in enumerate(data.split(b"\n"), start=1))


def inbox_paths() -> list[Finding]:
    """Staged files added, changed, copied or renamed under an agent-mail inbox, by path only."""
    if os.environ.get(INBOX_BYPASS) == "1":
        return []
    names = git("diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR").split(b"\0")
    return [Finding(p, 0, "inbox", "agent-mail", detect.BLOCK)
            for p in (n.decode("utf-8", "replace") for n in names if n) if INBOX.search(p)]


def staged(terms) -> list[Finding]:
    patch = git("diff", "--cached", "-M", *DIFF_FLAGS)
    findings: list[Finding] = inbox_paths()
    blobs = Blobs()
    try:
        for path, lines in added_lines(patch).items():
            findings += scan_blob(blobs, "", path, lines, terms, "")
    finally:
        blobs.close()
    return findings


def commit_range(rev_args: list[str], terms) -> list[Finding]:
    commits = git("rev-list", "--reverse", *rev_args, "--").decode().split()
    if len(commits) > MAX_COMMITS:
        raise GitError(f"{len(commits)} commits in the range, over the {MAX_COMMITS} the gate scans; "
                       "check the history with `sanitize.py check --tracked` and push from your own terminal")
    findings: list[Finding] = []
    blobs = Blobs()
    try:
        for sha in commits:
            label = sha[:8] + ":"
            message = git("log", "-1", "--format=%B", sha).decode("utf-8", "replace")
            findings += [Finding(label + "message", f.line, f.cls, f.rule, f.tier)
                         for f in scan_text("message", message, terms, "gate", None, message=True)]
            parents = git("rev-list", "--parents", "-n", "1", sha).decode().split()[1:]
            mode = ["--cc"] if len(parents) > 1 else ["-M", "--root"]
            patch = git("diff-tree", "-p", "-r", *mode, *DIFF_FLAGS, sha)
            for path, lines in added_lines(patch).items():
                findings += scan_blob(blobs, sha, path, lines, terms, label)
    finally:
        blobs.close()
    return findings


def ref_ranges(stdin_text: str, remote: str | None) -> list[list[str]]:
    """rev-list arguments for each pre-push tuple: `<local ref> <local sha> <remote ref> <remote sha>`."""
    exclude = [f"--remotes={remote}"] if remote else ["--remotes"]
    ranges = []
    for line in stdin_text.splitlines():
        parts = line.split()
        if len(parts) != 4:
            continue
        _lref, lsha, _rref, rsha = parts
        if lsha == ZERO:
            continue                                   # a deleted ref sends nothing
        known = rsha != ZERO and subprocess.run([*GIT, "cat-file", "-e", f"{rsha}^{{commit}}"],
                                                capture_output=True).returncode == 0
        ranges.append([f"{rsha}..{lsha}"] if known else [lsha, "--not", *exclude])
    return ranges


def message_text(path: Path) -> str:
    """The message as git will record it: comment lines and everything below the
    scissors line dropped."""
    raw = path.read_text(encoding="utf-8", errors="replace")
    try:
        char = git("config", "--get", "core.commentChar").decode().strip() or "#"
    except GitError:
        char = "#"
    char = "#" if char == "auto" or len(char) != 1 else char
    kept = []
    for line in raw.splitlines():
        if line.startswith(char) and ">8" in line and "-" * 8 in line:
            break
        if not line.startswith(char):
            kept.append(line)
    return "\n".join(kept)


def repo_root() -> Path | None:
    try:
        return Path(git("rev-parse", "--show-toplevel").decode().strip())
    except GitError:
        return None


# ---------------------------------------------------------------- reporting


def report(findings: list[Finding], as_json: bool, terms_skipped: bool) -> int:
    findings = sorted(set(findings), key=lambda f: (f.path, f.line, f.cls))
    blocks = [f for f in findings if f.tier == detect.BLOCK]
    warns = [f for f in findings if f.tier != detect.BLOCK]
    if as_json:
        print(json.dumps([vars(f) for f in findings], indent=2))
    err = sys.stderr
    # Said alongside findings only, so a clean commit stays silent on a station with no list.
    if terms_skipped and SCANNED[0] and findings:
        print("sanitize gate: the station term list is not readable here, so the term check was skipped", file=err)
    if not as_json:
        for f in findings:
            what = f"{f.cls}({f.rule})" if f.cls == "invisible" else f.cls
            print(f"  {display(f.path)}:{f.line}  {what}  {f.tier}", file=err)
    if blocks:
        print(f"sanitize gate: blocked - {len(blocks)} finding(s) that must not be committed or pushed "
              "(secrets, hidden-character attacks, a message that describes sensitivity, a text file too "
              "large to check). Remove the value and try again; the value itself is never printed.", file=err)
        if any(f.cls == "inbox" for f in blocks):
            print(f"sanitize gate: agent-mail inbox files are kept out of commits. Unstage them, or, to "
                  f"commit them on purpose, run this one commit as `{INBOX_BYPASS}=1 git commit ...`; "
                  "that lifts the inbox rule only.", file=err)
        return EXIT_BLOCK
    if warns and not as_json:
        by_class: dict[str, int] = {}
        for f in warns:
            by_class[f.cls] = by_class.get(f.cls, 0) + 1
        listed = ", ".join(f"{k} {v}" for k, v in sorted(by_class.items()))
        print(f"sanitize gate: {len(warns)} warning(s) ({listed}). Check each one; if it names something "
              "real or hides content, fix it and amend before you push.", file=err)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="sanitize gate", description=__doc__.split("\n\n")[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--staged", action="store_true", help="pre-commit: added lines in the index")
    mode.add_argument("--refs", action="store_true", help="pre-push: ref tuples on stdin")
    mode.add_argument("--range", metavar="A..B", help="every commit in a revision range")
    mode.add_argument("--message", metavar="FILE", help="commit-msg: the message file")
    mode.add_argument("--files", nargs="+", metavar="PATH", help="whole files at the review tier")
    ap.add_argument("--remote", help="pre-push: the remote name git passes the hook")
    ap.add_argument("--json", action="store_true", help="print findings as JSON on stdout")
    try:
        args = ap.parse_args(argv)
    except SystemExit as exc:
        return 2 if exc.code else 0
    try:
        terms = detect.station_terms_lenient()
        terms_skipped = terms is None
        terms = set(terms or ())
        if not args.files:
            terms |= detect.project_aliases(repo_root())
        if args.staged:
            findings = staged(terms)
        elif args.refs:
            findings = []
            for rev_args in ref_ranges(sys.stdin.read(), args.remote):
                findings += commit_range(rev_args, terms)
        elif args.range:
            findings = commit_range([args.range], terms)
        elif args.message:
            text = message_text(Path(args.message))
            findings = [Finding("message", f.line, f.cls, f.rule, f.tier)
                        for f in scan_text("message", text, terms, "gate", None, message=True)]
        else:
            findings = []
            for raw in args.files:
                p = Path(raw)
                if p.stat().st_size > MAX_TEXT_BYTES:
                    findings.append(Finding(str(p), 0, "too-large", "over-1-GiB", detect.BLOCK))
                    continue
                text = decode(p.read_bytes())
                if text is not None:
                    findings += scan_text(str(p), text, terms, "review", None)
        return report(findings, args.json, terms_skipped)
    except GitError as exc:
        print(f"sanitize gate: blocked - {exc}. A step that could not read what it checks is not a "
              "clean result.", file=sys.stderr)
        return EXIT_BLOCK
    except OSError as exc:
        print(f"sanitize gate: blocked - a file could not be read ({exc.strerror or type(exc).__name__})",
              file=sys.stderr)
        return EXIT_BLOCK
    except Exception as exc:                                  # never brick every commit on a bug here
        print(f"sanitize gate: internal error ({type(exc).__name__}); this commit was not checked",
              file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
