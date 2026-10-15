#!/usr/bin/env python3
"""PreToolUse hook: surface project identifiers in NEW content written to portable files.

A skill, a certification and a research artifact all travel further than the vault they
are written in: a skill gets copied, a certification feeds a merge into canon, and git
history keeps what a later edit removes from the tree. A check that runs at publish time
therefore runs too late to help, because by then the identifier is already committed.

So the check is at the write, not at the exit. It never blocks: every hit is returned to
the model as PreToolUse `additionalContext` and the write proceeds, so the model (or the
user, in place) decides whether the value is a leak or a legitimate word. A gate that
refuses ordinary prose because a term is also a dictionary word gets muted, and a muted
gate is worse than none.

GUARDED PATHS (portable or canon-bound; identifiers must never enter these):
    **/.claude/skills/**      **/.agents/skills/**    ~/.claude/hooks/**
    **/_RESEARCH/**           **/LEARNING/**          **/KNOWLEDGE-BASE/**
    **/.claude/tools/**       **/.claude/agents/**    **/.claude/commands/**
    **/specs/**               (seed copies of the files above)

UNGUARDED (identifiers belong here and are not the model's to strip):
    PROJECTS/**   tasks/**   DRAFTS/**   _PROJECTS/**   notes-*.md   anything else

WHAT IS SURFACED (never blocked)
    a project alias, from the station term list (~/.claude/private/identifier-terms.txt,
      gitignored, one term per line) plus the PROJECTS/ folder names of the target's
      own repo where it has any. Whole word. A term written in mixed case matches
      exactly as typed, so "Widget" never fires on "widget"; a term written all upper
      or all lower matches any capitalization.
    a person's initials with a role code, `AB (ROLE1)` in shape
    an environment-prefixed catalog: an environment name joined to a medallion
      layer as one word
    a work-item id, `STORY-000001` in shape, whose digits are not a synthetic run.
      NNNNnn, repdigits, consecutive runs and zero-padded counters are fixtures and
      pass silently; EPIC-/FEATURE-/STORY- are universal agile terms. Shape cannot
      tell a real tracker number from a made-up one, so the model judges.

    The examples above are deliberately synthetic. A detector's own documentation
    is the easiest place for a real value to hide, because nobody reads a rule
    table looking for the thing the rule describes.

Only NEW content is checked (Write content, Edit/MultiEdit new_string, NotebookEdit
new_source). old_string is exempt: matching bytes already on disk requires reproducing
them, and this hook must never make an existing identifier unremovable.

Always exits 0. A finding is printed as a PreToolUse `additionalContext` payload,
which the model sees while the write proceeds. On any internal error the hook stays
silent apart from a stderr note, so it can never brick editing.
"""
import json
import os
import pathlib
import re
import sys

GUARDED = (
    ("/.claude/skills/",), ("/.agents/skills/",), ("/.claude/hooks/",),
    ("/.claude/tools/",), ("/.claude/agents/",), ("/.claude/commands/",),
    ("/_RESEARCH/",), ("/LEARNING/",), ("/KNOWLEDGE-BASE/",),
    # A station spec carries the seed copies of the files above. The live hook
    # under ~/.claude/hooks/ was guarded and its published twin was not, so the
    # same bytes were checked in one location and unchecked in the other.
    ("/specs/",),
)
# Checked before GUARDED. A project workspace legitimately holds identifiers even when
# it sits under a guarded-looking path.
EXEMPT = ("/PROJECTS/", "/_PROJECTS/", "/tasks/", "/DRAFTS/", "/__archive/")

PLACEHOLDER = {
    "poc", "alias", "project", "vault", "name", "out", "x", "y", "v", "id",
    "acme", "test", "example", "sample", "foo", "bar", "contoso", "client",
    "certs", "drafts", "shared", "common", "archive", "templates",
}

PATTERNS = (
    (re.compile(r"\b[A-Z]{1,4}\s*\((?:DE|DA|ITL|BA|PM|QA|SA|SO)\d+\)"),
     "a person's initials with a role code"),
    (re.compile(r"\b(?:prod|uat|dev|test|stg)[-_]?(?:bronze|silver|gold|raw|landing)\b",
                re.I),
     "an environment-prefixed catalog name"),
)

# Handled apart from PATTERNS because the digits decide it, not the shape, and
# because the verdict is advisory. A skill whose subject IS work items has to be
# able to write the form, and no test can say which six-digit values are real.
WORK_ITEM_RE = re.compile(r"\b(?:STORY|TASK|BUG|FEATURE|EPIC|DEF)[-_](\d{3,})\b", re.I)
WORK_ITEM_WHY = "a work-item identifier that is not a synthetic run"


def synthetic(digits):
    """True for a run no tracker would issue: every digit the same, a consecutive
    ascending or descending run, or a zero-padded counter under three digits."""
    if len(set(digits)) == 1:
        return True
    stripped = digits.lstrip("0")
    if stripped != digits and len(stripped) <= 2:
        return True
    seq = [int(c) for c in digits]
    steps = {b - a for a, b in zip(seq, seq[1:])}
    return steps in ({1}, {-1})


def repo_of(path):
    for parent in [path] + list(path.parents):
        if (parent / ".git").exists():
            return parent
    return None


# The station's own term list: one identifier per line, `#` comments allowed, never
# committed (gitignored under private/). This is what makes the alias rule work in a
# repo that holds no PROJECTS/ folder of its own, such as the shared skills repo.
TERMS_FILE = pathlib.Path(os.environ.get("IDENTIFIER_TERMS_FILE")
                          or pathlib.Path.home() / ".claude" / "private" / "identifier-terms.txt")
