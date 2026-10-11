"""File-per-thread conversation store. STORY-000033 (FEATURE-000032, M4 prereq).

One JSON file per thread in config.data_path()/conversations/, shaped:
  {id, title, created_at, updated_at,
   turns: [{role, content, timestamp}],
   claude_session_id}   # Claude Code lane only - binds the thread to its
                        # persistent session (spec R28: one conversation =
                        # one session; --resume uses this id every turn)

Endpoint contract (spec, HTTP API table; routes wire up in app.py):
  GET    /conversations?limit=&offset=  -> list + X-Total-Count header
  POST   /conversations                 -> {id}
  GET    /conversations/{id}            -> {id, title, turns}   (404 unknown)
  DELETE /conversations/{id}            -> {status: "ok"}       (404 unknown)

Rules from the board's acceptance criteria:
  - title auto-set from the first user message's text
  - list is newest-first, sliced by limit/offset, header carries the total
  - deleting removes the file; unknown ids 404 rather than erroring
Token usage per turn persists here too (STORY-000037 writes it).
"""

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from second_brain import config

_TITLE_MAX = 60


def conversations_dir() -> Path:
    directory = config.data_path() / "conversations"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _file(conversation_id: str) -> Path:
    # Ids are generated hex, but the value arrives from a URL path segment;
    # anything that could leave the directory is treated as unknown.
    if not conversation_id or "/" in conversation_id or "\\" in conversation_id \
            or ".." in conversation_id or conversation_id.startswith("."):
        raise FileNotFoundError(conversation_id)
    return conversations_dir() / f"{conversation_id}.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write(data: dict) -> None:
    _file(data["id"]).write_text(json.dumps(data, indent=1))


def create() -> dict:
    data = {
        "id": uuid.uuid4().hex,
        "title": "",
        "created_at": _now(),
        "updated_at": _now(),
        "turns": [],
    }
    _write(data)
    return data


def read(conversation_id: str) -> dict:
    """Raises FileNotFoundError for an unknown id (route maps to 404)."""
    path = _file(conversation_id)
    if not path.is_file():
        raise FileNotFoundError(conversation_id)
    return json.loads(path.read_text())


def listing(limit: int | None = None, offset: int = 0) -> tuple[list[dict], int]:
    """Returns (page, total), newest-first. Total feeds X-Total-Count.
    limit None means the full list (the UI omits limit when expanded)."""
    threads = [json.loads(path.read_text())
               for path in conversations_dir().glob("*.json")]
    threads.sort(key=lambda t: t.get("updated_at", ""), reverse=True)
    total = len(threads)
    end = None if limit is None else offset + limit
    return threads[offset:end], total


def delete(conversation_id: str) -> None:
    path = _file(conversation_id)
    if not path.is_file():
        raise FileNotFoundError(conversation_id)
    path.unlink()


# Invisible and direction-control codepoints an agent reply could use to
# smuggle text past the user's eyes into the store - and from there into
# every other seat's prompt: Unicode tag-block ASCII smuggling, zero-width
# joiners, bidi overrides, raw terminal controls. Stripped from every
# non-user turn at persistence, the one choke point both lanes and the
# group loop write through; the strip count survives on the turn as
# `sanitized`. Tab and LF are structure, not smuggling, and survive, as
# does every visible codepoint - markdown, code fences, CJK, Arabic,
# box-drawing, math, emoji base glyphs. Known lossy by design: emoji
# composed with ZWJ or variation selectors degrade to their base glyphs,
# because the joiner is the smuggling channel. Ranges are built with
# chr() because this repo's own tooling refuses literal invisibles in
# source files.
_INVISIBLE_RANGES = (
    (0x00, 0x08), (0x0B, 0x1F), (0x7F, 0x7F),   # raw controls incl. CR, ESC
    (0xAD, 0xAD),                                # soft hyphen
    (0x061C, 0x061C),                            # arabic letter mark
    (0x115F, 0x1160), (0x3164, 0x3164),          # hangul fillers
    (0x180E, 0x180E),                            # mongolian vowel separator
    (0x200B, 0x200F),                            # zero-widths, LRM/RLM
    (0x2028, 0x2029),                            # line/paragraph separators
    (0x202A, 0x202E),                            # bidi embeddings/overrides
    (0x2060, 0x2065),                            # word joiner, invisibles
    (0x2066, 0x206F),                            # bidi isolates + deprecated
    (0xFE00, 0xFE0F),                            # variation selectors
    (0xFEFF, 0xFEFF),                            # BOM / zw no-break space
    (0xFFF9, 0xFFFB),                            # interlinear annotation
    (0x1D173, 0x1D17A),                          # musical format controls
    (0xE0000, 0xE007F),                          # tag block (ASCII smuggling)
    (0xE0100, 0xE01EF),                          # variation selectors suppl.
)
_INVISIBLE_RE = re.compile("[" + "".join(
    re.escape(chr(lo)) + "-" + re.escape(chr(hi)) if lo != hi
    else re.escape(chr(lo))
    for lo, hi in _INVISIBLE_RANGES) + "]")


def _strip_invisibles(text: str) -> tuple[str, int]:
    """Remove smuggling-capable invisibles; returns (clean, count)."""
    cleaned, count = _INVISIBLE_RE.subn("", text or "")
    return cleaned, count


