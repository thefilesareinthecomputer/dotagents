#!/usr/bin/env python3
"""PreToolUse(Write|Edit|MultiEdit|NotebookEdit) - deny a doc-file write that
ADDS a word from reject-words.toml, and steer the rewrite. GLOBAL.

The list is grouped into categories. Each category names its words, why they
are rejected, what to write instead, and optionally the question that separates
a legitimate use. The deny reason hands all of that to the agent, so a hit says
what to write rather than only refusing.

Scope: doc files only (DOC_SUFFIXES); code is never checked. A word joined to
others by a hyphen or underscore is part of a name, slug or identifier and is
ignored. A word inside a fenced block, a code span or double quotes is being
named rather than used, and is ignored.

Only new occurrences count. The incoming text is compared with the text it
replaces (Edit old_string, or the current file for Write), so keeping or
removing an existing occurrence never fires.

A legitimate use gets through by resubmitting the identical write: the first
deny records a hash of the path and incoming text for the session, and the
matching retry is allowed once.

A file that is somebody else's text verbatim (a quoted source, a transcript)
is exempt as a whole when its YAML frontmatter `tags` holds one of the tags the
list's `[exempt]` table names. The frontmatter is read from the file on disk
when one exists and from the incoming content only for a new file, so the tag
cannot arrive in the same write as the word; a tag anywhere else in the file
does not count.

List location: reject-words.toml beside this script, or REJECT_WORDS_FILE.
Fail-open: a garbage payload, a missing or unparseable list, or an unwritable
state dir allows the write.
"""
import hashlib
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

DOC_SUFFIXES = (".md", ".mdx", ".markdown", ".txt", ".rst")
FENCE = re.compile(r"^[ \t]*(`{3,}|~{3,}).*?^[ \t]*\1", re.MULTILINE | re.DOTALL)
CODE_SPAN = re.compile(r"`[^`\n]*`")
QUOTED = re.compile(r"[\"“][^\"”\n]*[\"”]")

# Sites that quote the words on purpose: the hooks and their tests, fixtures,
# and the slop catalog.
EXEMPT = ("/hooks/", "/tests/", "/fixtures/", "/skills/ai-slop-magic-eraser/")


def list_path():
    env = os.environ.get("REJECT_WORDS_FILE")
    return Path(env) if env else Path(__file__).resolve().with_name("reject-words.toml")


def load_categories(path):
    """Return [(name, compiled pattern, spec dict)]; [] on any problem,
    including a python3 older than 3.11, which has no tomllib."""
    try:
        import tomllib
        data = tomllib.loads(Path(path).read_text())
    except (ImportError, OSError, ValueError):
        return []
    cats = []
    for name, spec in data.items():
        if not isinstance(spec, dict) or not isinstance(spec.get("words"), list):
            continue
        words = [w for w in spec["words"] if isinstance(w, str) and w.strip()]
        if not words:
            continue
        alts = "|".join(
            r"\s+".join(map(re.escape, w.split()))
            for w in sorted(words, key=len, reverse=True)
        )
        pattern = re.compile(rf"(?<![\w-])({alts})(?![\w-])", re.IGNORECASE)
        cats.append((name, pattern, spec))
    return cats


def exempt_tags(path):
    """The [exempt] table's tags list; () when absent or malformed."""
    try:
        import tomllib
        data = tomllib.loads(Path(path).read_text())
        tags = (data.get("exempt") or {}).get("tags")
        return tuple(t.strip().lower() for t in tags if isinstance(t, str) and t.strip()) if isinstance(tags, list) else ()
    except (ImportError, OSError, ValueError, AttributeError):
        return ()


FRONTMATTER = re.compile("\\A\ufeff?---[ \\t]*\\r?\\n(.*?)\\r?\\n---[ \\t]*(?:\\r?\\n|\\Z)", re.DOTALL)


def frontmatter_tags(text):
    """Lowercased values of a frontmatter `tags` key: inline list, bare
    scalar, or block list. Plain YAML shapes only, no parser."""
    m = FRONTMATTER.match(text)
    if not m:
        return set()
    lines = m.group(1).splitlines()
    found = set()
    for i, line in enumerate(lines):
        km = re.match(r"^tags:[ \t]*(.*?)[ \t]*$", line)
        if not km:
            continue
        inline = km.group(1)
        if inline:
            found.update(re.findall(r"[^\s,\[\]\"']+", inline))
        else:
            for nxt in lines[i + 1:]:
                lm = re.match(r"^[ \t]+-[ \t]*(.+?)[ \t]*$", nxt)
                if not lm:
                    break
                found.add(lm.group(1).strip("\"'"))
        break
    return {t.lower() for t in found}