# Paths this hook always checks, whatever else is guarded: itself and the list.
SELF_GUARDED = ("/hooks/reject_identifiers.py", "/private/identifier-terms.txt")


def is_comment(line):
    """A comment is `#` followed by a space, or a bare `#`. `#tag` is a term."""
    s = line.strip()
    return s == "#" or s.startswith("# ")


def station_terms():
    try:
        lines = TERMS_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return set()
    return {ln.strip() for ln in lines if ln.strip() and not is_comment(ln)}


def aliases_for(path):
    """The station term list, plus subjects derived from the target repo's own
    PROJECTS/ folders where it has any. Only engagement-shaped folders count: one
    carrying a vault suffix, whose head is not a generic stand-in."""
    found = station_terms()
    repo = repo_of(path)
    if not repo:
        return found
    projects = repo / "PROJECTS"
    if not projects.is_dir():
        return found
    for child in projects.iterdir():
        if not child.is_dir():
            continue
        low = child.name.lower()
        if not any(s in low for s in ("-okf", "-enrich", "-staging", "-prev")):
            continue
        head = re.split(r"[-_]", child.name, maxsplit=1)[0]
        if len(head) >= 2 and not head.isdigit() and head.lower() not in PLACEHOLDER:
            found.add(head)
    return found


def guarded(path_str):
    normalized = path_str.replace(os.sep, "/")
    if not normalized.startswith("/"):
        normalized = "/" + normalized
    # The detector and its list are guarded first and unconditionally: a term written
    # into this file's comments, or into the list's header, is the same leak in the
    # one place a scrub never looks.
    if normalized.endswith(SELF_GUARDED):
        return True
    if any(marker in normalized for marker in EXEMPT):
        return False
    return any(marker in normalized for group in GUARDED for marker in group)


def self_text(target, text):
    """For a write to the term list, check only its comment lines; the entries ARE
    the terms. For any other target, check the text as given."""
    normalized = str(target).replace(os.sep, "/")
    if normalized.endswith(SELF_GUARDED[1]):
        return "\n".join(ln for ln in text.splitlines() if is_comment(ln))
    return text


def findings(text, aliases):
    """(matched value, reason) pairs. Callers that talk to the model report the
    reason and the position, never the value: the list is not the model's to read."""
    hits = []
    for regex, why in PATTERNS:
        for match in regex.finditer(text):
            hits.append((match.group(0), why, match.start()))
    for match in WORK_ITEM_RE.finditer(text):
        if not synthetic(match.group(1)):
            hits.append((match.group(0), WORK_ITEM_WHY, match.start()))
    hits.extend(alias_hits(text, aliases))
    return hits


def alias_hits(text, aliases):
    """(value, reason, start) for every term-list alias in text. Shared by the
    commit-message hook, so both gates match the same way.

    A single-case term matches any capitalization; a mixed-case term matches exactly
    as typed, because its case is its identity and the folded form is usually an
    ordinary word. Spacing inside a term is matched as written. Edges are "no word
    character on either side" rather than \\b, so a term that starts or ends with a
    symbol (#tag, @handle, sup#) still matches as a whole token."""
    out = []
    for alias in sorted(aliases):
        flags = re.I if (alias == alias.upper() or alias == alias.lower()) else 0
        pattern = r"(?<!\w)" + re.escape(alias) + r"(?!\w)"
        for match in re.finditer(pattern, text, flags):
            out.append((match.group(0), "a project alias", match.start()))
    return out


def describe(hits, scanned):
    """Human-readable hit list that never carries a matched value: reason, line in
    the scanned text, and length. The model wrote the text, so that locates it."""
    seen, out = set(), []
    for value, why, pos in hits:
        if value in seen:
            continue
        seen.add(value)
        lineno = scanned.count("\n", 0, pos) + 1
        out.append(f"{why}, line {lineno}, {len(value)} chars")
    return out


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    try:
        ti = payload.get("tool_input", {}) or {}
        tool = payload.get("tool_name", "")
        if tool == "Write":
            text = ti.get("content", "")
        elif tool == "Edit":
            text = ti.get("new_string", "")
        elif tool == "NotebookEdit":
            text = ti.get("new_source", "")
        elif tool == "MultiEdit":
            edits = ti.get("edits", [])
            text = "\n".join(e.get("new_string", "") for e in edits
                             if isinstance(e, dict)) if isinstance(edits, list) else ""
        else:
            return 0
        target = ti.get("file_path") or ti.get("notebook_path") or ""
        if not isinstance(text, str) or not text or not target:
            return 0
        if not guarded(str(target)):
            return 0
        path = pathlib.Path(target).expanduser()
        scanned = self_text(target, text)
        hits = findings(scanned, aliases_for(path))
        if not hits:
            return 0
    except Exception as exc:                                  # never brick editing
        print(f"reject_identifiers hook error, write allowed: {exc}", file=sys.stderr)
        return 0

    # Report where and why, never what.
    detail = describe(hits, scanned)

    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "additionalContext": (
            "IDENTIFIER CHECK (write allowed) on a file that travels: "
            f"{target}. Hits: {'; '.join(detail[:8])}{' ...' if len(detail) > 8 else ''}. "
            "Judge each one: if it is a private project, client or person identifier, "
            "or a real tracker number, replace it now with a role description or a "
            "synthetic stand-in, or move the content under PROJECTS/ or tasks/. If it "
            "is an ordinary word or a fixture, leave it and say so in one line to the "
            "user. Do not quote the token back.")}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
