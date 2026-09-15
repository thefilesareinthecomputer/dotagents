#!/usr/bin/env python3
"""PreToolUse hook: refuse a commit message that describes sensitive material.

A commit message is permanent, searchable, and never scrubbed. Removing an identifier
from a file while the commit says what was removed leaves a signpost that is worse than
the original: it names the category, points at the files, and dates the window, and no
file-level scan or later edit reaches it.

This blocks the `git commit` before it lands. Two classes:

  DISCLOSURE  the message describes the sensitivity rather than the change - "scrub",
              "sanitize", "redact", "leaked", "private aliases", "identifiers removed"
  IDENTIFIER  the message contains the thing itself - an alias, a work-item id, a
              person's initials with a role code, an environment-prefixed catalog

Say what changed, not why it was sensitive. "Generalize skill examples and paths for
packaging" carries the same meaning to a future reader with none of the signposting; the
rationale belongs in the private tracker, not in the object that ships with the code.

On any internal error the hook allows the commit and says so, rather than blocking every
commit on a bug of its own.
"""
import importlib.util
import json
import os
import pathlib
import re
import shlex
import sys

# One matcher for both gates: the term list, the alias edge and case rules, the
# synthetic-ID rule and the no-echo report all live in the write-time hook.
_spec = importlib.util.spec_from_file_location(
    "reject_identifiers", pathlib.Path(__file__).with_name("reject_identifiers.py"))
shared = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(shared)

# Scope: this hook inspects ONE thing, the message of a `git commit` this command runs.
# Every other Bash call exits 0 immediately. The tool matcher can only key on tool name,
# so the narrowing to commits happens here in `_is_git_commit`.

DISCLOSURE = re.compile(
    r"\b("
    r"scrub(bed|bing|s)?|saniti[sz](e|ed|ing|ation)|redact(ed|ing|ion)?|"
    r"leak(ed|ing|s|age)?|expos(ed|ure|ing)|de-?identif\w*|anonymi[sz]\w*|"
    r"identifiers?\s+(removed|stripped|cleared|out)|"
    r"(private|client|project)\s+(alias|aliases|identifiers?|names?|data)|"
    r"real\s+(incident|incidents|names?|people|dates?)|"
    r"person(al)?\s+(initials|identifiers?)|work-?item\s+identifiers?"
    r")\b",
    re.I,
)
PLACEHOLDER = {
    "poc", "alias", "project", "vault", "name", "out", "x", "y", "v", "id",
    "acme", "test", "example", "sample", "foo", "bar", "contoso", "client",
    "certs", "drafts", "shared", "common", "archive", "templates",
}
IDENTIFIER = (
    (re.compile(r"\b[A-Z]{1,4}\s*\((?:DE|DA|ITL|BA|PM|QA|SA|SO)\d+\)"),
     "a person's initials with a role code"),
    (re.compile(r"\b(?:prod|uat|dev|stg)[-_]?(?:bronze|silver|gold|raw|landing)\b", re.I),
     "an environment-prefixed catalog name"),
    (re.compile(r"(?:PROJECTS/)?[\w]+[-_](?:OKF|ENRICH|STAGING|PREV)\b"),
     "a project folder-naming convention"),
)


def aliases(cwd):
    """Subjects from the repo's own PROJECTS/ folders, so a new project needs no edit."""
    found = set()
    try:
        base = pathlib.Path(cwd) / "PROJECTS"
        if not base.is_dir():
            return found
        for child in base.iterdir():
            if not child.is_dir():
                continue
            low = child.name.lower()
            if not any(s in low for s in ("-okf", "-enrich", "-staging", "-prev")):
                continue
            head = re.split(r"[-_]", child.name, maxsplit=1)[0]
            if len(head) >= 2 and not head.isdigit() and head.lower() not in PLACEHOLDER:
                found.add(head)
    except OSError:
        pass
    return found


def _is_git_commit(segment):
    """Whether this shell segment actually RUNS `git commit`.

    Keyed on the command being invoked, never on the string appearing somewhere in the
    line. `python3 - <<PY ... git commit -m "..." ... PY` runs python, not git, and a
    grep for the word `commit` runs grep. Matching those is the difference between a
    guard and an obstacle."""
    try:
        tokens = shlex.split(segment, posix=True)
    except ValueError:
        tokens = segment.split()
    while tokens and ("=" in tokens[0] and not tokens[0].startswith("-")):
        tokens = tokens[1:]                       # strip leading VAR=value assignments
    if not tokens:
        return False
    if pathlib.PurePath(tokens[0]).name != "git":
        return False
    for tok in tokens[1:]:
        if tok == "commit":
            return True
        if tok in ("-C", "--git-dir", "--work-tree", "-c"):
            continue
        if tok.startswith("-") or "/" in tok or "=" in tok:
            continue
        return False                              # some other subcommand
    return False


def message_of(command):
    """The commit message text, from -m/-F or a heredoc body. Empty when none is inline,
    which is the editor path and cannot be inspected here."""
    segments = [s for s in re.split(r"(?:\|\||&&|[;|])", command) if s.strip()]
    if not any(_is_git_commit(s) for s in segments):
        return ""
    chunks = []
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        tokens = []
    for i, tok in enumerate(tokens):
        # -m, --message, and a short-flag cluster ending in m such as -am or -qm.
        cluster = tok.startswith("-") and not tok.startswith("--") and len(tok) > 2 and tok.endswith("m")
        if (tok in ("-m", "--message") or cluster) and i + 1 < len(tokens):
            chunks.append(tokens[i + 1])
        elif tok.startswith("--message="):
            chunks.append(tok.split("=", 1)[1])
    # A heredoc body is not a shell token; take everything after the delimiter.
    here = re.search(r"<<-?\s*'?([A-Za-z_]\w*)'?\s*\n(.*?)\n\1", command, re.S)
    if here:
        chunks.append(here.group(2))
    return "\n".join(chunks)


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    try:
        if payload.get("tool_name") != "Bash":
            return 0
        command = (payload.get("tool_input") or {}).get("command", "")
        if not isinstance(command, str):
            return 0
        text = message_of(command)
        if not text.strip():
            return 0
        hits = []
        for match in DISCLOSURE.finditer(text):
            hits.append((match.group(0), "describes the sensitivity, not the change",
                         match.start()))
        for regex, why in IDENTIFIER:
            for match in regex.finditer(text):
                hits.append((match.group(0), why, match.start()))
        for match in shared.WORK_ITEM_RE.finditer(text):
            if not shared.synthetic(match.group(1)):
                hits.append((match.group(0), shared.WORK_ITEM_WHY, match.start()))
        # The station term list plus this repo's PROJECTS/ folders, matched exactly
        # as the write-time hook matches them.
        hits.extend(shared.alias_hits(text, shared.station_terms() | aliases(os.getcwd())))
        if not hits:
            return 0
    except Exception as exc:
        print(f"reject_bad_commit_message error, commit allowed: {exc}",
              file=sys.stderr)
        return 0

    # Reason, line and length only. A refused message must not be quoted back, or
    # the refusal itself becomes the disclosure.
    detail = shared.describe(hits, text)
    print(
        "commit message refused:\n  " + "; ".join(detail[:8])
        + ("; ..." if len(detail) > 8 else "")
        + "\n\nA commit message is permanent, searchable and never scrubbed. One that "
        "names what was removed is a signpost: it gives the category, the files and the "
        "date window, and no later edit reaches it.\n"
        "Say what changed, not why it was sensitive. 'Generalize skill examples and paths "
        "for packaging' reads the same to a future maintainer and points at nothing. Keep "
        "the rationale in the private tracker.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