def is_exempt(tool_input, new, tags):
    """True when the file's frontmatter names an exempt tag. The tag is read
    from the file on disk whenever one exists, and from the incoming content
    only for a file being created, so a tag cannot be added to an authored
    document in the same write that adds a rejected word."""
    if not tags:
        return False
    p = Path(tool_input.get("file_path") or "")
    try:
        exists = p.is_file()
    except OSError:
        return False
    if exists:
        try:
            with p.open(encoding="utf-8", errors="replace") as f:
                text = f.read(8192)
        except OSError:
            return False
    else:
        text = new if "content" in tool_input else ""
    return bool(frontmatter_tags(text) & set(tags))


def strip_named(text):
    """Remove fenced blocks, code spans and double-quoted spans."""
    return QUOTED.sub("", CODE_SPAN.sub("", FENCE.sub("", text)))


def hits(text, cats):
    """Counter of (category, word) for every use outside named spans."""
    clean = strip_named(text)
    found = Counter()
    for name, pattern, _ in cats:
        for m in pattern.findall(clean):
            found[(name, " ".join(m.lower().split()))] += 1
    return found


def incoming_and_replaced(tool_input):
    """Return (new text, text it replaces) for the tool call."""
    ti = tool_input
    if "content" in ti:
        old = ""
        path = Path(ti.get("file_path") or "")
        try:
            if path.is_file():
                old = path.read_text(errors="replace")
        except OSError:
            pass
        return ti.get("content") or "", old
    if "edits" in ti:
        edits = ti.get("edits") or []
        return (
            "\n".join(e.get("new_string") or "" for e in edits),
            "\n".join(e.get("old_string") or "" for e in edits),
        )
    if "new_string" in ti:
        return ti.get("new_string") or "", ti.get("old_string") or ""
    return ti.get("new_source") or "", ""


def state_dir(session):
    """One directory per session; "." is excluded so no component is . or .."""
    sid = re.sub(r"[^A-Za-z0-9_-]", "", session or "") or "nosession"
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "reject-words" / sid


def seen_before(session, digest):
    """True if this exact write was already denied once; consumes the marker.
    unlink never follows a symlink, so a planted link only removes itself."""
    try:
        os.unlink(state_dir(session) / digest)
        return True
    except OSError:
        return False


def remember(session, digest):
    """Record the deny as an empty marker file. Never writes through a symlink.
    False means the retry escape cannot work, and the caller allows instead."""
    d = state_dir(session)
    try:
        d.mkdir(parents=True, exist_ok=True, mode=0o700)
    except OSError:
        return False
    if d.is_symlink() or not d.is_dir():
        return False
    try:
        fd = os.open(d / digest, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        os.close(fd)
        return True
    except FileExistsError:
        return True
    except OSError:
        return False


def reason(added, cats, filename):
    """One steer block per category hit, in list order."""
    specs = {name: spec for name, _, spec in cats}
    blocks = []
    for name, _, _ in cats:
        words = sorted(w for (c, w) in added if c == name)
        if not words:
            continue
        spec = specs[name]
        quoted = ", ".join(f'"{w}"' for w in words)
        parts = [f"{quoted} [{name}]."]
        if spec.get("why"):
            parts.append(f"Why: {spec['why']}")
        if spec.get("instead"):
            parts.append(f"Instead: {spec['instead']}")
        if spec.get("ask"):
            parts.append(spec["ask"])
        blocks.append(" ".join(parts))
    return (
        f"Rejected words in {filename}. " + " | ".join(blocks)
        + " If a use is the legitimate exception, resubmit the same write unchanged."
    )


def main():
    try:
        return check(json.loads(sys.stdin.read()))
    except Exception:                                 # never brick editing
        return 0


def check(payload):
    tool_input = payload.get("tool_input") or {}
    path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    if not path.lower().endswith(DOC_SUFFIXES) or any(p in path for p in EXEMPT):
        return 0
    cats = load_categories(list_path())
    if not cats:
        return 0

    new, old = incoming_and_replaced(tool_input)
    if is_exempt(tool_input, new, exempt_tags(list_path())):
        return 0
    added = hits(new, cats) - hits(old, cats)
    if not added:
        return 0

    session = payload.get("session_id") or ""
    digest = hashlib.sha256(f"{path}\0{new}".encode()).hexdigest()
    if seen_before(session, digest) or not remember(session, digest):
        return 0

    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason(added, cats, Path(path).name),
    }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