def append_turn(conversation_id: str, role: str, content: str,
                speaker: str | None = None, passed: bool = False,
                denials: list[dict] | None = None,
                manifest: dict | None = None,
                warnings: list[str] | None = None) -> None:
    """First user turn also sets the title.

    Group chat (SPEC-GROUP-CHAT-V1 G2): `speaker` tags a turn with a seat
    id (or "user"); `passed` marks a seat's PASS. `denials` records the
    refused tool calls of the turn, attributed to their source (chat
    `denied` frames), and `warnings` the harness's own stderr for the
    turn (chat `warnings` frames). All absent = legacy two-party turn,
    unchanged on disk.
    """
    data = read(conversation_id)
    if role != "user":
        content, stripped = _strip_invisibles(content)
        # The sibling fields persist agent-authored text too: warnings is
        # the child harness's stderr, and a denial's rule can quote the
        # seat workspace's own settings file. Same wash, counts discarded.
        if warnings:
            warnings = [_strip_invisibles(w)[0] for w in warnings]
        if denials:
            denials = [{k: _strip_invisibles(v)[0] if isinstance(v, str)
                        else v for k, v in entry.items()}
                       for entry in denials]
    else:
        stripped = 0
    turn: dict = {"role": role, "content": content, "timestamp": _now()}
    if stripped:
        turn["sanitized"] = stripped
    if speaker is not None:
        turn["speaker"] = speaker
    if passed:
        turn["passed"] = True
    if denials:
        turn["denials"] = list(denials)
    if warnings:
        turn["warnings"] = list(warnings)
    if manifest:
        turn["manifest"] = dict(manifest)
    data["turns"].append(turn)
    if role == "user" and not data["title"]:
        title = " ".join(content.split())
        data["title"] = title[:_TITLE_MAX]
    data["updated_at"] = _now()
    _write(data)


# --- participants (SPEC-GROUP-CHAT-V1 G1; a conversation without any
# stays legacy two-party) ---

_REPO_ROOT = Path(__file__).resolve().parents[2]


def slug(name: str) -> str:
    """Seat-id slug for a display name; also how @-mentions match roster
    names (group.resolve_mentions), so the two must never diverge."""
    return "".join(ch for ch in name.lower().replace(" ", "-")
                   if ch.isalnum() or ch == "-") or "seat"


# The main agent answers to these; never a seat id (group.resolve_mentions).
MAIN_ALIASES = frozenset({"main", "brain", "b", "2b", "b2", "second-brain"})

# Speaker ids the app itself uses to frame turns. A seat whose id slugged
# to one of these would render as `[user]: ...` in every other seat's
# prompt, which the AUTHORIZATION text treats as the user's own turn
# (security review 2026-09-03). The main aliases are NOT reserved: the
# orchestrator seat is deliberately seated as "B" (group.resolve_mentions).
RESERVED_SPEAKERS = frozenset({"user", "system"})


def add_participant(conversation_id: str, name: str, cwd: str,
                    harness: str = "claude", model: str = "",
                    effort: str = "", readonly: bool = False,
                    rules_source_writable: bool = False) -> dict:
    """Seat a participant; returns the stored seat. Ids are short slugs
    derived from the name, uniqued within the conversation. readonly
    marks a seat that may only read (file tools and shell denied at
    spawn), one of the two ways a rules-source directory can be seated.
    rules_source_writable is the other, and comes from the roster file
    alone: it admits the shared skills repo as a writable seat in its
    own repo (chat.assert_seat_root).

    Continuity rule (advisor audit 2026-08-27): the FIRST claude seat in
    this repo inherits the conversation's two-party session and has seen
    the whole thread - converting to group must not cost the main agent
    its accumulated context.
    """
    base = slug(name)
    if base in RESERVED_SPEAKERS:
        raise ValueError(f"{name!r} is a reserved speaker name")
    data = read(conversation_id)
    seats = data.setdefault("participants", [])
    inherit = (not seats and harness == "claude"
               and data.get("claude_session_id")
               and Path(cwd).resolve() == _REPO_ROOT)
    seat_id = base
    taken = {seat["id"] for seat in seats}
    counter = 2
    while seat_id in taken:
        seat_id = f"{base}-{counter}"
        counter += 1
    seat = {"id": seat_id, "name": name, "cwd": cwd, "harness": harness,
            "model": model, "effort": effort, "readonly": bool(readonly),
            "rules_source_writable": bool(rules_source_writable),
            "session_id": data["claude_session_id"] if inherit else "",
            "cursor": len(data["turns"]) if inherit else 0}
    seats.append(seat)
    data["updated_at"] = _now()
    _write(data)
    return seat


def update_participant(conversation_id: str, seat_id: str,
                       fields: dict) -> None:
    """Merge fields (session_id, cursor) into one seat; unknown seat ids
    raise KeyError so a caller bug never writes a ghost seat."""
    data = read(conversation_id)
    for seat in data.get("participants", []):
        if seat["id"] == seat_id:
            seat.update(fields)
            data["updated_at"] = _now()
            _write(data)
            return
    raise KeyError(seat_id)


def rewrite_turn(conversation_id: str, index: int, content: str,
                 passed: bool = False) -> None:
    """Replace one turn's content (group loop: a literal PASS reply
    becomes a passed-flag chip turn)."""
    data = read(conversation_id)
    turn = data["turns"][index]
    turn["content"] = content
    if passed:
        turn["passed"] = True
    data["updated_at"] = _now()
    _write(data)


def remove_participant(conversation_id: str, seat_id: str) -> None:
    data = read(conversation_id)
    seats = data.get("participants", [])
    kept = [seat for seat in seats if seat["id"] != seat_id]
    if len(kept) == len(seats):
        raise KeyError(seat_id)
    data["participants"] = kept
    data["updated_at"] = _now()
    _write(data)


def update(conversation_id: str, fields: dict) -> None:
    """Merge fields (claude_session_id, token_usage) into the thread file."""
    data = read(conversation_id)
    data.update(fields)
    data["updated_at"] = _now()
    _write(data)
